import base64
import struct
import zlib
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("reportlab")
pytest.importorskip("pypdf")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from tests.test_certificate import _PNG, _ready, client


def _png(width: int, height: int, *, mark: bool) -> str:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(b"\x00\x00\x00" if mark and x == 0 and y == 0 else b"\xff\xff\xff")
    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows)))
        + chunk(b"IEND", b"")
    )
    return base64.b64encode(data).decode()


def _portal(client: TestClient, case_id: str) -> dict[str, str]:
    created = client.post(f"/cases/{case_id}/signing-links")
    assert created.status_code == 201, created.text
    token = created.json()["url"].rstrip("/").rsplit("/", 1)[-1]
    headers = {"Authorization": f"Bearer {token}"}
    view = client.get("/portal", headers=headers)
    assert view.status_code == 200, view.text
    headers["digest"] = view.json()["review_digest"]
    return headers


def _reject(response, message: str) -> None:
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == message
    assert "4000" not in response.text
    assert "\\" not in response.json()["detail"]
    assert "Traceback" not in response.text


def test_office_rejects_bad_signatures_and_accepts_a_normal_one(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="CI sample", client_name="CI")
    oversized = _png(4001, 20, mark=True)
    tiny = _png(10, 10, mark=True)
    blank = _png(50, 20, mark=False)
    for payload, message in (
        (oversized, "The signature image is not an accepted size."),
        (tiny, "The signature image is not an accepted size."),
        (blank, "The signature is empty."),
    ):
        response = client.post(
            f"/cases/{case_id}/fill-and-sign",
            json={"signature_png_base64": payload, "field_values": {}, "consent": True},
        )
        _reject(response, message)
    assert client.get(f"/cases/{case_id}").json()["case"]["status"] != "signed"
    signed = client.post(
        f"/cases/{case_id}/fill-and-sign",
        json={"signature_png_base64": _PNG, "field_values": {}, "consent": True},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["case"]["status"] == "signed"


def test_portal_rejects_bad_signatures_and_accepts_a_normal_one(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="CI sample", client_name="CI")
    headers = _portal(client, case_id)
    digest = headers.pop("digest")
    auth = {"Authorization": headers["Authorization"]}
    for payload, message in (
        (_png(4001, 20, mark=True), "The signature image is not an accepted size."),
        (_png(49, 20, mark=True), "The signature image is not an accepted size."),
        (_png(50, 20, mark=False), "The signature is empty."),
    ):
        response = client.post(
            "/portal/sign",
            headers=auth,
            json={"signature_png_base64": payload, "review_digest": digest, "consent": True},
        )
        _reject(response, message)
    signed = client.post(
        "/portal/sign",
        headers=auth,
        json={"signature_png_base64": _PNG, "review_digest": digest, "consent": True},
    )
    assert signed.status_code == 200, signed.text
