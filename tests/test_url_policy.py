"""Tests for the research URL safety policy."""

import unittest
from unittest.mock import patch

from meta_harness.browser import BrowserClient
from meta_harness.url_policy import UrlPolicyError
from meta_harness.url_policy import validate_url

_PUBLIC = [(2, 1, 6, "", ("93.184.216.34", 443))]
_PRIVATE = [(2, 1, 6, "", ("10.0.0.5", 443))]


class UrlPolicyTests(unittest.TestCase):
    """Verify schemes, credentials, and address filtering."""

    def test_public_literal_address_is_allowed(self) -> None:
        """Allow a public literal IP address.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No exception is raised.
        """
        self.assertEqual(
            validate_url("https://93.184.216.34/path"),
            "https://93.184.216.34/path",
        )

    def test_public_hostname_is_allowed(self) -> None:
        """Allow a hostname that resolves to a public address.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No exception is raised.
        """
        with patch(
            "meta_harness.url_policy.socket.getaddrinfo", return_value=_PUBLIC
        ):
            validate_url("https://example.com")
        self.assertTrue(True)

    def test_blocked_schemes_are_rejected(self) -> None:
        """Reject file, data, and javascript URLs.

        Parameters
        ----------
        None

        Returns
        -------
        None
            UrlPolicyError is raised.
        """
        for url in ("file:///etc/passwd", "data:text/plain,x", "javascript:1"):
            with self.subTest(url=url):
                with self.assertRaises(UrlPolicyError):
                    validate_url(url)

    def test_private_addresses_are_rejected(self) -> None:
        """Reject loopback, private, and metadata addresses.

        Parameters
        ----------
        None

        Returns
        -------
        None
            UrlPolicyError is raised.
        """
        addresses = ("http://127.0.0.1", "http://10.0.0.5", "http://[::1]")
        for url in addresses:
            with self.subTest(url=url):
                with self.assertRaises(UrlPolicyError):
                    validate_url(url)
        with self.assertRaises(UrlPolicyError):
            validate_url("http://169.254.169.254/latest")

    def test_private_dns_resolution_is_rejected(self) -> None:
        """Reject a hostname that resolves to a private address.

        Parameters
        ----------
        None

        Returns
        -------
        None
            UrlPolicyError is raised.
        """
        with patch(
            "meta_harness.url_policy.socket.getaddrinfo", return_value=_PRIVATE
        ):
            with self.assertRaises(UrlPolicyError):
                validate_url("https://internal.example")

    def test_credentials_are_rejected(self) -> None:
        """Reject URLs with embedded usernames or passwords.

        Parameters
        ----------
        None

        Returns
        -------
        None
            UrlPolicyError is raised.
        """
        with self.assertRaises(UrlPolicyError):
            validate_url("https://user:pass@93.184.216.34")

    def test_browser_safe_mode_uses_policy(self) -> None:
        """Apply the policy only when safe mode is enabled.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Safe clients reject file URLs and normal clients do not.
        """
        BrowserClient(safe=False)._guard("file:///etc/passwd")
        with self.assertRaises(UrlPolicyError):
            BrowserClient(safe=True)._guard("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
