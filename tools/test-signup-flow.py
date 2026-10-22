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
  * a day's limits: 6 code emails per address (every route, Resend included), said with how long to wait; the owner's own device keeps
    2 spare codes a day; every code email to one account shares one hourly limit with Resend; an expired code is refused
  * nothing a stranger sends can lock the owner out: guesses at an address with no live code count only against the guesser's
    connection, and a freshly emailed code always works (hardening round 3, finding 1)
  * nothing tells a stranger who has an account: one answer for every code that does not sign in; Create my account counts every
    request against the connection's limit, with one answer for both limits; "Email me a code" answers as fast either way, with a
    mail server that takes 300 ms per message (and Forgot password on the sandbox too)
  * Google (sandbox) joining an account whose address was never proven needs the owner's own tick, and records it
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
t("a wrong code: the one plain answer, no tries count (it stays on the server)", (s, out, tok), (400, {"error": auth_api.WRONG_CODE_MSG, "code": "wrong_code"}, None))
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
t("the fifth wrong try ends the code (the same plain answer)", (s, out.get("code"), out.get("triesLeft"), out.get("expired")), (400, "wrong_code", None, None))
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
for i in range(auth_api.CODES_PER_IP_PER_HOUR):   # the shared limit (resend_code's too): 80 an hour per visitor address
    auth_api.send_login_code("x%d@example.com" % i, "10.3.0.1")
s, out, mail = auth_api.signup_passwordless("fresh@example.com", "10.3.0.1", agree=True)
t("at most %d codes an hour per connection, sign-up included" % auth_api.CODES_PER_IP_PER_HOUR, (s, out.get("code")), (429, "code_limit"))
fails = [auth_api.login_with_code("x%d@example.com" % (i % 12), "000000", "10.4.0.1")[0] for i in range(20)]
s, out, tok = auth_api.login_with_code("sam@example.com", "000000", "10.4.0.1")
t("20 wrong codes from one connection: locked for a while", s, 429)
for i in range(auth_api.SIGNUPS_PER_HOUR_LOCAL):
    auth_api.signup_passwordless("many%d@example.com" % i, "10.5.0.1", agree=True)
