import logging
from pathlib import Path

from app.core.paths import API_ROOT

_BUNDLED = API_ROOT / "app" / "assets" / "fonts" / "Rubik-Regular.ttf"
_CANDIDATES = (
    _BUNDLED,
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
)

logger = logging.getLogger(__name__)


def bundled_hebrew_font() -> Path | None:
    return _BUNDLED if _BUNDLED.is_file() else None


def resolve_hebrew_font(configured: Path | None) -> Path | None:
    ordered = [configured, *_CANDIDATES] if configured else list(_CANDIDATES)
    for path in ordered:
        if path is not None and path.is_file():
            return path
    logger.warning("No Hebrew-capable font found. Set HEBREW_FONT_PATH for RTL appearance.")
    return None
