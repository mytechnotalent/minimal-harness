---
name: minimal-harness-python-formatting
description: "Strict formatting, structural, and documentation rules for the minimal-harness Python scripts, including PEP8 compliance, 8-line function limits, and no blank lines within functions. Trigger when writing or refactoring Python code in this repository."
---

# Minimal Harness Python Scripting Rules

When writing, modifying, or refactoring Python code (`.py` files) in this repository, you MUST strictly adhere to the following rules:

## 1. PEP8 Compliance

- All Python code MUST strictly adhere to PEP8 formatting guidelines (e.g., 4-space indentation, appropriate naming conventions).
- Run `flake8` or equivalent on the script to verify.

## 2. Maximum Function Length (8-Line Rule)

- All functions MUST be no longer than 8 lines of code (excluding the `def` signature, docstrings, and decorator lines).
- If a function body exceeds 8 lines, you MUST refactor it by breaking it down into smaller helper functions.
- **Exception**: Cryptographic functions (e.g., encryption loops, hashing algorithms) are exempt from this rule to maintain algorithmic clarity and correctness.

## 3. No Blank Lines Within Functions

- There MUST be absolutely NO blank lines inside any function body.
- You may use blank lines *between* functions or classes (following PEP8), but never inside the execution block of a function.

## 4. Documentation

- Every file must have a module-level docstring.
- EVERY function must have a complete docstring following the exact NumPy style, explaining its purpose, parameters, and return value.
- You must use this EXACT format:

```python
    """
    Generate OBC bytecode for setting the system state.

    Parameters
    ----------
    state : int
        State ID.

    Returns
    -------
    bytes
        Bytecode sequence.
    """
```
