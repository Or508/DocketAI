"""Anchor and fill a flat PDF form: printed labels, drawn cells, and no AcroForm widgets.

read_flat_anchors binds each printed label to a process slot and to the cell, digit
boxes, or rule drawn for its value. fill_flat_form paints slot values into those
targets on a copy, then reopens the bytes and reads each value back. sign_flat_form
does the same and seals the result. The source file is never written.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import fitz

from app.core.exceptions import UnprocessableError
from app.domain.certificate import CertificateData, format_times
from app.domain.flat_anchors import Box, Segment, Word, find_labels, fold, resolve_target, section_of
from app.domain.form_anchors import SYNONYMS
from app.domain.text_layout import contains_hebrew
from app.schemas.process import FieldSpec
from app.services.certificate_page import add_certificate_page
from app.services.pdf_filler import (
    _FONT_SIZES,
    FieldFill,
    FilledForm,
    PdfFillerService,
    SignedArtifact,
    _draft_mark,
    _embed,
    _hebrew_font,
    _paint_rtl,
    _pin_dates,
    _readback_matches,
    _stable_id,
    _text_width,
)

_SIGNATURE_HEIGHTS = (40.0, 32.0, 24.0)
_MAX_PAGES = 20
_MAX_ANCHORS = 500
_LINE_FACTOR = 1.45
_INK = (0.11, 0.1, 0.08)


@dataclass(frozen=True)
class FlatProfile:
    """What a process declares about its flat form. All lists are closed.

    labels: extra printed labels per slot, beside the slot's own label and the synonym table.
    sections: every section title printed on the form, including sections that are not filled.
    slot_section: the section a slot's label must stand under. A slot named here binds nowhere else.
    """

    labels: dict[str, list[str]] = field(default_factory=dict)
    sections: list[str] = field(default_factory=list)
    slot_section: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_layout(cls, layout: dict | None) -> FlatProfile:
        raw = (layout or {}).get("flat_form") or {}
        return cls(
            labels={str(key): [str(item) for item in value] for key, value in (raw.get("labels") or {}).items()},
            sections=[str(item) for item in raw.get("sections") or []],
            slot_section={str(key): str(value) for key, value in (raw.get("slot_section") or {}).items()},
        )


@dataclass(frozen=True)
class _Page:
    words: list[Word]
    segments: list[Segment]
    panels: list[Box]
    marks: list[Box]


def read_flat_anchors(path: Path, fields: list[FieldSpec], profile: FlatProfile | None = None) -> list[dict]:
    """Anchors in the same shape as widget anchors, with kind "flat".

    A label with no drawn target is left out. So is a slot whose label resolves to more
    than one target: one slot, one place, or nothing.
    """
    profile = profile or FlatProfile()
    vocabulary = _vocabulary(fields, profile)
    found: dict[str, list[dict]] = {}
    document = fitz.open(path)
    try:
        for index, page in enumerate(document):
            if index >= _MAX_PAGES:
                break
            geometry = _read_page(page)
            sections = find_labels(geometry.words, profile.sections, whole=False) if profile.sections else []
            hits = sorted(find_labels(geometry.words, list(vocabulary)), key=lambda hit: (hit.box[1], -hit.box[0]))
            for hit in hits:
                key, match = vocabulary[hit.label]
                wanted = profile.slot_section.get(key)
                if wanted is not None and section_of(hit.box, sections) != wanted:
                    continue
                target = resolve_target(hit, geometry.words, geometry.segments, geometry.panels, geometry.marks)
                if target is None:
                    continue
                anchor = {
                    "kind": "flat",
                    "field_name": f"flat:{index}:{key}:1",
                    "label": hit.label,
                    "target": target.kind,
                    "page": index,
                    "rect": [round(value, 2) for value in target.rect],
                    "empty": True,
                    "value": None,
                    "slot_key": key,
                    "match": match,
                }
                if target.boxes:
                    anchor["boxes"] = [[round(value, 2) for value in box] for box in target.boxes]
                found.setdefault(key, []).append(anchor)
    finally:
        document.close()
    anchors = [items[0] for items in found.values() if len(items) == 1]
    anchors.sort(key=lambda anchor: (anchor["page"], anchor["rect"][1], -anchor["rect"][0]))
    return anchors[:_MAX_ANCHORS]


@dataclass
class _Plan:
    anchor: dict
    value: str
    size: float | None
    status: str = "ok"

    @property
    def comb(self) -> bool:
        return self.anchor.get("target") == "comb"


def fill_flat_form(
    pdf_bytes: bytes,
    anchors: list[dict],
    values: dict[str, str],
    font_path: Path | None,
) -> FilledForm:
    """Paint values[field_name] into each flat anchor and verify by reopening the result."""
    plans: list[_Plan] = []
    for anchor in anchors:
        if anchor.get("kind") != "flat":
            continue
        value = values.get(str(anchor.get("field_name") or ""), "").strip()
        if not value:
            continue
        if font_path is None:
            raise UnprocessableError("A Hebrew font is required before this form can be filled.")
        if anchor.get("target") == "comb":
            digits = re.sub(r"\D", "", value)
            boxes = anchor.get("boxes") or []
            fits = bool(digits) and len(digits) == len(boxes) and not re.search(r"[^\d\s\-+]", value)
            plans.append(_Plan(anchor, digits, _comb_size(boxes) if fits else None))
        else:
            plans.append(_Plan(anchor, value, _fit(value, fitz.Rect(anchor["rect"]), font_path)))
    if not plans:
        return FilledForm(pdf_bytes=pdf_bytes, fields=[])

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for plan in plans:
            if plan.size is None:
                plan.status = "overflow"
            elif document[int(plan.anchor["page"])].get_text("text", clip=fitz.Rect(plan.anchor["rect"])).strip():
                plan.status = "skipped_prefilled"
        for plan in plans:
            if plan.status != "ok":
                continue
            page = document[int(plan.anchor["page"])]
            if plan.comb:
                _paint_comb(page, plan.anchor["boxes"], plan.value, font_path, plan.size)
            else:
                _paint_rtl(page, fitz.Rect(plan.anchor["rect"]), plan.value, font_path, plan.size)
        _pin_dates(document)
        out = _stable_id(document.tobytes(garbage=4, deflate=True))
    finally:
        document.close()

    written = fitz.open(stream=out, filetype="pdf")
    try:
        for plan in plans:
            if plan.status != "ok":
                continue
            page = written[int(plan.anchor["page"])]
            rect = fitz.Rect(plan.anchor["rect"])
            if plan.comb:
                read = sorted(page.get_text("words", clip=rect), key=lambda word: word[0])
                ok = "".join(word[4] for word in read) == plan.value
            else:
                ok = _readback_matches(plan.value, page.get_text("text", clip=rect), contains_hebrew(plan.value))
            if not ok:
                plan.status = "mismatch"
    finally:
        written.close()
    fields = [
        FieldFill(
            str(plan.anchor["field_name"]),
            int(plan.anchor["page"]),
            plan.status,  # type: ignore[arg-type]
            plan.size if plan.status in ("ok", "mismatch") else None,
        )
        for plan in plans
    ]
    return FilledForm(pdf_bytes=out, fields=fields)


def signature_box(path: Path, labels: list[str]) -> tuple[int, list[float]]:
    """The one drawn place for a signature on this form. None, or more than one, is refused."""
    found: list[tuple[int, list[float]]] = []
    document = fitz.open(path)
    try:
        for index, page in enumerate(document):
            if index >= _MAX_PAGES:
                break
            geometry = _read_page(page)
            for hit in find_labels(geometry.words, labels):
                target = resolve_target(hit, geometry.words, geometry.segments, geometry.panels, geometry.marks)
                if target is None or target.kind == "comb":
                    continue
                x0, y0, x1, y1 = target.rect
                if target.kind == "underline":
                    # A writing rule leaves one text line. Take more room above it when it is blank.
                    for height in _SIGNATURE_HEIGHTS:
                        tall = fitz.Rect(x0, y1 - height, x1, y1)
                        if not page.get_text("text", clip=tall).strip():
                            y0 = tall.y0
                            break
                found.append((index, [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]))
    finally:
        document.close()
    if not found:
        raise UnprocessableError("This form has no signature box that can be located.")
    if len(found) > 1:
        raise UnprocessableError("This form has more than one signature box.")
    return found[0]


def preview_flat_form(
    filler: PdfFillerService,
    *,
    source_path: Path,
    anchors: list[dict],
    values: dict[str, str],
    rtl_names: set[str],
) -> bytes:
    """The uploaded form with the case values, marked as an unsigned draft."""
    filled = filler.fill_case_form(source_path=source_path, values=values, rtl_names=rtl_names)
    flat = fill_flat_form(filled.pdf_bytes, anchors, values, filler._resolved_font())
    document = fitz.open(stream=flat.pdf_bytes, filetype="pdf")
    try:
        for page in document:
            _draft_mark(page)
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def sign_flat_form(
    filler: PdfFillerService,
    *,
    source_path: Path,
    output_path: Path,
    anchors: list[dict],
    values: dict[str, str],
    rtl_names: set[str],
    signature_png: bytes,
    signature_labels: list[str],
    certificate: CertificateData,
    signed_at: datetime,
) -> SignedArtifact:
    """Fill the uploaded form, stamp the signature in its drawn box, then seal it like a template.

    Refused unless every value landed and read back, and the form shows exactly one signature box.
    The content digest is the filled and signed form before the certificate page and footers.
    """
    font_path = filler._resolved_font()
    page_index, rect = signature_box(source_path, signature_labels)
    filled = filler.fill_case_form(source_path=source_path, values=values, rtl_names=rtl_names)
    flat = fill_flat_form(filled.pdf_bytes, anchors, values, font_path)
    results = [*filled.fields, *flat.fields]
    failed = sorted({item.field_name for item in results if item.status != "ok"})
    placed = {item.field_name for item in results}
    unplaced = sorted(name for name, value in values.items() if value.strip() and name not in placed)
    if failed or unplaced:
        names = ", ".join([*failed, *unplaced])
        raise UnprocessableError(f"These values could not be written on the form: {names}.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open(stream=flat.pdf_bytes, filetype="pdf")
    try:
        document[page_index].insert_image(
            fitz.Rect(*rect), stream=signature_png, keep_proportion=True, overlay=True
        )
        document.bake(annots=True, widgets=True)
        form_bytes = document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()
    digest = hashlib.sha256(form_bytes).hexdigest()
    form_path = output_path.with_name(output_path.stem + "-form.pdf")
    form_path.write_bytes(form_bytes)
    # tobytes(garbage=4) leaves the open document unable to embed a font.
    document = fitz.open(stream=form_bytes, filetype="pdf")
    try:
        try:
            add_certificate_page(
                document,
                certificate,
                content_sha256=digest,
                signature_png=signature_png,
                font_path=font_path,
            )
            _stamp_audit_clear(
                document,
                case_reference=certificate.case_reference,
                signed_at=signed_at,
                digest=digest,
                signer_id=certificate.signer_verification_id,
                font_path=font_path,
            )
            document.save(output_path, garbage=4, deflate=True)
            file_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
        except Exception:
            form_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
            raise
        return SignedArtifact(
            content_sha256=digest,
            file_sha256=file_sha256,
            signer_verification_id=certificate.signer_verification_id,
            content_path=form_path,
            total_pages=document.page_count,
        )
    finally:
        document.close()


def _stamp_audit_clear(
    document,
    *,
    case_reference: str,
    signed_at: datetime,
    digest: str,
    signer_id: str,
    font_path: Path | None,
) -> None:
    """The audit line of _stamp_audit, put in a margin the form leaves blank.

    A template keeps its bottom margin free. A real form may print there, so each page
    takes the first blank strip: bottom, then top. A page with neither is refused.
    """
    utc, local = format_times(signed_at)
    total = document.page_count
    for index, page in enumerate(document, start=1):
        banner = (
            f"Ref {case_reference} | UTC {utc} | Israel {local} | Signer {signer_id} | "
            f"Page {index} of {total}\nContent SHA-256 {digest}"
        )
        strip = _blank_strip(page)
        if strip is None:
            raise UnprocessableError(f"Page {index} has no blank margin for the audit line.")
        fontname = _embed(page, font_path) if font_path is not None else "helv"
        edge = strip.y0 - 2 if strip.y0 > page.rect.height / 2 else strip.y1 + 2
        page.draw_line(
            fitz.Point(28, edge), fitz.Point(page.rect.width - 28, edge), color=(0.75, 0.72, 0.66), width=0.4
        )
        spare = page.insert_textbox(
            strip, banner, fontname=fontname, fontsize=6, align=fitz.TEXT_ALIGN_CENTER, color=(0.42, 0.4, 0.36)
        )
        if isinstance(spare, str) or spare < 0:
            raise UnprocessableError("The audit footer did not fit.")


def _blank_strip(page) -> fitz.Rect | None:
    width, height = page.rect.width, page.rect.height
    strips = (
        fitz.Rect(24, height - 34, width - 24, height - 4),
        fitz.Rect(24, height - 22, width - 24, height - 4),
        # Clear of a form number printed in the bottom corner.
        fitz.Rect(24, height - 22, width - 120, height - 4),
        fitz.Rect(24, 4, width - 24, 22),
    )
    words = [fitz.Rect(word[:4]) for word in page.get_text("words")]
    for strip in strips:
        guarded = fitz.Rect(strip.x0, strip.y0 - 1, strip.x1, strip.y1 + 1)
        if not any(guarded.intersects(word) for word in words):
            return strip
    return None


def _vocabulary(fields: list[FieldSpec], profile: FlatProfile) -> dict[str, tuple[str, str]]:
    """Every printed label this process may bind: label -> (slot key, match). Closed list.

    A label that would name two slots is dropped, so it binds to neither.
    """
    vocabulary: dict[str, tuple[str, str]] = {}
    clashes: set[str] = set()
    for spec in fields:
        own = [(label, "exact") for label in (spec.label_he, spec.label) if label]
        own += [(label, "synonym") for label in SYNONYMS.get(spec.key, ())]
        own += [(label, "synonym") for label in profile.labels.get(spec.key, [])]
        for label, match in own:
            folded = fold(label)
            existing = next((item for item in vocabulary if fold(item) == folded), None)
            if existing is None:
                vocabulary[label] = (spec.key, match)
            elif vocabulary[existing][0] != spec.key:
                clashes.add(existing)
    for label in clashes:
        vocabulary.pop(label, None)
    return vocabulary


def _read_page(page) -> _Page:
    words, rules, marks = _tokens(page)
    return _Page(words=words, segments=[*_segments(page), *rules], panels=_panels(page), marks=marks)


def _tokens(page) -> tuple[list[Word], list[Segment], list[Box]]:
    """Words built from characters, so a word split by kerning is whole again.

    A run of underscores is a writing rule, not a word. A symbol such as a tick box
    or a cross is ink, but never part of a label.
    """
    words: list[Word] = []
    rules: list[Segment] = []
    marks: list[Box] = []
    raw = page.get_text("rawdict")
    token: list[dict] = []

    def flush() -> None:
        if not token:
            return
        text = "".join(item["c"] for item in token)
        box = (
            min(item["bbox"][0] for item in token),
            min(item["bbox"][1] for item in token),
            max(item["bbox"][2] for item in token),
            max(item["bbox"][3] for item in token),
        )
        kind = _char_kind(text[0])
        if kind == "rule":
            if len(text) >= 3:
                rules.append(Segment(True, token[0]["origin"][1] + 1.0, box[0], box[2]))
        elif kind == "mark":
            marks.append(box)
        else:
            words.append(Word(box, text, (0, 0)))
        token.clear()

    for block in raw.get("blocks", []):
        # One token may run across the file's line objects: a row of cells is often cut
        # into several, sometimes in the middle of a word.
        for line in block.get("lines", []):
            spaced = False
            for span in line.get("spans", []):
                size = float(span.get("size") or 10)
                for char in span.get("chars", []):
                    if char["c"].isspace():
                        spaced = True
                        continue
                    if token:
                        last = token[-1]
                        gap = max(char["bbox"][0] - last["bbox"][2], last["bbox"][0] - char["bbox"][2])
                        # A space that takes no room is a typesetting artefact inside one word.
                        limit = size * (0.15 if spaced else 0.3)
                        drop = abs(char["bbox"][1] + char["bbox"][3] - last["bbox"][1] - last["bbox"][3]) / 2
                        if _char_kind(char["c"]) != _char_kind(last["c"]) or gap > limit or drop > size * 0.5:
                            flush()
                    spaced = False
                    token.append(char)
        flush()
    return _in_rows(words), _joined(rules), marks


def _char_kind(char: str) -> str:
    if char == "_":
        return "rule"
    if unicodedata.category(char)[0] in "SC":
        return "mark"
    return "text"


def _in_rows(words: list[Word]) -> list[Word]:
    """Group words into printed rows by position. The file's own line breaks split one row of cells."""
    rows: list[tuple[float, int]] = []
    placed: list[Word] = []
    for word in sorted(words, key=lambda item: (item.box[1] + item.box[3]) / 2):
        centre = (word.box[1] + word.box[3]) / 2
        height = word.box[3] - word.box[1]
        if rows and abs(centre - rows[-1][0]) <= height * 0.4:
            row = rows[-1][1]
        else:
            row = len(rows)
            rows.append((centre, row))
        placed.append(Word(word.box, word.text, (0, row)))
    # Pieces of one word that the file stores apart, such as a word and its apostrophe.
    whole: list[Word] = []
    for word in sorted(placed, key=lambda item: (item.line, item.box[0])):
        last = whole[-1] if whole else None
        if last is not None and last.line == word.line and word.box[0] - last.box[2] <= 0.6:
            hebrew = contains_hebrew(last.text) or contains_hebrew(word.text)
            text = word.text + last.text if hebrew else last.text + word.text
            box = (last.box[0], min(last.box[1], word.box[1]), max(last.box[2], word.box[2]), max(last.box[3], word.box[3]))
            whole[-1] = Word(box, text, word.line)
        else:
            whole.append(word)
    return whole


