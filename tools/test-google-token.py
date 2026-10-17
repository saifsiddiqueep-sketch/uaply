"""Tests "Continue with Google" the way Google's own button works: the page gets a signed token and posts it to UAply. Every kind of forged or wrong
token must be refused. Start tools/mock-google.py and a server configured for it (see tools/run-all-tests.sh), then:
  python tools/test-google-token.py [server_port]"""
import html
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "18768"
B = "http://127.0.0.1:%s" % PORT
M = "http://127.0.0.1:%s" % os.environ.get("MOCK_GOOGLE_PORT", "8790")      # where tools/mock-google.py listens
R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


def client():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(op, path, data=None, origin=True):
    h = {"Content-Type": "application/json"}
    if origin:
        h["Origin"] = B
    req = urllib.request.Request(B + path, data=json.dumps(data).encode() if data is not None else None, headers=h, method="POST" if data is not None else "GET")
    try:
        r = op.open(req)
        return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None


def token(**q):
    qs = "&".join("%s=%s" % (k, urllib.parse.quote(str(v))) for k, v in q.items())
    return json.loads(urllib.request.urlopen(M + "/mock/idtoken?" + qs).read())["credential"]


def me(op):
    return call(op, "/api/auth/me")[1]["user"]


a = client()
s, prov = call(a, "/api/auth/providers")
t("the page is told Google's button is available and which client ID to use", (prov["google"], prov["googleClientId"]), (True, "test.apps.googleusercontent.com"))

# a good token
s, out = call(a, "/api/auth/google/token", {"credential": token(email="new.google@gmail.com", sub="9001"), "agree": True})
t("a valid token signs a new person in", (s, out["user"]["email"]), (200, "new.google@gmail.com"))
t("that account has no password and its Gmail address counts as verified", (out["user"]["hasPassword"], out["user"]["emailVerified"]), (False, True))
t("the session cookie works afterwards", (me(a) or {}).get("email"), "new.google@gmail.com")
call(a, "/api/auth/logout", {})
t("the same Google account signs in again without agreeing twice", call(a, "/api/auth/google/token", {"credential": token(email="new.google@gmail.com", sub="9001")})[0], 200)
call(a, "/api/auth/logout", {})

# Google is the authority on an email only for Gmail and Workspace accounts (the hd claim); any other "verified" address is not trusted to prove ownership
w = client()
s, out = call(w, "/api/auth/google/token", {"credential": token(email="staff@corp.example", sub="9030", hd="corp.example"), "agree": True})
t("a Google Workspace account (hd) counts as verified", (s, out["user"]["emailVerified"]), (200, True))
call(w, "/api/auth/logout", {})
u = client()
s, out = call(u, "/api/auth/google/token", {"credential": token(email="fresh@example.com", sub="9020"), "agree": True})
t("a Google account with some other email signs in but is NOT treated as having proven that email", (s, out["user"]["emailVerified"]), (200, False))
call(u, "/api/auth/logout", {})
t("...and signs in again by its Google account number", call(u, "/api/auth/google/token", {"credential": token(email="fresh@example.com", sub="9020")})[0], 200)
call(u, "/api/auth/logout", {})
# the real owner of that address uses Forgot password: the emailed link proves the address is theirs, so the Google login Google did not
# vouch for (it may belong to whoever had the address before) stops opening the account
call(client(), "/api/auth/forgot", {"email": "fresh@example.com"})
links = re.findall(r"\?reset=([A-Za-z0-9_-]{20,100})", html.unescape(urllib.request.urlopen(B + "/outbox").read().decode("utf-8")))
t("the reset link reaches the test inbox", bool(links), True)
t("the owner sets a password with it", call(client(), "/api/auth/reset", {"token": links[0] if links else "x" * 30, "password": "owners own pass 1"})[0], 200)
s, out = call(client(), "/api/auth/google/token", {"credential": token(email="fresh@example.com", sub="9020")})
t("after that the unvouched Google login no longer opens the account", (s, out.get("code")), (400, "email_in_use"))
t("...and the owner logs in with the new password", call(client(), "/api/auth/login", {"email": "fresh@example.com", "password": "owners own pass 1"})[0], 200)

# consent for new accounts
b = client()
s, out = call(b, "/api/auth/google/token", {"credential": token(email="noconsent@example.com", sub="9002")})
t("a new person who has not agreed is told to tick the box", (s, out["code"], me(b)), (400, "agree", None))

# every kind of bad token
for bad in ("aud", "iss", "expired", "tamper", "none", "hs256", "kid", "future"):
    c = client()
    s, out = call(c, "/api/auth/google/token", {"credential": token(email="evil@example.com", sub="6666", bad=bad), "agree": True})
    t("a token that is wrong (%s) is refused and nobody is signed in" % bad, (s, out.get("code"), me(c)), (400, "failed", None))
for label, cred in (("garbage", "not.a.token"), ("empty", ""), ("a huge string", "a" * 9000), ("a number", 12345), ("nothing at all", None)):
    s, out = call(client(), "/api/auth/google/token", {"credential": cred, "agree": True})
    t("%s is refused" % label, s, 400)
s, out = call(client(), "/api/auth/google/token", {"credential": token(email="unverified@example.com", sub="9003", verified=0), "agree": True})
t("a Google email that Google says is not verified is refused", (s, out["code"]), (400, "unverified"))

