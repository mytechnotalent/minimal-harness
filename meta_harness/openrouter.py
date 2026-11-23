"""Minimal OpenRouter client for agent calls."""

from __future__ import annotations

import json
import os
import signal
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
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

_ALLOWED_MESSAGE_KEYS = {
    "role",
    "content",
    "tool_calls",
    "tool_call_id",
    "name",
}

_OPENCODE_URL = "https://opencode.ai/inference/go/openai/v1/chat/completions"
_ANTHROPIC_URL = "https://api.anthropic.com/v1"
_LOCAL_URL = "http://localhost:11434/v1/chat/completions"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _sanitize_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Strip provider-specific fields and repair tool sequences.

    Parameters
    ----------
    messages : list[dict[str, Any]]
        Raw conversation messages.

    Returns
    -------
    list[dict[str, Any]]
        Messages accepted by OpenAI-compatible endpoints.
    """
    pending: set[Any] = set()
    cleaned: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if _skip_message(message, index, pending):
            continue
        _track_calls(message, pending)
        cleaned.append(_allowed_fields(message))
    return cleaned


def _skip_message(
    message: dict[str, Any], index: int, pending: set[Any]
) -> bool:
    """Return whether a message is stale or an orphan tool result.

    Parameters
    ----------
    message : dict[str, Any]
        Conversation message.
    index : int
        Position in the conversation.
    pending : set[Any]
        Tool-call identifiers awaiting results.

    Returns
    -------
    bool
        ``True`` when the message must be dropped.
    """
    role = message.get("role")
    if role == "system" and index > 0:
        return True
    return role == "tool" and message.get("tool_call_id") not in pending


def _track_calls(message: dict[str, Any], pending: set[Any]) -> None:
    """Update the pending tool-call identifiers for a message.

    Parameters
    ----------
    message : dict[str, Any]
        Conversation message.
    pending : set[Any]
        Tool-call identifiers awaiting results.

    Returns
    -------
    None
        The pending set is updated.
    """
    role = message.get("role")
    if role == "assistant":
        pending.clear()
        pending.update(
            call.get("id") for call in message.get("tool_calls") or []
        )
    elif role == "tool":
        pending.discard(message.get("tool_call_id"))


def _allowed_fields(message: dict[str, Any]) -> dict[str, Any]:
    """Return only fields accepted by OpenAI-compatible endpoints.

    Parameters
    ----------
    message : dict[str, Any]
        Conversation message.

    Returns
    -------
    dict[str, Any]
        Filtered message.
    """
    return {
        key: value
        for key, value in message.items()
        if key in _ALLOWED_MESSAGE_KEYS
    }


def _provider_name() -> str:
    """Return the configured model provider.

    Parameters
    ----------
    None

    Returns
    -------
    str
        ``"opencode"``, ``"anthropic"``, ``"local"``, or
        ``"openrouter"``.
    """
    value = os.getenv("HARNESS_PROVIDER", "openrouter").strip().lower()
    if value in ("opencode", "opencode-go", "go"):
        return "opencode"
    if value in ("anthropic", "claude", "anthropic-messages"):
        return "anthropic"
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
        return _opencode_key()
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY")
    if provider == "local":
        return os.getenv("LOCAL_API_KEY") or "local"
    return os.getenv("OPENROUTER_API_KEY")


def _opencode_key() -> str | None:
    """Return the configured OpenCode key from either variable.

    Parameters
    ----------
    None

    Returns
    -------
    str or None
        OpenCode API key.
    """
    return os.getenv("OPENCODE_API_KEY") or os.getenv("OPENCODE_GO_API_KEY")


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
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    if provider == "local":
        return _local_model()
    return os.getenv("OPENROUTER_MODEL", "openrouter/free")


def _local_model() -> str:
    """Return the configured local model name.

    Parameters
    ----------
    None

    Returns
    -------
    str
        Local model name with fallbacks.
    """
    return (
        os.getenv("LOCAL_MODEL") or os.getenv("HARNESS_MODEL") or "local-model"
    )


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
        return _chat_url(os.getenv("OPENCODE_BASE_URL") or _OPENCODE_URL)
    if provider == "anthropic":
        return _messages_url(os.getenv("ANTHROPIC_BASE_URL") or _ANTHROPIC_URL)
    if provider == "local":
        return _chat_url(os.getenv("LOCAL_BASE_URL") or _LOCAL_URL)
    return os.getenv("OPENROUTER_BASE_URL") or _OPENROUTER_URL


def _messages_url(url: str) -> str:
    """Complete a base URL with the Anthropic messages path.

    Parameters
    ----------
    url : str
        Full endpoint or base URL.

    Returns
    -------
    str
        Endpoint ending in ``/messages``.
    """
    base = url.rstrip("/")
    if base.endswith("/messages"):
        return base
    if base.endswith("/v1"):
        return base + "/messages"
    if not urlparse(base).path:
        return base + "/v1/messages"
    return base


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


def _timeout_error(timeout: int) -> OpenRouterError:
    """Build a timeout error.

    Parameters
    ----------
    timeout : int
        Configured timeout in seconds.

    Returns
    -------
    OpenRouterError
        Timeout error.
    """
    return OpenRouterError(f"OpenRouter request exceeded {timeout} seconds.")


def _http_error(exc: urllib.error.HTTPError) -> OpenRouterError:
    """Build an HTTP provider error with a bounded body.

    Parameters
    ----------
    exc : urllib.error.HTTPError
        Provider error response.

    Returns
    -------
    OpenRouterError
        Normalized error.
    """
    detail = _error_body(exc)
    return OpenRouterError(
        f"OpenRouter request failed: HTTP {exc.code}: {detail}"
    )


def _error_body(exc: urllib.error.HTTPError) -> str:
    """Return a bounded provider error body.

    Parameters
    ----------
    exc : urllib.error.HTTPError
        Provider error response.

    Returns
    -------
    str
        Decoded body prefix.
    """
    try:
        text = exc.read().decode("utf-8", "replace")
    except Exception:
        return ""
    return text[:300]


def _append_usage(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON usage record to a log file.

    Parameters
    ----------
    path : pathlib.Path
        Log path.
    record : dict[str, Any]
        Usage record.

    Returns
    -------
    None
        The record is appended.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


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
        self._apply_environment()
        self._reset_usage()

    def _apply_environment(self) -> None:
        """Load optional endpoint settings from the environment.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Instance settings are updated.
        """
        self.site_url = os.getenv("OPENROUTER_SITE_URL", "http://localhost")
        self.app_name = os.getenv("OPENROUTER_APP_NAME", "savrenai")
        self.user_agent = os.getenv("HARNESS_USER_AGENT", "savrenai/0.1")
        self.session_id = uuid.uuid4().hex
        self.max_retries = int(os.getenv("OPENROUTER_MAX_RETRIES", "2"))
        self.timeout = int(os.getenv("HARNESS_MODEL_TIMEOUT", "180"))

    def _reset_usage(self) -> None:
        """Reset the usage counters.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Counters are zeroed.
        """
        self.call_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0
        self.cost = 0.0
        self.model_seconds = 0.0

    @property
    def provider(self) -> str:
        """Return the configured provider name.

        Parameters
        ----------
        None

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
        if self._provider == "anthropic":
            return self._anthropic_complete(system, user, temperature)
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
        if self._provider == "anthropic":
            return self._anthropic_chat(messages, tools)
        return self._openai_chat(messages, tools)

    def _openai_chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run one turn through an OpenAI-compatible endpoint.

        Parameters
        ----------
        messages : list[dict[str, Any]]
            Conversation messages.
        tools : list[dict[str, Any]]
            OpenAI-compatible tool schemas.

        Returns
        -------
        dict[str, Any]
            Validated provider response body.
        """
        clean = _sanitize_messages(messages)
        payload: dict[str, Any] = {"model": self.model, "messages": clean}
        if tools:
            payload["tools"] = tools
        body = self._send(self._build_payload_request(payload))
        return self._validate_chat(body)

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

    def _anthropic_complete(
        self, system: str, user: str, temperature: float
    ) -> str:
        """Run one text completion through the Anthropic API.

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
            Completion text.
        """
        payload = self._anthropic_payload(system, user, temperature)
        response = self._send(self._build_payload_request(payload))
        self._record_usage({"usage": _mapped_usage(response)})
        return _anthropic_text(response)

    def _anthropic_chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run one tool-capable turn through the Anthropic API.

        Parameters
        ----------
        messages : list[dict[str, Any]]
            Conversation messages.
        tools : list[dict[str, Any]]
            OpenAI-compatible tool schemas.

        Returns
        -------
        dict[str, Any]
            OpenAI-shaped response body.
        """
        clean = _sanitize_messages(messages)
        payload = self._anthropic_chat_payload(clean, tools)
        response = self._send(self._build_payload_request(payload))
        self._record_usage({"usage": _mapped_usage(response)})
        return {"choices": [{"message": _anthropic_message(response)}]}

    def _anthropic_payload(
        self, system: str, user: str, temperature: float
    ) -> dict[str, Any]:
        """Build an Anthropic text-completion payload.

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
        payload = {"model": self.model, "max_tokens": _anthropic_max_tokens()}
        payload["temperature"] = temperature
        payload["messages"] = [{"role": "user", "content": user}]
        _set_system(payload, system)
        return payload

    def _anthropic_chat_payload(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Build an Anthropic messages payload with tools.

        Parameters
        ----------
        messages : list[dict[str, Any]]
            Sanitized conversation messages.
        tools : list[dict[str, Any]]
            OpenAI-compatible tool schemas.

        Returns
        -------
        dict[str, Any]
            JSON-compatible payload.
        """
        system, turns = _anthropic_turns(messages)
        payload = {"model": self.model, "max_tokens": _anthropic_max_tokens()}
        payload["messages"] = turns
        _set_system(payload, system)
        if tools:
            payload["tools"] = _anthropic_tools(tools)
        return payload

    def _require_key(self) -> None:
        """Require an API key before a live request.

        Parameters
        ----------
        None

        Returns
        -------
        None
            This method returns after validation.
        """
        if not self.api_key:
            raise OpenRouterError(self._missing_key_message())

    def _missing_key_message(self) -> str:
        """Return the missing-key error for the active provider.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Human-readable error message.
        """
        if self._provider == "opencode":
            return "OPENCODE_API_KEY is not set."
        if self._provider == "anthropic":
            return "ANTHROPIC_API_KEY is not set."
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

        Parameters
        ----------
        None

        Returns
        -------
        str
            Provider endpoint URL, overridable via provider-specific
            environment variables.
        """
        return _provider_url(self._provider)

    def _headers(self) -> dict[str, str]:
        """Return required request headers.

        Parameters
        ----------
        None

        Returns
        -------
        dict[str, str]
            HTTP headers.
        """
        if self._provider == "anthropic":
            return self._anthropic_headers()
        return self._openai_headers()

    def _openai_headers(self) -> dict[str, str]:
        """Return OpenAI-compatible request headers.

        Parameters
        ----------
        None

        Returns
        -------
        dict[str, str]
            HTTP headers.
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}
        headers["Content-Type"] = "application/json"
        headers["User-Agent"] = self.user_agent
        headers["HTTP-Referer"] = self.site_url
        headers["X-Title"] = self.app_name
        headers["x-opencode-session"] = self.session_id
        return headers

    def _anthropic_headers(self) -> dict[str, str]:
        """Return Anthropic Messages request headers.

        Parameters
        ----------
        None

        Returns
        -------
        dict[str, str]
            HTTP headers.
        """
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
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
        started = time.monotonic()
        try:
            return self._send_body(request)
        except Exception as exc:
            raise self._request_error(exc) from exc
        finally:
            self._finish_send(armed, started)

    def _finish_send(self, armed, started) -> None:
        """Record request time and disarm the timeout alarm.

        Parameters
        ----------
        armed : bool
            Whether the alarm was armed.

        started : float
            Start time from ``time.monotonic``.

        Returns
        -------
        None
            Timing is recorded and the alarm is cleared.
        """
        self.model_seconds += time.monotonic() - started
        if armed:
            signal.alarm(0)

    def _arm_alarm(self) -> bool:
        """Arm the process timeout alarm when on the main thread.

        Parameters
        ----------
        None

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
            return _timeout_error(self.timeout)
        if isinstance(exc, urllib.error.HTTPError):
            return _http_error(exc)
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
                self._handle_http_error(exc, attempt)
            except (urllib.error.URLError, TimeoutError):
                self._handle_transport_error(attempt)
        raise OpenRouterError("OpenRouter retry loop ended unexpectedly.")

    def _handle_http_error(self, exc, attempt: int) -> None:
        """Retry or re-raise an HTTP provider error.

        Parameters
        ----------
        exc : urllib.error.HTTPError
            Provider error response.

        attempt : int
            Zero-based retry attempt.

        Returns
        -------
        None
            A retryable error sleeps; otherwise the error is re-raised.
        """
        if not self._retryable(exc) or attempt == self.max_retries:
            raise
        time.sleep(self._retry_delay(exc, attempt))

    def _handle_transport_error(self, attempt: int) -> None:
        """Retry or re-raise a transport error.

        Parameters
        ----------
        attempt : int
            Zero-based retry attempt.

        Returns
        -------
        None
            The error sleeps before retrying, or is re-raised.
        """
        if attempt == self.max_retries:
            raise
        time.sleep(min(2**attempt, 8.0))

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
        return error.code in (408, 409, 425, 429) or error.code >= 500

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

        Returns
        -------
        None
        """
        usage = body.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        self.call_count += 1
        self.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        self.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
        self.cached_tokens += int(details.get("cached_tokens", 0) or 0)
        self.cost += float(usage.get("cost", 0.0) or 0.0)
        self._log_usage(usage)

    def _log_usage(self, usage: dict[str, Any]) -> None:
        """Append one usage record when HARNESS_USAGE_LOG is set.

        Parameters
        ----------
        usage : dict[str, Any]
            Provider usage record.

        Returns
        -------
        None
            The log is appended when configured.
        """
        path = os.getenv("HARNESS_USAGE_LOG")
        if not path:
            return
        try:
            _append_usage(Path(path), {"model": self.model, **usage})
        except OSError:
            return

    def usage_summary(self) -> str:
        """Return a one-line summary of accumulated token usage.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Human-readable summary line.
        """
        return (
            f"calls={self.call_count} "
            f"prompt_tokens={self.prompt_tokens} "
            f"completion_tokens={self.completion_tokens} "
            f"cached_tokens={self.cached_tokens} "
            f"cost=${self.cost:.6f} "
            f"seconds={self.model_seconds:.1f}"
        )


