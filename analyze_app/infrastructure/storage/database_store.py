from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, Text, create_engine, event, func, inspect
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.sql import text as sql_text

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
    TestRunResult,
    WorkingTreeReport,
)


class Base(DeclarativeBase):
    pass


class RepositoryModel(Base):
    __tablename__ = "repositories"

    repo_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    origin_url: Mapped[str] = mapped_column(Text, nullable=False)
    working_path: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("CURRENT_TIMESTAMP"))

    commit_reports: Mapped[list["CommitReportModel"]] = relationship(
        "CommitReportModel",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    working_tree_reports: Mapped[list["WorkingTreeReportModel"]] = relationship(
        "WorkingTreeReportModel",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    project_map: Mapped["ProjectMapModel | None"] = relationship(
        "ProjectMapModel",
        back_populates="repository",
        cascade="all, delete-orphan",
        uselist=False,
    )
    ai_authorship_entries: Mapped[list["AIAuthorshipCacheModel"]] = relationship(
        "AIAuthorshipCacheModel",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    project_overview: Mapped["ProjectOverviewModel | None"] = relationship(
        "ProjectOverviewModel",
        back_populates="repository",
        cascade="all, delete-orphan",
        uselist=False,
    )
    analysis_snapshot: Mapped["RepositoryAnalysisSnapshotModel | None"] = relationship(
        "RepositoryAnalysisSnapshotModel",
        back_populates="repository",
        cascade="all, delete-orphan",
        uselist=False,
    )


class CommitReportModel(Base):
    __tablename__ = "commit_reports"

    repo_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.repo_id", ondelete="CASCADE"),
        primary_key=True,
    )
    commit_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    files_changed: Mapped[int] = mapped_column(Integer, nullable=False)
    lines_added: Mapped[int] = mapped_column(Integer, nullable=False)
    lines_deleted: Mapped[int] = mapped_column(Integer, nullable=False)
    issues_count: Mapped[int] = mapped_column(Integer, nullable=False)
    tests_total: Mapped[int] = mapped_column(Integer, nullable=False)
    tests_failed: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_summary: Mapped[str] = mapped_column(Text, nullable=False)
    model_info: Mapped[str] = mapped_column(Text, nullable=False)
    ai_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("CURRENT_TIMESTAMP"))

    repository: Mapped["RepositoryModel"] = relationship("RepositoryModel", back_populates="commit_reports")


class WorkingTreeReportModel(Base):
    __tablename__ = "working_tree_reports"

    repo_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.repo_id", ondelete="CASCADE"),
        primary_key=True,
    )
    status_key: Mapped[str] = mapped_column(Text, primary_key=True)
    files_changed: Mapped[int] = mapped_column(Integer, nullable=False)
    lines_added: Mapped[int] = mapped_column(Integer, nullable=False)
    lines_deleted: Mapped[int] = mapped_column(Integer, nullable=False)
    issues_count: Mapped[int] = mapped_column(Integer, nullable=False)
    tests_total: Mapped[int] = mapped_column(Integer, nullable=False)
    tests_failed: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_summary: Mapped[str] = mapped_column(Text, nullable=False)
    model_info: Mapped[str] = mapped_column(Text, nullable=False)
    ai_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("CURRENT_TIMESTAMP"))

    repository: Mapped["RepositoryModel"] = relationship("RepositoryModel", back_populates="working_tree_reports")


class ProjectMapModel(Base):
    __tablename__ = "project_maps"

    repo_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.repo_id", ondelete="CASCADE"),
        primary_key=True,
    )
    nodes_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    edges_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("CURRENT_TIMESTAMP"))

    repository: Mapped["RepositoryModel"] = relationship("RepositoryModel", back_populates="project_map")


class AnalysisJobModel(Base):
    __tablename__ = "analysis_jobs"

    job_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    job_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("CURRENT_TIMESTAMP"))


class AIAuthorshipCacheModel(Base):
    __tablename__ = "ai_authorship_cache"

    repo_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.repo_id", ondelete="CASCADE"),
        primary_key=True,
    )
    scope_key: Mapped[str] = mapped_column(Text, primary_key=True)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    top_signals_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    calibration_version: Mapped[str] = mapped_column(Text, nullable=False)
    model_info: Mapped[str] = mapped_column(Text, nullable=False)
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("CURRENT_TIMESTAMP"))

    repository: Mapped["RepositoryModel"] = relationship("RepositoryModel", back_populates="ai_authorship_entries")


