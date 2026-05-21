from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from analyze_app.infrastructure.analysis import pytest_runner, radon_runner, ruff_runner, vulture_runner
from analyze_app.infrastructure.analysis.duplication_runner import DuplicationRunner
from analyze_app.infrastructure.analysis.python_environment import (
    ManagedPythonEnvironment,
    PreparedPythonEnvironment,
    PythonEnvironmentError,
)
from analyze_app.infrastructure.analysis.pytest_runner import PytestRunner
from analyze_app.infrastructure.analysis.radon_runner import RadonRunner
from analyze_app.infrastructure.analysis.ruff_runner import RuffRunner
from analyze_app.infrastructure.analysis.ruff_settings import RegexRule, RuffSettings
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


def test_ruff_runner_applies_rule_settings(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, *args, **kwargs):
        captured["command"] = command
        return _completed([])

    monkeypatch.setattr(ruff_runner.subprocess, "run", fake_run)

    settings = RuffSettings(
        mode="override",
        select=["E", "F", "B"],
        ignore=["E501", "S101"],
        preview=True,
    )
    RuffRunner(settings).run(Path("."))

    assert captured["command"] == [
        "ruff",
        "check",
        ".",
        "--output-format",
        "json",
        "--select",
        "E,F,B",
        "--ignore",
        "E501,S101",
        "--preview",
    ]


def test_ruff_runner_reports_forbidden_custom_call(monkeypatch, tmp_path) -> None:
    (tmp_path / "main.py").write_text("print('debug')\n", encoding="utf-8")
    monkeypatch.setattr(ruff_runner.subprocess, "run", lambda *args, **kwargs: _completed([]))

    issues = RuffRunner(RuffSettings(forbidden_calls=["print"])).run(tmp_path)

    assert any(
        issue.tool == "custom-rule"
        and issue.file == "main.py"
        and issue.line == 1
        and "forbidden call: print" in issue.message
        for issue in issues
    )


def test_ruff_runner_reports_custom_regex_rule(monkeypatch, tmp_path) -> None:
    (tmp_path / "main.py").write_text("value = 'TODO'\n", encoding="utf-8")
    monkeypatch.setattr(ruff_runner.subprocess, "run", lambda *args, **kwargs: _completed([]))

    settings = RuffSettings(regex_rules=[RegexRule(pattern="TODO", message="TODO is forbidden")])
    issues = RuffRunner(settings).run(tmp_path)

    assert any(
        issue.tool == "custom-rule"
        and issue.file == "main.py"
        and issue.line == 1
        and "TODO is forbidden" in issue.message
        for issue in issues
    )


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
    assert result.failed_reasons["tests/test_sample.py::test_two"] == "Failed"


