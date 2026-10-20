"""The public address (UAPLY_PUBLIC_URL), the move to it, the search tags and a free-only launch (UAPLY_PLANS_HIDDEN). No network; under a minute.
  python tools/test-public-url.py [port]        (default 18820; uses port and port+1)
  1. UAPLY_PUBLIC_URL: what is accepted, and that it wins over public_url for email links and the Google fallback
  2. a server with it set: pages on another address get a 301 to the same path and query on the public host (GET and HEAD); /api/ and /healthz
     never move; a forged Host, an absolute address in the request line or a missing Host never send anyone to another site
  3. the canonical link, the site's name on the home page, /sitemap.xml and the Sitemap line in robots.txt
  4. a server without it (the sandbox, dev, this computer): nothing moved, nothing added
  5. plans hidden: the billing status says so, checkout answers 403, the assistant's plans answer never says Choose Plus"""
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import shutil
import time
import urllib.parse
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18820
TMP = tempfile.mkdtemp(prefix="uaply-puburl-")
R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


# ---------- 1. the variable itself (in this process) ----------
os.environ["UAPLY_CONFIG_FILE"] = "none"
os.environ["UAPLY_CONFIG_JSON"] = json.dumps({"public_url": "https://other.example.com", "google": {"public_url": "https://g.example.com"}})
import uaply_api  # noqa: E402
import google_auth  # noqa: E402
import billing_api  # noqa: E402
import chat_api  # noqa: E402


def env_url(v):
    if v is None:
        os.environ.pop("UAPLY_PUBLIC_URL", None)
    else:
        os.environ["UAPLY_PUBLIC_URL"] = v
    return uaply_api.public_url_env()


for v, want in (("https://uaply.net", "https://uaply.net"), ("https://uaply.net/", "https://uaply.net"), ("  HTTPS://UAPLY.NET//  ", "https://uaply.net"),
                ("https://uaply.net:8443", "https://uaply.net:8443"), ("http://uaply.net", ""), ("https://uaply.net/app", ""), ("https://ua ply.net", ""),
                ("https://user@uaply.net", ""), ("https://evil.com#@uaply.net", ""), ("https://uaply.net?x=1", ""), ("https://", ""), ("uaply.net", ""),
                ("https://uaply.net\r\nX-Evil: 1", ""), ("", ""), (None, "")):
    t("UAPLY_PUBLIC_URL=%r is taken as %r" % (v, want), env_url(v), want)
env_url("https://uaply.net")
cfg = uaply_api.config()
t("UAPLY_PUBLIC_URL wins over public_url for links in emails", uaply_api._site_base(cfg, "https://uaply-dev.onrender.com"), "https://uaply.net")
t("...and over google.public_url for the Google sign-in fallback", google_auth._settings()["public_url"], "https://uaply.net")
env_url(None)
t("unset: public_url in UAPLY_CONFIG_JSON is used as before", uaply_api._site_base(cfg, "https://uaply-dev.onrender.com"), "https://other.example.com")
t("unset: google.public_url is used as before", google_auth._settings()["public_url"], "https://g.example.com")
env_url("https://uaply.net/path")
t("an invalid UAPLY_PUBLIC_URL is ignored, not half-used", uaply_api._site_base(cfg), "https://other.example.com")
env_url(None)

# the assistant's plans answer on the release build with Stripe keys set: "Choose Plus" normally, never while plans are hidden
os.environ.update(STRIPE_SECRET_KEY="sk_test_mockkey123456", STRIPE_PRICE_PLUS="price_plus1", STRIPE_PRICE_PRO="price_pro1")
chat_api.RELEASE = True


def plans_answer():
    return next((a["body"] for a in chat_api.articles() if a["id"] == "plans"), "")


