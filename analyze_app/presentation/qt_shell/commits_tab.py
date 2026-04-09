from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from analyze_app.domain.entities import Commit


class CommitsTab(QWidget):
    commit_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.branch_filter = QLineEdit()
        self.branch_filter.setPlaceholderText("branch")
        self.author_filter = QLineEdit()
        self.author_filter.setPlaceholderText("author")
        self.text_filter = QLineEdit()
        self.text_filter.setPlaceholderText("text")
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Filters:"))
        filters.addWidget(self.branch_filter)
        filters.addWidget(self.author_filter)
        filters.addWidget(self.date_from)
        filters.addWidget(self.date_to)
        filters.addWidget(self.text_filter)

        self.graph_placeholder = QListWidget()
        self.graph_placeholder.addItem("Commit graph view (placeholder):")

        self.commit_list = QListWidget()
        self.commit_list.itemClicked.connect(self._on_commit_clicked)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.graph_placeholder)
        splitter.addWidget(self.commit_list)
        splitter.setSizes([750, 350])

        root = QVBoxLayout(self)
        root.addLayout(filters)
        root.addWidget(splitter)

    def set_commits(self, commits: list[Commit]) -> None:
        self.graph_placeholder.clear()
        self.commit_list.clear()
        for commit in commits:
            date_text = commit.authored_at.astimezone().strftime("%Y-%m-%d %H:%M")
            line = f"{commit.hash[:10]} • {commit.author} • {date_text}\n{commit.message}"
            item = QListWidgetItem(line)
            item.setData(Qt.UserRole, commit.hash)
            self.commit_list.addItem(item)
            self.graph_placeholder.addItem(f"● {commit.hash[:10]}  {commit.message}")

    def _on_commit_clicked(self, item: QListWidgetItem) -> None:
        commit_hash = item.data(Qt.UserRole)
        if commit_hash:
            self.commit_selected.emit(str(commit_hash))
