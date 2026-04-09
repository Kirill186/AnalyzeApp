from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QListWidget, QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget


class WorkspaceTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.stage_btn = QPushButton("Stage file")
        self.open_btn = QPushButton("Open in editor")
        self.diff_mode = QComboBox()
        self.diff_mode.addItems(["Split", "Unified"])

        top = QHBoxLayout()
        top.addWidget(QLabel("Working Tree Context"))
        top.addStretch()
        top.addWidget(self.diff_mode)
        top.addWidget(self.stage_btn)
        top.addWidget(self.open_btn)

        self.files_list = QListWidget()
        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.files_list)
        splitter.addWidget(self.diff_view)
        splitter.setSizes([350, 750])

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(splitter)

    def set_files(self, files: list[str]) -> None:
        self.files_list.clear()
        self.files_list.addItems(files)

    def set_diff(self, diff_text: str) -> None:
        self.diff_view.setPlainText(diff_text or "Нет изменений")
