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



def fresh(name, branch):
    """A disposable bare remote + clone on `branch` with one LF file committed; returns (remote, clone)."""
    base = tempfile.mkdtemp(prefix=f"uaply-{name}-")
    rem, wd = os.path.join(base, "remote.git"), os.path.join(base, "work")
    sh(base, "init", "-q", "--bare", "-b", "sandbox", rem)
    sh(base, "clone", "-q", rem, wd)
    for k, v in (("user.name", "Test"), ("user.email", "test@example.com"), ("commit.gpgsign", "false")):
        sh(wd, "config", k, v)
    write(os.path.join(wd, "a.txt"), "one\n")
    sh(wd, "add", "-A"); sh(wd, "commit", "-q", "-m", "base"); sh(wd, "push", "-q", "-u", "origin", "sandbox")
    sh(wd, "checkout", "-q", "-b", branch)
    return rem, wd


def write_lf(path, text):
    open(path, "wb").write(text.encode())  # raw LF bytes (text mode on Windows would write CRLF and hide the warning)


def tip(rem, branch):
    r = subprocess.run(["git", "log", "-1", "--format=%s", branch], cwd=rem, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


# c220: Git's "LF will be replaced by CRLF" warnings (stderr) are not conflicts — the WIP commits and pushes
rem, wd = fresh("crlf", "c1-crlf")
sh(wd, "config", "core.autocrlf", "true")
write_lf(os.path.join(wd, "a.txt"), "changed\n"); write_lf(os.path.join(wd, "new.txt"), "lf only\n")
warn = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=wd, capture_output=True, text=True)
check("CRLF" in warn.stderr and not warn.stdout.strip(), "crlf: precondition — git warns on stderr, no unmerged files")
w, u = handoff_wip.one(wd, "Feeds")
check(u is None and w and "WIP: Feeds handoff" in w, f"crlf: warnings ignored, committed + pushed ({u or w})")
check(tip(rem, "c1-crlf") == "WIP: Feeds handoff", "crlf: reached the remote")
check(not sh(wd, "status", "--porcelain"), "crlf: nothing left uncommitted")

# a real conflict with CRLF warnings around it → still blocked, merge state kept, remote untouched
sh(wd, "checkout", "-q", "-b", "side"); write(os.path.join(wd, "a.txt"), "side\n"); sh(wd, "commit", "-q", "-am", "side")
sh(wd, "checkout", "-q", "c1-crlf"); write(os.path.join(wd, "a.txt"), "mine\n"); sh(wd, "commit", "-q", "-am", "mine")
subprocess.run(["git", "merge", "-q", "side"], cwd=wd, capture_output=True)
w, u = handoff_wip.one(wd, "Feeds")
check(w is None and u and "NOT pushed" in u and "in progress" in u, "crlf conflict: blocked")
check(tip(rem, "c1-crlf") == "WIP: Feeds handoff", "crlf conflict: remote untouched")

# unmerged index with MERGE_HEAD gone (a deleted/broken merge state) → still blocked as a conflict
os.remove(sh(wd, "rev-parse", "--path-format=absolute", "--git-path", "MERGE_HEAD"))
check(bool(sh(wd, "ls-files", "--unmerged")), "no MERGE_HEAD: precondition — index still unmerged")
w, u = handoff_wip.one(wd, "Feeds")
check(w is None and u and "unresolved merge conflicts" in u, "no MERGE_HEAD: unmerged index still blocked")
check(tip(rem, "c1-crlf") == "WIP: Feeds handoff" and bool(sh(wd, "ls-files", "--unmerged")),
      "no MERGE_HEAD: remote untouched, conflict left for the owner")
sh(wd, "reset", "-q", "--hard", "HEAD")

# cherry-pick conflict → blocked; and again once CHERRY_PICK_HEAD is gone (unmerged index alone)
subprocess.run(["git", "cherry-pick", "side"], cwd=wd, capture_output=True)
w, u = handoff_wip.one(wd, "Feeds")
check(w is None and u and "in progress" in u, "cherry-pick conflict: blocked")
os.remove(sh(wd, "rev-parse", "--path-format=absolute", "--git-path", "CHERRY_PICK_HEAD"))
w, u = handoff_wip.one(wd, "Feeds")
check(w is None and u and "unresolved merge conflicts" in u, "cherry-pick, no CHERRY_PICK_HEAD: unmerged index blocked")
sh(wd, "reset", "-q", "--hard", "HEAD")

# rebase conflict → not pushed (rebase leaves HEAD detached), remote untouched
subprocess.run(["git", "rebase", "side"], cwd=wd, capture_output=True)
w, u = handoff_wip.one(wd, "Feeds")
check(w is None and u and "NOT" in u.upper() and tip(rem, "c1-crlf") == "WIP: Feeds handoff", f"rebase conflict: blocked ({u})")
subprocess.run(["git", "rebase", "--abort"], cwd=wd, capture_output=True)

# a rebase stopped on a named branch (rebase-merge present, HEAD not detached) → blocked as "in progress"
rb = sh(wd, "rev-parse", "--path-format=absolute", "--git-path", "rebase-merge")
os.makedirs(rb); write_lf(os.path.join(wd, "a.txt"), "mid-rebase\n")
w, u = handoff_wip.one(wd, "Feeds")
check(w is None and u and "in progress" in u and tip(rem, "c1-crlf") == "WIP: Feeds handoff", "rebase-merge on a branch: blocked")
os.rmdir(rb); sh(wd, "checkout", "-q", "--", "a.txt")

# the conflict check itself failing → raises, never read as "no conflicts"
real_git = handoff_wip.git
def failing_git(cwd, *a, **k):
    if a[:1] == ("ls-files",):
        raise RuntimeError("git ls-files --unmerged: simulated failure")
    return real_git(cwd, *a, **k)
handoff_wip.git = failing_git
write_lf(os.path.join(wd, "a.txt"), "dirty\n")
try:
    handoff_wip.one(wd, "Feeds")
    raised = ""
except RuntimeError as e:
    raised = str(e)
handoff_wip.git = real_git
check("ls-files" in raised and tip(rem, "c1-crlf") == "WIP: Feeds handoff", "ls-files failure: raises, nothing pushed")
sh(wd, "checkout", "-q", "--", "a.txt")

# a git command that fails → raises (fail closed: wip() reports it as unpushed), never treated as "no conflicts"
idx = sh(wd, "rev-parse", "--path-format=absolute", "--git-path", "index")
good = open(idx, "rb").read()
write_lf(os.path.join(wd, "a.txt"), "dirty again\n")
open(idx, "wb").write(b"not an index")
try:
    handoff_wip.one(wd, "Feeds")
    raised = ""
except RuntimeError as e:
    raised = str(e)
check(raised.startswith("git ") and tip(rem, "c1-crlf") == "WIP: Feeds handoff", f"git failure: raises, nothing pushed ({raised[:80]})")
open(idx, "wb").write(good)
warn = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=wd, capture_output=True, text=True)
check("CRLF" in warn.stderr, "run(): precondition — git warns on stderr")
try:
    handoff_wip.git(wd, "rev-parse", "--verify", "no-such-ref")
    check(False, "git(): non-zero exit raises")
except RuntimeError:
    check(True, "git(): non-zero exit raises")
check(handoff_wip.run(["git", "diff", "--name-only", "--diff-filter=U"], wd) == (0, ""),
      "run(): stdout only by default (CRLF warning not read as a file name)")

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
