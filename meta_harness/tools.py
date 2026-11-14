"""Built-in tools for the Minimal Harness agent runtime."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any
from typing import Callable

from .web_search import WebSearchClient
from .browser import BrowserClient
from .evaluator import AppEvaluator
from .provider import ProviderCatalog

PROTECTED_DIRS = {"meta_harness", "gui", "tests", "docs", "benchmarks", ".git"}
_SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "target",
    "dist",
    "build",
}
_MAX_FILE_BYTES = 1_000_000

_WEB_TOOLS = (
    "web_search",
    "browser_open",
    "browser_screenshot",
    "browser_assert",
)
TOOL_SCHEMAS = {
    "read": {"path": {"type": "string"}},
    "write": {"path": {"type": "string"}, "content": {"type": "string"}},
    "edit": {
        "path": {"type": "string"},
        "old": {"type": "string"},
        "new": {"type": "string"},
    },
    "patch": {
        "path": {"type": "string"},
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                },
            },
        },
    },
    "list": {"path": {"type": "string"}},
    "glob": {"pattern": {"type": "string"}, "limit": {"type": "integer"}},
    "grep": {
        "pattern": {"type": "string"},
        "path": {"type": "string"},
        "limit": {"type": "integer"},
    },
    "repo_map": {"limit": {"type": "integer"}},
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
    "patch": "Apply several old/new edits to one file in a single call.",
    "list": "List one workspace directory with names, types, and sizes.",
    "glob": "Find workspace files by a glob pattern such as **/*.py.",
    "grep": "Search workspace file contents with a regular expression.",
    "repo_map": "Return a compact sorted list of workspace files.",
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
    function = {
        "name": name,
        "description": TOOL_DESCRIPTIONS.get(
            name, f"Minimal Harness {name} tool"
        ),
        "parameters": {"type": "object", "properties": properties},
    }
    return {"type": "function", "function": function}


def _output_limit() -> int:
    """Return the configured tool-output character limit.

    Parameters
    ----------
    None

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


def _skip_path(root: Path, path: Path) -> bool:
    """Return whether a path should be hidden from search tools.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.
    path : pathlib.Path
        Candidate path.

    Returns
    -------
    bool
        ``True`` when the path is outside the root or in a skipped folder.
    """
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(part in _SKIP_DIRS for part in relative.parts)


def _iter_files(target: Path):
    """Yield files under a directory, skipping build and cache folders.

    Parameters
    ----------
    target : pathlib.Path
        File or directory to walk.

    Returns
    -------
    collections.abc.Iterator
        File paths.
    """
    if target.is_file():
        yield target
        return
    for path in target.rglob("*"):
        if path.is_file() and not _skip_path(target, path):
            yield path


def _line_number(content: str, index: int) -> int:
    """Return the one-based line number for a character index.

    Parameters
    ----------
    content : str
        File content.
    index : int
        Character offset.

    Returns
    -------
    int
        One-based line number.
    """
    return content.count("\n", 0, index) + 1


def _read_text(path: Path) -> str | None:
    """Read a text file, returning None for binary or oversized files.

    Parameters
    ----------
    path : pathlib.Path
        File to read.

    Returns
    -------
    str or None
        Decoded text, or ``None`` when unavailable.
    """
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _entry(child: Path) -> dict[str, Any]:
    """Describe one directory entry.

    Parameters
    ----------
    child : pathlib.Path
        Directory entry.

    Returns
    -------
    dict[str, Any]
        Name, type, and size.
    """
    kind = "file" if child.is_file() else "dir"
    size = child.stat().st_size if child.is_file() else 0
    return {"name": child.name, "type": kind, "size": size}


def _directory_entries(target: Path) -> list[dict[str, Any]]:
    """Return sorted entries for a directory or file path.

    Parameters
    ----------
    target : pathlib.Path
        Directory or file.

    Returns
    -------
    list[dict[str, Any]]
        Entry descriptions.
    """
    if not target.exists():
        raise ToolError("path not found")
    if target.is_file():
        return [_entry(target)]
    return _visible_entries(target)


def _visible_entries(target: Path) -> list[dict[str, Any]]:
    """Return sorted visible entries for a directory.

    Parameters
    ----------
    target : pathlib.Path
        Directory.

    Returns
    -------
    list[dict[str, Any]]
        Entry descriptions.
    """
    return [
        _entry(child)
        for child in sorted(target.iterdir())
        if not child.name.startswith(".") and child.name not in _SKIP_DIRS
    ]


