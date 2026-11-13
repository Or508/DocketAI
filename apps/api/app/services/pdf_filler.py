import base64
import hashlib
import html
import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import fitz

from app.core.exceptions import BadRequestError, UnprocessableError
from app.domain.certificate import CertificateData, format_times
from app.domain.text_layout import contains_hebrew, shape_for_pdf
from app.services.fonts import bundled_hebrew_font

logger = logging.getLogger(__name__)

_READ_ONLY = int(getattr(fitz, "PDF_FIELD_IS_READ_ONLY", 1))


@dataclass(frozen=True)
class SignedArtifact:
    content_sha256: str
    file_sha256: str
    signer_verification_id: str
    content_path: Path
    total_pages: int


_TEXT_WIDGET = int(getattr(fitz, "PDF_WIDGET_TYPE_TEXT", 7))
_MAX_WIDGETS = 500
_COMB = int(getattr(fitz, "PDF_TX_FIELD_IS_COMB", 1 << 24))
_MULTILINE = int(getattr(fitz, "PDF_TX_FIELD_IS_MULTILINE", 1 << 12))
_FONT_SIZES = tuple(11 - step * 0.5 for step in range(9))
_DRAFT_MARK = "טיוטה – לא חתום"
FillStatus = Literal["ok", "overflow", "mismatch", "skipped_prefilled", "comb_unsupported"]
_HEBREW_FONTS: dict[str, fitz.Font] = {}
# A trailer id is written as hex, or as a literal string when its bytes happen to be printable.
_PDF_STRING = br"(<[0-9A-Fa-f\s]*>|\((?:\\.|[^\\()]|\((?:\\.|[^\\()])*\))*\))"
_TRAILER_ID = re.compile(br"/ID\s*\[\s*" + _PDF_STRING + br"\s*" + _PDF_STRING + br"\s*\]", re.DOTALL)


@dataclass(frozen=True)
class FieldFill:
    field_name: str
    page: int
    status: FillStatus
    font_size: float | None


@dataclass(frozen=True)
class FilledForm:
    pdf_bytes: bytes
    fields: list[FieldFill]


@dataclass(frozen=True)
class WidgetReading:
    """One text widget of an uploaded AcroForm, read without changing the file."""

    field_name: str
    page_index: int
    rect: tuple[float, float, float, float]
    value: str | None

    @property
    def empty(self) -> bool:
        return self.value is None or self.value == ""


def read_form_widgets(path: Path) -> list[WidgetReading]:
    """Read the text widgets of a PDF through page.widgets() only.

    Only text widgets are read, because the slots they bind to are text values;
    a checkbox's "Off" is not an empty text field. Filling an uploaded form
    is PdfFillerService.fill_case_form. Signing stays in fill_and_sign.
    """
    readings: list[WidgetReading] = []
    document = fitz.open(path)
    try:
        for index, page in enumerate(document):
            for widget in page.widgets() or []:
                if int(widget.field_type or 0) != _TEXT_WIDGET:
                    continue
                name = (widget.field_name or "").strip()
                if not name:
                    continue
                raw = widget.field_value
                value = None if raw is None else str(raw)
                box = fitz.Rect(widget.rect)
                readings.append(
                    WidgetReading(
                        field_name=name[:200],
                        page_index=index,
                        rect=(round(box.x0, 2), round(box.y0, 2), round(box.x1, 2), round(box.y1, 2)),
                        value=value,
                    )
                )
                if len(readings) >= _MAX_WIDGETS:
                    return readings
    finally:
        document.close()
    return readings


