from uuid import UUID, uuid4


def document_key(organization_id: UUID, case_id: UUID, suffix: str) -> str:
    return f"org/{organization_id}/cases/{case_id}/documents/{uuid4().hex}{suffix}"


def signed_keys(organization_id: UUID, case_id: UUID) -> tuple[str, str]:
    folder = uuid4().hex
    base = f"org/{organization_id}/cases/{case_id}/signed/{folder}"
    return f"{base}/signed.pdf", f"{base}/form.pdf"


def validate_key(key: str) -> None:
    if not key or key.startswith("/") or "\\" in key:
        raise ValueError("Invalid object key.")
    if len(key) >= 2 and key[1] == ":":
        raise ValueError("Invalid object key.")
    for segment in key.split("/"):
        if segment in {"", ".", ".."}:
            raise ValueError("Invalid object key.")
