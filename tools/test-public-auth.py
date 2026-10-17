"""Sign-in on a server run the way the live site runs it: public (any address but 127.0.0.1), behind Render's HTTPS proxy, which sends
X-Forwarded-Proto: https and X-Forwarded-For, for the addresses uaply.net, www.uaply.net and the onrender.com addresses. Starts its own throwaway
servers (a stand-in Google on PORT+1 and UAply on PORT) and stops them at the end, so it needs nothing running:
  python tools/test-public-auth.py [port]          (default 18780; uses that port and the next one)
Checks: the cookies, the same-site check for each real address, Google tokens (good, wrong and forged), linking a Google account to a
password account, a new Google account starting empty, signing in again after a server restart, the password rules, the lock-out after
wrong passwords (also when the attacker changes the address it claims to come from), and the 6-digit code's expiry, tries and resends.
PUBLIC_TEST_ADDR picks the address the server listens on (default 127.0.0.2, which counts as public but cannot be reached from other computers)."""
import http.client
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18780
MPORT = PORT + 1
ADDR = os.environ.get("PUBLIC_TEST_ADDR", "127.0.0.2")
DATA = tempfile.mkdtemp(prefix="uaply-pubauth-")
SITE = "uaply.net"
CFG = {"feeds": [], "smtp": {}, "owner_copy": "", "public_url": "https://uaply.net",
       "google": {"client_id": "test.apps.googleusercontent.com", "client_secret": "test-secret", "public_url": "https://uaply.net",
                  "auth_url": "http://127.0.0.1:%d/auth" % MPORT, "token_url": "http://127.0.0.1:%d/token" % MPORT,
                  "certs_url": "http://127.0.0.1:%d/certs" % MPORT}}
R = []
PROCS = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


def start_server():
    env = dict(os.environ, HOST=ADDR, UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=DATA, OWNER_PASSWORD="ownerpw", UAPLY_CONFIG_JSON=json.dumps(CFG))
    env.pop("ANTHROPIC_API_KEY", None)
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(PORT), "dev", "--api"], cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PROCS.append(p)
    for _ in range(60):
        try:
            if req("GET", "/healthz")[0] == 200:
                return p
        except OSError:
            time.sleep(0.25)
    raise SystemExit("the test server did not start")


def req(method, path, body=None, host=SITE, origin="same", cookie="", xff="203.0.113.7", headers=None):
    """One request as Render's proxy passes it on: HTTPS outside, plain HTTP inside, with the visitor's address in X-Forwarded-For."""
    h = {"Host": host, "X-Forwarded-Proto": "https", "X-Forwarded-For": xff + ", 10.0.0.1"}
    if origin == "same":
        h["Origin"] = "https://" + host
    elif origin:
        h["Origin"] = origin
    if cookie:
        h["Cookie"] = cookie
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    c = http.client.HTTPConnection(ADDR, PORT, timeout=30)
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    raw = r.read()
    cookies = r.msg.get_all("Set-Cookie") or []
    c.close()
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    return r.status, data, cookies, {k.lower(): v for k, v in r.getheaders()}


def session_of(cookies):
    for c in cookies:
        m = re.match(r"uaply_dev_session=([^;]*)", c)
        if m:
            return m.group(1)
    return ""


def jar(cookies):
    tok = session_of(cookies)
    return "uaply_dev_session=" + tok if tok else ""


def me(cookie, host=SITE):
    return (req("GET", "/api/auth/me", cookie=cookie, host=host)[1] or {}).get("user")


def gtoken(**q):
    qs = urllib.parse.urlencode(q)
    return json.loads(urllib.request.urlopen("http://127.0.0.1:%d/mock/idtoken?%s" % (MPORT, qs)).read())["credential"]


def db():
    c = sqlite3.connect(os.path.join(DATA, "dev", "uaply.db"))
    c.row_factory = sqlite3.Row
    return c


