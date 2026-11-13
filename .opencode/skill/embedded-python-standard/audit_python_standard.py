"""Audit project Python files against the embedded Python standard."""

import ast
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "e2e-workspaces",
    "independent",
    "minimal_harness.egg-info",
    "node_modules",
    "runs",
}
PYCODESTYLE = [
    "--max-line-length=79",
    "--ignore=E121,E123,E126,E203,E226,E24,E704,W503,W504",
]
SECTION_NAMES = ("Parameters", "Returns")


def discover():
    """Collect every Python file subject to the standard.

    Parameters
    ----------
    None

    Returns
    -------
    list of pathlib.Path
        Project Python files outside generated directories.
    """
    found = []
    for base, dirs, names in os.walk(REPO):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
        found.extend(_python_paths(base, names))
    return found


def _python_paths(base, names):
    """Collect Python files in one walked directory.

    Parameters
    ----------
    base : str
        Directory path being walked.

    names : list of str
        Filenames directly inside that directory.

    Returns
    -------
    list of pathlib.Path
        Paths for the directory's Python files.
    """
    return [Path(base) / name for name in names if name.endswith(".py")]


def style_issues(paths):
    """Run pycodestyle at 79 columns over the file list.

    Parameters
    ----------
    paths : list of pathlib.Path
        Files subject to the style check.

    Returns
    -------
    list of str
        One formatted issue per pycodestyle finding.
    """
    command = [sys.executable, "-m", "pycodestyle", *PYCODESTYLE]
    command.extend(str(path) for path in paths)
    result = subprocess.run(command, capture_output=True, text=True)
    if "No module named" in result.stderr:
        return [result.stderr.strip()]
    return result.stdout.splitlines()


def dash_issues(path, text):
    """Report en and em dashes found in one source file.

    Parameters
    ----------
    path : pathlib.Path
        File being scanned.

    text : str
        Complete file text.

    Returns
    -------
    list of str
        One issue per source line containing a dash.
    """
    numbered = enumerate(text.splitlines(), 1)
    return [
        f"{path}:{lineno}: DASH hyphen-minus required"
        for lineno, line in numbered
        if "\u2013" in line or "\u2014" in line
    ]


def _file_issues(path, locals_):
    """Run every AST-level check on one file.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    locals_ : set of str
        Local top-level module names.

    Returns
    -------
    list of str
        Every structural issue found in the file.
    """
    text = path.read_text(encoding="utf-8")
    issues = dash_issues(path, text)
    issues.extend(ast_issues(path, text, locals_))
    return issues


def ast_issues(path, text, locals_):
    """Check docstrings, bodies, and imports in parsed source.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    text : str
        Complete file text.

    locals_ : set of str
        Local top-level module names.

    Returns
    -------
    list of str
        Syntax, docstring, body, and import issues.
    """
    tree = _parse(path, text)
    if isinstance(tree, str):
        return [tree]
    issues = []
    lines = text.splitlines()
    _check_definitions(path, tree, lines, issues)
    _check_imports(path, tree, lines, issues, locals_)
    return issues


def _parse(path, text):
    """Parse source text or return a formatted syntax issue.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    text : str
        Complete file text.

    Returns
    -------
    ast.Module or str
        Parsed tree, or one syntax issue string.
    """
    try:
        return ast.parse(text)
    except SyntaxError as exc:
        return f"{path}:{exc.lineno}: SYNTAX {exc.msg}"


def _check_definitions(path, tree, lines, issues):
    """Check modules, classes, and functions for rule violations.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    tree : ast.Module
        Parsed module.

    lines : list of str
        Source lines.

    issues : list of str
        Issue collector mutated in place.

    Returns
    -------
    None
        Found issues are appended to the collector.
    """
    if not ast.get_docstring(tree):
        issues.append(f"{path}:1: DOC module docstring required")
    for node in ast.walk(tree):
        _check_node(path, node, lines, issues)


def _check_node(path, node, lines, issues):
    """Dispatch one node to its class or function checker.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    node : ast.AST
        Node visited from the module tree.

    lines : list of str
        Source lines.

    issues : list of str
        Issue collector mutated in place.

    Returns
    -------
    None
        Found issues are appended to the collector.
    """
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef)
    if isinstance(node, ast.ClassDef):
        _check_class(path, node, issues)
    if isinstance(node, kinds):
        _check_function(path, node, lines, issues)


def _check_class(path, node, issues):
    """Require a docstring on a class.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    node : ast.ClassDef
        Class definition being checked.

    issues : list of str
        Issue collector mutated in place.

    Returns
    -------
    None
        An issue is appended when the docstring is missing.
    """
    if not ast.get_docstring(node):
        issues.append(f"{path}:{node.lineno}: DOC class docstring required")


def _check_function(path, node, lines, issues):
    """Check one function or method definition.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    node : ast.FunctionDef or ast.AsyncFunctionDef
        Definition being checked.

    lines : list of str
        Source lines.

    issues : list of str
        Issue collector mutated in place.

    Returns
    -------
    None
        Found issues are appended to the collector.
    """
    doc = ast.get_docstring(node)
    if not doc:
        issues.append(f"{path}:{node.lineno}: DOC docstring required")
        return
    _check_sections(path, node, doc, issues)
    _check_body(path, node, lines, issues)


