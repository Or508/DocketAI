"""Production refuses development defaults, and email can go out through the SES API."""

import asyncio

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.email_sender import EmailError, EmailSender, build_message

SAFE = {
    "environment": "production",
    "database_url": "postgresql+asyncpg://docket:secret@db.internal:5432/docketai",
    "storage_backend": "s3",
    "s3_bucket": "docketflow-files",
    "s3_region": "il-central-1",
    "email_backend": "ses",
    "email_from": "office@docketflow.example",
    "public_web_url": "https://app.docketflow.example",
    "mfa_secret_key": "ZmFrZS1rZXktZm9yLXRlc3RzLW9ubHktMzItYnl0ZXM=",
    "auto_create_schema": False,
}


def _settings(**overrides) -> Settings:
    # _env_file=None: a developer's own .env must not change what these tests see.
    return Settings(_env_file=None, **{**SAFE, **overrides})


def test_safe_production_settings_start() -> None:
    settings = _settings()
    assert settings.production_problems() == []
    assert settings.resolved_ses_region == "il-central-1"


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"database_url": "sqlite+aiosqlite:///./data/docketai.db"}, "DATABASE_URL"),
        ({"storage_backend": "local"}, "STORAGE_BACKEND"),
        ({"email_backend": "outbox"}, "EMAIL_BACKEND"),
        ({"email_from": ""}, "EMAIL_FROM"),
        ({"public_web_url": "http://localhost:3000"}, "PUBLIC_WEB_URL"),
        ({"public_web_url": "http://app.docketflow.example"}, "PUBLIC_WEB_URL"),
        ({"mfa_secret_key": ""}, "MFA_SECRET_KEY"),
        ({"auto_create_schema": True}, "AUTO_CREATE_SCHEMA"),
        ({"mfa_secret_key": "too-short"}, "44 characters"),
    ],
)
def test_production_refuses_each_development_default(override: dict, fragment: str) -> None:
    with pytest.raises(ValidationError, match=fragment):
        _settings(**override)


def test_a_standard_base64_key_from_render_works_like_the_urlsafe_one() -> None:
    import base64

    from cryptography.fernet import Fernet

    raw = bytes(range(250, 256)) + bytes(26)  # bytes that encode to + and / in standard base64
    standard = base64.b64encode(raw).decode()
    assert "+" in standard or "/" in standard
    settings = _settings(mfa_secret_key=standard)
    assert settings.mfa_secret_key == base64.urlsafe_b64encode(raw).decode()
    Fernet(settings.mfa_secret_key.encode())


def test_development_keeps_its_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.production_problems()  # listed, but nothing refuses to start


class _FakeSes:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[dict] = []
        self.fail = fail

    def send_email(self, **request) -> dict:
        if self.fail:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "MessageRejected", "Message": "Email address is not verified."}}, "SendEmail")
        self.sent.append(request)
        return {"MessageId": "1"}


def _message(settings: Settings):
    return build_message(
        settings, to="dana@example.com", office="משרד בדיקה", subject="נושא", text="שלום\nhttps://x", url="https://x", button="פתיחה"
    )


def test_ses_sends_the_raw_message_from_the_tel_aviv_region(monkeypatch: pytest.MonkeyPatch) -> None:
    import boto3

    fake = _FakeSes()
    regions: list[str] = []

    def client(name: str, region_name: str):
        assert name == "sesv2"
        regions.append(region_name)
        return fake

    monkeypatch.setattr(boto3, "client", client)
    settings = _settings(ses_configuration_set="docketflow")
    sender = EmailSender(settings)
    assert sender.available
    asyncio.run(sender.send(_message(settings)))
    [request] = fake.sent
    assert regions == ["il-central-1"]
    assert request["FromEmailAddress"] == "office@docketflow.example"
    assert request["Destination"] == {"ToAddresses": ["dana@example.com"]}
    assert b"Subject:" in request["Content"]["Raw"]["Data"]
    assert request["ConfigurationSetName"] == "docketflow"


def test_an_ses_refusal_is_an_email_error_the_office_can_read(monkeypatch: pytest.MonkeyPatch) -> None:
    import boto3

    monkeypatch.setattr(boto3, "client", lambda name, region_name: _FakeSes(fail=True))
    settings = _settings()
    with pytest.raises(EmailError, match="שרת הדואר"):
        asyncio.run(EmailSender(settings).send(_message(settings)))


def test_ses_without_a_from_address_is_not_available() -> None:
    assert not EmailSender(Settings(_env_file=None, email_backend="ses", email_from="")).available


def test_qdrant_can_be_switched_off_with_a_word() -> None:
    assert _settings(qdrant_url="off").qdrant_url == ""
    assert _settings(qdrant_url="http://qdrant:6333").qdrant_url == "http://qdrant:6333"
