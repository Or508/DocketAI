import base64
import re
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("reportlab")
pytest.importorskip("pypdf")

import pymupdf
from pypdf import PdfReader

from app.catalog.processes import PROCESSES
from app.services.pdf_filler import PdfFillerService
from app.services.template_factory import TemplateFactory

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_templates_and_hebrew_field_roundtrip(tmp_path: Path) -> None:
    factory = TemplateFactory(tmp_path, None)
    factory.ensure_templates(PROCESSES)
    onboarding = next(process for process in PROCESSES if process.key == "onboarding")
    template = tmp_path / onboarding.template_filename
    fields = set((PdfReader(str(template)).get_fields() or {}))
    for spec in onboarding.required_fields:
        assert spec["pdf_field_name"] in fields

    output = tmp_path / "signed.pdf"
    values = {spec["pdf_field_name"]: "Dana Cohen" for spec in onboarding.required_fields}
    values["address_he"] = "רחוב הרצל 12"
    artifact = PdfFillerService(None).fill_and_sign(
        template_path=template,
        output_path=output,
        values=values,
        signature_png=_PNG,
        signature_rect=list(onboarding.layout["signature_rect"]),
        page_index=0,
        rtl_fields={"address_he"},
        case_id="11111111-1111-1111-1111-111111111111",
    )
    assert artifact.signer_verification_id.startswith("DV-")
    assert len(artifact.content_sha256) == 64
    assert PdfReader(str(output)).get_fields() in (None, {})
    document = pymupdf.open(output)
    text = "\n".join(page.get_text() for page in document)
    widgets = list(document[0].widgets() or [])
    document.close()
    assert widgets == []
    assert "Dana Cohen" in text
    assert any("\u0590" <= character <= "\u05FF" for character in text)
    assert "11111111-1111-1111-1111-111111111111" in text
    assert "UTC" in text
    assert "Israel" in text
    assert f"SHA-256 {artifact.content_sha256}" in text
    assert artifact.signer_verification_id in text
    assert re.search(r"[0-9a-f]{64}", text)
    assert output.stat().st_size > template.stat().st_size
