from __future__ import annotations

import re

from pydantic import BaseModel

from app.config import SETTINGS

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\-\s()]{8,}\d)(?!\d)")
_CARD_RE = re.compile(r"(?<!\d)(\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})(?!\d)")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")

# Regex-based to catch the common variants — e.g. "игнорируй ВСЕ инструкции",
# "забудь все предыдущие", "ignore all previous", "ignore the system prompt".
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore-previous",
        re.compile(r"\bignore\s+(?:all\s+|the\s+)?(?:previous|prior|above|earlier)\b", re.IGNORECASE),
    ),
    (
        "disregard-previous",
        re.compile(
            r"\bdisregard\s+(?:all\s+|the\s+)?(?:previous|prior|above|earlier|instructions?)\b", re.IGNORECASE
        ),
    ),
    ("system-prompt", re.compile(r"\b(?:system\s+prompt|raw\s+mode|jailbreak)\b", re.IGNORECASE)),
    (
        "act-as",
        re.compile(r"\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be|roleplay\s+as)\b", re.IGNORECASE),
    ),
    (
        "ru-ignore",
        re.compile(
            r"\bигнорир(?:уй|овать|уйте)\s+(?:все\s+|любые\s+|предыдущ\w+\s+)*(?:инструкц\w+|правил\w+|систем\w+)?",
            re.IGNORECASE,
        ),
    ),
    (
        "ru-forget",
        re.compile(
            r"\bзабудь(?:те)?\s+(?:все\s+|любые\s+|предыдущ\w+\s+)*(?:инструкц\w+|правил\w+)?", re.IGNORECASE
        ),
    ),
    ("ru-you-are-now", re.compile(r"\bты\s+(?:теперь|сейчас)\b", re.IGNORECASE)),
    ("ru-new-instructions", re.compile(r"\bнов(?:ые|ая|ыми)\s+инструкц\w+", re.IGNORECASE)),
    ("ru-system-prompt", re.compile(r"\b(?:систем(?:а|ный)\s+промпт|сырой\s+режим)\b", re.IGNORECASE)),
)

# Rule-based toxicity detector — pure stdlib, runs on CPU in microseconds, no model files.
# Obscenity stems allow a short optional Cyrillic prefix (за-, на-, по-, под-, …) — without
# this, prefixed mat like "заебал" / "нахуй" / "охуенно" wouldn't match. Insult/threat/EN stems
# use a strict word boundary instead, since those are rarely prefixed.
_TOX_OBSCENITY_RU = (
    "хуй",
    "хуёв",
    "хуя",
    "хуе",
    "пизд",
    "пизде",
    "бляд",
    "блядь",
    "блять",
    "ебан",
    "ебал",
    "ебат",
    "ебуч",
    "ёбан",
    "ёбал",
    "ёбат",
    "ёбуч",
    "залуп",
    "мраз",
    "мудак",
    "пидор",
    "херн",
    "сук",
    "говн",
    "срат",
    "ссат",
)
_TOX_INSULT_RU = (
    "идиот",
    "идиотск",
    "придур",
    "дурак",
    "дурац",
    "тупой",
    "тупая",
    "тупиц",
    "урод",
    "ублюдок",
    "сволоч",
    "гад",
    "дебил",
    "кретин",
    "ничтожеств",
    "лошар",
)
_TOX_THREAT_RU = (
    "убью",
    "убить",
    "убей",
    "укокош",
    "сдохн",
    "сдохни",
    "разорв",
    "избит",
    "избью",
    "грохн",
    "повеш",
    "размозж",
)
_TOX_EN = (
    "fuck",
    "shit",
    "bitch",
    "asshole",
    "bastard",
    "moron",
    "retard",
    "kill you",
    "kill yourself",
    "go die",
)


def _toxicity_regex(stems: tuple[str, ...], *, allow_ru_prefix: bool = False) -> re.Pattern[str]:
    alt = "|".join(re.escape(s) for s in stems)
    prefix = r"(?:[а-яё]{0,4})?" if allow_ru_prefix else ""
    return re.compile(r"\b" + prefix + r"(?:" + alt + r")\w*", re.IGNORECASE)


_TOX_PATTERNS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    ("obscenity", _toxicity_regex(_TOX_OBSCENITY_RU, allow_ru_prefix=True), 0.5),
    ("insult", _toxicity_regex(_TOX_INSULT_RU), 0.5),
    ("threat", _toxicity_regex(_TOX_THREAT_RU), 0.7),
    ("en-toxic", _toxicity_regex(_TOX_EN), 0.5),
)

_DESTRUCTIVE_TOOLS = {"delete_transaction", "reset_budget", "delete_goal", "wipe_user_data"}


class ToxicityReport(BaseModel):
    score: float
    categories: list[str]
    hits: list[str]


class SafetyReport(BaseModel):
    redacted_text: str
    pii_hits: list[str]
    injection_suspected: bool
    injection_markers: list[str]
    toxic: bool
    toxicity_score: float
    toxicity_categories: list[str]
    toxicity_hits: list[str]


def redact_pii(text: str) -> tuple[str, list[str]]:
    if not SETTINGS.pii_redaction_enabled:
        return text, []
    hits: list[str] = []

    def _sub(label: str, pattern: re.Pattern[str], s: str) -> str:
        def repl(_m: re.Match[str]) -> str:
            hits.append(label)
            return f"[{label}]"

        return pattern.sub(repl, s)

    out = _sub("EMAIL", _EMAIL_RE, text)
    out = _sub("CARD", _CARD_RE, out)
    out = _sub("IBAN", _IBAN_RE, out)
    out = _sub("PHONE", _PHONE_RE, out)
    return out, hits


def detect_injection(text: str) -> list[str]:
    return [name for name, pattern in _INJECTION_PATTERNS if pattern.search(text)]


def score_toxicity(text: str) -> ToxicityReport:
    """Lightweight rule-based Russian + English toxicity check (no ML, no network)."""
    categories: list[str] = []
    hits: list[str] = []
    score = 0.0
    for label, pattern, weight in _TOX_PATTERNS:
        matches = pattern.findall(text)
        if not matches:
            continue
        categories.append(label)
        hits.extend(m.lower() for m in matches)
        score += weight * len(matches)
    return ToxicityReport(score=min(1.0, score), categories=categories, hits=hits)


def screen_user_input(text: str) -> SafetyReport:
    redacted, pii_hits = redact_pii(text)
    markers = detect_injection(text)
    tox = score_toxicity(text)
    return SafetyReport(
        redacted_text=redacted,
        pii_hits=pii_hits,
        injection_suspected=bool(markers),
        injection_markers=markers,
        toxic=tox.score >= SETTINGS.toxicity_threshold,
        toxicity_score=tox.score,
        toxicity_categories=tox.categories,
        toxicity_hits=tox.hits,
    )


def requires_confirmation(tool_name: str) -> bool:
    return tool_name in _DESTRUCTIVE_TOOLS
