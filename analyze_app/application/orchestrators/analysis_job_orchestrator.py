from __future__ import annotations

from pathlib import Path

from analyze_app.application.use_cases.build_project_map import BuildProjectMapUseCase
from analyze_app.application.use_cases.get_commit_report import CommitReportUseCase
from analyze_app.application.use_cases.get_working_tree_report import WorkingTreeReportUseCase
from analyze_app.infrastructure.jobs.queue import AnalysisQueue, Job, QueueWorker


class AnalysisJobOrchestrator:
    def __init__(
        self,
        commit_report_use_case: CommitReportUseCase,
        working_tree_report_use_case: WorkingTreeReportUseCase,
        project_map_use_case: BuildProjectMapUseCase,
    ) -> None:
        self.queue = AnalysisQueue()
        self.commit_report_use_case = commit_report_use_case
        self.working_tree_report_use_case = working_tree_report_use_case
        self.project_map_use_case = project_map_use_case
        self.worker = QueueWorker(
            self.queue,
            handlers={
                "commit_analysis": self._handle_commit_analysis,
                "working_tree_analysis": self._handle_working_tree,
                "map_rebuild": self._handle_map,
            },
        )

    def start(self) -> None:
        self.worker.start()

    def stop(self) -> None:
        self.worker.stop()

    def enqueue_commit_analysis(self, repo_id: int, repo_path: Path, commit_hash: str) -> bool:
        key = f"{repo_id}:{commit_hash}:commit_analysis"
        return self.queue.enqueue(
            Job(
                job_type="commit_analysis",
                key=key,
                payload={"repo_id": repo_id, "repo_path": str(repo_path), "commit_hash": commit_hash},
            )
        )

    def enqueue_working_tree_analysis(self, repo_id: int, repo_path: Path) -> bool:
        key = f"{repo_id}:{repo_path}:working_tree"
        return self.queue.enqueue(
            Job(job_type="working_tree_analysis", key=key, payload={"repo_id": repo_id, "repo_path": str(repo_path)})
        )

    def enqueue_map_rebuild(self, repo_id: int, repo_path: Path) -> bool:
        key = f"{repo_id}:{repo_path}:map_rebuild"
        return self.queue.enqueue(Job(job_type="map_rebuild", key=key, payload={"repo_id": repo_id, "repo_path": str(repo_path)}))

    def _handle_commit_analysis(self, job: Job) -> None:
        self.commit_report_use_case.execute(
            repo_id=int(job.payload["repo_id"]),
            repo_path=Path(job.payload["repo_path"]),
            commit_hash=str(job.payload["commit_hash"]),
        )

    def _handle_working_tree(self, job: Job) -> None:
        self.working_tree_report_use_case.execute(
            repo_id=int(job.payload["repo_id"]),
            repo_path=Path(job.payload["repo_path"]),
        )

    def _handle_map(self, job: Job) -> None:
        self.project_map_use_case.execute(repo_id=int(job.payload["repo_id"]), repo_path=Path(job.payload["repo_path"]))
