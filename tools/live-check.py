"""A check of a running UAply server from the outside, the way a stranger's browser sees it. Run it after every deploy:
  python tools/live-check.py --base https://uaply.onrender.com
  python tools/live-check.py --base http://127.0.0.1:20240          (a local server; tools/run-all-tests.sh does this, never the live site)
Options:
  --expect email,google,payments,persistent   (or --expect all)  a feature that is still off is a FAIL instead of a SKIP. Use it once the
                                               owner has pasted the keys, so a typo in Render's Environment page cannot pass quietly.
  --google-host HOST    where "Continue with Google" must send the browser (default accounts.google.com; the test suite's stand-in Google
                        runs on 127.0.0.1)
  --no-rate-limit       leave out the six wrong logins that prove the sign-in lock-out still answers
  --shields LISTDIR     also checks the site the way Brave Shields sees it: every UAply address the app loads (pages, scripts, /api paths,
                        images) against the ad-block filter lists in LISTDIR (EasyList, EasyPrivacy, uBlock filters, brave/adblock-lists:
                        plain .txt files), in Brave's standard mode (third-party only) and aggressive mode (first-party too), through
                        `node tools/shields.js`; and that the sign-in cookie is first-party (SameSite=Lax, Path=/, Secure on https).
Every line is PASS, FAIL or SKIP (needs ...). The exit code is 1 when any line is FAIL. Standard library only.

What it never does: sign up, sign in, swipe, send email to anyone, open a payment, or read a key. The wrong logins use a made-up address
at example.com that has no account, so nobody is locked out. Sign-up by email code, Google and a test-card purchase need a browser and a
real inbox: tools/ui-live.js does those."""
import argparse
import http.client
import json
import os
import re
import secrets
import ssl
import subprocess
import sys
import time
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--base", required=True, help="the site's address, e.g. https://uaply.onrender.com")
ap.add_argument("--expect", default="", help="comma list of features that must be on: email, google, payments, persistent (or all)")
ap.add_argument("--google-host", default="accounts.google.com")
ap.add_argument("--no-rate-limit", action="store_true")
ap.add_argument("--shields", default="", help="folder of ad-block filter lists (.txt): check no UAply address is blocked (Brave Shields)")
ap.add_argument("--branch", default="dev", help="the branch the site deploys from; its head on GitHub must be the commit the site runs (default dev)")
ap.add_argument("--commit", default="", help="the commit the site must run, instead of asking GitHub for the head of --branch")
ap.add_argument("--timeout", type=float, default=60)
A = ap.parse_args()

BASE = A.base.rstrip("/")
U = urllib.parse.urlsplit(BASE)
if U.scheme not in ("http", "https") or not U.hostname:
    sys.exit("--base must look like https://uaply.onrender.com")
HTTPS = U.scheme == "https"
HOSTPORT = U.netloc
EXPECT = {"email", "google", "payments", "persistent"} if A.expect.strip() == "all" else {x.strip() for x in A.expect.split(",") if x.strip()}
COUNT = {"PASS": 0, "FAIL": 0, "SKIP": 0}


def line(kind, name, extra=""):
    COUNT[kind] += 1
    print("%s %s%s" % (kind, name, ("  -> " + extra) if extra else ""))
    sys.stdout.flush()


def t(name, ok, extra=""):
    line("PASS" if ok else "FAIL", name, "" if ok else extra)
    return ok


def skip(name, needs):
    line("SKIP", name + " (needs " + needs + ")")


def off(feature, name, needs):
    """A feature that is not switched on: SKIP, or FAIL when --expect says it must be on by now."""
    if feature in EXPECT:
        line("FAIL", name, "it is off, and --expect says it must be on (" + needs + ")")
    else:
        skip(name, needs)


def info(text):
    print("     " + text)


