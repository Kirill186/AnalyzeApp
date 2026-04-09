from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class MetricCard(QFrame):
    clicked = Signal(str)

    def __init__(self, metric_name: str, grade: str = "—", value: str = "—", threshold: str = "") -> None:
        super().__init__()
        self.metric_name = metric_name
        self.setObjectName("card")
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(metric_name))
        self.grade_label = QLabel(f"Grade: {grade}")
        self.value_label = QLabel(f"Value: {value}")
        self.threshold_label = QLabel(threshold)
        self.threshold_label.setObjectName("secondary")
        layout.addWidget(self.grade_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.threshold_label)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit(self.metric_name)
        super().mousePressEvent(event)


class OverviewTab(QWidget):
    regenerate_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.project_title = QLabel("Выберите репозиторий")
        self.project_title.setStyleSheet("font-size: 24px; font-weight: 600;")
        self.stats_label = QLabel("Файлы: — • LOC: —")
        self.stats_label.setObjectName("secondary")

        metrics_box = QGroupBox("Quality Metrics Grades")
        self.metrics_layout = QGridLayout(metrics_box)
        self.cards: dict[str, MetricCard] = {}
        for idx, metric in enumerate(["complexity", "maintainability", "typing_health", "tests", "lint", "duplication_proxy"]):
            card = MetricCard(metric)
            self.metrics_layout.addWidget(card, idx // 3, idx % 3)
            self.cards[metric] = card

        overview_header = QHBoxLayout()
        overview_header.addWidget(QLabel("Project Overview"))
        self.regenerate_btn = QPushButton("Regenerate")
        self.regenerate_btn.clicked.connect(self.regenerate_requested.emit)
        overview_header.addStretch()
        overview_header.addWidget(self.regenerate_btn)

        self.overview_text = QTextBrowser()
        self.overview_text.setOpenExternalLinks(True)

        readme_box = QGroupBox("README")
        readme_layout = QVBoxLayout(readme_box)
        self.readme_text = QTextBrowser()
        self.readme_text.setMarkdown("README отсутствует")
        readme_layout.addWidget(self.readme_text)

        root = QVBoxLayout(self)
        root.addWidget(self.project_title)
        root.addWidget(self.stats_label)
        root.addWidget(metrics_box)
        root.addLayout(overview_header)
        root.addWidget(self.overview_text)
        root.addWidget(readme_box)

    def update_project_info(self, title: str, files_count: int, loc: int, summary: str) -> None:
        self.project_title.setText(title)
        self.stats_label.setText(f"Файлы: {files_count} • LOC: {loc}")
        self.overview_text.setMarkdown(summary or "Описание пока отсутствует")

    def update_metrics(self, metrics: dict[str, tuple[str, str, str]]) -> None:
        for metric_name, card in self.cards.items():
            grade, value, threshold = metrics.get(metric_name, ("—", "—", ""))
            card.grade_label.setText(f"Grade: {grade}")
            card.value_label.setText(f"Value: {value}")
            card.threshold_label.setText(threshold)

    def load_readme(self, repo_path: Path) -> None:
        for file_name in ["README.md", "readme.md", "README.rst", "README.txt"]:
            candidate = repo_path / file_name
            if not candidate.exists():
                continue
            content = candidate.read_text(encoding="utf-8", errors="ignore")
            if candidate.suffix.lower() == ".md":
                self.readme_text.setHtml(_render_markdown(content))
            else:
                self.readme_text.setPlainText(content)
            return
        self.readme_text.setMarkdown("README отсутствует")


def _render_markdown(content: str) -> str:
    try:
        import markdown  # type: ignore

        html = markdown.markdown(content, extensions=["fenced_code", "tables", "sane_lists"])
        return (
            "<style>"
            "body{color:#E6ECFF;background:#121A2B;font-family:Segoe UI,Arial,sans-serif;line-height:1.5;}"
            "a{color:#79A6FF;} pre{background:#1A2438;padding:10px;border-radius:8px;}"
            "code{background:#1A2438;padding:2px 4px;border-radius:4px;}"
            "table{border-collapse:collapse;} th,td{border:1px solid #2A3755;padding:6px;}"
            "</style>"
            f"<body>{html}</body>"
        )
    except Exception:  # noqa: BLE001
        return content