def _check_sections(path, node, doc, issues):
    """Require Parameters and Returns sections in definition docstrings.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    node : ast.FunctionDef or ast.AsyncFunctionDef
        Definition owning the docstring.

    doc : str
        Docstring text.

    issues : list of str
        Issue collector mutated in place.

    Returns
    -------
    None
        A missing-section issue is appended once.
    """
    headers = {line.strip() for line in doc.splitlines()}
    missing = [name for name in SECTION_NAMES if name not in headers]
    if missing:
        joined = " and ".join(missing)
        issues.append(f"{path}:{node.lineno}: SECT {joined} section required")


def _check_body(path, node, lines, issues):
    """Check the 8-line limit and the blank-line ban.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    node : ast.FunctionDef or ast.AsyncFunctionDef
        Definition being measured.

    lines : list of str
        Source lines.

    issues : list of str
        Issue collector mutated in place.

    Returns
    -------
    None
        Found issues are appended to the collector.
    """
    covered = _statement_lines(node)
    if len(covered) > 8:
        count = len(covered)
        issues.append(f"{path}:{node.lineno}: LEN {count} executable lines")
    span = covered | _docstring_span(node)
    _check_blanks(path, node, span, lines, issues)


def _statement_lines(node):
    """Collect executable line numbers of a definition body.

    Parameters
    ----------
    node : ast.FunctionDef or ast.AsyncFunctionDef
        Definition being measured.

    Returns
    -------
    set of int
        Source lines covered by non-docstring statements.
    """
    doc = _docstring_node(node)
    covered = set()
    for stmt in node.body:
        if stmt is not doc:
            covered.update(range(stmt.lineno, stmt.end_lineno + 1))
    return covered


def _docstring_node(node):
    """Return the docstring statement of a definition.

    Parameters
    ----------
    node : ast.AST
        Definition or module node.

    Returns
    -------
    ast.Expr or None
        The first constant-string statement, if present.
    """
    body = getattr(node, "body", [])
    first = body[0] if body else None
    if isinstance(first, ast.Expr):
        value = first.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return first
    return None


def _docstring_span(node):
    """Collect the source lines of a definition's docstring.

    Parameters
    ----------
    node : ast.AST
        Definition node with an optional docstring.

    Returns
    -------
    set of int
        Lines occupied by the docstring statement.
    """
    doc = _docstring_node(node)
    if doc is None:
        return set()
    return set(range(doc.lineno, doc.end_lineno + 1))


def _check_blanks(path, node, covered, lines, issues):
    """Reject blank lines inside a function body.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    node : ast.FunctionDef or ast.AsyncFunctionDef
        Definition being checked.

    covered : set of int
        Lines occupied by the body's statements.

    lines : list of str
        Source lines.

    issues : list of str
        Issue collector mutated in place.

    Returns
    -------
    None
        A blank-line issue is appended once.
    """
    if not covered:
        return
    if _blank_lines(covered, lines):
        issues.append(f"{path}:{node.lineno}: BLANK blank line in body")


def _blank_lines(covered, lines):
    """List blank source lines inside a covered span.

    Parameters
    ----------
    covered : set of int
        Lines occupied by the body's statements.

    lines : list of str
        Source lines.

    Returns
    -------
    list of int
        Blank line numbers inside the span.
    """
    inner = range(min(covered), max(covered) + 1)
    return [
        number
        for number in inner
        if number not in covered and not lines[number - 1].strip()
    ]


