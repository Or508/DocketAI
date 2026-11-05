from app.schemas.process import FieldSpec
from app.services.field_validator import (
    missing_required_fields,
    normalize_israeli_id,
    validate_field,
)


def _spec(field_type: str, key: str = "value") -> FieldSpec:
    return FieldSpec(
        key=key,
        label=key,
        field_type=field_type,  # type: ignore[arg-type]
        pdf_field_name=key,
    )


def test_israeli_id_checksum() -> None:
    assert normalize_israeli_id("123456782") == "123456782"
    assert normalize_israeli_id("123-456-782") == "123456782"
    assert normalize_israeli_id("123456783") is None
    assert normalize_israeli_id("000000000") is None


def test_field_formats() -> None:
    email = validate_field(_spec("email"), "Ada@Example.com")
    assert email.ok and email.normalized == "ada@example.com"
    phone = validate_field(_spec("phone"), "050-123-4567")
    assert phone.normalized == "0501234567"
    date = validate_field(_spec("date"), "04/11/2026")
    assert date.normalized == "2026-11-04"
    assert validate_field(_spec("date"), "2026-13-40").ok is False


def test_missing_required_fields_ignores_optional() -> None:
    specs = [
        FieldSpec(key="full_name", label="Full legal name", field_type="text", pdf_field_name="full_name"),
        FieldSpec(
            key="note",
            label="Note",
            field_type="text",
            pdf_field_name="note",
            required=False,
        ),
    ]
    missing = missing_required_fields(specs, {"note": "optional"})
    assert [item.key for item in missing] == ["full_name"]
