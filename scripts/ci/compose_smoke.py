"""Exercise a running DocketAI API with the committed sample PDF.

The password is read from DOCKET_USER_PASSWORD and is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample.pdf"
DEADLINE_SECONDS = 180


def _request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> tuple[int, bytes]:
    prepared = dict(headers or {})
    if token:
        prepared["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=prepared, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _json(status: int, body: bytes, expected: int) -> dict:
    if status != expected:
        print(f"HTTP {status}, expected {expected}.", file=sys.stderr)
        raise SystemExit(1)
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        print("Expected a JSON object.", file=sys.stderr)
        raise SystemExit(1)
    return payload


def _multipart(filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = f"----docketci{uuid.uuid4().hex}"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return head + content + tail, f"multipart/form-data; boundary={boundary}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a running DocketAI API.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = os.environ.get("DOCKET_USER_PASSWORD", "")
    if len(password) < 12:
        print("DOCKET_USER_PASSWORD is missing.", file=sys.stderr)
        return 1
    sample = FIXTURE.read_bytes()
    if not sample.startswith(b"%PDF") or len(sample) >= 5_000:
        print("The sample PDF is missing or larger than 5 KB.", file=sys.stderr)
        return 1

    base = args.base.rstrip("/")
    status, body = _request(
        "POST",
        f"{base}/auth/login",
        data=json.dumps({"email": args.email, "password": password}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    login = _json(status, body, 200)
    token = login.get("token")
    if not isinstance(token, str) or token == "":
        print("Login did not return a token.", file=sys.stderr)
        return 1

    status, body = _request("GET", f"{base}/health", token=token)
    health = _json(status, body, 200)
    if health.get("status") != "ok" or health.get("database") != "ok" or health.get("storage") != "ok":
        print("Health check is not ok.", file=sys.stderr)
        return 1

    status, body = _request(
        "POST",
        f"{base}/cases",
        token=token,
        data=json.dumps({"name": "CI sample", "process_key": "onboarding"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    created = _json(status, body, 201)
    case_id = created.get("id")
    if not isinstance(case_id, str):
        print("Case creation did not return an id.", file=sys.stderr)
        return 1

    payload, content_type = _multipart("sample.pdf", sample)
    status, body = _request(
        "POST",
        f"{base}/cases/{case_id}/upload",
        token=token,
        data=payload,
        headers={"Content-Type": content_type},
    )
    uploaded = _json(status, body, 200)
    if uploaded.get("rejected") or "sample.pdf" not in (uploaded.get("accepted_filenames") or []):
        print("The sample PDF was not accepted.", file=sys.stderr)
        return 1

    deadline = time.monotonic() + DEADLINE_SECONDS
    gap: dict | None = None
    while time.monotonic() < deadline:
        status, body = _request("GET", f"{base}/cases/{case_id}/status", token=token)
        gap = _json(status, body, 200)
        in_progress = gap.get("in_progress") or []
        if not in_progress and gap.get("status") != "processing":
            break
        time.sleep(2)
    else:
        print("Processing did not finish before the deadline.", file=sys.stderr)
        return 1

    assert gap is not None
    if gap.get("status") == "failed":
        print("Case processing failed.", file=sys.stderr)
        return 1
    unrecognized = gap.get("unrecognized") or []
    match = next((item for item in unrecognized if item.get("filename") == "sample.pdf"), None)
    if match is None:
        print("The sample was not left unrecognized, which is the no-AI result.", file=sys.stderr)
        return 1
    document_id = match.get("document_id")
    status, downloaded = _request(
        "GET",
        f"{base}/cases/{case_id}/documents/{document_id}/file",
        token=token,
    )
    if status != 200:
        print(f"Document download returned HTTP {status}.", file=sys.stderr)
        return 1
    if downloaded != sample:
        print("Downloaded bytes do not match the fixture.", file=sys.stderr)
        return 1
    print(f"Smoke check passed for case {case_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
