from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

APP_QSS = """
QMainWindow {
    background: #0B1020;
}
QWidget {
    color: #E6ECFF;
    background: #0B1020;
    font-size: 13px;
}
QMenuBar, QMenu, QTabWidget::pane, QSplitter, QScrollArea, QListWidget, QTreeWidget {
    background: #121A2B;
}
QListWidget {
    border: 1px solid #2A3755;
    border-radius: 8px;
    outline: none;
}
QGroupBox {
    border: 1px solid #2A3755;
    border-radius: 10px;
    margin-top: 10px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #9AA7C7;
}
QTabBar::tab {
    background: #1A2438;
    padding: 8px 14px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: #9AA7C7;
}
QTabBar::tab:selected {
    color: #E6ECFF;
    background: #5B8CFF;
}
QPushButton {
    background: #1A2438;
    border: 1px solid #2A3755;
    border-radius: 6px;
    padding: 6px 10px;
}
QPushButton:hover {
    border-color: #5B8CFF;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit {
    background: #1A2438;
    border: 1px solid #2A3755;
    border-radius: 6px;
    padding: 6px;
}
QLabel#secondary {
    color: #9AA7C7;
}
QFrame#card {
    background: #1A2438;
    border: 1px solid #2A3755;
    border-radius: 10px;
}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(APP_QSS)
    palette = app.palette()
    palette.setColor(QPalette.Window, QColor("#0B1020"))
    palette.setColor(QPalette.WindowText, QColor("#E6ECFF"))
    palette.setColor(QPalette.Base, QColor("#121A2B"))
    palette.setColor(QPalette.AlternateBase, QColor("#1A2438"))
    palette.setColor(QPalette.Text, QColor("#E6ECFF"))
    palette.setColor(QPalette.Button, QColor("#1A2438"))
    palette.setColor(QPalette.ButtonText, QColor("#E6ECFF"))
    palette.setColor(QPalette.Highlight, QColor("#5B8CFF"))
    app.setPalette(palette)
