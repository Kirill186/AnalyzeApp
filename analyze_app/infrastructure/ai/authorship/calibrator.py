from __future__ import annotations

import json
import math
from pathlib import Path


class ProbabilityCalibrator:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        payload = self._load_config(config_path)
        self.method: str = payload.get("method", "none")
        self.version: str = payload.get("calibration_version", "none")
        self.a: float = float(payload.get("a", 1.0))
        self.b: float = float(payload.get("b", 0.0))
        self.xs: list[float] = [float(x) for x in payload.get("xs", [])]
        self.ys: list[float] = [float(y) for y in payload.get("ys", [])]

    def calibrate(self, probability: float) -> float:
        p = min(max(probability, 1e-6), 1 - 1e-6)
        if self.method == "platt":
            logit = math.log(p / (1 - p))
            return self._sigmoid(self.a * logit + self.b)
        if self.method == "isotonic":
            return self._interpolate(p)
        return p

    @staticmethod
    def _sigmoid(value: float) -> float:
        if value >= 0:
            z = math.exp(-value)
            return 1 / (1 + z)
        z = math.exp(value)
        return z / (1 + z)

    def _interpolate(self, value: float) -> float:
        if not self.xs or not self.ys or len(self.xs) != len(self.ys):
            return value
        if value <= self.xs[0]:
            return self.ys[0]
        if value >= self.xs[-1]:
            return self.ys[-1]
        for idx in range(1, len(self.xs)):
            if value <= self.xs[idx]:
                x0, x1 = self.xs[idx - 1], self.xs[idx]
                y0, y1 = self.ys[idx - 1], self.ys[idx]
                if x1 == x0:
                    return y1
                ratio = (value - x0) / (x1 - x0)
                return y0 + ratio * (y1 - y0)
        return value

    @staticmethod
    def _load_config(path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {
            "method": "none",
            "calibration_version": "none",
        }
