"""Card 200: the owner's switch require_auto_consent (off unless the owner sets it to true). When on, UAply itself sends nothing (email, Recruitee,
an employer's hiring system or webhook) unless the person's current consent record also has Automatic submit (consent_api.auto_ok); the swipe is
then a hand-off, kept as one, never counted as sent. When off, the rule of today stands (consent_api.current is enough).
Against a stand-in Recruitee server and throwaway UAply servers it starts and stops (nothing leaves this computer):
  python tools/test-consent-gate.py [port]      (default: three free ports in a row)"""
import http.client
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import base64

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def _free_base(n=3):
    for base in range(31000, 60000, 7):
        try:
            socks = []
            for k in range(n):
                s_ = socket.socket()
                s_.bind(("127.0.0.1", base + k))
                socks.append(s_)
            for s_ in socks:
                s_.close()
            return base
        except OSError:
            for s_ in socks:
                s_.close()
    return 20460


PORT = int(sys.argv[1]) if len(sys.argv) > 1 else _free_base()
FAKE, PORT2 = PORT + 1, PORT + 2
TMP = tempfile.mkdtemp(prefix="uaply-consent-gate-")
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}", UAPLY_DATA_DIR=os.path.join(TMP, "unit"), UAPLY_DNS_CHECK="off")
R, PROCS = [], []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


import jobs_api  # noqa: E402
import consent_api  # noqa: E402

# ---------- a stand-in Recruitee careers site ----------
GOT = []


TUNNELS = []      # hosts a test server tried to reach through this stand-in as its HTTPS proxy (the real-site trap below)


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_CONNECT(self):
        TUNNELS.append(self.path.split(":")[0])
        self.send_response(403); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("latin-1")
        m = re.match(r"^/([a-z0-9-]+)/api/offers/([a-z0-9-]+)/candidates$", self.path)
        if not m:
            self.send_response(404); self.end_headers(); return
        fields = dict(re.findall(r'name="(candidate\[[a-z]+\])"\r\n\r\n([^\r]*)\r\n', body))
        cv = re.search(r'name="candidate\[cv\]"; filename="([^"]+)"', body)
        GOT.append({"company": m.group(1), "slug": m.group(2), "fields": fields, "cv": cv.group(1) if cv else "", "type": self.headers.get("Content-Type", "")})
        if m.group(2) == "broken-role":
            self.send_response(500); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b'{"error":"down"}'); return
        self.send_response(201); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"candidate": {"id": len(GOT)}}).encode())


fake = http.server.ThreadingHTTPServer(("127.0.0.1", FAKE), Fake)
threading.Thread(target=fake.serve_forever, daemon=True).start()

SRC = [s for s in jobs_api.SOURCES if s[0] == "recruitee"][0]


def offer(oid, slug, title):
    raw = jobs_api._recruitee_raw({"id": oid, "title": title, "slug": slug, "status": "published", "description": "Python and SQL. Build data tools with the team. 1 year of experience.",
                                   "locations": [{"country_code": "US", "city": "Philadelphia", "state_code": "PA"}], "careers_url": "https://%s.recruitee.com/o/%s" % (SRC[1], slug)}, SRC[2])
    return jobs_api._normalize(raw, "recruitee", SRC[2], SRC[1])


P1, P2, P3, P4 = offer(901, "data-analyst", "Data Analyst"), offer(902, "broken-role", "Data Engineer"), offer(903, "data-intern", "Data Intern"), offer(904, "data-lead", "Data Lead")
P5 = offer(905, "data-scientist", "Data Scientist")
P5 = dict(P5, ats=dict(P5["ats"], id="Bad Slug!"))     # an offer slug recruitee_url refuses
def seed(data):
    os.makedirs(data, exist_ok=True)
    cache = {"_version": jobs_api.CACHE_VERSION}
    for kind, board, name in jobs_api.SOURCES:
        if kind == "recruitee":
            cache["%s|%s|%s" % (kind, board, name)] = {"at": time.time(), "jobs": [], "status": "0 jobs"}
    cache["recruitee|%s|%s" % SRC[1:]]["jobs"] = [P1, P2, P3, P4, P5]
    with open(os.path.join(data, "jobs-cache.json"), "w", encoding="utf-8") as f:
        json.dump(cache, f)