def req(method, path, body=None, headers=None, raw=None):
    """One request, no redirects followed. Returns (status, headers with lower-case names (Set-Cookie joined by newlines), body bytes)."""
    h = {"Host": HOSTPORT, "User-Agent": "uaply-live-check/1", "Accept": "*/*"}
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
        h["Origin"] = BASE
    h.update(headers or {})
    conn = (http.client.HTTPSConnection(U.hostname, U.port or 443, timeout=A.timeout, context=ssl.create_default_context()) if HTTPS
            else http.client.HTTPConnection(U.hostname, U.port or 80, timeout=A.timeout))
    try:
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse()
        out = r.read()
        hd = {}
        for k, v in r.getheaders():
            k = k.lower()
            hd[k] = (hd[k] + "\n" + v) if k in hd else v
        return r.status, hd, out
    finally:
        conn.close()


def get_json(path):
    s, h, b = req("GET", path)
    try:
        return s, h, json.loads(b.decode("utf-8"))
    except ValueError:
        return s, h, None


def safe(fn, name):
    """A check that crashes (the site is down, a reply is not JSON) is a FAIL with the reason, and the other checks still run."""
    try:
        fn()
    except Exception as e:
        line("FAIL", name, "%s: %s" % (type(e).__name__, str(e)[:200]))


print("UAply live check of %s at %s UTC" % (BASE, time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())))
STATUS = {}


# ---------- the server answers ----------
def health():
    t0 = time.time()
    s, _, j = get_json("/healthz")
    t("/healthz answers {\"ok\": true}", s == 200 and isinstance(j, dict) and j.get("ok") is True, "%s %r" % (s, j))
    info("answered in %.2f s" % (time.time() - t0))


safe(health, "/healthz answers")


def home():
    s, h, b = req("GET", "/")
    page = b.decode("utf-8", "replace")
    t("the home page opens (200, HTML, title UAply)", s == 200 and "text/html" in h.get("content-type", "") and "<title>UAply</title>" in page,
      "%s %s, %d bytes" % (s, h.get("content-type"), len(b)))
    scripts = re.findall(r'<script src="([^"]+)"', page)
    t("the home page carries the app (an iframe and the shared scripts)", "<iframe" in page and len(scripts) >= 3, "%d scripts" % len(scripts))
    # the app is built in the browser from these files and the production page: each one must load, or a visitor sees a blank screen
    bad = []
    for src in [urllib.parse.urljoin("/", x) for x in scripts] + ["/prod-index.html"]:
        s2, h2, b2 = req("GET", src)
        if s2 != 200 or len(b2) < 200 or ("javascript" not in h2.get("content-type", "") and not src.endswith(".html")):
            bad.append("%s %s %s" % (src, s2, h2.get("content-type")))
    t("every script of the app and the production page load (%d files)" % (len(scripts) + 1), not bad, "; ".join(bad))
    # the headers a public server must send (tools/test-public.py checks the same on a local copy)
    t("header X-Content-Type-Options: nosniff", h.get("x-content-type-options") == "nosniff", repr(h.get("x-content-type-options")))
    t("header X-Frame-Options: SAMEORIGIN (other sites cannot frame UAply)", h.get("x-frame-options") == "SAMEORIGIN", repr(h.get("x-frame-options")))
    t("header Referrer-Policy: strict-origin-when-cross-origin", h.get("referrer-policy") == "strict-origin-when-cross-origin", repr(h.get("referrer-policy")))
    t("header Cache-Control: no-store (a shared computer never shows the last person's page)", "no-store" in h.get("cache-control", ""), repr(h.get("cache-control")))
    t("header Content-Security-Policy: frame-ancestors 'self', object-src 'none'", all(x in h.get("content-security-policy", "") for x in ("frame-ancestors 'self'", "object-src 'none'")),
      repr(h.get("content-security-policy")))
    origin_server = h.get("x-render-origin-server") or h.get("server", "")
    t("the server names no Python version (scanners match on it)", "Python/" not in origin_server, repr(origin_server))
    if HTTPS:
        hsts = h.get("strict-transport-security", "")
        m = re.search(r"max-age=(\d+)", hsts)
        t("header Strict-Transport-Security (HTTPS only, at least 180 days)", bool(m) and int(m.group(1)) >= 180 * 86400, repr(hsts))
    else:
        skip("header Strict-Transport-Security", "an https:// address; a local server sends it only behind an HTTPS proxy")
    t("no server error text in the home page", "Traceback" not in page and "Error response" not in page, "")


safe(home, "the home page")


