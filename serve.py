"""Tiny static server: python serve.py PORT ROOT [--api] [urlpath=file ...]
Serves ROOT; each urlpath=file alias maps one URL to a file outside ROOT (e.g. /prod-index.html to prod/index.html).
--api also exposes the back end used by sandbox and dev (prod does not):
  GET  /api/jobs          real postings (jobs_api.py)
  GET  /api/apply/config  delivery mode
  POST /api/apply         swipe right: deliver an application (uaply_api.py)
  POST /api/decision      swipe left or right: record the swipe
  GET  /outbox            simulated recruiter inbox + swipe stats   (/api/outbox for JSON)
  GET  /api/auth/me       the signed-in account, or null (auth_api.py)
  POST /api/auth/signup   create an account (email + password) and sign in
  POST /api/auth/login    sign in
  POST /api/auth/logout   sign out
  POST /api/auth/delete   delete the signed-in account (password required, or typing DELETE for a Google-only account)
  POST /api/auth/forgot   email a password reset link (the answer never says whether the email has an account)
  POST /api/auth/reset    set a new password from a reset link
  POST /api/auth/change-password   signed in: change the password (needs the current one)
  GET  /setup             owner checklist: Google keys, email login, test email (setup_api.py)
  POST /api/setup/test-mail   send the owner one test email
  POST /api/setup/save-feed-keys   the Job feed keys box (this computer only): save the USAJOBS and The Muse API keys; never echoed back
  POST /api/setup/save-mail   the Connect Gmail form (this computer only): save the Gmail address and App Password, then send a test
  GET  /api/auth/providers      which sign-in methods are on (google_auth.py)
  GET  /api/auth/google/start   "Continue with Google": send the browser to Google
  GET  /api/auth/google/callback  Google returns here; signs the person in and goes back to the app
  GET  /api/chat/config   whether the assistant's AI answers are on (chat_api.py)
  POST /api/chat          UAply Assistant: answer a support question from the help articles
  POST /api/feedback      store feedback sent through the assistant
  GET  /feedback          the feedback summary page (this server only listens on this computer)
  GET  /help/articles.json  the help articles the assistant answers from
  POST /api/auth/verify, /api/auth/resend   the 6-digit code that proves an email is the person's own
  POST /api/auth/google/token   "Continue with Google" through Google's own button
  POST /api/setup/save-google, save-stripe, save-ats, remove-ats   the other boxes on /setup (this computer only)
  GET  /api/billing/status, POST /api/billing/checkout, /api/billing/portal, /api/billing/webhook   Plus and Pro (billing_api.py)
  GET  /api/employer/me, /api/employer/logo/<id>, POST /api/employer/...   Hiring mode, sandbox only (employers_api.py)
  GET  /api/profile/readiness  is the profile complete enough to apply (readiness.py), with what is missing
  POST /api/profile/state      save Profile setup progress for the signed-in account; answers with its readiness
  POST /api/profile/resume   read a resume (PDF, Word or text, up to 5 MB) and answer with the profile fields found; nothing is kept (resume_parse.py)
  GET  /healthz           for the host's health check: {"ok": true} from memory, 503 once the server is stopping (HEAD too)
  POST /api/email/events  Brevo's webhook: bounces and complaints put an address on the bounce list (needs email_events_secret; mailer.py)
  GET  /api/status        what is switched on, as yes/no facts only (never a key, an address or a path), and the deployed commit: for tools/live-check.py
Accounts use an HttpOnly session cookie. When a signed-in user swipes right, a receipt goes to their email."""
import sys, os, re, json, http.server, base64, hmac, threading, time, signal, random

LEGAL_NAME = re.compile(r"^[A-Za-z0-9_-]+\.(html|css|png)$")       # the files in legal/: terms.html, style.css, favicon-32.png ...

try:
    port = int(sys.argv[1])
except (IndexError, ValueError):            # e.g. a host's start command whose $PORT came out empty
    sys.exit("[uaply] usage: python serve.py PORT ROOT [--api]. PORT must be a number (got %r). On Render the start command is "
             "python serve.py ${PORT:-10000} dev --api" % (sys.argv[1] if len(sys.argv) > 1 else ""))
# Locally the server only listens on this computer. A host sets HOST=0.0.0.0 so the public can reach it (always behind HTTPS).
BIND = os.environ.get("HOST", "127.0.0.1")
PUBLIC = BIND not in ("127.0.0.1", "localhost", "::1")
# Owner-only pages (/outbox, /feedback) need this password when the server is public. Without it they are switched off.
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "")
OWNER_PAGES = ("/outbox", "/api/outbox", "/feedback", "/setup")
root = os.path.abspath(sys.argv[2])
rest = sys.argv[3:]
api = "--api" in rest
alias = {}
for a in rest:
    if a == "--api":
        continue
    u, f = a.split("=", 1)
    alias[u] = os.path.abspath(f)

HERE = os.path.dirname(os.path.abspath(__file__))
# browsers and crawlers ask for /favicon.ico whatever the page says: answer with the instance's own icon (a PNG; every browser takes it)
alias.setdefault("/favicon.ico", next((f for f in (os.path.join(root, "favicon-32.png"), os.path.join(HERE, "legal", "favicon-32.png"))
                                       if os.path.isfile(f)), os.path.join(HERE, "legal", "favicon-32.png")))


def data_folder():
    """Where accounts, applications, feedback and the job cache are kept (UAPLY_DATA_DIR on a host, ./data here). It must be writable: without it
    nobody can sign up, so the server stops at once with a plain reason in the log instead of a traceback (on Render: the disk is not attached).
    Returns (folder, persistent) where persistent is False when Render runs this without a separate disk at that folder, None when unknown."""
    d = os.path.abspath(os.environ.get("UAPLY_DATA_DIR") or os.path.join(HERE, "data"))
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write-check-%d" % os.getpid())
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as e:
        sys.exit("[uaply] cannot write the data folder %s (%s: %s). Accounts and applications are kept there. On Render: open the service, "
                 "Disks, and check a disk is attached with the same mount path as UAPLY_DATA_DIR." % (d, type(e).__name__, e))
    # Render sets RENDER=true. Its persistent disk is a separate file system mounted at the folder (or a folder above it); anything else is
    # wiped at every deploy.
    if not os.environ.get("RENDER"):
        return d, None
    p = d
    while os.path.dirname(p) != p:
        if os.path.ismount(p):
            return d, True
        p = os.path.dirname(p)
    return d, False


