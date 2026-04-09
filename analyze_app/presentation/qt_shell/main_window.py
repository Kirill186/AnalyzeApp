from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
)

from analyze_app.application.use_cases.build_project_map import BuildProjectMapUseCase
from analyze_app.application.use_cases.build_project_overview import BuildProjectOverviewUseCase
from analyze_app.application.use_cases.get_working_tree_report import WorkingTreeReportUseCase
from analyze_app.application.use_cases.import_repository import ImportRepositoryUseCase
from analyze_app.application.use_cases.list_commits import ListCommitsUseCase
from analyze_app.infrastructure.ai.ollama_backend import OllamaBackend
from analyze_app.infrastructure.ai.project_overview_backend import ProjectOverviewBackend
from analyze_app.infrastructure.analysis.map.ast_map_builder import AstMapBuilder
from analyze_app.infrastructure.analysis.pytest_runner import PytestRunner
from analyze_app.infrastructure.analysis.ruff_runner import RuffRunner
from analyze_app.infrastructure.git.backend import GitBackend
from analyze_app.infrastructure.storage.sqlite_store import SqliteStore
from analyze_app.presentation.qt_shell.app_menu import build_menu
from analyze_app.presentation.qt_shell.repo_add_dialog import RepoAddDialog
from analyze_app.presentation.qt_shell.repo_sidebar import RepoSidebar
from analyze_app.presentation.qt_shell.report_tabs import ReportTabs
from analyze_app.presentation.qt_shell.state_store import RepoListItemVM, UiStateStore
from analyze_app.presentation.qt_shell.theme import apply_theme
from analyze_app.shared.config import DEFAULT_CONFIG


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
        self.sidebar.refresh_all_clicked.connect(self._load_repositories)
        self.sidebar.repo_selected.connect(self._on_repo_selected)

        self.menu.add_repository.triggered.connect(self._add_repository)
        self.menu.refresh_all.triggered.connect(self._load_repositories)
        self.menu.refresh_current.triggered.connect(self._refresh_current)
        self.menu.rebuild_map.triggered.connect(self._refresh_map)
        self.menu.run_working_tree.triggered.connect(self._refresh_working_tree)
        self.menu.run_commit.triggered.connect(self._refresh_commits)
        self.menu.toggle_sidebar.triggered.connect(lambda: self.sidebar.setVisible(not self.sidebar.isVisible()))

        self.tabs.commits_tab.commit_selected.connect(self._show_commit_in_status)

    def _bind_tab_actions(self) -> None:
        self.tabs.overview_tab.regenerate_requested.connect(self._regenerate_overview)

    def _load_repositories(self) -> None:
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
        self.sidebar.set_repositories(items)

    def _add_repository(self) -> None:
        dialog = RepoAddDialog(self)
        if dialog.exec() != dialog.Accepted:
            return
        use_case = ImportRepositoryUseCase(self.git_backend, self.store, DEFAULT_CONFIG.clone_root)
        try:
            repo_id, repo_path = use_case.execute(dialog.source)
        except (subprocess.CalledProcessError, ValueError) as error:
            QMessageBox.critical(self, "Import failed", str(error))
            return
        self.status.showMessage(f"Repository imported: {repo_path} (id={repo_id})", 5_000)
        self._load_repositories()

    def _on_repo_selected(self, repo_id: int) -> None:
        repos = [repo for repo in self._current_repo_items() if repo.repo_id == repo_id]
        if not repos:
            return
        self.current_repo = repos[0]
        self._refresh_current()

    def _current_repo_items(self) -> list[RepoListItemVM]:
        items: list[RepoListItemVM] = []
        favorites = self.state_store.favorites()
        for repo_id, origin_url, working_path, default_branch, created_at in self.store.list_repositories():
            source_type = "remote" if origin_url.startswith("http") or origin_url.endswith(".git") else "local"
            items.append(
                RepoListItemVM(
                    repo_id=repo_id,
                    title=Path(working_path).name or origin_url,
                    source_type=source_type,
                    group=source_type,
                    is_favorite=repo_id in favorites,
                    last_updated_at=datetime.fromisoformat(created_at) if created_at else None,
                    default_branch=default_branch,
                    health_grade=None,
                    working_path=working_path,
                    origin_url=origin_url,
                )
            )
        return items

    def _refresh_current(self) -> None:
        if not self.current_repo:
            self.status.showMessage("Выберите репозиторий в левой панели.", 4_000)
            return
        self._refresh_overview()
        self._refresh_commits()
        self._refresh_map()
        self._refresh_working_tree()

    def _refresh_overview(self) -> None:
        if not self.current_repo:
            return
        repo_path = Path(self.current_repo.working_path)
        tracked_files = self.git_backend.list_tracked_files(repo_path)
        loc = 0
        for file in tracked_files:
            if not file.endswith(".py"):
                continue
            content = self.git_backend.read_working_tree_file(repo_path, file)
            loc += len(content.splitlines())

        summary = "Описание пока не сгенерировано. Нажмите Regenerate."
        self.tabs.overview_tab.update_project_info(self.current_repo.title, len(tracked_files), loc, summary)
        self.tabs.overview_tab.update_metrics({})
        self.tabs.overview_tab.load_readme(repo_path)

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
        self.tabs.overview_tab.overview_text.setMarkdown(overview.summary)

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
        self.tabs.workspace_tab.set_files(status_lines)
        self.tabs.workspace_tab.set_diff(self.git_backend.read_working_tree_diff(repo_path))

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
            return
        self.status.showMessage(
            f"Working tree: files={report.metrics.files_changed} +{report.metrics.lines_added} -{report.metrics.lines_deleted}",
            5_000,
        )

    def _show_commit_in_status(self, commit_hash: str) -> None:
        self.status.showMessage(f"Selected commit: {commit_hash}", 4_000)


def run_desktop_app() -> None:
    app = QApplication(sys.argv)
    apply_theme(app)
    store = SqliteStore(DEFAULT_CONFIG.db_path)
    window = MainWindow(store, GitBackend())
    window.show()
    app.exec()
