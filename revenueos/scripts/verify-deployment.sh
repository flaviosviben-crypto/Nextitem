#!/usr/bin/env bash
# Verify a RevenueOS deployment by what it returns, not by whether it returns.
#
#   ./scripts/verify-deployment.sh https://revenueos-web.onrender.com
#
# A 200 proved nothing the last time this app broke: a stale backend answered
# every health check happily while serving the previous build. So each check
# below asserts on content that only the current version produces.
set -uo pipefail

BASE="${1:-http://localhost:3000}"
BASE="${BASE%/}"
pass=0; fail=0

check() { # name, url-path, jq-ish grep assertion described in $3
  local name="$1" path="$2" assertion="$3"
  local body
  body=$(curl -sS -m 90 "$BASE$path" 2>/dev/null)
  if [ -z "$body" ]; then
    printf '  \033[31mFAIL\033[0m  %-34s no response (free tier cold start can take ~60s — retry)\n' "$name"
    fail=$((fail+1)); return
  fi
  if printf '%s' "$body" | python3 -c "
import json,sys
try: d = json.load(sys.stdin)
except Exception as e: sys.exit(f'not JSON: {e}')
sys.exit(0 if ($assertion) else 'assertion failed')
" 2>/dev/null; then
    printf '  \033[32mPASS\033[0m  %s\n' "$name"
    pass=$((pass+1))
  else
    printf '  \033[31mFAIL\033[0m  %-34s %s\n' "$name" "$(printf '%s' "$body" | head -c 160)"
    fail=$((fail+1))
  fi
}

echo "Verifying $BASE"
echo

check "health reports a loaded dataset"  /api/health      "d['status']=='ok' and d['loaded'] is True"
check "overview names today's work"      /api/overview    "d['loaded'] is True and isinstance(d['today']['opportunities'],int) and bool(d['today']['note'])"
check "overview has no undefined counts" /api/overview    "d['today']['opportunities'] is not None and all(r.get('customer_name') and r.get('why_now') for r in d['today']['top'])"
check "opportunities are per-customer"   /api/opportunities "d['shown'] is not None and d['shown']>0 and all(o.get('customer_id') and o.get('customer_name') and o.get('why_now') and o.get('action') for o in d['opportunities'])"
check "every opportunity is reachable"   /api/opportunities "all(o['contactable'] is True for o in d['opportunities'])"
check "action center has the 6 states"   /api/actions     "d['statuses']==['New','Approved','Scheduled','Contacted','Converted','Ignored']"
check "action rows carry a reason"       /api/actions     "len(d['rows'])>0 and all(r.get('customer_name') and r.get('reason') for r in d['rows'])"
check "performance separates the layers" /api/performance "'modelled, not measured' in d['incremental_revenue_basis'].lower() and bool(d['attribution_note'])"
check "audit log is reachable"           /api/audit       "'entries' in d and isinstance(d['entries'],list)"
check "customers split value/lifecycle"  "/api/customers?limit=3" "bool(d['facets']['value_tiers']) and bool(d['facets']['lifecycles'])"

echo
# Every check above was issued against the FRONTEND origin and came back with
# real data, which is itself the proof that its server-side proxy reaches the
# API. All that is left is that the app shell is served: the pages are client
# components, so their headings are not in the server HTML and grepping for
# them would only ever produce a false alarm.
shell=$(curl -sS -m 90 "$BASE/opportunities" 2>/dev/null)
if printf '%s' "$shell" | grep -q "RevenueOS"; then
  printf '  \033[32mPASS\033[0m  app shell served, proxy chain proven\n'
  pass=$((pass+1))
else
  printf '  \033[31mFAIL\033[0m  app shell not served\n'
  fail=$((fail+1))
fi

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ] || exit 1
