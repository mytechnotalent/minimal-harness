"""merge_intervals tests."""

import unittest

from solution import merge_intervals


class MergeIntervalsTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_unsorted(self) -> None:
        """Verify the unsorted case."""
        self.assertEqual(merge_intervals([[5, 6], [1, 2]]), [[1, 2], [5, 6]])

    def test_nested(self) -> None:
        """Verify the nested case."""
        self.assertEqual(merge_intervals([[1, 10], [2, 3]]), [[1, 10]])

    def test_chain(self) -> None:
        """Verify the chain case."""
        self.assertEqual(
            merge_intervals([[1, 2], [2, 3], [4, 5]]), [[1, 3], [4, 5]]
        )

    def test_empty(self) -> None:
        """Verify the empty case."""
        self.assertEqual(merge_intervals([]), [])


if __name__ == "__main__":
    unittest.main()
