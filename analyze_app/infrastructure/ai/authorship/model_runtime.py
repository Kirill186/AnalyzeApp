from __future__ import annotations

import json
import math
from pathlib import Path

from analyze_app.domain.entities import AIAuthorshipSignal


class ModelRuntime:
    def __init__(self, artifact_path: Path) -> None:
        self.artifact_path = artifact_path
        payload = self._load_artifact(artifact_path)
        self.feature_order: list[str] = payload["feature_order"]
        self.weights: dict[str, float] = payload["weights"]
        self.bias: float = float(payload.get("bias", 0.0))
        self.model_version: str = str(payload.get("model_version", "heuristic-v1"))
        self.dataset_version: str = str(payload.get("dataset_version", "unknown"))

    def predict_probability(self, features: dict[str, float]) -> float:
        score = self.bias
        for name in self.feature_order:
            score += float(features.get(name, 0.0)) * float(self.weights.get(name, 0.0))
        return self._sigmoid(score)

    def explain(self, features: dict[str, float], top_k: int = 5) -> list[AIAuthorshipSignal]:
        contributions: list[tuple[str, float, float]] = []
        for name in self.feature_order:
            value = float(features.get(name, 0.0))
            weight = float(self.weights.get(name, 0.0))
            contributions.append((name, value, value * weight))

        contributions.sort(key=lambda item: abs(item[2]), reverse=True)
        top = contributions[:top_k]
        signals: list[AIAuthorshipSignal] = []
        for name, value, contribution in top:
            direction = "increase" if contribution >= 0 else "decrease"
            signals.append(
                AIAuthorshipSignal(
                    name=name,
                    value=value,
                    weight=float(self.weights.get(name, 0.0)),
                    direction=direction,
                    description=self._describe_signal(name, direction),
                )
            )
        return signals

    @staticmethod
    def _sigmoid(value: float) -> float:
        if value >= 0:
            z = math.exp(-value)
            return 1 / (1 + z)
        z = math.exp(value)
        return z / (1 + z)

    @staticmethod
    def _load_artifact(path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {
            "model_version": "heuristic-v1",
            "dataset_version": "none",
            "feature_order": [
                "line_count",
                "avg_line_length",
                "comment_ratio",
                "repetition_ratio",
                "function_count",
                "branch_count",
                "snake_case_ratio",
                "ast_depth",
                "embedding_std",
            ],
            "weights": {
                "line_count": 0.001,
                "avg_line_length": 0.02,
                "comment_ratio": -0.9,
                "repetition_ratio": 1.2,
                "function_count": -0.08,
                "branch_count": -0.04,
                "snake_case_ratio": -0.5,
                "ast_depth": -0.03,
                "embedding_std": 0.6,
            },
            "bias": -0.35,
        }

    @staticmethod
    def _describe_signal(name: str, direction: str) -> str:
        direction_ru = "повышает" if direction == "increase" else "понижает"
        return f"Признак {name} {direction_ru} итоговую вероятностную оценку."
