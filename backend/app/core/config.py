from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "ShambaLens AI"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./data/shambalens.db"
    database_url_unpooled: str | None = None
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_vision_model: str = "qwen/qwen3.8-27b"
    groq_reasoning_model: str = "openai/gpt-oss-120b"
    groq_verifier_model: str = "openai/gpt-oss-120b"
    ai_provider: str = "groq"
    demo_mode: bool = False
    max_upload_mb: int = Field(default=8, ge=1, le=25)
    max_image_pixels: int = Field(default=33_000_000, ge=1_000_000)
    upload_dir: Path = Path("data/uploads")
    image_storage: Literal["local", "firebase"] = "local"
    firebase_project_id: str | None = None
    firebase_storage_bucket: str | None = None
    firebase_service_account_json: SecretStr | None = None
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    anonymous_token_salt: str = "change-this-development-salt"
    model_timeout_seconds: float = Field(default=45, ge=3, le=180)
    model_max_retries: int = Field(default=1, ge=0, le=2)
    image_min_dimension: int = Field(default=320, ge=128, le=2048)
    image_blur_threshold: float = Field(default=55.0, ge=0)
    image_dark_threshold: float = Field(default=35.0, ge=0, le=255)
    image_bright_threshold: float = Field(default=225.0, ge=0, le=255)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def firebase_storage_has_required_identifiers(self) -> Settings:
        if self.image_storage == "firebase" and not (
            self.firebase_project_id and self.firebase_storage_bucket
        ):
            raise ValueError(
                "FIREBASE_PROJECT_ID and FIREBASE_STORAGE_BUCKET are required "
                "when IMAGE_STORAGE=firebase"
            )
        return self

    @property
    def async_database_url(self) -> str:
        return _to_async_database_url(self.database_url)

    @property
    def migration_database_url(self) -> str:
        return _to_async_database_url(self.database_url_unpooled or self.database_url)

    @property
    def upload_limit_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _to_async_database_url(value: str) -> str:
    """Translate common Neon URLs without mutating the configured secret.

    Neon's copy button emits libpq parameters. asyncpg uses ``ssl`` instead of
    ``sslmode`` and does not accept ``channel_binding`` as a connect argument.
    """
    url = make_url(value)
    if url.get_backend_name() in {"postgres", "postgresql"}:
        query = dict(url.query)
        sslmode = query.pop("sslmode", None)
        query.pop("channel_binding", None)
        if sslmode is not None:
            # asyncpg accepts libpq SSL mode names through ``ssl`` but rejects
            # the ``sslmode`` and ``channel_binding`` connect keywords emitted
            # by Neon's copy button.
            query["ssl"] = sslmode
        url = url.set(drivername="postgresql+asyncpg", query=query)
        return url.render_as_string(hide_password=False)
    if url.drivername == "sqlite":
        return url.set(drivername="sqlite+aiosqlite").render_as_string(hide_password=False)
    return value
