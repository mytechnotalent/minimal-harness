"""Responsive full-screen curses interface for the Minimal Harness agent."""

import curses
import textwrap
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
        self.status = "ready"
        self.scroll = 0

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
        while self._draw(screen):
            if not self._handle(screen.get_wch()):
                break

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
        self._transcript(screen, height, width)
        self._input(screen, height, width)
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
        self._add_status(
            screen, width, f"{self.status.upper()}  |  {self._model_name()}"
        )

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

    def _transcript(self, screen: Any, height: int, width: int) -> None:
        """Draw the wrapped conversation area.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        height : int
            Screen height.
        width : int
            Screen width.

        Returns
        -------
        None
            Transcript content is drawn.
        """
        bottom = max(height - 4, 4)
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
        rows = self._wrapped_lines(max(width - 4, 8))
        for row, line in enumerate(rows[-max(bottom - 5, 1) :], 4):
            self._line(screen, row, line, width)

    def _wrapped_lines(self, width: int) -> list[str]:
        """Wrap transcript lines to the available width.

        Parameters
        ----------
        width : int
            Maximum line width.

        Returns
        -------
        list[str]
            Wrapped transcript lines.
        """
        wrapped = []
        for line in self.lines:
            wrapped.extend(textwrap.wrap(line, width=width) or [""])
        return wrapped

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
        color = (
            curses.color_pair(2)
            if line.startswith("you>")
            else curses.color_pair(4)
        )
        self._add(screen, row, 1, line, width - 2, color)

    def _input(self, screen: Any, height: int, width: int) -> None:
        """Draw the active prompt bar.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        height : int
            Screen height.
        width : int
            Screen width.

        Returns
        -------
        None
            Input bar is drawn.
        """
        self._input_label(screen, height, width)
        self._input_text(screen, height, width, self._visible_prompt(width))

    def _input_label(self, screen: Any, height: int, width: int) -> None:
        """Draw the prompt label.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        height : int
            Screen height.
        width : int
            Screen width.

        Returns
        -------
        None
            Prompt label is drawn.
        """
        self._add(
            screen,
            height - 2,
            0,
            "  YOU  /  ENTER TO SEND",
            width,
            curses.color_pair(2) | curses.A_BOLD,
        )

    def _visible_prompt(self, width: int) -> str:
        """Return the visible portion of the prompt.

        Parameters
        ----------
        width : int
            Screen width.

        Returns
        -------
        str
            Rightmost visible prompt text.
        """
        return self.prompt[-max(width - 6, 1) :]

    def _input_text(
        self, screen: Any, height: int, width: int, visible: str
    ) -> None:
        """Draw prompt text and place the cursor.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        height : int
            Screen height.
        width : int
            Screen width.
        visible : str
            Visible prompt text.

        Returns
        -------
        None
            Prompt and cursor are drawn.
        """
        self._add_prompt(screen, height, width, visible)
        screen.move(height - 1, min(4 + len(visible), max(width - 1, 0)))

    def _add_prompt(
        self, screen: Any, height: int, width: int, visible: str
    ) -> None:
        """Draw the visible prompt text.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        height : int
            Screen height.
        width : int
            Screen width.
        visible : str
            Visible prompt text.

        Returns
        -------
        None
            Prompt text is drawn.
        """
        self._add(
            screen,
            height - 1,
            0,
            "  > " + visible,
            width,
            curses.color_pair(4),
        )

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
        if key in ("\n", "\r", curses.KEY_ENTER):
            return self._submit()
        if key == curses.KEY_RESIZE:
            return True
        return self._edit(key)

    def _edit(self, key: Any) -> bool:
        """Apply one editor key.

        Parameters
        ----------
        key : Any
            Curses key event.

        Returns
        -------
        bool
            Whether the interface continues.
        """
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
        if prompt:
            self._run_prompt(prompt)
        return True

    def _run_prompt(self, prompt: str) -> None:
        """Run a prompt and append its response.

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
        self.lines.append(f"agent> {self.agent.run(prompt)}")
        self.status = "ready"
