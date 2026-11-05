import logging
import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.container import Container
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError, ProcessingError
from app.core.time import utcnow
from app.domain.documents import DocumentView
from app.domain.enums import (
    AuditAction,
    CaseStatus,
    ClassificationSource,
    DocumentStatus,
)
from app.domain.readiness import signing_blockers
from app.domain.text_layout import contains_hebrew
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.document import Document
from app.models.process_definition import ProcessDefinition
from app.schemas.case import CaseCreate, CaseRead
from app.schemas.chat import ChatMessageRead, ChatRequest, FieldUpdateRequest
from app.schemas.gap import FillAndSignRequest, GapReport, ManualClassifyRequest, PipelineProgress
from app.schemas.process import DocumentTypeSpec, FieldSpec, ProcessRead
from app.schemas.workspace import CaseWorkspace, FileRejection, UploadResult
from app.services.chat_collector import OPENING
from app.services.field_validator import missing_required_fields, validate_field
from app.services.pdf_filler import decode_signature_png
from app.services.structural_excerpt import anchors_from_text, structural_signature
from app.services.uploads import store_upload

logger = logging.getLogger(__name__)

_DOCUMENT_ADAPTER = TypeAdapter(list[DocumentTypeSpec])
_FIELD_ADAPTER = TypeAdapter(list[FieldSpec])


