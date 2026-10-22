"""Starts UAply exactly the way Render runs it and checks what matters on deploy day. No network, no real email, no Render account; under a minute.
  python tools/test-render.py [port]        (default 18782; port+1 is a stand-in mail server)
How: render.yaml's own start command runs through a shell (so ${PORT:-10000} expands as on Render's Linux), with render.yaml's environment, RENDER=true,
test values for the secrets, the public host's headers (Host uaply.net, X-Forwarded-Proto https, X-Forwarded-For) and a temporary folder as the disk.
  1. render.yaml itself: plan with a disk, data folder = disk, health check path, start command, Python version, secrets never in the file
  2. first boot on an empty disk: health check, home page, security headers, cookie flags, owner pages behind OWNER_PASSWORD, where records are written
  3. a deploy: SIGTERM while a request is in progress (it must finish; the server must exit normally)
  4. the next boot on the same disk: still signed in, the outbox and feedback kept, the job list served at once from the saved copy
  5. a record cut short by a full disk or a forced stop does not hide the records after it
  6. a data folder that cannot be written, and a blank PORT: a plain reason in the log, not a traceback"""
import base64
import http.client
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18782
SMTP_PORT = PORT + 1
TMP = tempfile.mkdtemp(prefix="uaply-render-")
DISK = os.path.join(TMP, "var-data")           # stands in for Render's /var/data disk
OWNER = "render-test-owner-pw"
HOSTNAME = "uaply.net"
WIN = os.name == "nt"
R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


def shell():
    """The shell Render's start command runs in: /bin/sh on Linux; Git's bash on Windows. None if there is none."""
    if not WIN:
        return "/bin/sh"
    for p in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe", shutil.which("bash") or ""):
        if p and os.path.exists(p) and "system32" not in p.lower():          # not WSL's bash, which runs Linux, not this Python
            return p
    return None


# ---------- 1. render.yaml ----------
try:
    import yaml
    BP = yaml.safe_load(open(os.path.join(ROOT, "render.yaml"), encoding="utf-8"))
except ImportError:
    BP = None
    print("SKIP render.yaml checks (pip install pyyaml to run them)")
services = {s["name"]: s for s in (BP or {}).get("services", [])}
code = "".join(open(os.path.join(ROOT, f), encoding="utf-8").read() for f in os.listdir(ROOT) if f.endswith(".py"))
for name, s in services.items():
    env = {e["key"]: e for e in s.get("envVars", [])}
    t("%s: Python web service" % name, (s.get("type"), s.get("runtime")), ("web", "python"))
    t("%s: a paid plan (the free plan has no disk and sleeps after 15 minutes)" % name, s.get("plan") not in (None, "free"), True)
    t("%s: has a disk" % name, bool((s.get("disk") or {}).get("mountPath")), True)
    t("%s: UAPLY_DATA_DIR is the disk's mount path (records outside it are wiped at every deploy)" % name,
      (env.get("UAPLY_DATA_DIR") or {}).get("value"), (s.get("disk") or {}).get("mountPath"))
    t("%s: HOST=0.0.0.0 (Render reaches the server only on that address)" % name, (env.get("HOST") or {}).get("value"), "0.0.0.0")
    t("%s: health check at /healthz" % name, s.get("healthCheckPath"), "/healthz")
    t("%s: MALLOC_ARENA_MAX=2 (freed memory is reused instead of held per thread; the 512 MB plan)" % name, (env.get("MALLOC_ARENA_MAX") or {}).get("value"), "2")
    t("%s: start command uses Render's PORT, with 10000 if it is blank" % name, "${PORT:-10000}" in s.get("startCommand", ""), True)
    inst = (re.findall(r"serve\.py \S+ (\w+) --api", s.get("startCommand", "")) or [""])[0]
    t("%s: start command serves an existing folder with the back end on" % name, bool(inst) and os.path.isdir(os.path.join(ROOT, inst)), True)
    t("%s: PYTHON_VERSION is a full version, as Render requires" % name, bool(re.match(r"^3\.\d+\.\d+$", str((env.get("PYTHON_VERSION") or {}).get("value")))), True)
    for k, e in env.items():
        if e.get("sync") is False:
            t("%s: the secret %s is one the server reads" % (name, k), k in code, True)
        v = str(e.get("value", ""))
        if re.search(r"sk_(live|test)_|whsec_|sk-ant-|xkeysib-", v):
            t("%s: %s holds no secret in the repository" % (name, k), v, "(set in Render's dashboard)")

