from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from analyze_app.domain.entities import TestRunResult
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


class PytestRunner:
    def run(self, repo_path: Path, on_test_result: TestProgressCallback | None = None) -> TestRunResult:
        start = time.perf_counter()
        try:
            completed = subprocess.Popen(
                ["pytest", "-vv", "--tb=short", "--color=no"],
                cwd=repo_path,
                text=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        except FileNotFoundError:
            duration = time.perf_counter() - start
            return TestRunResult(duration_sec=duration, failed_tests=["pytest not found in PATH"])

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

        if result.total == 0:
            _apply_summary_counts(result, stdout)

        if result.total == 0:
            if completed.returncode:
                result.failed_tests.append("pytest execution failed")
            return result

        if completed.returncode:
            failures = [line for line in stdout.splitlines() if line.startswith("FAILED ")]
            for failure in failures:
                if failure not in result.failed_tests:
                    result.failed_tests.append(failure)
        return result


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
    elif status in {"SKIPPED", "XFAIL", "XFAILED"}:
        result.skipped += 1


def _apply_summary_counts(result: TestRunResult, stdout: str) -> None:
    for match in _SUMMARY_COUNT_RE.finditer(stdout):
        count = int(match.group("count"))
        kind = match.group("kind")
        if kind in {"passed", "xpassed"}:
            result.passed += count
        elif kind in {"failed", "error", "errors"}:
            result.failed += count
        elif kind in {"skipped", "xfailed"}:
            result.skipped += count
    result.total = result.passed + result.failed + result.skipped
