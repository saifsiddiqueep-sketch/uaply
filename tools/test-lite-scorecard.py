#!/usr/bin/env python3
"""Workflow Lite self-measurement: prompt guards (idle / 100k / Opus / late), the events log never holds prompt text or
secrets, `doctor.py --weekly` prints all four sections, and `doctor.py --protected` fails when a protected rule is
loosened. Uses a temp events file, a pinned clock and fake ccusage data — touches nothing real."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "lite"))
import hook_prompt  # noqa: E402
from _common import STATE_DIR, write_sess  # noqa: E402

FAILS = 0
TMP = Path(tempfile.mkdtemp(prefix="lite-scorecard-"))
EVENTS = TMP / "events.jsonl"
SIDS = []


def check(cond, what):
    global FAILS
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS += 1


def at(hour):
    """Local timestamp for today at <hour>:00."""
    lt = time.localtime()
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hour, 0, 0, 0, 0, -1))


def env(**extra):
    e = dict(os.environ, UAPLY_EVENTS_FILE=str(EVENTS), PYTHONIOENCODING="utf-8")
    e.setdefault("UAPLY_NOW", str(at(14)))
    e.update({k: str(v) for k, v in extra.items()})
    return e


def sess(name, **fields):
    sid = f"test-scorecard-{name}-{os.getpid()}"
    SIDS.append(sid)
    write_sess(sid, fields)
    return sid


def hook(prompt, sid, **extra):
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "lite" / "hook_prompt.py")],
                       input=json.dumps({"session_id": sid, "prompt": prompt}), capture_output=True, text=True,
                       encoding="utf-8", env=env(**extra))
    return r.returncode, r.stdout, r.stderr


def doctor(*args, **extra):
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "lite" / "doctor.py"), *args], capture_output=True,
                       text=True, encoding="utf-8", env=env(**extra))
    return r.returncode, r.stdout + r.stderr


try:
    noon = at(14)

    # (a) idle >60 min blocks with the four choices; "/" and go! are exempt
    sid = sess("idle", last_prompt_at=noon - 61 * 60, ctx_k=20)
    code, out, err = hook("what changed", sid)
    check(code == 2 and "/pickup" in err and "go!" in err and "/handoff" in err, "idle 61 min → blocked with /handoff, /clear, /pickup, go!")
    check(hook("/clear", sid)[0] == 0, "idle: /clear is not blocked")
    check(hook("go! keep going", sess("idle2", last_prompt_at=noon - 61 * 60))[0] == 0, "idle: go! sends anyway")
    check(hook("what changed", sess("idle59", last_prompt_at=noon - 59 * 60))[0] == 0, "idle 59 min → not blocked")
    check(hook("hi", sess("big", ctx_k=150))[0] == 2, "150k still blocks")

    # (b) 100k warning
    code, out, _ = hook("keep going", sess("warn", ctx_k=110))
    check(code == 0 and "110k" in out and "/handoff" in out, "110k → warning line")
    check("This chat is" not in hook("keep going", sess("nowarn", ctx_k=90))[1], "90k → no warning")

    # (c) Opus → sonnet nudge: once per chat, never on sensitive work
    sid = sess("opus", model="Opus 5.5")
    check(hook_prompt.OPUS_LINE in hook("move the trello card to waiting", sid)[1], "routine prompt on Opus → /model sonnet nudge")
    check(hook_prompt.OPUS_LINE not in hook("rename the card label", sid)[1], "nudge shows once per chat")
    check(hook_prompt.OPUS_LINE not in hook("fix the auth bug on the card", sess("opus2", model="Opus 5.5"))[1],
          "no nudge for auth/bug work")
    check(hook_prompt.OPUS_LINE not in hook("move the consent card", sess("opus3", model="Opus 5.5"))[1],
          "no nudge for consent work")
    check(hook_prompt.OPUS_LINE not in hook("move the trello card", sess("sonnet", model="Sonnet 5.5"))[1],
          "no nudge on Sonnet")

    # (d) late-session line after 1 AM, once
    sid = sess("late")
    check(hook_prompt.LATE_LINE in hook("keep going", sid, UAPLY_NOW=at(2))[1], "02:00 → late-session line")
    check(hook_prompt.LATE_LINE not in hook("keep going", sid, UAPLY_NOW=at(2))[1], "late line shows once per chat")
    check(hook_prompt.LATE_LINE not in hook("keep going", sess("day"))[1], "14:00 → no late line")

    # (e) events log has the prompt events but never the prompt text
    secret_words = "zebra-quartz-71 sk-ant-fake"
    hook(f"please look at {secret_words}", sess("text"))
    raw = EVENTS.read_text(encoding="utf-8") if EVENTS.exists() else ""
    evs = [json.loads(x) for x in raw.splitlines() if x.strip()]
    check(any(e.get("kind") == "prompt" and e.get("blocked") for e in evs), "blocked prompt logged")
    check(any(e.get("kind") == "prompt" and "opus" in str(e.get("nudge")) for e in evs), "Opus nudge logged")
    check("zebra-quartz" not in raw and "sk-ant" not in raw, "events log never holds prompt text")

    # (f) log_event drops secret-looking fields and caps long values
    os.environ["UAPLY_EVENTS_FILE"] = str(EVENTS)
    from _common import log_event  # noqa: E402
    log_event("probe", token="abc-secret-1", prompt="hello words", api_key="k-123", card="189", note="x" * 300)
    last = json.loads(EVENTS.read_text(encoding="utf-8").splitlines()[-1])
    check(last.get("kind") == "probe" and last.get("card") == "189", "log_event keeps plain fields")
    check(not {"token", "prompt", "api_key"} & set(last), "log_event drops token/prompt/key fields")
    check(len(str(last.get("note"))) <= 80, "log_event caps long values")
    rot = TMP / "rot.jsonl"
    rot.write_text("x" * (5 * 1024 * 1024 + 10), encoding="utf-8")
    os.environ["UAPLY_EVENTS_FILE"] = str(rot)
    log_event("probe", card="1")
    os.environ["UAPLY_EVENTS_FILE"] = str(EVENTS)
    check((TMP / "rot.jsonl.1").exists() and rot.stat().st_size < 1000, "events log rotates past 5 MB")

    # (g) doctor --weekly: seeded events + fake ccusage → all four sections and the Monday lines
    monday = "2026-11-02"
    mon_t = time.mktime((2026, 11, 2, 9, 0, 0, 0, 0, -1))
    seed = [{"ts": mon_t - 3 * 86400, "kind": "ship", "card": "189", "stage": "start"},
            {"ts": mon_t - 2 * 86400, "kind": "ship", "card": "189", "stage": "sandbox", "pr": 107},
            {"ts": mon_t - 86400, "kind": "lock", "target": "sandbox", "action": "timeout"},
            {"ts": mon_t - 86400, "kind": "prompt", "blocked": True, "idle_min": 70},
            {"ts": mon_t - 86400 + 5, "kind": "prompt", "blocked": False, "idle_min": 70},
            {"ts": mon_t - 9 * 86400, "kind": "ship", "card": "180", "stage": "sandbox", "pr": 99}]
    wk_events = TMP / "weekly.jsonl"
    wk_events.write_text("".join(json.dumps(e) + "\n" for e in seed), encoding="utf-8")
    cc = TMP / "ccusage.json"
    cc.write_text(json.dumps({"daily": [
        {"date": "2026-10-30", "totalCost": 12.5, "modelBreakdowns": [{"modelName": "claude-opus-5-5", "cost": 10.0},
                                                                     {"modelName": "claude-sonnet-5-5", "cost": 2.5}]},
        {"date": "2026-10-22", "totalCost": 8.0, "modelBreakdowns": [{"modelName": "claude-sonnet-5-5", "cost": 8.0}]},
    ]}), encoding="utf-8")
    code, out = doctor("--weekly", "--today", monday, UAPLY_EVENTS_FILE=wk_events, UAPLY_CCUSAGE_JSON=cc)
    check(code == 0, "doctor --weekly exits 0")
    check(all(h in out for h in ("EFFICIENCY", "PRODUCTIVITY", "EFFECTIVENESS", "RELIABILITY")), "all four sections")
    check("$/day" in out and "(last" in out, "cost line with last-week comparison")
    check("Monday review" in out and "30-day review" in out, "Monday + first-Monday lines on 2026-11-02")
    check(re.search(r"PRs merged to sandbox\s+1\s+\(last 1\)", out), "merged = 1 this week, 1 last week")
    check(re.search(r"lock timeouts\s+1\s+\(last 0\)", out), "lock timeouts = 1 this week, 0 last week")
    check(re.search(r"\$/day\s+\$1\.79\s+\(last \$1\.14\)", out), "$/day 1.79 vs 1.14 from fake ccusage")
    check(re.search(r"cold resumes\s+1\s", out), "a blocked idle prompt + its go! count as ONE cold restart")
    # ccusage ≥20 names the day "period" (not "date"); undated rows must not hide the "ccusage n/a" notice
    cc20 = TMP / "ccusage20.json"
    cc20.write_text(json.dumps({"daily": [
        {"period": "2026-10-30", "totalCost": 12.5, "modelBreakdowns": [{"modelName": "claude-opus-5-5", "cost": 10.0},
                                                                       {"modelName": "claude-sonnet-5-5", "cost": 2.5}]},
        {"period": "2026-10-22", "totalCost": 8.0, "modelBreakdowns": [{"modelName": "claude-sonnet-5-5", "cost": 8.0}]},
    ], "totals": {}}), encoding="utf-8")
    code, out = doctor("--weekly", "--today", monday, UAPLY_EVENTS_FILE=wk_events, UAPLY_CCUSAGE_JSON=cc20)
    check(re.search(r"\$/day\s+\$1\.79\s+\(last \$1\.14\)", out), "ccusage 20 'period' key read: $/day 1.79 vs 1.14")
    check(re.search(r"Opus share\s+80%", out), "ccusage 20: Opus share 80% from modelBreakdowns")
    cc_bad = TMP / "ccusage-undated.json"
    cc_bad.write_text(json.dumps({"daily": [{"day": "2026-10-30", "totalCost": 5.0}]}), encoding="utf-8")
    code, out = doctor("--weekly", "--today", monday, UAPLY_EVENTS_FILE=wk_events, UAPLY_CCUSAGE_JSON=cc_bad)
    check("ccusage n/a" in out, "rows with no date/period → the 'ccusage n/a' notice shows (not silent n/a)")
    code, out = doctor("--weekly", "--today", "2026-11-04", UAPLY_EVENTS_FILE=wk_events, UAPLY_CCUSAGE_JSON=cc)
    check("Monday review" not in out, "no Monday line on a Wednesday")

    # (h) protected rules: intact on the real repo; loosening one fails. The expected list lives HERE, not only in
    # doctor.py, so a proposal that deletes a rule or raises a limit in doctor.py fails this test too.
    expected = {("shared/uaply-assist.js", "the person ticks it"), ("docs/apply-by-email.md", "never submits automatically"),
                ("CLAUDE.md", "**UI GATE:"), ("CLAUDE.md", "REAL APP ONLY"), ("CLAUDE.md", "until Mohammed gives an explicit"),
                ("CLAUDE.md", "Live: Saif only"), ("tools/lite/queue.py", "live promotion is Saif-only"),
                ("tools/lite/handoff_wip.py", "an AI provider API key"), ("CLAUDE.md", "never commit secrets"),
                ("CLAUDE.md", "`queue.py take sandbox`"), ("tools/lite/queue.py", "def take("),
                ("docs/assisted-apply.md", "the person answers"), ("shared/uaply-assist.js", "humanCheck"),
                ("docs/handbook/07-conventions.md", "Never invent an answer")}
    limits = {"BIG_K": 150, "IDLE_MIN": 60, "WARN_K": 100}
    doc = __import__("doctor")
    have = {(rel, r) for _, rel, r in doc.PROTECTED_RULES if isinstance(r, str)}
    check(expected <= have, "doctor.py still lists every protected text rule")
    have_lim = {r[0]: r[1] for _, rel, r in doc.PROTECTED_RULES if isinstance(r, tuple)}
    check(all(k in have_lim and have_lim[k] <= v for k, v in limits.items()), "doctor.py limits are not raised")
    code, out = doctor("--protected")
    check(code == 0 and "FAIL" not in out, "protected rules intact on this repo")
    files = sorted({rel for _, rel, _ in __import__("doctor").PROTECTED_RULES})
    copy = TMP / "repo"
    for rel in files:
        (copy / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, copy / rel)
    check(doctor("--protected", UAPLY_ROOT=copy)[0] == 0, "copied rule files pass")
    hp = copy / "tools/lite/hook_prompt.py"
    hp.write_text(hp.read_text(encoding="utf-8").replace("BIG_K, WARN_K, IDLE_MIN = 150, 100, 60",
                                                         "BIG_K, WARN_K, IDLE_MIN = 200, 100, 60"), encoding="utf-8")
    code, out = doctor("--protected", UAPLY_ROOT=copy)
    check(code == 1 and "FAIL" in out, "raising BIG_K to 200 fails --protected")
    shutil.copy(ROOT / "tools/lite/hook_prompt.py", hp)
    hp.write_text(hp.read_text(encoding="utf-8").replace("BIG_K, WARN_K, IDLE_MIN = 150, 100, 60",
                                                         "BIG_K, WARN_K, IDLE_MIN = 120, 80, 45"), encoding="utf-8")
    check(doctor("--protected", UAPLY_ROOT=copy)[0] == 0, "making thresholds stricter still passes")
    hp.write_text(hp.read_text(encoding="utf-8") + "\nBIG_K = 500\n", encoding="utf-8")
    check(doctor("--protected", UAPLY_ROOT=copy)[0] == 1, "a second, looser BIG_K assignment fails --protected")
    shutil.copy(ROOT / "tools/lite/hook_prompt.py", hp)
    md = copy / "CLAUDE.md"
    md.write_text(md.read_text(encoding="utf-8").replace("REAL APP ONLY", "MOCKUPS OK"), encoding="utf-8")
    code, out = doctor("--protected", UAPLY_ROOT=copy)
    check(code == 1 and "FAIL" in out, "removing 'REAL APP ONLY' fails --protected")
finally:
    for sid in SIDS:
        for f in STATE_DIR.glob(f"sess-{sid}*"):
            f.unlink(missing_ok=True)
    shutil.rmtree(TMP, ignore_errors=True)

print("ALL PASSED" if FAILS == 0 else f"{FAILS} FAILED")
sys.exit(1 if FAILS else 0)
