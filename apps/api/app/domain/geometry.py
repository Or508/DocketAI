"""A4 geometry shared by templates and the signature stamp.

Coordinates use the PDF user space with the origin at the top-left, matching PyMuPDF.
"""

A4_WIDTH = 595.27
A4_HEIGHT = 841.89


def signature_rect() -> list[float]:
    x0 = 72.0
    box_height = 84.0
    y1 = A4_HEIGHT - 64.0
    y0 = y1 - box_height
    return [x0, y0, x0 + 260.0, y1]


def field_rects(count: int) -> list[tuple[float, float, float, float]]:
    y = 132.0
    rects: list[tuple[float, float, float, float]] = []
    for _ in range(count):
        rects.append((210.0, y, 523.0, y + 24.0))
        y += 46.0
    return rects


def to_reportlab_box(
    rect: tuple[float, float, float, float] | list[float],
    page_height: float,
) -> tuple[float, float, float, float]:
    """Convert a top-left rect into ReportLab's bottom-left x, y, width, height."""
    x0, y0, x1, y1 = rect
    return x0, page_height - y1, x1 - x0, y1 - y0
