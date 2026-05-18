from __future__ import annotations

import os
from pathlib import Path

from analyze_app.infrastructure.analysis.file_selection import is_ignored_path_parts


_README_SUFFIX_ORDER = {".md": 0, ".markdown": 1, ".rst": 2, ".txt": 3, "": 4}


def find_readme_candidates(repo_path: Path) -> list[Path]:
    if not repo_path.exists() or not repo_path.is_dir():
        return []

    root_files = [item for item in repo_path.iterdir() if _is_readme(item)]
    if root_files:
        root_files.sort(key=_readme_sort_key)
        return root_files

    nested_candidates: list[Path] = []
    for root, dirnames, filenames in os.walk(repo_path):
        root_path = Path(root)
        try:
            rel_parts = () if root_path == repo_path else root_path.relative_to(repo_path).parts
        except ValueError:
            continue

        dirnames[:] = [
            dirname for dirname in dirnames if not is_ignored_path_parts((*rel_parts, dirname))
        ]

        for filename in filenames:
            path = root_path / filename
            if not _is_readme(path):
                continue
            try:
                depth = len(path.relative_to(repo_path).parts)
            except ValueError:
                continue
            if depth <= 3:
                nested_candidates.append(path)

    nested_candidates.sort(
        key=lambda path: (
            len(path.relative_to(repo_path).parts),
            _readme_sort_key(path),
            str(path).lower(),
        )
    )
    return nested_candidates


def _is_readme(path: Path) -> bool:
    return path.is_file() and path.name.lower().startswith("readme")


def _readme_sort_key(path: Path) -> int:
    return _README_SUFFIX_ORDER.get(path.suffix.lower(), 9)
