import asyncio
import hashlib
import logging
import os
import re
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import fitz

from fastapi import UploadFile
from pydantic import TypeAdapter
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.container import Container
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ProcessingError,
    SignedFileIntegrityError,
)
from app.core.time import utcnow
from app.domain.certificate import (
    OFFICE_CONSENT_TEXT,
    PORTAL_CONSENT_TEXT,
    CertificateData,
    SignerContext,
)
from app.domain.case_scope import CaseScope, case_query
from app.domain.documents import DocumentView
from app.domain.enums import (
    AuditAction,
    CaseStatus,
    ClassificationSource,
    DocumentStatus,
)
from app.domain.provenance import INTAKE_PROMPT_EN, INTAKE_PROMPT_HE, why_items
from app.domain.readiness import signing_blockers
from app.domain.slot_reading import apply_proposals, read_document, retract_document
from app.domain.storage_keys import document_key, signed_keys
from app.domain.signing_links import as_utc
from app.domain.text_layout import contains_hebrew
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.document import Document
from app.models.process_definition import ProcessDefinition
from app.models.signing_link import SigningLink
from app.schemas.case import CaseAudit, CaseCertificate, CaseCreate, CaseRead
from app.schemas.chat import ChatMessageRead, ChatRequest, FieldUpdateRequest
from app.schemas.forms import (
    DocumentReadingReport,
    DocumentRoleRead,
    DocumentRoleUpdate,
    FillReport,
    FillReportField,
    IntakeForm,
    IntakeSummary,
    SlotConflict,
    SlotHit,
    SlotSkip,
)
from app.schemas.gap import (
    FillAndSignRequest,
    FormAnchorRef,
    GapReport,
    ManualClassifyRequest,
    OpenSlot,
    PipelineProgress,
    UnboundAnchor,
)
from app.schemas.process import DocumentTypeSpec, FieldSource, FieldSpec, ProcessRead, ValueSource
from app.schemas.workspace import CaseWorkspace, FileRejection, UploadResult
from app.services.chat_collector import OPENING, ChatTurn
from app.services.field_validator import missing_required_fields, validate_field
from app.services.pdf_filler import FilledForm, SignedArtifact, decode_signature_png
from app.services.object_store import ObjectMissingError, ObjectReader
from app.services.structural_excerpt import anchors_from_text, structural_signature
from app.services.preflight import preflight
from app.services.uploads import normalize_image, store_upload, stored_suffix

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatStart:
    turn: ChatTurn
    stamp: str

_DOCUMENT_ADAPTER = TypeAdapter(list[DocumentTypeSpec])
_FIELD_ADAPTER = TypeAdapter(list[FieldSpec])


