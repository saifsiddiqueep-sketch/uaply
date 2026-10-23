"""The sign-in concepts page: a sandbox-only look-around page (five sign-in and sign-up designs), never part of the real sign-in. No network.
  python tools/test-signin-lab.py [port]        (default 18840; uses port and port+1)
  1. the sandbox server answers GET and HEAD /signin-concepts.html with 200 and the page, and its controls bar links to it in a new tab
  2. the dev server (the release build) answers 404 for the same address and its page never links to it
  3. the page itself: says it is a preview, calls no server address, posts no form anywhere, and its brand fonts never hold up drawing"""
import http.client
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18840
TMP = tempfile.mkdtemp(prefix="uaply-signinlab-")
R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


def start(port, instance):
    env = dict(os.environ, UAPLY_DATA_DIR=os.path.join(TMP, instance), UAPLY_CONFIG_FILE="none",
               UAPLY_CONFIG_JSON='{"feeds":[],"smtp":{},"owner_copy":""}')
    for k in ("UAPLY_PUBLIC_URL", "RENDER"):
        env.pop(k, None)
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(port), os.path.join(ROOT, instance), "--api"], env=env,
                         stdout=subprocess.DEVNULL, stderr=open(os.path.join(TMP, "log-%s.txt" % instance), "w"), cwd=ROOT)
    for _ in range(80):
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            c.request("GET", "/healthz")
            if c.getresponse().status == 200:
                return p
        except OSError:
            time.sleep(0.25)
    p.kill()
    raise SystemExit("server on %d did not start" % port)


def req(port, method, path):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request(method, path)
    r = c.getresponse()
    out = (r.status, r.getheader("Content-Type") or "", r.read().decode("utf-8", "replace"))
    c.close()
    return out


SB, DV = PORT, PORT + 1
procs = []
try:
    procs.append(start(SB, "sandbox"))
    procs.append(start(DV, "dev"))

    # ---------- 1. the sandbox serves it and links to it ----------
    code, ctype, page = req(SB, "GET", "/signin-concepts.html")
    t("sandbox: GET /signin-concepts.html is 200", code, 200)
    t("sandbox: ...as an HTML page", ctype.startswith("text/html"), True)
    t("sandbox: ...and it is the concepts page", ("<title>UAply sign-in concepts</title>" in page, 'id="tabs"' in page), (True, True))
    t("sandbox: HEAD /signin-concepts.html is 200 too", req(SB, "HEAD", "/signin-concepts.html")[0], 200)
    t("sandbox: with a query string (?v=rose) it is still 200", req(SB, "GET", "/signin-concepts.html?v=rose")[0], 200)
    home = req(SB, "GET", "/")[2]
    link = re.search(r'<a [^>]*id="concepts"[^>]*>([^<]*)</a>', home)
    t("sandbox: the controls bar has a Sign-in concepts link", link.group(1) if link else None, "Sign-in concepts")
    tag = link.group(0) if link else ""
    t("sandbox: ...to signin-concepts.html, opened in a new tab without handing it the sandbox window",
      ('href="signin-concepts.html"' in tag, 'target="_blank"' in tag, 'rel="noopener"' in tag), (True, True, True))
    t("sandbox: ...placed next to All off", home.find('id="concepts"') - home.find('id="none"') in range(1, 80), True)

    # ---------- 2. dev never gets it ----------
    code, ctype, body = req(DV, "GET", "/signin-concepts.html")
    t("dev: GET /signin-concepts.html is 404", code, 404)
    t("dev: ...the app's own Page not found page, not the concepts", ('id="tabs"' in body, "Sign-in concepts" in body), (False, False))
    t("dev: HEAD /signin-concepts.html is 404 too", req(DV, "HEAD", "/signin-concepts.html")[0], 404)
    t("dev: its page never links to the concepts", "signin-concepts" in req(DV, "GET", "/")[2], False)
    t("dev: no copy of the page in the dev folder", os.path.exists(os.path.join(ROOT, "dev", "signin-concepts.html")), False)

    # ---------- 3. the page itself ----------
    t("page: says it is a sandbox preview that signs nobody in and sends nothing",
      ("SANDBOX PREVIEW" in page, "nothing here signs you in, creates an account or sends anything" in page), (True, True))
    t("page: calls no server address (no fetch, no XMLHttpRequest, no /api/)", [w for w in ("fetch(", "XMLHttpRequest", "/api/", "sendBeacon") if w in page], [])
    forms = len(re.findall(r"<form\b", page))
    t("page: no form has an action (each one is handled in the page)", re.search(r"<form\b[^>]*\baction=", page) is None, True)
    t("page: every form submit is stopped in the page (%d submit handlers, each starts with preventDefault)" % page.count("onsubmit=function(e){"),
      page.count("onsubmit=function(e){") == page.count("onsubmit=function(e){e.preventDefault();") > 0 and forms > 0, True)
    t("page: no input has a name, so nothing typed could ever ride along in an address", re.search(r"<input\b[^>]*\bname=", page) is None, True)
    font = re.search(r'<link rel="stylesheet" href="https://fonts\.googleapis\.com[^>]*>', page)
    t("page: the brand fonts load without holding up drawing (media=print, switched on load)",
      bool(font) and 'media="print"' in font.group(0) and "this.media='all'" in font.group(0), True)
    t("page: no other outside file (scripts, styles, images) is loaded",
      [u for u in re.findall(r'(?:src|href)="(https?://[^"]+)"', page) if not u.startswith("https://fonts.googleapis.com/")], [])
    t("page: system fonts follow each brand font, so offline it still draws",
      all(re.search(r"--%s:[^;]*'[^']+',\s*[^;]*(system-ui|ui-monospace)" % v, page) for v in ("display", "body", "mono")), True)
finally:
    for p in procs:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
    logs = ""
    for inst in ("sandbox", "dev"):
        try:
            with open(os.path.join(TMP, "log-%s.txt" % inst), encoding="utf-8", errors="replace") as f:
                logs += f.read()
        except OSError:
            pass
    t("no traceback in either server's log", "Traceback" in logs, False)
    shutil.rmtree(TMP, ignore_errors=True)

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