def _joined(rules: list[Segment]) -> list[Segment]:
    """Underscore runs printed end to end are one writing rule."""
    joined: list[Segment] = []
    for rule in sorted(rules, key=lambda item: (round(item.at, 1), item.a)):
        last = joined[-1] if joined else None
        if last is not None and abs(last.at - rule.at) <= 0.5 and rule.a - last.b <= 2.0:
            joined[-1] = Segment(True, last.at, last.a, max(last.b, rule.b))
        else:
            joined.append(rule)
    return joined


def _segments(page) -> list[Segment]:
    """Axis-aligned rules from stroked lines, rectangle edges, and hairline filled rectangles."""
    segments: list[Segment] = []

    def add(x0: float, y0: float, x1: float, y1: float) -> None:
        if abs(y1 - y0) <= 1.0 and abs(x1 - x0) > 2.0:
            segments.append(Segment(True, (y0 + y1) / 2, min(x0, x1), max(x0, x1)))
        elif abs(x1 - x0) <= 1.0 and abs(y1 - y0) > 2.0:
            segments.append(Segment(False, (x0 + x1) / 2, min(y0, y1), max(y0, y1)))

    for drawing in page.get_drawings():
        # Only dark ink counts. A white, pale or unstroked shape, such as a cell background
        # or the patch painted under a filled value, is not a rule.
        stroked = _dark(drawing.get("color"))
        filled = _dark(drawing.get("fill"))
        for item in drawing.get("items", []):
            if item[0] == "l":
                if stroked:
                    add(item[1].x, item[1].y, item[2].x, item[2].y)
            elif item[0] in ("re", "qu"):
                rect = fitz.Rect(item[1]) if item[0] == "re" else item[1].rect
                if rect.height <= 1.5 or rect.width <= 1.5:
                    if stroked or filled:
                        add(rect.x0, rect.y0, rect.x1, rect.y1)
                    continue
                if not stroked:
                    continue
                add(rect.x0, rect.y0, rect.x1, rect.y0)
                add(rect.x0, rect.y1, rect.x1, rect.y1)
                add(rect.x0, rect.y0, rect.x0, rect.y1)
                add(rect.x1, rect.y0, rect.x1, rect.y1)
    return segments


