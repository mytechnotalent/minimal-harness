"""Optional Playwright browser tools for page inspection."""

from pathlib import Path
from threading import Thread
from typing import Any
import importlib


class BrowserError(RuntimeError):
    """Represent unavailable or failed browser automation."""


class BrowserClient:
    """Open pages and capture screenshots with Playwright."""

    def open(self, url: str) -> dict[str, str]:
        """Navigate to a URL and return metadata.

        Parameters
        ----------
        url : str
            Page URL.

        Returns
        -------
        dict[str, str]
            URL, title, and visible text.
        """
        return self._threaded("open", url, "")

    def screenshot(self, url: str, path: str) -> dict[str, str]:
        """Navigate to a URL and save a PNG.

        Parameters
        ----------
        url : str
            Page URL.
        path : str
            Output PNG path.

        Returns
        -------
        dict[str, str]
            URL and screenshot path.
        """
        return self._threaded("screenshot", url, path)

    def assert_page(self, url: str, text: str) -> dict[str, Any]:
        """Assert that visible page text is present.

        Parameters
        ----------
        url : str
            Page URL.
        text : str
            Required visible text.

        Returns
        -------
        dict[str, Any]
            Assertion result and page metadata.
        """
        page = self.open(url)
        return {
            "passed": text in page["text"],
            "url": page["url"],
            "text": text,
        }

    def _threaded(self, mode: str, url: str, path: str) -> dict[str, str]:
        """Run browser work outside the caller's event loop.

        Parameters
        ----------
        mode : str
            Browser operation name.
        url : str
            Page URL.
        path : str
            Screenshot path.

        Returns
        -------
        dict[str, str]
            Operation result.
        """
        result, errors = {}, []
        self._join(mode, url, path, result, errors)
        return self._thread_result(result, errors)

    def _join(
        self,
        mode: str,
        url: str,
        path: str,
        result: dict[str, str],
        errors: list[Exception],
    ) -> None:
        """Run one worker thread.

        Parameters
        ----------
        mode : str
            Browser operation.
        url : str
            Page URL.
        path : str
            Screenshot path.
        result : dict[str, str]
            Result target.
        errors : list[Exception]
            Error target.

        Returns
        -------
        None
            Worker completion is awaited.
        """
        worker = Thread(
            target=self._worker, args=(mode, url, path, result, errors)
        )
        worker.start()
        worker.join()

    def _thread_result(
        self, result: dict[str, str], errors: list[Exception]
    ) -> dict[str, str]:
        """Return worker output or raise its error.

        Parameters
        ----------
        result : dict[str, str]
            Worker result.
        errors : list[Exception]
            Worker errors.

        Returns
        -------
        dict[str, str]
            Browser result.
        """
        if errors:
            raise errors[0]
        return result

    def _worker(
        self,
        mode: str,
        url: str,
        path: str,
        result: dict[str, str],
        errors: list[Exception],
    ) -> None:
        """Execute one browser operation in a worker thread.

        Parameters
        ----------
        mode : str
            Browser operation name.
        url : str
            Page URL.
        path : str
            Screenshot path.
        result : dict[str, str]
            Mutable result target.
        errors : list[Exception]
            Mutable error target.

        Returns
        -------
        None
            Result or error is stored in a supplied container.
        """
        playwright = browser = None
        try:
            playwright, browser, page = self._page()
            result.update(self._navigate(mode, url, path, page))
        except Exception as exc:
            errors.append(exc)
        finally:
            self._close(playwright, browser)

    def _navigate(
        self, mode: str, url: str, path: str, page: Any
    ) -> dict[str, str]:
        """Navigate and collect a browser result.

        Parameters
        ----------
        mode : str
            Browser operation.
        url : str
            Page URL.
        path : str
            Screenshot path.
        page : Any
            Playwright page.

        Returns
        -------
        dict[str, str]
            Operation result.
        """
        page.goto(url, wait_until="networkidle", timeout=30000)
        return self._page_result(mode, page, path)

    def _close(self, playwright: Any, browser: Any) -> None:
        """Close Playwright resources when initialized.

        Parameters
        ----------
        playwright : Any
            Playwright manager or None.
        browser : Any
            Browser instance or None.

        Returns
        -------
        None
            Resources are closed when present.
        """
        if browser:
            browser.close()
        if playwright:
            playwright.stop()

    def _page_result(self, mode: str, page: Any, path: str) -> dict[str, str]:
        """Collect metadata or write a screenshot.

        Parameters
        ----------
        mode : str
            Browser operation name.
        page : Any
            Playwright page object.
        path : str
            Screenshot path.

        Returns
        -------
        dict[str, str]
            Operation result.
        """
        return (
            self._metadata(page)
            if mode == "open"
            else self._save_screenshot(page, path)
        )

    def _metadata(self, page: Any) -> dict[str, str]:
        """Collect page metadata.

        Parameters
        ----------
        page : Any
            Playwright page.

        Returns
        -------
        dict[str, str]
            URL, title, and visible text.
        """
        return {
            "url": page.url,
            "title": page.title(),
            "text": page.inner_text("body")[:12000],
        }

    def _save_screenshot(self, page: Any, path: str) -> dict[str, str]:
        """Save a full-page screenshot.

        Parameters
        ----------
        page : Any
            Playwright page.
        path : str
            Screenshot path.

        Returns
        -------
        dict[str, str]
            URL and screenshot path.
        """
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target), full_page=True)
        return {"url": page.url, "path": str(target)}

    def _page(self) -> tuple[Any, Any, Any]:
        """Start a Chromium browser and page.

        Returns
        -------
        tuple[Any, Any, Any]
            Playwright manager, browser, and page.
        """
        return self._launch()

    def _start_playwright(self) -> tuple[Any, Any, Any]:
        """Start Playwright and headless Chromium.

        Returns
        -------
        tuple[Any, Any, Any]
            Playwright manager, browser, and page.
        """
        return self._launch()

    def _launch(self) -> tuple[Any, Any, Any]:
        """Start Playwright and Chromium.

        Returns
        -------
        tuple[Any, Any, Any]
            Playwright manager, browser, and page.
        """
        playwright = (
            importlib.import_module("playwright.sync_api")
            .sync_playwright()
            .start()
        )
        browser = playwright.chromium.launch(headless=True)
        return playwright, browser, browser.new_page()