# the shell expands ${PORT:-10000} the way Render's does
sh = shell()
if sh:
    for port_env, want in (("12345", "12345"), ("", "10000"), (None, "10000")):
        e = dict(os.environ)
        e.pop("PORT", None)
        if port_env is not None:
            e["PORT"] = port_env
        out = subprocess.run([sh, "-c", "echo ${PORT:-10000}"], env=e, capture_output=True, text=True, timeout=20).stdout.strip()
        t("the shell turns PORT=%r into port %s" % (port_env, want), out, want)
else:
    print("SKIP shell expansion (no sh or Git bash on this computer)")


# ---------- helpers ----------
mail_file = os.path.join(TMP, "mail.jsonl")
smtp = subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(SMTP_PORT), mail_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
ENV = dict(os.environ)
for k in ("ANTHROPIC_API_KEY", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "UAPLY_ATS_JSON", "UAPLY_FEEDS", "PORT"):
    ENV.pop(k, None)
dev = services.get("uaply-dev") or {"startCommand": "python serve.py ${PORT:-10000} dev --api",
                                       "envVars": [{"key": "HOST", "value": "0.0.0.0"}, {"key": "UAPLY_FEEDS", "value": "greenhouse,lever,ashby"}]}
for e in dev.get("envVars", []):
    if "value" in e:
        ENV[e["key"]] = str(e["value"])
for k in ("NO_PROXY", "no_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
    ENV.pop(k, None)
COMMIT = "0123abc4567def890123abc4567def890123abc4"            # stands in for the commit id Render passes as RENDER_GIT_COMMIT
ENV.update(PORT=str(PORT), RENDER="true", RENDER_GIT_COMMIT=COMMIT, UAPLY_DATA_DIR=DISK, UAPLY_CONFIG_FILE="none", OWNER_PASSWORD=OWNER, SUPPORT_EMAIL="support@example.com",
           UAPLY_CONFIG_JSON=json.dumps({"delivery": "test", "smtp": {"host": "127.0.0.1", "port": SMTP_PORT, "starttls": False,
                                                                    "from_addr": "uaply@example.com"}, "owner_copy": "owner@example.com", "google": {}}))
START = dev["startCommand"].split("#")[0].strip()


def boot(log_name, start=None, base=None, **extra):
    """Run the start command the way Render does. Returns (process, log path)."""
    env, start = dict(base or ENV, **extra), start or START
    log = os.path.join(TMP, log_name)
    cmd = start.replace("python ", '"%s" ' % sys.executable.replace("\\", "/"), 1)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if WIN else 0
    with open(log, "w") as f:
        if sh and not WIN:                   # Windows' Git bash cannot pass a stop signal on to Python, so there the variable is expanded below
            p = subprocess.Popen([sh, "-c", "exec " + cmd], cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT,
                                 creationflags=flags, start_new_session=not WIN)
        else:                                                    # expand the one variable exactly as the shell does (checked above)
            argv = [sys.executable] + [(env.get("PORT") or "10000") if a == "${PORT:-10000}" else env.get("PORT", "") if a == "$PORT" else a
                                       for a in start.split()[1:]]
            p = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT, creationflags=flags)
    return p, log


def wait_up(p, seconds=20):
    t0 = time.time()
    while time.time() - t0 < seconds:
        if p.poll() is not None:
            return None
        try:
            c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=2)
            c.request("GET", "/healthz", headers={"Host": HOSTNAME})
            if c.getresponse().status == 200:
                return time.time() - t0
        except OSError:
            pass
        time.sleep(0.1)
    return None


def req(method, path, body=None, headers=None, timeout=30):
    h = {"Host": HOSTNAME, "X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.7", "Origin": "https://" + HOSTNAME}
    h.update(headers or {})
    data = json.dumps(body) if body is not None else None
    if data:
        h["Content-Type"] = "application/json"
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=timeout)
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    out = r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    c.close()
    return out


