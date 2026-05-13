from __future__ import annotations

import json
import os
from pathlib import Path

OLLAMA_MODEL_URI_PREFIX = "ollama://"


def resolve_ollama_model_uri(model_uri: str) -> Path:
    model_ref = model_uri.removeprefix(OLLAMA_MODEL_URI_PREFIX).strip()
    if not model_ref:
        raise ValueError("Ollama model URI is empty")

    registry, namespace, model_name, tag = _parse_model_ref(model_ref)
    models_root = Path(os.getenv("OLLAMA_MODELS", Path.home() / ".ollama" / "models")).expanduser()
    manifest_path = models_root / "manifests" / registry / namespace / model_name / tag
    if not manifest_path.exists():
        raise FileNotFoundError(f"Ollama manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model_layer = next(
        (
            layer
            for layer in manifest.get("layers", [])
            if layer.get("mediaType") == "application/vnd.ollama.image.model"
        ),
        None,
    )
    if not model_layer:
        raise ValueError(f"Ollama manifest has no model layer: {manifest_path}")

    digest = str(model_layer.get("digest", "")).replace(":", "-")
    if not digest:
        raise ValueError(f"Ollama model layer has no digest: {manifest_path}")

    blob_path = models_root / "blobs" / digest
    if not blob_path.exists():
        raise FileNotFoundError(f"Ollama model blob not found: {blob_path}")
    return blob_path


def _parse_model_ref(model_ref: str) -> tuple[str, str, str, str]:
    name, _, tag = model_ref.partition(":")
    tag = tag or "latest"
    parts = [part for part in name.split("/") if part]

    if len(parts) == 1:
        return "registry.ollama.ai", "library", parts[0], tag
    if len(parts) == 2:
        return "registry.ollama.ai", parts[0], parts[1], tag
    if len(parts) == 3:
        return parts[0], parts[1], parts[2], tag

    raise ValueError(f"Unsupported Ollama model reference: {model_ref}")
