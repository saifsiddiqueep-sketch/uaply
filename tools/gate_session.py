"""A signed-in, confirmed test person for a local UAply server behind the sign-in gate (docs/ACCOUNTS.md, "The sign-in contract"): data
routes answer 401 {"code": "signin"} without a session and 403 {"code": "verify"} to an account whose email is not confirmed yet.

    import gate_session
    op = gate_session.session("http://127.0.0.1:8770")          # an opener that carries the session cookie
    jobs = gate_session.get_json(op, base + "/api/jobs")
    gate_session.install(base)                                   # or: every urllib.request.urlopen in this process carries one
    cookie = gate_session.cookie(base)                           # or: "name=value" for an http.client or hand-made request

A server in test mode (UAPLY_SIGNUP_TEST=1, never on a public server) confirms the new account at once. Without test mode the code is read
from the server's own test inbox (/outbox, open on a local server with no OWNER_PASSWORD) and typed into /api/auth/verify, as a person
would. Each call signs up a new person (gate.<random>@example.com) unless an email is given. Nothing here works against a public server.
"""
import http.cookiejar
import json
import re
import secrets
import time
import urllib.error
import urllib.request


def _opener(base):
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("Origin", base.rstrip("/")), ("User-Agent", "UAply test (tools/gate_session.py)")]   # the same-site check needs the Origin
    op.jar = jar
    return op


def _post(op, url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with op.open(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def session(base, email=None, password=None, first="Test", last="Person", tries=40):
    """An opener signed in as a new, confirmed account on the server at `base` (waits up to tries x 0.25 s for it to answer)."""
    base = base.rstrip("/")
    op = _opener(base)
    email = email or "gate.%s@example.com" % secrets.token_hex(5)
    password = password or "Gate-%s-pw" % secrets.token_hex(6)
    for i in range(tries):
        try:
            status, out = _post(op, base + "/api/auth/signup", {"email": email, "password": password, "first": first, "last": last, "agree": True})
            break
        except (urllib.error.URLError, ConnectionError, OSError):
            if i == tries - 1:
                raise
            time.sleep(0.25)
    if status == 409:                                   # that address already has an account: sign in instead
        status, out = _post(op, base + "/api/auth/login", {"email": email, "password": password})
    if status != 200:
        raise RuntimeError("sign-up on %s failed: HTTP %s %s" % (base, status, out))
    if not (out.get("user") or {}).get("emailVerified"):
        # no test mode: the 6-digit code from the server's test inbox, the newest one for this address
        code = ""
        for _ in range(20):
            with op.open(base + "/outbox", timeout=30) as r:
                page = r.read().decode("utf-8", "replace")
            # the inbox lists the newest first: "<b>123456 is your UAply verification code</b> to someone@example.com"
            found = re.findall(r"([0-9]{6}) is your UAply (?:verification|sign-in) code</b> to ([^<\s]+)", page)
            code = next((c for c, to in found if to.strip().lower() == email.lower()), "")
            if code:
                break
            time.sleep(0.25)
        status, out = _post(op, base + "/api/auth/verify", {"code": code})
        if status != 200:
            raise RuntimeError("confirming the test account on %s failed: HTTP %s %s" % (base, status, out))
    op.email = email
    return op


def get_json(op, url, timeout=60):
    with op.open(url, timeout=timeout) as r:
        return json.loads(r.read())


def install(base, **kw):
    """Every urllib.request.urlopen in this process carries a new test person's session (returns the opener)."""
    op = session(base, **kw)
    urllib.request.install_opener(op)
    return op


def cookie(base, **kw):
    """The session cookie of a new test person as a Cookie header value ("name=value")."""
    op = session(base, **kw)
    return "; ".join("%s=%s" % (c.name, c.value) for c in op.jar)
