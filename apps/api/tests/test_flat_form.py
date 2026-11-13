"""A flat form: printed labels and ruled boxes, no widgets. A value is painted only into a drawn target."""

from pathlib import Path

import pytest

pytest.importorskip("fitz")

import pymupdf

from app.domain.text_layout import shape_for_pdf
from app.schemas.process import FieldSpec
from app.services.flat_form import fill_flat_form, read_flat_anchors
from app.services.pdf_filler import _readback_matches

_FONT = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / "Rubik-Regular.ttf"


def _spec(key: str, label_he: str, field_type: str = "text") -> FieldSpec:
    return FieldSpec(key=key, label=key.replace("_", " "), label_he=label_he, field_type=field_type, pdf_field_name=key)


_FIELDS = [
    _spec("first_name", "שם פרטי"),
    _spec("last_name", "שם משפחה"),
    _spec("city", "עיר מגורים"),
    _spec("street", "רחוב"),
    _spec("phone", "טלפון", "phone"),
    _spec("national_id", "מספר זהות", "id_number"),
]


def _label(page, right: float, baseline: float, text: str, size: float = 8, *, shaped: bool = True) -> None:
    """Print Hebrew with its right edge at `right`. Unshaped text is extracted with reversed words."""
    shown = shape_for_pdf(text) if shaped else text
    width = pymupdf.Font(fontfile=str(_FONT)).text_length(shown, fontsize=size)
    page.insert_text((right - width, baseline), shown, fontname="rubik", fontsize=size)


def _flat_form(path: Path, *, logical: bool = False, signatures: int = 0) -> Path:
    """Synthetic flat form. Every target shape the resolver knows, plus the cases it must refuse."""
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_font(fontname="rubik", fontfile=str(_FONT))
    def put(right: float, y: float, text: str) -> None:
        _label(page, right, y, text, shaped=not logical)

    # A drawn rectangle with the label in its top-right corner: the value goes below the label.
    page.draw_rect(pymupdf.Rect(300, 100, 540, 140), width=0.7)
    put(536, 110, "שם פרטי")
    # A cell made of four separate lines, too short for a second row: the value goes beside the label.
    for start, end in (((60, 100), (280, 100)), ((60, 120), (280, 120)), ((60, 100), (60, 120)), ((280, 100), (280, 120))):
        page.draw_line(start, end, width=0.7)
    put(276, 113, "שם משפחה")
    # A label with a writing rule to its left.
    put(540, 200, "טלפון")
    page.draw_line((330, 202), (505, 202), width=0.7)
    # A cell that already holds ink is not a target.
    page.draw_rect(pymupdf.Rect(300, 240, 540, 280), width=0.7)
    put(536, 250, "עיר מגורים")
    page.insert_text((320, 272), "ALREADY HERE", fontsize=9)
    # A label inside running text, with nothing drawn for it.
    put(540, 340, "רחוב")
    # A label that is part of a longer printed phrase is a different label.
    page.draw_rect(pymupdf.Rect(300, 380, 540, 420), width=0.7)
    put(536, 390, "מספר זהות של בן הזוג")
    # Signature rules. A form to be signed shows exactly one.
    for index in range(signatures):
        put(540, 520 + index * 80, "חתימה")
        page.draw_line((330, 522 + index * 80), (505, 522 + index * 80), width=0.7)
    document.save(path)
    document.close()
    return path


def _anchors(path: Path) -> dict[str, dict]:
    return {anchor["slot_key"]: anchor for anchor in read_flat_anchors(path, _FIELDS)}


def test_each_drawn_target_shape_is_anchored_to_its_slot(tmp_path: Path) -> None:
    anchors = _anchors(_flat_form(tmp_path / "flat.pdf"))
    assert {key: anchor["target"] for key, anchor in anchors.items()} == {
        "first_name": "cell_below",
        "last_name": "cell_beside",
        "phone": "underline",
    }
    assert all(anchor["kind"] == "flat" and anchor["empty"] and anchor["match"] == "exact" for anchor in anchors.values())
    first = pymupdf.Rect(anchors["first_name"]["rect"])
    assert pymupdf.Rect(300, 100, 540, 140).contains(first) and first.y0 > 110
    last = pymupdf.Rect(anchors["last_name"]["rect"])
    assert pymupdf.Rect(60, 100, 280, 120).contains(last) and last.x1 < 245
    phone = pymupdf.Rect(anchors["phone"]["rect"])
    assert (phone.x0, phone.x1) == (330, 505) and phone.y1 < 202


