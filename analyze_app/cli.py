from __future__ import annotations

import argparse
import time
from pathlib import Path

from analyze_app.application.orchestrators.analysis_job_orchestrator import AnalysisJobOrchestrator
from analyze_app.application.use_cases.build_project_map import BuildProjectMapUseCase
from analyze_app.application.use_cases.commit_and_push import CommitAndPushUseCase
from analyze_app.application.use_cases.get_commit_report import CommitReportUseCase
from analyze_app.application.use_cases.get_working_tree_report import WorkingTreeReportUseCase
from analyze_app.application.use_cases.import_repository import ImportRepositoryUseCase
from analyze_app.application.use_cases.list_commits import ListCommitsUseCase
from analyze_app.infrastructure.ai.ollama_backend import OllamaBackend
from analyze_app.infrastructure.analysis.map.ast_map_builder import AstMapBuilder
from analyze_app.infrastructure.analysis.pytest_runner import PytestRunner
from analyze_app.infrastructure.analysis.ruff_runner import RuffRunner
from analyze_app.infrastructure.git.backend import GitBackend
from analyze_app.infrastructure.storage.sqlite_store import SqliteStore
from analyze_app.shared.config import DEFAULT_CONFIG


def _build_services(db_path: Path | None = None) -> tuple[GitBackend, SqliteStore, OllamaBackend, RuffRunner, PytestRunner]:
    config = DEFAULT_CONFIG
    store = SqliteStore(db_path or config.db_path)
    git_backend = GitBackend()
    ai_backend = OllamaBackend(config.ollama_url, config.ollama_model)
    return git_backend, store, ai_backend, RuffRunner(), PytestRunner()


def cmd_import(args: argparse.Namespace) -> None:
    git_backend, store, *_ = _build_services(args.db)
    use_case = ImportRepositoryUseCase(git_backend, store, DEFAULT_CONFIG.clone_root)
    repo_id, repo_path = use_case.execute(args.source)
    print(f"repo_id={repo_id} path={repo_path}")


def cmd_commits(args: argparse.Namespace) -> None:
    git_backend, *_ = _build_services(args.db)
    use_case = ListCommitsUseCase(git_backend)
    commits = use_case.execute(Path(args.repo_path), limit=args.limit)
    for commit in commits:
        print(f"{commit.hash[:10]} {commit.authored_at.isoformat()} {commit.author} :: {commit.message}")


def cmd_report(args: argparse.Namespace) -> None:
    git_backend, store, ai_backend, ruff_runner, pytest_runner = _build_services(args.db)
    use_case = CommitReportUseCase(git_backend, ruff_runner, pytest_runner, ai_backend, store)
    report = use_case.execute(args.repo_id, Path(args.repo_path), args.commit_hash, use_cache=not args.no_cache)

    print(f"commit: {report.commit_hash}")
    print(
        "metrics: "
        f"files={report.metrics.files_changed} +{report.metrics.lines_added} -{report.metrics.lines_deleted}"
    )
    print(f"issues: {len(report.issues)}")
    print(f"tests: total={report.tests.total} failed={report.tests.failed}")
    print(f"ai_model: {report.ai_summary.model_info}")
    print("ai_summary:")
    print(report.ai_summary.summary)
    print("evidence_blocks:")
    for evidence in report.ai_summary.evidence:
        print(f"- {evidence.file}: {evidence.reason}")


def cmd_working_tree_report(args: argparse.Namespace) -> None:
    git_backend, store, ai_backend, ruff_runner, pytest_runner = _build_services(args.db)
    use_case = WorkingTreeReportUseCase(git_backend, ruff_runner, pytest_runner, ai_backend, store)
    report = use_case.execute(args.repo_id, Path(args.repo_path), use_cache=not args.no_cache)
    print("working tree report")
    print(f"metrics: files={report.metrics.files_changed} +{report.metrics.lines_added} -{report.metrics.lines_deleted}")
    print(f"issues: {len(report.issues)}")
    print(f"tests: total={report.tests.total} failed={report.tests.failed}")
    print(f"ai_model: {report.ai_summary.model_info}")
    print("evidence_blocks:")
    for evidence in report.ai_summary.evidence:
        print(f"- {evidence.file}: {evidence.reason}")


