from __future__ import annotations

import json
import subprocess
from pathlib import Path

from analyze_app.domain.entities import Issue
from analyze_app.shared.process import decode_output


class RuffRunner:
    def run(self, repo_path: Path) -> list[Issue]:
        command = ["ruff", "check", ".", "--output-format", "json"]
        try:
            completed = subprocess.run(command, cwd=repo_path, text=False, capture_output=True)
        except FileNotFoundError:
            return [Issue(tool="ruff", message="ruff not found in PATH", severity="warning")]
        stdout = decode_output(completed.stdout)
        stderr = decode_output(completed.stderr)

        if completed.returncode not in (0, 1):
            return [Issue(tool="ruff", message=stderr.strip() or "ruff execution failed", severity="error")]
        if not stdout.strip():
            return []

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return [Issue(tool="ruff", message="ruff returned invalid JSON", severity="error")]
        if not isinstance(payload, list):
            return [Issue(tool="ruff", message="ruff returned unexpected JSON", severity="error")]

        issues: list[Issue] = []
        for item in payload:
            if not isinstance(item, dict):
                issues.append(Issue(tool="ruff", message="ruff returned unexpected issue payload", severity="error"))
                continue
            location = item.get("location") or {}
            if not isinstance(location, dict):
                location = {}
            issues.append(
                Issue(
                    tool="ruff",
                    message=item.get("message", "Unknown issue"),
                    file=item.get("filename"),
                    line=location.get("row"),
                    severity="warning",
                )
            )
        return issues
