from __future__ import annotations

from pathlib import Path

from analyze_app.infrastructure.git.backend import GitBackend


class CommitAndPushUseCase:
    def __init__(self, git_backend: GitBackend) -> None:
        self.git_backend = git_backend

    def execute(self, repo_path: Path, message: str, push: bool = True, paths: list[str] | None = None) -> str:
        self.git_backend.stage_paths(repo_path, paths=paths)
        commit_hash = self.git_backend.commit(repo_path, message)
        if push:
            self.git_backend.push_current_branch(repo_path)
        return commit_hash
