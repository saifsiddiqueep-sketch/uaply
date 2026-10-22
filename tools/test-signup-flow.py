"""Sign-up v2 (no password, an emailed 6-digit code) on the server: the sandbox runs it, dev and the live site behave exactly as before.
  python tools/test-signup-flow.py [sandbox port]        (default 18791; dev runs on the next port)
Starts its own throwaway sandbox and dev servers (stopped at the end), so it needs nothing running.
Checks, first on auth_api directly and then over HTTP:
  * sign-up without a password: an account with no usable password, the 18+ tick recorded (terms_at), a code made, and NO session yet
  * the code: wrong tries, five strikes, the right one signs in (verified), one use only; "new" only for a brand-new account
  * an address that already has an account gets a sign-in code with the same answer; "Email me a code" never says who has an account
  * limits: codes per address and per connection, wrong codes; a throwaway domain is refused
  * an unproven password on that address is removed when the code proves the inbox (like Continue with Google does), and so is a
    Google sign-in Google did not vouch for, with every session it had
  * any account whose address was never proven (no password, an unproven password, an unvouched Google login) is finished only with the
    code typer's own 18+ / Terms tick (needsAgree otherwise), and terms_at becomes that tick
  * a day's limits: 6 code emails per address, 15 wrong codes per address (then code sign-in stops for that address until the day is
    over); every code email to one account shares one hourly limit with Resend; an expired code is refused
  * Google: asked for "openid email" only, everywhere (the "profile" scope is a question for Saif); the sandbox keeps "new or not" 10
    minutes in memory; a Google sign-in on a pending no-password account links it without "password removed"
  * dev: POST /api/auth/signup without a password is still refused, the code routes are 404, /api/auth/providers is unchanged
  * a sandbox started with UAPLY_CODE_SIGNIN=0 (the test server for today's card) behaves like dev"""
import http.client
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18791
DEV_PORT = PORT + 1
TMP = tempfile.mkdtemp(prefix="uaply-signup-")
os.environ["UAPLY_DATA_DIR"] = os.path.join(TMP, "unit")
os.environ["UAPLY_CONFIG_FILE"] = "none"
os.environ["UAPLY_CONFIG_JSON"] = json.dumps({"delivery": "test", "smtp": {}, "feeds": [], "owner_copy": ""})

import auth_api  # noqa: E402
import google_auth  # noqa: E402

R = []
PROCS = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


def row(email):
    with auth_api._db() as c:
        return c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()


def sessions(uid):
    with auth_api._db() as c:
        return c.execute("SELECT COUNT(*) FROM sessions WHERE user_id=?", (uid,)).fetchone()[0]


# ---------------------------------------------------------------- auth_api directly
auth_api.init("signup-unit")
IP = "10.1.0.1"

s, out, mail = auth_api.signup_passwordless("sam@example.com", IP, agree=False)
t("no tick: refused (the 18+ / Terms box is required)", (s, mail), (400, None))
s, out, mail = auth_api.signup_passwordless("not-an-email", IP, agree=True)
t("a bad address: refused", s, 400)
s, out, mail = auth_api.signup_passwordless("throwaway@mailinator.com", IP, agree=True)
t("a throwaway domain: refused with the keep-it message", (s, out.get("error")), (400, auth_api.KEEP_MSG))

s, out, mail = auth_api.signup_passwordless("Sam@Example.com", IP, agree=True)
t("sign-up without a password: 200", s, 200)
t("the answer names only the address, never a user or a token", out, {"ok": True, "email": "sam@example.com"})
t("a code is made to be emailed", bool(mail) and mail[1] == "sam@example.com" and bool(re.fullmatch(r"[0-9]{6}", mail[2])), True)
r = row("sam@example.com")
t("the account has no usable password", r["has_password"], 0)
t("it starts unverified", r["email_verified"], 0)
t("the 18+ / Terms tick is recorded (terms_at)", bool(r["terms_at"]) and abs(r["terms_at"] - time.time()) < 60, True)
t("nobody is signed in until the code is typed", sessions(r["id"]), 0)
code1 = mail[2]

