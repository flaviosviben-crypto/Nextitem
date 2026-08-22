#!/usr/bin/env bash
# Start RevenueOS locally, refusing to hide behind a stale process.
#
# The failure this exists to prevent: a previous server keeps the port, the new
# one dies with EADDRINUSE, and every health check still returns 200 — from the
# OLD code. The app then serves a mix of new frontend and stale backend, which
# looks like a bug in the product rather than a bug in the startup.
set -euo pipefail
cd "$(dirname "$0")"

port_owner() { lsof -ti tcp:"$1" 2>/dev/null || true; }

for port in 8000 3000; do
  owner=$(port_owner "$port")
  if [ -n "$owner" ]; then
    echo "Port $port is already held by PID $owner."
    echo "Stop it first:  kill $owner"
    exit 1
  fi
done

mkdir -p .logs
( cd backend && setsid nohup .venv/bin/python -m uvicorn app.main:app --port 8000 \
    > ../.logs/api.log 2>&1 < /dev/null & )
( cd frontend && setsid nohup npx next dev -p 3000 \
    > ../.logs/web.log 2>&1 < /dev/null & )

# Wait for the API, then prove it is *this* build by asking for a route that
# only exists here. A 200 on /api/health alone would not have caught the bug.
for _ in $(seq 30); do
  sleep 1
  code=$(curl -s -m 2 -o /dev/null -w '%{http_code}' localhost:8000/api/overview || true)
  [ "$code" = "200" ] && break
done
if [ "${code:-}" != "200" ]; then
  echo "Backend did not come up as the current build (/api/overview -> ${code:-no response})."
  tail -20 .logs/api.log
  exit 1
fi

for _ in $(seq 30); do
  sleep 1
  curl -sf -m 2 -o /dev/null localhost:3000 && break
done

echo "RevenueOS is up:  http://localhost:3000   (API http://localhost:8000)"
echo "Logs: .logs/api.log  .logs/web.log"
