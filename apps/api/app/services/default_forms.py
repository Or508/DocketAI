"""The blank form each process can load onto a case with one click."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.services.fonts import resolve_hebrew_font
from app.services.form101 import FORM_101_VERSION, build_form_101, build_onboarding_form_101
from app.services.real_estate_form import REAL_ESTATE_FORM_VERSION, build_real_estate_form

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DefaultForm:
    path: Path
    # The name the file takes on the case.
    filename: str
    title: str
    # What to tell the office when the file is not there.
    missing: str


def default_form(process_key: str, settings: Settings) -> DefaultForm | None:
    """The blank for this process, or None when the process has none to offer.

    The path may not exist: BL/6101 is an official file the office supplies. Form 101
    is drawn here when the office has not put its own copy in place, so it always exists.
    Both onboarding processes load a Form 101, each drawn with its own slots.
    """
    if process_key == "bl_6101":
        return DefaultForm(
            path=settings.resolved_bl_6101_template,
            filename="bl_6101_official.pdf",
            title="BL/6101",
            missing=(
                "The official BL/6101 form is not on this server. "
                "Set BL_6101_TEMPLATE_PATH to the blank PDF, or upload the form."
            ),
        )
    if process_key in _FORM_101:
        supplied = settings.resolved_form_101_template
        return DefaultForm(
            path=supplied if supplied.is_file() else _drawn_form_101(settings, process_key),
            filename="form_101_official.pdf",
            title="Form 101",
            missing="Form 101 could not be prepared on this server. Upload the form instead.",
        )
    if process_key == "real_estate":
        supplied = settings.resolved_real_estate_template
        return DefaultForm(
            path=supplied if supplied.is_file() else _drawn(settings, *_REAL_ESTATE),
            filename="real_estate_official.pdf",
            title="real estate",
            missing="The real estate form could not be prepared on this server. Upload the form instead.",
        )
    return None


# Each Form 101 process has its own slots, so each gets its own drawing: (file stem, builder).
_FORM_101 = {
    "employee_onboarding": ("form-101-blank", build_form_101),
    "onboarding": ("form-101-onboarding-blank", build_onboarding_form_101),
}


_REAL_ESTATE = (f"real-estate-blank-v{REAL_ESTATE_FORM_VERSION}.pdf", build_real_estate_form)


def _drawn_form_101(settings: Settings, process_key: str) -> Path:
    stem, build = _FORM_101[process_key]
    return _drawn(settings, f"{stem}-v{FORM_101_VERSION}.pdf", build)


def _drawn(settings: Settings, filename: str, build) -> Path:
    """The server's own drawing of a blank, made once and kept beside the generated templates."""
    path = settings.resolved_template_dir / filename
    if path.is_file():
        return path
    font = resolve_hebrew_font(settings.hebrew_font_path)
    if font is None:
        logger.error("Drawing %s needs a Hebrew font and none is available", filename)
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        staged.write_bytes(build(font))
        os.replace(staged, path)
        logger.info("Drew blank form at %s", path)
    except Exception:
        logger.exception("Could not draw the blank form %s", filename)
    return path