def _panels(page) -> list[Box]:
    """White cells: white filled rectangles, merged where they overlap, on a page that shades around them."""
    limit = page.rect.width * page.rect.height * 0.5
    rects: list[fitz.Rect] = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        if fill is None or any(float(part) < 0.97 for part in fill):
            continue
        for item in drawing.get("items", []):
            if item[0] != "re":
                continue
            rect = fitz.Rect(item[1])
            if rect.width >= 6 and rect.height >= 6 and rect.width * rect.height < limit:
                rects.append(rect)
    parent = list(range(len(rects)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for left in range(len(rects)):
        for right in range(left + 1, len(rects)):
            a, b = rects[left], rects[right]
            if min(a.x1, b.x1) - max(a.x0, b.x0) > 0.5 and min(a.y1, b.y1) - max(a.y0, b.y0) > 0.5:
                parent[root(left)] = root(right)
    merged: dict[int, fitz.Rect] = {}
    for index, rect in enumerate(rects):
        key = root(index)
        merged[key] = fitz.Rect(rect) if key not in merged else merged[key] | rect
    return [(rect.x0, rect.y0, rect.x1, rect.y1) for rect in merged.values()]


def _dark(color) -> bool:
    return color is not None and all(float(part) < 0.6 for part in color)


def _fit(value: str, rect: fitz.Rect, font_path: Path) -> float | None:
    """Largest size where one line fits the width and the line fits the height."""
    if "\n" in value:
        return None
    for size in _FONT_SIZES:
        if size * _LINE_FACTOR + 2 > rect.height:
            continue
        if _text_width(value, size, rtl=True, font_path=font_path) <= rect.width - 4:
            return size
    return None


def _comb_size(boxes: list[list[float]]) -> float | None:
    width = min(box[2] - box[0] for box in boxes)
    height = min(box[3] - box[1] for box in boxes)
    size = min(10.0, width * 0.9, height * 0.8)
    return round(size, 1) if size >= 5 else None


def _paint_comb(page, boxes: list[list[float]], digits: str, font_path: Path, size: float) -> None:
    """One digit per box, left to right, centred. The ticks and the baseline are not covered."""
    fontname = _embed(page, font_path)
    font = _hebrew_font(font_path)
    for digit, box in zip(digits, boxes):
        width = font.text_length(digit, fontsize=size)
        x = (box[0] + box[2]) / 2 - width / 2
        page.insert_text((x, box[3] - 2.0), digit, fontname=fontname, fontsize=size, color=_INK)
