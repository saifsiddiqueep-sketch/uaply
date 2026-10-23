"""Swipe phase B, Recruitee (October 23, 2026): a posting on a Recruitee careers site takes the application through the site's own public
apply endpoint (POST https://{company}.recruitee.com/api/offers/{slug}/candidates, no employer key), behind the owner's switch
recruitee_submit (default on), with the consent record, Send applications for me, the receipt and Job Tracker as for any hiring-system send.
Against a stand-in Recruitee server and throwaway UAply servers it starts and stops (nothing leaves this computer):
  python tools/test-recruitee.py [port]      (default: three free ports in a row)"""
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
TMP = tempfile.mkdtemp(prefix="uaply-recruitee-")
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}", UAPLY_DATA_DIR=os.path.join(TMP, "unit"), UAPLY_DNS_CHECK="off")
R, PROCS = [], []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


import ats_api  # noqa: E402
import jobs_api  # noqa: E402
import consent_api  # noqa: E402

t("the apply address is the careers site's own endpoint", ats_api.recruitee_url("curotec", "data-analyst"), "http://127.0.0.1:%d/curotec/api/offers/data-analyst/candidates" % FAKE
  if os.environ.get("UAPLY_ATS_BASE_RECRUITEE") else "https://curotec.recruitee.com/api/offers/data-analyst/candidates")
t("...and nothing for a company or slug that is not a plain name", (ats_api.recruitee_url("cu/rotec", "x"), ats_api.recruitee_url("curotec", "../x")), ("", ""))

# ---------- a stand-in Recruitee careers site ----------
GOT = []


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

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
t("a Recruitee posting carries its company and offer slug as the hiring system it lives in", P1["ats"], {"kind": "recruitee", "board": SRC[1], "id": "data-analyst"})


def seed(data):
    os.makedirs(data, exist_ok=True)
    cache = {"_version": jobs_api.CACHE_VERSION}
    for kind, board, name in jobs_api.SOURCES:
        if kind == "recruitee":
            cache["%s|%s|%s" % (kind, board, name)] = {"at": time.time(), "jobs": [], "status": "0 jobs"}
    cache["recruitee|%s|%s" % SRC[1:]]["jobs"] = [P1, P2, P3, P4]
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


def start(port, name, cfg):
    data = os.path.join(TMP, name)
    seed(data)
    env = dict(os.environ, UAPLY_DATA_DIR=data, UAPLY_CONFIG_JSON=json.dumps(cfg), UAPLY_SIGNUP_TEST="1", UAPLY_REQUEST_LOG="off",
               UAPLY_ATS_BASE_RECRUITEE="http://127.0.0.1:%d" % FAKE)
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
        req(port, "POST", "/api/consent", {"version": consent_api.VERSION, "text": consent_api.full_text(False), "auto": False}, cookie)
    return cookie


RESUME = {"name": "Rae Cruz resume.pdf", "data": "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4 Rae Cruz resume for the Recruitee test %%EOF").decode()}


def apply(port, ck, job, email):
    return req(port, "POST", "/api/apply", {"consent": True, "confirm_real": True, "match": 70, "job": {"id": job["id"], "co": job["co"], "role": job["role"], "url": job["url"]},
                                            "profile": {"name": "Rae Cruz", "email": email, "ext": {"phone": "215-555-0177"}}, "resume": RESUME}, ck)[:2]


