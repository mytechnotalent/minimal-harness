"""Dark neon cyber theme for the Minimal Harness desktop shell."""

from PySide6.QtWidgets import QApplication

BG = "#04070a"
PANEL = "#0a1014"
PANEL_ALT = "#0d161c"
BORDER = "#1f6f5c"
TEXT = "#c8ffe8"
MUTED = "#6fae9b"
NEON = "#39ff88"
CYAN = "#21d4fd"
MAGENTA = "#ff2bd6"
SELECT = "#123f33"
USER_BUBBLE = "#0e3b2c"
AGENT_BUBBLE = "#0a2d3a"
TOOL_BUBBLE = "#141a22"

FONT_STACK = (
    '"JetBrains Mono", "Cascadia Code", "Fira Code", '
    "Consolas, Menlo, monospace"
)

STYLESHEET = f"""
* {{
    font-family: {FONT_STACK};
    font-size: 13px;
}}
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
}}
#PanelCard {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
#QuestionCard {{
    background-color: {PANEL_ALT};
    border: 1px solid {NEON};
    border-radius: 6px;
}}
#QuestionCard QLabel {{
    color: {TEXT};
}}
#Sidebar {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
#Sidebar QListWidget {{
    border: none;
    background: transparent;
    color: {TEXT};
}}
#Sidebar QListWidget::item {{
    padding: 6px 8px;
    border-radius: 4px;
}}
#Sidebar QListWidget::item:selected {{
    background-color: {SELECT};
    color: {NEON};
}}
#PanelCard QTextEdit, #PanelCard QPlainTextEdit, #PanelCard QLineEdit {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    color: {TEXT};
}}
QLabel {{
    color: {TEXT};
    background: transparent;
}}
#statusLabel {{
    color: {CYAN};
}}
#voiceStatus {{
    color: {MAGENTA};
}}
#workspaceLabel {{
    color: {MUTED};
}}
QTextEdit {{
    background-color: {PANEL_ALT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {NEON};
    selection-color: {BG};
}}
QPlainTextEdit {{
    background-color: {PANEL_ALT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {NEON};
    selection-color: {BG};
}}
QPushButton {{
    background-color: {PANEL_ALT};
    color: {NEON};
    border: 1px solid {NEON};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    background-color: {SELECT};
    color: {CYAN};
    border-color: {CYAN};
}}
QPushButton:pressed {{
    background-color: {NEON};
    color: {BG};
}}
QPushButton:disabled {{
    background-color: {PANEL};
    color: {MUTED};
    border-color: {BORDER};
}}
QCheckBox {{
    color: {MUTED};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background-color: {PANEL_ALT};
}}
QCheckBox::indicator:checked {{
    background-color: {NEON};
    border-color: {NEON};
}}
QInputDialog QLineEdit, QLineEdit {{
    background-color: {PANEL_ALT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {NEON};
    selection-color: {BG};
}}
QSplitter::handle {{
    background-color: {BORDER};
    width: 2px;
}}
QScrollBar:vertical {{
    background: {PANEL};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {NEON};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
QMenu {{
    background-color: {PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
QMenu::item:selected {{
    background-color: {SELECT};
    color: {NEON};
}}
QDialog, QMessageBox {{
    background-color: {PANEL};
    color: {TEXT};
}}
"""


def apply_palette(app: QApplication) -> None:
    """Apply the dark neon stylesheet to an application.

    Parameters
    ----------
    app : QApplication
        Application receiving the stylesheet.

    Returns
    -------
    None
        The stylesheet is set on the application.
    """
    app.setStyleSheet(STYLESHEET)
