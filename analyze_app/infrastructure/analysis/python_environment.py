from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from analyze_app.shared.config import DEFAULT_CONFIG
from analyze_app.shared.process import decode_output


_ENV_SCHEMA_VERSION = 1
_DEPENDENCY_FILES = ("requirements.txt",)
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class PythonEnvironmentError(RuntimeError):
    pass


class DependencyInstallationDeclined(PythonEnvironmentError):
    pass


@dataclass(slots=True)
class PreparedPythonEnvironment:
    executable: Path
    env: dict[str, str]
    managed: bool = False


@dataclass(slots=True)
class DependencyInstallPlan:
    env_path: Path
    manifests: list[Path]
    dependencies: list[str]


class ManagedPythonEnvironment:
    def __init__(self, env_root: Path | None = None) -> None:
        self.env_root = env_root or DEFAULT_CONFIG.python_env_root

    def prepare(self, repo_path: Path, *, install_dependencies: bool = True) -> PreparedPythonEnvironment:
        repo_path = repo_path.resolve()
        manifests = _dependency_manifests(repo_path)
        if not manifests:
            return PreparedPythonEnvironment(Path(sys.executable), dict(os.environ), managed=False)

        env_path = self._env_path(repo_path)
        python_executable = _venv_python(env_path)
        signature = _environment_signature(repo_path, manifests)
        marker_path = env_path / ".analyze_env.json"
        needs_install = not python_executable.exists() or _read_marker(marker_path) != signature

        if needs_install and not install_dependencies:
            raise DependencyInstallationDeclined(
                "Dependency installation was declined; pytest was not run for this repository."
            )

        if not python_executable.exists():
            self._create_venv(env_path)

        if _read_marker(marker_path) != signature:
            self._install_dependencies(repo_path, python_executable, manifests)
            _write_marker(marker_path, signature)

        return PreparedPythonEnvironment(
            executable=python_executable,
            env=_venv_env(env_path),
            managed=True,
        )

    def dependency_install_plan(self, repo_path: Path) -> DependencyInstallPlan | None:
        repo_path = repo_path.resolve()
        manifests = _dependency_manifests(repo_path)
        if not manifests:
            return None

        env_path = self._env_path(repo_path)
        marker_path = env_path / ".analyze_env.json"
        python_executable = _venv_python(env_path)
        signature = _environment_signature(repo_path, manifests)
        if python_executable.exists() and _read_marker(marker_path) == signature:
            return None

        return DependencyInstallPlan(
            env_path=env_path,
            manifests=manifests,
            dependencies=_dependency_lines(manifests),
        )

    def delete_for_repo(self, repo_path: Path) -> bool:
        env_path = self._env_path(repo_path.resolve()).resolve()
        env_root = self.env_root.resolve()
        try:
            env_path.relative_to(env_root)
        except ValueError as error:
            raise PythonEnvironmentError(f"Refusing to delete Python environment outside {env_root}") from error

        if not env_path.exists():
            return False
        if not env_path.is_dir():
            raise PythonEnvironmentError(f"Python environment path is not a directory: {env_path}")

        shutil.rmtree(env_path)
        return True

    def _env_path(self, repo_path: Path) -> Path:
        digest = hashlib.sha256(str(repo_path).encode("utf-8")).hexdigest()[:12]
        safe_name = _SAFE_NAME_RE.sub("-", repo_path.name).strip(".-") or "repo"
        return self.env_root / f"{safe_name}-{digest}"

    def _create_venv(self, env_path: Path) -> None:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [sys.executable, "-m", "venv", str(env_path)],
            text=False,
            capture_output=True,
        )
        if completed.returncode:
            raise PythonEnvironmentError(_format_command_error("create virtual environment", completed))

    def _install_dependencies(self, repo_path: Path, python_executable: Path, manifests: list[Path]) -> None:
        for manifest in manifests:
            completed = subprocess.run(
                [
                    str(python_executable),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "-r",
                    str(manifest.relative_to(repo_path)),
                ],
                cwd=repo_path,
                text=False,
                capture_output=True,
            )
            if completed.returncode:
                raise PythonEnvironmentError(_format_command_error(f"install {manifest.name}", completed))

        completed = subprocess.run(
            [str(python_executable), "-c", "import pytest"],
            cwd=repo_path,
            text=False,
            capture_output=True,
        )
        if completed.returncode:
            completed = subprocess.run(
                [
                    str(python_executable),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "pytest",
                ],
                cwd=repo_path,
                text=False,
                capture_output=True,
            )
            if completed.returncode:
                raise PythonEnvironmentError(_format_command_error("install pytest", completed))


def _dependency_manifests(repo_path: Path) -> list[Path]:
    return [
        repo_path / filename
        for filename in _DEPENDENCY_FILES
        if (repo_path / filename).is_file()
    ]


def _dependency_lines(manifests: list[Path]) -> list[str]:
    dependencies: list[str] = []
    for manifest in manifests:
        try:
            lines = manifest.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            dependency = line.strip()
            if not dependency or dependency.startswith("#"):
                continue
            dependencies.append(f"{manifest.name}: {dependency}")
    return dependencies


def _environment_signature(repo_path: Path, manifests: list[Path]) -> dict[str, object]:
    return {
        "schema_version": _ENV_SCHEMA_VERSION,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "manifests": [
            {
                "path": str(path.relative_to(repo_path)).replace("\\", "/"),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in manifests
        ],
    }


def _venv_python(env_path: Path) -> Path:
    if os.name == "nt":
        return env_path / "Scripts" / "python.exe"
    return env_path / "bin" / "python"


def _venv_env(env_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    scripts_dir = env_path / ("Scripts" if os.name == "nt" else "bin")
    env["VIRTUAL_ENV"] = str(env_path)
    env["PATH"] = f"{scripts_dir}{os.pathsep}{env.get('PATH', '')}"
    return env


def _read_marker(marker_path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_marker(marker_path: Path, payload: dict[str, object]) -> None:
    marker_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _format_command_error(action: str, completed: subprocess.CompletedProcess[bytes]) -> str:
    output = "\n".join(
        part.strip()
        for part in (decode_output(completed.stdout), decode_output(completed.stderr))
        if part.strip()
    )
    tail = "\n".join(output.splitlines()[-12:])
    return f"Python environment setup failed during {action}: {tail or f'exit code {completed.returncode}'}"
