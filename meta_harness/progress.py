"""Live progress dashboard for the adversarial optimization loop."""

import curses
import queue
import threading
import time
from typing import Any

from .pipeline import SearchPipeline

_FALLBACK = "?"
_CANDIDATE_HEADER = "  id            review   gate1    gate2    score   status"
_DESCRIBE = {
    "run_started": lambda e: f"run started: {e.get('iterations')} iterations",
    "iteration_started": lambda e: f"iteration {e.get('iteration')} started",
    "stage_started": lambda e: f"  {e.get('stage')} running",
    "stage_finished": lambda e: f"  {e.get('stage')} complete",
    "reviewed": lambda e: _review_line(e),
    "gate1": lambda e: _gate_line("gate1", e),
    "gate2": lambda e: _gate_line("gate2", e),
    "adjudicated": lambda e: f"  adjudicator selected {e.get('selected')}",
    "candidate_recorded": lambda e: _candidate_line(e),
    "iteration_finished": lambda e: _iteration_line(e),
    "run_finished": lambda e: f"run finished: {e.get('stop_reason')}",
}


def _review_line(event: dict) -> str:
    """Format a review result line.

    Parameters
    ----------
    event : dict
        Reviewed event.

    Returns
    -------
    str
        Log line.
    """
    verdict = "pass" if event.get("passed") else "block"
    return f"  review {event.get('candidate_id')}: {verdict}"


def _gate_line(name: str, event: dict) -> str:
    """Format a gate-result line.

    Parameters
    ----------
    name : str
        Gate name, ``gate1`` or ``gate2``.
    event : dict
        Gate event.

    Returns
    -------
    str
        Log line.
    """
    key = "final_passed" if name == "gate2" else "passed"
    passed = event.get(key)
    score = event.get("score")
    return (
        f"  {name} {event.get('candidate_id')}: passed={passed} score={score}"
    )


def _candidate_line(event: dict) -> str:
    """Format a finalized candidate line.

    Parameters
    ----------
    event : dict
        Candidate record event.

    Returns
    -------
    str
        Log line.
    """
    status = "finalist" if event.get("final_passed") else "dropped"
    score = event.get("score")
    return f"candidate {event.get('candidate_id')}: {status} score={score}"


def _iteration_line(event: dict) -> str:
    """Format an end-of-iteration line.

    Parameters
    ----------
    event : dict
        Iteration-finished event.

    Returns
    -------
    str
        Log line.
    """
    best = event.get("winner_id")
    score = event.get("winner_score")
    return f"iteration {event.get('iteration')} best={best} score={score}"


def _mark(value: object) -> str:
    """Return a yes/no/dash marker for a boolean flag.

    Parameters
    ----------
    value : object
        Flag value, possibly unknown.

    Returns
    -------
    str
        ``yes``, ``no``, or ``-``.
    """
    if value is None:
        return "-"
    return "yes" if value else "no"


def _score(value: object) -> str:
    """Format a candidate score.

    Parameters
    ----------
    value : object
        Score value.

    Returns
    -------
    str
        Score text or a dash.
    """
    return "-" if value is None else f"{float(value):.2f}"


def _status(row: dict) -> str:
    """Return a short status label for a candidate row.

    Parameters
    ----------
    row : dict
        Candidate row state.

    Returns
    -------
    str
        Status label.
    """
    if row.get("final"):
        return "finalist"
    if row.get("gate"):
        return "gated"
    if row.get("review") is False:
        return "blocked"
    return "pending"


def _format_candidate(row: dict) -> str:
    """Format one candidate table row.

    Parameters
    ----------
    row : dict
        Candidate row state.

    Returns
    -------
    str
        Fixed-width table row.
    """
    return (
        f"  {str(row.get('id')):<14}{_mark(row.get('review')):<9}"
        f"{_mark(row.get('gate')):<9}{_mark(row.get('final')):<9}"
        f"{_score(row.get('score')):<8}{_status(row)}"
    )


