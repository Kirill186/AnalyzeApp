from __future__ import annotations

import re
from pathlib import Path
from threading import Lock
from typing import Any

from analyze_app.domain.entities import EvidenceBlock, LLMResult, ProjectOverviewResult
from analyze_app.infrastructure.ai.ollama_cache import OLLAMA_MODEL_URI_PREFIX, resolve_ollama_model_uri

_LLAMA_CACHE: dict[tuple[str, int, int, int], Any] = {}
_LLAMA_CACHE_LOCK = Lock()

DIFF_PROMPT_CHAR_LIMIT = 8000
PROJECT_CONTEXT_CHAR_LIMIT = 12000
DIFF_MAX_TOKENS = 260
PROJECT_MAX_TOKENS = 280
LLAMA_BATCH_SIZE = 512


class LlamaCppBackend:
    def __init__(
        self,
        model_path: str | Path,
        context_size: int = 4096,
        n_threads: int = 0,
        n_gpu_layers: int = 0,
    ) -> None:
        self.model_ref = str(model_path).strip()
        self.model = self.model_ref or "<unset>"
        self._resolved_model_path: Path | None = None
        self.context_size = context_size
        self.n_threads = n_threads
        self.n_gpu_layers = n_gpu_layers

    def summarize_diff(self, diff_text: str) -> LLMResult:
        prompt = (
            "Суммаризируй изменения. Ответь на русском в формате:\n"
            "1) Что изменено\n2) Риски\n3) Рекомендации\n4) Evidence blocks (файл: причина).\n\n"
            f"DIFF:\n{diff_text[:DIFF_PROMPT_CHAR_LIMIT]}"
        )

        try:
            text = self._generate(prompt, max_tokens=DIFF_MAX_TOKENS, temperature=0.1)
            return LLMResult(
                summary=text,
                model_info=f"llama-cpp:{self.model}",
                evidence=self._extract_evidence(diff_text, text),
            )
        except Exception as exc:  # noqa: BLE001
            return LLMResult(
                summary=f"AI summary unavailable: {self._humanize_error(exc)}",
                model_info=f"llama-cpp:{self.model}",
                evidence=self._extract_evidence(diff_text, ""),
            )

    def summarize_project(self, context: str) -> ProjectOverviewResult:
        prompt = (
            "Ты готовишь описание репозитория для страницы проекта.\n"
            "Напиши 1-2 плотных абзаца на русском языке:\n"
            "1) в чем суть проекта и какую задачу он решает;\n"
            "2) как устроена его структура (ключевые слои/модули).\n"
            "Без списков и без markdown.\n\n"
            f"CONTEXT:\n{context[:PROJECT_CONTEXT_CHAR_LIMIT]}"
        )

        try:
            return ProjectOverviewResult(
                summary=self._generate(prompt, max_tokens=PROJECT_MAX_TOKENS, temperature=0.2),
                model_info=f"llama-cpp:{self.model}",
            )
        except Exception as exc:  # noqa: BLE001
            return ProjectOverviewResult(
                summary=f"Project overview unavailable: {self._humanize_error(exc)}",
                model_info=f"llama-cpp:{self.model}",
            )

    def _generate(self, prompt: str, max_tokens: int, temperature: float) -> str:
        llm = self._get_llm()
        try:
            response = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": "Ты помогаешь анализировать код. Отвечай кратко и по делу."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.9,
                repeat_penalty=1.1,
            )
            text = response["choices"][0]["message"]["content"]
        except Exception:  # noqa: BLE001
            response = llm(
                f"{prompt}\n\nОтвет:",
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.9,
                repeat_penalty=1.1,
                echo=False,
            )
            text = response["choices"][0]["text"]
        return str(text).strip() or "AI response is empty"

    def _get_llm(self) -> Any:
        model_path = self._resolve_model_path()
        if not model_path.exists():
            raise FileNotFoundError(f"GGUF model file not found: {model_path}")
        if not model_path.is_file():
            raise ValueError(f"GGUF model path is not a file: {model_path}")

        cache_key = (
            str(model_path.resolve()),
            self.context_size,
            self.n_threads,
            self.n_gpu_layers,
        )
        with _LLAMA_CACHE_LOCK:
            cached = _LLAMA_CACHE.get(cache_key)
            if cached is not None:
                return cached

            try:
                from llama_cpp import Llama
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "llama-cpp-python is not installed. Install CPU wheel: "
                    "pip install --only-binary=:all: "
                    "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu "
                    "llama-cpp-python==0.3.0"
                ) from exc

            kwargs: dict[str, Any] = {
                "model_path": str(model_path),
                "n_ctx": self.context_size,
                "n_batch": min(LLAMA_BATCH_SIZE, self.context_size),
                "n_ubatch": min(LLAMA_BATCH_SIZE, self.context_size),
                "verbose": False,
            }
            if self.n_threads > 0:
                kwargs["n_threads"] = self.n_threads
                kwargs["n_threads_batch"] = self.n_threads
            if self.n_gpu_layers != 0:
                kwargs["n_gpu_layers"] = self.n_gpu_layers

            llm = Llama(**kwargs)
            _LLAMA_CACHE[cache_key] = llm
            return llm

    def _resolve_model_path(self) -> Path:
        if self._resolved_model_path is not None:
            return self._resolved_model_path
        if not self.model_ref:
            raise ValueError("set ANALYZE_APP_LLM_MODEL_PATH to a local .gguf file or ollama://model:tag")

        if self.model_ref.startswith(OLLAMA_MODEL_URI_PREFIX):
            self._resolved_model_path = resolve_ollama_model_uri(self.model_ref)
        else:
            self._resolved_model_path = Path(self.model_ref).expanduser()
        return self._resolved_model_path

    def _extract_evidence(self, diff_text: str, summary: str) -> list[EvidenceBlock]:
        file_paths = []
        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                file_paths.append(line.replace("+++ b/", "", 1).strip())
        unique_paths = list(dict.fromkeys(p for p in file_paths if p and p != "/dev/null"))

        evidence: list[EvidenceBlock] = []
        for path in unique_paths[:5]:
            reason = "Изменения в diff"
            match = re.search(rf"{re.escape(path)}.*", summary, flags=re.IGNORECASE)
            if match:
                reason = "Упомянуто в AI-summary"
            evidence.append(EvidenceBlock(file=path, reason=reason))
        return evidence

    @staticmethod
    def _humanize_error(exc: Exception) -> str:
        return str(exc)
