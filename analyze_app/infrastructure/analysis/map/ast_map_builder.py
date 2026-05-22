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
LARGE_AST_FILE_THRESHOLD = 450
LARGE_PROJECT_FILE_THRESHOLD = 900


class AstMapBuilder:
    def build(
        self,
        repo_path: Path,
        churn: dict[str, int] | None = None,
        tracked_files: list[str] | None = None,
        include_file_links: bool = True,
    ) -> ProjectGraph:
        churn = churn or {}
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        python_files = [
            rel_path
            for rel_path in _python_files(repo_path, tracked_files)
            if not _is_ignored_path(tuple(rel_path.split("/")))
        ]

        if len(python_files) > LARGE_AST_FILE_THRESHOLD:
            return _build_file_hotspot_map(repo_path, churn, tracked_files, include_file_links=include_file_links)

        import_edges = []
        if include_file_links:
            import_edges = _build_python_file_import_edges(repo_path, python_files, include_external=True)
        for rel_path in python_files:
            rel_parts = tuple(rel_path.split("/"))
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
            except (OSError, SyntaxError, UnicodeDecodeError):
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

        if not nodes:
            project_files = _visible_project_files(repo_path, tracked_files)
            if len(project_files) > LARGE_PROJECT_FILE_THRESHOLD:
                import_edges = []
                if include_file_links:
                    import_edges = _build_python_file_import_edges(
                        repo_path,
                        _python_paths_from(project_files),
                        include_external=False,
                    )
                return _build_file_hotspot_map_from_paths(project_files, churn, import_edges)
            return _build_generic_file_map_from_paths(project_files, churn)
        return ProjectGraph(nodes=nodes, edges=[*edges, *import_edges])


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
    return _build_generic_file_map_from_paths(_visible_project_files(repo_path, tracked_files), churn)


def _build_file_hotspot_map(
    repo_path: Path,
    churn: dict[str, int],
    tracked_files: list[str] | None,
    *,
    include_file_links: bool = True,
) -> ProjectGraph:
    project_files = _visible_project_files(repo_path, tracked_files)
    import_edges = []
    if include_file_links:
        import_edges = _build_python_file_import_edges(
            repo_path,
            _python_paths_from(project_files),
            include_external=False,
        )
    return _build_file_hotspot_map_from_paths(project_files, churn, import_edges)


def _build_file_hotspot_map_from_paths(
    rel_paths: list[str],
    churn: dict[str, int],
    edges: list[GraphEdge] | None = None,
) -> ProjectGraph:
    nodes: list[GraphNode] = []
    seen_nodes: set[str] = set()

    for rel_path in rel_paths:
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

    return ProjectGraph(nodes=nodes, edges=edges or [])


def _build_generic_file_map_from_paths(rel_paths: list[str], churn: dict[str, int]) -> ProjectGraph:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    seen_nodes: set[str] = set()

    for rel_path in rel_paths:
        rel_parts = tuple(rel_path.split("/"))

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


def _visible_project_files(repo_path: Path, tracked_files: list[str] | None) -> list[str]:
    return [
        rel_path
        for rel_path in _project_files(repo_path, tracked_files)
        if not _is_ignored_path(tuple(rel_path.split("/")))
    ]


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


def _python_paths_from(rel_paths: list[str]) -> list[str]:
    return [path for path in rel_paths if path.endswith(".py")]


def _build_python_file_import_edges(
    repo_path: Path,
    python_files: list[str],
    include_external: bool,
) -> list[GraphEdge]:
    module_index = _python_module_index(python_files)
    edges: list[GraphEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for rel_path in python_files:
        source_id = f"file:{rel_path}"
        py_file = repo_path.joinpath(*rel_path.split("/"))
        try:
            module = ast.parse(py_file.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue

        for import_node in ast.walk(module):
            if not isinstance(import_node, (ast.Import, ast.ImportFrom)):
                continue
            for target_id in _import_target_ids(rel_path, import_node, module_index, include_external):
                if target_id == source_id:
                    continue
                _append_unique_edge(edges, seen_edges, source_id, target_id, "imports")

    return edges


def _python_module_index(python_files: list[str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for rel_path in python_files:
        if not rel_path.endswith(".py"):
            continue

        module_path = rel_path[:-3]
        module_name = module_path.replace("/", ".")
        index.setdefault(module_name, rel_path)

        if module_path.endswith("/__init__"):
            package_path = module_path[: -len("/__init__")]
            if package_path:
                index.setdefault(package_path.replace("/", "."), rel_path)

    return index


def _import_target_ids(
    source_path: str,
    import_node: ast.Import | ast.ImportFrom,
    module_index: dict[str, str],
    include_external: bool,
) -> list[str]:
    if isinstance(import_node, ast.Import):
        return _import_targets_for_import(import_node, module_index, include_external)
    return _import_targets_for_from_import(source_path, import_node, module_index, include_external)


def _import_targets_for_import(
    import_node: ast.Import,
    module_index: dict[str, str],
    include_external: bool,
) -> list[str]:
    targets: list[str] = []
    for alias in import_node.names:
        rel_path = _resolve_module_path(alias.name, module_index)
        if rel_path:
            targets.append(f"file:{rel_path}")
        elif include_external:
            targets.append(f"module:{alias.name}")
    return _dedupe_preserve_order(targets)


def _import_targets_for_from_import(
    source_path: str,
    import_node: ast.ImportFrom,
    module_index: dict[str, str],
    include_external: bool,
) -> list[str]:
    base_module = _absolute_from_import_base(source_path, import_node)
    if not base_module:
        return []

    candidates: list[str] = []
    if import_node.module:
        candidates.append(base_module)

    for alias in import_node.names:
        if alias.name == "*":
            continue
        candidates.append(f"{base_module}.{alias.name}")

    targets: list[str] = []
    for module_name in _dedupe_preserve_order(candidates):
        rel_path = _resolve_module_path(module_name, module_index)
        if rel_path:
            targets.append(f"file:{rel_path}")

    if not targets and include_external and import_node.level == 0 and import_node.module:
        targets.append(f"module:{import_node.module}")

    return _dedupe_preserve_order(targets)


def _absolute_from_import_base(source_path: str, import_node: ast.ImportFrom) -> str:
    if import_node.level <= 0:
        return import_node.module or ""

    package_parts = source_path[:-3].split("/")[:-1]
    if import_node.level > len(package_parts) + 1:
        return ""

    keep_parts = len(package_parts) - import_node.level + 1
    base_parts = package_parts[:keep_parts]
    if import_node.module:
        base_parts.extend(part for part in import_node.module.split(".") if part)
    return ".".join(base_parts)


def _resolve_module_path(module_name: str, module_index: dict[str, str]) -> str | None:
    if module_name in module_index:
        return module_index[module_name]

    parts = module_name.split(".")
    for end in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in module_index:
            return module_index[candidate]
    return None


def _append_unique_edge(
    edges: list[GraphEdge],
    seen_edges: set[tuple[str, str, str]],
    source: str,
    target: str,
    relation: str,
) -> None:
    key = (source, target, relation)
    if key in seen_edges:
        return
    seen_edges.add(key)
    edges.append(GraphEdge(source=source, target=target, relation=relation))


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
