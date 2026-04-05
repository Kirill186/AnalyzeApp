from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from analyze_app.domain.entities import Commit, FileChange


class GitBackend:
    def clone_or_open(self, source: str, clone_root: Path) -> Path:
        clone_root.mkdir(parents=True, exist_ok=True)
        if source.startswith("http://") or source.startswith("https://") or source.endswith(".git"):
            repo_name = Path(source.rstrip("/").rsplit("/", 1)[-1]).stem
            destination = clone_root / repo_name
            if destination.exists():
                self._git(["fetch", "--all"], destination)
            else:
                self._git(["clone", source, str(destination)], clone_root.parent)
            return destination
        return Path(source).resolve()

    def list_commits(self, repo_path: Path, limit: int = 20) -> list[Commit]:
        fmt = "%H|%an|%aI|%s"
        output = self._git(["log", f"--max-count={limit}", f"--pretty=format:{fmt}"], repo_path)
        commits: list[Commit] = []
        for row in output.splitlines():
            commit_hash, author, authored_at, message = row.split("|", 3)
            commits.append(
                Commit(
                    hash=commit_hash,
                    author=author,
                    authored_at=datetime.fromisoformat(authored_at.replace("Z", "+00:00")),
                    message=message,
                )
            )
        return commits

    def read_commit_diff(self, repo_path: Path, commit_hash: str) -> str:
        return self._git(["show", "--format=", commit_hash], repo_path)

    def read_commit_file_changes(self, repo_path: Path, commit_hash: str) -> list[FileChange]:
        output = self._git(["show", "--numstat", "--format=", commit_hash], repo_path)
        changes: list[FileChange] = []
        for row in output.splitlines():
            parts = row.split("\t")
            if len(parts) != 3:
                continue
            add_raw, del_raw, path = parts
            additions = int(add_raw) if add_raw.isdigit() else 0
            deletions = int(del_raw) if del_raw.isdigit() else 0
            changes.append(FileChange(path=path, additions=additions, deletions=deletions))
        return changes

    def _git(self, args: list[str], cwd: Path) -> str:
        command = ["git", *args]
        completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=True)
        return completed.stdout.strip()
