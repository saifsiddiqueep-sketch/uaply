"""Canada's server groundwork (legal_ca.py), switched off by default, and the US first-swipe agreement unchanged by it. In this process and
over HTTP against two throwaway servers it starts and stops (CANADA_ENABLED off and on; nothing leaves this computer):
  python tools/test-canada-legal.py [port]      (default 18990; uses that port and the next one)
  (a) the US words: legal/, consent_api.py and shared/ as on origin/sandbox (while on this card's c190- branch), and the agreement's text
      hashes to the same values as before
  (b) switched off: /api/legal/region, /api/legal/accept and /api/legal/quebec-waitlist answer 404 like an unknown address; region() is US
      for everyone; docs/legal-drafts is never served
  (c) switched on: an acceptance is kept on the ledger; a new country or version asks again; Quebec is QC; the waitlist takes an address only
      with optin exactly true and keeps only the address, the time and the words' version; the questions left to the person
  (d) POST /api/consent still keeps the consents row and answers as before (and writes one first-swipe row on the ledger)"""
import hashlib
import http.client
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18990
TMP = tempfile.mkdtemp(prefix="uaply-canada-")
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}", UAPLY_DATA_DIR=os.path.join(TMP, "unit"), UAPLY_DNS_CHECK="off")
os.environ.pop("CANADA_ENABLED", None)
R = []
PROCS = []

# the first-swipe agreement's words as on sandbox before Canada (SHA-256 of consent_api.full_text(False) and full_text(True), October 30)
US_TEXT_SHA = "4e65e65c0b1a3802dd11959705ac19ce25ba2652a7b368577c4d92bc38158324"
US_TEXT_AUTO_SHA = "e0ca5f7bfd8f4b5a0ba69f6c9c21f8a7fbb606cf57f1d9f4b6c8061a2b620427"


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


import auth_api  # noqa: E402
import consent_api  # noqa: E402
import legal_ca  # noqa: E402

# ---------- (a) the US words are byte for byte the same ----------
branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
if branch.startswith("c190-"):        # this card's own branch: later branches change shared/ on purpose, so the check belongs to this one
    base = "origin/sandbox" if subprocess.run(["git", "rev-parse", "--verify", "-q", "origin/sandbox"], cwd=ROOT, capture_output=True).returncode == 0 else "sandbox"
    same = subprocess.run(["git", "diff", "--quiet", base, "--", "legal/", "consent_api.py", "shared/"], cwd=ROOT, capture_output=True).returncode
    t("legal/, consent_api.py and shared/ are as on %s (git diff --quiet)" % base, same, 0)
t("the first-swipe words hash as before (without the Automatic submit line)", hashlib.sha256(consent_api.full_text(False).encode("utf-8")).hexdigest(), US_TEXT_SHA)
t("...and with it", hashlib.sha256(consent_api.full_text(True).encode("utf-8")).hexdigest(), US_TEXT_AUTO_SHA)
t("...and the version is still 6", consent_api.VERSION, 6)

# ---------- (b) switched off, in this process ----------
t("switched off unless CANADA_ENABLED is set", legal_ca.enabled(), False)
for v in ("0", "false", "no", "", "on"):
    os.environ["CANADA_ENABLED"] = v
    if legal_ca.enabled():
        t("CANADA_ENABLED=%r switches nothing on" % v, True, False)
os.environ.pop("CANADA_ENABLED", None)
t("switched off: region() is US with nothing to confirm, whatever the profile or the address says",
  [legal_ca.region(*a) for a in (("CA", "QC"), ("Canada", "ON", "CA", "ON"), ("US", "", "CA", "QC"), ("", ""))], [{"region": "US", "confirm": False}] * 4)

# ---------- (c) switched on, in this process ----------
os.environ["CANADA_ENABLED"] = "1"
t("CANADA_ENABLED=1 switches it on (read at each call)", legal_ca.enabled(), True)
for v in ("true", "YES", " yes "):
    os.environ["CANADA_ENABLED"] = v
    t("...and so does %r" % v, legal_ca.enabled(), True)
