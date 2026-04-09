from __future__ import annotations

from pathlib import Path

from analyze_app.domain.entities import ProjectOverviewResult
from analyze_app.infrastructure.ai.project_overview_backend import ProjectOverviewBackend
from analyze_app.infrastructure.git.backend import GitBackend


class BuildProjectOverviewUseCase:
    def __init__(self, git_backend: GitBackend, ai_backend: ProjectOverviewBackend) -> None:
        self.git_backend = git_backend
        self.ai_backend = ai_backend

    def execute(self, repo_path: Path, max_files: int = 120) -> ProjectOverviewResult:
        files = self._collect_repo_files(repo_path, max_files=max_files)
        architecture_excerpt = self._read_text_file(repo_path / "docs/architecture_v2_ru.md", max_chars=5000)
        readme_excerpt = self._read_text_file(repo_path / "README.md", max_chars=4000)

        context = (
            f"Repository path: {repo_path}\n\n"
            "Top-level and tracked files:\n"
            f"{files}\n\n"
            "Architecture excerpt:\n"
            f"{architecture_excerpt}\n\n"
            "README excerpt:\n"
            f"{readme_excerpt}\n"
        )
        return self.ai_backend.summarize_project(context)

    def _collect_repo_files(self, repo_path: Path, max_files: int) -> str:
        tracked = self.git_backend.list_tracked_files(repo_path)
        selected = tracked[:max_files]
        if len(tracked) > max_files:
            selected.append(f"... and {len(tracked) - max_files} more files")
        return "\n".join(selected)

    @staticmethod
    def _read_text_file(path: Path, max_chars: int) -> str:
        if not path.exists() or not path.is_file():
            return "(missing)"
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
