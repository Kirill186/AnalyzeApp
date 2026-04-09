from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from PySide6.QtCore import QSettings


DEFAULT_QUALITY_THRESHOLDS: dict[str, list[float]] = {
    "lint_issues_per_kloc": [2.0, 6.0, 12.0, 20.0],
    "mypy_errors_per_kloc": [0.0, 1.0, 3.0, 6.0],
    "tests_failed_rate_pct": [0.0, 2.0, 5.0, 10.0],
    "complexity_b_plus_share_pct": [5.0, 10.0, 20.0, 35.0],
    "maintainability_avg_mi": [85.0, 75.0, 65.0, 50.0],
    "dead_code_findings_per_kloc": [1.0, 3.0, 6.0, 10.0],
    "duplication_pct": [3.0, 6.0, 10.0, 15.0],
}


@dataclass(slots=True)
class RepoListItemVM:
    repo_id: int
    title: str
    source_type: Literal["local", "remote"]
    group: Literal["favorites", "local", "remote", "archived"]
    is_favorite: bool
    last_updated_at: datetime | None
    default_branch: str
    health_grade: str | None
    working_path: str
    origin_url: str


class UiStateStore:
    def __init__(self) -> None:
        self.settings = QSettings("AnalyzeApp", "AnalyzeAppDesktop")

    def repo_order(self) -> list[int]:
        raw = self.settings.value("repo_order", [])
        if isinstance(raw, list):
            return [int(item) for item in raw]
        return []

    def set_repo_order(self, repo_ids: list[int]) -> None:
        self.settings.setValue("repo_order", repo_ids)

    def repo_groups(self) -> dict[int, str]:
        raw = self.settings.value("repo_groups", {})
        if isinstance(raw, dict):
            return {int(k): str(v) for k, v in raw.items()}
        return {}

    def set_repo_group(self, repo_id: int, group: str) -> None:
        groups = self.repo_groups()
        groups[repo_id] = group
        self.settings.setValue("repo_groups", groups)

    def favorites(self) -> set[int]:
        raw = self.settings.value("repo_favorites", [])
        if isinstance(raw, list):
            return {int(item) for item in raw}
        return set()

    def set_favorites(self, favorites: set[int]) -> None:
        self.settings.setValue("repo_favorites", sorted(favorites))

    def quality_thresholds(self) -> dict[str, list[float]]:
        raw = self.settings.value("quality_thresholds", {})
        parsed: dict[str, list[float]] = {}
        if isinstance(raw, dict):
            for key, values in raw.items():
                if not isinstance(values, list) or len(values) != 4:
                    continue
                try:
                    parsed[str(key)] = [float(value) for value in values]
                except (TypeError, ValueError):
                    continue

        for key, defaults in DEFAULT_QUALITY_THRESHOLDS.items():
            parsed.setdefault(key, defaults.copy())
        return parsed

    def set_quality_thresholds(self, thresholds: dict[str, list[float]]) -> None:
        normalized: dict[str, list[float]] = {}
        for key, defaults in DEFAULT_QUALITY_THRESHOLDS.items():
            values = thresholds.get(key, defaults)
            if len(values) != 4:
                values = defaults
            normalized[key] = [float(value) for value in values]
        self.settings.setValue("quality_thresholds", normalized)

    def reset_quality_thresholds(self) -> None:
        self.set_quality_thresholds({key: value.copy() for key, value in DEFAULT_QUALITY_THRESHOLDS.items()})
