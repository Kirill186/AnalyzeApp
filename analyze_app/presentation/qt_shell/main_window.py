from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess

from PySide6.QtCore import QObject, QThread, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
)

from analyze_app.application.use_cases.build_project_map import BuildProjectMapUseCase
from analyze_app.application.use_cases.build_project_overview import BuildProjectOverviewUseCase
from analyze_app.application.use_cases.detect_ai_authorship import DetectAIAuthorshipUseCase
from analyze_app.application.use_cases.get_working_tree_report import WorkingTreeReportUseCase
from analyze_app.application.use_cases.import_repository import ImportRepositoryUseCase
from analyze_app.application.use_cases.list_commits import ListCommitsUseCase
from analyze_app.domain.entities import Commit, GraphEdge, GraphNode, ProjectGraph
from analyze_app.infrastructure.ai.ollama_backend import OllamaBackend
from analyze_app.infrastructure.ai.project_overview_backend import ProjectOverviewBackend
from analyze_app.infrastructure.ai.authorship import FeatureExtractor, ModelRuntime, ProbabilityCalibrator
from analyze_app.infrastructure.analysis.duplication_runner import DuplicationRunner
from analyze_app.infrastructure.analysis.map.ast_map_builder import AstMapBuilder
from analyze_app.infrastructure.analysis.mypy_runner import MypyRunner
from analyze_app.infrastructure.analysis.pytest_runner import PytestRunner
from analyze_app.infrastructure.analysis.radon_runner import RadonRunner
from analyze_app.infrastructure.analysis.ruff_runner import RuffRunner
from analyze_app.infrastructure.analysis.vulture_runner import VultureRunner
from analyze_app.infrastructure.git.backend import GitBackend
from analyze_app.infrastructure.storage.sqlite_store import SqliteStore
from analyze_app.presentation.qt_shell.app_menu import build_menu
from analyze_app.presentation.qt_shell.repo_add_dialog import RepoAddDialog
from analyze_app.presentation.qt_shell.repo_sidebar import RepoSidebar
from analyze_app.presentation.qt_shell.report_tabs import ReportTabs
from analyze_app.presentation.qt_shell.settings_dialog import QualitySettingsDialog
from analyze_app.presentation.qt_shell.state_store import RepoListItemVM, UiStateStore
from analyze_app.presentation.qt_shell.theme import apply_theme
from analyze_app.shared.config import DEFAULT_CONFIG


@dataclass(slots=True)
class ImportResult:
    repo_id: int
    repo_path: Path


class ImportRepositoryWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, source: str, git_backend: GitBackend, store: SqliteStore) -> None:
        super().__init__()
        self.source = source
        self.git_backend = git_backend
        self.store = store

    @Slot()
    def run(self) -> None:
        use_case = ImportRepositoryUseCase(self.git_backend, self.store, DEFAULT_CONFIG.clone_root)
        try:
            repo_id, repo_path = use_case.execute(self.source)
        except Exception as error:  # noqa: BLE001
            self.failed.emit(str(error))
            return
        self.finished.emit(ImportResult(repo_id=repo_id, repo_path=repo_path))


@dataclass(slots=True)
class RepositoryRefreshResult:
    repo_id: int
    repo_path: Path
    data_refresh_message: str | None
    files_count: int
    loc: int
    summary: str
    metrics: dict[str, tuple[str, str, str]]
    commits: list
    project_map: object
    workspace_files: list[dict[str, object]]
    workspace_diffs: dict[str, str]
    working_tree_message: str | None


class RepositoryRefreshWorker(QObject):
    finished = Signal(object)
    failed = Signal(int, str)

    def __init__(
        self,
        repo: RepoListItemVM,
        git_backend: GitBackend,
        store: SqliteStore,
        thresholds: dict[str, list[float]],
    ) -> None:
        super().__init__()
        self.repo = repo
        self.git_backend = git_backend
        self.store = store
        self.thresholds = thresholds

    @Slot()
    def run(self) -> None:
        try:
            result = self._build_result()
        except Exception as error:  # noqa: BLE001
            self.failed.emit(self.repo.repo_id, str(error))
            return
        self.finished.emit(result)

    def _build_result(self) -> RepositoryRefreshResult:
        repo_path = Path(self.repo.working_path)
        data_refresh_message = self.git_backend.refresh_remote_data(repo_path)
        tracked_files = self.git_backend.list_tracked_files(repo_path)
        loc = _count_python_loc(self.git_backend, repo_path, tracked_files)

        metrics = _calculate_quality_metrics(
            repo_id=self.repo.repo_id,
            repo_path=repo_path,
            loc=loc,
            thresholds=self.thresholds,
            git_backend=self.git_backend,
            store=self.store,
            use_cache=False,
        )
        commits = ListCommitsUseCase(self.git_backend).execute(repo_path, limit=50)
        project_map = BuildProjectMapUseCase(self.git_backend, AstMapBuilder(), self.store).execute(
            self.repo.repo_id,
            repo_path,
            use_cache=False,
        )

        status_lines = self.git_backend.status_porcelain(repo_path)
        file_rows = _parse_status_rows(status_lines)
        use_case = WorkingTreeReportUseCase(
            self.git_backend,
            RuffRunner(),
            PytestRunner(),
            OllamaBackend(DEFAULT_CONFIG.ollama_url, DEFAULT_CONFIG.ollama_model),
            self.store,
        )
        try:
            report = use_case.execute(self.repo.repo_id, repo_path, use_cache=False)
        except Exception:  # noqa: BLE001
            report = None

        workspace_files = _build_workspace_files_payload(
            file_rows,
            report.issues if report else [],
            report.tests if report else None,
        )
        workspace_diffs = {
            file_row["path"]: self.git_backend.read_working_tree_diff(repo_path, file_row["path"])
            for file_row in file_rows
        }
        working_tree_message = None
        if report:
            working_tree_message = (
                f"Working tree: files={report.metrics.files_changed} "
                f"+{report.metrics.lines_added} -{report.metrics.lines_deleted}"
            )

        return RepositoryRefreshResult(
            repo_id=self.repo.repo_id,
            repo_path=repo_path,
            data_refresh_message=data_refresh_message,
            files_count=len(tracked_files),
            loc=loc,
            summary="",
            metrics=metrics,
            commits=commits,
            project_map=project_map,
            workspace_files=workspace_files,
            workspace_diffs=workspace_diffs,
            working_tree_message=working_tree_message,
        )


