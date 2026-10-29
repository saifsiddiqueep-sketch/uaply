#!/usr/bin/env python3
"""Background auto-check (PostToolUse on Edit/Write, async). Runs `node check.js` after Claude edits a
front-end/server file. SILENT when it passes (zero tokens). Only on failure does it wake Claude with the
last 15 lines (exit 2 + asyncRewake), so Claude never spends tokens running/reading passing checks.
Debounced: at most one run per 45 s."""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _common import read_state, write_state  # noqa: E402

EXTS = (".js", ".mjs", ".html", ".css", ".py", ".json")


def main():
    try:
        d = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except Exception:
        d = {}
    path = str((d.get("tool_input") or {}).get("file_path", ""))
    if not path.endswith(EXTS) or "/tools/lite/" in path.replace("\\", "/"):
        return 0
    if time.time() - read_state().get("last_check_at", 0) < 45:
        return 0
    write_state({"last_check_at": time.time()})
    root = os.environ.get("CLAUDE_PROJECT_DIR") or d.get("cwd") or "."
    if not os.path.exists(os.path.join(root, "check.js")):
        return 0
    try:
        r = subprocess.run(["node", "check.js"], cwd=root, capture_output=True, text=True, timeout=120)
    except Exception as e:
        print(f"[lite auto-check] could not run node check.js: {e}", file=sys.stderr)
        return 2
    if r.returncode == 0:
        return 0
    tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-15:])
    print(f"[lite auto-check] node check.js FAILED (exit {r.returncode}) after editing {os.path.basename(path)}:\n{tail}",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