s, out, mail = auth_api.signup_passwordless("many-more@example.com", "10.5.0.1", agree=True)
t("the new-accounts-per-hour cap applies too (with the same answer as the code limit)", (s, out), (429, {"error": auth_api.CODE_LIMIT_MSG, "code": "code_limit"}))

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
t("an expired code, right digits: refused with the same plain answer, no session", (s, out.get("code"), tok), (400, "wrong_code", None))
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

    # hardening round 3, finding 1 (blocker): guesses at an address with no live code used to count toward a day's lock of 15, so 15
    # requests a day (no email, no code needed) kept the owner out for good. Now they count only against the guesser's own connection.
    s, out, mail = auth_api.signup_passwordless("victim@example.com", "10.9.10.1", agree=True)
    s, out, tok = auth_api.login_with_code("victim@example.com", mail[2], "10.9.10.1", True)
    t("finding 1: the owner's account exists and works", (s, bool(tok)), (200, True))
    for day_ in range(3):
        guesses = [auth_api.login_with_code("victim@example.com", "%06d" % i, "10.9.20.%d" % (i % 15))[0] for i in range(30)]
        clock.add += 60
        mail = auth_api.send_login_code("victim@example.com", "10.9.21.%d" % day_)[2]
        s, out, tok = auth_api.login_with_code("victim@example.com", mail[2], "10.9.22.%d" % day_, True)
        t("finding 1, day %d: 30 guesses from 15 connections with no code out, then the owner's fresh code signs in" % (day_ + 1),
          (all(g == 400 for g in guesses), s, bool(tok)), (True, 200, True))
        clock.add += 86400
    # with a live code: wrong guesses count against that code's 5 tries only; a new code then works at once (nothing locks the address)
    mail = auth_api.send_login_code("victim@example.com", "10.9.23.1")[2]
    burned = [auth_api.login_with_code("victim@example.com", "%06d" % ((int(mail[2]) + 1 + i) % 1000000), "10.9.24.%d" % i)[0] for i in range(5)]
    mail = auth_api.send_login_code("victim@example.com", "10.9.23.2")[2]
    s, out, tok = auth_api.login_with_code("victim@example.com", mail[2], "10.9.25.1", True)
    t("finding 1: 5 wrong tries end that one code; the owner's next code signs in at once", (burned, s, bool(tok)), ([400] * 5, 200, True))
    s, out, tok = auth_api.login_with_code("victim@example.com", "123456", "10.9.25.1", True)
    t("finding 1: a guess with no code out is the same plain answer", (s, out.get("code")), (400, "wrong_code"))
    clock.add += 86400

    # finding 5: the day's cap says how long, and the owner's own device keeps 2 spare codes a day
    s, out, mail = auth_api.signup_passwordless("capped@example.com", "10.9.30.1", agree=True)
    s, out, tok = auth_api.login_with_code("capped@example.com", mail[2], "10.9.30.1", True)
    device = auth_api.known_device(out["user"]["id"])
    t("finding 5: a code sign-in gives this device its known-device value", bool(re.fullmatch(r"[0-9]+\.[0-9a-f]{32}", device)), True)
    clock.add += 86400                                     # a new day: the sign-up's own code no longer counts
    sends = []
    for i in range(6):                                     # a stranger: 6 codes over 2 hours (3, then 3)
        sends.append(auth_api.send_login_code("capped@example.com", "10.9.31.%d" % i)[0])
        if i == 2:
            clock.add += 3601
    clock.add += 1800
    s, out, mail = auth_api.send_login_code("capped@example.com", "10.9.32.1")
    t("finding 5: after a stranger's 6 codes, another device is refused with its own code word and how long (not 'an hour')",
      (sends, s, out.get("code"), "about 23 hours" in out.get("error", ""), "an hour" in out.get("error", "")), ([200] * 6, 429, "code_day", True, False))
    s2, out2, mail2 = auth_api.send_login_code("nobody-capped@example.com", "10.9.32.2")
    t("finding 5: the cap is the same for an address with no account (the first code goes out the same)", s2, 200)
    s, out, mail = auth_api.send_login_code("capped@example.com", "10.9.33.1", device)
    t("finding 5: the owner's own device still gets a code", (s, bool(mail)), (200, True))
    s, out, tok = auth_api.login_with_code("capped@example.com", mail[2], "10.9.33.1", True)
    t("finding 5: ...and it signs in", (s, bool(tok)), (200, True))
    forged = device.split(".")[0] + "." + "0" * 32
    s, out, mail = auth_api.send_login_code("capped@example.com", "10.9.33.2", forged)
    t("finding 5: a made-up device value gets no spare code", (s, out.get("code")), (429, "code_day"))
    s, out, mail = auth_api.send_login_code("capped@example.com", "10.9.33.3", device)
    s3, out3, mail3 = auth_api.send_login_code("capped@example.com", "10.9.33.4", device)
    t("finding 5: 2 spare codes a day for the owner's device, then the day's answer", (s, s3, out3.get("code")), (200, 429, "code_day"))
    s, out, mail = auth_api.signup_passwordless("capped@example.com", "10.9.33.5", agree=True)
    t("finding 5: Create my account gets the same day's answer", (s, out.get("code")), (429, "code_day"))
    clock.add += 86400

    # every route that emails a code counts toward the day's cap: Resend on a signed-in, unconfirmed card (resend_code_daily)
    err, user, rtok = auth_api.oauth_login("google", "g-day", "resend@example.org", True, False)
    got = []
    for hour in range(3):
        got += [auth_api.resend_code_daily(rtok, "10.9.40.%d%d" % (hour, i))[0] for i in range(3)]
        clock.add += 3601
    s, out, mail = auth_api.send_login_code("resend@example.org", "10.9.41.1")
    t("Resend counts toward the day's cap too (3, 3, then refused), and so does Email me a code after it", (got, s, out.get("code")), ([200] * 6 + [429] * 3, 429, "code_day"))
    t("...Resend's own day answer says how long", "hours" in auth_api.resend_code_daily(rtok, "10.9.41.2")[1].get("error", ""), True)
    clock.add += 86400
    with auth_api._lock:
        n_day = len(auth_api._code_day)
    t("the day's counts are kept apart from the hourly ones (memory is bounded by the day)", n_day > 0, True)
