"""Convert Markdown tables into readable row blocks."""


def readable_markdown(text: str) -> str:
    """Replace Markdown tables with readable labeled rows.

    Parameters
    ----------
    text : str
        Markdown text.

    Returns
    -------
    str
        Markdown without pipe tables.
    """
    lines = text.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        index = _copy_line(lines, index, output)
    return "\n".join(output)


def _copy_line(lines: list[str], index: int, output: list[str]) -> int:
    """Copy one line or render a table starting at it.

    Parameters
    ----------
    lines : list of str
        Source lines.
    index : int
        Current line index.
    output : list of str
        Output lines.

    Returns
    -------
    int
        Next line index.
    """
    if _is_table_start(lines, index):
        return _render_table(lines, index, output)
    output.append(lines[index])
    return index + 1


def _is_table_start(lines: list[str], index: int) -> bool:
    """Return whether a pipe table starts at one line.

    Parameters
    ----------
    lines : list of str
        Source lines.
    index : int
        Current line index.

    Returns
    -------
    bool
        ``True`` when a header and separator begin here.
    """
    if index + 1 >= len(lines):
        return False
    return lines[index].strip().startswith("|") and _is_rule(lines[index + 1])


def _is_rule(line: str) -> bool:
    """Return whether a line is a Markdown table separator.

    Parameters
    ----------
    line : str
        Candidate separator.

    Returns
    -------
    bool
        ``True`` when every cell is dashes and optional colons.
    """
    if "|" not in line:
        return False
    cells = _cells(line)
    return bool(cells) and all(_is_rule_cell(cell) for cell in cells)


def _cells(line: str) -> list[str]:
    """Split one table row into trimmed cells.

    Parameters
    ----------
    line : str
        Table row.

    Returns
    -------
    list of str
        Cell text.
    """
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_rule_cell(cell: str) -> bool:
    """Return whether one cell is a separator cell.

    Parameters
    ----------
    cell : str
        Cell text.

    Returns
    -------
    bool
        ``True`` for dashes with optional colons.
    """
    text = cell.replace(":", "").replace("-", "").strip()
    return not text


def _render_table(lines: list[str], index: int, output: list[str]) -> int:
    """Render a table as one labeled block per row.

    Parameters
    ----------
    lines : list of str
        Source lines.
    index : int
        Header line index.
    output : list of str
        Output lines.

    Returns
    -------
    int
        Index after the table.
    """
    headers = _cells(lines[index])
    index += 2
    while index < len(lines) and lines[index].strip().startswith("|"):
        output.append(_row_text(headers, _cells(lines[index])))
        output.append("")
        index += 1
    return index


def _row_text(headers: list[str], cells: list[str]) -> str:
    """Join one row's labeled cells into a single line.

    Parameters
    ----------
    headers : list of str
        Column headers.
    cells : list of str
        Row cells.

    Returns
    -------
    str
        Labeled row text.
    """
    parts = [
        f"**{header}:** {cell}" for header, cell in zip(headers, cells) if cell
    ]
    return "; ".join(parts)
