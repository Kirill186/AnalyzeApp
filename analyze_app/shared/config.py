from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    db_path: Path = Path(os.getenv("ANALYZE_APP_DB_PATH", ".analyze_app.sqlite3"))
    clone_root: Path = Path(os.getenv("ANALYZE_APP_CLONE_ROOT", "./.analyze_repos"))
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
