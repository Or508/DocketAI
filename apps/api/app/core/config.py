from functools import lru_cache
from pathlib import Path
from typing import Self

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
    queue_enabled: bool = True
    qdrant_url: str = "http://localhost:6333"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    embedding_model: str = "text-embedding-004"
    embedding_dimensions: int = 768
    confidence_threshold: float = Field(default=0.75, ge=0, le=1)
    auto_create_schema: bool = True
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    storage_dir: Path | None = None
    template_dir: Path | None = None
    hebrew_font_path: Path | None = None
    max_upload_bytes: int = 25 * 1024 * 1024
    max_files_per_upload: int = 20
    max_vision_pages: int = Field(default=2, ge=1, le=5)

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
        return self

    @property
    def resolved_storage_dir(self) -> Path:
        return self.storage_dir or (API_ROOT / "data" / "storage")

    @property
    def resolved_template_dir(self) -> Path:
        return self.template_dir or (API_ROOT / "app" / "assets" / "templates")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
