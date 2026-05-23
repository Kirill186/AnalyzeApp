from __future__ import annotations

from analyze_app.application.use_cases.get_commit_report import CommitReportUseCase
from analyze_app.infrastructure.ai.llama_cpp_backend import LlamaCppBackend
from analyze_app.infrastructure.ai.prompts import DIFF_SUMMARY_PROMPT_VERSION, build_diff_summary_prompt


class FakeDiffBackend:
    model = "local-model"
    prompt_version = DIFF_SUMMARY_PROMPT_VERSION


class CapturingLlamaBackend(LlamaCppBackend):
    def __init__(self) -> None:
        super().__init__("local-model")
        self.prompt = ""
        self.max_tokens = 0
        self.temperature = 0.0

    def _generate(self, prompt: str, max_tokens: int, temperature: float) -> str:
        self.prompt = prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        return "Изменение уточняет обработку diff и делает описание более содержательным."


def test_diff_summary_prompt_prefers_narrative_over_numbered_lists() -> None:
    prompt = build_diff_summary_prompt("diff --git a/app.py b/app.py", 8000)

    assert "без markdown, нумерации и списков" in prompt
    assert "Первый абзац: 3-5 содержательных предложений" in prompt
    assert "не перечисляй их механически" in prompt
    assert "1) Что изменено" not in prompt
    assert "Evidence blocks" not in prompt


def test_llama_diff_summary_uses_versioned_narrative_prompt() -> None:
    backend = CapturingLlamaBackend()

    result = backend.summarize_diff("+++ b/app.py\n+print('hello')\n")

    assert result.summary.startswith("Изменение уточняет")
    assert "без markdown, нумерации и списков" in backend.prompt
    assert backend.max_tokens >= 360
    assert backend.temperature == 0.2
    assert f"prompt={DIFF_SUMMARY_PROMPT_VERSION}" in result.model_info
    assert result.model_info.endswith(backend.model)


def test_commit_report_cache_requires_current_prompt_version() -> None:
    use_case = CommitReportUseCase(
        git_backend=object(),
        ruff_runner=object(),
        pytest_runner=object(),
        ai_backend=FakeDiffBackend(),
        store=object(),
    )

    assert not use_case._is_cache_compatible("llama-cpp:local-model")
    assert use_case._is_cache_compatible(
        f"llama-cpp:prompt={DIFF_SUMMARY_PROMPT_VERSION}:local-model"
    )
