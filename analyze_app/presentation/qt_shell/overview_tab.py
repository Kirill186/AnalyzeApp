from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from analyze_app.presentation.qt_shell.web_view_utils import markdown_to_html, render_html_template


class OverviewTab(QWidget):
    regenerate_requested = Signal()

    METRICS_ORDER: list[tuple[str, str]] = [
        ("lint", "Линт"),
        ("typing_health", "Типы"),
        ("tests", "Тесты"),
        ("complexity", "Сложность"),
        ("maintainability", "Поддержка"),
        ("dead_code", "Мертвый код"),
        ("duplication", "Дубли"),
        ("ai_signal", "AI-сигнал"),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state = self._empty_state()

        self.regenerate_btn = QPushButton("Regenerate")
        self.regenerate_btn.clicked.connect(self.regenerate_requested.emit)

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        toolbar.addWidget(self.regenerate_btn)

        self.web = QWebEngineView()

        root = QVBoxLayout(self)
        root.addLayout(toolbar)
        root.addWidget(self.web)
        self._render()

    def _empty_state(self) -> dict[str, object]:
        return {
            "title": "Выберите репозиторий",
            "filesCount": "—",
            "loc": "—",
            "summaryHtml": "<p class='muted'>Описание пока отсутствует</p>",
            "readmeHtml": "<p class='muted'>README отсутствует</p>",
            "metrics": [
                {"label": label, "grade": "—", "value": "—", "threshold": "", "loading": False}
                for _, label in self.METRICS_ORDER
            ],
        }

    def reset(self) -> None:
        self._state = self._empty_state()
        self._render()

    def set_loading(self, title: str) -> None:
        self._state["title"] = title
        self._state["filesCount"] = "..."
        self._state["loc"] = "..."
        self._state["summaryHtml"] = "<p class='muted'>Анализ выполняется...</p>"
        self._state["readmeHtml"] = "<p class='muted'>Анализ выполняется...</p>"
        self._state["metrics"] = [
            {"label": label, "grade": "", "value": "Анализ выполняется", "threshold": "", "loading": True}
            for _, label in self.METRICS_ORDER
        ]
        self._render()

    def set_summary_markdown(self, summary: str) -> None:
        self._state["summaryHtml"] = markdown_to_html(summary or "Описание пока отсутствует")
        self._render()

    def update_project_info(self, title: str, files_count: int, loc: int, summary: str) -> None:
        self._state["title"] = title
        self._state["filesCount"] = files_count
        self._state["loc"] = loc
        self._state["summaryHtml"] = markdown_to_html(summary or "Описание пока отсутствует")
        self._render()

    def update_metrics(self, metrics: dict[str, tuple[str, str, str]]) -> None:
        self._state["metrics"] = []
        for metric_name, label in self.METRICS_ORDER:
            grade, value, threshold = metrics.get(metric_name, ("—", "—", ""))
            self._state["metrics"].append(
                {"label": label, "grade": grade, "value": value, "threshold": threshold, "loading": False}
            )
        self._render()

    def load_readme(self, repo_path: Path) -> None:
        candidates = _find_readme_candidates(repo_path)
        if candidates:
            candidate = candidates[0]
            content = candidate.read_text(encoding="utf-8", errors="ignore")
            self._state["readmeHtml"] = markdown_to_html(content)
        else:
            self._state["readmeHtml"] = "<p class='muted'>README отсутствует</p>"
        self._render()

    def _render(self) -> None:
        template_path = Path(__file__).with_name("web_assets") / "overview.html"
        html = render_html_template(template_path, self._state)
        self.web.setHtml(html, QUrl.fromLocalFile(str(template_path.parent)))


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
