"""Built-in tools for the Minimal Harness agent runtime."""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from .web_search import WebSearchClient
from .browser import BrowserClient
from .evaluator import AppEvaluator
from .provider import ProviderCatalog

PROTECTED_DIRS = {"meta_harness", "gui", "tests", "docs", "benchmarks", ".git"}

TOOL_SCHEMAS = {
    "read": {"path": {"type": "string"}},
    "write": {"path": {"type": "string"}, "content": {"type": "string"}},
    "edit": {
        "path": {"type": "string"},
        "old": {"type": "string"},
        "new": {"type": "string"},
    },
    "bash": {"command": {"type": "string"}, "timeout": {"type": "integer"}},
    "web_search": {"query": {"type": "string"}, "limit": {"type": "integer"}},
    "browser_open": {"url": {"type": "string"}},
    "browser_screenshot": {
        "url": {"type": "string"},
        "path": {"type": "string"},
    },
    "browser_assert": {"url": {"type": "string"}, "text": {"type": "string"}},
    "evaluate_app": {"path": {"type": "string"}},
    "ask": {
        "question": {
            "type": "string",
            "description": "The single question to ask.",
        },
        "options": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Two to five suggested answers.",
        },
    },
    "suggest": {
        "options": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short next-step labels, under the options key.",
        }
    },
    "list_models": {"free_only": {"type": "boolean"}},
}


TOOL_DESCRIPTIONS = {
    "read": "Read a workspace file path; URLs are not valid here.",
    "web_search": (
        "Search the public web and return titles, URLs, and snippets."
    ),
    "browser_open": "Open a web URL and return its title and visible text.",
    "browser_assert": (
        "Open a URL and check that specific visible text is present."
    ),
    "ask": ("Ask the user one question. Call with question and options."),
    "suggest": ("Record short next-step labels. Call with an options array."),
}


