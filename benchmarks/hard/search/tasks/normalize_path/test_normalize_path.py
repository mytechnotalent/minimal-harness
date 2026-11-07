"""normalize_path tests."""

import unittest

from solution import normalize_path


class NormalizePathTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_absolute(self) -> None:
        """Verify the absolute case."""
        self.assertEqual(normalize_path("/a//b/./c"), "/a/b/c")

    def test_parent(self) -> None:
        """Verify the parent case."""
        self.assertEqual(normalize_path("a/b/../c"), "a/c")

    def test_dot(self) -> None:
        """Verify the dot case."""
        self.assertEqual(normalize_path("."), ".")


if __name__ == "__main__":
    unittest.main()
