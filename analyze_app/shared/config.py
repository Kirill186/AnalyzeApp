from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    db_path: Path = Path(".analyze_app.sqlite3")
    clone_root: Path = Path("./.analyze_repos")
    ollama_url: str = "http://localhost:11434/api/generate"
    ollama_model: str = "llama3.1"


DEFAULT_CONFIG = AppConfig()
