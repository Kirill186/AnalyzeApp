from __future__ import annotations

from pathlib import Path

from analyze_app.domain.entities import ChangeMetrics, WorkingTreeReport
from analyze_app.infrastructure.ai.ollama_backend import OllamaBackend
from analyze_app.infrastructure.analysis.pytest_runner import PytestRunner
from analyze_app.infrastructure.analysis.ruff_runner import RuffRunner
from analyze_app.infrastructure.git.backend import GitBackend
from analyze_app.infrastructure.storage.sqlite_store import SqliteStore


class WorkingTreeReportUseCase:
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

    def execute(self, repo_id: int, repo_path: Path, use_cache: bool = True) -> WorkingTreeReport:
        status = self.git_backend.status_porcelain(repo_path)
        status_key = "\n".join(status)

        if use_cache:
            cached = self.store.load_working_tree_report(repo_id, status_key)
            if cached:
                return cached

        diff_text = self.git_backend.read_working_tree_diff(repo_path)
        changes = self.git_backend.read_working_tree_file_changes(repo_path)
        metrics = ChangeMetrics(
            files_changed=len(changes),
            lines_added=sum(c.additions for c in changes),
            lines_deleted=sum(c.deletions for c in changes),
        )
        issues = self.ruff_runner.run(repo_path)
        tests = self.pytest_runner.run(repo_path)
        ai_summary = self.ai_backend.summarize_diff(diff_text)

        report = WorkingTreeReport(metrics=metrics, issues=issues, tests=tests, ai_summary=ai_summary)
        self.store.save_working_tree_report(repo_id, status_key, report)
        return report