class MainWindow(QMainWindow):
    def __init__(self, store: SqliteStore, git_backend: GitBackend) -> None:
        super().__init__()
        self.store = store
        self.git_backend = git_backend
        self.state_store = UiStateStore()
        self.current_repo: RepoListItemVM | None = None

        self.setWindowTitle("AnalyzeApp")
        self.resize(1400, 900)
        self.setMinimumWidth(1280)

        self.sidebar = RepoSidebar()
        self.tabs = ReportTabs()
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.import_thread: QThread | None = None
        self.import_worker: ImportRepositoryWorker | None = None
        self.refresh_thread: QThread | None = None
        self.refresh_worker: RepositoryRefreshWorker | None = None
        self.active_refresh_repo_id: int | None = None
        self.refresh_queue: list[int] = []
        self.refresh_all_running = False

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.tabs)
        splitter.setSizes([320, 1080])
        self.setCentralWidget(splitter)

        self.menu = build_menu(self)
        self._bind_actions(splitter)
        self._bind_tab_actions()
        self._load_repositories()

    def _bind_actions(self, splitter: QSplitter) -> None:
        self.sidebar.add_clicked.connect(self._add_repository)
        self.sidebar.refresh_all_clicked.connect(self._refresh_all)
        self.sidebar.repo_selected.connect(self._on_repo_selected)
        self.sidebar.repo_delete_requested.connect(self._delete_repository)

        self.menu.add_repository.triggered.connect(self._add_repository)
        self.menu.refresh_all.triggered.connect(self._refresh_all)
        self.menu.refresh_current.triggered.connect(self._refresh_current)
        self.menu.rebuild_map.triggered.connect(self._refresh_current)
        self.menu.run_working_tree.triggered.connect(self._refresh_current)
        self.menu.run_commit.triggered.connect(self._refresh_commits)
        self.menu.toggle_sidebar.triggered.connect(lambda: self.sidebar.setVisible(not self.sidebar.isVisible()))
        self.menu.quality_grades.triggered.connect(self._open_quality_settings)

        self.tabs.commits_tab.commit_selected.connect(self._show_commit_in_status)
        self.tabs.commits_tab.ai_summary_requested.connect(self._describe_commit_with_ai)
        self.tabs.workspace_tab.stage_requested.connect(self._stage_workspace_file)
        self.tabs.workspace_tab.open_requested.connect(self._open_workspace_file)

    def _bind_tab_actions(self) -> None:
        self.tabs.overview_tab.regenerate_requested.connect(self._regenerate_overview)
        self.tabs.overview_tab.refresh_requested.connect(self._refresh_current)

    def _open_quality_settings(self) -> None:
        dialog = QualitySettingsDialog(self.state_store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and self.current_repo:
            self._refresh_current()

    def _load_repositories(self) -> None:
        self.sidebar.set_repositories(self._repository_items())

    def _repository_items(self) -> list[RepoListItemVM]:
        items: list[RepoListItemVM] = []
        favorites = self.state_store.favorites()
        groups = self.state_store.repo_groups()
        for repo_id, origin_url, working_path, default_branch, created_at in self.store.list_repositories():
            source_type = "remote" if origin_url.startswith("http") or origin_url.endswith(".git") else "local"
            group = groups.get(repo_id, source_type)
            is_favorite = repo_id in favorites
            title = Path(working_path).name or origin_url
            last_updated = datetime.fromisoformat(created_at) if created_at else None
            items.append(
                RepoListItemVM(
                    repo_id=repo_id,
                    title=title,
                    source_type=source_type,
                    group=group if group in {"favorites", "local", "remote", "archived"} else source_type,
                    is_favorite=is_favorite,
                    last_updated_at=last_updated,
                    default_branch=default_branch,
                    health_grade=None,
                    working_path=working_path,
                    origin_url=origin_url,
                )
            )

        order = self.state_store.repo_order()
        ordering = {repo_id: idx for idx, repo_id in enumerate(order)}
        items.sort(key=lambda item: ordering.get(item.repo_id, 10_000 + item.repo_id))
        return items

    def _add_repository(self) -> None:
        dialog = RepoAddDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._start_repository_import(dialog.source)

    def _start_repository_import(self, source: str) -> None:
        if self.import_thread is not None and self.import_thread.isRunning():
            self.status.showMessage("Repository import is already running.", 4_000)
            return

        self.status.showMessage("Repository import started in background.", 5_000)
        self.import_thread = QThread(self)
        self.import_worker = ImportRepositoryWorker(source=source, git_backend=self.git_backend, store=self.store)
        self.import_worker.moveToThread(self.import_thread)

        self.import_thread.started.connect(self.import_worker.run)
        self.import_worker.finished.connect(self._on_import_finished)
        self.import_worker.failed.connect(self._on_import_failed)
        self.import_worker.finished.connect(self.import_thread.quit)
        self.import_worker.failed.connect(self.import_thread.quit)
        self.import_thread.finished.connect(self._cleanup_import_worker)
        self.import_thread.start()

    @Slot(object)
    def _on_import_finished(self, result: ImportResult) -> None:
        self.status.showMessage(f"Repository imported: {result.repo_path} (id={result.repo_id})", 5_000)
        self._load_repositories()
        self._on_repo_selected(result.repo_id)

    @Slot(str)
    def _on_import_failed(self, error: str) -> None:
        QMessageBox.critical(self, "Import failed", error)

    @Slot()
    def _cleanup_import_worker(self) -> None:
        if self.import_worker:
            self.import_worker.deleteLater()
            self.import_worker = None
        if self.import_thread:
            self.import_thread.deleteLater()
            self.import_thread = None

    def _on_repo_selected(self, repo_id: int) -> None:
        repos = [repo for repo in self._current_repo_items() if repo.repo_id == repo_id]
        if not repos:
            return
        self.current_repo = repos[0]
        self._load_saved_repository_result()

    def _load_saved_repository_result(self) -> None:
        if not self.current_repo:
            return

        payload = self.store.load_repository_analysis_snapshot(self.current_repo.repo_id)
        if payload:
            result = _repository_result_from_snapshot(self.current_repo, payload, self.store)
            self._apply_repository_result(result, update_summary=True)
            self.status.showMessage(f"Loaded saved analysis: {self.current_repo.title}", 4_000)
            return

        cached_overview = self.store.load_project_overview(self.current_repo.repo_id)
        summary = cached_overview[0] if cached_overview else "Описание пока не сгенерировано. Нажмите Regenerate."
        self.tabs.overview_tab.update_project_info(self.current_repo.title, "-", "-", summary)
        self.tabs.overview_tab.update_metrics({})
        self.tabs.overview_tab.load_readme(Path(self.current_repo.working_path))
        self.tabs.commits_tab.clear()
        self.tabs.project_map_tab.clear()
        self.tabs.workspace_tab.clear()
        self.status.showMessage(f"No saved analysis yet: {self.current_repo.title}", 5_000)

    def _delete_repository(self, repo_id: int) -> None:
        repos = [repo for repo in self._current_repo_items() if repo.repo_id == repo_id]
        title = repos[0].title if repos else f"#{repo_id}"
        reply = QMessageBox.question(
            self,
            "Remove repository",
            f"Remove '{title}' from AnalyzeApp? Files on disk will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.store.delete_repository(repo_id)
        self.state_store.remove_repository(repo_id)
        if self.current_repo and self.current_repo.repo_id == repo_id:
            self.current_repo = None
            self._clear_tabs()
        self._load_repositories()
        self.status.showMessage(f"Repository removed: {title}", 5_000)

    def _clear_tabs(self) -> None:
        self.tabs.overview_tab.reset()
        self.tabs.commits_tab.clear()
        self.tabs.project_map_tab.clear()
        self.tabs.workspace_tab.clear()

    def _current_repo_items(self) -> list[RepoListItemVM]:
        return self._repository_items()

    def _refresh_current(self) -> None:
        if not self.current_repo:
            self.status.showMessage("Select a repository in the left sidebar.", 4_000)
            return
        if self._start_repository_refresh(self.current_repo):
            self._show_repo_loading(self.current_repo)

    def _refresh_all(self) -> None:
        repos = self._repository_items()
        if not repos:
            self.status.showMessage("No repositories to refresh.", 4_000)
            return

        active_id = self.active_refresh_repo_id
        self.refresh_queue = [repo.repo_id for repo in repos if repo.repo_id != active_id]
        self.refresh_all_running = True
        if self.refresh_thread is not None and self.refresh_thread.isRunning():
            self.status.showMessage(f"Refresh all queued: {len(self.refresh_queue)} repositories left.", 5_000)
            return

        self.status.showMessage(f"Refresh all started: {len(self.refresh_queue)} repositories.", 5_000)
        self._start_next_queued_refresh()

    def _show_repo_loading(self, repo: RepoListItemVM) -> None:
        self.tabs.overview_tab.set_loading(repo.title)
        self.tabs.commits_tab.set_loading()
        self.tabs.project_map_tab.set_loading()
        self.tabs.workspace_tab.set_loading()
        self.status.showMessage(f"Analysis started: {repo.title}", 5_000)

    def _start_repository_refresh(self, repo: RepoListItemVM) -> bool:
        if self.refresh_thread is not None and self.refresh_thread.isRunning():
            if repo.repo_id == self.active_refresh_repo_id:
                self.status.showMessage(f"Analysis already running: {repo.title}", 4_000)
                return False
            self._queue_repository_refresh(repo)
            self.status.showMessage(f"Analysis queued: {repo.title}", 4_000)
            return False

        self.active_refresh_repo_id = repo.repo_id
        self.refresh_thread = QThread(self)
        self.refresh_worker = RepositoryRefreshWorker(
            repo=repo,
            git_backend=self.git_backend,
            store=self.store,
            thresholds=self.state_store.quality_thresholds(),
        )
        self.refresh_worker.moveToThread(self.refresh_thread)

        self.refresh_thread.started.connect(self.refresh_worker.run)
        self.refresh_worker.finished.connect(self._on_refresh_finished)
        self.refresh_worker.failed.connect(self._on_refresh_failed)
        self.refresh_worker.finished.connect(self.refresh_thread.quit)
        self.refresh_worker.failed.connect(self.refresh_thread.quit)
        self.refresh_thread.finished.connect(self._cleanup_refresh_worker)
        self.refresh_thread.start()
        return True

    def _queue_repository_refresh(self, repo: RepoListItemVM) -> None:
        if repo.repo_id == self.active_refresh_repo_id:
            return
        if repo.repo_id not in self.refresh_queue:
            self.refresh_queue.append(repo.repo_id)

    def _start_next_queued_refresh(self) -> None:
        while self.refresh_queue:
            repo_id = self.refresh_queue.pop(0)
            repos = [repo for repo in self._repository_items() if repo.repo_id == repo_id]
            if not repos:
                continue
            repo = repos[0]
            if self._start_repository_refresh(repo):
                if self.current_repo and self.current_repo.repo_id == repo.repo_id:
                    self._show_repo_loading(repo)
                else:
                    self.status.showMessage(f"Analysis started: {repo.title}", 5_000)
                return

        if self.refresh_all_running:
            self.refresh_all_running = False
            self.status.showMessage("Refresh all finished.", 5_000)

    @Slot(object)
    def _on_refresh_finished(self, result: RepositoryRefreshResult) -> None:
        self.store.save_repository_analysis_snapshot(result.repo_id, _snapshot_payload_from_result(result))

        if not self.current_repo or self.current_repo.repo_id != result.repo_id:
            return

        self._apply_repository_result(result, update_summary=False)
        messages = [message for message in (result.data_refresh_message, result.working_tree_message) if message]
        if messages:
            self.status.showMessage(" ".join(messages), 5_000)
        else:
            self.status.showMessage(f"Analysis finished: {self.current_repo.title}", 5_000)

    def _apply_repository_result(self, result: RepositoryRefreshResult, *, update_summary: bool) -> None:
        title = self.current_repo.title if self.current_repo and self.current_repo.repo_id == result.repo_id else result.repo_path.name
        if update_summary:
            self.tabs.overview_tab.update_project_info(title, result.files_count, result.loc, result.summary)
        else:
            self.tabs.overview_tab.update_project_stats(title, result.files_count, result.loc)
        self.tabs.overview_tab.update_metrics(result.metrics)
        self.tabs.overview_tab.load_readme(result.repo_path)
        self.tabs.commits_tab.set_commits(result.commits)
        self.tabs.project_map_tab.set_project_map(result.project_map)
        self.tabs.workspace_tab.set_workspace_data(result.workspace_files, result.workspace_diffs)

    @Slot(int, str)
    def _on_refresh_failed(self, repo_id: int, error: str) -> None:
        if self.current_repo and self.current_repo.repo_id == repo_id:
            self.tabs.overview_tab.update_project_stats(self.current_repo.title, 0, 0)
            self.tabs.overview_tab.update_metrics({})
            self.tabs.commits_tab.clear()
            self.tabs.project_map_tab.clear()
            self.tabs.workspace_tab.clear()
            self.status.showMessage(f"Repository analysis failed: {error}", 8_000)

    @Slot()
    def _cleanup_refresh_worker(self) -> None:
        self.active_refresh_repo_id = None
        if self.refresh_worker:
            self.refresh_worker.deleteLater()
            self.refresh_worker = None
        if self.refresh_thread:
            self.refresh_thread.deleteLater()
            self.refresh_thread = None

        self._start_next_queued_refresh()

    def _refresh_overview(self) -> None:
        if not self.current_repo:
            return
        repo_path = Path(self.current_repo.working_path)
        tracked_files = self.git_backend.list_tracked_files(repo_path)
        loc = self._count_python_loc(repo_path, tracked_files)

        cached_overview = self.store.load_project_overview(self.current_repo.repo_id)
        summary = cached_overview[0] if cached_overview else "Описание пока не сгенерировано. Нажмите Regenerate."
        self.tabs.overview_tab.update_project_info(self.current_repo.title, len(tracked_files), loc, summary)
        self.tabs.overview_tab.update_metrics(self._calculate_quality_metrics(repo_path, loc))
        self.tabs.overview_tab.load_readme(repo_path)

    def _count_python_loc(self, repo_path: Path, tracked_files: list[str] | None = None) -> int:
        loc = 0
        files = tracked_files if tracked_files is not None else self.git_backend.list_tracked_files(repo_path)
        for file in files:
            if not file.endswith(".py"):
                continue
            content = self.git_backend.read_working_tree_file(repo_path, file)
            loc += len(content.splitlines())
        return loc

    def _calculate_quality_metrics(self, repo_path: Path, loc: int) -> dict[str, tuple[str, str, str]]:
        thresholds = self.state_store.quality_thresholds()
        kloc = max(loc / 1000.0, 0.001)

        metrics: dict[str, tuple[str, str, str]] = {}

        ruff_issues = RuffRunner().run(repo_path)
        lint_count = len([issue for issue in ruff_issues if issue.severity in {"warning", "error"}])
        lint_per_kloc = lint_count / kloc
        lint_thr = thresholds["lint_issues_per_kloc"]
        metrics["lint"] = (
            self._grade_lower_better(lint_per_kloc, lint_thr),
            f"{lint_count} ({lint_per_kloc:.1f}/KLOC)",
            self._fmt_thresholds("<=", lint_thr),
        )

        mypy_issues = MypyRunner().run(repo_path)
        mypy_errors = len([issue for issue in mypy_issues if issue.severity == "error"])
        mypy_per_kloc = mypy_errors / kloc
        mypy_thr = thresholds["mypy_errors_per_kloc"]
        metrics["typing_health"] = (
            self._grade_lower_better(mypy_per_kloc, mypy_thr),
            f"{mypy_errors} ({mypy_per_kloc:.1f}/KLOC)",
            self._fmt_thresholds("<=", mypy_thr),
        )

        tests = PytestRunner().run(repo_path)
        if tests.total > 0:
            failed_rate = (tests.failed / tests.total) * 100.0
            test_thr = thresholds["tests_failed_rate_pct"]
            metrics["tests"] = (
                self._grade_lower_better(failed_rate, test_thr),
                f"{tests.failed}/{tests.total} ({failed_rate:.1f}%)",
                self._fmt_thresholds("<=", test_thr),
            )
        else:
            metrics["tests"] = ("—", "n/a", "нет данных тестов")

        radon_issues = RadonRunner().run(repo_path)
        complexity_ranks = _extract_ranks(radon_issues)
        if complexity_ranks:
            b_plus = sum(1 for rank in complexity_ranks if rank in {"B", "C", "D", "E", "F"})
            share_pct = (b_plus / len(complexity_ranks)) * 100.0
            complexity_thr = thresholds["complexity_b_plus_share_pct"]
            max_complexity = max(_extract_values(radon_issues, r"complexity\s+([0-9]+(?:\.[0-9]+)?)"), default=0.0)
            metrics["complexity"] = (
                self._grade_lower_better(share_pct, complexity_thr),
                f"{share_pct:.1f}% B+ (max {max_complexity:.0f})",
                self._fmt_thresholds("<=", complexity_thr),
            )
        else:
            metrics["complexity"] = ("—", "n/a", "нет данных radon")

        maintainability_values = _extract_values(radon_issues, r"Maintainability index is\s+([0-9]+(?:\.[0-9]+)?)")
        if maintainability_values:
            avg_mi = sum(maintainability_values) / len(maintainability_values)
            mi_thr = thresholds["maintainability_avg_mi"]
            metrics["maintainability"] = (
                self._grade_upper_better(avg_mi, mi_thr),
                f"{avg_mi:.1f}",
                self._fmt_thresholds(">=", mi_thr),
            )
        else:
            metrics["maintainability"] = ("—", "n/a", "нет данных radon")

        dead_code_issues = VultureRunner().run(repo_path)
        dead_code_count = len([issue for issue in dead_code_issues if issue.severity in {"warning", "error"}])
        dead_code_per_kloc = dead_code_count / kloc
        dead_thr = thresholds["dead_code_findings_per_kloc"]
        metrics["dead_code"] = (
            self._grade_lower_better(dead_code_per_kloc, dead_thr),
            f"{dead_code_count} ({dead_code_per_kloc:.1f}/KLOC)",
            self._fmt_thresholds("<=", dead_thr),
        )

        duplication = DuplicationRunner().run(repo_path)
        dup_thr = thresholds["duplication_pct"]
        metrics["duplication"] = (
            self._grade_lower_better(duplication.duplication_pct, dup_thr),
            f"{duplication.duplication_pct:.1f}% ({duplication.duplicate_groups} групп)",
            self._fmt_thresholds("<=", dup_thr),
        )
        metrics["ai_signal"] = self._calculate_ai_signal_metric(repo_path)

        return metrics

    def _calculate_ai_signal_metric(self, repo_path: Path) -> tuple[str, str, str]:
        if not self.current_repo:
            return "—", "n/a", "репозиторий не выбран"
        try:
            result = self._build_ai_authorship_use_case().execute(
                repo_id=self.current_repo.repo_id,
                repo_path=repo_path,
                scope="working_tree",
                use_cache=True,
            )
        except Exception:
            return "—", "n/a", "нет данных AIAuthorship"

        probability_pct = result.probability * 100.0
        if probability_pct < 20:
            grade = "A"
        elif probability_pct < 40:
            grade = "B"
        elif probability_pct < 60:
            grade = "C"
        elif probability_pct < 80:
            grade = "D"
        else:
            grade = "E"
        return grade, f"{probability_pct:.1f}% (conf {result.confidence:.2f})", "ниже — лучше"

    def _build_ai_authorship_use_case(self):
        return DetectAIAuthorshipUseCase(
            git_backend=self.git_backend,
            store=self.store,
            extractor=FeatureExtractor(),
            model_runtime=ModelRuntime(DEFAULT_CONFIG.ai_authorship_model_path),
            calibrator=ProbabilityCalibrator(DEFAULT_CONFIG.ai_authorship_calibration_path),
        )

    @staticmethod
    def _fmt_thresholds(operator: str, values: list[float]) -> str:
        return f"A{operator}{values[0]:g}, B{operator}{values[1]:g}, C{operator}{values[2]:g}, D{operator}{values[3]:g}"

    def _grade_lower_better(self, value: float, thresholds: list[float]) -> str:
        if value <= thresholds[0]:
            return "A"
        if value <= thresholds[1]:
            return "B"
        if value <= thresholds[2]:
            return "C"
        if value <= thresholds[3]:
            return "D"
        return "E"

    def _grade_upper_better(self, value: float, thresholds: list[float]) -> str:
        if value >= thresholds[0]:
            return "A"
        if value >= thresholds[1]:
            return "B"
        if value >= thresholds[2]:
            return "C"
        if value >= thresholds[3]:
            return "D"
        return "E"

    def _regenerate_overview(self) -> None:
        if not self.current_repo:
            return
        repo_path = Path(self.current_repo.working_path)
        backend = ProjectOverviewBackend(DEFAULT_CONFIG.ollama_url, DEFAULT_CONFIG.ollama_model)
        use_case = BuildProjectOverviewUseCase(self.git_backend, backend)
        try:
            overview = use_case.execute(repo_path)
        except Exception as error:  # noqa: BLE001
            QMessageBox.warning(self, "AI overview", str(error))
            return
        self.store.save_project_overview(self.current_repo.repo_id, overview.summary, overview.model_info)
        self.tabs.overview_tab.set_summary_markdown(overview.summary)

    def _refresh_commits(self) -> None:
        if not self.current_repo:
            return
        use_case = ListCommitsUseCase(self.git_backend)
        commits = use_case.execute(Path(self.current_repo.working_path), limit=50)
        self.tabs.commits_tab.set_commits(commits)

    def _refresh_map(self) -> None:
        if not self.current_repo:
            return
        use_case = BuildProjectMapUseCase(self.git_backend, AstMapBuilder(), self.store)
        project_map = use_case.execute(self.current_repo.repo_id, Path(self.current_repo.working_path), use_cache=True)
        self.tabs.project_map_tab.set_project_map(project_map)

    def _refresh_working_tree(self) -> None:
        if not self.current_repo:
            return
        repo_path = Path(self.current_repo.working_path)
        status_lines = self.git_backend.status_porcelain(repo_path)
        file_rows = _parse_status_rows(status_lines)

        use_case = WorkingTreeReportUseCase(
            self.git_backend,
            RuffRunner(),
            PytestRunner(),
            OllamaBackend(DEFAULT_CONFIG.ollama_url, DEFAULT_CONFIG.ollama_model),
            self.store,
        )
        try:
            report = use_case.execute(self.current_repo.repo_id, repo_path, use_cache=True)
        except Exception:  # noqa: BLE001
            report = None
        files_payload = self._build_workspace_files_payload(file_rows, report.issues if report else [], report.tests if report else None)
        diff_by_file = {
            file_row["path"]: self.git_backend.read_working_tree_diff(repo_path, file_row["path"])
            for file_row in file_rows
        }
        self.tabs.workspace_tab.set_workspace_data(files_payload, diff_by_file)
        if not report:
            return
        self.status.showMessage(
            f"Working tree: files={report.metrics.files_changed} +{report.metrics.lines_added} -{report.metrics.lines_deleted}",
            5_000,
        )

    def _build_workspace_files_payload(self, file_rows: list[dict[str, str]], issues: list, tests) -> list[dict[str, object]]:
        lint_by_file: dict[str, int] = {}
        issues_by_file: dict[str, int] = {}
        for issue in issues:
            path = (issue.file or "").replace("\\", "/")
            if not path:
                continue
            issues_by_file[path] = issues_by_file.get(path, 0) + 1
            if issue.tool == "ruff":
                lint_by_file[path] = lint_by_file.get(path, 0) + 1
        failed_tests = tests.failed_tests if tests else []

        payload: list[dict[str, object]] = []
        for item in file_rows:
            path = item["path"]
            test_label = ""
            if failed_tests and any(path in failed for failed in failed_tests):
                test_label = "tests: failed"
            payload.append(
                {
                    "path": path,
                    "status": item["status"],
                    "lint": lint_by_file.get(path, 0),
                    "issues": issues_by_file.get(path, 0),
                    "tests": test_label,
                }
            )
        return payload

    def _stage_workspace_file(self, file_path: str) -> None:
        if not self.current_repo:
            return
        repo_path = Path(self.current_repo.working_path)
        self.git_backend.stage_paths(repo_path, [file_path])
        self.status.showMessage(f"Staged: {file_path}", 4_000)
        self._refresh_current()

    def _open_workspace_file(self, file_path: str) -> None:
        if not self.current_repo:
            return
        absolute_path = Path(self.current_repo.working_path) / file_path
        editor = _detect_editor_command()
        if editor:
            subprocess.Popen([*editor, str(absolute_path)])  # noqa: S603
            self.status.showMessage(f"Opened in editor: {file_path}", 4_000)
            return
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(absolute_path)))
        if opened:
            self.status.showMessage(f"Opened: {file_path}", 4_000)
            return
        self.status.showMessage(f"Не удалось открыть файл: {file_path}", 5_000)


    def _describe_commit_with_ai(self, commit_hash: str) -> None:
        if not self.current_repo:
            return
        repo_path = Path(self.current_repo.working_path)
        diff_text = self.git_backend.read_commit_diff(repo_path, commit_hash)
        backend = OllamaBackend(DEFAULT_CONFIG.ollama_url, DEFAULT_CONFIG.ollama_model)
        result = backend.summarize_diff(diff_text)
        self.tabs.commits_tab.set_commit_summary(commit_hash, result.summary, result.model_info)
        self.status.showMessage(f"Описание коммита обновлено: {commit_hash[:10]}", 5_000)

    def _show_commit_in_status(self, commit_hash: str) -> None:
        self.status.showMessage(f"Selected commit: {commit_hash}", 4_000)


