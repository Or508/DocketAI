"""The downloadable sample documents fill every Form 101 detail they carry, through the real reader."""

import importlib.util
import sys
from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")

from app.catalog.processes import PROCESSES
from app.domain.slot_reading import read_document
from app.schemas.process import DocumentTypeSpec, FieldSpec
from app.services.document_processor import clean_text

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_documents.py"
_PUBLISHED = Path(__file__).resolve().parents[2] / "web" / "public" / "demo"
_TYPES = {"01-teudat-zehut.pdf": "id_copy", "02-arnona.pdf": "proof_of_address", "03-ishur-bank.pdf": "bank_confirmation"}


def _module():
    spec = importlib.util.spec_from_file_location("demo_documents", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # A dataclass looks its module up by name while it is being built.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read(data: bytes, type_key: str) -> dict[str, str]:
    seed = next(process for process in PROCESSES if process.key == "employee_onboarding")
    fields = [FieldSpec.model_validate(item) for item in seed.required_fields]
    spec = next(DocumentTypeSpec.model_validate(item) for item in seed.required_documents if item["type_key"] == type_key)
    with pymupdf.open(stream=data, filetype="pdf") as document:
        text = clean_text(document[0].get_text("text"))
    outcome = read_document(spec.reading, text, fields, set())
    assert outcome.blocked is None
    return {item.slot_key: item.value for item in outcome.proposals if item.value}


def test_each_sample_fills_its_details() -> None:
    demo = _module()
    found: dict[str, str] = {}
    for sample in demo.SAMPLES:
        found.update(_read(demo.build(sample), _TYPES[sample.filename]))
    assert found == {key: demo.PERSON[key] for key in found}
    assert set(found) == set(demo.PERSON)


def test_the_published_files_match_the_script() -> None:
    demo = _module()
    for sample in demo.SAMPLES:
        published = _PUBLISHED / sample.filename
        assert published.exists(), f"Run scripts/demo_documents.py: {published.name} is missing"
        assert _read(published.read_bytes(), _TYPES[sample.filename]) == _read(demo.build(sample), _TYPES[sample.filename])


def test_every_sample_says_it_is_invented() -> None:
    demo = _module()
    for sample in demo.SAMPLES:
        with pymupdf.open(stream=demo.build(sample), filetype="pdf") as document:
            assert "כל הפרטים בדויים" in document[0].get_text("text")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("aiosqlite")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from tests.support import authenticate

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("FORM_101_TEMPLATE_PATH", str(tmp_path / "server" / "form_101.pdf"))
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


def test_the_dashboard_demo_case_fills_the_form_with_no_ai(client) -> None:
    """The "תיק לדוגמה" button: open the case, load Form 101, upload each sample with its drawer."""
    demo = _module()
    created = client.post(
        "/cases",
        json={"name": "טופס 101 — דוגמה", "process_key": "employee_onboarding", "client_name": "דנה כהן (דוגמה)"},
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    assert client.post(f"/cases/{case_id}/load-default-form").status_code == 200
    for name, type_key in _TYPES.items():
        uploaded = client.post(
            f"/cases/{case_id}/upload",
            files=[("files", (name, (_PUBLISHED / name).read_bytes(), "application/pdf"))],
            data={"document_type": type_key},
        )
        assert uploaded.status_code == 200, uploaded.text
    workspace = client.get(f"/cases/{case_id}").json()
    assert workspace["gap"]["unrecognized"] == []
    assert {item["document_type"] for item in workspace["gap"]["identified"]} == set(_TYPES.values())
    values = workspace["field_values"]
    assert {key: values.get(key) for key in demo.PERSON} == demo.PERSON
