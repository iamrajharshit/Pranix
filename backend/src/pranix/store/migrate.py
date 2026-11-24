# SPDX-License-Identifier: AGPL-3.0-only
"""Run Alembic programmatically, so the migrations ship inside the package (no alembic.ini)."""

from __future__ import annotations

from importlib import resources

from alembic import command
from alembic.config import Config


def config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(resources.files("pranix.store") / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade(url: str, rev: str = "head") -> None:
    command.upgrade(config(url), rev)


def downgrade(url: str, rev: str) -> None:
    command.downgrade(config(url), rev)


def current(url: str) -> None:
    command.current(config(url))
