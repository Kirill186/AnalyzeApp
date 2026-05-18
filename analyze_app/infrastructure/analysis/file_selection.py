from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


IGNORED_PATH_PARTS = {
    ".eggs",
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "site-packages",
    "target",
    "venv",
}


def normalize_rel_path(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip("/")


def is_ignored_path_parts(parts: Iterable[str]) -> bool:
    return any(part.startswith(".") or part in IGNORED_PATH_PARTS for part in parts if part)


def is_ignored_rel_path(path: str | Path) -> bool:
    normalized = normalize_rel_path(path)
    return is_ignored_path_parts(normalized.split("/"))


def select_python_files(repo_path: Path, tracked_files: list[str] | None = None) -> list[str]:
    if tracked_files is not None:
        candidates = [normalize_rel_path(path) for path in tracked_files]
    else:
        candidates = []
        for py_file in repo_path.rglob("*.py"):
            try:
                candidates.append(normalize_rel_path(py_file.relative_to(repo_path)))
            except ValueError:
                continue

    selected: list[str] = []
    for rel_path in candidates:
        if not rel_path.endswith(".py") or is_ignored_rel_path(rel_path):
            continue
        if not repo_path.joinpath(*rel_path.split("/")).is_file():
            continue
        selected.append(rel_path)
    return sorted(set(selected))
