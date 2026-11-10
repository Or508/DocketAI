from enum import Enum


class CaseStatus(str, Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    FILLING = "filling"
    SIGNED = "signed"
    FAILED = "failed"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    CLASSIFIED = "classified"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class ClassificationSource(str, Enum):
    PENDING = "pending"
    AUTO = "auto"
    HUMAN = "human"


class AuditAction(str, Enum):
    AUTO_CLASSIFY = "auto_classify"
    MANUAL_CLASSIFY = "manual_classify"
    FILL_AND_SIGN = "fill_and_sign"
    SIGNATURE_INVALIDATED = "signature_invalidated"
    SIGNING_LINK_CREATED = "signing_link_created"
    SIGNING_LINK_REVOKED = "signing_link_revoked"
    FIELD_PREFILLED = "field_prefilled"
