"""Names and audit rows for the office archive bundle."""

import re
from typing import Any

# Both onboarding processes fill a Form 101, so their exported form carries that name.
_FORM_STEMS = {"onboarding": "form_101", "employee_onboarding": "form_101"}


def form_names(process_key: str) -> tuple[str, str]:
    """The archive names of a case's form, signed and draft, after the form its process fills."""
    stem = _FORM_STEMS.get(process_key) or re.sub(r"[^a-z0-9_]+", "_", process_key.lower()).strip("_") or "form"
    return f"{stem}_signed.pdf", f"{stem}_draft.pdf"


MANIFEST_NAME = "verification_manifest.json"
SOURCE_FOLDER = "source_documents"

# Audit details that identify records and files, never a person. Anything else an
# audit row holds (addresses, browser strings, storage paths, free text) stays out.
_SAFE_KEYS = frozenset(
    {
        "at_upload",
        "case_reference",
        "channel",
        "confidence",
        "consent",
        "content_hash",
        "content_sha256",
        "document_id",
        "document_type",
        "documents",
        "expires_at",
        "fields",
        "file_sha256",
        "form_document_id",
        "form_pdf",
        "form_pdf_sha256",
        "link_id",
        "needs_human_review",
        "note_id",
        "reader",
        "revoke_reason",
        "revoked_links",
        "role",
        "signed_at",
        "signer_verification_id",
        "status",
        "superseded_content_sha256",
        "superseded_signed_at",
        "superseded_signed_pdf_sha256",
        "superseded_verification_id",
    }
)

# Notes on these actions are fixed sentences written by the system, not by a person.
_SYSTEM_NOTE_ACTIONS = frozenset({"signature_invalidated"})

_UNSAFE_NAME = re.compile(r'[\x00-\x1f<>:"/\\|?*]+')


def safe_details(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    kept = {str(key): item for key, item in value.items() if key in _SAFE_KEYS}
    return kept or None


def audit_entry(
    *,
    event_id: object,
    action: str,
    actor: str,
    created_at: str | None,
    document_id: object | None,
    previous_value: object,
    new_value: object,
    notes: str | None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": str(event_id),
        "action": action,
        "actor": actor,
        "created_at": created_at,
        "document_id": str(document_id) if document_id is not None else None,
        "previous": safe_details(previous_value),
        "details": safe_details(new_value),
    }
    if notes and action in _SYSTEM_NOTE_ACTIONS:
        entry["notes"] = notes
    return entry


def timeline_metadata(previous_value: object, new_value: object) -> dict[str, Any]:
    """One flat record per event: the safe details, under the names the timeline shows.

    What an event set comes from its new value. A signature or file it replaced or
    removed is named as superseded, so the two are never confused.
    """
    before = safe_details(previous_value) or {}
    after = safe_details(new_value) or {}
    metadata: dict[str, Any] = {**before, **after}
    if after.get("signer_verification_id"):
        metadata["verification_id"] = after["signer_verification_id"]
    if before.get("signer_verification_id") and "superseded_verification_id" not in metadata:
        metadata["superseded_verification_id"] = before["signer_verification_id"]
    if before.get("file_sha256") and "superseded_signed_pdf_sha256" not in metadata:
        metadata["superseded_signed_pdf_sha256"] = before["file_sha256"]
    for key in ("signer_verification_id", "file_sha256", "content_sha256"):
        if key in before and key not in after:
            metadata.pop(key, None)
    digest = (
        after.get("file_sha256")
        or after.get("content_hash")
        or after.get("form_pdf_sha256")
        or before.get("content_hash")
    )
    if digest:
        metadata["sha256"] = digest
    return metadata


def source_name(label: str, original_filename: str, taken: set[str]) -> str:
    """`source_documents/{label}_{filename}`, flattened to one path segment and made unique."""
    filename = _UNSAFE_NAME.sub("_", original_filename).strip(" .") or "file"
    prefix = _UNSAFE_NAME.sub("_", label).strip(" .") or "document"
    base = f"{prefix}_{filename}"[:180]
    candidate = base
    counter = 2
    while candidate.casefold() in taken:
        stem, dot, suffix = base.rpartition(".")
        candidate = f"{stem}_{counter}.{suffix}" if dot else f"{base}_{counter}"
        counter += 1
    taken.add(candidate.casefold())
    return f"{SOURCE_FOLDER}/{candidate}"
