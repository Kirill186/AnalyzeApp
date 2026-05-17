from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from analyze_app.infrastructure.analysis import pytest_runner, radon_runner, ruff_runner
from analyze_app.infrastructure.analysis.pytest_runner import PytestRunner
from analyze_app.infrastructure.analysis.radon_runner import RadonRunner
from analyze_app.infrastructure.analysis.ruff_runner import RuffRunner


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
