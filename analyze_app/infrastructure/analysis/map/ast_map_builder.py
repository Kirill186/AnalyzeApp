from __future__ import annotations

import ast
from pathlib import Path

from analyze_app.domain.entities import GraphEdge, GraphNode, ProjectGraph


class AstMapBuilder:
    def build(self, repo_path: Path, churn: dict[str, int] | None = None) -> ProjectGraph:
        churn = churn or {}
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        for py_file in sorted(repo_path.rglob("*.py")):
            rel_parts = py_file.relative_to(repo_path).parts
            if any(part.startswith(".") for part in rel_parts):
                continue
            rel_path = "/".join(rel_parts)
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

        return ProjectGraph(nodes=nodes, edges=edges)
