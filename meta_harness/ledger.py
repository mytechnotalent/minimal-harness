"""Deterministic checks for answer arithmetic and constraints."""

import ast
import operator

_TOLERANCE = 0.01
_LEDGER_WORDS = (
    "budget",
    "cost",
    "price",
    "total",
    "calculate",
    "math",
    "protein",
    "calorie",
    "quantity",
    "at least",
    "no more than",
    "maximum",
    "minimum",
    "per day",
    "per week",
    "percent",
    "average",
    "sum",
)
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def needs_ledger(prompt: str, answer: str) -> bool:
    """Return whether an answer has numeric work worth checking.

    Parameters
    ----------
    prompt : str
        User question.
    answer : str
        Draft answer.

    Returns
    -------
    bool
        ``True`` when the text has numbers and a numeric requirement.
    """
    text = f"{prompt}\n{answer}".lower()
    if not any(char.isdigit() for char in text):
        return False
    return any(word in text for word in _LEDGER_WORDS)


def ledger_issues(ledger: dict) -> list[str]:
    """Return arithmetic and constraint issues from a ledger.

    Parameters
    ----------
    ledger : dict
        Extracted ledger.

    Returns
    -------
    list of str
        Human-readable issue strings.
    """
    issues = _computation_issues(ledger.get("computations") or [])
    issues.extend(_constraint_issues(ledger.get("constraints") or []))
    return issues


def evaluate(expression: str) -> float:
    """Evaluate a numeric arithmetic expression safely.

    Parameters
    ----------
    expression : str
        Expression containing numbers, parentheses, and basic operators.

    Returns
    -------
    float
        Evaluated value.
    """
    node = ast.parse(expression, mode="eval")
    return float(_value(node.body))


def _value(node):
    """Return the value of one allowed AST node.

    Parameters
    ----------
    node : ast.AST
        Expression node.

    Returns
    -------
    float
        Numeric value.

    Raises
    ------
    ValueError
        When the node is not pure arithmetic.
    """
    if _is_constant(node):
        return node.value
    if _is_unary(node):
        return _unary(node)
    if _is_binary(node):
        return _binary(node)
    raise ValueError("unsupported expression")


def _is_constant(node) -> bool:
    """Return whether a node is a numeric constant.

    Parameters
    ----------
    node : ast.AST
        Expression node.

    Returns
    -------
    bool
        ``True`` for numeric constants.
    """
    return isinstance(node, ast.Constant) and isinstance(
        node.value, (int, float)
    )


def _is_unary(node) -> bool:
    """Return whether a node is a unary plus or minus.

    Parameters
    ----------
    node : ast.AST
        Expression node.

    Returns
    -------
    bool
        ``True`` for unary numeric operations.
    """
    return isinstance(node, ast.UnaryOp) and isinstance(
        node.op, (ast.UAdd, ast.USub)
    )


def _is_binary(node) -> bool:
    """Return whether a node is an allowed binary operation.

    Parameters
    ----------
    node : ast.AST
        Expression node.

    Returns
    -------
    bool
        ``True`` for supported arithmetic operators.
    """
    return isinstance(node, ast.BinOp) and type(node.op) in _OPS


def _unary(node) -> float:
    """Evaluate a unary plus or minus.

    Parameters
    ----------
    node : ast.UnaryOp
        Unary node.

    Returns
    -------
    float
        Signed value.
    """
    value = _value(node.operand)
    return value if isinstance(node.op, ast.UAdd) else -value


def _binary(node) -> float:
    """Evaluate one binary arithmetic operation.

    Parameters
    ----------
    node : ast.BinOp
        Binary node.

    Returns
    -------
    float
        Operation result.
    """
    left = _value(node.left)
    right = _value(node.right)
    return _OPS[type(node.op)](left, right)


def _computation_issues(items: list) -> list[str]:
    """Return issues for every computation entry.

    Parameters
    ----------
    items : list
        Computation entries.

    Returns
    -------
    list of str
        Issues for entries that do not reconcile.
    """
    issues = []
    for item in items:
        issue = _computation_issue(item)
        if issue:
            issues.append(issue)
    return issues


def _computation_issue(item) -> str:
    """Return one computation issue or an empty string.

    Parameters
    ----------
    item : object
        Computation entry.

    Returns
    -------
    str
        Issue text, or an empty string when the entry reconciles.
    """
    if not isinstance(item, dict):
        return ""
    label, expression = _computation_fields(item)
    stated = _number(item.get("stated"))
    actual = _actual(expression)
    if actual is None:
        return f"{label}: could not evaluate {expression!r}"
    return _mismatch(label, stated, actual)


def _computation_fields(item: dict) -> tuple[str, str]:
    """Return the label and expression of one computation.

    Parameters
    ----------
    item : dict
        Computation entry.

    Returns
    -------
    tuple of str
        Label and expression.
    """
    label = str(item.get("label") or "computation")
    expression = str(item.get("expression") or "")
    return label, expression


def _actual(expression: str):
    """Return a safe evaluation or ``None``.

    Parameters
    ----------
    expression : str
        Arithmetic expression.

    Returns
    -------
    float or None
        Evaluated value, or ``None`` when invalid.
    """
    try:
        return evaluate(expression)
    except (ValueError, SyntaxError, ZeroDivisionError):
        return None


def _mismatch(label: str, stated, actual: float) -> str:
    """Return a mismatch message when a stated value is wrong.

    Parameters
    ----------
    label : str
        Computation label.
    stated : float or None
        Number claimed by the answer.
    actual : float
        Recomputed value.

    Returns
    -------
    str
        Mismatch message, or an empty string.
    """
    if stated is None or _close(stated, actual):
        return ""
    return f"{label}: stated {stated:g}, recomputed {actual:g}"


def _number(value):
    """Return a float for a numeric value.

    Parameters
    ----------
    value : object
        Candidate number.

    Returns
    -------
    float or None
        Numeric value, or ``None`` for booleans and non-numbers.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _close(first: float, second: float) -> bool:
    """Return whether two numbers agree within tolerance.

    Parameters
    ----------
    first : float
        First number.
    second : float
        Second number.

    Returns
    -------
    bool
        ``True`` when the difference is within tolerance.
    """
    return abs(first - second) <= max(_TOLERANCE, abs(second) * _TOLERANCE)


def _constraint_issues(items: list) -> list[str]:
    """Return issues for partial or omitted constraints.

    Parameters
    ----------
    items : list
        Constraint entries.

    Returns
    -------
    list of str
        Issues for unmet requirements.
    """
    issues = []
    for item in items:
        name = _unmet(item)
        if name:
            issues.append(name)
    return issues


def _unmet(item) -> str:
    """Return one unmet constraint description.

    Parameters
    ----------
    item : object
        Constraint entry.

    Returns
    -------
    str
        Issue text, or an empty string when the constraint is met.
    """
    if not isinstance(item, dict):
        return ""
    if item.get("status") not in ("partial", "omitted"):
        return ""
    name = str(item.get("requirement") or "constraint")
    return f"{name}: {item.get('status')}"