def _tool_schema(name: str, properties: dict[str, Any]) -> dict[str, Any]:
    """Build an OpenAI-compatible tool schema.

    Parameters
    ----------
    name : str
        Tool name.
    properties : dict[str, Any]
        Argument properties.

    Returns
    -------
    dict[str, Any]
        Tool schema.
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": TOOL_DESCRIPTIONS.get(
                name, f"Minimal Harness {name} tool"
            ),
            "parameters": {"type": "object", "properties": properties},
        },
    }


def _output_limit() -> int:
    """Return the configured tool-output character limit.

    Returns
    -------
    int
        Maximum serialized characters returned to the model.
    """
    try:
        return max(1000, int(os.getenv("HARNESS_TOOL_OUTPUT_LIMIT", "12000")))
    except ValueError:
        return 12000


def _bound_output(text: str) -> str:
    """Truncate oversized tool output while keeping both ends.

    Parameters
    ----------
    text : str
        Serialized tool result.

    Returns
    -------
    str
        Original text, or a JSON wrapper with clipped output.
    """
    limit = _output_limit()
    if len(text) <= limit:
        return text
    head = text[: limit * 2 // 3]
    tail = text[-(limit // 3) :]
    content = head + "\n...[truncated]...\n" + tail
    return json.dumps({"truncated": True, "output": content})


class ToolError(RuntimeError):
    """Represent a rejected or failed tool operation."""


class ToolRegistry:
    """Register and execute bounded agent tools."""

    def __init__(
        self,
        root: Path | str = ".",
        questioner: Callable[[str, list[str]], str] | None = None,
        require_project_folder: bool = False,
    ) -> None:
        """Initialize tools rooted at one workspace.

        Parameters
        ----------
        root : pathlib.Path or str
            Workspace root for file operations.
        questioner : collections.abc.Callable or None
            Optional callback that presents a question with options and
            returns the user's chosen answer. When absent, the ``ask``
            tool is not advertised.
        require_project_folder : bool
            Refuse new root-level files and harness source files.

        Returns
        -------
        None
            This initializer configures the registry.
        """
        self.root = Path(root).resolve()
        self.questioner = questioner
        self.require_project_folder = require_project_folder
        self.suggestions: list[str] = []
        self.tools = self._tool_map()

    def _tool_map(self) -> dict[str, Callable[..., Any]]:
        """Build the registered tool map.

        Returns
        -------
        dict[str, Callable[..., Any]]
            Tool names and bound implementations.
        """
        return {name: getattr(self, name) for name in TOOL_SCHEMAS}

    def schema(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool schemas.

        Returns
        -------
        list[dict[str, Any]]
            Schemas advertised to the model.
        """
        return [
            self._schema(name)
            for name in self.tools
            if name not in ("ask", "suggest") or self.questioner is not None
        ]

    def _advertised_names(self) -> set[str]:
        """Return currently advertised tool names.

        Returns
        -------
        set[str]
            Tool names exposed to the model.
        """
        return {item["function"]["name"] for item in self.schema()}

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute one named tool.

        Parameters
        ----------
        name : str
            Registered tool name.
        arguments : dict[str, Any]
            Tool arguments.

        Returns
        -------
        str
            JSON result or error message.
        """
        if name not in self._advertised_names():
            raise ToolError(f"Tool not available: {name}")
        try:
            result = self.tools[name](**arguments)
        except Exception as exc:
            raise ToolError(f"Tool {name} failed: {exc}") from exc
        return _bound_output(json.dumps(result, default=str))

    def read(self, path: str) -> dict[str, str]:
        """Read a workspace file.

        Parameters
        ----------
        path : str
            Relative file path.

        Returns
        -------
        dict[str, str]
            Path and file content.
        """
        target = self._path(path)
        return {"path": path, "content": target.read_text()}

    def write(self, path: str, content: str) -> dict[str, Any]:
        """Write a workspace file.

        Parameters
        ----------
        path : str
            Relative file path.
        content : str
            New file content.

        Returns
        -------
        dict[str, Any]
            Written path and byte count.
        """
        target = self._path(path)
        self._check_project_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return {"path": path, "bytes": len(content.encode())}

    def _check_project_path(self, target: Path) -> None:
        """Enforce the project-folder rule for new files.

        Parameters
        ----------
        target : pathlib.Path
            Resolved file path.

        Returns
        -------
        None
            The write is allowed or a ``ToolError`` is raised.
        """
        if not self.require_project_folder or target.exists():
            return
        relative = target.relative_to(self.root)
        if len(relative.parts) < 2:
            raise ToolError("Create a named project folder before writing.")
        if relative.parts[0] in PROTECTED_DIRS:
            raise ToolError("Do not create files in the harness source tree.")

    def edit(self, path: str, old: str, new: str) -> dict[str, Any]:
        """Replace one exact text fragment in a workspace file.

        Parameters
        ----------
        path : str
            Relative file path.
        old : str
            Existing exact text.
        new : str
            Replacement text.

        Returns
        -------
        dict[str, Any]
            Edited path and replacement count.
        """
        target = self._path(path)
        content = target.read_text()
        if content.count(old) != 1:
            raise ToolError("edit requires exactly one matching fragment")
        target.write_text(content.replace(old, new))
        return {"path": path, "replacements": 1}

    def bash(self, command: str, timeout: int = 30) -> dict[str, Any]:
        """Run a shell command in the workspace.

        Parameters
        ----------
        command : str
            Shell command.
        timeout : int
            Maximum execution seconds.

        Returns
        -------
        dict[str, Any]
            Exit code and bounded output.
        """
        if self._is_install(command):
            self._require_install_ok()
        result = self._run_command(command, timeout)
        return self._command_result(result)

    def _is_install(self, command: str) -> bool:
        """Detect package-install commands.

        Parameters
        ----------
        command : str
            Shell command to inspect.

        Returns
        -------
        bool
            Whether the command installs packages.
        """
        text = command.lower()
        pattern = (
            r"\b(pip3?|python\d*(?:\.\d+)?\s+-m\s+pip|npm|yarn|pnpm|"
            r"apt|apt-get|dnf|yum|pacman|brew|choco|winget|cargo|go|"
            r"gem|conda|playwright)\s+(install|i|add|-s)\b"
        )
        return bool(re.search(pattern, text))

    def _require_install_ok(self) -> None:
        """Ask the user to approve a package install.

        Returns
        -------
        None
            Execution continues only after approval.

        Raises
        ------
        ToolError
            When no questioner exists or approval is denied.
        """
        if self.questioner is None:
            raise ToolError("Installing software needs your approval first.")
        answer = self.questioner(
            "I need to download and install a tool for this. " "Is that okay?",
            ["Yes, install it", "No, don't install"],
        )
        if not answer.lower().startswith("yes"):
            raise ToolError(
                "Install declined. Do not install software without "
                "approval."
            )

    def _run_command(
        self, command: str, timeout: int
    ) -> subprocess.CompletedProcess[str]:
        """Run a command in the workspace.

        Parameters
        ----------
        command : str
            Shell command.
        timeout : int
            Timeout seconds.

        Returns
        -------
        subprocess.CompletedProcess[str]
            Process result.
        """
        return subprocess.run(
            command,
            cwd=self.root,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _command_result(
        self, result: subprocess.CompletedProcess[str]
    ) -> dict[str, Any]:
        """Bound process output.

        Parameters
        ----------
        result : subprocess.CompletedProcess[str]
            Process result.

        Returns
        -------
        dict[str, Any]
            Exit code and output.
        """
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-12000:],
        }

    def web_search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        """Search the public web.

        Parameters
        ----------
        query : str
            Search query.
        limit : int
            Maximum result count.

        Returns
        -------
        list[dict[str, str]]
            Public search results.
        """
        return WebSearchClient().search(query, limit)

    def browser_open(self, url: str) -> dict[str, str]:
        """Open a page and return visible metadata.

        Parameters
        ----------
        url : str
            Page URL.

        Returns
        -------
        dict[str, str]
            Page URL, title, and visible text.
        """
        return BrowserClient().open(url)

    def browser_screenshot(self, url: str, path: str) -> dict[str, str]:
        """Capture a page screenshot.

        Parameters
        ----------
        url : str
            Page URL.
        path : str
            Screenshot path inside the workspace.

        Returns
        -------
        dict[str, str]
            Page URL and screenshot path.
        """
        target = self._path(path)
        return BrowserClient().screenshot(url, str(target))

    def browser_assert(self, url: str, text: str) -> dict[str, Any]:
        """Assert visible text on a page.

        Parameters
        ----------
        url : str
            Page URL.
        text : str
            Required visible text.

        Returns
        -------
        dict[str, Any]
            Assertion result.
        """
        return BrowserClient().assert_page(url, text)

    def evaluate_app(self, path: str = ".") -> dict[str, Any]:
        """Score a web application deterministically.

        Parameters
        ----------
        path : str
            Application directory inside the workspace.

        Returns
        -------
        dict[str, Any]
            Deterministic app evaluation.
        """
        return AppEvaluator().evaluate(self._path(path))

    def list_models(self, free_only: bool = False) -> list[dict[str, Any]]:
        """List OpenRouter models.

        Parameters
        ----------
        free_only : bool
            Return only zero-priced models.

        Returns
        -------
        list[dict[str, Any]]
            Provider model records.
        """
        catalog = ProviderCatalog()
        return catalog.free_models() if free_only else catalog.list_models()

    def ask(
        self, question: str, options: list[str] | None = None
    ) -> dict[str, str]:
        """Ask the interactive user a question.

        Parameters
        ----------
        question : str
            Question to present.
        options : list[str] or None
            Suggested answers. The interface always adds a custom option.

        Returns
        -------
        dict[str, str]
            The question and the chosen answer.
        """
        if self.questioner is None:
            raise ToolError("no interactive user is available to answer")
        answer = self.questioner(question, list(options or []))
        return {"question": question, "answer": answer}

    def suggest(self, options: list[str] | None = None) -> dict[str, bool]:
        """Record short optional next-step suggestions.

        Parameters
        ----------
        options : list[str] or None
            Short action-shaped labels. At most four are kept.

        Returns
        -------
        dict[str, bool]
            Acknowledgement that the suggestions were recorded.
        """
        kept = [str(item)[:40] for item in (options or []) if str(item)]
        self.suggestions = kept[:4]
        return {"ok": True}

    def _path(self, path: str) -> Path:
        """Resolve and confine a workspace path.

        Parameters
        ----------
        path : str
            Relative workspace path.

        Returns
        -------
        pathlib.Path
            Confined absolute path.
        """
        target = (self.root / path).resolve()
        if target != self.root and self.root not in target.parents:
            raise ToolError("path escapes workspace")
        return target

    def _schema(self, name: str) -> dict[str, Any]:
        """Build one tool schema.

        Parameters
        ----------
        name : str
            Tool name.

        Returns
        -------
        dict[str, Any]
            OpenAI-compatible function schema.
        """
        return _tool_schema(name, TOOL_SCHEMAS[name])
