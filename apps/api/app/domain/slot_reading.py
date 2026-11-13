"""Fail-closed reading of slot values from a classified document.

A document type declares which slots it may supply, and by which closed rule.
One unambiguous value is proposed. Doubt, a second value, or no text proposes nothing.
No model call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.text_layout import contains_hebrew
from app.schemas.process import DocumentReading, FieldSpec, ReadingRule
from app.services.field_validator import normalize_israeli_id, validate_field

_AMBIGUOUS = "ambiguous"
_LABEL_VALUE = re.compile(r"^(.+?)\s*[:：\-]\s*(.+)$")
_FOLLOWING_FIELD = re.compile(r"\sמספר\s+(?=\D)")
# A biometric card prints the number as prefix, seven digits, check digit: "1 0000000 9".
_SPACED_ID = re.compile(r"(?<!\d)(?<!\d )\d \d{7} \d(?! ?\d)")

_ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+")
# The translation beside a label, with the comma or slash that sets it apart.
_TRANSLATION = re.compile(r"[,،;/|]*\s*[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+(?:\s+[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+)*\s*[,،;/|]*")
_PUNCTUATION = re.compile(r"[,،;:.|/]")
_EDGES = " /|,.;:،"
# What a transcript adds around a printed line: emphasis marks, bullets, table bars.
_MARKUP = re.compile(r"\*\*|__|`")
_BULLET = re.compile(r"^\s*(?:#+|>+|[-*•])\s+")
_DIGITS_ONLY = re.compile(r"[\d\s\-]+")
# Street, house number, town, and an optional postal code, as a bill prints them on one line.
_HOUSE = r"(?P<number>\d{1,4}[א-ת]?(?:/\d{1,3})?)"
_ADDRESS = re.compile(r"^(?P<street>\D+?)\s+" + _HOUSE + r"(?:\s*,\s*|\s+)(?P<city>\D+?)(?:\s+\d{5,7})?$")
_STREET_AND_HOUSE = re.compile(r"^(?P<street>\D+?)\s+" + _HOUSE + r"$")
_STREET_WORD = re.compile(r"^(?:רחוב|רח['׳])\s+")


def _joined_digits(match: re.Match[str]) -> str:
    return match.group(0).replace(" ", "")


@dataclass(frozen=True)
class SlotProposal:
    slot_key: str
    value: str | None
    reason: str | None
    rule: str
    label: str | None


@dataclass(frozen=True)
class ReadOutcome:
    proposals: list[SlotProposal]
    blocked: str | None


def read_document(
    reading: DocumentReading,
    text: str,
    specs: list[FieldSpec],
    case_ids: set[str],
) -> ReadOutcome:
    """Propose values for an enabled reading. Disabled readings are not called."""
    by_key = {spec.key: spec for spec in specs}
    if not text.strip():
        return ReadOutcome(
            proposals=[
                SlotProposal(rule.slot_key, None, "no_text_layer", rule.kind, None)
                for rule in reading.rules
                if rule.slot_key in by_key
            ],
            blocked=None,
        )

    printed = [label for rule in reading.rules for label in rule.labels]
    printed += [label for rule in reading.rules for part in rule.parts for label in part.labels]
    proposals = [
        _propose(rule, text, by_key.get(rule.slot_key), reading.one_person, printed) for rule in reading.rules
    ]
    proposals = _collapse([item for item in proposals if item is not None])
    identity = [
        item.value
        for item in proposals
        if item.value and by_key[item.slot_key].field_type == "id_number"
    ]
    if case_ids and len(identity) == 1 and identity[0] not in case_ids:
        blocked = [
            SlotProposal(item.slot_key, None, "id_mismatch", item.rule, item.label) for item in proposals
        ]
        return ReadOutcome(proposals=blocked, blocked="id_mismatch")
    return ReadOutcome(proposals=proposals, blocked=None)


def apply_proposals(
    current: dict[str, str],
    proposals: list[SlotProposal],
) -> tuple[dict[str, str], list[SlotProposal], list[tuple[str, str]]]:
    """Write only into an empty slot. A different existing value is a conflict."""
    writes: dict[str, str] = {}
    skips: list[SlotProposal] = []
    conflicts: list[tuple[str, str]] = []
    for item in proposals:
        if item.value is None:
            skips.append(item)
            continue
        existing = current.get(item.slot_key, "").strip()
        if not existing:
            writes[item.slot_key] = item.value
            continue
        if existing == item.value:
            skips.append(SlotProposal(item.slot_key, None, "already_filled", item.rule, item.label))
            continue
        conflicts.append((item.slot_key, item.value))
    return writes, skips, conflicts


def retract_document(
    values: dict[str, str],
    sources: dict[str, dict],
    document_id: str,
) -> tuple[dict[str, str], dict[str, dict]]:
    """Drop values this document supplied, so a new classification has to earn them again."""
    kept_values = dict(values)
    kept_sources = dict(sources)
    for key, raw in list(sources.items()):
        if not isinstance(raw, dict):
            continue
        if raw.get("source") == "document" and raw.get("document_id") == document_id:
            kept_values.pop(key, None)
            kept_sources.pop(key, None)
    return kept_values, kept_sources


def _collapse(proposals: list[SlotProposal]) -> list[SlotProposal]:
    grouped: dict[str, list[SlotProposal]] = {}
    for item in proposals:
        grouped.setdefault(item.slot_key, []).append(item)
    collapsed: list[SlotProposal] = []
    for slot_key, items in grouped.items():
        values = {item.value for item in items if item.value}
        if len(values) > 1:
            collapsed.append(SlotProposal(slot_key, None, "ambiguous_match", items[0].rule, None))
        elif len(values) == 1:
            collapsed.append(next(item for item in items if item.value))
        else:
            doubt = next((item for item in items if item.reason == "ambiguous_match"), None)
            collapsed.append(doubt or items[0])
    return collapsed


def _propose(
    rule: ReadingRule,
    text: str,
    spec: FieldSpec | None,
    one_person: bool,
    printed: list[str],
) -> SlotProposal | None:
    if spec is None:
        return None
    if rule.kind == "unique" and (not one_person or spec.field_type == "date"):
        return SlotProposal(rule.slot_key, None, "label_not_found", rule.kind, None)
    raw, label = _raw_value(rule, text, spec, printed)
    if raw == _AMBIGUOUS:
        return SlotProposal(rule.slot_key, None, "ambiguous_match", rule.kind, label)
    if raw is None:
        return SlotProposal(rule.slot_key, None, "label_not_found", rule.kind, label)
    if spec.field_type == "text" and not _short_text(raw):
        return SlotProposal(rule.slot_key, None, "validator_rejected", rule.kind, label)
    result = validate_field(spec, raw)
    if not result.ok:
        return SlotProposal(rule.slot_key, None, "validator_rejected", rule.kind, label)
    return SlotProposal(rule.slot_key, result.normalized, None, rule.kind, label)


def _raw_value(
    rule: ReadingRule, text: str, spec: FieldSpec, printed: list[str]
) -> tuple[str | None, str | None]:
    if rule.kind == "composite":
        return _composite(rule, text, printed)
    if rule.kind == "labeled" or rule.labels:
        raw, label = _labeled(text, rule.labels, printed)
        if rule.piece and raw is not None and raw != _AMBIGUOUS:
            raw = _address_piece(raw, rule.piece)
        return raw, label
    if rule.kind == "unique":
        return _unique(text, spec), None
    return None, None


def _composite(rule: ReadingRule, text: str, printed: list[str]) -> tuple[str | None, str | None]:
    parts: list[str] = []
    labels: list[str] = []
    for part in rule.parts:
        raw, label = _labeled(text, part.labels, printed)
        if raw == _AMBIGUOUS:
            return _AMBIGUOUS, label
        if raw is None:
            return None, label
        parts.append(raw)
        if label:
            labels.append(label)
    return " ".join(parts), " + ".join(labels) or None


def _labeled(text: str, labels: list[str], printed: list[str]) -> tuple[str | None, str | None]:
    if not labels:
        return None, None
    found: dict[str, str] = {}
    for orientation in _orientations(text):
        lines = [plain for line in orientation.splitlines() if (plain := _plain(line))]
        normalized = {_norm(label): label for label in labels}
        known = {**{_norm(label): label for label in printed}, **normalized}
        taken = -1
        for index, raw_line in enumerate(lines):
            if index == taken:
                # This line was the value of the label above it. "בנק לדוגמה" is not a new label.
                continue
            line = _without_translation(raw_line, normalized)
            split = _split_label(line, normalized)
            if split is not None:
                _keep(found, normalized, split[1])
                continue
            if _only_labels(line, normalized):
                # The label stands alone, or beside its translation. The value is the line below.
                if index + 1 < len(lines):
                    below = lines[index + 1].strip()
                    value = _clip_value(below, list(normalized.values()))
                    if value and not _is_label_line(below, known):
                        found[_value_key(value)] = value
                        taken = index + 1
                continue
            leading = _leading_label(line, list(normalized.values()))
            if leading is not None and leading[1].strip():
                _keep(found, normalized, leading[1], skip=leading[0])
    if len(found) > 1:
        return _AMBIGUOUS, None
    if len(found) == 1:
        value = next(iter(found.values()))
        return value, _matched_label(value, text, labels)
    return None, None


def _without_translation(line: str, labels: dict[str, str]) -> str:
    """Drop the Arabic printed beside a known label, as an identity card does."""
    if not _ARABIC.search(line):
        return line
    folded = f" {_norm(_PUNCTUATION.sub(' ', line))} "
    if not any(f" {key} " in folded for key in labels):
        return line
    return " ".join(_TRANSLATION.sub(" ", line).split()).strip(_EDGES)


def _plain(line: str) -> str:
    """The printed words of a transcript line, without emphasis marks, bullets or table bars."""
    line = _BULLET.sub("", _MARKUP.sub("", line)).strip()
    if "|" not in line:
        return line
    cells = [cell.strip() for cell in line.split("|")]
    cells = [cell for cell in cells if cell and set(cell) - set("-: ")]
    if len(cells) == 2:
        # A two-cell row is a label and its value.
        return f"{cells[0]}: {cells[1]}"
    return cells[0] if len(cells) == 1 else line


def _value_key(value: str) -> str:
    """The same number is one value however its digits are spaced."""
    if _DIGITS_ONLY.fullmatch(value):
        return re.sub(r"\D", "", value)
    return _norm(value)


def _address_piece(value: str, piece: str) -> str | None:
    """One piece of a printed address line. A line with no house number is left whole, as the street."""
    value = value.strip()
    match = _ADDRESS.match(value) or _STREET_AND_HOUSE.match(value)
    if match is None:
        return value if piece == "street" else None
    found = (match.groupdict().get("number" if piece == "house_number" else piece) or "").strip(" ,-–")
    if piece == "street":
        found = _STREET_WORD.sub("", found)
    return found or None


def _is_label_line(line: str, known: dict[str, str]) -> bool:
    """A line that is another label of this document, or looks like a two-language label."""
    if _only_labels(_without_translation(line, known), known):
        return True
    return bool(_ARABIC.search(line)) and contains_hebrew(line)


def _only_labels(line: str, labels: dict[str, str]) -> bool:
    """True when the line is one label, or the same label in more than one language."""
    rest = _norm(line)
    if not rest:
        return False
    keys = sorted(labels, key=len, reverse=True)
    while rest:
        for key in keys:
            if rest == key or rest.startswith(key + " "):
                rest = rest[len(key) :].strip(_EDGES + "-")
                break
        else:
            return False
    return True


def _matched_label(value: str, text: str, labels: list[str]) -> str | None:
    folded = _norm(value)
    for orientation in _orientations(text):
        for label in labels:
            if _norm(label) in _norm(orientation) and folded in _norm(orientation):
                return label
    return labels[0]


def _unique(text: str, spec: FieldSpec) -> str | None:
    found: set[str] = set()
    for orientation in _orientations(text):
        if spec.field_type == "id_number":
            for run in re.findall(r"\d{7,9}", _SPACED_ID.sub(_joined_digits, orientation)):
                normalized = normalize_israeli_id(run)
                if normalized:
                    found.add(normalized)
        elif spec.field_type == "email":
            for match in re.findall(r"[^@\s]+@[^@\s]+\.[^@\s]+", orientation):
                result = validate_field(spec, match)
                if result.ok:
                    found.add(result.normalized)
        elif spec.field_type == "phone":
            for match in re.findall(r"\+?\d[\d\-\s]{7,16}\d", orientation):
                result = validate_field(spec, match)
                if result.ok:
                    found.add(result.normalized)
    if len(found) > 1:
        return _AMBIGUOUS
    if len(found) == 1:
        return next(iter(found))
    return None


def _keep(
    found: dict[str, str],
    labels: dict[str, str],
    value: str,
    skip: str | None = None,
) -> None:
    clipped = _clip_value(value, [item for item in labels.values() if item != skip])
    if clipped and _norm(clipped) not in labels:
        found[_value_key(clipped)] = clipped


def _clip_value(value: str, labels: list[str]) -> str:
    """Keep the address, and drop the next column when a bill prints it on the same line."""
    cut = len(value)
    for label in labels:
        index = value.find(label)
        if index > 0:
            cut = min(cut, index)
    following = _FOLLOWING_FIELD.search(value)
    if following is not None:
        cut = min(cut, following.start())
    return value[:cut].strip(" \t:：-–—")


def _leading_label(line: str, labels: list[str]) -> tuple[str, str] | None:
    """A label at the start of the line, with the value after it and no colon."""
    raw = line.strip()
    folded = _norm(raw)
    for label in sorted(labels, key=lambda item: len(_norm(item)), reverse=True):
        prefix = _norm(label)
        if folded != prefix and not folded.startswith(prefix + " "):
            continue
        head = raw[: len(label)]
        if _norm(head) != prefix:
            continue
        return label, raw[len(label) :].strip()
    return None


def _split_label(line: str, labels: dict[str, str]) -> tuple[str, str] | None:
    match = _LABEL_VALUE.match(line.strip())
    if match is None:
        return None
    left, right = match.group(1).strip(), match.group(2).strip()
    if _norm(left) in labels and right:
        return labels[_norm(left)], right
    if _norm(right) in labels and left:
        return labels[_norm(right)], left
    return None


def _orientations(text: str) -> list[str]:
    lines = text.splitlines() or [text]
    flipped: list[str] = []
    changed = False
    for line in lines:
        if contains_hebrew(line):
            reversed_line = line[::-1]
            flipped.append(reversed_line)
            changed = changed or reversed_line != line
        else:
            flipped.append(line)
    versions = [text]
    if changed:
        versions.append("\n".join(flipped))
    return versions


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _short_text(value: str) -> bool:
    words = value.split()
    return len(value) <= 80 and 0 < len(words) <= 6
