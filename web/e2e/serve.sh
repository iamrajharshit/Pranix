#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Start the backend for end-to-end tests: built web app, fixture place index, fake AI provider.
set -euo pipefail
PORT="${1:-8010}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
python3 "$ROOT/tools/build_geonames.py" "$ROOT/backend/tests/fixtures/geonames" "$TMP/geonames.sqlite" \
  --cities cities_fixture.txt >/dev/null
export PRANIX_ENV=test
export PRANIX_WEB_DIST="$ROOT/web/dist"
export PRANIX_GEO_DB_PATH="$TMP/geonames.sqlite"
export PRANIX_EPHE_PATH="${PRANIX_EPHE_PATH:-$ROOT/data/ephe}"
export PRANIX_FONTS_DIR="${PRANIX_FONTS_DIR:-$ROOT/data/fonts}"
export PRANIX_LLM_FAKE="${PRANIX_LLM_FAKE:-ok}"
cd "$ROOT/backend"
exec python3 -m uvicorn pranix.gateway.app:app --host 127.0.0.1 --port "$PORT" --log-level warning
