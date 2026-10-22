"""Syntax and rendering checks that ordinary linters miss.
  python tools/test-pages.py

1. Every Python file compiles with this Python (py_compile), so a syntax error can never reach a server start.
2. Every page and email the server builds is rendered once with realistic data, including hostile text. This catches template
   mistakes that only fail at run time, such as a bare % inside a %-formatted page (that broke the test inbox once).
3. Every script in those pages, in the app's HTML files, in shared/*.js, tools/*.js and the Apps Script files is parsed by Node
   (node --check), and checked for the line break that JavaScript silently joins: a line starting with ( [ or ` right after a
   line that ends a value. The browser then calls the previous value instead of starting a new statement (ESLint calls this
   no-unexpected-multiline). That exact mistake broke the setup page's buttons once.
4. Every shell script parses (bash -n).
"""
import glob
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ["UAPLY_DATA_DIR"] = tempfile.mkdtemp()
os.environ["UAPLY_CONFIG_JSON"] = json.dumps({"delivery": "test", "smtp": {}, "owner_copy": "owner@example.com", "feeds": [],
                                              "google": {"client_id": "123456789012-abcdefg1234567.apps.googleusercontent.com"}})
sys.path.insert(0, ROOT)
ok = bad = 0
TMP = tempfile.mkdtemp()
SKIP_DIRS = ("node_modules", os.sep + "mobile" + os.sep, "__pycache__", os.sep + ".git" + os.sep, os.sep + "share" + os.sep)


def t(name, good, detail=""):
    global ok, bad
    if good:
        ok += 1
        print("PASS", name)
    else:
        bad += 1
        print("FAIL", name, ("\n   " + detail) if detail else "")


def files(pattern):
    return [p for p in glob.glob(os.path.join(ROOT, pattern), recursive=True) if not any(s in p for s in SKIP_DIRS)]


# ---- 1. Python compiles -------------------------------------------------------------------------------------------------------------------
broken = []
for p in files("**/*.py"):
    try:
        py_compile.compile(p, cfile=os.path.join(TMP, "x.pyc"), doraise=True)
    except py_compile.PyCompileError as e:
        broken.append("%s: %s" % (os.path.relpath(p, ROOT), str(e).splitlines()[-1][:160]))
t("every Python file compiles (%d files)" % len(files("**/*.py")), not broken, "; ".join(broken))

# ---- 2. every server page and email renders ---------------------------------------------------------------------------------------------
import auth_api      # noqa: E402
import chat_api      # noqa: E402
import emails        # noqa: E402
import setup_api     # noqa: E402
import uaply_api     # noqa: E402

for mod in (uaply_api, auth_api, chat_api):
    mod.init("sandbox")
EVIL = '<img src=x onerror=alert(1)> 100% "quoted" & {braces} %s %d'
cand = {"name": "Sam " + EVIL, "email": "sam@example.com", "title": "Intern", "loc": "Philadelphia, PA", "edu": "Bachelor", "years": 1, "skills": ["Python"],
        "ext": {"phone": "+1 215 555 0100", "school": "Drexel", "auth": "citizen", "sponsor": "no"}, "resume_file": "r.pdf"}
job = {"id": 1, "co": "Acme " + EVIL, "role": "Engineer " + EVIL, "url": "https://acme.example/j", "loc": "Remote", "type": "internship", "mode": "remote",
       "sal": [50000, 70000], "desc": "Build things. " + EVIL}
rendered = {}
for status in ("delivered_test", "sent", "handoff", "failed"):
    rec = {"id": "r" + status, "at": int(time.time()), "mode": "test" if status == "delivered_test" else "live", "job": job, "candidate": cand, "note": EVIL,
           "match": 80, "to": "recruiting@acme.example", "simulated": status == "delivered_test", "status": status, "user": None, "resume": None,
           "channels": ["email"], "autofill": {"filled": 2, "total": 3, "items": [{"q": "Why " + EVIL, "a": EVIL}]}}
    uaply_api.APPS.append(rec)
    ctx = uaply_api._mail_ctx(uaply_api.config(), rec, EVIL, "sam@example.com")
    try:
        rendered["receipt " + status] = emails.applicant_receipt(ctx)[2] or ""
        rendered["owner copy " + status] = emails.owner_copy(ctx)[2] or ""
        t("the applicant's receipt and the owner's copy render (%s)" % status, True)
    except Exception as e:
        t("the applicant's receipt and the owner's copy render (%s)" % status, False, "%s: %s" % (type(e).__name__, e))