class ProgressState:
    """Reduce pipeline progress events into dashboard-friendly state."""

    def __init__(self, total: int, seed: str = "") -> None:
        """Initialize empty dashboard state.

        Parameters
        ----------
        total : int
            Total planned iterations.
        seed : str
            Seed task description.

        Returns
        -------
        None
            This initializer mutates the instance.
        """
        self.total, self.seed = total, seed
        self.iteration, self.stage = 0, "starting"
        self.started, self.finished = time.monotonic(), None
        self.log, self.order, self.candidates = [], [], {}
        self.winner_id, self.winner_score = None, None
        self.usage, self.stop_reason = "calls=0", ""
        self.cancelled, self.done = False, False

    def apply(self, event: dict) -> None:
        """Fold one progress event into the dashboard state.

        Parameters
        ----------
        event : dict
            Progress event carrying an ``event`` key.

        Returns
        -------
        None
            State is updated in place.
        """
        line = _describe(event)
        if line:
            self.log.append(line)
        handler = getattr(self, "_on_" + str(event.get("event", "")), None)
        if handler is not None:
            handler(event)

    def _on_run_started(self, event: dict) -> None:
        """Record the planned iteration count.

        Parameters
        ----------
        event : dict
            Run-started event.

        Returns
        -------
        None
            State is updated.
        """
        self.total = int(event.get("iterations", self.total))

    def _on_iteration_started(self, event: dict) -> None:
        """Record the active iteration number.

        Parameters
        ----------
        event : dict
            Iteration-started event.

        Returns
        -------
        None
            State is updated.
        """
        self.iteration = int(event.get("iteration", self.iteration))

    def _on_stage_started(self, event: dict) -> None:
        """Record the active stage name.

        Parameters
        ----------
        event : dict
            Stage-started event.

        Returns
        -------
        None
            State is updated.
        """
        self.stage = str(event.get("stage", self.stage))

    def _on_stage_finished(self, event: dict) -> None:
        """Mark the active stage as idle.

        Parameters
        ----------
        event : dict
            Stage-finished event.

        Returns
        -------
        None
            State is updated.
        """
        self.stage = "idle"

    def _on_reviewed(self, event: dict) -> None:
        """Record a candidate review verdict.

        Parameters
        ----------
        event : dict
            Reviewed event.

        Returns
        -------
        None
            Candidate row is updated.
        """
        self._ensure(event.get("candidate_id"))["review"] = bool(
            event.get("passed")
        )

    def _on_gate1(self, event: dict) -> None:
        """Record a first-gate result.

        Parameters
        ----------
        event : dict
            Gate-one event.

        Returns
        -------
        None
            Candidate row is updated.
        """
        row = self._ensure(event.get("candidate_id"))
        row["gate"] = bool(event.get("passed"))
        row["score"] = event.get("score")

    def _on_gate2(self, event: dict) -> None:
        """Record a final-gate result.

        Parameters
        ----------
        event : dict
            Gate-two event.

        Returns
        -------
        None
            Candidate row is updated.
        """
        self._ensure(event.get("candidate_id"))["final"] = bool(
            event.get("final_passed")
        )

    def _on_candidate_recorded(self, event: dict) -> None:
        """Record a finalized candidate summary.

        Parameters
        ----------
        event : dict
            Candidate record event.

        Returns
        -------
        None
            Candidate row is updated.
        """
        self._ensure(event.get("candidate_id")).update(self._record(event))

    def _on_iteration_finished(self, event: dict) -> None:
        """Record the best candidate after an iteration.

        Parameters
        ----------
        event : dict
            Iteration-finished event.

        Returns
        -------
        None
            State is updated.
        """
        self.winner_id = event.get("winner_id")
        self.winner_score = event.get("winner_score")

    def _on_run_finished(self, event: dict) -> None:
        """Record the terminal run outcome.

        Parameters
        ----------
        event : dict
            Run-finished event.

        Returns
        -------
        None
            State is finalized.
        """
        self.winner_id = event.get("winner_id", self.winner_id)
        self.winner_score = event.get("winner_score", self.winner_score)
        self.stop_reason = str(event.get("stop_reason", ""))
        self.cancelled = bool(event.get("cancelled"))
        self.finished = time.monotonic()
        self.done = True

    def _record(self, event: dict) -> dict:
        """Build a candidate partial update from a record event.

        Parameters
        ----------
        event : dict
            Candidate record event.

        Returns
        -------
        dict
            Candidate row fields.
        """
        return {
            "id": str(event.get("candidate_id", _FALLBACK)),
            "review": event.get("review_passed"),
            "gate": event.get("gate_passed"),
            "final": event.get("final_passed"),
            "score": event.get("score"),
        }

    def _ensure(self, candidate_id: object) -> dict:
        """Return the mutable row for a candidate, creating it if new.

        Parameters
        ----------
        candidate_id : object
            Candidate identifier.

        Returns
        -------
        dict
            Candidate row state.
        """
        cid = str(candidate_id) if candidate_id else _FALLBACK
        if cid not in self.candidates:
            self.order.append(cid)
            self.candidates[cid] = self._blank(cid)
        return self.candidates[cid]

    def _blank(self, candidate_id: str) -> dict:
        """Create an empty candidate row.

        Parameters
        ----------
        candidate_id : str
            Candidate identifier.

        Returns
        -------
        dict
            Empty row with unknown flags.
        """
        return {
            "id": candidate_id,
            "review": None,
            "gate": None,
            "final": None,
            "score": None,
        }