def req(port, method, path, body=None, cookie=""):
    h = {"Host": "127.0.0.1:%d" % port, "Origin": "http://127.0.0.1:%d" % port}
    if cookie:
        h["Cookie"] = cookie
    if body is not None:
        h["Content-Type"] = "application/json"
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    raw = r.read()
    ck = [v.split(";", 1)[0] for k, v in r.getheaders() if k.lower() == "set-cookie"]
    c.close()
    try:
        return r.status, json.loads(raw), ck
    except ValueError:
        return r.status, raw.decode("utf-8", "replace"), ck


def start(port, name, cfg, stand_in=True):
    data = os.path.join(TMP, name)
    seed(data)
    env = dict(os.environ, UAPLY_DATA_DIR=data, UAPLY_CONFIG_JSON=json.dumps(cfg), UAPLY_SIGNUP_TEST="1", UAPLY_REQUEST_LOG="off",
               UAPLY_ATS_BASE_RECRUITEE="http://127.0.0.1:%d" % FAKE)
    if not stand_in:                     # the real careers site's address
        env.pop("UAPLY_ATS_BASE_RECRUITEE")
    env.pop("RENDER", None)
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(port), "dev", "--api"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PROCS.append(p)
    for _ in range(80):
        try:
            if req(port, "GET", "/healthz")[0] == 200:
                return p
        except OSError:
            time.sleep(0.25)
    raise SystemExit("a test server did not start")


def person(port, email, consent=True):
    s, out, ck = req(port, "POST", "/api/auth/signup", {"email": email, "password": "pass for " + email, "agree": True, "first": "Rae", "last": "Cruz"})
    cookie = ck[0] if ck else ""
    if consent:
        req(port, "POST", "/api/consent", {"version": consent_api.VERSION, "text": consent_api.full_text(False), "auto": False, "ticks": {"authorize": True, "accurate": True}}, cookie)
    return cookie


RESUME = {"name": "Rae Cruz resume.pdf", "data": "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4 Rae Cruz resume for the Recruitee test %%EOF").decode()}


def apply(port, ck, job, email):
    return req(port, "POST", "/api/apply", {"consent": True, "confirm_real": True, "match": 70, "job": {"id": job["id"], "co": job["co"], "role": job["role"], "url": job["url"]},
                                            "profile": {"name": "Rae Cruz", "email": email, "ext": {"phone": "215-555-0177"}}, "resume": RESUME}, ck)[:2]


def agree(port, ck, auto):
    return req(port, "POST", "/api/consent", {"version": consent_api.VERSION, "text": consent_api.full_text(auto), "auto": auto,
                                              "ticks": {"authorize": True, "accurate": True}}, ck)[0]


def plan(port, ck, job, email):
    return req(port, "POST", "/api/apply/plan", {"plan_only": True, "job": {"id": job["id"], "co": job["co"], "role": job["role"], "url": job["url"]},
                                                 "profile": {"name": "Rae Cruz", "email": email}}, ck)[1].get("status")


def stop():
    for p in PROCS:
        p.terminate()
        p.wait(10)
    PROCS.clear()


def sent_count(port, email):
    s, ob, _ = req(port, "GET", "/api/outbox")
    return sorted(x.get("status") for x in ob.get("applications", []) if (x.get("candidate") or {}).get("email") == email)