# linking to an existing password account proves ownership of that email
pw = client()
call(pw, "/api/auth/signup", {"email": "linked@gmail.com", "password": "correct horse 99", "agree": True})
t("a new password account starts unverified", me(pw)["emailVerified"], False)
g = client()                                    # pw stays signed in: the link below must sign it out
s, out = call(g, "/api/auth/google/token", {"credential": token(email="linked@gmail.com", sub="9004")})
t("Google with the same Gmail address signs into that same account", (s, out["user"]["email"]), (200, "linked@gmail.com"))
t("...the password nobody confirmed by email is removed, and the page is told", (out["user"]["hasPassword"], out.get("passwordRemoved")), (False, True))
t("...whoever set that password is signed out of it", me(pw), None)
t("...and that password no longer works", call(client(), "/api/auth/login", {"email": "linked@gmail.com", "password": "correct horse 99"})[0], 401)
t("...and that proves the email is theirs", me(g)["emailVerified"], True)

# the Google account id, not the email, identifies the person
call(g, "/api/auth/logout", {})
s, out = call(g, "/api/auth/google/token", {"credential": token(email="changed.address@example.com", sub="9004")})
t("the same Google id with a changed email is still the same account", out["user"]["email"], "linked@gmail.com")

# a Workspace account links to an existing account on its own domain...
call(pw, "/api/auth/signup", {"email": "boss@corp.example", "password": "correct horse 99", "agree": True})
call(pw, "/api/auth/logout", {})
s, out = call(client(), "/api/auth/google/token", {"credential": token(email="boss@corp.example", sub="9031", hd="corp.example")})
t("a Workspace account links to the existing account with its address (its unconfirmed password removed)", (s, out["user"]["email"], out["user"]["hasPassword"]), (200, "boss@corp.example", False))
# ...but a plain "verified" address on any other domain can NOT take over an existing account (the address may have changed hands)
call(pw, "/api/auth/signup", {"email": "victim@example.com", "password": "correct horse 99", "agree": True})
call(pw, "/api/auth/logout", {})
thief = client()
s, out = call(thief, "/api/auth/google/token", {"credential": token(email="victim@example.com", sub="9040"), "agree": True})
t("another Google account claiming that address cannot take over the existing account", (s, out["code"], me(thief)), (400, "email_in_use", None))
login = client()
s, out = call(login, "/api/auth/login", {"email": "victim@example.com", "password": "correct horse 99"})
t("the real owner still logs in, and the account is still unverified (nothing was linked)", (s, out["user"]["emailVerified"]), (200, False))

# Google's button sets its own cookie (g_state) with quotes and commas in it; that must never sign anyone out
sess = client()
call(sess, "/api/auth/google/token", {"credential": token(email="cookie.test@example.com", sub="9010"), "agree": True})
cookie_val = [c for h in sess.handlers if hasattr(h, "cookiejar") for c in h.cookiejar if c.name.endswith("_session")][0]
req = urllib.request.Request(B + "/api/auth/me", headers={"Cookie": '%s=%s; g_state={"i_l":0,"i_ll":1791990000000,"i_b":"a,b;c"}; other="x,y"' % (cookie_val.name, cookie_val.value)})
t("a session still works when Google's own cookie is sent alongside it", json.loads(urllib.request.urlopen(req).read())["user"]["email"], "cookie.test@example.com")

# only this site's own pages may post
t("a cross-site post is refused", call(client(), "/api/auth/google/token", {"credential": token(email="x@example.com", sub="9005"), "agree": True}, origin=False)[0], 403)

# trying many tokens quickly is limited
last = 0
for i in range(35):
    last = call(client(), "/api/auth/google/token", {"credential": "junk.junk.junk"})[0]
t("hammering the endpoint is limited", last, 429)

# straight on jwt_rs256 (no server, so the limit above does not apply): the expiry rules and an outage at Google
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import jwt_rs256  # noqa: E402
CERTS, AUD, ISS = M + "/certs", "test.apps.googleusercontent.com", ("https://accounts.google.com", "accounts.google.com")


def check(cred):
    try:
        return jwt_rs256.verify(cred, AUD, ISS, CERTS)["email"]
    except jwt_rs256.TokenError as e:
        return str(e)


t("a token that expired 20 seconds ago is still accepted (a minute of clock difference is forgiven, as Google's libraries do)", check(token(email="skew@gmail.com", sub="1", bad="skew")), "skew@gmail.com")
t("a token that expired 10 minutes ago is refused", check(token(email="old@gmail.com", sub="1", bad="expired")), "expired")
t("a token that claims to last three days is refused (Google's last an hour)", check(token(email="long@gmail.com", sub="1", bad="longlife")), "lasts too long")
before = json.loads(urllib.request.urlopen(M + "/mock/stats").read())["certs"]
for i in range(6):
    check(token(email="k%d@example.com" % i, sub="1", bad="kid"))
for i in range(3):
    check(token(email="ok%d@gmail.com" % i, sub="1"))
after = json.loads(urllib.request.urlopen(M + "/mock/stats").read())["certs"]
t("six tokens with made-up key ids and three good ones fetch Google's key list at most twice (once fresh, once for the unknown id)", after - before <= 2, True)
good = token(email="unit@gmail.com", sub="9060")
real_fetch = jwt_rs256._fetch_keys


def down(url):
    raise OSError("Google is unreachable")


jwt_rs256._fetch_keys = down
jwt_rs256._keys["until"] = 0                                 # the cached list is out of date and Google cannot be reached
t("when Google cannot be reached, a key already known still checks the token", check(good), "unit@gmail.com")
jwt_rs256._keys.update(url="", by_kid={}, until=0, tried=0)
t("...but with no key known at all the token is refused (never accepted unchecked)", check(good), "could not get the public keys")
jwt_rs256._fetch_keys = real_fetch
import google_auth  # noqa: E402
t("both of Google's issuer spellings are accepted (with and without https://)", set(google_auth.ISSUERS), {"https://accounts.google.com", "accounts.google.com"})

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
