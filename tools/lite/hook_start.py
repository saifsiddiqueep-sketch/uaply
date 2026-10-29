#!/usr/bin/env python3
"""SessionStart hook (new chat, /clear, resume, after compaction). Prints a few LIVE facts so a fresh chat
knows where it is: repo, branch, commit, uncommitted files, new sandbox commits, merge locks, unfinished bots.

v1.6 Core: fetch capped at 5s and skipped offline [fix 7]; a resumed chat keeps its idle clock, so the
big-chat blocker still catches an old chat reopened the next day [fix 5]."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _common import read_stdin_json, founder, git, read_sess, write_sess, write_state  # noqa: E402


def safe(*a, timeout=5):
    try:
        return git(*a, check=False, timeout=timeout)
    except Exception:
        return None          # None = failed/timed out; "" = ran fine with no output


def fetch_ok():
    """True only if `git fetch origin sandbox` actually succeeded within 5 seconds."""
    import subprocess
    try:
        return subprocess.run(["git", "fetch", "-q", "origin", "sandbox"], capture_output=True,
                              timeout=5).returncode == 0
    except Exception:
        return False


def main():
    d = read_stdin_json()
    sess, source = d.get("session_id"), d.get("source", "startup")

    root = safe("rev-parse", "--show-toplevel")
    if not root:
        print("[lite] Not inside a git repo — read-only until you open the UAply folder.")
    else:
        remote = (safe("remote", "get-url", "origin") or "").rsplit("/", 2)[-2:]
        branch = safe("branch", "--show-current") or "DETACHED"
        sha = safe("rev-parse", "--short", "HEAD") or "?"
        dirty = len([x for x in (safe("status", "--porcelain") or "").splitlines() if x.strip()])
        warn = ""
        if "uaply" not in "/".join(remote).lower():
            warn = " ⚠ origin is not the UAply repo — read-only"
        elif branch in ("dev", "main"):
            warn = " ⚠ on LIVE branch — read-only; branch off sandbox"
        print(f"[lite] {founder()} · {os.path.basename(root)} · {branch}@{sha} · {dirty} uncommitted{warn}")

        online = fetch_ok()   # fix 7
        if online:
            behind = safe("rev-list", "--count", "HEAD..origin/sandbox") or ""
            if behind.isdigit() and int(behind) > 0:
                print(f"[lite] sandbox has {behind} commit(s) this branch doesn't have — offer `git merge origin/sandbox` "
                      f"before building.")
            out = safe("ls-remote", "origin", "refs/heads/lock/*", timeout=5) or ""
            held = [l.split("refs/heads/lock/")[-1] for l in out.splitlines() if "refs/heads/lock/" in l]
            locks = "locks: " + (", ".join(f"{h} HELD" for h in held) if held else "all free")
            write_state({"locks": locks, "locks_at": time.time()})
            if held:
                print(f"[lite] {locks} (python tools/lite/queue.py status for who)")
        else:
            print("[lite] offline or slow network — skipped the sandbox and lock check.")

    try:
        from jobs import running
        orphans = running(exclude_session=sess)
        if orphans:
            names = ", ".join(f"{v.get('type')} ({int((time.time() - v['started']) / 60)} min)" for _, v in orphans[:5])
            print(f"[lite] ⚠ {len(orphans)} bot(s) never finished: {names}. Tell the user first; offer resume / redo / drop; "
                  f"then `python tools/lite/jobs.py clear <id>`.")
    except Exception:
        pass

    # fix 5: only a brand-new or cleared chat starts a fresh idle clock; resume keeps the old one
    prev = read_sess(sess)
    upd = {"started": prev.get("started", time.time())}
    if source in ("startup", "clear") or not prev.get("last_prompt_at"):
        upd["last_prompt_at"] = time.time()
    if source == "clear":
        upd["ctx_k"] = 0
    write_sess(sess, upd)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:      # a start-up hook must never break Claude Code
        print(f"[lite] start check skipped ({type(e).__name__}).")
