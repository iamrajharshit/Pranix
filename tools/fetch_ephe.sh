#!/usr/bin/env sh
# SPDX-License-Identifier: AGPL-3.0-only
# Download the Swiss Ephemeris data files (1800-2399 CE) and verify checksums (ENG-07).
# Files are (c) Astrodienst AG, used under the AGPL; they are never committed to git.
set -eu
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SUMS="$SCRIPT_DIR/../data/ephe/SHA256SUMS"
DEST="${1:-$SCRIPT_DIR/../data/ephe}"
# Pinned to the upstream commit whose files our SHA256SUMS describe (29 May 2026). Upstream "master" moved on
# 21 Nov 2026 ("compressed ephemeris update"), which broke the checksums. Move this pin only on purpose, with
# new checksums and a golden-snapshot review (rule 4: same input, same bytes).
REV="cae9ecd4b201544d85e411aced17660932514d43"
BASE="https://raw.githubusercontent.com/aloistr/swisseph/$REV/ephe"
mkdir -p "$DEST"
for f in sepl_18.se1 semo_18.se1 seas_18.se1; do
  [ -f "$DEST/$f" ] || curl -fsSL -o "$DEST/$f" "$BASE/$f"
done
(cd "$DEST" && sha256sum -c "$SUMS")