pages = [("the test inbox", lambda: uaply_api.outbox_html()), ("the setup page", lambda: setup_api.page("127.0.0.1:8766", "http")),
         ("the feedback page", lambda: chat_api.feedback_html()), ("the verification email", lambda: emails.verification_email("123456")[2]),
         ("the help request email", lambda: emails.support_ticket({"topic": "bug", "message": EVIL, "email": "sam@example.com", "at": time.time(), "id": "x"})[1]),
         ("the help request reply", lambda: emails.support_ack({"topic": "bug", "message": EVIL, "email": "sam@example.com", "at": time.time(), "id": "x"})[1])]
for name, fn in pages:
    try:
        out = fn()
        rendered[name] = out.decode("utf-8") if isinstance(out, bytes) else (out or "")
        t(name + " renders", True)
    except Exception as e:
        t(name + " renders", False, "%s: %s" % (type(e).__name__, e))
t("hostile text in the test inbox is shown as text, never as a tag", "<img src=x" not in rendered.get("the test inbox", "<img src=x"))

# ---- 3. every script parses, and has no line break JavaScript would join ----------------------------------------------------------------
SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)
ENDS_VALUE = re.compile(r"[\w$)\]}'\"]$")
STARTS_CALL = re.compile(r"^[(\[`]")


def _scan(code):
    """One pass over the code: which characters are code (not inside a string, template, comment or regex), and for each } the
    position of the { it closes. Good enough for this codebase's scripts; Node has already checked they parse."""
    is_code = bytearray(len(code))
    match, stack, i, n, last = {}, [], 0, len(code), ""
    while i < n:
        c = code[i]
        if c in "'\"`":
            q, i = c, i + 1
            while i < n and code[i] != q:
                if code[i] == "\\":
                    i += 1
                elif q == "`" and code[i] == "$" and i + 1 < n and code[i + 1] == "{":   # ${...} inside a template: skip to its end
                    depth, i = 1, i + 2
                    while i < n and depth:
                        depth += {"{": 1, "}": -1}.get(code[i], 0)
                        i += 1
                    continue
                i += 1
            i += 1
            last = "v"
            continue
        if code.startswith("//", i):
            i = code.find("\n", i)
            i = n if i < 0 else i
            continue
        if code.startswith("/*", i):
            j = code.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "/" and (last in "(,=:[!&|?{};+-*%<>~^" or last == "" or re.search(r"\b(return|typeof|case)\s*$", code[max(0, i - 8):i])):
            i += 1                                              # a regular expression literal: skip it (and its [classes])
            cls = False
            while i < n and (code[i] != "/" or cls):
                if code[i] == "\\":
                    i += 1
                elif code[i] == "[":
                    cls = True
                elif code[i] == "]":
                    cls = False
                elif code[i] == "\n":
                    break
                i += 1
            i += 1
            last = "v"
            continue
        is_code[i] = 1
        if c == "{":
            stack.append(i)
        elif c == "}" and stack:
            match[i] = stack.pop()
        if not c.isspace():
            last = c if c in "(,=:[!&|?{};+-*%<>~^)]}" else "v"
        i += 1
    return is_code, match