class CaseService:
    def __init__(self, session: AsyncSession, container: Container, scope: CaseScope) -> None:
        self.session = session
        self.container = container
        self.scope = scope

    async def list_cases(self) -> list[CaseRead]:
        stmt = (
            case_query(self.scope)
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
        if self.scope.organization_id is None:
            raise ForbiddenError("A system scope cannot create cases.")
        case = Case(
            organization_id=self.scope.organization_id,
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
        document_type: str | None = None,
        role: str | None = None,
        replace_existing: bool = False,
    ) -> tuple[UploadResult, bool]:
        """Store the files. A document type or role named with the upload is the office's
        own choice: it is kept whatever automatic classification would have said, and it
        is applied to a file this case already holds. With replace_existing, the files
        that sat in that drawer before are removed once a new one is in.
        """
        if not files:
            raise BadRequestError("Choose at least one file.")
        limit = self.container.settings.max_files_per_upload
        if len(files) > limit:
            raise BadRequestError(f"Upload at most {limit} files at a time.")

        case = await self._get_case(case_id)
        chosen_type = _drawer_type(case, document_type)
        chosen_role = _drawer_role(role)
        held = {document.content_hash: document.id for document in case.documents}
        repeated: list[uuid.UUID] = []
        known_hashes = set(held)
        accepted: list[str] = []
        skipped: list[str] = []
        rejected: list[FileRejection] = []
        created_keys: list[str] = []
        removed_keys: list[str] = []

        try:
            with tempfile.TemporaryDirectory() as work:
                for upload in files:
                    suffix = Path(upload.filename or "upload").suffix.lower()
                    dest = Path(work) / f"{uuid.uuid4().hex}{suffix}"
                    try:
                        stored = await store_upload(
                            upload,
                            dest,
                            max_bytes=self.container.settings.max_upload_bytes,
                        )
                    except BadRequestError as exc:
                        rejected.append(
                            FileRejection(filename=Path(upload.filename or "upload").name, reason=exc.message)
                        )
                        continue
                    if stored.content_hash in known_hashes:
                        os.remove(stored.storage_path)
                        skipped.append(stored.original_filename)
                        if stored.content_hash in held:
                            repeated.append(held[stored.content_hash])
                        continue
                    try:
                        await preflight(
                            Path(stored.storage_path),
                            stored.mime_type,
                            self.container.settings,
                            stored.original_filename,
                        )
                        await self.container.scanner.scan(Path(stored.storage_path), stored.original_filename)
                    except BadRequestError as exc:
                        os.remove(stored.storage_path)
                        rejected.append(FileRejection(filename=stored.original_filename, reason=exc.message))
                        continue
                    try:
                        local, mime = await asyncio.to_thread(
                            normalize_image, Path(stored.storage_path), stored.mime_type
                        )
                    except Exception:
                        if os.path.exists(stored.storage_path):
                            os.remove(stored.storage_path)
                        rejected.append(
                            FileRejection(
                                filename=stored.original_filename,
                                reason=f"{stored.original_filename} could not be read as an image.",
                            )
                        )
                        continue
                    known_hashes.add(stored.content_hash)
                    key = document_key(case.organization_id, case.id, stored_suffix(mime))
                    created_keys.append(key)
                    size = local.stat().st_size
                    with local.open("rb") as handle:
                        await self.container.store.upload_file(key, handle, mime)
                    os.remove(local)
                    self.session.add(
                        Document(
                            case_id=case.id,
                            original_filename=stored.original_filename,
                            storage_path=key,
                            mime_type=mime,
                            file_size=size,
                            content_hash=stored.content_hash,
                            status=DocumentStatus.UPLOADED,
                            document_type=chosen_type,
                            confidence=1.0 if chosen_type else None,
                            classification_source=(
                                ClassificationSource.HUMAN if chosen_type else ClassificationSource.PENDING
                            ),
                            role=chosen_role or "evidence",
                        )
                    )
                    accepted.append(stored.original_filename)

                if replace_existing and (accepted or repeated) and case.status != CaseStatus.SIGNED:
                    removed_keys = self._remove_documents(
                        case, _drawer_occupants(case, chosen_type, chosen_role, keep=set(repeated))
                    )
                if accepted:
                    self._invalidate_signature(case, reason="A new file was uploaded after signing.")
                    case.status = CaseStatus.PROCESSING
                    case.pipeline_stage = "parsing"
                    case.pipeline_message = "Parsing"
                    case.pipeline_completed = 0
                    case.pipeline_total = len(accepted)
                    case.updated_at = utcnow()
                elif removed_keys:
                    case.status = _derive_status(case.documents, case.status)
                    self._refresh_pipeline(case)
                    case.updated_at = utcnow()
                await self.session.commit()
        except Exception:
            await self.session.rollback()
            for key in created_keys:
                try:
                    await self.container.store.delete_file(key)
                except Exception:
                    logger.exception("Could not delete object %s after a failed upload", key)
            raise
        await self._delete_objects(removed_keys)
        for document_id in dict.fromkeys(repeated):
            await self._file_existing(case_id, document_id, chosen_type, chosen_role)
        if removed_keys:
            await self._reread(case_id)
        self.session.expire_all()
        refreshed = await self._get_case(case_id)
        result = UploadResult(
            workspace=self._workspace(refreshed),
            accepted_filenames=accepted,
            skipped_duplicates=skipped,
            rejected=rejected,
        )
        return result, bool(accepted) or _has_stalled_documents(refreshed)

    async def _file_existing(
        self,
        case_id: uuid.UUID,
        document_id: uuid.UUID,
        chosen_type: str | None,
        chosen_role: str | None,
    ) -> None:
        """Apply the drawer the office picked to a file the case already holds."""
        case = await self._get_case(case_id)
        document = next((item for item in case.documents if item.id == document_id), None)
        if document is None or case.status == CaseStatus.SIGNED:
            return
        waiting = document.status in {DocumentStatus.UPLOADED, DocumentStatus.PROCESSING}
        if chosen_type is not None:
            if waiting:
                # Ingestion has not finished with this file: it keeps this label when it does.
                document.document_type = chosen_type
                document.confidence = 1.0
                document.classification_source = ClassificationSource.HUMAN
                await self.session.commit()
            elif document.document_type != chosen_type or document.status != DocumentStatus.CLASSIFIED:
                await self.classify_manual(
                    case_id, ManualClassifyRequest(document_id=document_id, document_type=chosen_type)
                )
        if chosen_role is not None and document.role != chosen_role:
            if waiting:
                document.role = chosen_role
                await self.session.commit()
                return
            try:
                await self.set_document_role(case_id, document_id, DocumentRoleUpdate(role=chosen_role))
            except ConflictError as exc:
                logger.info("Role %s not applied to document %s: %s", chosen_role, document_id, exc.message)

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
        fields = _field_specs(case.process_definition)
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
            # A type the office chose with the upload outranks whatever the reader finds.
            chosen = (
                document.document_type
                if document.classification_source == ClassificationSource.HUMAN and document.document_type
                else None
            )
            document.status = DocumentStatus.PROCESSING
            document.updated_at = utcnow()
            await self.session.commit()
            try:
                await self.container.pipeline.process_document(
                    self.session,
                    document,
                    catalog,
                    organization_id=case.organization_id,
                    fields=fields,
                    layout=case.process_definition.layout,
                    classify=chosen is None,
                )
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
            if chosen is not None:
                unread = document.status == DocumentStatus.FAILED
                document.document_type = chosen
                document.confidence = 1.0
                document.classification_source = ClassificationSource.HUMAN
                document.status = DocumentStatus.CLASSIFIED
                document.error_message = None
                if unread:
                    document.rationale = "Filed by the office. Its text could not be read."
                self.session.add(
                    AuditLog(
                        case_id=case_id,
                        document_id=document.id,
                        action=AuditAction.MANUAL_CLASSIFY,
                        actor="office",
                        new_value={"document_type": chosen, "confidence": 1.0, "at_upload": True},
                    )
                )
            if document.role == "form" and (
                document.mime_type != "application/pdf" or not document.form_anchors
            ):
                # Nothing can be placed on a file with no readable form fields.
                document.role = "evidence"
            case.pipeline_completed = index
            await self.session.commit()
            classified = document.status == DocumentStatus.CLASSIFIED
            if document.form_anchors:
                await self._prefill_from_document(case_id, document_id)
            if classified:
                await self._read_slots_from_document(case_id, document_id)

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

    async def _prefill_from_document(self, case_id: uuid.UUID, document_id: uuid.UUID) -> None:
        """Copy filled widget values into empty slots.

        A value is used only when the existing validator accepts it, every widget
        bound to that slot in this document agrees, and the slot has no value yet.
        An existing value is never replaced, whether it matches or not.
        """
        case = await self._locked_case(case_id)
        if case is None or case.status == CaseStatus.SIGNED:
            await self.session.rollback()
            return
        document = next((item for item in case.documents if item.id == document_id), None)
        if document is None or document.status == DocumentStatus.FAILED:
            await self.session.rollback()
            return
        by_key = {spec.key: spec for spec in _field_specs(case.process_definition)}
        candidates: dict[str, set[str]] = {}
        for anchor in document.form_anchors or []:
            key = anchor.get("slot_key")
            value = anchor.get("value")
            if not isinstance(key, str) or anchor.get("empty") or not isinstance(value, str):
                continue
            spec = by_key.get(key)
            if spec is None:
                continue
            result = validate_field(spec, value)
            if result.ok:
                candidates.setdefault(key, set()).add(result.normalized)
        current = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        merged = dict(current)
        filled: list[str] = []
        for key, values in sorted(candidates.items()):
            if len(values) != 1 or current.get(key, "").strip():
                continue
            merged[key] = next(iter(values))
            filled.append(key)
        if not filled:
            await self.session.rollback()
            return
        sources = dict(case.field_sources or {})
        for key in filled:
            sources[key] = {"source": "document", "document_id": str(document.id)}
        case.field_sources = sources
        case.field_values = merged
        self._mark_data_completion(case)
        case.updated_at = utcnow()
        # The audit row names the slots only; the values are personal data.
        self.session.add(
            AuditLog(
                case_id=case.id,
                document_id=document.id,
                action=AuditAction.FIELD_PREFILLED,
                actor="system",
                new_value={"fields": filled},
            )
        )
        await self.session.commit()

    async def _mark_pipeline_failed(self, case_id: uuid.UUID) -> None:
        try:
            await self.session.rollback()
        except Exception:
            logger.exception("Could not roll back the failed ingestion")
        case = await self.session.scalar(case_query(self.scope).where(Case.id == case_id))
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
        # What this file supplied under its old label has to be earned again.
        self._retract(case, [document])
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
            organization_id=case.organization_id,
        )
        self.session.add(
            AuditLog(
                case_id=case.id,
                document_id=document.id,
                action=AuditAction.MANUAL_CLASSIFY,
                actor=self.scope.actor,
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
        await self._reread(case_id)
        return self._workspace(await self._get_case(case_id))

    async def delete_document(self, case_id: uuid.UUID, document_id: uuid.UUID) -> CaseWorkspace:
        """Remove a file from the case, with the details it supplied.

        Details the office or the client typed stay. The files that remain are read
        again, so one of them can supply a slot the removed file had taken.
        """
        case = await self._get_case(case_id)
        document = next((item for item in case.documents if item.id == document_id), None)
        if document is None:
            raise NotFoundError("Document not found on this case.")
        if case.status == CaseStatus.SIGNED:
            raise ConflictError("This case is already signed.")
        if document.status == DocumentStatus.PROCESSING and not _is_stalled(document):
            raise ConflictError("This document is still processing.")
        keys = self._remove_documents(case, [document])
        self._invalidate_signature(case, reason="A file was removed after signing.")
        case.status = _derive_status(case.documents, case.status)
        self._refresh_pipeline(case)
        case.updated_at = utcnow()
        await self.session.commit()
        await self._delete_objects(keys)
        await self._reread(case_id)
        return self._workspace(await self._get_case(case_id))

    def _retract(self, case: Case, documents: list[Document]) -> None:
        values = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        sources = {
            str(key): dict(value) for key, value in (case.field_sources or {}).items() if isinstance(value, dict)
        }
        for document in documents:
            values, sources = retract_document(values, sources, str(document.id))
        case.field_values = values
        case.field_sources = sources
        self._mark_data_completion(case)

    def _remove_documents(self, case: Case, documents: list[Document]) -> list[str]:
        """Drop the rows and what they supplied. Returns the stored objects to delete after commit."""
        keys: list[str] = []
        self._retract(case, documents)
        for document in documents:
            keys.append(document.storage_path)
            self.session.add(
                AuditLog(
                    case_id=case.id,
                    action=AuditAction.DOCUMENT_REMOVED,
                    actor=self.scope.actor,
                    previous_value={
                        "document_id": str(document.id),
                        "document_type": document.document_type,
                        "role": document.role,
                        "content_hash": document.content_hash,
                    },
                )
            )
            case.documents.remove(document)
        return keys

    async def _delete_objects(self, keys: list[str]) -> None:
        for key in keys:
            try:
                await self.container.store.delete_file(key)
            except Exception:
                logger.exception("Could not delete object %s of a removed document", key)

    async def _reread(self, case_id: uuid.UUID) -> None:
        """Run the closed readers again over every file the case holds, oldest first."""
        self.session.expire_all()
        case = await self._get_case(case_id)
        ordered = sorted(case.documents, key=lambda item: (item.created_at, str(item.id)))
        todo = [
            (item.id, bool(item.form_anchors), item.status == DocumentStatus.CLASSIFIED) for item in ordered
        ]
        for document_id, anchored, classified in todo:
            if anchored:
                await self._prefill_from_document(case_id, document_id)
            if classified:
                await self._read_slots_from_document(case_id, document_id)
        case = await self._locked_case(case_id)
        if case is None:
            await self.session.rollback()
            return
        self._refresh_pipeline(case)
        await self.session.commit()

    async def _read_slots_from_document(self, case_id: uuid.UUID, document_id: uuid.UUID) -> None:
        """Write empty slots from a classified document, and only the slots that type supplies.

        An existing value is left as it is. An ambiguous or invalid reading is skipped,
        so the detail stays with the office.
        """
        case = await self._locked_case(case_id)
        if case is None or case.status == CaseStatus.SIGNED:
            await self.session.rollback()
            return
        document = next((item for item in case.documents if item.id == document_id), None)
        if document is None or document.status != DocumentStatus.CLASSIFIED or not document.document_type:
            await self.session.rollback()
            return
        required, optional = _document_specs(case.process_definition)
        type_spec = next(
            (item for item in required + optional if item.type_key == document.document_type),
            None,
        )
        reading = type_spec.reading if type_spec is not None else None
        fields = _field_specs(case.process_definition)
        current, sources = retract_document(
            {str(key): str(value) for key, value in (case.field_values or {}).items()},
            {str(key): dict(value) for key, value in (case.field_sources or {}).items() if isinstance(value, dict)},
            str(document.id),
        )
        report: dict = {
            "enabled": bool(reading and reading.enabled),
            "accepted": [],
            "skips": [],
            "conflicts": [],
            "blocked": None,
        }
        filled: list[str] = []
        if reading is not None and reading.enabled:
            case_ids = {
                current[spec.key].strip()
                for spec in fields
                if spec.field_type == "id_number" and current.get(spec.key, "").strip()
            }
            outcome = read_document(reading, document.extracted_text or "", fields, case_ids)
            writes, skips, conflicts = apply_proposals(current, outcome.proposals)
            for key, value in writes.items():
                current[key] = value
                sources[key] = {"source": "document", "document_id": str(document.id)}
                filled.append(key)
            accepted = {
                item.slot_key: item
                for item in outcome.proposals
                if item.value and item.slot_key in writes
            }
            report = {
                "enabled": True,
                "accepted": [
                    {"slot_key": key, "rule": accepted[key].rule, "label": accepted[key].label}
                    for key in filled
                    if key in accepted
                ],
                "skips": [
                    {
                        "slot_key": item.slot_key,
                        "reason": item.reason,
                        "rule": item.rule,
                        "label": item.label,
                    }
                    for item in skips
                    if item.reason
                ],
                "conflicts": [{"slot_key": key, "value": value} for key, value in conflicts],
                "blocked": outcome.blocked,
            }
        case.field_values = current
        case.field_sources = sources
        document.reading_report = report
        self._mark_data_completion(case)
        case.updated_at = utcnow()
        document.updated_at = utcnow()
        if filled:
            self.session.add(
                AuditLog(
                    case_id=case.id,
                    document_id=document.id,
                    action=AuditAction.FIELD_PREFILLED,
                    actor="system",
                    new_value={"fields": filled, "reader": document.document_type},
                )
            )
        await self.session.commit()

    async def chat(self, case_id: uuid.UUID, payload: ChatRequest) -> CaseWorkspace:
        await self.chat_begin(case_id, payload)
        case = await self._get_case(case_id)
        return self._workspace(case)

    async def chat_begin(
        self,
        case_id: uuid.UUID,
        payload: ChatRequest,
        *,
        reject_if_signed: bool = False,
        source: ValueSource = "office",
    ) -> ChatStart:
        case = await self._get_case(case_id)
        fields = _field_specs(case.process_definition)
        values = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        message = payload.message.strip()
        await self.session.commit()
        turn = await self.container.chat.respond(fields=fields, values=values, message=message)
        stamp = await self._commit_chat_turn(
            case_id, message, turn, reject_if_signed=reject_if_signed, source=source
        )
        return ChatStart(turn=turn, stamp=stamp)

    async def chat_finish(
        self,
        case_id: uuid.UUID,
        stamp: str,
        draft: str,
        final: str,
    ) -> CaseWorkspace:
        case = await self._locked_case(case_id)
        if case is None:
            raise NotFoundError("Case not found.")
        if final != draft:
            history = [dict(item) for item in list(case.chat_history or [])]
            for item in reversed(history):
                if (
                    item.get("role") == "assistant"
                    and item.get("created_at") == stamp
                    and item.get("content") == draft
                ):
                    item["content"] = final
                    case.chat_history = history
                    case.updated_at = utcnow()
                    await self.session.commit()
                    break
        stored = await self._get_case(case_id)
        return self._workspace(stored)

    async def _commit_chat_turn(
        self,
        case_id: uuid.UUID,
        message: str,
        turn: ChatTurn,
        *,
        reject_if_signed: bool = False,
        source: ValueSource = "office",
    ) -> str:
        case = await self._locked_case(case_id)
        if case is None:
            raise NotFoundError("Case not found.")
        if reject_if_signed and case.status == CaseStatus.SIGNED:
            raise ConflictError("This form is already signed.")
        current = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        merged = dict(current)
        merged.update(turn.values)
        if merged != current and case.status == CaseStatus.SIGNED:
            self._invalidate_signature(case, reason="A field changed after signing.")
            case.status = CaseStatus.FILLING
        _record_sources(case, current, merged, source)
        case.field_values = merged
        self._mark_data_completion(case)
        history = list(case.chat_history or [])
        stamp = utcnow().isoformat()
        history.append({"role": "user", "content": message, "created_at": stamp})
        history.append({"role": "assistant", "content": turn.reply, "created_at": stamp})
        case.chat_history = history[-100:]
        self._refresh_pipeline(case)
        case.updated_at = utcnow()
        await self.session.commit()
        return stamp

    async def _locked_case(self, case_id: uuid.UUID) -> Case | None:
        stmt = (
            case_query(self.scope)
            .where(Case.id == case_id)
            .options(selectinload(Case.documents), selectinload(Case.process_definition))
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        return await self.session.scalar(stmt)

    async def set_field(
        self,
        case_id: uuid.UUID,
        payload: FieldUpdateRequest,
        *,
        reject_if_signed: bool = False,
        source: ValueSource = "office",
    ) -> CaseWorkspace:
        case = await self._get_case(case_id)
        if reject_if_signed and case.status == CaseStatus.SIGNED:
            raise ConflictError("This form is already signed.")
        fields = _field_specs(case.process_definition)
        spec = next((item for item in fields if item.key == payload.key), None)
        if spec is None:
            raise BadRequestError(f"Unknown field '{payload.key}'.")
        result = validate_field(spec, payload.value)
        if not result.ok:
            raise BadRequestError(result.message)
        current = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        merged = dict(current)
        merged[spec.key] = result.normalized
        if merged != (case.field_values or {}) and case.status == CaseStatus.SIGNED:
            self._invalidate_signature(case, reason="A field changed after signing.")
            case.status = CaseStatus.FILLING
        _record_sources(case, current, merged, source)
        case.field_values = merged
        self._mark_data_completion(case)
        self._refresh_pipeline(case)
        case.updated_at = utcnow()
        await self.session.commit()
        return self._workspace(case)

    async def fill_and_sign(
        self,
        case_id: uuid.UUID,
        payload: FillAndSignRequest,
        context: SignerContext,
    ) -> CaseWorkspace:
        case = await self._get_case(case_id)
        return await self._sign_case(case, payload, actor=self.scope.actor, context=context)

    async def _sign_case(
        self,
        case: Case,
        payload: FillAndSignRequest,
        *,
        actor: str,
        context: SignerContext,
        before_fill: Callable[[], Awaitable[None]] | None = None,
        after_sign: Callable[[SignedArtifact], Awaitable[dict[str, object] | None]] | None = None,
        link_issued_at: datetime | None = None,
    ) -> CaseWorkspace:
        # Lock first so a concurrent signing cannot pass this check and replace the packet.
        locked = await self._locked_case(case.id)
        if locked is None:
            raise NotFoundError("Case not found.")
        case = locked
        if case.status == CaseStatus.SIGNED:
            raise ConflictError("This case is already signed.")
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

        form = _sign_form(case)
        if form is not None:
            missing = _unanchored_labels(fields, form, merged)
            if missing:
                raise ConflictError(
                    "These details have no place on the form: " + ", ".join(missing) + "."
                )

        signature = decode_signature_png(payload.signature_png_base64)
        layout = case.process_definition.layout or {}
        pdf_values: dict[str, str] = {}
        rtl_fields: set[str] = set()
        template = None
        rect = None
        if form is None:
            rect = layout.get("signature_rect")
            if not isinstance(rect, list) or len(rect) != 4:
                raise ConflictError("This process has no signature box configured.")
            template = self.container.settings.resolved_template_dir / case.process_definition.template_filename
            if not template.is_file():
                raise ConflictError("The form template is missing.")
            for spec in fields:
                value = merged.get(spec.key, "").strip()
                if not value:
                    continue
                pdf_values[spec.pdf_field_name] = value
                if spec.rtl or contains_hebrew(value):
                    rtl_fields.add(spec.pdf_field_name)

        packet_key, form_key = signed_keys(case.organization_id, case.id)
        _record_sources(
            case,
            {str(key): str(value) for key, value in (case.field_values or {}).items()},
            merged,
            "client" if actor == "signer" else "office",
        )
        case.field_values = merged
        self._mark_data_completion(case)
        if before_fill is not None:
            await before_fill()
        signed_at = utcnow()
        if not (case.case_reference or "").strip():
            case.case_reference = "DK-" + uuid.uuid4().hex[:12].upper()
        signer_id = f"DV-{uuid.uuid4().hex[:12].upper()}"
        consent = PORTAL_CONSENT_TEXT if context.channel == "portal" else OFFICE_CONSENT_TEXT
        certificate = CertificateData(
            document_title=case.process_definition.name,
            case_reference=case.case_reference,
            client_name=case.client_name,
            signer_verification_id=signer_id,
            channel=context.channel,
            ip=context.ip,
            user_agent=context.user_agent,
            consent_text=consent,
            created_at=as_utc(case.created_at) or signed_at,
            data_completed_at=as_utc(case.data_completed_at),
            link_issued_at=as_utc(link_issued_at) if link_issued_at is not None else None,
            signed_at=signed_at,
        )
        created_keys: list[str] = []
        commit_started = False
        try:
            audit_fields: list[str]
            form_document_id: str | None = None
            with tempfile.TemporaryDirectory() as work:
                output = Path(work) / "signed.pdf"
                if form is None:
                    artifact = self.container.pdf_filler.fill_and_sign(
                        template_path=template,
                        output_path=output,
                        values=pdf_values,
                        signature_png=signature,
                        signature_rect=[float(item) for item in rect],
                        page_index=int(layout.get("page_index", 0)),
                        rtl_fields=rtl_fields,
                        certificate=certificate,
                        signed_at=signed_at,
                    )
                    audit_fields = sorted(pdf_values)
                else:
                    values, rtl_names = _fill_inputs(case, form)
                    async with self.container.store.local_copy(form.storage_path) as source:
                        from app.services.flat_form import sign_flat_form

                        artifact = await asyncio.to_thread(
                            sign_flat_form,
                            self.container.pdf_filler,
                            source_path=source,
                            output_path=output,
                            anchors=form.form_anchors or [],
                            values=values,
                            rtl_names=rtl_names,
                            signature_png=signature,
                            signature_labels=[str(item) for item in layout["signature_labels"]],
                            certificate=certificate,
                            signed_at=signed_at,
                        )
                    audit_fields = sorted(values)
                    form_document_id = str(form.id)
                created_keys.append(form_key)
                with artifact.content_path.open("rb") as handle:
                    await self.container.store.upload_file(form_key, handle, "application/pdf")
                created_keys.append(packet_key)
                with output.open("rb") as handle:
                    await self.container.store.upload_file(packet_key, handle, "application/pdf")
            case.output_path = packet_key
            case.content_path = form_key
            case.content_sha256 = artifact.content_sha256
            case.file_sha256 = artifact.file_sha256
            case.signer_verification_id = artifact.signer_verification_id
            case.signed_at = signed_at
            case.certificate_data = CaseCertificate(
                case_reference=case.case_reference,
                channel=context.channel,
                signer_ip=context.ip,
                signer_user_agent=context.user_agent,
                consent_text=consent,
                created_at=certificate.created_at,
                data_completed_at=certificate.data_completed_at,
                link_issued_at=certificate.link_issued_at,
                signed_at=signed_at,
                total_pages=artifact.total_pages,
            ).model_dump(mode="json")
            case.status = CaseStatus.SIGNED
            case.pipeline_stage = "signed"
            case.pipeline_message = "Signed packet is ready."
            case.updated_at = utcnow()
            if context.channel == "office":
                await self.session.execute(
                    update(SigningLink)
                    .where(
                        SigningLink.case_id == case.id,
                        SigningLink.revoked_at.is_(None),
                        SigningLink.completed_at.is_(None),
                    )
                    .values(revoked_at=utcnow(), revoke_reason="signed_by_office")
                )
            extra = await after_sign(artifact) if after_sign is not None else None
            recorded = {
                "output_path": case.output_path,
                "fields": audit_fields,
                "content_sha256": artifact.content_sha256,
                "file_sha256": artifact.file_sha256,
                "signer_verification_id": artifact.signer_verification_id,
                "ip": context.ip,
                "user_agent": context.user_agent,
                "channel": context.channel,
                "case_reference": case.case_reference,
            }
            if form_document_id is not None:
                recorded["form_document_id"] = form_document_id
            if extra:
                recorded.update(extra)
            self.session.add(
                AuditLog(
                    case_id=case.id,
                    action=AuditAction.FILL_AND_SIGN,
                    actor=actor,
                    new_value=recorded,
                )
            )
            commit_started = True
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            if commit_started:
                logger.error("Signing commit failed; retained objects %s", created_keys)
            else:
                for key in created_keys:
                    try:
                        await self.container.store.delete_file(key)
                    except Exception:
                        logger.exception("Could not delete object %s after a failed signing", key)
            raise
        stored = await self._get_case(case.id)
        return self._workspace(stored)

    async def signed_pdf(self, case_id: uuid.UUID) -> tuple[bytes, str]:
        case = await self._get_case(case_id)
        if case.status != CaseStatus.SIGNED or not case.output_path:
            raise NotFoundError("This case has no signed document yet.")
        try:
            data = await self.container.store.download_file(case.output_path)
        except ObjectMissingError as exc:
            raise NotFoundError("The signed document file is missing.") from exc
        if case.file_sha256 and hashlib.sha256(data).hexdigest() != case.file_sha256:
            logger.error("Signed file integrity check failed for case %s", case.id)
            raise SignedFileIntegrityError()
        return data, f"{_safe_stem(case.name)}-signed.pdf"

    async def certificate_pdf(self, case_id: uuid.UUID) -> bytes:
        case = await self._get_case(case_id)
        if case.status != CaseStatus.SIGNED or not case.output_path or not case.certificate_data:
            raise NotFoundError("This case has no certificate.")
        data, _filename = await self.signed_pdf(case_id)
        document = fitz.open(stream=data, filetype="pdf")
        try:
            if document.page_count < 1:
                raise NotFoundError("This case has no certificate.")
            single = fitz.open()
            try:
                single.insert_pdf(document, from_page=document.page_count - 1, to_page=document.page_count - 1)
                return single.tobytes()
            finally:
                single.close()
        finally:
            document.close()

    def _mark_data_completion(self, case: Case) -> None:
        fields = _field_specs(case.process_definition)
        values = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        if missing_required_fields(fields, values):
            case.data_completed_at = None
        elif case.data_completed_at is None:
            case.data_completed_at = utcnow()

    async def document_file(self, case_id: uuid.UUID, document_id: uuid.UUID) -> tuple[ObjectReader, str, str]:
        case = await self._get_case(case_id)
        document = next((item for item in case.documents if item.id == document_id), None)
        if document is None:
            raise NotFoundError("Document not found on this case.")
        try:
            reader = await self.container.store.open_read(document.storage_path)
        except ObjectMissingError as exc:
            raise NotFoundError("The document file is missing.") from exc
        return reader, document.mime_type, document.original_filename

    async def set_document_role(
        self,
        case_id: uuid.UUID,
        document_id: uuid.UUID,
        payload: DocumentRoleUpdate,
    ) -> DocumentRoleRead:
        case = await self._get_case(case_id)
        if case.status == CaseStatus.SIGNED:
            raise ConflictError("This case is already signed.")
        document = next((item for item in case.documents if item.id == document_id), None)
        if document is None:
            raise NotFoundError("Document not found on this case.")
        if payload.role == "form" and document.mime_type.startswith("image/"):
            raise ConflictError(
                "A picture of a form has no text to place details on. Upload the form as a PDF."
            )
        if payload.role == "form" and (document.mime_type != "application/pdf" or not document.form_anchors):
            raise ConflictError("Only a PDF with form fields can be marked as a form.")
        previous = {"role": document.role, "display_title": document.display_title}
        changed = document.role != payload.role
        if changed:
            self._retract(case, [document])
        document.role = payload.role
        if payload.display_title is not None:
            document.display_title = payload.display_title
        document.updated_at = utcnow()
        case.updated_at = utcnow()
        self.session.add(
            AuditLog(
                case_id=case.id,
                document_id=document.id,
                action=AuditAction.DOCUMENT_ROLE_CHANGED,
                actor=self.scope.actor,
                previous_value=previous,
                new_value={"role": document.role, "display_title": document.display_title},
            )
        )
        await self.session.commit()
        result = DocumentRoleRead(
            document_id=document.id,
            role=document.role,  # type: ignore[arg-type]
            display_title=document.display_title,
        )
        if changed:
            await self._reread(case_id)
        return result

    async def filled_preview(self, case_id: uuid.UUID, document_id: uuid.UUID) -> bytes:
        case = await self._get_case(case_id)
        document = next((item for item in case.documents if item.id == document_id), None)
        if document is None:
            raise NotFoundError("Document not found on this case.")
        if document.role != "form":
            raise ConflictError("This document is not a form.")
        filled = await self._fill_original(case, document)
        return await asyncio.to_thread(self.container.pdf_filler.stamp_draft, filled.pdf_bytes)

    async def fill_report(self, case_id: uuid.UUID, document_id: uuid.UUID) -> FillReport:
        case = await self._get_case(case_id)
        document = next((item for item in case.documents if item.id == document_id), None)
        if document is None:
            raise NotFoundError("Document not found on this case.")
        filled = await self._fill_original(case, document)
        stored = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        sources = _field_sources(case)
        pending: dict[tuple[str, int], list[str]] = {}
        for item in filled.fields:
            pending.setdefault((item.field_name, item.page), []).append(item.status)
        rows: list[FillReportField] = []
        for anchor in _bound_anchors(document):
            name = str(anchor.get("field_name") or "")
            page = int(anchor.get("page") or 0)
            key = str(anchor.get("slot_key"))
            source = sources.get(key)
            if not stored.get(key, "").strip():
                status = "awaiting_value"
            else:
                queue = pending.get((name, page), [])
                status = queue.pop(0) if queue else "mismatch"
            rows.append(
                FillReportField(
                    field_name=name,
                    page=page,
                    slot_key=key,
                    status=status,  # type: ignore[arg-type]
                    source=source.source if source is not None else None,
                )
            )
        return FillReport(document_id=document.id, fields=rows)

    async def intake(self, case_id: uuid.UUID) -> IntakeSummary:
        case = await self._get_case(case_id)
        fields = _field_specs(case.process_definition)
        values = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        forms: list[IntakeForm] = []
        documents = sorted(case.documents, key=lambda item: (item.created_at, str(item.id)))
        for document in documents:
            anchors = [anchor for anchor in (document.form_anchors or []) if isinstance(anchor, dict)]
            if document.mime_type != "application/pdf" or not anchors:
                continue
            bound = [anchor for anchor in anchors if anchor.get("slot_key")]
            role = document.role if document.role in {"evidence", "form"} else "evidence"
            forms.append(
                IntakeForm(
                    document_id=document.id,
                    filename=document.original_filename,
                    role=role,  # type: ignore[arg-type]
                    display_title=document.display_title,
                    widgets_total=len(anchors),
                    bound=len(bound),
                    bound_empty=sum(1 for anchor in bound if anchor.get("empty")),
                    unbound=len(anchors) - len(bound),
                )
            )
        return IntakeSummary(
            forms=forms,
            missing_documents=self._gap(case).missing,
            open_slots=_open_slots(case, fields, values),
            prompt_he=INTAKE_PROMPT_HE,
            prompt_en=INTAKE_PROMPT_EN,
        )

    async def _fill_original(self, case: Case, document: Document) -> FilledForm:
        values, rtl_names = _fill_inputs(case, document)
        try:
            async with self.container.store.local_copy(document.storage_path) as path:
                filled = await asyncio.to_thread(
                    self.container.pdf_filler.fill_case_form,
                    source_path=path,
                    values=values,
                    rtl_names=rtl_names,
                )
            flat = await asyncio.to_thread(
                self.container.pdf_filler.fill_flat,
                filled.pdf_bytes,
                document.form_anchors or [],
                values,
            )
            return FilledForm(pdf_bytes=flat.pdf_bytes, fields=[*filled.fields, *flat.fields])
        except ObjectMissingError as exc:
            raise NotFoundError("The document file is missing.") from exc

    async def _get_case(self, case_id: uuid.UUID) -> Case:
        stmt = (
            case_query(self.scope)
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
            field_sources=_field_sources(case),
            missing_fields=missing_required_fields(fields, values),
            open_slots=_open_slots(case, fields, values),
            unbound_anchors=_unbound_anchors(case),
            ready_to_sign=not blockers and case.status != CaseStatus.SIGNED,
            signing_blockers=blockers,
            consent_text=OFFICE_CONSENT_TEXT,
            readings=_reading_reports(case),
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
            if not _is_signed_form(case, document)
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
            audit=self._audit(case),
        )

    def _audit(self, case: Case) -> CaseAudit:
        signed = case.status == CaseStatus.SIGNED and bool(case.output_path)
        if not signed:
            return CaseAudit(
                is_signed=False,
                signed_at=None,
                signer_verification_id=None,
                content_sha256=None,
                file_sha256=None,
                certificate=None,
            )
        signed_at = case.signed_at
        if signed_at is not None and signed_at.tzinfo is None:
            signed_at = signed_at.replace(tzinfo=timezone.utc)
        certificate = None
        if case.certificate_data:
            certificate = CaseCertificate.model_validate(case.certificate_data)
        return CaseAudit(
            is_signed=True,
            signed_at=signed_at,
            signer_verification_id=case.signer_verification_id,
            content_sha256=case.content_sha256,
            file_sha256=case.file_sha256,
            certificate=certificate,
        )

    def _invalidate_signature(self, case: Case, *, reason: str) -> None:
        previous = {
            "signer_verification_id": case.signer_verification_id,
            "content_sha256": case.content_sha256,
            "file_sha256": case.file_sha256,
            "output_path": case.output_path,
            "signed_at": case.signed_at.isoformat() if case.signed_at else None,
        }
        if not any(previous.values()):
            case.signed_at = None
            return
        previous["case_reference"] = case.case_reference
        previous["content_path"] = case.content_path
        # The audit row is the record of where the superseded packet lives.
        case.output_path = None
        case.content_path = None
        case.certificate_data = None
        case.content_sha256 = None
        case.file_sha256 = None
        case.signer_verification_id = None
        case.signed_at = None
        self.session.add(
            AuditLog(
                case_id=case.id,
                action=AuditAction.SIGNATURE_INVALIDATED,
                actor=self.scope.actor,
                previous_value=previous,
                notes=reason,
            )
        )


def _reading_reports(case: Case) -> list[DocumentReadingReport]:
    reports: list[DocumentReadingReport] = []
    for document in sorted(case.documents, key=lambda item: (item.created_at, str(item.id))):
        raw = document.reading_report
        if not isinstance(raw, dict):
            continue
        reports.append(
            DocumentReadingReport(
                document_id=document.id,
                filename=document.original_filename,
                document_type=document.document_type,
                enabled=bool(raw.get("enabled")),
                accepted=[SlotHit.model_validate(item) for item in raw.get("accepted") or []],
                skips=[SlotSkip.model_validate(item) for item in raw.get("skips") or []],
                conflicts=[SlotConflict.model_validate(item) for item in raw.get("conflicts") or []],
                blocked=raw.get("blocked"),
            )
        )
    return reports


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


def _record_sources(case: Case, before: dict[str, str], after: dict[str, str], source: ValueSource) -> None:
    """Mark every slot whose value changed with where the new value came from."""
    changed = [key for key, value in after.items() if before.get(key) != value]
    if not changed:
        return
    sources = dict(case.field_sources or {})
    for key in changed:
        sources[key] = {"source": source, "document_id": None}
    case.field_sources = sources


def _field_sources(case: Case) -> dict[str, FieldSource]:
    sources: dict[str, FieldSource] = {}
    for key, raw in (case.field_sources or {}).items():
        try:
            sources[str(key)] = FieldSource.model_validate(raw)
        except Exception:
            continue
    return sources


def _sign_form(case: Case) -> Document | None:
    """The one uploaded form this process signs, or None when it signs a template."""
    layout = case.process_definition.layout or {}
    if layout.get("sign_source") != "uploaded_form":
        return None
    forms = [
        document
        for document in case.documents
        if document.role == "form" and document.status != DocumentStatus.FAILED
    ]
    if len(forms) != 1:
        raise ConflictError("Mark exactly one uploaded form before signing.")
    return forms[0]


_STALLED_AFTER_SECONDS = 120


def _drawer_type(case: Case, document_type: str | None) -> str | None:
    """The document type named with an upload, checked against this process."""
    chosen = (document_type or "").strip()
    if not chosen:
        return None
    required, optional = _document_specs(case.process_definition)
    if chosen not in {item.type_key for item in required + optional}:
        raise BadRequestError("That document type is not part of this process.")
    return chosen


def _drawer_role(role: str | None) -> str | None:
    chosen = (role or "").strip()
    if not chosen:
        return None
    if chosen not in {"evidence", "form"}:
        raise BadRequestError("A file is either evidence or a form.")
    return chosen


def _is_stalled(document: Document) -> bool:
    touched = document.updated_at or document.created_at
    if touched is None:
        return True
    if touched.tzinfo is None:
        touched = touched.replace(tzinfo=utcnow().tzinfo)
    return (utcnow() - touched).total_seconds() > _STALLED_AFTER_SECONDS


def _drawer_occupants(
    case: Case,
    chosen_type: str | None,
    chosen_role: str | None,
    keep: set[uuid.UUID],
) -> list[Document]:
    """The saved files already filed where the new upload is going."""
    found: list[Document] = []
    for document in case.documents:
        if document.id is None or document.id in keep:
            continue
        in_drawer = (
            chosen_type is not None
            and document.document_type == chosen_type
            and (
                document.status == DocumentStatus.CLASSIFIED
                or document.classification_source == ClassificationSource.HUMAN
            )
        )
        is_form = chosen_role == "form" and document.role == "form"
        if in_drawer or is_form:
            found.append(document)
    return found


def _has_stalled_documents(case: Case) -> bool:
    """Files left unread by a job that never finished, so the next upload picks them up."""
    now = utcnow()
    for document in case.documents:
        if document.status not in {DocumentStatus.UPLOADED, DocumentStatus.PROCESSING}:
            continue
        touched = as_utc(document.updated_at) or as_utc(document.created_at)
        if touched is None or (now - touched).total_seconds() > _STALLED_AFTER_SECONDS:
            return True
    return False


def _is_signed_form(case: Case, document: Document) -> bool:
    """The form a process signs is not evidence: once read, it needs no document type."""
    layout = case.process_definition.layout or {}
    return (
        layout.get("sign_source") == "uploaded_form"
        and document.role == "form"
        and document.status in {DocumentStatus.CLASSIFIED, DocumentStatus.NEEDS_REVIEW}
    )


def _unanchored_labels(fields: list[FieldSpec], form: Document, values: dict[str, str]) -> list[str]:
    """Required slots that have a value but no drawn place on the uploaded form."""
    bound = {str(anchor.get("slot_key")) for anchor in _bound_anchors(form)}
    return [
        spec.label_he or spec.label
        for spec in fields
        if spec.required and values.get(spec.key, "").strip() and spec.key not in bound
    ]


def _bound_anchors(document: Document) -> list[dict]:
    return [
        anchor
        for anchor in (document.form_anchors or [])
        if isinstance(anchor, dict) and anchor.get("slot_key")
    ]


def _fill_inputs(case: Case, document: Document) -> tuple[dict[str, str], set[str]]:
    """Map each bound widget that already has a slot value to the text that fills it."""
    specs = {spec.key: spec for spec in _field_specs(case.process_definition)}
    stored = {str(key): str(value) for key, value in (case.field_values or {}).items()}
    values: dict[str, str] = {}
    rtl_names: set[str] = set()
    for anchor in _bound_anchors(document):
        key = str(anchor.get("slot_key"))
        raw = stored.get(key, "").strip()
        if not raw:
            continue
        name = str(anchor.get("field_name") or "")
        if not name:
            continue
        values[name] = raw
        spec = specs.get(key)
        if (spec is not None and spec.rtl) or contains_hebrew(raw):
            rtl_names.add(name)
    return values, rtl_names


def _anchor_documents(case: Case) -> list[tuple[Document, dict]]:
    pairs: list[tuple[Document, dict]] = []
    for document in sorted(case.documents, key=lambda item: item.created_at):
        if document.status == DocumentStatus.FAILED:
            continue
        for anchor in document.form_anchors or []:
            if isinstance(anchor, dict):
                pairs.append((document, anchor))
    return pairs


def _open_slots(case: Case, fields: list[FieldSpec], values: dict[str, str]) -> list[OpenSlot]:
    """Required slots with no value. Each lists the empty widgets bound to it, if any."""
    pairs = _anchor_documents(case)
    slots: list[OpenSlot] = []
    for spec in missing_required_fields(fields, values):
        anchors = [
            FormAnchorRef(
                document_id=document.id,
                filename=document.original_filename,
                field_name=str(anchor.get("field_name", "")),
                page=int(anchor.get("page", 0)),
                rect=[float(item) for item in anchor.get("rect", [])],
                match=anchor.get("match"),
            )
            for document, anchor in pairs
            if anchor.get("slot_key") == spec.key and anchor.get("empty") and anchor.get("match")
        ]
        slots.append(
            OpenSlot(
                key=spec.key,
                label=spec.label,
                label_he=spec.label_he,
                anchors=anchors,
                why=why_items(case, spec),
            )
        )
    return slots


def _unbound_anchors(case: Case) -> list[UnboundAnchor]:
    return [
        UnboundAnchor(
            document_id=document.id,
            filename=document.original_filename,
            field_name=str(anchor.get("field_name", "")),
            page=int(anchor.get("page", 0)),
            empty=bool(anchor.get("empty")),
        )
        for document, anchor in _anchor_documents(case)
        if not anchor.get("slot_key")
    ]
