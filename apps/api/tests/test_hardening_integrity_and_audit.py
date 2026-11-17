"""The case integrity report, signing link revocation, and the office audit center."""

from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("PIL")

from fastapi.testclient import TestClient

from app.domain.integrity import CaseFacts, FiledDocument, ids_in_text, israeli_id_is_valid, run_checks
from tests.support import SignedOut, authenticate
from tests.test_bl6101_sanity_drill import _ID, _PNG_B64, _auth, _pdf, _set, _sign_body, _token
from tests.test_smart_upload_and_real_estate import (  # noqa: F401  (client is the fixture)
    _BANK_LINES,
    _drop,
    _everyday,
    _timeline,
    client,
)

_DANA = "דנה כהן"
_TYPED = {"house_number": "15", "phone": "0501234567"}
_CODES = [
    "target_form_loaded",
    "required_drawers",
    "national_id_checksum",
    "cross_doc_consistency",
    "required_fields_complete",
]
_OTHER_ID = next(str(number) for number in range(200000000, 200000100) if israeli_id_is_valid(str(number)))


def _new(client: TestClient, key: str, client_name: str | None = _DANA, headers: dict[str, str] | None = None) -> str:
    body = {"name": "Case", "process_key": key}
    if client_name is not None:
        body["client_name"] = client_name
    created = client.post("/cases", headers=headers, json=body)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _other_office(client: TestClient) -> dict[str, str]:
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    return {"Authorization": f"Bearer {other['token']}"}


def _ready_101(client: TestClient, tmp_path: Path) -> str:
    """A Form 101 case with its form, its three documents read, and the rest typed: ready to sign."""
    case_id = _new(client, "employee_onboarding")
    assert client.post(f"/cases/{case_id}/load-default-form").status_code == 200
    assert _drop(client, case_id, _everyday(tmp_path)).status_code == 200
    body: dict = {}
    for key, value in _TYPED.items():
        body = _set(client, case_id, key, value)
    assert body["ready_to_sign"] is True, body["signing_blockers"]
    return case_id


