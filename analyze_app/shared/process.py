from __future__ import annotations


def decode_output(data: bytes | None) -> str:
    if not data:
        return ""

    for encoding in ("utf-8", "cp1251", "cp866"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace")
