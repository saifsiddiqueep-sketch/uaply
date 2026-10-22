"""The outside uptime check (tools/uptime-check.py, run by .github/workflows/uptime.yml) against a stand-in site and a stand-in GitHub, both
on this computer: a site that is up, one that blips for a second (a deploy), one whose health check says 503, a dead address, and the
way back up. It proves the single issue "uaply.net is down" is opened only after two failed tries, edited (never duplicated) while the site
stays down, and closed with a note when it is back; and that the daily snapshot file holds the public facts. Never touches the live site
or the real GitHub.
  python tools/test-uptime.py [port]          (uses that port and the next two; without one, free ports the computer picks)
A port that is already taken fails at once (no address reuse), so two runs at the same time can never answer each other's requests."""
import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 0
BOT = {"login": "github-actions[bot]"}
TOKEN = "ghs_test_token_never_printed"
R = []

site = {"mode": "up", "blips": 0, "readyz": 404, "home": "<title>UAply</title>"}
issues, comments, gh_seen = {}, [], []
# an issue a person opened with the same title (say, for broken swiping the check cannot see): the check must never edit or close it
human = {"number": 77, "title": "uaply.net is down", "state": "open", "body": "Swiping is broken for me", "user": {"login": "a-founder"}}


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


class Site(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, body, ctype="application/json"):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path
        if p == "/healthz":
            if site["mode"] == "blip" and site["blips"] > 0:          # a deploy: the first answer is 503, the next ones are fine
                site["blips"] -= 1
                return self.reply(503, '{"ok": false, "stopping": true}')
            if site["mode"] == "sick":
                return self.reply(503, '{"ok": false, "stopping": true}')
            return self.reply(200, '{"ok": true}')
        if p == "/":
            return self.reply(200, site["home"], "text/html")
        if p == "/readyz":
            return self.reply(site["readyz"], "{}")
        if p == "/api/status":
            return self.reply(200, '{"ok": true, "public": true, "email": true, "commit": "abc1234"}')
        return self.reply(404, "{}")


