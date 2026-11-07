"""chunk tests."""

import unittest

from solution import chunk


class ChunkTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_two(self) -> None:
        """Verify the two case."""
        self.assertEqual(chunk([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])

    def test_large(self) -> None:
        """Verify the large case."""
        self.assertEqual(chunk([1, 2], 5), [[1, 2]])


if __name__ == "__main__":
    unittest.main()
