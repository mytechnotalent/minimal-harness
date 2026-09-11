"""Tests for the fibonacci(n) starter task."""

import unittest

from solution import fibonacci


class FibonacciTests(unittest.TestCase):
    """Verify fibonacci(n) returns the nth Fibonacci number."""

    def test_zero(self) -> None:
        """fibonacci(0) is 0."""
        self.assertEqual(fibonacci(0), 0)

    def test_one(self) -> None:
        """fibonacci(1) is 1."""
        self.assertEqual(fibonacci(1), 1)

    def test_ten(self) -> None:
        """fibonacci(10) is 55."""
        self.assertEqual(fibonacci(10), 55)


if __name__ == "__main__":
    unittest.main()
