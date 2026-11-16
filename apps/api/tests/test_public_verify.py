import hashlib
from pathlib import Path
from uuid import UUID

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("reportlab")

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import session_scope
from app.models.case import Case
from app.services.verify_service import mask_name, normalize_code
from tests.support import SignedOut, authenticate
from tests.test_portal import _ANSWERS, _PNG, _auth, _ready, _token

_SIGN = {"signature_png_base64": _PNG, "field_values": {}, "consent": True}
_FIELDS = {
    "valid",
    "status",
    "verification_id",
    "process_type",
    "masked_client_name",
    "signed_at",
    "signed_pdf_sha256",
    "hash_matches",
}
_CLIENT = "אור יוסף"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
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


def _name(client: TestClient, case_id: str, name: str) -> None:
    async def rename() -> None:
        async with session_scope() as session:
            case = await session.get(Case, UUID(case_id))
            assert case is not None
            case.client_name = name
            await session.commit()

    client.portal.call(rename)


def _signed(client: TestClient, tmp_path: Path) -> tuple[str, dict, bytes]:
    case_id, _ = _ready(client, tmp_path)
    _name(client, case_id, _CLIENT)
    signed = client.post(f"/cases/{case_id}/fill-and-sign", json=_SIGN)
    assert signed.status_code == 200, signed.text
    pdf = client.get(f"/cases/{case_id}/signed-document").content
    return case_id, signed.json()["case"]["audit"], pdf


def _public(client: TestClient) -> SignedOut:
    """A caller with no office session and no signing link."""
    return SignedOut(client)


