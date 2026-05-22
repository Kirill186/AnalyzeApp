from __future__ import annotations

from analyze_app.infrastructure.analysis.map import ast_map_builder
from analyze_app.infrastructure.analysis.map.ast_map_builder import AstMapBuilder


def test_small_python_project_keeps_ast_structure(tmp_path) -> None:
    source = tmp_path / "app.py"
    source.write_text(
        "class Service:\n"
        "    def run(self):\n"
        "        return 1\n"
        "\n"
        "def helper():\n"
        "    return 2\n",
        encoding="utf-8",
    )

    graph = AstMapBuilder().build(tmp_path, churn={"app.py": 7}, tracked_files=["app.py"])

    assert any(node.kind == "class" and node.label == "Service" for node in graph.nodes)
    assert any(node.kind == "function" and node.label == "helper" for node in graph.nodes)
    assert any(edge.relation == "contains" for edge in graph.edges)


def test_python_project_links_local_imports_between_files(tmp_path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "a.py").write_text(
        "import os\n"
        "import pkg.d\n"
        "from .b import Thing\n"
        "from . import c\n"
        "from pkg import e\n",
        encoding="utf-8",
    )
    (package / "b.py").write_text("class Thing:\n    pass\n", encoding="utf-8")
    (package / "c.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "d.py").write_text("VALUE = 2\n", encoding="utf-8")
    (package / "e.py").write_text("VALUE = 3\n", encoding="utf-8")

    graph = AstMapBuilder().build(
        tmp_path,
        tracked_files=[
            "pkg/__init__.py",
            "pkg/a.py",
            "pkg/b.py",
            "pkg/c.py",
            "pkg/d.py",
            "pkg/e.py",
        ],
    )

    edges = {(edge.source, edge.target, edge.relation) for edge in graph.edges}
    assert ("file:pkg/a.py", "file:pkg/b.py", "imports") in edges
    assert ("file:pkg/a.py", "file:pkg/c.py", "imports") in edges
    assert ("file:pkg/a.py", "file:pkg/d.py", "imports") in edges
    assert ("file:pkg/a.py", "file:pkg/e.py", "imports") in edges
    assert ("file:pkg/a.py", "module:os", "imports") in edges


def test_large_python_project_uses_file_hotspot_map(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ast_map_builder, "LARGE_AST_FILE_THRESHOLD", 1)
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "a.py").write_text("from pkg import b\n", encoding="utf-8")
    (package / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
    tracked_files = [
        "pkg/a.py",
        "pkg/b.py",
        ".venv/vendor.py",
        "README.md",
    ]

    graph = AstMapBuilder().build(
        tmp_path,
        churn={"pkg/a.py": 12, "README.md": 3},
        tracked_files=tracked_files,
    )

    assert {(edge.source, edge.target, edge.relation) for edge in graph.edges} == {
        ("file:pkg/a.py", "file:pkg/b.py", "imports")
    }
    assert all(node.kind == "file" for node in graph.nodes)
    assert {node.path for node in graph.nodes} == {"pkg/a.py", "pkg/b.py", "README.md"}
    assert next(node for node in graph.nodes if node.path == "pkg/a.py").hotspot_score == 12


def test_large_non_python_project_uses_file_hotspot_map(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ast_map_builder, "LARGE_PROJECT_FILE_THRESHOLD", 2)
    tracked_files = ["src/a.js", "src/b.css", "docs/README.md"]

    graph = AstMapBuilder().build(tmp_path, churn={}, tracked_files=tracked_files)

    assert graph.edges == []
    assert [node.kind for node in graph.nodes] == ["file", "file", "file"]
