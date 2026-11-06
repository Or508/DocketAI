import asyncio

from app.schemas.process import FieldSpec
from app.services.chat_collector import ChatCollector

_NAME = FieldSpec(
    key="full_name",
    label="Full legal name",
    label_he=None,
    field_type="text",
    pdf_field_name="full_name",
    required=True,
    rtl=False,
)


def test_unconfigured_clerk_uses_the_next_empty_field() -> None:
    class Off:
        configured = False

        async def extract_fields(self, **kwargs):
            raise AssertionError("extract should not run without a key")

    turn = asyncio.run(
        ChatCollector(Off()).respond(fields=[_NAME], values={}, message="Dana Cohen")  # type: ignore[arg-type]
    )
    assert turn.values == {"full_name": "Dana Cohen"}
    assert turn.accepted == ["Full legal name"]
    assert "Dana Cohen" not in turn.reply


def test_configured_failure_does_not_store_the_message() -> None:
    class Boom:
        configured = True

        async def extract_fields(self, **kwargs):
            raise RuntimeError("model down")

    turn = asyncio.run(
        ChatCollector(Boom()).respond(fields=[_NAME], values={}, message="what's next?")  # type: ignore[arg-type]
    )
    assert turn.values == {}
    assert turn.accepted == []
    assert "could not read" in turn.reply
    assert "what's next" not in turn.reply
