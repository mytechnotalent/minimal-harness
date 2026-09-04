"""Tests for the optional public web-search client."""

import unittest
from unittest.mock import DEFAULT, patch

from meta_harness.web_search import WebSearchClient

FALLBACK_QUERY = "Kevin Thomas mytechnotalent"
FALLBACK_VALUE = [
    {"title": "Kevin Thomas", "url": "https://github.com/mytechnotalent"}
]
FALLBACK_PATCHES = {"_fetch": DEFAULT, "_github_fallback": DEFAULT}


class WebSearchTests(unittest.TestCase):
    """Verify web result parsing and failure handling."""

    def test_search_parses_result_links(self) -> None:
        """Parse result links from a mocked search response.

        Returns
        -------
        None
            Assertions pass when links are extracted.
        """
        html = '<a class="result__a" href="https://example.com">Example</a>'
        with patch.object(WebSearchClient, "_fetch", return_value=html):
            results = WebSearchClient().search("example")
        self.assertEqual(
            results, [{"title": "Example", "url": "https://example.com"}]
        )

    def test_search_returns_empty_results_on_failure(self) -> None:
        """Return an empty list when the provider is unavailable.

        Returns
        -------
        None
            Assertions pass when failures are contained.
        """
        with patch.object(WebSearchClient, "_fetch", side_effect=OSError):
            results = WebSearchClient().search("example")
        self.assertEqual(results, [])

    def test_search_uses_github_fallback_when_html_has_no_results(
        self,
    ) -> None:
        """Use a public GitHub profile when HTML search is blocked.

        Returns
        -------
        None
            Assertions pass when the fallback returns a profile.
        """
        results, fallback = self._fallback_result()
        fallback.assert_called_once_with(FALLBACK_QUERY, 5)
        self.assertEqual(results[0]["title"], "Kevin Thomas")

    def _fallback_result(self):
        """Run a mocked GitHub fallback search.

        Returns
        -------
        tuple[list[dict], Mock]
            Results and fallback mock.
        """
        with patch.multiple(WebSearchClient, **FALLBACK_PATCHES) as mocks:
            mocks["_fetch"].return_value = "challenge"
            mocks["_github_fallback"].return_value = FALLBACK_VALUE
            return (
                WebSearchClient().search(FALLBACK_QUERY),
                mocks["_github_fallback"],
            )


if __name__ == "__main__":
    unittest.main()
