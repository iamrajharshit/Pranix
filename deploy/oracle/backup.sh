#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Nightly encrypted database backup (D70, HOST-12). Run from cron on the server:
#   15 2 * * *  cd ~/pranix/deploy/oracle && ./backup.sh >> ~/pranix-backup.log 2>&1
#
# 1. pg_dump (custom format) from the db container, or from PGURL when set (tests, Neon)
# 2. encrypt with AES-256 (openssl, PBKDF2) using the passphrase in BACKUP_KEY_FILE
# 3. copy to BACKUP_TARGET: oci://<bucket> (OCI CLI) or dir:<folder>
# 4. keep BACKUP_KEEP_DAYS days (default 14); an Object Storage retention rule is the second guard
# The dump never touches the server's disk unencrypted. Nothing personal is printed.
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
: "${BACKUP_KEY_FILE:?set BACKUP_KEY_FILE (a 64-hex passphrase file, chmod 600)}"
: "${BACKUP_TARGET:?set BACKUP_TARGET, e.g. oci://pranix-backups or dir:/tmp/backups}"
KEEP="${BACKUP_KEEP_DAYS:-14}"
NAME="pranix-$(date -u +%Y%m%dT%H%M%SZ).dump.enc"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# PGX: optional command prefix so the client tools match the server's major version (CI uses a
# postgres:16 container); on the server the db container's own pg_dump is used.
if [ -n "${PGURL:-}" ]; then dump() { ${PGX:-} pg_dump --format=custom --no-owner "$PGURL"; }
else dump() { docker compose exec -T db pg_dump --format=custom --no-owner -U pranix pranix; }; fi
dump | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$BACKUP_KEY_FILE" -out "$TMP/$NAME"
SIZE=$(wc -c < "$TMP/$NAME")
[ "$SIZE" -gt 64 ] || { echo "backup: dump is empty, aborting"; exit 1; }

case "$BACKUP_TARGET" in
  oci://*)
    BUCKET="${BACKUP_TARGET#oci://}"
    oci os object put --bucket-name "$BUCKET" --name "db/$NAME" --file "$TMP/$NAME" --no-multipart >/dev/null
    CUTOFF=$(date -u -d "-$KEEP days" +%Y%m%dT%H%M%SZ)
    oci os object list --bucket-name "$BUCKET" --prefix db/pranix- --all --query 'data[].name' --raw-output \
      | tr -d '[]", ' | grep . | while read -r obj; do
        stamp="${obj#db/pranix-}"; stamp="${stamp%%.*}"
        [[ "$stamp" < "$CUTOFF" ]] && oci os object delete --bucket-name "$BUCKET" --object-name "$obj" --force >/dev/null
      done ;;
  dir:*)
    DIR="${BACKUP_TARGET#dir:}"; mkdir -p "$DIR"
    cp "$TMP/$NAME" "$DIR/"
    find "$DIR" -name 'pranix-*.dump.enc' -mtime +"$KEEP" -delete ;;
  *) echo "backup: unknown BACKUP_TARGET"; exit 1 ;;
esac
echo "backup: ok $NAME ($SIZE bytes) -> ${BACKUP_TARGET%%:*}"
