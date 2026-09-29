#!/bin/sh
# Start a jury demo with an intact audit chain.
set -e
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
rm -f "$ROOT/backend/data/audit.db"
API="${SURGESHIELD_API:-http://127.0.0.1:8010}"
if curl -sf -H "X-API-Key: ${SURGESHIELD_API_KEY:-surgeshield-demo}" -X POST "$API/simulate/reset" >/dev/null; then
  echo "Engine reset at $API"
else
  echo "Audit database removed. Start the API, then open the dashboard."
fi
echo "Dashboard: http://localhost:3010"
echo "API:       $API"
