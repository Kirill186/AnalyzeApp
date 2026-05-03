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
        fmt = "%H|%P|%an|%aI|%s"
        output = self._git(["log", f"--max-count={limit}", f"--pretty=format:{fmt}"], repo_path)
        commits: list[Commit] = []
        for row in output.splitlines():
            commit_hash, parents_raw, author, authored_at, message = row.split("|", 4)
            parents = tuple(parent for parent in parents_raw.split() if parent)
            commits.append(
                Commit(
                    hash=commit_hash,
                    author=author,
                    authored_at=datetime.fromisoformat(authored_at.replace("Z", "+00:00")),
                    message=message,
                    parents=parents,
                )
            )
        return commits

    def last_commit_at(self, repo_path: Path) -> datetime | None:
        try:
            output = self._git(["log", "-1", "--format=%cI"], repo_path)
        except subprocess.CalledProcessError:
            return None
        if not output:
            return None
        try:
            return datetime.fromisoformat(output.replace("Z", "+00:00"))
        except ValueError:
            return None

    def checkout(self, repo_path: Path, ref: str) -> None:
        self._git(["checkout", ref], repo_path)

    def read_commit_diff(self, repo_path: Path, commit_hash: str) -> str:
        return self._git(["show", "--format=", commit_hash], repo_path)

    def read_commit_file_changes(self, repo_path: Path, commit_hash: str) -> list[FileChange]:
        output = self._git(["show", "--numstat", "--format=", commit_hash], repo_path)
        return self._parse_numstat(output)

    def read_working_tree_diff(self, repo_path: Path, file_path: str | None = None) -> str:
        args = ["diff", "HEAD"]
        if file_path:
            args.extend(["--", file_path])
        return self._git(args, repo_path)

    def read_working_tree_file_changes(self, repo_path: Path) -> list[FileChange]:
        output = self._git(["diff", "--numstat", "HEAD"], repo_path)
        return self._parse_numstat(output)

    def status_porcelain(self, repo_path: Path) -> list[str]:
        output = self._git(["status", "--porcelain"], repo_path)
        return [line for line in output.splitlines() if line.strip()]

    def list_tracked_files(self, repo_path: Path) -> list[str]:
        output = self._git(["ls-files"], repo_path)
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

    def refresh_remote_data(self, repo_path: Path) -> str | None:
        try:
            remotes = [line for line in self._git(["remote"], repo_path).splitlines() if line.strip()]
        except subprocess.CalledProcessError:
            return None
        if not remotes:
            return None

        try:
            self._git(["fetch", "--all", "--prune"], repo_path)
        except subprocess.CalledProcessError as error:
            return f"Fetch failed: {_format_git_error(error)}"

        if self.status_porcelain(repo_path):
            return "Fetched latest remote data; local changes left untouched."

        branch = self._git(["branch", "--show-current"], repo_path)
        if not branch:
            return "Fetched latest remote data."

        try:
            self._git(["pull", "--ff-only"], repo_path)
        except subprocess.CalledProcessError as error:
            return f"Fetched latest remote data; fast-forward skipped: {_format_git_error(error)}"
        return "Fetched latest remote data and fast-forwarded current branch."



    def read_file_at_commit(self, repo_path: Path, commit_hash: str, file_path: str) -> str:
        try:
            return self._git(["show", f"{commit_hash}:{file_path}"], repo_path)
        except subprocess.CalledProcessError:
            return ""

    def read_working_tree_file(self, repo_path: Path, file_path: str) -> str:
        path = repo_path / file_path
        if not path.exists() or not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="ignore")

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


def _format_git_error(error: subprocess.CalledProcessError) -> str:
    message = (error.stderr or error.output or "").strip()
    if not message:
        return f"git exited with code {error.returncode}"
    return message.splitlines()[-1]
