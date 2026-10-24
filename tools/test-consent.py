"""The consent record (Saif, October 23, 2026: no automatic send of any kind without it; consent_api.py). The box's words in
shared/uaply-live.js are word for word the ones the server keeps; POST /api/consent keeps the version, the time, the visitor's address and the
words' SHA-256 on the account; /api/auth/me shows it; nothing is sent to an employer without the current version on record; taking it back
stops the sends; the rows go with the account. In this process and over HTTP against a throwaway server it starts and stops (a stand-in mail
server keeps every message: nothing leaves this computer):
  python tools/test-consent.py [port]      (default 20475; uses that port and the next one)"""
import hashlib
import http.client
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20475
SMTP_PORT = PORT + 1
TMP = tempfile.mkdtemp(prefix="uaply-consent-")
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}", UAPLY_DATA_DIR=os.path.join(TMP, "unit"), UAPLY_DNS_CHECK="off")
R = []
PROCS = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


import auth_api  # noqa: E402
import consent_api  # noqa: E402

# ---------- the box's words are the server's words ----------
LIVE = open(os.path.join(ROOT, "shared", "uaply-live.js"), encoding="utf-8").read()
m_text = re.search(r"var CONSENT_TEXT=(\[.*?\]);\n", LIVE, re.S)
m_tail = re.search(r'var CONSENT_AUTO_TAIL=("(?:[^"\\]|\\.)*");', LIVE)
m_where = re.search(r"^\s*(function autoWhere\(cfg\)\{.*\})\s*$", LIVE, re.M)
m_at = re.search(r"AUTO_AT=(\d+);", LIVE)
m_v = re.search(r"var CONSENT_V=(\d+);", LIVE)
js_text = json.loads(m_text.group(1)) if m_text else []
t("the page's box version is the server's", int(m_v.group(1)) if m_v else None, consent_api.VERSION)
t("the box's paragraphs are word for word the server's", js_text, list(consent_api.TEXT))
t("...and the tick sits at the same place (after the four ways, above the last lines)", int(m_at.group(1)) if m_at else None, consent_api.AUTO_AT)
# the Automatic submit line: its "where" is built from shared/assist-systems.json on both sides; run the page's own autoWhere in node
SHIPPED = json.load(open(os.path.join(ROOT, "shared", "assist-systems.json"), encoding="utf-8"))
ON = {"systems": {"greenhouse": {"mode": "automatic", "counsel_approved": False, "human_check_share": 0},
                  "ashby": {"mode": "automatic", "counsel_approved": True, "human_check_share": 0},
                  "workable": {"mode": "automatic", "counsel_approved": True, "human_check_share": False},
                  "lever": {"mode": "automatic", "counsel_approved": True, "human_check_share": 0.0}, "other": {"mode": "automatic", "counsel_approved": True, "human_check_share": 0}}}
js_lines = []
if m_where and m_tail:
    prog = m_where.group(1) + "\nconst tail=" + m_tail.group(1) + ";\nconst cfgs=JSON.parse(process.argv[1]);\n" + \
        "console.log(JSON.stringify(cfgs.map(c=>'Automatic submit: '+autoWhere(c)+'.'+tail)));"
    out = subprocess.run(["node", "-e", prog, json.dumps([SHIPPED, ON, None])], capture_output=True, text=True, encoding="utf-8")
    js_lines = json.loads(out.stdout or "[]")
t("the Automatic submit line is the server's, built from the same systems file (as shipped, two switched on, and none read)", js_lines,
  [consent_api.auto_text(SHIPPED), consent_api.auto_text(ON), consent_api.auto_text({})])
t("...and while nothing is switched on it says so, not a system's name", consent_api.auto_text(SHIPPED).startswith("Automatic submit: where a hiring system allows it; none is switched on yet."), True)
t("...and once one is, it names it (only a system with the lawyer's approval and no human check measured)", "switched on now: Ashby, Lever." in consent_api.auto_text(ON), True)
js_auto = js_lines[0] if js_lines else ""
t("the words agreed to, as the page builds them, hash to the server's own (without and with the tick, the tick after the four ways)",
  (consent_api.digest("\n".join(js_text)), consent_api.digest("\n".join(js_text[:consent_api.AUTO_AT] + [js_auto] + js_text[consent_api.AUTO_AT:]))),
  (consent_api.digest(consent_api.full_text(False)), consent_api.digest(consent_api.full_text(True))))
