from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from analyze_app.presentation.qt_shell.readme_finder import find_readme_candidates
from analyze_app.presentation.qt_shell.web_view_utils import markdown_to_html, render_html_template


class OverviewWebPage(QWebEnginePage):
    regenerate_requested = Signal()

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:  # type: ignore[override]
        if url.scheme() == "analyzeapp" and url.host().lower() == "regenerate-overview":
            self.regenerate_requested.emit()
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class OverviewTab(QWidget):
    regenerate_requested = Signal()
    refresh_requested = Signal()

    METRICS_ORDER: list[tuple[str, str]] = [
        ("lint", "Линт"),
        ("typing_health", "Типы"),
        ("complexity", "Сложность"),
        ("maintainability", "Поддержка"),
        ("dead_code", "Мертвый код"),
        ("duplication", "Дубли"),
        ("ai_signal", "AI-оценка"),
        ("tests", "Тесты"),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state = self._empty_state()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        toolbar.addWidget(self.refresh_btn)

        self.web = QWebEngineView()
        self.page = OverviewWebPage(self.web)
        self.page.regenerate_requested.connect(self.regenerate_requested.emit)
        self.web.setPage(self.page)

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
                {
                    "name": name,
                    "label": label,
                    "grade": "—",
                    "value": "—",
                    "threshold": "",
                    "details": [],
                    "loading": False,
                }
                for name, label in self.METRICS_ORDER
            ],
        }

    def reset(self) -> None:
        self._state = self._empty_state()
        self._render()

    def set_loading(self, title: str) -> None:
        self._state["title"] = title
        self._state["filesCount"] = "..."
        self._state["loc"] = "..."
        self._state["readmeHtml"] = "<p class='muted'>Анализ выполняется...</p>"
        self._state["metrics"] = [
            {
                "name": name,
                "label": label,
                "grade": "",
                "value": "Анализ выполняется",
                "threshold": "",
                "details": [],
                "loading": True,
            }
            for name, label in self.METRICS_ORDER
        ]
        self._render()

    def set_summary_markdown(self, summary: str) -> None:
        self._state["summaryHtml"] = markdown_to_html(summary or "Описание пока отсутствует")
        self._render()

    def set_summary_loading(self) -> None:
        self._state["summaryHtml"] = (
            "<p class='muted'><span class='loader'></span> Генерация описания проекта...</p>"
        )
        self._render()

    def update_project_stats(self, title: str, files_count: int | str, loc: int | str) -> None:
        self._state["title"] = title
        self._state["filesCount"] = files_count
        self._state["loc"] = loc
        self._render()

    def update_title(self, title: str) -> None:
        self._state["title"] = title
        self._render()

    def update_project_info(self, title: str, files_count: int | str, loc: int | str, summary: str) -> None:
        self._state["title"] = title
        self._state["filesCount"] = files_count
        self._state["loc"] = loc
        self._state["summaryHtml"] = markdown_to_html(summary or "Описание пока отсутствует")
        self._render()

    def update_metrics(
        self,
        metrics: dict[str, tuple[str, str, str]],
        metric_details: dict[str, list[dict[str, str]]] | None = None,
    ) -> None:
        self._state["metrics"] = []
        metric_details = metric_details or {}
        for metric_name, label in self.METRICS_ORDER:
            grade, value, threshold = metrics.get(metric_name, ("—", "—", ""))
            details = metric_details.get(metric_name, [])
            self._state["metrics"].append(
                {
                    "name": metric_name,
                    "label": label,
                    "grade": grade,
                    "value": value,
                    "threshold": threshold,
                    "details": details,
                    "loading": False,
                }
            )
        self._render()

    def update_metric(
        self,
        metric_name: str,
        metric: tuple[str, str, str],
        details: list[dict[str, str]] | None = None,
    ) -> None:
        grade, value, threshold = metric
        metrics = self._state.get("metrics")
        if not isinstance(metrics, list):
            return
        for item in metrics:
            if not isinstance(item, dict) or item.get("name") != metric_name:
                continue
            payload = {"grade": grade, "value": value, "threshold": threshold, "loading": False}
            if details is not None:
                payload["details"] = details
            item.update(payload)
            self._render()
            return

    def load_readme(self, repo_path: Path) -> None:
        candidates = find_readme_candidates(repo_path)
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
