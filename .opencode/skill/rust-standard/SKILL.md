---
name: rust-standard
description: "Use when writing, editing, or reviewing Rust. Enforces the REA conventions: file headers, crate-level denies, docs on every item, 8-line functions, no blank lines inside functions, and strict clippy."
---

# Rust standard

Reference: https://github.com/mytechnotalent/rea/blob/main/CONVENTIONS.md

These rules are mandatory.

## File header

Every `.rs` file starts with a `//!` header: title, file name, author, date,
and the full MIT license. Use the project author, not a copied name. A blank
line follows the header.

```rust
//! Title Of The File
//!
//! **File:** `name.rs`
//! **Author:** <PROJECT AUTHOR>
//! **Date:** <YEAR>
//!
//! MIT License
//!
//! Copyright (c) <YEAR> <PROJECT AUTHOR>
```

## Crate attributes

Every crate root carries:

```rust
#![forbid(unsafe_code)]
#![deny(clippy::all, clippy::pedantic)]
#![deny(missing_docs)]
#![deny(clippy::missing_docs_in_private_items)]
```

## Imports and documentation

- Put a comment above each private `use` group.
- Every item has a `///` doc comment: public and private functions, constants,
  types, fields, variants, trait methods, and tests.
- Function docs use `# Arguments`, `# Returns`, `# Errors`, `# Panics`,
  `# Example` in that order, when they apply.
- The doc comment comes before attributes such as `#[must_use]`.

## Functions and tests

- A function body has at most 8 lines and no blank lines inside it.
- Every file with a function has `#[cfg(test)] mod tests` using
  `use super::*;`.
- Each test has a doc comment and is named `test_<behavior>`.
- Every new function, module, and command has at least one test. A file
  without tests is incomplete.

## Formatting and verification

- `rustfmt.toml`: `struct_lit_width = 80` and `chain_width = 80`.
- Prefer `Result`, `Option`, and `?`. Avoid `unwrap` and `expect` outside tests.
- Verify with `cargo fmt --check`,
  `cargo clippy --workspace --all-targets -- -D warnings`,
  `cargo test`, and `cargo xtask check` when present.

## README release notes

Keep exactly one `# New in vX.Y.Z` section for the current version. Replace it
in place on each release. Prior notes belong in GitHub Releases and `PLAN.md`.
