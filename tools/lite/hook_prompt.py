#!/usr/bin/env python3
"""UserPromptSubmit hook — runs BEFORE your message reaches Claude (costs 0 tokens when it blocks).

BIG-CHAT BLOCKER: if this chat is ≥150k tokens, or it was idle >60 min, the message is stopped before Claude
re-reads the whole chat. Choose: /handoff, /clear, /pickup <area> (cheapest restart) or start the message with
go!  to send it anyway.   [fix 4: was "!go", but "!" means shell mode in Claude Code]
Otherwise adds one [lite] line (model · effort · context) for the MODE check, plus at most one line each for:
≥100k context (finish, /handoff, /clear), Opus on a routine prompt (/model sonnet), and a session after 1 AM.
Every prompt appends one event (numbers only, never prompt text) to ~/.uaply/state/events.jsonl.

AUTO-BRIEF: a long or dictated prompt (80+ words, or 3+ asks) also gets one [lite] line telling Claude to apply
/brief first. Never for prompts starting with "/" or "go!", and it never blocks."""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _common import log_event, read_stdin_json, read_sess, read_state, write_sess  # noqa: E402

BIG_K, WARN_K, IDLE_MIN = 150, 100, 60
LATE_HOURS = range(1, 5)                 # 1:00–4:59 local time
ESCAPE = "go!"
BRIEF_WORDS, BRIEF_ASKS = 80, 3
BRIEF_LINE = ("[lite] Long/dictated prompt — apply the /brief skill first: rewrite it the top-0.1% way, show QUEUE "
              "(or 'BRIEF ✓' + one-line goal if it's a single ask), then execute.")
# one ask per numbered/bulleted line, plus each "also" / "and then" / "another thing" joining asks in running speech
ASK_LINE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+", re.M)
ASK_JOIN = re.compile(r"\b(?:also|and then|another thing)\b", re.I)


WARN_LINE = "[lite] This chat is {ctx}k — finish the current step, then /handoff and /clear (blocked at 150k)."
OPUS_LINE = "[lite] Routine prompt on Opus — /model sonnet saves ~60% here."
LATE_LINE = "[lite] Late session — consider /handoff now so tomorrow's chat starts cheap."
# routine = Trello / renames / copy / quick questions; never nudge on anything sensitive or hard
ROUTINE = re.compile(r"\b(trello|card|rename|typo|copy|wording|reword|label|move|status|quick q|what is|where is|list)\b", re.I)
SENSITIVE = re.compile(r"(consent|secur|auth|login|password|token|secret|payment|billing|stripe|money|refund|legal|"
                       r"privacy|gdpr|terms|bug|crash|error|fail|broken|migrat|live|prod)", re.I)
PICKUP = re.compile(r"^/pickup\s+([A-Za-z&-]+)", re.I)


def now():
    return float(os.environ.get("UAPLY_NOW") or time.time())     # tests pin the clock


def opus_nudge(model, prompt):
    """True when Opus is running a short routine prompt with nothing sensitive in it."""
    return ("opus" in str(model).lower() and len(prompt.split()) <= 40 and bool(ROUTINE.search(prompt))
            and not SENSITIVE.search(prompt) and not prompt.startswith("/"))


def needs_brief(prompt):
    """True for a long or multi-ask prompt that /brief should rewrite first."""
    if not prompt or prompt.startswith("/") or prompt.lower().startswith(ESCAPE):
        return False
    if len(prompt.split()) >= BRIEF_WORDS:
        return True
    lines = len(ASK_LINE.findall(prompt))
    asks = max(lines, 1) + len(ASK_JOIN.findall(prompt))
    return asks >= BRIEF_ASKS


def main():
    d = read_stdin_json()
    sid = d.get("session_id")
    prompt = (d.get("prompt") or "").strip()
    s, g = read_sess(sid), read_state()
    t = now()
    ctx = int(s.get("ctx_k") or 0)
    last = s.get("last_prompt_at")
    idle = int((t - last) / 60) if last else 0
    m = PICKUP.match(prompt)
    area = m.group(1).lower() if m else s.get("area")
    model = s.get("model") or g.get("model", "unknown (status line not running)")
    ev = dict(area=area, model=model.split(" ")[0], ctx_k=ctx, idle_min=idle, blocked=False, override=False, nudge="")

    forced = prompt.lower().startswith(ESCAPE)
    exempt = forced or prompt.startswith("/")
    ev["override"] = forced and (ctx >= BIG_K or idle > IDLE_MIN)
    if not exempt and (ctx >= BIG_K or idle > IDLE_MIN):
        why = f"this chat is {ctx}k tokens" if ctx >= BIG_K else f"you were away {idle} min (the cache is cold) and this chat is {ctx}k"
        log_event("prompt", **dict(ev, blocked=True))
        print(f"⛔ Workflow Lite stopped this message to save tokens: {why}, so sending it would re-read the whole chat.\n"
              f"   • /handoff  → save what only this chat knows, then /clear\n"
              f"   • /clear    → free fresh start (your branch, Trello and handoff files are still there)\n"
              f"   • /pickup <area> → cheapest restart: a fresh chat from the area's last handoff\n"
              f"   • {ESCAPE} <your message> → send it anyway", file=sys.stderr)
        sys.exit(2)

    effort = d.get("effort")
    effort = effort.get("level") if isinstance(effort, dict) else effort
    effort = effort or s.get("effort") or g.get("effort", "unknown")
    upd = {"last_prompt_at": t, "area": area}
    lines = [f"[lite] running {model} · effort {effort} · context {ctx}k"]
    if needs_brief(prompt):
        lines.append(BRIEF_LINE)
    if ctx >= WARN_K:
        lines.append(WARN_LINE.format(ctx=ctx))
        ev["nudge"] += "warn100 "
    if opus_nudge(model, prompt) and not s.get("opus_nudged"):
        lines.append(OPUS_LINE)
        upd["opus_nudged"] = True
        ev["nudge"] += "opus "
    if time.localtime(t).tm_hour in LATE_HOURS and not s.get("late_nudged"):
        lines.append(LATE_LINE)
        upd["late_nudged"] = True
        ev["nudge"] += "late "
    write_sess(sid, upd)
    ev["nudge"] = ev["nudge"].strip()
    log_event("prompt", **ev)
    print("\n".join(lines))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        pass   # never block a prompt because of a hook bug
