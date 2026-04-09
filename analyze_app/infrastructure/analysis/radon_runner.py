from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from analyze_app.domain.entities import Issue
from analyze_app.shared.process import decode_output


class RadonRunner:
    def run(self, repo_path: Path) -> list[Issue]:
        complexity_issues = self._run_cc(repo_path)
        maintainability_issues = self._run_mi(repo_path)
        return [*complexity_issues, *maintainability_issues]

    def _run_cc(self, repo_path: Path) -> list[Issue]:
        command = self._build_command("cc")
        completed = subprocess.run(command, cwd=repo_path, text=False, capture_output=True)
        stdout = decode_output(completed.stdout)
        stderr = decode_output(completed.stderr)

        if completed.returncode != 0:
            return [
                Issue(
                    tool="radon",
                    message=stderr.strip() or "radon cc execution failed",
                    severity="error",
                )
            ]
        if not stdout.strip():
            return []

        try:
            payload: dict[str, list[dict[str, Any]]] = json.loads(stdout)
        except json.JSONDecodeError:
            return [Issue(tool="radon", message="radon cc returned invalid JSON", severity="error")]

        issues: list[Issue] = []
        for file_name, blocks in payload.items():
            for block in blocks:
                rank = block.get("rank", "?")
                complexity = block.get("complexity", "?")
                block_name = block.get("name", "<module>")
                block_type = block.get("type", "block")
                issues.append(
                    Issue(
                        tool="radon",
                        file=file_name,
                        line=block.get("lineno"),
                        severity="warning",
                        message=f"{block_type} '{block_name}' has complexity {complexity} (rank {rank})",
                    )
                )
        return issues

    def _run_mi(self, repo_path: Path) -> list[Issue]:
        command = self._build_command("mi")
        completed = subprocess.run(command, cwd=repo_path, text=False, capture_output=True)
        stdout = decode_output(completed.stdout)
        stderr = decode_output(completed.stderr)

        if completed.returncode != 0:
            return [
                Issue(
                    tool="radon",
                    message=stderr.strip() or "radon mi execution failed",
                    severity="error",
                )
            ]
        if not stdout.strip():
            return []

        try:
            payload: dict[str, Any] = json.loads(stdout)
        except json.JSONDecodeError:
            return [Issue(tool="radon", message="radon mi returned invalid JSON", severity="error")]

        issues: list[Issue] = []
        for file_name, details in payload.items():
            if isinstance(details, dict):
                score = details.get("mi", "?")
                rank = details.get("rank", "?")
            else:
                score = details
                rank = "?"
            issues.append(
                Issue(
                    tool="radon",
                    file=file_name,
                    severity="warning",
                    message=f"Maintainability index is {score} (rank {rank})",
                )
            )
        return issues

    @staticmethod
    def _build_command(metric: str) -> list[str]:
        return [sys.executable, "-m", "radon", metric, ".", "-j"]