reg = legal_ca.region
t("no country in the profile: US", reg("", ""), {"region": "US", "confirm": False})
t("Canada, Ontario: CA", reg("Canada", "ON"), {"region": "CA", "confirm": False})
t("a province with no country means Canada", reg("", "british columbia"), {"region": "CA", "confirm": False})
t("Quebec in the profile: QC (code or name, with or without the accent)", [reg("CA", "QC"), reg("ca", "Québec"), reg("Canada", "quebec")], [{"region": "QC", "confirm": False}] * 3)
t("the address never decides the country: a US profile from a Canadian address stays US, and asks to confirm", reg("US", "", "CA", "ON"), {"region": "US", "confirm": True})
t("a Canadian profile from a US address stays CA, and asks to confirm", reg("CA", "ON", "US", "NY"), {"region": "CA", "confirm": True})
t("an address in Quebec makes it QC (the stricter rules), and asks to confirm when the profile says another province", reg("CA", "ON", "CA", "QC"), {"region": "QC", "confirm": True})
t("the address agreeing with the profile: nothing to confirm", reg("CA", "ON", "CA", "ON"), {"region": "CA", "confirm": False})
t("a US address's state is not a Canadian province (CA there is California)", reg("US", "", "US", "CA"), {"region": "US", "confirm": False})
t("the Canadian documents: privacy, terms, apply, AI and marketing, each version 1, all drafts",
  {k: (d["version"], d["status"]) for k, d in legal_ca.DOCS.items()},
  {"privacy-ca": (1, "draft"), "terms-ca": (1, "draft"), "apply-ca": (1, "draft"), "ai-ca": (1, "draft"), "marketing-ca": (1, "draft")})

SENS = {
    "What is your Social Insurance Number (SIN)?": "sin", "SIN": "sin", "Numéro d'assurance sociale (NAS)": "sin", "Votre NAS": "sin",
    "Are you legally entitled to work in Canada?": "work_eligibility", "Do you hold a valid work permit?": "work_eligibility",
    "Are you eligible to work in Canada without sponsorship?": "work_eligibility", "Êtes-vous autorisé à travailler au Canada?": "work_eligibility",
    "Are you a Canadian citizen or permanent resident?": "work_eligibility",
    "Date of birth": "dob_age", "What is your age?": "dob_age", "Date de naissance": "dob_age", "Are you 18 years of age or older?": "dob_age",
    "Employment equity self-identification": "self_id", "Do you identify as Indigenous (First Nations, Métis or Inuit)?": "self_id",
    "Are you a member of a visible minority?": "self_id", "Do you identify as a woman?": "self_id",
    "Do you identify as a person with a disability?": "self_id", "Persons with disabilities (employment equity)": "self_id",
    "Do you have a disability?": "disability", "Will you require an accommodation during the interview?": "disability",
    "Avez-vous besoin de mesures d’adaptation?": "disability",
    "Do you have a criminal record for which a pardon has not been granted?": "criminal_record",
    "Do you consent to a background check?": "criminal_record", "Vulnerable sector police check": "criminal_record",
    "Avez-vous un casier judiciaire?": "criminal_record",
}
NOT = ("Why do you want to work here?", "Years of experience with Python", "LinkedIn profile", "How did you hear about us?",
       "Describe a time you managed a project", "Single sign-on experience", "Desired salary", "Which page did you find us on?")
t("is_sensitive_ca: each question left to the person gets its category", {q: legal_ca.is_sensitive_ca(q) for q in SENS}, SENS)
t("...and ordinary questions get None", [legal_ca.is_sensitive_ca(q) for q in NOT], [None] * len(NOT))

# the ledger and the waitlist, in this process
auth_api.init("unit")
s, out, tok, mail = auth_api.signup_with_code("ledger.one@example.com", "ledger pass 1", "198.51.100.70", True, first="Led", last="Ger", verified=True)
uid = out["user"]["id"]
t("needs_consent: nothing on the ledger", legal_ca.needs_consent(auth_api.latest_acceptance(uid, "privacy-ca"), "privacy-ca", 1, "CA", "ON"), True)
row = auth_api.record_acceptance(uid, "privacy-ca", 1, "CA", "ON", "checkbox")
t("record_acceptance keeps the document, version, country, province and method, and the time", (row["doc"], row["version"], row["country"], row["province"], row["method"], abs(row["at"] - time.time()) < 5),
  ("privacy-ca", 1, "CA", "ON", "checkbox", True))
