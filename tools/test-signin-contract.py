"""The sign-in contract (docs/ACCOUNTS.md, "The sign-in contract"; Saif, October 22, 2026) and the server-side open items 12 to 23 of the
sign-in record. Sign-up is email, first and last name and a password; the emailed code verifies the address after sign-up and is the other
way to sign in; nobody reaches site data without an account; UAPLY_SIGNUP_TEST=1 (never on a public server) signs a filler account in at
once. In this process (auth_api, uaply_api, emails) and over HTTP against three throwaway servers it starts and stops:
  python tools/test-signin-contract.py [port]      (default 20460; uses that port and the next three)"""
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
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20460
TMP = tempfile.mkdtemp(prefix="uaply-contract-")
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}", UAPLY_DATA_DIR=os.path.join(TMP, "unit"), UAPLY_DNS_CHECK="off")
os.makedirs(os.path.join(TMP, "unit"), exist_ok=True)
R = []
PROCS = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


import auth_api  # noqa: E402
import emails  # noqa: E402
import uaply_api  # noqa: E402

auth_api.init("contract")
uaply_api.init("contract")
IP = "198.51.100.40"

# ---------- names on the account (item 12, reversed: sign-up is email, first and last name and a password) ----------
s, out, tok, mail = auth_api.signup_with_code("dana.lee@example.com", "dana pass 123", IP, True, first="  Dana ", last="Lee\x07​")
t("sign-up keeps the first and last name, cleaned (spaces, control and zero-width characters out)", (s, out["user"]["first"], out["user"]["last"]), (200, "Dana", "Lee"))
me = auth_api.user_for(tok)
t("...and the account gives them back (what /api/auth/me returns)", (me["first"], me["last"], me["emailVerified"]), ("Dana", "Lee", False))
t("...a name longer than 60 characters is cut", auth_api.clean_name("x" * 90), "x" * 60)
t("...and a code to verify the address is made", bool(mail and re.fullmatch(r"\d{6}", mail[2] or "")), True)
s2, out2, tok2, mail2 = auth_api.signup_with_code("filler.one@example.com", "filler pass 1", IP, True, first="Filler", last="One", verified=True)
t("test mode (verified=True): the account is verified at once, signed in, and no code is made", (s2, out2["user"]["emailVerified"], bool(tok2), mail2), (200, True, True, None))
t("the same password rules: at least 8 characters", auth_api.signup_with_code("short.pw@example.com", "1234567", IP, True)[0], 400)
t("the same tick rule: no 18+ / Terms tick, no account", auth_api.signup_with_code("no.tick@example.com", "no tick pass 1", IP, False)[0], 400)
uaply_api.config()
payload = {"consent": True, "plan_only": True, "job": {"id": 1, "co": "Example Co", "role": "Analyst", "url": "https://example.com/jobs/1"},
           "profile": {"name": "", "email": "dana.lee@example.com", "ext": {"phone": "215-555-0100"}}}
code_noname = uaply_api.submit(payload, None)[1].get("error", "")
code_withacct = uaply_api.submit(payload, me)
t("an empty profile name is filled from the account's names (signed out it is still asked for)",
  ("Add your name" in code_noname, "Add your name" in json.dumps(code_withacct[1])), (True, False))

# ---------- item 19: an address that cannot exist ----------
bad = ["a@example..com", "a@.example.com", "a@-x.com", "a@x-.com", "a@example.c", "a@ex ample.com", "a@" + "b" * 250 + ".com"]
good = ["first.last+tag@mail.example.co.uk", "a@x.io", "o'brien@example.com".replace("'", ""), "a@x-y.example.com"]
t("addresses that cannot exist are refused (a@example..com, a@.example.com, a label starting or ending with -, too long)",
  [auth_api.canonical_email(x) for x in bad], [""] * len(bad))
t("...real ones still pass", [bool(auth_api.canonical_email(x)) for x in good], [True] * len(good))

# ---------- item 17: a right code typed in full-width or Arabic-Indic digits ----------
s, out, mail = auth_api.signup_passwordless("digits@example.com", IP, True)
code = mail[2]
full = "".join(chr(0xFF10 + int(ch)) for ch in code)
s, out, tok3 = auth_api.login_with_code("digits@example.com", full, IP, True)
t("a right code typed in full-width digits signs in (not a wrong try)", (s, bool(tok3)), (200, True))
s, out, mail = auth_api.send_login_code("digits@example.com", IP)
arabic = "".join(chr(0x0660 + int(ch)) for ch in mail[2])
t("...and in Arabic-Indic digits", auth_api.login_with_code("digits@example.com", arabic, IP, True)[0], 200)
t("...while wrong digits are still wrong", auth_api.login_with_code("digits@example.com", "０" * 6, IP, True)[0], 400)

