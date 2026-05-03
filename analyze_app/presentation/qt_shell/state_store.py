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
    group: str
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
            return _coerce_int_list(raw)
        if isinstance(raw, tuple):
            return _coerce_int_list(list(raw))
        if isinstance(raw, str):
            return _coerce_int_list(raw.split(","))
        return []

    def set_repo_order(self, repo_ids: list[int]) -> None:
        self.settings.setValue("repo_order", repo_ids)

    def repo_group_order(self) -> list[str]:
        raw = self.settings.value("repo_group_order", [])
        if isinstance(raw, list):
            return _coerce_str_list(raw)
        if isinstance(raw, tuple):
            return _coerce_str_list(list(raw))
        if isinstance(raw, str):
            return _coerce_str_list(raw.split(","))
        return []

    def set_repo_group_order(self, groups: list[str]) -> None:
        self.settings.setValue("repo_group_order", _coerce_str_list(groups))

    def repo_groups(self) -> dict[int, str]:
        raw = self.settings.value("repo_groups", {})
        if isinstance(raw, dict):
            groups: dict[int, str] = {}
            for key, value in raw.items():
                try:
                    repo_id = int(key)
                except (TypeError, ValueError):
                    continue
                group = str(value).strip()
                if group:
                    groups[repo_id] = group
            return groups
        return {}

    def set_repo_group(self, repo_id: int, group: str) -> None:
        self.ensure_repo_group(group)
        groups = self.repo_groups()
        groups[repo_id] = group
        self.settings.setValue("repo_groups", groups)

    def ensure_repo_group(self, group: str) -> None:
        group = str(group or "").strip()
        if not group or group == "favorites":
            return
        groups = self.repo_group_order()
        if group not in groups:
            groups.append(group)
            self.set_repo_group_order(groups)

    def rename_repo_group(self, old_group: str, new_group: str, repo_ids: list[int] | None = None) -> None:
        old_group = str(old_group or "").strip()
        new_group = str(new_group or "").strip()
        if not old_group or not new_group or old_group == new_group or new_group == "favorites":
            return

        order: list[str] = []
        for group in self.repo_group_order():
            replacement = new_group if group == old_group else group
            if replacement not in order:
                order.append(replacement)
        if new_group not in order:
            order.append(new_group)
        self.set_repo_group_order(order)

        groups = self.repo_groups()
        for repo_id, group in list(groups.items()):
            if group == old_group:
                groups[repo_id] = new_group
        for repo_id in repo_ids or []:
            groups[int(repo_id)] = new_group
        self.settings.setValue("repo_groups", groups)

    def delete_repo_group(self, group: str, fallback_groups: dict[int, str] | None = None) -> None:
        group = str(group or "").strip()
        if not group:
            return

        groups = self.repo_groups()
        for repo_id, fallback in (fallback_groups or {}).items():
            fallback = str(fallback or "").strip()
            if fallback and fallback != group:
                groups[int(repo_id)] = fallback
            else:
                groups.pop(int(repo_id), None)
        for repo_id, repo_group in list(groups.items()):
            if repo_group == group:
                groups.pop(repo_id, None)
        self.settings.setValue("repo_groups", groups)
        self.set_repo_group_order([item for item in self.repo_group_order() if item != group])

    def favorites(self) -> set[int]:
        raw = self.settings.value("repo_favorites", [])
        if isinstance(raw, list):
            return {int(item) for item in raw}
        return set()

    def set_favorites(self, favorites: set[int]) -> None:
        self.settings.setValue("repo_favorites", sorted(favorites))

    def remove_repository(self, repo_id: int) -> None:
        order = [item for item in self.repo_order() if item != repo_id]
        self.set_repo_order(order)

        groups = self.repo_groups()
        groups.pop(repo_id, None)
        self.settings.setValue("repo_groups", groups)

        favorites = self.favorites()
        favorites.discard(repo_id)
        self.set_favorites(favorites)

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


def _coerce_int_list(values: list[object]) -> list[int]:
    parsed: list[int] = []
    for value in values:
        try:
            parsed.append(int(value))
        except (TypeError, ValueError):
            continue
    return parsed


def _coerce_str_list(values: list[object]) -> list[str]:
    parsed: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item != "favorites" and item not in parsed:
            parsed.append(item)
    return parsed
