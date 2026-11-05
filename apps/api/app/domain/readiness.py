from app.domain.enums import CaseStatus


def signing_blockers(
    *,
    status: CaseStatus,
    missing_labels: list[str],
    unrecognized_count: int,
    in_progress_count: int,
    missing_field_labels: list[str],
) -> list[str]:
    reasons: list[str] = []
    if in_progress_count or status == CaseStatus.PROCESSING:
        reasons.append("Documents are still processing.")
    if unrecognized_count == 1:
        reasons.append("1 document still needs review.")
    elif unrecognized_count:
        reasons.append(f"{unrecognized_count} documents still need review.")
    if missing_labels:
        reasons.append("Missing required documents: " + ", ".join(missing_labels) + ".")
    if missing_field_labels:
        reasons.append("Still need: " + ", ".join(missing_field_labels) + ".")
    if status == CaseStatus.FAILED and not reasons:
        reasons.append("The case failed processing.")
    if status == CaseStatus.DRAFT and not reasons:
        reasons.append("Upload the document bundle before signing.")
    return reasons