def _integrity(client: TestClient, case_id: str, headers: dict[str, str] | None = None) -> dict:
    response = client.get(f"/cases/{case_id}/integrity", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _checks(report: dict) -> dict[str, dict]:
    assert [item["code"] for item in report["checks"]] == _CODES
    for item in report["checks"]:
        assert set(item) == {"code", "label_he", "status", "detail_he", "field_key", "drawer_type"}
        assert item["status"] in {"pass", "warn", "fail"} and item["label_he"] and item["detail_he"]
    return {item["code"]: item for item in report["checks"]}


def _audit(client: TestClient, headers: dict[str, str] | None = None, **params) -> dict:
    response = client.get("/audit", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


# Integrity


def test_the_id_checksum_rule_and_the_ids_found_in_text() -> None:
    assert israeli_id_is_valid(_ID) and israeli_id_is_valid(_OTHER_ID) and _OTHER_ID != _ID
    wrong = _ID[:-1] + str((int(_ID[-1]) + 1) % 10)
    assert not israeli_id_is_valid(wrong)
    assert not israeli_id_is_valid("000000000") and not israeli_id_is_valid("12345678x")
    assert not israeli_id_is_valid("1234567890")
    # A shorter number is padded on the left, as it is printed on older cards.
    assert israeli_id_is_valid(str(int("0000000" + "18")))
    assert ids_in_text(f"מספר זהות {_ID}\nחשבון {wrong}\nטלפון 0501234567") == {_ID}


def test_an_empty_case_is_blocked_and_says_what_is_missing(client: TestClient) -> None:
    case_id = _new(client, "bl_6101")
    report = _integrity(client, case_id)
    assert set(report) == {"case_id", "status", "score", "checks"}
    assert report["case_id"] == case_id
    assert report["status"] == "block"
    checks = _checks(report)
    assert checks["target_form_loaded"]["status"] == "fail"
    assert checks["required_drawers"]["status"] == "fail"
    assert checks["required_drawers"]["drawer_type"] == "id_copy"
    assert checks["national_id_checksum"]["status"] == "warn"
    assert checks["national_id_checksum"]["field_key"] == "national_id"
    assert checks["cross_doc_consistency"]["status"] == "warn"
    assert checks["required_fields_complete"]["status"] == "warn"
    assert checks["required_fields_complete"]["field_key"] == "national_id"
    # Half marks for the two warnings, nothing else.
    assert report["score"] == 15
    # The same case gives the same report, and reading it leaves no trace.
    assert _integrity(client, case_id) == report
    assert _timeline(client, case_id) == []


def test_a_complete_case_passes_every_check(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready_101(client, tmp_path)
    report = _integrity(client, case_id)
    checks = _checks(report)
    assert {item["status"] for item in checks.values()} == {"pass"}
    assert (report["status"], report["score"]) == ("pass", 100)
    assert "10" in checks["target_form_loaded"]["detail_he"]
    assert "3" in checks["cross_doc_consistency"]["detail_he"]
    # The report names fields and drawers, never the client's values.
    assert _ID not in str(report) and "456789" not in str(report)

    # One drawer emptied and one field still open: blocked, and the score drops.
    documents = client.get(f"/cases/{case_id}").json()["gap"]["identified"]
    bank = next(item["document_id"] for item in documents if item["document_type"] == "bank_confirmation")
    assert client.delete(f"/cases/{case_id}/documents/{bank}").status_code in {200, 204}
    after = _integrity(client, case_id)
    assert after["status"] == "block" and after["score"] < 100
    assert _checks(after)["required_drawers"]["drawer_type"] == "bank_confirmation"


def test_a_document_that_names_another_person_is_caught(client: TestClient, tmp_path: Path) -> None:
    case_id = _new(client, "bl_6101")
    foreign = _pdf(tmp_path / "bank.pdf", [*_BANK_LINES, "מספר זהות בעל החשבון", _OTHER_ID])
    files = [item for item in _everyday(tmp_path) if item[0] != "bank.pdf"] + [("bank.pdf", foreign)]
    dropped = _drop(client, case_id, files)
    assert dropped.status_code == 200, dropped.text
    assert dropped.json()["field_values"]["national_id"] == _ID

    report = _integrity(client, case_id)
    cross = _checks(report)["cross_doc_consistency"]
    assert cross["status"] == "fail"
    assert (cross["drawer_type"], cross["field_key"]) == ("bank_confirmation", "national_id")
    assert report["status"] == "block"
    assert _checks(report)["national_id_checksum"]["status"] == "pass"
    assert _ID not in str(report) and _OTHER_ID not in str(report)

    # The right bank letter in its place: the documents agree again.
    (tmp_path / "fixed").mkdir()
    fixed = _pdf(tmp_path / "fixed" / "bank-ok.pdf", _BANK_LINES)
    assert _drop(client, case_id, [("bank-ok.pdf", fixed)]).status_code == 200
    assert _checks(_integrity(client, case_id))["cross_doc_consistency"]["status"] == "pass"


def test_the_rules_for_a_bad_id_two_forms_and_a_process_without_an_id_field(client: TestClient) -> None:
    wrong = _ID[:-1] + str((int(_ID[-1]) + 1) % 10)
    facts = CaseFacts(
        form_count=2,
        form_bound=4,
        form_required=True,
        missing_drawers=[],
        waiting_files=1,
        required_drawer_count=3,
        required_fields=[("national_id", "מספר זהות", True), ("phone", "טלפון נייד", False)],
        id_key="national_id",
        id_value=wrong,
        cross_checked_drawers=["id_copy", "bank_confirmation"],
        documents=[
            FiledDocument("id_copy", "תעודת זהות", f"מספר {_ID}"),
            FiledDocument("bank_confirmation", "אישור בנק", f"בעל החשבון {_OTHER_ID}"),
        ],
    )
    verdict, score, checks = run_checks(facts)
    by_code = {item.code: item for item in checks}
    assert verdict == "block"
    assert by_code["target_form_loaded"].status == "fail"
    assert by_code["required_drawers"].status == "warn"
    assert by_code["national_id_checksum"].status == "fail"
    # The case number is unsound, so the two documents are compared with each other.
    assert by_code["cross_doc_consistency"].status == "fail"
    assert by_code["cross_doc_consistency"].drawer_type == "bank_confirmation"
    assert by_code["required_fields_complete"].status == "warn"
    assert score == round(25 / 2 + 20 / 2)

    # Real estate has no ID field and one identity document: those two checks do not apply, and
    # a missing blank only warns, because the case can still be signed on the built-in template.
    deal = _checks(_integrity(client, _new(client, "real_estate")))
    assert deal["target_form_loaded"]["status"] == "warn"
    assert deal["national_id_checksum"]["status"] == "pass"
    assert deal["cross_doc_consistency"]["status"] == "pass"


def test_another_office_and_a_stranger_get_no_integrity_report(client: TestClient) -> None:
    case_id = _new(client, "bl_6101")
    assert client.get(f"/cases/{case_id}/integrity", headers=_other_office(client)).status_code == 404
    with SignedOut(client) as anonymous:
        assert anonymous.get(f"/cases/{case_id}/integrity").status_code == 401
    assert client.get("/cases/00000000-0000-0000-0000-000000000000/integrity").status_code == 404


# Revoking a signing link


def test_revoking_the_link_kills_the_token_and_hands_the_case_back(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready_101(client, tmp_path)
    token = _token(client, case_id)
    view = client.get("/portal", headers=_auth(token))
    assert view.status_code == 200, view.text
    assert client.get(f"/cases/{case_id}/signing-link").json()["state"] == "open"

    revoked = client.post(f"/cases/{case_id}/revoke-link")
    assert revoked.status_code == 200, revoked.text
    body = revoked.json()
    assert set(client.get(f"/cases/{case_id}").json()) == set(body)
    assert body["case"]["id"] == case_id
    assert body["case"]["status"] == "filling"
    assert body["ready_to_sign"] is True

    # The token is dead everywhere the signer could use it.
    assert client.get("/portal", headers=_auth(token)).status_code in {404, 409, 410}
    assert client.get("/portal/preview", headers=_auth(token)).status_code in {404, 409, 410}
    signing = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG_B64, "review_digest": view.json()["review_digest"], "consent": True},
    )
    assert signing.status_code in {404, 409, 410}, signing.text
    assert client.get(f"/cases/{case_id}").json()["case"]["status"] == "filling"
    assert client.get(f"/cases/{case_id}/signing-link").json()["state"] == "unavailable"

    record = next(event for event in _timeline(client, case_id) if event["action"] == "signing_link_revoked")
    staff = client.get("/auth/me").json()
    assert record["actor"] == f"user:{staff['id']}"
    assert record["metadata"]["revoked_links"] == 1
    assert record["metadata"]["revoke_reason"] == "office"
    assert record["metadata"]["status"] == "filling"

    # Nothing left to revoke.
    assert client.post(f"/cases/{case_id}/revoke-link").status_code == 404

    # The clerk corrects a detail and sends a new link; the old token stays dead.
    assert _set(client, case_id, "phone", "0529876543")["field_values"]["phone"] == "0529876543"
    fresh = _token(client, case_id)
    assert fresh != token
    assert client.get("/portal", headers=_auth(fresh)).status_code == 200
    assert client.get("/portal", headers=_auth(token)).status_code in {404, 409, 410}


def test_a_signed_case_another_office_and_a_stranger_cannot_revoke(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready_101(client, tmp_path)
    token = _token(client, case_id)

    headers = _other_office(client)
    assert client.post(f"/cases/{case_id}/revoke-link", headers=headers).status_code == 404
    with SignedOut(client) as anonymous:
        assert anonymous.post(f"/cases/{case_id}/revoke-link").status_code == 401
    assert client.get("/portal", headers=_auth(token)).status_code == 200

    # Once the client has signed, the seal stands: nothing is revoked and nothing changes.
    view = client.get("/portal", headers=_auth(token)).json()
    signed = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG_B64, "review_digest": view["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text
    before = client.get(f"/cases/{case_id}").json()
    refused = client.post(f"/cases/{case_id}/revoke-link")
    assert refused.status_code == 409, refused.text
    assert client.get(f"/cases/{case_id}").json() == before
    assert before["case"]["status"] == "signed"
    assert client.get("/portal/signed-document", headers=_auth(token)).status_code == 200

    # A case with no link at all has nothing to revoke.
    assert client.post(f"/cases/{_new(client, 'bl_6101')}/revoke-link").status_code == 404


# The audit center


def test_the_audit_center_lists_the_offices_events_with_counters_and_filters(
    client: TestClient, tmp_path: Path
) -> None:
    empty = _audit(client)
    assert empty["events"] == [] and empty["total_events"] == 0 and empty["matched_events"] == 0

    first = _ready_101(client, tmp_path)
    _token(client, first)
    assert client.post(f"/cases/{first}/revoke-link").status_code == 200
    assert client.post(f"/cases/{first}/fill-and-sign", json=_sign_body()).status_code == 200
    quick = client.post("/clients/quick-case", json={"source_case_id": first, "process_type": "real_estate"})
    assert quick.status_code == 201, quick.text
    second = quick.json()["case"]["id"]
    yossi = _new(client, "bl_6101", "יוסי לוי")
    assert _drop(client, yossi, _everyday(tmp_path)).status_code == 200

    center = _audit(client)
    assert set(center) == {
        "total_events",
        "signed_count",
        "smart_uploads_count",
        "vault_reuses_count",
        "revocations_count",
        "action_counts",
        "matched_events",
        "events",
    }
    assert (center["signed_count"], center["smart_uploads_count"]) == (1, 2)
    assert (center["vault_reuses_count"], center["revocations_count"]) == (1, 1)
    assert center["total_events"] == sum(center["action_counts"].values()) == center["matched_events"]
    assert center["total_events"] == len(center["events"])
    for event in center["events"]:
        assert set(event) == {
            "event_id",
            "case_id",
            "client_name",
            "case_name",
            "process_type",
            "action",
            "actor",
            "created_at",
            "metadata",
        }
    stamps = [event["created_at"] for event in center["events"]]
    assert stamps == sorted(stamps, reverse=True)
    assert {event["case_id"] for event in center["events"]} == {first, second, yossi}
    by_case = {event["case_id"]: event for event in center["events"]}
    assert (by_case[first]["client_name"], by_case[first]["process_type"]) == (_DANA, "employee_onboarding")
    assert by_case[second]["process_type"] == "real_estate"
    assert by_case[yossi]["client_name"] == "יוסי לוי"
    # The trail carries identifiers and counts, never what was typed or read.
    assert _ID not in str(center) and "0501234567" not in str(center) and "456789" not in str(center)

    # Filter by action.
    uploads = _audit(client, action="smart_upload_completed")
    assert [event["action"] for event in uploads["events"]] == ["smart_upload_completed"] * 2
    assert [event["case_id"] for event in uploads["events"]] == [yossi, first]
    assert uploads["matched_events"] == 2 and uploads["total_events"] == center["total_events"]
    assert [item["filename"] for item in uploads["events"][0]["metadata"]["routed_files"]] == [
        "id.pdf",
        "arnona.pdf",
        "bank.pdf",
    ]
    revocations = _audit(client, action="signing_link_revoked")
    assert [event["case_id"] for event in revocations["events"]] == [first]
    assert revocations["events"][0]["metadata"]["revoked_links"] == 1
    reuse = _audit(client, action="client_vault_reused")["events"]
    assert [event["case_id"] for event in reuse] == [second]
    assert reuse[0]["metadata"]["source_case_id"] == first
    assert client.get("/audit", params={"action": "no_such_action"}).status_code == 400

    # Search by client, by process, by action name; narrow with both; cap the page.
    assert {event["case_id"] for event in _audit(client, q="יוסי")["events"]} == {yossi}
    assert {event["case_id"] for event in _audit(client, q="real_estate")["events"]} == {second}
    assert {event["action"] for event in _audit(client, q="revoked")["events"]} == {"signing_link_revoked"}
    both = _audit(client, q="דנה", action="smart_upload_completed")
    assert [event["case_id"] for event in both["events"]] == [first]
    assert _audit(client, q="אין כזה לקוח")["events"] == []
    # A wildcard typed into the search is just a character.
    assert _audit(client, q="%")["events"] == []
    capped = _audit(client, limit=1)
    assert len(capped["events"]) == 1 and capped["matched_events"] == center["total_events"]
    assert capped["events"][0] == center["events"][0]
    assert client.get("/audit", params={"limit": 0}).status_code == 422


def test_the_audit_center_never_shows_another_offices_events(client: TestClient, tmp_path: Path) -> None:
    mine = _new(client, "bl_6101")
    assert _drop(client, mine, _everyday(tmp_path)).status_code == 200
    headers = _other_office(client)

    theirs = _audit(client, headers)
    assert theirs["events"] == [] and theirs["total_events"] == 0 and theirs["action_counts"] == {}
    assert _audit(client, headers, q=_DANA)["events"] == []
    assert _audit(client, headers, action="smart_upload_completed")["matched_events"] == 0

    own = _new(client, "bl_6101", "לקוח אחר", headers)
    assert _drop(client, own, _everyday(tmp_path), headers).status_code == 200
    theirs = _audit(client, headers)
    assert {event["case_id"] for event in theirs["events"]} == {own}
    assert theirs["smart_uploads_count"] == 1
    ours = _audit(client)
    assert {event["case_id"] for event in ours["events"]} == {mine}
    assert ours["smart_uploads_count"] == 1
    assert {event["event_id"] for event in ours["events"]}.isdisjoint(event["event_id"] for event in theirs["events"])

    with SignedOut(client) as anonymous:
        assert anonymous.get("/audit").status_code == 401
