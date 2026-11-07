"""Small DuckDuckGo-backed web search client for agent context."""

from html.parser import HTMLParser
import json
import os
import re
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

_BROWSER_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}


def _capitalized_words(query: str) -> list[str]:
    """Return capitalized name-like tokens.

    Parameters
    ----------
    query : str
        Search terms.

    Returns
    -------
    list[str]
        Capitalized words in order.
    """
    return re.findall(r"\b[A-Z][a-z]{1,}\b", query)


def _looks_like_person(query: str) -> bool:
    """Return whether a query names a person or profile.

    Parameters
    ----------
    query : str
        Search terms.

    Returns
    -------
    bool
        Whether GitHub profile search should run.
    """
    lowered = query.lower()
    if lowered.startswith("@") or "github" in lowered or "who is" in lowered:
        return True
    return len(_capitalized_words(query)) >= 2


def _person_name(query: str) -> str:
    """Return the name-like part of a query.

    Parameters
    ----------
    query : str
        Search terms.

    Returns
    -------
    str
        Up to three capitalized words, or an empty string.
    """
    return " ".join(_capitalized_words(query)[:3])


def _merge_results(
    primary: list[dict[str, str]],
    secondary: list[dict[str, str]],
    limit: int,
) -> list[dict[str, str]]:
    """Merge result lists with URL deduplication.

    Parameters
    ----------
    primary : list[dict[str, str]]
        Highest-priority results.
    secondary : list[dict[str, str]]
        Remaining results.
    limit : int
        Maximum result count.

    Returns
    -------
    list[dict[str, str]]
        Deduplicated results.
    """
    seen: set[str] = set()
    merged: list[dict[str, str]] = []
    for item in primary + secondary:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            merged.append(item)
    return merged[:limit]


def _github_headers() -> dict[str, str]:
    """Build GitHub API headers with optional authentication.

    Returns
    -------
    dict[str, str]
        Request headers.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "minimal-harness/0.1",
    }
    token = os.getenv("HARNESS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


class _ResultParser(HTMLParser):
    """Extract result titles and links from DuckDuckGo HTML."""

    def __init__(self) -> None:
        """Initialize parser state.

        Returns
        -------
        None
            This initializer mutates parser state.
        """
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._link = ""
        self._title = ""

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Capture result links.

        Parameters
        ----------
        tag : str
            HTML tag name.
        attrs : list[tuple[str, str or None]]
            HTML attributes.

        Returns
        -------
        None
            Parser state is updated.
        """
        values = dict(attrs)
        classes = values.get("class", "")
        if tag == "a" and ("result__a" in classes or "result-link" in classes):
            self._link = values.get("href", "") or ""

    def handle_data(self, data: str) -> None:
        """Capture text for the active result link.

        Parameters
        ----------
        data : str
            Text encountered by the parser.

        Returns
        -------
        None
            Parser state is updated.
        """
        if self._link:
            self._title += data.strip()

    def handle_endtag(self, tag: str) -> None:
        """Store a completed result link.

        Parameters
        ----------
        tag : str
            HTML tag name.

        Returns
        -------
        None
            Completed result may be appended.
        """
        if tag == "a" and self._link and self._title:
            self.results.append({"title": self._title, "url": self._link})
            self._link, self._title = "", ""


