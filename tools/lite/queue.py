#!/usr/bin/env python3
"""Merge queue for Mohammed + Saif. One lock per target, held on GitHub itself (atomic), so two people
can never merge into the same target at the same time.

  python tools/lite/queue.py status                 # who holds sandbox / live
  python tools/lite/queue.py take sandbox "c34 swipe fix"
  python tools/lite/queue.py wait sandbox "c34 swipe fix"   # waits in line, takes it when free (max 60 min)
  python tools/lite/queue.py release sandbox
  python tools/lite/queue.py break sandbox --yes    # clear a stale lock (>45 min) after checking with the holder

Targets: sandbox (merges into the sandbox branch) and live (sandbox -> dev promotion; Saif only).

How it works: the lock is a tiny branch `lock/<target>` on origin. Creating it uses
`git push --force-with-lease=<ref>:` (empty expected value = "must not exist"), which GitHub applies
atomically: if two people try at once, exactly one wins. Release deletes it, but only if it is still ours.
NOTE: if a branch ruleset restricts branch creation for everyone, allow the `lock/*` pattern.
"""
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, __import__("os").path.dirname(__file__))
from _common import die, founder, git, load_env, trello  # noqa: E402

TARGETS = {"sandbox", "live"}
STALE_MIN = 45
PUSH_TIMEOUT = 90  # lock pushes run the pre-push hook on some laptops; 30s timed out
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def ref(t):
    return f"refs/heads/lock/{t}"


def remote_sha(t):
    out = git("ls-remote", "origin", ref(t), timeout=20)
    return out.split()[0] if out else None


def holder_info(t, sha):
    git("fetch", "-q", "origin", f"+{ref(t)}:refs/lite/lock-{t}", check=False, timeout=30)
    msg = git("log", "-1", "--format=%B", f"refs/lite/lock-{t}", check=False)
    when = git("log", "-1", "--format=%ct", f"refs/lite/lock-{t}", check=False)
    age = int((time.time() - int(when)) / 60) if when.isdigit() else -1
    return msg.strip() or "(unknown holder)", age


def status_line(t):
    sha = remote_sha(t)
    if not sha:
        return f"{t}: FREE"
    msg, age = holder_info(t, sha)
    stale = "  ⚠ STALE — ask holder, then `break`" if age >= STALE_MIN else ""
    return f"{t}: LOCKED by {msg} ({age} min){stale}"


def mirror(text):
    """Best-effort: comment on the Trello '🚦 Merge Queue' card if TRELLO_QUEUE_CARD is set. Never blocks."""
    import os
    load_env()
    card = os.environ.get("TRELLO_QUEUE_CARD")
    if not card:
        return
    try:
        trello("POST", f"/cards/{card}/actions/comments", {"text": text})
    except Exception as e:  # Trello down must never block a merge lock
        print(f"(Trello mirror skipped: {e})")


def take(t, note):
    if t == "live" and founder().lower() not in ("saif", "unknown"):
        die("live promotion is Saif-only. Ask Saif to run: queue.py take live ...")
    who = founder()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = f"{who} | {note or 'no note'} | {stamp}"
    commit = git("commit-tree", EMPTY_TREE, "-m", msg)
    r = __import__("subprocess").run(
        ["git", "push", "-q", f"--force-with-lease={ref(t)}:", "origin", f"{commit}:{ref(t)}"],
        capture_output=True, text=True, timeout=PUSH_TIMEOUT)
    if r.returncode != 0:
        print(status_line(t))
        return False
    print(f"{t}: TAKEN by {msg}. Merge now, then run: queue.py release {t}")
    mirror(f"🔒 {t} taken — {msg}")
    return True


def release(t, force=False):
    sha = remote_sha(t)
    if not sha:
        print(f"{t}: already FREE")
        return
    msg, age = holder_info(t, sha)
    if not force and not msg.lower().startswith(founder().lower()):
        die(f"{t} is held by {msg}, not you. Use `break {t} --yes` only after checking with them.")
    git("push", "-q", f"--force-with-lease={ref(t)}:{sha}", "origin", f":{ref(t)}", timeout=PUSH_TIMEOUT)
    print(f"{t}: RELEASED (was {msg}, {age} min)")
    mirror(f"🔓 {t} released by {founder()} (was {msg})")


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd = a[0]
    if cmd == "status":
        for t in sorted(TARGETS):
            print(status_line(t))
        return
    if len(a) < 2 or a[1] not in TARGETS:
        die(f"usage: queue.py {cmd} <sandbox|live> [note]")
    t, note = a[1], " ".join(x for x in a[2:] if x != "--yes")
    if cmd == "take":
        sys.exit(0 if take(t, note) else 2)
    elif cmd == "wait":
        deadline = time.time() + 60 * 60
        print(f"In line for {t}. Checking every 20s (max 60 min)...")
        while time.time() < deadline:
            if take(t, note):
                return
            time.sleep(20)
        die(f"Gave up after 60 min. {status_line(t)}", 2)
    elif cmd == "release":
        release(t)
    elif cmd == "break":
        if "--yes" not in a:
            die("break needs --yes. Check with the holder first.")
        release(t, force=True)
    else:
        die(f"unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