# ---------- what is switched on ----------
def status():
    s, _, j = get_json("/api/status")
    if s == 200 and isinstance(j, dict) and j.get("ok") is True:
        STATUS.update(j, source="/api/status")
        odd = {k: v for k, v in j.items() if not (isinstance(v, bool) or v is None or (k == "commit" and isinstance(v, str) and re.fullmatch(r"[0-9a-f]{7}", v)))}
        t("/api/status answers with yes/no facts only (and the deployed commit's short id)", not odd, "a value that is not yes/no: %r" % odd)
        return
    # an older server (before /api/status): the same facts from the endpoints the app already reads
    skip("/api/status", "a deploy of the commit that adds it; the facts below come from /api/auth/providers and /api/billing/status")
    _, _, p = get_json("/api/auth/providers")
    _, _, b = get_json("/api/billing/status")
    _, _, c = get_json("/api/chat/config")
    p, b, c = p or {}, b or {}, c or {}
    STATUS.update(source="older endpoints", persistent=None, email=bool(p.get("canEmail")), google=bool(p.get("googleRedirect")),
                  googleButton=bool(p.get("google")), payments=bool(b.get("enabled")), paymentsTest=bool(b.get("enabled") and b.get("test")),
                  paymentsWebhook=None, ai=bool(c.get("ai")), public=(c.get("owner") is False) if "owner" in c else None)


safe(status, "what is switched on")
if STATUS:
    def yn(v):
        return "unknown" if v is None else ("on" if v else "off")
    info("switched on (%s): data on a persistent disk: %s | email: %s | Google sign-in: %s | payments: %s%s | AI answers: %s"
         % (STATUS.get("source"), {True: "yes", False: "NO", None: "unknown"}[STATUS.get("persistent")], yn(STATUS.get("email")),
            yn(STATUS.get("google")) if STATUS.get("google") or not STATUS.get("googleButton") else "button only (no client secret)",
            yn(STATUS.get("payments")), (", test mode" if STATUS.get("paymentsTest") else ", LIVE mode") if STATUS.get("payments") else "",
            yn(STATUS.get("ai"))))
PUBLIC = STATUS.get("public") is not False          # unknown counts as public: the stricter checks


def persistent():
    v = STATUS.get("persistent")
    if v is True:
        t("accounts are kept on a persistent disk (they survive a deploy)", True)
    elif v is False:
        off("persistent", "accounts are kept on a persistent disk", "the Render disk: Disks, add uaply-data at /var/data, then UAPLY_DATA_DIR=/var/data. "
            "Until then every account vanishes at the next deploy")
    else:
        off("persistent", "accounts are kept on a persistent disk", "/api/status to say so (a deploy of the commit that adds it), or a host that can tell" if STATUS.get("source") != "/api/status"
            else "a host that can tell (only Render reports its disk)")


safe(persistent, "persistent disk")


# ---------- the deploy is the latest push ----------
def deployed():
    """The commit the site runs (/api/status, from Render's RENDER_GIT_COMMIT) against the head of the branch on GitHub. On October 17 every
    deploy had been started by hand: a push to dev had never redeployed the site, and nothing said so."""
    live = STATUS.get("commit")
    if not live:
        if STATUS.get("source") != "/api/status" or "commit" not in STATUS:
            skip("the site runs the latest push to %s" % A.branch, "a deploy of the commit that adds the commit to /api/status")
        else:
            skip("the site runs the latest push to %s" % A.branch, "a server on Render (it says which commit it runs through RENDER_GIT_COMMIT)")
        return
    want, where = (A.commit or "").strip().lower(), "--commit"
    if not want:
        try:
            out = subprocess.run(["git", "ls-remote", "origin", "refs/heads/" + A.branch], cwd=ROOT, capture_output=True, text=True, timeout=30).stdout
            want, where = (out.split() or [""])[0], "origin/" + A.branch
        except (OSError, subprocess.SubprocessError) as e:
            skip("the site runs the latest push to %s" % A.branch, "git and this repository's GitHub remote (%s), or --commit SHA" % type(e).__name__)
            return
    if not re.fullmatch(r"[0-9a-f]{7,40}", want):
        skip("the site runs the latest push to %s" % A.branch, "the head of %s from GitHub (git ls-remote gave nothing), or --commit SHA" % where)
        return
    info("the site runs commit %s; %s is %s" % (live, where, want[:7]))
    t("the site runs the latest push (%s = %s)" % (where, want[:7]), want.startswith(live),
      "the site runs %s, %s is %s. If the push was more than 10 minutes ago it was never deployed: in Render, Manual Deploy > Deploy latest "
      "commit, then fix auto-deploy (DEPLOY.md, \"Auto-deploy\")" % (live, where, want[:7]))


