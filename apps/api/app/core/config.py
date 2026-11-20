from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import API_ROOT, REPO_ROOT


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(API_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = (
        f"sqlite+aiosqlite:///{(API_ROOT / 'data' / 'docketai.db').as_posix()}"
    )
    redis_url: str = "redis://localhost:6379/0"
    queue_enabled: bool = False
    qdrant_url: str = "http://localhost:6333"
    # The main model. Claude answers first; Gemini is the backup and the source of embeddings.
    ai_provider: Literal["claude", "gemini"] = "claude"
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5-5"
    claude_timeout_seconds: float = Field(default=120.0, gt=0)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    # text-embedding-004 was retired and now answers 404. Vectors from different models never share a collection.
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = Field(default=768, ge=1, le=3072)
    confidence_threshold: float = Field(default=0.75, ge=0, le=1)
    auto_create_schema: bool = True
    log_level: str = "INFO"
    session_ttl_hours: int = 12
    # Wrong passwords from one address lock that address out of that account only, so a stranger
    # cannot lock a colleague out. The account itself locks only after many failures from anywhere.
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    login_account_max_failures: int = Field(default=25, ge=1)
    # Per-address request limits, kept in this process's memory. Run one API process per limit,
    # or put a shared limiter in front, when scaling out.
    rate_limit_enabled: bool = True
    login_rate_limit: int = Field(default=30, ge=1)
    login_rate_window_seconds: int = Field(default=900, ge=1)
    public_rate_limit: int = Field(default=120, ge=1)
    public_rate_window_seconds: int = Field(default=60, ge=1)
    # Two-step login. Without MFA_SECRET_KEY the server keeps its own key file beside the database.
    mfa_secret_key: str = ""
    mfa_key_path: Path | None = None
    mfa_issuer: str = "DocketFlow"
    storage_backend: Literal["local", "s3"] = "local"
    s3_bucket: str = ""
    s3_region: str = ""
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_force_path_style: bool = False
    s3_server_side_encryption: str = ""
    s3_kms_key_id: str = ""
    storage_dir: Path | None = None
    template_dir: Path | None = None
    hebrew_font_path: Path | None = None
    # The blank official BL/6101 the office loads with one click.
    bl_6101_template_path: Path | None = None
    # A blank Form 101 to use instead of the one this server draws for itself.
    form_101_template_path: Path | None = None
    # A blank real estate form to use instead of the one this server draws for itself.
    real_estate_template_path: Path | None = None
    max_upload_bytes: int = 25 * 1024 * 1024
    max_files_per_upload: int = 20
    max_vision_pages: int = Field(default=2, ge=1, le=5)
    chat_stream_idle_timeout_seconds: float = Field(default=20, gt=0)
    public_web_url: str = "http://localhost:3000"
    signing_link_ttl_hours: int = 72
    # How long a client's document intake link works. 0 means it does not expire.
    intake_link_ttl_hours: int = Field(default=168, ge=0)
    signing_link_download_hours: int = 168
    signing_link_max_chat_turns: int = 40
    preflight_timeout_seconds: int = 20
    preflight_memory_mb: int = 768
    preflight_max_pages: int = 300
    preflight_max_page_inches: int = 200
    preflight_max_decompressed_mb: int = 512
    preflight_max_image_pixels: int = 50_000_000
    preflight_reject_pdf_javascript: bool = True
    clamav_host: str = ""
    clamav_port: int = 3310
    clamav_timeout_seconds: int = 30
    # Messages to clients. "outbox" writes each email as an .eml file under OUTBOX_DIR instead of sending it,
    # "smtp" sends it, "disabled" refuses to send email (WhatsApp links still work).
    email_backend: Literal["disabled", "outbox", "smtp"] = "outbox"
    outbox_dir: Path | None = None
    email_from: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: float = Field(default=20, gt=0)
    # Reminders go out this many days after the first message, one per entry, until the client acts.
    reminder_days: str = "2,5"
    reminder_poll_seconds: int = Field(default=300, ge=10)
    # Israel time. No reminder is sent outside these hours, or on Saturday.
    reminder_start_hour: int = Field(default=9, ge=0, le=23)
    reminder_end_hour: int = Field(default=20, ge=1, le=24)
    # A cap on emails per case per day, whatever the office clicks.
    max_messages_per_case_per_day: int = Field(default=10, ge=1)

    @field_validator("storage_dir", "outbox_dir", "template_dir", "hebrew_font_path", "bl_6101_template_path", "form_101_template_path", "real_estate_template_path", mode="before")
    @classmethod
    def blank_path(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @model_validator(mode="after")
    def normalize(self) -> Self:
        self.database_url = _normalize_database_url(self.database_url)
        self.qdrant_url = self.qdrant_url.strip()
        self.gemini_api_key = self.gemini_api_key.strip()
        self.anthropic_api_key = self.anthropic_api_key.strip()
        self.mfa_secret_key = self.mfa_secret_key.strip()
        self.claude_model = self.claude_model.strip()
        self.s3_bucket = self.s3_bucket.strip()
        self.s3_region = self.s3_region.strip()
        self.s3_endpoint_url = self.s3_endpoint_url.strip()
        self.s3_access_key_id = self.s3_access_key_id.strip()
        self.s3_secret_access_key = self.s3_secret_access_key.strip()
        self.s3_server_side_encryption = self.s3_server_side_encryption.strip()
        self.s3_kms_key_id = self.s3_kms_key_id.strip()
        if self.storage_backend == "s3":
            if not self.s3_bucket:
                raise ValueError("s3_bucket is required when storage_backend is s3.")
            if bool(self.s3_access_key_id) != bool(self.s3_secret_access_key):
                raise ValueError(
                    "s3_access_key_id and s3_secret_access_key must both be set or both be blank."
                )
        return self

    @property
    def resolved_mfa_key_path(self) -> Path:
        return self.mfa_key_path or (API_ROOT / "data" / "mfa.key")

    @property
    def resolved_outbox_dir(self) -> Path:
        return self.outbox_dir or (API_ROOT / "data" / "outbox")

    @property
    def reminder_schedule_days(self) -> list[int]:
        """REMINDER_DAYS as sorted whole days, ignoring blanks and anything that is not a positive number."""
        days = {int(part) for part in self.reminder_days.split(",") if part.strip().isdigit() and int(part) > 0}
        return sorted(days)

    @property
    def resolved_storage_dir(self) -> Path:
        return self.storage_dir or (API_ROOT / "data" / "storage")

    @property
    def resolved_bl_6101_template(self) -> Path:
        return self.bl_6101_template_path or (REPO_ROOT / "test_files_for_browser" / "bl_6101_official.pdf")

    @property
    def resolved_form_101_template(self) -> Path:
        return self.form_101_template_path or (REPO_ROOT / "test_files_for_browser" / "form_101_official.pdf")

    @property
    def resolved_real_estate_template(self) -> Path:
        return self.real_estate_template_path or (REPO_ROOT / "test_files_for_browser" / "real_estate_official.pdf")

    @property
    def resolved_template_dir(self) -> Path:
        return self.template_dir or (API_ROOT / "app" / "assets" / "templates")


@lru_cache
def get_settings() -> Settings:
    return Settings()
