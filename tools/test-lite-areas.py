"""Area cards stay put + /handoff tidies the bot ledger, offline:   python tools/test-lite-areas.py
trello.py update never moves a card that lives in '📍 Areas' (and never moves a work card into it), while work cards
still move; jobs.py clear-mine drops only this chat's finished bots and keeps running ones and other chats'."""
import contextlib
import io
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "lite"))
import jobs  # noqa: E402
import trello  # noqa: E402

fails = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


# ---- fake Trello board: no network ------------------------------------------------------------------
LISTS = [{"id": "L-areas", "name": "📍 Areas"}, {"id": "L-next", "name": "Next / queued — retain progress"},
         {"id": "L-wait", "name": "Waiting on someone"}]
CARDS = {"191": {"id": "C191", "name": "191 Job Feeds", "idList": "L-areas", "shortUrl": "u191", "closed": False},
         "34": {"id": "C34", "name": "Feed retry fix", "idList": "L-next", "shortUrl": "u34", "closed": False}}
moves, comments = [], []


def fake_trello(method, path, params=None, timeout=15):
    if path.endswith("/lists"):
        return LISTS
    if "/cards/" in path and method == "GET" and path.startswith("/boards/"):
        return dict(CARDS[path.rsplit("/", 1)[1]])
    if method == "PUT":
        moves.append((path.rsplit("/", 1)[1], params["idList"]))
        return {}
    if method == "POST" and path.endswith("/actions/comments"):
        comments.append(path)
        return {"id": "x"}
    raise AssertionError(f"unexpected call {method} {path}")


trello.trello = fake_trello
trello.board = lambda: "TEST"


def run_update(*a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        trello.update(*a, **kw)
    return out.getvalue()


out = run_update("191", "Next / queued — retain progress", "progress")
check(not moves and "not moved" in out, "area card + --list: NOT moved")
check(len(comments) == 1, "area card: the comment still posts")
out = run_update("191", "Waiting on someone")
check(not moves, "area card → Waiting: NOT moved")
out = run_update("34", "📍 Areas")
check(not moves and "not moved" in out, "work card → 📍 Areas: NOT moved")
out = run_update("34", "Waiting on someone", "PR #9")
check(moves == [("C34", "L-wait")], f"work card → Waiting: moved ({moves})")

# a second 'Areas — old' list earlier on the board can't hide the real one
LISTS.insert(0, {"id": "L-old", "name": "Areas — old"})
moves.clear()
run_update("191", "Waiting on someone")
check(not moves, "area card with an 'Areas — old' list present: NOT moved")
LISTS.pop(0)

# gh-event moves through update() too, so a PR on an area-numbered branch can't drag the area card
moves.clear()
os.environ["GITHUB_EVENT_PATH"] = os.path.join(tempfile.mkdtemp(prefix="uaply-areas-"), "ev.json")
Path(os.environ["GITHUB_EVENT_PATH"]).write_text(
    '{"action":"opened","pull_request":{"head":{"ref":"c191-x"},"base":{"ref":"sandbox"},"html_url":"h"}}',
    encoding="utf-8")
LISTS.append({"id": "L-review", "name": "Review"})
with contextlib.redirect_stdout(io.StringIO()):
    trello.gh_event()
check(not moves, "gh-event on c191-* branch: area card NOT moved")

# the skills say it in words too (the connector path doesn't go through trello.py)
for skill in ("handoff", "pickup"):
    text = Path(ROOT, ".claude", "skills", skill, "SKILL.md").read_text(encoding="utf-8")
    check("NEVER move" in text and "📍 Areas" in text, f"{skill} skill: area cards are never moved")
check("jobs.py clear-mine" in Path(ROOT, ".claude", "skills", "handoff", "SKILL.md").read_text(encoding="utf-8"),
      "handoff skill: runs jobs.py clear-mine")

# ---- bot ledger: clear-mine ---------------------------------------------------------------------------
tmp = Path(tempfile.mkdtemp(prefix="uaply-jobs-"))
jobs.LITE_DIR, jobs.LEDGER = tmp, tmp / "jobs.json"
now = time.time()
jobs.save({
    "a": {"type": "builder", "session": "me", "started": now, "status": "DONE", "ended": now},
    "b": {"type": "reviewer", "session": "me", "started": now, "status": "CLEARED", "ended": now},
    "c": {"type": "runner", "session": "me", "started": now, "status": "RUNNING"},
    "d": {"type": "builder", "session": "other", "started": now, "status": "DONE", "ended": now},
    "e": {"type": "builder", "session": "other", "started": now, "status": "RUNNING"},
})


def run_jobs(*a, env=None):
    old = {k: os.environ.get(k) for k in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")}
    for k in old:
        os.environ.pop(k, None)
    os.environ.update(env or {})
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            jobs._locked(a[0], list(a))
    except SystemExit:
        pass
    finally:
        for k, v in old.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
    return out.getvalue()


out = run_jobs("clear-mine", env={"CLAUDE_CODE_SESSION_ID": "me"})
left = jobs.load()
check("a" not in left and "b" not in left, "clear-mine: this chat's finished bots removed")
check(left.get("c", {}).get("status") == "RUNNING" and "still RUNNING" in out, "clear-mine: this chat's running bot kept + named")
check("d" in left and "e" in left, "clear-mine: other chats' bots untouched")
out = run_jobs("clear-mine")
check("nothing cleared" in out and len(jobs.load()) == 3, "clear-mine without a session id: clears nothing")
out = run_jobs("clear-mine", "other")
check(set(jobs.load()) == {"c", "e"}, "clear-mine <id>: explicit session works")

if fails:
    print(f"\n{len(fails)} FAILED")
    sys.exit(1)
print("\nALL AREA/LEDGER CHECKS PASSED")
