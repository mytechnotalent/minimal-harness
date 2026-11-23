# Mandatory coding standards

These rules are non-negotiable. Apply them to every file you create or modify.
Detect the language from the file extension. If a project has a stricter local
standard, follow the stricter rule.

Never attribute generated code to Kevin Thomas. Use the project's author or
owner, or the user's name, in file headers. Do not copy a third-party
copyright header with the wrong author. Replace the reference author with the
project author.

No U+2013 en dash or U+2014 em dash anywhere. Use the hyphen-minus `-`.

## Tests are mandatory

Every new function, module, command, or behavior must ship with a unit test in
the same change. Tests must be deterministic and offline where possible. Cover
the success path and at least one failure or edge case. Code without tests is
not complete and must not be presented as finished.

## Python

- PEP 8 and Black with `line-length = 79`; Flake8 clean.
- Every `.py` file has a module docstring.
- Every function has a full NumPy-style docstring with Parameters and Returns.
- A function body has at most 8 executable lines and no blank lines inside it.
- Break longer bodies into private helpers.
- Use the standard library first. Do not add a dependency without asking.
- Add `tests/test_<module>.py` with `unittest` for every new function, module,
  and command. Cover the success path and at least one failure or edge case.
- Before finishing: `black --check`, `flake8`, `python -m compileall -q`, and
  the full test suite.

## C

Follow the embedded C standard exactly:

- At most 8 executable lines per function. Count wrapped continuation lines.
- No blank lines inside a function body. Use comments to separate steps.
- Doxygen block on every function declaration in the header with `@brief`,
  `@param` for every parameter (`@param void No parameters.` when none), and
  `@return`. Static functions carry their block in the `.c`.
- Every source file opens with an MIT header block: copyright, author, email,
  GitHub, file, desc, created. Use the project author, not a copied name.
- Include guards: `#ifndef <MODULE>_H`, `#define <MODULE>_H`, `#endif // <MODULE>_H`.
- Naming: files and modules `snake_case`; functions `module_action`; macros
  `UPPER_SNAKE`; types `name_t`; file-scope statics `g_name`.
- One responsibility per file: `src/<module>.c` with `include/<module>.h`.
- Hardware access goes through a HAL seam so host tests can substitute mocks.
- 79-column lines, four-space indent, no tabs.
- Add host unit tests under `tests/` for every module, using the HAL mock.
  A module without a test is incomplete.
- Build with `-Wall -Wextra -Werror` and run the full host test suite.

## C++

Use the same C standard as the baseline:

- At most 8 executable lines per function, no blank lines inside a function.
- Doxygen blocks on declarations with `@brief`, `@param`, `@return`.
- Headers use include guards; names use `snake_case`; types use `name_t`.
- 79-column lines, four-space indent, no tabs.
- Prefer the standard library and RAII. No raw `new`/`delete`; no C-style casts.
- Keep one responsibility per file and keep hardware access behind a seam.
- Add host unit tests under `tests/` for every module. A class or module
  without a test is incomplete.
- Build with `-Wall -Wextra -Werror` and run the full test suite.

## Rust

Follow the REA conventions exactly:

- Every `.rs` file starts with a `//!` header: title, file name, author, date,
  and the full MIT license. Use the project author, not a copied name.
- Crate roots carry:
  `#![forbid(unsafe_code)]`,
  `#![deny(clippy::all, clippy::pedantic)]`,
  `#![deny(missing_docs)]`,
  `#![deny(clippy::missing_docs_in_private_items)]`.
- Put a comment above each private `use` group.
- Every item has a `///` doc comment, including private functions, constants,
  fields, variants, trait methods, and tests. Function docs use
  `# Arguments`, `# Returns`, `# Errors`, `# Panics`, `# Example` in that order.
- A function body has at most 8 lines and no blank lines inside it.
- Every file with a function has `#[cfg(test)] mod tests` using
  `use super::*;`. Test names are `test_<behavior>` and each has a doc comment.
- Every new function, module, and command has at least one test. A file
  without tests is incomplete.
- Use `struct_lit_width = 80` and `chain_width = 80` in `rustfmt.toml`.
- Prefer `Result`, `Option`, and `?`. Avoid `unwrap` and `expect` outside tests.
- Verify with `cargo fmt --check`, `cargo clippy --workspace --all-targets --
  -D warnings`, `cargo test`, and `cargo xtask check` when present.

## Assembly

Follow the RP2350 RISC-V assembly style:

- File header block: `FILE`, `DESCRIPTION`, `BRIEF`, `AUTHOR`, `CREATION DATE`,
  `UPDATE DATE`. Use the project author, not a copied name.
- Use `.include "constants.s"` for shared constants.
- Emit sections in this order: `.section .text` with `.align 2`, `.section
  .rodata`, `.section .data`, `.section .bss`, each with a short comment.
- Document every function with a Doxygen-style block: `@brief`, `@details`,
  `@param`, `@retval`.
- Export functions with `.global <name>` and `.type <name>, @function`.
- Use two-space indentation for instructions; align mnemonics and operands so
  comments line up. Use a `#` comment on every load, call, and branch.
- Name public routines `Module_Action` and local labels `.Loop`, `.Done`.
- Keep the ABI: arguments in `a0`-`a7`, return in `a0`, preserve `s0`-`s11`.
- End functions with `ret`. Build with the project toolchain and check that it
  assembles and links with no warnings.
- Add a host or on-target test harness that exercises every public routine.
  Document hardware-only tests and the command that runs them. A routine
  without a test is incomplete.

## Finish checklist

- The language-specific formatter and linter pass with no warnings.
- The project builds and its tests pass.
- No en dash or em dash is present.
- File headers carry the project author, not a copied name.
- Every function satisfies the length and documentation rules.
