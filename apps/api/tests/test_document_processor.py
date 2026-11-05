from pathlib import Path

import pytest

pytest.importorskip("fitz")

import pymupdf

from app.core.exceptions import ProcessingError
from app.services.document_processor import TEXT_CHARS_PER_PAGE, DocumentProcessor


def _save(path: Path, pages: list[str]) -> None:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_selectable_text_skips_vision(tmp_path: Path) -> None:
    path = tmp_path / "digital.pdf"
    _save(path, ["Declaration of the undersigned party. " * 8])
    result = DocumentProcessor(max_vision_pages=2)._extract_sync(path)
    assert result.images == []
    assert result.searchable is True
    assert len(result.text) > TEXT_CHARS_PER_PAGE


def test_sparse_page_renders_jpeg_near_170_dpi(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    _save(path, ["ID"])
    result = DocumentProcessor(max_vision_pages=2)._extract_sync(path)
    assert len(result.images) == 1
    assert result.images[0].mime_type == "image/jpeg"
    assert result.images[0].data.startswith(b"\xff\xd8")
    pixmap = pymupdf.Pixmap(result.images[0].data)
    assert 1200 < pixmap.width < 1700


def test_only_sparse_pages_are_rendered(tmp_path: Path) -> None:
    path = tmp_path / "mixed.pdf"
    _save(path, ["Section heading and boilerplate agreement text. " * 6, ""])
    result = DocumentProcessor(max_vision_pages=2)._extract_sync(path)
    assert result.page_count == 2
    assert len(result.images) == 1


def test_password_protected_pdf_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "locked.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="user-secret",
        owner_pw="owner-secret",
    )
    document.close()
    with pytest.raises(ProcessingError, match="password-protected"):
        DocumentProcessor()._extract_sync(path)


def test_unreadable_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"")
    with pytest.raises(ProcessingError, match="could not be read"):
        DocumentProcessor()._extract_sync(path)