def test_inked_cells_bare_labels_and_longer_phrases_are_not_anchored(tmp_path: Path) -> None:
    anchors = _anchors(_flat_form(tmp_path / "flat.pdf"))
    assert "city" not in anchors
    assert "street" not in anchors
    assert "national_id" not in anchors


def test_labels_extracted_with_reversed_words_anchor_the_same_slots(tmp_path: Path) -> None:
    anchors = _anchors(_flat_form(tmp_path / "logical.pdf", logical=True))
    assert set(anchors) == {"first_name", "last_name", "phone"}


def test_values_are_painted_into_the_targets_and_read_back(tmp_path: Path) -> None:
    path = _flat_form(tmp_path / "flat.pdf")
    original = path.read_bytes()
    anchors = read_flat_anchors(path, _FIELDS)
    values = {anchor["field_name"]: value for anchor in anchors for key, value in (
        ("first_name", "דנה"), ("last_name", "כהן"), ("phone", "0501234567")
    ) if anchor["slot_key"] == key}
    filled = fill_flat_form(original, anchors, values, _FONT)
    assert path.read_bytes() == original
    assert {item.field_name: item.status for item in filled.fields} == {name: "ok" for name in values}
    written = pymupdf.open(stream=filled.pdf_bytes, filetype="pdf")
    try:
        for anchor in anchors:
            text = written[0].get_text("text", clip=pymupdf.Rect(anchor["rect"]))
            value = values[anchor["field_name"]]
            assert _readback_matches(value, text, any("֐" <= ch <= "׿" for ch in value))
        # The printed labels are still on the page.
        assert len(read_flat_anchors_from_bytes(filled.pdf_bytes, tmp_path)) == 0
    finally:
        written.close()
    assert fill_flat_form(original, anchors, values, _FONT).pdf_bytes == filled.pdf_bytes


def read_flat_anchors_from_bytes(data: bytes, tmp_path: Path) -> list[dict]:
    """A filled form has ink in every target, so a second pass finds nothing left to anchor."""
    path = tmp_path / "filled.pdf"
    path.write_bytes(data)
    return read_flat_anchors(path, _FIELDS)


def test_a_value_too_wide_for_its_target_is_not_painted(tmp_path: Path) -> None:
    path = _flat_form(tmp_path / "flat.pdf")
    anchors = [anchor for anchor in read_flat_anchors(path, _FIELDS) if anchor["slot_key"] == "last_name"]
    values = {anchors[0]["field_name"]: "כהן " * 40}
    filled = fill_flat_form(path.read_bytes(), anchors, values, _FONT)
    assert [item.status for item in filled.fields] == ["overflow"]
    page = pymupdf.open(stream=filled.pdf_bytes, filetype="pdf")[0]
    assert page.get_text("text", clip=pymupdf.Rect(anchors[0]["rect"])).strip() == ""


def test_a_target_inked_after_anchoring_is_skipped(tmp_path: Path) -> None:
    path = _flat_form(tmp_path / "flat.pdf")
    anchors = [anchor for anchor in read_flat_anchors(path, _FIELDS) if anchor["slot_key"] == "first_name"]
    document = pymupdf.open(path)
    rect = pymupdf.Rect(anchors[0]["rect"])
    document[0].insert_text((rect.x0 + 10, rect.y1 - 6), "TAKEN", fontsize=9)
    inked = document.tobytes()
    document.close()
    filled = fill_flat_form(inked, anchors, {anchors[0]["field_name"]: "דנה"}, _FONT)
    assert [item.status for item in filled.fields] == ["skipped_prefilled"]