def test_pytest_runner_uses_current_python_and_clears_addopts(monkeypatch) -> None:
    lines = [
        b"============================== 1 passed in 0.01s ==============================\n",
    ]
    captured: dict[str, object] = {}

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = iter(lines)
            self.returncode: int | None = None

        def wait(self) -> int:
            self.returncode = 0
            return self.returncode

    def fake_popen(command, *args, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs.get("env", {})
        return FakeProcess()

    monkeypatch.setattr(pytest_runner.sys, "executable", "python-from-app")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--lf")
    monkeypatch.setattr(pytest_runner.subprocess, "Popen", fake_popen)

    result = PytestRunner().run(Path("."))

    assert captured["command"][:3] == ["python-from-app", "-m", "pytest"]
    assert captured["env"]["PYTEST_ADDOPTS"] == ""
    assert result.total == 1
    assert result.passed == 1


def test_pytest_runner_counts_collection_errors_with_completed_tests(monkeypatch) -> None:
    lines = [
        b"tests/test_math.py::test_one PASSED [ 50%]\n",
        b"E   ModuleNotFoundError: No module named 'playwright'\n",
        b"=========================== short test summary info ===========================\n",
        b"ERROR tests/test_ui.py\n",
        b"========================= 1 passed, 1 error in 0.23s =========================\n",
    ]

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = iter(lines)
            self.returncode: int | None = None

        def wait(self) -> int:
            self.returncode = 1
            return self.returncode

    monkeypatch.setattr(pytest_runner.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    result = PytestRunner().run(Path("."))

    assert result.total == 2
    assert result.passed == 1
    assert result.failed == 1
    assert "tests/test_ui.py" in result.failed_tests
    assert result.failed_reasons["tests/test_ui.py"] == "ModuleNotFoundError: No module named 'playwright'"


def test_pytest_runner_summary_ignores_collection_preamble_counts(monkeypatch) -> None:
    lines = [
        b"collecting ... collected 15 items / 1 error\n",
        b"=========================== short test summary info ===========================\n",
        b"ERROR tests/test_ui.py\n",
        b"============================== 1 error in 0.43s ==============================\n",
    ]

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = iter(lines)
            self.returncode: int | None = None

        def wait(self) -> int:
            self.returncode = 1
            return self.returncode

    monkeypatch.setattr(pytest_runner.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    result = PytestRunner().run(Path("."))

    assert result.total == 1
    assert result.failed == 1
    assert result.failed_tests == ["tests/test_ui.py"]


def test_pytest_runner_records_short_summary_failure_reason(monkeypatch) -> None:
    lines = [
        b"tests/test_api.py::test_duckduckgo_instant_answer_api FAILED [100%]\n",
        b"=========================== short test summary info ===========================\n",
        b"FAILED tests/test_api.py::test_duckduckgo_instant_answer_api - assert 202 == 200\n",
        b"============================== 1 failed in 0.43s ==============================\n",
    ]

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = iter(lines)
            self.returncode: int | None = None

        def wait(self) -> int:
            self.returncode = 1
            return self.returncode

    monkeypatch.setattr(pytest_runner.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    result = PytestRunner().run(Path("."))

    nodeid = "tests/test_api.py::test_duckduckgo_instant_answer_api"
    assert result.failed_tests == [nodeid]
    assert result.failed_reasons[nodeid] == "assert 202 == 200"


def test_pytest_runner_uses_managed_python_environment(monkeypatch, tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    venv_python = tmp_path / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    lines = [
        b"============================== 1 passed in 0.01s ==============================\n",
    ]
    captured: dict[str, object] = {}

    class FakeEnvironment:
        def prepare(self, path: Path, *, install_dependencies: bool = True) -> PreparedPythonEnvironment:
            assert path == repo_path
            assert install_dependencies is True
            return PreparedPythonEnvironment(venv_python, {"PATH": "managed"}, managed=True)

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = iter(lines)
            self.returncode: int | None = None

        def wait(self) -> int:
            self.returncode = 0
            return self.returncode

    def fake_popen(command, *args, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs.get("env", {})
        return FakeProcess()

    monkeypatch.setattr(pytest_runner.subprocess, "Popen", fake_popen)

    result = PytestRunner(python_environment=FakeEnvironment()).run(repo_path)

    assert captured["command"][:3] == [str(venv_python), "-m", "pytest"]
    assert captured["env"]["PATH"] == "managed"
    assert captured["env"]["PYTEST_ADDOPTS"] == ""
    assert result.total == 1
    assert result.passed == 1


def test_pytest_runner_reports_environment_setup_failure() -> None:
    class FakeEnvironment:
        def prepare(self, path: Path, *, install_dependencies: bool = True) -> PreparedPythonEnvironment:
            raise PythonEnvironmentError("dependency install failed")

    result = PytestRunner(python_environment=FakeEnvironment()).run(Path("."))

    assert result.total == 0
    assert result.failed == 0
    assert result.failed_tests == []
    assert result.not_run_reason == "dependency install failed"


def test_managed_python_environment_installs_requirements_once(monkeypatch, tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "requirements.txt").write_text("pytest==7.3.1\nrequests==2.31.0\n", encoding="utf-8")
    env_root = tmp_path / "envs"
    commands: list[list[str]] = []

    def fake_run(command, *args, **kwargs):
        command = [str(part) for part in command]
        commands.append(command)
        if command[1:3] == ["-m", "venv"]:
            env_path = Path(command[-1])
            python_path = env_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            python_path.parent.mkdir(parents=True, exist_ok=True)
            python_path.write_text("", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(pytest_runner.sys, "executable", "python-from-app")
    monkeypatch.setattr("analyze_app.infrastructure.analysis.python_environment.sys.executable", "python-from-app")
    monkeypatch.setattr("analyze_app.infrastructure.analysis.python_environment.subprocess.run", fake_run)

    environment = ManagedPythonEnvironment(env_root)
    prepared = environment.prepare(repo_path)

    assert prepared.managed is True
    assert prepared.executable.exists()
    assert any(command[1:4] == ["-m", "pip", "install"] and "-r" in command for command in commands)

    commands.clear()
    environment.prepare(repo_path)

    assert commands == []


def test_managed_python_environment_can_decline_dependency_install(monkeypatch, tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "requirements.txt").write_text("pytest==7.3.1\n", encoding="utf-8")
    env_root = tmp_path / "envs"

    def fake_run(command, *args, **kwargs):
        command = [str(part) for part in command]
        if command[1:3] == ["-m", "venv"]:
            env_path = Path(command[-1])
            python_path = env_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            python_path.parent.mkdir(parents=True, exist_ok=True)
            python_path.write_text("", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("analyze_app.infrastructure.analysis.python_environment.sys.executable", "python-from-app")
    monkeypatch.setattr("analyze_app.infrastructure.analysis.python_environment.subprocess.run", fake_run)

    environment = ManagedPythonEnvironment(env_root)
    result = PytestRunner(python_environment=environment, install_dependencies=False).run(repo_path)

    assert result.total == 0
    assert result.failed == 0
    assert result.not_run_reason.startswith("Dependency installation was declined")


def test_managed_python_environment_delete_for_repo_removes_env(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    environment = ManagedPythonEnvironment(tmp_path / "envs")
    env_path = environment._env_path(repo_path.resolve())
    env_path.mkdir(parents=True)
    (env_path / ".analyze_env.json").write_text("{}", encoding="utf-8")

    assert environment.delete_for_repo(repo_path) is True
    assert not env_path.exists()
    assert environment.delete_for_repo(repo_path) is False


def test_managed_python_environment_delete_refuses_outside_env_root(tmp_path, monkeypatch) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    outside_path = tmp_path / "outside-env"
    outside_path.mkdir()
    environment = ManagedPythonEnvironment(tmp_path / "envs")
    monkeypatch.setattr(environment, "_env_path", lambda path: outside_path)

    with pytest.raises(PythonEnvironmentError, match="outside"):
        environment.delete_for_repo(repo_path)

    assert outside_path.exists()


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
