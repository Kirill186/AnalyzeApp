from __future__ import annotations

import json
from urllib import request

from analyze_app.domain.entities import LLMResult


class OllamaBackend:
    def __init__(self, endpoint: str, model: str) -> None:
        self.endpoint = endpoint
        self.model = model

    def summarize_diff(self, diff_text: str) -> LLMResult:
        prompt = (
            "Суммаризируй изменения коммита. Ответь на русском в 3 пунктах: "
            "что изменено, риски, рекомендации.\n\n"
            f"DIFF:\n{diff_text[:8000]}"
        )
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        req = request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
                text = data.get("response", "AI summary is unavailable")
        except Exception as exc:  # noqa: BLE001
            text = f"AI summary unavailable: {exc}"
        return LLMResult(summary=text, model_info=f"ollama:{self.model}")
