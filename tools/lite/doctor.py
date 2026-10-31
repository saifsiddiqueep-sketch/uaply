#!/usr/bin/env python3
"""Workflow Lite v1.6 Core self-test. Every line is PASS or FAIL with the fix. Costs zero tokens.

  python tools/lite/doctor.py                  setup self-test (+ protected rules)
  python tools/lite/doctor.py --weekly [--today YYYY-MM-DD]   scorecard: this week vs last week
  python tools/lite/doctor.py --protected      only the protected-rules check (proposals may only tighten them)
  python tools/lite/doctor.py --log ship card=189 pr=107 stage=sandbox   append one event (used by /ship)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _common import ENV_FILE, STATE_DIR, die, git, load_env, log_event, read_events, read_state, trello  # noqa: E402

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
    # the self-test's fake prompts go to a temp events file, never the real scorecard log
    env = dict(os.environ, UAPLY_EVENTS_FILE=str(Path(tempfile.gettempdir()) / "uaply-doctor-events.jsonl"))
    r = subprocess.run([bash, str(HERE / "run.sh"), script], input=json.dumps(payload), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=30, env=env)
    return r.returncode, r.stdout, r.stderr


# ---- protected rules: a weekly proposal may only make these STRICTER ---------------------------
# (name, file, check). A check is a text that must stay in the file, or (CONSTANT, highest allowed value).
# Loosening one (deleting the text, raising the number) makes `doctor.py --protected` and the test suite FAIL.
PROTECTED_RULES = [
    ("consent/auto-submit: consent boxes are left for the person", "shared/uaply-assist.js", "the person ticks it"),
    ("consent/auto-submit: never submits automatically", "docs/apply-by-email.md", "never submits automatically"),
    ("UI gate (real app, Mohammed approves)", "CLAUDE.md", "**UI GATE:"),
    ("UI gate (real app, Mohammed approves)", "CLAUDE.md", "REAL APP ONLY"),
    ("UI gate (real app, Mohammed approves)", "CLAUDE.md", "until Mohammed gives an explicit"),
    ("live = Saif only", "CLAUDE.md", "Live: Saif only"),
    ("live = Saif only", "tools/lite/queue.py", "live promotion is Saif-only"),
    ("secrets guard", "tools/lite/handoff_wip.py", "an AI provider API key"),
    ("secrets guard", "CLAUDE.md", "never commit secrets"),
    ("merge lock", "CLAUDE.md", "`queue.py take sandbox`"),
    ("merge lock", "tools/lite/queue.py", "def take("),
    ("no CAPTCHA/login bypass: the person answers human checks", "docs/assisted-apply.md", "the person answers"),
    ("no CAPTCHA/login bypass: the person answers human checks", "shared/uaply-assist.js", "humanCheck"),
    ("never invent facts", "docs/handbook/07-conventions.md", "Never invent an answer"),
    ("big-chat block stays at ≤150k", "tools/lite/hook_prompt.py", ("BIG_K", 150)),
    ("idle block stays at ≤60 min", "tools/lite/hook_prompt.py", ("IDLE_MIN", 60)),
    ("100k warning stays at ≤100k", "tools/lite/hook_prompt.py", ("WARN_K", 100)),
]


def repo_root():
    return Path(os.environ.get("UAPLY_ROOT") or git("rev-parse", "--show-toplevel", check=False) or HERE.parent.parent)


def _const(text, name):
    """Value of NAME in 'NAME = 1' or 'A, NAME, C = 1, 2, 3' (the hook_prompt.py style).
    None (→ FAIL) unless NAME is assigned exactly once, so a later 'BIG_K = 500' can't slip past."""
    hits = []
    for line in text.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        left, right = line.split("#", 1)[0].split("=", 1)
        names = [x.strip() for x in left.split(",")]
        if name in names:
            vals = [x.strip() for x in right.split(",")]
            try:
                hits.append(float(vals[names.index(name)]))
            except (ValueError, IndexError):
                return None
    return hits[0] if len(hits) == 1 else None


