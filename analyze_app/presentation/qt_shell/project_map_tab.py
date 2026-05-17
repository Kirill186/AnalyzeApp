from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from PySide6.QtCore import QSignalBlocker, QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from analyze_app.domain.entities import ProjectGraph
from analyze_app.presentation.qt_shell.web_view_utils import render_html_template


class ProjectMapWebPage(QWebEnginePage):
    open_requested = Signal(str)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:  # type: ignore[override]
        if url.scheme() != "analyzeapp":
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)
        if url.host().lower() != "project-map":
            return False

        params = parse_qs(url.query())
        action = (params.get("action") or [""])[0].lower()
        file_path = (params.get("file") or [""])[0]
        if action == "open" and file_path:
            self.open_requested.emit(file_path)
        return False


class ProjectMapTab(QWidget):
    open_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Structural view", "Hotspot overlay"])

        top = QHBoxLayout()
        top.addWidget(QLabel("Mode:"))
        top.addWidget(self.mode_combo)
        top.addStretch()

        self.web = QWebEngineView()
        self.page = ProjectMapWebPage(self.web)
        self.page.open_requested.connect(self.open_requested.emit)
        self.web.setPage(self.page)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.web)

        self._nodes: list[dict[str, str | int]] = []
        self._edges: list[dict[str, str]] = []
        self._loading = False

        self.mode_combo.currentTextChanged.connect(self._render_current_state)
        self._render_current_state()

    def set_project_map(self, graph: ProjectGraph) -> None:
        self._loading = False
        self._nodes = [
            {
                "id": node.node_id,
                "kind": node.kind,
                "label": node.label,
                "path": node.path,
                "hotspot": node.hotspot_score,
            }
            for node in graph.nodes
        ]
        self._edges = [
            {
                "source": edge.source,
                "target": edge.target,
                "relation": edge.relation,
            }
            for edge in graph.edges
        ]
        self._render_current_state()

    def set_loading(self) -> None:
        self._loading = True
        self._nodes = []
        self._edges = []
        self._render_current_state()

    def clear(self) -> None:
        self._loading = False
        self._nodes = []
        self._edges = []
        self._render_current_state()

    def set_mode(self, mode: str) -> None:
        index = self.mode_combo.findText(mode)
        if index < 0:
            return
        with QSignalBlocker(self.mode_combo):
            self.mode_combo.setCurrentIndex(index)
        self._render_current_state()

    def _render_current_state(self) -> None:
        template_path = Path(__file__).with_name("web_assets") / "project_map.html"
        html = render_html_template(
            template_path,
            {
                "nodes": self._nodes,
                "edges": self._edges,
                "mode": self.mode_combo.currentText(),
                "loading": self._loading,
            },
        )
        self.web.setHtml(html, QUrl.fromLocalFile(str(template_path.parent)))