try:
    os.environ["UAPLY_ATS_BASE_RECRUITEE"] = "http://127.0.0.1:%d" % FAKE
    t("(with the stand-in's address set, the endpoint goes to it)", ats_api.recruitee_url("curotec", "data-analyst"), "http://127.0.0.1:%d/curotec/api/offers/data-analyst/candidates" % FAKE)
    live = {"feeds": ["recruitee"], "delivery": "live", "smtp": {}, "owner_copy": "", "daily_limit": 50, "google": {}, "grace_seconds": 0}
    start(PORT, "live", live)
    a = person(PORT, "rae@example.org")
    by = {j["id"]: j for j in req(PORT, "GET", "/api/jobs", cookie=a)[1]["jobs"]}
    t("the card says Ready and applies instantly (the switch is on by default)", ((by.get(P1["id"]) or {}).get("instant"), (by.get(P1["id"]) or {}).get("route")), (True, "Ready"))
    t("the card's plan says ready", req(PORT, "POST", "/api/apply/plan", {"plan_only": True, "job": {"id": P1["id"], "co": P1["co"], "role": P1["role"], "url": P1["url"]},
                                                                         "profile": {"name": "Rae Cruz", "email": "rae@example.org"}}, a)[1].get("status"), "ready")
    nc = person(PORT, "noconsent@example.org", consent=False)
    s, out = apply(PORT, nc, P1, "noconsent@example.org")
    t("no agreement on record: nothing is sent (403 consent)", (s, out.get("code"), len(GOT)), (403, "consent", 0))
    s, out = apply(PORT, a, P1, "rae@example.org")
    t("a swipe right is sent through Recruitee's apply endpoint", (s, out.get("status"), out.get("to")), (200, "sent", "%s on Recruitee" % P1["co"]))
    g = GOT[-1] if GOT else {}
    t("...to this offer, as one multipart form", (len(GOT), g.get("company"), g.get("slug"), g.get("type", "").startswith("multipart/form-data")), (1, SRC[1], "data-analyst", True))
    t("...with the name, email, phone and the resume file", (g.get("fields", {}).get("candidate[name]"), g.get("fields", {}).get("candidate[email]"), g.get("fields", {}).get("candidate[phone]"), g.get("cv")),
      ("Rae Cruz", "rae@example.org", "215-555-0177", "Rae Cruz resume.pdf"))
    t("...and nothing else (no voluntary answer, no message)", sorted(g.get("fields", {})), ["candidate[email]", "candidate[name]", "candidate[phone]"])
    t("swiping right again is the same application, not a second one", (apply(PORT, a, P1, "rae@example.org")[1].get("status"), len(GOT)), ("duplicate", 1))
    s, out = apply(PORT, a, P2, "rae@example.org")
    t("Recruitee refusing it: the swipe says not sent (Job Tracker offers Try again)", (out.get("status"), len(GOT)), ("failed", 2))
    req(PORT, "POST", "/api/auth/send-for-me", {"on": False}, a)
    s, out = apply(PORT, a, P3, "rae@example.org")
    t("Send applications for me off: only saved, nothing reaches Recruitee", (out.get("status"), out.get("sendForMe"), len(GOT)), ("handoff", False, 2))
    req(PORT, "POST", "/api/auth/send-for-me", {"on": True}, a)
    s, ob, _ = req(PORT, "GET", "/api/outbox")
    rec = [x for x in ob.get("applications", []) if x.get("job", {}).get("id") == P1["id"]]
    t("the record says where it went (the hiring system channel)", (rec[0].get("status"), rec[0].get("channels")) if rec else None, ("sent", ["hiring system"]))
    for p in PROCS:
        p.terminate()
        p.wait(10)
    PROCS.clear()
    # the owner's switch off: Recruitee postings are hand-offs again
    start(PORT2, "off", dict(live, recruitee_submit=False))
    b = person(PORT2, "bea@example.org")
    by = {j["id"]: j for j in req(PORT2, "GET", "/api/jobs", cookie=b)[1]["jobs"]}
    s, out = apply(PORT2, b, P4, "bea@example.org")
    t("recruitee_submit false: the card is a hand-off and a swipe sends nothing", ((by.get(P4["id"]) or {}).get("instant", False), out.get("status"), len(GOT)), (False, "handoff", 2))
    for p in PROCS:
        p.terminate()
        p.wait(10)
    PROCS.clear()
    # test delivery: what the live app would do, nothing reaches Recruitee
    start(PORT2, "test", dict(live, delivery="test"))
    c = person(PORT2, "cam@example.org")
    s, out = apply(PORT2, c, P4, "cam@example.org")
    t("test delivery: simulated, nothing reaches Recruitee", (out.get("status"), out.get("to"), len(GOT)), ("delivered_test", "%s on Recruitee (simulated)" % P4["co"], 2))
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
