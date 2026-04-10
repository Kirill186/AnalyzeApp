from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView

from analyze_app.presentation.qt_shell.web_view_utils import escape_plain, render_html_template


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

        self._files: list[str] = []
        self._diff = ""
        self.web = QWebEngineView()

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.web)
        self._render()

    def set_files(self, files: list[str]) -> None:
        self._files = files
        self._render()

    def set_diff(self, diff_text: str) -> None:
        self._diff = diff_text or "Нет изменений"
        self._render()

    def _render(self) -> None:
        template_path = Path(__file__).with_name("web_assets") / "workspace.html"
        payload = {"files": self._files, "diff": escape_plain(self._diff)}
        html = render_html_template(template_path, payload)
        self.web.setHtml(html, QUrl.fromLocalFile(str(template_path.parent)) )
