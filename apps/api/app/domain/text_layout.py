import re

_HEBREW = re.compile(r"[\u0590-\u05FF]")


def contains_hebrew(text: str) -> bool:
    return bool(_HEBREW.search(text))


def clean_text(value: str) -> str:
    return value.replace("\x00", "").strip()


def shape_for_pdf(text: str) -> str:
    """Visual-order text for engines that draw glyphs left to right."""
    import arabic_reshaper
    from bidi.algorithm import get_display

    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)
