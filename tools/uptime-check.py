"""Is uaply.net up? The outside uptime check that .github/workflows/uptime.yml runs on GitHub (docs/uptime.md says what it does in plain
words). It asks the site from outside Render, the way a phone app or a visitor would:
  /healthz   must answer 200 with {"ok": true} (the server is running and not stopping)
  /          the home page must answer 200 and name UAply (the domain, Cloudflare and the page itself)
  /readyz    must answer 200 once the server has one; a 404 is a SKIP ("not on this server yet"), never an alarm

  python tools/uptime-check.py                                 checks https://uaply.net once; exit 0 up, 1 down
  python tools/uptime-check.py --base http://127.0.0.1:9       a dead address: every check FAILs, exit 1
Options:
  --confirm-after SECONDS   when a check fails, wait this long and check again; the site is "down" only when the second try fails too, so
                            the few seconds of a deploy never raise an alarm (the workflow uses 120)
  --json FILE               also write the result and the site's public /api/status facts (yes/no answers and the commit, never a key)
                            to FILE: the daily health snapshot keeps these after Render deletes its logs (7 days)
  --issue                   keep the single GitHub issue "uaply.net is down": open it when the site is down, edit it (silently) while it stays
                            down, and close it with a note when the site is back. Only an issue that GitHub Actions opened
                            (github-actions[bot]) is edited or closed: one a person opens with the same title is never touched. Needs GITHUB_TOKEN (or GH_TOKEN) and GITHUB_REPOSITORY,
                            which GitHub Actions sets; --repo and --api override them (the test points --api at a stand-in GitHub).
                            Exit 0 when the issue says what is true (up or down), 2 when GitHub could not be told.
  --notify "@a @b"          who the issue mentions (default: the UPTIME_NOTIFY variable, else nobody: the repository's watchers still get it)
Standard library only. It never signs in, never sends email itself and never prints the token."""
import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

TITLE = "uaply.net is down"
BOT = "github-actions[bot]"                       # who opens the issue when the workflow's GITHUB_TOKEN is used

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--base", default="https://uaply.net")
ap.add_argument("--timeout", type=float, default=30)
ap.add_argument("--confirm-after", type=float, default=0)
ap.add_argument("--json", default="")
ap.add_argument("--issue", action="store_true")
ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
ap.add_argument("--api", default=os.environ.get("GITHUB_API_URL", "https://api.github.com"))
ap.add_argument("--notify", default=os.environ.get("UPTIME_NOTIFY", ""))
A = ap.parse_args()
BASE = A.base.rstrip("/")
UA = "UAply-uptime-check/1 (+https://uaply.net)"


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def fetch(path):
    """(status or None, body text, headers, ms, error words). Redirects are followed, as a browser would."""
    t0 = time.monotonic()
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "*/*", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=A.timeout) as r:
            return r.status, r.read(200000).decode("utf-8", "replace"), r.headers, int((time.monotonic() - t0) * 1000), ""
    except urllib.error.HTTPError as e:
        body = e.read(20000).decode("utf-8", "replace") if e.fp else ""
        return e.code, body, e.headers, int((time.monotonic() - t0) * 1000), ""
    except Exception as e:                        # refused, timed out, no such name, a bad certificate: the site cannot be reached
        why = getattr(e, "reason", None) or e
        return None, "", {}, int((time.monotonic() - t0) * 1000), "%s: %s" % (type(e).__name__, why)


def check_once():
    """Every check once: a list of {name, path, result PASS/FAIL/SKIP, status, ms, detail}."""
    out = []

    def add(name, path, result, status, ms, detail=""):
        out.append({"name": name, "path": path, "result": result, "status": status, "ms": ms, "detail": detail})

    def blocked(h):
        return (h.get("cf-mitigated") or "") == "challenge"

    st, body, h, ms, err = fetch("/healthz")
    try:
        ok = json.loads(body).get("ok") is True
    except (ValueError, AttributeError):
        ok = False
    if st == 200 and ok:
        add("health (/healthz)", "/healthz", "PASS", st, ms)
    else:
        add("health (/healthz)", "/healthz", "FAIL", st, ms, err or ("Cloudflare's bot check answered, not UAply" if blocked(h) else
                                                                     "answered %s %s" % (st, body.strip()[:80])))
    st, body, h, ms, err = fetch("/")
    if st == 200 and re.search(r"uaply", body, re.I):
        add("home page (/)", "/", "PASS", st, ms)
    else:
        add("home page (/)", "/", "FAIL", st, ms, err or ("Cloudflare's bot check answered, not UAply" if blocked(h) else
                                                         "answered %s without the UAply page" % st))
    st, body, h, ms, err = fetch("/readyz")
    if st == 200:
        add("ready (/readyz)", "/readyz", "PASS", st, ms)
    elif st == 404:
        add("ready (/readyz)", "/readyz", "SKIP", st, ms, "not on this server yet")
    else:
        add("ready (/readyz)", "/readyz", "FAIL", st, ms, err or "answered %s %s" % (st, body.strip()[:80]))
    return out


def show(checks, label=""):
    for c in checks:
        line = "%s %s%s  (%s, %d ms)" % (c["result"], label, c["name"], c["status"] if c["status"] is not None else "no answer", c["ms"])
        print(line + ("  -> " + c["detail"] if c["detail"] else ""))
    sys.stdout.flush()