t("the hash is the SHA-256 of the words, one paragraph per line", consent_api.digest("a  b\n\nc "), hashlib.sha256(b"a b\nc").hexdigest())
t("the box (version 5) says the authorization, the match line, the three ways plainly, how to stop it, and the tick",
  (consent_api.TEXT[0].startswith("A swipe right authorizes UAply to submit your application on your behalf"),
   consent_api.TEXT[1].startswith("The match percentage is worked out automatically") and consent_api.TEXT[1].endswith("How matching works"),
   consent_api.TEXT[2] == "A swipe right goes one of three ways:", consent_api.TEXT[3].startswith("Into the employer's own hiring system"),
   consent_api.TEXT[4].startswith("By email, with your resume"), consent_api.TEXT[5].startswith("Everywhere else, saved to Job Tracker with a receipt"),
   "turn off Send applications for me in Profile, Account" in consent_api.TEXT[8], consent_api.auto_text().startswith("Automatic submit:")), (True,) * 8)
t("the tick is off unless the person ticks it (the box's checkbox has no checked attribute)", bool(re.search(r'id="kcAuto"[^>]*checked', LIVE)), False)
TERMS = open(os.path.join(ROOT, "legal", "terms.html"), encoding="utf-8").read()
sub = [li for li in re.findall(r"<li>(.*?)</li>", TERMS, re.S) if "presses its Submit button for you" in li]
t("Terms section 3 matches the box: UAply presses Submit for you only with the person's Automatic submit setting turned on",
  (len(sub), bool(sub) and "only if you have turned on Automatic submit" in sub[0]), (1, True))