def decode_signature_png(payload: str) -> bytes:
    raw_payload = payload.strip()
    if raw_payload.startswith("data:"):
        if "," not in raw_payload:
            raise BadRequestError("The signature image is not valid base64.")
        raw_payload = raw_payload.split(",", 1)[1]
    try:
        data = base64.b64decode(raw_payload, validate=True)
    except Exception as exc:
        raise BadRequestError("The signature image is not valid base64.") from exc
    if len(data) > 2_000_000:
        raise BadRequestError("The signature image is larger than 2 MB.")
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 24:
        raise BadRequestError("The signature must be a PNG image.")
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width > 4000 or height > 2000 or width < 50 or height < 20:
        raise BadRequestError("The signature image is not an accepted size.")
    if not _signature_has_ink(data):
        raise BadRequestError("The signature is empty.")
    return data


def _signature_has_ink(data: bytes) -> bool:
    # Pillow does this in C. A per-pixel Python loop took seconds on a large
    # blank image and held the event loop for every other request.
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            rgba = image.convert("RGBA")
    except Exception as exc:
        raise BadRequestError("The signature must be a PNG image.") from exc
    flat = Image.alpha_composite(Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba).convert("L")
    # Ink is anything darker than near-white.
    ink = flat.point(lambda value: 255 if value < 250 else 0)
    return ink.getbbox() is not None


