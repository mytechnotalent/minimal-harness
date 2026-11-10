---
name: minimal-harness-python-formatting
description: "Strict formatting, structural, and documentation rules for the minimal-harness Python scripts, including pycodestyle at 79 columns, 8-line function limits, no blank lines within functions, and a ban on en/em dashes. Trigger when writing or refactoring Python code in this repository."
---

# Minimal Harness Python Scripting Rules

The authoritative skill is
`.opencode/skill/embedded-python-standard/SKILL.md`. This file mirrors its
rules for tooling that only scans `.github/`.

## Rules

1. Full PEP 8, enforced by `pycodestyle` at `--max-line-length=79`. Four-space
   indent, no tabs, no trailing whitespace, two blank lines between top-level
   definitions.
2. No function or method longer than 8 executable lines. The docstring does not
   count toward the limit. Split the work into a helper.
3. No blank lines inside a function body.
4. Every module, class, function, and method has a docstring. Function and
   method docstrings contain a `Parameters` section and a `Returns` section
   (write `None` when nothing is returned), in NumPy style.
5. No U+2013 (en dash) or U+2014 (em dash) anywhere. Use the hyphen-minus `-`.
6. Imports are grouped standard library, third party, local, with one import
   per line.

## Verify

```bash
python3 .opencode/skill/embedded-python-standard/audit_python_standard.py
```
