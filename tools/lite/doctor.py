#!/usr/bin/env python3
"""Workflow Lite v1.6 Core self-test. Every line is PASS or FAIL with the fix. Costs zero tokens.

  python tools/lite/doctor.py
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _common import ENV_FILE, STATE_DIR, git, load_env, read_state, trello  # noqa: E402

fails = 0
HERE = Path(__file__).resolve().parent


def check(name, ok, fix=""):
    global fails
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  → {fix}"))
    fails += 0 if ok else 1


def run_hook(script, payload):
    """Run a hook exactly the way Claude Code will: through run.sh with JSON on stdin."""
    bash = shutil.which("bash")
    if not bash:
        return 127, "", "bash not found"
    r = subprocess.run([bash, str(HERE / "run.sh"), script], input=json.dumps(payload), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=30)
    return r.returncode, r.stdout, r.stderr


def main():
    load_env()
    print(f"Python {sys.version.split()[0]} · {sys.platform}")
    root = git("rev-parse", "--show-toplevel", check=False)
    check("inside a git repo", bool(root), "cd into your UAply clone")
    origin = git("remote", "get-url", "origin", check=False)
    check("origin is the UAply repo", "uaply" in origin.lower(), f"origin is '{origin}'")

    settings = Path(root or ".") / ".claude" / "settings.json"
    try:
        cfg = json.loads(settings.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    hooks = cfg.get("hooks", {})
    for ev in ("SessionStart", "UserPromptSubmit", "SubagentStart", "SubagentStop", "PostToolUse"):
        check(f"hook {ev} registered", ev in hooks, "copy .claude/settings.json from the Lite package")
    check("hooks use the run.sh launcher (Mac + Windows safe)", "run.sh" in json.dumps(hooks),
          "use the v1.6 settings.json (hooks call tools/lite/run.sh)")
    check("ultracode off by default", cfg.get("ultracode") is False, 'set "ultracode": false')
    check("effort cap allows xhigh", cfg.get("maxEffortLevel") in ("xhigh", "max"), 'set "maxEffortLevel": "xhigh"')

    check("~/.uaply/lite.env exists", ENV_FILE.exists(), f"create {ENV_FILE} with FOUNDER=Mohammed (or Saif)")
    check("FOUNDER set (Mohammed or Saif)", os.environ.get("FOUNDER", "").lower() in ("mohammed", "saif"),
          f"FOUNDER is '{os.environ.get('FOUNDER', '')}' — put FOUNDER=Mohammed or FOUNDER=Saif in lite.env")

    # Real end-to-end hook runs (this is what catches Windows encoding and Mac python3 problems)
    code, out, err = run_hook("hook_start.py", {"session_id": "doctor-test", "source": "startup"})
    check("start hook runs and prints", code == 0 and "[lite]" in out, (err or out or f"exit {code}")[:160])
    code, out, err = run_hook("statusline.py", {"session_id": "doctor-test", "model": {"display_name": "Test ⚠"},
                                                "effort": {"level": "medium"},
                                                "context_window": {"total_input_tokens": 160000}})
    check("status line runs (incl. ⚠ symbols)", code == 0 and "ctx 160k" in out, (err or out or f"exit {code}")[:160])
    code, out, err = run_hook("hook_prompt.py", {"session_id": "doctor-test", "prompt": "hello"})
    check("big-chat blocker stops a 160k chat", code == 2 and "go!" in err, f"exit {code}: {(err or out)[:120]}")
    code, out, err = run_hook("hook_prompt.py", {"session_id": "doctor-test", "prompt": "go! hello"})
    check("'go!' lets a message through", code == 0, f"exit {code}: {(err or out)[:120]}")
    code, out, err = run_hook("hook_prompt.py", {"session_id": "doctor-brief", "prompt": " ".join(["word"] * 85)})
    check("long prompt gets the /brief line", code == 0 and "Long/dictated" in out, f"exit {code}: {(err or out)[:120]}")
    code, out, err = run_hook("hook_prompt.py", {"session_id": "doctor-brief", "prompt": "hello"})
    check("short prompt gets no /brief line", code == 0 and "Long/dictated" not in out, f"exit {code}: {(err or out)[:120]}")
    for f in STATE_DIR.glob("sess-doctor-*.json"):
        f.unlink()

    s = read_state()
    seen = s.get("seen_at")
    check("status line has run inside Claude Code", bool(seen) and time.time() - seen < 7 * 86400,
          "open Claude Code in the repo once, then re-run doctor (if still FAIL: /statusline)")
    try:
        me = trello("GET", "/members/me", {"fields": "username"})
        check("Trello credentials work (optional)", bool(me.get("username")))
    except Exception as e:
        print(f"SKIP  Trello credentials (optional): {str(e)[:90]}")
    # /handoff posts to the '📍 Areas' cards; if that list is missing, handoffs can't be shared.
    import trello as tr  # noqa: E402 — same folder
    if tr.missing_keys():
        print(f"WARN  /handoff can't post to Trello yet → {tr._keys_msg(tr.missing_keys())}")
    else:
        try:
            cards = tr.area_cards()
            check(f"'{tr.AREAS_LIST}' list has 12 area cards (found {len(cards)})", len(cards) == 12,
                  "restore/unarchive the area cards in Trello so each area has exactly one card")
        except Exception as e:
            check(f"'{tr.AREAS_LIST}' list reachable for /handoff", False, tr._explain(e))
    check("node available (for ccusage + check.js)", bool(shutil.which("node")), "install Node.js LTS from nodejs.org")
    r = git("ls-remote", "origin", "refs/heads/lock/*", check=False, timeout=15)
    check("GitHub reachable for the merge lock", r is not None, "check your internet / GitHub login")
    print(f"\n{'ALL GOOD' if not fails else f'{fails} problem(s) — fix the FAIL lines above'}")
    sys.exit(min(fails, 1))


if __name__ == "__main__":
    main()
