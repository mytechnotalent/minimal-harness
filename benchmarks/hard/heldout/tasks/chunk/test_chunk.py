"""chunk tests."""

import unittest

from solution import chunk


class ChunkTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_exact(self) -> None:
        """Verify the exact case."""
        self.assertEqual(chunk([1, 2, 3], 3), [[1, 2, 3]])

    def test_remainder(self) -> None:
        """Verify the remainder case."""
        self.assertEqual(chunk([1, 2, 3, 4], 3), [[1, 2, 3], [4]])

    def test_strings(self) -> None:
        """Verify the strings case."""
        self.assertEqual(chunk(["a", "b"], 1), [["a"], ["b"]])


if __name__ == "__main__":
    unittest.main()