finally:
    auth_api.time = real_time

# finding 2: Create my account on a connection that used up its sign-ups: an address with an account and one without get the very same answer
auth_api.signup_passwordless("member@example.com", "10.10.0.1", agree=True)
for i in range(auth_api.SIGNUPS_PER_HOUR_LOCAL - 1):
    auth_api.signup_passwordless("filler%d@example.com" % i, "10.10.0.1", agree=True)
a1 = auth_api.signup_passwordless("member@example.com", "10.10.0.1", agree=True)[:2]
a2 = auth_api.signup_passwordless("stranger@example.com", "10.10.0.1", agree=True)[:2]
t("finding 2: after the connection's sign-ups, an existing address and a new one get the same answer", (a1, a1 == a2), ((429, {"error": auth_api.CODE_LIMIT_MSG, "code": "code_limit"}), True))
for i in range(3):
    auth_api.send_login_code("made-up%d@example.com" % i, "10.10.0.2")
for i in range(auth_api.CODES_PER_IP_PER_HOUR - 3):
    auth_api.send_login_code("x-up%d@example.com" % i, "10.10.0.2")
b1 = auth_api.signup_passwordless("member@example.com", "10.10.0.2", agree=True)[:2]
b2 = auth_api.signup_passwordless("stranger2@example.com", "10.10.0.2", agree=True)[:2]
t("finding 2: after the connection's code emails, the same answer again for both", (b1, b1 == b2), ((429, {"error": auth_api.CODE_LIMIT_MSG, "code": "code_limit"}), True))

# finding 3: "Email me a code" then one wrong code: the same answer whether or not the address has an account
auth_api.signup_passwordless("known3@example.com", "10.10.1.1", agree=True)
k = auth_api.send_login_code("known3@example.com", "10.10.1.2")
u = auth_api.send_login_code("unknown3@example.com", "10.10.1.3")
t("finding 3: Email me a code answers the same", (k[:2], u[:2]), ((200, {"ok": True}), (200, {"ok": True})))
kw = auth_api.login_with_code("known3@example.com", "%06d" % ((int(k[2][2]) + 1) % 1000000), "10.10.1.4")
uw = auth_api.login_with_code("unknown3@example.com", "000000", "10.10.1.5")
t("finding 3: ...and so does a wrong code after it (no tries count, no 'expired' for one only)", (kw[:2], kw[:2] == uw[:2]), ((400, {"error": auth_api.WRONG_CODE_MSG, "code": "wrong_code"}), True))

# finding 6: a Google login Google vouches for, joining an account someone else opened on that Gmail address (no code typed), needs the
# owner's own tick on the sandbox (oauth_login_ticked), and the tick on record becomes the owner's
auth_api.signup_passwordless("owner.g@gmail.com", "10.10.2.1", agree=True)
with auth_api._db() as c:
    c.execute("UPDATE users SET terms_at=1 WHERE email='owner.g@gmail.com'")      # the stranger's tick
err, user, gt = auth_api.oauth_login_ticked("google", "g-owner", "owner.g@gmail.com", False, True)
t("finding 6: Google on someone else's unfinished account, no tick: 'agree_owner', no session", (err, gt, row("owner.g@gmail.com")["terms_at"]), ("agree_owner", None, 1))
err, user, gt = auth_api.oauth_login_ticked("google", "g-owner", "owner.g@gmail.com", True, True)
t("finding 6: ...ticked: signed in, verified, and the tick on record is the owner's (terms_at now)",
  (err, bool(gt), user and user["emailVerified"], abs(row("owner.g@gmail.com")["terms_at"] - time.time()) < 60), (None, True, True, True))
err, user, gt = auth_api.oauth_login_ticked("google", "g-owner", "owner.g@gmail.com", False, True)
t("finding 6: ...after that, Google signs in without the tick (the account is proven and the identity known)", (err, bool(gt)), (None, True))
err, user, gt = auth_api.oauth_login_ticked("google", "g-new", "brand.new.g@gmail.com", False, True)
t("finding 6: a brand-new Google account still needs the tick, as before", err, "agree")
auth_api.signup_passwordless("devrule.g@gmail.com", "10.10.2.2", agree=True)
err, user, gt = auth_api.oauth_login("google", "g-devrule", "devrule.g@gmail.com", False, True)
t("oauth_login itself (dev and the live site) now asks the owner's own tick too before joining an account never proven", (err, gt), ("agree", None))
err, user, gt = auth_api.oauth_login("google", "g-devrule", "devrule.g@gmail.com", True, True)
t("...and with the tick it joins and signs in", (err, bool(gt), (user or {}).get("emailVerified")), (None, True, True))