def protected(root=None):
    """PASS/FAIL per protected rule. Returns the number of loosened rules."""
    root = Path(root or repo_root())
    bad = 0
    for name, rel, rule in PROTECTED_RULES:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except OSError:
            text = ""
        if isinstance(rule, tuple):
            v = _const(text, rule[0])
            ok, what = v is not None and v <= rule[1], f"{rule[0]} must stay ≤ {rule[1]} (is {v})"
        else:
            ok, what = rule in text, f"'{rule}' was removed"
        print(f"{'PASS' if ok else 'FAIL'}  protected: {name} ({rel})" + ("" if ok else f"  → {what}; proposals may only make it stricter"))
        bad += 0 if ok else 1
    return bad


# ---- weekly scorecard: events.jsonl + ccusage, this week vs last week ----------------------------
CCUSAGE = "ccusage@20.0.46"      # pinned: npx must not fetch whatever is newest on npm
def ccusage_days():
    """[{date, cost, opus}] from `npx ccusage daily --json` (or the UAPLY_CCUSAGE_JSON file in tests). [] if n/a."""
    try:
        f = os.environ.get("UAPLY_CCUSAGE_JSON")
        if f:
            raw = Path(f).read_text(encoding="utf-8")
        else:
            npx = shutil.which("npx")
            if not npx:
                return []
            raw = subprocess.run([npx, "--yes", CCUSAGE, "daily", "--json"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=120).stdout
        out = []
        for d in json.loads(raw).get("daily", []):
            opus = sum(m.get("cost", 0) for m in d.get("modelBreakdowns", []) if "opus" in str(m.get("modelName", "")).lower())
            out.append({"date": d.get("date", ""), "cost": float(d.get("totalCost", 0) or 0), "opus": float(opus)})
        return out
    except Exception:
        return []


def _median(xs):
    xs = sorted(xs)
    return None if not xs else xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2


def _hours(m):
    return "n/a" if m is None else f"{m / 3600:.1f} h" if m < 2 * 86400 else f"{m / 86400:.1f} d"


def week_stats(ev, days, t0, t1, card_start):
    """Numbers for one 7-day window [t0, t1)."""
    w = [e for e in ev if t0 <= e.get("ts", 0) < t1]
    k = lambda kind, **f: [e for e in w if e.get("kind") == kind and all(e.get(a) == b for a, b in f.items())]  # noqa: E731
    d0, d1 = time.strftime("%Y-%m-%d", time.localtime(t0)), time.strftime("%Y-%m-%d", time.localtime(t1 - 1))
    cd = [d for d in days if d0 <= d["date"] <= d1]
    cost = sum(d["cost"] for d in cd)
    merged = k("ship", stage="sandbox")
    live = k("ship", stage="dev")
    to_sb = [e["ts"] - card_start[e.get("card")] for e in merged if e.get("card") in card_start]
    to_live = [e["ts"] - card_start[e.get("card")] for e in live if e.get("card") in card_start]
    pr_fix = {}
    for e in k("ship", stage="fix"):
        pr_fix[e.get("pr")] = pr_fix.get(e.get("pr"), 0) + 1
    findings = [e.get("findings", 0) for e in k("ship", stage="review")]
    suites = k("suite", action="end")
    failed_labels = {x for e in suites for x in str(e.get("failing", "none")).split("|") if x and x != "none"}
    return {
        "cost_day": (cost / 7) if cd else None, "cost_pr": (cost / len(merged)) if cd and merged else None,
        "opus_share": (sum(d["opus"] for d in cd) / cost) if cost else None,
        "cold": len(k("session", source="resume")) + sum(1 for e in k("prompt") if e.get("blocked") and e.get("idle_min", 0) > 60),
        "compactions": len(k("session", source="compact")),
        "merged": len(merged), "completed": len([e for e in k("card", action="move") if "complet" in str(e.get("to", "")).lower()]),
        "to_sandbox": _median(to_sb), "to_live": _median(to_live),
        "ui_rejects": len(k("ship", ui_gate="reject")),
        "findings_pr": (sum(findings) / len(findings)) if findings else None,
        "second_fix": sum(1 for n in pr_fix.values() if n >= 2), "reverts": len(k("ship", stage="revert")),
        "lock_timeouts": len(k("lock", action="timeout")), "handoff_fails": len(k("handoff", action="post", ok=False)),
        "stale_bots": len(k("bot", action="stale")), "concurrent": len(k("suite", action="start", concurrent=1)),
        "flaky": len(failed_labels) if any(e.get("fails") == 0 for e in suites) else 0,
        "false_alarms": len([e for e in k("prompt") if e.get("override")]),
    }


SCORECARD = [
    ("EFFICIENCY", [("$/day", "cost_day", "${:.2f}"), ("$/merged PR", "cost_pr", "${:.2f}"),
                    ("Opus share", "opus_share", "{:.0%}"), ("cold resumes", "cold", "{}"), ("compactions", "compactions", "{}")]),
    ("PRODUCTIVITY", [("PRs merged to sandbox", "merged", "{}"), ("cards reaching Completed", "completed", "{}"),
                      ("median card start→sandbox", "to_sandbox", _hours), ("median card start→live", "to_live", _hours)]),
    ("EFFECTIVENESS", [("UI-gate rejects", "ui_rejects", "{}"), ("review findings/PR", "findings_pr", "{:.1f}"),
                       ("PRs needing a 2nd fix", "second_fix", "{}"), ("reverts", "reverts", "{}")]),
    ("RELIABILITY", [("lock timeouts", "lock_timeouts", "{}"), ("handoff failures", "handoff_fails", "{}"),
                     ("stale bots", "stale_bots", "{}"), ("concurrent suites", "concurrent", "{}"),
                     ("flaky groups", "flaky", "{}"), ("guard false alarms (go! overrides)", "false_alarms", "{}")]),
]


def weekly(today=None):
    """Print this week vs last week. today = 'YYYY-MM-DD' (tests); the week is the 7 days ending that day."""
    day = time.strptime(today, "%Y-%m-%d") if today else time.localtime()
    end = time.mktime((day.tm_year, day.tm_mon, day.tm_mday + 1, 0, 0, 0, 0, 0, -1))
    ev = read_events(end - 14 * 86400 - 60 * 86400)          # card starts up to 60 days back
    card_start = {}
    for e in ev:
        if e.get("kind") == "ship" and e.get("stage") == "start" and e.get("card") not in card_start:
            card_start[e.get("card")] = e["ts"]
    days = ccusage_days()
    this, last = (week_stats(ev, days, end - 7 * 86400, end, card_start),
                  week_stats(ev, days, end - 14 * 86400, end - 7 * 86400, card_start))
    fmt = lambda v, f: "n/a" if v is None else (f(v) if callable(f) else f.format(v))  # noqa: E731
    print(f"Workflow Lite scorecard — 7 days to {time.strftime('%a %Y-%m-%d', day)} (this week vs last week)")
    if not days:
        print("  (ccusage n/a — $ lines need `npx ccusage daily --json`; Node.js + internet)")
    for section, rows in SCORECARD:
        print(section)
        for label, key, f in rows:
            print(f"  {label:<38} {fmt(this[key], f):>9}   (last {fmt(last[key], f)})")
    if day.tm_wday == 0:
        print("\nMonday review: post this scorecard (signed) on the Release & Health area card; propose ≤3 tweaks to "
              "EXISTING rules/thresholds/skills (metric · predicted effect · undo) in ONE PR nobody merges without "
              "Mohammed; check last week's tweaks (keep / revert / extend) under 'Experiments' in docs/workflow-lite.md; "
              "turn open 'Incidents' into proposals. Protected rules may only get stricter.")
        if day.tm_mday <= 7:
            print("First Monday of the month: also run the 30-day review on Opus.")
    return this


def log_cli(args):
    """doctor.py --log <kind> key=value ...   (used by /ship: PR #, card #, stage, UI-gate result)."""
    if not args:
        die("usage: doctor.py --log <kind> key=value ...")
    fields = {}
    for a in args[1:]:
        k, _, v = a.partition("=")
        fields[k] = int(v) if v.lstrip("-").isdigit() else v
    log_event(args[0], **fields)
    print(f"logged {args[0]} " + " ".join(f"{k}={v}" for k, v in fields.items()))


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
    check("protected rules intact (consent, UI gate, live, secrets, lock, CAPTCHA, facts)", protected(root or None) == 0,
          "a change loosened a protected rule — undo it (proposals may only make them stricter)")
    print(f"\n{'ALL GOOD' if not fails else f'{fails} problem(s) — fix the FAIL lines above'}")
    sys.exit(min(fails, 1))


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv[:1] == ["--weekly"]:
        weekly(argv[argv.index("--today") + 1] if "--today" in argv else None)
    elif argv[:1] == ["--protected"]:
        sys.exit(min(protected(), 1))
    elif argv[:1] == ["--log"]:
        log_cli(argv[1:])
    else:
        main()
