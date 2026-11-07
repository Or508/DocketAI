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
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    embedding_model: str = "text-embedding-004"
    embedding_dimensions: int = 768
    confidence_threshold: float = Field(default=0.75, ge=0, le=1)
    auto_create_schema: bool = True
    log_level: str = "INFO"
    session_ttl_hours: int = 12
    login_max_failures: int = 5
    login_lock_minutes: int = 15
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
    max_upload_bytes: int = 25 * 1024 * 1024
    max_files_per_upload: int = 20
    max_vision_pages: int = Field(default=2, ge=1, le=5)
    chat_stream_idle_timeout_seconds: float = Field(default=20, gt=0)
    public_web_url: str = "http://localhost:3000"
    signing_link_ttl_hours: int = 72
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

    @field_validator("storage_dir", "template_dir", "hebrew_font_path", mode="before")
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
    def resolved_storage_dir(self) -> Path:
        return self.storage_dir or (API_ROOT / "data" / "storage")

    @property
    def resolved_template_dir(self) -> Path:
        return self.template_dir or (API_ROOT / "app" / "assets" / "templates")


@lru_cache
def get_settings() -> Settings:
    return Settings()