safe(deployed, "the deployed commit")


# ---------- the job list ----------
def jobs():
    t0 = time.time()
    s, _, j = get_json("/api/jobs")
    took = time.time() - t0
    if not t("/api/jobs answers with a job list", s == 200 and isinstance(j, dict) and isinstance(j.get("jobs"), list), "%s" % s):
        return
    js = j["jobs"]
    t("/api/jobs has real postings (at least 50)", len(js) >= 50, "%d jobs" % len(js))
    no_url = [x.get("id") for x in js if not (isinstance(x.get("url"), str) and re.match(r"^https?://", x["url"]))]
    no_src = [x.get("id") for x in js if not (isinstance(x.get("source"), str) and x["source"].strip())]
    t("every card has a link to the employer (url)", not no_url, "%d without: ids %s" % (len(no_url), no_url[:5]))
    t("every card says where it came from (source, the \"via\" credit)", not no_src, "%d without: ids %s" % (len(no_src), no_src[:5]))
    t("every card has a company and a role", all(x.get("co") and x.get("role") for x in js), "")
    src = j.get("sources") if isinstance(j.get("sources"), dict) else {}
    counts = {}
    for x in js:
        counts[x.get("source", "?")] = counts.get(x.get("source", "?"), 0) + 1
    info("%d jobs in %.1f s from %d sources; most: %s" % (len(js), took, len(counts),
         ", ".join("%s %d" % kv for kv in sorted(counts.items(), key=lambda kv: -kv[1])[:6])))
    quiet = sorted(k for k, v in src.items() if not re.match(r"^[1-9]\d* jobs?$", str(v)))
    if quiet:
        info("feeds with nothing right now: " + "; ".join("%s (%s)" % (k, src[k]) for k in quiet))
    if j.get("fetched_at"):
        age = (time.time() - j["fetched_at"]) / 3600
        t("the job list is fresh (read in the last 24 hours)", age < 24, "%.1f hours old" % age)


safe(jobs, "/api/jobs")


# ---------- accounts ----------
def me():
    s, h, j = get_json("/api/auth/me")
    t("/api/auth/me answers {\"user\": null} to a visitor with no cookie", s == 200 and j == {"user": None}, "%s %r" % (s, j))
    t("/api/auth/me sets no cookie for a visitor", "set-cookie" not in h, h.get("set-cookie", ""))


safe(me, "/api/auth/me")


def cross_site():
    s, _, _ = req("POST", "/api/auth/login", {"email": "nobody@example.com", "password": "x"}, headers={"Origin": "https://evil.example"})
    t("a sign-in posted from another site is refused (403)", s == 403, str(s))
    s, _, _ = req("POST", "/api/auth/signup", raw=b'{"email":"a@example.com"}', headers={"Content-Type": "application/json"})
    t("a sign-up with no Origin header is refused (403)", s == 403, str(s))


safe(cross_site, "cross-site requests")


def rate_limit():
    if A.no_rate_limit:
        skip("the sign-in lock-out still answers", "a run without --no-rate-limit")
        return
    who = "live-check-%s@example.com" % secrets.token_hex(6)          # no such account: nobody real is locked out
    got = []
    for _ in range(6):
        got.append(req("POST", "/api/auth/login", {"email": who, "password": "wrong password %s" % secrets.token_hex(3)})[0])
    t("wrong passwords answer 'Wrong email or password' (401)", got[:5] == [401] * 5, "statuses %s" % got)
    t("the 6th wrong password in a row is locked out (429)", got[5] == 429, "statuses %s" % got)


safe(rate_limit, "sign-in lock-out")


