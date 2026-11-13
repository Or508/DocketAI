"""The shapes a real government form uses: white cells on a shaded panel, header cells,
digit boxes, underscore rules, and the same label in two sections. All synthetic."""

import io
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("fitz")

import pymupdf
from PIL import Image, ImageDraw

from app.core.exceptions import UnprocessableError
from app.domain.certificate import CertificateData
from app.schemas.process import FieldSpec
from app.services.flat_form import FlatProfile, fill_flat_form, read_flat_anchors, sign_flat_form, signature_box
from app.services.pdf_filler import PdfFillerService
from tests.test_flat_form import _FONT, _label

_INSURED = "פרטי המבוטח"
_SPOUSE = "פרטי בן/בת הזוג"
_ADDRESS = "כתובת מגורים"
_ID = "100000009"
_SIGNED_AT = datetime(2026, 11, 11, 9, 30, tzinfo=timezone.utc)
_SIGN_LABELS = ["חתימת המבוטח"]


def _spec(key: str, label_he: str, field_type: str = "text") -> FieldSpec:
    return FieldSpec(key=key, label=key.replace("_", " "), label_he=label_he, field_type=field_type, pdf_field_name=key)


_FIELDS = [
    _spec("last_name", "שם משפחה"),
    _spec("national_id", "מספר זהות", "id_number"),
    _spec("street", "רחוב"),
]
_PROFILE = FlatProfile(
    sections=[_INSURED, _SPOUSE, _ADDRESS],
    slot_section={"last_name": _INSURED, "national_id": _INSURED, "street": _ADDRESS},
)
_WHITE = (1, 1, 1)
_GREY = (0.85, 0.85, 0.85)


def _cell(page, rect: tuple[float, float, float, float]) -> None:
    page.draw_rect(pymupdf.Rect(rect), color=None, fill=_WHITE)


def _comb(page, left: float, bottom: float, boxes: int = 9, width: float = 17.4) -> None:
    for index in range(boxes + 1):
        x = left + index * width
        page.draw_line((x, bottom - 7), (x, bottom), width=0.5)
    page.draw_line((left, bottom), (left + boxes * width, bottom), width=0.5)


def _shaded_form(path: Path, *, margin_text: bool = False) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_font(fontname="rubik", fontfile=str(_FONT))
    page.draw_rect(pymupdf.Rect(40, 80, 570, 300), color=None, fill=_GREY)

    _label(page, 552, 95, _INSURED)
    _cell(page, (352, 100, 556, 140))
    _label(page, 552, 111, "שם משפחה")
    _cell(page, (50, 100, 216, 140))
    # The label is stored as three pieces: one word, then a word cut in two with no gap.
    _label(page, 212, 111, "מספר")
    cut = pymupdf.Font(fontfile=str(_FONT)).text_length("זה", fontsize=8)
    _label(page, 186, 111, "זה")
    _label(page, 186 - cut, 111, "ות")
    _comb(page, 54, 138)

    _label(page, 552, 160, _SPOUSE)
    _cell(page, (352, 165, 556, 205))
    _label(page, 552, 176, "שם משפחה")
    _cell(page, (50, 165, 216, 205))
    _label(page, 212, 176, "מספר זהות")
    _comb(page, 54, 203)

    _label(page, 552, 225, _ADDRESS)
    _cell(page, (395, 230, 556, 242))
    _label(page, 490, 239.5, "רחוב")
    _cell(page, (395, 244, 556, 264))

    # A signature rule printed as underscores, with a cross between the label and the rule.
    _label(page, 320, 480, "חתימת המבוטח")
    page.insert_text((246, 480), "×", fontsize=9)
    page.insert_text((60, 480), "_" * 32, fontsize=10)
    if margin_text:
        _label(page, 420, 765, "טופס זה מנוסח בלשון זכר")
        page.insert_text((510, 781), "BL 0000", fontsize=7)
    document.save(path)
    document.close()
    return path


def _anchors(path: Path, profile: FlatProfile | None = _PROFILE) -> dict[str, dict]:
    return {anchor["slot_key"]: anchor for anchor in read_flat_anchors(path, _FIELDS, profile)}


def test_white_cells_header_cells_and_digit_boxes_are_anchored(tmp_path: Path) -> None:
    anchors = _anchors(_shaded_form(tmp_path / "form.pdf"))
    assert {key: anchor["target"] for key, anchor in anchors.items()} == {
        "last_name": "cell_below",
        "national_id": "comb",
        "street": "cell_under",
    }
    assert pymupdf.Rect(352, 100, 556, 140).contains(pymupdf.Rect(anchors["last_name"]["rect"]))
    assert anchors["street"]["rect"] == [395, 244, 556, 264]
    boxes = anchors["national_id"]["boxes"]
    assert len(boxes) == 9
    assert all(pymupdf.Rect(50, 100, 216, 140).contains(pymupdf.Rect(box)) for box in boxes)
    assert [box[0] for box in boxes] == sorted(box[0] for box in boxes)


def test_a_label_binds_only_under_its_declared_section(tmp_path: Path) -> None:
    path = _shaded_form(tmp_path / "form.pdf")
    scoped = _anchors(path)
    assert scoped["last_name"]["rect"][1] < 140
    assert scoped["national_id"]["rect"][1] < 140
    # Without a section the same label names two places, so the slot binds to neither.
    unscoped = _anchors(path, None)
    assert "last_name" not in unscoped and "national_id" not in unscoped
    assert unscoped["street"]["target"] == "cell_under"


