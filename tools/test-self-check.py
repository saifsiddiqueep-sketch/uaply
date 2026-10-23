"""The owner's self-check in /api/status (October 22, next to the outside uptime check in docs/uptime.md): when a job board was last read
successfully, when an email last went out, how much room the data disk has left, and plain warnings. Owner only. Starts its own
throwaway servers (a public one on PORT behind a pretend HTTPS proxy, a stand-in mail server on PORT+1, a second public one on PORT+2)
and stops them at the end:
  python tools/test-self-check.py [port]          (default 20460; uses that port and the next two)"""
import base64
import http.client
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20460
ADDR = "127.0.0.2"                     # counts as a public server, yet nobody else can reach it
TMP = tempfile.mkdtemp(prefix="uaply-selfcheck-")
R = []
PROCS = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


def req(method, path, body=None, owner=None, port=PORT):
    h = {"Host": "uaply.example", "X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.9", "Origin": "https://uaply.example"}
    if owner is not None:
        h["Authorization"] = "Basic " + base64.b64encode(("owner:" + owner).encode()).decode()
    if body is not None:
        h["Content-Type"] = "application/json"
    c = http.client.HTTPConnection(ADDR, port, timeout=30)
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    raw = r.read()
    c.close()
    try:
        return r.status, json.loads(raw)
    except ValueError:
        return r.status, {}


def start(port, data, extra=None):
    cfg = {"feeds": [], "owner_copy": "", "public_url": "https://uaply.example",
           "smtp": {"host": "127.0.0.1", "port": PORT + 1, "starttls": False, "from_addr": "uaply@example.com"}}
    env = dict(os.environ, HOST=ADDR, UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=data, OWNER_PASSWORD="ownerpw", UAPLY_CONFIG_JSON=json.dumps(cfg),
               UAPLY_CF_RANGES="0", UAPLY_DNS_CHECK="off", **(extra or {}))
    for k in ("ANTHROPIC_API_KEY", "UAPLY_FEEDS"):
        env.pop(k, None)
    PROCS.append(subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(port), "dev", "--api"], cwd=ROOT, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for _ in range(80):
        try:
            if req("GET", "/healthz", port=port)[0] == 200:
                return
        except OSError:
            time.sleep(0.25)
    raise SystemExit("the test server did not start")


try:
    # ---- the pieces, in this process ----
    os.environ.update(UAPLY_DATA_DIR=os.path.join(TMP, "unit"), UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}")
    os.makedirs(os.path.join(TMP, "unit"), exist_ok=True)
    import mailer  # noqa: E402
    import jobs_api  # noqa: E402
    mailer.init(os.path.join(TMP, "unit"))
    t("mail: nothing sent yet", mailer.last_sent(), 0)
    mailer._bump()
    t("mail: a sent email is remembered with its time", abs(mailer.last_sent() - time.time()) < 5, True)
    first = mailer.last_sent()
    mailer._bump(full=True)
    t("...a 'quota used up' answer is not a sent email (the time stays)", mailer.last_sent(), first)
    path = os.path.join(TMP, "unit", "mail-count.json")
    st = json.load(open(path, encoding="utf-8"))
    st.update(day="2000-01-01", sent=7)
    json.dump(st, open(path, "w", encoding="utf-8"))
    mailer._count_mem.clear()
    t("...and it is kept across days (and restarts: it is in mail-count.json)", (mailer.last_sent(), mailer.today()[0]), (first, 0))
    t("feeds: no board read yet", jobs_api.last_feed_ok(), 0)
    jobs_api._note_health(("greenhouse", "acme", "Acme"), False, error="HTTP 500")
    t("feeds: a failed read is not a refresh", jobs_api.last_feed_ok(), 0)
    jobs_api._note_health(("greenhouse", "acme", "Acme"), True, jobs=12)
    jobs_api._note_health(("lever", "beta", "Beta"), False, error="timeout")
    t("feeds: the last good read of any board", abs(jobs_api.last_feed_ok() - time.time()) < 5, True)

    # ---- over HTTP, as the live site runs ----
    PROCS.append(subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(PORT + 1), os.path.join(TMP, "fake-smtp.jsonl")],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    start(PORT, os.path.join(TMP, "a"))
    s, j = req("GET", "/api/status")
    t("a visitor's /api/status has no self-check", (s, "selfCheck" in j), (200, False))
    t("...nor does a wrong owner password", "selfCheck" in req("GET", "/api/status", owner="wrong")[1], False)
    s, j = req("GET", "/api/status", owner="ownerpw")
    sc = j.get("selfCheck") or {}
    t("the owner's /api/status has it: job boards, email, disk, warnings", sorted(sc), ["disk", "email", "feeds", "ok", "upMinutes", "warnings"])
    t("...the disk's free and total room in MB", isinstance(sc["disk"]["freeMB"], int) and sc["disk"]["freeMB"] > 0 and sc["disk"]["totalMB"] >= sc["disk"]["freeMB"]
      and 0 <= sc["disk"]["usedPercent"] <= 100, True)
    t("...job boards switched off here: nothing read, and no warning for that", (sc["feeds"], sc["warnings"], sc["ok"]),
      ({"on": False, "lastOk": None, "minutesAgo": None}, [], True))
    t("...email set up, nothing sent yet", sc["email"], {"on": True, "lastSent": None, "minutesAgo": None})
    flat = json.dumps(j)
    t("...no folder name, address or password in it", any(x in flat for x in (TMP, "ownerpw", "uaply@example.com", "127.0.0.1")), False)
    s, _ = req("POST", "/api/auth/signup", {"email": "self.check@example.com", "password": "self check 99", "agree": True})
    t("(a sign-up emails its code)", s, 200)
    for _ in range(40):
        sc = req("GET", "/api/status", owner="ownerpw")[1].get("selfCheck") or {}
        if sc.get("email", {}).get("lastSent"):
            break
        time.sleep(0.25)
    t("after an email goes out, the owner sees when (just now)", (bool(sc["email"]["lastSent"]), sc["email"]["minutesAgo"]), (True, 0))
    t("...and a visitor still sees none of it", "selfCheck" in req("GET", "/api/status")[1], False)
    # a data disk nearly full: a plain warning (here the threshold is raised above any real disk)
    start(PORT + 2, os.path.join(TMP, "b"), {"UAPLY_DISK_LOW_MB": "100000000"})
    sc = req("GET", "/api/status", owner="ownerpw", port=PORT + 2)[1].get("selfCheck") or {}
    t("a nearly full data disk is a plain warning, and the check is not ok", (sc.get("ok"), sc.get("warnings")),
      (False, ["Less than 100000000 MB free on the data disk."]))
finally:
    for p in PROCS:
        try:
            p.terminate()
            p.wait(10)
        except Exception:
            pass

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