def _anthropic_max_tokens() -> int:
    """Return the configured Anthropic output token limit.

    Parameters
    ----------
    None

    Returns
    -------
    int
        Maximum tokens per request.
    """
    return int(os.getenv("ANTHROPIC_MAX_TOKENS", "8192"))


def _set_system(payload: dict[str, Any], system: str) -> None:
    """Attach a non-empty system instruction to a payload.

    Parameters
    ----------
    payload : dict[str, Any]
        Payload being built.
    system : str
        System instruction.

    Returns
    -------
    None
        The payload is updated in place.
    """
    if system:
        payload["system"] = system


def _anthropic_turns(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Split OpenAI messages into system text and Anthropic turns.

    Parameters
    ----------
    messages : list[dict[str, Any]]
        Sanitized conversation messages.

    Returns
    -------
    tuple[str, list[dict[str, Any]]]
        System instruction and translated turns.
    """
    system = _system_text(messages)
    turns = [_anthropic_turn(m) for m in messages if m.get("role") != "system"]
    return system, [turn for turn in turns if turn is not None]


def _system_text(messages: list[dict[str, Any]]) -> str:
    """Join system messages into one instruction string.

    Parameters
    ----------
    messages : list[dict[str, Any]]
        Sanitized conversation messages.

    Returns
    -------
    str
        Combined system text.
    """
    parts = [
        str(message.get("content", ""))
        for message in messages
        if message.get("role") == "system"
    ]
    return " ".join(parts).strip()


def _anthropic_turn(message: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one OpenAI-shaped message to an Anthropic turn.

    Parameters
    ----------
    message : dict[str, Any]
        OpenAI-shaped message.

    Returns
    -------
    dict[str, Any] or None
        Translated turn, or ``None`` for unsupported roles.
    """
    role = message.get("role")
    if role == "tool":
        return _tool_result_turn(message)
    if role == "assistant" and message.get("tool_calls"):
        return {"role": "assistant", "content": _assistant_blocks(message)}
    if role in ("user", "assistant"):
        return _plain_turn(role, message)
    return None


def _plain_turn(role: str, message: dict[str, Any]) -> dict[str, Any]:
    """Build a plain user or assistant turn.

    Parameters
    ----------
    role : str
        Turn role.
    message : dict[str, Any]
        OpenAI-shaped message.

    Returns
    -------
    dict[str, Any]
        Plain content turn.
    """
    content = str(message.get("content", ""))
    return {"role": role, "content": content}


def _assistant_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Build Anthropic content blocks for an assistant tool-call turn.

    Parameters
    ----------
    message : dict[str, Any]
        Assistant message with tool calls.

    Returns
    -------
    list[dict[str, Any]]
        Text and tool-use content blocks.
    """
    blocks = []
    text = str(message.get("content", "")).strip()
    if text:
        blocks.append({"type": "text", "text": text})
    for call in message.get("tool_calls") or []:
        blocks.append(_tool_use_block(call))
    return blocks


def _tool_use_block(call: dict[str, Any]) -> dict[str, Any]:
    """Convert one OpenAI tool call to an Anthropic tool-use block.

    Parameters
    ----------
    call : dict[str, Any]
        OpenAI tool call.

    Returns
    -------
    dict[str, Any]
        Tool-use content block.
    """
    function = call.get("function") or {}
    return {
        "type": "tool_use",
        "id": call.get("id", ""),
        "name": function.get("name", ""),
        "input": _anthropic_arguments(function.get("arguments", {})),
    }


def _anthropic_arguments(raw: Any) -> dict[str, Any]:
    """Parse tool-call arguments into an input mapping.

    Parameters
    ----------
    raw : Any
        Raw argument payload.

    Returns
    -------
    dict[str, Any]
        Parsed argument mapping.
    """
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _tool_result_turn(message: dict[str, Any]) -> dict[str, Any]:
    """Convert an OpenAI tool message to a tool-result turn.

    Parameters
    ----------
    message : dict[str, Any]
        Tool message.

    Returns
    -------
    dict[str, Any]
        User turn carrying the tool result block.
    """
    result = {
        "type": "tool_result",
        "tool_use_id": message.get("tool_call_id", ""),
        "content": str(message.get("content", "")),
    }
    return {"role": "user", "content": [result]}


def _anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert OpenAI tool schemas to Anthropic tools.

    Parameters
    ----------
    tools : list[dict[str, Any]]
        OpenAI tool schemas.

    Returns
    -------
    list[dict[str, Any]]
        Anthropic tool definitions.
    """
    return [_anthropic_tool(tool) for tool in tools]


def _anthropic_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert one OpenAI tool schema to an Anthropic tool.

    Parameters
    ----------
    tool : dict[str, Any]
        OpenAI tool schema.

    Returns
    -------
    dict[str, Any]
        Anthropic tool definition.
    """
    function = tool.get("function") or {}
    return {
        "name": function.get("name", ""),
        "description": function.get("description", ""),
        "input_schema": function.get("parameters") or {"type": "object"},
    }


def _anthropic_message(response: dict[str, Any]) -> dict[str, Any]:
    """Convert an Anthropic response to an OpenAI-shaped message.

    Parameters
    ----------
    response : dict[str, Any]
        Anthropic Messages response.

    Returns
    -------
    dict[str, Any]
        OpenAI-shaped assistant message.
    """
    content = response.get("content") or []
    return {
        "role": "assistant",
        "content": _anthropic_text(response),
        "tool_calls": _anthropic_tool_calls(content),
    }


def _anthropic_text(response: dict[str, Any]) -> str:
    """Join the text blocks of an Anthropic response.

    Parameters
    ----------
    response : dict[str, Any]
        Anthropic Messages response.

    Returns
    -------
    str
        Combined text content.
    """
    parts = []
    for block in response.get("content") or []:
        if block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "\n".join(parts)


def _anthropic_tool_calls(content: list) -> list[dict[str, Any]]:
    """Collect tool-use blocks as OpenAI tool calls.

    Parameters
    ----------
    content : list
        Anthropic content blocks.

    Returns
    -------
    list[dict[str, Any]]
        OpenAI tool-call records.
    """
    calls = []
    for block in content:
        if block.get("type") == "tool_use":
            calls.append(_tool_call_block(block))
    return calls


def _tool_call_block(block: dict[str, Any]) -> dict[str, Any]:
    """Convert one tool-use block to an OpenAI tool call.

    Parameters
    ----------
    block : dict[str, Any]
        Tool-use content block.

    Returns
    -------
    dict[str, Any]
        OpenAI tool-call record.
    """
    return {
        "id": block.get("id", ""),
        "type": "function",
        "function": {
            "name": block.get("name", ""),
            "arguments": json.dumps(block.get("input") or {}),
        },
    }


def _mapped_usage(response: dict[str, Any]) -> dict[str, Any]:
    """Map an Anthropic usage record to OpenAI-style counters.

    Parameters
    ----------
    response : dict[str, Any]
        Anthropic Messages response.

    Returns
    -------
    dict[str, Any]
        OpenAI-style usage mapping.
    """
    usage = response.get("usage") or {}
    return {
        "prompt_tokens": usage.get("input_tokens", 0) or 0,
        "completion_tokens": usage.get("output_tokens", 0) or 0,
        "cached_tokens": usage.get("cache_read_input_tokens", 0) or 0,
        "cost": 0.0,
    }


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
