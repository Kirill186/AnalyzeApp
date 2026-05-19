from __future__ import annotations

from pathlib import Path

from analyze_app.application.use_cases.detect_ai_authorship import DetectAIAuthorshipUseCase
from analyze_app.domain.entities import FileChange
from analyze_app.infrastructure.ai.authorship import FeatureExtractor


class FakeGitBackend:
    def __init__(self, files: dict[str, str], changed: list[str] | None = None) -> None:
        self.files = files
        self.changed = changed or []

    def read_working_tree_file_changes(self, repo_path: Path) -> list[FileChange]:
        return [FileChange(path=path, additions=1, deletions=0) for path in self.changed]

    def list_tracked_files(self, repo_path: Path) -> list[str]:
        return list(self.files)

    def read_working_tree_file(self, repo_path: Path, file_path: str) -> str:
        return self.files.get(file_path, "")


class FakeStore:
    def __init__(self) -> None:
        self.saved_scope_key: str | None = None

    def load_ai_authorship(self, repo_id: int, scope_key: str):
        return None

    def save_ai_authorship(self, repo_id: int, scope_key: str, result) -> None:
        self.saved_scope_key = scope_key


class FakeRuntime:
    model_version = "fake-model"
    dataset_version = "fake-dataset"

    def __init__(self) -> None:
        self.code_blobs: list[str] = []

    def predict_code_probability(self, code_blobs: list[str]) -> float:
        self.code_blobs = list(code_blobs)
        return 0.42

    def predict_probability(self, features: dict[str, float]) -> float:
        return 0.42

    def explain(self, features: dict[str, float], top_k: int = 5) -> list:
        return []


class FakeCalibrator:
    version = "fake-calibration"

    def calibrate(self, probability: float) -> float:
        return probability


def build_use_case(files: dict[str, str], changed: list[str] | None = None):
    runtime = FakeRuntime()
    store = FakeStore()
    use_case = DetectAIAuthorshipUseCase(
        git_backend=FakeGitBackend(files, changed),
        store=store,
        extractor=FeatureExtractor(),
        model_runtime=runtime,
        calibrator=FakeCalibrator(),
    )
    return use_case, runtime, store


def test_working_tree_scores_all_tracked_python_files_even_when_changes_exist() -> None:
    use_case, runtime, store = build_use_case(
        {
            "changed.py": "def changed():\n    return 'changed'\n",
            "unchanged.py": "def unchanged():\n    return 'unchanged'\n",
            "notes.txt": "not python",
        },
        changed=["changed.py"],
    )

    result = use_case.execute(1, Path("."), "working_tree", use_cache=False)

    assert result.probability == 0.42
    assert any("def changed" in blob for blob in runtime.code_blobs)
    assert any("def unchanged" in blob for blob in runtime.code_blobs)
    assert all("not python" not in blob for blob in runtime.code_blobs)
    assert store.saved_scope_key is not None
    assert DetectAIAuthorshipUseCase.SEGMENTATION_VERSION in store.saved_scope_key


def test_model_receives_solution_like_chunks_instead_of_whole_file() -> None:
    use_case, runtime, _store = build_use_case(
        {
            "service.py": (
                "import os\n\n"
                "class Service:\n"
                "    def add(self, value):\n"
                "        return value + 1\n\n"
                "    def remove(self, value):\n"
                "        return value - 1\n\n"
                "def top_level():\n"
                "    return os.getcwd()\n"
            )
        }
    )

    result = use_case.execute(1, Path("."), "working_tree", use_cache=False)

    assert len(runtime.code_blobs) == 4
    assert result.confidence == 0.155
    assert any(blob.startswith("class Service:\n    def add") for blob in runtime.code_blobs)
    assert any(blob.startswith("class Service:\n    def remove") for blob in runtime.code_blobs)
    assert any(blob.startswith("def top_level") for blob in runtime.code_blobs)
    assert any(blob.startswith("import os") for blob in runtime.code_blobs)
    assert not any(
        "def add" in blob and "def remove" in blob and "def top_level" in blob
        for blob in runtime.code_blobs
    )


def test_syntax_error_falls_back_to_original_blob() -> None:
    use_case, runtime, _store = build_use_case({"broken.py": "def broken(:\n    pass\n"})

    use_case.execute(1, Path("."), "working_tree", use_cache=False)

    assert runtime.code_blobs == ["def broken(:\n    pass\n"]
