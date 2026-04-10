from __future__ import annotations

import html
import json
from pathlib import Path

from markdown import markdown


def markdown_to_html(text: str) -> str:
    if not text.strip():
        return "<p class='muted'>Нет данных</p>"
    return markdown(text, extensions=["fenced_code", "tables"])


def escape_plain(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def render_html_template(template_path: Path, payload: dict) -> str:
    template = template_path.read_text(encoding="utf-8")
    return template.replace("__DATA_JSON__", json.dumps(payload, ensure_ascii=False))