if api:
    DATA_DIR, PERSISTENT = data_folder()
    # the sandbox and dev pages load these shared files and a copy of the production page; no command-line aliases needed
    for url, rel in (("/uaply-envs.js", "shared/uaply-envs.js"), ("/uaply-nav.js", "shared/uaply-nav.js"),
                     ("/uaply-live.js", "shared/uaply-live.js"), ("/uaply-profile.js", "shared/uaply-profile.js"),
                     ("/uaply-chat.js", "shared/uaply-chat.js"), ("/uaply-employers.js", "shared/uaply-employers.js"),
                     ("/uaply-learn.js", "shared/uaply-learn.js"), ("/uaply-resume.js", "shared/uaply-resume.js"),
                     ("/uaply-onboard.js", "shared/uaply-onboard.js"),
                     ("/help/articles.json", "help/articles.json"),
                     ("/prod-index.html", "prod/index.html")):
        alias.setdefault(url, os.path.join(HERE, rel))
    import jobs_api, uaply_api, auth_api, chat_api, google_auth, setup_api, billing_api, employers_api, resume_parse
    uaply_api.init(os.path.basename(root))
    employers_api.init(os.path.basename(root))                    # Hiring mode: on for the sandbox only
    auth_api.init(os.path.basename(root))
    chat_api.init(os.path.basename(root))
    billing_api.PUBLIC = PUBLIC                                     # Plan and billing: buy buttons on a public server only when Stripe keys are set
    uaply_api.hide_errors = jobs_api.hide_errors = PUBLIC       # a hosted server never shows visitors raw error text; the owner's own computer still does
    uaply_api.PUBLIC = PUBLIC                                   # the live site never labels a real hand-off email [TEST]
    uaply_api.start_mail_worker()                               # sends receipts and copies held back by the daily email limit (mailer.py)
    # the job-list warm-up starts after the port is bound (at the end of this file), so the health check passes at once

OOPS ="Something went wrong on our side. Try again in a moment."


def log_oops(where, e):
    """The real reason goes to the server's own log (the owner can read it there); a visitor only ever sees the plain sentence above."""
    sys.stderr.write("[uaply] %s failed: %s: %s\n" % (where, type(e).__name__, str(e)[:300]))
    sys.stderr.flush()


