"""word_wrap tests."""

import unittest

from solution import word_wrap


class WordWrapTests(unittest.TestCase):
    """Verify the benchmark cases."""

    def test_small(self) -> None:
        """Verify the small case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(word_wrap("a b c", 2), ["a", "b", "c"])

    def test_wrap(self) -> None:
        """Verify the wrap case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(
            word_wrap("wrap this text", 7), ["wrap", "this", "text"]
        )

    def test_pair(self) -> None:
        """Verify the pair case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(word_wrap("abc def ghi", 7), ["abc def", "ghi"])

    def test_huge(self) -> None:
        """Verify the huge case.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.assertEqual(
            word_wrap("supercalifragilistic", 5), ["supercalifragilistic"]
        )


if __name__ == "__main__":
    unittest.main()
