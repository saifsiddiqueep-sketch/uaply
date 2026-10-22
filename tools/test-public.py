"""Tests the server the way a real host runs it: public (HOST=0.0.0.0), behind an HTTPS proxy, with an owner password.
  HOST=0.0.0.0 OWNER_PASSWORD=ownerpw UAPLY_DATA_DIR=<empty folder> python serve.py 8772 dev --api
  python tools/test-public.py [port] [address]
The address defaults to 127.0.0.1. A server started with HOST=127.0.0.2 is also public (any address other than 127.0.0.1) yet is
not reachable from other computers, which makes it the safer way to run this test."""
import base64
import http.client
import json
import re
import socket
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8772
ADDR = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
HOST = "uaply.example"
R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


def req(method, path, body=None, headers=None, proto="https", host=HOST, origin=True):
    h = {"Host": host, "X-Forwarded-Proto": proto, "X-Forwarded-For": "203.0.113.7"}
    if origin:
        h["Origin"] = "%s://%s" % (proto, host)
    h.update(headers or {})
    if body is not None:
        h["Content-Type"] = "application/json"
    c = http.client.HTTPConnection(ADDR, PORT, timeout=30)
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    data = r.read()
    out = (r.status, {k.lower(): v for k, v in r.getheaders()}, data)
    c.close()
    return out


def auth(pw):
    return {"Authorization": "Basic " + base64.b64encode(b"owner:" + pw.encode()).decode()}


t("health check answers (the host uses it)", req("GET", "/healthz")[0], 200)
s, h, _ = req("POST", "/api/auth/signup", {"email": "pub1@example.com", "password": "correct horse 99", "agree": True})
t("sign-up works behind the HTTPS proxy", s, 200)
cookie = h.get("set-cookie", "")
t("session cookie is HttpOnly, Secure and SameSite=Lax", all(x in cookie for x in ("HttpOnly", "Secure", "SameSite=Lax")), True)
t("HSTS header is sent over HTTPS", "strict-transport-security" in h, True)
t("no-sniff and frame protection headers are sent", "x-content-type-options" in h and h.get("x-frame-options") == "SAMEORIGIN", True)
t("CSP: only this site may frame it, no plugins, no <base> elsewhere, and the web manifest and service worker come only from this site",
  h.get("content-security-policy"), "frame-ancestors 'self'; object-src 'none'; base-uri 'self'; manifest-src 'self'; worker-src 'self'")
t("Permissions-Policy switches off camera, microphone, USB and the payment API (location is left to the app's own prompt)",
  h.get("permissions-policy"), "camera=(), microphone=(), usb=(), payment=()")
t("the Server header names no Python version (Render passes it on as x-render-origin-server)", h.get("server"), "UAply")
s, h, body = req("HEAD", "/healthz")
t("HEAD /healthz answers 200 with no body (uptime monitors ask that way)", (s, body), (200, b""))
t("a cross-site sign-up is refused", req("POST", "/api/auth/signup", {"email": "pub2@example.com", "password": "correct horse 99", "agree": True},
                                         headers={"Origin": "https://evil.example"})[0], 403)
t("a request with no Origin is refused", req("POST", "/api/auth/login", {"email": "a@b.co", "password": "x"}, origin=False)[0], 403)

for path in ("/outbox", "/api/outbox", "/feedback", "/setup", "/api/feed-health"):
    t("%s needs the owner password" % path, req("GET", path)[0], 401)
    t("%s refuses a wrong password" % path, req("GET", path, headers=auth("nope"))[0], 401)
    t("%s opens with the owner password" % path, req("GET", path, headers=auth("ownerpw"))[0], 200)
t("the test-mail button needs the owner password", req("POST", "/api/setup/test-mail", {})[0], 403)
t("the test-mail button works for the owner", req("POST", "/api/setup/test-mail", {}, headers=auth("ownerpw"))[0], 200)
t("the Connect Gmail form is refused on a hosted server (secrets live in the host dashboard)", req("POST", "/api/setup/save-mail", {"email": "a@gmail.com", "password": "abcdefghijklmnop"}, headers=auth("ownerpw"))[0], 403)
t("the Connect Gmail form needs the owner password", req("POST", "/api/setup/save-mail", {})[0], 403)
t("the Connect hiring system box is refused on a hosted server", req("POST", "/api/setup/save-ats", {"kind": "greenhouse", "board": "acme", "api_key": "abcdefgh1234"}, headers=auth("ownerpw"))[0], 403)
t("the Connect Google box is refused on a hosted server", req("POST", "/api/setup/save-google", {"client_id": "123456789012-abcdefg.apps.googleusercontent.com"}, headers=auth("ownerpw"))[0], 403)

