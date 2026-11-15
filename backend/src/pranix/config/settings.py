# SPDX-License-Identifier: AGPL-3.0-only
"""Typed settings. Secrets are SecretStr and are only ever shown as short fingerprints (CFG-02)."""

from __future__ import annotations

import hashlib
from functools import cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables win; a local .env (repo root or backend/) fills the rest.
    # .env is git-ignored. On Render there is no .env: values come from its secret store.
    model_config = SettingsConfigDict(env_prefix="PRANIX_", env_file=("../.env", ".env"), extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    service_mode: Literal["all", "distributed"] = "all"
    ephe_path: str = "/app/data/ephe"
    feature_chat: bool = False
    feature_passkeys: bool = False
    max_profiles_per_user: int = Field(default=5, ge=1, le=20)
    guest_ttl_seconds: int = Field(default=86_400, ge=60, le=86_400)
    map_tile_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

    # Secrets (required in prod, optional in dev/test)
    database_url: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    log_pepper: SecretStr | None = None
    chart_key_pepper: SecretStr | None = None

    def secret_fingerprints(self) -> dict[str, str]:
        """Names and 6-char fingerprints only; never the value."""
        out = {}
        for name, value in self:
            if isinstance(value, SecretStr):
                out[name] = hashlib.sha256(value.get_secret_value().encode()).hexdigest()[:6]
            elif name in SECRET_NAMES:
                out[name] = "missing"
        return out

    def problems(self) -> list[str]:
        if self.env != "prod":
            return []
        return [f"{n} is required in prod" for n in SECRET_NAMES if getattr(self, n) is None]


SECRET_NAMES = ("database_url", "gemini_api_key", "groq_api_key", "log_pepper", "chart_key_pepper")


@cache
def get_settings() -> Settings:
    return Settings()
