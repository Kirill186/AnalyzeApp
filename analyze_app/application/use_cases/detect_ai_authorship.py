from __future__ import annotations

import ast
import hashlib
import textwrap
from pathlib import Path

from analyze_app.domain.entities import AIAuthorshipResult
from analyze_app.infrastructure.ai.authorship import AuthorshipRuntime, FeatureExtractor, ProbabilityCalibrator
from analyze_app.infrastructure.git.backend import GitBackend
from analyze_app.infrastructure.storage.database_store import DatabaseStore


class DetectAIAuthorshipUseCase:
    SEGMENTATION_VERSION = "solution_chunks_v1"

    DISCLAIMER = (
        "Оценка носит вероятностный характер и не доказывает факт AI-генерации. "
        "Нельзя использовать результат как единственное основание для санкционных решений."
    )

    def __init__(
        self,
        git_backend: GitBackend,
        store: DatabaseStore,
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
        source_blobs = self._collect_code(repo_path, scope, commit_hash, files)
        solution_blobs = self._solution_like_blobs(source_blobs)
        scope_key = self._scope_key(scope, commit_hash, files, source_blobs)

        if use_cache:
            cached = self.store.load_ai_authorship(repo_id, scope_key)
            if (
                cached
                and cached.model_info.startswith(self.model_runtime.model_version)
                and cached.calibration_version == self.calibrator.version
            ):
                return cached

        source_features = self._aggregate_features(source_blobs)
        features = self._aggregate_features(solution_blobs)

        if hasattr(self.model_runtime, "predict_code_probability"):
            raw_probability = self.model_runtime.predict_code_probability(solution_blobs)  # type: ignore[attr-defined]
        else:
            raw_probability = self.model_runtime.predict_probability(features)
        calibrated_probability = self.calibrator.calibrate(raw_probability)
        confidence = self._confidence(source_features, len(source_blobs))
        signals = self.model_runtime.explain(features)

        result = AIAuthorshipResult(
            scope=scope,
            probability=round(calibrated_probability, 4),
            confidence=round(confidence, 4),
            top_signals=signals,
            calibration_version=self.calibrator.version,
            model_info=(
                f"{self.model_runtime.model_version} "
                f"(dataset={self.model_runtime.dataset_version}; segments={self.SEGMENTATION_VERSION})"
            ),
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
            return [
                self.git_backend.read_working_tree_file(repo_path, file_path)
                for file_path in file_paths
                if file_path.endswith(".py")
            ]

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
            code = []
            for file_path in self.git_backend.list_tracked_files(repo_path):
                if not file_path.endswith(".py"):
                    continue
                text = self.git_backend.read_working_tree_file(repo_path, file_path)
                if text:
                    code.append(text)
            return code

        raise ValueError(f"Unsupported scope: {scope}")

    def _solution_like_blobs(self, code_blobs: list[str]) -> list[str]:
        segmented: list[str] = []
        for code in code_blobs:
            segmented.extend(self._split_solution_like_chunks(code))
        return segmented or code_blobs

    def _split_solution_like_chunks(self, code: str) -> list[str]:
        lines = code.splitlines(keepends=True)
        if not lines:
            return []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return [code]

        chunks: list[str] = []
        consumed: list[tuple[int, int]] = []

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunk = self._node_source(lines, node)
                if chunk:
                    chunks.append(chunk)
                    consumed.append(self._node_span(node))
                continue

            if isinstance(node, ast.ClassDef):
                class_chunks = self._class_solution_chunks(lines, node)
                if class_chunks:
                    chunks.extend(class_chunks)
                    consumed.append(self._node_span(node))
                    continue

            if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith)):
                chunk = self._node_source(lines, node)
                if chunk:
                    chunks.append(chunk)
                    consumed.append(self._node_span(node))

        top_level = self._unconsumed_top_level_chunk(lines, consumed)
        if top_level:
            chunks.append(top_level)

        return chunks or [code]

    def _class_solution_chunks(self, lines: list[str], node: ast.ClassDef) -> list[str]:
        methods = [
            item
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        if not methods:
            chunk = self._node_source(lines, node)
            return [chunk] if chunk else []

        header = self._class_header(lines, node)
        chunks: list[str] = []
        for method in methods:
            method_source = self._node_source(lines, method, dedent=False)
            if not method_source:
                continue
            chunks.append(f"{header}\n{method_source}".rstrip() + "\n")
        return chunks

    @staticmethod
    def _node_source(lines: list[str], node: ast.AST, dedent: bool = True) -> str:
        start, end = DetectAIAuthorshipUseCase._node_span(node)
        source = "".join(lines[start - 1 : end]).strip("\n")
        if dedent:
            source = textwrap.dedent(source)
        return source.rstrip() + "\n" if source.strip() else ""

    @staticmethod
    def _node_span(node: ast.AST) -> tuple[int, int]:
        start = getattr(node, "lineno", 1)
        for decorator in getattr(node, "decorator_list", []):
            start = min(start, getattr(decorator, "lineno", start))
        end = getattr(node, "end_lineno", start)
        return start, end

    @staticmethod
    def _class_header(lines: list[str], node: ast.ClassDef) -> str:
        start = getattr(node, "lineno", 1)
        for decorator in getattr(node, "decorator_list", []):
            start = min(start, getattr(decorator, "lineno", start))
        end = start
        if node.body:
            end = max(start, getattr(node.body[0], "lineno", start) - 1)
        header = "".join(lines[start - 1 : end]).rstrip()
        return textwrap.dedent(header) or f"class {node.name}:"

    @staticmethod
    def _unconsumed_top_level_chunk(lines: list[str], consumed: list[tuple[int, int]]) -> str:
        if not consumed:
            return ""

        ranges = sorted(consumed)
        remaining: list[str] = []
        range_index = 0
        for line_number, line in enumerate(lines, start=1):
            while range_index < len(ranges) and line_number > ranges[range_index][1]:
                range_index += 1
            in_consumed_range = (
                range_index < len(ranges)
                and ranges[range_index][0] <= line_number <= ranges[range_index][1]
            )
            if not in_consumed_range and line.strip():
                remaining.append(line)

        source = textwrap.dedent("".join(remaining)).strip()
        return source + "\n" if source else ""

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
            return f"commit:{commit_hash}:{DetectAIAuthorshipUseCase.SEGMENTATION_VERSION}:{content_hash}"
        if scope == "file":
            normalized = ",".join(sorted(files or []))
            return f"file:{normalized}:{DetectAIAuthorshipUseCase.SEGMENTATION_VERSION}:{content_hash}"
        return f"working_tree:{DetectAIAuthorshipUseCase.SEGMENTATION_VERSION}:{content_hash}"

    @staticmethod
    def _content_hash(code_blobs: list[str]) -> str:
        digest = hashlib.sha256()
        for text in code_blobs:
            digest.update(len(text).to_bytes(8, "big", signed=False))
            digest.update(text.encode("utf-8", errors="replace"))
        return digest.hexdigest()[:16]