s2, out2, mail2 = auth_api.signup_passwordless("sam@example.com", IP, agree=True)
t("the same address again: the very same answer (nobody learns it has an account)", (s2, out2), (s, out))
t("...and a fresh code goes to that inbox", bool(mail2) and mail2[2] != "" and mail2[0] == r["id"], True)
with auth_api._db() as c:
    t("still one account for that address", c.execute("SELECT COUNT(*) FROM users WHERE email='sam@example.com'").fetchone()[0], 1)
code2 = mail2[2]

s, out, tok = auth_api.login_with_code("sam@example.com", code1, IP, True)
t("the older code no longer works once a new one was sent", (s, tok), (400, None) if code1 != code2 else (200, tok))
wrong = "%06d" % ((int(code2) + 1) % 1000000)
for i in range(3):
    s, out, tok = auth_api.login_with_code("sam@example.com", wrong, IP)
t("a wrong code says how many tries are left", (s, out.get("triesLeft"), tok), (400, 1, None))
s, out, tok = auth_api.login_with_code("sam@example.com", "12", IP)
t("a short code is refused before it counts", s, 400)
s, out, tok = auth_api.login_with_code("sam@example.com", code2, IP)
t("the right code for a brand-new account, without the tick: needsAgree, no session", (s, out.get("needsAgree"), tok), (400, True, None))
s, out, tok = auth_api.login_with_code("sam@example.com", code2, IP, True)
t("the right code signs in", (s, bool(tok)), (200, True))
t("...verified, no password, and marked new (so the page says Account created)", (out["user"]["emailVerified"], out["user"]["hasPassword"], out["user"]["new"]), (True, False, True))
t("the session is real", (auth_api.user_for(tok) or {}).get("email"), "sam@example.com")
s, out, tok2 = auth_api.login_with_code("sam@example.com", code2, IP, True)
t("a code works once", (s, tok2), (400, None))

s, out, mail = auth_api.send_login_code("sam@example.com", "10.1.0.2")
t("Email me a code, known address: the same plain answer and a code", (s, out, bool(mail)), (200, {"ok": True}, True))
s, out, tok = auth_api.login_with_code("sam@example.com", mail[2], "10.1.0.2")
t("signing in again: not new (the page says You're signed in)", (s, out["user"]["new"]), (200, False))
s, out, mail = auth_api.send_login_code("nobody@example.com", "10.1.0.2")
t("Email me a code, unknown address: the same answer and no email", (s, out, mail), (200, {"ok": True}, None))

# five wrong tries end a code
s, out, mail = auth_api.signup_passwordless("five@example.com", "10.1.0.3", agree=True)
bad = "%06d" % ((int(mail[2]) + 7) % 1000000)
for i in range(5):
    s, out, tok = auth_api.login_with_code("five@example.com", bad, "10.1.0.3")
t("the fifth wrong try ends the code", out.get("expired"), True)
s, out, tok = auth_api.login_with_code("five@example.com", mail[2], "10.1.0.3", True)
t("...and then even the right digits do not work", (s, tok), (400, None))

# an address someone else signed up (they ticked 18+): the owner's code finishes it only with the owner's own tick, recorded anew
s, out, mail = auth_api.signup_passwordless("own@example.com", "10.1.0.4", agree=True)
with auth_api._db() as c:
    c.execute("UPDATE users SET terms_at=1 WHERE email='own@example.com'")
s, out, mail = auth_api.send_login_code("own@example.com", "10.1.0.5")
s, out, tok = auth_api.login_with_code("own@example.com", mail[2], "10.1.0.5")
t("squatted address, owner's Email me a code without a tick: needsAgree, no session", (s, out.get("needsAgree"), tok), (400, True, None))
s, out, tok = auth_api.login_with_code("own@example.com", mail[2], "10.1.0.5", True)
t("...ticked: signs in, new, and the tick on record is the owner's (terms_at now)", (s, out["user"]["new"], abs(row("own@example.com")["terms_at"] - time.time()) < 60), (200, True, True))

# limits
for i in range(3):
    auth_api.send_login_code("limit@example.com", "10.2.0.%d" % i)
s, out, mail = auth_api.send_login_code("limit@example.com", "10.2.0.9")
t("at most 3 codes an hour per address (same 429 whether or not it has an account)", (s, out.get("code"), mail), (429, "code_limit", None))
for i in range(12):
    auth_api.send_login_code("x%d@example.com" % i, "10.3.0.1")
