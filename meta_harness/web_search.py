"""Small DuckDuckGo-backed web search client for agent context."""

from html.parser import HTMLParser
import json
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


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
        if tag == "a" and "result__a" in values.get("class", ""):
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
        try:
            body = self._fetch(query)
        except Exception:
            return []
        parser = _ResultParser()
        parser.feed(body)
        return parser.results[:limit] or self._github_fallback(query, limit)

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
        username = query.split()[-1].lstrip("@")
        if not username.isalnum():
            return []
        try:
            return self._github_profile(username, limit)
        except Exception:
            return []

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
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "minimal-harness/0.1",
            },
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
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        request = Request(url, headers={"User-Agent": "minimal-harness/0.1"})
        with urlopen(request, timeout=15) as response:
            return response.read().decode("utf-8", errors="replace")
