"""Tests for Markdown table normalization."""

import unittest

from meta_harness.markdown_text import readable_markdown


class MarkdownTableTests(unittest.TestCase):
    """Verify tables become readable labeled rows."""

    def test_table_becomes_labeled_rows(self) -> None:
        """A pipe table becomes labeled row text.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The row is readable and the rule is gone.
        """
        text = "| Item | Cost |\n| --- | --- |\n| Eggs | $6 |\n"
        result = readable_markdown(text)
        self.assertIn("**Item:** Eggs; **Cost:** $6", result)
        self.assertNotIn("| --- |", result)

    def test_plain_text_is_unchanged(self) -> None:
        """Text without a table passes through unchanged.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The input is returned as-is.
        """
        text = "hello\nworld"
        self.assertEqual(readable_markdown(text), text)

    def test_missing_rule_leaves_pipes(self) -> None:
        """A pipe block without a rule is not treated as a table.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The original pipe lines remain.
        """
        text = "| a | b |\n| x | y |\n"
        self.assertEqual(readable_markdown(text), text.rstrip("\n"))

    def test_empty_cells_are_skipped(self) -> None:
        """Empty cells do not produce empty labels.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Only populated labels appear.
        """
        text = "| A | B |\n| --- | --- |\n| one | |\n"
        self.assertIn("**A:** one", readable_markdown(text))
