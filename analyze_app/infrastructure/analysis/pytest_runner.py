from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from analyze_app.domain.entities import TestRunResult
from analyze_app.infrastructure.analysis.python_environment import (
    DependencyInstallationDeclined,
    ManagedPythonEnvironment,
    PreparedPythonEnvironment,
    PythonEnvironmentError,
)
from analyze_app.shared.process import decode_output


TestProgressCallback = Callable[[str, str], None]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_TEST_RESULT_RE = re.compile(
    r"^(?P<nodeid>.+?)\s+(?P<status>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS|XFAILED|XPASSED)"
    r"(?:\s+\[[^\]]+\])?$"
)
_SUMMARY_COUNT_RE = re.compile(
    r"(?P<count>\d+)\s+(?P<kind>passed|failed|skipped|xfailed|xpassed|error|errors)\b"
)
_SUMMARY_LINE_RE = re.compile(r"^=+\s*(?P<body>.*?)\s*=+$")
_SHORT_SUMMARY_FAILURE_RE = re.compile(r"^(?P<status>FAILED|ERROR)\s+(?P<target>\S+)")


@dataclass(slots=True)
class _SummaryFailure:
    status: str
    target: str
    message: str


class PytestRunner:
    def __init__(
        self,
        python_environment: ManagedPythonEnvironment | None = None,
        *,
        use_managed_environment: bool = True,
        install_dependencies: bool = True,
    ) -> None:
        self.python_environment = python_environment or ManagedPythonEnvironment()
        self.use_managed_environment = use_managed_environment
        self.install_dependencies = install_dependencies

    def run(self, repo_path: Path, on_test_result: TestProgressCallback | None = None) -> TestRunResult:
        start = time.perf_counter()
        try:
            python = self._prepare_python(repo_path)
        except DependencyInstallationDeclined as error:
            duration = time.perf_counter() - start
            return TestRunResult(duration_sec=duration, not_run_reason=str(error))
        except PythonEnvironmentError as error:
            duration = time.perf_counter() - start
            return TestRunResult(duration_sec=duration, not_run_reason=str(error))

        try:
            completed = subprocess.Popen(
                [str(python.executable), "-m", "pytest", "-vv", "--tb=short", "--color=no"],
                cwd=repo_path,
                text=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env={**python.env, "PYTHONUNBUFFERED": "1", "PYTEST_ADDOPTS": ""},
            )
        except FileNotFoundError:
            duration = time.perf_counter() - start
            return TestRunResult(duration_sec=duration, not_run_reason=f"Python executable not found: {python.executable}")

        result = TestRunResult()
        output_lines: list[str] = []
        if completed.stdout:
            for raw_line in completed.stdout:
                line = decode_output(raw_line).rstrip("\r\n")
                output_lines.append(line)
                parsed = _parse_test_result_line(line)
                if not parsed:
                    continue
                nodeid, status = parsed
                _record_test_result(result, nodeid, status)
                if on_test_result:
                    try:
                        on_test_result(nodeid, status)
                    except Exception:  # noqa: BLE001
                        pass

        completed.wait()
        duration = time.perf_counter() - start
        result.duration_sec = duration
        stdout = "\n".join(output_lines)

        summary_counts = _parse_summary_counts(output_lines)
        if summary_counts.total > 0:
            result.passed = summary_counts.passed
            result.failed = summary_counts.failed
            result.skipped = summary_counts.skipped
            result.total = summary_counts.total

        if result.total == 0:
            if completed.returncode:
                if "No module named pytest" in stdout:
                    result.not_run_reason = "pytest is not installed for the selected Python"
                else:
                    result.not_run_reason = "pytest execution failed"
            return result

        if completed.returncode:
            failures = _summary_failures(output_lines)
            for failure in failures:
                if failure.target not in result.failed_tests:
                    result.failed_tests.append(failure.target)
                reason = failure.message or _fallback_failure_reason(output_lines, failure.target)
                if reason:
                    result.failed_reasons[failure.target] = reason
        return result

    def _prepare_python(self, repo_path: Path) -> PreparedPythonEnvironment:
        if self.use_managed_environment:
            return self.python_environment.prepare(repo_path, install_dependencies=self.install_dependencies)
        return PreparedPythonEnvironment(Path(sys.executable), dict(os.environ), managed=False)