def _describe(event: dict) -> str:
    """Return a one-line log message for a progress event.

    Parameters
    ----------
    event : dict
        Progress event.

    Returns
    -------
    str
        Log line, or an empty string for an unknown event.
    """
    builder = _DESCRIBE.get(str(event.get("event", "")))
    return "" if builder is None else builder(event)


class ProgressTUI:
    """Render a live dashboard while a search pipeline runs."""

    def __init__(self, pipeline: SearchPipeline, seed: str) -> None:
        """Initialize the live progress interface.

        Parameters
        ----------
        pipeline : SearchPipeline
            Pipeline to run and observe.
        seed : str
            Seed task description.

        Returns
        -------
        None
            This initializer mutates the instance.
        """
        self.pipeline, self.seed = pipeline, seed
        self.state = ProgressState(pipeline.config.iterations, seed)
        self.events: queue.Queue[dict] = queue.Queue()
        self.cancel = threading.Event()
        self.error: Exception | None = None
        self.result = None
        self._thread: threading.Thread | None = None

    def run(self) -> None:
        """Run the pipeline behind a live dashboard.

        Returns
        -------
        None
            The dashboard exits after the pipeline finishes.
        """
        self._start()
        curses.wrapper(self._screen)
        self._thread.join(timeout=2)
        print(self._summary())

    def _start(self) -> None:
        """Wire the observer and launch the worker thread.

        Returns
        -------
        None
            Worker thread is started.
        """
        self.pipeline.observer = self.events.put
        self.pipeline.should_stop = self.cancel.is_set
        self._thread = threading.Thread(target=self._work, daemon=True)
        self._thread.start()

    def _work(self) -> None:
        """Run the pipeline and capture its result or error.

        Returns
        -------
        None
            Outcome is stored on the instance.
        """
        try:
            self.result = self.pipeline.run(self.seed)
        except Exception as exc:
            self.error = exc
            self.events.put({"event": "run_finished", "stop_reason": str(exc)})

    def _screen(self, screen: Any) -> None:
        """Drive the dashboard until the run ends and ``q`` is pressed.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.

        Returns
        -------
        None
            The interface exits on completion.
        """
        self._setup(screen)
        while not self._finished_step(screen):
            pass

    def _finished_step(self, screen: Any) -> bool:
        """Render one frame and handle the quit/cancel key.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.

        Returns
        -------
        bool
            ``True`` when a finished run should exit the interface.
        """
        self._pump()
        self._draw(screen)
        key = self._key(screen)
        if key in ("q", "Q") and not self.state.done:
            self.cancel.set()
        return key in ("q", "Q") and self.state.done

    def _key(self, screen: Any) -> str | None:
        """Read one key with a short timeout.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.

        Returns
        -------
        str or None
            Key character, or ``None`` on timeout.
        """
        screen.timeout(200)
        try:
            return str(screen.get_wch())
        except curses.error:
            return None

    def _pump(self) -> None:
        """Drain queued events and refresh the usage line.

        Returns
        -------
        None
            State is updated.
        """
        while not self.events.empty():
            self.state.apply(self.events.get_nowait())
        self.state.usage = self._usage()

    def _usage(self) -> str:
        """Return the client usage summary when available.

        Returns
        -------
        str
            Usage string.
        """
        try:
            return self.pipeline.client.usage_summary()
        except (AttributeError, TypeError):
            return self.state.usage

    def _setup(self, screen: Any) -> None:
        """Configure terminal behavior and colors.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.

        Returns
        -------
        None
            Terminal settings are applied.
        """
        curses.curs_set(0)
        screen.keypad(True)
        curses.start_color()
        curses.use_default_colors()
        self._colors()

    def _colors(self) -> None:
        """Register the dashboard color palette.

        Returns
        -------
        None
            Curses color pairs are registered.
        """
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_WHITE, -1)
        curses.init_pair(5, curses.COLOR_RED, -1)

    def _draw(self, screen: Any) -> None:
        """Draw the full dashboard.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.

        Returns
        -------
        None
            Screen is updated.
        """
        screen.erase()
        height, width = screen.getmaxyx()
        row = self._header(screen, width)
        self._rule(screen, row, width)
        row = self._candidates(screen, row + 1, width)
        self._activity(screen, row, height - 2, width)
        self._footer(screen, height, width)
        screen.refresh()

    def _header(self, screen: Any, width: int) -> int:
        """Draw the title, status, and progress line.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        width : int
            Screen width.

        Returns
        -------
        int
            First free row below the header.
        """
        title = "  MINIMAL HARNESS  /  LIVE OPTIMIZE"
        self._add(
            screen, 0, 0, title, width, curses.color_pair(1) | curses.A_BOLD
        )
        self._add(
            screen, 1, 0, self._status_text(), width, curses.color_pair(3)
        )
        self._add(
            screen, 2, 0, self._progress_text(), width, curses.color_pair(4)
        )
        return 3

    def _status_text(self) -> str:
        """Compose the iteration and elapsed status line.

        Returns
        -------
        str
            Status text.
        """
        stage = "done" if self.state.done else self.state.stage
        window = f"{self.state.iteration}/{self.state.total}"
        clock = self._elapsed()
        return f"  iteration {window}   |   stage: {stage}   |   {clock}"

    def _progress_text(self) -> str:
        """Compose a textual progress bar line.

        Returns
        -------
        str
            Progress bar and winner text.
        """
        total = max(self.state.total, 1)
        filled = int(20 * self.state.iteration / total)
        bar = "[" + "#" * filled + "-" * (20 - filled) + "]"
        winner = self.state.winner_id or "none"
        return f"  {bar}   winner={winner} score={self.state.winner_score}"

    def _elapsed(self) -> str:
        """Return elapsed time as mm:ss.

        Returns
        -------
        str
            Elapsed time.
        """
        now = self.state.finished or time.monotonic()
        span = int(now - self.state.started)
        return f"{span // 60:02d}:{span % 60:02d}"

    def _candidates(self, screen: Any, start: int, width: int) -> int:
        """Draw the candidate table.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        start : int
            First row of the section.
        width : int
            Screen width.

        Returns
        -------
        int
            First free row below the table.
        """
        self._add(screen, start, 0, "  CANDIDATES", width, curses.A_BOLD)
        self._add(
            screen, start + 1, 0, _CANDIDATE_HEADER, width, curses.A_BOLD
        )
        rows = [
            _format_candidate(self.state.candidates[c])
            for c in self.state.order
        ]
        return self._draw_rows(screen, start + 2, rows, width)

    def _draw_rows(
        self, screen: Any, row: int, rows: list[str], width: int
    ) -> int:
        """Draw candidate rows and return the next free row.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        row : int
            Starting row.
        rows : list[str]
            Row texts.
        width : int
            Screen width.

        Returns
        -------
        int
            Row after the last drawn line.
        """
        for offset, text in enumerate(rows):
            self._add(
                screen, row + offset, 0, text, width, curses.color_pair(4)
            )
        return row + len(rows)

    def _activity(
        self, screen: Any, start: int, bottom: int, width: int
    ) -> None:
        """Draw the scrolling activity log.

        Parameters
        ----------
        screen : Any
            Initialized curses screen.
        start : int
            First available row.
        bottom : int
            Exclusive last available row.
        width : int
            Screen width.

        Returns
        -------
        None
            Log lines are drawn.
        """
        self._add(screen, start, 0, "  ACTIVITY", width, curses.A_BOLD)
        visible = max(bottom - start - 1, 0)
        lines = self.state.log[-visible:] if visible else []
        for offset, line in enumerate(lines):
            self._add(
                screen,
                start + 1 + offset,
                0,
                line,
                width,
                curses.color_pair(4),
            )

    def _footer(self, screen: Any, height: int, width: int) -> None:
        """Draw the usage summary and key hint.

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
            Footer is drawn.
        """
        self._rule(screen, height - 2, width)
        self._add(
            screen, height - 1, 0, self._hint(), width, curses.color_pair(3)
        )

    def _hint(self) -> str:
        """Compose the footer hint line.

        Returns
        -------
        str
            Usage, winner, and key hint text.
        """
        if self.state.done:
            winner = self.state.winner_id or "none"
            return f"  {self.state.usage}   |   winner={winner}   |   [q] quit"
        return f"  {self.state.usage}   |   [q] cancel"

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
        if row >= 0:
            self._add(
                screen,
                row,
                0,
                "-" * max(width, 1),
                width,
                curses.color_pair(1),
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
            self._write(screen, row, column, text, width, attr)

    def _write(
        self,
        screen: Any,
        row: int,
        column: int,
        text: str,
        width: int,
        attr: int,
    ) -> None:
        """Write one clipped line, ignoring ncurses corner errors.

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
            Text is written when the terminal allows it.
        """
        try:
            screen.addnstr(row, column, text, max(width, 0), attr)
        except curses.error:
            pass

    def _summary(self) -> str:
        """Return the one-line summary printed after the dashboard.

        Returns
        -------
        str
            Summary text.
        """
        if self.error is not None:
            return f"optimize failed: {self.error}"
        winner = self.state.winner_id or "none"
        score = self.state.winner_score
        reason = self.state.stop_reason
        return f"winner={winner} score={score} {reason}"