def test_a_valid_seal_is_confirmed_to_anyone_without_personal_details(client: TestClient, tmp_path: Path) -> None:
    case_id, seal, pdf = _signed(client, tmp_path)
    code = seal["signer_verification_id"]
    assert code.startswith("DV-")

    with _public(client) as anonymous:
        response = anonymous.get(f"/verify/{code}")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == _FIELDS
    assert body["valid"] is True
    assert body["status"] == "valid"
    assert body["verification_id"] == code
    assert body["process_type"] == "onboarding"
    assert body["masked_client_name"] == "אור י."
    assert body["signed_at"][:19] == seal["signed_at"][:19]
    assert body["signed_pdf_sha256"] == seal["file_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert body["hash_matches"] is None

    # Nothing personal, and nothing that points at the case or the office.
    workspace = client.get(f"/cases/{case_id}").json()
    banned = [case_id, case_id.replace("-", ""), _CLIENT, "יוסף", workspace["case"]["name"], *_ANSWERS]
    banned += [str(value) for value in workspace["field_values"].values() if len(str(value)) > 3]
    for secret in banned:
        assert secret not in response.text


def test_the_code_is_case_insensitive_and_unknown_codes_are_not_found(client: TestClient, tmp_path: Path) -> None:
    _case_id, seal, _pdf = _signed(client, tmp_path)
    code = seal["signer_verification_id"]
    with _public(client) as anonymous:
        lowered = anonymous.get(f"/verify/{code.lower()}")
        assert lowered.status_code == 200, lowered.text
        assert lowered.json()["verification_id"] == code
        assert anonymous.get(f"/verify/%20{code.lower()}%20").status_code == 200

        missing = anonymous.get("/verify/DV-000000000000")
        assert missing.status_code == 404
        for junk in ("nonsense", "DV-", code[:-1], code + "0", "DV-%25", "' OR 1=1 --"):
            refused = anonymous.get(f"/verify/{junk}")
            assert refused.status_code == 404, junk
            assert refused.json() == missing.json()


def test_a_file_hash_is_compared_against_the_seal(client: TestClient, tmp_path: Path) -> None:
    _case_id, seal, pdf = _signed(client, tmp_path)
    code = seal["signer_verification_id"]
    digest = hashlib.sha256(pdf).hexdigest()
    with _public(client) as anonymous:
        same = anonymous.get(f"/verify/{code}", params={"sha256": digest})
        assert same.status_code == 200, same.text
        assert same.json()["hash_matches"] is True
        assert same.json()["valid"] is True
        assert anonymous.get(f"/verify/{code}", params={"sha256": digest.upper()}).json()["hash_matches"] is True

        altered = hashlib.sha256(pdf + b"\n").hexdigest()
        other = anonymous.get(f"/verify/{code}", params={"sha256": altered})
        assert other.status_code == 200, other.text
        # The seal itself is still good; it is this file that is not the signed one.
        assert other.json()["valid"] is True
        assert other.json()["hash_matches"] is False
        assert other.json()["signed_pdf_sha256"] == digest

        for bad in ("abc", "z" * 64, digest + "0"):
            assert anonymous.get(f"/verify/{code}", params={"sha256": bad}).status_code == 422
        # A hash never rescues an unknown code.
        assert anonymous.get("/verify/DV-000000000000", params={"sha256": digest}).status_code == 404


def test_a_reopened_case_reports_its_old_seal_as_superseded(client: TestClient, tmp_path: Path) -> None:
    case_id, seal, pdf = _signed(client, tmp_path)
    old = seal["signer_verification_id"]
    digest = hashlib.sha256(pdf).hexdigest()
    assert client.post(f"/cases/{case_id}/reopen").status_code == 200

    with _public(client) as anonymous:
        response = anonymous.get(f"/verify/{old}", params={"sha256": digest})
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == _FIELDS
        assert body["valid"] is False
        assert body["status"] == "superseded"
        assert body["verification_id"] == old
        assert body["masked_client_name"] == "אור י."
        # The file is still recognised as the one that was signed under this code.
        assert body["signed_pdf_sha256"] == digest
        assert body["hash_matches"] is True
        assert body["signed_at"][:16] == seal["signed_at"][:16]

        # Signed again: a new seal is valid, and the old one stays superseded.
        resigned = client.post(f"/cases/{case_id}/fill-and-sign", json=_SIGN)
        assert resigned.status_code == 200, resigned.text
        fresh = resigned.json()["case"]["audit"]
        assert fresh["signer_verification_id"] != old
        current = anonymous.get(f"/verify/{fresh['signer_verification_id']}", params={"sha256": digest}).json()
        assert current["valid"] is True
        assert current["status"] == "valid"
        assert current["signed_pdf_sha256"] == fresh["file_sha256"]
        assert current["hash_matches"] is False
        stale = anonymous.get(f"/verify/{old}").json()
        assert stale["valid"] is False
        assert stale["status"] == "superseded"
        assert stale["signed_pdf_sha256"] == digest


def test_a_seal_made_through_a_signing_link_verifies_and_an_edit_supersedes_it(
    client: TestClient, tmp_path: Path
) -> None:
    case_id, _ = _ready(client, tmp_path)
    link = client.post(f"/cases/{case_id}/signing-links")
    token = _token(link.json()["url"])
    view = client.get("/portal", headers=_auth(token)).json()
    signed = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG, "review_digest": view["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text
    seal = client.get(f"/cases/{case_id}").json()["case"]["audit"]
    code = seal["signer_verification_id"]
    with _public(client) as anonymous:
        body = anonymous.get(f"/verify/{code}").json()
        assert body["valid"] is True
        assert body["masked_client_name"] == "D."
        assert body["signed_pdf_sha256"] == seal["file_sha256"]

        # Editing a signed case drops its signature, which supersedes the seal too.
        edited = client.post(f"/cases/{case_id}/fields", json={"key": "full_name", "value": "Dana Levi"})
        assert edited.status_code == 200, edited.text
        if edited.json()["case"]["status"] != "signed":
            after = anonymous.get(f"/verify/{code}").json()
            assert after["valid"] is False
            assert after["status"] == "superseded"
            assert "Levi" not in str(after)


def test_a_signed_file_finds_its_own_seal_without_a_code(client: TestClient, tmp_path: Path) -> None:
    case_id, seal, pdf = _signed(client, tmp_path)
    digest = hashlib.sha256(pdf).hexdigest()
    with _public(client) as anonymous:
        found = anonymous.get(f"/verify/by-hash/{digest.upper()}")
        assert found.status_code == 200, found.text
        assert found.headers["cache-control"] == "no-store"
        body = found.json()
        assert set(body) == _FIELDS
        assert body["valid"] is True
        assert body["verification_id"] == seal["signer_verification_id"]
        assert body["signed_pdf_sha256"] == digest
        assert body["hash_matches"] is True
        assert case_id not in found.text

        altered = hashlib.sha256(pdf + b"\n").hexdigest()
        assert anonymous.get(f"/verify/by-hash/{altered}").status_code == 404
        assert anonymous.get("/verify/by-hash/abc").status_code == 422

        assert client.post(f"/cases/{case_id}/reopen").status_code == 200
        stale = anonymous.get(f"/verify/by-hash/{digest}").json()
        assert stale["valid"] is False
        assert stale["status"] == "superseded"
        assert stale["hash_matches"] is True


def test_names_are_masked_and_codes_normalised() -> None:
    assert mask_name("אור יוסף") == "אור י."
    assert mask_name("  Dana   Rachel  Cohen ") == "Dana C."
    assert mask_name("Dana") == "D."
    assert mask_name("") == ""
    assert mask_name(None) == ""
    assert normalize_code(" dv-2b135505283c ") == "DV-2B135505283C"
    assert normalize_code("DV-2B135505283") is None
    assert normalize_code("DK-2B135505283C") is None
    assert normalize_code("DV-2B135505283G") is None