def owner(pw=OWNER):
    return {"Authorization": "Basic " + base64.b64encode(("owner:" + pw).encode()).decode()}


def stop(p):
    """What Render does at a deploy: SIGTERM (Ctrl+Break on Windows), then a forced stop after 30 seconds. Returns the exit code, or None."""
    try:
        if WIN:
            p.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(p.pid, signal.SIGTERM)
        return p.wait(timeout=25)
    except Exception:
        p.kill()
        p.wait()
        return None


def persistent(d):
    """The server's own rule: on Render the folder (or one above it) must be a separate disk."""
    p = os.path.abspath(d)
    while os.path.dirname(p) != p:
        if os.path.ismount(p):
            return True
        p = os.path.dirname(p)
    return False


def readlog(log):
    with open(log, encoding="utf-8", errors="replace") as f:
        return f.read()


def fake_job(i, src):
    return {"id": 900000 + i, "co": src[2], "role": "Render test role %d" % i, "loc": "Philadelphia, PA", "mode": "onsite", "sal": [0, 0], "yrs": 0,
            "edu": "High school", "skills": ["Python"], "blurb": "x", "desc": "x", "type": "internship", "url": "https://example.com/job/%d" % i,
            "source": "test", "contact": "", "apply": "link", "live": True, "ats": None, "posted": 0, "perks": [], "comm": False}