def is_down(checks):
    return any(c["result"] == "FAIL" for c in checks)


# ---- the check ----
started = now()
first = check_once()
show(first)
checks, down = first, is_down(first)
if down and A.confirm_after > 0:
    print("A check failed. Checking again in %d seconds, so a deploy's few seconds never raise an alarm." % A.confirm_after)
    sys.stdout.flush()
    time.sleep(A.confirm_after)
    checks = check_once()
    show(checks, "(again) ")
    down = is_down(checks)
print("%s is %s at %s" % (BASE, "DOWN" if down else "up", now().isoformat()))

if A.json:
    st, body, _, ms, err = fetch("/api/status")
    try:
        facts = json.loads(body) if st == 200 else None
    except ValueError:
        facts = None
    snap = {"checkedAt": started.isoformat(), "base": BASE, "up": not down, "checks": checks,
            "firstTry": first if first is not checks else None,
            "status": facts, "statusAnswer": st, "statusMs": ms}
    d = os.path.dirname(os.path.abspath(A.json))
    os.makedirs(d, exist_ok=True)
    with open(A.json, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2)
    print("wrote " + A.json)

if not A.issue:
    sys.exit(1 if down else 0)


# ---- the single GitHub issue ----
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
if not TOKEN or not A.repo:
    print("FAIL --issue needs GITHUB_TOKEN (or GH_TOKEN) and --repo (or GITHUB_REPOSITORY)")
    sys.exit(2)
API = A.api.rstrip("/")


def gh(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def run_link():
    s, rid = os.environ.get("GITHUB_SERVER_URL", ""), os.environ.get("GITHUB_RUN_ID", "")
    return "%s/%s/actions/runs/%s" % (s, A.repo, rid) if s and rid else ""


def field(body, name):
    m = re.search(r"^- %s: (.+)$" % re.escape(name), body or "", re.M)
    return m.group(1).strip() if m else ""


def issue_body(first_seen, count, checks):
    tries = " twice in a row (two tries %d seconds apart)" % A.confirm_after if A.confirm_after > 0 else ""
    failed = [c for c in checks if c["result"] == "FAIL"]
    # say what happened: no answer at all, or an answer that was an error; and the apps only when the site itself (health or home) failed
    if failed and all(c["status"] is None for c in failed):
        what = "got no answer from %s%s." % (BASE, tries)
    else:
        what = "got an error answer from %s%s." % (BASE, tries)
    lines = ["UAply's outside uptime check " + what]
    if any(c["path"] in ("/healthz", "/") for c in failed):
        lines.append("The phone apps load this site, so they are probably down too.")
    lines += ["",
             "- First seen: %s" % first_seen, "- Last checked: %s" % now().isoformat(), "- Failed checks in a row: %d" % count]
    if run_link():
        lines.append("- Latest check: %s" % run_link())
    lines += ["", "What failed on the latest try:", ""]
    for c in failed:
        lines.append("- %s %s: %s" % (c["result"], c["name"], c["detail"] or c["status"]))
    lines += ["", "What to do: open the service on Render (uaply, Events and Logs), then DEPLOY.md, \"Running the live site\".",
              "This issue closes by itself with a note when the site answers again. To silence the check, see docs/uptime.md."]
    if A.notify.strip():
        lines += ["", A.notify.strip()]
    return "\n".join(lines)


try:
    found = [i for i in gh("GET", "/repos/%s/issues?state=open&per_page=100" % A.repo) or []
             if i.get("title") == TITLE and "pull_request" not in i and (i.get("user") or {}).get("login") == BOT]
    issue = found[0] if found else None
    if down and not issue:
        made = gh("POST", "/repos/%s/issues" % A.repo, {"title": TITLE, "body": issue_body(now().isoformat(), 1, checks)})
        print("opened issue #%s \"%s\"" % (made.get("number"), TITLE))
    elif down:
        first_seen = field(issue.get("body"), "First seen") or now().isoformat()
        try:
            count = int(field(issue.get("body"), "Failed checks in a row") or 0) + 1
        except ValueError:
            count = 1
        gh("PATCH", "/repos/%s/issues/%s" % (A.repo, issue["number"]), {"body": issue_body(first_seen, count, checks)})
        print("updated issue #%s (still down, %d checks in a row)" % (issue["number"], count))
    elif issue:
        first_seen = field(issue.get("body"), "First seen")
        try:
            mins = int((now() - datetime.datetime.fromisoformat(first_seen)).total_seconds() // 60)
            how_long = " It was first seen down at %s, about %d minutes earlier." % (first_seen, mins)
        except ValueError:
            how_long = ""
        note = "%s answers again: no check failed at %s (%s).%s Closing." % (
        BASE, now().isoformat(), ", ".join("%s %s" % (c["name"], c["result"]) for c in checks), how_long)
        gh("POST", "/repos/%s/issues/%s/comments" % (A.repo, issue["number"]), {"body": note})
        gh("PATCH", "/repos/%s/issues/%s" % (A.repo, issue["number"]), {"state": "closed", "state_reason": "completed"})
        print("closed issue #%s: the site is back" % issue["number"])
    else:
        print("no open issue, nothing to change")
except Exception as e:
    print("FAIL could not update the GitHub issue: %s %s" % (type(e).__name__, getattr(e, "code", "") or e))
    sys.exit(2)
sys.exit(0)
