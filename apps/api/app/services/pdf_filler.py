import base64
import hashlib
import html
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import fitz

from app.core.exceptions import BadRequestError, UnprocessableError
from app.domain.text_layout import contains_hebrew, shape_for_pdf
from app.services.fonts import bundled_hebrew_font

logger = logging.getLogger(__name__)

_READ_ONLY = int(getattr(fitz, "PDF_FIELD_IS_READ_ONLY", 1))
_ISRAEL = ZoneInfo("Asia/Jerusalem")


@dataclass(frozen=True)
class SignedArtifact:
    content_sha256: str
    signer_verification_id: str


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
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise BadRequestError("The signature must be a PNG image.")
    return data


class PdfFillerService:
    """Fill an AcroForm, stamp a signature, then flatten both into page content.

    Hebrew is painted after flattening with python-bidi and arabic-reshaper so
    the widget appearance cannot cover it. The audit footer records the SHA-256
    of that flattened packet. The digest cannot include the footer that prints
    it, so the stamp is applied after the hash is taken.
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
        case_id: str,
        signer_verification_id: str | None = None,
    ) -> SignedArtifact:
        missing = _missing_fields(template_path, set(values))
        if missing:
            names = ", ".join(sorted(missing))
            raise UnprocessableError(f"The template is missing form fields: {names}.")

        font_path = self._resolved_font()
        if rtl_fields and font_path is None:
            raise UnprocessableError("A Hebrew font is required before this form can be flattened.")

        signer_id = signer_verification_id or f"DV-{uuid4().hex[:12].upper()}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open(template_path)
        try:
            if page_index < 0 or page_index >= document.page_count:
                raise UnprocessableError("The signature page is outside the template.")
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
            digest = hashlib.sha256(document.tobytes(garbage=4, deflate=True)).hexdigest()
            _stamp_audit(document, case_id=case_id, digest=digest, signer_id=signer_id, font_path=font_path)
            document.save(output_path, garbage=4, deflate=True)
            return SignedArtifact(content_sha256=digest, signer_verification_id=signer_id)
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


def _write_widget(widget, value: str, rtl: bool) -> None:
    widget.field_value = value
    widget.text_fontsize = 11
    widget.field_flags = int(widget.field_flags or 0) | _READ_ONLY
    if rtl:
        widget.text_color = (1, 1, 1)
        widget.fill_color = (1, 1, 1)
    else:
        widget.text_color = (0.11, 0.1, 0.08)
        widget.fill_color = (1, 1, 1)
    widget.update()


def _paint_rtl(page, rect, value: str, font_path: Path | None) -> None:
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
                fontsize=11,
                align=fitz.TEXT_ALIGN_RIGHT,
                color=(0.11, 0.1, 0.08),
            )
            return
        except Exception:
            logger.warning("Bidi text draw failed; falling back to HTML layout", exc_info=True)
    _paint_html(page, inner, value, font_path)


def _paint_html(page, inner, value: str, font_path: Path | None) -> None:
    body = "<br/>".join(html.escape(line) for line in value.splitlines()) or "&#160;"
    markup = f'<div dir="rtl">{body}</div>'
    css, archive = _rtl_css(font_path)
    kwargs: dict = {"css": css, "overlay": True}
    if archive is not None:
        kwargs["archive"] = archive
    page.insert_htmlbox(inner, markup, **kwargs)


def _stamp_audit(document, *, case_id: str, digest: str, signer_id: str, font_path: Path | None) -> None:
    utc = datetime.now(timezone.utc)
    local = utc.astimezone(_ISRAEL)
    banner = (
        f"Case {case_id}  |  UTC {utc:%Y-%m-%d %H:%M}  |  Israel {local:%Y-%m-%d %H:%M}  |  "
        f"Signer {signer_id}\nSHA-256 {digest}"
    )
    for page in document:
        fontname = _embed(page, font_path) if font_path is not None else "helv"
        top = page.rect.height - 22
        page.draw_line(
            fitz.Point(28, top - 2),
            fitz.Point(page.rect.width - 28, top - 2),
            color=(0.75, 0.72, 0.66),
            width=0.4,
        )
        page.insert_textbox(
            fitz.Rect(24, top, page.rect.width - 24, page.rect.height - 2),
            banner,
            fontname=fontname,
            fontsize=6,
            align=fitz.TEXT_ALIGN_CENTER,
            color=(0.42, 0.4, 0.36),
        )


def _embed(page, font_path: Path) -> str:
    page.insert_font(fontname="rubik", fontfile=str(font_path))
    return "rubik"


def _rtl_css(font_path: Path | None) -> tuple[str, object | None]:
    if font_path is not None and font_path.is_file():
        css = (
            f'@font-face {{font-family: docket; src: url("{font_path.name}");}}'
            "* {font-family: docket; font-size: 11pt; direction: rtl; text-align: right;}"
        )
        return css, fitz.Archive(str(font_path.parent))
    css = "* {font-family: sans-serif; font-size: 11pt; direction: rtl; text-align: right;}"
    return css, None
