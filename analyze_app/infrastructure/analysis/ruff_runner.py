from __future__ import annotations

import json
import subprocess
from pathlib import Path

from analyze_app.domain.entities import Issue
from analyze_app.infrastructure.analysis.custom_rule_runner import CustomRuleRunner
from analyze_app.infrastructure.analysis.ruff_settings import RuffSettings
from analyze_app.shared.process import decode_output


class RuffRunner:
    def __init__(self, settings: RuffSettings | None = None) -> None:
        self.settings = settings or RuffSettings()

    def run(self, repo_path: Path, tracked_files: list[str] | None = None) -> list[Issue]:
        command = self._build_command()
        issues: list[Issue] = []
        try:
            completed = subprocess.run(command, cwd=repo_path, text=False, capture_output=True)
        except FileNotFoundError:
            issues.append(Issue(tool="ruff", message="ruff not found in PATH", severity="warning"))
            issues.extend(CustomRuleRunner(self.settings).run(repo_path, tracked_files=tracked_files))
            return issues
        stdout = decode_output(completed.stdout)
        stderr = decode_output(completed.stderr)

        if completed.returncode not in (0, 1):
            issues.append(Issue(tool="ruff", message=stderr.strip() or "ruff execution failed", severity="error"))
            issues.extend(CustomRuleRunner(self.settings).run(repo_path, tracked_files=tracked_files))
            return issues
        if stdout.strip():
            issues.extend(self._parse_output(stdout))

        issues.extend(CustomRuleRunner(self.settings).run(repo_path, tracked_files=tracked_files))
        return issues

    def _build_command(self) -> list[str]:
        command = ["ruff", "check", ".", "--output-format", "json"]
        select = ",".join(self.settings.select)
        ignore = ",".join(self.settings.ignore)
        if self.settings.mode == "extend":
            if select:
                command.extend(["--extend-select", select])
            if ignore:
                command.extend(["--extend-ignore", ignore])
        elif self.settings.mode == "override":
            if select:
                command.extend(["--select", select])
            if ignore:
                command.extend(["--ignore", ignore])
        if self.settings.preview:
            command.append("--preview")
        return command

    @staticmethod
    def _parse_output(stdout: str) -> list[Issue]:
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
            code = item.get("code")
            raw_message = str(item.get("message", "Unknown issue"))
            message = f"[{code}] {raw_message}" if code else raw_message
            issues.append(
                Issue(
                    tool="ruff",
                    message=message,
                    file=item.get("filename"),
                    line=location.get("row"),
                    severity="warning",
                )
            )
        return issues
