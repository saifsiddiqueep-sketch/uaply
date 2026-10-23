"""A long-running local server and today's files on disk: a file added to shared/ after the server started is served at once (by its
own name, as /shared/<file>, and by its hashed name), an address that tries to leave shared/ is refused, and once serve.py or an
*_api.py changes on disk a local server says so (X-UAply-Stale: restart, and "restart me" in its log) while a public one never does.
Starts its own servers on free ports and stops only those.
  python tools/test-stale-server.py"""
import http.client
import os
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHARED = os.path.join(ROOT, "shared")
R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start(host, watch):
    port, d = free_port(), tempfile.mkdtemp(prefix="uaply-stale-")
    log = open(os.path.join(d, "server.log"), "w", encoding="utf-8")
    env = dict(os.environ, UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}", UAPLY_DATA_DIR=d, HOST=host, UAPLY_STALE_WATCH=watch,
               OWNER_PASSWORD="ownerpw", PYTHONUNBUFFERED="1")
    for v in ("UAPLY_FEEDS", "RENDER"):
        env.pop(v, None)
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(port), os.path.join(ROOT, "sandbox"), "--api"],
                            env=env, stdout=log, stderr=log, cwd=ROOT)
    for _ in range(80):
        try:
            if get(port, "/healthz")[0] in (200, 503):
                break
        except OSError:
            time.sleep(0.25)
    return proc, port, os.path.join(d, "server.log")


def get(port, path):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    c.request("GET", path)
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, {k.lower(): v for k, v in r.getheaders()}, body


watch = os.path.join(tempfile.mkdtemp(prefix="uaply-watch-"), "fake_api.py")
with open(watch, "w") as f:
    f.write("# stands in for an *_api.py that changes on disk\n")
time.sleep(1.2)
local, lport, llog = start("127.0.0.1", watch)
public, pport, plog = start("0.0.0.0", watch)
name = "uaply-zz-added-%d" % os.getpid()
js, css = os.path.join(SHARED, name + ".js"), os.path.join(SHARED, name + ".css")
try:
    with open(llog, encoding="utf-8") as f:
        t("a local server logs the git commit it was started from", "[uaply] started from git " in f.read(), True)
    with open(plog, encoding="utf-8") as f:
        t("...a public one does not", "started from git" in f.read(), False)
    t("before the file exists it is not found", get(lport, "/%s.js" % name)[0], 404)
    with open(js, "w", encoding="utf-8", newline="\n") as f:
        f.write("window.__added = 1;\n")
    with open(css, "w", encoding="utf-8", newline="\n") as f:
        f.write("body{}\n")
    st, hd, body = get(lport, "/%s.js" % name)
    t("a script added to shared/ after the start is served by its own name, without a restart", (st, body, "javascript" in hd.get("content-type", "")),
      (200, b"window.__added = 1;\n", True))
    st, hd, body = get(lport, "/shared/%s.js" % name)
    t("...and as /shared/<file>", (st, body), (200, b"window.__added = 1;\n"))
    t("...with the same rules as the other shared files (no-store under its plain name, nosniff)",
      (hd.get("cache-control"), hd.get("x-content-type-options")), ("no-store", "nosniff"))
    import hashlib
    h = hashlib.sha256(b"body{}\n").hexdigest()[:10]
    st, hd, body = get(lport, "/%s.%s.css" % (name, h))
    t("its hashed name works too, kept for a year", (st, body, hd.get("cache-control")), (200, b"body{}\n", "public, max-age=31536000, immutable"))
    t("an old file still answers as before (/uaply-nav.js)", get(lport, "/uaply-nav.js")[0], 200)
    for bad in ("/shared/../serve.py", "/shared/..%2Fserve.py", "/shared/%2e%2e/serve.py", "/shared/%2e%2e%2fserve.py", "/shared/sub/../../serve.py",
                "/shared/..\\serve.py", "/uaply-..%2Fserve.js", "/shared//etc/passwd", "/shared/C:/Windows/win.ini", "/shared/.git/HEAD"):
        st, hd, body = get(lport, bad)
        t("an address that tries to leave shared/ is refused: %s" % bad, (st != 200, b"import sys, os" in body, b"ref: refs" in body), (True, False, False))
    t("no stale-code header while the code on disk is the code the server started with",
      ("x-uaply-stale" in get(lport, "/healthz")[1], "x-uaply-stale" in get(pport, "/healthz")[1]), (False, False))
    with open(watch, "a") as f:
        f.write("# changed\n")
    seen = False
    for _ in range(30):
        if get(lport, "/healthz")[1].get("x-uaply-stale") == "restart":
            seen = True
            break
        time.sleep(0.5)
    t("after an *_api.py changes on disk, a local server answers normally with X-UAply-Stale: restart",
      (seen, get(lport, "/uaply-nav.js")[0]), (True, 200))
    for _ in range(4):
        get(lport, "/healthz")
    time.sleep(0.5)
    with open(llog, encoding="utf-8") as f:
        t("...and logs 'code changed on disk, restart me' once (at most once a minute)", f.read().count("code changed on disk, restart me"), 1)
    time.sleep(5.5)
    t("a public server never sends it", "x-uaply-stale" in get(pport, "/healthz")[1], False)
    t("...and never restarts itself (both still the same processes)", (local.poll(), public.poll()), (None, None))
finally:
    for f in (js, css):
        try:
            os.remove(f)
        except OSError:
            pass
    for p in (local, public):                    # only the servers this test started
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()

print("%d / %d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
