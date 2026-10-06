"""Responsive full-screen curses interface for the Minimal Harness agent."""

import curses
import queue
import textwrap
import threading
import time
from typing import Any

from .agent import Agent


class TUI:
    """Render a polished, responsive terminal workspace for an agent."""

    def __init__(self, agent: Agent) -> None:
        """Initialize the interface.

        Parameters
        ----------
        agent : Agent
            Agent used for prompts.

        Returns
        -------
        None
            The interface is initialized.
        """
        self.agent, self.lines, self.prompt = agent, [], ""
        self.status, self.scroll, self._choice = "ready", 0, 0
        self.screen, self._dots = None, 0
        self._suggestion_map, self._suggestion_hit = {}, {}
        self._max_scroll, self._visible_rows = 0, 1
        self._worker, self._result, self._error = None, None, None
        self._done, self._ui_requests = threading.Event(), queue.Queue()

    def run(self) -> None:
        """Start the full-screen interface.

        Returns
        -------
        None
            The interface exits on quit input.
        """
        curses.wrapper(self._screen)

    def _screen(self, screen: Any) -> None:
        """Process screen events.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.

        Returns
        -------
        None
            Interaction continues until exit.
        """
        self._setup(screen)
        while self._step(screen):
            pass

    def _step(self, screen: Any) -> bool:
        """Animate, draw, and handle one key press.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.

        Returns
        -------
        bool
            Whether the interface continues.
        """
        self._tick()
        self._draw(screen)
        key = self._read_key(screen)
        if key is None:
            return True
        return self._handle(key)

    def _read_key(self, screen: Any) -> Any:
        """Read one key with a short timeout so the UI keeps animating.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.

        Returns
        -------
        Any
            Key event, or ``None`` when the timeout elapses.
        """
        screen.timeout(120)
        try:
            return screen.get_wch()
        except curses.error:
            return None

    def _tick(self) -> None:
        """Advance the thinking animation and apply a finished worker.

        Returns
        -------
        None
            Spinner state is updated.
        """
        self._serve_ui_request()
        self._dots = int(time.monotonic() * 2) % 3 + 1
        if self._worker is not None and self._done.is_set():
            self._finish_worker()

    def _serve_ui_request(self) -> None:
        """Answer one queued question from the worker thread.

        Returns
        -------
        None
            At most one pending question is served.
        """
        try:
            request = self._ui_requests.get_nowait()
        except queue.Empty:
            return
        question, options, response, event = request
        response["answer"] = self._ask_user(question, options)
        event.set()

    def _setup(self, screen: Any) -> None:
        """Configure terminal behavior and color styles.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.

        Returns
        -------
        None
            Terminal settings are applied.
        """
        self.screen = screen
        self.agent.tools.questioner = self._request_question
        self._enable_mouse()
        curses.curs_set(1)
        screen.keypad(True)
        curses.start_color()
        curses.use_default_colors()
        self._colors()

    def _colors(self) -> None:
        """Define the interface color palette.

        Returns
        -------
        None
            Curses color pairs are registered.
        """
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_WHITE, -1)

    def _draw(self, screen: Any) -> bool:
        """Draw the workspace and keep the loop alive.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.

        Returns
        -------
        bool
            Whether drawing should continue.
        """
        screen.erase()
        height, width = screen.getmaxyx()
        self._header(screen, width)
        top = self._input_top(height, width)
        self._transcript(screen, top, width)
        self._input(screen, height, width, top)
        screen.refresh()
        return True

    def _header(self, screen: Any, width: int) -> None:
        """Draw the title and runtime status.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        width : int
            Screen width.

        Returns
        -------
        None
            Header is drawn.
        """
        self._header_title(screen, width)
        self._header_status(screen, width)
        self._rule(screen, 2, width)

    def _header_title(self, screen: Any, width: int) -> None:
        """Draw the workspace title.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        width : int
            Screen width.

        Returns
        -------
        None
            Title is drawn.
        """
        title = "  MINIMAL HARNESS  /  ADVERSARIAL WORKSPACE"
        self._add(
            screen, 0, 0, title, width, curses.color_pair(1) | curses.A_BOLD
        )

    def _header_status(self, screen: Any, width: int) -> None:
        """Draw status and model information.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        width : int
            Screen width.

        Returns
        -------
        None
            Status is drawn.
        """
        meta = f"{self._status_label()}  |  {self._model_name()}"
        if self.scroll:
            meta += f"  |  scrolled {self.scroll}"
        self._add_status(screen, width, meta)

    def _status_label(self) -> str:
        """Return the header status, animating while thinking.

        Returns
        -------
        str
            Status label with an animated dot count when thinking.
        """
        if self.status == "thinking":
            return "thinking" + "." * self._dots
        return self.status.upper()

    def _add_status(self, screen: Any, width: int, meta: str) -> None:
        """Draw right-aligned status metadata.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        width : int
            Screen width.
        meta : str
            Status metadata.

        Returns
        -------
        None
            Status metadata is drawn.
        """
        self._add(
            screen,
            1,
            0,
            meta.rjust(max(width, len(meta))),
            width,
            curses.color_pair(3),
        )

    def _transcript(self, screen: Any, top: int, width: int) -> None:
        """Draw the wrapped conversation area above the input box.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        top : int
            Row of the input label.
        width : int
            Screen width.

        Returns
        -------
        None
            Transcript content is drawn.
        """
        bottom = max(top - 1, 4)
        self._transcript_label(screen, width)
        self._transcript_rows(screen, bottom, width)
        self._rule(screen, bottom, width)

    def _transcript_label(self, screen: Any, width: int) -> None:
        """Draw the conversation label.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        width : int
            Screen width.

        Returns
        -------
        None
            Label is drawn.
        """
        self._add(
            screen,
            3,
            0,
            "  CONVERSATION",
            width,
            curses.color_pair(4) | curses.A_BOLD,
        )

    def _transcript_rows(self, screen: Any, bottom: int, width: int) -> None:
        """Draw the visible wrapped transcript rows.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        bottom : int
            Last transcript row.
        width : int
            Screen width.

        Returns
        -------
        None
            Visible rows are drawn.
        """
        entries = self._wrapped_entries(max(width - 4, 8))
        window = self._window(entries, max(bottom - 5, 1))
        self._suggestion_hit = {}
        for row, (line, source) in enumerate(window, 4):
            self._line(screen, row, line, width)
            self._map_suggestion(row, source)

    def _window(
        self, entries: list[tuple[str, int]], count: int
    ) -> list[tuple[str, int]]:
        """Return the wrapped entries visible at the current scroll.

        Parameters
        ----------
        entries : list[tuple[str, int]]
            All wrapped transcript entries.
        count : int
            Number of visible rows.

        Returns
        -------
        list[tuple[str, int]]
            The visible slice, newest at the bottom.
        """
        self._visible_rows = count
        self._max_scroll = max(0, len(entries) - count)
        self.scroll = self._clamp_scroll(self.scroll)
        end = len(entries) - self.scroll
        start = max(end - count, 0)
        return entries[start:end]

    def _map_suggestion(self, row: int, source: int) -> None:
        """Record the click target for a suggestion row.

        Parameters
        ----------
        row : int
            Screen row.
        source : int
            Source transcript line index.

        Returns
        -------
        None
            The hit map is updated when the line is a suggestion.
        """
        if source in self._suggestion_map:
            self._suggestion_hit[row] = self._suggestion_map[source]

    def _wrapped_entries(self, width: int) -> list[tuple[str, int]]:
        """Wrap transcript lines and track each source index.

        Parameters
        ----------
        width : int
            Maximum line width.

        Returns
        -------
        list[tuple[str, int]]
            Wrapped text paired with its source line index.
        """
        entries: list[tuple[str, int]] = []
        for index, line in enumerate(self.lines):
            for part in textwrap.wrap(line, width=width) or [""]:
                entries.append((part, index))
        return entries

    def _line(self, screen: Any, row: int, line: str, width: int) -> None:
        """Draw one transcript line with role styling.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        row : int
            Screen row.
        line : str
            Transcript text.
        width : int
            Screen width.

        Returns
        -------
        None
            One line is drawn.
        """
        color = self._line_attr(line)
        self._add(screen, row, 1, line, width - 2, color)

    def _line_attr(self, line: str) -> int:
        """Return the display attribute for a transcript line.

        Parameters
        ----------
        line : str
            Transcript line.

        Returns
        -------
        int
            Curses display attributes.
        """
        if line.startswith("you>"):
            return curses.color_pair(2)
        if line.lstrip().startswith("\u25b8"):
            return curses.color_pair(1) | curses.A_UNDERLINE
        return curses.color_pair(4)

    def _input(self, screen: Any, height: int, width: int, top: int) -> None:
        """Draw the active prompt bar.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        height : int
            Screen height.
        width : int
            Screen width.
        top : int
            Row of the input label.

        Returns
        -------
        None
            Input bar is drawn.
        """
        self._input_label(screen, top, width)
        self._draw_prompt(
            screen,
            top,
            width,
            self._visible_prompt_lines(height, width),
        )

    def _input_label(self, screen: Any, row: int, width: int) -> None:
        """Draw the prompt label.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        row : int
            Label row.
        width : int
            Screen width.

        Returns
        -------
        None
            Prompt label is drawn.
        """
        self._add(
            screen,
            row,
            0,
            self._input_label_text(),
            width,
            curses.color_pair(2) | curses.A_BOLD,
        )

    def _input_label_text(self) -> str:
        """Return the input label, animated while thinking.

        Returns
        -------
        str
            Prompt label, or a busy message while thinking.
        """
        if self.status == "thinking":
            return "  THINKING" + "." * self._dots + "  /  PLEASE WAIT"
        return "  YOU  /  ENTER TO SEND"

    def _input_top(self, height: int, width: int) -> int:
        """Return the row of the input label for the current prompt.

        Parameters
        ----------
        height : int
            Screen height.
        width : int
            Screen width.

        Returns
        -------
        int
            Label row, clamped below the header.
        """
        rows = len(self._visible_prompt_lines(height, width))
        return max(height - rows - 1, 5)

    def _visible_prompt_lines(self, height: int, width: int) -> list[str]:
        """Return the prompt rows that fit in the input box.

        Parameters
        ----------
        height : int
            Screen height.
        width : int
            Screen width.

        Returns
        -------
        list[str]
            Visible wrapped prompt lines, newest at the bottom.
        """
        lines = self._prompt_lines(width)
        cap = self._max_prompt_rows(height)
        return lines[-cap:] if len(lines) > cap else lines

    def _prompt_lines(self, width: int) -> list[str]:
        """Wrap the current prompt to the input width.

        Parameters
        ----------
        width : int
            Screen width.

        Returns
        -------
        list[str]
            Wrapped prompt lines, always at least one.
        """
        wrapped = textwrap.wrap(self.prompt, width=max(width - 6, 8))
        return wrapped or [""]

    def _max_prompt_rows(self, height: int) -> int:
        """Return the maximum input rows for a screen height.

        Parameters
        ----------
        height : int
            Screen height.

        Returns
        -------
        int
            Row cap between one and eight.
        """
        return max(1, min(8, (height - 5) // 3))

    def _draw_prompt(
        self,
        screen: Any,
        top: int,
        width: int,
        rows: list[str],
    ) -> None:
        """Draw wrapped prompt rows and place the cursor.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        top : int
            Row of the input label.
        width : int
            Screen width.
        rows : list[str]
            Visible prompt lines.

        Returns
        -------
        None
            Prompt rows and cursor are drawn.
        """
        for offset, line in enumerate(rows):
            self._prompt_row(screen, top + 1 + offset, line, offset, width)
        self._move_cursor(screen, top + len(rows), width, rows)

    def _prompt_row(
        self, screen: Any, row: int, line: str, offset: int, width: int
    ) -> None:
        """Draw one prompt row with a first-line marker.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        row : int
            Screen row.
        line : str
            Prompt line text.
        offset : int
            Zero-based row index.
        width : int
            Screen width.

        Returns
        -------
        None
            One prompt row is drawn.
        """
        prefix = "  > " if offset == 0 else "    "
        self._add(screen, row, 0, prefix + line, width, curses.color_pair(4))

    def _move_cursor(
        self, screen: Any, row: int, width: int, rows: list[str]
    ) -> None:
        """Place the cursor at the end of the prompt.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        row : int
            Cursor row.
        width : int
            Screen width.
        rows : list[str]
            Visible prompt lines.

        Returns
        -------
        None
            Cursor is moved.
        """
        last = rows[-1] if rows else ""
        screen.move(row, min(4 + len(last), max(width - 1, 0)))

    def _rule(self, screen: Any, row: int, width: int) -> None:
        """Draw a horizontal divider.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        row : int
            Screen row.
        width : int
            Screen width.

        Returns
        -------
        None
            Divider is drawn.
        """
        self._add(
            screen, row, 0, "-" * max(width, 1), width, curses.color_pair(1)
        )

    def _add(
        self,
        screen: Any,
        row: int,
        column: int,
        text: str,
        width: int,
        attr: int,
    ) -> None:
        """Write clipped text without failing on small terminals.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        row : int
            Screen row.
        column : int
            Screen column.
        text : str
            Text to draw.
        width : int
            Maximum writable width.
        attr : int
            Curses display attributes.

        Returns
        -------
        None
            Text is written when space permits.
        """
        if row >= 0 and width > 0:
            screen.addnstr(row, column, text, width, attr)

    def _model_name(self) -> str:
        """Return the configured model label.

        Returns
        -------
        str
            Model label or default marker.
        """
        return getattr(self.agent.client, "model", None) or "openrouter/free"

    def _handle(self, key: Any) -> bool:
        """Handle one keyboard event.

        Parameters
        ----------
        key : Any
            Curses key event.

        Returns
        -------
        bool
            Whether the interface continues.
        """
        if key in ("\x03", "\x04"):
            return False
        if key == curses.KEY_RESIZE:
            return True
        if key == curses.KEY_MOUSE:
            return self._handle_mouse()
        return self._submit() if self._is_confirm(key) else self._edit(key)

    def _edit(self, key: Any) -> bool:
        """Apply one editor or transcript-scroll key.

        Parameters
        ----------
        key : Any
            Curses key event.

        Returns
        -------
        bool
            Whether the interface continues.
        """
        if key in self._scroll_keys():
            return self._scroll(key)
        if key in (curses.KEY_BACKSPACE, "\x08", "\x7f"):
            self.prompt = self.prompt[:-1]
        elif isinstance(key, str) and key.isprintable():
            self.prompt += key
        return True

    def _submit(self) -> bool:
        """Submit the current prompt.

        Returns
        -------
        bool
            Whether the interface continues.
        """
        prompt, self.prompt = self.prompt.strip(), ""
        if prompt == "/quit":
            return False
        if prompt and self._worker is None:
            self._start_worker(prompt)
        return True

    def _begin_prompt(self, prompt: str) -> None:
        """Append the user prompt and enter the thinking state.

        Parameters
        ----------
        prompt : str
            User prompt.

        Returns
        -------
        None
            Transcript and status are updated.
        """
        self.lines.append(f"you> {prompt}")
        self.status = "thinking"
        self.scroll = 0
        self._suggestion_map = {}

    def _start_worker(self, prompt: str) -> None:
        """Run a prompt on a background thread so the UI keeps animating.

        Parameters
        ----------
        prompt : str
            User prompt.

        Returns
        -------
        None
            The worker thread is started.
        """
        self._begin_prompt(prompt)
        self._result, self._error = None, None
        self._done.clear()
        self._worker = threading.Thread(
            target=self._work, args=(prompt,), daemon=True
        )
        self._worker.start()

    def _work(self, prompt: str) -> None:
        """Run the agent and capture its result or error.

        Parameters
        ----------
        prompt : str
            User prompt.

        Returns
        -------
        None
            The result is stored and completion is signalled.
        """
        try:
            self._result = self.agent.run(prompt)
        except Exception as exc:
            self._error = exc
        finally:
            self._done.set()

    def _finish_worker(self) -> None:
        """Append the worker's answer and leave the thinking state.

        Returns
        -------
        None
            Transcript and status are updated.
        """
        self._worker = None
        self.scroll = 0
        self._append_answer(self._worker_text())
        self._append_suggestions()
        self.status = "error" if self._error else "ready"

    def _worker_text(self) -> str:
        """Return the worker answer or its error text.

        Returns
        -------
        str
            Answer text, or a readable error.
        """
        if self._error is not None:
            return f"error: {self._error}"
        return self._result or ""

    def _request_question(self, question: str, options: list[str]) -> str:
        """Ask the main thread to present a question.

        Parameters
        ----------
        question : str
            Question text.
        options : list[str]
            Suggested answers.

        Returns
        -------
        str
            The answer chosen by the user.
        """
        response: dict = {}
        event = threading.Event()
        self._ui_requests.put((question, options, response, event))
        event.wait()
        return str(response.get("answer", ""))

    def _append_answer(self, response: str) -> None:
        """Append an assistant answer, preserving paragraph breaks.

        Parameters
        ----------
        response : str
            Final assistant text.

        Returns
        -------
        None
            Answer lines are appended to the transcript.
        """
        lines = response.splitlines() or [""]
        self.lines.append(f"agent> {lines[0]}")
        for line in lines[1:]:
            self.lines.append(line)

    def _append_suggestions(self) -> None:
        """Append clickable suggestions from the last answer.

        Returns
        -------
        None
            Suggestion lines and their hit map are recorded.
        """
        suggestions = self._take_suggestions()
        if not suggestions:
            return
        self.lines.append("")
        self.lines.append("  Suggestions:")
        for action in suggestions:
            self._suggestion_map[len(self.lines)] = action
            self.lines.append(f"  \u25b8 {action}")

    def _take_suggestions(self) -> list[str]:
        """Read and clear the agent's pending suggestions.

        Returns
        -------
        list[str]
            Short suggestion labels, newest only.
        """
        raw = getattr(self.agent.tools, "suggestions", None)
        self.agent.tools.suggestions = []
        if not isinstance(raw, (list, tuple)):
            return []
        return [str(item) for item in raw][:4]

    def _enable_mouse(self) -> None:
        """Enable mouse click reporting when the terminal allows it.

        Returns
        -------
        None
            Mouse reporting is requested.
        """
        try:
            curses.mousemask(curses.ALL_MOUSE_EVENTS)
        except curses.error:
            pass

    def _handle_mouse(self) -> bool:
        """Scroll or run a suggestion based on a mouse event.

        Returns
        -------
        bool
            Whether the interface continues.
        """
        event = self._mouse_event()
        if event is None:
            return True
        _, row, state = event
        if self._scroll_wheel(state):
            return True
        return self._click_suggestion(row, state)

    def _mouse_event(self) -> tuple[int, int, int] | None:
        """Return the pending mouse event coordinates.

        Returns
        -------
        tuple[int, int, int] or None
            ``(x, row, state)`` or ``None`` when unavailable.
        """
        try:
            _, x, row, _, state = curses.getmouse()
        except curses.error:
            return None
        return x, row, state

    def _scroll_wheel(self, state: int) -> bool:
        """Scroll the transcript for a wheel event.

        Parameters
        ----------
        state : int
            Mouse button state bits.

        Returns
        -------
        bool
            Whether a wheel event was handled.
        """
        if state & curses.BUTTON4_PRESSED:
            self.scroll = self._clamp_scroll(self.scroll + 3)
            return True
        if state & curses.BUTTON5_PRESSED:
            self.scroll = self._clamp_scroll(self.scroll - 3)
            return True
        return False

    def _click_suggestion(self, row: int, state: int) -> bool:
        """Run the suggestion under a left click.

        Parameters
        ----------
        row : int
            Clicked screen row.
        state : int
            Mouse button state bits.

        Returns
        -------
        bool
            Whether the interface continues.
        """
        action = self._suggestion_hit.get(row)
        pressed = state & (curses.BUTTON1_CLICKED | curses.BUTTON1_RELEASED)
        if action and pressed and self._worker is None:
            self._start_worker(action)
        return True

    def _scroll_keys(self) -> tuple:
        """Return the transcript scroll key codes.

        Returns
        -------
        tuple
            Key codes that scroll the transcript.
        """
        return (
            curses.KEY_UP,
            curses.KEY_DOWN,
            curses.KEY_PPAGE,
            curses.KEY_NPAGE,
            curses.KEY_HOME,
            curses.KEY_END,
        )

    def _scroll(self, key: Any) -> bool:
        """Adjust the transcript scroll offset for one key.

        Parameters
        ----------
        key : Any
            Scroll key event.

        Returns
        -------
        bool
            Whether the interface continues.
        """
        if key == curses.KEY_HOME:
            self.scroll = self._max_scroll
            return True
        if key == curses.KEY_END:
            self.scroll = 0
            return True
        self.scroll = self._clamp_scroll(self.scroll + self._scroll_delta(key))
        return True

    def _scroll_delta(self, key: Any) -> int:
        """Return the row delta for a scroll key.

        Parameters
        ----------
        key : Any
            Scroll key event.

        Returns
        -------
        int
            Positive to scroll up, negative to scroll down.
        """
        if key == curses.KEY_UP:
            return 1
        if key == curses.KEY_DOWN:
            return -1
        page = max(self._visible_rows, 1)
        return page if key == curses.KEY_PPAGE else -page

    def _clamp_scroll(self, value: int) -> int:
        """Clamp a scroll offset to the transcript bounds.

        Parameters
        ----------
        value : int
            Requested offset.

        Returns
        -------
        int
            Offset constrained to ``[0, _max_scroll]``.
        """
        return max(0, min(value, self._max_scroll))

    def _ask_user(self, question: str, options: list[str]) -> str:
        """Ask the user a question and return the chosen answer.

        Parameters
        ----------
        question : str
            Question text.
        options : list[str]
            Suggested answers.

        Returns
        -------
        str
            Selected option or typed answer.
        """
        entries = [str(item) for item in options] + ["Type your own answer"]
        self.screen.timeout(-1)
        answer = self._run_choice(question, entries)
        self.lines.extend([f"? {question}", f"you> {answer}"])
        return answer

    def _run_choice(self, question: str, entries: list[str]) -> str:
        """Render the option picker until the user decides.

        Parameters
        ----------
        question : str
            Question text.
        entries : list[str]
            Selectable entries.

        Returns
        -------
        str
            Selected option or typed answer.
        """
        self._choice = 0
        while True:
            self._draw_question(question, entries, self._choice)
            decision = self._choice_key(entries)
            if decision is not None:
                return self._choice_result(entries, decision)

    def _choice_key(self, entries: list[str]) -> int | None:
        """Handle one key press in the option picker.

        Parameters
        ----------
        entries : list[str]
            Selectable entries.

        Returns
        -------
        int or None
            Chosen index, or ``None`` while browsing.
        """
        key = self.screen.get_wch()
        if self._move_choice(key, len(entries)):
            return None
        if self._is_confirm(key):
            return self._choice
        return self._number_choice(key, len(entries))

    def _move_choice(self, key: Any, count: int) -> bool:
        """Move the picker selection for an arrow key.

        Parameters
        ----------
        key : Any
            Key event.
        count : int
            Number of entries.

        Returns
        -------
        bool
            Whether the selection moved.
        """
        if self._is_up(key):
            self._choice = (self._choice - 1) % count
            return True
        if self._is_down(key):
            self._choice = (self._choice + 1) % count
            return True
        return False

    def _choice_result(self, entries: list[str], decision: int) -> str:
        """Resolve a picker decision into an answer string.

        Parameters
        ----------
        entries : list[str]
            Selectable entries.
        decision : int
            Chosen index.

        Returns
        -------
        str
            Selected option or a typed custom answer.
        """
        if decision == len(entries) - 1:
            return self._read_answer()
        return entries[decision]

    def _is_up(self, key: Any) -> bool:
        """Return whether a key means move up.

        Parameters
        ----------
        key : Any
            Key event.

        Returns
        -------
        bool
            Whether the key moves the selection up.
        """
        return key in (curses.KEY_UP, "k")

    def _is_down(self, key: Any) -> bool:
        """Return whether a key means move down.

        Parameters
        ----------
        key : Any
            Key event.

        Returns
        -------
        bool
            Whether the key moves the selection down.
        """
        return key in (curses.KEY_DOWN, "j")

    def _is_confirm(self, key: Any) -> bool:
        """Return whether a key confirms the selection.

        Parameters
        ----------
        key : Any
            Key event.

        Returns
        -------
        bool
            Whether the key submits the current choice.
        """
        return key in ("\n", "\r", curses.KEY_ENTER)

    def _number_choice(self, key: Any, count: int) -> int | None:
        """Convert a digit key into an option index.

        Parameters
        ----------
        key : Any
            Key event.
        count : int
            Number of entries.

        Returns
        -------
        int or None
            Zero-based index, or ``None`` for a non-digit key.
        """
        if not (isinstance(key, str) and key.isdigit()):
            return None
        index = int(key) - 1
        return index if 0 <= index < count else None

    def _draw_question(
        self, question: str, entries: list[str], selected: int
    ) -> None:
        """Draw the question and option list.

        Parameters
        ----------
        question : str
            Question text.
        entries : list[str]
            Selectable entries.
        selected : int
            Highlighted index.

        Returns
        -------
        None
            Screen is updated.
        """
        screen = self.screen
        screen.erase()
        height, width = screen.getmaxyx()
        self._add(
            screen,
            0,
            0,
            "  MINIMAL HARNESS  /  QUESTION",
            width,
            curses.color_pair(1) | curses.A_BOLD,
        )
        row = self._question_text(screen, question, width)
        self._option_rows(screen, entries, selected, row, width)
        self._add(
            screen,
            height - 1,
            0,
            "  arrows + Enter, or press a number",
            width,
            curses.color_pair(3),
        )
        screen.refresh()

    def _question_text(self, screen: Any, question: str, width: int) -> int:
        """Draw wrapped question text.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        question : str
            Question text.
        width : int
            Screen width.

        Returns
        -------
        int
            First free row below the question.
        """
        row = 2
        lines = textwrap.wrap(question, width=max(width - 4, 8)) or [question]
        for line in lines:
            self._add(
                screen,
                row,
                0,
                "  " + line,
                width,
                curses.color_pair(4) | curses.A_BOLD,
            )
            row += 1
        return row + 1

    def _option_rows(
        self,
        screen: Any,
        entries: list[str],
        selected: int,
        row: int,
        width: int,
    ) -> None:
        """Draw the option rows, highlighting the selection.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        entries : list[str]
            Selectable entries.
        selected : int
            Highlighted index.
        row : int
            First option row.
        width : int
            Screen width.

        Returns
        -------
        None
            Option rows are drawn.
        """
        for index, entry in enumerate(entries):
            self._add(
                screen,
                row + index,
                0,
                f"  [{index + 1}] {entry}",
                width,
                self._option_attr(index, selected),
            )

    def _option_attr(self, index: int, selected: int) -> int:
        """Return the display attribute for an option row.

        Parameters
        ----------
        index : int
            Option index.
        selected : int
            Highlighted index.

        Returns
        -------
        int
            Curses display attributes.
        """
        if index == selected:
            return curses.A_REVERSE | curses.color_pair(2)
        return curses.color_pair(4)

    def _read_answer(self) -> str:
        """Collect a typed custom answer.

        Returns
        -------
        str
            Trimmed answer text.
        """
        answer = ""
        while True:
            self._draw_answer(answer)
            key = self.screen.get_wch()
            if self._is_confirm(key):
                return answer.strip()
            answer = self._edit_answer(answer, key)

    def _draw_answer(self, text: str) -> None:
        """Draw the custom-answer prompt.

        Parameters
        ----------
        text : str
            Current answer text.

        Returns
        -------
        None
            Screen is updated.
        """
        screen = self.screen
        screen.erase()
        height, width = screen.getmaxyx()
        self._add(
            screen,
            0,
            0,
            "  MINIMAL HARNESS  /  YOUR ANSWER",
            width,
            curses.color_pair(1) | curses.A_BOLD,
        )
        self._add(
            screen,
            2,
            0,
            "  Type your answer and press Enter:",
            width,
            curses.color_pair(4),
        )
        self._add(screen, 4, 0, "  > " + text, width, curses.color_pair(2))
        screen.move(4, min(4 + len(text), max(width - 1, 0)))
        screen.refresh()

    def _edit_answer(self, answer: str, key: Any) -> str:
        """Apply one editing key to the typed answer.

        Parameters
        ----------
        answer : str
            Current text.
        key : Any
            Key event.

        Returns
        -------
        str
            Updated text.
        """
        if key in (curses.KEY_BACKSPACE, "\x08", "\x7f"):
            return answer[:-1]
        if isinstance(key, str) and key.isprintable():
            return answer + key
        return answer