def cmd_project_map(args: argparse.Namespace) -> None:
    git_backend, store, *_ = _build_services(args.db)
    use_case = BuildProjectMapUseCase(git_backend, AstMapBuilder(), store)
    project_map = use_case.execute(args.repo_id, Path(args.repo_path), max_commits=args.max_commits, use_cache=not args.no_cache)

    print(f"project map: nodes={len(project_map.nodes)} edges={len(project_map.edges)}")
    hot_files = sorted((node for node in project_map.nodes if node.kind == "file"), key=lambda n: n.hotspot_score, reverse=True)
    print("top hotspots:")
    for node in hot_files[: args.top]:
        print(f"- {node.path}: {node.hotspot_score}")
    if not hot_files:
        print("(не найдено .py файлов внутри указанного repo_path)")
        print(f"проверьте путь: {Path(args.repo_path).resolve()}")


def cmd_commit_push(args: argparse.Namespace) -> None:
    git_backend, *_ = _build_services(args.db)
    use_case = CommitAndPushUseCase(git_backend)
    commit_hash = use_case.execute(
        repo_path=Path(args.repo_path),
        message=args.message,
        push=not args.no_push,
        paths=args.paths,
    )
    print(f"created commit: {commit_hash}")
    if args.no_push:
        print("push skipped")


def cmd_enqueue_jobs(args: argparse.Namespace) -> None:
    git_backend, store, ai_backend, ruff_runner, pytest_runner = _build_services(args.db)
    commit_report = CommitReportUseCase(git_backend, ruff_runner, pytest_runner, ai_backend, store)
    working_tree_report = WorkingTreeReportUseCase(git_backend, ruff_runner, pytest_runner, ai_backend, store)
    project_map = BuildProjectMapUseCase(git_backend, AstMapBuilder(), store)

    orchestrator = AnalysisJobOrchestrator(commit_report, working_tree_report, project_map)
    orchestrator.start()
    try:
        if args.commit_hash:
            accepted = orchestrator.enqueue_commit_analysis(args.repo_id, Path(args.repo_path), args.commit_hash)
            print(f"commit_analysis enqueued={accepted}")
        accepted = orchestrator.enqueue_working_tree_analysis(args.repo_id, Path(args.repo_path))
        print(f"working_tree_analysis enqueued={accepted}")
        accepted = orchestrator.enqueue_map_rebuild(args.repo_id, Path(args.repo_path))
        print(f"map_rebuild enqueued={accepted}")
        time.sleep(args.wait_sec)
    finally:
        orchestrator.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="AnalyzeApp CLI")
    parser.add_argument("--db", type=Path, default=None, help="Path to SQLite DB")
    subparsers = parser.add_subparsers(required=True)

    import_parser = subparsers.add_parser("import", help="Import repository by path or URL")
    import_parser.add_argument("source")
    import_parser.set_defaults(func=cmd_import)

    commits_parser = subparsers.add_parser("commits", help="List repository commits")
    commits_parser.add_argument("repo_path")
    commits_parser.add_argument("--limit", type=int, default=20)
    commits_parser.set_defaults(func=cmd_commits)

    report_parser = subparsers.add_parser("report", help="Build commit report")
    report_parser.add_argument("repo_id", type=int)
    report_parser.add_argument("repo_path")
    report_parser.add_argument("commit_hash")
    report_parser.add_argument("--no-cache", action="store_true")
    report_parser.set_defaults(func=cmd_report)

    working_tree_parser = subparsers.add_parser("working-tree-report", help="Build report for working tree")
    working_tree_parser.add_argument("repo_id", type=int)
    working_tree_parser.add_argument("repo_path")
    working_tree_parser.add_argument("--no-cache", action="store_true")
    working_tree_parser.set_defaults(func=cmd_working_tree_report)

    map_parser = subparsers.add_parser("project-map", help="Build AST project map with hotspots")
    map_parser.add_argument("repo_id", type=int)
    map_parser.add_argument("repo_path")
    map_parser.add_argument("--max-commits", type=int, default=200)
    map_parser.add_argument("--top", type=int, default=10)
    map_parser.add_argument("--no-cache", action="store_true")
    map_parser.set_defaults(func=cmd_project_map)

    commit_push_parser = subparsers.add_parser("commit-push", help="Stage, commit and optionally push")
    commit_push_parser.add_argument("repo_path")
    commit_push_parser.add_argument("-m", "--message", required=True)
    commit_push_parser.add_argument("--paths", nargs="*")
    commit_push_parser.add_argument("--no-push", action="store_true")
    commit_push_parser.set_defaults(func=cmd_commit_push)

    jobs_parser = subparsers.add_parser("enqueue-jobs", help="Run background analysis jobs")
    jobs_parser.add_argument("repo_id", type=int)
    jobs_parser.add_argument("repo_path")
    jobs_parser.add_argument("--commit-hash")
    jobs_parser.add_argument("--wait-sec", type=float, default=1.0)
    jobs_parser.set_defaults(func=cmd_enqueue_jobs)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
