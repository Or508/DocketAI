from pathlib import Path

import fitz

from app.core.exceptions import UnprocessableError
from app.domain.certificate import CertificateData, format_times
from app.domain.text_layout import contains_hebrew, shape_for_pdf
from app.services.pdf_filler import _embed

_MARGIN = 36.0
_FOOTER = 36.0
_INK = (0.11, 0.1, 0.08)
_DISCLOSURE = (
    "This certificate records events in the DocketAI system. "
    "It does not verify the signer's identity. "
    "To check this copy, ask the office to compare the SHA-256 of the complete file with its record."
)


def add_certificate_page(
    document,
    data: CertificateData,
    *,
    content_sha256: str,
    signature_png: bytes,
    font_path: Path | None,
) -> None:
    if document.page_count < 1:
        raise UnprocessableError("The signed form has no pages.")
    if font_path is None:
        raise UnprocessableError("A Hebrew font is required before this form can be flattened.")
    first = document[0].rect
    page = document.new_page(width=first.width, height=first.height)
    fontname = _embed(page, font_path)
    limit = page.rect.height - _FOOTER
    x0 = _MARGIN
    x1 = page.rect.width - _MARGIN
    y = 40.0

    def write(text: str, size: float, *, gap: float = 5) -> None:
        nonlocal y
        room = limit - y
        if room <= size:
            raise UnprocessableError("Certificate text did not fit.")
        rect = fitz.Rect(x0, y, x1, limit)
        shown = shape_for_pdf(text) if contains_hebrew(text) else text
        spare = page.insert_textbox(
            rect,
            shown,
            fontname=fontname,
            fontsize=size,
            color=_INK,
            align=fitz.TEXT_ALIGN_LEFT,
        )
        if isinstance(spare, str) or spare < 0:
            raise UnprocessableError("Certificate text did not fit.")
        y += (room - spare) + gap

    def when(value) -> str:
        if value is None:
            return "Not recorded"
        utc, local = format_times(value)
        return f"{utc} | {local}"

    if data.client_name and data.client_name.strip():
        named = f'"{data.client_name.strip()} (entered by the office, not verified)"'
    else:
        named = "Not recorded"
    method = "Secure signing link" if data.channel == "portal" else "Office workspace"
    if data.channel == "portal":
        confirmed = f'The signer confirmed: "{data.consent_text}"'
    else:
        confirmed = f'The office user confirmed: "{data.consent_text}"'
    browser = _chunks(data.user_agent) if data.user_agent else "Not recorded"

    write("Certificate of Completion", 16, gap=10)
    write("Document", 11, gap=2)
    write(data.document_title, 9)
    write(f"Case reference: {data.case_reference}", 9, gap=8)
    write("Integrity", 11, gap=2)
    write("Signed form content SHA-256", 9, gap=1)
    write(content_sha256, 8, gap=2)
    write(
        "Calculated before this certificate and the page footers were added. "
        "The office holds a separate hash of the complete file.",
        8,
        gap=8,
    )
    write("Signer", 11, gap=2)
    write(f"Named signer: {named}", 9)
    write(f"Signature record ID: {data.signer_verification_id}", 9)
    write(f"Signing method: {method}", 9)
    write(f"IP address as reported: {data.ip or 'Not recorded'}", 9)
    write(f"Browser as reported: {browser}", 8)
    write(f"Signed at: {when(data.signed_at)}", 9, gap=8)
    write("Timeline", 11, gap=2)
    write(f"Case created: {when(data.created_at)}", 9)
    write(f"Data collection completed: {when(data.data_completed_at)}", 9)
    if data.channel == "portal":
        write(f"Signing link issued: {when(data.link_issued_at)}", 9)
    write(f"Signed: {when(data.signed_at)}", 9, gap=8)
    write("Signature", 11, gap=3)
    box_height = 64.0
    if y + box_height > limit:
        raise UnprocessableError("Certificate text did not fit.")
    box = fitz.Rect(x0, y, x0 + 220, y + box_height)
    page.draw_rect(box, color=(0.45, 0.42, 0.38), width=0.6)
    page.insert_image(box, stream=signature_png, keep_proportion=True)
    y += box_height + 8
    write(confirmed, 8, gap=3)
    write(_DISCLOSURE, 8, gap=0)


def _chunks(value: str, size: int = 48) -> str:
    return "\n".join(value[i : i + size] for i in range(0, len(value), size))
