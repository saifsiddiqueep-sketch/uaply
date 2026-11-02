#!/usr/bin/env python3
"""Handoff step 0: leave no work stranded on one laptop.   (run through trello.py wip — see .claude/skills/handoff)

For each worktree the area used: commit any uncommitted changes as "WIP: <area> handoff" on that worktree's OWN
branch and push it (never sandbox/dev/main, never force, no PR). Before pushing, the existing audit
(tools/audit-files.py) and the checks below must find no keys, .env files or user data in ANY file version the push
would publish (every unpushed commit, not just the files as they are now); if they do, nothing is committed or
pushed and the reason goes in the note. Prints the two note lines:
  WIP BRANCHES: <branch → last commit>
  UNPUSHED WORK: none (checked)   |   <what's still local and why>
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

PROTECTED = {"sandbox", "dev", "main", "master", "HEAD"}
MAX_BYTES = 5_000_000

# file names that are private by rule (.gitignore lists most of them; a forced add or a new name must still be caught)
PRIVATE_PATHS = re.compile(r"(^|/)(\.env(\..*)?|uaply-config\.json.*|uaply-partners\.json.*|uaply-backup-[^/]*|"
                           r"HANDOFF[^/]*\.md|PROGRESS\.md|CLAUDE\.local\.md|lite\.env|[^/]*\.(pem|key|p12|pfx|jks|keystore|"
                           r"sqlite3?|db))$|(^|/)data/", re.I)
# binary files we can't read for keys or user data: only these kinds may go out unchecked
BINARY_OK = re.compile(r"\.(png|jpe?g|gif|webp|ico|icns|svg|woff2?|ttf|otf|eot|mp3|mp4|webm|wav|pdf|zip|jar|gz)$", re.I)
# every file version the push would publish is checked against all of these (the audit only sees the files as they are now)
SECRETS = [(re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"), "an AI provider API key"),
           (re.compile(r"\bAKIA[0-9A-Z]{16}"), "an AWS access key"),
           (re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"), "a Google client secret"),
           (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "a private key"),
           (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), "a GitHub token"),
           (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "a Slack token"),
           (re.compile(r"\b[sr]k_live_[A-Za-z0-9]{10,}"), "a live Stripe key"),
           (re.compile(r"\bwhsec_[A-Za-z0-9]{20,}"), "a Stripe webhook secret"),
           (re.compile(r"\bxkeysib-[a-f0-9]{20,}"), "a Brevo API key"),
           (re.compile(r"\brnd_[A-Za-z0-9]{20,}"), "a Render API key"),
           (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"), "a GitHub token"),
           (re.compile(r"\bATTA[A-Za-z0-9]{60,}"), "a Trello token"),
           (re.compile(r"(?im)^\s*(?:export\s+)?[\"']?(TRELLO_TOKEN|TRELLO_KEY|[A-Z_]*(?:SECRET|PASSWORD|PASSWD|API_KEY|TOKEN))"
                       r"[\"']?\s*[=:]\s*[\"']?[A-Za-z0-9_\-/+!@#$%^&*.]{12,}[\"']?\s*,?\s*$"), "a KEY=value secret line")]
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
OK_MAIL = re.compile(r"@(example\.(com|org|net)|uaply\.(net|com)|test|localhost|users\.noreply\.github\.com)$", re.I)
AUDIT_SECRET = ("looks like it contains", "holds private settings")


def run(args, cwd, timeout=120, env=None, binary=False):
    r = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, env=env)
    if binary:
        return r.returncode, r.stdout
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    return r.returncode, out.strip()


def git(cwd, *args, env=None):
    code, out = run(["git", *args], cwd, env=env)
    if code:
        raise RuntimeError(f"git {' '.join(args)}: {out.splitlines()[-1] if out else code}")
    return out


def check_text(path, data):
    """Plain-English problem with one file version, or None."""
    if PRIVATE_PATHS.search(path):
        return f"{path} (private file by name)"
    if len(data) > MAX_BYTES:
        return f"{path} (over 5 MB — too big to check for user data)"
    if b"\0" in data[:8000]:
        return None if BINARY_OK.search(path) else f"{path} (binary file — can't check it for keys or user data)"
    text = data.decode("utf-8", "replace")
    for rx, what in SECRETS:
        if rx.search(text):
            return f"{path} (looks like {what})"
    mails = {m.group(0).lower() for m in EMAIL.finditer(text) if not OK_MAIL.search(m.group(0))}
    if len(mails) >= 5:
        return f"{path} ({len(mails)} real-looking email addresses — user data?)"
    return None


def candidate(cwd, area, dirty):
    """The commit a push would send (a new WIP commit over the work as it is now, if dirty), built on a throwaway
    index so the real index is untouched until the scan is clean. Returns the commit sha."""
    if not dirty:
        return git(cwd, "rev-parse", "HEAD")
    index = git(cwd, "rev-parse", "--path-format=absolute", "--git-path", "index")
    tmpdir = tempfile.mkdtemp(prefix="uaply-wip-")
    try:
        tmp_index = os.path.join(tmpdir, "index")
        if os.path.isfile(index):
            shutil.copyfile(index, tmp_index)
        env = dict(os.environ, GIT_INDEX_FILE=tmp_index)
        git(cwd, "add", "-A", env=env)
        tree = git(cwd, "write-tree", env=env)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return git(cwd, "commit-tree", tree, "-p", "HEAD", "-m", f"WIP: {area} handoff")


def scan(cwd, commit):
    """Plain-English problems in every file version `commit` would publish (all objects no remote has yet); [] = safe."""
    # origin only: the push goes there, so commits that only a fork has must be checked too
    code, out = run(["git", "rev-list", "--objects", commit, "--not", "--remotes=origin"], cwd, binary=True)
    if code:
        return ["could not list what the push would send"]
    objs = {}
    for ln in out.split(b"\n"):
        sha, _, path = ln.partition(b" ")
        if sha and path:
            objs[sha.decode()] = path.decode("utf-8", "replace")
    bad = []
    # rev-list names each file version once; the same contents saved as .env AND a harmless name must still be caught
    code, names = run(["git", "log", "--format=", "--name-only", "--no-renames", "--root", "-m", commit,
                       "--not", "--remotes=origin"], cwd)
    if code:
        return ["could not list the file names the push would send"]
    for path in sorted(set(names.splitlines())):
        if path.strip() and PRIVATE_PATHS.search(path.strip()):
            problem = f"{path.strip()} (private file by name)"
            if problem not in bad:
                bad.append(problem)
    if objs:
        r = subprocess.run(["git", "cat-file", "--batch-check"], cwd=cwd, input="\n".join(objs).encode() + b"\n",
                           capture_output=True, timeout=120)
        if r.returncode:
            return ["could not read what the push would send"]
        for ln in r.stdout.decode().splitlines():
            sha, kind, size = (ln.split() + ["", ""])[:3]
            path = objs.get(sha, sha)
            if kind in ("tree", "commit", "tag"):
                continue
            if kind != "blob":
                problem = f"{path} (could not be read)"
            elif int(size) > MAX_BYTES:
                problem = check_text(path, b"") if PRIVATE_PATHS.search(path) else f"{path} (over 5 MB — too big to check for user data)"
            else:
                c, data = run(["git", "cat-file", "blob", sha], cwd, binary=True)
                problem = check_text(path, data) if c == 0 else f"{path} (could not be read)"
            if problem and problem not in bad:
                bad.append(problem)
    audit = os.path.join(cwd, "tools", "audit-files.py")
    if os.path.isfile(audit):
        _, out = run([sys.executable, audit], cwd, timeout=300)
        if "Traceback" in out or not re.search(r"\d+ error\(s\), \d+ warning\(s\)", out):
            bad.append("audit: tools/audit-files.py did not finish — fix it, then rerun")
        bad += [f"audit: {ln.strip()}" for ln in out.splitlines() if any(k in ln for k in AUDIT_SECRET)]
    return bad


def one(cwd, area):
    """Returns (wip_line or None, unpushed_line or None) for one worktree."""
    name = os.path.basename(os.path.normpath(cwd))
    if not os.path.isdir(cwd):
        return None, f"{cwd}: folder not found"
    try:
        branch = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    except RuntimeError as e:
        return None, f"{name}: not a git worktree ({e})"
    dirty = bool(git(cwd, "status", "--porcelain", "-uall"))
    upstream = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd)
    base = upstream[1] if upstream[0] == 0 else None
    if not base and run(["git", "rev-parse", "--verify", "-q", f"origin/{branch}"], cwd)[0] == 0:
        base = f"origin/{branch}"
    ahead = int(git(cwd, "rev-list", "--count", f"{base}..HEAD")) if base else 1
    if branch in PROTECTED:
        why = "detached HEAD" if branch == "HEAD" else f"on protected branch '{branch}'"
        if dirty or (base and ahead):
            return None, f"{name}: {why} — not committed/pushed by handoff; move the work to a c<card#>-<slug> branch"
        return None, None
    if not dirty and base and not ahead:
        return f"{branch} → {git(cwd, 'log', '-1', '--format=%h %s')}", None
    # a WIP commit mid-merge would push conflict markers and the index reset would drop the merge: leave it alone
    busy = [h for h in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply")
            if os.path.exists(git(cwd, "rev-parse", "--path-format=absolute", "--git-path", h))]
    if busy or git(cwd, "diff", "--name-only", "--diff-filter=U"):
        what = "a merge/rebase/cherry-pick in progress" if busy else "unresolved merge conflicts"
        return None, f"{name} ({branch}): NOT pushed — {what}; finish or abort it, then rerun"
    head = git(cwd, "rev-parse", "HEAD")
    commit = candidate(cwd, area, dirty)
    problems = scan(cwd, commit)
    if problems:
        return None, f"{name} ({branch}): NOT pushed — " + "; ".join(problems[:6])
    if commit != head:
        # exactly the tree that was scanned becomes the branch tip; then the index catches up (work files untouched)
        git(cwd, "update-ref", "-m", f"WIP: {area} handoff", "HEAD", commit, head)
        git(cwd, "reset", "-q")
    code, out = run(["git", "push", "-q", "-u", "origin", f"HEAD:refs/heads/{branch}"], cwd)
    tip = git(cwd, "log", "-1", "--format=%h %s")
    if code:
        reason = out.splitlines()[-1] if out else f"exit {code}"
        return None, f"{name} ({branch} {tip}): committed locally, push failed — {reason}"
    return f"{branch} → {tip}", None


def wip(area, paths):
    wips, local = [], []
    for p in paths or ["."]:
        try:
            w, u = one(os.path.abspath(p), area)
        except Exception as e:  # noqa: BLE001 — one bad worktree must not hide the others
            w, u = None, f"{p}: check failed — {str(e)[:150]}"
        if w:
            wips.append(w)
        if u:
            local.append(u)
    print("WIP BRANCHES: " + ("; ".join(wips) if wips else "none"))
    try:
        from _common import log_event
        log_event("handoff", action="wip_pushed", branches=len(wips), unpushed=len(local))
    except Exception:
        pass
    print("UNPUSHED WORK: " + ("; ".join(local) if local else "none (checked)"))
    return 1 if local else 0
