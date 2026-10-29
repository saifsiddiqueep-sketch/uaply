#!/usr/bin/env python3
"""Status line: model · effort · context size · 5h usage · merge locks · bots running.
Saves model/effort/context per chat so the blocker and MODE check use the right numbers. Costs zero tokens."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _common import read_stdin_json, read_state, write_sess, write_state  # noqa: E402


def main():
    d = read_stdin_json()
    model = (d.get("model") or {}).get("display_name") or "?"
    effort = (d.get("effort") or {}).get("level") or "n/a"
    cw = d.get("context_window") or {}
    ctx_k = int((cw.get("total_input_tokens") or 0) / 1000)
    five = ((d.get("rate_limits") or {}).get("five_hour") or {}).get("used_percentage")
    write_sess(d.get("session_id"), {"model": model, "effort": effort, "ctx_k": ctx_k})
    write_state({"model": model, "effort": effort, "seen_at": time.time()})
    g = read_state()
    parts = [f"{model} · {effort}", f"ctx {ctx_k}k" + (" ⚠ big — /clear soon" if ctx_k >= 120 else "")]
    if five is not None:
        parts.append(f"5h {int(five)}%")
    if g.get("locks"):
        age = int((time.time() - g.get("locks_at", 0)) / 60)
        parts.append(f"{g['locks']} ({age}m ago)" if age > 30 else g["locks"])
    try:
        from jobs import running
        n = len(running())
        if n:
            parts.append(f"bots running: {n}")
    except Exception:
        pass
    print("  |  ".join(parts))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Workflow Lite")
