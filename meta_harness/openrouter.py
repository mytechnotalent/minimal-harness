"""Minimal OpenRouter client for agent calls."""

import json
import os
import signal
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any
from urllib.parse import urlparse

_LOCAL_NAMES = (
    "local",
    "ollama",
    "lmstudio",
    "llama.cpp",
    "llamacpp",
    "vllm",
    "openai-compatible",
    "openai_compatible",
)


def _provider_name() -> str:
    """Return the configured model provider.

    Returns
    -------
    str
        ``"opencode"``, ``"local"``, or ``"openrouter"``.
    """
    value = os.getenv("HARNESS_PROVIDER", "openrouter").strip().lower()
    if value in ("opencode", "opencode-go", "go"):
        return "opencode"
    if value in _LOCAL_NAMES:
        return "local"
    return "openrouter"


def _provider_key(provider: str) -> str | None:
    """Return the API key for a provider.

    Parameters
    ----------
    provider : str
        Provider name.

    Returns
    -------
    str or None
        Configured API key.
    """
    if provider == "opencode":
        return os.getenv("OPENCODE_API_KEY") or os.getenv(
            "OPENCODE_GO_API_KEY"
        )
    if provider == "local":
        return os.getenv("LOCAL_API_KEY") or "local"
    return os.getenv("OPENROUTER_API_KEY")


def _provider_model(provider: str) -> str:
    """Return the default model for a provider.

    Parameters
    ----------
    provider : str
        Provider name.

    Returns
    -------
    str
        Configured or default model identifier.
    """
    if provider == "opencode":
        return os.getenv("OPENCODE_MODEL", "deepseek-v4.1-flash")
    if provider == "local":
        return (
            os.getenv("LOCAL_MODEL")
            or os.getenv("HARNESS_MODEL")
            or "local-model"
        )
    return os.getenv("OPENROUTER_MODEL", "openrouter/free")


def _provider_url(provider: str) -> str:
    """Return the chat-completions endpoint for a provider.

    Parameters
    ----------
    provider : str
        Provider name.

    Returns
    -------
    str
        Configured or default endpoint URL.
    """
    if provider == "opencode":
        default = "https://opencode.ai/inference/go/openai/v1/chat/completions"
        return _chat_url(os.getenv("OPENCODE_BASE_URL") or default)
    if provider == "local":
        default = "http://localhost:11434/v1/chat/completions"
        return _chat_url(os.getenv("LOCAL_BASE_URL") or default)
    default = "https://openrouter.ai/api/v1/chat/completions"
    return os.getenv("OPENROUTER_BASE_URL") or default


def _chat_url(url: str) -> str:
    """Complete a base URL with the chat-completions path.

    Parameters
    ----------
    url : str
        Full endpoint or base URL.

    Returns
    -------
    str
        Endpoint ending in ``/chat/completions``.
    """
    base = url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1") or base.endswith("/openai/v1"):
        return base + "/chat/completions"
    if not urlparse(base).path:
        return base + "/v1/chat/completions"
    return base


class OpenRouterError(RuntimeError):
    """Represent an OpenRouter request or response failure."""