class PdfFillerService:
    """Fill an AcroForm, stamp a signature, then flatten both into page content.

    Hebrew is painted after flattening with python-bidi and arabic-reshaper so
    the widget appearance cannot cover it. The content digest is the flattened
    form before the certificate page and the page footers are added.
    """

    def __init__(self, font_path: Path | None) -> None:
        self._font_path = font_path

    def fill_and_sign(
        self,
        *,
        template_path: Path,
        output_path: Path,
        values: dict[str, str],
        signature_png: bytes,
        signature_rect: list[float],
        page_index: int,
        rtl_fields: set[str],
        certificate: CertificateData,
        signed_at: datetime,
    ) -> SignedArtifact:
        missing = _missing_fields(template_path, set(values))
        if missing:
            names = ", ".join(sorted(missing))
            raise UnprocessableError(f"The template is missing form fields: {names}.")

        font_path = self._resolved_font()
        if rtl_fields and font_path is None:
            raise UnprocessableError("A Hebrew font is required before this form can be flattened.")

        signer_id = certificate.signer_verification_id
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open(template_path)
        try:
            if page_index < 0 or page_index >= document.page_count:
                raise UnprocessableError("The signature page is outside the template.")
            rtl_paint = self._apply_values(document, values, rtl_fields)
            page = document[page_index]
            page.insert_image(
                fitz.Rect(*signature_rect),
                stream=signature_png,
                keep_proportion=True,
                overlay=True,
            )
            document.bake(annots=True, widgets=True)
            for index, rect, value in rtl_paint:
                _paint_rtl(document[index], rect, value, font_path)
            form_bytes = document.tobytes(garbage=4, deflate=True)
            digest = hashlib.sha256(form_bytes).hexdigest()
            form_path = output_path.with_name(output_path.stem + "-form.pdf")
            form_path.write_bytes(form_bytes)
        finally:
            document.close()
        # tobytes(garbage=4) leaves the open document unable to embed a font.
        document = fitz.open(stream=form_bytes)
        try:
            try:
                from app.services.certificate_page import add_certificate_page

                add_certificate_page(
                    document,
                    certificate,
                    content_sha256=digest,
                    signature_png=signature_png,
                    font_path=font_path,
                )
                _stamp_audit(
                    document,
                    case_reference=certificate.case_reference,
                    signed_at=signed_at,
                    digest=digest,
                    signer_id=signer_id,
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
                signer_verification_id=signer_id,
                content_path=form_path,
                total_pages=document.page_count,
            )
        finally:
            document.close()

    def _apply_values(
        self,
        document: fitz.Document,
        values: dict[str, str],
        rtl_fields: set[str],
    ) -> list[tuple[int, fitz.Rect, str]]:
        rtl_paint: list[tuple[int, fitz.Rect, str]] = []
        for index, page in enumerate(document):
            for widget in list(page.widgets() or []):
                if widget.field_name not in values:
                    widget.field_flags = int(widget.field_flags or 0) | _READ_ONLY
                    widget.update()
                    continue
                value = values[widget.field_name]
                rtl = widget.field_name in rtl_fields or contains_hebrew(value)
                _write_widget(widget, value, rtl)
                if rtl:
                    rtl_paint.append((index, fitz.Rect(widget.rect), value))
        return rtl_paint

    def render_preview(
        self,
        *,
        template_path: Path,
        values: dict[str, str],
        rtl_fields: set[str],
    ) -> bytes:
        missing = _missing_fields(template_path, set(values))
        if missing:
            names = ", ".join(sorted(missing))
            raise UnprocessableError(f"The template is missing form fields: {names}.")
        font_path = self._resolved_font()
        if rtl_fields and font_path is None:
            raise UnprocessableError("A Hebrew font is required before this form can be flattened.")
        document = fitz.open(template_path)
        try:
            rtl_paint = self._apply_values(document, values, rtl_fields)
            document.bake(annots=True, widgets=True)
            for index, rect, value in rtl_paint:
                _paint_rtl(document[index], rect, value, font_path)
            for page in document:
                _draft_mark(page)
            return document.tobytes(garbage=4, deflate=True)
        finally:
            document.close()

    def fill_case_form(
        self,
        *,
        source_path: Path,
        values: dict[str, str],
        rtl_names: set[str],
    ) -> FilledForm:
        """Fill empty text widgets from the original bytes and return a new PDF.

        The source file is never written. A widget that already has a value, or
        that cannot take the text, is left untouched.
        """
        font_path = self._resolved_font()
        # Open the stored original. tobytes() returns a new file; nothing is saved back.
        document = fitz.open(source_path)
        try:
            plans = _plan_fills(document, values, rtl_names, font_path)
            paints: list[tuple[int, fitz.Rect, str, float]] = []
            pending: dict[tuple[int, str], list[_WidgetPlan]] = {}
            for plan in plans:
                if plan.write:
                    pending.setdefault((plan.page, plan.field_name), []).append(plan)
            for index, page in enumerate(document):
                for widget in list(page.widgets() or []):
                    queue = pending.get((index, widget.field_name or ""))
                    if not queue:
                        continue
                    plan = queue.pop(0)
                    if plan.font_size is None:
                        continue
                    _write_widget(widget, plan.value, plan.rtl, plan.font_size)
                    if plan.rtl:
                        paints.append((plan.page, plan.rect, plan.value, plan.font_size))
            if any(plan.write for plan in plans):
                document.bake(annots=True, widgets=True)
                for index, rect, value, font_size in paints:
                    _paint_rtl(document[index], rect, value, font_path, font_size)
            _pin_dates(document)
            pdf_bytes = _stable_id(document.tobytes(garbage=4, deflate=True))
        finally:
            document.close()
        # Text written by bake is visible to get_text only after the bytes are reopened.
        if any(plan.write for plan in plans):
            written = fitz.open(stream=pdf_bytes, filetype="pdf")
            try:
                for plan in plans:
                    if not plan.write:
                        continue
                    extracted = written[plan.page].get_text("text", clip=plan.rect)
                    plan.status = "ok" if _readback_matches(plan.value, extracted, plan.rtl) else "mismatch"
            finally:
                written.close()
        fields = [
            FieldFill(
                field_name=plan.field_name,
                page=plan.page,
                status=plan.status,  # type: ignore[arg-type]
                font_size=plan.font_size,
            )
            for plan in plans
        ]
        return FilledForm(pdf_bytes=pdf_bytes, fields=fields)

    def fill_flat(self, pdf_bytes: bytes, anchors: list[dict], values: dict[str, str]) -> FilledForm:
        from app.services.flat_form import fill_flat_form

        return fill_flat_form(pdf_bytes, anchors, values, self._resolved_font())

    def stamp_draft(self, pdf_bytes: bytes) -> bytes:
        """Stamp every page with the Hebrew draft line, using the existing RTL painter."""
        font_path = self._resolved_font()
        if font_path is None:
            raise UnprocessableError("A Hebrew font is required before this form can be filled.")
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            for page in document:
                rect = fitz.Rect(36, 12, max(page.rect.width - 36, 200), 36)
                _paint_rtl(page, rect, _DRAFT_MARK, font_path)
            _pin_dates(document)
            return _stable_id(document.tobytes(garbage=4, deflate=True))
        finally:
            document.close()

    def _resolved_font(self) -> Path | None:
        if self._font_path is not None and self._font_path.is_file():
            return self._font_path
        return bundled_hebrew_font()