s, out, mail = auth_api.signup_passwordless("fresh@example.com", "10.3.0.1", agree=True)
t("at most 12 codes an hour per connection, sign-up included", (s, out.get("code")), (429, "code_limit"))
fails = [auth_api.login_with_code("x%d@example.com" % (i % 12), "000000", "10.4.0.1")[0] for i in range(20)]
s, out, tok = auth_api.login_with_code("sam@example.com", "000000", "10.4.0.1")
t("20 wrong codes from one connection: locked for a while", s, 429)
for i in range(auth_api.SIGNUPS_PER_HOUR_LOCAL):
    auth_api.signup_passwordless("many%d@example.com" % i, "10.5.0.1", agree=True)
s, out, mail = auth_api.signup_passwordless("many-more@example.com", "10.5.0.1", agree=True)
t("the existing new-accounts-per-hour cap applies too", (s, out.get("code")), (429, "signup_limit"))

# an unproven password on the address is removed when the code proves the inbox
s, out, ptok = auth_api.signup("pw@example.com", "correct horse 99", "10.6.0.1", True)
with auth_api._db() as c:
    c.execute("UPDATE users SET terms_at=1 WHERE email='pw@example.com'")      # the tick of whoever chose that password
s, out, mail = auth_api.send_login_code("pw@example.com", "10.6.0.2")
s, out, tok = auth_api.login_with_code("pw@example.com", mail[2], "10.6.0.2")
t("code sign-in on an unverified password account without the tick: needsAgree, no session (their tick is not the owner's)", (s, out.get("needsAgree"), tok), (400, True, None))
s, out, tok = auth_api.login_with_code("pw@example.com", mail[2], "10.6.0.2", True)
t("code sign-in on an unverified password account: password removed and said so (ticked; not new)", (s, out["user"]["hasPassword"], out["user"].get("passwordRemoved"), out["user"]["new"]), (200, False, True, False))
t("...and the tick on record is the owner's (terms_at now)", abs(row("pw@example.com")["terms_at"] - time.time()) < 60, True)
t("...the session made with that password has ended", auth_api.user_for(ptok), None)
s, out, tok = auth_api.login("pw@example.com", "correct horse 99", "10.6.0.1")
t("...and the password no longer signs in", s, 401)

# a Google sign-in Google does not vouch for (not Gmail, no Workspace domain): once the inbox's owner proves the address with a code,
# that Google login no longer opens the account and its session has ended
err, user, xtok = auth_api.oauth_login("google", "g-x", "lee@example.org", True, False)
t("Google, address it does not vouch for: an unverified account and a session", (err, bool(xtok), user and user["emailVerified"]), (None, True, False))
with auth_api._db() as c:
    c.execute("UPDATE users SET terms_at=1 WHERE email='lee@example.org'")
s, out, mail = auth_api.send_login_code("lee@example.org", "10.6.1.1")
s, out, tok = auth_api.login_with_code("lee@example.org", mail[2], "10.6.1.1")
t("an unvouched Google account, the owner's code without the tick: needsAgree, no session", (s, out.get("needsAgree"), tok), (400, True, None))
s, out, tok = auth_api.login_with_code("lee@example.org", mail[2], "10.6.1.1", True)
t("the inbox's owner signs in with the code", (s, bool(tok)), (200, True))
t("...the answer says Google sign-in was taken off (the card stops offering it), and the tick is the owner's", (out["user"].get("googleRemoved"), abs(row("lee@example.org")["terms_at"] - time.time()) < 60), (True, True))
t("...the earlier Google session has ended", auth_api.user_for(xtok), None)
t("...the owner's own session works", (auth_api.user_for(tok) or {}).get("email"), "lee@example.org")
err, user, xtok2 = auth_api.oauth_login("google", "g-x", "lee@example.org", True, False)
t("...and that Google login no longer opens the account", (err, xtok2), ("email_in_use", None))

# a code that has run out of time: refused (expired), no session; a fresh code then works
s, out, mail = auth_api.signup_passwordless("late@example.com", "10.6.2.1", agree=True)
with auth_api._db() as c:
    c.execute("UPDATE email_codes SET expires_at=? WHERE user_id=?", (int(time.time()) - 1, mail[0]))
