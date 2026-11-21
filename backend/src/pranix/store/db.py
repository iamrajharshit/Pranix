# SPDX-License-Identifier: AGPL-3.0-only
"""Database engine and sessions (D70): PostgreSQL 16 everywhere (Docker locally, on the Oracle VM,
Neon as fallback). Sync, like the rest of the app.

Small pool (HOST-08: at most 5), `pool_pre_ping`, a 3 s connect timeout, and one retry on a
connection error so a Neon compute waking from scale-to-zero doesn't fail a request.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str, pool_size: int = 5) -> Engine:
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=0,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": 3, "application_name": "pranix"},
    )


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def transaction(factory: sessionmaker[Session]) -> Iterator[Session]:
    """One unit of work: commit on success, roll back on any error."""
    with factory() as s, s.begin():
        yield s


def with_retry[T](fn: Callable[[], T]) -> T:
    """Run `fn` and retry once on a connection error (scale-to-zero wake-up)."""
    try:
        return fn()
    except OperationalError:
        return fn()


def ping(engine: Engine) -> bool:
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False