def _missing_fields(template_path: Path, expected: set[str]) -> set[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(template_path))
    present = set((reader.get_fields() or {}).keys())
    return expected - present


def _write_widget(widget, value: str, rtl: bool, font_size: float = 11) -> None:
    widget.field_value = value
    widget.text_fontsize = font_size
    widget.field_flags = int(widget.field_flags or 0) | _READ_ONLY
    if rtl:
        widget.text_color = (1, 1, 1)
        widget.fill_color = (1, 1, 1)
    else:
        widget.text_color = (0.11, 0.1, 0.08)
        widget.fill_color = (1, 1, 1)
    widget.update()


def _paint_rtl(page, rect, value: str, font_path: Path | None, font_size: float = 11) -> None:
    inner = fitz.Rect(rect.x0 + 2, rect.y0 + 1, rect.x1 - 2, rect.y1 - 1)
    page.draw_rect(inner, color=None, fill=(1, 1, 1), overlay=True)
    lines = [
        shape_for_pdf(line) if contains_hebrew(line) else line
        for line in value.splitlines()
    ]
    shown = "\n".join(lines)
    if font_path is not None:
        fontname = _embed(page, font_path)
        try:
            page.insert_textbox(
                inner,
                shown,
                fontname=fontname,
                fontsize=font_size,
                align=fitz.TEXT_ALIGN_RIGHT,
                color=(0.11, 0.1, 0.08),
            )
            return
        except Exception:
            logger.warning("Bidi text draw failed; falling back to HTML layout", exc_info=True)
    _paint_html(page, inner, value, font_path, font_size)


def _paint_html(page, inner, value: str, font_path: Path | None, font_size: float = 11) -> None:
    body = "<br/>".join(html.escape(line) for line in value.splitlines()) or "&#160;"
    markup = f'<div dir="rtl">{body}</div>'
    css, archive = _rtl_css(font_path, font_size)
    kwargs: dict = {"css": css, "overlay": True}
    if archive is not None:
        kwargs["archive"] = archive
    page.insert_htmlbox(inner, markup, **kwargs)


def _draft_mark(page) -> None:
    page.draw_line(
        fitz.Point(48, page.rect.height - 48),
        fitz.Point(page.rect.width - 48, 48),
        color=(0.72, 0.18, 0.16),
        width=1.4,
    )
    pivot = fitz.Point(72, page.rect.height * 0.72)
    page.insert_text(
        pivot,
        "DRAFT - NOT SIGNED",
        fontsize=22,
        color=(0.72, 0.18, 0.16),
        morph=(pivot, fitz.Matrix(32)),
        overlay=True,
    )


def _stamp_audit(
    document,
    *,
    case_reference: str,
    signed_at: datetime,
    digest: str,
    signer_id: str,
    font_path: Path | None,
) -> None:
    utc, local = format_times(signed_at)
    total = document.page_count
    for index, page in enumerate(document, start=1):
        banner = (
            f"Ref {case_reference} | UTC {utc} | Israel {local} | Signer {signer_id} | "
            f"Page {index} of {total}\nContent SHA-256 {digest}"
        )
        fontname = _embed(page, font_path) if font_path is not None else "helv"
        top = page.rect.height - 34
        page.draw_line(
            fitz.Point(28, top - 2),
            fitz.Point(page.rect.width - 28, top - 2),
            color=(0.75, 0.72, 0.66),
            width=0.4,
        )
        spare = page.insert_textbox(
            fitz.Rect(24, top, page.rect.width - 24, page.rect.height - 4),
            banner,
            fontname=fontname,
            fontsize=6,
            align=fitz.TEXT_ALIGN_CENTER,
            color=(0.42, 0.4, 0.36),
        )
        if isinstance(spare, str) or spare < 0:
            raise UnprocessableError("The audit footer did not fit.")


