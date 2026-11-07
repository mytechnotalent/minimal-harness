"""Tests for the optional public web-search client."""

import unittest
from unittest.mock import DEFAULT, patch

from meta_harness.web_search import (
    WebSearchClient,
    _looks_like_person,
    _person_name,
)

FALLBACK_QUERY = "Kevin Thomas mytechnotalent"
FALLBACK_VALUE = [
    {"title": "Kevin Thomas", "url": "https://github.com/mytechnotalent"}
]
FALLBACK_PATCHES = {
    "_fetch": DEFAULT,
    "_bing_search": DEFAULT,
    "_playwright_search": DEFAULT,
    "_github_people": DEFAULT,
    "_github_fallback": DEFAULT,
}


class WebSearchTests(unittest.TestCase):
    """Verify web result parsing and failure handling."""

    def test_search_parses_result_links(self) -> None:
        """Parse result links from a mocked search response."""
        html = '<a class="result__a" href="https://example.com">Example</a>'
        with patch.object(WebSearchClient, "_fetch", return_value=html):
            results = WebSearchClient().search("example")
        self.assertEqual(
            results, [{"title": "Example", "url": "https://example.com"}]
        )

    def test_search_parses_lite_result_links(self) -> None:
        """Parse result links from DuckDuckGo Lite markup."""
        html = '<a class="result-link" href="https://example.com">Example</a>'
        with patch.object(WebSearchClient, "_fetch", return_value=html):
            results = WebSearchClient().search("example")
        self.assertEqual(
            results, [{"title": "Example", "url": "https://example.com"}]
        )

    def test_search_returns_empty_results_on_failure(self) -> None:
        """Return an empty list when every provider is unavailable."""
        with patch.multiple(WebSearchClient, **FALLBACK_PATCHES) as mocks:
            mocks["_fetch"].side_effect = OSError
            mocks["_bing_search"].return_value = []
            mocks["_playwright_search"].return_value = []
            mocks["_github_fallback"].return_value = []
            results = WebSearchClient().search("example")
        self.assertEqual(results, [])

    def test_search_uses_bing_when_html_empty(self) -> None:
        """Use Bing RSS before browser and GitHub fallbacks."""
        expected = [{"title": "Example", "url": "https://example.com"}]
        with patch.multiple(
            WebSearchClient,
            _fetch=DEFAULT,
            _bing_search=DEFAULT,
            _playwright_search=DEFAULT,
        ) as mocks:
            mocks["_fetch"].return_value = ""
            mocks["_bing_search"].return_value = expected
            mocks["_playwright_search"].return_value = []
            results = WebSearchClient().search("example")
        self.assertEqual(results, expected)
        mocks["_playwright_search"].assert_not_called()

    def test_bing_rss_results_parsed(self) -> None:
        """Parse titles and links from a Bing RSS body."""
        body = (
            "<rss><channel><item><title>Python</title>"
            "<link>https://python.org</link></item></channel></rss>"
        )
        results = WebSearchClient()._rss_results(body)
        self.assertEqual(
            results,
            [
                {
                    "title": "Python",
                    "url": "https://python.org",
                    "snippet": "",
                }
            ],
        )

    def test_search_uses_playwright_when_html_and_bing_empty(self) -> None:
        """Fall back to the browser when HTML and Bing yield no results."""
        expected = [{"title": "Example", "url": "https://example.com"}]
        with patch.multiple(
            WebSearchClient,
            _fetch=DEFAULT,
            _bing_search=DEFAULT,
            _playwright_search=DEFAULT,
        ) as mocks:
            mocks["_fetch"].return_value = ""
            mocks["_bing_search"].return_value = []
            mocks["_playwright_search"].return_value = expected
            results = WebSearchClient().search("example")
        self.assertEqual(results, expected)

    def test_search_uses_github_fallback_when_html_has_no_results(
        self,
    ) -> None:
        """Use GitHub when HTML and browser searches are empty."""
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
            mocks["_bing_search"].return_value = []
            mocks["_playwright_search"].return_value = []
            mocks["_github_people"].return_value = []
            mocks["_github_fallback"].return_value = FALLBACK_VALUE
            return (
                WebSearchClient().search(FALLBACK_QUERY),
                mocks["_github_fallback"],
            )

    def test_person_query_merges_github_profiles(self) -> None:
        """A person query puts GitHub profiles before web results."""
        people = [
            {
                "title": "Kevin Thomas (@mytechnotalent)",
                "url": "https://github.com/mytechnotalent",
                "snippet": "Reverse engineering tutor",
            }
        ]
        with patch.multiple(
            WebSearchClient, _fetch=DEFAULT, _github_people=DEFAULT
        ) as mocks:
            mocks["_fetch"].return_value = (
                '<a class="result__a" href="https://example.com">Kevin</a>'
            )
            mocks["_github_people"].return_value = people
            results = WebSearchClient().search(
                "who is Kevin Thomas of reverse engineering"
            )
        self.assertEqual(
            results[0]["url"], "https://github.com/mytechnotalent"
        )

    def test_person_query_detection(self) -> None:
        """Person-like queries produce a GitHub name query."""
        query = "who is Kevin Thomas of reverse engineering"
        self.assertTrue(_looks_like_person(query))
        self.assertFalse(_looks_like_person("Python asyncio tutorial"))
        self.assertEqual(_person_name(query), "Kevin Thomas")

    def test_github_fallback_searches_full_query(self) -> None:
        """A multi-word query uses GitHub user search, not a last token."""
        expected = [{"title": "mytechnotalent", "url": "https://github.com"}]
        with patch.object(
            WebSearchClient, "_github_search", return_value=expected
        ) as search:
            with patch.object(WebSearchClient, "_github_profile") as profile:
                results = WebSearchClient()._github_fallback(FALLBACK_QUERY, 3)
        search.assert_called_once_with(FALLBACK_QUERY, 3)
        profile.assert_not_called()
        self.assertEqual(results, expected)

    def test_github_fallback_uses_profile_for_single_token(self) -> None:
        """A single token is treated as a GitHub username."""
        expected = [{"title": "profile", "url": "https://github.com"}]
        with patch.object(
            WebSearchClient, "_github_profile", return_value=expected
        ) as profile:
            results = WebSearchClient()._github_fallback("mytechnotalent", 3)
        profile.assert_called_once_with("mytechnotalent", 3)
        self.assertEqual(results, expected)


if __name__ == "__main__":
    unittest.main()
