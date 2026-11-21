# SPDX-License-Identifier: AGPL-3.0-only
"""Accounts schema (Data_model_v1.1 §2) as SQLAlchemy 2 models.

The initial Alembic migration creates exactly these tables; a test compares the two so they
can never drift. Personal fields are encrypted before they reach a model (`*_enc` columns);
the database never sees a birth date, time, place, name or pronouns in clear text.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    MetaData,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {"pk": "%(table_name)s_pkey", "fk": "%(table_name)s_%(column_0_name)s_fkey"}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _ts(nullable: bool = True, now: bool = False) -> Mapped[datetime]:
    return mapped_column(TIMESTAMP(timezone=True), nullable=nullable, server_default=func.now() if now else None)


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("octet_length(handle) = 64", name="users_handle_check"),
        UniqueConstraint("handle", name="users_handle_key"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    handle: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    display_label: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    age_confirmed_at: Mapped[datetime | None] = _ts()
    terms_version: Mapped[str | None] = mapped_column(Text)
    privacy_version: Mapped[str | None] = mapped_column(Text)
    consent_version: Mapped[str | None] = mapped_column(Text)
    consent_at: Mapped[datetime | None] = _ts()
    created_at: Mapped[datetime] = _ts(nullable=False, now=True)
    last_login_at: Mapped[datetime | None] = _ts()


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (
        CheckConstraint("provider IN ('google')", name="auth_identities_provider_check"),
        UniqueConstraint("provider", "provider_sub", name="auth_identities_provider_provider_sub_key"),
        Index("auth_identities_user_id_idx", "user_id"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_sub: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _ts(nullable=False, now=True)


class PasskeyCredential(Base):
    __tablename__ = "passkey_credentials"
    __table_args__ = (Index("passkey_credentials_user_id_idx", "user_id"),)
    credential_id: Mapped[bytes] = mapped_column(BYTEA, primary_key=True)
    user_id: Mapped[uuid.UUID] = _user_fk()
    public_key: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    sign_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    transports: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    backup_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    backup_state: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rp_id: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts(nullable=False, now=True)
    last_used_at: Mapped[datetime | None] = _ts()


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"
    __table_args__ = (Index("recovery_codes_user_id_idx", "user_id", postgresql_where=text("used_at IS NULL")),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    code_hmac: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    pepper_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    used_at: Mapped[datetime | None] = _ts()
    created_at: Mapped[datetime] = _ts(nullable=False, now=True)


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("NOT (is_primary AND for_other_person)", name="other_person_never_primary"),
        Index("profiles_user_id_idx", "user_id"),
        Index("one_primary_per_user", "user_id", unique=True, postgresql_where=text("is_primary")),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    for_other_person: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    inputs_enc: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    enc_key_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ruleset_id: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    save_chat: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = _ts(nullable=False, now=True)
    updated_at: Mapped[datetime] = _ts(nullable=False, now=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="chat_messages_role_check"),
        Index("chat_messages_profile_id_created_at_idx", "profile_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content_enc: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    enc_key_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = _ts(nullable=False, now=True)


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("sessions_user_id_idx", "user_id"), Index("sessions_expires_at_idx", "expires_at"))
    id_hash: Mapped[bytes] = mapped_column(BYTEA, primary_key=True)
    user_id: Mapped[uuid.UUID] = _user_fk()
    created_at: Mapped[datetime] = _ts(nullable=False, now=True)
    last_seen_at: Mapped[datetime] = _ts(nullable=False, now=True)
    expires_at: Mapped[datetime] = _ts(nullable=False)
    absolute_expires_at: Mapped[datetime] = _ts(nullable=False)


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"
    __table_args__ = (
        CheckConstraint("kind IN ('webauthn_reg','webauthn_login','oidc')", name="auth_challenges_kind_check"),
        Index("auth_challenges_expires_at_idx", "expires_at"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = _ts(nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("audit_events_at_idx", "at"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = _ts(nullable=False, now=True)
