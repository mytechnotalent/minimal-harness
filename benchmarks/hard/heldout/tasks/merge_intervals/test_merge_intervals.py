"""merge_intervals tests."""

import unittest

from solution import merge_intervals


class MergeIntervalsTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_single(self) -> None:
        """Verify the single case."""
        self.assertEqual(merge_intervals([[1, 2]]), [[1, 2]])

    def test_overlap_zero(self) -> None:
        """Verify the overlap_zero case."""
        self.assertEqual(merge_intervals([[1, 4], [0, 4]]), [[0, 4]])

    def test_reverse_touch(self) -> None:
        """Verify the reverse_touch case."""
        self.assertEqual(merge_intervals([[2, 3], [1, 2]]), [[1, 3]])

    def test_disjoint(self) -> None:
        """Verify the disjoint case."""
        self.assertEqual(merge_intervals([[1, 2], [3, 4]]), [[1, 2], [3, 4]])


if __name__ == "__main__":
    unittest.main()
