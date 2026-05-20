from __future__ import annotations

import sqlite3

from sqlalchemy import inspect

from analyze_app.domain.entities import (
    AIAuthorshipResult,
    AIAuthorshipSignal,
    ChangeMetrics,
    CommitReport,
    EvidenceBlock,
    GraphEdge,
    GraphNode,
    LLMResult,
    ProjectGraph,
    TestRunResult as DomainTestRunResult,
    WorkingTreeReport,
)
from analyze_app.infrastructure.storage.database_store import DatabaseStore


def test_sqlalchemy_schema_declares_repository_foreign_keys(tmp_path) -> None:
    store = DatabaseStore(tmp_path / "app.sqlite3")
    inspector = inspect(store.engine)

    child_tables = {
        "commit_reports",
        "working_tree_reports",
        "project_maps",
        "ai_authorship_cache",
        "project_overviews",
        "repository_analysis_snapshots",
    }

    for table_name in child_tables:
        foreign_keys = inspector.get_foreign_keys(table_name)
        assert any(
            fk["referred_table"] == "repositories"
            and fk["constrained_columns"] == ["repo_id"]
            for fk in foreign_keys
        )


def test_store_round_trips_reports_and_json_payloads(tmp_path) -> None:
    store = DatabaseStore(tmp_path / "app.sqlite3")
    repo_id = store.add_repository("https://example.test/repo.git", str(tmp_path / "repo"))

    store.save_commit_report(
        repo_id,
        CommitReport(
            commit_hash="abc123",
            metrics=ChangeMetrics(files_changed=2, lines_added=10, lines_deleted=3),
            issues=[],
            tests=DomainTestRunResult(total=4, passed=3, failed=1),
            ai_summary=LLMResult(
                summary="commit summary",
                model_info="local/test-model",
                evidence=[EvidenceBlock(file="app.py", reason="important diff")],
            ),
        ),
    )
    commit_report = store.load_commit_report(repo_id, "abc123")
    assert commit_report is not None
    assert commit_report[2:5] == (2, 10, 3)
    assert commit_report[8] == "commit summary"
    assert "important diff" in commit_report[10]

    store.save_working_tree_report(
        repo_id,
        " M app.py",
        WorkingTreeReport(
            metrics=ChangeMetrics(files_changed=1, lines_added=5, lines_deleted=0),
            issues=[],
            tests=DomainTestRunResult(total=1, passed=1, failed=0),
            ai_summary=LLMResult(
                summary="working tree summary",
                model_info="local/test-model",
                evidence=[EvidenceBlock(file="app.py", reason="changed")],
            ),
        ),
    )
    working_tree_report = store.load_working_tree_report(repo_id, " M app.py")
    assert working_tree_report is not None
    assert working_tree_report.ai_summary.evidence[0].file == "app.py"

    project_map = ProjectGraph(
        nodes=[GraphNode(node_id="file:app.py", kind="file", label="app.py", path="app.py", hotspot_score=2)],
        edges=[GraphEdge(source="file:app.py", target="func:run", relation="contains")],
    )
    store.save_project_map(repo_id, project_map)
    assert store.load_project_map(repo_id) == project_map

    store.save_project_overview(repo_id, "overview", "model")
    assert store.load_project_overview(repo_id) == ("overview", "model")

    store.save_repository_analysis_snapshot(repo_id, {"metrics": {"lint": ["A", "0", "<=1"]}})
    assert store.load_repository_analysis_snapshot(repo_id) == {"metrics": {"lint": ["A", "0", "<=1"]}}

    store.save_ai_authorship(
        repo_id,
        "working_tree:v1:hash",
        AIAuthorshipResult(
            scope="working_tree",
            probability=0.12,
            data_sufficiency=0.8,
            top_signals=[
                AIAuthorshipSignal(
                    name="line_count",
                    value=120.0,
                    weight=0.2,
                    direction="info",
                    description="enough code",
                )
            ],
            calibration_version="v1",
            model_info="model/dataset",
            disclaimer="probabilistic",
        ),
    )
    cached_authorship = store.load_ai_authorship(repo_id, "working_tree:v1:hash")
    assert cached_authorship is not None
    assert cached_authorship.data_sufficiency == 0.8
    assert cached_authorship.top_signals[0].name == "line_count"


def test_delete_repository_cascades_related_rows(tmp_path) -> None:
    store = DatabaseStore(tmp_path / "app.sqlite3")
    repo_id = store.add_repository("local", str(tmp_path / "repo"))

    store.save_project_overview(repo_id, "overview", "model")
    store.save_repository_analysis_snapshot(repo_id, {"files_count": 3})
    store.save_project_map(repo_id, ProjectGraph(nodes=[], edges=[]))

    store.delete_repository(repo_id)

    assert store.list_repositories() == []
    assert store.load_project_overview(repo_id) is None
    assert store.load_repository_analysis_snapshot(repo_id) is None
    assert store.load_project_map(repo_id) is None


def test_store_migrates_legacy_tables_to_foreign_keys(tmp_path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE repositories (
                repo_id INTEGER PRIMARY KEY AUTOINCREMENT,
                origin_url TEXT NOT NULL,
                working_path TEXT NOT NULL,
                default_branch TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE project_overviews (
                repo_id INTEGER PRIMARY KEY,
                summary TEXT NOT NULL,
                model_info TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            "INSERT INTO repositories (origin_url, working_path, default_branch) VALUES (?, ?, ?)",
            ("local", str(tmp_path / "repo"), "main"),
        )
        conn.execute(
            "INSERT INTO project_overviews (repo_id, summary, model_info) VALUES (?, ?, ?)",
            (1, "legacy overview", "legacy model"),
        )

    store = DatabaseStore(db_path)
    inspector = inspect(store.engine)

    assert store.load_project_overview(1) == ("legacy overview", "legacy model")
    assert any(
        fk["referred_table"] == "repositories"
        and fk["constrained_columns"] == ["repo_id"]
        for fk in inspector.get_foreign_keys("project_overviews")
    )
