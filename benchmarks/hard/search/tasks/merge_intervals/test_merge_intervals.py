"""merge_intervals tests."""

import unittest

from solution import merge_intervals


class MergeIntervalsTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_classic(self) -> None:
        """Verify the classic case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(
            merge_intervals([[1, 3], [2, 6], [8, 10], [15, 18]]),
            [[1, 6], [8, 10], [15, 18]],
        )

    def test_touching(self) -> None:
        """Verify the touching case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(merge_intervals([[1, 4], [4, 5]]), [[1, 5]])


if __name__ == "__main__":
    unittest.main()
