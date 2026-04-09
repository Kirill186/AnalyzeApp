from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from PySide6.QtCore import QSettings


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
