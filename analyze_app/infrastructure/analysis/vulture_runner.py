from __future__ import annotations

import subprocess
from pathlib import Path

from analyze_app.domain.entities import Issue
from analyze_app.shared.process import decode_output


class VultureRunner:
    def __init__(self, min_confidence: int = 80) -> None:
        self.min_confidence = min_confidence

    def run(self, repo_path: Path) -> list[Issue]:
        command = ["vulture", ".", "--min-confidence", str(self.min_confidence)]
        completed = subprocess.run(command, cwd=repo_path, text=False, capture_output=True)
        stdout = decode_output(completed.stdout)
        stderr = decode_output(completed.stderr)

        if completed.returncode not in (0, 3):
            return [Issue(tool="vulture", message=stderr.strip() or "vulture execution failed", severity="error")]
        if not stdout.strip():
            return []

        issues: list[Issue] = []
        for line in stdout.splitlines():
            parsed = self._parse_output_line(line)
            if not parsed:
                continue
            file_name, line_no, message = parsed
            issues.append(
                Issue(
                    tool="vulture",
                    file=file_name,
                    line=line_no,
                    severity="warning",
                    message=message,
                )
            )

        return issues

    @staticmethod
    def _parse_output_line(line: str) -> tuple[str, int | None, str] | None:
        parts = line.split(":", maxsplit=2)
        if len(parts) < 3:
            return None

        file_name = parts[0].strip() or None
        line_raw = parts[1].strip()
        message = parts[2].strip()
        if not file_name or not message:
            return None

        line_no = int(line_raw) if line_raw.isdigit() else None
        return file_name, line_no, message