s, out, tok = auth_api.login_with_code("late@example.com", mail[2], "10.6.2.1", True)
t("an expired code, right digits: refused as expired, no session", (s, out.get("expired"), tok), (400, True, None))
s, out, mail = auth_api.send_login_code("late@example.com", "10.6.2.1")
s, out, tok = auth_api.login_with_code("late@example.com", mail[2], "10.6.2.1", True)
t("...and a fresh code then signs in", (s, bool(tok)), (200, True))

# every code email to one account shares one hourly limit: Resend on a signed-in card (resend_code, ("u", id)) and Email me a code
err, user, btok = auth_api.oauth_login("google", "g-both", "both@example.org", True, False)
r1 = auth_api.resend_code(btok, "10.6.3.1")[0]
r2 = auth_api.resend_code(btok, "10.6.3.2")[0]
s, out, mail = auth_api.send_login_code("both@example.org", "10.6.3.3")
t("one account: 2 Resends and 1 Email me a code go out", (r1, r2, s, bool(mail)), (200, 200, 200, True))
s, out, mail = auth_api.send_login_code("both@example.org", "10.6.3.4")
t("...a 4th code email that hour is refused (one limit, not 3 + 3)", (s, out.get("code"), mail), (429, "code_limit", None))
t("...and so is a 4th through Resend", auth_api.resend_code(btok, "10.6.3.5")[0], 429)


# a day's limits, on a clock the test moves forward (auth_api reads time.time())
class Clock:
    def __init__(self, real):
        self.real, self.add = real, 0.0

    def time(self):
        return self.real.time() + self.add

    def __getattr__(self, name):
        return getattr(self.real, name)


real_time = auth_api.time
clock = auth_api.time = Clock(real_time)
try:
    sent = []
    for hour in range(3):                                  # 3 an hour is allowed; over three hours that would be 9
        for i in range(3):
            sent.append(auth_api.send_login_code("daily@example.com", "10.9.%d.%d" % (hour, i))[0])
        clock.add += 3601
    t("a day's limit: at most 6 code emails to one address (3 an hour, then 3, then none)", sent, [200] * 6 + [429] * 3)
    clock.add += 86400
    t("...the next day the address gets codes again", auth_api.send_login_code("daily@example.com", "10.9.9.1")[0], 200)

    # 15 wrong codes for one address in a day: code sign-in stops for it, even with the right digits, until the day is over
    s, out, mail = auth_api.signup_passwordless("guess@example.com", "10.9.10.1", agree=True)
    wrong_answers = []
    for hour in range(3):
        if hour:
            mail = auth_api.send_login_code("guess@example.com", "10.9.10.%d" % (hour + 1))[2]
        bad = "%06d" % ((int(mail[2]) + 1) % 1000000)
        for i in range(5):                                 # five wrong tries end each code; spread over hours so the 15-minute limits never trip
            wrong_answers.append(auth_api.login_with_code("guess@example.com", bad, "10.9.11.%d" % hour)[0])
        clock.add += 3601
    t("15 wrong codes over three hours are each refused", all(a == 400 for a in wrong_answers) and len(wrong_answers) == 15, True)
    mail = auth_api.send_login_code("guess@example.com", "10.9.10.9")[2]
    s, out, tok = auth_api.login_with_code("guess@example.com", mail[2], "10.9.12.1", True)
    t("...then even the right code is refused for the rest of the day (no session)", (s, out.get("code"), tok), (429, "code_day", None))
    s, out, tok = auth_api.login_with_code("nobody-guess@example.com", "123456", "10.9.12.1", True)
    t("...an address with no account answers as before (400), so the limit says nothing about who has an account", s, 400)
    clock.add += 86400
    mail = auth_api.send_login_code("guess@example.com", "10.9.13.1")[2]
    s, out, tok = auth_api.login_with_code("guess@example.com", mail[2], "10.9.13.1", True)
    t("...the next day the right code signs in", (s, bool(tok)), (200, True))
    with auth_api._lock:
        n_day = len(auth_api._code_day)
    t("the day's counts are kept apart from the hourly ones (memory is bounded by the day)", n_day > 0, True)
finally:
    auth_api.time = real_time