def _snapshot_payload_from_result(result: RepositoryRefreshResult) -> dict:
    return {
        "files_count": result.files_count,
        "loc": result.loc,
        "metrics": {name: list(values) for name, values in result.metrics.items()},
        "commits": [_commit_to_payload(commit) for commit in result.commits],
        "project_map": _project_map_to_payload(result.project_map),
        "workspace_files": result.workspace_files,
        "workspace_diffs": result.workspace_diffs,
        "working_tree_message": result.working_tree_message,
    }


def _repository_result_from_snapshot(
    repo: RepoListItemVM,
    payload: dict,
    store: SqliteStore,
) -> RepositoryRefreshResult:
    cached_overview = store.load_project_overview(repo.repo_id)
    summary = cached_overview[0] if cached_overview else str(payload.get("summary") or "")
    raw_metrics = payload.get("metrics") or {}
    if not isinstance(raw_metrics, dict):
        raw_metrics = {}
    raw_workspace_diffs = payload.get("workspace_diffs") or {}
    if not isinstance(raw_workspace_diffs, dict):
        raw_workspace_diffs = {}
    raw_project_map = payload.get("project_map") or {}
    if not isinstance(raw_project_map, dict):
        raw_project_map = {}
    metrics = {
        str(name): _metric_tuple(values)
        for name, values in raw_metrics.items()
    }
    commits = [
        _commit_from_payload(item)
        for item in (payload.get("commits") or [])
        if isinstance(item, dict)
    ]
    workspace_files = [
        dict(item)
        for item in (payload.get("workspace_files") or [])
        if isinstance(item, dict)
    ]
    workspace_diffs = {
        str(path): str(diff)
        for path, diff in raw_workspace_diffs.items()
    }
    return RepositoryRefreshResult(
        repo_id=repo.repo_id,
        repo_path=Path(repo.working_path),
        data_refresh_message=None,
        files_count=_coerce_int(payload.get("files_count")),
        loc=_coerce_int(payload.get("loc")),
        summary=summary,
        metrics=metrics,
        commits=commits,
        project_map=_project_map_from_payload(raw_project_map),
        workspace_files=workspace_files,
        workspace_diffs=workspace_diffs,
        working_tree_message=None,
    )


