"""The employer connect walkthrough (swipe phase B, October 23, 2026), in test mode: the owner makes the employer's link, the employer opens
it in a browser, pastes their Greenhouse key, tests it and connects (under two minutes, timed), and the next swipe right on one of their
postings arrives in their hiring system as a new candidate. A stand-in Greenhouse (tools/mock-ats.py) and a UAply server in sign-up test
mode, both started and stopped here; nothing leaves this computer.
  python tools/ui-connect.py [first port]        (uses 2 ports from there; default: two free ones in a row)"""
import base64
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def _free_base(n=2):
    for base in range(32000, 60000, 5):
        socks = []
        try:
            for k in range(n):
                s_ = socket.socket()
                s_.bind(("127.0.0.1", base + k))
                socks.append(s_)
            return base
        except OSError:
            pass
        finally:
            for s_ in socks:
                s_.close()
    return 20470


P = int(sys.argv[1]) if len(sys.argv) > 1 else _free_base()
MOCK, PORT = P, P + 1
TMP = tempfile.mkdtemp(prefix="uaply-connect-")
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=TMP)
import jobs_api  # noqa: E402
import consent_api  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


def req(method, path, body=None, cookie=""):
    h = {"Host": "127.0.0.1:%d" % PORT, "Origin": "http://127.0.0.1:%d" % PORT}
    if cookie:
        h["Cookie"] = cookie
    if body is not None:
        h["Content-Type"] = "application/json"
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=60)
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    raw = r.read()
    ck = [v.split(";", 1)[0] for k, v in r.getheaders() if k.lower() == "set-cookie"]
    c.close()
    try:
        return r.status, json.loads(raw), ck
    except ValueError:
        return r.status, raw.decode("utf-8", "replace"), ck


SRC = [s for s in jobs_api.SOURCES if s[0] == "greenhouse"][0]
POSTING = jobs_api._normalize(dict(id="1001", title="Robotics Intern", company="Acme Robotics", loc="Philadelphia, PA", remote=None,
                                   url="https://job-boards.greenhouse.io/acme/jobs/1001", salary_text="", posted=int(time.time()),
                                   text="Python and SQL. Build robots with the team. 1 year of experience."), "greenhouse", "Acme Robotics", "acme")
POSTING2 = jobs_api._normalize(dict(id="1002", title="Controls Intern", company="Acme Robotics", loc="Philadelphia, PA", remote=None,
                                    url="https://job-boards.greenhouse.io/acme/jobs/1002", salary_text="", posted=int(time.time()),
                                    text="Python and SQL. Controls with the team. 1 year of experience."), "greenhouse", "Acme Robotics", "acme")
