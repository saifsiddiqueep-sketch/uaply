#!/usr/bin/env python3
"""Bot ledger: so no bot (sub-chat) is ever forgotten or left half-done. Zero model tokens.

Hooks call it automatically:
  SubagentStart -> jobs.py start   (records the bot as RUNNING)
  SubagentStop  -> jobs.py stop    (marks it DONE with the first line of its result)
  SessionStart  -> hook_start.py prints any bot still RUNNING from an earlier session as ORPHANED
You can run:
  python tools/lite/jobs.py list          # running + last 10 finished
  python tools/lite/jobs.py clear <id>    # mark an orphan as handled
  python tools/lite/jobs.py clear-mine    # /handoff: drop THIS chat's finished bots (session from $CLAUDE_CODE_SESSION_ID)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _common import LITE_DIR, _Lock  # noqa: E402

LEDGER = LITE_DIR / "jobs.json"


def load():
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(d):
    LITE_DIR.mkdir(parents=True, exist_ok=True)
    # keep the file small: drop finished jobs older than 7 days
    cutoff = time.time() - 7 * 86400
    d = {k: v for k, v in d.items() if v.get("status") == "RUNNING" or v.get("ended", 0) > cutoff}
    tmp = LEDGER.with_name(f"jobs.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    os.replace(tmp, LEDGER)   # atomic


def payload():
    try:
        return json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except Exception:
        return {}


def running(exclude_session=None):
    return [(k, v) for k, v in load().items()
            if v.get("status") == "RUNNING" and v.get("session") != exclude_session]


def main(a):
    cmd = a[0] if a else "list"
    if cmd in ("start", "stop", "clear", "clear-mine"):
        with _Lock(LEDGER):
            return _locked(cmd, a)
    if cmd == "list":
        return _locked(cmd, a)
    print(__doc__)


def _locked(cmd, a):
    if cmd == "start":
        p = payload()
        jid = p.get("agent_id") or f"job-{int(time.time())}"
        d = load()
        d[jid] = {"type": p.get("agent_type", "?"), "session": p.get("session_id"), "cwd": p.get("cwd"),
                  "started": time.time(), "status": "RUNNING"}
        save(d)
    elif cmd == "stop":
        p = payload()
        jid = p.get("agent_id")
        d = load()
        if jid in d:
            msg = (p.get("last_assistant_message") or "").strip().splitlines()
            d[jid].update(status="DONE", ended=time.time(), result=(msg[0][:120] if msg else ""))
            save(d)
    elif cmd == "list":
        d = load()
        if not d:
            print("No bots recorded.")
        for k, v in sorted(d.items(), key=lambda kv: -kv[1].get("started", 0))[:15]:
            age = int((time.time() - v.get("started", 0)) / 60)
            print(f"{v['status']:8} {v.get('type', '?'):12} {age:>4} min ago  {k}  {v.get('result', '')}")
    elif cmd == "clear-mine":
        sid = a[1] if len(a) > 1 else (os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID"))
        if not sid:
            print("No session id (CLAUDE_CODE_SESSION_ID unset) — nothing cleared.")
            sys.exit(0)
        d = load()
        mine = [k for k, v in d.items() if v.get("session") == sid]
        gone = [k for k in mine if d[k].get("status") != "RUNNING"]
        for k in gone:
            del d[k]
        save(d)
        still = len(mine) - len(gone)
        print(f"Cleared {len(gone)} finished bot record(s) from this chat."
              + (f" {still} still RUNNING — say so in the handoff." if still else ""))
    elif cmd == "clear" and len(a) > 1:
        d = load()
        if a[1] in d:
            d[a[1]].update(status="CLEARED", ended=time.time())
            save(d)
            print(f"{a[1]} cleared")
    sys.exit(0)


if __name__ == "__main__":
    main(sys.argv[1:])