# Google on a pending no-password account (made but its code never typed)
auth_api.signup_passwordless("gabi@gmail.com", "10.7.0.1", agree=True)
err, user, gtok = auth_api.oauth_login("google", "g-1", "gabi@gmail.com", False, True)
t("Google (Gmail) on a pending no-password account: links and verifies it", (err, user and user["emailVerified"]), (None, True))
t("...with no 'password removed' message (there was no password)", "passwordRemoved" in (user or {}), False)
t("...and the account is new as far as the page is concerned", auth_api.created_within(user["id"], 60), True)
auth_api.remember_google(user["id"], True)
t("the page's hint holds only 'new or not' (no name from Google)", auth_api.google_hint(user["id"]), {"new": True})
with sqlite3.connect(auth_api._path) as db:
    cols = [r_[1] for r_ in db.execute("PRAGMA table_info(users)").fetchall()]
t("...and the account table has no name column (nothing from Google beyond email and account number)", any("name" in c_ for c_ in cols), False)

# the old password sign-up is unchanged
s, out, tok = auth_api.signup("old@example.com", "", "10.8.0.1", True)
t("today's sign-up still needs a password", (s, out.get("error")), (400, "Use a password between 8 and 128 characters."))

# Google's request is unchanged everywhere: "openid email" (asking for "profile" is Saif's call, question Q2)
import uaply_api  # noqa: E402
cfg = {"google": {"client_id": "t.apps.googleusercontent.com", "client_secret": "s", "auth_url": "http://127.0.0.1:1/auth"}}
real_config = uaply_api.config
uaply_api.config = lambda: cfg
url, st = google_auth.start("127.0.0.1:1", "http", True)
t("Google is asked for openid email only", urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["scope"], ["openid email"])
claims = {"sub": "1", "email": "a@gmail.com", "given_name": "A", "family_name": "B"}
t("Google's answer is read for email and account number only", sorted(google_auth._identity(claims)), ["email", "provider", "subject", "trusted"])
t("serve.py does not change Google's request", "PROFILE_SCOPE" in open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read(), False)
uaply_api.config = real_config


# ---------------------------------------------------------------- over HTTP: sandbox and dev side by side
def start(port, inst, **extra):
    env = dict(os.environ, UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=os.path.join(TMP, inst + str(port)),
               UAPLY_CONFIG_JSON=json.dumps({"delivery": "test", "smtp": {}, "feeds": [], "owner_copy": ""}), **extra)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("HOST", None)
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(port), inst, "--api"], cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PROCS.append(p)
    for _ in range(80):
        try:
            if req(port, "GET", "/healthz")[0] == 200:
                return
        except OSError:
            time.sleep(0.25)
    raise SystemExit("the %s test server did not start on %d" % (inst, port))


