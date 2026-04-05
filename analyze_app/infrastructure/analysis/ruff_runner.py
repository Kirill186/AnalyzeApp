from __future__ import annotations

import json
import subprocess
from pathlib import Path

from analyze_app.domain.entities import Issue


class RuffRunner:
    def run(self, repo_path: Path) -> list[Issue]:
        command = ["ruff", "check", ".", "--output-format", "json"]
        completed = subprocess.run(command, cwd=repo_path, text=True, capture_output=True)
        if completed.returncode not in (0, 1):
            return [Issue(tool="ruff", message=completed.stderr.strip() or "ruff execution failed", severity="error")]
        if not completed.stdout.strip():
            return []
        payload = json.loads(completed.stdout)
        issues: list[Issue] = []
        for item in payload:
            location = item.get("location") or {}
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