def _ends_value(code, end, match):
    """Whether the code just before position `end` finishes a value (so a following ( [ or ` would continue it)."""
    j = end - 1
    while j >= 0 and code[j].isspace():
        j -= 1
    if j < 0:
        return False
    c = code[j]
    if c != "}":
        return bool(re.match(r"[\w$)\]'\"`]", c)) and not re.search(r"\b(return|else|do|typeof|case)$", code[max(0, j - 8):j + 1])
    o = match.get(j)
    if o is None:
        return False
    before = code[max(0, o - 200):o].rstrip()
    if re.search(r"(=>|\bfunction\b\s*[\w$]*\s*\([^()]*\))$", before):       # a function body: a value only if the function is an expression
        head = before[:re.search(r"(=>|\bfunction\b\s*[\w$]*\s*\([^()]*\))$", before).start()].rstrip()
        if before.endswith("=>"):
            return True
        return bool(re.search(r"([=(:,?&|!]|\breturn)$", head))
    return bool(re.search(r"([=(:,?&|!]|\breturn)$", before))                # an object literal is a value; a block is not


def joined_lines(code):
    """Line pairs that JavaScript reads as one expression although they look like two statements (ESLint no-unexpected-multiline)."""
    is_code, match = _scan(code)
    found, pos = [], 0
    for n, line in enumerate(code.split("\n"), 1):
        k = pos + len(line) - len(line.lstrip())
        if k < len(code) and is_code[k] and code[k] in "([`" and _ends_value(code, pos, match):
            prev = code[:pos].rstrip().rsplit("\n", 1)[-1]
            found.append("line %d: %s  <-  %s" % (n, line.strip()[:50], prev.strip()[-50:]))
        pos += len(line) + 1
    return found


sources = []                                                       # (label, code)
for name, page in rendered.items():
    for i, s in enumerate(SCRIPT.findall(page)):
        sources.append(("%s, script %d" % (name, i + 1), s))
for p in files("**/*.html"):
    with open(p, encoding="utf-8") as f:
        for i, s in enumerate(SCRIPT.findall(f.read())):
            sources.append(("%s, script %d" % (os.path.relpath(p, ROOT), i + 1), s))
for p in files("shared/*.js") + files("tools/*.js") + files("marketing/*.gs") + files("*.js"):
    with open(p, encoding="utf-8") as f:
        sources.append((os.path.relpath(p, ROOT), f.read()))

node = shutil.which("node")
parse_errors, joins = [], []
for i, (label, code) in enumerate(sources):
    if node and code.strip():
        tmp = os.path.join(TMP, "s%d.js" % i)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(code)
        r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
        if r.returncode != 0:
            msg = [x for x in r.stderr.splitlines() if "Error" in x]
            parse_errors.append("%s: %s" % (label, (msg[0] if msg else r.stderr.strip())[:160]))
    for j in joined_lines(code):
        joins.append("%s %s" % (label, j))
t("every script parses (%d scripts: pages the server builds, the app's HTML, shared, tools, Apps Script)" % len(sources), bool(node) and not parse_errors,
  "; ".join(parse_errors) or ("" if node else "node is not installed"))
t("no line break that JavaScript would silently join (a line starting with ( [ or ` after a value)", not joins, "\n   ".join(joins[:10]))

# the check itself works: it catches the mistake that once broke the setup page, and does not cry wolf on safe code
SHOULD_FLAG = ["document.getElementById('sv').onclick=function(){go()}\n(function(){sync()})();", "x={a:1}\n[1].forEach(f)", "foo()\n(bar)",
               "var f=()=>{go()}\n(1)"]
FINE = ["a=function(){go()};\n;(function(){sync()})();", "if(a){b()}\n[1].forEach(f)", "var s=`a\n(x)\n`;", "function g(){go()}\n(function(){})()",
        "var r=/" + chr(92) + "d{6}/;\nif(a){}\n(function(){})()", "return\n(x)"]
t("...and that check catches the mistake that once broke the setup page (and %d like it), with no false alarms on %d safe patterns" % (len(SHOULD_FLAG) - 1, len(FINE)),
  all(joined_lines(c) for c in SHOULD_FLAG) and not any(joined_lines(c) for c in FINE),
  "missed: %s; false alarms: %s" % ([c for c in SHOULD_FLAG if not joined_lines(c)], [c for c in FINE if joined_lines(c)]))

# ---- 4. shell scripts parse --------------------------------------------------------------------------------------------------------------
bash = shutil.which("bash")
sh_bad = []
for p in files("**/*.sh"):
    r = subprocess.run([bash, "-n", p], capture_output=True, text=True) if bash else None
    if r is not None and r.returncode != 0:
        sh_bad.append("%s: %s" % (os.path.relpath(p, ROOT), r.stderr.strip()[:160]))
