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
        candidates = _find_readme_candidates(repo_path)
        if candidates:
            candidate = candidates[0]
            content = candidate.read_text(encoding="utf-8", errors="ignore")
            if candidate.suffix.lower() == ".md" or candidate.name.lower() == "readme":
                self.readme_text.setMarkdown(content)
            else:
                self.readme_text.setPlainText(content)
            return
        self.readme_text.setMarkdown("README отсутствует")


def _find_readme_candidates(repo_path: Path) -> list[Path]:
    if not repo_path.exists() or not repo_path.is_dir():
        return []

    def is_readme(path: Path) -> bool:
        return path.is_file() and path.name.lower().startswith("readme")

    preferred_suffix_order = {".md": 0, ".markdown": 1, ".rst": 2, ".txt": 3, "": 4}

    root_files = [item for item in repo_path.iterdir() if is_readme(item)]
    if root_files:
        root_files.sort(key=lambda path: preferred_suffix_order.get(path.suffix.lower(), 9))
        return root_files

    nested_candidates: list[Path] = []
    for path in repo_path.rglob("*"):
        if not is_readme(path):
            continue
        try:
            depth = len(path.relative_to(repo_path).parts)
        except ValueError:
            continue
        if depth <= 3:
            nested_candidates.append(path)

    nested_candidates.sort(
        key=lambda path: (
            len(path.relative_to(repo_path).parts),
            preferred_suffix_order.get(path.suffix.lower(), 9),
            str(path).lower(),
        )
    )
    return nested_candidates
