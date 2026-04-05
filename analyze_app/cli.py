from __future__ import annotations

import argparse
from pathlib import Path

from analyze_app.application.use_cases.get_commit_report import CommitReportUseCase
from analyze_app.application.use_cases.import_repository import ImportRepositoryUseCase
from analyze_app.application.use_cases.list_commits import ListCommitsUseCase
from analyze_app.infrastructure.ai.ollama_backend import OllamaBackend
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


def main() -> None:
    parser = argparse.ArgumentParser(description="AnalyzeApp MVP CLI")
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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