def owner_pages():
    if not PUBLIC:
        skip("owner pages need the owner password", "a public server (this one says it runs on the owner's own computer, where they are open)")
        return
    for p in ("/setup", "/outbox", "/api/outbox", "/feedback"):
        s = req("GET", p)[0]
        t("%s is closed to visitors (401 with the owner password set, 403 without)" % p, s in (401, 403), str(s))


safe(owner_pages, "owner pages")


def paths():
    for p in ("/legal//etc/passwd", "/legal/..%2f..%2fserve.py", "/../serve.py", "/uaply-config.json", "/data/uaply.db"):
        s, _, b = req("GET", p)
        t("%s reads nothing from the server" % p, s != 200 or (b"import " not in b and b"root:" not in b and b"smtp" not in b.lower()), str(s))


safe(paths, "paths outside the site")


# ---------- the legal pages and Support ----------
def legal():
    s, h, _ = req("GET", "/legal")
    t("/legal (no slash) goes to the legal pages", s in (301, 302) and h.get("location", "").endswith("/legal/"), "%s %s" % (s, h.get("location")))
    for name, title in (("", "UAply legal"), ("terms.html", "UAply Terms of Service"), ("privacy.html", "UAply Privacy Policy"),
                        ("ai-and-employment.html", "UAply AI and matching"), ("copyright.html", "UAply Copyright and content"),
                        ("support.html", "UAply Support")):
        s, h, b = req("GET", "/legal/" + name)
        page = b.decode("utf-8", "replace")
        t("/legal/%s opens with the title \"%s\"" % (name, title), s == 200 and ("<title>%s</title>" % title) in page, "%s, %d bytes" % (s, len(b)))
        if name == "support.html":
            t("/legal/support.html gives a way to reach a person (an email address)", bool(re.search(r"mailto:[^\"']+@", page)), "")


safe(legal, "legal pages")


# ---------- email ----------
def email():
    who = "live-check-%s@example.com" % secrets.token_hex(6)        # no account: nothing is ever emailed
    s, _, b = req("POST", "/api/auth/forgot", {"email": who})
    j = json.loads(b.decode("utf-8")) if b else {}
    if STATUS.get("email"):
        t("email is on: Forgot password answers without saying whether the address has an account", s == 200 and j.get("ok") is True and j.get("delivery") == "sent", "%s %r" % (s, j))
        skip("sign-up by email code reaches a real inbox", "tools/ui-live.js --email you+tag@gmail.com and the code from that inbox")
        s2, _, _ = req("POST", "/api/email/events", {"event": "hard_bounce", "email": who})        # no secret: must be refused, never recorded
        t("the bounce webhook refuses a call without the shared secret", s2 in (401, 404), str(s2))
        if STATUS.get("emailEvents"):
            t("bounces and complaints from Brevo are switched on (email_events_secret)", True)
        elif STATUS.get("source") == "/api/status":
            off("emailEvents", "bounces and complaints from Brevo reach UAply", "email_events_secret in UAPLY_CONFIG_JSON and the Brevo webhook (DEPLOY.md, Email: bounces)")
    else:
        t("email is off: Forgot password says plainly it is not available (never promises a link)", s == 200 and j.get("delivery") == ("unavailable" if PUBLIC else "delivered_test"), "%s %r" % (s, j))
        off("email", "email is on (sign-up codes, receipts, password resets)", "the Brevo SMTP key in UAPLY_CONFIG_JSON (the smtp block); the log must say email: on")


safe(email, "email")


