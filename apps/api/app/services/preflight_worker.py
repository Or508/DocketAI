"""Bounded PDF and image check. Run as python -m app.services.preflight_worker <path> <mime>.

Limits come from the environment the parent process builds. This module does not
read Settings, and it prints exactly one JSON line.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_JS = re.compile(r"/JS(?![A-Za-z])")


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, separators=(",", ":")), flush=True)


def _limit(name: str) -> int:
    return int(os.environ[name])


def _reject_javascript() -> bool:
    return os.environ.get("PREFLIGHT_REJECT_PDF_JAVASCRIPT", "true").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _keyword(definition: str, *, reject_javascript: bool) -> str | None:
    if re.search(r"/Launch(?![A-Za-z])", definition):
        return "launch_action"
    if re.search(r"/RichMedia(?![A-Za-z])", definition):
        return "rich_media"
    if re.search(r"/EmbeddedFile(?![A-Za-z])", definition):
        return "embedded_file"
    if reject_javascript and (
        re.search(r"/JavaScript(?![A-Za-z])", definition) or _JS.search(definition)
    ):
        return "javascript"
    return None


def _check_pdf(path: Path) -> tuple[str | None, int]:
    import fitz

    document = fitz.open(path)
    try:
        if document.needs_pass or document.is_encrypted:
            return "encrypted", 0
        pages = document.page_count
        max_pages = _limit("PREFLIGHT_MAX_PAGES")
        if pages < 1:
            return "unreadable", 0
        if pages > max_pages:
            return "too_many_pages", pages
        max_points = _limit("PREFLIGHT_MAX_PAGE_INCHES") * 72
        for page in document:
            rect = page.rect
            if rect.width > max_points or rect.height > max_points:
                return "page_too_large", pages
        cap = _limit("PREFLIGHT_MAX_DECOMPRESSED_MB") * 1024 * 1024
        total = 0
        count = document.xref_length()
        for xref in range(1, count):
            if not document.xref_is_stream(xref):
                continue
            total += len(document.xref_stream(xref))
            if total > cap:
                return "too_large_decompressed", pages
        if document.embfile_count() > 0:
            return "embedded_file", pages
        reject_javascript = _reject_javascript()
        for xref in range(1, count):
            reason = _keyword(document.xref_object(xref), reject_javascript=reject_javascript)
            if reason is not None:
                return reason, pages
        return None, pages
    finally:
        document.close()


def _check_image(path: Path) -> tuple[str | None, int]:
    # Pillow reads dimensions from the header without decoding pixels. A page
    # rect is in points, which depend on the DPI tag, so it cannot bound pixels.
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    pixel_cap = _limit("PREFLIGHT_MAX_IMAGE_PIXELS")
    max_pages = _limit("PREFLIGHT_MAX_PAGES")
    with Image.open(path) as image:
        frames = int(getattr(image, "n_frames", 1) or 1)
        if frames < 1:
            return "unreadable", 0
        if frames > max_pages:
            return "too_many_pages", frames
        for index in range(frames):
            if index:
                image.seek(index)
            width, height = image.size
            if width < 1 or height < 1:
                return "unreadable", frames
            if width * height > pixel_cap:
                return "image_too_large", frames
    return None, frames


def _apply_limits() -> None:
    # Set in the child itself: preexec_fn is unsafe in a threaded parent.
    if os.name != "posix":
        return
    import resource

    memory = _limit("PREFLIGHT_MEMORY_MB") * 1024 * 1024
    cpu = _limit("PREFLIGHT_CPU_SECONDS")
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))


def main() -> int:
    if len(sys.argv) != 3:
        _emit({"ok": False, "reason": "unreadable"})
        return 0
    path = Path(sys.argv[1])
    mime = sys.argv[2]
    try:
        _apply_limits()
        if mime == "application/pdf":
            reason, pages = _check_pdf(path)
        elif mime.startswith("image/"):
            reason, pages = _check_image(path)
        else:
            reason, pages = "unreadable", 0
    except Exception:
        _emit({"ok": False, "reason": "unreadable"})
        return 0
    if reason is None:
        _emit({"ok": True, "pages": pages})
    else:
        _emit({"ok": False, "reason": reason})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
