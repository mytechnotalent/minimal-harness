"""Built-in tools for the Minimal Harness agent runtime."""

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from .web_search import WebSearchClient
from .browser import BrowserClient
from .evaluator import AppEvaluator
from .provider import ProviderCatalog

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
    "list_models": {"free_only": {"type": "boolean"}},
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
            "description": f"Minimal Harness {name} tool",
            "parameters": {"type": "object", "properties": properties},
        },
    }


class ToolError(RuntimeError):
    """Represent a rejected or failed tool operation."""


class ToolRegistry:
    """Register and execute bounded agent tools."""

    def __init__(self, root: Path | str = ".") -> None:
        """Initialize tools rooted at one workspace.

        Parameters
        ----------
        root : pathlib.Path or str
            Workspace root for file operations.

        Returns
        -------
        None
            This initializer configures the registry.
        """
        self.root = Path(root).resolve()
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
        return [self._schema(name) for name in self.tools]

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
        if name not in self.tools:
            raise ToolError(f"Unknown tool: {name}")
        try:
            return json.dumps(self.tools[name](**arguments), default=str)
        except Exception as exc:
            raise ToolError(f"Tool {name} failed: {exc}") from exc

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
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return {"path": path, "bytes": len(content.encode())}

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
        result = self._run_command(command, timeout)
        return self._command_result(result)

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
