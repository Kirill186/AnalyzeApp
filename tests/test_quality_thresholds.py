from __future__ import annotations

from pathlib import Path

from analyze_app.domain.entities import AIAuthorshipResult
from analyze_app.presentation.qt_shell import main_window
from analyze_app.presentation.qt_shell.settings_dialog import QUALITY_FIELDS
from analyze_app.presentation.qt_shell.state_store import DEFAULT_QUALITY_THRESHOLDS


class FakeAIAuthorshipUseCase:
    def execute(self, *args, **kwargs) -> AIAuthorshipResult:
        return AIAuthorshipResult(
            scope="working_tree",
            probability=0.45,
            data_sufficiency=0.9,
            top_signals=[],
            calibration_version="fake-calibration",
            model_info="fake-model",
            disclaimer="",
        )


def test_quality_settings_exposes_ai_authorship_thresholds() -> None:
    field = next(field for field in QUALITY_FIELDS if field.key == "ai_authorship_probability_pct")

    assert DEFAULT_QUALITY_THRESHOLDS[field.key] == [20.0, 40.0, 60.0, 80.0]
    assert field.label == "AI-оценка"
    assert field.direction == "lower"
    assert field.suffix == "%"


def test_ai_signal_grade_uses_quality_thresholds(monkeypatch) -> None:
    monkeypatch.setattr(
        main_window,
        "_build_ai_authorship_use_case",
        lambda *args, **kwargs: FakeAIAuthorshipUseCase(),
    )

    metric, _details = main_window._calculate_ai_signal_metric_result(
        repo_id=1,
        repo_path=Path("."),
        git_backend=object(),
        store=object(),
        thresholds={"ai_authorship_probability_pct": [10.0, 30.0, 50.0, 70.0]},
    )

    assert metric == ("C", "45.0% (данные 0.90)", "A<=10, B<=30, C<=50, D<=70")
