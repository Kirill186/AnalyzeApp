from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from analyze_app.domain.entities import TestRunResult


class PytestRunner:
    SUMMARY_RE = re.compile(r"=+\s*(.+?)\s*in\s*([0-9.]+)s\s*=+")

    def run(self, repo_path: Path) -> TestRunResult:
        start = time.perf_counter()
        completed = subprocess.run(["pytest", "-q"], cwd=repo_path, text=True, capture_output=True)
        duration = time.perf_counter() - start
        summary_line = ""
        for line in reversed(completed.stdout.splitlines()):
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
            failures = [line for line in completed.stdout.splitlines() if line.startswith("FAILED ")]
            result.failed_tests.extend(failures)
        return result