def _commit_to_payload(commit: Commit) -> dict[str, object]:
    return {
        "hash": commit.hash,
        "author": commit.author,
        "authored_at": commit.authored_at.isoformat(),
        "message": commit.message,
        "parents": list(commit.parents),
    }


def _commit_from_payload(payload: dict) -> Commit:
    authored_at_raw = str(payload.get("authored_at") or "")
    try:
        authored_at = datetime.fromisoformat(authored_at_raw)
    except ValueError:
        authored_at = datetime.now().astimezone()
    parents_raw = payload.get("parents") or []
    if isinstance(parents_raw, str):
        parents_raw = parents_raw.split()
    elif not isinstance(parents_raw, (list, tuple, set)):
        parents_raw = []
    return Commit(
        hash=str(payload.get("hash") or ""),
        author=str(payload.get("author") or ""),
        authored_at=authored_at,
        message=str(payload.get("message") or ""),
        parents=tuple(str(parent) for parent in parents_raw),
    )


def _project_map_to_payload(project_map: object) -> dict[str, list[dict[str, object]]]:
    nodes = getattr(project_map, "nodes", []) or []
    edges = getattr(project_map, "edges", []) or []
    return {
        "nodes": [
            {
                "node_id": node.node_id,
                "kind": node.kind,
                "label": node.label,
                "path": node.path,
                "hotspot_score": node.hotspot_score,
            }
            for node in nodes
        ],
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "relation": edge.relation,
            }
            for edge in edges
        ],
    }


