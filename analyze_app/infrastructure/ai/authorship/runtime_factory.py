from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from analyze_app.domain.entities import AIAuthorshipSignal
from analyze_app.infrastructure.ai.authorship.model_runtime import ModelRuntime
from analyze_app.infrastructure.ai.authorship.onnx_model_runtime import OnnxModelRuntime


_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_ONNX_CALIBRATION_PATH = _PACKAGE_DIR / "onnx_default_calibration.json"


class AuthorshipRuntime(Protocol):
    model_version: str
    dataset_version: str

    def predict_probability(self, features: dict[str, float]) -> float:
        ...

    def explain(self, features: dict[str, float], top_k: int = 5) -> list[AIAuthorshipSignal]:
        ...


def build_authorship_runtime(model_path: Path) -> AuthorshipRuntime:
    if _looks_like_onnx_artifact(model_path):
        return OnnxModelRuntime(model_path)
    return ModelRuntime(model_path)


def resolve_authorship_calibration_path(model_path: Path, fallback_path: Path) -> Path:
    if model_path.is_dir():
        candidate = model_path / "calibration.json"
    elif model_path.suffix.lower() == ".onnx":
        candidate = model_path.parent / "calibration.json"
    else:
        candidate = fallback_path

    if _looks_like_onnx_artifact(model_path):
        if candidate.exists() and not _is_uncalibrated(candidate):
            return candidate
        if _DEFAULT_ONNX_CALIBRATION_PATH.exists():
            return _DEFAULT_ONNX_CALIBRATION_PATH

    return candidate if candidate.exists() else fallback_path


def _looks_like_onnx_artifact(path: Path) -> bool:
    return path.suffix.lower() == ".onnx" or (path.is_dir() and (path / "model.onnx").exists())


def _is_uncalibrated(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    method = str(payload.get("method", "none")).lower()
    version = str(payload.get("calibration_version", "none")).lower()
    return method == "none" or version.startswith("uncalibrated")
