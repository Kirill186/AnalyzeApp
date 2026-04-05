from __future__ import annotations

import sqlite3
from pathlib import Path

from analyze_app.domain.entities import CommitReport


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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (repo_id, commit_hash)
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
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO commit_reports (
                    repo_id, commit_hash, files_changed, lines_added, lines_deleted,
                    issues_count, tests_total, tests_failed, ai_summary, model_info
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )

    def load_commit_report(self, repo_id: int, commit_hash: str) -> tuple | None:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM commit_reports WHERE repo_id = ? AND commit_hash = ?",
                (repo_id, commit_hash),
            )
            return cursor.fetchone()
