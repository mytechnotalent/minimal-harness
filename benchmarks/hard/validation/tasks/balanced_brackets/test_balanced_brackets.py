"""balanced_brackets tests."""

import unittest

from solution import balanced_brackets


class BalancedBracketsTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_empty(self) -> None:
        """Verify the empty case."""
        self.assertTrue(balanced_brackets(""))

    def test_open(self) -> None:
        """Verify the open case."""
        self.assertFalse(balanced_brackets("("))

    def test_text(self) -> None:
        """Verify the text case."""
        self.assertTrue(balanced_brackets("a(b)c"))

    def test_all(self) -> None:
        """Verify the all case."""
        self.assertTrue(balanced_brackets("{[()]}"))


if __name__ == "__main__":
    unittest.main()
