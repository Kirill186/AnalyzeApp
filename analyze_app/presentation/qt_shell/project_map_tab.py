from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from analyze_app.domain.entities import ProjectGraph
from analyze_app.presentation.qt_shell.web_view_utils import render_html_template


class ProjectMapTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Structural view", "Hotspot overlay"])

        top = QHBoxLayout()
        top.addWidget(QLabel("Mode:"))
        top.addWidget(self.mode_combo)
        top.addStretch()

        self.web = QWebEngineView()

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.web)
        self._render([])

    def set_project_map(self, graph: ProjectGraph) -> None:
        nodes = [
            {
                "kind": node.kind,
                "label": node.label,
                "path": node.path,
                "hotspot": f"{node.hotspot_score:.2f}",
            }
            for node in graph.nodes
        ]
        self._render(nodes)

    def _render(self, nodes: list[dict[str, str]]) -> None:
        template_path = Path(__file__).with_name("web_assets") / "project_map.html"
        html = render_html_template(template_path, {"nodes": nodes, "mode": self.mode_combo.currentText()})
        self.web.setHtml(html, QUrl.fromLocalFile(str(template_path.parent)) )