class WebSearchClient:
    """Search the public web without an API key."""

    def __init__(self) -> None:
        """Initialize the profile cache.

        Returns
        -------
        None
            The cache starts empty.
        """
        self._profiles: dict[str, dict] = {}

    def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        """Return public search results for a query.

        Parameters
        ----------
        query : str
            Search terms.
        limit : int
            Maximum number of results.

        Returns
        -------
        list[dict[str, str]]
            Result titles and URLs, or an empty list on failure.
        """
        results = self._html_search(query)
        if not results:
            results = self._bing_search(query)
        if not results:
            results = self._playwright_search(query)
        people = (
            self._github_people(query) if _looks_like_person(query) else []
        )
        merged = _merge_results(people, results, limit)
        return merged or self._github_fallback(query, limit)

    def _bing_search(self, query: str) -> list[dict[str, str]]:
        """Search Bing's RSS feed without an API key.

        Parameters
        ----------
        query : str
            Search terms.

        Returns
        -------
        list[dict[str, str]]
            Parsed result titles and URLs, or an empty list.
        """
        request = Request(
            "https://www.bing.com/search?format=rss&q=" + quote_plus(query),
            headers=_BROWSER_HEADERS,
        )
        with urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
        return self._rss_results(body)

    def _rss_results(self, body: str) -> list[dict[str, str]]:
        """Parse Bing RSS items into result dictionaries.

        Parameters
        ----------
        body : str
            RSS response body.

        Returns
        -------
        list[dict[str, str]]
            Result titles and URLs, or an empty list.
        """
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError:
            return []
        return [
            {
                "title": item.findtext("title") or "",
                "url": item.findtext("link") or "",
                "snippet": item.findtext("description") or "",
            }
            for item in root.findall(".//item")
            if item.findtext("link")
        ]

    def _html_search(self, query: str) -> list[dict[str, str]]:
        """Fetch and parse DuckDuckGo HTML results.

        Parameters
        ----------
        query : str
            Search terms.

        Returns
        -------
        list[dict[str, str]]
            Parsed results, or an empty list.
        """
        try:
            body = self._fetch(query)
        except Exception:
            return []
        parser = _ResultParser()
        parser.feed(body)
        return parser.results

    def _playwright_search(self, query: str) -> list[dict[str, str]]:
        """Search with a real browser when HTML parsing fails.

        Parameters
        ----------
        query : str
            Search terms.

        Returns
        -------
        list[dict[str, str]]
            Browser search results, or an empty list.
        """
        try:
            return self._browser_results(query)
        except Exception:
            return []

    def _browser_results(self, query: str) -> list[dict[str, str]]:
        """Load DuckDuckGo in Chromium and scrape results.

        Parameters
        ----------
        query : str
            Search terms.

        Returns
        -------
        list[dict[str, str]]
            Result titles and URLs.
        """
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                return self._page_results(browser, query)
            finally:
                browser.close()

    def _page_results(self, browser, query: str) -> list[dict[str, str]]:
        """Scrape result anchors from a DuckDuckGo page.

        Parameters
        ----------
        browser : playwright.sync_api.Browser
            Headless browser.
        query : str
            Search terms.

        Returns
        -------
        list[dict[str, str]]
            Result titles and URLs.
        """
        page = browser.new_page()
        page.goto(
            "https://duckduckgo.com/?q=" + quote_plus(query), timeout=20000
        )
        page.wait_for_selector(
            "a[data-testid='result-title-a']", timeout=10000
        )
        return page.eval_on_selector_all(
            "a[data-testid='result-title-a']",
            "els => els.map(e => ({title: e.innerText, url: e.href}))",
        )

    def _github_fallback(self, query: str, limit: int) -> list[dict[str, str]]:
        """Search public GitHub users when HTML search is blocked.

        Parameters
        ----------
        query : str
            Search terms.
        limit : int
            Maximum number of results.

        Returns
        -------
        list[dict[str, str]]
            Public GitHub profile results.
        """
        username = _single_username(query)
        try:
            if username:
                return self._github_profile(username, limit)
            return self._github_search(query, limit)
        except Exception:
            return []

    def _github_people(
        self, query: str, limit: int = 2
    ) -> list[dict[str, str]]:
        """Find GitHub profiles matching a person-like query.

        Parameters
        ----------
        query : str
            Search terms.
        limit : int
            Maximum number of profiles.

        Returns
        -------
        list[dict[str, str]]
            Profile results with bios.
        """
        name = _person_name(query)
        if not name:
            return []
        try:
            items = self._search_items(name, limit)
        except Exception:
            return []
        return [self._github_person(item) for item in items[:limit]]

    def _github_person(self, item: dict) -> dict[str, str]:
        """Format one GitHub search item with its profile.

        Parameters
        ----------
        item : dict
            GitHub user search item.

        Returns
        -------
        dict[str, str]
            Profile result.
        """
        login = str(item.get("login", "unknown"))
        profile = self._cached_profile(login)
        return self._person_result(login, profile, item)

    def _person_result(
        self, login: str, profile: dict, item: dict
    ) -> dict[str, str]:
        """Build a profile result dictionary.

        Parameters
        ----------
        login : str
            GitHub login.
        profile : dict
            Profile payload, possibly empty.
        item : dict
            Search item fallback.

        Returns
        -------
        dict[str, str]
            Profile result.
        """
        name = profile.get("name") or login
        bio = profile.get("bio") or ""
        title = self._person_title(name, login, bio)
        url = profile.get("html_url") or item.get("html_url", "")
        return {"title": title, "url": url, "snippet": bio}

    def _person_title(self, name: str, login: str, bio: str) -> str:
        """Build a profile title.

        Parameters
        ----------
        name : str
            Display name.
        login : str
            GitHub login.
        bio : str
            Profile bio.

        Returns
        -------
        str
            Title with optional bio.
        """
        title = f"{name} (@{login})"
        return title + ": " + bio if bio else title

    def _cached_profile(self, login: str) -> dict:
        """Return a cached GitHub profile.

        Parameters
        ----------
        login : str
            GitHub login.

        Returns
        -------
        dict
            Profile payload, or an empty dict.
        """
        if login not in self._profiles:
            self._profiles[login] = self._fetch_profile(login)
        return self._profiles[login]

    def _fetch_profile(self, login: str) -> dict:
        """Fetch one GitHub profile safely.

        Parameters
        ----------
        login : str
            GitHub login.

        Returns
        -------
        dict
            Profile payload, or an empty dict.
        """
        try:
            return self._profile_response(self._profile_request(login))
        except Exception:
            return {}

    def _search_items(self, query: str, limit: int) -> list[dict]:
        """Search GitHub users and return raw items.

        Parameters
        ----------
        query : str
            Search terms.
        limit : int
            Maximum number of items.

        Returns
        -------
        list[dict]
            GitHub user search items.
        """
        request = Request(
            "https://api.github.com/search/users?q="
            + quote_plus(query)
            + f"&per_page={limit}",
            headers=_github_headers(),
        )
        body = self._profile_response(request)
        return body.get("items", [])[:limit]

    def _github_profile(
        self, username: str, limit: int
    ) -> list[dict[str, str]]:
        """Fetch one public GitHub profile as a search result.

        Parameters
        ----------
        username : str
            GitHub username.
        limit : int
            Maximum number of results.

        Returns
        -------
        list[dict[str, str]]
            Profile title, URL, and public bio.
        """
        profile = self._profile_response(self._profile_request(username))
        return self._profile_result(profile, username, limit)

    def _github_search(self, query: str, limit: int) -> list[dict[str, str]]:
        """Search GitHub users with the full query.

        Parameters
        ----------
        query : str
            Search terms.
        limit : int
            Maximum number of results.

        Returns
        -------
        list[dict[str, str]]
            Matching public GitHub profiles.
        """
        try:
            items = self._search_items(query, limit)
        except Exception:
            return []
        return [
            {
                "title": f"{item.get('login', 'unknown')} (GitHub profile)",
                "url": item.get("html_url", ""),
            }
            for item in items
        ]

    def _profile_request(self, username: str) -> Request:
        """Build a GitHub profile request.

        Parameters
        ----------
        username : str
            GitHub username.

        Returns
        -------
        urllib.request.Request
            Profile request.
        """
        return Request(
            f"https://api.github.com/users/{username}",
            headers=_github_headers(),
        )

    def _profile_result(
        self, profile: dict, username: str, limit: int
    ) -> list[dict[str, str]]:
        """Format a public GitHub profile result.

        Parameters
        ----------
        profile : dict
            GitHub profile data.
        username : str
            GitHub username.
        limit : int
            Maximum result count.

        Returns
        -------
        list[dict[str, str]]
            Formatted profile result.
        """
        title = f"{profile.get('name') or username} (@{username})"
        bio = profile.get("bio") or "Public GitHub profile"
        return [{"title": f"{title}: {bio}", "url": profile["html_url"]}][
            :limit
        ]

    def _profile_response(self, request: Request) -> dict:
        """Fetch and decode a GitHub profile response.

        Parameters
        ----------
        request : urllib.request.Request
            Profile request.

        Returns
        -------
        dict
            Decoded profile.
        """
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    def _fetch(self, query: str) -> str:
        """Fetch DuckDuckGo search HTML.

        Parameters
        ----------
        query : str
            Search terms.

        Returns
        -------
        str
            Search response HTML.
        """
        request = Request(
            "https://html.duckduckgo.com/html/",
            data=urlencode({"q": query}).encode(),
            headers=_BROWSER_HEADERS,
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            return response.read().decode("utf-8", errors="replace")


def _single_username(query: str) -> str:
    """Return a username when the query is a single token.

    Parameters
    ----------
    query : str
        Search terms.

    Returns
    -------
    str
        Candidate username, or an empty string.
    """
    text = query.strip()
    if text.startswith("@"):
        text = text[1:]
    return text if text.isalnum() else ""