def _project_map_from_payload(payload: dict) -> ProjectGraph:
    nodes: list[GraphNode] = []
    for item in payload.get("nodes") or []:
        if not isinstance(item, dict):
            continue
        nodes.append(
            GraphNode(
                node_id=str(item.get("node_id") or item.get("id") or ""),
                kind=str(item.get("kind") or ""),
                label=str(item.get("label") or ""),
                path=str(item.get("path") or ""),
                hotspot_score=_coerce_int(item.get("hotspot_score", item.get("hotspot"))),
            )
        )

    edges: list[GraphEdge] = []
    for item in payload.get("edges") or []:
        if not isinstance(item, dict):
            continue
        edges.append(
            GraphEdge(
                source=str(item.get("source") or ""),
                target=str(item.get("target") or ""),
                relation=str(item.get("relation") or ""),
            )
        )
    return ProjectGraph(nodes=nodes, edges=edges)


def _metric_tuple(values: object) -> tuple[str, str, str]:
    if isinstance(values, (list, tuple)):
        items = list(values)
    else:
        items = []
    grade = str(items[0]) if len(items) > 0 else "-"
    value = str(items[1]) if len(items) > 1 else "-"
    threshold = str(items[2]) if len(items) > 2 else ""
    return grade, value, threshold


def _coerce_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def run_desktop_app() -> None:
    app = QApplication(sys.argv)
    apply_theme(app)
    store = SqliteStore(DEFAULT_CONFIG.db_path)
    window = MainWindow(store, GitBackend())
    window.show()
    app.exec()