try:
    t("auto_ok needs the current version and the Automatic submit tick", (consent_api.auto_ok({"v": consent_api.VERSION, "auto": True}),
      consent_api.auto_ok({"v": consent_api.VERSION, "auto": False}), consent_api.auto_ok({"v": consent_api.VERSION}),
      consent_api.auto_ok({"v": consent_api.VERSION - 1, "auto": True}), consent_api.auto_ok(None)), (True, False, False, False, False))
    live = {"feeds": ["recruitee"], "delivery": "live", "smtp": {}, "owner_copy": "", "daily_limit": 50, "google": {}, "grace_seconds": 0, "recruitee_submit": True}

    # ---- switch off (today): the authorization tick alone lets UAply send ----
    start(PORT, "off", live)
    a = person(PORT, "rae@example.org")
    s, out = apply(PORT, a, P1, "rae@example.org")
    t("switch off, Automatic submit not ticked: sent, as today", (s, out.get("status"), len(GOT)), (200, "sent", 1))
    stop()

    # ---- switch on ----
    on = dict(live, require_auto_consent=True)
    start(PORT2, "on", on)
    nc = person(PORT2, "none@example.org", consent=False)
    s, out = apply(PORT2, nc, P1, "none@example.org")
    t("switch on, no agreement on record: 403 consent, nothing sent", (s, out.get("code"), len(GOT)), (403, "consent", 1))

    b = person(PORT2, "bea@example.org")                     # agreed, Automatic submit not ticked
    t("switch on, Automatic submit not ticked: the card's plan says hand-off", plan(PORT2, b, P1, "bea@example.org"), "handoff")
    s, out = apply(PORT2, b, P1, "bea@example.org")
    t("...a swipe right is a hand-off, nothing reaches Recruitee", (s, out.get("status"), out.get("why"), len(GOT)), (200, "handoff", "auto_off", 1))
    s, out = apply(PORT2, b, P1, "bea@example.org")
    t("...swiping again (a retry) is the same hand-off, still nothing sent", (out.get("status"), out.get("was"), len(GOT)), ("duplicate", "handoff", 1))
    t("...the record keeps it as a hand-off, never as sent", sent_count(PORT2, "bea@example.org"), ["handoff"])

    c = person(PORT2, "cam@example.org", consent=False)
    t("(Cam agrees with Automatic submit ticked)", agree(PORT2, c, True), 200)
    s, out = apply(PORT2, c, P1, "cam@example.org")
    t("switch on, Automatic submit ticked: sent through Recruitee", (out.get("status"), len(GOT)), ("sent", 2))
    s, out = apply(PORT2, c, P2, "cam@example.org")
    t("...Recruitee refusing one: failed (a retry may send again)", (out.get("status"), len(GOT)), ("failed", 3))
    t("(Cam agrees again, Automatic submit now not ticked)", agree(PORT2, c, False), 200)
    s, out = apply(PORT2, c, P2, "cam@example.org")
    t("...the retry of the failed one is a hand-off now, nothing sent", (out.get("status"), out.get("why"), len(GOT)), ("handoff", "auto_off", 3))
    t("(Cam agrees again with Automatic submit ticked, then takes the agreement back)",
      (agree(PORT2, c, True), req(PORT2, "POST", "/api/consent", {"withdraw": True}, c)[0]), (200, 200))
    s, out = apply(PORT2, c, P3, "cam@example.org")
    t("...agreement withdrawn: 403 consent, nothing sent", (s, out.get("code"), len(GOT)), (403, "consent", 3))

    d = person(PORT2, "dee@example.org", consent=False)
    agree(PORT2, d, True)
    req(PORT2, "POST", "/api/auth/send-for-me", {"on": False}, d)
    s, out = apply(PORT2, d, P4, "dee@example.org")
    t("switch on, Automatic submit ticked but Send applications for me off: only saved, as before", (out.get("status"), out.get("sendForMe"), len(GOT)), ("handoff", False, 3))
    stop()

    # ---- a value that is not exactly true leaves the switch off ----
    start(PORT2, "str", dict(live, require_auto_consent="true"))
    e = person(PORT2, "eli@example.org")
    t("require_auto_consent \"true\" (a string, not true): off, sent as today", (apply(PORT2, e, P3, "eli@example.org")[1].get("status"), len(GOT)), ("sent", 4))
    stop()
finally:
    for p in PROCS:
        try:
            p.terminate()
            p.wait(10)
        except Exception:
            pass
    fake.shutdown()
    shutil.rmtree(TMP, ignore_errors=True)

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
