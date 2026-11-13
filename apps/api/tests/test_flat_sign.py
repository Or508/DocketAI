"""Signing the uploaded flat form itself: every value lands, one signature box, then the seal."""

import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("fitz")

import pymupdf
from PIL import Image, ImageDraw

from app.core.exceptions import UnprocessableError
from app.domain.certificate import CertificateData
from app.services.flat_form import preview_flat_form, read_flat_anchors, sign_flat_form, signature_box
from app.services.pdf_filler import PdfFillerService, _readback_matches
from tests.test_flat_form import _FIELDS, _FONT, _flat_form

_SIGNED_AT = datetime(2026, 11, 11, 9, 30, tzinfo=timezone.utc)
_LABELS = ["חתימה"]
_SLOT_VALUES = {"first_name": "דנה", "last_name": "כהן", "phone": "0501234567"}


def _signature() -> bytes:
    image = Image.new("RGBA", (400, 120), (255, 255, 255, 0))
    ImageDraw.Draw(image).line([(20, 90), (140, 30), (220, 95), (380, 40)], fill=(20, 20, 60, 255), width=5)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _certificate() -> CertificateData:
    return CertificateData(
        document_title="Flat form",
        case_reference="DK-TEST00000001",
        client_name="Test Client",
        signer_verification_id="DV-TEST00000001",
        channel="office",
        ip=None,
        user_agent=None,
        consent_text="I reviewed this form and sign it.",
        created_at=_SIGNED_AT,
        data_completed_at=_SIGNED_AT,
        link_issued_at=None,
        signed_at=_SIGNED_AT,
    )


def _inputs(path: Path, slot_values: dict[str, str] | None = None) -> tuple[list[dict], dict[str, str]]:
    anchors = read_flat_anchors(path, _FIELDS)
    wanted = _SLOT_VALUES if slot_values is None else slot_values
    values = {anchor["field_name"]: wanted[anchor["slot_key"]] for anchor in anchors if anchor["slot_key"] in wanted}
    return anchors, values


def _sign(path: Path, out: Path, anchors: list[dict], values: dict[str, str]):
    return sign_flat_form(
        PdfFillerService(_FONT),
        source_path=path,
        output_path=out,
        anchors=anchors,
        values=values,
        rtl_names=set(),
        signature_png=_signature(),
        signature_labels=_LABELS,
        certificate=_certificate(),
        signed_at=_SIGNED_AT,
    )


def test_the_signature_box_is_the_one_drawn_rule_and_is_tall_enough_to_sign(tmp_path: Path) -> None:
    page, rect = signature_box(_flat_form(tmp_path / "flat.pdf", signatures=1), _LABELS)
    assert page == 0
    assert (rect[0], rect[2]) == (330, 505)
    assert rect[3] < 522 and rect[3] - rect[1] >= 39


def test_a_form_with_no_signature_box_or_with_two_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UnprocessableError):
        signature_box(_flat_form(tmp_path / "none.pdf"), _LABELS)
    with pytest.raises(UnprocessableError):
        signature_box(_flat_form(tmp_path / "two.pdf", signatures=2), _LABELS)


def test_signing_writes_the_values_and_the_signature_on_the_uploaded_form(tmp_path: Path) -> None:
    path = _flat_form(tmp_path / "flat.pdf", signatures=1)
    original = path.read_bytes()
    anchors, values = _inputs(path)
    out = tmp_path / "out" / "signed.pdf"
    artifact = _sign(path, out, anchors, values)

    assert path.read_bytes() == original
    assert artifact.content_sha256 == hashlib.sha256(artifact.content_path.read_bytes()).hexdigest()
    assert artifact.file_sha256 == hashlib.sha256(out.read_bytes()).hexdigest()
    assert artifact.total_pages == 2

    form = pymupdf.open(artifact.content_path)
    try:
        assert form.page_count == 1
        for anchor in anchors:
            value = values[anchor["field_name"]]
            text = form[0].get_text("text", clip=pymupdf.Rect(anchor["rect"]))
            assert _readback_matches(value, text, any("֐" <= ch <= "׿" for ch in value))
        _page, rect = signature_box(path, _LABELS)
        placed = [form[0].get_image_rects(image[0])[0] for image in form[0].get_images()]
        assert len(placed) == 1
        assert pymupdf.Rect(rect).contains(placed[0])
    finally:
        form.close()
    packet = pymupdf.open(out)
    try:
        assert "DK-TEST00000001" in packet[0].get_text()
        assert artifact.content_sha256 in "".join(packet[1].get_text().split())
    finally:
        packet.close()


def test_a_value_that_does_not_fit_blocks_the_signature(tmp_path: Path) -> None:
    path = _flat_form(tmp_path / "flat.pdf", signatures=1)
    anchors, values = _inputs(path, {**_SLOT_VALUES, "last_name": "כהן " * 40})
    out = tmp_path / "signed.pdf"
    with pytest.raises(UnprocessableError):
        _sign(path, out, anchors, values)
    assert not out.exists()
    assert not out.with_name("signed-form.pdf").exists()


def test_a_value_with_no_place_on_the_form_blocks_the_signature(tmp_path: Path) -> None:
    path = _flat_form(tmp_path / "flat.pdf", signatures=1)
    anchors, values = _inputs(path)
    values["flat:0:street:1"] = "הרצל 10"
    with pytest.raises(UnprocessableError):
        _sign(path, tmp_path / "signed.pdf", anchors, values)


def test_the_preview_shows_the_values_and_is_marked_as_a_draft(tmp_path: Path) -> None:
    path = _flat_form(tmp_path / "flat.pdf", signatures=1)
    anchors, values = _inputs(path)
    data = preview_flat_form(PdfFillerService(_FONT), source_path=path, anchors=anchors, values=values, rtl_names=set())
    page = pymupdf.open(stream=data, filetype="pdf")[0]
    assert "DRAFT - NOT SIGNED" in page.get_text()
    assert "0501234567" in page.get_text("text", clip=pymupdf.Rect(next(a for a in anchors if a["slot_key"] == "phone")["rect"]))
    assert page.get_images() == []
