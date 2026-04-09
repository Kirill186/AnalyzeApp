from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Repository:
    repo_id: int
    origin_url: str
    working_path: str
    default_branch: str = "main"


@dataclass(slots=True)
class Commit:
    hash: str
    author: str
    authored_at: datetime
    message: str


@dataclass(slots=True)
class FileChange:
    path: str
    additions: int
    deletions: int


@dataclass(slots=True)
class Issue:
    tool: str
    message: str
    file: str | None = None
    line: int | None = None
    severity: str = "warning"


@dataclass(slots=True)
class ChangeMetrics:
    files_changed: int
    lines_added: int
    lines_deleted: int


@dataclass(slots=True)
class TestRunResult:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_sec: float = 0.0
    failed_tests: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EvidenceBlock:
    file: str
    reason: str


@dataclass(slots=True)
class LLMResult:
    summary: str
    model_info: str
    evidence: list[EvidenceBlock] = field(default_factory=list)


@dataclass(slots=True)
class AIAuthorshipSignal:
    name: str
    value: float
    weight: float
    direction: str
    description: str


@dataclass(slots=True)
class AIAuthorshipResult:
    scope: str
    probability: float
    confidence: float
    top_signals: list[AIAuthorshipSignal]
    calibration_version: str
    model_info: str
    disclaimer: str


@dataclass(slots=True)
class CommitReport:
    commit_hash: str
    metrics: ChangeMetrics
    issues: list[Issue]
    tests: TestRunResult
    ai_summary: LLMResult


@dataclass(slots=True)
class WorkingTreeReport:
    metrics: ChangeMetrics
    issues: list[Issue]
    tests: TestRunResult
    ai_summary: LLMResult


@dataclass(slots=True)
class GraphNode:
    node_id: str
    kind: str
    label: str
    path: str
    hotspot_score: int = 0


@dataclass(slots=True)
class GraphEdge:
    source: str
    target: str
    relation: str


@dataclass(slots=True)
class ProjectGraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
