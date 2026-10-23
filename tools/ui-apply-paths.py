"""Swipe right in a real browser on every delivery path and check what the person is told: the toast and the Applied row.
Starts its own stand-in hiring system (mock-ats.py), stand-in mail server (fake-smtp.py) and three UAply servers: dev in test mode,
dev in live mode (mail to the stand-in, owner copy on) and the sandbox. Employers: one that takes email, one connected through
Greenhouse, one through Lever, one link-only, and public Greenhouse postings (one asks a question no profile can answer, one
employer system that fails). Nothing leaves this computer. It runs twice, on fresh servers each time: at phone size (390x844) and at laptop size
(1280x800), and at 375x812 (the smallest phone the sign-up and the agreement are checked at); SIZES=390x844 runs one. In the phone app (a stand-in for its assist plugin) a hand-off opens the employer's form right after the
swipe ("one tap", October 23), timed from the swipe to the form being asked for.
  python tools/ui-apply-paths.py [first port]        (uses 5 ports from there; default 18780)"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
P = int(sys.argv[1]) if len(sys.argv) > 1 else 18780
ATS, SMTP, PORTS = P, P + 1, {"devtest": P + 2, "devlive": P + 3, "sbtest": P + 4}
INST = {"devtest": "dev", "devlive": "dev", "sbtest": "sandbox"}
TMP = tempfile.mkdtemp(prefix="uaply-applypaths-")
sys.path.insert(0, ROOT)
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=TMP)
import jobs_api  # noqa: E402


def seed(data):
    """The employers and postings every server knows (the same for all three)."""
    os.makedirs(data, exist_ok=True)

    def post(kind, board, name, rid, title):
        url = ("https://boards.greenhouse.io/%s/jobs/%s" % (board, rid)) if kind == "greenhouse" else "https://jobs.lever.co/%s/%s" % (board, rid)
        return jobs_api._normalize(dict(id=rid, title=title, company=name, loc="Philadelphia, PA", remote=None, url=url, salary_text="", posted=int(time.time()),
                                        text="Python and SQL. Build data tools with the team. 1 year of experience."), kind, name, board)
    cache = {"_version": jobs_api.CACHE_VERSION}
    for kind, board, name in jobs_api.SOURCES:              # every feed is "fresh and empty" so nothing is fetched from the internet
        if kind in ("greenhouse", "lever"):
            cache["%s|%s|%s" % (kind, board, name)] = {"at": time.time(), "jobs": [], "status": "0 jobs"}
    cache["greenhouse|discord|Discord"]["jobs"] = [post("greenhouse", "discord", "Discord", "1001", "Data Intern"),
                                                   post("greenhouse", "discord", "Discord", "1002", "Data Intern Two"),      # the one-tap swipe
                                                   post("greenhouse", "discord", "Discord", "1003", "Data Intern Three")]    # one tap, with the switch off
    cache["greenhouse|dropbox|Dropbox"]["jobs"] = [post("greenhouse", "dropbox", "Dropbox", "1005", "Broken System Intern")]
    with open(os.path.join(data, "jobs-cache.json"), "w", encoding="utf-8") as f:
        json.dump(cache, f)
    consent = "test partner agreement"
    with open(os.path.join(data, "uaply-partners.json"), "w", encoding="utf-8") as f:
        json.dump({"employers": [
            {"name": "Mail Co", "consent": consent, "contact": "hr@mailco.example", "url": "https://mailco.example/jobs",
             "jobs": [{"role": "Marketing Intern", "skills": ["SEO"], "type": "internship", "loc": "Philadelphia, PA", "mode": "hybrid"},
                      {"role": "Sales Intern", "skills": ["SEO"], "type": "internship", "loc": "Philadelphia, PA", "mode": "hybrid"}]},
            {"name": "GH Partner", "consent": consent, "url": "https://ghpartner.example/careers", "ats": {"kind": "greenhouse", "board": "acme", "api_key": "gh-secret-key-123"},
             "jobs": [{"role": "Robotics Intern", "skills": ["Python"], "ats_job_id": "1001", "loc": "Philadelphia, PA", "type": "internship"},
                      {"role": "Odd Question Role", "skills": ["Python"], "ats_job_id": "1003", "loc": "Philadelphia, PA"}]},
            {"name": "Lever Partner", "consent": consent, "url": "https://leverpartner.example/careers", "ats": {"kind": "lever", "board": "acme", "api_key": "lever-key-456"},
             "jobs": [{"role": "Support Engineer", "skills": ["SQL"], "ats_job_id": "posting-1", "loc": "Philadelphia, PA"}]},
            {"name": "Link Co", "consent": consent, "url": "https://linkco.example/careers",
             "jobs": [{"role": "Barista", "skills": ["Communication"], "type": "parttime", "loc": "Philadelphia, PA"}]}]}, f)


def call(port, path, body=None, cookie=""):
    h = {"Origin": "http://127.0.0.1:%d" % port, "Content-Type": "application/json"}
    if cookie:
        h["Cookie"] = cookie
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=json.dumps(body).encode() if body is not None else None, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read()), r.headers


def account(srv, data):
    """A verified account (ui@example.com), the way a person makes one: sign up, then type the emailed code. The servers run in
    sign-up test mode (UAPLY_SIGNUP_TEST=1), which confirms the account at once; the live one does not, and its code is read from the mail.
    Returns the session cookie: the sign-in gate keeps the job list for signed-in, confirmed people."""
    port = PORTS[srv]
    for i in range(60):                    # the server may still be starting
        try:
            out, hdrs = call(port, "/api/auth/signup", {"email": "ui@example.com", "password": "test pass 12345", "first": "Sam", "last": "Rivera", "agree": True})
            break
        except OSError:
            if i == 59:
                raise
            time.sleep(0.5)
    ck = hdrs["Set-Cookie"].split(";")[0]
    if (out.get("user") or {}).get("emailVerified"):
        return ck
    code = []
    for _ in range(40):
        time.sleep(0.25)
        text = ""
        mail = os.path.join(data, "mail.jsonl")
        if os.path.exists(mail):
            text = " ".join(json.loads(x)["raw"] for x in open(mail, encoding="utf-8") if x.strip())
        c = sqlite3.connect(os.path.join(data, INST[srv], "uaply.db"))
        text += " ".join(r[0] for r in c.execute("SELECT body FROM user_mail"))
        c.close()
        code = re.findall(r"verification code is:\s+(\d{6})", text)
        if code:
            break
    call(port, "/api/auth/verify", {"code": code[-1] if code else ""}, ck)
    return ck


def run(size):
    """Fresh servers, the account, then the browser half on each server at this size. Returns the number of servers whose half failed."""
    w, h = size.split("x")
    tmp = os.path.join(TMP, size)
    procs = [subprocess.Popen([sys.executable, os.path.join(HERE, "mock-ats.py"), str(ATS)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]
    try:
        for srv, port in PORTS.items():
            data = os.path.join(tmp, srv)
            seed(data)
            cfg = {"feeds": ["greenhouse", "lever"], "delivery": "test", "smtp": {}, "google": {}, "owner_copy": ""}
            if srv == "devlive":
                cfg.update(delivery="live", owner_copy="owner@uaply.example", smtp={"host": "127.0.0.1", "port": SMTP, "starttls": False, "from_addr": "apply@uaply.example"})
                procs.append(subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(SMTP), os.path.join(data, "mail.jsonl")],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            env = dict(os.environ, UAPLY_DATA_DIR=data, UAPLY_CONFIG_JSON=json.dumps(cfg), UAPLY_ATS_BASE_GREENHOUSE="http://127.0.0.1:%d" % ATS,
                       UAPLY_ATS_BASE_LEVER="http://127.0.0.1:%d" % ATS, UAPLY_ATS_JSON=json.dumps([{"kind": "greenhouse", "board": "dropbox", "api_key": "gh-secret-key-123"}]))
            env.pop("RENDER", None)
            # sign-up test mode (never public) confirms ui@example.com at once, but it also sends no mail at all, so the live server, whose
            # job is to send applications to the stand-in mail server, runs without it and its account is confirmed with the emailed code
            env["UAPLY_SIGNUP_TEST"] = "" if srv == "devlive" else "1"
            procs.append(subprocess.Popen([sys.executable, "serve.py", str(port), INST[srv], "--api"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        for srv, port in PORTS.items():
            for _ in range(60):
                try:
                    if json.loads(urllib.request.urlopen("http://127.0.0.1:%d/healthz" % port, timeout=5).read()).get("ok"):
                        break
                except Exception:
                    time.sleep(0.5)
            ck = account(srv, os.path.join(tmp, srv))
            ids = {}
            for _ in range(60):          # the job list answers only a signed-in, verified account (the sign-in gate)
                try:
                    ids = {"%s|%s" % (j["co"], j["role"]): j["id"] for j in call(port, "/api/jobs", cookie=ck)[0]["jobs"]}
                    if ids:
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            json.dump(ids, open(os.path.join(tmp, "ids-%s.json" % srv), "w"))
        failed = 0
        for srv, port in PORTS.items():
            env = dict(os.environ, SRV=srv, PORT=str(port), IDS=os.path.join(tmp, "ids-%s.json" % srv), W=w, H=h)
            failed += subprocess.run(["node", os.path.join(HERE, "cdp.js"), os.path.join(HERE, "ui-apply-paths.js")], cwd=ROOT, env=env).returncode != 0
        return failed
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(10)
            except Exception:
                pass
        time.sleep(0.5)


code = 1
try:
    failed = 0
    for size in (os.environ.get("SIZES") or "375x812 390x844 1280x800").split():
        print("---- %s ----" % size)
        sys.stdout.flush()
        failed += run(size)
    code = 1 if failed else 0
finally:
    shutil.rmtree(TMP, ignore_errors=True)
print("apply paths in the browser:", "all passed" if code == 0 else "FAILED")
sys.exit(code)
