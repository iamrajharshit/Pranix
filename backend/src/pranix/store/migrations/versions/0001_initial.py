# SPDX-License-Identifier: AGPL-3.0-only
"""Initial accounts schema: Data_model_v1.1 §2, verbatim apart from explicit index names.

Revision ID: 0001_initial
Revises:
"""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

UP = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  handle            bytea NOT NULL UNIQUE CHECK (octet_length(handle) = 64),
  display_label     text  NOT NULL,
  email             text,
  avatar_url        text,
  age_confirmed_at  timestamptz,
  terms_version     text,
  privacy_version   text,
  consent_version   text,
  consent_at        timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  last_login_at     timestamptz
);

CREATE TABLE auth_identities (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider      text NOT NULL CHECK (provider IN ('google')),
  provider_sub  text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_sub)
);
CREATE INDEX auth_identities_user_id_idx ON auth_identities(user_id);

CREATE TABLE passkey_credentials (
  credential_id    bytea PRIMARY KEY,
  user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  public_key       bytea NOT NULL,
  sign_count       bigint NOT NULL DEFAULT 0,
  transports       text[],
  backup_eligible  boolean NOT NULL,
  backup_state     boolean NOT NULL,
  rp_id            text NOT NULL,
  label            text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  last_used_at     timestamptz
);
CREATE INDEX passkey_credentials_user_id_idx ON passkey_credentials(user_id);

CREATE TABLE recovery_codes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hmac   bytea NOT NULL,
  pepper_id   smallint NOT NULL,
  used_at     timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX recovery_codes_user_id_idx ON recovery_codes(user_id) WHERE used_at IS NULL;

CREATE TABLE profiles (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  for_other_person  boolean NOT NULL DEFAULT false,
  inputs_enc        bytea NOT NULL,
  enc_key_id        smallint NOT NULL,
  ruleset_id        text NOT NULL,
  is_primary        boolean NOT NULL DEFAULT false,
  save_chat         boolean NOT NULL DEFAULT false,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT other_person_never_primary CHECK (NOT (is_primary AND for_other_person))
);
CREATE INDEX profiles_user_id_idx ON profiles(user_id);
CREATE UNIQUE INDEX one_primary_per_user ON profiles(user_id) WHERE is_primary;

CREATE TABLE chat_messages (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id   uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  role         text NOT NULL CHECK (role IN ('user','assistant')),
  content_enc  bytea NOT NULL,
  enc_key_id   smallint NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX chat_messages_profile_id_created_at_idx ON chat_messages(profile_id, created_at);

CREATE TABLE sessions (
  id_hash             bytea PRIMARY KEY,
  user_id             uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at          timestamptz NOT NULL DEFAULT now(),
  last_seen_at        timestamptz NOT NULL DEFAULT now(),
  expires_at          timestamptz NOT NULL,
  absolute_expires_at timestamptz NOT NULL
);
CREATE INDEX sessions_user_id_idx ON sessions(user_id);
CREATE INDEX sessions_expires_at_idx ON sessions(expires_at);

CREATE TABLE auth_challenges (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind        text NOT NULL CHECK (kind IN ('webauthn_reg','webauthn_login','oidc')),
  data        bytea NOT NULL,
  expires_at  timestamptz NOT NULL
);
CREATE INDEX auth_challenges_expires_at_idx ON auth_challenges(expires_at);

CREATE TABLE audit_events (
  id          bigserial PRIMARY KEY,
  actor       text NOT NULL,
  action      text NOT NULL,
  at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_at_idx ON audit_events(at);
"""

DOWN = """
DROP TABLE IF EXISTS audit_events, auth_challenges, sessions, chat_messages, profiles,
  recovery_codes, passkey_credentials, auth_identities, users;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