t("every shell script parses (bash -n, %d files)" % len(files("**/*.sh")), bool(bash) and not sh_bad, "; ".join(sh_bad) or ("" if bash else "bash is not installed"))

# ---- 5. the installable website and the Play Store pages, on a running server ------------------------------------------------------------
# the web manifest and its icons, the service worker and its offline screen, /.well-known/assetlinks.json with UAPLY_ASSETLINKS_SHA256
# unset, set and set wrongly, and the account-deletion page. tools/ui-installable.js checks the same in Chrome (installable, offline).
import http.client  # noqa: E402
import socket  # noqa: E402
import struct  # noqa: E402

FP1 = ":".join(["AB"] * 32)
FP2 = "12" * 32                                                     # 64 bare hex digits: accepted and written with colons


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    n = s.getsockname()[1]
    s.close()
    return n


def server(extra, code=None):
    """A throwaway server (code: a folder holding a copy of the code to run instead of this one)."""
    code = code or ROOT
    port = free_port()
    env = dict(os.environ, UAPLY_DATA_DIR=tempfile.mkdtemp(dir=TMP), UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON='{"feeds":[],"smtp":{}}', **extra)
    for k in ("UAPLY_ASSETLINKS_SHA256", "UAPLY_PUBLIC_URL", "HOST"):
        if k not in extra:
            env.pop(k, None)
    log = open(os.path.join(TMP, "server-%d.log" % port), "w")
    p = subprocess.Popen([sys.executable, os.path.join(code, "serve.py"), str(port), os.path.join(code, "dev"), "--api"], env=env, cwd=code,
                         stdout=subprocess.DEVNULL, stderr=log)
    for _ in range(120):
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            c.request("GET", "/healthz")
            if c.getresponse().status == 200:
                return p, port, log
        except OSError:
            time.sleep(0.25)
    p.kill()
    raise SystemExit("the test server did not start")


