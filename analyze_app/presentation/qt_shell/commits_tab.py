from __future__ import annotations

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSplitter, QVBoxLayout, QWidget

from analyze_app.domain.entities import Commit
from analyze_app.presentation.qt_shell.web_view_utils import escape_plain, render_html_template
from pathlib import Path


class CommitsTab(QWidget):
    commit_selected = Signal(str)
    checkout_requested = Signal(str)
    ai_summary_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._selected_hash: str | None = None
        self._commits: list[Commit] = []
        self._summary_text = ""

        self.commit_list = QListWidget()
        self.commit_list.itemClicked.connect(self._select_commit_from_list)

        self.checkout_btn = QPushButton("Checkout")
        self.checkout_btn.clicked.connect(self._emit_checkout)
        self.describe_btn = QPushButton("Описание (Ollama)")
        self.describe_btn.clicked.connect(self._emit_ai_summary)

        actions = QHBoxLayout()
        actions.addWidget(QLabel("История коммитов"))
        actions.addStretch()
        actions.addWidget(self.checkout_btn)
        actions.addWidget(self.describe_btn)

        left = QVBoxLayout()
        left.addLayout(actions)
        left.addWidget(self.commit_list)

        left_panel = QWidget()
        left_panel.setLayout(left)

        self.web = QWebEngineView()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.web)
        splitter.setSizes([460, 900])

        root = QVBoxLayout(self)
        root.addWidget(splitter)
        self._render()

    def set_commits(self, commits: list[Commit]) -> None:
        self._selected_hash = None
        self._commits = commits
        self.commit_list.clear()

        for commit in commits:
            date_text = commit.authored_at.astimezone().strftime("%Y-%m-%d %H:%M")
            line = f"{commit.hash[:10]} • {commit.author} • {date_text}\n{commit.message}"
            item = QListWidgetItem(line)
            item.setData(Qt.UserRole, commit.hash)
            self.commit_list.addItem(item)

        if commits:
            self._set_selected_hash(commits[0].hash)
        else:
            self._render()

    def set_commit_summary(self, commit_hash: str, summary: str, model_info: str) -> None:
        self._summary_text = f"{commit_hash[:10]}\nМодель: {model_info}\n\n{summary}"
        self._render()

    def _set_selected_hash(self, commit_hash: str) -> None:
        self._selected_hash = commit_hash
        for idx in range(self.commit_list.count()):
            item = self.commit_list.item(idx)
            if item.data(Qt.UserRole) == commit_hash:
                self.commit_list.setCurrentItem(item)
                break
        self.commit_selected.emit(commit_hash)
        self._render()

    def _select_commit_from_list(self, item: QListWidgetItem) -> None:
        commit_hash = item.data(Qt.UserRole)
        if commit_hash:
            self._set_selected_hash(str(commit_hash))

    def _emit_checkout(self) -> None:
        if self._selected_hash:
            self.checkout_requested.emit(self._selected_hash)

    def _emit_ai_summary(self) -> None:
        if self._selected_hash:
            self.ai_summary_requested.emit(self._selected_hash)

    def _render(self) -> None:
        serialized = []
        for commit in self._commits:
            serialized.append(
                {
                    "shortHash": commit.hash[:10],
                    "author": commit.author,
                    "date": commit.authored_at.astimezone().strftime("%Y-%m-%d %H:%M"),
                    "message": commit.message.replace("\n", " ").strip() or "(без сообщения)",
                }
            )
        payload = {"commits": serialized, "summary": escape_plain(self._summary_text)}
        template_path = Path(__file__).with_name("web_assets") / "commits.html"
        html = render_html_template(template_path, payload)
        self.web.setHtml(html, QUrl.fromLocalFile(str(template_path.parent)) )
