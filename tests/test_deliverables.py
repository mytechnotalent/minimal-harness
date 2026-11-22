"""Tests for deliverable verification and completion status."""

import unittest

from meta_harness.deliverables import deliverable_issues

_VERIFIED = "Status: completed and verified."


def _test_trace() -> list[dict]:
    """Build a successful test-command record.

    Parameters
    ----------
    None

    Returns
    -------
    list of dict
        One bash execution record.
    """
    return [
        {
            "tool": "bash",
            "status": "ok",
            "arguments": {"command": "python -m unittest"},
        }
    ]


class MissingFileTests(unittest.TestCase):
    """Verify requested files are checked against changed files."""

    def test_requested_file_is_present(self) -> None:
        """A created requested file passes.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No issues are returned.
        """
        prompt = "Create report.md"
        answer = "Created report.md. " + _VERIFIED
        changed = ["report.md"]
        self.assertEqual([], deliverable_issues(prompt, answer, changed, []))

    def test_missing_requested_file_is_reported(self) -> None:
        """A missing requested file is reported.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The issue names the file.
        """
        prompt = "Create report.md"
        answer = "Status: partially completed."
        issues = deliverable_issues(prompt, answer, [], [])
        self.assertIn("report.md", issues[0])

    def test_wrong_directory_is_reported(self) -> None:
        """A file in the wrong directory is reported.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The path mismatch is flagged.
        """
        prompt = "Create tools/audit.py"
        answer = _VERIFIED
        issues = deliverable_issues(prompt, answer, ["audit.py"], [])
        self.assertIn("tools/audit.py", issues[0])


class FileClaimTests(unittest.TestCase):
    """Verify unsupported file claims are flagged."""

    def test_false_file_claim_is_reported(self) -> None:
        """A file the answer names but did not change is reported.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The issue names the unrelated file.
        """
        prompt = "Create report.md"
        answer = "I also wrote summary.txt. " + _VERIFIED
        issues = deliverable_issues(prompt, answer, ["report.md"], [])
        self.assertTrue(any("summary.txt" in issue for issue in issues))


class TestClaimTests(unittest.TestCase):
    """Verify test-passing claims need a recorded run."""

    def test_unbacked_test_claim_is_reported(self) -> None:
        """Tests claimed without a command are reported.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The missing run is flagged.
        """
        prompt = "Create run.py"
        answer = "All tests passed. " + _VERIFIED
        issues = deliverable_issues(prompt, answer, ["run.py"], [])
        self.assertTrue(any("tests passed" in issue for issue in issues))

    def test_backed_test_claim_passes(self) -> None:
        """A recorded successful test command supports the claim.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No issues are returned.
        """
        prompt = "Create run.py"
        answer = "All tests passed. " + _VERIFIED
        issues = deliverable_issues(prompt, answer, ["run.py"], _test_trace())
        self.assertEqual([], issues)


class StatusTests(unittest.TestCase):
    """Verify completion status is explicit."""

    def test_missing_status_is_reported(self) -> None:
        """A file task without a status is reported.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The missing status is flagged.
        """
        prompt = "Create run.py"
        issues = deliverable_issues(prompt, "Created run.py.", ["run.py"], [])
        self.assertTrue(any("completion status" in issue for issue in issues))

    def test_non_deliverable_task_is_skipped(self) -> None:
        """A news request has no deliverable checks.

        Parameters
        ----------
        None

        Returns
        -------
        None
            No issues are returned.
        """
        issues = deliverable_issues("find news", "Here are stories.", [], [])
        self.assertEqual([], issues)
