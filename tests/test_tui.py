"""Headless tests for the full-screen TUI event handling."""

import curses
import threading
import unittest
from unittest.mock import Mock, patch

from meta_harness.tui import TUI


class FakeScreen:
    """Minimal curses screen that returns queued key events."""

    def __init__(self, keys: list) -> None:
        """Store queued key events.

        Parameters
        ----------
        keys : list
            Key events returned in order.

        Returns
        -------
        None
            This initializer mutates the instance.
        """
        self._keys = list(keys)

    def get_wch(self):
        """Return the next queued key event.

        Returns
        -------
        object
            Queued key event.
        """
        return self._keys.pop(0)

    def timeout(self, value) -> None:
        """Ignore a timeout request.

        Parameters
        ----------
        value : int
            Timeout in milliseconds.

        Returns
        -------
        None
            The request is ignored.
        """
        return

    def addnstr(self, row, column, text, width, attr) -> None:
        """Accept a drawn line and ignore it.

        Parameters
        ----------
        row : int
            Screen row.
        column : int
            Screen column.
        text : str
            Drawn text.
        width : int
            Maximum width.
        attr : int
            Display attributes.

        Returns
        -------
        None
            The call is ignored.
        """
        return


class TUITests(unittest.TestCase):
    """Verify TUI keyboard actions without opening a terminal."""

    def test_submit_runs_agent_and_quit_stops(self) -> None:
        """Submit a prompt and then exit the interface.

        Returns
        -------
        None
            Assertions pass when input events work.
        """
        agent = Mock()
        agent.run.return_value = "done"
        tui = TUI(agent)
        for key in "hello":
            tui._handle(key)
        self.assertTrue(tui._handle("\n"))
        tui.prompt = "/quit"
        self.assertFalse(tui._submit())

    def test_long_prompt_grows_input_box(self) -> None:
        """A long prompt wraps and lifts the input box upward.

        Returns
        -------
        None
            Assertions pass when the box scales with the prompt.
        """
        tui = TUI(Mock())
        empty_top = tui._input_top(24, 40)
        tui.prompt = "word " * 40
        lines = tui._prompt_lines(40)
        self.assertGreater(len(lines), 1)
        self.assertLess(tui._input_top(24, 40), empty_top)
        capped = tui._visible_prompt_lines(24, 40)
        self.assertEqual(len(capped), tui._max_prompt_rows(24))

    def test_ask_user_returns_selected_option(self) -> None:
        """Selecting a numbered option returns its label.

        Returns
        -------
        None
            Assertions pass when the option is returned.
        """
        tui = TUI(Mock())
        tui.screen = FakeScreen(["2"])
        tui._draw_question = Mock()
        answer = tui._ask_user("Pick one", ["alpha", "beta"])
        self.assertEqual(answer, "beta")
        self.assertIn("you> beta", tui.lines)

    def test_ask_user_reads_custom_answer(self) -> None:
        """Choosing the custom entry collects typed text.

        Returns
        -------
        None
            Assertions pass when the typed answer is returned.
        """
        tui = TUI(Mock())
        tui.screen = FakeScreen(["3", "h", "i", "\n"])
        tui._draw_question = Mock()
        tui._draw_answer = Mock()
        answer = tui._ask_user("Pick one", ["alpha", "beta"])
        self.assertEqual(answer, "hi")

    def test_run_prompt_keeps_paragraphs(self) -> None:
        """Paragraph breaks in an answer are preserved as blank lines.

        Returns
        -------
        None
            Assertions pass when blank lines survive.
        """
        agent = Mock()
        agent.run.return_value = "First part.\n\nSecond part."
        agent.tools.suggestions = []
        tui = TUI(agent)
        tui._start_worker("hi")
        tui._worker.join()
        tui._tick()
        self.assertIn("agent> First part.", tui.lines)
        self.assertIn("", tui.lines)
        self.assertIn("Second part.", tui.lines)

    def test_run_prompt_adds_clickable_suggestions(self) -> None:
        """Agent suggestions become clickable transcript entries.

        Returns
        -------
        None
            Assertions pass when suggestions are mapped.
        """
        agent = Mock()
        agent.run.return_value = "Answer."
        agent.tools.suggestions = ["Find local experts", "Find local class"]
        tui = TUI(agent)
        tui._start_worker("hi")
        tui._worker.join()
        tui._tick()
        self.assertIn("  Suggestions:", tui.lines)
        self.assertEqual(
            list(tui._suggestion_map.values()),
            ["Find local experts", "Find local class"],
        )

    def test_mouse_click_runs_suggestion(self) -> None:
        """Clicking a suggestion row submits it as the next prompt.

        Returns
        -------
        None
            Assertions pass when the mapped action is submitted.
        """
        tui = TUI(Mock())
        tui._suggestion_hit = {7: "Find local experts"}
        tui._start_worker = Mock()
        with patch("meta_harness.tui.curses.getmouse") as mouse:
            mouse.return_value = (0, 0, 7, 0, curses.BUTTON1_CLICKED)
            tui._handle_mouse()
        tui._start_worker.assert_called_once_with("Find local experts")

    def test_suggestion_rows_mapped_for_mouse(self) -> None:
        """Suggestion lines map to their on-screen rows.

        Returns
        -------
        None
            Assertions pass when the hit map targets the row.
        """
        tui = TUI(Mock())
        tui.lines = [
            "you> hi",
            "agent> answer",
            "",
            "  Suggestions:",
            "  \u25b8 Find local experts",
        ]
        tui._suggestion_map = {4: "Find local experts"}
        tui._line_attr = Mock(return_value=0)
        tui._transcript_rows(FakeScreen([]), 10, 80)
        self.assertEqual(tui._suggestion_hit.get(8), "Find local experts")

    def test_window_uses_scroll_offset(self) -> None:
        """The visible window shifts up as the scroll offset grows.

        Returns
        -------
        None
            Assertions pass when slicing tracks the offset.
        """
        tui = TUI(Mock())
        entries = [(str(index), index) for index in range(20)]
        tui.scroll = 0
        self.assertEqual(tui._window(entries, 5), entries[15:20])
        tui.scroll = 3
        self.assertEqual(tui._window(entries, 5), entries[12:17])
        self.assertEqual(tui._max_scroll, 15)

    def test_scroll_keys_adjust_and_clamp(self) -> None:
        """Scroll keys move within bounds and jump to ends.

        Returns
        -------
        None
            Assertions pass when offsets clamp correctly.
        """
        tui = TUI(Mock())
        tui._max_scroll, tui._visible_rows = 10, 5
        tui._scroll(curses.KEY_UP)
        self.assertEqual(tui.scroll, 1)
        tui._scroll(curses.KEY_PPAGE)
        self.assertEqual(tui.scroll, 6)
        tui._scroll(curses.KEY_END)
        self.assertEqual(tui.scroll, 0)
        tui._scroll(curses.KEY_HOME)
        self.assertEqual(tui.scroll, 10)
        tui._scroll(curses.KEY_UP)
        self.assertEqual(tui.scroll, 10)

    def test_mouse_wheel_scrolls(self) -> None:
        """A wheel-up event scrolls the transcript back.

        Returns
        -------
        None
            Assertions pass when the offset increases.
        """
        tui = TUI(Mock())
        tui._max_scroll = 10
        with patch("meta_harness.tui.curses.getmouse") as mouse:
            mouse.return_value = (0, 0, 0, 0, curses.BUTTON4_PRESSED)
            tui._handle_mouse()
        self.assertEqual(tui.scroll, 3)

    def test_status_label_animates_dots(self) -> None:
        """The status shows growing dots while thinking.

        Returns
        -------
        None
            Assertions pass when the label animates.
        """
        tui = TUI(Mock())
        tui.status, tui._dots = "thinking", 2
        self.assertEqual(tui._status_label(), "thinking..")
        tui.status = "ready"
        self.assertEqual(tui._status_label(), "READY")

    def test_worker_finishes_on_tick(self) -> None:
        """A completed worker appends its answer and resets status.

        Returns
        -------
        None
            Assertions pass when the answer is appended.
        """
        agent = Mock()
        agent.run.return_value = "done"
        agent.tools.suggestions = []
        tui = TUI(agent)
        tui._start_worker("hi")
        tui._worker.join()
        tui._tick()
        self.assertIsNone(tui._worker)
        self.assertEqual(tui.status, "ready")
        self.assertIn("agent> done", tui.lines)

    def test_serve_ui_request_answers_worker(self) -> None:
        """A queued worker question is answered and released.

        Returns
        -------
        None
            Assertions pass when the response event is set.
        """
        tui = TUI(Mock())
        tui._ask_user = Mock(return_value="blue")
        response, event = {}, threading.Event()
        tui._ui_requests.put(("Color?", ["red"], response, event))
        tui._serve_ui_request()
        self.assertEqual(response["answer"], "blue")
        self.assertTrue(event.is_set())


if __name__ == "__main__":
    unittest.main()
