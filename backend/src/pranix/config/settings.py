# SPDX-License-Identifier: AGPL-3.0-only
"""Typed settings. Secrets are SecretStr and are only ever shown as short fingerprints (CFG-02)."""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# In a source checkout: <repo>/backend/src/pranix/config/settings.py. In the Docker image these
# paths do not exist and nothing below changes anything.
BACKEND_DIR = Path(__file__).resolve().parents[3]
REPO_DIR = BACKEND_DIR.parent
PATH_FIELDS = ("ephe_path", "geo_db_path", "fonts_dir", "web_dist")


def _resolve(value: str, default: str) -> str:
    """Make a data path work whichever folder the server was started from.
    Relative paths are tried against the working folder, backend/ and the repo root; the Docker
    default (/app/data/...) falls back to the repo's data/ folder when it is not there."""
    p = Path(value)
    if value == default and not p.exists():  # checked first: "/app/..." has no drive on Windows
        local = REPO_DIR / "data" / p.name if p.parent.name == "data" else REPO_DIR / "web" / "dist"
        return str(local) if local.exists() else value
    if p.is_absolute() or value.startswith(("/", "\\")):
        return value
    for base in (Path.cwd(), BACKEND_DIR, REPO_DIR):
        if (base / p).exists():
            return str((base / p).resolve())
    return value


class Settings(BaseSettings):
    # Real environment variables win; a local .env fills the rest. It is found next to the code
    # (repo root or backend/) or in the working folder, so the start folder does not matter.
    # .env is git-ignored. On Render there is no .env: values come from its secret store.
    model_config = SettingsConfigDict(
        env_prefix="PRANIX_",
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env", "../.env", ".env"),
        extra="ignore",
    )

    env: Literal["dev", "test", "prod"] = "dev"
    service_mode: Literal["all", "distributed"] = "all"
    ephe_path: str = "/app/data/ephe"
    geo_db_path: str = "/app/data/geonames.sqlite"
    fonts_dir: str = "/app/data/fonts"
    web_dist: str = "/app/web"
    feature_chat: bool = False
    feature_passkeys: bool = False
    max_profiles_per_user: int = Field(default=5, ge=1, le=20)
    guest_ttl_seconds: int = Field(default=86_400, ge=60, le=86_400)
    guest_cache_max: int = Field(default=2_000, ge=10, le=50_000)
    rate_profiles_per_min: int = Field(default=30, ge=1)
    rate_places_per_min: int = Field(default=60, ge=1)
    rate_insights_per_min: int = Field(default=20, ge=1)
    rate_images_per_min: int = Field(default=10, ge=1)
    # Library: production serves approved entries only (FR-LIB-03); dev/test also serve drafts.
    library_allow_drafts: bool | None = None
    # AI providers (insights chain, FR-LLM). Model names change: verify against each console.
    gemini_models: list[str] = ["gemini-flash-latest", "gemini-flash-lite-latest"]
    gemini_rpm: int = Field(default=10, ge=1)
    groq_model: str = "llama-3.3-70b-versatile"
    groq_rpm: int = Field(default=30, ge=1)
    # Behind Render's proxy the client IP is the first X-Forwarded-For entry; never trust it elsewhere.
    trust_proxy: bool = False
    map_tile_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

    # Secrets (required in prod, optional in dev/test)
    database_url: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    log_pepper: SecretStr | None = None
    chart_key_pepper: SecretStr | None = None

    @field_validator(
        *("database_url", "gemini_api_key", "groq_api_key", "log_pepper", "chart_key_pepper"), mode="before"
    )
    @classmethod
    def _blank_is_missing(cls, v: object) -> object:
        # "PRANIX_GROQ_API_KEY=" in a .env means "not set", never an empty key or empty pepper.
        if isinstance(v, SecretStr):
            v = v.get_secret_value()
        return None if isinstance(v, str) and not v.strip() else v

    @model_validator(mode="after")
    def _resolve_paths(self) -> Settings:
        for name in PATH_FIELDS:
            setattr(self, name, _resolve(getattr(self, name), type(self).model_fields[name].default))
        return self

    def secret_fingerprints(self) -> dict[str, str]:
        """Names and 6-char fingerprints only; never the value."""
        out = {}
        for name, value in self:
            if isinstance(value, SecretStr):
                out[name] = hashlib.sha256(value.get_secret_value().encode()).hexdigest()[:6]
            elif name in SECRET_NAMES:
                out[name] = "missing"
        return out

    @property
    def allow_drafts(self) -> bool:
        return self.library_allow_drafts if self.library_allow_drafts is not None else self.env != "prod"

    def problems(self) -> list[str]:
        """Prod must have the peppers. The database becomes required with accounts (P1.5);
        missing AI keys are allowed: insight cards then use curated library text (FR-LLM-16)."""
        if self.env != "prod":
            return []
        out = []
        for n in REQUIRED_IN_PROD:
            v = getattr(self, n)
            if v is None:
                out.append(f"{n} is required in prod")
            elif len(v.get_secret_value()) < MIN_PEPPER_CHARS:
                out.append(f"{n} must be at least {MIN_PEPPER_CHARS} characters in prod")
        return out


SECRET_NAMES = ("database_url", "gemini_api_key", "groq_api_key", "log_pepper", "chart_key_pepper")
REQUIRED_IN_PROD = ("log_pepper", "chart_key_pepper")
MIN_PEPPER_CHARS = 32  # e.g. python -c "import secrets; print(secrets.token_hex(32))"


@cache
def get_settings() -> Settings:
    return Settings()
