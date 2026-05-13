#!/usr/bin/env bash
# Trigger an on-demand backup via the API.
#
# Usage:
#   ./scripts/backup.sh
#
# Talks to the running `api` service on http://localhost:8000. Requires the
# stack to be up (`docker compose up`).

set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"

echo "Requesting backup at ${API_URL}/backups ..."
response=$(curl -sS -X POST "${API_URL}/backups" --max-time 600)
echo "${response}"
