#!/usr/bin/env sh
# SPDX-License-Identifier: AGPL-3.0-only
# Download GeoNames (CC BY 4.0) and build the offline place index.
# Usage: tools/fetch_geonames.sh [out.sqlite]   (needs: pip install -e "backend[dev]" for timezonefinder)
set -eu
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
OUT="${1:-$SCRIPT_DIR/../data/geonames.sqlite}"
SRC="$SCRIPT_DIR/../data/geonames-src"
BASE="https://download.geonames.org/export/dump"
mkdir -p "$SRC"
for f in cities500.zip admin1CodesASCII.txt countryInfo.txt; do
  [ -f "$SRC/$f" ] || curl -fsSL -o "$SRC/$f" "$BASE/$f"
done
python -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extract('cities500.txt', sys.argv[2])" "$SRC/cities500.zip" "$SRC"
python "$SCRIPT_DIR/build_geonames.py" "$SRC" "$OUT"
echo "built $OUT"
