#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Run the API like the Oracle VM does (2 CPUs) with the fake AI provider and roomy rate limits,
# so a load run measures the app, not the per-IP limiter (which has its own spike test).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
python3 "$ROOT/tools/build_geonames.py" "$ROOT/backend/tests/fixtures/geonames" "$TMP/geonames.sqlite" --cities cities_fixture.txt >/dev/null
export PRANIX_ENV=test PRANIX_LLM_FAKE="${PRANIX_LLM_FAKE:-ok}" PRANIX_GEO_DB_PATH="$TMP/geonames.sqlite"
export PRANIX_EPHE_PATH="${PRANIX_EPHE_PATH:-$ROOT/data/ephe}"
export PRANIX_RATE_PROFILES_PER_MIN=100000 PRANIX_RATE_PLACES_PER_MIN=100000 PRANIX_RATE_INSIGHTS_PER_MIN=100000
cd "$ROOT/backend"
exec taskset -c 0,1 python3 -m uvicorn pranix.gateway.app:app --host 127.0.0.1 --port "${PORT:-8000}" --log-level warning