class CaseService:
    def __init__(self, session: AsyncSession, container: Container) -> None:
        self.session = session
        self.container = container

    async def list_cases(self) -> list[CaseRead]:
        stmt = (
            select(Case)
            .options(selectinload(Case.documents), selectinload(Case.process_definition))
            .order_by(Case.created_at.desc())
            .limit(100)
        )
        rows = (await self.session.scalars(stmt)).all()
        return [self._case_read(case) for case in rows]

    async def create_case(self, payload: CaseCreate) -> CaseRead:
        data = payload.normalized()
        process = await self.session.scalar(
            select(ProcessDefinition).where(ProcessDefinition.key == data.process_key)
        )
        if process is None:
            raise NotFoundError(f"Unknown process '{data.process_key}'.")
        case = Case(
            name=data.name,
            client_name=data.client_name,
            process_definition_id=process.id,
            status=CaseStatus.DRAFT,
            pipeline_stage="draft",
            pipeline_message="Upload the document bundle before signing.",
            field_values={},
            chat_history=[
                {
                    "role": "assistant",
                    "content": OPENING,
                    "created_at": utcnow().isoformat(),
                }
            ],
        )
        case.process_definition = process
        self.session.add(case)
        await self.session.commit()
        stored = await self._get_case(case.id)
        return self._case_read(stored)

    async def workspace(self, case_id: uuid.UUID) -> CaseWorkspace:
        case = await self._get_case(case_id)
        return self._workspace(case)

    async def gap(self, case_id: uuid.UUID) -> GapReport:
        case = await self._get_case(case_id)
        return self._gap(case)

    async def add_uploads(
        self,
        case_id: uuid.UUID,
        files: list[UploadFile],
    ) -> tuple[UploadResult, bool]:
        if not files:
            raise BadRequestError("Choose at least one file.")
        limit = self.container.settings.max_files_per_upload
        if len(files) > limit:
            raise BadRequestError(f"Upload at most {limit} files at a time.")

        case = await self._get_case(case_id)
        case_dir = self.container.settings.resolved_storage_dir / "cases" / str(case.id)
        known_hashes = {document.content_hash for document in case.documents}
        accepted: list[str] = []
        skipped: list[str] = []
        rejected: list[FileRejection] = []
        created_paths: list[Path] = []

        for upload in files:
            suffix = Path(upload.filename or "upload").suffix.lower()
            dest = case_dir / f"{uuid.uuid4().hex}{suffix}"
            try:
                stored = await store_upload(
                    upload,
                    dest,
                    max_bytes=self.container.settings.max_upload_bytes,
                )
            except BadRequestError as exc:
                rejected.append(FileRejection(filename=Path(upload.filename or "upload").name, reason=exc.message))
                continue
            if stored.content_hash in known_hashes:
                Path(stored.storage_path).unlink(missing_ok=True)
                skipped.append(stored.original_filename)
                continue
            known_hashes.add(stored.content_hash)
            created_paths.append(Path(stored.storage_path))
            self.session.add(
                Document(
                    case_id=case.id,
                    original_filename=stored.original_filename,
                    storage_path=stored.storage_path,
                    mime_type=stored.mime_type,
                    file_size=stored.file_size,
                    content_hash=stored.content_hash,
                    status=DocumentStatus.UPLOADED,
                    classification_source=ClassificationSource.PENDING,
                )
            )
            accepted.append(stored.original_filename)

        try:
            if accepted:
                case.status = CaseStatus.PROCESSING
                case.pipeline_stage = "parsing"
                case.pipeline_message = "Parsing"
                case.pipeline_completed = 0
                case.pipeline_total = len(accepted)
                case.updated_at = utcnow()
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            for path in created_paths:
                path.unlink(missing_ok=True)
            raise
        self.session.expire(case, ["documents"])
        refreshed = await self._get_case(case_id)
        result = UploadResult(
            workspace=self._workspace(refreshed),
            accepted_filenames=accepted,
            skipped_duplicates=skipped,
            rejected=rejected,
        )
        return result, bool(accepted)

    async def run_ingestion(self, case_id: uuid.UUID) -> None:
        try:
            await self._ingest(case_id)
        except Exception:
            logger.exception("Ingestion failed for case %s", case_id)
            try:
                await self._mark_pipeline_failed(case_id)
            except Exception:
                logger.exception("Could not record the pipeline failure for case %s", case_id)
            raise

    async def _ingest(self, case_id: uuid.UUID) -> None:
        case = await self._get_case(case_id)
        required, optional = _document_specs(case.process_definition)
        catalog = required + optional
        pending_ids = [
            document.id
            for document in case.documents
            if document.status in {DocumentStatus.UPLOADED, DocumentStatus.PROCESSING}
        ]
        case.status = CaseStatus.PROCESSING
        case.pipeline_stage = "parsing"
        case.pipeline_message = "Parsing"
        case.pipeline_completed = 0
        case.pipeline_total = len(pending_ids)
        case.updated_at = utcnow()
        await self.session.commit()

        total = len(pending_ids)
        for index, document_id in enumerate(pending_ids, start=1):
            case = await self._get_case(case_id)
            case.pipeline_stage = "classifying"
            case.pipeline_message = f"Classifying: {index}/{total}"
            case.pipeline_completed = index - 1
            case.pipeline_total = total
            document = await self.session.get(Document, document_id)
            if document is None or document.status not in {
                DocumentStatus.UPLOADED,
                DocumentStatus.PROCESSING,
            }:
                continue
            document.status = DocumentStatus.PROCESSING
            document.updated_at = utcnow()
            await self.session.commit()
            try:
                await self.container.pipeline.process_document(self.session, document, catalog)
            except ProcessingError as exc:
                logger.info("Document %s was not readable: %s", document_id, exc)
                document.status = DocumentStatus.FAILED
                document.error_message = str(exc)[:500]
                document.updated_at = utcnow()
            except Exception:
                logger.exception("Failed to process document %s", document_id)
                document.status = DocumentStatus.FAILED
                document.error_message = "This file could not be processed."
                document.updated_at = utcnow()
            case.pipeline_completed = index
            await self.session.commit()

        refreshed = await self._get_case(case_id)
        refreshed.pipeline_stage = "auditing"
        refreshed.pipeline_message = "Auditing"
        refreshed.updated_at = utcnow()
        await self.session.commit()

        refreshed = await self._get_case(case_id)
        refreshed.status = _derive_status(refreshed.documents, refreshed.status)
        self._refresh_pipeline(refreshed)
        refreshed.updated_at = utcnow()
        await self.session.commit()

    async def _mark_pipeline_failed(self, case_id: uuid.UUID) -> None:
        try:
            await self.session.rollback()
        except Exception:
            logger.exception("Could not roll back the failed ingestion")
        case = await self.session.get(Case, case_id)
        if case is None:
            return
        if case.pipeline_stage in {"signed", "ready_for_signature", "awaiting_input"}:
            return
        case.pipeline_stage = "failed"
        case.pipeline_message = "Processing stopped. Unreadable files are marked on the checklist."
        if case.status == CaseStatus.PROCESSING:
            case.status = CaseStatus.READY_FOR_REVIEW
        case.updated_at = utcnow()
        await self.session.commit()

    async def classify_manual(self, case_id: uuid.UUID, payload: ManualClassifyRequest) -> CaseWorkspace:
        case = await self._get_case(case_id)
        document = next((item for item in case.documents if item.id == payload.document_id), None)
        if document is None:
            raise NotFoundError("Document not found on this case.")
        if document.status == DocumentStatus.PROCESSING:
            raise ConflictError("This document is still processing.")

        required, optional = _document_specs(case.process_definition)
        allowed = {item.type_key for item in required + optional}
        doc_type = payload.document_type.strip()
        if doc_type not in allowed:
            raise BadRequestError("That document type is not part of this process.")

        previous = {
            "document_type": document.document_type,
            "confidence": document.confidence,
            "status": document.status.value,
        }
        document.document_type = doc_type
        document.confidence = 1.0
        document.status = DocumentStatus.CLASSIFIED
        document.classification_source = ClassificationSource.HUMAN
        document.error_message = None
        if payload.note:
            document.rationale = payload.note.strip()
        document.updated_at = utcnow()

        anchors = anchors_from_text(document.extracted_text or "")
        point_id = await self.container.learning.record(
            document_id=document.id,
            document_type=doc_type,
            process_type=case.process_definition.key,
            anchors=anchors,
            structural_signature=structural_signature(anchors) if anchors else "",
        )
        self.session.add(
            AuditLog(
                case_id=case.id,
                document_id=document.id,
                action=AuditAction.MANUAL_CLASSIFY,
                actor="user",
                previous_value=previous,
                new_value={"document_type": doc_type, "confidence": 1.0},
                embedding_point_id=point_id,
                notes=payload.note.strip() if payload.note else None,
            )
        )
        case.status = _derive_status(case.documents, case.status)
        self._refresh_pipeline(case)
        case.updated_at = utcnow()
        await self.session.commit()
        return self._workspace(case)

    async def chat(self, case_id: uuid.UUID, payload: ChatRequest) -> CaseWorkspace:
        case = await self._get_case(case_id)
        fields = _field_specs(case.process_definition)
        values, reply = await self.container.chat.respond(
            fields=fields,
            values={str(key): str(value) for key, value in (case.field_values or {}).items()},
            message=payload.message.strip(),
        )
        changed = values != (case.field_values or {})
        case.field_values = values
        if changed and case.status == CaseStatus.SIGNED:
            self._clear_signed_output(case)
            case.status = CaseStatus.FILLING
        history = list(case.chat_history or [])
        stamp = utcnow().isoformat()
        history.append({"role": "user", "content": payload.message.strip(), "created_at": stamp})
        history.append({"role": "assistant", "content": reply, "created_at": stamp})
        case.chat_history = history[-100:]
        self._refresh_pipeline(case)
        case.updated_at = utcnow()
        await self.session.commit()
        return self._workspace(case)

    async def set_field(self, case_id: uuid.UUID, payload: FieldUpdateRequest) -> CaseWorkspace:
        case = await self._get_case(case_id)
        fields = _field_specs(case.process_definition)
        spec = next((item for item in fields if item.key == payload.key), None)
        if spec is None:
            raise BadRequestError(f"Unknown field '{payload.key}'.")
        result = validate_field(spec, payload.value)
        if not result.ok:
            raise BadRequestError(result.message)
        merged = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        merged[spec.key] = result.normalized
        if merged != (case.field_values or {}) and case.status == CaseStatus.SIGNED:
            self._clear_signed_output(case)
            case.status = CaseStatus.FILLING
        case.field_values = merged
        self._refresh_pipeline(case)
        case.updated_at = utcnow()
        await self.session.commit()
        return self._workspace(case)

    async def fill_and_sign(self, case_id: uuid.UUID, payload: FillAndSignRequest) -> CaseWorkspace:
        case = await self._get_case(case_id)
        fields = _field_specs(case.process_definition)
        by_key = {item.key: item for item in fields}
        merged = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        for key, raw in payload.field_values.items():
            spec = by_key.get(key)
            if spec is None:
                raise BadRequestError(f"Unknown field '{key}'.")
            result = validate_field(spec, raw)
            if not result.ok:
                raise BadRequestError(result.message)
            merged[key] = result.normalized

        gap = self._gap(case)
        blockers = self._blockers(case, gap, merged)
        if blockers:
            raise ConflictError(" ".join(blockers))

        signature = decode_signature_png(payload.signature_png_base64)
        layout = case.process_definition.layout or {}
        rect = layout.get("signature_rect")
        if not isinstance(rect, list) or len(rect) != 4:
            raise ConflictError("This process has no signature box configured.")
        template = self.container.settings.resolved_template_dir / case.process_definition.template_filename
        if not template.is_file():
            raise ConflictError("The form template is missing.")

        pdf_values: dict[str, str] = {}
        rtl_fields: set[str] = set()
        for spec in fields:
            value = merged.get(spec.key, "").strip()
            if not value:
                continue
            pdf_values[spec.pdf_field_name] = value
            if spec.rtl or contains_hebrew(value):
                rtl_fields.add(spec.pdf_field_name)

        output = (
            self.container.settings.resolved_storage_dir
            / "cases"
            / str(case.id)
            / "signed"
            / f"{_safe_stem(case.name)}-signed.pdf"
        )
        output.unlink(missing_ok=True)
        try:
            artifact = self.container.pdf_filler.fill_and_sign(
                template_path=template,
                output_path=output,
                values=pdf_values,
                signature_png=signature,
                signature_rect=[float(item) for item in rect],
                page_index=int(layout.get("page_index", 0)),
                rtl_fields=rtl_fields,
                case_id=str(case.id),
            )
            case.field_values = merged
            case.output_path = str(output)
            case.content_sha256 = artifact.content_sha256
            case.signer_verification_id = artifact.signer_verification_id
            case.status = CaseStatus.SIGNED
            case.pipeline_stage = "signed"
            case.pipeline_message = "Signed packet is ready."
            case.updated_at = utcnow()
            self.session.add(
                AuditLog(
                    case_id=case.id,
                    action=AuditAction.FILL_AND_SIGN,
                    actor="user",
                    new_value={
                        "output_path": case.output_path,
                        "fields": sorted(pdf_values),
                        "content_sha256": artifact.content_sha256,
                        "signer_verification_id": artifact.signer_verification_id,
                    },
                )
            )
            await self.session.commit()
        except Exception:
            output.unlink(missing_ok=True)
            await self.session.rollback()
            raise
        stored = await self._get_case(case_id)
        return self._workspace(stored)

    async def signed_pdf(self, case_id: uuid.UUID) -> Path:
        case = await self._get_case(case_id)
        if case.status != CaseStatus.SIGNED or not case.output_path:
            raise NotFoundError("This case has no signed document yet.")
        path = Path(case.output_path).resolve()
        root = self.container.settings.resolved_storage_dir.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise NotFoundError("This case has no signed document yet.") from exc
        if not path.is_file():
            raise NotFoundError("The signed document file is missing.")
        return path

    async def document_file(self, case_id: uuid.UUID, document_id: uuid.UUID) -> tuple[Path, str, str]:
        case = await self._get_case(case_id)
        document = next((item for item in case.documents if item.id == document_id), None)
        if document is None:
            raise NotFoundError("Document not found on this case.")
        path = Path(document.storage_path).resolve()
        root = self.container.settings.resolved_storage_dir.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise NotFoundError("Document not found on this case.") from exc
        if not path.is_file():
            raise NotFoundError("The document file is missing.")
        return path, document.mime_type, document.original_filename

    async def _get_case(self, case_id: uuid.UUID) -> Case:
        stmt = (
            select(Case)
            .where(Case.id == case_id)
            .options(
                selectinload(Case.documents),
                selectinload(Case.process_definition),
            )
        )
        case = await self.session.scalar(stmt)
        if case is None:
            raise NotFoundError("Case not found.")
        return case

    def _workspace(self, case: Case) -> CaseWorkspace:
        required, optional = _document_specs(case.process_definition)
        fields = _field_specs(case.process_definition)
        values = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        gap = self._gap(case)
        blockers = self._blockers(case, gap, values)
        return CaseWorkspace(
            case=self._case_read(case),
            gap=gap,
            process=ProcessRead(
                key=case.process_definition.key,
                name=case.process_definition.name,
                description=case.process_definition.description,
                required_documents=required,
                optional_documents=optional,
                required_fields=fields,
            ),
            messages=[ChatMessageRead.model_validate(item) for item in (case.chat_history or [])],
            field_values=values,
            missing_fields=missing_required_fields(fields, values),
            ready_to_sign=not blockers,
            signing_blockers=blockers,
        )

    def _gap(self, case: Case) -> GapReport:
        required, optional = _document_specs(case.process_definition)
        labels = {item.type_key: item.label for item in required + optional}
        label_he = {item.type_key: item.label_he for item in required + optional}
        views = [
            DocumentView(
                document_id=document.id,
                filename=document.original_filename,
                document_type=document.document_type,
                confidence=document.confidence,
                status=document.status,
                source=document.classification_source,
                rationale=document.rationale,
                error_message=document.error_message,
            )
            for document in case.documents
        ]
        report = self.container.gap_analyzer.analyze(
            case_id=case.id,
            status=case.status,
            requirements=required,
            labels=labels,
            label_he=label_he,
            documents=views,
        )
        report.pipeline = self._pipeline(case)
        return report

    def _pipeline(self, case: Case) -> PipelineProgress:
        stage = case.pipeline_stage or "draft"
        allowed = {
            "draft",
            "parsing",
            "classifying",
            "auditing",
            "awaiting_input",
            "ready_for_signature",
            "signed",
            "failed",
        }
        if stage not in allowed:
            stage = "draft"
        return PipelineProgress(
            stage=stage,  # type: ignore[arg-type]
            completed=int(case.pipeline_completed or 0),
            total=int(case.pipeline_total or 0),
            message=case.pipeline_message or "",
        )

    def _refresh_pipeline(self, case: Case) -> None:
        documents = list(case.documents)
        if any(
            document.status in {DocumentStatus.UPLOADED, DocumentStatus.PROCESSING}
            for document in documents
        ):
            return
        if case.status == CaseStatus.SIGNED:
            case.pipeline_stage = "signed"
            case.pipeline_message = "Signed packet is ready."
            return
        if documents and all(document.status == DocumentStatus.FAILED for document in documents):
            message = next(
                (document.error_message for document in documents if document.error_message),
                "Every file failed.",
            )
            case.pipeline_stage = "failed"
            case.pipeline_message = message[:240]
            return
        values = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        gap = self._gap(case)
        blockers = self._blockers(case, gap, values)
        if blockers:
            case.pipeline_stage = "awaiting_input"
            case.pipeline_message = blockers[0][:240]
            return
        case.pipeline_stage = "ready_for_signature"
        case.pipeline_message = "Ready for signature."

    def _blockers(self, case: Case, gap: GapReport, values: dict[str, str]) -> list[str]:
        fields = _field_specs(case.process_definition)
        return signing_blockers(
            status=case.status,
            missing_labels=[item.label for item in gap.missing],
            unrecognized_count=len(gap.unrecognized),
            in_progress_count=len(gap.in_progress),
            missing_field_labels=[item.label for item in missing_required_fields(fields, values)],
        )

    def _case_read(self, case: Case) -> CaseRead:
        return CaseRead(
            id=case.id,
            name=case.name,
            client_name=case.client_name,
            status=case.status,
            process_key=case.process_definition.key,
            process_name=case.process_definition.name,
            document_count=len(case.documents),
            download_ready=case.status == CaseStatus.SIGNED and bool(case.output_path),
            created_at=case.created_at,
            updated_at=case.updated_at,
        )

    def _clear_signed_output(self, case: Case) -> None:
        if case.output_path:
            Path(case.output_path).unlink(missing_ok=True)
            case.output_path = None
        case.content_sha256 = None
        case.signer_verification_id = None


