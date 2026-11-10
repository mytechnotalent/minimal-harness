"""Tests for the optional public web-search client."""

import unittest
from unittest.mock import DEFAULT
from unittest.mock import patch

from meta_harness.web_search import WebSearchClient
from meta_harness.web_search import _looks_like_person
from meta_harness.web_search import _person_name

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
        """Parse result links from a mocked search response.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        html = '<a class="result__a" href="https://example.com">Example</a>'
        with patch.object(WebSearchClient, "_fetch", return_value=html):
            results = WebSearchClient().search("example")
        self.assertEqual(
            results, [{"title": "Example", "url": "https://example.com"}]
        )

    def test_search_parses_lite_result_links(self) -> None:
        """Parse result links from DuckDuckGo Lite markup.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        html = '<a class="result-link" href="https://example.com">Example</a>'
        with patch.object(WebSearchClient, "_fetch", return_value=html):
            results = WebSearchClient().search("example")
        self.assertEqual(
            results, [{"title": "Example", "url": "https://example.com"}]
        )

    def test_search_returns_empty_results_on_failure(self) -> None:
        """Return an empty list when every provider is unavailable.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        with patch.multiple(WebSearchClient, **FALLBACK_PATCHES) as mocks:
            mocks["_fetch"].side_effect = OSError
            mocks["_bing_search"].return_value = []
            mocks["_playwright_search"].return_value = []
            mocks["_github_fallback"].return_value = []
            results = WebSearchClient().search("example")
        self.assertEqual(results, [])

    def test_search_uses_bing_when_html_empty(self) -> None:
        """Use Bing RSS before browser and GitHub fallbacks.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        expected = _example_results()
        found = _search_with(
            _fetch="", _bing_search=expected, _playwright_search=[]
        )
        self.assertEqual(found["results"], expected)
        found["_playwright_search"].assert_not_called()

    def test_bing_rss_results_parsed(self) -> None:
        """Parse titles and links from a Bing RSS body.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        results = WebSearchClient()._rss_results(_RSS_BODY)
        self.assertEqual(results, _RSS_EXPECTED)

    def test_search_uses_playwright_when_html_and_bing_empty(self) -> None:
        """Fall back to the browser when HTML and Bing yield no results.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        expected = _example_results()
        found = _search_with(
            _fetch="", _bing_search=[], _playwright_search=expected
        )
        self.assertEqual(found["results"], expected)

    def test_search_uses_github_fallback_when_html_has_no_results(
        self,
    ) -> None:
        """Use GitHub when HTML and browser searches are empty.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        results, fallback = self._fallback_result()
        fallback.assert_called_once_with(FALLBACK_QUERY, 5)
        self.assertEqual(results[0]["title"], "Kevin Thomas")

    def _fallback_result(self):
        """Run a mocked GitHub fallback search.

        Parameters
        ----------
        None

        Returns
        -------
        tuple[list[dict], Mock]
            Results and fallback mock.
        """
        with patch.multiple(WebSearchClient, **FALLBACK_PATCHES) as mocks:
            _set_fallback(mocks)
            results = WebSearchClient().search(FALLBACK_QUERY)
            return results, mocks["_github_fallback"]

    def test_person_query_merges_github_profiles(self) -> None:
        """A person query puts GitHub profiles before web results.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        results = _person_search(_profile_results())
        self.assertEqual(
            results[0]["url"], "https://github.com/mytechnotalent"
        )

    def test_person_query_detection(self) -> None:
        """Person-like queries produce a GitHub name query.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        query = "who is Kevin Thomas of reverse engineering"
        self.assertTrue(_looks_like_person(query))
        self.assertFalse(_looks_like_person("Python asyncio tutorial"))
        self.assertEqual(_person_name(query), "Kevin Thomas")

    @patch.object(WebSearchClient, "_github_profile")
    @patch.object(WebSearchClient, "_github_search")
    def test_github_fallback_searches_full_query(
        self, search, profile
    ) -> None:
        """A multi-word query uses GitHub user search, not a last token.

        Parameters
        ----------
        search : unittest.mock.Mock
            Patched GitHub user search.

        profile : unittest.mock.Mock
            Patched single-profile lookup.

        Returns
        -------
        None
        """
        expected = [{"title": "mytechnotalent", "url": "https://github.com"}]
        search.return_value = expected
        results = WebSearchClient()._github_fallback(FALLBACK_QUERY, 3)
        search.assert_called_once_with(FALLBACK_QUERY, 3)
        profile.assert_not_called()
        self.assertEqual(results, expected)

    def test_github_fallback_uses_profile_for_single_token(self) -> None:
        """A single token is treated as a GitHub username.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        expected = [{"title": "profile", "url": "https://github.com"}]
        with patch.object(
            WebSearchClient, "_github_profile", return_value=expected
        ) as profile:
            results = WebSearchClient()._github_fallback("mytechnotalent", 3)
        profile.assert_called_once_with("mytechnotalent", 3)
        self.assertEqual(results, expected)


if __name__ == "__main__":
    unittest.main()


_RSS_BODY = (
    "<rss><channel><item><title>Python</title>"
    "<link>https://python.org</link></item></channel></rss>"
)
_RSS_EXPECTED = [
    {"title": "Python", "url": "https://python.org", "snippet": ""}
]
_PERSON_HTML = '<a class="result__a" href="https://example.com">Kevin</a>'
_PERSON_QUERY = "who is Kevin Thomas of reverse engineering"


def _example_results() -> list[dict]:
    """Return one canned example result.

    Parameters
    ----------
    None

    Returns
    -------
    list of dict
        Single example result.
    """
    return [{"title": "Example", "url": "https://example.com"}]


def _search_with(**values):
    """Run a search with patched backends and given return values.

    Parameters
    ----------
    values : dict
        Backend return values keyed by method name.

    Returns
    -------
    dict
        Mock mapping plus the ``results`` key.
    """
    with patch.multiple(WebSearchClient, **FALLBACK_PATCHES) as mocks:
        for name, value in values.items():
            mocks[name].return_value = value
        results = WebSearchClient().search("example")
    return {**mocks, "results": results}


def _set_fallback(mocks) -> None:
    """Install fallback return values on the mocks.

    Parameters
    ----------
    mocks : dict
        Mock mapping from ``patch.multiple``.

    Returns
    -------
    None
        Mocks are configured.
    """
    mocks["_fetch"].return_value = "challenge"
    mocks["_bing_search"].return_value = []
    mocks["_playwright_search"].return_value = []
    mocks["_github_people"].return_value = []
    mocks["_github_fallback"].return_value = FALLBACK_VALUE


def _profile_results() -> list[dict]:
    """Return a canned GitHub profile result.

    Parameters
    ----------
    None

    Returns
    -------
    list of dict
        Single profile result.
    """
    return [
        {
            "title": "Kevin Thomas (@mytechnotalent)",
            "url": "https://github.com/mytechnotalent",
            "snippet": "Reverse engineering tutor",
        }
    ]


def _person_search(people) -> list[dict]:
    """Run a person-query search with GitHub profiles stubbed.

    Parameters
    ----------
    people : list of dict
        Profile results returned by the GitHub stub.

    Returns
    -------
    list of dict
        Search results.
    """
    patches = {"_fetch": DEFAULT, "_github_people": DEFAULT}
    with patch.multiple(WebSearchClient, **patches) as mocks:
        mocks["_fetch"].return_value = _PERSON_HTML
        mocks["_github_people"].return_value = people
        return WebSearchClient().search(_PERSON_QUERY)
