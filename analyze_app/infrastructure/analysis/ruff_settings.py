from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


RuffMode = Literal["respect", "extend", "override"]


RUFF_RULE_GROUPS: tuple[tuple[str, str], ...] = (
    ("E", "pycodestyle errors"),
    ("W", "pycodestyle warnings"),
    ("F", "Pyflakes"),
    ("I", "isort"),
    ("B", "flake8-bugbear"),
    ("UP", "pyupgrade"),
    ("SIM", "flake8-simplify"),
    ("S", "flake8-bandit"),
    ("PL", "Pylint"),
    ("RUF", "Ruff-specific"),
)


DEFAULT_RUFF_SELECT = ["E", "F", "I"]


@dataclass(slots=True)
class RegexRule:
    pattern: str
    message: str = ""
    enabled: bool = True


@dataclass(slots=True)
class RuffSettings:
    mode: RuffMode = "respect"
    select: list[str] = field(default_factory=lambda: DEFAULT_RUFF_SELECT.copy())
    ignore: list[str] = field(default_factory=list)
    preview: bool = False
    custom_rules_enabled: bool = True
    forbidden_calls: list[str] = field(default_factory=list)
    regex_rules: list[RegexRule] = field(default_factory=list)


def ruff_settings_from_mapping(payload: object) -> RuffSettings:
    if not isinstance(payload, dict):
        return RuffSettings()

    raw_mode = str(payload.get("mode") or "respect")
    mode: RuffMode = raw_mode if raw_mode in {"respect", "extend", "override"} else "respect"  # type: ignore[assignment]

    return RuffSettings(
        mode=mode,
        select=_coerce_code_list(payload.get("select"), default=DEFAULT_RUFF_SELECT),
        ignore=_coerce_code_list(payload.get("ignore"), default=[]),
        preview=_coerce_bool(payload.get("preview"), False),
        custom_rules_enabled=_coerce_bool(payload.get("custom_rules_enabled"), True),
        forbidden_calls=_coerce_call_list(payload.get("forbidden_calls")),
        regex_rules=_coerce_regex_rules(payload.get("regex_rules")),
    )


def ruff_settings_to_mapping(settings: RuffSettings) -> dict[str, object]:
    return {
        "mode": settings.mode,
        "select": _coerce_code_list(settings.select, default=DEFAULT_RUFF_SELECT),
        "ignore": _coerce_code_list(settings.ignore, default=[]),
        "preview": bool(settings.preview),
        "custom_rules_enabled": bool(settings.custom_rules_enabled),
        "forbidden_calls": _coerce_call_list(settings.forbidden_calls),
        "regex_rules": [
            {
                "pattern": rule.pattern.strip(),
                "message": rule.message.strip(),
                "enabled": bool(rule.enabled),
            }
            for rule in settings.regex_rules
            if rule.pattern.strip()
        ],
    }


def _coerce_code_list(value: object, *, default: list[str]) -> list[str]:
    if isinstance(value, str):
        candidates = value.replace(",", " ").split()
    elif isinstance(value, (list, tuple, set)):
        candidates = [str(item) for item in value]
    else:
        candidates = default

    parsed: list[str] = []
    for item in candidates:
        code = str(item or "").strip().upper()
        if code and code not in parsed:
            parsed.append(code)
    return parsed


def _coerce_call_list(value: object) -> list[str]:
    if isinstance(value, str):
        candidates = value.replace(",", " ").split()
    elif isinstance(value, (list, tuple, set)):
        candidates = [str(item) for item in value]
    else:
        candidates = []

    parsed: list[str] = []
    for item in candidates:
        call_name = str(item or "").strip()
        if call_name and call_name not in parsed:
            parsed.append(call_name)
    return parsed


def _coerce_regex_rules(value: object) -> list[RegexRule]:
    if not isinstance(value, list):
        return []

    rules: list[RegexRule] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        pattern = str(item.get("pattern") or "").strip()
        if not pattern:
            continue
        rules.append(
            RegexRule(
                pattern=pattern,
                message=str(item.get("message") or "").strip(),
                enabled=_coerce_bool(item.get("enabled"), True),
            )
        )
    return rules


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, int):
        return bool(value)
    return default