# Google on a pending no-password account (made but its code never typed)
auth_api.signup_passwordless("gabi@gmail.com", "10.7.0.1", agree=True)
err, user, gtok = auth_api.oauth_login("google", "g-1", "gabi@gmail.com", True, True)
t("Google (Gmail) on a pending no-password account, with the owner's tick: links and verifies it", (err, user and user["emailVerified"]), (None, True))
t("...with no 'password removed' message (there was no password)", "passwordRemoved" in (user or {}), False)
t("...and it does not claim to have made the account (the code sign-up did): no created flag", "created" in (user or {}), False)
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
def start(port, inst, cfg=None, **extra):
    env = dict(os.environ, UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=os.path.join(TMP, inst + str(port)), UAPLY_DNS_CHECK="off",
               UAPLY_CONFIG_JSON=json.dumps(cfg or {"delivery": "test", "smtp": {}, "feeds": [], "owner_copy": ""}), **extra)
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


def inbox_code(port, before=""):
    """The newest code in the test inbox (waiting a moment for one that differs from `before`: "Email me a code" sends after it answers)."""
    for _ in range(40):
        s, page, _ = req(port, "GET", "/outbox")
        m = re.search(r"([0-9]{6}) is your UAply verification code", page if isinstance(page, str) else "")
        if m and m.group(1) != before:
            return m.group(1)
        time.sleep(0.1)
    return ""


