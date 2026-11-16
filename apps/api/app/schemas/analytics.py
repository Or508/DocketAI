from pydantic import BaseModel


class ProcessBreakdown(BaseModel):
    process_type: str
    total: int
    filling: int
    waiting_for_signature: int
    signed: int


class AnalyticsSummary(BaseModel):
    """Counts for one office. total = filling + waiting_for_signature + signed."""

    total_cases: int
    # Unsigned, with details still missing or the client not yet asked to sign.
    filling_cases: int
    # Unsigned, and either every detail is in place or a signing link is open.
    waiting_for_signature_cases: int
    signed_cases: int
    # Mean hours from opening a case to its signature, over the signed cases.
    avg_hours_to_sign: float | None
    # Of every filled field, the share a document supplied rather than a person typing it.
    auto_extraction_rate_pct: float
    by_process_type: list[ProcessBreakdown]
    # The raw case status, as the cabinet stores it.
    by_status: dict[str, int]
