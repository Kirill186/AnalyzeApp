from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from analyze_app.domain.entities import Commit, FileChange
from analyze_app.shared.process import decode_output


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
        return self._parse_numstat(output)

    def read_working_tree_diff(self, repo_path: Path) -> str:
        return self._git(["diff", "HEAD"], repo_path)

    def read_working_tree_file_changes(self, repo_path: Path) -> list[FileChange]:
        output = self._git(["diff", "--numstat", "HEAD"], repo_path)
        return self._parse_numstat(output)

    def status_porcelain(self, repo_path: Path) -> list[str]:
        output = self._git(["status", "--porcelain"], repo_path)
        return [line for line in output.splitlines() if line.strip()]

    def stage_paths(self, repo_path: Path, paths: list[str] | None = None) -> None:
        if paths:
            self._git(["add", *paths], repo_path)
            return
        self._git(["add", "-A"], repo_path)

    def commit(self, repo_path: Path, message: str) -> str:
        self._git(["commit", "-m", message], repo_path)
        return self._git(["rev-parse", "HEAD"], repo_path)

    def push_current_branch(self, repo_path: Path) -> None:
        self._git(["push"], repo_path)

    def file_churn(self, repo_path: Path, max_commits: int = 200) -> dict[str, int]:
        output = self._git(["log", f"--max-count={max_commits}", "--numstat", "--format="], repo_path)
        churn: dict[str, int] = {}
        for change in self._parse_numstat(output):
            churn[change.path] = churn.get(change.path, 0) + change.additions + change.deletions
        return churn

    def _parse_numstat(self, output: str) -> list[FileChange]:
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
        completed = subprocess.run(command, cwd=cwd, text=False, capture_output=True)
        stdout = decode_output(completed.stdout)
        stderr = decode_output(completed.stderr)
        if completed.returncode != 0:
            raise subprocess.CalledProcessError(completed.returncode, command, output=stdout, stderr=stderr)
        return stdout.strip()
