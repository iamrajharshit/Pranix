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


FakeMode = Literal["off", "ok", "invalid_json", "numerals", "fear", "unknown_fact", "slow", "rate_limited", "down"]


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
    # Meaning-keyed AI cache (D70): a SQLite file on a writable volume; empty = in-memory only.
    cache_path: str = ""
    feature_chat: bool = False
    feature_inspect: bool = False  # Chart Inspector (plan §15.7 launch gate); turn on in .env to try it
    feature_passkeys: bool = False
    max_profiles_per_user: int = Field(default=5, ge=1, le=20)
    guest_ttl_seconds: int = Field(default=86_400, ge=60, le=86_400)
    guest_cache_max: int = Field(default=2_000, ge=10, le=50_000)
    rate_profiles_per_min: int = Field(default=30, ge=1)
    rate_places_per_min: int = Field(default=60, ge=1)
    rate_insights_per_min: int = Field(default=20, ge=1)
    rate_images_per_min: int = Field(default=10, ge=1)
    rate_inspect_per_min: int = Field(default=60, ge=1)  # cheap: built in milliseconds (plan §8)
    # Library: production serves approved entries only (FR-LIB-03); dev/test also serve drafts.
    library_allow_drafts: bool | None = None
    # AI providers (insights chain, FR-LLM). Model names change: verify against each console.
    gemini_models: list[str] = ["gemini-flash-latest", "gemini-flash-lite-latest"]
    gemini_rpm: int = Field(default=10, ge=1)
    groq_model: str = "llama-3.3-70b-versatile"
    groq_rpm: int = Field(default=30, ge=1)
    # Local model (F5, D77): one setting group for both places it runs.
    #   PC:     PRANIX_LOCAL_LLM_URL=http://localhost:11434/v1   PRANIX_LOCAL_LLM_MODEL=gemma4:e2b   (Ollama)
    #   Oracle: PRANIX_LOCAL_LLM_URL=http://llm:8080/v1          + PRANIX_LOCAL_LLM_API_KEY          (llama.cpp)
    local_llm_url: str = ""
    local_llm_model: str = "gemma4:e2b"
    local_llm_timeout_s: float = Field(default=60.0, ge=1.0, le=600.0)
    local_llm_rpm: int = Field(default=6, ge=1)
    local_llm_concurrency: int = Field(default=1, ge=1, le=8)
    # Which chain the insights use: "default" = Gemini free -> Groq -> local -> curated;
    # "dev" = local only (offline, zero cost); "cloud" = Gemini and Groq only (no local model).
    llm_chains: Literal["default", "dev", "cloud"] = "default"
    # Background re-wording (D77): a reading served as curated text is re-worded later by the local
    # model, one at a time, and cached for the next reader. Needs PRANIX_LOCAL_LLM_URL.
    background_reword: bool = True
    background_reword_max: int = Field(default=200, ge=1, le=5000)
    # Test-only fake provider (F1): replaces every real provider; refused in prod.
    llm_fake: FakeMode = "off"
    llm_fake_delay_ms: int = Field(default=0, ge=0, le=60_000)
    # Behind Render's proxy the client IP is the first X-Forwarded-For entry; never trust it elsewhere.
    trust_proxy: bool = False
    map_tile_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

    # Secrets (required in prod, optional in dev/test)
    database_url: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    local_llm_api_key: SecretStr | None = None
    log_pepper: SecretStr | None = None
    chart_key_pepper: SecretStr | None = None

    @field_validator(
        *("database_url", "gemini_api_key", "groq_api_key", "local_llm_api_key", "log_pepper", "chart_key_pepper"),
        mode="before",
    )
    @classmethod
    def _blank_is_missing(cls, v: object) -> object:
        # "PRANIX_GROQ_API_KEY=" in a .env means "not set", never an empty key or empty pepper.
        if isinstance(v, SecretStr):
            v = v.get_secret_value()
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("local_llm_url")
    @classmethod
    def _http_url(cls, v: str) -> str:
        v = v.strip()
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("local_llm_url must start with http:// or https://")
        return v.rstrip("/")

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
        if self.llm_fake != "off":
            out.append("llm_fake must be off in prod")
        if self.llm_chains == "dev":
            out.append("llm_chains=dev is for a developer machine, not prod")
        if self.local_llm_url and self.local_llm_api_key is None:
            out.append("local_llm_api_key is required in prod when local_llm_url is set")
        for n in REQUIRED_IN_PROD:
            v = getattr(self, n)
            if v is None:
                out.append(f"{n} is required in prod")
            elif len(v.get_secret_value()) < MIN_PEPPER_CHARS:
                out.append(f"{n} must be at least {MIN_PEPPER_CHARS} characters in prod")
        return out


SECRET_NAMES = ("database_url", "gemini_api_key", "groq_api_key", "local_llm_api_key", "log_pepper", "chart_key_pepper")
REQUIRED_IN_PROD = ("log_pepper", "chart_key_pepper")
MIN_PEPPER_CHARS = 32  # e.g. python -c "import secrets; print(secrets.token_hex(32))"


@cache
def get_settings() -> Settings:
    return Settings()
