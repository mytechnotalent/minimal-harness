"""Minimal OpenRouter client for agent calls."""

import json
import os
import signal
import time
import urllib.error
import urllib.request
from typing import Any


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
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("OPENROUTER_MODEL", "openrouter/free")
        self.site_url = os.getenv("OPENROUTER_SITE_URL", "http://localhost")
        self.app_name = os.getenv("OPENROUTER_APP_NAME", "minimal-harness")
        self.max_retries = int(os.getenv("OPENROUTER_MAX_RETRIES", "2"))

    @property
    def provider(self) -> str:
        """Return the configured provider name.

        Returns
        -------
        str
            Provider identifier.
        """
        return "openrouter"

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
            raise OpenRouterError("OPENROUTER_API_KEY is not set.")

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
            OpenRouter endpoint URL.
        """
        return "https://openrouter.ai/api/v1/chat/completions"

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
            "HTTP-Referer": self.site_url,
            "X-Title": self.app_name,
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
        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.alarm(120)
        try:
            return self._send_body(request)
        except Exception as exc:
            raise self._request_error(exc) from exc
        finally:
            signal.alarm(0)

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
            return OpenRouterError("OpenRouter request exceeded 120 seconds.")
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
        with urllib.request.urlopen(request, timeout=30) as response:
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
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError(
                f"Unexpected OpenRouter response: {body}"
            ) from exc


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
