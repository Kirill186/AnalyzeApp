from __future__ import annotations

from typing import Protocol

from analyze_app.domain.entities import LLMResult, ProjectOverviewResult


class DiffSummaryBackend(Protocol):
    model: str

    def summarize_diff(self, diff_text: str) -> LLMResult:
        ...


class ProjectOverviewAIBackend(Protocol):
    model: str

    def summarize_project(self, context: str) -> ProjectOverviewResult:
        ...