repo_data_before = os.path.exists(os.path.join(ROOT, "data"))
procs = []
try:
    for _ in range(100):                                    # the stand-in mail server is listening
        try:
            socket.create_connection(("127.0.0.1", SMTP_PORT), timeout=1).close()
            break
        except OSError:
            time.sleep(0.1)
    # ---------- 2. first boot on an empty disk (third-party feeds off here so nothing reaches the network) ----------
    p, log = boot("boot1.log", UAPLY_FEEDS="")
    procs.append(p)
    up = wait_up(p)
    t("first boot: the health check answers within 15 seconds", up is not None and up < 15, True)
    print("     (first boot to a passing health check: %s s)" % ("%.1f" % up if up else "never"))
    text = readlog(log)
    t("the log says where records go and that the server is public", "data: %s" % DISK in text and "0.0.0.0:%d (public)" % PORT in text, True)
    t("the log flags a data folder that is not a real disk (as on Render without one)", "NOT a persistent disk" in text, not persistent(DISK))
    t("the log never shows the owner password", OWNER in text, False)
    s, h, body = req("GET", "/")
    t("home page", s, 200)
    t("HSTS, no-sniff and frame protection behind Render's HTTPS", ("strict-transport-security" in h, h.get("x-content-type-options"), h.get("x-frame-options")),
      (True, "nosniff", "SAMEORIGIN"))
    t("no Python version in the Server header (Render passes it on as x-render-origin-server)", h.get("server"), "UAply")
    t0 = time.time()
    hz = [req("GET", "/healthz") for _ in range(20)]
    t("health check: 200 {\"ok\": true}, quick (20 in %.2f s), and HEAD works too" % (time.time() - t0),
      ([x[0] for x in hz] == [200] * 20, json.loads(hz[0][2]), time.time() - t0 < 2, req("HEAD", "/healthz")[:3:2]), (True, {"ok": True}, True, (200, b"")))
    t("/api/status names the deployed commit (the short id of RENDER_GIT_COMMIT)", json.loads(req("GET", "/api/status")[2]).get("commit"), COMMIT[:7])
    s, h, body = req("GET", "/api/jobs")
    t("job list answers on a fresh disk", (s, "jobs" in json.loads(body)), (200, True))
    s, h, body = req("POST", "/api/auth/signup", {"email": "render@example.com", "password": "correct horse 99", "agree": True})
    cookie = h.get("set-cookie", "")
    t("sign-up behind Render's proxy", s, 200)
    t("session cookie: HttpOnly, Secure, SameSite=Lax, whole site, 30 days", all(x in cookie for x in ("HttpOnly", "; Secure", "SameSite=Lax", "Path=/", "Max-Age=2592000")), True)
    session = cookie.split(";", 1)[0]
    t("the sign-up code email reached the mail server", os.path.exists(mail_file) and "render@example.com" in open(mail_file, encoding="utf-8").read(), True)
    for path in ("/outbox", "/api/outbox", "/feedback", "/setup"):
        t("%s: closed without the owner password, closed with a wrong one, open with it" % path,
          (req("GET", path)[0], req("GET", path, headers=owner("wrong"))[0], req("GET", path, headers=owner())[0]), (401, 401, 200))
    s, h, body = req("GET", "/setup", headers=owner())
    t("/setup on the host never shows a secret", OWNER in body.decode() or "correct horse" in body.decode(), False)
    t("/setup cannot write settings on the host (they live in Render's dashboard)",
      req("POST", "/api/setup/save-mail", {"email": "a@gmail.com", "password": "abcdefghijklmnop"}, headers=owner())[0], 403)
    job = {"id": 900001, "co": "Example Co", "role": "Intern", "url": "https://example.com/job/1", "source": "test", "loc": "Philadelphia, PA"}
    s, h, body = req("POST", "/api/apply", {"consent": True, "job": job, "profile": {"ext": {"phone": "215-555-0100"}, "name": "Render Test", "email": "render@example.com"}},
                     headers={"Cookie": session})
    t("swipe right is recorded", s, 200)
    t("swipe left is recorded", req("POST", "/api/decision", {"dir": "pass", "jobId": 900002, "session": "s1", "co": "X", "role": "Y", "pct": 40})[0], 200)
    t("feedback is recorded", req("POST", "/api/feedback", {"rating": 5, "text": "render feedback one", "source": "chat"})[0], 200)
    inst = os.path.join(DISK, "dev")
    for f in ("uaply.db", "applications.jsonl", "decisions.jsonl", "feedback.jsonl"):
        t("written on the disk: dev/%s" % f, os.path.exists(os.path.join(inst, f)), True)
    t("nothing written next to the code (it is wiped at every deploy)", os.path.exists(os.path.join(ROOT, "data")), repo_data_before)
    text = readlog(log)
    t("the log has one line per API request: method, path, status, time", bool(re.search(r"\[uaply\] POST /api/auth/signup 200 \d+ ms", text)) and
      bool(re.search(r"\[uaply\] POST /api/apply 200 \d+ ms", text)), True)
    lines = "\n".join(x for x in text.splitlines() if re.match(r"\[uaply\] (GET|POST|HEAD) ", x))
    t("...and never the visitor's address, a cookie, an email address, a query string or the health checks",
      any(x in lines for x in ("203.0.113.7", session.split("=", 1)[-1], "@", "?", "/healthz")), False)
    if os.path.exists("/proc/%d/status" % p.pid):
        rss = int(re.search(r"VmRSS:\s+(\d+)", open("/proc/%d/status" % p.pid).read()).group(1)) // 1024
        t("memory after first boot is far below the 512 MB plan (%d MB)" % rss, rss < 200, True)

    # ---------- 3. a deploy: SIGTERM while a request is still arriving ----------
    sock = socket.create_connection(("127.0.0.1", PORT), timeout=30)
    payload = json.dumps({"dir": "apply", "jobId": 900003, "session": "s1", "co": "X", "role": "Y", "pct": 70}).encode()
    sock.sendall(("POST /api/decision HTTP/1.1\r\nHost: %s\r\nOrigin: https://%s\r\nX-Forwarded-Proto: https\r\nContent-Type: application/json\r\n"
                  "Content-Length: %d\r\n\r\n" % (HOSTNAME, HOSTNAME, len(payload))).encode())
    time.sleep(0.5)                                     # the server is now inside this request, waiting for its body
    t0 = time.time()
    try:
        if WIN:
            p.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(p.pid, signal.SIGTERM)
    except Exception as e:
        print("     (could not signal: %s)" % e)
    seen = []                                           # what a newcomer gets while the server stops: 503 from /healthz, then a refused connection
    while time.time() - t0 < 0.7:
        try:
            c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=2)
            c.request("GET", "/healthz", headers={"Host": HOSTNAME})
            seen.append((round(time.time() - t0, 2), c.getresponse().status))
            c.close()
        except OSError:
            seen.append((round(time.time() - t0, 2), "refused"))
        time.sleep(0.05)
    try:
        sock.sendall(payload)
        answer = sock.recv(4096).decode("utf-8", "replace")
    except OSError:
        answer = ""
    sock.close()
    t("SIGTERM: the request in progress still gets its answer", answer.startswith("HTTP/1.0 200") or answer.startswith("HTTP/1.1 200"), True)
    late = [s for at, s in seen if at >= 0.3]
    t("SIGTERM: a newcomer is turned away at once (the health check says 503, then the port refuses): %s" % sorted(set(s for _, s in seen), key=str),
      bool(late) and all(s in (503, "refused") for s in late) and late[-1] == "refused", True)
    try:
        code = p.wait(timeout=25)
    except subprocess.TimeoutExpired:
        p.kill()
        code = "still running after 25 s"
    took = time.time() - t0
    t("SIGTERM: the server exits normally (code 0) within 5 seconds, far inside Render's 30 (%.1f s)" % took, (code, took < 5), (0, True))
    t("SIGTERM: the log says it stopped cleanly", "[uaply] stopped" in readlog(log), True)
    m = re.search(r"\[uaply\] daily (\{.*\})", readlog(log))
    day = json.loads(m.group(1)) if m else {}
    t("SIGTERM: the day's summary line is written first (requests, errors, sign-ups, applications, slowest paths)",
      (day.get("why"), day.get("requests", 0) > 10, day.get("signups"), day.get("applications"), day.get("5xx"), bool(day.get("slowest")),
       isinstance(day.get("p95_ms"), int), day.get("health_checks", 0) >= 20),
      ("stop", True, 1, 1, 0, True, True, True))
    t("SIGTERM: the swipe that was in progress was saved", '"jobId": 900003' in open(os.path.join(inst, "decisions.jsonl"), encoding="utf-8").read(), True)

    # ---------- 4. the next boot on the same disk (a redeploy), with the job list saved by the last run ----------
    import jobs_api
    feeds = [x.strip() for x in ENV.get("UAPLY_FEEDS", "").split(",") if x.strip()]
    srcs = [s for s in jobs_api.SOURCES if s[0] in feeds]
    # the saved list is two hours old (past its 30 minutes, inside the day it may be used) and one board is missing from it (it failed last
    # time), so every board refreshes; the network is a black hole that accepts and never answers, so a request that waited for a board would
    # take 20 seconds or more instead of answering at once
    cache = {"|".join(s): {"at": time.time() - 7200, "jobs": [fake_job(i, s)], "status": "1 jobs"} for i, s in enumerate(srcs[1:])}
    cache["_version"] = jobs_api.CACHE_VERSION
    with open(os.path.join(DISK, "jobs-cache.json"), "w", encoding="utf-8") as f:
        json.dump(cache, f)
    hole = socket.socket()
    hole.bind(("127.0.0.1", PORT + 2))
    hole.listen(64)
    NET = {"HTTPS_PROXY": "http://127.0.0.1:%d" % (PORT + 2), "HTTP_PROXY": "http://127.0.0.1:%d" % (PORT + 2)}
    # a write that was cut short (a full disk, a forced stop): the last line has no end
    with open(os.path.join(inst, "applications.jsonl"), "a", encoding="utf-8") as f:
        f.write('{"id": "cut-short", "job": {"co": "Bro')
    p, log = boot("boot2.log", UAPLY_FEEDS=",".join(feeds), **NET)
    procs.append(p)
    up = wait_up(p)
    t("redeploy: the health check answers within 15 seconds", up is not None and up < 15, True)
    print("     (boot on a filled disk to a passing health check: %s s)" % ("%.1f" % up if up else "never"))
    s, h, body = req("GET", "/api/auth/me", headers={"Cookie": session})
    t("redeploy: the person is still signed in (sessions live on the disk)", (json.loads(body).get("user") or {}).get("email"), "render@example.com")
    s, h, body = req("GET", "/api/outbox", headers=owner())
    t("redeploy: the outbox still has the application", len(json.loads(body).get("applications", [])), 1)
    t0 = time.time()
    s, h, body = req("GET", "/api/jobs")
    took = time.time() - t0
    got = json.loads(body)
    t("redeploy: jobs come at once from the saved copy on the disk, while every board refreshes behind it (%d boards, %.2f s)" % (len(srcs) - 1, took),
      (s, len(got["jobs"]), took < 3), (200, len(srcs) - 1, True))
    t("redeploy: the board missing from the saved copy says loading instead of holding the visitor up",
      got["sources"].get(srcs[0][2] + ("/" + srcs[0][1] if srcs[0][0] in jobs_api.MULTI else "")), "loading")
    t0 = time.time()
    t("redeploy: the health check stays quick while the boards are read", (req("GET", "/healthz")[0], time.time() - t0 < 1), (200, True))
    t("redeploy: feedback is still on the owner's Feedback page", "render feedback one" in req("GET", "/feedback", headers=owner())[2].decode(), True)
    s, h, body = req("POST", "/api/apply", {"consent": True, "job": dict(job, id=900004, role="Second intern"),
                                            "profile": {"ext": {"phone": "215-555-0100"}, "name": "Render Test", "email": "render@example.com"}}, headers={"Cookie": session})
    t("redeploy: a new swipe right after the cut-short line", s, 200)
    stop(p)

    # ---------- 5. the boot after that: the cut-short line hides nothing ----------
    p, log = boot("boot3.log", UAPLY_FEEDS=",".join(feeds), **NET)
    procs.append(p)
    wait_up(p)
    s, h, body = req("GET", "/api/outbox", headers=owner())
    roles = sorted(a.get("job", {}).get("role", "") for a in json.loads(body).get("applications", []))
    t("both applications survive a line that was cut short", roles, ["Intern", "Second intern"])
    t("the log names the skipped broken line", "skipped 1 broken line" in readlog(log), True)
    stop(p)

    # ---------- the sandbox service: its own start command and settings, on its own empty disk ----------
    sb = services.get("uaply-sandbox")
    if sb:
        sb_env = dict(ENV)
        for e in sb.get("envVars", []):
            if "value" in e:
                sb_env[e["key"]] = str(e["value"])
        p, log = boot("sandbox.log", start=sb["startCommand"].split("#")[0].strip(), base=sb_env, UAPLY_FEEDS="", UAPLY_DATA_DIR=os.path.join(TMP, "sb-disk"))
        procs.append(p)
        up = wait_up(p)
        t("sandbox: the health check answers within 15 seconds", up is not None and up < 15, True)
        t("sandbox: home page and Hiring mode's sign-in check answer", (req("GET", "/")[0], req("GET", "/api/employer/me")[0] in (200, 401)), (200, True))
        t("sandbox: the log names the sandbox and its own disk folder", "[uaply] sandbox on" in readlog(log) and os.path.join(TMP, "sb-disk") in readlog(log), True)
        t("sandbox: stops cleanly", stop(p), 0)

    # ---------- 6. a data folder that cannot be written, and a blank PORT ----------
    blocker = os.path.join(TMP, "a-file")
    open(blocker, "w").close()
    p, log = boot("boot4.log", UAPLY_DATA_DIR=os.path.join(blocker, "data"))
    procs.append(p)
    try:
        code = p.wait(timeout=20)
    except subprocess.TimeoutExpired:
        code = None
    text = readlog(log)
    t("unwritable data folder: the server stops at once instead of running without records", code not in (None, 0), True)
    t("unwritable data folder: the log gives the plain reason, not a traceback", ("cannot write the data folder" in text, "Traceback" in text), (True, False))
    r = subprocess.run([sys.executable, "serve.py", "", "dev", "--api"], cwd=ROOT, env=dict(ENV, UAPLY_DATA_DIR=os.path.join(TMP, "x")),
                       capture_output=True, text=True, timeout=20)
    t("a blank port number gives a plain message, not a traceback", (r.returncode != 0, "PORT must be a number" in r.stderr, "Traceback" in r.stderr),
      (True, True, False))
except Exception as e:                                       # a server that never came up, for example: one FAIL instead of a traceback
    t("the checks ran to the end", "%s: %s" % (type(e).__name__, e), "no error")
finally:
    for p in procs:
        if p.poll() is None:
            p.kill()
            p.wait()
    smtp.kill()
    smtp.wait()
    if "hole" in globals():
        hole.close()
    shutil.rmtree(TMP, ignore_errors=True)

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
