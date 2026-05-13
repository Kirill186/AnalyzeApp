from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(slots=True)
class AppConfig:
    db_path: Path = Path(os.getenv("ANALYZE_APP_DB_PATH", ".analyze_app.sqlite3"))
    clone_root: Path = Path(os.getenv("ANALYZE_APP_CLONE_ROOT", "./.analyze_repos"))
    llm_backend: str = os.getenv("ANALYZE_APP_LLM_BACKEND", "llama_cpp")
    llm_model_path: str = os.getenv("ANALYZE_APP_LLM_MODEL_PATH", "ollama://llama3.2:latest")
    llm_context_size: int = _env_int("ANALYZE_APP_LLM_CONTEXT_SIZE", 4096)
    llm_threads: int = _env_int("ANALYZE_APP_LLM_THREADS", 0)
    llm_gpu_layers: int = _env_int("ANALYZE_APP_LLM_GPU_LAYERS", 0)
    ollama_url: str = os.getenv("ANALYZE_APP_OLLAMA_URL", "http://localhost:11434/api/generate")
    ollama_model: str = os.getenv("ANALYZE_APP_OLLAMA_MODEL", "llama3.2:latest")
    ai_authorship_model_path: Path = Path(
        os.getenv("ANALYZE_APP_AI_AUTHORSHIP_MODEL_PATH", "analyze_app/infrastructure/ai/authorship/default_model.json")
    )
    ai_authorship_calibration_path: Path = Path(
        os.getenv(
            "ANALYZE_APP_AI_AUTHORSHIP_CALIBRATION_PATH",
            "analyze_app/infrastructure/ai/authorship/default_calibration.json",
        )
    )


DEFAULT_CONFIG = AppConfig()
