"""Color palette and stylesheet for the SavrenAI desktop shell."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

DOMINANT = "#11302A"
SECONDARY = "#AFB4AD"
ACCENT = "#D6CFBF"
NEUTRAL = "#F8F3EC"

DARK_TEXT = "#E6EDF3"
DARK_BORDER = "#3A4650"
DARK_ACCENT = "#22303A"
DARK_SURFACE = "#1A2228"
DARK_BASE = "#12181D"
DARK_INPUT = "#0E1418"

STYLESHEET = f"""
* {{
    font-family: sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget {{
    background-color: {NEUTRAL};
    color: {DOMINANT};
}}
#PanelCard {{
    background-color: white;
    border: 1px solid {SECONDARY};
    border-radius: 8px;
}}
#Sidebar {{
    background-color: white;
    border: 1px solid {SECONDARY};
    border-radius: 8px;
}}
#Sidebar QListWidget {{
    border: none;
    background: transparent;
}}
#Sidebar QListWidget::item {{
    padding: 6px 8px;
    border-radius: 4px;
}}
#Sidebar QListWidget::item:selected {{
    background-color: {ACCENT};
    color: {DOMINANT};
}}
#PanelCard QTextEdit, #PanelCard QPlainTextEdit, #PanelCard QLineEdit {{
    background-color: {NEUTRAL};
    border: 1px solid {SECONDARY};
}}
QLabel {{
    color: {DOMINANT};
    background: transparent;
}}
QTextEdit {{
    background-color: white;
    color: #000000;
    border: 1px solid {SECONDARY};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {ACCENT};
    selection-color: {DOMINANT};
}}
QPlainTextEdit {{
    background-color: white;
    color: #000000;
    border: 1px solid {SECONDARY};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {ACCENT};
    selection-color: {DOMINANT};
}}
QPushButton {{
    background-color: {ACCENT};
    color: {DOMINANT};
    border: 1px solid {SECONDARY};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    background-color: #c5bda9;
}}
QPushButton:pressed {{
    background-color: #b4ab95;
}}
QPushButton:disabled {{
    background-color: {NEUTRAL};
    color: {SECONDARY};
}}
QInputDialog QLineEdit, QLineEdit {{
    background-color: white;
    border: 1px solid {SECONDARY};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {ACCENT};
}}
QSplitter::handle {{
    background-color: {SECONDARY};
    width: 2px;
}}
"""

DARK_STYLESHEET = f"""
* {{
    font-family: sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget {{
    background-color: {DARK_BASE};
    color: {DARK_TEXT};
}}
#PanelCard {{
    background-color: {DARK_SURFACE};
    border: 1px solid {DARK_BORDER};
    border-radius: 8px;
}}
#Sidebar {{
    background-color: {DARK_SURFACE};
    border: 1px solid {DARK_BORDER};
    border-radius: 8px;
}}
#Sidebar QListWidget {{
    border: none;
    background: transparent;
}}
#Sidebar QListWidget::item {{
    padding: 6px 8px;
    border-radius: 4px;
}}
#Sidebar QListWidget::item:selected {{
    background-color: {DARK_ACCENT};
    color: {DARK_TEXT};
}}
#PanelCard QTextEdit, #PanelCard QPlainTextEdit, #PanelCard QLineEdit {{
    background-color: {DARK_INPUT};
    border: 1px solid {DARK_BORDER};
}}
QLabel {{
    color: {DARK_TEXT};
    background: transparent;
}}
QTextEdit {{
    background-color: {DARK_INPUT};
    color: {DARK_TEXT};
    border: 1px solid {DARK_BORDER};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {DARK_ACCENT};
    selection-color: #FFFFFF;
}}
QPlainTextEdit {{
    background-color: {DARK_INPUT};
    color: {DARK_TEXT};
    border: 1px solid {DARK_BORDER};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {DARK_ACCENT};
    selection-color: #FFFFFF;
}}
QPushButton {{
    background-color: {DARK_ACCENT};
    color: {DARK_TEXT};
    border: 1px solid {DARK_BORDER};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    background-color: #2B3D4A;
}}
QPushButton:pressed {{
    background-color: #1A2730;
}}
QPushButton:disabled {{
    background-color: {DARK_BASE};
    color: {DARK_BORDER};
}}
QInputDialog QLineEdit, QLineEdit {{
    background-color: {DARK_INPUT};
    color: {DARK_TEXT};
    border: 1px solid {DARK_BORDER};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {DARK_ACCENT};
}}
QSplitter::handle {{
    background-color: {DARK_BORDER};
    width: 2px;
}}
"""


def apply_palette(app: QApplication, dark: bool = False) -> None:
    """Apply the app-wide color palette.

    Parameters
    ----------
    app : QApplication
        Application receiving the stylesheet.
    dark : bool
        Whether to apply the dark stylesheet.

    Returns
    -------
    None
        The selected stylesheet is set on the application.
    """
    app.setStyleSheet(DARK_STYLESHEET if dark else STYLESHEET)