class OpenRouterClient:
    """Send OpenAI-compatible chat completion requests."""

    def __init__(self, model: str | None = None) -> None:
        """Initialize configuration from environment variables.

        Parameters
        ----------
        model : str or None
            Optional model override.

        Returns
        -------
        None
            This initializer mutates the client instance.
        """
        self._provider = _provider_name()
        self.api_key = _provider_key(self._provider)
        self.model = model or _provider_model(self._provider)
        self.site_url = os.getenv("OPENROUTER_SITE_URL", "http://localhost")
        self.app_name = os.getenv("OPENROUTER_APP_NAME", "minimal-harness")
        self.user_agent = os.getenv(
            "HARNESS_USER_AGENT", "minimal-harness/0.1"
        )
        self.session_id = uuid.uuid4().hex
        self.max_retries = int(os.getenv("OPENROUTER_MAX_RETRIES", "2"))
        self.timeout = int(os.getenv("HARNESS_MODEL_TIMEOUT", "180"))
        self.call_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    @property
    def provider(self) -> str:
        """Return the configured provider name.

        Returns
        -------
        str
            Provider identifier.
        """
        return self._provider

    def complete(
        self, system: str, user: str, temperature: float = 0.2
    ) -> str:
        """Return one model completion.

        Parameters
        ----------
        system : str
            System instruction.
        user : str
            User payload.
        temperature : float
            Sampling temperature.

        Returns
        -------
        str
            Completion content.
        """
        self._require_key()
        body = self._send(self._build_request(system, user, temperature))
        return self._extract_content(body)

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Request a response that may contain tool calls.

        Parameters
        ----------
        messages : list[dict[str, Any]]
            Conversation messages.
        tools : list[dict[str, Any]]
            OpenAI-compatible tool schemas.

        Returns
        -------
        dict[str, Any]
            Provider response body.
        """
        self._require_key()
        payload = {"model": self.model, "messages": messages, "tools": tools}
        return self._validate_chat(
            self._send(self._build_payload_request(payload))
        )

    def _validate_chat(self, body: dict[str, Any]) -> dict[str, Any]:
        """Validate a chat response before agent processing.

        Parameters
        ----------
        body : dict[str, Any]
            Provider response body.

        Returns
        -------
        dict[str, Any]
            Valid chat response.
        """
        if "choices" not in body:
            raise OpenRouterError(
                f"OpenRouter returned an error response: {body}"
            )
        self._record_usage(body)
        return body

    def _build_payload_request(
        self, payload: dict[str, Any]
    ) -> urllib.request.Request:
        """Build a request from a prepared payload.

        Parameters
        ----------
        payload : dict[str, Any]
            JSON-compatible request payload.

        Returns
        -------
        urllib.request.Request
            Configured HTTP request.
        """
        data = json.dumps(payload).encode("utf-8")
        return urllib.request.Request(
            self._url(), data=data, headers=self._headers(), method="POST"
        )

    def _require_key(self) -> None:
        """Require an API key before a live request.

        Returns
        -------
        None
            This method returns after validation.
        """
        if not self.api_key:
            raise OpenRouterError(self._missing_key_message())

    def _missing_key_message(self) -> str:
        """Return the missing-key error for the active provider.

        Returns
        -------
        str
            Human-readable error message.
        """
        if self._provider == "opencode":
            return "OPENCODE_API_KEY is not set."
        return "OPENROUTER_API_KEY is not set."

    def _build_request(
        self, system: str, user: str, temperature: float
    ) -> urllib.request.Request:
        """Build an authenticated request.

        Parameters
        ----------
        system : str
            System instruction.
        user : str
            User payload.
        temperature : float
            Sampling temperature.

        Returns
        -------
        urllib.request.Request
            Configured HTTP request.
        """
        data = json.dumps(self._payload(system, user, temperature)).encode(
            "utf-8"
        )
        return urllib.request.Request(
            self._url(), data=data, headers=self._headers(), method="POST"
        )

    def _payload(
        self, system: str, user: str, temperature: float
    ) -> dict[str, Any]:
        """Create a chat completion payload.

        Parameters
        ----------
        system : str
            System instruction.
        user : str
            User payload.
        temperature : float
            Sampling temperature.

        Returns
        -------
        dict[str, Any]
            JSON-compatible payload.
        """
        messages = self._messages(system, user)
        return {
            "model": self.model,
            "temperature": temperature,
            "messages": messages,
        }

    def _messages(self, system: str, user: str) -> list[dict[str, str]]:
        """Build chat messages.

        Parameters
        ----------
        system : str
            System instruction.
        user : str
            User payload.

        Returns
        -------
        list[dict[str, str]]
            Chat messages.
        """
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _url(self) -> str:
        """Return the completion endpoint.

        Returns
        -------
        str
            Provider endpoint URL, overridable via provider-specific
            environment variables.
        """
        return _provider_url(self._provider)

    def _headers(self) -> dict[str, str]:
        """Return required request headers.

        Returns
        -------
        dict[str, str]
            HTTP headers.
        """
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "HTTP-Referer": self.site_url,
            "X-Title": self.app_name,
            "x-opencode-session": self.session_id,
        }

    def _send(self, request: urllib.request.Request) -> dict[str, Any]:
        """Send a request and decode its body.

        Parameters
        ----------
        request : urllib.request.Request
            Request to send.

        Returns
        -------
        dict[str, Any]
            Decoded response body.
        """
        armed = self._arm_alarm()
        try:
            return self._send_body(request)
        except Exception as exc:
            raise self._request_error(exc) from exc
        finally:
            if armed:
                signal.alarm(0)

    def _arm_alarm(self) -> bool:
        """Arm the process timeout alarm when on the main thread.

        Returns
        -------
        bool
            ``True`` when an alarm was set and must be cleared. Worker
            threads cannot install signal handlers, and Windows has no
            ``SIGALRM``, so those cases rely on the socket timeout.
        """
        if threading.current_thread() is not threading.main_thread():
            return False
        if not hasattr(signal, "SIGALRM"):
            return False
        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.alarm(self.timeout)
        return True

    def _request_error(self, exc: Exception) -> OpenRouterError:
        """Convert request exceptions to readable client errors.

        Parameters
        ----------
        exc : Exception
            Request exception.

        Returns
        -------
        OpenRouterError
            Normalized error.
        """
        if isinstance(exc, TimeoutError):
            return OpenRouterError(
                f"OpenRouter request exceeded {self.timeout} seconds."
            )
        return OpenRouterError(f"OpenRouter request failed: {exc}")

    def _send_body(self, request: urllib.request.Request) -> dict[str, Any]:
        """Send a request through the retry wrapper.

        Parameters
        ----------
        request : urllib.request.Request
            Request to send.

        Returns
        -------
        dict[str, Any]
            Decoded response body.
        """
        return self._send_once(request)

    def _send_once(self, request: urllib.request.Request) -> dict[str, Any]:
        """Send a request through the retry wrapper.

        Parameters
        ----------
        request : urllib.request.Request
            Request to send.

        Returns
        -------
        dict[str, Any]
            Decoded response body.
        """
        return self._retry_open(request)

    def _retry_open(self, request: urllib.request.Request) -> dict[str, Any]:
        """Retry transient provider responses with bounded backoff.

        Parameters
        ----------
        request : urllib.request.Request
            Request to send.

        Returns
        -------
        dict[str, Any]
            Decoded response body.
        """
        for attempt in range(self.max_retries + 1):
            try:
                return self._open(request)
            except urllib.error.HTTPError as exc:
                if not self._retryable(exc) or attempt == self.max_retries:
                    raise
                time.sleep(self._retry_delay(exc, attempt))
            except (urllib.error.URLError, TimeoutError):
                if attempt == self.max_retries:
                    raise
                time.sleep(min(2**attempt, 8.0))
        raise OpenRouterError("OpenRouter retry loop ended unexpectedly.")

    def _retryable(self, error: urllib.error.HTTPError) -> bool:
        """Identify HTTP responses safe to retry.

        Parameters
        ----------
        error : urllib.error.HTTPError
            Provider HTTP error.

        Returns
        -------
        bool
            Whether retrying is appropriate.
        """
        return error.code == 429 or error.code >= 500

    def _retry_delay(
        self, error: urllib.error.HTTPError, attempt: int
    ) -> float:
        """Calculate a short retry delay.

        Parameters
        ----------
        error : urllib.error.HTTPError
            Provider HTTP error.
        attempt : int
            Zero-based retry attempt.

        Returns
        -------
        float
            Delay in seconds.
        """
        header = error.headers.get("Retry-After")
        return min(float(header) if header else 2**attempt, 8.0)

    def _open(self, request: urllib.request.Request) -> dict[str, Any]:
        """Open a request and decode its response.

        Parameters
        ----------
        request : urllib.request.Request
            Request to send.

        Returns
        -------
        dict[str, Any]
            Decoded response body.
        """
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def _extract_content(self, body: dict[str, Any]) -> str:
        """Extract completion text from a response.

        Parameters
        ----------
        body : dict[str, Any]
            Decoded provider response.

        Returns
        -------
        str
            Completion content.
        """
        self._record_usage(body)
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError(
                f"Unexpected OpenRouter response: {body}"
            ) from exc

    def _record_usage(self, body: dict[str, Any]) -> None:
        """Add this response's token counts to the running totals.

        Parameters
        ----------
        body : dict[str, Any]
            Decoded provider response.
        """
        usage = body.get("usage") or {}
        self.call_count += 1
        self.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        self.completion_tokens += int(usage.get("completion_tokens", 0) or 0)

    def usage_summary(self) -> str:
        """Return a one-line summary of accumulated token usage.

        Returns
        -------
        str
            Human-readable summary line.
        """
        return (
            f"calls={self.call_count} "
            f"prompt_tokens={self.prompt_tokens} "
            f"completion_tokens={self.completion_tokens}"
        )


def _raise_timeout(signum: int, frame: Any) -> None:
    """Raise a timeout from the process alarm.

    Parameters
    ----------
    signum : int
        Received signal number.
    frame : Any
        Current execution frame.

    Returns
    -------
    None
        This function always raises TimeoutError.
    """
    raise TimeoutError("OpenRouter request timed out")
