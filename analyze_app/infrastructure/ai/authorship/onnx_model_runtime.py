from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analyze_app.domain.entities import AIAuthorshipSignal


class OnnxModelRuntime:
    def __init__(self, artifact_path: Path, max_chunks_per_blob: int = 16) -> None:
        self.artifact_path = artifact_path
        self.artifact_dir = artifact_path if artifact_path.is_dir() else artifact_path.parent
        self.model_path = self.artifact_dir / "model.onnx" if artifact_path.is_dir() else artifact_path
        self.max_chunks_per_blob = max_chunks_per_blob

        if not self.model_path.exists():
            raise FileNotFoundError(f"ONNX model not found: {self.model_path}")

        try:
            import numpy as np
            import onnxruntime as ort
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "ONNX AI-authorship runtime requires optional dependencies: "
                "onnxruntime, transformers, numpy."
            ) from exc

        self.np = np
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.artifact_dir), local_files_only=True)
        self.session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
        self.input_names = {item.name for item in self.session.get_inputs()}
        self.output_names = [item.name for item in self.session.get_outputs()]
        self.max_length = self._resolve_max_length()
        self.ai_label_id = self._resolve_ai_label_id()
        self.model_version = self._build_model_version()
        self.dataset_version = self._build_dataset_version()

    def predict_code_probability(self, code_blobs: list[str]) -> float:
        probabilities: list[float] = []
        weights: list[int] = []

        for code in code_blobs or [""]:
            encoded = self.tokenizer(
                code or " ",
                truncation=True,
                padding="max_length",
                max_length=self.max_length,
                return_tensors="np",
                return_overflowing_tokens=True,
                stride=min(64, max(0, self.max_length // 4)),
            )
            input_ids = encoded["input_ids"]
            chunk_count = min(len(input_ids), self.max_chunks_per_blob)
            for index in range(chunk_count):
                inputs = self._slice_inputs(encoded, index)
                logits = self.session.run(None, inputs)[0]
                probabilities.append(self._softmax_ai_probability(logits[0]))
                weights.append(int((inputs["attention_mask"][0] > 0).sum()) if "attention_mask" in inputs else 1)

        if not probabilities:
            return 0.0

        total_weight = max(sum(weights), 1)
        return float(sum(probability * weight for probability, weight in zip(probabilities, weights)) / total_weight)

    def predict_probability(self, features: dict[str, float]) -> float:
        raise RuntimeError("OnnxModelRuntime requires code blobs. Use predict_code_probability().")

    def explain(self, features: dict[str, float], top_k: int = 5) -> list[AIAuthorshipSignal]:
        signal_specs = [
            ("repetition_ratio", "increase", "Higher token repetition can make code look more template-like."),
            ("comment_ratio", "decrease", "More natural comments usually reduce AI-likeness in this heuristic explanation."),
            ("avg_line_length", "increase", "Long uniform lines can contribute to AI-likeness."),
            ("branch_count", "decrease", "More branch structure can look less template-like."),
            ("ast_depth", "decrease", "Deeper syntax trees can indicate more hand-shaped control flow."),
            ("syntax_error", "increase", "Syntax errors lower data sufficiency and can distort authorship estimates."),
        ]
        ranked = sorted(signal_specs, key=lambda item: abs(float(features.get(item[0], 0.0))), reverse=True)
        signals: list[AIAuthorshipSignal] = []
        for name, direction, description in ranked[:top_k]:
            signals.append(
                AIAuthorshipSignal(
                    name=name,
                    value=float(features.get(name, 0.0)),
                    weight=0.0,
                    direction=direction,
                    description=description,
                )
            )
        return signals

    def _slice_inputs(self, encoded: Any, index: int) -> dict[str, Any]:
        inputs: dict[str, Any] = {}
        for name in self.input_names:
            if name in encoded:
                inputs[name] = encoded[name][index : index + 1]
        return inputs

    def _softmax_ai_probability(self, logits: Any) -> float:
        values = self.np.asarray(logits, dtype=self.np.float64)
        values = values - values.max()
        exps = self.np.exp(values)
        probabilities = exps / exps.sum()
        return float(probabilities[self.ai_label_id])

    def _resolve_max_length(self) -> int:
        training_args = self._read_json(self.artifact_dir / "training_args.json")
        if isinstance(training_args.get("max_length"), int):
            return int(training_args["max_length"])
        model_max_length = int(getattr(self.tokenizer, "model_max_length", 512) or 512)
        if model_max_length > 100_000:
            return 512
        return min(max(model_max_length, 16), 512)

    def _resolve_ai_label_id(self) -> int:
        labels = self._read_json(self.artifact_dir / "labels.json")
        label2id = labels.get("label2id", {})
        return int(label2id.get("ai", 1))

    def _build_model_version(self) -> str:
        parts = [self.model_path.name, str(self.model_path.stat().st_size), str(self.model_path.stat().st_mtime_ns)]
        external_data = self.artifact_dir / "model.onnx.data"
        if external_data.exists():
            parts.extend([external_data.name, str(external_data.stat().st_size), str(external_data.stat().st_mtime_ns)])
        return "onnx-codebert:" + ":".join(parts)

    def _build_dataset_version(self) -> str:
        metrics = self._read_json(self.artifact_dir / "metrics.json")
        f1_ai = metrics.get("f1_ai")
        if isinstance(f1_ai, (int, float)):
            return f"ai-signal-v1:f1_ai={float(f1_ai):.4f}"
        return "ai-signal-v1"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