# ---------- item 16: change password on an account with no password ----------
s, out = auth_api.change_password(tok3, "whatever", "a new password 1", IP)
t("change password on a code account says it has no password and how it signs in, without Google",
  (s, out.get("code"), "no password" in out["error"], "code sent to your email" in out["error"], "Google" in out["error"]), (400, "no_password", True, True, False))
err, guser, gtok = auth_api.oauth_login("google", "g-contract-1", "gina@gmail.com", True, True)
s, out = auth_api.change_password(gtok, "whatever", "a new password 1", IP)
t("...and names Google only when a Google login is linked", (s, "or with Google" in out["error"]), (400, True))

# ---------- item 23: whether Google is linked ----------
t("google_linked: true for the Google account, false for a code or password account",
  (auth_api.google_linked(guser["id"]), auth_api.google_linked(me["id"]), auth_api.google_linked(auth_api.user_for(tok3)["id"])), (True, False, False))

# ---------- item 15: one sentence for the sign-up limit and the code limit, the same for every address ----------
t("the limit sentence fits both causes and does not tell a newcomer to check an inbox",
  ("sign-ups or codes" in auth_api.CODE_LIMIT_MSG, "Check your inbox" in auth_api.CODE_LIMIT_MSG), (True, False))
ip2 = "198.51.100.41"
for i in range(auth_api.SIGNUPS_PER_HOUR_LOCAL):
    auth_api.signup_passwordless("fill.%d@example.com" % i, ip2, True)
a = auth_api.signup_passwordless("dana.lee@example.com", ip2, True)[:2]
b = auth_api.signup_passwordless("nobody.at.all@example.com", ip2, True)[:2]
t("...an address with an account and one without get the same 429 and the same words", (a, a == b), ((429, {"error": auth_api.CODE_LIMIT_MSG, "code": "code_limit"}), True))

# ---------- item 13: the day counters have a size cap ----------
keep = auth_api.CODE_DAY_MAX
auth_api.CODE_DAY_MAX = 50
try:
    with auth_api._lock:
        auth_api._code_day.clear()
        for i in range(70):
            auth_api._code_day_recent(("send", "flood.%d@example.com" % i)).append(time.time() + i)
        size, oldest_kept = len(auth_api._code_day), ("send", "flood.0@example.com") in auth_api._code_day
    t("the day counters never grow past their cap (the oldest go first)", (size <= 50, oldest_kept, ("send", "flood.69@example.com") in auth_api._code_day), (True, False, True))
    x = auth_api.send_login_code("dana.lee@example.com", "198.51.100.42")[:2]
    y = auth_api.send_login_code("never.signed.up@example.com", "198.51.100.43")[:2]
    t("...and with the counters full, an address with an account and one without get the same answer", (x[0], x == y), (200, True))
finally:
    auth_api.CODE_DAY_MAX = keep

# ---------- item 20: Forgot password writes its token after the answer ----------
def resets():
    with sqlite3.connect(auth_api._path) as c:
        return c.execute("SELECT COUNT(*) FROM password_resets").fetchone()[0]
n0 = resets()
s, out, mail = auth_api.request_reset("dana.lee@example.com", "198.51.100.44", defer=True)
s2, out2, mail2 = auth_api.request_reset("no.account.here@example.com", "198.51.100.44", defer=True)
t("Forgot password answers the same with or without an account, and writes nothing before the answer",
  ((s, out) == (s2, out2), mail[2], mail2, resets() - n0), (True, None, None, 0))
uid, addr, token = auth_api.issue_reset_token(mail[0])
t("...the link's token is written on the background thread, just before it is emailed", (addr, len(token) > 20, resets() - n0), ("dana.lee@example.com", True, 1))

# ---------- item 21: a sign-in code says what it is ----------
subj, text, page = emails.signin_code_email("123456")
t("a sign-in code email says it signs in, that UAply never asks for it, and what to do if it was not you",
  (subj, "This code signs in to your UAply account" in text, "UAply will never ask you for it" in text, "If it was not you, ignore this email" in text,
   "Confirm your email" in page), ("123456 is your UAply sign-in code", True, True, True, False))