def _embed(page, font_path: Path) -> str:
    page.insert_font(fontname="rubik", fontfile=str(font_path))
    return "rubik"


@dataclass
class _WidgetPlan:
    field_name: str
    page: int
    rect: fitz.Rect
    value: str
    rtl: bool
    font_size: float | None
    status: str
    write: bool


def _plan_fills(
    document: fitz.Document,
    values: dict[str, str],
    rtl_names: set[str],
    font_path: Path | None,
) -> list[_WidgetPlan]:
    plans: list[_WidgetPlan] = []
    for index, page in enumerate(document):
        for widget in list(page.widgets() or []):
            name = widget.field_name or ""
            if name not in values or int(widget.field_type or 0) != _TEXT_WIDGET:
                continue
            value = values[name]
            rect = fitz.Rect(widget.rect)
            raw = widget.field_value
            if raw not in (None, ""):
                plans.append(_WidgetPlan(name, index, rect, value, False, None, "skipped_prefilled", False))
                continue
            if int(widget.field_flags or 0) & _COMB:
                plans.append(_WidgetPlan(name, index, rect, value, False, None, "comb_unsupported", False))
                continue
            maxlen = int(widget.text_maxlen or 0)
            if maxlen and len(value) > maxlen:
                plans.append(_WidgetPlan(name, index, rect, value, False, None, "overflow", False))
                continue
            rtl = name in rtl_names or contains_hebrew(value)
            if rtl and font_path is None:
                raise UnprocessableError("A Hebrew font is required before this form can be filled.")
            multiline = bool(int(widget.field_flags or 0) & _MULTILINE)
            font_size = _fit_font_size(value, rect, rtl=rtl, font_path=font_path, multiline=multiline)
            if font_size is None:
                plans.append(_WidgetPlan(name, index, rect, value, rtl, None, "overflow", False))
                continue
            plans.append(_WidgetPlan(name, index, rect, value, rtl, font_size, "ok", True))
    return plans


def _fit_font_size(
    text: str,
    rect: fitz.Rect,
    *,
    rtl: bool,
    font_path: Path | None,
    multiline: bool,
) -> float | None:
    usable_width = rect.width - 4
    if usable_width <= 0:
        return None
    for size in _FONT_SIZES:
        if _text_fits(text, usable_width, rect.height, size, rtl=rtl, font_path=font_path, multiline=multiline):
            return size
    return None


def _text_fits(
    text: str,
    width: float,
    height: float,
    size: float,
    *,
    rtl: bool,
    font_path: Path | None,
    multiline: bool,
) -> bool:
    if not text:
        return True

    def measure(sample: str) -> float:
        return _text_width(sample, size, rtl=rtl, font_path=font_path)

    if not multiline:
        if "\n" in text:
            return False
        return measure(text) <= width
    count = _line_count(text, width, measure)
    if count is None:
        return False
    return count * size <= height


def _line_count(text: str, width: float, measure) -> int | None:
    count = 0
    for paragraph in text.split("\n"):
        if paragraph == "":
            count += 1
            continue
        remaining = paragraph
        while remaining:
            if measure(remaining) <= width:
                count += 1
                break
            split_at = _longest_prefix(remaining, width, measure)
            if split_at <= 0:
                return None
            space = remaining.rfind(" ", 0, split_at)
            if space > 0:
                split_at = space
            count += 1
            remaining = remaining[split_at:].lstrip(" ")
            if not remaining and split_at == 0:
                return None
    return count