def req(port, method, path, body=None, cookie="", origin=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    h = {"Host": "127.0.0.1:%d" % port}
    if body is not None:
        h["Content-Type"] = "application/json"
        h["Origin"] = origin or "http://127.0.0.1:%d" % port
    if cookie:
        h["Cookie"] = cookie
    c.request(method, path, json.dumps(body) if body is not None else None, h)
    r = c.getresponse()
    raw = r.read()
    try:
        j = json.loads(raw.decode("utf-8"))
    except ValueError:
        j = raw.decode("utf-8", "replace")
    out = (r.status, j, r.getheader("Set-Cookie") or "")
    c.close()
    return out


def inbox_code(port):
    s, page, _ = req(port, "GET", "/outbox")
    m = re.search(r"([0-9]{6}) is your UAply verification code", page if isinstance(page, str) else "")
    return m.group(1) if m else ""


try:
    start(PORT, "sandbox")
    start(DEV_PORT, "dev")
    s, j, _ = req(PORT, "GET", "/api/auth/providers")
    t("sandbox: providers says codeSignin", j.get("codeSignin"), True)
    s, j, _ = req(DEV_PORT, "GET", "/api/auth/providers")
    t("dev: providers is exactly as before (no codeSignin key)", "codeSignin" in j, False)

    s, j, ck = req(PORT, "POST", "/api/auth/signup", {"email": "web@example.com", "agree": True, "passwordless": True})
    t("sandbox: sign-up without a password answers 200", (s, j.get("ok"), j.get("email")), (200, True, "web@example.com"))
    t("sandbox: ...and sets no session cookie", ck, "")
    t("sandbox: the code went to this computer's test inbox", j.get("delivery"), "delivered_test")
    s, j, _ = req(PORT, "POST", "/api/auth/signup", {"email": "web2@example.com", "passwordless": True})
    t("sandbox: no tick, no account", s, 400)
    code = inbox_code(PORT)
    s, j, ck = req(PORT, "POST", "/api/auth/code/verify", {"email": "web@example.com", "code": "000000" if code != "000000" else "111111"})
    t("sandbox: a wrong code is refused, no cookie", (s, ck), (400, ""))
    s, j, ck = req(PORT, "POST", "/api/auth/code/verify", {"email": "web@example.com", "code": code})
    t("sandbox: the right code without the tick: needsAgree, no cookie", (s, j.get("needsAgree"), ck), (400, True, ""))
    s, j, ck = req(PORT, "POST", "/api/auth/code/verify", {"email": "web@example.com", "code": code, "agree": True})
    t("sandbox: the right code signs in with the session cookie", (s, "uaply_sandbox_session=" in ck), (200, True))
    t("sandbox: ...new account, verified", (j["user"]["new"], j["user"]["emailVerified"]), (True, True))
    cookie = ck.split(";", 1)[0]
    s, j, _ = req(PORT, "GET", "/api/auth/me", cookie=cookie)
    t("sandbox: /api/auth/me knows the person", (j.get("user") or {}).get("email"), "web@example.com")
    s, j, _ = req(PORT, "POST", "/api/auth/code/send", {"email": "nobody@example.com"})
    t("sandbox: Email me a code for an unknown address: the plain answer", (s, j), (200, {"ok": True}))
    s, j, _ = req(PORT, "POST", "/api/auth/code/send", {"email": "web@example.com"}, origin="https://evil.example")
    t("sandbox: another site cannot ask for codes", s, 403)
    s, j, ck = req(PORT, "POST", "/api/auth/signup", {"email": "pw-web@example.com", "password": "correct horse 99", "agree": True})
    t("sandbox: today's password sign-up still works", (s, bool(ck)), (200, True))

    s, j, ck = req(DEV_PORT, "POST", "/api/auth/signup", {"email": "dev@example.com", "agree": True, "passwordless": True})
    t("dev: sign-up without a password is still refused (unchanged)", (s, j.get("error"), ck), (400, "Use a password between 8 and 128 characters.", ""))
    for path in ("/api/auth/code/send", "/api/auth/code/verify"):
        s, j, _ = req(DEV_PORT, "POST", path, {"email": "dev@example.com", "code": "123456"})
        t("dev: %s does not exist (404)" % path, s, 404)
        s, j, _ = req(DEV_PORT, "POST", path, {"email": "dev@example.com"}, origin="https://evil.example")
        t("dev: %s is 404 even before the same-site check (exactly as before)" % path, s, 404)
    s, j, ck = req(DEV_PORT, "POST", "/api/auth/signup", {"email": "dev@example.com", "password": "correct horse 99", "agree": True})
    t("dev: password sign-up signs in at once, as before", (s, "uaply_dev_session=" in ck, j["user"]["hasPassword"]), (200, True, True))
    s, j, _ = req(DEV_PORT, "GET", "/api/auth/me", cookie=ck.split(";", 1)[0])
    t("dev: /api/auth/me has no Google hint key", "google" in (j.get("user") or {}), False)

    # a sandbox with UAPLY_CODE_SIGNIN=0 (how run-all-tests.sh checks today's password card on the sandbox): exactly like dev
    start(PORT + 2, "sandbox", UAPLY_CODE_SIGNIN="0")
    s, j, _ = req(PORT + 2, "GET", "/api/auth/providers")
    t("sandbox, code sign-in off: providers has no codeSignin key", "codeSignin" in j, False)
    s, j, _ = req(PORT + 2, "POST", "/api/auth/code/send", {"email": "off@example.com"})
    t("sandbox, code sign-in off: the code routes are 404", s, 404)
    s, j, ck = req(PORT + 2, "POST", "/api/auth/signup", {"email": "off@example.com", "agree": True, "passwordless": True})
    t("sandbox, code sign-in off: sign-up without a password is refused", (s, ck), (400, ""))
finally:
    for p in PROCS:
        p.terminate()
    for p in PROCS:
        try:
            p.wait(10)
        except Exception:
            p.kill()

print("\n%d / %d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
