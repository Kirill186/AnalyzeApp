from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from analyze_app.presentation.qt_shell.web_view_utils import render_html_template


class WorkspaceWebPage(QWebEnginePage):
    file_selected = Signal(str)
    mode_selected = Signal(str)
    stage_requested = Signal(str)
    open_requested = Signal(str)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:  # type: ignore[override]
        if url.scheme() != "analyzeapp":
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)
        if url.host().lower() != "workspace":
            return False

        params = parse_qs(url.query())
        file_path = (params.get("file") or [""])[0]
        mode = (params.get("value") or [""])[0].lower()
        action = (params.get("action") or [""])[0].lower()

        if action == "select" and file_path:
            self.file_selected.emit(file_path)
        elif action == "mode" and mode in {"split", "unified"}:
            self.mode_selected.emit(mode)
        elif action == "stage" and file_path:
            self.stage_requested.emit(file_path)
        elif action == "open" and file_path:
            self.open_requested.emit(file_path)
        return False


class WorkspaceTab(QWidget):
    file_selected = Signal(str)
    stage_requested = Signal(str)
    open_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._files: list[dict[str, object]] = []
        self._diff_by_file: dict[str, str] = {}
        self._selected_file: str | None = None
        self._mode = "split"

        self.web = QWebEngineView()
        self.page = WorkspaceWebPage(self.web)
        self.page.file_selected.connect(self._on_file_selected)
        self.page.mode_selected.connect(self._on_mode_selected)
        self.page.stage_requested.connect(self.stage_requested.emit)
        self.page.open_requested.connect(self.open_requested.emit)
        self.web.setPage(self.page)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.web)
        self._render()

    def set_workspace_data(
        self,
        files: list[dict[str, object]],
        diff_by_file: dict[str, str],
        selected_file: str | None = None,
    ) -> None:
        self._files = files
        self._diff_by_file = diff_by_file
        known_paths = {str(item.get("path") or "") for item in files}
        target = selected_file or self._selected_file or (files[0]["path"] if files else None)
        self._selected_file = target if target in known_paths else (files[0]["path"] if files else None)
        self._render()

    def _on_file_selected(self, file_path: str) -> None:
        self._selected_file = file_path
        self.file_selected.emit(file_path)
        self._render()

    def _on_mode_selected(self, mode: str) -> None:
        if mode not in {"split", "unified"}:
            return
        self._mode = mode
        self._render()

    def _render(self) -> None:
        template_path = Path(__file__).with_name("web_assets") / "workspace.html"
        payload = {
            "files": self._files,
            "selectedFile": self._selected_file,
            "mode": self._mode,
            "diffText": self._diff_by_file.get(self._selected_file or "", ""),
        }
        html = render_html_template(template_path, payload)
        self.web.setHtml(html, QUrl.fromLocalFile(str(template_path.parent)))
