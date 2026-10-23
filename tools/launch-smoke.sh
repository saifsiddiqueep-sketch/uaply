#!/usr/bin/env bash
# The launch-day smoke check in one command (docs/runbook-launch.md, steps 3 and 4). Read only: it never signs up, sends email or
# changes anything on the site.
#   bash tools/launch-smoke.sh https://uaply.net [folder]
# In order: one timed /healthz probe, tools/live-check.py --expect all --no-rate-limit (every SKIP with its reason), tools/ui-live.js at 390x844 and 1280x800 in
# --read-only mode, then one summary block: PASS / FAIL / SKIP counts per tool, the healthz time, the commit the site runs (from
# /api/status) and the local time. With UAPLY_OWNER_PASSWORD set in this terminal (never typed on the command line), it also reads the
# owner's self-check from /api/status. The summary and both tools' full output go to <folder>/launch-smoke-<time>.txt (folder: the
# second argument, else $TMPDIR, else the system temp folder). Exit code: 0 when no tool reported a FAIL.
# What "read only" means here: live-check.py runs with --no-rate-limit (no wrong-password tries) and its other writes are ones the site
# must refuse or that change nothing (a sign-in from another site, a sign-up with no Origin, Stripe's and Brevo's webhooks without their
# signature or secret, a checkout with no account, Forgot password for a made-up example.com address that has no account, a sign-out
# with no session, the help assistant's question); ui-live.js --read-only answers every non-GET request to the
# site in the browser instead of sending it (the help assistant's question is sent: the site answers it from its articles and keeps nothing).
cd "$(dirname "$0")/.." || exit 2
BASE="${1%/}"
if ! printf '%s' "$BASE" | grep -Eq '^https?://[^/]+$'; then echo "usage: bash tools/launch-smoke.sh https://uaply.net [folder]"; exit 2; fi
DIR="${2:-${TMPDIR:-${TEMP:-/tmp}}}"
mkdir -p "$DIR" || exit 2
STAMP="$(date +%Y-%m-%d-%H%M%S)"
FILE="$DIR/launch-smoke-$STAMP.txt"
LC="$(mktemp)"; UL="$(mktemp)"
trap 'rm -f "$LC" "$UL" "$GL"' EXIT

counts() {  # counts <log>: "P passed, F failed, S skipped" from the tool's own last summary line
  grep -Eo '^[0-9]+ passed, [0-9]+ failed, [0-9]+ skipped' "$1" | tail -1
}

# 1. healthz, timed
HZ="$(curl -s -o /dev/null -m 60 -w '%{http_code} in %{time_total} s' "$BASE/healthz" 2>/dev/null || echo "no answer")"
echo "healthz: $HZ"

# 2. the live check
echo "live-check.py ..."
PYTHONIOENCODING=utf-8 python tools/live-check.py --base "$BASE" --expect all --no-rate-limit > "$LC" 2>&1
LCC="$(counts "$LC")"

# 3. a stranger's first visit, both sizes, nothing sent that could change the site
echo "ui-live.js (390x844 and 1280x800, read only) ..."
node tools/cdp.js tools/ui-live.js --base "$BASE" --read-only > "$UL" 2>&1
ULC="$(counts "$UL")"

# 3b. the sign-in gate, when the server says it is on (/api/status or /api/auth/providers "gate": true), or GATE=1 in this terminal
GL="$(mktemp)"; GLC="not run (the server does not report the gate on)"
GATE_ON="$(curl -s -m 30 "$BASE/api/status" "$BASE/api/auth/providers" | python -c "import sys,json,re
t=sys.stdin.read(); print('yes' if re.search(r'\"gate\"\s*:\s*true', t) else 'no')")"
if [ "$GATE_ON" = yes ] || [ "$GATE" = 1 ]; then
  echo "ui-gate-live.js (390x844 and 1280x800, read only) ..."
  node tools/cdp.js tools/ui-gate-live.js --base "$BASE" > "$GL" 2>&1
  GLC="$(grep -Eo '^[0-9]+ passed, [0-9]+ failed, [0-9]+ waiting' "$GL" | tail -1)"
fi

# 4. what the site says it runs (public), and the owner's self-check when the password is in this terminal
STATUS="$(curl -s -m 30 "$BASE/api/status")"
COMMIT="$(printf '%s' "$STATUS" | python -c "import sys,json
try: print(json.load(sys.stdin).get('commit') or 'not given')
except Exception: print('no /api/status answer')")"
SELF="not read (set UAPLY_OWNER_PASSWORD in this terminal to read it)"
if [ -n "$UAPLY_OWNER_PASSWORD" ]; then
  SELF="$(curl -s -m 30 -u "owner:$UAPLY_OWNER_PASSWORD" "$BASE/api/status" | python -c "import sys,json
try:
    s=json.load(sys.stdin).get('selfCheck')
    print('not in this answer (wrong password, or a deploy without it)' if not s else ('ok' if s.get('ok') else 'WARNINGS: ' + '; '.join(map(str, s.get('warnings') or []))))
except Exception: print('no answer')")"
fi

FAILS=$(( $(grep -c '^FAIL' "$LC") + $(grep -c '^FAIL' "$UL") + $(grep -c '^TEST SCRIPT FAILED' "$UL") + $(grep -c '^FAIL\|^TEST SCRIPT FAILED' "$GL") ))
{
  echo "UAply launch smoke check of $BASE"
  echo "  local time      $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "  healthz         $HZ"
  echo "  site runs       $COMMIT"
  echo "  live-check.py   ${LCC:-no summary (see below)}"
  echo "  ui-live.js      ${ULC:-no summary (see below)}   (390x844 and 1280x800, read only)"
  echo "  ui-gate-live.js ${GLC:-no summary (see below)}"
  echo "  owner check     $SELF"
  echo "  result          $( [ "$FAILS" -eq 0 ] && echo "no FAIL" || echo "$FAILS FAIL line(s): see below")"
  grep -E '^(FAIL|TEST SCRIPT FAILED)' "$LC" "$UL" "$GL" | sed 's/^[^:]*://; s/^/    /'
  echo "  skips (each with its reason):"
  grep -hE '^SKIP' "$LC" "$UL" | sed 's/^/    /'
} > "$FILE.summary"
cat "$FILE.summary"
{ cat "$FILE.summary"; echo; echo "===== live-check.py"; cat "$LC"; echo; echo "===== ui-live.js --read-only"; cat "$UL"; echo; echo "===== ui-gate-live.js"; cat "$GL"; } > "$FILE"
rm -f "$FILE.summary"
echo "written to $FILE"
[ "$FAILS" -eq 0 ]
