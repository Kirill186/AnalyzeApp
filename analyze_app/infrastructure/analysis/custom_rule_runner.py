from __future__ import annotations

import ast
import re
from pathlib import Path

from analyze_app.domain.entities import Issue
from analyze_app.infrastructure.analysis.file_selection import select_python_files
from analyze_app.infrastructure.analysis.ruff_settings import RegexRule, RuffSettings


class CustomRuleRunner:
    def __init__(self, settings: RuffSettings) -> None:
        self.settings = settings

    def run(self, repo_path: Path, tracked_files: list[str] | None = None) -> list[Issue]:
        if not self.settings.custom_rules_enabled:
            return []

        forbidden_calls = {call.strip() for call in self.settings.forbidden_calls if call.strip()}
        regex_rules = [rule for rule in self.settings.regex_rules if rule.enabled and rule.pattern.strip()]
        if not forbidden_calls and not regex_rules:
            return []

        issues: list[Issue] = []
        for rel_path in select_python_files(repo_path, tracked_files):
            file_path = repo_path.joinpath(*rel_path.split("/"))
            try:
                source = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                source = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError as error:
                issues.append(
                    Issue(
                        tool="custom-rule",
                        file=rel_path,
                        message=f"[AX000] custom rule could not read file: {error}",
                        severity="error",
                    )
                )
                continue

            issues.extend(self._run_regex_rules(rel_path, source, regex_rules))
            if forbidden_calls:
                issues.extend(self._run_forbidden_call_rules(rel_path, source, forbidden_calls))

        return issues

    @staticmethod
    def _run_regex_rules(rel_path: str, source: str, rules: list[RegexRule]) -> list[Issue]:
        compiled_rules: list[tuple[RegexRule, re.Pattern[str]]] = []
        issues: list[Issue] = []
        for rule in rules:
            try:
                compiled_rules.append((rule, re.compile(rule.pattern)))
            except re.error as error:
                issues.append(
                    Issue(
                        tool="custom-rule",
                        file=rel_path,
                        message=f"[AX002] invalid custom regex '{rule.pattern}': {error}",
                        severity="error",
                    )
                )

        for line_no, line in enumerate(source.splitlines(), start=1):
            for rule, pattern in compiled_rules:
                if not pattern.search(line):
                    continue
                message = rule.message or f"custom pattern matched: {rule.pattern}"
                issues.append(
                    Issue(
                        tool="custom-rule",
                        file=rel_path,
                        line=line_no,
                        message=f"[AX002] {message}",
                        severity="warning",
                    )
                )
        return issues

    @staticmethod
    def _run_forbidden_call_rules(rel_path: str, source: str, forbidden_calls: set[str]) -> list[Issue]:
        try:
            tree = ast.parse(source, filename=rel_path)
        except SyntaxError:
            return []

        issues: list[Issue] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node.func)
            if not call_name or call_name not in forbidden_calls:
                continue
            issues.append(
                Issue(
                    tool="custom-rule",
                    file=rel_path,
                    line=node.lineno,
                    message=f"[AX001] forbidden call: {call_name}(...)",
                    severity="warning",
                )
            )
        return issues


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = [node.attr]
        value = node.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        else:
            return ""
        return ".".join(reversed(parts))
    return ""
