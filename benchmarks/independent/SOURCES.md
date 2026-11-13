# Independent corpus sources

These workspaces are vendored from real projects under their own licenses and
are intentionally excluded from this repository's formatter, linter, and style
audit. Hidden tests are the projects' own test files, not authored here.

- `itsdangerous_signer`: https://github.com/pallets/itsdangerous at
  `672971d66a2ef9f85151e53283113f33d642dabd` (BSD-3-Clause). Hidden test:
  `tests/test_itsdangerous/test_signer.py`.
- `iniconfig_parser`: https://github.com/pytest-dev/iniconfig at
  `e0f1ee1ccd69634acf5d127ed2ea6e628f18da31` (MIT). Hidden test:
  `testing/test_iniconfig.py`.
- `packaging_utils`: https://github.com/pypa/packaging at
  `284ff8900e59115dc86f85ca4e9d87d95e7dbc75` (Apache-2.0 OR BSD-2-Clause).
  Hidden test: `tests/test_utils.py`.

License texts are in `benchmarks/independent/licenses/`.
