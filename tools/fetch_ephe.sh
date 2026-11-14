#!/usr/bin/env sh
# SPDX-License-Identifier: AGPL-3.0-only
# Download the Swiss Ephemeris data files (1800-2399 CE) and verify checksums (ENG-07).
# Files are (c) Astrodienst AG, used under the AGPL; they are never committed to git.
set -eu
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SUMS="$SCRIPT_DIR/../data/ephe/SHA256SUMS"
DEST="${1:-$SCRIPT_DIR/../data/ephe}"
BASE="https://raw.githubusercontent.com/aloistr/swisseph/master/ephe"
mkdir -p "$DEST"
for f in sepl_18.se1 semo_18.se1 seas_18.se1; do
  [ -f "$DEST/$f" ] || curl -fsSL -o "$DEST/$f" "$BASE/$f"
done
(cd "$DEST" && sha256sum -c "$SUMS")
