from __future__ import annotations

import json
from urllib import request

from analyze_app.domain.entities import ProjectOverviewResult


class ProjectOverviewBackend:
    def __init__(self, endpoint: str, model: str) -> None:
        self.endpoint = endpoint
        self.model = model

    def summarize_project(self, context: str) -> ProjectOverviewResult:
        prompt = (
            "Ты готовишь описание репозитория для страницы проекта.\n"
            "Напиши 1-2 плотных абзаца на русском языке:\n"
            "1) в чем суть проекта и какую задачу он решает;\n"
            "2) как устроена его структура (ключевые слои/модули).\n"
            "Без списков и без markdown.\n\n"
            f"CONTEXT:\n{context[:12000]}"
        )

        try:
            import ollama

            response = ollama.generate(
                model=self.model,
                prompt=prompt,
                options={"temperature": 0.2, "top_p": 0.9, "repeat_penalty": 1.1, "num_predict": 280},
            )
            return ProjectOverviewResult(
                summary=response.get("response", "Project overview is unavailable"),
                model_info=f"ollama-sdk:{self.model}",
            )
        except Exception as exc:  # noqa: BLE001
            sdk_error = self._humanize_error(exc)

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
            return ProjectOverviewResult(
                summary=data.get("response", "Project overview is unavailable"),
                model_info=f"ollama-http:{self.model}",
            )
        except Exception as exc:  # noqa: BLE001
            http_error = self._humanize_error(exc)
            return ProjectOverviewResult(
                summary=f"Project overview unavailable: {sdk_error}; {http_error}",
                model_info=f"ollama:{self.model}",
            )

    def _humanize_error(self, exc: Exception) -> str:
        message = str(exc)
        if "404" in message:
            return f"model '{self.model}' not found in Ollama. Run: ollama pull {self.model}"
        return message
