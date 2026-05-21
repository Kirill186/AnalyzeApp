from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from PySide6.QtCore import QSettings

from analyze_app.infrastructure.analysis.ruff_settings import (
    RuffSettings,
    ruff_settings_from_mapping,
    ruff_settings_to_mapping,
)
from analyze_app.shared.config import DEFAULT_CONFIG


DEFAULT_QUALITY_THRESHOLDS: dict[str, list[float]] = {
    "lint_issues_per_kloc": [2.0, 6.0, 12.0, 20.0],
    "mypy_errors_per_kloc": [0.0, 1.0, 3.0, 6.0],
    "tests_passed_rate_pct": [100.0, 98.0, 95.0, 90.0],
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


@dataclass(slots=True)
class AISettings:
    backend: Literal["llama_cpp", "ollama"]
    model_path: str
    context_size: int
    threads: int
    gpu_layers: int
    ollama_url: str
    ollama_model: str
    use_solution_chunks: bool = True


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

    def repo_titles(self) -> dict[int, str]:
        raw = self.settings.value("repo_titles", {})
        if isinstance(raw, dict):
            titles: dict[int, str] = {}
            for key, value in raw.items():
                try:
                    repo_id = int(key)
                except (TypeError, ValueError):
                    continue
                title = str(value).strip()
                if title:
                    titles[repo_id] = title
            return titles
        return {}

    def set_repo_title(self, repo_id: int, title: str) -> None:
        titles = self.repo_titles()
        cleaned_title = title.strip()
        if cleaned_title:
            titles[repo_id] = cleaned_title
        else:
            titles.pop(repo_id, None)
        self.settings.setValue("repo_titles", titles)

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

        titles = self.repo_titles()
        titles.pop(repo_id, None)
        self.settings.setValue("repo_titles", titles)

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

    def ruff_settings(self) -> RuffSettings:
        raw = self.settings.value("ruff/settings", "")
        if isinstance(raw, str) and raw.strip():
            try:
                return ruff_settings_from_mapping(json.loads(raw))
            except json.JSONDecodeError:
                return RuffSettings()
        if isinstance(raw, dict):
            return ruff_settings_from_mapping(raw)
        return RuffSettings()

    def set_ruff_settings(self, settings: RuffSettings) -> None:
        payload = ruff_settings_to_mapping(settings)
        self.settings.setValue("ruff/settings", json.dumps(payload, ensure_ascii=False))

    def editor_command(self) -> str:
        return str(self.settings.value("editor/command", "") or "").strip()

    def set_editor_command(self, command: str) -> None:
        self.settings.setValue("editor/command", command.strip())

    def ai_settings(self) -> AISettings:
        backend = str(self.settings.value("ai/backend", DEFAULT_CONFIG.llm_backend) or DEFAULT_CONFIG.llm_backend)
        backend = backend if backend in {"llama_cpp", "ollama"} else "llama_cpp"
        return AISettings(
            backend=backend,  # type: ignore[arg-type]
            model_path=str(
                self.settings.value("ai/model_path", DEFAULT_CONFIG.llm_model_path) or DEFAULT_CONFIG.llm_model_path
            ),
            context_size=_coerce_int(self.settings.value("ai/context_size", DEFAULT_CONFIG.llm_context_size), 4096),
            threads=_coerce_int(self.settings.value("ai/threads", DEFAULT_CONFIG.llm_threads), 0),
            gpu_layers=_coerce_int(self.settings.value("ai/gpu_layers", DEFAULT_CONFIG.llm_gpu_layers), 0),
            ollama_url=str(self.settings.value("ai/ollama_url", DEFAULT_CONFIG.ollama_url) or DEFAULT_CONFIG.ollama_url),
            ollama_model=str(
                self.settings.value("ai/ollama_model", DEFAULT_CONFIG.ollama_model) or DEFAULT_CONFIG.ollama_model
            ),
            use_solution_chunks=_coerce_bool(self.settings.value("ai/use_solution_chunks", True), True),
        )

    def set_ai_settings(self, settings: AISettings) -> None:
        self.settings.setValue("ai/backend", settings.backend)
        self.settings.setValue("ai/model_path", settings.model_path)
        self.settings.setValue("ai/context_size", int(settings.context_size))
        self.settings.setValue("ai/threads", int(settings.threads))
        self.settings.setValue("ai/gpu_layers", int(settings.gpu_layers))
        self.settings.setValue("ai/ollama_url", settings.ollama_url)
        self.settings.setValue("ai/ollama_model", settings.ollama_model)
        self.settings.setValue("ai/use_solution_chunks", bool(settings.use_solution_chunks))


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


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, int):
        return bool(value)
    return default