def _parse_test_result_line(line: str) -> tuple[str, str] | None:
    clean = _ANSI_RE.sub("", line).strip()
    match = _TEST_RESULT_RE.match(clean)
    if not match:
        return None
    nodeid = match.group("nodeid").strip()
    if "::" not in nodeid:
        return None
    return nodeid, match.group("status")


def _record_test_result(result: TestRunResult, nodeid: str, status: str) -> None:
    result.total += 1
    if status in {"PASSED", "XPASS", "XPASSED"}:
        result.passed += 1
    elif status in {"FAILED", "ERROR"}:
        result.failed += 1
        result.failed_tests.append(nodeid)
        result.failed_reasons.setdefault(nodeid, status.title())
    elif status in {"SKIPPED", "XFAIL", "XFAILED"}:
        result.skipped += 1


def _apply_summary_counts(result: TestRunResult, stdout: str) -> None:
    summary_counts = _parse_summary_counts(stdout.splitlines())
    result.passed += summary_counts.passed
    result.failed += summary_counts.failed
    result.skipped += summary_counts.skipped
    result.total = result.passed + result.failed + result.skipped


def _parse_summary_counts(output_lines: list[str]) -> TestRunResult:
    result = TestRunResult()
    for line in reversed(output_lines):
        clean = _ANSI_RE.sub("", line).strip()
        match = _SUMMARY_LINE_RE.match(clean)
        if not match:
            continue
        body = match.group("body")
        if not _SUMMARY_COUNT_RE.search(body):
            continue
        _apply_summary_body_counts(result, body)
        return result
    return result


def _apply_summary_body_counts(result: TestRunResult, body: str) -> None:
    for match in _SUMMARY_COUNT_RE.finditer(body):
        count = int(match.group("count"))
        kind = match.group("kind")
        if kind in {"passed", "xpassed"}:
            result.passed += count
        elif kind in {"failed", "error", "errors"}:
            result.failed += count
        elif kind in {"skipped", "xfailed"}:
            result.skipped += count
    result.total = result.passed + result.failed + result.skipped


def _summary_failures(output_lines: list[str]) -> list[_SummaryFailure]:
    failures: list[_SummaryFailure] = []
    in_short_summary = False
    for line in output_lines:
        clean = _ANSI_RE.sub("", line).strip()
        if "short test summary info" in clean:
            in_short_summary = True
            continue
        if not in_short_summary:
            continue
        match = _SHORT_SUMMARY_FAILURE_RE.match(clean)
        if not match:
            continue
        message = ""
        marker = " - "
        if marker in clean:
            message = clean.split(marker, 1)[1].strip()
        failures.append(
            _SummaryFailure(
                status=match.group("status"),
                target=match.group("target"),
                message=message,
            )
        )
    return failures


def _fallback_failure_reason(output_lines: list[str], target: str) -> str:
    error_lines = [
        _ANSI_RE.sub("", line).strip()[4:].strip()
        for line in output_lines
        if _ANSI_RE.sub("", line).strip().startswith("E   ")
    ]
    if len(error_lines) == 1:
        return error_lines[0]
    if not error_lines:
        return ""
    target_index = next(
        (index for index, line in enumerate(output_lines) if target.replace("/", "\\") in line or target in line),
        -1,
    )
    if target_index >= 0:
        for line in output_lines[target_index:]:
            clean = _ANSI_RE.sub("", line).strip()
            if clean.startswith("E   "):
                return clean[4:].strip()
    return error_lines[-1]
