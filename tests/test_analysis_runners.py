from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from analyze_app.infrastructure.analysis import pytest_runner, radon_runner, ruff_runner, vulture_runner
from analyze_app.infrastructure.analysis.duplication_runner import DuplicationRunner
from analyze_app.infrastructure.analysis.pytest_runner import PytestRunner
from analyze_app.infrastructure.analysis.radon_runner import RadonRunner
from analyze_app.infrastructure.analysis.ruff_runner import RuffRunner
from analyze_app.infrastructure.analysis.vulture_runner import VultureRunner


def _completed(stdout: object, *, returncode: int = 0, stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        returncode=returncode,
        stdout=json.dumps(stdout).encode("utf-8"),
        stderr=stderr.encode("utf-8"),
    )


def test_radon_cc_reports_per_file_parse_errors(monkeypatch) -> None:
    payload = {
        "bad.py": {"error": "invalid decimal literal (<unknown>, line 11)"},
        "ok.py": [
            {
                "rank": "A",
                "complexity": 1,
                "name": "simple",
                "type": "function",
                "lineno": 3,
            }
        ],
    }

    monkeypatch.setattr(radon_runner.subprocess, "run", lambda *args, **kwargs: _completed(payload))

    issues = RadonRunner()._run_cc(Path("."))

    assert any(issue.file == "bad.py" and "could not analyze file" in issue.message for issue in issues)
    assert any(issue.file == "ok.py" and "simple" in issue.message for issue in issues)


def test_ruff_reports_unexpected_issue_payload(monkeypatch) -> None:
    payload = [
        {"message": "valid", "filename": "ok.py", "location": {"row": 4}},
        "not an issue object",
    ]

    monkeypatch.setattr(ruff_runner.subprocess, "run", lambda *args, **kwargs: _completed(payload))

    issues = RuffRunner().run(Path("."))

    assert any(issue.file == "ok.py" and issue.line == 4 for issue in issues)
    assert any(issue.message == "ruff returned unexpected issue payload" for issue in issues)


def test_pytest_runner_streams_completed_tests(monkeypatch) -> None:
    lines = [
        b"tests/test_sample.py::test_one PASSED [ 50%]\n",
        b"tests/test_sample.py::test_two FAILED [100%]\n",
        b"FAILED tests/test_sample.py::test_two - AssertionError\n",
    ]

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = iter(lines)
            self.returncode: int | None = None

        def wait(self) -> int:
            self.returncode = 1
            return self.returncode

    monkeypatch.setattr(pytest_runner.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    seen: list[tuple[str, str]] = []
    result = PytestRunner().run(Path("."), on_test_result=lambda nodeid, status: seen.append((nodeid, status)))

    assert seen == [
        ("tests/test_sample.py::test_one", "PASSED"),
        ("tests/test_sample.py::test_two", "FAILED"),
    ]
    assert result.total == 2
    assert result.passed == 1
    assert result.failed == 1
    assert "tests/test_sample.py::test_two" in result.failed_tests


def test_vulture_runner_scans_only_selected_python_files(monkeypatch, tmp_path) -> None:
    (tmp_path / "main.py").write_text("def used():\n    return 1\n", encoding="utf-8")
    hidden_dir = tmp_path / ".venv"
    hidden_dir.mkdir()
    (hidden_dir / "vendor.py").write_text("def unused():\n    return 2\n", encoding="utf-8")

    seen_command: list[str] = []

    def fake_run(command, *args, **kwargs):
        seen_command.extend(command)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(vulture_runner.subprocess, "run", fake_run)

    issues = VultureRunner().run(tmp_path, tracked_files=["main.py", ".venv/vendor.py", "missing.py"])

    assert issues == []
    assert seen_command[:2] == ["vulture", "main.py"]
    assert "." not in seen_command
    assert ".venv/vendor.py" not in seen_command
    assert "missing.py" not in seen_command


def test_duplication_runner_scans_only_selected_python_files(tmp_path) -> None:
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    hidden_dir = tmp_path / ".venv"
    hidden_dir.mkdir()
    duplicate_block = "\n".join(f"line_{index} = {index}" for index in range(6))
    (hidden_dir / "first.py").write_text(duplicate_block, encoding="utf-8")
    (hidden_dir / "second.py").write_text(duplicate_block, encoding="utf-8")

    result = DuplicationRunner().run(tmp_path, tracked_files=["main.py"])

    assert result.duplicate_groups == 0
    assert result.duplication_pct == 0.0


def test_duplication_runner_reports_duplicate_locations(tmp_path) -> None:
    duplicate_block = "\n".join(f"value_{index} = {index}" for index in range(6))
    (tmp_path / "first.py").write_text(f"{duplicate_block}\n", encoding="utf-8")
    (tmp_path / "second.py").write_text(f"\n{duplicate_block}\n", encoding="utf-8")

    result = DuplicationRunner().run(tmp_path, tracked_files=["first.py", "second.py"])

    assert result.duplicate_groups >= 1
    assert result.duplicate_blocks
    locations = {(location.file, location.line) for location in result.duplicate_blocks[0].locations}
    assert ("first.py", 1) in locations
    assert ("second.py", 2) in locations
