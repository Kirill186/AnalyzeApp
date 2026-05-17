from __future__ import annotations

import ast
from pathlib import Path

from analyze_app.domain.entities import GraphEdge, GraphNode, ProjectGraph


MAP_FILE_EXTENSIONS = {
    ".bat",
    ".c",
    ".cmd",
    ".cpp",
    ".cs",
    ".css",
    ".dart",
    ".go",
    ".gradle",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".md",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".scss",
    ".sh",
    ".svelte",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}
MAP_FILE_NAMES = {
    "Dockerfile",
    "Makefile",
    "README",
    "README.md",
    "compose.yaml",
    "docker-compose.yml",
}
IGNORED_PARTS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "target",
    "venv",
}


class AstMapBuilder:
    def build(
        self,
        repo_path: Path,
        churn: dict[str, int] | None = None,
        tracked_files: list[str] | None = None,
    ) -> ProjectGraph:
        churn = churn or {}
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        for rel_path in _python_files(repo_path, tracked_files):
            rel_parts = tuple(rel_path.split("/"))
            if _is_ignored_path(rel_parts):
                continue
            py_file = repo_path.joinpath(*rel_parts)
            file_node_id = f"file:{rel_path}"
            nodes.append(
                GraphNode(
                    node_id=file_node_id,
                    kind="file",
                    label=rel_path,
                    path=rel_path,
                    hotspot_score=churn.get(rel_path, 0),
                )
            )

            try:
                module = ast.parse(py_file.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue

            for item in module.body:
                if isinstance(item, ast.ClassDef):
                    class_id = f"class:{rel_path}:{item.name}"
                    nodes.append(
                        GraphNode(
                            node_id=class_id,
                            kind="class",
                            label=item.name,
                            path=rel_path,
                            hotspot_score=churn.get(rel_path, 0),
                        )
                    )
                    edges.append(GraphEdge(source=file_node_id, target=class_id, relation="contains"))
                    for child in item.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            func_id = f"function:{rel_path}:{item.name}.{child.name}"
                            nodes.append(
                                GraphNode(
                                    node_id=func_id,
                                    kind="function",
                                    label=child.name,
                                    path=rel_path,
                                    hotspot_score=churn.get(rel_path, 0),
                                )
                            )
                            edges.append(GraphEdge(source=class_id, target=func_id, relation="contains"))
                elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_id = f"function:{rel_path}:{item.name}"
                    nodes.append(
                        GraphNode(
                            node_id=func_id,
                            kind="function",
                            label=item.name,
                            path=rel_path,
                            hotspot_score=churn.get(rel_path, 0),
                        )
                    )
                    edges.append(GraphEdge(source=file_node_id, target=func_id, relation="contains"))
                elif isinstance(item, (ast.Import, ast.ImportFrom)):
                    import_names = []
                    if isinstance(item, ast.Import):
                        import_names = [alias.name for alias in item.names]
                    else:
                        import_names = [item.module] if item.module else []
                    for import_name in import_names:
                        target = f"module:{import_name}"
                        edges.append(GraphEdge(source=file_node_id, target=target, relation="imports"))

        if not nodes:
            return _build_generic_file_map(repo_path, churn, tracked_files)
        return ProjectGraph(nodes=nodes, edges=edges)


def _python_files(repo_path: Path, tracked_files: list[str] | None) -> list[str]:
    if tracked_files is not None:
        return sorted(_normalize_path(path) for path in tracked_files if _normalize_path(path).endswith(".py"))

    paths: list[str] = []
    for py_file in sorted(repo_path.rglob("*.py")):
        try:
            rel_path = _normalize_path(str(py_file.relative_to(repo_path)))
        except ValueError:
            continue
        paths.append(rel_path)
    return paths


def _build_generic_file_map(
    repo_path: Path,
    churn: dict[str, int],
    tracked_files: list[str] | None,
) -> ProjectGraph:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    seen_nodes: set[str] = set()

    rel_paths = _project_files(repo_path, tracked_files)
    for rel_path in rel_paths:
        rel_parts = tuple(rel_path.split("/"))
        if _is_ignored_path(rel_parts):
            continue

        parent_id: str | None = None
        if len(rel_parts) > 1:
            module_path = rel_parts[0]
            parent_id = f"module:{module_path}"
            if parent_id not in seen_nodes:
                seen_nodes.add(parent_id)
                nodes.append(
                    GraphNode(
                        node_id=parent_id,
                        kind="module",
                        label=module_path,
                        path=module_path,
                        hotspot_score=0,
                    )
                )

        file_node_id = f"file:{rel_path}"
        if file_node_id in seen_nodes:
            continue
        seen_nodes.add(file_node_id)
        nodes.append(
            GraphNode(
                node_id=file_node_id,
                kind="file",
                label=rel_path,
                path=rel_path,
                hotspot_score=churn.get(rel_path, 0),
            )
        )
        if parent_id:
            edges.append(GraphEdge(source=parent_id, target=file_node_id, relation="contains"))

    return ProjectGraph(nodes=nodes, edges=edges)


def _project_files(repo_path: Path, tracked_files: list[str] | None) -> list[str]:
    if tracked_files is not None:
        candidates = [_normalize_path(path) for path in tracked_files]
    else:
        candidates = []
        for path in repo_path.rglob("*"):
            if not path.is_file():
                continue
            try:
                candidates.append(_normalize_path(str(path.relative_to(repo_path))))
            except ValueError:
                continue
    return sorted(path for path in candidates if _is_project_map_file(path))


def _is_project_map_file(path: str) -> bool:
    name = Path(path).name
    suffix = Path(path).suffix.lower()
    return name in MAP_FILE_NAMES or suffix in MAP_FILE_EXTENSIONS


def _is_ignored_path(parts: tuple[str, ...]) -> bool:
    return any(part.startswith(".") or part in IGNORED_PARTS for part in parts)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")