def _check_imports(path, tree, lines, issues, locals_):
    """Check import order, grouping, and one-per-line rules.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    tree : ast.Module
        Parsed module.

    lines : list of str
        Source lines.

    issues : list of str
        Issue collector mutated in place.

    locals_ : set of str
        Local top-level module names.

    Returns
    -------
    None
        Found issues are appended to the collector.
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _check_single(path, node, issues)
    _check_order(path, tree, lines, issues, locals_)


def _check_single(path, node, issues):
    """Reject star imports and multiple names on one import line.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    node : ast.Import or ast.ImportFrom
        Import statement being checked.

    issues : list of str
        Issue collector mutated in place.

    Returns
    -------
    None
        An issue is appended for offending imports.
    """
    star = any(alias.name == "*" for alias in node.names)
    if star or len(node.names) > 1:
        issues.append(f"{path}:{node.lineno}: IMP1 one import per line")


def _check_order(path, tree, lines, issues, locals_):
    """Enforce stdlib, third-party, then local import ordering.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    tree : ast.Module
        Parsed module.

    lines : list of str
        Source lines.

    issues : list of str
        Issue collector mutated in place.

    locals_ : set of str
        Local top-level module names.

    Returns
    -------
    None
        Found issues are appended to the collector.
    """
    kinds = (ast.Import, ast.ImportFrom)
    imports = [stmt for stmt in tree.body if isinstance(stmt, kinds)]
    categories = [_category(stmt, locals_) for stmt in imports]
    _report_order(path, imports, categories, issues)
    _report_separation(path, imports, categories, lines, issues)


def _root_module(stmt):
    """Return the root module name of an import statement.

    Parameters
    ----------
    stmt : ast.Import or ast.ImportFrom
        Import statement being classified.

    Returns
    -------
    str
        First dotted component of the imported module.
    """
    if isinstance(stmt, ast.Import):
        return stmt.names[0].name.split(".")[0]
    return (stmt.module or "").split(".")[0]


def _category(stmt, locals_):
    """Classify one import statement by source group.

    Parameters
    ----------
    stmt : ast.Import or ast.ImportFrom
        Import statement being classified.

    locals_ : set of str
        Local top-level module names.

    Returns
    -------
    int
        Zero for stdlib, one for third-party, two for local.
    """
    if getattr(stmt, "level", 0):
        return 2
    root = _root_module(stmt)
    if root in locals_:
        return 2
    if root in sys.stdlib_module_names or root == "__future__":
        return 0
    return 1


def _report_order(path, imports, categories, issues):
    """Flag imports that appear after a later import group.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    imports : list of ast.AST
        Module-level import statements in order.

    categories : list of int
        Category code of each import statement.

    issues : list of str
        Issue collector mutated in place.

    Returns
    -------
    None
        Found issues are appended to the collector.
    """
    pairs = zip(categories, categories[1:])
    for index, (previous, current) in enumerate(pairs, 1):
        if current < previous:
            line = imports[index].lineno
            issues.append(f"{path}:{line}: IMPGRP import group order")


def _report_separation(path, imports, categories, lines, issues):
    """Require a blank line between import category groups.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    imports : list of ast.AST
        Module-level import statements in order.

    categories : list of int
        Category code of each import statement.

    lines : list of str
        Source lines.

    issues : list of str
        Issue collector mutated in place.

    Returns
    -------
    None
        Found issues are appended to the collector.
    """
    for index in range(1, len(imports)):
        if categories[index] != categories[index - 1]:
            _check_gap(path, imports, index, issues)


def _check_gap(path, imports, index, issues):
    """Verify a blank line between two adjacent import groups.

    Parameters
    ----------
    path : pathlib.Path
        File being audited.

    imports : list of ast.AST
        Module-level import statements in order.

    index : int
        Position of the later import statement.

    issues : list of str
        Issue collector mutated in place.

    Returns
    -------
    None
        An issue is appended when no blank line separates groups.
    """
    previous = imports[index - 1]
    later = imports[index]
    gap = later.lineno - previous.end_lineno
    if gap < 2:
        issues.append(f"{path}:{later.lineno}: IMPSEP blank line required")


def _local_modules():
    """List top-level module names defined in the repository.

    Parameters
    ----------
    None

    Returns
    -------
    set of str
        Names importable from the repository root.
    """
    names = {"setup_app"}
    for child in REPO.iterdir():
        if (child / "__init__.py").exists():
            names.add(child.name)
    return names


def _collect_ast(paths, locals_):
    """Run AST checks on every audited file.

    Parameters
    ----------
    paths : list of pathlib.Path
        Files subject to the audit.

    locals_ : set of str
        Local top-level module names.

    Returns
    -------
    list of str
        Every structural issue found.
    """
    issues = []
    for path in paths:
        issues.extend(_file_issues(path, locals_))
    return issues


def _report(issues):
    """Print the audit outcome.

    Parameters
    ----------
    issues : list of str
        Every issue found by the audit.

    Returns
    -------
    None
        Issues print one per line with a failure count.
    """
    if issues:
        print("\n".join(issues))
        print(f"failures: {len(issues)}")
    else:
        print("clean")


def main(argv):
    """Audit selected Python files and report every violation.

    Parameters
    ----------
    argv : list of str
        Optional file or directory arguments narrowing the audit.

    Returns
    -------
    int
        Exit status, zero only when every check passes.
    """
    paths = _select(argv)
    locals_ = _local_modules()
    issues = style_issues(paths)
    issues.extend(_collect_ast(paths, locals_))
    _report(issues)
    return 1 if issues else 0


def _select(argv):
    """Choose audit targets from command line arguments.

    Parameters
    ----------
    argv : list of str
        File or directory arguments, empty for the whole repository.

    Returns
    -------
    list of pathlib.Path
        Python files selected for the audit.
    """
    if not argv:
        return discover()
    targets = []
    for argument in argv:
        targets.extend(_expand(Path(argument)))
    return sorted(targets)


def _expand(path):
    """Expand one command line target to Python files.

    Parameters
    ----------
    path : pathlib.Path
        File or directory named on the command line.

    Returns
    -------
    list of pathlib.Path
        Python files under the target.
    """
    if path.is_file():
        return [path]
    found = []
    for base, dirs, names in os.walk(path):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
        found.extend(_python_paths(base, names))
    return found


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