# nothing outside the site folder can be read
for p in ("/../serve.py", "/..%2fserve.py", "/%2e%2e/serve.py", "/legal/../serve.py", "/legal/..%2f..%2fserve.py", "/../uaply-config.json", "/data/uaply.db"):
    s, _, body = req("GET", p)
    t("path %s leaks nothing" % p, s != 200 or b"import " not in body and b"smtp" not in body.lower(), True)
# an absolute path after /legal/ once read any file on the server (on a host: /legal//proc/self/environ, the accounts database...)
import os  # noqa: E402
me = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "serve.py")).replace(os.sep, "/")
for p in ("/legal/" + me, "/legal//" + me.split(":", 1)[-1].lstrip("/"), "/legal//etc/passwd", "/legal/%2Fetc%2Fpasswd", "/legal/C:/Windows/win.ini"):
    s, _, body = req("GET", p)
    t("absolute path %s after /legal/ reads nothing" % p[:60], s == 404 and b"import " not in body and b"root:" not in body, True)
s, h, _ = req("GET", "/legal")
t("a typed /legal (no slash) goes to the legal pages", (s, h.get("location")), (302, "/legal/"))
for p in ("/legal/", "/legal/terms.html", "/legal/privacy.html", "/legal/style.css", "/legal/favicon-32.png"):
    t("legal file %s still opens" % p, req("GET", p)[0], 200)
t("a made-up path is a plain 404", req("GET", "/nope.html")[0], 404)
s, h, body = req("GET", "/nope.html")
t("a made-up path shows the app's own Page not found page with a way back", (h.get("content-type", "").startswith("text/html"), b"Page not found" in body,
  b'href="/">Back to UAply' in body, b"Error response" in body), (True, True, True, False))
s, h, body = req("GET", "/api/nope")
t("an unknown /api/ address keeps the plain answer (read by scripts, not people)", (s, b"Page not found" in body), (404, False))
s, h, body = req("HEAD", "/nope.html")
t("HEAD on a made-up path is a 404 with no body", (s, body), (404, b""))
s, h, body = req("GET", "/favicon.ico")
t("/favicon.ico is the app's icon (browsers and crawlers ask for it)", (s, h.get("content-type"), body[:8]), (200, "image/png", b"\x89PNG\r\n\x1a\n"))
s, h, body = req("GET", "/robots.txt")
t("/robots.txt lets the site be indexed but not the API or the owner pages", (s, h.get("content-type", "").startswith("text/plain"),
  all(x in body for x in (b"User-agent: *", b"Disallow: /api/", b"Disallow: /outbox", b"Disallow: /setup"))), (200, True, True))
s, _, body = req("GET", "/legal/terms.html")
t("the legal pages have a Back to UAply link", b'href="../" class="home">&larr; Back to UAply' in body, True)
t("POST to an unknown path is refused", req("POST", "/api/secret", {})[0], 404)
t("oversized body is refused", req("POST", "/api/auth/login", {"email": "a@b.co", "password": "x" * 50000})[0], 413)
t("an empty POST is a plain 400, not a size error", req("POST", "/api/auth/login")[0], 400)
t("a JSON list instead of an object is a 400", req("POST", "/api/auth/login", [1, 2, 3])[0], 400)

# odd addresses must get a clean answer, never a dropped connection, and never the source code
def raw_status(request_bytes):
    s = socket.create_connection((ADDR, PORT), timeout=10)
    s.sendall(request_bytes)
    first = s.recv(200).split(b"\r\n")[0]
    s.close()
    return first.split(b" ")[1].decode() if first.startswith(b"HTTP/") else "no reply"


for label, line in (("%00 in the address", b"GET /%00 HTTP/1.1"), ("%00 in the middle of a name", b"GET /index.html%00.py HTTP/1.1"),
                    ("a raw null byte", b"GET /\x00 HTTP/1.1"), ("a raw null byte in a legal page", b"GET /legal/\x00terms.html HTTP/1.1")):
    t("%s gets a clean 400" % label, raw_status(line + b"\r\nHost: " + HOST.encode() + b"\r\nConnection: close\r\n\r\n"), "400")
