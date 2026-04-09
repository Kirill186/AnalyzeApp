from __future__ import annotations

from pathlib import Path

from analyze_app.domain.entities import ProjectGraph
from analyze_app.infrastructure.analysis.map.ast_map_builder import AstMapBuilder
from analyze_app.infrastructure.git.backend import GitBackend
from analyze_app.infrastructure.storage.sqlite_store import SqliteStore


class BuildProjectMapUseCase:
    def __init__(self, git_backend: GitBackend, map_builder: AstMapBuilder, store: SqliteStore) -> None:
        self.git_backend = git_backend
        self.map_builder = map_builder
        self.store = store

    def execute(self, repo_id: int, repo_path: Path, max_commits: int = 200, use_cache: bool = True) -> ProjectGraph:
        if use_cache:
            cached = self.store.load_project_map(repo_id)
            if cached:
                return cached

        churn = self.git_backend.file_churn(repo_path, max_commits=max_commits)
        project_map = self.map_builder.build(repo_path, churn=churn)
        self.store.save_project_map(repo_id, project_map)
        return project_map
