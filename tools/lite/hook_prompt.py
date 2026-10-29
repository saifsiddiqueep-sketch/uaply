#!/usr/bin/env python3
"""UserPromptSubmit hook — runs BEFORE your message reaches Claude (costs 0 tokens when it blocks).

BIG-CHAT BLOCKER: if this chat is ≥150k tokens, or it was idle ≥60 min and is ≥30k, the message is stopped
before Claude re-reads the whole chat. Choose: /clear (free fresh start), /handoff (save first, then /clear),
or start the message with  go!  to send it anyway.   [fix 4: was "!go", but "!" means shell mode in Claude Code]
Otherwise adds one [lite] line (model · effort · context) for the MODE check."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _common import read_stdin_json, read_sess, read_state, write_sess  # noqa: E402

BIG_K, IDLE_MIN, IDLE_MIN_K = 150, 60, 30
ESCAPE = "go!"


def main():
    d = read_stdin_json()
    sid = d.get("session_id")
    prompt = (d.get("prompt") or "").strip()
    s, g = read_sess(sid), read_state()
    ctx = int(s.get("ctx_k") or 0)
    last = s.get("last_prompt_at")
    idle = int((time.time() - last) / 60) if last else 0

    forced = prompt.lower().startswith(ESCAPE)
    exempt = forced or prompt.startswith("/")
    if not exempt and (ctx >= BIG_K or (idle >= IDLE_MIN and ctx >= IDLE_MIN_K)):
        why = f"this chat is {ctx}k tokens" if ctx >= BIG_K else f"you were away {idle} min and this chat is {ctx}k"
        print(f"⛔ Workflow Lite stopped this message to save tokens: {why}, so sending it would re-read the whole chat.\n"
              f"   • /clear    → free fresh start (your branch, Trello and handoff files are still there)\n"
              f"   • /handoff  → save what only this chat knows, then /clear\n"
              f"   • {ESCAPE} <your message> → send it anyway", file=sys.stderr)
        sys.exit(2)

    effort = d.get("effort")
    effort = effort.get("level") if isinstance(effort, dict) else effort
    effort = effort or s.get("effort") or g.get("effort", "unknown")
    model = s.get("model") or g.get("model", "unknown (status line not running)")
    write_sess(sid, {"last_prompt_at": time.time()})
    print(f"[lite] running {model} · effort {effort} · context {ctx}k")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        pass   # never block a prompt because of a hook bug