t("the server still answers after those", req("GET", "/healthz")[0], 200)
home = req("GET", "/")[2]
for p in ("/..%5Cserve.py", "/..%5C..%5Cserve.py/", "/%5C..%5Cuaply-config.json"):
    s, _, body = req("GET", p)
    # the app's own page is all such a path may get (the home page as sent, or the same file with its plain script names)
    page = re.sub(rb'(uaply-[a-z]+)\.[0-9a-f]{10}\.js', rb'\1.js', home)
    t("backslash path %s serves no source or settings" % p, s in (301, 404) or (s == 200 and body in (home, page)), True)

# a public server with no email login must say so, not promise a link it cannot send (tools/test-smtp.py covers real sending)
s, h, body = req("POST", "/api/auth/forgot", {"email": "pub1@example.com"})
out = json.loads(body)
t("forgot says email is unavailable instead of promising a link", (s, out.get("delivery"), out.get("ok")), (200, "unavailable", False))
page = req("GET", "/outbox", headers=auth("ownerpw"))[2].decode("utf-8")
t("no reset link was created or stored", "?reset=" not in page.replace("&amp;", "&"), True)

# /api/status (tools/live-check.py reads it from anywhere): yes/no facts only, never a password, key, address or folder
s, _, body = req("GET", "/api/status")
st = json.loads(body)
t("/api/status answers with yes/no facts only (and the deployed commit's short id, or null off Render)",
  (s, all(isinstance(v, bool) or v is None for k, v in st.items() if k not in ("commit", "apply")), st.get("commit") is None or bool(re.fullmatch(r"[0-9a-f]{7}", st["commit"]))),
  (200, True, True))
ap = st.get("apply") or {}
t("/api/status apply: only a yes/no, the delivery mode and job counts per way of applying",
  (sorted(ap), isinstance(ap.get("ok"), bool), ap.get("mode") in ("test", "live"), all(isinstance(v, int) for v in (ap.get("classes") or {}).values()),
   all(isinstance(v, bool) for v in (ap.get("configured") or {}).values()), sorted(ap.get("classes") or {})),
  (["classes", "configured", "mode", "ok"], True, True, True, True, ["ats", "email", "handoff", "webhook"]))
t("/api/status shows the question types employers asked only to the owner", ("questions" in st, "questions" in json.loads(req("GET", "/api/status", headers=auth("ownerpw"))[2])), (False, True))
t("/api/status says what this server has on (public, owner pages on, email off)", (st.get("public"), st.get("ownerPages"), st.get("email")), (True, True, False))
t("/api/status holds no secret or folder name", any(x in body.decode() for x in ("ownerpw", "uaply-", "/", "\\\\")), False)

# the job list is sent gzip-compressed to a browser that takes it, plain otherwise; the owner's feed health lists every source
import gzip  # noqa: E402
s1, h1, b1 = req("GET", "/api/jobs", headers={"Accept-Encoding": "gzip, deflate, br"})
s2, h2, b2 = req("GET", "/api/jobs")
plain = json.loads(b2)
t("/api/jobs: compressed for a browser that takes gzip, the same list as the plain answer",
  (s1, h1.get("content-encoding"), json.loads(gzip.decompress(b1))["sources"] == plain["sources"] if h1.get("content-encoding") == "gzip" else None, s2, h2.get("content-encoding")),
  (200, "gzip", True, 200, None))
t("/api/jobs says how many sources are still loading (the app asks again while any are)", isinstance(plain.get("pending"), int), True)
fh = json.loads(req("GET", "/api/feed-health", headers=auth("ownerpw"))[2])
t("/api/feed-health (owner): every source with its count, successes, failures and whether it is switched off",
  (fh.get("count", 0) > 50, sorted(fh["sources"][0]) if fh.get("sources") else None),
  (True, ["applyPath", "checkKinds", "checkPages", "checkSampled", "error", "failures", "formKind", "humanCheck", "inARow", "jobs", "lastError", "lastOk", "links", "ms", "name", "off", "ok", "retry", "route", "source", "status", "withCheck"]))

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