def last_code(email):
    """The newest 6-digit code in the server's test inbox (no real email is connected in this test)."""
    with db() as c:
        row = c.execute("SELECT subject FROM user_mail WHERE to_addr=? ORDER BY id DESC LIMIT 1", (email,)).fetchone()
    m = re.match(r"\s*(\d{6})", row["subject"] if row else "")
    return m.group(1) if m else ""


try:
    PROCS.append(subprocess.Popen([sys.executable, os.path.join(HERE, "mock-google.py"), str(MPORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    time.sleep(2.5)                                           # the stand-in Google makes its signing key first
    start_server()

    # ---------- cookies ----------
    s, out, ck, hd = req("POST", "/api/auth/signup", {"email": "pub.cookie@example.com", "password": "correct horse 99", "agree": True})
    t("sign-up works behind the HTTPS proxy", s, 200)
    c0 = next((c for c in ck if c.startswith("uaply_dev_session=")), "")
    t("the session cookie is HttpOnly, Secure, SameSite=Lax, for the whole site, for 30 days",
      all(x in c0 for x in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=2592000")), True)
    t("the session cookie has no Domain (so it stays on the exact address the person used)", "domain=" in c0.lower(), False)
    t("HTTPS is pinned for a year (HSTS)", hd.get("strict-transport-security"), "max-age=31536000")
    s, out, ck2, _ = req("POST", "/api/auth/login", {"email": "pub.cookie@example.com", "password": "correct horse 99"})
    t("log-in sets the same kind of cookie", all(x in (ck2 or [""])[0] for x in ("HttpOnly", "Secure", "SameSite=Lax")), True)
    s, out, ck3, _ = req("POST", "/api/auth/logout", {}, cookie=jar(ck2))
    t("sign-out clears the cookie (Max-Age=0, still Secure)", ("Max-Age=0" in (ck3 or [""])[0], "Secure" in (ck3 or [""])[0]), (True, True))
    t("...and that session no longer works", me(jar(ck2)), None)
    s, out, ck4, hd4 = req("GET", "/api/auth/google/start?agree=1")
    oc = next((c for c in ck4 if "_oauth=" in c), "")
    t("the Google sign-in state cookie is HttpOnly, Secure, SameSite=Lax, limited to the Google paths, 10 minutes",
      all(x in oc for x in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/api/auth/google", "Max-Age=600")), True)

    # ---------- the same-site check, for every real address ----------
    for host in ("uaply.net", "www.uaply.net", "uaply.onrender.com", "uaply-dev.onrender.com"):
        s = req("POST", "/api/auth/login", {"email": "nobody@example.com", "password": "whatever 123"}, host=host)[0]
        t("a request from the site's own page at https://%s is accepted (401 = it reached the password check)" % host, s, 401)
    for label, host, origin in (("another website", SITE, "https://evil.example"),
                                ("a look-alike address", SITE, "https://uaply.net.evil.example"),
                                ("the http:// version of the site behind HTTPS", SITE, "http://uaply.net"),
                                ("the Render address posting to uaply.net", SITE, "https://uaply-dev.onrender.com"),
                                ("a sandboxed frame (Origin: null)", SITE, "null"),
                                ("no Origin at all", SITE, "")):
        t("a request from %s is refused" % label, req("POST", "/api/auth/login", {"email": "a@b.co", "password": "x"}, host=host, origin=origin)[0], 403)

    # ---------- Google's button: tokens ----------
    s, prov, _, _ = req("GET", "/api/auth/providers")
    t("the page is told the Google button is on, with the client ID", (prov["google"], prov["googleClientId"]), (True, "test.apps.googleusercontent.com"))
    for host in ("uaply.net", "www.uaply.net", "uaply.onrender.com", "uaply-dev.onrender.com"):
        t("the full-page Google sign-in returns to the address the person is on (%s)" % host,
          (req("GET", "/api/auth/providers", host=host)[1] or {}).get("googleRedirectUri"), "https://%s/api/auth/google/callback" % host)
    s, out, gck, _ = req("POST", "/api/auth/google/token", {"credential": gtoken(email="brand.new@gmail.com", sub="7001"), "agree": True})
    t("a good Google token signs a new person in", (s, (out.get("user") or {}).get("email")), (200, "brand.new@gmail.com"))
    gc = next((c for c in gck if c.startswith("uaply_dev_session=")), "")
    t("...with the same HttpOnly, Secure, SameSite=Lax cookie", all(x in gc for x in ("HttpOnly", "Secure", "SameSite=Lax")), True)
    u = me(jar(gck))
    t("a brand-new Google account: verified Gmail, no password, free plan", (u["emailVerified"], u["hasPassword"], u["plan"]), (True, False, "free"))
    st = req("GET", "/api/billing/status", cookie=jar(gck))[1] or {}
    t("...and nothing on file yet (signed in, free plan, no applications counted)", (st.get("signedIn"), st.get("plan"), st.get("used")), (True, "free", 0))
    for bad in ("aud", "iss", "expired", "future", "tamper", "none", "hs256", "kid", "longlife"):
        s, out, ck5, _ = req("POST", "/api/auth/google/token", {"credential": gtoken(email="evil@gmail.com", sub="6666", bad=bad), "agree": True},
                             xff="198.51.100.%d" % (len(bad) + 10))
        t("a Google token that is wrong (%s) is refused and sets no session" % bad, (s, (out or {}).get("code"), session_of(ck5)), (400, "failed", ""))
    s, out, _, _ = req("POST", "/api/auth/google/token", {"credential": gtoken(email="unverified@gmail.com", sub="6667", verified=0), "agree": True})
    t("a Google email Google has not verified is refused", (s, out.get("code")), (400, "unverified"))

    # ---------- linking a Google account to a password account ----------
    # someone signs up with another person's Gmail address and a password, and never proves the address ...
    s, out, ack, _ = req("POST", "/api/auth/signup", {"email": "owner.of.this@gmail.com", "password": "attacker pass 1", "agree": True}, xff="198.51.100.66")
    attacker = jar(ack)
    # ... then the real owner arrives with Google
    s, out, rck, _ = req("POST", "/api/auth/google/token", {"credential": gtoken(email="owner.of.this@gmail.com", sub="7002")})
    t("Google with the same Gmail address signs into that existing account", (s, (out.get("user") or {}).get("email")), (200, "owner.of.this@gmail.com"))
    t("...the password set by someone who never proved the address is removed", (out.get("user") or {}).get("hasPassword"), False)
    t("...the page is told, so it can say so", out.get("passwordRemoved"), True)
    t("...whoever set that password is signed out", me(attacker), None)
    t("...and that password no longer works", req("POST", "/api/auth/login", {"email": "owner.of.this@gmail.com", "password": "attacker pass 1"}, xff="198.51.100.67")[0], 401)
    t("...and the real owner is signed in with a verified email", (me(jar(rck)) or {}).get("emailVerified"), True)
    # a password account that DID prove its address keeps its password when Google is linked
    s, out, vck, _ = req("POST", "/api/auth/signup", {"email": "proven@gmail.com", "password": "my own pass 22", "agree": True})
    s, out, _, _ = req("POST", "/api/auth/verify", {"code": last_code("proven@gmail.com")}, cookie=jar(vck))
    t("a password account proves its email with the 6-digit code", (s, out.get("ok")), (200, True))
    s, out, _, _ = req("POST", "/api/auth/google/token", {"credential": gtoken(email="proven@gmail.com", sub="7003")})
    t("Google then links to it and the password is kept", (s, (out.get("user") or {}).get("hasPassword"), out.get("passwordRemoved")), (200, True, None))
    t("...and the first device stays signed in", (me(jar(vck)) or {}).get("email"), "proven@gmail.com")
    t("...and the password still works", req("POST", "/api/auth/login", {"email": "proven@gmail.com", "password": "my own pass 22"})[0], 200)

    # ---------- sign-in survives a server restart (sessions are on disk) ----------
    keep = jar(rck)
    PROCS[-1].terminate()
    PROCS[-1].wait(10)
    start_server()
    t("after the server restarts, the person is still signed in", (me(keep) or {}).get("email"), "owner.of.this@gmail.com")
    t("...and a password account can still log in", req("POST", "/api/auth/login", {"email": "proven@gmail.com", "password": "my own pass 22"})[0], 200)

    # ---------- password rules ----------
    rules = (("7 characters", "abc4567", 400), ("8 characters", "abcd5678", 200), ("128 characters", "p" * 127 + "1", 200),
             ("129 characters", "p" * 128 + "1", 400))
    for i, (label, pw, want) in enumerate(rules):
        t("a password of %s is %s" % (label, "accepted" if want == 200 else "refused"),
          req("POST", "/api/auth/signup", {"email": "rule%d@example.com" % i, "password": pw, "agree": True}, xff="192.0.2.%d" % (i + 1))[0], want)
    t("the email itself as the password is refused", req("POST", "/api/auth/signup", {"email": "same@example.com", "password": "SAME@example.com", "agree": True}, xff="192.0.2.20")[0], 400)
    t("sign-up without the 18+ and Terms box is refused", req("POST", "/api/auth/signup", {"email": "noagree@example.com", "password": "correct horse 99"}, xff="192.0.2.21")[0], 400)
    t("a second account with the same email is refused", req("POST", "/api/auth/signup", {"email": "PROVEN@gmail.com", "password": "correct horse 99", "agree": True}, xff="192.0.2.22")[0], 409)
    t("a bad email address is refused", req("POST", "/api/auth/signup", {"email": "not-an-email", "password": "correct horse 99", "agree": True}, xff="192.0.2.23")[0], 400)

    # ---------- lock-out after wrong passwords ----------
    req("POST", "/api/auth/signup", {"email": "lock.me@example.com", "password": "the right one 1", "agree": True}, xff="192.0.2.30")
    got = [req("POST", "/api/auth/login", {"email": "lock.me@example.com", "password": "wrong %d" % i}, xff="192.0.2.31")[0] for i in range(6)]
    t("five wrong passwords, then the sixth try is held back", got, [401] * 5 + [429])
    t("during the lock-out even the right password is held back", req("POST", "/api/auth/login", {"email": "lock.me@example.com", "password": "the right one 1"}, xff="192.0.2.31")[0], 429)
    t("the owner of the account, from another connection, can still log in", req("POST", "/api/auth/login", {"email": "lock.me@example.com", "password": "the right one 1"}, xff="192.0.2.32")[0], 200)
    # an attacker who sends a made-up X-Forwarded-For with every try (Render keeps the first entry the visitor sent)
    req("POST", "/api/auth/signup", {"email": "target@example.com", "password": "the right one 2", "agree": True}, xff="192.0.2.40")
    spoofed = [req("POST", "/api/auth/login", {"email": "target@example.com", "password": "guess %d" % i}, xff="10.%d.%d.9" % (i // 200, i % 200))[0] for i in range(25)]
    t("guessing with a different made-up address every try is still stopped (after 20 wrong tries on one account)", (spoofed[:20] == [401] * 20, spoofed[20:]), (True, [429] * 5))
    t("...and the right password is held back too while that lasts (15 minutes)", req("POST", "/api/auth/login", {"email": "target@example.com", "password": "the right one 2"}, xff="192.0.2.41")[0], 429)
    t("...but the owner can still get in with Forgot password or Google; other accounts are not affected",
      req("POST", "/api/auth/login", {"email": "lock.me@example.com", "password": "the right one 1"}, xff="192.0.2.42")[0], 200)

    # ---------- the 6-digit code: tries, resend, expiry ----------
    s, out, cck, _ = req("POST", "/api/auth/signup", {"email": "code.check@example.com", "password": "correct horse 99", "agree": True}, xff="192.0.2.50")
    cj = jar(cck)
    first = last_code("code.check@example.com")
    t("sign-up makes a 6-digit code (here in the test inbox, as no real email is connected)", bool(re.fullmatch(r"\d{6}", first)), True)
    wrong = "%06d" % ((int(first or 0) + 1) % 1000000)
    tries = [req("POST", "/api/auth/verify", {"code": wrong}, cookie=cj)[1] for _ in range(5)]
    t("five wrong codes count down and then end the code", [x.get("triesLeft") for x in tries[:4]] + [bool(tries[4].get("expired"))], [4, 3, 2, 1, True])
    t("after that the right code is refused too", bool(req("POST", "/api/auth/verify", {"code": first}, cookie=cj)[1].get("expired")), True)
    s, out, _, _ = req("POST", "/api/auth/resend", {}, cookie=cj)
    second = last_code("code.check@example.com")
    t("Send a new code makes a different code", (s, bool(second) and second != first), (200, True))
    with db() as c:
        c.execute("UPDATE email_codes SET expires_at=? WHERE user_id=(SELECT id FROM users WHERE email='code.check@example.com')", (int(time.time()) - 1,))
    t("a code older than 10 minutes is refused as expired", bool(req("POST", "/api/auth/verify", {"code": second}, cookie=cj)[1].get("expired")), True)
    req("POST", "/api/auth/resend", {}, cookie=cj)
    third = last_code("code.check@example.com")
    t("a fresh code works", req("POST", "/api/auth/verify", {"code": third}, cookie=cj)[0], 200)
    t("the account is now verified", (me(cj) or {}).get("emailVerified"), True)
    s2, o2, c2, _ = req("POST", "/api/auth/signup", {"email": "code.limit@example.com", "password": "correct horse 99", "agree": True}, xff="192.0.2.51")
    t("at most three new codes an hour", [req("POST", "/api/auth/resend", {}, cookie=jar(c2))[0] for _ in range(4)], [200, 200, 200, 429])

    # ---------- the full-page Google sign-in (used on iPhone and iPad) on the www address ----------
    host = "www.uaply.net"
    urllib.request.urlopen("http://127.0.0.1:%d/mock/next?%s" % (MPORT, urllib.parse.urlencode({"email": "iphone.user@gmail.com", "sub": "7100", "verified": "1"})))
    s, _, sck, h1 = req("GET", "/api/auth/google/start?agree=1", host=host, origin="")
    loc = h1.get("location", "")
    ru = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query).get("redirect_uri", [""])[0]
    t("on www.uaply.net Google is asked to return to www.uaply.net (where the state cookie lives)", ru, "https://www.uaply.net/api/auth/google/callback")
    state_cookie = next((c.split(";")[0] for c in sck if "_oauth=" in c), "")

    class _Stop(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        urllib.request.build_opener(_Stop).open(loc.replace("https://accounts.google.com/o/oauth2/v2/auth", "http://127.0.0.1:%d/auth" % MPORT))
        back = ""
    except urllib.error.HTTPError as e:
        back = e.headers.get("Location", "")
    cb = urllib.parse.urlparse(back)
    s, _, fck, h3 = req("GET", cb.path + "?" + cb.query, host=host, origin="", cookie=state_cookie)
    t("the callback signs the person in and goes back to the app", (s, h3.get("location")), (302, "/?signed_in=google"))
    t("...and they are signed in on www.uaply.net", (me(jar(fck), host=host) or {}).get("email"), "iphone.user@gmail.com")
finally:
    for p in PROCS:
        try:
            p.terminate()
            p.wait(10)
        except Exception:
            pass

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