# ---------- Continue with Google ----------
def google():
    _, _, p = get_json("/api/auth/providers")
    p = p or {}
    if not STATUS.get("google"):
        s, h, _ = req("GET", "/api/auth/google/start")
        t("Google is off: the app is told so (no Google button) and /api/auth/google/start says off", not p.get("googleRedirect") and s == 302 and h.get("location", "").endswith("/?auth_error=off"),
          "%s %s %r" % (s, h.get("location"), p))
        off("google", "Continue with Google", "the client ID and client secret in UAPLY_CONFIG_JSON (the google block); the log must say Google sign-in: on")
        return
    want_cb = BASE + "/api/auth/google/callback"
    t("Google is on: the app is told to show the full-page Continue with Google", p.get("googleRedirect") is True and p.get("googleRedirectUri") == want_cb, "%r" % p)
    s, h, _ = req("GET", "/api/auth/google/start")
    loc = h.get("location", "")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(loc).query)
    t("/api/auth/google/start sends the browser to %s" % A.google_host, s == 302 and urllib.parse.urlsplit(loc).netloc == A.google_host, "%s %s" % (s, loc[:120]))
    t("...with this site's own callback as redirect_uri", (q.get("redirect_uri") or [""])[0] == want_cb, (q.get("redirect_uri") or [""])[0])
    t("...asking only for openid and email, with PKCE and a state", set((q.get("scope") or [""])[0].split()) == {"openid", "email"} and
      (q.get("code_challenge_method") or [""])[0] == "S256" and bool((q.get("state") or [""])[0]) and (q.get("response_type") or [""])[0] == "code", repr({k: v[0] for k, v in q.items() if k != "code_challenge"})[:200])
    ck = [c for c in h.get("set-cookie", "").split("\n") if "_oauth=" in c]
    t("...and a short-lived HttpOnly, SameSite=Lax state cookie%s" % (", Secure" if HTTPS else ""),
      bool(ck) and "HttpOnly" in ck[0] and "SameSite=Lax" in ck[0] and (not HTTPS or "Secure" in ck[0]), ck[0] if ck else "no state cookie")
    if A.google_host != "accounts.google.com" or s != 302:
        return
    # Google's own first page: a wrong client or a missing redirect address shows up here as Google's error page. Nobody signs in.
    gu = urllib.parse.urlsplit(loc)
    c = http.client.HTTPSConnection(gu.netloc, timeout=A.timeout, context=ssl.create_default_context())
    try:
        c.request("GET", gu.path + "?" + gu.query, headers={"User-Agent": "Mozilla/5.0 (uaply-live-check)", "Accept-Language": "en"})
        r = c.getresponse()
        body = r.read(400000).decode("utf-8", "replace")
        gl = r.getheader("Location") or ""
    finally:
        c.close()
    err = re.search(r"(redirect_uri_mismatch|invalid_client|deleted_client|org_internal|access_denied|invalid_request|origin_mismatch)", body + gl)
    t("Google accepts this client and callback (its sign-in page opens, no Error 400/401)", r.status in (200, 302) and not err,
      "%s %s" % (r.status, err.group(1) if err else gl[:100]))
    skip("a real Google account signs in", "a person: this check never signs in to Google (tools/ui-live.js checks the button and the redirect)")


safe(google, "Continue with Google")


# ---------- Plan and billing ----------
def payments():
    _, _, b = get_json("/api/billing/status")
    b = b or {}
    plans = b.get("plans") or {}
    t("the plans and prices are Free $0, Plus $9.99, Pro $19.99", [plans.get(k, {}).get("price") for k in ("free", "plus", "pro")] == [0, 9.99, 19.99], repr(plans)[:160])
    s, _, raw = req("POST", "/api/billing/webhook", raw=b'{"id":"evt_forged","type":"checkout.session.completed"}', headers={"Content-Type": "application/json", "Stripe-Signature": "t=1,v1=00"})
    t("a webhook without Stripe's signature is refused (400)", s == 400, "%s %s" % (s, raw[:80]))
    s, _, _ = req("POST", "/api/billing/checkout", {"plan": "plus"})
    if not STATUS.get("payments"):
        t("payments are off: Plan & billing says free during early access, no buy buttons", b.get("enabled") is False and (b.get("early") is True) == PUBLIC and b.get("plan") == "free", repr({k: b.get(k) for k in ("enabled", "early", "buttons")}))
        t("payments are off: a checkout is refused (503)", s == 503, str(s))
        off("payments", "a Stripe test-card purchase", "STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_PLUS and STRIPE_PRICE_PRO in Render; then tools/ui-live.js --stripe-test")
        return
    t("payments are on: Plan & billing offers real buttons (not early access)", b.get("enabled") is True and b.get("buttons") is True and b.get("early") is False, repr({k: b.get(k) for k in ("enabled", "early", "buttons")}))
    t("payments are on: a checkout with no account is refused (401, sign in first)", s == 401, str(s))
    if STATUS.get("paymentsWebhook") is not None:
        t("payments are on with the webhook secret set (otherwise people pay and never get the plan)", STATUS["paymentsWebhook"] is True, "STRIPE_WEBHOOK_SECRET is missing or does not start with whsec_")
    info("payments are in %s mode%s" % ("TEST" if STATUS.get("paymentsTest") else "LIVE",
         ": test cards work here (tools/ui-live.js --stripe-test)" if STATUS.get("paymentsTest") else
         ": test cards cannot unlock a plan here, and this check never uses a real card"))
    skip("a purchase goes through and the plan reads Plus", "tools/ui-live.js --email ... --stripe-test (test-mode keys only)")