def _longest_prefix(text: str, width: float, measure) -> int:
    low = 0
    high = len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if measure(text[:mid]) <= width:
            low = mid
        else:
            high = mid - 1
    return low


def _text_width(text: str, fontsize: float, *, rtl: bool, font_path: Path | None) -> float:
    if rtl:
        # get_text_length only accepts Base-14 fonts, so the bundled face is
        # measured with Font.text_length — the width call behind that helper.
        if font_path is None:
            return fitz.get_text_length(text, fontname="helv", fontsize=fontsize)
        return _hebrew_font(font_path).text_length(text, fontsize=fontsize)
    return fitz.get_text_length(text, fontname="helv", fontsize=fontsize)


def _hebrew_font(font_path: Path) -> fitz.Font:
    key = str(font_path)
    cached = _HEBREW_FONTS.get(key)
    if cached is None:
        cached = fitz.Font(fontfile=key)
        _HEBREW_FONTS[key] = cached
    return cached


def _readback_matches(expected: str, extracted: str, rtl: bool) -> bool:
    if not rtl:
        return " ".join(expected.split()) == " ".join(extracted.split())
    expected_letters = _hebrew_letters(expected)
    found_letters = _hebrew_letters(extracted)
    doubled = sorted(expected_letters + expected_letters)
    if found_letters not in (expected_letters, doubled):
        return False
    sequences = _digit_sequences(expected)
    found = _digits(extracted)
    options = set(sequences)
    for left in sequences:
        for right in sequences:
            options.add(left + right)
    return found in options


def _hebrew_letters(text: str) -> list[str]:
    return sorted(character for character in text if "\u0590" <= character <= "\u05FF")


def _digits(text: str) -> str:
    return "".join(character for character in text if character.isdigit())


def _digit_sequences(text: str) -> set[str]:
    """Logical digit order, and the same runs reversed for visual-order extraction."""
    runs = re.findall(r"\d+", text)
    return {"".join(runs), "".join(reversed(runs))}


def _pin_dates(document: fitz.Document) -> None:
    """Keep two fills of the same inputs from drifting across a timestamp boundary."""
    metadata = dict(document.metadata or {})
    metadata["creationDate"] = "D:20260101000000Z"
    metadata["modDate"] = "D:20260101000000Z"
    document.set_metadata(metadata)


def _stable_id(data: bytes) -> bytes:
    """Replace the random trailer id with a hash so the same fill is byte-identical."""
    match = None
    for match in _TRAILER_ID.finditer(data):
        pass
    if match is None:
        return data
    # Both halves are replaced. The first is seeded from the clock, so two fills that
    # straddle a second would otherwise differ. A source file's own id is carried over
    # as the first half, in whichever form it was written.
    first, second = match.group(1), match.group(2)

    def width(token: bytes) -> int:
        return len(token) - 2 if token.startswith(b"<") else 32

    def with_ids(one: bytes, two: bytes) -> bytes:
        return (
            data[: match.start(1)]
            + b"<" + one + b">"
            + data[match.end(1) : match.start(2)]
            + b"<" + two + b">"
            + data[match.end(2) :]
        )

    digest = hashlib.sha256(with_ids(b"0" * width(first), b"0" * width(second))).hexdigest().encode("ascii")
    return with_ids((digest * 2)[: width(first)], (digest * 2)[: width(second)])


def _rtl_css(font_path: Path | None, font_size: float = 11) -> tuple[str, object | None]:
    # The default stays the literal "11pt" so the signing path's fallback is unchanged.
    size = "11pt" if font_size == 11 else f"{font_size:g}pt"
    if font_path is not None and font_path.is_file():
        css = (
            f'@font-face {{font-family: docket; src: url("{font_path.name}");}}'
            f"* {{font-family: docket; font-size: {size}; direction: rtl; text-align: right;}}"
        )
        return css, fitz.Archive(str(font_path.parent))
    css = f"* {{font-family: sans-serif; font-size: {size}; direction: rtl; text-align: right;}}"
    return css, None
