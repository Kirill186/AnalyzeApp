from __future__ import annotations

from pathlib import Path

from analyze_app.domain.entities import ChangeMetrics, CommitReport, LLMResult, TestRunResult
from analyze_app.infrastructure.ai.ollama_backend import OllamaBackend
from analyze_app.infrastructure.analysis.pytest_runner import PytestRunner
from analyze_app.infrastructure.analysis.ruff_runner import RuffRunner
from analyze_app.infrastructure.git.backend import GitBackend
from analyze_app.infrastructure.storage.sqlite_store import SqliteStore


class CommitReportUseCase:
    def __init__(
        self,
        git_backend: GitBackend,
        ruff_runner: RuffRunner,
        pytest_runner: PytestRunner,
        ai_backend: OllamaBackend,
        store: SqliteStore,
    ) -> None:
        self.git_backend = git_backend
        self.ruff_runner = ruff_runner
        self.pytest_runner = pytest_runner
        self.ai_backend = ai_backend
        self.store = store

    def execute(self, repo_id: int, repo_path: Path, commit_hash: str, use_cache: bool = True) -> CommitReport:
        if use_cache:
            cached = self.store.load_commit_report(repo_id, commit_hash)
            if cached and self._is_cache_compatible(cached[9]) and not self._is_unavailable_summary(cached[8]):
                return CommitReport(
                    commit_hash=commit_hash,
                    metrics=ChangeMetrics(files_changed=cached[2], lines_added=cached[3], lines_deleted=cached[4]),
                    issues=[],
                    tests=TestRunResult(total=cached[6], failed=cached[7], passed=max(cached[6] - cached[7], 0)),
                    ai_summary=LLMResult(summary=cached[8], model_info=cached[9]),
                )

        diff_text = self.git_backend.read_commit_diff(repo_path, commit_hash)
        changes = self.git_backend.read_commit_file_changes(repo_path, commit_hash)
        metrics = ChangeMetrics(
            files_changed=len(changes),
            lines_added=sum(c.additions for c in changes),
            lines_deleted=sum(c.deletions for c in changes),
        )
        issues = self.ruff_runner.run(repo_path)
        tests = self.pytest_runner.run(repo_path)
        ai_summary = self.ai_backend.summarize_diff(diff_text)
        report = CommitReport(
            commit_hash=commit_hash,
            metrics=metrics,
            issues=issues,
            tests=tests,
            ai_summary=ai_summary,
        )
        self.store.save_commit_report(repo_id, report)
        return report

    def _is_cache_compatible(self, cached_model_info: str) -> bool:
        return cached_model_info.endswith(self.ai_backend.model)

    @staticmethod
    def _is_unavailable_summary(summary: str) -> bool:
        return summary.strip().lower().startswith("ai summary unavailable")