def get(port, path, method="GET", host=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request(method, path, headers={"Host": host} if host else {})
    r = c.getresponse()
    out = (r.status, r.getheader("Content-Type") or "", r.read(), r.getheader("Content-Security-Policy") or "", r.getheader("Location"))
    c.close()
    return out


def png_size(b):
    return struct.unpack(">II", b[16:24]) if b[:8] == b"\x89PNG\r\n\x1a\n" else None


procs = []
try:
    pa, A, _ = server({})
    procs.append(pa)
    st, ct, body, csp, _ = get(A, "/uaply.webmanifest")
    man = {}
    try:
        man = json.loads(body)
    except ValueError:
        pass
    dev_html = open(os.path.join(ROOT, "dev", "index.html"), encoding="utf-8").read()
    sb_html = open(os.path.join(ROOT, "sandbox", "index.html"), encoding="utf-8").read()
    bg_token = re.search(r"--bg:(#[0-9A-Fa-f]{6})", sb_html).group(1).upper()
    t("/uaply.webmanifest is served as a web manifest and is valid JSON", (st, ct, bool(man)) == (200, "application/manifest+json", True), "%s %s" % (st, ct))
    t("the manifest: name and short_name UAply, start_url and scope /, display standalone",
      (man.get("name"), man.get("short_name"), man.get("start_url"), man.get("scope"), man.get("display")) == ("UAply", "UAply", "/", "/", "standalone"),
      json.dumps(man)[:300])
    t("the manifest's theme and background colours are the app's own background token (%s)" % bg_token,
      (str(man.get("theme_color")).upper(), str(man.get("background_color")).upper()) == (bg_token, bg_token), "%s %s" % (man.get("theme_color"), man.get("background_color")))
    icons, icon_bad = man.get("icons") or [], []
    for ic in icons:
        s2, c2, b2, _, _ = get(A, ic.get("src", ""))
        w = png_size(b2)
        want = tuple(int(x) for x in str(ic.get("sizes", "0x0")).split("x"))
        if s2 != 200 or c2 != "image/png" or w != want:
            icon_bad.append("%s: %s %s %s (wanted %s)" % (ic.get("src"), s2, c2, w, want))
    kinds = {(ic.get("sizes"), ic.get("purpose")) for ic in icons}
    t("every manifest icon is served as a PNG of the size it claims", bool(icons) and not icon_bad, "; ".join(icon_bad))
    t("...and they include 192 and 512 pixel icons, each as an ordinary and a maskable one",
      {("192x192", "any"), ("512x512", "any"), ("192x192", "maskable"), ("512x512", "maskable")} <= kinds, str(sorted(kinds)))
    t("dev and the sandbox both link the manifest and register the service worker",
      all('<link rel="manifest" href="/uaply.webmanifest">' in h and 'serviceWorker.register("/uaply-sw.js")' in h for h in (dev_html, sb_html)))
    st, ct, sw, csp, _ = get(A, "/uaply-sw.js")
    t("/uaply-sw.js is served at the site root as JavaScript (so its scope is the whole site)", (st, ct.split(";")[0]) in ((200, "text/javascript"), (200, "application/javascript")), "%s %s" % (st, ct))
    sws = sw.decode("utf-8", "replace")
    saved = re.search(r'var PAGE = "([^"]+)", ICON = "([^"]+)"', sws)
    t("the service worker saves only the offline screen and its icon, and never writes to its cache anywhere else",
      bool(saved) and saved.groups() == ("/uaply-offline.html", "/uaply-icon-192.png") and ".put(" not in sws and sws.count("addAll(") == 1, sws[:200])
    owner = re.search(r'var OWNER_PAGES = (\[[^\]]*\])', sws)
    srv = open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read()
    srv_owner = re.search(r'^OWNER_PAGES = \(([^)]*)\)', srv, re.M)
    t("...and leaves /api/, /healthz, /.well-known/ and the owner's pages (the same list as serve.py) alone even for page loads",
      all(x in sws for x in ('p.indexOf("/api/") === 0', 'p === "/healthz"', 'p.indexOf("/.well-known/") === 0')) and bool(owner) and bool(srv_owner)
      and sorted(json.loads(owner.group(1))) == sorted(re.findall(r'"(/[a-z]+)"', srv_owner.group(1))),
      "%s / %s" % (owner and owner.group(1), srv_owner and srv_owner.group(1)))
    t("the pages' security policy lets the manifest and the worker come only from this site", "manifest-src 'self'" in csp and "worker-src 'self'" in csp
      and "frame-ancestors 'self'" in csp, csp)
    st, ct, off, _, _ = get(A, "/uaply-offline.html")
    offs = off.decode("utf-8", "replace")
    t("/uaply-offline.html: the offline and starting-up screen, retrying through /healthz and reloading the page asked for",
      st == 200 and "UAply is starting up" in offs and "You're offline" in offs and 'fetch("/healthz"' in offs and "location.reload()" in offs, str(st))
    st, ct, body, _, _ = get(A, "/.well-known/assetlinks.json")
    hs = get(A, "/.well-known/assetlinks.json", "HEAD")[0]
    t("UAPLY_ASSETLINKS_SHA256 unset: /.well-known/assetlinks.json is a plain 404 (JSON, GET and HEAD), not an empty statement",
      (st, ct, hs, b"package_name" in body) == (404, "application/json", 404, False), "%s %s %s" % (st, ct, body[:80]))
    # /.well-known/security.txt (RFC 9116): who to tell about a security problem, the privacy page, and an expiry a year away
    # ---- versioned script and style names: the pages ask for uaply-nav.<hash>.js, which may be kept a year; the pages themselves never ----
    def hdr(port, path):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", path)
        r = c.getresponse()
        out = (r.status, r.getheader("Cache-Control") or "", r.read())
        c.close()
        return out
    import hashlib as _hl
    st_home, cc_home, home = hdr(A, "/")
    homes = home.decode("utf-8", "replace")
    names = re.findall(r'<script src="(uaply-[a-z]+)\.([0-9a-f]{10})\.js"></script>', homes)
    plain_left = re.findall(r'<script src="uaply-[a-z]+\.js"></script>', homes)
    want = re.findall(r'<script src="(uaply-[a-z]+)\.js"></script>', dev_html)
    t("the home page asks for every script by its versioned name (uaply-nav.<hash>.js), none by the plain name, and is itself never kept",
      st_home == 200 and [n for n, _ in names] == want and not plain_left and cc_home == "no-store", "%s %s %s" % (names, plain_left, cc_home))
    right = all(h == _hl.sha256(open(os.path.join(ROOT, "shared", n + ".js"), "rb").read()).hexdigest()[:10] for n, h in names)
    t("...each name carries the first 10 hex digits of that file's SHA-256", bool(names) and right, names)
    n0, h0 = names[0] if names else ("uaply-nav", "0" * 10)
    st_v, cc_v, body_v = hdr(A, "/%s.%s.js" % (n0, h0))
    t("a versioned script is sent with a year's cache (public, max-age=31536000, immutable) and is the file itself",
      (st_v, cc_v, body_v == open(os.path.join(ROOT, "shared", n0 + ".js"), "rb").read()) == (200, "public, max-age=31536000, immutable", True), (st_v, cc_v))
    st_o, cc_o, _ = hdr(A, "/%s.0000000000.js" % n0)
    t("an old name (a page from before a deploy) gets today's file, never kept", (st_o, cc_o), (200, "no-store"))
    st_l, cc_l, legal_page = hdr(A, "/legal/terms.html")
    sty = re.search(r'href="style\.([0-9a-f]{10})\.css"', legal_page.decode("utf-8", "replace"))
    st_s, cc_s, _ = hdr(A, "/legal/style.%s.css" % (sty.group(1) if sty else "x"))
    t("the legal pages ask for style.<hash>.css, kept a year; the pages themselves and the API never",
      bool(sty) and (st_s, cc_s, cc_l, hdr(A, "/api/auth/me")[1]) == (200, "public, max-age=31536000, immutable", "no-store", "no-store"), (cc_s, cc_l))
    t("the service worker and the assist script keep their plain names (other programs ask for them by those)",
      'register("/uaply-sw.js")' in homes and hdr(A, "/uaply-sw.js")[1] == "no-store")
    # a changed file gets a new name: a copy of the code, one script changed
    code = tempfile.mkdtemp(dir=TMP)
    for name in os.listdir(ROOT):
        src = os.path.join(ROOT, name)
        if name.endswith(".py") and os.path.isfile(src):
            shutil.copy2(src, code)
    for d in ("shared", "dev", "legal", "prod", "help"):
        shutil.copytree(os.path.join(ROOT, d), os.path.join(code, d))
    pc, C, _ = server({}, code)
    procs.append(pc)
    before = dict(re.findall(r'<script src="(uaply-[a-z]+)\.([0-9a-f]{10})\.js"></script>', hdr(C, "/")[2].decode("utf-8", "replace")))
    with open(os.path.join(code, "shared", "uaply-nav.js"), "a", encoding="utf-8") as fh:
        fh.write("\n/* changed for the test */\n")
    after = dict(re.findall(r'<script src="(uaply-[a-z]+)\.([0-9a-f]{10})\.js"></script>', hdr(C, "/")[2].decode("utf-8", "replace")))
    t("a changed file gets a new name at once (no restart), and only that file",
      before.get("uaply-nav") and after.get("uaply-nav") and before["uaply-nav"] != after["uaply-nav"]
      and {k: v for k, v in before.items() if k != "uaply-nav"} == {k: v for k, v in after.items() if k != "uaply-nav"}, (before, after))
    t("...and the old name is no longer kept (today's file, no-store)", hdr(C, "/uaply-nav.%s.js" % before.get("uaply-nav", "x"))[1], "no-store")

    st, ct, sec, _, loc = get(A, "/.well-known/security.txt")
    secs = sec.decode("utf-8", "replace")
    exp = re.search(r"^Expires: (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)$", secs, re.M)
    days = (time.mktime(time.strptime(exp.group(1), "%Y-%m-%dT%H:%M:%SZ")) - time.mktime(time.gmtime())) / 86400 if exp else 0
    t("/.well-known/security.txt: plain text with the company's contact address, the privacy page, and an expiry a year from now",
      st == 200 and ct.startswith("text/plain") and "Contact: mailto:uaplytechnologies@uaply.net" in secs and "/legal/privacy.html" in secs
      and 360 <= days <= 366 and re.search(r"^Canonical: \S+/\.well-known/security\.txt$", secs, re.M) is not None, "%s %s %r" % (st, ct, secs[:300]))

    pb, B, logb = server({"UAPLY_ASSETLINKS_SHA256": " %s , %s, not-a-fingerprint, %s ,," % (FP1.lower(), FP2, FP1),
                          "UAPLY_PUBLIC_URL": "https://uaply.net"})
    procs.append(pb)
    st, ct, body, _, loc = get(B, "/.well-known/assetlinks.json", host="uaply.net")
    try:
        al = json.loads(body)
    except ValueError:
        al = None
    tgt = (al or [{}])[0].get("target", {}) if isinstance(al, list) else {}
    t("set: assetlinks.json is served as JSON with the handle_all_urls relation for the Android package com.uaply.app",
      (st, ct, isinstance(al, list) and len(al) == 1 and al[0].get("relation") == ["delegate_permission/common.handle_all_urls"],
       tgt.get("namespace"), tgt.get("package_name")) == (200, "application/json", True, "android_app", "com.uaply.app"), "%s %s" % (st, body[:200]))
    t("set: both fingerprints, upper case with colons, each once; the entry that is not a fingerprint is left out",
      tgt.get("sha256_cert_fingerprints") == [FP1, ":".join(["12"] * 32)], str(tgt.get("sha256_cert_fingerprints")))
    st2, _, _, _, loc2 = get(B, "/.well-known/assetlinks.json", host="uaply.onrender.com")
    st3, _, _, _, loc3 = get(B, "/legal/privacy.html", host="uaply.onrender.com")
    t("set: assetlinks.json answers on every address without a redirect (Android does not follow one), while pages still move",
      (st2, loc2, st3, loc3) == (200, None, 301, "https://uaply.net/legal/privacy.html"), "%s %s / %s %s" % (st2, loc2, st3, loc3))
    t("set: HEAD answers 200 too", get(B, "/.well-known/assetlinks.json", "HEAD", host="uaply.net")[0] == 200)
    logb.flush()
    time.sleep(0.2)
    t("set: the server log says one entry was ignored, without repeating it",
      "1 entry ignored" in open(logb.name, encoding="utf-8").read() and "not-a-fingerprint" not in open(logb.name, encoding="utf-8").read())

    st, ct, dpage, _, _ = get(A, "/legal/delete-account.html")
    ds = dpage.decode("utf-8", "replace")
    nav = open(os.path.join(ROOT, "shared", "uaply-nav.js"), encoding="utf-8").read()
    labels = ["More account options", "Delete my account", "I understand this cannot be undone", "Skip survey", "Send and continue",
              "Type DELETE to confirm", "Delete all my data", "Forgot password?"]
    missing = [x for x in labels if x not in nav]
    t("/legal/delete-account.html is served and gives the steps in the app's own words (each button it names exists in the app)",
      st == 200 and "Profile</b>, then <b>Account" in ds and "More account options" in ds and "Delete my account" in ds and not missing, "%s missing in the app: %s" % (st, missing))
    t("...and says what to do without the app or a password, and what is kept", "If you cannot sign in" in ds and "mailto:" in ds and "What may be kept" in ds)
    linked = [f for f in ("privacy.html", "support.html", "index.html") if 'href="delete-account.html"' not in open(os.path.join(ROOT, "legal", f), encoding="utf-8").read()]
    t("the Privacy Policy, Support and the legal index link to the deletion page", not linked, "no link in " + ", ".join(linked))
finally:
    for p in procs:
        p.kill()
        p.wait()

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d / %d" % (ok, ok + bad))
sys.exit(1 if bad else 0)
