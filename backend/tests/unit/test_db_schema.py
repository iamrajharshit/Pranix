# SPDX-License-Identifier: AGPL-3.0-only
"""Accounts database (F2): migrations, schema rules and erasure, on a real PostgreSQL 16.

Runs when PRANIX_TEST_DATABASE_URL points at an empty database (CI starts one); skipped otherwise.
"""

import os
import uuid
from collections.abc import Iterator

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from pranix.store import migrate
from pranix.store.db import make_engine, ping, session_factory, transaction, with_retry
from pranix.store.models import Base, ChatMessage, Profile, Session, User

URL = os.environ.get("PRANIX_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="PRANIX_TEST_DATABASE_URL not set")

TABLES = {
    "users",
    "auth_identities",
    "passkey_credentials",
    "recovery_codes",
    "profiles",
    "chat_messages",
    "sessions",
    "auth_challenges",
    "audit_events",
}


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    migrate.downgrade(URL, "base")
    migrate.upgrade(URL)
    e = make_engine(URL)
    yield e
    e.dispose()


def _user(s, n: int = 0) -> User:  # type: ignore[no-untyped-def]
    u = User(handle=bytes([n]) * 64, display_label=f"Seeker-{n}")
    s.add(u)
    s.flush()
    return u


def _profile(user_id: uuid.UUID, **kw: object) -> Profile:
    return Profile(user_id=user_id, inputs_enc=b"\x01ciphertext", enc_key_id=1, ruleset_id="vedic-core@1", **kw)


def test_upgrade_creates_every_table_and_models_match(engine: Engine) -> None:
    assert TABLES <= set(inspect(engine).get_table_names())
    with engine.connect() as c:
        diffs = compare_metadata(MigrationContext.configure(c), Base.metadata)
    assert diffs == [], diffs


def test_downgrade_then_upgrade_round_trips(engine: Engine) -> None:
    migrate.downgrade(URL, "base")
    assert not TABLES & set(inspect(engine).get_table_names())
    migrate.upgrade(URL)
    assert TABLES <= set(inspect(engine).get_table_names())


def test_a_profile_for_someone_else_can_never_be_primary(engine: Engine) -> None:
    f = session_factory(engine)
    with pytest.raises(IntegrityError), transaction(f) as s:
        u = _user(s, 1)
        s.add(_profile(u.id, for_other_person=True, is_primary=True))


def test_only_one_primary_profile_per_user(engine: Engine) -> None:
    f = session_factory(engine)
    with pytest.raises(IntegrityError), transaction(f) as s:
        u = _user(s, 2)
        s.add_all([_profile(u.id, is_primary=True), _profile(u.id, is_primary=True)])


def test_deleting_a_user_erases_everything_of_theirs(engine: Engine) -> None:
    f = session_factory(engine)
    with transaction(f) as s:
        u = _user(s, 3)
        p = _profile(u.id, is_primary=True)
        s.add(p)
        s.flush()
        s.add(ChatMessage(profile_id=p.id, role="user", content_enc=b"\x01x", enc_key_id=1))
        s.add(
            Session(
                id_hash=b"h" * 32,
                user_id=u.id,
                expires_at=text("now() + interval '7 days'"),
                absolute_expires_at=text("now() + interval '30 days'"),
            )
        )
        uid, pid = u.id, p.id
    with transaction(f) as s:
        s.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    with transaction(f) as s:
        assert s.scalar(select(Profile).where(Profile.id == pid)) is None
        assert s.scalar(select(ChatMessage).where(ChatMessage.profile_id == pid)) is None
        assert s.scalar(select(Session).where(Session.user_id == uid)) is None


def test_handle_must_be_sixty_four_bytes_and_roles_are_checked(engine: Engine) -> None:
    f = session_factory(engine)
    with pytest.raises(IntegrityError), transaction(f) as s:
        s.add(User(handle=b"short", display_label="x"))
    with pytest.raises(IntegrityError), transaction(f) as s:
        u = _user(s, 4)
        p = _profile(u.id)
        s.add(p)
        s.flush()
        s.add(ChatMessage(profile_id=p.id, role="system", content_enc=b"x", enc_key_id=1))


def test_ping_and_retry(engine: Engine) -> None:
    assert ping(engine)
    assert not ping(make_engine("postgresql://nobody@127.0.0.1:1/none"))
    calls = []

    def flaky() -> int:
        calls.append(1)
        if len(calls) == 1:
            from sqlalchemy.exc import OperationalError

            raise OperationalError("SELECT 1", {}, Exception("waking up"))
        return 42

    assert with_retry(flaky) == 42 and len(calls) == 2