# robots.txt: the app and the legal pages may be indexed; the API and the owner-only pages are not pages for search engines
ROBOTS = b"User-agent: *\nDisallow: /api/\nDisallow: /outbox\nDisallow: /feedback\nDisallow: /setup\nAllow: /\n"
# the app's own page for an address that does not exist (it used to be Python's bare "Error response" page)
NOT_FOUND_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Page not found - UAply</title><link rel="icon" type="image/png" href="/favicon.ico"><meta name="robots" content="noindex">
<style>
:root{--bg:#FDF0F2;--surface:#FFFFFF;--ink:#2A1218;--muted:#7B5560;--line:#F3DADF;--accent:#C92A55;--accent2:#F0663B;--accent-ink:#FFFFFF}
@media (prefers-color-scheme: dark){:root{--bg:#190B10;--surface:#26131A;--ink:#FBE9EE;--muted:#C79BA6;--line:#40222B;--accent:#FF7A98;--accent2:#FFA86B;--accent-ink:#1A0A0F}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px 16px;background:var(--bg);color:var(--ink);font:16px/1.5 'DM Sans','Segoe UI',system-ui,sans-serif}
main{max-width:420px;width:100%;background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:28px 24px;text-align:center}
h1{margin:0 0 8px;font-size:24px}p{margin:0 0 20px;color:var(--muted)}
a.btn{display:inline-block;min-height:44px;padding:11px 22px;border-radius:999px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--accent-ink);font-weight:700;text-decoration:none}
nav{margin-top:18px;font-size:14px;color:var(--muted)}nav a{color:inherit}
</style></head>
<body><main><h1>Page not found</h1><p>There is nothing at this address. It may have moved, or the link may have a typo.</p>
<a class="btn" href="/">Back to UAply</a>
<nav><a href="/legal/">Terms and policies</a> &middot; <a href="/legal/support.html">Support</a></nav></main></body></html>
""".encode("utf-8")

MAX_BODY = 40000
MAX_APPLY_BODY = 1500000
MAX_COMPANY_BODY = 200000

# Swipes per visitor per minute. A person swipes a few times a minute; a script hammering the server would otherwise fill its disk and memory.
SWIPE_LIMITS = {"/api/apply": 40, "/api/decision": 150, "/api/profile/resume": 12}   # a person reads a resume once or twice
_swipes, _swipes_lock = {}, threading.Lock()
_resume_count, _resume_count_lock = [0], threading.Lock()          # resumes read since the start: the only thing the log says about them


def too_fast(path, ip):
    limit = SWIPE_LIMITS.get(path)
    if not limit:
        return False
    now = time.time()
    with _swipes_lock:
        if len(_swipes) > 20000:                          # forget visitors who have gone quiet
            for k in [k for k, v in _swipes.items() if not v or now - v[-1] > 60]:
                del _swipes[k]
        hits = [t for t in _swipes.get((path, ip), []) if now - t < 60]
        if len(hits) >= limit:
            _swipes[(path, ip)] = hits
            return True
        hits.append(now)
        _swipes[(path, ip)] = hits
        return False


def dns_check():
    """Whether sign-up asks DNS if the address's domain can receive mail (auth_api.mail_domain_status). On by default only where it
    matters: a public server that really sends the code, where a dead domain would only bounce and hurt the sender's reputation.
    UAPLY_DNS_CHECK=on or off overrides that (tests use on, with UAPLY_DNS_SERVER pointing at a stand-in resolver)."""
    force = (os.environ.get("UAPLY_DNS_CHECK") or "").strip().lower()
    if force in ("on", "off"):
        return force == "on"
    return PUBLIC and bool(uaply_api.mail_ready())


# ---- what the server did: one line per API request, and one summary line a day (at midnight UTC, and when the server stops) ----
# The lines hold no IP address, no query string (reset links carry their token there), no cookie and no email address: only the method,
# the path, the status and the time taken. UAPLY_REQUEST_LOG=off keeps the per-request lines out (the daily line stays).
REQUEST_LOG = (os.environ.get("UAPLY_REQUEST_LOG") or "on").strip().lower() not in ("off", "0", "no", "false")
SLOW_MS = 1000                                   # any request slower than this gets its line, whatever its path
MAX_PATHS = 80                                   # distinct paths kept in the day's figures (scanners try thousands of made-up ones)
_stats_lock = threading.Lock()


def _new_stats():
    return {"since": time.time(), "requests": 0, "health": 0, "codes": {}, "paths": {}, "signups": 0, "logins": 0, "applications": 0, "ms": []}


TIMES_KEPT = 20000                               # request times kept for the day's p50 and p95 (a fair sample once there are more)


_stats = _new_stats()


def _path_key(path):
    if path.startswith("/api/employer/logo/"):
        return "/api/employer/logo/*"
    if path.startswith("/api/") or path in OWNER_PAGES or path in ("/", "/robots.txt"):
        return path[:60]
    return "(files and pages)"


def record_request(method, path, code, ms):
    """Count one answered request (called by the handler) and log its line when it is an API call, an error or slow."""
    if path == "/healthz":                                       # Render asks every few seconds: counted apart, never logged
        with _stats_lock:
            _stats["health"] += 1
        return
    key = _path_key(path)
    with _stats_lock:
        s = _stats
        s["requests"] += 1
        s["codes"][code] = s["codes"].get(code, 0) + 1
        if key not in s["paths"] and len(s["paths"]) >= MAX_PATHS:
            key = "(other)"
        n, total, worst = s["paths"].get(key, (0, 0.0, 0.0))
        s["paths"][key] = (n + 1, total + ms, max(worst, ms))
        if len(s["ms"]) < TIMES_KEPT:                            # Render shows response times only on its Pro plan: these stand in for them
            s["ms"].append(ms)
        else:                                                    # reservoir sampling: every request of the day equally likely to be kept
            i = random.randrange(s["requests"])
            if i < TIMES_KEPT:
                s["ms"][i] = ms
        if method == "POST" and code == 200:
            if path == "/api/auth/signup":
                s["signups"] += 1
            elif path == "/api/auth/login":
                s["logins"] += 1
            elif path == "/api/apply":
                s["applications"] += 1
    if REQUEST_LOG and PUBLIC and (path.startswith("/api/") or path in OWNER_PAGES or code >= 500 or ms >= SLOW_MS):
        sys.stderr.write("[uaply] %s %s %d %d ms\n" % (method, key if key != "(files and pages)" else path[:80], code, ms))
        sys.stderr.flush()


def _rss_mb():
    """This process's memory now and at its peak, in MB (Linux; None elsewhere). Read from /proc: no extra module, a microsecond."""
    try:
        with open("/proc/self/status") as f:
            st = f.read()
        return tuple(int(re.search(r"%s:\s+(\d+)" % k, st).group(1)) // 1024 for k in ("VmRSS", "VmHWM"))
    except (OSError, AttributeError):
        return None, None


def daily_summary(reason="day"):
    """The day's figures as one line of JSON after '[uaply] daily', and a fresh count. reason: 'day' at midnight UTC, 'stop' at a deploy."""
    global _stats
    with _stats_lock:
        s, _stats = _stats, _new_stats()
    codes = s["codes"]
    slowest = sorted(((v[1] / v[0], k, v) for k, v in s["paths"].items() if v[0]), reverse=True)[:5]
    now_mb, peak_mb = _rss_mb()
    times = sorted(s["ms"])

    def pct(q):
        return int(times[min(len(times) - 1, int(len(times) * q / 100))]) if times else None
    out = {"day": time.strftime("%Y-%m-%d", time.gmtime(s["since"])), "from": time.strftime("%H:%M", time.gmtime(s["since"])),
           "to": time.strftime("%H:%M", time.gmtime()), "why": reason, "requests": s["requests"],
           "2xx": sum(n for c, n in codes.items() if 200 <= c < 300), "3xx": sum(n for c, n in codes.items() if 300 <= c < 400),
           "4xx": sum(n for c, n in codes.items() if 400 <= c < 500), "429": codes.get(429, 0),
           "5xx": sum(n for c, n in codes.items() if c >= 500), "signups": s["signups"], "logins": s["logins"], "applications": s["applications"],
           "p50_ms": pct(50), "p95_ms": pct(95),
           "slowest": [{"path": k, "n": v[0], "avg_ms": int(avg), "max_ms": int(v[2])} for avg, k, v in slowest],
           "health_checks": s["health"], "memory_mb": now_mb, "peak_memory_mb": peak_mb}
    return "[uaply] daily " + json.dumps(out, separators=(",", ":"))


def _midnight_loop():
    while True:
        now = time.time()
        time.sleep((int(now // 86400) + 1) * 86400 - now + 0.5)   # just after midnight UTC
        sys.stderr.write(daily_summary("day") + "\n")
        sys.stderr.flush()


_stopping = threading.Event()                    # set at SIGTERM: /healthz answers 503 from then on


class H(http.server.SimpleHTTPRequestHandler):
    server_version = "UAply"                     # not "SimpleHTTP/0.6 Python/3.12.7": no version for a scanner to match (Render passes it on)
    sys_version = ""

    def __init__(self, *a, **k):
        super().__init__(*a, directory=root, **k)

    def version_string(self):
        return self.server_version

    def handle_one_request(self):
        """Count the requests being answered, so a stop (a deploy) can let them finish first. An idle kept-open connection is not counted."""
        self._counted = False
        self._code = None
        try:
            super().handle_one_request()
        finally:
            if self._counted:
                with _busy_lock:
                    _busy[0] -= 1
                if self._code and getattr(self, "command", None):
                    try:
                        record_request(self.command, self.path.split("?", 1)[0], self._code, (time.monotonic() - self._t0) * 1000)
                    except Exception:
                        pass

    def send_response(self, code, message=None):
        self._code = code
        super().send_response(code, message)

    def parse_request(self):
        """A null byte in the address (raw or as %00) is never valid: answer 400 instead of letting the file lookup fail and drop the connection."""
        with _busy_lock:                                     # a request line arrived: from here on this request is "in progress"
            _busy[0] += 1
        self._counted = True
        self._t0 = time.monotonic()
        if not super().parse_request():
            return False
        if "\x00" in self.path or "%00" in self.path.lower():
            self.send_error(400, "Bad request")
            return False
        return True

    def translate_path(self, path):
        p = path.split("?", 1)[0].split("#", 1)[0]
        if api and p.startswith("/legal/"):                              # Terms, Privacy, AI disclosure, Copyright
            # only a plain file name inside legal/. Joining the raw rest of the address once let /legal//etc/passwd (or
            # /legal/C:/...) read ANY file on the server, because joining onto an absolute path throws the folder away.
            name = p[len("/legal/"):] or "index.html"
            return os.path.join(HERE, "legal", name if LEGAL_NAME.match(name) else "not-a-legal-page")
        return alias.get(p) or super().translate_path(path)

    def send_error(self, code, message=None, explain=None):
        """A page that does not exist gets the app's own "Page not found" page with a way back, not Python's bare error page.
        Addresses under /api/ keep the plain answer (scripts read those, not people); every other error is unchanged."""
        if code != 404 or self.path.split("?", 1)[0].startswith("/api/") or self.command not in ("GET", "HEAD"):
            return super().send_error(code, message, explain)
        self.send_response(404, message)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(NOT_FOUND_PAGE)))
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        if self.command == "GET":
            self.wfile.write(NOT_FOUND_PAGE)

    def _send(self, code, body, ctype="application/json", headers=()):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _refuse(self, code, body):
        """Answer a request whose body is not read (or not wanted), then hang up cleanly. Closing a connection while the client's body is still
        unread makes the system reset it, and the client can lose the answer before reading it (seen on Windows with a garbled Content-Length).
        So: say "Connection: close", then read away whatever is still arriving for a moment before the server closes."""
        self._send(code, body, headers=(("Connection", "close"),))
        try:
            self.connection.settimeout(0.2)
            for _ in range(32):                                  # at most about 2 MB, and never longer than the client keeps sending
                if not self.connection.recv(65536):
                    break
        except OSError:
            pass

    def _cookie_value(self, name):
        """One cookie's value from the request ('' if absent). Parsed by hand on purpose: other sites' tools set cookies with quotes and commas in
        them (Google's sign-in button sets g_state={"i_l":0}), and Python's strict parser then throws away the WHOLE header, signing people out."""
        for part in (self.headers.get("Cookie") or "").split(";"):
            key, sep, val = part.strip().partition("=")
            if sep and key == name:
                return val.strip().strip('"')
        return ""

    def _token(self):
        """The session token from this instance's cookie ('' if there is none)."""
        return self._cookie_value(auth_api.cookie_name())

    def _cookie(self, token):
        secure = "; Secure" if (self.headers.get("X-Forwarded-Proto") == "https") else ""
        age = auth_api.SESSION_SECONDS if token else 0
        return [("Set-Cookie", "%s=%s; HttpOnly; SameSite=Lax; Path=/; Max-Age=%d%s" % (auth_api.cookie_name(), token, age, secure))]

    def _origin_parts(self):
        host = self.headers.get("Host") or "localhost"
        return host, ("https" if self.headers.get("X-Forwarded-Proto") == "https" else "http")

    def _site_base(self):
        """The public address of this site, for links in emails."""
        cfg = uaply_api.config()
        g = cfg.get("google") if isinstance(cfg.get("google"), dict) else {}
        for v in (cfg.get("public_url"), g.get("public_url")):
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                return v.rstrip("/")
        host, proto = self._origin_parts()
        return "%s://%s" % (proto, host)

    def _redirect(self, where, headers=()):
        self.send_response(302)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()

    def _oauth_cookie(self, value):
        secure = "; Secure" if (self.headers.get("X-Forwarded-Proto") == "https") else ""
        return ("Set-Cookie", "%s_oauth=%s; HttpOnly; SameSite=Lax; Path=/api/auth/google; Max-Age=%d%s" % (
            auth_api.cookie_name(), value, 600 if value else 0, secure))

    def _google(self, p):
        """The two redirects of "Continue with Google"."""
        import urllib.parse
        q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
        host, proto = self._origin_parts()
        if p == "/api/auth/google/start":
            url, state = google_auth.start(host, proto, (q.get("agree") or [""])[0] == "1")
            if not url:
                return self._redirect("/?auth_error=off")
            return self._redirect(url, [self._oauth_cookie(state)])
        err, ident, agreed = google_auth.finish(q, self._cookie_value(auth_api.cookie_name() + "_oauth"), host, proto)
        if err:
            return self._redirect("/?auth_error=" + err, [self._oauth_cookie("")])
        err, user, token = auth_api.oauth_login(ident["provider"], ident["subject"], ident["email"], agreed, ident.get("trusted", True))
        if err:
            return self._redirect("/?auth_error=" + err, [self._oauth_cookie("")])
        return self._redirect("/?signed_in=google" + ("&password_removed=1" if user.get("passwordRemoved") else ""), self._cookie(token) + [self._oauth_cookie("")])

    def _owner_ok(self):
        """Owner pages: open on this computer; on a public server only with OWNER_PASSWORD (any username)."""
        if not PUBLIC:
            return True
        if not OWNER_PASSWORD:
            return False
        try:
            kind, val = (self.headers.get("Authorization") or "").split(" ", 1)
            pw = base64.b64decode(val).decode("utf-8").split(":", 1)[1] if kind == "Basic" else ""
        except Exception:
            pw = ""
        return hmac.compare_digest(pw.encode(), OWNER_PASSWORD.encode())

    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/healthz":                                                 # for the host's health check
            return self._health()
        if p == "/robots.txt":
            return self._send(200, ROBOTS, "text/plain; charset=utf-8")
        if api and p == "/legal":                                           # a typed uaply.net/legal (no slash) finds the legal pages too
            return self._redirect("/legal/")
        if api and p in OWNER_PAGES and not self._owner_ok():
            if not OWNER_PASSWORD:
                return self._send(403, {"error": "Owner pages are off on this server. Set OWNER_PASSWORD to use them."})
            return self._send(401, {"error": "Owner password required."}, headers=[("WWW-Authenticate", 'Basic realm="UAply owner"')])
        if api:
            try:
                if p == "/api/jobs":
                    return self._send(200, jobs_api.get_json())
                if p == "/api/apply/config":
                    cfg_out = uaply_api.public_config()
                    if not PUBLIC:                          # only a copy running on the owner's computer has a test inbox page to point to
                        cfg_out["testInbox"] = "/outbox"
                    return self._send(200, cfg_out)
                if p == "/api/outbox":
                    return self._send(200, uaply_api.outbox_json())
                if p == "/outbox":
                    return self._send(200, uaply_api.outbox_html(), "text/html; charset=utf-8")
                if p == "/api/status":
                    return self._send(200, status_facts())
                if p == "/api/profile/readiness":
                    return self._send(*uaply_api.get_readiness(auth_api.user_for(self._token())))
                if p == "/api/auth/me":
                    return self._send(200, {"user": auth_api.user_for(self._token())})
                if p == "/api/auth/providers":
                    return self._send(200, google_auth.public_config(*self._origin_parts()))
                if p in ("/api/auth/google/start", "/api/auth/google/callback"):
                    return self._google(p)
                if p == "/api/billing/status":
                    return self._send(200, billing_api.status(auth_api.user_for(self._token())))
                if p == "/api/employer/me":
                    return self._send(*employers_api.me(auth_api.user_for(self._token())))
                if p.startswith("/api/employer/logo/"):
                    img = employers_api.logo(p[len("/api/employer/logo/"):])
                    return self._send(200, img[1], img[0]) if img else self._send(404, {"error": "not found"})
                if p == "/api/chat/config":
                    return self._send(200, dict(chat_api.public_config(), owner=not PUBLIC))      # "owner": this server runs on the owner's own computer, so owner-only hints may be shown
                if p == "/feedback":
                    return self._send(200, chat_api.feedback_html(), "text/html; charset=utf-8")
                if p == "/setup":
                    return self._send(200, setup_api.page(*self._origin_parts()), "text/html; charset=utf-8")
            except Exception as e:
                log_oops(p, e)
                return self._send(502, {"error": OOPS})
        super().do_GET()

    def _health(self, head=False):
        """Render's health check: answered from memory (no disk, no job feeds, no lock), so it stays quick while the boards are being read.
        503 once the server is stopping, so nothing new is sent to a copy that is on its way out."""
        code, body = (503, b'{"ok": false, "stopping": true}') if _stopping.is_set() else (200, b'{"ok": true}')
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if code == 503:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def do_HEAD(self):
        if self.path.split("?", 1)[0] == "/healthz":                     # uptime monitors often ask with HEAD
            return self._health(head=True)
        super().do_HEAD()

    def do_POST(self):
        p = self.path.split("?", 1)[0]
        if api and p == "/api/billing/webhook":        # from Stripe, not from our pages: its signature replaces the same-site check
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if not 0 < n <= 512000:
                return self._refuse(400, {"error": "bad size"})
            try:
                code, out = billing_api.webhook(self.rfile.read(n), self.headers.get("Stripe-Signature") or "")
            except Exception as e:                      # say so (Stripe then sends the event again later) instead of dropping the connection
                log_oops(p, e)
                code, out = 500, {"error": OOPS}
            return self._send(code, out)
        if api and p == "/api/email/events":           # from Brevo (bounces, complaints): the shared secret replaces the same-site check
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if not 0 < n <= 262144:
                return self._refuse(400, {"error": "bad size"})
            try:
                code, out = uaply_api.email_events(self.rfile.read(n), self.headers.get("Authorization") or "")
            except Exception as e:
                log_oops(p, e)
                code, out = 500, {"error": OOPS}
            return self._send(code, out, headers=[("WWW-Authenticate", 'Basic realm="uaply"')] if code == 401 else ())
        if not api or p not in ("/api/apply", "/api/decision", "/api/auth/signup", "/api/auth/login", "/api/auth/logout",
                                "/api/auth/delete", "/api/auth/forgot", "/api/auth/reset", "/api/auth/change-password",
                                "/api/setup/test-mail", "/api/setup/save-mail", "/api/setup/save-google", "/api/setup/save-ats", "/api/setup/remove-ats", "/api/setup/save-stripe", "/api/setup/save-feed-keys", "/api/auth/google/token", "/api/auth/verify", "/api/auth/resend", "/api/chat", "/api/feedback", "/api/billing/checkout", "/api/billing/portal",
                                "/api/employer/company", "/api/employer/job", "/api/employer/job/status", "/api/employer/applicant",
                                "/api/employer/import", "/api/profile/resume", "/api/profile/state"):
            return self._refuse(404, {"error": "not found"})
        # Only accept requests made by this site's own pages (blocks cross-site forms and scripts).
        origin = self.headers.get("Origin")
        host = self.headers.get("Host") or ""
        if origin not in ("http://" + host, "https://" + host) or (PUBLIC and origin != "https://" + host and
                                                                  self.headers.get("X-Forwarded-Proto") == "https"):
            return self._refuse(403, {"error": "cross-site request refused"})
        if p == "/api/profile/resume":
            return self._resume_upload()
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:                                                                     # nothing was sent: a bad request, not a too-large one
                return self._refuse(400, {"error": "bad request"})
            # an application may carry a resume file (up to 1 MB, sent as text); a company profile may carry its logo (up to 120 KB)
            if n > (MAX_APPLY_BODY if p == "/api/apply" else MAX_COMPANY_BODY if p == "/api/employer/company" else MAX_BODY):
                if p == "/api/apply":                    # the app shows this sentence to the person, so it says what to do
                    return self._refuse(413, {"error": "This application is too large to send. Use a resume file under 1 MB (Profile setup, Background and links).", "code": "too_big"})
                return self._refuse(413, {"error": "bad size"})
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("not an object")
        except Exception:                                        # a garbled Content-Length, a body that is not JSON, or one that is not an object
            return self._refuse(400, {"error": "bad request"})
        ip = self.client_address[0]
        if PUBLIC and self.headers.get("X-Forwarded-For"):          # behind the host's proxy: the visitor's own address
            ip = self.headers["X-Forwarded-For"].split(",")[0].strip()[:64] or ip
        if too_fast(p, ip):
            return self._send(429, {"error": "You're swiping faster than UAply can keep up. Wait a moment and try again.", "code": "slow_down"})
        try:
            if p == "/api/auth/signup":
                # the account and its first code are made in one locked step (auth_api.signup_with_code), so a Google sign-in for the same
                # address racing this sign-up can never leave it half made
                code, out, token, mail = auth_api.signup_with_code(payload.get("email"), payload.get("password"), ip, payload.get("agree"),
                                                                   dns_check(), auth_api.SIGNUPS_PER_HOUR if PUBLIC else None)
                if mail:                                         # a new password account must prove it owns the email: send the first code
                    uid, addr, digits = mail
                    out = dict(out, delivery=uaply_api.send_verification_mail(uid, addr, digits))
                return self._send(code, out, headers=self._cookie(token) if token else ())
            if p == "/api/auth/login":
                code, out, token = auth_api.login(payload.get("email"), payload.get("password"), ip)
                return self._send(code, out, headers=self._cookie(token) if token else ())
            if p == "/api/setup/save-google":
                if not self._owner_ok():
                    return self._send(403, {"error": "Owner pages are off or need the owner password."})
                if PUBLIC:
                    return self._send(403, {"ok": False, "message": "On a hosted server, add the Google client ID in the host's dashboard (UAPLY_CONFIG_JSON), not here."})
                code, out = setup_api.save_google(payload)
                return self._send(code, out)
            if p == "/api/setup/save-stripe":
                if not self._owner_ok():
                    return self._send(403, {"error": "Owner pages are off or need the owner password."})
                if PUBLIC:
                    return self._send(403, {"ok": False, "message": "On a hosted server, add the Stripe keys in the host's dashboard (STRIPE_SECRET_KEY and the others), not here."})
                code, out = setup_api.save_stripe(payload)
                return self._send(code, out)
            if p in ("/api/setup/save-ats", "/api/setup/remove-ats"):
                if not self._owner_ok():
                    return self._send(403, {"error": "Owner pages are off or need the owner password."})
                if PUBLIC:                                      # a host keeps keys in its dashboard (UAPLY_ATS_JSON), not in a file a page can write
                    return self._send(403, {"ok": False, "message": "On a hosted server, add employers' keys in the host's dashboard (UAPLY_ATS_JSON), not here."})
                code, out = (setup_api.save_ats if p.endswith("save-ats") else setup_api.remove_ats)(payload)
                return self._send(code, out)
            if p == "/api/setup/save-feed-keys":
                if not self._owner_ok():
                    return self._send(403, {"error": "Owner pages are off or need the owner password."})
                if PUBLIC:                                      # a hosted server keeps its keys in its dashboard, not in a file the page can write
                    return self._send(403, {"ok": False, "message": "On a hosted server, add the job feed keys in the host's dashboard (UAPLY_CONFIG_JSON, feed_keys), not here."})
                code, out = setup_api.save_feed_keys(payload)
                return self._send(code, out)
            if p == "/api/setup/save-mail":
                if not self._owner_ok():
                    return self._send(403, {"error": "Owner pages are off or need the owner password."})
                if PUBLIC:                                      # a hosted server keeps its secrets in its dashboard, not in a file the page can write
                    return self._send(403, {"ok": False, "message": "On a hosted server, add the email settings in the host's dashboard (UAPLY_CONFIG_JSON), not here."})
                code, out = setup_api.save_mail(payload)
                return self._send(code, out)
            if p == "/api/setup/test-mail":
                if not self._owner_ok():
                    return self._send(403, {"error": "Owner pages are off or need the owner password."})
                code, out = setup_api.test_mail()
                return self._send(code, out)
            if p == "/api/auth/google/token":                    # "Continue with Google": the page sends the signed token Google's button gave it
                msg = {"agree": "Tick the box to confirm you are 18 or older and agree to the Terms and Privacy Policy, then choose Google again.",
                       "failed": "Google sign-in could not be checked. Try again.", "unverified": "Google says that email address is not verified, so UAply cannot use it.",
                       "off": "Google sign-in is not switched on.", "limited": "Too many tries. Wait a minute and try again.",
                       "email_in_use": "That email already has a UAply account. Sign in with your email and password instead.",
                       "disposable": auth_api.KEEP_MSG}
                err, ident = google_auth.verify_credential(payload.get("credential"), ip)
                if not err:
                    err, user, token = auth_api.oauth_login(ident["provider"], ident["subject"], ident["email"], payload.get("agree") is True, ident.get("trusted", True))
                if err:
                    return self._send(429 if err == "limited" else 400, {"error": msg.get(err, msg["failed"]), "code": err})
                out = {"user": user}
                if user.pop("passwordRemoved", False):           # a password nobody had proven was the owner's was removed (auth_api.oauth_login)
                    out["passwordRemoved"] = True
                return self._send(200, out, headers=self._cookie(token))
            if p == "/api/auth/verify":
                code, out = auth_api.verify_code(self._token(), payload.get("code"), ip)
                return self._send(code, out)
            if p == "/api/auth/resend":
                code, out, mail = auth_api.resend_code(self._token(), ip)
                if mail:
                    uid, addr, digits = mail
                    mail_status = uaply_api.send_verification_mail(uid, addr, digits)
                    out = dict(out, delivery=mail_status)
                return self._send(code, out)
            if p == "/api/auth/forgot":
                if PUBLIC and not uaply_api.mail_ready():       # a real server that cannot send email must not pretend to
                    return self._send(200, {"ok": False, "delivery": "unavailable",
                                            "message": "Password reset by email is not available right now. Use Help, then Talk to a person, and we will help you get back in."})
                code, out, mail = auth_api.request_reset(payload.get("email"), ip)
                if mail:
                    uid, addr, tok = mail
                    link = self._site_base() + "/?reset=" + tok
                    body = ("Hi,\n\nSomeone asked to reset the password for this UAply account. Use this link within one hour:\n\n%s\n\n"
                            "If you did not ask for this, ignore this email; your password has not changed.\n\n--\nUAply") % link
                    status = uaply_api.send_system_mail(uid, addr, "Reset your UAply password", body, secret=True, kind="reset")
                    out = dict(out, delivery=status)
                else:
                    out = dict(out, delivery=("sent" if uaply_api.mail_ready() else "delivered_test"))
                return self._send(code, out)
            if p == "/api/auth/reset":
                code, out = auth_api.reset_password(payload.get("token"), payload.get("password"), ip)
                return self._send(code, out, headers=self._cookie("") if code == 200 else ())
            if p == "/api/auth/change-password":
                code, out = auth_api.change_password(self._token(), payload.get("current"), payload.get("password"), ip)
                return self._send(code, out)
            if p == "/api/auth/logout":
                auth_api.logout(self._token())
                return self._send(200, {"ok": True}, headers=self._cookie(""))
            if p == "/api/auth/delete":
                # the Stripe subscription is cancelled first; if Stripe refuses, the account is kept (billing_api.cancel_on_delete)
                code, out, uid = auth_api.delete_account(self._token(), payload.get("password"), ip, payload.get("confirm") or "",
                                                         before_delete=billing_api.cancel_on_delete)
                if uid:
                    out["applicationsRemoved"] = uaply_api.forget_user(uid)
                    chat_api.forget_user(uid)
                    return self._send(code, out, headers=self._cookie(""))
                return self._send(code, out)
            if p == "/api/chat":
                code, out = chat_api.chat(payload, ip)
            elif p == "/api/feedback":
                code, out = chat_api.feedback(payload, ip, auth_api.user_for(self._token()), notify=uaply_api.send_support_ticket)
            elif p == "/api/apply":
                u = auth_api.user_for(self._token())
                over = billing_api.limit_reached(u)
                code, out = (402, {"error": over, "code": "limit"}) if over else uaply_api.submit(payload, u, self._site_base())
            elif p == "/api/profile/state":
                code, out = uaply_api.save_readiness(payload, auth_api.user_for(self._token()))
            elif p == "/api/billing/checkout":
                code, out = billing_api.checkout(auth_api.user_for(self._token()), payload.get("plan"), self._site_base())
            elif p == "/api/billing/portal":
                code, out = billing_api.portal(auth_api.user_for(self._token()), self._site_base())
            elif p == "/api/employer/company":
                code, out = employers_api.save_company(auth_api.user_for(self._token()), payload)
            elif p == "/api/employer/job":
                code, out = employers_api.save_job(auth_api.user_for(self._token()), payload)
            elif p == "/api/employer/job/status":
                code, out = employers_api.set_status(auth_api.user_for(self._token()), payload)
            elif p == "/api/employer/applicant":
                code, out = employers_api.set_stage(auth_api.user_for(self._token()), payload)
            elif p == "/api/employer/import":
                code, out = employers_api.import_page(auth_api.user_for(self._token()), payload.get("url"))
            else:
                code, out = uaply_api.record_decision(payload)
        except Exception as e:
            log_oops(p, e)
            code, out = 500, {"error": OOPS}
        self._send(code, out)

    def _resume_upload(self):
        """Fill from your resume: the file (JSON with a data: URL, or a multipart form) is read in memory and the fields found go back to the
        page. No account is needed (the profile lives on the device), the file and its text are never written anywhere, and the log gets only
        a count."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n <= 0:
            return self._refuse(400, {"error": resume_parse.MESSAGES["bad_request"], "code": "bad_request"})
        if n > resume_parse.MAX_BODY:
            return self._refuse(413, {"error": resume_parse.MESSAGES["too_big"], "code": "too_big"})
        ip = self.client_address[0]
        if PUBLIC and self.headers.get("X-Forwarded-For"):
            ip = self.headers["X-Forwarded-For"].split(",")[0].strip()[:64] or ip
        if too_fast("/api/profile/resume", ip):
            return self._refuse(429, {"error": "You have read several resumes in a minute. Wait a moment and try again.", "code": "slow_down"})
        try:
            body = self.rfile.read(n)
            code, out = resume_parse.handle(body, self.headers.get("Content-Type") or "")
        except Exception as e:
            log_oops("/api/profile/resume", e)
            code, out = 500, {"error": OOPS}
        with _resume_count_lock:
            _resume_count[0] += 1
            sys.stderr.write("[uaply] resume read #%d: %s\n" % (_resume_count[0], ("%s, %d fields" % (out.get("kind"), out.get("found", 0))) if code == 200 else out.get("code", code)))
        self._send(code, out)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "SAMEORIGIN")               # the app frames itself; other sites may not
        # the same rule for browsers that only read CSP, plus no plugins and no <base> tag pointing scripts elsewhere. Deliberately no script
        # or style rules: the pages carry their own inline code, and Google's and Stripe's pages are reached by full-page redirects.
        self.send_header("Content-Security-Policy", "frame-ancestors 'self'; object-src 'none'; base-uri 'self'")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), usb=(), payment=()")   # never used; location stays the browser's default (the app asks)
        if self.headers.get("X-Forwarded-Proto") == "https":
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        super().end_headers()

    def log_message(self, fmt, *args):
        if not PUBLIC:                                                   # keep request logs out of a host's logs (they hold IPs)
            super().log_message(fmt, *args)

def status_facts():
    """GET /api/status: the same on/off facts as the start-up line in the log, so a check run from anywhere (tools/live-check.py) can say what
    is configured after a deploy. Only yes/no answers: never a key, a password, an email address, a price id or a folder name.
    persistent is null where it cannot be known (any host but Render, or the owner's own computer). commit is the one exception to yes/no: the
    short id of the deployed commit (RENDER_GIT_COMMIT), or null off Render."""
    b = billing_api.settings()
    return {"ok": True, "public": PUBLIC, "persistent": PERSISTENT, "email": bool(uaply_api.mail_ready()),
            "emailEvents": bool(uaply_api.events_secret()),
            "google": bool(google_auth.enabled()), "googleButton": bool(google_auth.button_enabled()),
            "payments": bool(b["on"]), "paymentsTest": bool(b["on"] and b["test"]),
            "paymentsWebhook": bool(b["on"] and str(b.get("webhook_secret") or "").startswith("whsec_")),
            "ai": bool(chat_api.ai_ready()), "ownerPages": bool(OWNER_PASSWORD) if PUBLIC else True, "commit": COMMIT}


# The commit this copy runs: Render sets RENDER_GIT_COMMIT (the full id) for every deploy. Only its first 7 hex digits are shown (public
# anyway on GitHub); tools/live-check.py compares them with the branch on GitHub, so a deploy that never happened is caught. None elsewhere.
COMMIT = (lambda c: c[:7] if re.fullmatch(r"[0-9a-f]{7,40}", c) else None)((os.environ.get("RENDER_GIT_COMMIT") or "").strip().lower())


class Server(http.server.ThreadingHTTPServer):
    request_queue_size = 128         # Python's default of 5 refuses connections outright when a burst of visitors arrives at once


def startup_summary():
    """One line in the host's log saying what this server will do: where records go and which features are on. Never a secret, only on/off."""
    if not api:
        return "[uaply] serving %s on %s:%d" % (root, BIND, port)
    try:
        json.loads(os.environ.get("UAPLY_CONFIG_JSON") or "{}")
        cfg_note = "valid" if os.environ.get("UAPLY_CONFIG_JSON") else "not set"
    except ValueError:
        cfg_note = "NOT VALID JSON, ignored"
    disk = {True: "persistent disk", False: "NOT a persistent disk: everything is lost at the next deploy", None: "local folder"}[PERSISTENT]
    return ("[uaply] %s on %s:%d (%s) | data: %s (%s) | feeds: %s | email: %s | owner pages: %s | AI answers: %s | Google sign-in: %s | payments: %s | UAPLY_CONFIG_JSON: %s | commit: %s"
            % (os.path.basename(root), BIND, port, "public" if PUBLIC else "this computer only", DATA_DIR, disk,
               ",".join(sorted(jobs_api.feeds_allowed())) or "off", ("on (bounce events: %s)" % ("on" if uaply_api.events_secret() else "off")) if uaply_api.mail_ready() else "off (test inbox only)",
               ("on" if OWNER_PASSWORD else "off (no OWNER_PASSWORD)") if PUBLIC else "on", "on" if chat_api.ai_ready() else "off",
               google_auth.summary(), billing_api.summary(), cfg_note, COMMIT or "unknown"))


_busy, _busy_lock = [0], threading.Lock()
srv = Server((BIND, port), H)


def _stop(signum, frame):
    """A host stops the server with SIGTERM at every deploy (Render then waits 30 seconds before forcing it). Stop taking new requests, let the
    ones in progress finish (a swipe that is sending an email, a sign-up), then exit normally."""
    _stopping.set()                                                # /healthz says 503 from now on
    sys.stderr.write("[uaply] stopping (signal %d): finishing %d request(s) in progress\n" % (signum, _busy[0]))
    sys.stderr.flush()
    threading.Thread(target=srv.shutdown, daemon=True).start()     # shutdown() waits for serve_forever, so it cannot run on this thread


for _sig in ("SIGTERM", "SIGBREAK"):          # SIGBREAK: Ctrl+Break on Windows, the same stop on the owner's own computer
    if hasattr(signal, _sig):
        signal.signal(getattr(signal, _sig), _stop)

sys.stderr.write(startup_summary() + "\n")
if PUBLIC and api and PERSISTENT is False:
    sys.stderr.write("[uaply] WARNING: %s is not on a persistent disk. Accounts, applications and feedback will disappear at the next deploy. "
                     "In Render: the service, Disks, add a disk with mount path %s.\n" % (DATA_DIR, DATA_DIR))
sys.stderr.flush()
if api:
    # the port is open before the boards are read: the health check passes at once, and a saved list on the disk is served at once while
    # every board refreshes behind it (jobs_api._load_source). On an empty disk the first visitor waits for this same read, never a second one.
    threading.Thread(target=jobs_api.get_jobs, daemon=True).start()
threading.Thread(target=_midnight_loop, daemon=True).start()
DRAIN_SECONDS = 15                            # the longest a stop waits for requests in progress: with the rest, about 16 s of Render's 30
srv.serve_forever()
srv.socket.close()                            # stop accepting at once: a new connection is refused now instead of waiting for the drain
time.sleep(0.2)                               # a connection accepted just before the stop gets to read its request line
_until = time.time() + DRAIN_SECONDS
while _busy[0] > 0 and time.time() < _until:
    time.sleep(0.05)
srv.server_close()
sys.stderr.write(daily_summary("stop") + "\n")
sys.stderr.write("[uaply] stopped%s\n" % ("" if _busy[0] <= 0 else " (%d request(s) did not finish in time)" % _busy[0]))
sys.stderr.flush()