def test_digits_are_written_one_per_box_and_read_back(tmp_path: Path) -> None:
    path = _shaded_form(tmp_path / "form.pdf")
    anchors = read_flat_anchors(path, _FIELDS, _PROFILE)
    names = {anchor["slot_key"]: anchor["field_name"] for anchor in anchors}
    values = {names["national_id"]: _ID, names["last_name"]: "כהן", names["street"]: "הרצל"}
    filled = fill_flat_form(path.read_bytes(), anchors, values, _FONT)
    assert {item.status for item in filled.fields} == {"ok"}
    page = pymupdf.open(stream=filled.pdf_bytes, filetype="pdf")[0]
    comb = next(anchor for anchor in anchors if anchor["slot_key"] == "national_id")
    for digit, box in zip(_ID, comb["boxes"]):
        assert page.get_text("text", clip=pymupdf.Rect(box)).strip() == digit
    # The spouse's boxes stay empty.
    assert page.get_text("text", clip=pymupdf.Rect(50, 190, 216, 205)).strip() == ""
    assert read_flat_anchors_count(filled.pdf_bytes, tmp_path) == 0


def read_flat_anchors_count(data: bytes, tmp_path: Path) -> int:
    path = tmp_path / "filled.pdf"
    path.write_bytes(data)
    return len(read_flat_anchors(path, _FIELDS, _PROFILE))


@pytest.mark.parametrize("value", ["12345678", "1000000090", "10000000A"])
def test_a_value_that_is_not_exactly_one_digit_per_box_is_not_written(tmp_path: Path, value: str) -> None:
    path = _shaded_form(tmp_path / "form.pdf")
    anchors = [anchor for anchor in read_flat_anchors(path, _FIELDS, _PROFILE) if anchor["slot_key"] == "national_id"]
    filled = fill_flat_form(path.read_bytes(), anchors, {anchors[0]["field_name"]: value}, _FONT)
    assert [item.status for item in filled.fields] == ["overflow"]
    page = pymupdf.open(stream=filled.pdf_bytes, filetype="pdf")[0]
    assert page.get_text("text", clip=pymupdf.Rect(anchors[0]["rect"])).strip() == ""


def test_an_underscore_rule_with_a_symbol_before_it_is_the_signature_box(tmp_path: Path) -> None:
    page, rect = signature_box(_shaded_form(tmp_path / "form.pdf"), _SIGN_LABELS)
    assert page == 0
    assert 55 <= rect[0] <= 65 and rect[2] < 246
    assert rect[3] <= 481.5 and rect[3] - rect[1] >= 39


def test_the_audit_line_takes_a_blank_margin_and_never_covers_print(tmp_path: Path) -> None:
    path = _shaded_form(tmp_path / "form.pdf", margin_text=True)
    anchors = read_flat_anchors(path, _FIELDS, _PROFILE)
    names = {anchor["slot_key"]: anchor["field_name"] for anchor in anchors}
    image = Image.new("RGBA", (400, 120), (255, 255, 255, 0))
    ImageDraw.Draw(image).line([(20, 90), (140, 30), (220, 95), (380, 40)], fill=(20, 20, 60, 255), width=5)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    certificate = CertificateData(
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
    out = tmp_path / "signed.pdf"
    sign_flat_form(
        PdfFillerService(_FONT),
        source_path=path,
        output_path=out,
        anchors=anchors,
        values={names["national_id"]: _ID, names["last_name"]: "כהן", names["street"]: "הרצל"},
        rtl_names=set(),
        signature_png=buffer.getvalue(),
        signature_labels=_SIGN_LABELS,
        certificate=certificate,
        signed_at=_SIGNED_AT,
    )
    page = pymupdf.open(out)[0]
    words = page.get_text("words")
    audit = [pymupdf.Rect(word[:4]) for word in words if word[1] > 740 and word[4] in {"Ref", "Content", "SHA-256"}]
    printed = [pymupdf.Rect(word[:4]) for word in words if word[1] > 740 and (word[4] == "0000" or "א" <= word[4][:1] <= "ת")]
    assert len(audit) == 3 and printed
    assert not any(a.intersects(p) for a in audit for p in printed)


def test_a_page_with_no_blank_margin_is_not_signed(tmp_path: Path) -> None:
    path = _shaded_form(tmp_path / "form.pdf", margin_text=True)
    document = pymupdf.open(path)
    document[0].insert_text((30, 782), "printed across the whole bottom margin " * 3, fontsize=7)
    document[0].insert_text((30, 16), "printed across the whole top margin " * 3, fontsize=7)
    crowded = tmp_path / "crowded.pdf"
    document.save(crowded)
    document.close()
    anchors = read_flat_anchors(crowded, _FIELDS, _PROFILE)
    with pytest.raises(UnprocessableError):
        sign_flat_form(
            PdfFillerService(_FONT),
            source_path=crowded,
            output_path=tmp_path / "signed.pdf",
            anchors=anchors,
            values={},
            rtl_names=set(),
            signature_png=_png(),
            signature_labels=_SIGN_LABELS,
            certificate=_certificate(),
            signed_at=_SIGNED_AT,
        )
    assert not (tmp_path / "signed.pdf").exists()


def _png() -> bytes:
    image = Image.new("RGBA", (400, 120), (255, 255, 255, 0))
    ImageDraw.Draw(image).line([(20, 90), (380, 40)], fill=(20, 20, 60, 255), width=5)
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


def test_a_profile_is_read_from_the_process_layout() -> None:
    profile = FlatProfile.from_layout(
        {"flat_form": {"labels": {"city": ["יישוב"]}, "sections": [_INSURED], "slot_section": {"city": _INSURED}}}
    )
    assert profile == FlatProfile(labels={"city": ["יישוב"]}, sections=[_INSURED], slot_section={"city": _INSURED})
    assert FlatProfile.from_layout(None) == FlatProfile()
    assert FlatProfile.from_layout({"signature_rect": [1, 2, 3, 4]}) == FlatProfile()
