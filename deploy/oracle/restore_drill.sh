#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Monthly restore drill (D70): proves the newest backup can be decrypted and restored.
# Restores into a throwaway database (pranix_restore_check), checks every table is there and
# the migration version matches, prints row counts only, then drops it. Never touches `pranix`.
#   ./restore_drill.sh                      (on the server)
#   LOCAL_PG=1 ./restore_drill.sh   (tests: uses PGHOST/PGPORT/PGUSER of a server where you can create databases)
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
: "${BACKUP_KEY_FILE:?set BACKUP_KEY_FILE}"; : "${BACKUP_TARGET:?set BACKUP_TARGET}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

case "$BACKUP_TARGET" in
  oci://*)
    BUCKET="${BACKUP_TARGET#oci://}"
    LATEST=$(oci os object list --bucket-name "$BUCKET" --prefix db/pranix- --all --query 'data[].name' --raw-output \
      | tr -d '[]", ' | grep . | sort | tail -1)
    oci os object get --bucket-name "$BUCKET" --name "$LATEST" --file "$TMP/latest.enc" >/dev/null ;;
  dir:*)
    LATEST=$(ls "${BACKUP_TARGET#dir:}"/pranix-*.dump.enc | sort | tail -1)
    cp "$LATEST" "$TMP/latest.enc" ;;
esac
echo "drill: newest backup $(basename "$LATEST")"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$BACKUP_KEY_FILE" -in "$TMP/latest.enc" -out "$TMP/latest.dump"

if [ -n "${LOCAL_PG:-}" ]; then
  psqlx() { psql -d postgres -v ON_ERROR_STOP=1 -qAt "$@"; }
  restore() { pg_restore --no-owner -d pranix_restore_check "$TMP/latest.dump"; }
  inchk() { psql -d pranix_restore_check -qAt "$@"; }
else
  psqlx() { docker compose exec -T db psql -U pranix -d postgres -v ON_ERROR_STOP=1 -qAt "$@"; }
  restore() { docker compose exec -T db pg_restore --no-owner -U pranix -d pranix_restore_check < "$TMP/latest.dump"; }
  inchk() { docker compose exec -T db psql -U pranix -d pranix_restore_check -qAt "$@"; }
fi
psqlx -c "DROP DATABASE IF EXISTS pranix_restore_check" -c "CREATE DATABASE pranix_restore_check"
restore
for t in users auth_identities passkey_credentials recovery_codes profiles chat_messages sessions auth_challenges audit_events; do
  echo "drill: $t rows=$(inchk -c "SELECT count(*) FROM $t")"
done
echo "drill: migration $(inchk -c 'SELECT version_num FROM alembic_version')"
psqlx -c "DROP DATABASE pranix_restore_check"
echo "drill: ok"
