import logging
from pathlib import Path

from reportlab.lib.colors import Color, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.catalog.processes import ProcessSeed
from app.domain.geometry import field_rects, to_reportlab_box
from app.domain.text_layout import contains_hebrew, shape_for_pdf

logger = logging.getLogger(__name__)

_INK = Color(0.11, 0.1, 0.08)
_TIDE = Color(0.06, 0.30, 0.29)
_LINE = Color(0.78, 0.74, 0.66)


class TemplateFactory:
    def __init__(self, directory: Path, font_path: Path | None) -> None:
        self._directory = directory
        self._font_path = font_path
        self._font_ready = False

    def ensure_templates(self, processes: tuple[ProcessSeed, ...] | list[ProcessSeed]) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        for process in processes:
            if process.layout.get("sign_source") == "uploaded_form":
                continue
            path = self._directory / process.template_filename
            if path.exists():
                continue
            self._build(process, path)
            logger.info("Wrote form template %s", path.name)

    def _build(self, process: ProcessSeed, path: Path) -> None:
        from reportlab.lib.pagesizes import A4

        page_width, page_height = A4
        form_canvas = canvas.Canvas(str(path), pagesize=A4)
        form_canvas.setTitle(process.name)
        form_canvas.setAuthor("DocketAI")
        form_canvas.setFillColor(_TIDE)
        form_canvas.rect(0, page_height - 36, page_width, 36, stroke=0, fill=1)
        form_canvas.setFillColor(white)
        form_canvas.setFont("Times-Bold", 16)
        form_canvas.drawString(72, page_height - 24, "DocketAI")
        form_canvas.setFillColor(_INK)
        form_canvas.setFont("Times-Bold", 18)
        form_canvas.drawString(72, page_height - 68, process.name)
        form_canvas.setStrokeColor(_LINE)
        form_canvas.line(72, page_height - 80, page_width - 72, page_height - 80)

        form = form_canvas.acroForm
        rects = field_rects(len(process.required_fields))
        for spec, rect in zip(process.required_fields, rects, strict=True):
            x, y, width, height = to_reportlab_box(rect, page_height)
            label = spec.get("label_he") or spec["label"]
            self._draw_label(form_canvas, str(label), x - 12, y + 6)
            form.textfield(
                name=spec["pdf_field_name"],
                tooltip=spec["label"],
                x=x,
                y=y,
                width=width,
                height=height,
                borderWidth=0.6,
                borderColor=_LINE,
                fillColor=white,
                textColor=_INK,
                forceBorder=True,
                fontSize=10,
            )

        signature = process.layout["signature_rect"]
        sx, sy, sw, sh = to_reportlab_box(signature, page_height)
        form_canvas.setStrokeColor(_TIDE)
        form_canvas.setLineWidth(0.8)
        form_canvas.rect(sx, sy, sw, sh, stroke=1, fill=0)
        form_canvas.setFillColor(_TIDE)
        form_canvas.setFont("Times-Roman", 9)
        form_canvas.drawString(sx, sy - 12, "Signature")
        form_canvas.save()

    def _draw_label(self, form_canvas: canvas.Canvas, text: str, right_x: float, baseline: float) -> None:
        if contains_hebrew(text) and self._font_path is not None:
            self._register_font()
            shown = shape_for_pdf(text)
            form_canvas.setFont("DocketHeb", 10)
            form_canvas.setFillColor(_INK)
            form_canvas.drawRightString(right_x, baseline, shown)
            return
        form_canvas.setFont("Times-Roman", 10)
        form_canvas.setFillColor(_INK)
        form_canvas.drawRightString(right_x, baseline, text)

    def _register_font(self) -> None:
        if self._font_ready or self._font_path is None:
            return
        pdfmetrics.registerFont(TTFont("DocketHeb", str(self._font_path)))
        self._font_ready = True