class Sink:
    """A local mail server that takes `delay` seconds per message, like a real mail service (nothing leaves this computer)."""
    def __init__(self, delay):
        import socket
        import threading
        self.delay, self.msgs, self.lock = delay, [], threading.Lock()
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(50)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        import threading
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.handle, args=(c,), daemon=True).start()

    def handle(self, c):
        f = c.makefile("rb")
        say = lambda x: c.sendall((x + "\r\n").encode())
        say("220 sink ESMTP")
        rcpt = []
        try:
            while True:
                line = f.readline()
                if not line:
                    break
                u = line.decode("latin-1").strip().upper()
                if u.startswith("EHLO"):
                    c.sendall(b"250-sink\r\n250-8BITMIME\r\n250 SMTPUTF8\r\n")
                elif u.startswith("RCPT TO"):
                    rcpt.append(line.decode("latin-1").strip()[8:].strip(" <>").lower())
                    say("250 ok")
                elif u == "DATA":
                    say("354 go")
                    data = []
                    while True:
                        x = f.readline()
                        if not x or x in (b".\r\n", b".\n"):
                            break
                        data.append(x.decode("utf-8", "replace"))
                    time.sleep(self.delay)
                    with self.lock:
                        self.msgs.append((",".join(rcpt), "".join(data), time.time()))
                    rcpt = []
                    say("250 queued")
                elif u.startswith("QUIT"):
                    say("221 bye")
                    break
                else:
                    say("250 ok")
        finally:
            c.close()

    def code_for(self, addr, wait=5.0):
        end = time.time() + wait
        while time.time() < end:
            with self.lock:
                for to, data, at in reversed(self.msgs):
                    m = re.search(r"([0-9]{6}) is your UAply verification code", data)
                    if addr in to and m:
                        return m.group(1)
            time.sleep(0.05)
        return ""

    def count(self, addr):
        with self.lock:
            return sum(1 for to, d, a in self.msgs if addr in to)


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

    # finding 1 over HTTP (the reviewer's repro): 15 guesses with no code out, then the owner's freshly emailed code signs in
    s, j, _ = req(PORT, "POST", "/api/auth/signup", {"email": "victim@example.com", "agree": True, "passwordless": True})
    c0 = inbox_code(PORT)
    s, j, ck = req(PORT, "POST", "/api/auth/code/verify", {"email": "victim@example.com", "code": c0, "agree": True})
    t("sandbox, finding 1: the owner's account is made", s, 200)
    t("sandbox, finding 5: a code sign-in sets the known-device cookie (HttpOnly, SameSite=Strict, /api/auth only)",
      bool(re.search(r"uaply_sandbox_session_known=[0-9]+\.[0-9a-f]{32}; HttpOnly; SameSite=Strict; Path=/api/auth; Max-Age=7776000", ck)), True)
    guesses = [req(PORT, "POST", "/api/auth/code/verify", {"email": "victim@example.com", "code": "%06d" % i})[0] for i in range(15)]
    s, j, _ = req(PORT, "POST", "/api/auth/code/send", {"email": "victim@example.com"})
    c1 = inbox_code(PORT, c0)
    s, j, ck = req(PORT, "POST", "/api/auth/code/verify", {"email": "victim@example.com", "code": c1, "agree": True})
    t("sandbox, finding 1: 15 guesses (all 400), then the owner's emailed code signs in (was 429 code_day)", (guesses, s, "uaply_sandbox_session=" in ck), ([400] * 15, 200, True))

    # a sandbox with UAPLY_CODE_SIGNIN=0 (how run-all-tests.sh checks today's password card on the sandbox): exactly like dev
    start(PORT + 2, "sandbox", UAPLY_CODE_SIGNIN="0")
    s, j, _ = req(PORT + 2, "GET", "/api/auth/providers")
    t("sandbox, code sign-in off: providers has no codeSignin key", "codeSignin" in j, False)
    s, j, _ = req(PORT + 2, "POST", "/api/auth/code/send", {"email": "off@example.com"})
    t("sandbox, code sign-in off: the code routes are 404", s, 404)
    s, j, ck = req(PORT + 2, "POST", "/api/auth/signup", {"email": "off@example.com", "agree": True, "passwordless": True})
    t("sandbox, code sign-in off: sign-up without a password is refused", (s, ck), (400, ""))

    # finding 4: a mail server that takes 300 ms per message. "Email me a code" answers as fast for an address with an account (it emails
    # a code) as for one without (it emails nothing); the code still arrives. Forgot password on the sandbox too.
    sink = Sink(0.3)
    SP = PORT + 6
    start(SP, "sandbox", cfg={"delivery": "test", "feeds": [], "owner_copy": "",
                              "smtp": {"host": "127.0.0.1", "port": sink.port, "from_addr": "noreply@example.test", "starttls": False}})
    s, j, _ = req(SP, "GET", "/api/auth/providers")
    t("slow mail: the server can email (codeSignin on)", (j.get("canEmail"), j.get("codeSignin")), (True, True))
    for i in range(3):
        req(SP, "POST", "/api/auth/signup", {"email": "has%d@example.com" % i, "agree": True, "passwordless": True})
    for i in range(3):
        sink.code_for("has%d@example.com" % i)

    def timed(path, body):
        t0 = time.time()
        s_, j_, _ = req(SP, "POST", path, body)
        return s_, time.time() - t0

    has = [timed("/api/auth/code/send", {"email": "has%d@example.com" % i}) for i in range(3)]
    none = [timed("/api/auth/code/send", {"email": "none%d@example.com" % i}) for i in range(3)]
    t("finding 4: Email me a code answers 200 for all six", [x[0] for x in has + none], [200] * 6)
    t("finding 4: ...and as fast with an account as without (each under 0.2 s; the mail server takes 0.3 s)",
      (max(x[1] for x in has) < 0.2, max(x[1] for x in none) < 0.2), (True, True))
    print("     timings with an account %s, without %s" % (["%.3f" % x[1] for x in has], ["%.3f" % x[1] for x in none]))
    time.sleep(1.5)
    t("finding 4: ...the codes still arrive, one per address with an account, none for the others",
      ([sink.count("has%d@example.com" % i) for i in range(3)], [sink.count("none%d@example.com" % i) for i in range(3)]), ([2, 2, 2], [0, 0, 0]))
    code = sink.code_for("has0@example.com")
    s, j, ck = req(SP, "POST", "/api/auth/code/verify", {"email": "has0@example.com", "code": code, "agree": True})
    t("finding 4: ...and the code from the slow mail server signs in", s, 200)
    f1 = timed("/api/auth/forgot", {"email": "has1@example.com"})
    f2 = timed("/api/auth/forgot", {"email": "none1@example.com"})
    t("finding 4: Forgot password on the sandbox answers as fast either way", (f1[0], f2[0], f1[1] < 0.2, f2[1] < 0.2), (200, 200, True, True))

    # finding 6 over HTTP: the full Google trip against the stand-in (tools/mock-google.py), on a sandbox and on dev
    MG = PORT + 7
    mock = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "mock-google.py"), str(MG)], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PROCS.append(mock)
    G = {"client_id": "test.apps.googleusercontent.com", "client_secret": "test-secret", "auth_url": "http://127.0.0.1:%d/auth" % MG,
         "token_url": "http://127.0.0.1:%d/token" % MG, "certs_url": "http://127.0.0.1:%d/certs" % MG}
    GP = PORT + 8
    start(GP, "sandbox", cfg={"delivery": "test", "smtp": {}, "feeds": [], "owner_copy": "", "google": G})

    def mget(path):
        for _ in range(40):
            try:
                c = http.client.HTTPConnection("127.0.0.1", MG, timeout=20)
                c.request("GET", path)
                r = c.getresponse()
                r.read()
                c.close()
                return r.getheader("Location") or ""
            except OSError:
                time.sleep(0.25)
        raise SystemExit("the stand-in for Google did not start on %d" % MG)

    def google(email, sub, agree):
        mget("/mock/next?" + urllib.parse.urlencode({"email": email, "sub": sub, "verified": "1"}))
        c_ = http.client.HTTPConnection("127.0.0.1", GP, timeout=20)
        c_.request("GET", "/api/auth/google/start" + ("?agree=1" if agree else ""), headers={"Host": "127.0.0.1:%d" % GP})
        r_ = c_.getresponse()
        r_.read()
        loc, oc = r_.getheader("Location"), (r_.getheader("Set-Cookie") or "").split(";")[0]
        c_.close()
        back = mget(loc.replace("http://127.0.0.1:%d" % MG, ""))
        c_ = http.client.HTTPConnection("127.0.0.1", GP, timeout=20)
        c_.request("GET", back.split("127.0.0.1:%d" % GP, 1)[1], headers={"Host": "127.0.0.1:%d" % GP, "Cookie": oc})
        r_ = c_.getresponse()
        r_.read()
        out_ = (r_.getheader("Location") or "", ", ".join(v for k, v in r_.getheaders() if k.lower() == "set-cookie"))
        c_.close()
        return out_

    def terms(port, inst, email):
        with sqlite3.connect(os.path.join(TMP, inst + str(port), inst, "uaply.db")) as db_:
            r_ = db_.execute("SELECT terms_at FROM users WHERE email=?", (email,)).fetchone()
        return r_[0] if r_ else None

    req(GP, "POST", "/api/auth/signup", {"email": "owner.g@gmail.com", "agree": True, "passwordless": True})   # the stranger
    before = terms(GP, "sandbox", "owner.g@gmail.com")
    time.sleep(1.1)
    loc, ck = google("owner.g@gmail.com", "7001", False)
    t("sandbox, finding 6: the owner's Google (from Welcome back, no tick) on that unfinished account: asked to tick, no session",
      (loc, "uaply_sandbox_session=" in ck), ("/?auth_error=agree_owner", False))
    loc, ck = google("owner.g@gmail.com", "7001", True)
    after = terms(GP, "sandbox", "owner.g@gmail.com")
    t("sandbox, finding 6: ...ticked: signed in, and the tick on record is the owner's, not the stranger's",
      (loc, "uaply_sandbox_session=" in ck, before is not None and after is not None and after > before), ("/?signed_in=google", True, True))
    sess = re.search(r"uaply_sandbox_session=([^;,]+)", ck)
    s, j, _ = req(GP, "GET", "/api/auth/me", cookie="uaply_sandbox_session=" + (sess.group(1) if sess else ""))
    t("sandbox, finding 6: ...and the page is told the account was just finished (Account created), with no stray field",
      ((j.get("user") or {}).get("google"), "finished" in (j.get("user") or {})), ({"new": True}, False))
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