safe(payments, "Plan and billing")


# ---------- the help assistant and the apply settings ----------
def help_and_apply():
    s, _, b = req("POST", "/api/chat", {"messages": [{"role": "user", "content": "How do I apply?"}]})
    j = json.loads(b.decode("utf-8")) if b else {}
    src = [x.get("id") for x in (j.get("sources") or [])]
    t("the help assistant answers \"How do I apply?\" from its swipe-right article", s == 200 and bool(j.get("answer")) and "swipe-right" in src, "%s %r" % (s, (j.get("answer") or j.get("error") or "")[:100]))
    _, _, c = get_json("/api/apply/config")
    c = c or {}
    t("/api/apply/config answers with the delivery mode", c.get("mode") in ("test", "live"), repr(c))
    info("delivery mode: %s (%s)" % (c.get("mode"), "nothing is sent to any employer" if c.get("mode") == "test" else "applications go to employers who agreed"))


safe(help_and_apply, "help and apply settings")

# ---------- Brave Shields: filter lists and the sign-in cookie ----------
SHIELD_URLS = ["/", "/legal/terms.html", "/legal/support.html", "/prod-index.html", "/help/articles.json", "/favicon-32.png?v=2", "/favicon-192.png?v=2",
               "/apple-touch-icon.png?v=2"] + ["/uaply-%s.js" % n for n in ("nav", "live", "profile", "chat", "learn", "envs")] + [
               "/api/" + n for n in ("auth/me", "auth/providers", "auth/signup", "auth/login", "auth/logout", "auth/verify", "auth/google/start",
                                     "billing/status", "billing/checkout", "billing/portal", "apply", "apply/config", "decision", "jobs", "profile",
                                     "feedback", "chat", "chat/config", "status")] + ["/outbox", "/feedback"]


def shields():
    kind = lambda u: "script" if u.endswith(".js") else "image" if ".png" in u else "document" if u in ("/", "/legal/support.html", "/outbox") else \
        "subdocument" if u.startswith("/legal/") else "xmlhttprequest"
    lst = [[BASE + u, kind(u)] for u in SHIELD_URLS]
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run(["node", os.path.join(here, "shields.js"), A.shields, "-", "x", BASE + "/"], input=json.dumps(lst), capture_output=True, text=True, timeout=900)
    rows = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    t("shields: the filter lists were read (%d addresses checked)" % len(rows), r.returncode == 0 and len(rows) == len(lst), (r.stderr or "")[-200:])
    for mode in ("standard", "aggressive"):
        bad = [x["url"] + " by " + x[mode] for x in rows if x[mode]]
        t("shields (%s mode): no UAply address is blocked by any filter rule" % mode, not bad, " | ".join(bad[:4]))
    s2, h, _ = req("POST", "/api/auth/logout", {})
    ck = h.get("set-cookie", "")
    t("shields: the sign-in cookie is first-party: HttpOnly, SameSite=Lax, Path=/" + (", Secure" if HTTPS else ""),
      bool(ck) and "SameSite=Lax" in ck and "Path=/" in ck and "HttpOnly" in ck and (not HTTPS or "Secure" in ck), "%s %r" % (s2, ck[:160]))


if A.shields:
    safe(shields, "Brave Shields")

print("\n%d passed, %d failed, %d skipped" % (COUNT["PASS"], COUNT["FAIL"], COUNT["SKIP"]))
print("%d / %d" % (COUNT["PASS"], COUNT["PASS"] + COUNT["FAIL"]))
sys.exit(1 if COUNT["FAIL"] else 0)
