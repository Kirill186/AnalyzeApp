from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

APP_QSS = """
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #090F1F, stop:0.55 #0A1328, stop:1 #060A14);
}
QWidget {
    color: #E6ECFF;
    background: transparent;
    font-size: 13px;
}
QMenuBar, QMenu, QTabWidget::pane, QSplitter, QScrollArea, QListWidget, QTreeWidget {
    background: #121A2B;
}
QTabWidget::pane {
    border: 1px solid #2A3755;
    border-radius: 10px;
    background: rgba(18, 27, 45, 0.92);
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
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4D79D8, stop:1 #42B4D4);
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
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QAbstractSpinBox {
    background: #1A2438;
    color: #E6ECFF;
    border: 1px solid #2A3755;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #5B8CFF;
    selection-color: #F4F7FF;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover, QDateEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QAbstractSpinBox:hover {
    background: #1A2438;
    border-color: #5B8CFF;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QAbstractSpinBox:focus {
    background: #1A2438;
    border-color: #5B8CFF;
}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QDateEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QAbstractSpinBox:disabled {
    background: #121A2B;
    color: #7F8EAD;
    border-color: #2A3755;
}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background: #24314C;
    border: none;
    width: 18px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background: #2D4166;
}
QSpinBox::up-button:disabled, QSpinBox::down-button:disabled, QDoubleSpinBox::up-button:disabled, QDoubleSpinBox::down-button:disabled {
    background: #121A2B;
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
