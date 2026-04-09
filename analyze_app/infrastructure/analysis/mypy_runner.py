from __future__ import annotations

import re
import subprocess
from pathlib import Path

from analyze_app.domain.entities import Issue
from analyze_app.shared.process import decode_output


_MYPY_LINE_RE = re.compile(
    r"^(?P<file>.*?):(?P<line>\d+)(?::(?P<column>\d+))?: (?P<kind>error|note): (?P<message>.*)$"
)


class MypyRunner:
    def run(self, repo_path: Path) -> list[Issue]:
        command = [
            "mypy",
            ".",
            "--hide-error-context",
            "--no-color-output",
            "--show-error-codes",
            "--no-error-summary",
        ]
        try:
            completed = subprocess.run(command, cwd=repo_path, text=False, capture_output=True)
        except FileNotFoundError:
            return [Issue(tool="mypy", message="mypy not found in PATH", severity="warning")]
        stdout = decode_output(completed.stdout)
        stderr = decode_output(completed.stderr)

        if completed.returncode not in (0, 1):
            return [Issue(tool="mypy", message=stderr.strip() or "mypy execution failed", severity="error")]
        if not stdout.strip():
            return []

        issues: list[Issue] = []
        for line in stdout.splitlines():
            match = _MYPY_LINE_RE.match(line.strip())
            if not match:
                continue

            kind = match.group("kind")
            severity = "error" if kind == "error" else "warning"
            issues.append(
                Issue(
                    tool="mypy",
                    file=match.group("file"),
                    line=int(match.group("line")),
                    severity=severity,
                    message=match.group("message").strip(),
                )
            )
        return issues