t("...and a sign-up's code keeps the confirm-your-email wording", emails.verification_email("123456")[0], "123456 is your UAply verification code")
t("passwordless sign-up of an address that already has an account emails a sign-in code; a new address a confirm code",
  (auth_api.signup_passwordless("dana.lee@example.com", "198.51.100.45", True)[2][3], auth_api.signup_passwordless("brand.new@example.com", "198.51.100.45", True)[2][3]),
  ("signin", "confirm"))


# ---------- over HTTP ----------
def req(port, method, path, body=None, cookie="", addr="127.0.0.1", public=False):
    h = {"Host": "uaply.example" if public else "127.0.0.1:%d" % port}
    h["Origin"] = ("https://" if public else "http://") + h["Host"]
    if public:
        h.update({"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.50"})
    if cookie:
        h["Cookie"] = cookie
    if body is not None:
        h["Content-Type"] = "application/json"
    c = http.client.HTTPConnection(addr, port, timeout=30)
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    raw = r.read()
    ck = [v.split(";", 1)[0] for k, v in r.getheaders() if k.lower() == "set-cookie"]
    c.close()
    try:
        return r.status, json.loads(raw), ck
    except ValueError:
        return r.status, raw.decode("utf-8", "replace"), ck


def start(port, data, cfg, extra=None, public=False):
    env = dict(os.environ, UAPLY_DATA_DIR=data, UAPLY_CONFIG_JSON=json.dumps(cfg), UAPLY_CF_RANGES="0", UAPLY_DNS_CHECK="off", **(extra or {}))
    env.pop("UAPLY_SIGNUP_TEST", None) if not (extra or {}).get("UAPLY_SIGNUP_TEST") else None
    if public:
        env.update(HOST="127.0.0.2", OWNER_PASSWORD="ownerpw")
    PROCS.append(subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(port), "dev", "--api"], cwd=ROOT, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for _ in range(80):
        try:
            if req(port, "GET", "/healthz", addr="127.0.0.2" if public else "127.0.0.1", public=public)[0] == 200:
                return
        except OSError:
            time.sleep(0.25)
    raise SystemExit("a test server did not start")


MAILS = os.path.join(TMP, "mail.jsonl")


def mail_code(addr, kind, after="", wait=6.0):
    end = time.time() + wait
    while time.time() < end:
        try:
            rows = [json.loads(x) for x in open(MAILS, encoding="utf-8") if x.strip()]
        except (OSError, ValueError):
            rows = []
        for r in reversed(rows):
            m = re.search(r"([0-9]{6}) is your UAply %s code" % kind, r.get("raw", ""))
            if addr in json.dumps(r.get("to")) and m and m.group(1) != after:
                return m.group(1), r.get("raw", "")
        time.sleep(0.1)
    return "", ""


