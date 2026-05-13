from __future__ import annotations

from analyze_app.infrastructure.ai.base import DiffSummaryBackend, ProjectOverviewAIBackend
from analyze_app.infrastructure.ai.llama_cpp_backend import LlamaCppBackend
from analyze_app.infrastructure.ai.ollama_backend import OllamaBackend
from analyze_app.infrastructure.ai.project_overview_backend import ProjectOverviewBackend
from analyze_app.shared.config import AppConfig


def build_diff_ai_backend(config: AppConfig) -> DiffSummaryBackend:
    backend = _normalize_backend_name(config.llm_backend)
    if backend in {"llama_cpp", "llamacpp", "gguf"}:
        return _build_llama_cpp_backend(config)
    if backend == "ollama":
        return OllamaBackend(config.ollama_url, config.ollama_model)
    raise ValueError(f"Unsupported ANALYZE_APP_LLM_BACKEND: {config.llm_backend}")


def build_project_overview_backend(config: AppConfig) -> ProjectOverviewAIBackend:
    backend = _normalize_backend_name(config.llm_backend)
    if backend in {"llama_cpp", "llamacpp", "gguf"}:
        return _build_llama_cpp_backend(config)
    if backend == "ollama":
        return ProjectOverviewBackend(config.ollama_url, config.ollama_model)
    raise ValueError(f"Unsupported ANALYZE_APP_LLM_BACKEND: {config.llm_backend}")


def _build_llama_cpp_backend(config: AppConfig) -> LlamaCppBackend:
    return LlamaCppBackend(
        model_path=config.llm_model_path,
        context_size=config.llm_context_size,
        n_threads=config.llm_threads,
        n_gpu_layers=config.llm_gpu_layers,
    )


def _normalize_backend_name(name: str) -> str:
    return name.strip().lower().replace("-", "_")
