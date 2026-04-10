from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from analyze_app.domain.entities import Commit
from analyze_app.presentation.qt_shell.web_view_utils import escape_plain, render_html_template


class CommitsWebPage(QWebEnginePage):
    commit_selected = Signal(str)
    ai_requested = Signal(str)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:  # type: ignore[override]
        if url.scheme() == "analyzeapp":
            action = url.host().lower()
            commit_hash = url.path().lstrip("/")
            if action == "select" and commit_hash:
                self.commit_selected.emit(commit_hash)
            elif action == "ai" and commit_hash:
                self.ai_requested.emit(commit_hash)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class CommitsTab(QWidget):
    commit_selected = Signal(str)
    ai_summary_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._selected_hash: str | None = None
        self._commits: list[Commit] = []
        self._summary_text = ""

        title = QLabel("История коммитов")

        self.web = QWebEngineView()
        self.page = CommitsWebPage(self.web)
        self.page.commit_selected.connect(self._set_selected_hash)
        self.page.ai_requested.connect(self._on_ai_requested_from_web)
        self.web.setPage(self.page)

        root = QVBoxLayout(self)
        root.addWidget(title)
        root.addWidget(self.web)
        self._render()

    def set_commits(self, commits: list[Commit]) -> None:
        self._commits = commits
        self._selected_hash = commits[0].hash if commits else None
        if self._selected_hash:
            self.commit_selected.emit(self._selected_hash)
        self._render()

    def set_commit_summary(self, commit_hash: str, summary: str, model_info: str) -> None:
        self._summary_text = f"{commit_hash[:10]}\nМодель: {model_info}\n\n{summary}"
        self._render()

    def _set_selected_hash(self, commit_hash: str) -> None:
        self._selected_hash = commit_hash
        self.commit_selected.emit(commit_hash)

    def _on_ai_requested_from_web(self, commit_hash: str) -> None:
        self._set_selected_hash(commit_hash)
        self.ai_summary_requested.emit(commit_hash)

    def _render(self) -> None:
        serialized = []
        for commit in self._commits:
            serialized.append(
                {
                    "hash": commit.hash,
                    "shortHash": commit.hash[:10],
                    "author": commit.author,
                    "date": commit.authored_at.astimezone().strftime("%Y-%m-%d %H:%M"),
                    "message": commit.message.replace("\n", " ").strip() or "(без сообщения)",
                    "description": self._summary_text if self._selected_hash == commit.hash and self._summary_text else "",
                }
            )
        payload = {
            "commits": serialized,
            "summary": escape_plain(self._summary_text),
            "selectedHash": self._selected_hash,
        }
        template_path = Path(__file__).with_name("web_assets") / "commits.html"
        html = render_html_template(template_path, payload)
        self.web.setHtml(html, QUrl.fromLocalFile(str(template_path.parent)))
