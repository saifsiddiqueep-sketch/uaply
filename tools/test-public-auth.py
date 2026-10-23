"""Sign-in on a server run the way the live site runs it: public (any address but 127.0.0.1), behind Render's HTTPS proxy, which sends
X-Forwarded-Proto: https and X-Forwarded-For, for the addresses uaply.net, www.uaply.net and the onrender.com addresses. Starts its own throwaway
servers (a stand-in Google on PORT+1, UAply on PORT, and for the sandbox's emailed-code sign-in a stand-in mail server on PORT+2 and three
sandbox servers on PORT+3 to PORT+5) and stops them at the end, so it needs nothing running:
  python tools/test-public-auth.py [port]          (default 18780; uses that port and the next five)
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
    env = dict(os.environ, HOST=ADDR, UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=DATA, OWNER_PASSWORD="ownerpw", UAPLY_CONFIG_JSON=json.dumps(CFG),
               UAPLY_CF_RANGES="0")                 # Cloudflare's list: the built-in copy (no internet in tests)
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


def req(method, path, body=None, host=SITE, origin="same", cookie="", xff="203.0.113.7", headers=None, port=None):
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
    c = http.client.HTTPConnection(ADDR, port or PORT, timeout=30)
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


def last_code(email, wait=5.0):
    """The newest 6-digit code in the server's test inbox (no real email is connected in this test). A sign-up answers first and emails its
    code a moment later, so this waits up to `wait` seconds for one to be there."""
    end = time.time() + wait
    while True:
        with db() as c:
            row = c.execute("SELECT subject FROM user_mail WHERE to_addr=? ORDER BY id DESC LIMIT 1", (email,)).fetchone()
        m = re.match(r"\s*(\d{6})", row["subject"] if row else "")
        if m or time.time() > end:
            return m.group(1) if m else ""
        time.sleep(0.1)


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
    # ... then the real owner arrives with Google: their own 18+ / Terms tick first, since the one on record is whoever opened the account
    s, out, rck, _ = req("POST", "/api/auth/google/token", {"credential": gtoken(email="owner.of.this@gmail.com", sub="7002")})
    t("Google joining an account whose address was never proven asks for the owner's own tick first (and signs nobody in)", (s, out.get("code"), session_of(rck)), (400, "agree_owner", ""))
    t("...and changes nothing yet: the password is still there", (me(attacker) or {}).get("hasPassword"), True)
    before = int(time.time())
    s, out, rck, _ = req("POST", "/api/auth/google/token", {"credential": gtoken(email="owner.of.this@gmail.com", sub="7002"), "agree": True})
    t("Google with the same Gmail address and the owner's tick signs into that existing account", (s, (out.get("user") or {}).get("email")), (200, "owner.of.this@gmail.com"))
    with db() as c:
        ta = c.execute("SELECT terms_at FROM users WHERE email='owner.of.this@gmail.com'").fetchone()["terms_at"]
    t("...and the 18+ / Terms tick on record is now the owner's (terms_at is this sign-in's)", ta >= before, True)
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
    # the address is the hop the host's proxy added (serve.client_ip), never what the sender wrote before it (October 22 audit: the first
    # entry used to be trusted, so a script that wrote a new made-up address every try was never locked out)
    req("POST", "/api/auth/signup", {"email": "forged.xff@example.com", "password": "the right one 3", "agree": True}, xff="192.0.2.60")
    forged = [req("POST", "/api/auth/login", {"email": "forged.xff@example.com", "password": "wrong %d" % i}, xff="1.2.%d.%d, 198.51.100.200" % (i, i))[0] for i in range(6)]
    t("a script that writes a new made-up X-Forwarded-For first entry every try is still locked out after five (its real hop is the same)", forged, [401] * 5 + [429])
    # behind Cloudflare: the last hop is a Cloudflare server, and CF-Connecting-IP names the visitor; anywhere else that header is ignored
    cf = [req("POST", "/api/auth/login", {"email": "forged.xff@example.com", "password": "wrong cf %d" % i}, xff="9.9.%d.9, 173.245.48.%d" % (i, i + 1),
              headers={"CF-Connecting-IP": "198.51.100.201"})[0] for i in range(6)]
    t("behind Cloudflare the visitor is CF-Connecting-IP: one visitor through six Cloudflare servers is locked out after five", cf, [401] * 5 + [429])
    fake_cf = [req("POST", "/api/auth/login", {"email": "forged.xff@example.com", "password": "wrong fcf %d" % i}, xff="198.51.100.202",
                   headers={"CF-Connecting-IP": "198.51.100.%d" % (50 + i)})[0] for i in range(6)]
    t("...and a CF-Connecting-IP sent from anywhere but Cloudflare is ignored (still locked out after five)", fake_cf, [401] * 5 + [429])
    # many real addresses guessing one password (a botnet): the per-account cap stops it after 20 wrong tries
    req("POST", "/api/auth/signup", {"email": "target@example.com", "password": "the right one 2", "agree": True}, xff="192.0.2.40")
    spoofed = [req("POST", "/api/auth/login", {"email": "target@example.com", "password": "guess %d" % i}, xff="10.%d.%d.9, 198.18.%d.%d" % (i // 200, i % 200, i // 200, i % 200 + 1))[0] for i in range(25)]
    t("guessing from a different real address every try is still stopped (after 20 wrong tries on one account)", (spoofed[:20] == [401] * 20, spoofed[20:]), (True, [429] * 5))

    # ---------- sign-up limits a campus can live with (October 22: 5 an hour per address turned students away) ----------
    camp = [req("POST", "/api/auth/signup", {"email": "student%d@example.com" % i, "password": "campus pass %d" % i, "agree": True},
                xff="5.6.%d.7, 198.51.100.220" % i) for i in range(41)]
    t("40 sign-ups an hour from one campus address work (made-up first entries do not change the count); the 41st is refused",
      ([c[0] for c in camp[:40]] == [200] * 40, camp[40][0], camp[40][1].get("code")), (True, 429, "signup_limit"))
    t("...and it says what to do (wait an hour, or sign in)", "Wait an hour" in camp[40][1].get("error", "") and "sign in" in camp[40][1].get("error", ""), True)
    same = [req("POST", "/api/auth/signup", {"email": "again@example.com", "password": "again pass 1", "agree": True}, xff="198.51.100.221") for _ in range(6)]
    t("one email tried six times from one address: made once, then 'already has an account' four times, then refused",
      ([c[0] for c in same], same[5][1].get("code")), ([200, 409, 409, 409, 409, 429], "signup_email_limit"))
    t("...with what to do (the code in the inbox, or sign in)", "Check your inbox" in same[5][1].get("error", "") and "sign in" in same[5][1].get("error", ""), True)
    t("...while a different email from that address still signs up", req("POST", "/api/auth/signup", {"email": "another@example.com", "password": "another pass 1", "agree": True}, xff="198.51.100.221")[0], 200)
    sys.path.insert(0, ROOT)
    import auth_api  # noqa: E402
    t("the code limits: 3 per account, 80 per address, 5 per address and email, each an hour",
      tuple(getattr(auth_api, k, None) for k in ("CODES_PER_IP_PER_HOUR", "PER_IP_EMAIL_PER_HOUR", "SIGNUPS_PER_HOUR")), (80, 5, 40))
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
    # ---------- the sandbox's emailed-code sign-in (sign-up v2): the real visitor's address, the shared limits, a site-wide cap ----------
    MAILPORT, SBPORT, CAPPORT, CAP2PORT = PORT + 2, PORT + 3, PORT + 4, PORT + 5
    PROCS.append(subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(MAILPORT), os.path.join(DATA, "fake-smtp.jsonl")],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    SBCFG = dict(CFG, smtp={"host": "127.0.0.1", "port": MAILPORT, "starttls": False, "from_addr": "uaply@example.com"})

    def start_sandbox(port, data, extra=None):
        env = dict(os.environ, HOST=ADDR, UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=data, OWNER_PASSWORD="ownerpw", UAPLY_CONFIG_JSON=json.dumps(SBCFG),
                   UAPLY_CF_RANGES="0", **(extra or {}))
        for k in ("ANTHROPIC_API_KEY", "UAPLY_CODE_SIGNIN"):
            env.pop(k, None)
        PROCS.append(subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(port), "sandbox", "--api"], cwd=ROOT, env=env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        for _ in range(80):
            try:
                if req("GET", "/healthz", port=port)[0] == 200:
                    return
            except OSError:
                time.sleep(0.25)
        raise SystemExit("the sandbox test server did not start")

    start_sandbox(SBPORT, DATA + "-sb")                  # the default hour of 500 code emails (one visitor's share: 80)
    t("the sandbox server signs in by emailed code (its mail server is set up)", (req("GET", "/api/auth/providers", port=SBPORT)[1] or {}).get("codeSignin"), True)
    # the code routes count the host's last hop too: a made-up first X-Forwarded-For entry on every try changes nothing
    wrong = [req("POST", "/api/auth/code/verify", {"email": "nobody.%d@example.com" % i, "code": "000000"}, xff="7.7.%d.%d, 198.51.100.230" % (i, i),
                 port=SBPORT)[0] for i in range(21)]
    t("code sign-in: a script writing a new made-up first entry every try is still stopped after 20 (its real hop is the same)",
      (wrong[:20] == [400] * 20, wrong[20]), (True, 429))
    sends = [req("POST", "/api/auth/code/send", {"email": "fresh.%d@example.com" % i}, xff="8.8.%d.%d, 198.51.100.231" % (i // 250, i % 250), port=SBPORT)
             for i in range(81)]
    t("code emails: 80 an hour from one real address, made-up first entries or not (the limit resend_code has), then the plain limit answer",
      ([x[0] for x in sends[:80]] == [200] * 80, sends[80][0], (sends[80][1] or {}).get("code")), (True, 429, "code_limit"))
    t("...while another visitor can still ask for a code", req("POST", "/api/auth/code/send", {"email": "fresh.other@example.com"}, xff="198.51.100.234", port=SBPORT)[0], 200)
    # IPv6: each address is its own connection; the site's share counts the /64 (a campus or a carrier hands out many addresses of one)
    six = [req("POST", "/api/auth/code/send", {"email": "six.%d@example.com" % i}, xff="2001:db8:77:1::%x" % (i + 1), port=SBPORT)[0] for i in range(60)]
    t("IPv6: 60 different addresses of one /64 can each get a code in one hour under the default cap", six, [200] * 60)
    more = [req("POST", "/api/auth/code/send", {"email": "six.more.%d@example.com" % i}, xff="2001:db8:77:1:ffff::%x" % (i + 1), port=SBPORT)[0] for i in range(21)]
    t("...the /64 shares one visitor's 80 of the site's hour: the 81st code from it is held back with the plain limit answer, not 'UAply is busy'",
      (more[:20] == [200] * 20, more[20]), (True, 429))
    t("...while the next /64 is another visitor", req("POST", "/api/auth/code/send", {"email": "six.next@example.com"}, xff="2001:db8:77:2::1", port=SBPORT)[0], 200)
    # Google never calls an older account new: the account was made by this sign-in or it was not (no more "made in the last 60 seconds")
    req("POST", "/api/auth/signup", {"email": "made.before@gmail.com", "password": "made before 1", "agree": True}, xff="198.51.100.232", port=SBPORT)
    s, out, _, _ = req("POST", "/api/auth/google/token", {"credential": gtoken(email="made.before@gmail.com", sub="8101"), "agree": True}, xff="198.51.100.232", port=SBPORT)
    t("Google joins an account a password sign-up made seconds ago (with the owner's tick)", s, 200)
    t("...and does not call it a new account", ((out.get("user") or {}).get("google") or {}).get("new"), False)
    s, out, _, _ = req("POST", "/api/auth/google/token", {"credential": gtoken(email="really.new@gmail.com", sub="8102"), "agree": True}, xff="198.51.100.233", port=SBPORT)
    t("...while an account this Google sign-in made is new", ((out.get("user") or {}).get("google") or {}).get("new"), True)
    s, out, _, _ = req("POST", "/api/auth/google/token", {"credential": gtoken(email="really.new@gmail.com", sub="8102"), "agree": True}, xff="198.51.100.233", port=SBPORT)
    t("...and signing in with Google again a few seconds later is a sign-in, not 'Account created' a second time",
      (s, ((out.get("user") or {}).get("google") or {}).get("new")), (200, False))
    # a ceiling on the code emails the whole site sends in an hour (UAPLY_CODE_SENDS_PER_HOUR; 500 by default, 3 on this server)
    start_sandbox(CAPPORT, DATA + "-cap", {"UAPLY_CODE_SENDS_PER_HOUR": "3"})
    caps = [req("POST", "/api/auth/code/send", {"email": "cap.%d@example.com" % i}, xff="198.51.100.%d" % (240 + i), port=CAPPORT) for i in range(4)]
    t("site-wide: once the hour's code emails are used up, the next visitor (another address, another email) is held back",
      ([c[0] for c in caps], (caps[3][1] or {}).get("code")), ([200, 200, 200, 429], "code_busy"))
    t("...with a plain answer: try again in a few minutes, or use Google", "few minutes" in (caps[3][1] or {}).get("error", "") and "Google" in (caps[3][1] or {}).get("error", ""), True)
    t("...and Create my account is held back the same way", (req("POST", "/api/auth/signup", {"email": "cap.new@example.com", "agree": True, "passwordless": True},
                                                               xff="198.51.100.250", port=CAPPORT)[1] or {}).get("code"), "code_busy")

    # ---------- the site's hour cannot be used up by a few addresses, and an account's owner always gets a code (October 22 review) ----------
    t("one visitor may use 5% of the site's hour of code emails, never less than one connection's own 80: 80 of the default 500",
      (getattr(auth_api, "SITE_SHARE_PERCENT", None), getattr(auth_api, "site_share", lambda: None)()), (5, 80))
    t("...the share counts an IPv6 visitor by its /64, an IPv4 one (also written as IPv6) by its address",
      [getattr(auth_api, "share_key", lambda x: x)(x) for x in ("2001:db8:1:2:3:4:5:6", "198.51.100.7", "::ffff:198.51.100.7")],
      ["2001:db8:1:2::/64", "198.51.100.7", "198.51.100.7"])
    start_sandbox(CAP2PORT, DATA + "-cap2", {"UAPLY_CODE_SENDS_PER_HOUR": "40"})          # 40 an hour, so 2 per address

    def mail_code(addr, after="", wait=6.0):
        end = time.time() + wait
        while time.time() < end:
            try:
                with open(os.path.join(DATA, "fake-smtp.jsonl"), encoding="utf-8") as f:
                    rows = [json.loads(x) for x in f if x.strip()]
            except (OSError, ValueError):
                rows = []
            for r in reversed(rows):
                m = re.search(r"([0-9]{6}) is your UAply (?:verification|sign-in) code", r.get("raw", ""))
                if addr in json.dumps(r.get("to")) and m:
                    if m.group(1) != after:
                        return m.group(1)
                    break
            time.sleep(0.1)
        return ""

    def cookie_named(cookies, name):
        for c in cookies:
            m = re.match(r"(%s=[^;]+)" % re.escape(name), c)
            if m:
                return m.group(1)
        return ""
    send2 = lambda email, xff, cookie="": req("POST", "/api/auth/code/send", {"email": email}, xff=xff, cookie=cookie, port=CAP2PORT)
    # the owner of an account signs in with a code once on their phone: it keeps the known-device cookie and a session
    req("POST", "/api/auth/signup", {"email": "known.owner@example.com", "agree": True, "passwordless": True}, xff="198.51.100.10", port=CAP2PORT)
    c0 = mail_code("known.owner@example.com")
    s, out, cks, _ = req("POST", "/api/auth/code/verify", {"email": "known.owner@example.com", "code": c0, "agree": True}, xff="198.51.100.10", port=CAP2PORT)
    known_ck, sess_ck = cookie_named(cks, "uaply_sandbox_session_known"), cookie_named(cks, "uaply_sandbox_session")
    t("(set-up) the owner's code sign-in gives the known-device cookie and a session", (s, bool(known_ck), bool(sess_ck)), (200, True, True))
    filled = [send2("fill.%d.%d@example.com" % (n, k), "198.51.101.%d" % (n + 1))[0] for n in range(13) for k in range(3)]
    stranger = send2("someone.new@example.com", "198.51.102.1")[1] or {}
    t("(set-up) 13 more addresses use up the rest of the hour (40 here); a newcomer is then told UAply is busy",
      (filled == [200] * 39, stranger.get("code")), (True, "code_busy"))
    t("...the owner's address from a device that never signed in is held back like anyone else", (send2("known.owner@example.com", "198.51.102.2")[1] or {}).get("code"), "code_busy")
    s, out, _, _ = send2("known.owner@example.com", "198.51.102.2", cookie=known_ck)
    c1 = mail_code("known.owner@example.com", after=c0)
    t("...but the owner's known device still gets a code while the site's hour is used up", (s, bool(c1)), (200, True))
    s, out, _, _ = send2("known.owner@example.com", "198.51.102.3", cookie=sess_ck)
    t("...and so does a device signed in to that verified account", (s, bool(mail_code("known.owner@example.com", after=c1))), (200, True))
    t("...while that session asks for another address's code in vain (no pass for other accounts, and nothing said about them)",
      (send2("someone.else@example.com", "198.51.102.3", cookie=sess_ck)[1] or {}).get("code"), "code_busy")
    s, out, ucks, _ = req("POST", "/api/auth/signup", {"email": "unproven@example.com", "password": "unproven pass 1", "agree": True}, xff="198.51.102.4", port=CAP2PORT)
    ujar = cookie_named(ucks, "uaply_sandbox_session")
    t("...and an account nobody proved yet (anyone can open one) gets no pass for Resend", (s, (req("POST", "/api/auth/resend", {}, xff="198.51.102.4", cookie=ujar, port=CAP2PORT)[1] or {}).get("code")),
      (200, "code_busy"))

finally:
    for p in PROCS:
        try:
            p.terminate()
            p.wait(10)
        except Exception:
            pass

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
