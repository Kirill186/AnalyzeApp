from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QListWidget, QSplitter, QTextEdit, QVBoxLayout, QWidget

from analyze_app.domain.entities import ProjectGraph


class ProjectMapTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Structural view", "Hotspot overlay"])

        top = QHBoxLayout()
        top.addWidget(QLabel("Mode:"))
        top.addWidget(self.mode_combo)
        top.addStretch()

        self.graph_list = QListWidget()
        self.details = QTextEdit()
        self.details.setReadOnly(True)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.graph_list)
        splitter.addWidget(self.details)
        splitter.setSizes([700, 400])

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(splitter)

        self.graph_list.currentTextChanged.connect(self._show_details)

    def set_project_map(self, graph: ProjectGraph) -> None:
        self.graph_list.clear()
        for node in graph.nodes:
            self.graph_list.addItem(f"{node.kind}: {node.label} ({node.path}) [hotspot={node.hotspot_score}]")

    def _show_details(self, text: str) -> None:
        self.details.setPlainText(text)