procs = []
try:
    data = os.path.join(TMP, "srv")
    os.makedirs(data)
    cache = {"_version": jobs_api.CACHE_VERSION}
    for kind, board, name in jobs_api.SOURCES:
        if kind in ("greenhouse", "lever"):
            cache["%s|%s|%s" % (kind, board, name)] = {"at": time.time(), "jobs": [], "status": "0 jobs"}
    cache["greenhouse|%s|%s" % SRC[1:]]["jobs"] = [POSTING, POSTING2]
    LSRC = [s_ for s_ in jobs_api.SOURCES if s_[0] == "lever"][0]
    LPOST = jobs_api._normalize(dict(id="posting-uuid-1", title="Lever Robotics Intern", company="Acme Lever", loc="Philadelphia, PA", remote=None,
                                     url="https://jobs.lever.co/acme/posting-uuid-1", salary_text="", posted=int(time.time()),
                                     text="Python and SQL. 1 year of experience."), "lever", "Acme Lever", "acme")
    cache["lever|%s|%s" % LSRC[1:]] = {"at": time.time(), "jobs": [LPOST], "status": "1 job"}
    json.dump(cache, open(os.path.join(data, "jobs-cache.json"), "w", encoding="utf-8"))
    procs.append(subprocess.Popen([sys.executable, os.path.join(HERE, "mock-ats.py"), str(MOCK)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    cfg = {"feeds": ["greenhouse", "lever"], "delivery": "live", "smtp": {}, "owner_copy": "", "google": {}, "daily_limit": 50, "grace_seconds": 0}
    env = dict(os.environ, UAPLY_DATA_DIR=data, UAPLY_CONFIG_JSON=json.dumps(cfg), UAPLY_SIGNUP_TEST="1", UAPLY_REQUEST_LOG="off",
               UAPLY_ATS_BASE_GREENHOUSE="http://127.0.0.1:%d" % MOCK, UAPLY_ATS_BASE_LEVER="http://127.0.0.1:%d" % MOCK)
    env.pop("RENDER", None)
    env.pop("UAPLY_ATS_JSON", None)
    procs.append(subprocess.Popen([sys.executable, "serve.py", str(PORT), "dev", "--api"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for _ in range(80):
        try:
            if req("GET", "/healthz")[0] == 200:
                break
        except OSError:
            time.sleep(0.25)
    s, out, ck = req("POST", "/api/auth/signup", {"email": "pat@example.org", "password": "pass for pat", "agree": True, "first": "Pat", "last": "Doe"})
    me = ck[0]
    req("POST", "/api/consent", {"version": consent_api.VERSION, "text": consent_api.full_text(False), "auto": False, "ticks": {"authorize": True, "accurate": True}}, me)
    job = [j for j in req("GET", "/api/jobs", cookie=me)[1]["jobs"] if j["role"] == "Robotics Intern"][0]
    t("before the employer connects, their posting is a hand-off", job.get("instant", False), False)
    t("only the owner makes a connect link (an unknown system is refused)", req("POST", "/api/setup/connect-invite", {"kind": "taleo", "board": "acme"})[0], 400)
    s, inv, _ = req("POST", "/api/setup/connect-invite", {"kind": "greenhouse", "board": "acme"})
    url = (inv or {}).get("url", "")
    t("the owner's link for the outreach email", (s, url.startswith("http://127.0.0.1:%d/employers/connect?k=greenhouse&b=acme&e=" % PORT)), (200, True))
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    t("a save with a tampered link is refused (a stranger cannot connect a board)", req("POST", "/api/employer/connect/save", dict(q, s="0" * 32, key="gh-secret-key-123", agree=True))[0], 403)
    t("...and so is one without the employer's agreement", req("POST", "/api/employer/connect/save", dict(q, key="gh-secret-key-123"))[1].get("ok"), False)
    o = subprocess.run(["node", os.path.join(HERE, "cdp.js"), os.path.join(HERE, "ui-connect.js")], cwd=ROOT, env=dict(os.environ, CONNECT_URL=url),
                       capture_output=True, text=True, encoding="utf-8", timeout=300)
    print(o.stdout.strip())
    t("the employer's walkthrough in the browser passed", o.returncode, 0)
    job = [j for j in req("GET", "/api/jobs", cookie=me)[1]["jobs"] if j["role"] == "Robotics Intern"][0]
    t("now their posting applies instantly", job.get("instant"), True)
    resume = {"name": "Pat Doe resume.pdf", "data": "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4 Pat Doe resume for the connect test %%EOF").decode()}
    s, out, _ = req("POST", "/api/apply", {"consent": True, "confirm_real": True, "match": 80, "job": {"id": job["id"], "co": job["co"], "role": job["role"], "url": job["url"]},
                                           "profile": {"name": "Pat Doe", "email": "pat@example.org", "ext": {"phone": "215-555-0188", "auth": "citizen", "sponsor": "no"}}, "resume": resume}, me)
    got = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/__received" % MOCK, timeout=10).read())
    gh = [g for g in got if g.get("system") == "greenhouse" and g.get("job") == "1001"]
    t("...and the next swipe right arrives in their Greenhouse as a new candidate", (s, out.get("status"), len(gh), (gh[0]["fields"].get("email") if gh else None)),
      (200, "sent", 1, "pat@example.org"))
    keyfile = os.path.join(data, "dev", "ats-connections.json")
    t("the key is kept in the server's own records folder, not in the employer list or a page", (os.path.exists(keyfile), "gh-secret-key-123" in json.dumps(req("GET", "/api/jobs", cookie=me)[1])),
      (True, False))

    def conn(kind):
        rows = json.load(open(keyfile, encoding="utf-8")).get("ats_connections") or []
        return [(c.get("status"), c.get("api_key")) for c in rows if c.get("kind") == kind and c.get("board") == "acme"]
    t("the Greenhouse key was pending until that send got through; now it is connected", conn("greenhouse"), [("connected", "gh-secret-key-123")])
    # one connect per link
    s, out, _ = req("POST", "/api/employer/connect/save", dict(q, key="gh-secret-key-123", agree=True))
    t("the same link a second time: 'already used, ask for a new link'", (s, "already used" in out.get("message", ""), "new link" in out.get("message", "")), (409, True, True))
    t("...and its page shows no form", ("This link was already used" in req("GET", urllib.parse.urlsplit(url).path + "?" + urllib.parse.urlsplit(url).query)[1]), True)
    # a new key never overwrites a working one
    q2 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(req("POST", "/api/setup/connect-invite", {"kind": "greenhouse", "board": "acme"})[1]["url"]).query))
    s, out, _ = req("POST", "/api/employer/connect/save", dict(q2, key="gh-someone-elses-key-999", agree=True))
    t("a fresh link with a different key: refused, the working key is kept", (s, conn("greenhouse")), (409, [("connected", "gh-secret-key-123")]))
    # the probe against a stand-in Lever API: a made-up key cannot be checked, so it stays pending, and a failed send never promotes it
    q3 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(req("POST", "/api/setup/connect-invite", {"kind": "lever", "board": "acme"})[1]["url"]).query))
    s, out, _ = req("POST", "/api/employer/connect/save", dict(q3, key="lever-made-up-key-000", agree=True))
    t("Lever, a made-up key: saved as pending, never 'Connected'", (s, out.get("pending"), out.get("message", "").startswith("Connected"), conn("lever")),
      (200, True, False, [("pending", "lever-made-up-key-000")]))
    lv = [j for j in req("GET", "/api/jobs", cookie=me)[1]["jobs"] if j["co"] == "Acme Lever"][0]
    s, out, _ = req("POST", "/api/apply", {"consent": True, "confirm_real": True, "match": 80, "job": {"id": lv["id"], "co": lv["co"], "role": lv["role"], "url": lv["url"]},
                                           "profile": {"name": "Pat Doe", "email": "pat@example.org", "ext": {"phone": "215-555-0188", "auth": "citizen", "sponsor": "no"}}, "resume": resume}, me)
    t("...Lever refuses the made-up key (401) on the first swipe: the key is dropped and the swipe is only saved, not failed", (out.get("status"), conn("lever")), ("handoff", []))
    lv = [j for j in req("GET", "/api/jobs", cookie=me)[1]["jobs"] if j["co"] == "Acme Lever"][0]
    t("...and that board's postings are hand-offs again", lv.get("instant", False), False)
    # a connected key that gets a 401 keeps today's behaviour: failed, and kept
    rows = json.load(open(keyfile, encoding="utf-8"))
    for c in rows["ats_connections"]:
        if c.get("kind") == "greenhouse":
            c["api_key"] = "gh-revoked-key-000"
    json.dump(rows, open(keyfile, "w", encoding="utf-8"))
    POST2 = [j for j in req("GET", "/api/jobs", cookie=me)[1]["jobs"] if j["role"] == "Controls Intern"][0]
    s, out, _ = req("POST", "/api/apply", {"consent": True, "confirm_real": True, "match": 80, "job": {"id": POST2["id"], "co": POST2["co"], "role": POST2["role"], "url": POST2["url"]},
                                           "profile": {"name": "Pat Doe", "email": "pat@example.org", "ext": {"phone": "215-555-0188", "auth": "citizen", "sponsor": "no"}}, "resume": resume}, me)
    t("a connected key refused (401): failed as today, and the key is kept", (out.get("status"), conn("greenhouse")), ("failed", [("connected", "gh-revoked-key-000")]))
finally:
    for p_ in procs:
        p_.terminate()
    for p_ in procs:
        try:
            p_.wait(10)
        except Exception:
            pass
    shutil.rmtree(TMP, ignore_errors=True)

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