def _glob_files(root: Path, pattern: str, limit: int) -> list[str]:
    """Return workspace files matching a glob pattern.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.
    pattern : str
        Glob pattern.
    limit : int
        Maximum result count.

    Returns
    -------
    list[str]
        Relative file paths.
    """
    if pattern.startswith(("/", "..")):
        raise ToolError("pattern must stay inside the workspace")
    return _matched_files(root, pattern, limit)


def _matched_files(root: Path, pattern: str, limit: int) -> list[str]:
    """Return files matching a safe glob pattern.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.
    pattern : str
        Glob pattern.
    limit : int
        Maximum result count.

    Returns
    -------
    list[str]
        Relative file paths.
    """
    files = []
    for path in sorted(root.glob(pattern)):
        if path.is_file() and not _skip_path(root, path):
            files.append(str(path.relative_to(root)))
        if len(files) >= limit:
            break
    return files


def _file_matches(path: Path, root: Path, regex, limit: int) -> list[dict]:
    """Return matching lines from one file.

    Parameters
    ----------
    path : pathlib.Path
        File to search.
    root : pathlib.Path
        Workspace root.
    regex : re.Pattern
        Compiled pattern.
    limit : int
        Maximum matches.

    Returns
    -------
    list[dict]
        Path, line number, and text for each match.
    """
    text = _read_text(path)
    if text is None:
        return []
    relative = str(path.relative_to(root))
    return _line_records(text, relative, regex, limit)


def _line_records(text: str, relative: str, regex, limit: int) -> list[dict]:
    """Return matching line records for one file.

    Parameters
    ----------
    text : str
        File content.
    relative : str
        Relative file path.
    regex : re.Pattern
        Compiled pattern.
    limit : int
        Maximum records.

    Returns
    -------
    list[dict]
        Match records.
    """
    found = [
        {"path": relative, "line": number, "text": line[:200]}
        for number, line in enumerate(text.splitlines(), start=1)
        if regex.search(line)
    ]
    return found[:limit]


def _grep_path(target: Path, root: Path, regex, limit: int) -> list[dict]:
    """Return matching lines from a file or directory.

    Parameters
    ----------
    target : pathlib.Path
        File or directory.
    root : pathlib.Path
        Workspace root.
    regex : re.Pattern
        Compiled pattern.
    limit : int
        Maximum matches.

    Returns
    -------
    list[dict]
        Match records.
    """
    files = [target] if target.is_file() else list(_iter_files(target))
    return _collect_matches(files, root, regex, limit)


def _collect_matches(files, root: Path, regex, limit: int) -> list[dict]:
    """Collect matching lines from a list of files.

    Parameters
    ----------
    files : list
        Candidate files.
    root : pathlib.Path
        Workspace root.
    regex : re.Pattern
        Compiled pattern.
    limit : int
        Maximum matches.

    Returns
    -------
    list[dict]
        Match records.
    """
    matches = []
    for path in files:
        if _skip_path(root, path):
            continue
        matches.extend(_file_matches(path, root, regex, limit - len(matches)))
        if len(matches) >= limit:
            break
    return matches


def _repo_files(root: Path, limit: int) -> list[str]:
    """Return a sorted relative file list for a repository map.

    Parameters
    ----------
    root : pathlib.Path
        Workspace root.
    limit : int
        Maximum file count.

    Returns
    -------
    list[str]
        Relative file paths.
    """
    files = []
    for path in _iter_files(root):
        if _skip_path(root, path):
            continue
        files.append(str(path.relative_to(root)))
        if len(files) >= limit:
            break
    return sorted(files)


def _duplicate_hint(content: str, old: str) -> str:
    """Return an error that lists the first matching line.

    Parameters
    ----------
    content : str
        File content.
    old : str
        Repeated fragment.

    Returns
    -------
    str
        Error text.
    """
    line = _line_number(content, content.index(old))
    return f"edit fragment is not unique; first match at line {line}"


def _pattern_hint(content: str, matches: list) -> str:
    """Return an error that lists duplicate fuzzy-match lines.

    Parameters
    ----------
    content : str
        File content.
    matches : list
        Regex match objects.

    Returns
    -------
    str
        Error text.
    """
    lines = [_line_number(content, match.start()) for match in matches[:5]]
    numbers = ", ".join(str(line) for line in lines)
    return f"edit fragment is not unique; matches at lines {numbers}"


