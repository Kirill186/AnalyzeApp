from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from analyze_app.domain.entities import (
    ChangeMetrics,
    CommitReport,
    EvidenceBlock,
    GraphEdge,
    GraphNode,
    LLMResult,
    ProjectGraph,
    TestRunResult,
    WorkingTreeReport,
)


class SqliteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS repositories (
                    repo_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    origin_url TEXT NOT NULL,
                    working_path TEXT NOT NULL,
                    default_branch TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS commit_reports (
                    repo_id INTEGER NOT NULL,
                    commit_hash TEXT NOT NULL,
                    files_changed INTEGER NOT NULL,
                    lines_added INTEGER NOT NULL,
                    lines_deleted INTEGER NOT NULL,
                    issues_count INTEGER NOT NULL,
                    tests_total INTEGER NOT NULL,
                    tests_failed INTEGER NOT NULL,
                    ai_summary TEXT NOT NULL,
                    model_info TEXT NOT NULL,
                    ai_evidence TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (repo_id, commit_hash)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS working_tree_reports (
                    repo_id INTEGER NOT NULL,
                    status_key TEXT NOT NULL,
                    files_changed INTEGER NOT NULL,
                    lines_added INTEGER NOT NULL,
                    lines_deleted INTEGER NOT NULL,
                    issues_count INTEGER NOT NULL,
                    tests_total INTEGER NOT NULL,
                    tests_failed INTEGER NOT NULL,
                    ai_summary TEXT NOT NULL,
                    model_info TEXT NOT NULL,
                    ai_evidence TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (repo_id, status_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_maps (
                    repo_id INTEGER PRIMARY KEY,
                    nodes_json TEXT NOT NULL,
                    edges_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_type TEXT NOT NULL,
                    job_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def add_repository(self, origin_url: str, working_path: str, default_branch: str = "main") -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO repositories (origin_url, working_path, default_branch)
                VALUES (?, ?, ?)
                """,
                (origin_url, working_path, default_branch),
            )
            return int(cursor.lastrowid)

    def save_commit_report(self, repo_id: int, report: CommitReport) -> None:
        evidence_json = json.dumps([{"file": item.file, "reason": item.reason} for item in report.ai_summary.evidence])
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO commit_reports (
                    repo_id, commit_hash, files_changed, lines_added, lines_deleted,
                    issues_count, tests_total, tests_failed, ai_summary, model_info, ai_evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repo_id,
                    report.commit_hash,
                    report.metrics.files_changed,
                    report.metrics.lines_added,
                    report.metrics.lines_deleted,
                    len(report.issues),
                    report.tests.total,
                    report.tests.failed,
                    report.ai_summary.summary,
                    report.ai_summary.model_info,
                    evidence_json,
                ),
            )

    def load_commit_report(self, repo_id: int, commit_hash: str) -> tuple | None:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM commit_reports WHERE repo_id = ? AND commit_hash = ?",
                (repo_id, commit_hash),
            )
            return cursor.fetchone()

    def save_working_tree_report(self, repo_id: int, status_key: str, report: WorkingTreeReport) -> None:
        evidence_json = json.dumps([{"file": item.file, "reason": item.reason} for item in report.ai_summary.evidence])
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO working_tree_reports (
                    repo_id, status_key, files_changed, lines_added, lines_deleted,
                    issues_count, tests_total, tests_failed, ai_summary, model_info, ai_evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repo_id,
                    status_key,
                    report.metrics.files_changed,
                    report.metrics.lines_added,
                    report.metrics.lines_deleted,
                    len(report.issues),
                    report.tests.total,
                    report.tests.failed,
                    report.ai_summary.summary,
                    report.ai_summary.model_info,
                    evidence_json,
                ),
            )

    def load_working_tree_report(self, repo_id: int, status_key: str) -> WorkingTreeReport | None:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT files_changed, lines_added, lines_deleted, tests_total, tests_failed, ai_summary, model_info, ai_evidence "
                "FROM working_tree_reports WHERE repo_id = ? AND status_key = ?",
                (repo_id, status_key),
            )
            row = cursor.fetchone()
            if not row:
                return None

        evidence_payload = json.loads(row[7]) if row[7] else []
        evidence = [EvidenceBlock(file=item["file"], reason=item["reason"]) for item in evidence_payload]
        return WorkingTreeReport(
            metrics=ChangeMetrics(files_changed=row[0], lines_added=row[1], lines_deleted=row[2]),
            issues=[],
            tests=TestRunResult(total=row[3], failed=row[4], passed=max(row[3] - row[4], 0)),
            ai_summary=LLMResult(summary=row[5], model_info=row[6], evidence=evidence),
        )

    def save_project_map(self, repo_id: int, project_map: ProjectGraph) -> None:
        nodes = [asdict(node) for node in project_map.nodes]
        edges = [asdict(edge) for edge in project_map.edges]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO project_maps (repo_id, nodes_json, edges_json)
                VALUES (?, ?, ?)
                """,
                (repo_id, json.dumps(nodes), json.dumps(edges)),
            )

    def load_project_map(self, repo_id: int) -> ProjectGraph | None:
        with self._connect() as conn:
            cursor = conn.execute("SELECT nodes_json, edges_json FROM project_maps WHERE repo_id = ?", (repo_id,))
            row = cursor.fetchone()
            if not row:
                return None

        nodes_raw = json.loads(row[0])
        edges_raw = json.loads(row[1])
        nodes = [GraphNode(**item) for item in nodes_raw]
        edges = [GraphEdge(**item) for item in edges_raw]
        return ProjectGraph(nodes=nodes, edges=edges)

    def save_job(self, job_type: str, job_key: str, payload: dict, status: str = "queued") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO analysis_jobs (job_type, job_key, status, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (job_type, job_key, status, json.dumps(payload)),
            )