os.environ.pop("UAPLY_PLANS_HIDDEN", None)
t("plans shown: the assistant's plans answer says to tap Choose Plus (so the next check means something)", "Choose Plus" in plans_answer(), True)
os.environ["UAPLY_PLANS_HIDDEN"] = "1"
t("plans hidden: the assistant's plans answer never says Choose Plus or Choose Pro", ("Choose Plus" in plans_answer(), "Choose Pro" in plans_answer()), (False, False))
t("plans hidden: ...and says Plus and Pro are coming soon", "coming soon" in plans_answer(), True)
t("plans hidden: billing_api.hidden()", billing_api.hidden(), True)
os.environ["UAPLY_PLANS_HIDDEN"] = "0"
t("UAPLY_PLANS_HIDDEN=0 is off", billing_api.hidden(), False)
os.environ.pop("UAPLY_PLANS_HIDDEN", None)
os.environ["UAPLY_CONFIG_JSON"] = json.dumps({"plans_hidden": True})
t('"plans_hidden": true in UAPLY_CONFIG_JSON hides them too', billing_api.hidden(), True)
os.environ["UAPLY_CONFIG_JSON"] = json.dumps({"plans_hidden": "yes"})
t('"plans_hidden": "yes" (not true) does not', billing_api.hidden(), False)
for k in ("STRIPE_SECRET_KEY", "STRIPE_PRICE_PLUS", "STRIPE_PRICE_PRO", "UAPLY_CONFIG_JSON"):
    os.environ.pop(k, None)


# ---------- servers ----------
def start(port, extra):
    env = dict(os.environ, UAPLY_DATA_DIR=os.path.join(TMP, str(port)), HOST="0.0.0.0", UAPLY_CONFIG_FILE="none",
               UAPLY_CONFIG_JSON='{"feeds":[],"smtp":{},"owner_copy":""}', **extra)
    for k in ("UAPLY_PUBLIC_URL", "UAPLY_PLANS_HIDDEN"):
        if k not in extra:
            env.pop(k, None)
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(port), os.path.join(ROOT, "dev"), "--api"], env=env,
                         stdout=subprocess.DEVNULL, stderr=open(os.path.join(TMP, "log-%d.txt" % port), "w"), cwd=ROOT)
    for _ in range(80):
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            c.request("GET", "/healthz")
            if c.getresponse().status == 200:
                return p
        except OSError:
            time.sleep(0.25)
    raise SystemExit("server on %d did not start" % port)