def _fuzzy_match(content: str, old: str) -> tuple[int, int]:
    """Return the span of one whitespace-insensitive match.

    Parameters
    ----------
    content : str
        File content.
    old : str
        Fragment to find.

    Returns
    -------
    tuple[int, int]
        Start and end offsets.
    """
    pattern = r"\s+".join(re.escape(part) for part in old.split())
    matches = list(re.finditer(pattern, content))
    if len(matches) == 1:
        return matches[0].span()
    if matches:
        raise ToolError(_pattern_hint(content, matches))
    raise ToolError("edit fragment not found; read the file and retry")


def _apply_edit(content: str, old: str, new: str) -> tuple[str, int]:
    """Replace one fragment, allowing whitespace-insensitive matches.

    Parameters
    ----------
    content : str
        File content.
    old : str
        Existing fragment.
    new : str
        Replacement text.

    Returns
    -------
    tuple[str, int]
        Updated content and replacement count.
    """
    count = content.count(old)
    if count == 1:
        return content.replace(old, new), 1
    if count > 1:
        raise ToolError(_duplicate_hint(content, old))
    span = _fuzzy_match(content, old)
    return content[: span[0]] + new + content[span[1] :], 1


def _apply_patches(content: str, edits: list[dict[str, str]]) -> str:
    """Apply a list of old/new edits in order.

    Parameters
    ----------
    content : str
        File content.
    edits : list[dict[str, str]]
        Old/new fragments.

    Returns
    -------
    str
        Updated content.
    """
    if not edits:
        raise ToolError("patch needs at least one edit")
    updated = content
    for edit in edits:
        updated, _ = _apply_edit(updated, edit["old"], edit["new"])
    return updated


_TEST_MARKERS = (
    "FAILED ",
    "ERROR:",
    "FAIL:",
    "AssertionError",
    "Ran ",
    "FAILED (",
)


_TEST_PREFIXES = (
    "FAILED ",
    "FAILED (",
    "ERROR:",
    "FAIL:",
    "E   ",
    "AssertionError",
)


def _keep_test_line(line: str) -> bool:
    """Return whether a line is useful test failure output.

    Parameters
    ----------
    line : str
        Output line.

    Returns
    -------
    bool
        ``True`` for summary and failure lines.
    """
    return line.startswith(_TEST_PREFIXES) or line.startswith("Ran ")


def _compact_test_output(text: str) -> str:
    """Keep failing test lines instead of a full test log.

    Parameters
    ----------
    text : str
        Command output.

    Returns
    -------
    str
        Bounded output.
    """
    if not any(marker in text for marker in _TEST_MARKERS):
        return text[-12000:]
    lines = [line for line in text.splitlines() if _keep_test_line(line)]
    return "\n".join(lines[:60])[-4000:] or text[-4000:]


_SAFE_PATHS = {"/dev/null", "/dev/stdout", "/dev/stderr"}


def _command_tokens(command: str) -> list[str]:
    """Split a shell command into tokens for path checks.

    Parameters
    ----------
    command : str
        Shell command.

    Returns
    -------
    list[str]
        Command tokens.
    """
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _inside_workspace(token: str, root: Path) -> bool:
    """Return whether a path token resolves inside the workspace.

    Parameters
    ----------
    token : str
        Path token.
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    bool
        ``True`` when the path is inside the root.
    """
    try:
        Path(token).resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _escapes_workspace(token: str, root: Path) -> bool:
    """Return whether a token points outside the workspace.

    Parameters
    ----------
    token : str
        Command token.
    root : pathlib.Path
        Workspace root.

    Returns
    -------
    bool
        ``True`` when the token must be rejected.
    """
    if token.startswith(("~", "..")):
        return True
    if token.startswith("/"):
        return not _inside_workspace(token, root) and token not in _SAFE_PATHS
    return False


class ToolError(RuntimeError):
    """Represent a rejected or failed tool operation."""


