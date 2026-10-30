"""Handoff safety net, offline:   python tools/test-lite-handoff.py
trello.py wip commits + pushes uncommitted work on the worktree's own branch, never on sandbox/dev/main, and refuses
to push keys, .env files or user data; trello.py decisions carries forward every OPEN DECISION not marked resolved."""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "lite"))
import handoff_wip  # noqa: E402
import trello  # noqa: E402

fails = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


def sh(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)


tmp = tempfile.mkdtemp(prefix="uaply-handoff-")
remote, work = os.path.join(tmp, "remote.git"), os.path.join(tmp, "work")
sh(tmp, "init", "-q", "--bare", "-b", "sandbox", remote)
sh(tmp, "clone", "-q", remote, work)
for k, v in (("user.name", "Test"), ("user.email", "test@example.com"), ("commit.gpgsign", "false")):
    sh(work, "config", k, v)
write(os.path.join(work, "a.txt"), "one\n")
sh(work, "add", "-A"); sh(work, "commit", "-q", "-m", "base"); sh(work, "push", "-q", "-u", "origin", "sandbox")


def remote_has(branch):
    return subprocess.run(["git", "rev-parse", "--verify", "-q", f"refs/heads/{branch}"], cwd=remote, capture_output=True).returncode == 0


# on sandbox: dirty work is reported, never committed or pushed
write(os.path.join(work, "a.txt"), "two\n")
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and "protected branch 'sandbox'" in u, "sandbox: not committed, reported as unpushed")
check(sh(work, "log", "-1", "--format=%s") == "base", "sandbox: no WIP commit made")

# own branch, dirty → WIP commit + push
sh(work, "checkout", "-q", "-b", "c34-feed-fix")
w, u = handoff_wip.one(work, "Feeds")
check(u is None and w and w.startswith("c34-feed-fix → ") and "WIP: Feeds handoff" in w, f"own branch: committed + pushed ({w})")
check(remote_has("c34-feed-fix"), "own branch: reached the remote")
check(not sh(work, "status", "--porcelain"), "own branch: nothing left uncommitted")

# clean and pushed → listed, nothing unpushed
w, u = handoff_wip.one(work, "Feeds")
check(u is None and w and "WIP: Feeds handoff" in w, "clean: listed as a WIP branch, nothing unpushed")

# a .env file → blocked, nothing committed
write(os.path.join(work, ".env"), "X=1\n")
sh(work, "add", "-f", ".env")
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and ".env" in u and "NOT pushed" in u, ".env: blocked and named in the note")
sh(work, "rm", "-q", "--cached", ".env"); os.remove(os.path.join(work, ".env"))

# a live key → blocked
write(os.path.join(work, "cfg.py"), "STRIPE = 'sk_live_" + "a1B2c3D4e5F6g7H8" + "'\n")
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and "live Stripe key" in u, "live key: blocked")
os.remove(os.path.join(work, "cfg.py"))

# user data (many real-looking addresses) → blocked
write(os.path.join(work, "users.csv"), "".join(f"p{i}@gmail.com\n" for i in range(8)))
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and "email addresses" in u, "user data: blocked")
os.remove(os.path.join(work, "users.csv"))

# a Trello token, a KEY=value secret → blocked
write(os.path.join(work, "t.txt"), "tok ATTA" + "a1" * 32 + "\n")
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and "Trello token" in u, "Trello token: blocked")
os.remove(os.path.join(work, "t.txt"))
write(os.path.join(work, "s.sh"), "export TRELLO_TOKEN=\"" + "b2" * 12 + "\"\n")
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and "KEY=value" in u, "KEY=value secret: blocked")
os.remove(os.path.join(work, "s.sh"))

# an unknown binary or an oversized file → blocked; an image is fine
write(os.path.join(work, "blob.bin"), "a\0b")
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and "binary file" in u, "unknown binary: blocked")
os.remove(os.path.join(work, "blob.bin"))
write(os.path.join(work, "big.txt"), "x" * (handoff_wip.MAX_BYTES + 10))
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and "over 5 MB" in u, "oversized file: blocked")
os.remove(os.path.join(work, "big.txt"))
check(handoff_wip.check_text("img/logo.png", b"\x89PNG\0\0") is None, "image binary: allowed")

# a key committed then deleted in a later local commit → still blocked (the push would publish the old version)
write(os.path.join(work, "k.py"), "K = 'sk_live_" + "Z9y8X7w6V5u4" + "'\n")
sh(work, "add", "-A"); sh(work, "commit", "-q", "-m", "add key")
os.remove(os.path.join(work, "k.py")); sh(work, "add", "-A"); sh(work, "commit", "-q", "-m", "remove key")
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and "live Stripe key" in u, "key in history: blocked")
sh(work, "reset", "-q", "--hard", "origin/c34-feed-fix")