try:
    PROCS.append(subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(PORT + 2), MAILS], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    SMTP = {"host": "127.0.0.1", "port": PORT + 2, "starttls": False, "from_addr": "uaply@example.com"}
    # A: this computer, test mode on
    start(PORT, os.path.join(TMP, "a"), {"feeds": [], "smtp": {}, "owner_copy": ""}, {"UAPLY_SIGNUP_TEST": "1"})
    s, prov, _ = req(PORT, "GET", "/api/auth/providers")
    t("test mode: providers says signupTest (and codeSignin) on this computer", (prov.get("signupTest"), prov.get("codeSignin")), (True, True))
    s, out, ck = req(PORT, "POST", "/api/auth/signup", {"email": "filler@example.com", "password": "filler pass 1", "agree": True, "first": "Fill", "last": "Er"})
    t("test mode: sign-up makes a verified account and signs it in at once, no email", (s, out["user"]["emailVerified"], bool(ck), out.get("delivery"), out.get("testMode")),
      (200, True, True, "none", True))
    s, ob, _ = req(PORT, "GET", "/api/outbox")
    t("...nothing went to the test inbox", "filler@example.com" in json.dumps(ob), False)
    t("signed out, the job list answers 401 'Sign in first.'", req(PORT, "GET", "/api/jobs")[:2], (401, {"error": "Sign in first.", "code": "signin"}))
    s, jobs, _ = req(PORT, "GET", "/api/jobs", cookie=ck[0])
    t("...signed in, it answers", (s, "jobs" in jobs), (200, True))
    s, me1, _ = req(PORT, "GET", "/api/auth/me", cookie=ck[0])
    t("/api/auth/me gives first, last and googleLinked", ((me1["user"] or {}).get("first"), me1["user"].get("last"), me1["user"].get("googleLinked")), ("Fill", "Er", False))
    # B: a public server with email (as the live site)
    start(PORT + 1, os.path.join(TMP, "b"), {"feeds": [], "smtp": SMTP, "owner_copy": "", "public_url": "https://uaply.example"}, {"UAPLY_SIGNUP_TEST": "1"}, public=True)
    s, prov, _ = req(PORT + 1, "GET", "/api/auth/providers", addr="127.0.0.2", public=True)
    t("public with email: codeSignin on, and never signupTest (even with UAPLY_SIGNUP_TEST=1 set)", (prov.get("codeSignin"), prov.get("signupTest", False)), (True, False))
    t0 = time.time()
    s, out, ck = req(PORT + 1, "POST", "/api/auth/signup", {"email": "real.person@example.com", "password": "real pass 123", "agree": True,
                                                            "first": "Real", "last": "Person"}, addr="127.0.0.2", public=True)
    t("sign-up answers 200 with the account (names kept, not yet verified) and signs in", (s, out["user"]["first"], out["user"]["emailVerified"], bool(ck), out.get("delivery")),
      (200, "Real", False, True, "sent"))
    code, raw = mail_code("real.person@example.com", "verification")
    t("...then the verification code is emailed (after the answer)", bool(code), True)
    s, out, _ = req(PORT + 1, "POST", "/api/auth/verify", {"code": code}, cookie=ck[0], addr="127.0.0.2", public=True)
    me2 = req(PORT + 1, "GET", "/api/auth/me", cookie=ck[0], addr="127.0.0.2", public=True)[1]
    t("...and verifies the address", (s, out.get("ok"), (me2.get("user") or {}).get("emailVerified")), (200, True, True))
    s, out, _ = req(PORT + 1, "POST", "/api/auth/code/send", {"email": "real.person@example.com"}, addr="127.0.0.2", public=True)
    code2, raw2 = mail_code("real.person@example.com", "sign-in", after=code)
    t("Email me a code: a sign-in code, under its own subject (item 21; the wording is checked above)", (s, bool(code2)), (200, True))
    s, out, ck2 = req(PORT + 1, "POST", "/api/auth/code/verify", {"email": "real.person@example.com", "code": code2}, addr="127.0.0.2", public=True)
    t("...and it signs in (the other way in)", (s, bool(ck2)), (200, True))
    a = req(PORT + 1, "POST", "/api/auth/forgot", {"email": "real.person@example.com"}, addr="127.0.0.2", public=True)[:2]
    b = req(PORT + 1, "POST", "/api/auth/forgot", {"email": "no.such.person@example.com"}, addr="127.0.0.2", public=True)[:2]
    t("Forgot password answers the same either way on a public server (item 20)", (a[0], a == b), (200, True))
    end = time.time() + 6
    got_link = False
    while time.time() < end and not got_link:
        got_link = any("?reset=" in json.loads(x).get("raw", "") for x in open(MAILS, encoding="utf-8") if x.strip())
        time.sleep(0.1)
    t("...and the link is emailed after the answer", got_link, True)
    # C: a public server with no email: no code routes pretending to send, and no test mode
    start(PORT + 3, os.path.join(TMP, "c"), {"feeds": [], "smtp": {}, "owner_copy": ""}, {"UAPLY_SIGNUP_TEST": "1"}, public=True)
    s, prov, _ = req(PORT + 3, "GET", "/api/auth/providers", addr="127.0.0.2", public=True)
    t("public with no email: no codeSignin and no signupTest", (prov.get("codeSignin", False), prov.get("signupTest", False)), (False, False))
    t("...Email me a code refuses to pretend (503 mail_off)", req(PORT + 3, "POST", "/api/auth/code/send", {"email": "x@example.com"}, addr="127.0.0.2", public=True)[:2],
      (503, {"error": "Signing in with an emailed code is not available right now. Use Continue with Google, or try again later.", "code": "mail_off"}))
    s, out, ck = req(PORT + 3, "POST", "/api/auth/signup", {"email": "pw.only@example.com", "password": "pw only 123", "agree": True}, addr="127.0.0.2", public=True)
    t("...the password sign-up still works there (unverified, as before)", (s, out["user"]["emailVerified"], bool(ck)), (200, False, True))
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
