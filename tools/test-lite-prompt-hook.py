"""Auto-brief nudge in the prompt hook, offline:   python tools/test-lite-prompt-hook.py
A long (80+ words) or multi-ask (3+) prompt gets one '[lite] Long/dictated prompt' line telling Claude to apply /brief;
short prompts, '/' commands and 'go!' get nothing; the hook never blocks; the big-chat blocker is unchanged."""
import json
import os
import subprocess
import sys
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
                       text=True, encoding="utf-8", errors="replace", timeout=30)
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
finally:
    for sid in (small, big):
        f = STATE_DIR / f"sess-{sid}.json"
        if f.exists():
            f.unlink()

print(f"{len(fails) == 0 and 'ALL PASSED' or f'{len(fails)} FAILED'}")
sys.exit(1 if fails else 0)