def req(port, method, path, host, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": host, "X-Forwarded-Proto": "https"}
    h.update(headers or {})
    c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    for k, v in h.items():
        c.putheader(k, v)
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        c.putheader("Content-Type", "application/json")
        c.putheader("Content-Length", str(len(data)))
    c.endheaders(data)
    r = c.getresponse()
    out = (r.status, r.getheader("Location"), r.read().decode("utf-8", "replace"), r.getheader("Content-Length"))
    c.close()
    return out


def raw(port, data):
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.sendall(data)
    got = b""
    try:
        while True:
            b = s.recv(65536)
            if not b:
                break
            got += b
    except socket.timeout:
        pass
    s.close()
    head = got.split(b"\r\n\r\n", 1)[0].decode("latin-1")
    loc = next((ln.split(":", 1)[1].strip() for ln in head.split("\r\n") if ln.lower().startswith("location:")), None)
    return head.split("\r\n", 1)[0], loc


A, B = PORT, PORT + 1
pa = start(A, {"UAPLY_PUBLIC_URL": "https://uaply.net/", "UAPLY_PLANS_HIDDEN": "1"})
pb = start(B, {})
try:
    # ---------- 2. the move to the public host ----------
    mv = req(A, "GET", "/", "www.uaply.net")
    t("GET / on www.uaply.net: 200, the 'UAply has moved to uaply.net' page (not a blind 301)", (mv[0], mv[1], "UAply has moved to uaply.net" in mv[2]), (200, None, True))
    t("the moved page: with nothing to keep it goes on to https://uaply.net/ at once (script and, without script, a meta refresh)",
      ('location.replace("https://uaply.net/")' in mv[2], '<meta http-equiv="refresh" content="0;url=https://uaply.net/">' in mv[2]), (True, True))
    t("the moved page: it looks for this instance's own storage key (dev/index.html's KEY)", 'var K="hireswipe.dev.v1"' in mv[2], True)
    t("the moved page: offers Save a backup and Continue to uaply.net with the ?moved=1 hint",
      ('id="save"' in mv[2], 'href="https://uaply.net/?moved=1"' in mv[2]), (True, True))
    t("the moved page: its canonical is the public home page, and it sends nothing anywhere (no fetch, no form)",
      ('<link rel="canonical" href="https://uaply.net/">' in mv[2], "fetch(" in mv[2] or "<form" in mv[2]), (True, False))
    mq = req(A, "GET", "/?billing=success", "uaply-dev.onrender.com")
    t("GET /?billing=success on the onrender.com address: the moved page goes on to the same query on uaply.net",
      (mq[0], 'location.replace("https://uaply.net/?billing=success")' in mq[2]), (200, True))
    t("the home page of uaply.net itself is never the moved page", "UAply has moved" in req(A, "GET", "/", "uaply.net")[2], False)
    t("GET a legal page with a query on the onrender.com address: 301 to the same path and query",
      req(A, "GET", "/legal/terms.html?a=1&b=2", "uaply-dev.onrender.com")[:2], (301, "https://uaply.net/legal/terms.html?a=1&b=2"))
    t("HEAD / on www.uaply.net: 301 too", req(A, "HEAD", "/", "www.uaply.net")[:2], (301, "https://uaply.net/"))
    t("robots.txt on www.uaply.net: 301 (crawlers follow it)", req(A, "GET", "/robots.txt", "www.uaply.net")[:2], (301, "https://uaply.net/robots.txt"))
    t("GET / on uaply.net itself: 200, no move", req(A, "GET", "/", "uaply.net")[:2], (200, None))
    t("GET / on UAPLY.NET:443 (same host, other spelling): 200, no move", req(A, "GET", "/", "UAPLY.NET:443")[:2], (200, None))
    t("/api/status on www.uaply.net: answered there, never moved", req(A, "GET", "/api/status", "www.uaply.net")[:2], (200, None))
    t("/api/auth/google/callback on the onrender.com address: never moved (Google returns to the address it was started on)",
      req(A, "GET", "/api/auth/google/callback?code=x&state=y", "uaply-dev.onrender.com")[0] != 301, True)
    t("/healthz on the onrender.com address: 200, never moved (Render's health check)", req(A, "GET", "/healthz", "uaply-dev.onrender.com")[:2], (200, None))
    t("HEAD /healthz on the onrender.com address: 200", req(A, "HEAD", "/healthz", "uaply-dev.onrender.com")[:2], (200, None))
    st = req(A, "POST", "/api/billing/webhook", "uaply-dev.onrender.com", body={"type": "x"}, headers={"Stripe-Signature": "t=1,v1=bad"})
    t("POST /api/billing/webhook on the onrender.com address: handled there (refused for its bad signature), never moved", (st[0] != 301, st[1]), (True, None))
    t("POST / on www.uaply.net: never a 301 (only GET and HEAD move)", req(A, "POST", "/", "www.uaply.net", body={})[0] != 301, True)
    t("/api (no slash) is not moved either", req(A, "GET", "/api", "www.uaply.net")[0] != 301, True)
    st = req(A, "GET", "//evil.example.com/x", "www.uaply.net")
    t("GET //evil.example.com/x: the move stays on uaply.net (the path, not another host)", (st[0], urllib.parse.urlsplit(st[1] or "").netloc), (301, "uaply.net"))
    st = req(A, "GET", "/legal/", "evil.example.com")
    t("a forged Host header: the 301 still goes only to https://uaply.net/", st[:2], (301, "https://uaply.net/legal/"))
    st = req(A, "GET", "/", "evil.example.com")
    t("a forged Host header on the home page: the moved page names only uaply.net", ("evil" in st[2], 'location.replace("https://uaply.net/")' in st[2]), (False, True))
    line, loc = raw(A, "GET /legal/café x HTTP/1.1\r\nHost: www.uaply.net\r\nConnection: close\r\n\r\n".replace(" x ", " ").encode("utf-8"))
    t("a path with non-ASCII letters: the Location is percent-encoded (UTF-8 bytes kept)", loc, "https://uaply.net/legal/caf%C3%A9")
    line, loc = raw(A, b"GET /legal/?q=a%20b&c=d HTTP/1.1\r\nHost: www.uaply.net\r\nConnection: close\r\n\r\n")
    t("an already-encoded query is kept as it is (not encoded twice)", loc, "https://uaply.net/legal/?q=a%20b&c=d")
    # a request line with a valid version but too many words: Python answers 400 with headers before it has read any (self.headers unset)
    line, loc = raw(A, b"GET / extra HTTP/1.1\r\nHost: www.uaply.net\r\n\r\n")
    t("a malformed request line (four words): a plain 400 with headers, no crash", line.split(" ")[1:2], ["400"])
    line, loc = raw(A, b"GET /a b c HTTP/1.0\r\n\r\n")
    t("the same with HTTP/1.0: a plain 400", line.split(" ")[1] if " " in line else line, "400")
    t("...and the server still answers afterwards", req(A, "GET", "/healthz", "uaply.net")[0], 200)
    line, loc = raw(A, b"GET http://evil.example.com/steal HTTP/1.1\r\nHost: www.uaply.net\r\nConnection: close\r\n\r\n")
    t("an absolute address in the request line is never turned into a move to it", loc is None or loc.startswith("https://uaply.net/"), True)
    line, loc = raw(A, b"GET / HTTP/1.0\r\n\r\n")
    t("no Host header (HTTP/1.0): served, not moved", (line.split(" ")[1], loc), ("200", None))
    line, loc = raw(A, b"GET /a\rb HTTP/1.1\r\nHost: www.uaply.net\r\nConnection: close\r\n\r\n")
    t("a carriage return in the path never reaches a Location header", loc is None or ("\r" not in loc and loc.startswith("https://uaply.net/")), True)

    # ---------- 3. search tags on the public host ----------
    home = req(A, "GET", "/", "uaply.net")
    t("home page: canonical link to https://uaply.net/", '<link rel="canonical" href="https://uaply.net/">' in home[2], True)
    ld = home[2].split('<script type="application/ld+json">', 1)[1].split("</script>", 1)[0] if 'application/ld+json' in home[2] else "{}"
    t("home page: a WebSite block named UAply, alternateName uaply.net, url https://uaply.net/", json.loads(ld),
      {"@context": "https://schema.org", "@type": "WebSite", "name": "UAply", "alternateName": "uaply.net", "url": "https://uaply.net/"})
    t("home page: the tags sit inside <head>", home[2].find('rel="canonical"') < home[2].lower().find("</head>"), True)
    t("home page: a meta description", '<meta name="description" content="UAply: swipe right to apply to jobs that match your profile.">' in home[2], True)
    t("home page: Content-Length matches the page with the tags", int(home[3]), len(home[2].encode("utf-8")))
    hd = req(A, "HEAD", "/", "uaply.net")
    t("HEAD /: same length as GET, no body", (hd[0], hd[3], hd[2]), (200, home[3], ""))
    t("/?billing=success: the same canonical (no query)", '<link rel="canonical" href="https://uaply.net/">' in req(A, "GET", "/?billing=success", "uaply.net")[2], True)
    t("/prod-index.html (the page the app frames): canonical to the home page", '<link rel="canonical" href="https://uaply.net/">' in req(A, "GET", "/prod-index.html", "uaply.net")[2], True)
    for page, canon in (("/legal/", "https://uaply.net/legal/"), ("/legal/index.html", "https://uaply.net/legal/"),
                        ("/legal/terms.html", "https://uaply.net/legal/terms.html"), ("/legal/privacy.html", "https://uaply.net/legal/privacy.html"),
                        ("/legal/support.html", "https://uaply.net/legal/support.html"), ("/legal/ai-and-employment.html", "https://uaply.net/legal/ai-and-employment.html")):
        st = req(A, "GET", page, "uaply.net")
        t("%s: 200 with canonical %s, and no WebSite block" % (page, canon), (st[0], '<link rel="canonical" href="%s">' % canon in st[2], "ld+json" in st[2]), (200, True, False))
    t("/legal/style.css is not touched", "canonical" in req(A, "GET", "/legal/style.css", "uaply.net")[2], False)
    t("/legal/not-a-page.html still 404", req(A, "GET", "/legal/not-a-page.html", "uaply.net")[0], 404)
    rb = req(A, "GET", "/robots.txt", "uaply.net")
    t("robots.txt: the rules as before plus the Sitemap line", (rb[0], "Disallow: /api/" in rb[2], rb[2].strip().splitlines()[-1]), (200, True, "Sitemap: https://uaply.net/sitemap.xml"))
    sm = req(A, "GET", "/sitemap.xml", "uaply.net")
    locs = [e.text for e in ET.fromstring(sm[2]).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")] if sm[0] == 200 else []
    legal = sorted("https://uaply.net/legal/" + n for n in os.listdir(os.path.join(ROOT, "legal")) if n.endswith(".html") and n != "index.html")
    t("/sitemap.xml: valid XML listing the home page, /legal/ and every legal page, all on https://uaply.net", (sm[0], locs),
      (200, ["https://uaply.net/", "https://uaply.net/legal/"] + legal))
    t("/sitemap.xml: includes the support page", "https://uaply.net/legal/support.html" in locs, True)

    # ---------- 4. a server without the variable ----------
    t("unset: GET / on www.uaply.net is served, not moved", req(B, "GET", "/", "www.uaply.net")[:2], (200, None))
    t("unset: GET / on the onrender.com address is served", req(B, "GET", "/", "uaply-dev.onrender.com")[:2], (200, None))
    hb = req(B, "GET", "/", "uaply.net")[2]
    t("unset: no canonical link and no WebSite block on the home page", ("canonical" in hb, "ld+json" in hb), (False, False))
    t("unset: the meta description is still there (it is part of the page)", 'name="description"' in hb, True)
    t("unset: no canonical link on a legal page", "canonical" in req(B, "GET", "/legal/terms.html", "uaply.net")[2], False)
    t("unset: robots.txt has no Sitemap line", "Sitemap" in req(B, "GET", "/robots.txt", "uaply.net")[2], False)
    t("unset: /sitemap.xml does not exist", req(B, "GET", "/sitemap.xml", "uaply.net")[0], 404)

    # ---------- 5. plans hidden ----------
    sa = json.loads(req(A, "GET", "/api/billing/status", "uaply.net")[2])
    t("plans hidden: /api/billing/status says hidden, and offers no Choose buttons", (sa.get("hidden"), sa.get("buttons")), (True, False))
    co = req(A, "POST", "/api/billing/checkout", "uaply.net", body={"plan": "plus"}, headers={"Origin": "https://uaply.net"})
    t("plans hidden: /api/billing/checkout answers 403 with a friendly reason", (co[0], json.loads(co[2]).get("code"), "coming soon" in co[2]), (403, "plans_hidden", True))
    t("plans hidden: ...which says plans are not open yet, never that every account is on Free", ("not open yet" in co[2], "every account" in co[2]), (True, False))
    sb = json.loads(req(B, "GET", "/api/billing/status", "uaply.net")[2])
    t("not hidden (the default): hidden is false", sb.get("hidden"), False)
    cb = req(B, "POST", "/api/billing/checkout", "uaply.net", body={"plan": "plus"}, headers={"Origin": "https://uaply.net"})
    t("not hidden: checkout gives its usual answer, not plans_hidden", (cb[0], json.loads(cb[2]).get("code")), (503, None))
finally:
    for p in (pa, pb):
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
    logs = ""
    for port in (A, B):
        try:
            with open(os.path.join(TMP, "log-%d.txt" % port), encoding="utf-8", errors="replace") as f:
                logs += f.read()
        except OSError:
            pass
    t("no traceback in either server's log (malformed requests included)", "Traceback" in logs, False)
    shutil.rmtree(TMP, ignore_errors=True)

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
