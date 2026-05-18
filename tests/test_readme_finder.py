from __future__ import annotations

from analyze_app.presentation.qt_shell.readme_finder import find_readme_candidates


def test_find_readme_candidates_ignores_tool_cache_readmes(tmp_path) -> None:
    cache_dir = tmp_path / ".pytest_cache"
    cache_dir.mkdir()
    (cache_dir / "README.md").write_text("pytest cache docs", encoding="utf-8")

    assert find_readme_candidates(tmp_path) == []


def test_find_readme_candidates_uses_nested_project_readme(tmp_path) -> None:
    cache_dir = tmp_path / ".pytest_cache"
    cache_dir.mkdir()
    (cache_dir / "README.md").write_text("pytest cache docs", encoding="utf-8")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    readme = docs_dir / "README.md"
    readme.write_text("project docs", encoding="utf-8")

    assert find_readme_candidates(tmp_path) == [readme]
