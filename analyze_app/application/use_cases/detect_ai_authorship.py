from __future__ import annotations

import hashlib
from pathlib import Path

from analyze_app.domain.entities import AIAuthorshipResult
from analyze_app.infrastructure.ai.authorship import AuthorshipRuntime, FeatureExtractor, ProbabilityCalibrator
from analyze_app.infrastructure.git.backend import GitBackend
from analyze_app.infrastructure.storage.sqlite_store import SqliteStore


class DetectAIAuthorshipUseCase:
    DISCLAIMER = (
        "Оценка носит вероятностный характер и не доказывает факт AI-генерации. "
        "Нельзя использовать результат как единственное основание для санкционных решений."
    )

    def __init__(
        self,
        git_backend: GitBackend,
        store: SqliteStore,
        extractor: FeatureExtractor,
        model_runtime: AuthorshipRuntime,
        calibrator: ProbabilityCalibrator,
    ) -> None:
        self.git_backend = git_backend
        self.store = store
        self.extractor = extractor
        self.model_runtime = model_runtime
        self.calibrator = calibrator

    def execute(
        self,
        repo_id: int,
        repo_path: Path,
        scope: str,
        commit_hash: str | None = None,
        files: list[str] | None = None,
        use_cache: bool = True,
    ) -> AIAuthorshipResult:
        code_blobs = self._collect_code(repo_path, scope, commit_hash, files)
        scope_key = self._scope_key(scope, commit_hash, files, code_blobs)

        if use_cache:
            cached = self.store.load_ai_authorship(repo_id, scope_key)
            if cached and cached.model_info.startswith(self.model_runtime.model_version):
                return cached

        features = self._aggregate_features(code_blobs)

        if hasattr(self.model_runtime, "predict_code_probability"):
            raw_probability = self.model_runtime.predict_code_probability(code_blobs)  # type: ignore[attr-defined]
        else:
            raw_probability = self.model_runtime.predict_probability(features)
        calibrated_probability = self.calibrator.calibrate(raw_probability)
        confidence = self._confidence(features, len(code_blobs))
        signals = self.model_runtime.explain(features)

        result = AIAuthorshipResult(
            scope=scope,
            probability=round(calibrated_probability, 4),
            confidence=round(confidence, 4),
            top_signals=signals,
            calibration_version=self.calibrator.version,
            model_info=f"{self.model_runtime.model_version} (dataset={self.model_runtime.dataset_version})",
            disclaimer=self.DISCLAIMER,
        )
        self.store.save_ai_authorship(repo_id, scope_key, result)
        return result

    def _collect_code(
        self,
        repo_path: Path,
        scope: str,
        commit_hash: str | None,
        files: list[str] | None,
    ) -> list[str]:
        if scope == "file":
            file_paths = files or []
            return [self.git_backend.read_working_tree_file(repo_path, file_path) for file_path in file_paths if file_path.endswith(".py")]

        if scope == "commit":
            if not commit_hash:
                raise ValueError("commit_hash is required for commit scope")
            changed = self.git_backend.read_commit_file_changes(repo_path, commit_hash)
            code: list[str] = []
            for item in changed:
                if not item.path.endswith(".py"):
                    continue
                text = self.git_backend.read_file_at_commit(repo_path, commit_hash, item.path)
                if text:
                    code.append(text)
            return code

        if scope == "working_tree":
            changed = self.git_backend.read_working_tree_file_changes(repo_path)
            code = []
            for item in changed:
                if not item.path.endswith(".py"):
                    continue
                text = self.git_backend.read_working_tree_file(repo_path, item.path)
                if text:
                    code.append(text)
            if code:
                return code

            for file_path in self.git_backend.list_tracked_files(repo_path):
                if not file_path.endswith(".py"):
                    continue
                text = self.git_backend.read_working_tree_file(repo_path, file_path)
                if text:
                    code.append(text)
            return code

        raise ValueError(f"Unsupported scope: {scope}")

    def _aggregate_features(self, code_blobs: list[str]) -> dict[str, float]:
        if not code_blobs:
            return self.extractor.extract("")

        extracted = [self.extractor.extract(text) for text in code_blobs]
        keys = set().union(*(feature_set.keys() for feature_set in extracted))
        return {key: sum(features.get(key, 0.0) for features in extracted) / len(extracted) for key in keys}

    @staticmethod
    def _confidence(features: dict[str, float], files_count: int) -> float:
        line_count = max(features.get("line_count", 0.0), 0.0)
        syntax_error_penalty = 0.4 if features.get("syntax_error", 0.0) > 0 else 0.0
        base = min(1.0, (line_count / 200.0) + (files_count / 10.0))
        return max(0.05, base - syntax_error_penalty)

    @staticmethod
    def _scope_key(scope: str, commit_hash: str | None, files: list[str] | None, code_blobs: list[str]) -> str:
        content_hash = DetectAIAuthorshipUseCase._content_hash(code_blobs)
        if scope == "commit":
            return f"commit:{commit_hash}:{content_hash}"
        if scope == "file":
            normalized = ",".join(sorted(files or []))
            return f"file:{normalized}:{content_hash}"
        return f"working_tree:{content_hash}"

    @staticmethod
    def _content_hash(code_blobs: list[str]) -> str:
        digest = hashlib.sha256()
        for text in code_blobs:
            digest.update(len(text).to_bytes(8, "big", signed=False))
            digest.update(text.encode("utf-8", errors="replace"))
        return digest.hexdigest()[:16]
