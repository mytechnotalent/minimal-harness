"""Offline tests for the thinking pulse dot."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from gui.app import PulseDot
except Exception:
    QApplication = None
    PulseDot = None


@unittest.skipIf(PulseDot is None, "PySide6 is not installed")
class PulseDotTest(unittest.TestCase):
    """Verify pulse geometry and start/stop state."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create the shared Qt application.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The application is stored on the class.
        """
        cls.app = QApplication.instance() or QApplication([])

    def test_radius_pulses_in_range(self) -> None:
        """Radius grows and shrinks between the fixed bounds.

        Parameters
        ----------
        None

        Returns
        -------
        None
            The radius bounds and travel are asserted.
        """
        dot = PulseDot()
        radii = []
        for step in range(80):
            dot._phase = step / 80
            radii.append(dot._radius())
        self.assertGreaterEqual(min(radii), 2.0)
        self.assertLessEqual(max(radii), 7.0)
        self.assertGreater(max(radii) - min(radii), 4.5)

    def test_stop_hides_dot(self) -> None:
        """Stopping the timer hides the widget.

        Parameters
        ----------
        None

        Returns
        -------
        None
            Visibility before and after stopping is asserted.
        """
        dot = PulseDot()
        dot.start()
        self.assertTrue(dot.isVisible())
        dot.stop()
        self.assertFalse(dot.isVisible())