def _document_specs(process: ProcessDefinition) -> tuple[list[DocumentTypeSpec], list[DocumentTypeSpec]]:
    required = _DOCUMENT_ADAPTER.validate_python(process.required_documents or [])
    optional = _DOCUMENT_ADAPTER.validate_python(process.optional_documents or [])
    return required, optional


def _field_specs(process: ProcessDefinition) -> list[FieldSpec]:
    return _FIELD_ADAPTER.validate_python(process.required_fields or [])


def _derive_status(documents: list[Document], current: CaseStatus) -> CaseStatus:
    if not documents:
        return CaseStatus.DRAFT
    if any(document.status in {DocumentStatus.UPLOADED, DocumentStatus.PROCESSING} for document in documents):
        return CaseStatus.PROCESSING
    if any(
        document.status in {DocumentStatus.NEEDS_REVIEW, DocumentStatus.FAILED}
        for document in documents
    ):
        return CaseStatus.READY_FOR_REVIEW
    if all(document.status == DocumentStatus.CLASSIFIED for document in documents):
        if current == CaseStatus.SIGNED:
            return CaseStatus.SIGNED
        return CaseStatus.FILLING
    return CaseStatus.READY_FOR_REVIEW


def _safe_stem(name: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "-", name, flags=re.UNICODE).strip("-.")
    return (cleaned or "docket")[:60]