class ProjectOverviewModel(Base):
    __tablename__ = "project_overviews"

    repo_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.repo_id", ondelete="CASCADE"),
        primary_key=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    model_info: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("CURRENT_TIMESTAMP"))

    repository: Mapped["RepositoryModel"] = relationship("RepositoryModel", back_populates="project_overview")


class RepositoryAnalysisSnapshotModel(Base):
    __tablename__ = "repository_analysis_snapshots"

    repo_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.repo_id", ondelete="CASCADE"),
        primary_key=True,
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("CURRENT_TIMESTAMP"))

    repository: Mapped["RepositoryModel"] = relationship("RepositoryModel", back_populates="analysis_snapshot")


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class DatabaseStore:
    _FK_TABLES: dict[str, str] = {
        "commit_reports": """
            CREATE TABLE commit_reports (
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
                ai_evidence JSON NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (repo_id, commit_hash),
                FOREIGN KEY(repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE
            )
        """,
        "working_tree_reports": """
            CREATE TABLE working_tree_reports (
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
                ai_evidence JSON NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (repo_id, status_key),
                FOREIGN KEY(repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE
            )
        """,
        "project_maps": """
            CREATE TABLE project_maps (
                repo_id INTEGER NOT NULL,
                nodes_json JSON NOT NULL,
                edges_json JSON NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (repo_id),
                FOREIGN KEY(repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE
            )
        """,
        "ai_authorship_cache": """
            CREATE TABLE ai_authorship_cache (
                repo_id INTEGER NOT NULL,
                scope_key TEXT NOT NULL,
                scope TEXT NOT NULL,
                probability REAL NOT NULL,
                confidence REAL NOT NULL,
                top_signals_json JSON NOT NULL,
                calibration_version TEXT NOT NULL,
                model_info TEXT NOT NULL,
                disclaimer TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (repo_id, scope_key),
                FOREIGN KEY(repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE
            )
        """,
        "project_overviews": """
            CREATE TABLE project_overviews (
                repo_id INTEGER NOT NULL,
                summary TEXT NOT NULL,
                model_info TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (repo_id),
                FOREIGN KEY(repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE
            )
        """,
        "repository_analysis_snapshots": """
            CREATE TABLE repository_analysis_snapshots (
                repo_id INTEGER NOT NULL,
                payload_json JSON NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (repo_id),
                FOREIGN KEY(repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE
            )
        """,
    }

    def __init__(self, path: Path) -> None:
        self.path = path
        if self.path.parent != Path("."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(URL.create("sqlite", database=str(self.path)), future=True)
        event.listen(self.engine, "connect", _enable_sqlite_foreign_keys)
        self._Session = sessionmaker(self.engine, expire_on_commit=False, future=True)
        self._init_schema()

    def _init_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        self._migrate_legacy_foreign_keys()

    def _migrate_legacy_foreign_keys(self) -> None:
        inspector = inspect(self.engine)
        existing_tables = set(inspector.get_table_names())
        if "repositories" not in existing_tables:
            return

        for table_name, create_sql in self._FK_TABLES.items():
            if table_name not in existing_tables:
                continue
            foreign_keys = inspector.get_foreign_keys(table_name)
            if any(fk.get("referred_table") == "repositories" for fk in foreign_keys):
                continue
            self._rebuild_fk_table(table_name, create_sql)

    def _rebuild_fk_table(self, table_name: str, create_sql: str) -> None:
        temp_table = f"__tmp_{table_name}_with_fk"
        with self.engine.begin() as conn:
            columns = [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})")]
            column_sql = ", ".join(columns)
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS {temp_table}")
            conn.exec_driver_sql(create_sql.replace(f"CREATE TABLE {table_name}", f"CREATE TABLE {temp_table}", 1))
            conn.exec_driver_sql(
                f"""
                INSERT INTO {temp_table} ({column_sql})
                SELECT {column_sql}
                FROM {table_name}
                WHERE EXISTS (
                    SELECT 1
                    FROM repositories
                    WHERE repositories.repo_id = {table_name}.repo_id
                )
                """
            )
            conn.exec_driver_sql(f"DROP TABLE {table_name}")
            conn.exec_driver_sql(f"ALTER TABLE {temp_table} RENAME TO {table_name}")

    def add_repository(self, origin_url: str, working_path: str, default_branch: str = "main") -> int:
        with self._Session() as session:
            repository = RepositoryModel(
                origin_url=origin_url,
                working_path=working_path,
                default_branch=default_branch,
            )
            session.add(repository)
            session.commit()
            return repository.repo_id

    def list_repositories(self) -> list[tuple[int, str, str, str, str]]:
        with self._Session() as session:
            repositories = (
                session.query(RepositoryModel)
                .order_by(RepositoryModel.repo_id.desc())
                .all()
            )
            return [
                (
                    repository.repo_id,
                    repository.origin_url,
                    repository.working_path,
                    repository.default_branch,
                    str(repository.created_at),
                )
                for repository in repositories
            ]

    def delete_repository(self, repo_id: int) -> None:
        with self._Session() as session:
            repository = session.get(RepositoryModel, repo_id)
            if repository:
                session.delete(repository)
            session.commit()

    def save_commit_report(self, repo_id: int, report: CommitReport) -> None:
        evidence = [{"file": item.file, "reason": item.reason} for item in report.ai_summary.evidence]
        values = {
            "repo_id": repo_id,
            "commit_hash": report.commit_hash,
            "files_changed": report.metrics.files_changed,
            "lines_added": report.metrics.lines_added,
            "lines_deleted": report.metrics.lines_deleted,
            "issues_count": len(report.issues),
            "tests_total": report.tests.total,
            "tests_failed": report.tests.failed,
            "ai_summary": report.ai_summary.summary,
            "model_info": report.ai_summary.model_info,
            "ai_evidence": evidence,
        }
        with self._Session() as session:
            self._upsert(
                session,
                CommitReportModel,
                values,
                index_elements=[CommitReportModel.repo_id, CommitReportModel.commit_hash],
            )
            session.commit()

    def load_commit_report(self, repo_id: int, commit_hash: str) -> tuple | None:
        with self._Session() as session:
            report = session.get(CommitReportModel, {"repo_id": repo_id, "commit_hash": commit_hash})
            if not report:
                return None
            return (
                report.repo_id,
                report.commit_hash,
                report.files_changed,
                report.lines_added,
                report.lines_deleted,
                report.issues_count,
                report.tests_total,
                report.tests_failed,
                report.ai_summary,
                report.model_info,
                self._json_text(report.ai_evidence),
                str(report.created_at),
            )

    def save_working_tree_report(self, repo_id: int, status_key: str, report: WorkingTreeReport) -> None:
        evidence = [{"file": item.file, "reason": item.reason} for item in report.ai_summary.evidence]
        values = {
            "repo_id": repo_id,
            "status_key": status_key,
            "files_changed": report.metrics.files_changed,
            "lines_added": report.metrics.lines_added,
            "lines_deleted": report.metrics.lines_deleted,
            "issues_count": len(report.issues),
            "tests_total": report.tests.total,
            "tests_failed": report.tests.failed,
            "ai_summary": report.ai_summary.summary,
            "model_info": report.ai_summary.model_info,
            "ai_evidence": evidence,
        }
        with self._Session() as session:
            self._upsert(
                session,
                WorkingTreeReportModel,
                values,
                index_elements=[WorkingTreeReportModel.repo_id, WorkingTreeReportModel.status_key],
            )
            session.commit()

    def load_working_tree_report(self, repo_id: int, status_key: str) -> WorkingTreeReport | None:
        with self._Session() as session:
            row = session.get(WorkingTreeReportModel, {"repo_id": repo_id, "status_key": status_key})
            if not row:
                return None

            evidence_payload = self._json_payload(row.ai_evidence, fallback=[])
            evidence = [EvidenceBlock(file=item["file"], reason=item["reason"]) for item in evidence_payload]
            return WorkingTreeReport(
                metrics=ChangeMetrics(
                    files_changed=row.files_changed,
                    lines_added=row.lines_added,
                    lines_deleted=row.lines_deleted,
                ),
                issues=[],
                tests=TestRunResult(
                    total=row.tests_total,
                    failed=row.tests_failed,
                    passed=max(row.tests_total - row.tests_failed, 0),
                ),
                ai_summary=LLMResult(summary=row.ai_summary, model_info=row.model_info, evidence=evidence),
            )

    def save_project_map(self, repo_id: int, project_map: ProjectGraph) -> None:
        values = {
            "repo_id": repo_id,
            "nodes_json": [asdict(node) for node in project_map.nodes],
            "edges_json": [asdict(edge) for edge in project_map.edges],
        }
        with self._Session() as session:
            self._upsert(
                session,
                ProjectMapModel,
                values,
                index_elements=[ProjectMapModel.repo_id],
            )
            session.commit()

    def load_project_map(self, repo_id: int) -> ProjectGraph | None:
        with self._Session() as session:
            row = session.get(ProjectMapModel, repo_id)
            if not row:
                return None

            nodes_raw = self._json_payload(row.nodes_json, fallback=[])
            edges_raw = self._json_payload(row.edges_json, fallback=[])
            nodes = [GraphNode(**item) for item in nodes_raw]
            edges = [GraphEdge(**item) for item in edges_raw]
            return ProjectGraph(nodes=nodes, edges=edges)

    def save_job(self, job_type: str, job_key: str, payload: dict, status: str = "queued") -> None:
        values = {
            "job_type": job_type,
            "job_key": job_key,
            "status": status,
            "payload_json": payload,
        }
        with self._Session() as session:
            self._upsert(
                session,
                AnalysisJobModel,
                values,
                index_elements=[AnalysisJobModel.job_key],
            )
            session.commit()

    def save_project_overview(self, repo_id: int, summary: str, model_info: str) -> None:
        values = {
            "repo_id": repo_id,
            "summary": summary,
            "model_info": model_info,
        }
        with self._Session() as session:
            self._upsert(
                session,
                ProjectOverviewModel,
                values,
                index_elements=[ProjectOverviewModel.repo_id],
            )
            session.commit()

    def load_project_overview(self, repo_id: int) -> tuple[str, str] | None:
        with self._Session() as session:
            row = session.get(ProjectOverviewModel, repo_id)
            if not row:
                return None
            return row.summary, row.model_info

    def save_repository_analysis_snapshot(self, repo_id: int, payload: dict) -> None:
        values = {
            "repo_id": repo_id,
            "payload_json": payload,
        }
        with self._Session() as session:
            self._upsert(
                session,
                RepositoryAnalysisSnapshotModel,
                values,
                index_elements=[RepositoryAnalysisSnapshotModel.repo_id],
            )
            session.commit()

    def load_repository_analysis_snapshot(self, repo_id: int) -> dict | None:
        with self._Session() as session:
            row = session.get(RepositoryAnalysisSnapshotModel, repo_id)
            if not row:
                return None
            payload = self._json_payload(row.payload_json, fallback={})
            return dict(payload)

    def save_ai_authorship(self, repo_id: int, scope_key: str, result: AIAuthorshipResult) -> None:
        values = {
            "repo_id": repo_id,
            "scope_key": scope_key,
            "scope": result.scope,
            "probability": result.probability,
            "confidence": result.confidence,
            "top_signals_json": [asdict(signal) for signal in result.top_signals],
            "calibration_version": result.calibration_version,
            "model_info": result.model_info,
            "disclaimer": result.disclaimer,
        }
        with self._Session() as session:
            self._upsert(
                session,
                AIAuthorshipCacheModel,
                values,
                index_elements=[AIAuthorshipCacheModel.repo_id, AIAuthorshipCacheModel.scope_key],
            )
            session.commit()

    def load_ai_authorship(self, repo_id: int, scope_key: str) -> AIAuthorshipResult | None:
        with self._Session() as session:
            row = session.get(AIAuthorshipCacheModel, {"repo_id": repo_id, "scope_key": scope_key})
            if not row:
                return None

            signals_raw = self._json_payload(row.top_signals_json, fallback=[])
            signals = [AIAuthorshipSignal(**item) for item in signals_raw]
            return AIAuthorshipResult(
                scope=row.scope,
                probability=float(row.probability),
                confidence=float(row.confidence),
                top_signals=signals,
                calibration_version=row.calibration_version,
                model_info=row.model_info,
                disclaimer=row.disclaimer,
            )

    @staticmethod
    def _upsert(
        session: Session,
        model: type[Base],
        values: dict[str, Any],
        index_elements: Sequence[Any],
    ) -> None:
        insert_stmt = sqlite_insert(model).values(**values)
        update_values = {
            key: value
            for key, value in values.items()
            if key not in {column.key for column in index_elements}
        }
        update_values["created_at"] = func.current_timestamp()
        session.execute(
            insert_stmt.on_conflict_do_update(
                index_elements=index_elements,
                set_=update_values,
            )
        )

    @staticmethod
    def _json_payload(value: Any, fallback: Any) -> Any:
        if value in (None, ""):
            return fallback
        if isinstance(value, str):
            return json.loads(value)
        return value

    @staticmethod
    def _json_text(value: Any) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value if value is not None else [])