def _extract_values(issues: list, pattern: str) -> list[float]:
    compiled = re.compile(pattern)
    values: list[float] = []
    for issue in issues:
        match = compiled.search(issue.message)
        if not match:
            continue
        try:
            values.append(float(match.group(1)))
        except ValueError:
            continue
    return values


def _extract_ranks(issues: list) -> list[str]:
    compiled = re.compile(r"\(rank\s+([A-F])\)")
    ranks: list[str] = []
    for issue in issues:
        match = compiled.search(issue.message)
        if match:
            ranks.append(match.group(1))
    return ranks


def _parse_status_rows(status_lines: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in status_lines:
        if len(line) < 3:
            continue
        status = ""
        raw_path = ""
        # Expected porcelain line: XY<space>path.
        # GitBackend._git() strips surrounding whitespace for the whole output,
        # so the very first line can lose its leading space and become X<space>path.
        if len(line) >= 3 and line[2] == " ":
            status = line[:2].strip() or "??"
            raw_path = line[3:]
        elif len(line) >= 2 and line[1] == " ":
            status = line[0].strip() or "??"
            raw_path = line[2:]
        else:
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            status = parts[0].strip() or "??"
            raw_path = parts[1]
        path = raw_path.split(" -> ", 1)[-1].strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        if not path:
            continue
        rows.append({"status": status, "path": path})
    return rows


def _count_python_loc(git_backend: GitBackend, repo_path: Path, tracked_files: list[str] | None = None) -> int:
    loc = 0
    files = tracked_files if tracked_files is not None else git_backend.list_tracked_files(repo_path)
    for file in files:
        if not file.endswith(".py"):
            continue
        content = git_backend.read_working_tree_file(repo_path, file)
        loc += len(content.splitlines())
    return loc


def _calculate_quality_metrics(
    repo_id: int,
    repo_path: Path,
    loc: int,
    thresholds: dict[str, list[float]],
    git_backend: GitBackend,
    store: SqliteStore,
    use_cache: bool = True,
) -> dict[str, tuple[str, str, str]]:
    kloc = max(loc / 1000.0, 0.001)
    metrics: dict[str, tuple[str, str, str]] = {}

    ruff_issues = RuffRunner().run(repo_path)
    lint_count = len([issue for issue in ruff_issues if issue.severity in {"warning", "error"}])
    lint_per_kloc = lint_count / kloc
    lint_thr = thresholds["lint_issues_per_kloc"]
    metrics["lint"] = (
        _grade_lower_better(lint_per_kloc, lint_thr),
        f"{lint_count} ({lint_per_kloc:.1f}/KLOC)",
        _fmt_thresholds("<=", lint_thr),
    )

    mypy_issues = MypyRunner().run(repo_path)
    mypy_errors = len([issue for issue in mypy_issues if issue.severity == "error"])
    mypy_per_kloc = mypy_errors / kloc
    mypy_thr = thresholds["mypy_errors_per_kloc"]
    metrics["typing_health"] = (
        _grade_lower_better(mypy_per_kloc, mypy_thr),
        f"{mypy_errors} ({mypy_per_kloc:.1f}/KLOC)",
        _fmt_thresholds("<=", mypy_thr),
    )

    tests = PytestRunner().run(repo_path)
    if tests.total > 0:
        failed_rate = (tests.failed / tests.total) * 100.0
        test_thr = thresholds["tests_failed_rate_pct"]
        metrics["tests"] = (
            _grade_lower_better(failed_rate, test_thr),
            f"{tests.failed}/{tests.total} ({failed_rate:.1f}%)",
            _fmt_thresholds("<=", test_thr),
        )
    else:
        metrics["tests"] = ("—", "n/a", "нет данных тестов")

    radon_issues = RadonRunner().run(repo_path)
    complexity_ranks = _extract_ranks(radon_issues)
    if complexity_ranks:
        b_plus = sum(1 for rank in complexity_ranks if rank in {"B", "C", "D", "E", "F"})
        share_pct = (b_plus / len(complexity_ranks)) * 100.0
        complexity_thr = thresholds["complexity_b_plus_share_pct"]
        max_complexity = max(_extract_values(radon_issues, r"complexity\s+([0-9]+(?:\.[0-9]+)?)"), default=0.0)
        metrics["complexity"] = (
            _grade_lower_better(share_pct, complexity_thr),
            f"{share_pct:.1f}% B+ (max {max_complexity:.0f})",
            _fmt_thresholds("<=", complexity_thr),
        )
    else:
        metrics["complexity"] = ("—", "n/a", "нет данных radon")

    maintainability_values = _extract_values(radon_issues, r"Maintainability index is\s+([0-9]+(?:\.[0-9]+)?)")
    if maintainability_values:
        avg_mi = sum(maintainability_values) / len(maintainability_values)
        mi_thr = thresholds["maintainability_avg_mi"]
        metrics["maintainability"] = (
            _grade_upper_better(avg_mi, mi_thr),
            f"{avg_mi:.1f}",
            _fmt_thresholds(">=", mi_thr),
        )
    else:
        metrics["maintainability"] = ("—", "n/a", "нет данных radon")

    dead_code_issues = VultureRunner().run(repo_path)
    dead_code_count = len([issue for issue in dead_code_issues if issue.severity in {"warning", "error"}])
    dead_code_per_kloc = dead_code_count / kloc
    dead_thr = thresholds["dead_code_findings_per_kloc"]
    metrics["dead_code"] = (
        _grade_lower_better(dead_code_per_kloc, dead_thr),
        f"{dead_code_count} ({dead_code_per_kloc:.1f}/KLOC)",
        _fmt_thresholds("<=", dead_thr),
    )

    duplication = DuplicationRunner().run(repo_path)
    dup_thr = thresholds["duplication_pct"]
    metrics["duplication"] = (
        _grade_lower_better(duplication.duplication_pct, dup_thr),
        f"{duplication.duplication_pct:.1f}% ({duplication.duplicate_groups} групп)",
        _fmt_thresholds("<=", dup_thr),
    )
    metrics["ai_signal"] = _calculate_ai_signal_metric(repo_id, repo_path, git_backend, store, use_cache=use_cache)

    return metrics


def _calculate_ai_signal_metric(
    repo_id: int,
    repo_path: Path,
    git_backend: GitBackend,
    store: SqliteStore,
    use_cache: bool = True,
) -> tuple[str, str, str]:
    try:
        result = _build_ai_authorship_use_case(git_backend, store).execute(
            repo_id=repo_id,
            repo_path=repo_path,
            scope="working_tree",
            use_cache=use_cache,
        )
    except Exception:
        return "—", "n/a", "нет данных AIAuthorship"

    probability_pct = result.probability * 100.0
    if probability_pct < 20:
        grade = "A"
    elif probability_pct < 40:
        grade = "B"
    elif probability_pct < 60:
        grade = "C"
    elif probability_pct < 80:
        grade = "D"
    else:
        grade = "E"
    return grade, f"{probability_pct:.1f}% (conf {result.confidence:.2f})", "ниже — лучше"


def _build_ai_authorship_use_case(git_backend: GitBackend, store: SqliteStore) -> DetectAIAuthorshipUseCase:
    return DetectAIAuthorshipUseCase(
        git_backend=git_backend,
        store=store,
        extractor=FeatureExtractor(),
        model_runtime=ModelRuntime(DEFAULT_CONFIG.ai_authorship_model_path),
        calibrator=ProbabilityCalibrator(DEFAULT_CONFIG.ai_authorship_calibration_path),
    )


def _build_workspace_files_payload(file_rows: list[dict[str, str]], issues: list, tests) -> list[dict[str, object]]:
    lint_by_file: dict[str, int] = {}
    issues_by_file: dict[str, int] = {}
    for issue in issues:
        path = (issue.file or "").replace("\\", "/")
        if not path:
            continue
        issues_by_file[path] = issues_by_file.get(path, 0) + 1
        if issue.tool == "ruff":
            lint_by_file[path] = lint_by_file.get(path, 0) + 1
    failed_tests = tests.failed_tests if tests else []

    payload: list[dict[str, object]] = []
    for item in file_rows:
        path = item["path"]
        test_label = ""
        if failed_tests and any(path in failed for failed in failed_tests):
            test_label = "tests: failed"
        payload.append(
            {
                "path": path,
                "status": item["status"],
                "lint": lint_by_file.get(path, 0),
                "issues": issues_by_file.get(path, 0),
                "tests": test_label,
            }
        )
    return payload


def _fmt_thresholds(operator: str, values: list[float]) -> str:
    return f"A{operator}{values[0]:g}, B{operator}{values[1]:g}, C{operator}{values[2]:g}, D{operator}{values[3]:g}"


def _grade_lower_better(value: float, thresholds: list[float]) -> str:
    if value <= thresholds[0]:
        return "A"
    if value <= thresholds[1]:
        return "B"
    if value <= thresholds[2]:
        return "C"
    if value <= thresholds[3]:
        return "D"
    return "E"


def _grade_upper_better(value: float, thresholds: list[float]) -> str:
    if value >= thresholds[0]:
        return "A"
    if value >= thresholds[1]:
        return "B"
    if value >= thresholds[2]:
        return "C"
    if value >= thresholds[3]:
        return "D"
    return "E"


def _detect_editor_command() -> list[str] | None:
    env_value = os.environ.get("ANALYZEAPP_EDITOR") or os.environ.get("EDITOR")
    if env_value:
        parts = shlex.split(env_value)
        if parts:
            return parts
    for candidate in ("code", "zed", "subl", "nvim", "vim"):
        if shutil.which(candidate):
            return [candidate]
    return None