t("needs_consent: the same document, version, country and province is covered", legal_ca.needs_consent(row, "privacy-ca", 1, "CA", "ON"), False)
t("...a new country asks again", legal_ca.needs_consent(row, "privacy-ca", 1, "US", ""), True)
t("...a new province asks again", legal_ca.needs_consent(row, "privacy-ca", 1, "CA", "BC"), True)
t("...a new version asks again", legal_ca.needs_consent(row, "privacy-ca", 2, "CA", "ON"), True)
t("...another document's acceptance does not cover this one", legal_ca.needs_consent(row, "terms-ca", 1, "CA", "ON"), True)
db = sqlite3.connect(auth_api._path, isolation_level=None)      # reads only, and one insert the ledger must refuse
try:
    db.execute("INSERT INTO legal_acceptances(user_id, doc, version, at, method) VALUES(?,?,?,?,?)", (uid, "privacy-ca", 1, 0, "email"))
    bad_method = "kept"
except sqlite3.IntegrityError:
    bad_method = "refused"
t("the ledger refuses a method other than checkbox or swipe", bad_method, "refused")
t("waitlist: optin missing, false, the string \"true\" or 1 is refused",
  [auth_api.waitlist_add("q@example.com", o)[0] for o in (None, False, "true", 1)], [400] * 4)
t("waitlist: a bad address is refused", auth_api.waitlist_add("not an address", True)[0], 400)
t("waitlist: an address with optin true is kept (and again changes nothing)", (auth_api.waitlist_add("Q.One@Example.com", True, 1), auth_api.waitlist_add("q.one@example.com", True, 1)[0]),
  ((200, {"ok": True}), 200))
t("waitlist keeps only the address, the time and the words' version", [r[1] for r in db.execute("PRAGMA table_info(quebec_waitlist)").fetchall()], ["id", "email", "at", "wording_version"])
t("...one row, the address as UAply keeps addresses", [(r[0], r[1]) for r in db.execute("SELECT email, wording_version FROM quebec_waitlist").fetchall()], [("q.one@example.com", 1)])
auth_api.record_consent(uid, consent_api.VERSION, "198.51.100.70", consent_api.digest(consent_api.full_text(False)), False, True, True)
t("record_consent writes one first-swipe row on the ledger (US, checkbox, the words' SHA-256)",
  db.execute("SELECT doc, version, country, province, method, text_sha256 FROM legal_acceptances WHERE user_id=? AND doc='first-swipe'", (uid,)).fetchall(),
  [("first-swipe", 6, "US", "", "checkbox", consent_api.digest(consent_api.full_text(False)))])
auth_api.record_consent(uid, 0, "198.51.100.70", "", False)
t("...and a take-back writes none", db.execute("SELECT COUNT(*) FROM legal_acceptances WHERE user_id=? AND doc='first-swipe'", (uid,)).fetchone()[0], 1)
auth_api.delete_account(tok, "ledger pass 1", "198.51.100.70")
t("deleting the account removes its ledger rows", db.execute("SELECT COUNT(*) FROM legal_acceptances WHERE user_id=?", (uid,)).fetchone()[0], 0)
db.close()
os.environ.pop("CANADA_ENABLED", None)


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
    c.close()
    try:
        return r.status, json.loads(raw)
    except ValueError:
        return r.status, raw.decode("utf-8", "replace")


def server(port, data, on):
    env = dict(os.environ, UAPLY_DATA_DIR=data, UAPLY_CONFIG_JSON=json.dumps({"feeds": [], "delivery": "test", "owner_copy": "", "google": {}, "smtp": {}}),
               UAPLY_DNS_CHECK="off", UAPLY_REQUEST_LOG="off")
    for k in ("UAPLY_SIGNUP_TEST", "RENDER", "OWNER_PASSWORD", "CANADA_ENABLED", "HOST"):
        env.pop(k, None)
    if on:
        env["CANADA_ENABLED"] = "1"
    PROCS.append(subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(port), "dev", "--api"], cwd=ROOT, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))


def wait(port):
    for _ in range(120):
        try:
            if req(port, "GET", "/healthz")[0] == 200:
                return True
        except OSError:
            time.sleep(0.25)
    return False


