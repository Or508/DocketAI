"""Smart upload files a mixed drop by itself, and the real estate process runs on its own blank form."""

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("PIL")

import pymupdf
from fastapi.testclient import TestClient

from app.catalog.processes import PROCESSES
from app.core.config import get_settings
from app.domain.smart_routing import route_document
from app.domain.text_layout import contains_hebrew
from app.schemas.process import FieldSpec
from app.services.flat_form import FlatProfile, read_flat_anchors, signature_box
from app.services.fonts import resolve_hebrew_font
from app.services.form101 import build_form_101
from app.services.pdf_filler import _readback_matches
from app.services.real_estate_form import REAL_ESTATE_FORM_VERSION, build_real_estate_form
from tests.support import SignedOut, authenticate
from tests.test_bl6101_sanity_drill import _ID, _PNG_B64, _auth, _classify, _pdf, _set, _sign_body, _token, _upload

_DEAL = next(process for process in PROCESSES if process.key == "real_estate")
_DEAL_FIELDS = [FieldSpec.model_validate(item) for item in _DEAL.required_fields]
_DEAL_SLOTS = ["buyer_name", "seller_name", "property_address_he", "parcel_number", "price", "contract_date"]
_DEAL_TYPED = {
    "buyer_name": "דנה כהן",
    "seller_name": "יוסי לוי",
    "property_address_he": "הרצל 15, תל אביב",
    "parcel_number": "6941/12",
    "price": "2500000",
    "contract_date": "2026-12-01",
}
# What the three everyday documents say, under names an office would give them.
_ID_LINES = ["שם פרטי: דנה", "שם משפחה: כהן", _ID]
_ARNONA_LINES = ["רחוב", "הרצל", "עיר", "תל אביב"]
_BANK_LINES = ["שם הבנק: לאומי", "מספר סניף", "800", "מספר חשבון", "456789"]
_READ = {
    "national_id": _ID,
    "first_name": "דנה",
    "last_name": "כהן",
    "street": "הרצל",
    "city": "תל אביב",
    "bank_name": "לאומי",
    "bank_branch": "800",
    "bank_account": "456789",
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
    # No office copy of any blank: Form 101 and the real estate form are drawn, BL/6101 is absent.
    monkeypatch.setenv("FORM_101_TEMPLATE_PATH", str(tmp_path / "server" / "form_101.pdf"))
    monkeypatch.setenv("REAL_ESTATE_TEMPLATE_PATH", str(tmp_path / "server" / "real_estate.pdf"))
    monkeypatch.setenv("BL_6101_TEMPLATE_PATH", str(tmp_path / "server" / "bl_6101.pdf"))
    monkeypatch.setenv("QUEUE_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    from app.db.session import reset_db

    get_settings.cache_clear()
    reset_db()
    from app.main import app

    with TestClient(app) as test_client:
        authenticate(test_client)
        yield test_client
    reset_db()
    get_settings.cache_clear()


def _font() -> Path:
    font = resolve_hebrew_font(None)
    assert font is not None
    return font


def _open(client: TestClient, key: str, headers: dict[str, str] | None = None) -> str:
    created = client.post("/cases", headers=headers, json={"name": "Case", "process_key": key, "client_name": "דנה כהן"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _drop(client: TestClient, case_id: str, files: list[tuple[str, bytes]], headers: dict[str, str] | None = None):
    return client.post(
        f"/cases/{case_id}/smart-upload",
        headers=headers,
        files=[("files", (name, data, "application/pdf")) for name, data in files],
    )


def _everyday(tmp_path: Path) -> list[tuple[str, bytes]]:
    return [
        ("id.pdf", _pdf(tmp_path / "id.pdf", _ID_LINES)),
        ("arnona.pdf", _pdf(tmp_path / "arnona.pdf", _ARNONA_LINES)),
        ("bank.pdf", _pdf(tmp_path / "bank.pdf", _BANK_LINES)),
    ]


def _forms(client: TestClient, case_id: str) -> list[dict]:
    return client.get(f"/cases/{case_id}/intake").json()["forms"]


def _timeline(client: TestClient, case_id: str) -> list[dict]:
    return client.get(f"/cases/{case_id}/timeline").json()


def _drawers(body: dict) -> dict[str, list[str]]:
    """Which files sit in which drawer, by filename."""
    found: dict[str, list[str]] = {}
    for item in body["gap"]["identified"]:
        found.setdefault(item["document_type"], []).append(item["filename"])
    return found


# Routing


def test_a_file_is_routed_only_when_one_drawer_clearly_leads() -> None:
    allowed = ["id_copy", "proof_of_address", "bank_confirmation"]
    assert route_document("scan-001.pdf", "אישור ניהול חשבון\nבנק לאומי", allowed).document_type == "bank_confirmation"
    assert route_document("scan-002.pdf", "חשבון ארנונה לשנת 2026", allowed).document_type == "proof_of_address"
    assert route_document("scan-003.pdf", "תעודת זהות", allowed).matched_by == "content"
    assert route_document("arnona.pdf", "", allowed).matched_by == "filename"
    assert route_document("ID.PDF", "שם פרטי", allowed).matched_by == "filename_and_content"
    # Nothing to go on, a tie, or a type this process does not take: left for the office.
    assert route_document("scan-004.pdf", "מסמך כללי", allowed) is None
    assert route_document("scan-005.pdf", "תעודת זהות\nארנונה", allowed) is None
    assert route_document("tabu.pdf", "נסח טאבו", allowed) is None
    assert route_document("tabu.pdf", "נסח טאבו", ["title_deed", "id_copy"]).document_type == "title_deed"


# Smart upload


def test_one_drop_of_id_arnona_and_bank_fills_the_three_drawers_and_the_fields(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _open(client, "bl_6101")
    dropped = _drop(client, case_id, _everyday(tmp_path))
    assert dropped.status_code == 200, dropped.text
    body = dropped.json()

    # The workspace is at the root of the response, with one line per file beside it.
    workspace = client.get(f"/cases/{case_id}").json()
    assert set(workspace) <= set(body)
    assert set(body) - set(workspace) == {"routed_files"}
    assert body["case"]["id"] == case_id
    assert body["case"]["document_count"] == 3
    assert body["case"]["status"] != "processing"

    routed = {item["filename"]: item for item in body["routed_files"]}
    assert [item["filename"] for item in body["routed_files"]] == ["id.pdf", "arnona.pdf", "bank.pdf"]
    assert {name: item["document_type"] for name, item in routed.items()} == {
        "id.pdf": "id_copy",
        "arnona.pdf": "proof_of_address",
        "bank.pdf": "bank_confirmation",
    }
    assert all(item["outcome"] == "routed" and item["role"] == "evidence" for item in routed.values())
    assert all(item["status"] == "classified" and item["document_id"] for item in routed.values())
    assert all(item["drawer_label_he"] and not item["duplicate"] for item in routed.values())
    assert _drawers(body) == {
        "id_copy": ["id.pdf"],
        "proof_of_address": ["arnona.pdf"],
        "bank_confirmation": ["bank.pdf"],
    }
    assert body["gap"]["missing"] == [] and body["gap"]["unrecognized"] == []

    # Every detail the three documents carry is on the case, each traced to its file.
    for key, value in _READ.items():
        assert body["field_values"][key] == value, key
        assert body["field_sources"][key]["source"] == "document", key
    assert body["field_sources"]["national_id"]["document_id"] == routed["id.pdf"]["document_id"]
    assert body["field_sources"]["bank_name"]["document_id"] == routed["bank.pdf"]["document_id"]

    record = next(event for event in _timeline(client, case_id) if event["action"] == "smart_upload_completed")
    staff = client.get("/auth/me").json()
    assert record["actor"] == f"user:{staff['id']}"
    assert record["metadata"]["documents"] == 3


def test_a_new_drop_replaces_the_drawer_and_the_same_file_is_not_stored_twice(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _open(client, "bl_6101")
    assert _drop(client, case_id, _everyday(tmp_path)).status_code == 200

    # The same bank letter again: filed, not stored a second time.
    again = _drop(client, case_id, [("bank.pdf", (tmp_path / "bank.pdf").read_bytes())])
    assert again.status_code == 200, again.text
    assert again.json()["case"]["document_count"] == 3
    assert again.json()["routed_files"][0]["duplicate"] is True
    assert again.json()["routed_files"][0]["outcome"] == "routed"

    # A different bank letter takes the drawer, and its details replace the old ones.
    newer = _pdf(tmp_path / "bank-2.pdf", ["שם הבנק: דיסקונט", "מספר סניף", "123", "מספר חשבון", "998877"])
    replaced = _drop(client, case_id, [("bank-2.pdf", newer)])
    assert replaced.status_code == 200, replaced.text
    body = replaced.json()
    assert body["case"]["document_count"] == 3
    assert _drawers(body)["bank_confirmation"] == ["bank-2.pdf"]
    assert body["field_values"]["bank_name"] == "דיסקונט"
    assert body["field_values"]["bank_account"] == "998877"
    # The other drawers are untouched.
    assert body["field_values"]["national_id"] == _ID
    assert _drawers(body)["id_copy"] == ["id.pdf"]


def test_a_dropped_form_becomes_the_case_form_and_an_unknown_file_waits_for_the_office(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _open(client, "employee_onboarding")
    mystery = _pdf(tmp_path / "scan-77.pdf", ["מסמך כללי ללא כותרת"])
    dropped = _drop(
        client,
        case_id,
        [("blank.pdf", build_form_101(_font())), *_everyday(tmp_path), ("scan-77.pdf", mystery)],
    )
    assert dropped.status_code == 200, dropped.text
    body = dropped.json()
    routed = {item["filename"]: item for item in body["routed_files"]}

    assert routed["blank.pdf"]["outcome"] == "routed"
    assert routed["blank.pdf"]["role"] == "form" and routed["blank.pdf"]["matched_by"] == "form"
    assert routed["blank.pdf"]["document_type"] is None
    forms = _forms(client, case_id)
    assert [(item["filename"], item["role"], item["bound"]) for item in forms] == [("blank.pdf", "form", 10)]

    assert routed["scan-77.pdf"]["outcome"] == "unrouted"
    assert routed["scan-77.pdf"]["reason"]
    assert [item["filename"] for item in body["gap"]["unrecognized"]] == ["scan-77.pdf"]

    # The three documents were read onto the form's slots in the same request.
    for key, value in _READ.items():
        assert body["field_values"][key] == value, key

    # Dropping a fresh copy of the form replaces the one on the case.
    marked = pymupdf.open(stream=build_form_101(_font()), filetype="pdf")
    marked.set_metadata({"title": "Second copy"})
    second = marked.tobytes()
    marked.close()
    swapped = _drop(client, case_id, [("blank-2.pdf", second)])
    assert swapped.status_code == 200, swapped.text
    assert [item["filename"] for item in _forms(client, case_id)] == ["blank-2.pdf"]


def test_smart_upload_refuses_bad_drops_signed_cases_other_offices_and_strangers(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _open(client, "bl_6101")
    files = _everyday(tmp_path)

    too_many = [(f"id-{index}.pdf", _pdf(tmp_path / f"id-{index}.pdf", [f"מסמך {index}"])) for index in range(11)]
    assert _drop(client, case_id, too_many).status_code == 400
    assert client.post(f"/cases/{case_id}/smart-upload").status_code == 422
    assert client.get(f"/cases/{case_id}").json()["case"]["document_count"] == 0

    # A file that is not a document is refused by name; the others are still filed.
    mixed = client.post(
        f"/cases/{case_id}/smart-upload",
        files=[
            ("files", ("id.pdf", files[0][1], "application/pdf")),
            ("files", ("notes.exe", b"MZ not a document", "application/octet-stream")),
        ],
    )
    assert mixed.status_code == 200, mixed.text
    outcomes = {item["filename"]: item["outcome"] for item in mixed.json()["routed_files"]}
    assert outcomes == {"id.pdf": "routed", "notes.exe": "rejected"}
    assert mixed.json()["case"]["document_count"] == 1

    # Another office cannot see or change this case; a stranger is turned away.
    before = client.get(f"/cases/{case_id}").json()
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    headers = {"Authorization": f"Bearer {other['token']}"}
    assert _drop(client, case_id, files, headers).status_code == 404
    with SignedOut(client) as anonymous:
        assert anonymous.post(
            f"/cases/{case_id}/smart-upload", files=[("files", ("id.pdf", files[0][1], "application/pdf"))]
        ).status_code == 401
    assert client.get(f"/cases/{case_id}").json() == before
    theirs = _open(client, "bl_6101", headers)
    own = _drop(client, theirs, files, headers)
    assert own.status_code == 200, own.text
    assert own.json()["case"]["document_count"] == 3

    # A signed case keeps its files.
    deal, _form_id, _values = _prepared_deal(client, tmp_path)
    assert client.post(f"/cases/{deal}/fill-and-sign", json=_sign_body()).status_code == 200
    count = client.get(f"/cases/{deal}").json()["case"]["document_count"]
    assert _drop(client, deal, files).status_code == 409
    assert client.get(f"/cases/{deal}").json()["case"]["document_count"] == count
    assert client.get(f"/cases/{deal}").json()["case"]["status"] == "signed"


# Real estate


def _deal_blank() -> bytes:
    return build_real_estate_form(_font())


def _prepared_deal(client: TestClient, tmp_path: Path) -> tuple[str, str, dict[str, str]]:
    """A real estate case with its form loaded, its required documents filed, and every detail in."""
    case_id = _open(client, "real_estate")
    loaded = client.post(f"/cases/{case_id}/load-default-form")
    assert loaded.status_code == 200, loaded.text
    required = [item["type_key"] for item in _DEAL.required_documents]
    for index, document_type in enumerate(required):
        name = f"deal-doc-{index}.pdf"
        document_id = _upload(client, case_id, name, _pdf(tmp_path / name, [f"מסמך עסקה {index}"]))
        _classify(client, case_id, document_id, document_type)
    body: dict = {}
    for key, value in _DEAL_TYPED.items():
        body = _set(client, case_id, key, value)
    assert body["ready_to_sign"] is True, body["signing_blockers"]
    return case_id, _forms(client, case_id)[0]["document_id"], body["field_values"]


def _assert_deal_filled(pdf: bytes, values: dict[str, str], tmp_path: Path) -> pymupdf.Document:
    blank = tmp_path / "deal-blank-for-anchors.pdf"
    blank.write_bytes(_deal_blank())
    anchors = {
        anchor["slot_key"]: anchor
        for anchor in read_flat_anchors(blank, _DEAL_FIELDS, FlatProfile.from_layout(_DEAL.layout))
    }
    document = pymupdf.open(stream=pdf, filetype="pdf")
    for key in _DEAL_SLOTS:
        anchor = anchors[key]
        shown = document[anchor["page"]].get_text("text", clip=pymupdf.Rect(anchor["rect"]))
        assert _readback_matches(values[key], shown, contains_hebrew(values[key])), key
    return document


def test_the_real_estate_blank_is_stable_and_has_a_cell_for_every_field(tmp_path: Path) -> None:
    first = _deal_blank()
    assert first == _deal_blank()
    path = tmp_path / "real_estate.pdf"
    path.write_bytes(first)
    document = pymupdf.open(path)
    try:
        assert document.page_count == 2
        assert not any(page.first_widget for page in document)
        for page in document:
            strip = pymupdf.Rect(0, page.rect.height - 36, page.rect.width, page.rect.height)
            assert not page.get_text("text", clip=strip).strip()
    finally:
        document.close()
    anchors = read_flat_anchors(path, _DEAL_FIELDS, FlatProfile.from_layout(_DEAL.layout))
    assert sorted(anchor["slot_key"] for anchor in anchors) == sorted(spec.key for spec in _DEAL_FIELDS)
    assert sorted(anchor["slot_key"] for anchor in anchors) == sorted(_DEAL_SLOTS)
    assert all(anchor["page"] == 0 and anchor["target"] == "cell_below" for anchor in anchors)
    page, rect = signature_box(path, _DEAL.layout["signature_labels"])
    assert page == 1
    assert rect[2] - rect[0] > 150 and rect[3] - rect[1] > 40


def test_loading_the_default_form_puts_the_real_estate_form_on_the_case(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client, "real_estate")
    loaded = client.post(f"/cases/{case_id}/load-default-form")
    assert loaded.status_code == 200, loaded.text
    body = loaded.json()
    assert body["case"]["document_count"] == 1
    assert body["gap"]["unrecognized"] == [] and body["gap"]["in_progress"] == []

    forms = _forms(client, case_id)
    assert [(item["filename"], item["role"]) for item in forms] == [("real_estate_official.pdf", "form")]
    assert forms[0]["bound"] == len(_DEAL_SLOTS)
    stored = client.get(f"/cases/{case_id}/documents/{forms[0]['document_id']}/file").content
    assert stored == _deal_blank()
    assert [path.name for path in (tmp_path / "templates").glob("real-estate-blank-v*.pdf")] == [
        f"real-estate-blank-v{REAL_ESTATE_FORM_VERSION}.pdf"
    ]
    record = next(event for event in _timeline(client, case_id) if event["action"] == "default_form_loaded")
    assert record["metadata"]["sha256"] == hashlib.sha256(stored).hexdigest()

    # Another office cannot load a form onto this case.
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    headers = {"Authorization": f"Bearer {other['token']}"}
    assert client.post(f"/cases/{case_id}/load-default-form", headers=headers).status_code == 404
    assert client.get(f"/cases/{case_id}", headers=headers).status_code == 404


def test_the_real_estate_preview_shows_every_value_in_its_cell_as_a_draft(client: TestClient, tmp_path: Path) -> None:
    case_id, form_id, values = _prepared_deal(client, tmp_path)
    preview = client.get(f"/cases/{case_id}/documents/{form_id}/filled-preview")
    assert preview.status_code == 200, preview.text
    document = _assert_deal_filled(preview.content, values, tmp_path)
    try:
        assert document.page_count == 2
        shown = " ".join(page.get_text() for page in document)
        assert "טיוטה" in shown or "הטויט" in shown
        assert document[1].get_image_info() == []
    finally:
        document.close()

    token = _token(client, case_id)
    signer = client.get("/portal/preview", headers=_auth(token))
    assert signer.status_code == 200, signer.text
    seen = _assert_deal_filled(signer.content, values, tmp_path)
    try:
        assert "DRAFT - NOT SIGNED" in " ".join(page.get_text() for page in seen)
    finally:
        seen.close()


def test_the_buyer_signs_the_real_estate_form_through_the_link_and_the_seal_verifies(
    client: TestClient, tmp_path: Path
) -> None:
    case_id, _form_id, values = _prepared_deal(client, tmp_path)
    token = _token(client, case_id)
    view = client.get("/portal", headers=_auth(token)).json()
    assert view["ready_to_sign"] is True
    signed = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG_B64, "review_digest": view["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text

    office = client.get(f"/cases/{case_id}").json()
    assert office["case"]["status"] == "signed"
    seal = office["case"]["audit"]
    packet = client.get(f"/cases/{case_id}/signed-document").content
    assert hashlib.sha256(packet).hexdigest() == seal["file_sha256"]

    document = _assert_deal_filled(packet, values, tmp_path)
    try:
        # The two form pages, then the seal page.
        assert document.page_count == 3
        blank = tmp_path / "deal-blank-for-signature.pdf"
        blank.write_bytes(_deal_blank())
        page_index, rect = signature_box(blank, _DEAL.layout["signature_labels"])
        box = pymupdf.Rect(rect)
        placed = [pymupdf.Rect(item["bbox"]) for item in document[page_index].get_image_info()]
        assert page_index == 1 and placed
        assert all(box.contains(item) or (box & item).get_area() > 0.9 * item.get_area() for item in placed)
        assert document[0].get_image_info() == []
        assert seal["signer_verification_id"] in document[2].get_text()
    finally:
        document.close()

    with SignedOut(client) as anonymous:
        verified = anonymous.get(
            f"/verify/{seal['signer_verification_id']}", params={"sha256": hashlib.sha256(packet).hexdigest()}
        )
    assert verified.status_code == 200, verified.text
    assert verified.json()["valid"] is True
    assert verified.json()["process_type"] == "real_estate"

    # Another office reaches neither the packet nor the case.
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    headers = {"Authorization": f"Bearer {other['token']}"}
    assert client.get(f"/cases/{case_id}/signed-document", headers=headers).status_code == 404
    assert client.post(f"/cases/{case_id}/fill-and-sign", headers=headers, json=_sign_body()).status_code == 404


def test_a_real_estate_case_with_no_form_still_signs_the_generated_template(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _open(client, "real_estate")
    for index, item in enumerate(_DEAL.required_documents):
        name = f"deal-doc-{index}.pdf"
        document_id = _upload(client, case_id, name, _pdf(tmp_path / name, [f"מסמך עסקה {index}"]))
        _classify(client, case_id, document_id, item["type_key"])
    for key, value in _DEAL_TYPED.items():
        _set(client, case_id, key, value)
    assert _forms(client, case_id) == []
    signed = client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body())
    assert signed.status_code == 200, signed.text
    document = pymupdf.open(stream=client.get(f"/cases/{case_id}/signed-document").content, filetype="pdf")
    try:
        assert document.page_count == 2
    finally:
        document.close()


def test_every_catalog_template_reports_a_form_ready_to_load(client: TestClient, tmp_path: Path) -> None:
    listed = {item["process_type"]: item for item in client.get("/templates").json()}
    # BL/6101 is an official file the office supplies; it is absent here and says so.
    assert listed["bl_6101"]["default_template_available"] is False
    for key in ("onboarding", "real_estate", "employee_onboarding"):
        assert listed[key]["default_template_available"] is True, key
        assert listed[key]["form_source"] == "official_blank", key
    deal = listed["real_estate"]
    assert [item["key"] for item in deal["mapped_fields"]] == _DEAL_SLOTS
    assert {(item["target"]["page"], item["target"]["mode"]) for item in deal["mapped_fields"]} == {(1, "text")}

    # With the official blank in place, every template in the catalog is ready.
    server = tmp_path / "server" / "bl_6101.pdf"
    official = Path(__file__).resolve().parents[3] / "test_files_for_browser" / "bl_6101_official.pdf"
    if not official.is_file():
        pytest.skip("the official BL/6101 blank is not in this checkout")
    server.parent.mkdir(parents=True, exist_ok=True)
    server.write_bytes(official.read_bytes())
    ready = client.get("/templates").json()
    assert all(item["default_template_available"] is True for item in ready)