class ToolRegistry:
    """Register and execute bounded agent tools."""

    def __init__(
        self,
        root: Path | str = ".",
        questioner: Callable[[str, list[str]], str] | None = None,
        require_project_folder: bool = False,
        web_enabled: bool = True,
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

        web_enabled : bool
            Advertise web and browser tools.

        Returns
        -------
        None
            This initializer configures the registry.
        """
        self.root = Path(root).resolve()
        self.questioner = questioner
        self.require_project_folder = require_project_folder
        self.web_enabled = web_enabled
        self.suggestions: list[str] = []
        self.tools = self._tool_map()

    def _tool_map(self) -> dict[str, Callable[..., Any]]:
        """Build the registered tool map.

        Parameters
        ----------
        None

        Returns
        -------
        dict[str, Callable[..., Any]]
            Tool names and bound implementations.
        """
        names = [
            name
            for name in TOOL_SCHEMAS
            if self.web_enabled or name not in _WEB_TOOLS
        ]
        return {name: getattr(self, name) for name in names}

    def schema(self, names=None) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool schemas.

        Parameters
        ----------
        names : iterable or None
            Optional tool names to advertise.

        Returns
        -------
        list[dict[str, Any]]
            Schemas advertised to the model.
        """
        selected = self.tools if names is None else names
        return [
            self._schema(name)
            for name in selected
            if name not in ("ask", "suggest") or self.questioner is not None
        ]

    def _advertised_names(self) -> set[str]:
        """Return currently advertised tool names.

        Parameters
        ----------
        None

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
        updated, count = _apply_edit(content, old, new)
        target.write_text(updated)
        return {"path": path, "replacements": count}

    def patch(self, path: str, edits: list[dict[str, str]]) -> dict[str, Any]:
        """Apply several exact edits to one workspace file.

        Parameters
        ----------
        path : str
            Relative file path.
        edits : list[dict[str, str]]
            Old and new fragments.

        Returns
        -------
        dict[str, Any]
            Edited path and replacement count.
        """
        target = self._path(path)
        updated = _apply_patches(target.read_text(), edits)
        target.write_text(updated)
        return {"path": path, "replacements": len(edits)}

    def list(self, path: str = ".") -> dict[str, Any]:
        """List one workspace directory.

        Parameters
        ----------
        path : str
            Relative directory path.

        Returns
        -------
        dict[str, Any]
            Entries with name, type, and size.
        """
        entries = _directory_entries(self._path(path))
        return {"path": path, "entries": entries, "count": len(entries)}

    def glob(self, pattern: str, limit: int = 100) -> dict[str, Any]:
        """Find workspace files by glob pattern.

        Parameters
        ----------
        pattern : str
            Glob such as ``**/*.py``.
        limit : int
            Maximum result count.

        Returns
        -------
        dict[str, Any]
            Matching relative paths.
        """
        files = _glob_files(self.root, pattern, max(1, limit))
        return {"pattern": pattern, "files": files, "count": len(files)}

    def grep(
        self, pattern: str, path: str = ".", limit: int = 50
    ) -> dict[str, Any]:
        """Search workspace file contents with a regular expression.

        Parameters
        ----------
        pattern : str
            Regular expression.
        path : str
            Relative file or directory.
        limit : int
            Maximum match count.

        Returns
        -------
        dict[str, Any]
            Path, line, and text for each match.
        """
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            raise ToolError(f"invalid pattern: {exc}") from exc
        matches = _grep_path(self._path(path), self.root, regex, limit)
        return {"pattern": pattern, "matches": matches, "count": len(matches)}

    def repo_map(self, limit: int = 200) -> dict[str, Any]:
        """Return a compact sorted list of workspace files.

        Parameters
        ----------
        limit : int
            Maximum file count.

        Returns
        -------
        dict[str, Any]
            Relative file paths.
        """
        files = _repo_files(self.root, max(1, limit))
        return {"files": files, "count": len(files)}

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
        self._check_command(command)
        if self._is_install(command):
            self._require_install_ok()
        result = self._run_command(command, timeout)
        return self._command_result(result)

    def _check_command(self, command: str) -> None:
        """Reject shell commands that reach outside the workspace.

        Parameters
        ----------
        command : str
            Shell command.

        Returns
        -------
        None
            The command is allowed or ``ToolError`` is raised.
        """
        for token in _command_tokens(command):
            if _escapes_workspace(token, self.root):
                raise ToolError(f"command path escapes workspace: {token}")

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

        Parameters
        ----------
        None

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
        answer = self._ask_install()
        if not answer.lower().startswith("yes"):
            raise ToolError(
                "Install declined. Do not install software without "
                "approval."
            )

    def _ask_install(self) -> str:
        """Ask the user to approve a package install.

        Parameters
        ----------
        None

        Returns
        -------
        str
            The user's answer text.
        """
        return self.questioner(
            "I need to download and install a tool for this. Is that okay?",
            ["Yes, install it", "No, don't install"],
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
            "stdout": _compact_test_output(result.stdout),
            "stderr": _compact_test_output(result.stderr),
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
