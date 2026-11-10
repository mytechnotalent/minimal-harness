"""Background agent worker with a GUI-thread question bridge."""

import threading
from typing import Any

from PySide6.QtCore import QObject
from PySide6.QtCore import Signal


class QuestionBridge:
    """Carry an agent question to the GUI thread and return the answer."""

    def __init__(self, question: str, options: list[str]) -> None:
        """Prepare a pending prompt.

        Parameters
        ----------
        question : str
            Question text for the user.
        options : list[str]
            Suggested answers.

        Returns
        -------
        None
            The bridge starts unanswered.
        """
        self.question = question
        self.options = options
        self.answer: str = "no answer"
        self.event = threading.Event()


class AgentWorker(QObject):
    """Run blocking agent turns without freezing the event loop."""

    prompt_ready = Signal(str)
    prompt_started = Signal(str)
    started = Signal()
    tool = Signal(str, dict, str)
    answered = Signal(str)
    asked = Signal(str, list, object)
    error = Signal(str)

    def __init__(self, agent: Any) -> None:
        """Configure the worker.

        Parameters
        ----------
        agent : Agent
            Backend agent executed on this worker.

        Returns
        -------
        None
            The worker is ready to process prompts.
        """
        super().__init__()
        self._agent = agent
        agent.observer = self._observe
        self.prompt_ready.connect(self.run)

    def _observe(self, name: str, arguments: dict, content: str) -> None:
        """Forward a tool execution from the worker thread.

        Parameters
        ----------
        name : str
            Tool name.
        arguments : dict
            Tool arguments.
        content : str
            Tool result content.

        Returns
        -------
        None
            The tool signal is emitted.
        """
        self.tool.emit(name, arguments, content)

    def run(self, prompt: str) -> None:
        """Execute one prompt and emit the final reply.

        Parameters
        ----------
        prompt : str
            User message delivered to the agent.

        Returns
        -------
        None
            Output is broadcast through signals.
        """
        self._agent.tools.questioner = self._ask
        self.prompt_started.emit(prompt)
        self.started.emit()
        self._deliver(prompt)

    def _deliver(self, prompt: str) -> None:
        """Run the agent and emit the reply or error.

        Parameters
        ----------
        prompt : str
            User message delivered to the agent.

        Returns
        -------
        None
            Output is broadcast through signals.
        """
        try:
            answer = self._agent.run(prompt)
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.answered.emit(answer)

    def _ask(self, question: str, options: list[str]) -> str:
        """Block until the GUI thread answers a question.

        Parameters
        ----------
        question : str
            Question text for the user.
        options : list[str]
            Suggested answers.

        Returns
        -------
        str
            Chosen answer.
        """
        bridge = QuestionBridge(question, list(options or []))
        self.asked.emit(question, list(options or []), bridge)
        bridge.event.wait()
        return bridge.answer

    def resolve(self, bridge: QuestionBridge, answer: str) -> None:
        """Deliver a GUI answer to a waiting bridge.

        Parameters
        ----------
        bridge : QuestionBridge
            Pending prompt waiting on an answer.
        answer : str
            Selected response.

        Returns
        -------
        None
            The blocked worker resumes.
        """
        bridge.answer = answer
        bridge.event.set()
