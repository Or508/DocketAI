from dataclasses import dataclass
from pathlib import Path

import fitz

from app.core.exceptions import ProcessingError
from app.domain.text_layout import clean_text

TEXT_CHARS_PER_PAGE = 100
VISION_DPI = 170


@dataclass(frozen=True)
class PageImage:
    mime_type: str
    data: bytes


@dataclass(frozen=True)
class ExtractionResult:
    page_count: int
    text: str
    images: list[PageImage]
    searchable: bool


class DocumentProcessor:
    """Send selectable text to the classifier, and render only sparse pages."""

    def __init__(self, max_vision_pages: int = 2) -> None:
        self._max_vision_pages = max_vision_pages

    async def extract(self, path: Path) -> ExtractionResult:
        import asyncio

        return await asyncio.to_thread(self._extract_sync, path)

    def _extract_sync(self, path: Path) -> ExtractionResult:
        try:
            document = fitz.open(path)
        except Exception as exc:
            raise ProcessingError("This file could not be read. It may be damaged.") from exc

        try:
            if getattr(document, "needs_pass", 0):
                raise ProcessingError(
                    "This PDF is password-protected. Remove the password and upload it again."
                )
            if getattr(document, "is_encrypted", False) and not document.authenticate(""):
                raise ProcessingError(
                    "This PDF is password-protected. Remove the password and upload it again."
                )
            if document.page_count < 1:
                raise ProcessingError("This file has no pages.")

            parts: list[str] = []
            sparse: list[int] = []
            for index, page in enumerate(document):
                text = clean_text(page.get_text("text") or "")
                parts.append(text)
                if len(text) <= TEXT_CHARS_PER_PAGE:
                    sparse.append(index)

            zoom = VISION_DPI / 72
            matrix = fitz.Matrix(zoom, zoom)
            images: list[PageImage] = []
            for index in sparse[: self._max_vision_pages]:
                pixmap = document[index].get_pixmap(matrix=matrix, alpha=False)
                images.append(PageImage("image/jpeg", pixmap.tobytes("jpeg", jpg_quality=80)))

            return ExtractionResult(
                page_count=document.page_count,
                text=clean_text("\n\n".join(parts))[:50_000],
                images=images,
                searchable=not images,
            )
        finally:
            document.close()
