import hashlib
import sys
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import session_scope
from app.domain.case_scope import CaseScope, case_query
from app.models.case import Case
from app.models.document import Document
from app.services.object_store import LocalObjectStore, ObjectMissingError, build_object_store
from app.services.storage_paths import resolve_stored


@dataclass(frozen=True)
class _Item:
    kind: str
    row_id: UUID
    organization_id: UUID
    stored: str
    expected_hash: str | None


def _relative(root, stored: str) -> str | None:
    resolved = resolve_stored(root, stored)
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


async def migrate_storage(*, dry_run: bool) -> int:
    settings = get_settings()
    if settings.storage_backend != "s3":
        print("migrate-storage requires storage_backend=s3.", file=sys.stderr)
        return 1
    root = settings.resolved_storage_dir
    source = LocalObjectStore(root)
    destination = build_object_store(settings)
    migrated = skipped = missing = mismatched = 0

    async with session_scope() as session:
        cases = list(
            await session.scalars(case_query(CaseScope.system()).options(selectinload(Case.documents)))
        )
        items: list[_Item] = []
        for case in cases:
            for document in case.documents:
                items.append(
                    _Item("document", document.id, case.organization_id, document.storage_path, document.content_hash)
                )
            if case.output_path:
                items.append(_Item("output", case.id, case.organization_id, case.output_path, case.file_sha256))
            if case.content_path:
                items.append(_Item("content", case.id, case.organization_id, case.content_path, case.content_sha256))

    for item in items:
        if item.stored.startswith("org/"):
            skipped += 1
            continue
        relative = _relative(root, item.stored)
        if relative is None:
            print(f"skipped outside root: {item.stored}", file=sys.stderr)
            skipped += 1
            continue
        try:
            payload = await source.get_bytes(relative)
        except ObjectMissingError:
            print(f"missing: {item.stored}", file=sys.stderr)
            missing += 1
            continue
        digest = hashlib.sha256(payload).hexdigest()
        if item.expected_hash and digest != item.expected_hash:
            print(f"mismatched: {item.stored}", file=sys.stderr)
            mismatched += 1
            continue
        target = f"org/{item.organization_id}/{relative}"
        if dry_run:
            migrated += 1
            continue
        staged = root / ".migrate-stage"
        staged.mkdir(parents=True, exist_ok=True)
        temporary = staged / "object.bin"
        temporary.write_bytes(payload)
        try:
            await destination.put_file(target, temporary, "application/octet-stream")
            copied = await destination.get_bytes(target)
        finally:
            temporary.unlink(missing_ok=True)
        if hashlib.sha256(copied).hexdigest() != digest:
            print(f"mismatched: {item.stored}", file=sys.stderr)
            mismatched += 1
            continue
        async with session_scope() as session:
            if item.kind == "document":
                row = await session.get(Document, item.row_id)
                if row is None:
                    missing += 1
                    continue
                row.storage_path = target
            else:
                case = await session.scalar(case_query(CaseScope.system()).where(Case.id == item.row_id))
                if case is None:
                    missing += 1
                    continue
                if item.kind == "output":
                    case.output_path = target
                else:
                    case.content_path = target
            await session.commit()
        migrated += 1

    print(f"migrated={migrated} skipped={skipped} missing={missing} mismatched={mismatched}")
    return 1 if missing or mismatched else 0
