#!/bin/sh
# Restart the API on a fresh audit chain. Deleting the file is not enough:
# the running process keeps the old database open.
set -e
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
API="${SURGESHIELD_API:-http://127.0.0.1:8010}"
KEY="${SURGESHIELD_API_KEY:-surgeshield-demo}"

PIDS="$(lsof -nP -iTCP:8010 -sTCP:LISTEN -t 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
  kill $PIDS || true
  sleep 0.4
fi

rm -f "$ROOT/backend/data/audit.db" "$ROOT/backend/data/history.db"
mkdir -p "$ROOT/backend/data"
nohup env -u SURGESHIELD_DATASET PYTHONPATH=. .venv/bin/uvicorn backend.app.main:app \
  --host 127.0.0.1 --port 8010 --loop asyncio --http h11 \
  >> "$ROOT/backend/data/api.log" 2>&1 &

i=0
until curl -sf "$API/health" >/dev/null; do
  i=$((i + 1))
  if [ "$i" -ge 40 ]; then
    echo "API did not start. See backend/data/api.log"
    exit 1
  fi
  sleep 0.5
done

BODY="$(curl -sf -H "X-API-Key: $KEY" "$API/audit/verify")"
python3 -c '
import json, sys
body = json.loads(sys.argv[1])
if body.get("ok"):
    print("Chain intact (%s records)" % body.get("records", 0))
else:
    print("Broken at record %s" % body.get("broken_at"))
    sys.exit(1)
' "$BODY"

echo "Dashboard: http://localhost:3010"
echo "API:       $API"