def account(data, email):
    """A verified account made in the server's own database; the cookie that signs it in."""
    os.environ["UAPLY_DATA_DIR"] = data
    auth_api.init("dev")
    s, out, tok, mail = auth_api.signup_with_code(email, "pass for " + email, "198.51.100.71", True, first="Can", last="Ada", verified=True)
    return "%s=%s" % (auth_api.cookie_name(), tok), out["user"]["id"]


GOOD = {"version": consent_api.VERSION, "text": consent_api.full_text(False), "auto": False, "ticks": {"authorize": True, "accurate": True}}
ACCEPT = {"doc": "privacy-ca", "version": 1, "method": "checkbox", "country": "CA", "province": "ON"}
OFF, ON = PORT, PORT + 1
off_data, on_data = os.path.join(TMP, "off"), os.path.join(TMP, "on")
try:
    os.makedirs(off_data)
    os.makedirs(on_data)
    server(OFF, off_data, False)
    server(ON, on_data, True)
    t("both servers start", (wait(OFF), wait(ON)), (True, True))
    ck_off, uid_off = account(off_data, "us.person@example.com")
    ck_on, uid_on = account(on_data, "ca.person@example.com")

    # (b) switched off: the three routes are an unknown address, signed in or not
    unknown_get, unknown_post = req(OFF, "GET", "/api/legal/nope"), req(OFF, "POST", "/api/legal/nope", {"x": 1})
    t("an unknown address answers 404 (GET and POST)", (unknown_get[0], unknown_post[0]), (404, 404))
    t("switched off: GET /api/legal/region answers as an unknown address", [req(OFF, "GET", "/api/legal/region?country=CA&province=QC", cookie=c) for c in ("", ck_off)], [unknown_get] * 2)
    t("switched off: POST /api/legal/accept answers as an unknown address", [req(OFF, "POST", "/api/legal/accept", ACCEPT, c) for c in ("", ck_off)], [unknown_post] * 2)
    t("switched off: POST /api/legal/quebec-waitlist answers as an unknown address",
      [req(OFF, "POST", "/api/legal/quebec-waitlist", {"email": "w@example.com", "optin": True}, c) for c in ("", ck_off)], [unknown_post] * 2)
    for port, name in ((OFF, "switched off"), (ON, "switched on")):
        t("%s: the Canadian drafts are never served (docs/legal-drafts, also by a ../ or an encoded path)" % name,
          [req(port, "GET", u)[0] for u in ("/docs/legal-drafts/canada/README.md", "/docs/legal-drafts/canada/privacy-ca.md", "/../docs/legal-drafts/canada/README.md",
                                             "/%2e%2e/docs/legal-drafts/canada/README.md", "/legal/../docs/legal-drafts/canada/README.md", "/legal/privacy-ca.md")], [404] * 6)
    db = sqlite3.connect(os.path.join(off_data, "dev", "uaply.db"))
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    t("switched off: no waitlist table was made", "quebec_waitlist" in tables, False)

    # (d) the US agreement, as before, on the switched-off server
    s, out = req(OFF, "POST", "/api/consent", GOOD, ck_off)
    con = out.get("consent") or {} if isinstance(out, dict) else {}
    t("POST /api/consent: 200 {ok, consent: {v, at, auto, authorize, accurate}} as before",
      (s, sorted(out), sorted(con), con.get("v"), con.get("auto"), con.get("authorize"), con.get("accurate"), isinstance(con.get("at"), int)),
      (200, ["consent", "ok"], ["accurate", "at", "authorize", "auto", "v"], 6, False, True, True, True))
    row = db.execute("SELECT version, ip, text_sha256, auto, authorize, accurate FROM consents WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid_off,)).fetchone()
    t("...the consents row is kept as before (version, address, the words' SHA-256, the ticks)", row, (6, "127.0.0.1", consent_api.digest(consent_api.full_text(False)), 0, 1, 1))
    t("...the words' SHA-256 is the one from before Canada", row[2] if row else None, hashlib.sha256(consent_api.full_text(False).encode("utf-8")).hexdigest())
    t("...and one first-swipe row on the ledger", db.execute("SELECT doc, version, country, province, method FROM legal_acceptances WHERE user_id=?", (uid_off,)).fetchall(),
      [("first-swipe", 6, "US", "", "checkbox")])
    t("POST /api/consent refusals are unchanged (old version, missing ticks, signed out)",
      (req(OFF, "POST", "/api/consent", dict(GOOD, version=5), ck_off), req(OFF, "POST", "/api/consent", dict(GOOD, ticks={}), ck_off)[1].get("code"), req(OFF, "POST", "/api/consent", GOOD)),
      ((409, {"error": "This page is out of date. Reload UAply and agree to the current terms.", "code": "consent_old"}), "consent_ticks", (401, {"error": "Sign in first.", "code": "signin"})))
    db.close()

    # (c) switched on, over HTTP
    t("switched on: GET /api/legal/region (no country: US; Canada, Ontario: CA; Quebec: QC; this computer's address is no hint)",
      [req(ON, "GET", u)[1] for u in ("/api/legal/region", "/api/legal/region?country=CA&province=ON", "/api/legal/region?country=Canada&province=Qu%C3%A9bec")],
      [{"region": "US", "confirm": False}, {"region": "CA", "confirm": False}, {"region": "QC", "confirm": False}])
    t("accept: signed out answers 401", req(ON, "POST", "/api/legal/accept", ACCEPT)[0], 401)
    t("accept: an unknown document, an old or made-up version, a method other than checkbox or swipe, no province: refused",
      [req(ON, "POST", "/api/legal/accept", dict(ACCEPT, **ch), ck_on)[0] for ch in ({"doc": "privacy"}, {"doc": "first-swipe"}, {"version": 2}, {"version": "1"}, {"version": True},
                                                                                      {"method": "email"}, {"province": ""}, {"country": "US"})],
      [400, 400, 409, 409, 409, 400, 400, 400])
    s, out = req(ON, "POST", "/api/legal/accept", ACCEPT, ck_on)
    t("accept: 200 with the ledger row", (s, (out.get("acceptance") or {}).get("doc")), (200, "privacy-ca"))
    db = sqlite3.connect(os.path.join(on_data, "dev", "uaply.db"))
    row = db.execute("SELECT user_id, doc, version, at, country, province, method FROM legal_acceptances WHERE doc='privacy-ca'").fetchall()
    t("...the row: the account, the document, its version, the time, the country, the province and the method",
      [(r[0], r[1], r[2], abs(r[3] - time.time()) < 30, r[4], r[5], r[6]) for r in row], [(uid_on, "privacy-ca", 1, True, "CA", "ON", "checkbox")])
    req(ON, "POST", "/api/legal/accept", dict(ACCEPT, doc="apply-ca", method="swipe", country="Canada", province="Québec"), ck_on)
    t("...a swipe in Quebec is kept as CA, QC, swipe", db.execute("SELECT country, province, method FROM legal_acceptances WHERE doc='apply-ca'").fetchall(), [("CA", "QC", "swipe")])
    t("waitlist over HTTP: optin missing, false or the string \"true\" is refused",
      [req(ON, "POST", "/api/legal/quebec-waitlist", b)[0] for b in ({"email": "wl@example.com"}, {"email": "wl@example.com", "optin": False}, {"email": "wl@example.com", "optin": "true"})],
      [400, 400, 400])
    t("...with optin true it is kept (signed out: the waitlist is for people who cannot sign up yet)",
      req(ON, "POST", "/api/legal/quebec-waitlist", {"email": "wl@example.com", "optin": True, "name": "Not Kept", "province": "QC"}), (200, {"ok": True}))
    rows = db.execute("SELECT * FROM quebec_waitlist").fetchall()
    t("...and only the address, the time and the words' version are kept (no name, no address of the visitor)",
      [(r[1], isinstance(r[2], int), r[3], len(r)) for r in rows], [("wl@example.com", True, legal_ca.WAITLIST_WORDING, 4)])
    c = http.client.HTTPConnection("127.0.0.1", ON, timeout=30)
    c.request("POST", "/api/legal/quebec-waitlist", body=json.dumps({"email": "y@example.com", "optin": True}),
              headers={"Host": "127.0.0.1:%d" % ON, "Origin": "https://evil.example", "Content-Type": "application/json"})
    t("...a cross-site post answers 403", c.getresponse().status, 403)
    c.close()
    s, out = req(ON, "POST", "/api/consent", GOOD, ck_on)
    t("switched on too, POST /api/consent answers as before", (s, sorted(out), (out.get("consent") or {}).get("v")), (200, ["consent", "ok"], 6))
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
