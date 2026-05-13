#!/usr/bin/env bash
# Restore the placebo DB from an S3 snapshot.
#
# Usage:
#   ./scripts/restore.sh                   # list available snapshots
#   ./scripts/restore.sh <s3-key>          # restore that snapshot (with confirmation)
#   ./scripts/restore.sh <s3-key> --yes    # skip confirmation
#
# Talks to the running `api` service on http://localhost:8000. The backup
# service takes a pre-restore safety snapshot automatically before wiping
# the DB, so this is recoverable if you change your mind within 30 days.

set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"

list_snapshots() {
  echo "Fetching snapshot list from ${API_URL}/backups ..."
  curl -sS "${API_URL}/backups" \
    | python3 -c '
import json, sys
snaps = json.load(sys.stdin)
if not snaps:
    print("(no snapshots)")
    sys.exit(0)
print(f"{\"KIND\":<13} {\"SIZE\":>10} {\"WHEN\":<22} KEY")
for s in snaps:
    size_mb = s["size_bytes"] / 1024 / 1024
    print(f"{s[\"kind\"]:<13} {size_mb:>8.2f}MB {s[\"last_modified\"][:19]:<22} {s[\"key\"]}")
'
}

if [[ $# -eq 0 ]]; then
  list_snapshots
  echo
  echo "To restore: ./scripts/restore.sh <s3-key>"
  exit 0
fi

KEY="$1"
SKIP_CONFIRM="${2:-}"

if [[ "${SKIP_CONFIRM}" != "--yes" ]]; then
  echo "About to restore: ${KEY}"
  echo "This will WIPE the current database and replace it with the snapshot."
  echo "A pre-restore safety snapshot will be taken first."
  read -r -p "Type 'restore' to confirm: " confirm
  if [[ "${confirm}" != "restore" ]]; then
    echo "Aborted."
    exit 1
  fi
fi

echo "Restoring from ${KEY} ..."
# URL-encode the key for the query param.
encoded=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "${KEY}")
curl -sS -X POST "${API_URL}/backups/restore?key=${encoded}" --max-time 1200
echo
