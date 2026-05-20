from __future__ import annotations

import json
import math
from pathlib import Path

from analyze_app.application.use_cases.detect_ai_authorship import DetectAIAuthorshipUseCase
from analyze_app.domain.entities import AIAuthorshipResult
from analyze_app.infrastructure.ai.authorship import FeatureExtractor, ProbabilityCalibrator
from analyze_app.infrastructure.ai.authorship.runtime_factory import resolve_authorship_calibration_path


class FakeGitBackend:
    def list_tracked_files(self, repo_path: Path) -> list[str]:
        return ["sample.py"]

    def read_working_tree_file_changes(self, repo_path: Path) -> list:
        return []

    def read_working_tree_file(self, repo_path: Path, file_path: str) -> str:
        return "def answer():\n    return 42\n"


class FakeRuntime:
    model_version = "fake-model"
    dataset_version = "fake-dataset"

    def predict_probability(self, features: dict[str, float]) -> float:
        return 0.25

    def explain(self, features: dict[str, float], top_k: int = 5) -> list:
        return []


class FakeStore:
    def __init__(self, cached: AIAuthorshipResult | None) -> None:
        self.cached = cached
        self.saved: AIAuthorshipResult | None = None

    def load_ai_authorship(self, repo_id: int, scope_key: str) -> AIAuthorshipResult | None:
        return self.cached

    def save_ai_authorship(self, repo_id: int, scope_key: str, result: AIAuthorshipResult) -> None:
        self.saved = result


class IdentityCalibrator:
    version = "new-calibration"

    def calibrate(self, probability: float) -> float:
        return probability


def test_temperature_calibration_softens_probability(tmp_path: Path) -> None:
    config_path = tmp_path / "calibration.json"
    config_path.write_text(
        json.dumps({"method": "temperature", "calibration_version": "t2", "temperature": 2.0}),
        encoding="utf-8",
    )
    calibrator = ProbabilityCalibrator(config_path)

    raw_probability = 0.86371128
    expected = 1 / (1 + math.exp(-(math.log(raw_probability / (1 - raw_probability)) / 2.0)))

    assert math.isclose(calibrator.calibrate(raw_probability), expected)
    assert calibrator.calibrate(raw_probability) < raw_probability
    assert calibrator.calibrate(0.5) == 0.5


def test_cached_ai_authorship_result_is_invalidated_when_calibration_changes() -> None:
    cached = AIAuthorshipResult(
        scope="working_tree",
        probability=0.99,
        data_sufficiency=0.99,
        top_signals=[],
        calibration_version="old-calibration",
        model_info="fake-model (dataset=fake-dataset)",
        disclaimer="",
    )
    store = FakeStore(cached)
    use_case = DetectAIAuthorshipUseCase(
        git_backend=FakeGitBackend(),
        store=store,
        extractor=FeatureExtractor(),
        model_runtime=FakeRuntime(),
        calibrator=IdentityCalibrator(),
    )

    result = use_case.execute(1, Path("."), "working_tree")

    assert result.probability == 0.25
    assert result.calibration_version == "new-calibration"
    assert store.saved is result


def test_uncalibrated_onnx_artifact_uses_tracked_temperature_default(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "onnx"
    artifact_dir.mkdir()
    (artifact_dir / "model.onnx").write_bytes(b"")
    (artifact_dir / "calibration.json").write_text(
        json.dumps({"method": "none", "calibration_version": "uncalibrated-v1"}),
        encoding="utf-8",
    )
    fallback = tmp_path / "fallback.json"
    fallback.write_text(json.dumps({"method": "platt"}), encoding="utf-8")

    resolved = resolve_authorship_calibration_path(artifact_dir, fallback)

    assert resolved.name == "onnx_default_calibration.json"