class GitHub(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def auth(self):
        gh_seen.append((self.command, self.path.split("?")[0], self.headers.get("Authorization")))
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            self.reply(401, {"message": "Bad credentials"})
            return False
        return True

    def do_GET(self):
        if not self.auth():
            return
        if self.path.startswith("/repos/o/r/issues?") and "state=open" in self.path:
            # a pull request also comes back from this list on GitHub: the check must not take it for the issue
            pr = {"number": 99, "title": "uaply.net is down", "state": "open", "body": "", "pull_request": {}, "user": BOT}
            return self.reply(200, [pr, human] + [i for i in issues.values() if i["state"] == "open"])
        self.reply(404, {})

    def do_POST(self):
        if not self.auth():
            return
        b = self.body()
        if self.path == "/repos/o/r/issues":
            n = len(issues) + 1
            issues[n] = {"number": n, "title": b["title"], "body": b["body"], "state": "open", "user": BOT}
            return self.reply(201, issues[n])
        if self.path.startswith("/repos/o/r/issues/") and self.path.endswith("/comments"):
            comments.append((int(self.path.split("/")[5]), b["body"]))
            return self.reply(201, {})
        self.reply(404, {})

    def do_PATCH(self):
        if not self.auth():
            return
        n = int(self.path.split("/")[5])
        target = issues.get(n) or (human if n == human["number"] else None)
        if target is None:
            return self.reply(404, {"message": "Not Found"})
        target.update(self.body())
        self.reply(200, target)


class Server(http.server.ThreadingHTTPServer):
    allow_reuse_address = False                     # http.server turns it on; on Windows that lets a second process share a taken port
    allow_reuse_port = False


ports = []
for port, h in ((PORT, Site), (PORT + 1 if PORT else 0, GitHub)):
    srv = Server(("127.0.0.1", port), h)
    ports.append(srv.server_address[1])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
SITE, GH = ports
if PORT:
    DEAD = PORT + 2                                 # nothing listens on DEAD
else:                                               # a port that was free a moment ago and that nothing listens on now
    k = socket.socket()
    k.bind(("127.0.0.1", 0))
    DEAD = k.getsockname()[1]
    k.close()


def run(*args, base=None, token=TOKEN, issue=True):
    cmd = [sys.executable, os.path.join(HERE, "uptime-check.py"), "--base", base or "http://127.0.0.1:%d" % SITE, "--timeout", "5"]
    if issue:
        cmd += ["--issue", "--repo", "o/r", "--api", "http://127.0.0.1:%d" % GH, "--notify", "@founder-one @founder-two"]
    env = dict(os.environ, GITHUB_TOKEN=token, GITHUB_SERVER_URL="https://github.example", GITHUB_RUN_ID="42")
    env.pop("GH_TOKEN", None)
    env.pop("UPTIME_NOTIFY", None)
    p = subprocess.run(cmd + list(args), capture_output=True, text=True, env=env, timeout=120)
    return p.returncode, p.stdout + p.stderr


def open_issues():
    return [i for i in issues.values() if i["state"] == "open"]


# 1. the plain check, no GitHub
code, out = run(issue=False)
t("a site that is up: exit 0, health and home page PASS", (code, "PASS health (/healthz)" in out, "PASS home page (/)" in out), (0, True, True))
t("no /readyz on the server yet (404) is a SKIP, not an alarm", "SKIP ready (/readyz)" in out and "not on this server yet" in out, True)
code, out = run(base="http://127.0.0.1:%d" % DEAD, issue=False)
t("a dead address: exit 1, every check FAILs, the line says DOWN", (code, out.count("FAIL "), "is DOWN" in out), (1, 3, True))
site["mode"] = "sick"
code, out = run(issue=False)
t("health answering 503: exit 1, and the reason is in the line", (code, "answered 503" in out), (1, True))
site["mode"] = "up"
site["readyz"] = 500
code, out = run(issue=False)
t("a /readyz that answers 500 once it exists is a FAIL", (code, "FAIL ready (/readyz)" in out), (1, True))
site["readyz"] = 200
code, out = run(issue=False)
t("a /readyz that answers 200 is a PASS", (code, "PASS ready (/readyz)" in out), (0, True))
site["readyz"] = 404
site["home"] = "<h1>Something else</h1>"
code, out = run(issue=False)
t("a home page that is not UAply's is a FAIL", (code, "without the UAply page" in out), (1, True))
site["home"] = "<title>UAply</title>"

# 2. the daily snapshot file
snap = os.path.join(tempfile.mkdtemp(prefix="uaply-uptime-"), "day", "uaply-health-2026-10-22.json")
code, out = run("--json", snap, issue=False)
data = json.load(open(snap, encoding="utf-8")) if os.path.exists(snap) else {}
t("--json writes the dated snapshot with the result and the public facts", (code, data.get("up"), (data.get("status") or {}).get("commit"),
  len(data.get("checks") or [])), (0, True, "abc1234", 3))

# 3. the single issue
code, out = run("--confirm-after", "1")
t("up, no issue open: nothing changes on GitHub", (code, len(issues), "nothing to change" in out), (0, 0, True))
site.update(mode="blip", blips=1)
code, out = run("--confirm-after", "1")
t("a one-second blip (a deploy): the second try passes, no issue", (code, len(issues), "Checking again" in out, "is up" in out), (0, 0, True, True))
site["mode"] = "sick"
code, out = run("--confirm-after", "1")
t("down on both tries: one issue opened, exit 0 (the issue says it)", (code, len(issues), len(open_issues())), (0, 1, 1))
i = issues.get(1) or {"title": "", "body": ""}     # a plain FAIL below, never a crash, if no issue was opened
t("...saying the site answered with an error (503), and that the apps are probably down too",
  ("got an error answer from" in i["body"], "got no answer" in i["body"], "phone apps load this site" in i["body"]), (True, False, True))
t("...titled exactly \"uaply.net is down\"", i["title"], "uaply.net is down")
t("...saying what failed, when, how many tries, the run link and the people", all(x in i["body"] for x in (
  "twice in a row", "- First seen: ", "- Failed checks in a row: 1", "FAIL health (/healthz): answered 503", "https://github.example/o/r/actions/runs/42",
  "Render", "docs/uptime.md", "@founder-one @founder-two")), True)
t("...and not listing the /readyz SKIP as a failure", "readyz" in i["body"], False)
first_seen = [x for x in i["body"].splitlines() if x.startswith("- First seen: ")][0]
code, out = run("--confirm-after", "1")
t("still down: the same issue is edited, not a second one, and no comment (no email every check)",
  (code, len(issues), len(comments), "Failed checks in a row: 2" in issues[1]["body"]), (0, 1, 0, True))
t("...keeping when it was first seen", first_seen in issues[1]["body"], True)
code, out = run("--confirm-after", "1", base="http://127.0.0.1:%d" % DEAD)
t("a dead address while the issue is open: still one issue, 3 in a row, the reason says no answer",
  (len(issues), "Failed checks in a row: 3" in issues[1]["body"], "no answer" in issues[1]["body"] or "URLError" in issues[1]["body"]),
  (1, True, True))
t("...and its first sentence now says no answer, not an error answer",
  ("got no answer from" in issues[1]["body"], "got an error answer" in issues[1]["body"]), (True, False))
site["mode"] = "up"
code, out = run("--confirm-after", "1")
t("back up: a note is added and the issue closes", (code, issues[1]["state"], len(comments), comments[0][0] if comments else None), (0, "closed", 1, 1))
t("...the note says it answers again and since when it was down", ("answers again" in comments[0][1], "first seen down" in comments[0][1]),
  (True, True))
t("...and says 'no check failed' with the /readyz SKIP named, never 'every check passed'",
  ("no check failed" in comments[0][1], "ready (/readyz) SKIP" in comments[0][1], "every check passed" in comments[0][1]), (True, True, False))
code, out = run("--confirm-after", "1")
t("up again afterwards: nothing changes (the pull request with the same title is never touched)",
  (code, len(issues), len(comments), "nothing to change" in out, any("/issues/99" in p for _, p, _ in gh_seen)), (0, 1, 1, True, False))
site["mode"] = "sick"
code, out = run("--confirm-after", "1")
t("a new outage later opens a new issue (the closed one stays as history)", (len(issues), len(open_issues()), issues[2]["state"]), (2, 1, "open"))
site["mode"] = "up"
run("--confirm-after", "1")
site["readyz"] = 500
code, out = run("--confirm-after", "1")
t("only /readyz fails (500): an issue that says an error answer and does not claim the apps are down",
  (len(issues), issues[3]["state"] if 3 in issues else None, "got an error answer" in issues.get(3, {}).get("body", ""),
   "phone apps" in issues.get(3, {}).get("body", ""), "FAIL ready (/readyz): answered 500" in issues.get(3, {}).get("body", "")),
  (3, "open", True, False, True))
site["readyz"] = 404
code, out = run("--confirm-after", "1")
t("...and it closes when /readyz is back to 404 (a SKIP)", (code, issues.get(3, {}).get("state")), (0, "closed"))
t("an issue a person opened with the same title is never edited, commented on or closed",
  (human["state"], human["body"], any("/issues/77" in p for _, p, _ in gh_seen)), ("open", "Swiping is broken for me", False))

# 4. what can go wrong on GitHub's side
code, out = run("--confirm-after", "1", token="wrong")
t("GitHub refuses the token: exit 2 with a plain FAIL line", (code, "FAIL could not update the GitHub issue" in out), (2, True))
code, out = run(token="")
t("no token at all: exit 2, says what is missing", (code, "needs GITHUB_TOKEN" in out), (2, True))
every = "".join(run("--confirm-after", "1", token=tok)[1] for tok in (TOKEN, "wrong"))
t("the token is never printed", TOKEN in every or "wrong" in every.replace("went wrong", ""), False)
t("every call to GitHub carried the token as a Bearer header", all(a in ("Bearer " + TOKEN, "Bearer wrong") for _, _, a in gh_seen), True)

# 5. the workflows themselves (PyYAML when installed: tools/audit-files.py and CI install it)
wf = os.path.join(ROOT, ".github", "workflows")
try:
    import yaml
    up = yaml.safe_load(open(os.path.join(wf, "uptime.yml"), encoding="utf-8"))
    on = up.get("on", up.get(True))
    crons = [c["cron"] for c in on["schedule"]]
    job = up["jobs"]["check"]
    t("uptime.yml: every 10 minutes (the 7-past line and the in-between ones)", crons, ["7 * * * *", "17,27,37,47,57 * * * *"])
    t("uptime.yml: can open issues and read the code, nothing more", up["permissions"], {"contents": "read", "issues": "write"})
    t("uptime.yml: the job runs every 10 minutes and by hand, only the 7-past line when UPTIME_HOURLY is on, and never when paused",
      job["if"].replace("\n", " ").split(), ("vars.UPTIME_PAUSED != 'on' && (github.event_name != 'schedule' || github.event.schedule == '7 * * * *' "
                                              "|| vars.UPTIME_HOURLY != 'on')").split())
    t("uptime.yml: the checkout does not leave the token in .git/config", job["steps"][0]["with"].get("persist-credentials"), False)
    t("uptime.yml: runs the check with two tries 2 minutes apart and the issue", "--confirm-after 120 --issue" in json.dumps(job["steps"]), True)
    day = yaml.safe_load(open(os.path.join(wf, "health-snapshot.yml"), encoding="utf-8"))
    don = day.get("on", day.get(True))
    steps = json.dumps(day["jobs"]["snapshot"]["steps"])
    t("health-snapshot.yml: once a day, and by hand", ([c["cron"] for c in don["schedule"]], "workflow_dispatch" in don), (["23 11 * * *"], True))
    t("health-snapshot.yml: keeps a dated file for 90 days, without the wrong logins", ("--json" in steps, "retention-days" in steps and "90" in steps,
      "--no-rate-limit" in steps, "upload-artifact" in steps), (True, True, True, True))
    snap_steps = day["jobs"]["snapshot"]["steps"]
    t("health-snapshot.yml: a missing or broken script turns the run red (no JSON, no summary line, no files)",
      ("test -s" in snap_steps[1]["run"], "passed, [0-9]+ failed" in snap_steps[1]["run"], snap_steps[2]["with"].get("if-no-files-found")),
      (True, True, "error"))
    t("health-snapshot.yml: reads only", day["permissions"], {"contents": "read"})
except ImportError:
    print("SKIP the workflow files (needs PyYAML: pip install pyyaml)")

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