# ---------- in this process: the record on the account ----------
auth_api.init("consent")
s, out, tok, mail = auth_api.signup_with_code("rec.one@example.com", "record pass 1", "198.51.100.60", True, first="Rec", last="One", verified=True)
uid = out["user"]["id"]
t("no record before the person agrees", auth_api.consent_for(uid), None)
rec = auth_api.record_consent(uid, consent_api.VERSION, "198.51.100.60", consent_api.digest(consent_api.full_text(False)), False)
t("the record: the version, the time, and the tick", (rec["v"], abs(rec["at"] - time.time()) < 5, rec["auto"]), (consent_api.VERSION, True, False))
t("...current, so UAply may send; no automatic submit without the tick", (consent_api.current(rec), consent_api.auto_ok(rec)), (True, False))
db = sqlite3.connect(auth_api._path)
row = db.execute("SELECT version, ip, text_sha256, auto FROM consents WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
t("...kept on the account with the visitor's address and the words' SHA-256", row, (consent_api.VERSION, "198.51.100.60", consent_api.digest(consent_api.full_text(False)), 0))
auth_api.record_consent(uid, 3, "198.51.100.60", "x" * 64, False)
t("an earlier version on record is not current: UAply sends nothing", consent_api.current(auth_api.consent_for(uid)), False)
auth_api.record_consent(uid, 0, "198.51.100.60", "", False)
t("taking it back leaves no agreement on record", auth_api.consent_for(uid), None)
for i in range(30):
    auth_api.record_consent(uid, consent_api.VERSION, "198.51.100.%d" % (i % 250), "y" * 64, i % 2 == 0)
t("an account keeps at most its last %d agreements" % auth_api.CONSENT_ROWS, db.execute("SELECT COUNT(*) FROM consents WHERE user_id=?", (uid,)).fetchone()[0], auth_api.CONSENT_ROWS)
code, out_del, gone = auth_api.delete_account(tok, "record pass 1", "198.51.100.60")
t("deleting the account removes its agreements", (code, db.execute("SELECT COUNT(*) FROM consents WHERE user_id=?", (uid,)).fetchone()[0]), (200, 0))
db.close()


# ---------- over HTTP ----------
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


MAILS = os.path.join(TMP, "mail.jsonl")


def mails_to(addr):
    """The messages addressed to `addr` (by their recipients, not their words: a receipt names the employer's address too)."""
    try:
        rows = [json.loads(x) for x in open(MAILS, encoding="utf-8") if x.strip()]
    except (OSError, ValueError):
        return []
    return [m for m in rows if addr in [str(r).lower() for r in (m.get("to") or [])]]


def account(email, verify=True):
    s, out, ck = req(PORT, "POST", "/api/auth/signup", {"email": email, "password": "pass for " + email, "agree": True, "first": "Con", "last": "Sent"})
    cookie = ck[0] if ck else ""
    if verify:
        code = ""
        for _ in range(60):
            hits = [re.search(r"([0-9]{6}) is your UAply verification code", x.get("raw", "")) for x in mails_to(email)]
            hits = [h for h in hits if h]
            if hits:
                code = hits[-1].group(1)
                break
            time.sleep(0.1)
        req(PORT, "POST", "/api/auth/verify", {"code": code}, cookie)
    return cookie


def apply(cookie, email, job):
    return req(PORT, "POST", "/api/apply", {"consent": True, "confirm_real": True, "job": job,
                                            "profile": {"name": "Con Sent", "email": email, "ext": {"phone": "215-555-0101"}}}, cookie)[:2]


def partner_job(co, role):
    return {"id": 200000 + int(hashlib.sha1(("partner:%s:%s" % (co, role)).encode()).hexdigest()[:6], 16), "co": co, "role": role,
            "url": "https://mailco.example/jobs", "contact": "hr@mailco.example"}


try:
    PROCS.append(subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(SMTP_PORT), MAILS], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    data = os.path.join(TMP, "live")
    os.makedirs(data, exist_ok=True)
    with open(os.path.join(data, "uaply-partners.json"), "w", encoding="utf-8") as f:
        json.dump({"employers": [{"name": "Mail Co", "consent": "test partner agreement", "contact": "hr@mailco.example", "url": "https://mailco.example/jobs",
                                  "jobs": [{"role": "Marketing Intern", "skills": ["SEO"], "loc": "Philadelphia, PA"},
                                           {"role": "Sales Intern", "skills": ["SEO"], "loc": "Philadelphia, PA"},
                                           {"role": "Design Intern", "skills": ["SEO"], "loc": "Philadelphia, PA"}]},
                                 {"name": "Hook Co", "consent": "test partner agreement", "url": "https://hookco.example/jobs", "webhook": "http://127.0.0.1:9/uaply-hook",
                                  "webhook_secret": "test-hook-secret", "jobs": [{"role": "Hook Intern", "skills": ["SEO"], "loc": "Philadelphia, PA"}]}]}, f)
    cfg = {"feeds": [], "delivery": "live", "owner_copy": "", "google": {}, "grace_seconds": 0, "daily_limit": 50,
           "smtp": {"host": "127.0.0.1", "port": SMTP_PORT, "starttls": False, "from_addr": "apply@uaply.example"}}
    env = dict(os.environ, UAPLY_DATA_DIR=data, UAPLY_CONFIG_JSON=json.dumps(cfg), UAPLY_DNS_CHECK="off", UAPLY_REQUEST_LOG="off", UAPLY_ALLOW_LOCAL_WEBHOOK="1")
    for k in ("UAPLY_SIGNUP_TEST", "RENDER", "OWNER_PASSWORD"):
        env.pop(k, None)
    PROCS.append(subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(PORT), "dev", "--api"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for _ in range(80):
        try:
            if req(PORT, "GET", "/healthz")[0] == 200:
                break
        except OSError:
            time.sleep(0.25)
    good = {"version": consent_api.VERSION, "text": consent_api.full_text(False), "auto": False}
    t("signed out, POST /api/consent answers 401 signin", req(PORT, "POST", "/api/consent", good)[:2][0], 401)
    unv = account("unverified@example.com", verify=False)
    t("...an account whose address is not confirmed answers 403 verify", req(PORT, "POST", "/api/consent", good, unv)[1].get("code"), "verify")
    ck = account("person@example.com")
    t("an earlier version is refused (409 consent_old: the page is out of date)", req(PORT, "POST", "/api/consent", dict(good, version=3), ck)[:2],
      (409, {"error": "This page is out of date. Reload UAply and agree to the current terms.", "code": "consent_old"}))
    t("words other than the server's are refused (409 consent_text)", req(PORT, "POST", "/api/consent", dict(good, text=good["text"] + " And more."), ck)[1].get("code"), "consent_text")
    t("...and so is the tick claimed without its words", req(PORT, "POST", "/api/consent", dict(good, auto=True), ck)[1].get("code"), "consent_text")
    job1, job2 = partner_job("Mail Co", "Marketing Intern"), partner_job("Mail Co", "Sales Intern")
    s, out = apply(ck, "person@example.com", job1)
    t("with no agreement on record, nothing is sent to the employer (403 consent)", (s, out.get("code"), len(mails_to("hr@mailco.example"))), (403, "consent", 0))
    s, out, _ = req(PORT, "POST", "/api/consent", good, ck)
    t("the box's words are kept: 200 with the record", (s, (out.get("consent") or {}).get("v"), (out.get("consent") or {}).get("auto")), (200, consent_api.VERSION, False))
    me = req(PORT, "GET", "/api/auth/me", cookie=ck)[1].get("user") or {}
    t("/api/auth/me shows the agreement on record", ((me.get("consent") or {}).get("v"), (me.get("consent") or {}).get("auto"), isinstance((me.get("consent") or {}).get("at"), int)),
      (consent_api.VERSION, False, True))
    db = sqlite3.connect(os.path.join(data, "dev", "uaply.db"))
    row = db.execute("SELECT c.version, c.ip, c.text_sha256, c.auto FROM consents c JOIN users u ON u.id=c.user_id WHERE u.email=? ORDER BY c.id DESC LIMIT 1",
                     ("person@example.com",)).fetchone()
    t("...with the visitor's address (the last hop) and the words' SHA-256", row, (consent_api.VERSION, "127.0.0.1", consent_api.digest(consent_api.full_text(False)), 0))
    s, out = apply(ck, "person@example.com", job1)
    t("now the swipe right is sent", (s, out.get("status")), (200, "sent"))
    s, out, _ = req(PORT, "POST", "/api/consent", {"version": consent_api.VERSION, "text": consent_api.full_text(True), "auto": True}, ck)
    t("agreeing with the Automatic submit tick is kept as such", (s, (out.get("consent") or {}).get("auto"), ((req(PORT, "GET", "/api/auth/me", cookie=ck)[1].get("user") or {}).get("consent") or {}).get("auto")),
      (200, True, True))
    s, out, _ = req(PORT, "POST", "/api/consent", {"withdraw": True}, ck)
    t("taking it back: no agreement on record", (s, (req(PORT, "GET", "/api/auth/me", cookie=ck)[1].get("user") or {}).get("consent")), (200, None))
    n = len(mails_to("hr@mailco.example"))
    s, out = apply(ck, "person@example.com", job2)
    t("...and nothing more is sent for this person", (s, out.get("code"), len(mails_to("hr@mailco.example"))), (403, "consent", n))
    # ---------- Send applications for me (Profile, Account; Terms section 3): off, every swipe right only saves the job ----------
    t("the switch needs a session", req(PORT, "POST", "/api/auth/send-for-me", {"on": False})[0], 401)
    t("...and a plain on or off", req(PORT, "POST", "/api/auth/send-for-me", {"on": "no"}, ck)[0], 400)
    me = req(PORT, "GET", "/api/auth/me", cookie=ck)[1].get("user") or {}
    t("Send applications for me is on unless the person turns it off", me.get("sendForMe"), True)
    req(PORT, "POST", "/api/consent", good, ck)                       # agreed again, so only the switch decides
    s, out, _ = req(PORT, "POST", "/api/auth/send-for-me", {"on": False}, ck)
    t("turning it off is kept on the account", (s, out.get("sendForMe"), (req(PORT, "GET", "/api/auth/me", cookie=ck)[1].get("user") or {}).get("sendForMe")), (200, False, False))
    n = len(mails_to("hr@mailco.example"))
    s, out = apply(ck, "person@example.com", job2)
    t("...then a swipe right only saves the job (a hand-off), and the employer gets nothing", (s, out.get("status"), out.get("sendForMe"), len(mails_to("hr@mailco.example"))),
      (200, "handoff", False, n))
    job3 = partner_job("Mail Co", "Design Intern")
    s, out = req(PORT, "POST", "/api/apply/plan", {"plan_only": True, "job": job3, "profile": {"name": "Con Sent", "email": "person@example.com"}}, ck)[:2]
    t("...and the card says it would only be saved", out.get("status"), "handoff")
    hook = dict(partner_job("Hook Co", "Hook Intern"), url="https://hookco.example/jobs", contact="")
    s, out = apply(ck, "person@example.com", hook)
    t("...an employer's webhook too: only saved, nothing is posted to it (with the switch on the same swipe tries the webhook)",
      (s, out.get("status"), out.get("sendForMe")), (200, "handoff", False))
    s, out, _ = req(PORT, "POST", "/api/auth/send-for-me", {"on": True}, ck)
    s, out = apply(ck, "person@example.com", job3)
    t("turned on again, a swipe right is sent", (s, out.get("status"), len(mails_to("hr@mailco.example"))), (200, "sent", n + 1))
    ck2 = account("hookcheck@example.com")
    req(PORT, "POST", "/api/consent", good, ck2)
    s, out = apply(ck2, "hookcheck@example.com", hook)
    t("...and with it on, the webhook route is tried (nothing listens on this test address, so it fails: proof it was not skipped)", (s, out.get("status")), (200, "failed"))
    db.close()
finally:
    for p in PROCS:
        try:
            p.terminate()
            p.wait(10)
        except Exception:
            pass
    shutil.rmtree(TMP, ignore_errors=True)

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