# a .env removed with rm --cached after being committed → still blocked
write(os.path.join(work, ".env"), "X=1\n"); sh(work, "add", "-f", ".env"); sh(work, "commit", "-q", "-m", "env")
sh(work, "rm", "-q", "--cached", ".env")
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and ".env" in u, ".env in history: blocked")
check(sh(remote, "log", "-1", "--format=%s", "c34-feed-fix") == "WIP: Feeds handoff", "blocked: remote untouched")
sh(work, "reset", "-q", "--hard", "origin/c34-feed-fix"); os.remove(os.path.join(work, ".env"))

# an AWS key committed then removed → still blocked (the audit only reads the files as they are now)
write(os.path.join(work, "aws.py"), "K = 'AKIA" + "ABCDEFGH" * 2 + "'\n")
sh(work, "add", "-A"); sh(work, "commit", "-q", "-m", "aws")
sh(work, "rm", "-q", "aws.py"); sh(work, "commit", "-q", "-m", "rm")
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and "AWS access key" in u, "AWS key in history: blocked")
sh(work, "reset", "-q", "--hard", "origin/c34-feed-fix")

# an OpenAI key, a lowercase password line → blocked
for fname, text, what in (("o.py", "k = 'sk-proj-" + "q1W2e3R4t5Y6u7I8o9P0" + "'\n", "AI provider API key"),
                          ("p.cfg", "password = \"" + "Hunter2Hunter2" + "\"\n", "KEY=value")):
    write(os.path.join(work, fname), text)
    w, u = handoff_wip.one(work, "Feeds")
    check(w is None and u and what in u, f"{what}: blocked")
    os.remove(os.path.join(work, fname))

# the same contents saved as .env AND an innocent name → the .env name is still caught
write(os.path.join(work, ".env"), "same\n"); write(os.path.join(work, "notes.txt"), "same\n")
sh(work, "add", "-f", ".env", "notes.txt")
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and ".env" in u, "duplicate contents under .env: blocked")
sh(work, "rm", "-q", "--cached", ".env", "notes.txt")
os.remove(os.path.join(work, ".env")); os.remove(os.path.join(work, "notes.txt"))

# a merge in progress → left alone, merge not lost
sh(work, "checkout", "-q", "-b", "side"); write(os.path.join(work, "a.txt"), "side\n")
sh(work, "commit", "-q", "-am", "side"); sh(work, "checkout", "-q", "c34-feed-fix")
write(os.path.join(work, "a.txt"), "mine\n"); sh(work, "commit", "-q", "-am", "mine")
subprocess.run(["git", "merge", "-q", "side"], cwd=work, capture_output=True)
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and "in progress" in u, "merge in progress: not committed or pushed")
check(subprocess.run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=work, capture_output=True).returncode == 0,
      "merge in progress: merge state kept")
sh(work, "merge", "--abort"); sh(work, "reset", "-q", "--hard", "origin/c34-feed-fix")

# committed but unpushed on a branch → pushed
write(os.path.join(work, "b.txt"), "b\n"); sh(work, "add", "-A"); sh(work, "commit", "-q", "-m", "local only")
w, u = handoff_wip.one(work, "Feeds")
check(u is None and w and "local only" in w and sh(remote, "log", "-1", "--format=%s", "c34-feed-fix") == "local only",
      "unpushed commit: pushed")

# detached HEAD with changes → reported
sh(work, "checkout", "-q", "--detach"); write(os.path.join(work, "a.txt"), "three\n")
w, u = handoff_wip.one(work, "Feeds")
check(w is None and u and "detached HEAD" in u, "detached: reported, not pushed")

# OPEN DECISIONS carried forward
note = """AREA: Job Feeds   BY: Saif   DATE: Oct 29
GOAL: more feeds
OPEN DECISIONS: Saif — keep USAJobs cap?; Mohammed — logo size ✅ resolved
- Who owns the Greenhouse key (Saif)
- [x] Drop Lever
- Rate limit 5/min — RESOLVED Oct 28
- Still unresolved: retry window
- Retry policy not resolved yet
Next release date: Nov 3 (Saif)
FILES THAT MATTER: server/feeds.py
— Saif via Claude"""
got = trello.open_decisions(note)
check(got == ["Saif — keep USAJobs cap?", "Who owns the Greenhouse key (Saif)", "Still unresolved: retry window",
                   "Retry policy not resolved yet", "Next release date: Nov 3 (Saif)"],
      f"decisions: open ones kept, resolved dropped ({got})")
check(trello.open_decisions("AREA: x\nOPEN DECISIONS: none\nNEXT: y") == [], "decisions: 'none' carries nothing")
md = """**AREA:** Feeds
**OPEN DECISIONS:** Saif - pricing
- pricing tier, to be resolved Friday
- keep the ✅ badge?
- logo size (resolved Oct 28)
**NEXT:** ship it"""
got = trello.open_decisions(md)
check(got == ["Saif - pricing", "pricing tier, to be resolved Friday", "keep the ✅ badge?"],
      f"decisions: bold headings, mid-sentence 'resolved'/✅ kept, NEXT ends the list ({got})")

print("ALL HANDOFF CHECKS PASSED" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
