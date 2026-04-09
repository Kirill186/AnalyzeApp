from __future__ import annotations

import json
import re
from urllib import request

from analyze_app.domain.entities import EvidenceBlock, LLMResult


class OllamaBackend:
    def __init__(self, endpoint: str, model: str) -> None:
        self.endpoint = endpoint
        self.model = model

    def summarize_diff(self, diff_text: str) -> LLMResult:
        prompt = (
            "Суммаризируй изменения. Ответь на русском в формате:\n"
            "1) Что изменено\n2) Риски\n3) Рекомендации\n4) Evidence blocks (файл: причина).\n\n"
            f"DIFF:\n{diff_text[:8000]}"
        )

        # Основной путь: локальный SDK ollama (как в вашем рабочем скрипте).
        try:
            import ollama

            response = ollama.generate(
                model=self.model,
                prompt=prompt,
                options={"temperature": 0.1, "top_p": 0.9, "repeat_penalty": 1.1, "num_predict": 260},
            )
            text = response.get("response", "AI summary is unavailable")
            return LLMResult(
                summary=text,
                model_info=f"ollama-sdk:{self.model}",
                evidence=self._extract_evidence(diff_text, text),
            )
        except Exception as exc:  # noqa: BLE001
            sdk_error = self._humanize_error(exc)

        # Fallback: HTTP API (на случай, если SDK не установлен).
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
            return LLMResult(
                summary=text,
                model_info=f"ollama-http:{self.model}",
                evidence=self._extract_evidence(diff_text, text),
            )
        except Exception as exc:  # noqa: BLE001
            http_error = self._humanize_error(exc)
            return LLMResult(
                summary=f"AI summary unavailable: {sdk_error}; {http_error}",
                model_info=f"ollama:{self.model}",
                evidence=self._extract_evidence(diff_text, ""),
            )

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

    def _humanize_error(self, exc: Exception) -> str:
        message = str(exc)
        if "404" in message:
            return f"model '{self.model}' not found in Ollama. Run: ollama pull {self.model}"
        return message
