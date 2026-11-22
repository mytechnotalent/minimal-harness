"""Deterministic checks for answer arithmetic and constraints."""

import ast
import operator
import re

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
_LIMIT_HEAD = (
    r"(?:under|fewer than|less than|at most|no more than|maximum of"
    r"|max of|limit of)"
)
_LIMIT_TAIL = r"(?:or fewer|or less|maximum|max|limit)"
_LIMIT_PATTERNS = (
    ("words", re.compile(_LIMIT_HEAD + r"\s+(\d+)\s+words?\b", re.I)),
    ("words", re.compile(r"in\s+(\d+)\s+words?\b", re.I)),
    (
        "words",
        re.compile(r"(\d+)\s+words?\s+" + _LIMIT_TAIL + r"\b", re.I),
    ),
    (
        "characters",
        re.compile(_LIMIT_HEAD + r"\s+(\d+)\s+(?:characters?|chars?)\b", re.I),
    ),
)


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
        ``True`` when the text has numbers and a numeric or limit
        requirement.
    """
    if _limit_hit(prompt):
        return True
    text = f"{prompt}\n{answer}".lower()
    if not any(char.isdigit() for char in text):
        return False
    return any(word in text for word in _LEDGER_WORDS)


def limit_issues(prompt: str, answer: str) -> list[str]:
    """Return word or character limit violations in an answer.

    Parameters
    ----------
    prompt : str
        User question.
    answer : str
        Draft answer.

    Returns
    -------
    list of str
        One issue per exceeded limit.
    """
    issues: list[str] = []
    for unit, pattern in _LIMIT_PATTERNS:
        match = pattern.search(prompt)
        if match:
            issues.extend(_limit_issue(unit, int(match.group(1)), answer))
    return list(dict.fromkeys(issues))


def _limit_hit(prompt: str) -> bool:
    """Return whether the prompt states a word or character limit.

    Parameters
    ----------
    prompt : str
        User question.

    Returns
    -------
    bool
        ``True`` when a limit pattern matches.
    """
    return any(pattern.search(prompt) for _, pattern in _LIMIT_PATTERNS)


def _limit_issue(unit: str, limit: int, answer: str) -> list[str]:
    """Return the issue for one stated limit.

    Parameters
    ----------
    unit : str
        Either words or characters.
    limit : int
        Maximum allowed count.
    answer : str
        Draft answer.

    Returns
    -------
    list of str
        Empty when within the limit, otherwise one issue.
    """
    actual = _count_unit(unit, answer)
    if actual <= limit:
        return []
    return [f"answer has {actual} {unit} but the limit is {limit}"]


def _count_unit(unit: str, answer: str) -> int:
    """Count words or characters in the answer.

    Parameters
    ----------
    unit : str
        Either words or characters.
    answer : str
        Draft answer.

    Returns
    -------
    int
        Count for the requested unit.
    """
    if unit == "words":
        return len(answer.split())
    return len(answer)


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
    computations = ledger.get("computations") or []
    issues = _computation_issues(computations)
    issues.extend(_distribution_issues(ledger.get("distributions") or []))
    issues.extend(_period_issues(computations))
    issues.extend(_constraint_issues(ledger.get("constraints") or []))
    return issues


def _distribution_issues(items: list) -> list[str]:
    """Return issues for percentages that do not sum correctly.

    Parameters
    ----------
    items : list
        Distribution entries.

    Returns
    -------
    list of str
        Issues for distributions that do not reconcile.
    """
    issues = []
    for item in items:
        issue = _distribution_issue(item)
        if issue:
            issues.append(issue)
    return issues


def _distribution_issue(item) -> str:
    """Return one distribution issue or an empty string.

    Parameters
    ----------
    item : object
        Distribution entry.

    Returns
    -------
    str
        Issue text, or an empty string when it reconciles.
    """
    if not isinstance(item, dict):
        return ""
    parts = item.get("parts") or []
    if not parts:
        return ""
    return _distribution_check(item, parts)


def _distribution_check(item: dict, parts: list) -> str:
    """Return the reconciliation message for one distribution.

    Parameters
    ----------
    item : dict
        Distribution entry.
    parts : list
        Distribution parts.

    Returns
    -------
    str
        Mismatch message, or an empty string.
    """
    label = str(item.get("label") or "distribution")
    total = _number(item.get("total"))
    actual = _parts_sum(parts)
    if actual is None:
        return f"{label}: could not read distribution percentages"
    expected = 100.0 if total is None else total
    return _mismatch(f"{label} percentages", expected, actual)


def _parts_sum(parts: list):
    """Return the sum of part percentages.

    Parameters
    ----------
    parts : list
        Distribution parts.

    Returns
    -------
    float or None
        Sum, or ``None`` when a part is not numeric.
    """
    values = [
        _number(part.get("percent"))
        for part in parts
        if isinstance(part, dict)
    ]
    if not values or any(value is None for value in values):
        return None
    return sum(values)


def _period_issues(entries: list) -> list[str]:
    """Return issues for inconsistent monthly and annual totals.

    Parameters
    ----------
    entries : list
        Computation entries.

    Returns
    -------
    list of str
        Issues for derived period totals that do not reconcile.
    """
    issues = []
    for item in entries:
        issue = _period_issue(entries, item)
        if issue:
            issues.append(issue)
    return issues


def _period_issue(entries: list, item) -> str:
    """Return one period issue or an empty string.

    Parameters
    ----------
    entries : list
        Computation entries.
    item : object
        Computation entry.

    Returns
    -------
    str
        Issue text, or an empty string when it reconciles.
    """
    if not isinstance(item, dict):
        return ""
    base = _find_entry(entries, item.get("derived_from"))
    if base is None:
        return ""
    return _period_check(item, base)


def _period_check(item: dict, base: dict) -> str:
    """Return the reconciliation message for one period total.

    Parameters
    ----------
    item : dict
        Current computation entry.
    base : dict
        Base computation entry.

    Returns
    -------
    str
        Mismatch message, or an empty string.
    """
    factor = _period_factor(item.get("period"), base.get("period"))
    stated = _number(item.get("stated"))
    base_stated = _number(base.get("stated"))
    if factor is None or stated is None or base_stated is None:
        return ""
    return _period_mismatch(item, stated, base_stated * factor)


def _find_entry(entries: list, label):
    """Return the computation with a matching label.

    Parameters
    ----------
    entries : list
        Computation entries.
    label : object
        Wanted label.

    Returns
    -------
    dict or None
        Matching entry.
    """
    for entry in entries:
        if isinstance(entry, dict) and entry.get("label") == label:
            return entry
    return None


def _period_factor(period, base_period):
    """Return the multiplier from the base period to the current period.

    Parameters
    ----------
    period : object
        Current period.
    base_period : object
        Base period.

    Returns
    -------
    float or None
        Multiplier, or ``None`` when the pair is unsupported.
    """
    factors = {
        ("year", "month"): 12.0,
        ("month", "year"): 1 / 12,
    }
    return factors.get((period, base_period))


def _period_mismatch(item: dict, stated: float, expected: float) -> str:
    """Return the period mismatch message.

    Parameters
    ----------
    item : dict
        Computation entry.
    stated : float
        Number claimed by the answer.
    expected : float
        Value derived from the base period.

    Returns
    -------
    str
        Mismatch message, or an empty string.
    """
    label = str(item.get("label") or "period total")
    return _mismatch(label, stated, expected, _number(item.get("tolerance")))


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
    if not expression:
        return _missing_expression(item, label, stated)
    return _evaluated(label, expression, stated, item)


def _evaluated(label: str, expression: str, stated, item: dict) -> str:
    """Return the issue for a computation with an expression.

    Parameters
    ----------
    label : str
        Computation label.
    expression : str
        Arithmetic expression.
    stated : float or None
        Number claimed by the answer.
    item : dict
        Computation entry.

    Returns
    -------
    str
        Issue text, or an empty string when the entry reconciles.
    """
    actual = _actual(expression)
    if actual is None:
        return f"{label}: could not evaluate {expression!r}"
    return _mismatch(label, stated, actual, _number(item.get("tolerance")))


def _missing_expression(item: dict, label: str, stated) -> str:
    """Return an issue for a derived total with no arithmetic.

    Parameters
    ----------
    item : dict
        Computation entry.
    label : str
        Computation label.
    stated : float or None
        Number claimed by the answer.

    Returns
    -------
    str
        Issue text, or an empty string when the entry is not derived.
    """
    if not item.get("derived") or stated is None:
        return ""
    return f"{label}: stated {stated:g} has no arithmetic to verify"


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


def _mismatch(label: str, stated, actual: float, tolerance=None) -> str:
    """Return a mismatch message when a stated value is wrong.

    Parameters
    ----------
    label : str
        Computation label.
    stated : float or None
        Number claimed by the answer.
    actual : float
        Recomputed value.
    tolerance : float or None
        Absolute rounding tolerance.

    Returns
    -------
    str
        Mismatch message, or an empty string.
    """
    if stated is None or _close(stated, actual, tolerance):
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


def _close(first: float, second: float, tolerance=None) -> bool:
    """Return whether two numbers agree within tolerance.

    Parameters
    ----------
    first : float
        First number.
    second : float
        Second number.
    tolerance : float or None
        Absolute rounding tolerance from the answer.

    Returns
    -------
    bool
        ``True`` when the difference is within tolerance.
    """
    if tolerance is not None and tolerance >= 0:
        return abs(first - second) <= tolerance
    return abs(first - second) <= _TOLERANCE


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
    status = str(item.get("status") or "")
    if status not in ("partial", "omitted", "impossible"):
        return ""
    return _unmet_text(item, status)


def _unmet_text(item, status: str) -> str:
    """Return the issue text for one unmet constraint.

    Parameters
    ----------
    item : object
        Constraint entry.
    status : str
        Unmet status label.

    Returns
    -------
    str
        Issue text naming the requirement.
    """
    name = str(item.get("requirement") or "constraint")
    if status != "impossible":
        return f"{name}: {status}"
    reason = str(item.get("evidence") or "no reason given")
    return f"{name}: impossible ({reason})"
