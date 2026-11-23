"""URL safety policy for research browser tools."""

import ipaddress
import socket
from urllib.parse import urlsplit


class UrlPolicyError(ValueError):
    """Report a URL that research tools must not open."""


def validate_url(url):
    """Return a safe HTTP URL or raise.

    Parameters
    ----------
    url : str
        Candidate URL.

    Returns
    -------
    str
        The original URL when accepted.
    """
    parts = urlsplit(url.strip())
    _check_scheme(parts)
    _check_credentials(parts)
    _check_host(parts.hostname)
    return url


def _check_scheme(parts):
    """Require an HTTP or HTTPS URL with a host.

    Parameters
    ----------
    parts : urllib.parse.SplitResult
        Parsed URL.

    Returns
    -------
    None
        The scheme and host are accepted.
    """
    if parts.scheme.lower() not in ("http", "https"):
        raise UrlPolicyError("only http and https URLs are allowed")
    if not parts.hostname:
        raise UrlPolicyError("URL must include a host")


def _check_credentials(parts):
    """Reject URLs that embed credentials.

    Parameters
    ----------
    parts : urllib.parse.SplitResult
        Parsed URL.

    Returns
    -------
    None
        The URL has no embedded credentials.
    """
    if parts.username is not None or parts.password is not None:
        raise UrlPolicyError("URLs with credentials are not allowed")


def _check_host(host):
    """Reject hosts that resolve to non-public addresses.

    Parameters
    ----------
    host : str
        Hostname or literal address.

    Returns
    -------
    None
        Every resolved address is public.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise UrlPolicyError(f"cannot resolve host: {host}") from exc
    for address in {info[4][0] for info in infos}:
        _check_address(address)


def _check_address(text):
    """Reject one non-public IP address.

    Parameters
    ----------
    text : str
        IP address text.

    Returns
    -------
    None
        The address is public.
    """
    try:
        address = ipaddress.ip_address(text.split("%")[0])
    except ValueError as exc:
        raise UrlPolicyError(f"invalid IP address: {text}") from exc
    if not address.is_global:
        raise UrlPolicyError(f"non-public address is not allowed: {text}")
