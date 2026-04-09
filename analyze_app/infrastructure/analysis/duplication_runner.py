from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from analyze_app.domain.entities import DuplicationResult


class DuplicationRunner:
    """Simple line-based duplicate detector for Python files."""

    def __init__(self, min_lines: int = 6) -> None:
        self.min_lines = min_lines

    def run(self, repo_path: Path) -> DuplicationResult:
        files = [path for path in repo_path.rglob("*.py") if ".git" not in path.parts]
        normalized_by_file: dict[Path, list[str]] = {}
        total_loc = 0

        for file_path in files:
            try:
                raw_lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            cleaned = [line.strip() for line in raw_lines if line.strip() and not line.strip().startswith("#")]
            normalized_by_file[file_path] = cleaned
            total_loc += len(cleaned)

        if total_loc == 0:
            return DuplicationResult(duplicate_groups=0, duplicate_fragments=0, duplicated_lines=0, duplication_pct=0.0)

        windows: dict[tuple[str, ...], list[tuple[Path, int]]] = defaultdict(list)
        for file_path, lines in normalized_by_file.items():
            if len(lines) < self.min_lines:
                continue
            for start in range(0, len(lines) - self.min_lines + 1):
                window = tuple(lines[start : start + self.min_lines])
                windows[window].append((file_path, start))

        duplicate_groups = 0
        duplicate_fragments = 0
        duplicated_lines = 0
        for occurrences in windows.values():
            if len(occurrences) <= 1:
                continue
            unique_occurrences = {(str(path), line) for path, line in occurrences}
            if len(unique_occurrences) <= 1:
                continue
            duplicate_groups += 1
            duplicate_fragments += len(unique_occurrences)
            duplicated_lines += self.min_lines * (len(unique_occurrences) - 1)

        duplication_pct = min(100.0, (duplicated_lines / total_loc) * 100.0)
        return DuplicationResult(
            duplicate_groups=duplicate_groups,
            duplicate_fragments=duplicate_fragments,
            duplicated_lines=duplicated_lines,
            duplication_pct=duplication_pct,
        )
