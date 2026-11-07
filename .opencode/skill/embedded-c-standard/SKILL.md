---
name: embedded-c-standard
description: "Use when writing, editing, or reviewing C or C++ firmware. Enforces the strict embedded standard: 8-line functions, no blank lines inside functions, Doxygen declarations, a fixed module layout, and no en or em dashes."
---

# Embedded C and C++ standard

Reference: https://github.com/mytechnotalent/Embedded-Hacking/blob/main/.opencode/skill/embedded-c-standard/SKILL.md

These rules are mandatory. There is no variation between projects.

## Rules

1. No function longer than 8 executable lines. Count wrapped continuation
   lines. Split the work into a `static` helper.
2. No blank lines inside a function body. Separate steps with comments.
3. Documentation lives in the header. Every function declaration carries a
   Doxygen block with `@brief`, a `@param` for each parameter
   (`@param void No parameters.` when none), and `@return`. A `static`
   function carries its block in the `.c`. Do not duplicate the block.
4. No U+2013 (en dash) or U+2014 (em dash). Use the hyphen-minus `-`.
5. Every source file opens with an MIT header block: copyright, author, email,
   GitHub, file, description, created. Use the project author, not a copied
   name.
6. Every header uses `#ifndef <MODULE>_H`, `#define <MODULE>_H`, and
   `#endif // <MODULE>_H`.
7. Naming: files and modules `snake_case`; functions `module_action`; macros
   `UPPER_SNAKE`; types `name_t`; file-scope statics `g_name`.
8. One responsibility per file: `src/<module>.c` with `include/<module>.h`.
   Hardware access goes through a HAL seam so host tests can use mocks.
9. 79-column lines, four-space indent, no tabs.
10. Every module has host unit tests under `tests/` using the HAL mock. A
    module without a test is incomplete. Cover the success path and at least
    one failure or edge case.

## C++

Use the same rules. Prefer the standard library and RAII. Do not use raw
`new`/`delete` or C-style casts. Headers keep include guards. Build with
`-Wall -Wextra -Werror` and run tests.

## Layout

```text
firmware/
  src/        <module>.c or <module>.cpp
  include/    <module>.h or <module>.hpp
  tests/      host unit tests, mock/, harness/
  CMakeLists.txt
scripts/      run_tests.py  check_coverage.py  build.sh
```

## Verify

Run the project audit or build. Exit 0 and zero warnings are required before
the change is complete.
