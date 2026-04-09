from __future__ import annotations

import subprocess
import time
from pathlib import Path

from analyze_app.domain.entities import TestRunResult
from analyze_app.shared.process import decode_output


class PytestRunner:
    def run(self, repo_path: Path) -> TestRunResult:
        start = time.perf_counter()
        try:
            completed = subprocess.run(["pytest", "-q"], cwd=repo_path, text=False, capture_output=True)
        except FileNotFoundError:
            duration = time.perf_counter() - start
            return TestRunResult(duration_sec=duration, failed_tests=["pytest not found in PATH"])
        duration = time.perf_counter() - start
        stdout = decode_output(completed.stdout)

        summary_line = ""
        for line in reversed(stdout.splitlines()):
            if " in " in line and ("passed" in line or "failed" in line or "skipped" in line):
                summary_line = line
                break

        result = TestRunResult(duration_sec=duration)
        if not summary_line:
            if completed.returncode != 0:
                result.failed_tests.append("pytest execution failed")
            return result

        for segment in summary_line.split(","):
            segment = segment.strip()
            if segment.endswith("passed"):
                result.passed = int(segment.split()[0])
            elif segment.endswith("failed"):
                result.failed = int(segment.split()[0])
            elif segment.endswith("skipped"):
                result.skipped = int(segment.split()[0])
        result.total = result.passed + result.failed + result.skipped

        if completed.returncode != 0:
            failures = [line for line in stdout.splitlines() if line.startswith("FAILED ")]
            result.failed_tests.extend(failures)
        return result
