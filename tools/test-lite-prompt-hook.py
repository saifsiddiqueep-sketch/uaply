"""Auto-brief nudge in the prompt hook, offline:   python tools/test-lite-prompt-hook.py
A long (80+ words) or multi-ask (3+) prompt gets one '[lite] Long/dictated prompt' line telling Claude to apply /brief;
short prompts, '/' commands and 'go!' get nothing; the hook never blocks; the big-chat blocker is unchanged."""
import json
import os
import subprocess
import sys
import tempfile
import uuid

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "lite"))
import hook_prompt  # noqa: E402
from _common import STATE_DIR, write_sess  # noqa: E402

fails = []
LONG = " ".join(["word"] * 85)


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


def hook(prompt, sid):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "lite", "hook_prompt.py")],
                       input=json.dumps({"session_id": sid, "prompt": prompt}), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=30,
                       env=dict(os.environ, UAPLY_EVENTS_FILE=os.path.join(tempfile.gettempdir(), "uaply-test-events.jsonl")))
    return r.returncode, r.stdout, r.stderr


small, big = f"test-brief-{uuid.uuid4().hex[:8]}", f"test-brief-{uuid.uuid4().hex[:8]}"
try:
    code, out, _ = hook(LONG, small)
    check(code == 0 and hook_prompt.BRIEF_LINE in out, "an 85-word prompt prints the /brief line and exits 0")
    code, out, _ = hook("Fix the header. Also update the footer, and then email Saif.", small)
    check(code == 0 and hook_prompt.BRIEF_LINE in out, "3 asks joined by 'also' / 'and then' print the /brief line")
    code, out, _ = hook("1. fix the header\n2. fix the footer\n3. ship it", small)
    check(code == 0 and hook_prompt.BRIEF_LINE in out, "3 numbered lines print the /brief line")
    code, out, _ = hook("Another thing: rename the card, also move it", small)
    check(code == 0 and hook_prompt.BRIEF_LINE in out, "'another thing' counts as an ask")
    for p, what in (("fix the header please", "a short prompt"), ("/ship 42 " + LONG, "a '/' command"),
                    ("go! " + LONG, "a 'go!' prompt"), ("Also fix the footer", "a short prompt with one 'also'"),
                    ("1. fix the header\n2. fix the footer", "2 numbered lines")):
        code, out, _ = hook(p, small)
        check(code == 0 and "[lite] running" in out and "Long/dictated" not in out, f"{what} prints no /brief line")
    check(not hook_prompt.needs_brief("Calsonic and thenar"), "'also'/'and then' inside other words don't count")

    write_sess(big, {"ctx_k": 160})
    code, out, err = hook(LONG, big)
    check(code == 2 and "go!" in err and "Long/dictated" not in out, "the big-chat blocker still stops a 160k chat")
    code, out, _ = hook("go! " + LONG, big)
    check(code == 0 and "Long/dictated" not in out, "'go!' still gets through the blocker, with no /brief line")

    # go! always passes: alone, with leading spaces, any case, full-width, and logs override=true (big + idle chats)
    events = os.path.join(tempfile.gettempdir(), "uaply-test-events.jsonl")
    idle_big, idle_small = f"test-go-{uuid.uuid4().hex[:8]}", f"test-go-{uuid.uuid4().hex[:8]}"
    extra = [idle_big, idle_small]
    for p in ("go!", "  go! text", "GO! text", "﻿go! text", "ｇｏ！ text"):
        for sid, state, what in ((big, {"ctx_k": 160}, "160k chat"),
                                 (idle_big, {"ctx_k": 40, "last_prompt_at": hook_prompt.now() - 90 * 60}, "40k chat idle 90 min")):
            write_sess(sid, state)
            code, out, err = hook(p, sid)
            with open(events, encoding="utf-8") as f:
                last = json.loads(f.read().strip().splitlines()[-1])
            check(code == 0 and "[lite] running" in out and last.get("override") is True and not last.get("blocked"),
                  f"{p!r} passes a {what} and logs override=true")
    code, out, _ = hook("go!", small)
    with open(events, encoding="utf-8") as f:
        check(code == 0 and json.loads(f.read().strip().splitlines()[-1]).get("override") is True,
              "'go!' on a fresh small chat passes and logs override=true")

    # idle block only at >=20k; under 20k it prints one note line and sends
    write_sess(idle_big, {"ctx_k": 20, "last_prompt_at": hook_prompt.now() - 90 * 60})
    code, out, err = hook("what changed", idle_big)
    check(code == 2 and "away 90 min" in err, "idle 90 min at 20k → blocked")
    write_sess(idle_small, {"ctx_k": 0, "last_prompt_at": hook_prompt.now() - 128 * 60})
    code, out, err = hook("what changed", idle_small)
    notes = [l for l in out.splitlines() if l.startswith("[lite] Idle")]
    check(code == 0 and len(notes) == 1 and "only 0k" in notes[0] and not err, "idle 128 min at 0k → sent with one note line")
    write_sess(idle_small, {"ctx_k": 19, "last_prompt_at": hook_prompt.now() - 128 * 60})
    code, out, _ = hook("what changed", idle_small)
    check(code == 0 and "[lite] Idle" in out, "idle at 19k → sent with the note")
    code, out, _ = hook("what changed", idle_small)
    check(code == 0 and "[lite] Idle" not in out, "the next prompt (no longer idle) gets no note")
    extra.append(f"test-go-{uuid.uuid4().hex[:8]}")
    code, out, err = hook("", extra[-1])
    check(code == 0, "an empty prompt payload never blocks")
finally:
    for sid in (small, big, *globals().get("extra", [])):
        f = STATE_DIR / f"sess-{sid}.json"
        if f.exists():
            f.unlink()

print(f"{len(fails) == 0 and 'ALL PASSED' or f'{len(fails)} FAILED'}")
sys.exit(1 if fails else 0)
