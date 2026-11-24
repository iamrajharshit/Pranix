# SPDX-License-Identifier: AGPL-3.0-only
"""Alembic environment: one linear history, run by `pranix-ctl db upgrade` (Data_model_v1 §5)."""

from __future__ import annotations

from alembic import context

from pranix.store.db import make_engine
from pranix.store.models import Base

config = context.config
url = config.get_main_option("sqlalchemy.url")
if not url:
    raise RuntimeError("no database URL: set PRANIX_DATABASE_URL")

engine = make_engine(url, pool_size=1)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
