from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.services.chat_collector import ChatCollector
from app.services.classification_engine import ClassificationEngine
from app.services.document_processor import DocumentProcessor
from app.services.fonts import resolve_hebrew_font
from app.services.gap_analyzer import GapAnalyzer
from app.services.gemini_client import GoogleGeminiClient
from app.services.learning_store import QdrantLearningStore
from app.services.pdf_filler import PdfFillerService
from app.services.pipeline import IngestionPipeline
from app.services.template_factory import TemplateFactory


@dataclass
class Container:
    settings: Settings
    processor: DocumentProcessor
    classifier: ClassificationEngine
    gap_analyzer: GapAnalyzer
    pdf_filler: PdfFillerService
    learning: QdrantLearningStore
    pipeline: IngestionPipeline
    chat: ChatCollector
    templates: TemplateFactory


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    font = resolve_hebrew_font(settings.hebrew_font_path)
    gemini = GoogleGeminiClient(settings)
    processor = DocumentProcessor(max_vision_pages=settings.max_vision_pages)
    classifier = ClassificationEngine(gemini, settings.confidence_threshold)
    learning = QdrantLearningStore(settings, gemini)
    return Container(
        settings=settings,
        processor=processor,
        classifier=classifier,
        gap_analyzer=GapAnalyzer(settings.confidence_threshold),
        pdf_filler=PdfFillerService(font),
        learning=learning,
        pipeline=IngestionPipeline(processor, classifier, learning),
        chat=ChatCollector(gemini),
        templates=TemplateFactory(settings.resolved_template_dir, font),
    )
