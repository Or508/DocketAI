"""Structural anchors for vector memory.

The learning store must not embed raw client documents. These helpers keep
headers, field labels, and boilerplate legal lines, and strip identifiers,
phone numbers, emails, and the values that sit beside a label.
"""

import hashlib
import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:\+?\d[\d\-\s().]{7,}\d)")
_ID = re.compile(r"\b\d{7,9}\b")
_LONG_DIGITS = re.compile(r"\d{4,}")
_BOILERPLATE = (
    "form",
    "declaration",
    "agreement",
    "section",
    "article",
    "schedule",
    "appendix",
    "whereas",
    "hereby",
    "undersigned",
    "terms and conditions",
    "טופס",
    "הצהרה",
    "סעיף",
    "נספח",
    "הסכם",
    "אישור",
)


def anchors_from_text(text: str, limit: int = 12) -> list[str]:
    anchors: list[str] = []
    for raw in (text or "").splitlines():
        anchor = _anchor(" ".join(raw.split()))
        if anchor and anchor not in anchors:
            anchors.append(anchor)
        if len(anchors) >= limit:
            break
    return anchors


def structural_signature(anchors: list[str]) -> str:
    blob = "\n".join(sorted(anchors)).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def embedding_text(anchors: list[str]) -> str:
    return "\n".join(anchors)[:1_200]


def _anchor(line: str) -> str | None:
    if len(line) < 3:
        return None
    cleaned = _redact(line)
    if not cleaned or cleaned == "[redacted]":
        return None
    if ":" in cleaned:
        label, _, value = cleaned.partition(":")
        label = label.strip()
        value = value.strip()
        if not 2 <= len(label) <= 80:
            return None
        if len(value) > 40 and _is_boilerplate(value):
            return f"{label}: {value[:220]}"
        return f"{label}:"
    if _is_boilerplate(cleaned) and len(cleaned) >= 12:
        return cleaned[:220]
    letters = [character for character in cleaned if character.isalpha()]
    has_latin_cap = any("A" <= character <= "Z" for character in cleaned)
    if letters and has_latin_cap and cleaned.upper() == cleaned and 4 <= len(cleaned) <= 80:
        return cleaned
    return None


def _redact(line: str) -> str:
    line = _EMAIL.sub("[redacted]", line)
    line = _PHONE.sub("[redacted]", line)
    line = _ID.sub("[redacted]", line)
    line = _LONG_DIGITS.sub("", line)
    return " ".join(line.split())


def _is_boilerplate(line: str) -> bool:
    lowered = line.lower()
    return any(token in lowered for token in _BOILERPLATE)
