#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-only
# Keep <name>.duckdns.org pointing at this server. Run from cron every 5 minutes.
# Reads the subdomain and token from ~/.duckdns (chmod 600):  DUCKDNS_DOMAIN=pranix  DUCKDNS_TOKEN=...
set -eu
. "$HOME/.duckdns"
result=$(curl -fsS --max-time 20 \
  "https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip=")
[ "$result" = "OK" ] || { echo "duckdns update failed: $result" >&2; exit 1; }
