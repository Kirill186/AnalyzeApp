from __future__ import annotations

from pathlib import Path

from analyze_app.domain.entities import Commit
from analyze_app.infrastructure.git.backend import GitBackend


class ListCommitsUseCase:
    def __init__(self, git_backend: GitBackend) -> None:
        self.git_backend = git_backend

    def execute(self, repo_path: Path, limit: int = 20) -> list[Commit]:
        return self.git_backend.list_commits(repo_path, limit=limit)
