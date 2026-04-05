from __future__ import annotations

from pathlib import Path

from analyze_app.infrastructure.git.backend import GitBackend
from analyze_app.infrastructure.storage.sqlite_store import SqliteStore


class ImportRepositoryUseCase:
    def __init__(self, git_backend: GitBackend, store: SqliteStore, clone_root: Path) -> None:
        self.git_backend = git_backend
        self.store = store
        self.clone_root = clone_root

    def execute(self, source: str) -> tuple[int, Path]:
        repo_path = self.git_backend.clone_or_open(source, self.clone_root)
        repo_id = self.store.add_repository(source, str(repo_path))
        return repo_id, repo_path
