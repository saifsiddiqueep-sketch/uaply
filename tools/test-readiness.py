"""Profile readiness and the swipe lock on the server (readiness.py, Trello card 9). Starts its own throwaway servers (sandbox on PORT, dev on
PORT+1) with an empty data folder, and stops them at the end, so it needs nothing running:
  python tools/test-readiness.py [port]          (default 18790; uses that port and the next one)
Checks: the readiness rules (required: name, email, phone, city, resume file or link; optional fields never block), POST /api/apply refused
with code profile_incomplete on the sandbox when the profile is not ready, even sent straight to the server with no swipe, and allowed once
it is; GET /api/profile/readiness and POST /api/profile/state for signed-in and signed-out visitors; the dev release build unchanged; and an
account made before the profile_state column existed still signs in and applies."""
import base64
import http.client
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import readiness  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18790
DATA = tempfile.mkdtemp(prefix="uaply-ready-")
R = []
PROCS = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


# ---------- the rules on their own ----------
FULL = {"name": "Ada Lovelace", "email": "ada@example.com", "loc": "Philadelphia", "ext": {"phone": "+1 215 555 0100"}}
t("empty profile is not_started", readiness.check({})["state"], "not_started")
t("nothing at all (not a dict) is not_started", readiness.check(None)["state"], "not_started")
t("name only is in_progress", readiness.check({"name": "Ada"})["state"], "in_progress")
t("everything but a resume is in_progress", readiness.check(FULL)["state"], "in_progress")
t("missing list names the resume only", [m["key"] for m in readiness.check(FULL)["missing"]], ["resume"])
t("a resume file makes it ready", readiness.check(FULL, True)["state"], "ready")
t("a resume link (https) makes it ready", readiness.check(dict(FULL, ext={"phone": "2155550100", "resume": "https://ada.example/cv.pdf"}))["state"], "ready")
t("an http resume link does not count", readiness.check(dict(FULL, ext={"phone": "2155550100", "resume": "http://ada.example/cv.pdf"}))["state"], "in_progress")
t("a bad phone does not count", [m["key"] for m in readiness.check(dict(FULL, ext={"phone": "call me"}), True)["missing"]], ["phone"])
t("a bad email does not count", [m["key"] for m in readiness.check(dict(FULL, email="ada@"), True)["missing"]], ["email"])
t("percent is 80 with four of five", readiness.check(FULL)["percent"], 80)
t("earliest step: about before where", readiness.check({"loc": "x"})["step"], "about")
t("earliest step when only the city is missing", readiness.check(dict(FULL, loc=""), True)["step"], "where")
t("earliest step when only the resume is missing", readiness.check(FULL)["step"], "back")
t("optional fields empty never block (no title, skills, pay, GPA, EEO, authorization)",
  readiness.check(dict(FULL, title="", skills=[], years=0, edu="", ext={"phone": "2155550100", "gpa": "", "auth": "", "salary": "", "types": []}), True)["state"], "ready")
t("enforced on the sandbox by default", readiness.enforced({}, "sandbox"), True)
t("not enforced on dev by default", readiness.enforced({}, "dev"), False)
t("require_ready:true turns it on elsewhere", readiness.enforced({"require_ready": True}, "dev"), True)
t("require_ready:false turns it off in the sandbox", readiness.enforced({"require_ready": False}, "sandbox"), False)


# ---------- an account made before the profile_state column existed ----------
old = os.path.join(DATA, "sandbox")
# a real accounts database with one account in it, then the new column taken away again: what a server made before this change left behind
subprocess.run([sys.executable, "-c", "import sys, sqlite3, os; sys.path.insert(0, %r); import auth_api; auth_api.init('sandbox'); "
                "print(auth_api.signup('grace@example.com', 'an old password 1', '127.0.0.1', True)[0]); "
                "c = sqlite3.connect(os.path.join(%r, 'uaply.db')); c.execute('ALTER TABLE users DROP COLUMN profile_state'); c.commit()" % (ROOT, old)],
               env=dict(os.environ, UAPLY_DATA_DIR=DATA), check=True, stdout=subprocess.DEVNULL)
with sqlite3.connect(os.path.join(old, "uaply.db")) as c:
    t("the old database really has no profile_state column", "profile_state" in [r[1] for r in c.execute("PRAGMA table_info(users)")], False)

def start(port, inst):
    env = dict(os.environ, UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=DATA, UAPLY_CONFIG_JSON=json.dumps({"feeds": [], "smtp": {}}))
    env.pop("ANTHROPIC_API_KEY", None)
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(port), inst, "--api"], cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PROCS.append(p)
    for _ in range(80):
        try:
            if req(port, "GET", "/healthz")[0] == 200:
                return p
        except OSError:
            time.sleep(0.25)
    raise SystemExit("the test server did not start (%s)" % inst)


def req(port, method, path, body=None, cookie=""):
    h = {"Host": "127.0.0.1:%d" % port, "Origin": "http://127.0.0.1:%d" % port}
    if cookie:
        h["Cookie"] = cookie
    if body is not None:
        h["Content-Type"] = "application/json"
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    raw = r.read()
    ck = [x.split(";")[0] for x in (r.msg.get_all("Set-Cookie") or [])]
    c.close()
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    return r.status, data, ck


PDF = {"name": "ada.pdf", "data": "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4\n% a tiny test resume file\n%%EOF").decode()}


def app(profile, resume=None, job_id=1):
    p = {"consent": True, "job": {"id": job_id, "co": "Northwind Freight", "role": "Frontend Engineer", "url": "https://example.com/x", "loc": "Remote"},
         "profile": profile}
    if resume:
        p["resume"] = resume
    return p


try:
    try:
        start(PORT, "sandbox")
        start(PORT + 1, "dev")
        SB, DEV = PORT, PORT + 1

        # the old database was upgraded in place (additive column), and its schema now has profile_state
        with sqlite3.connect(os.path.join(old, "uaply.db")) as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(users)")]
        t("an old accounts database gets the profile_state column", "profile_state" in cols, True)

        code, out, ck = req(SB, "POST", "/api/auth/login", {"email": "grace@example.com", "password": "an old password 1"})
        t("an account made before the change still signs in", code, 200)
        code, out, _ = req(SB, "GET", "/api/profile/readiness", cookie="; ".join(ck))
        t("  ... and reads as not_started with nothing saved", (out["signedIn"], out["state"], out["saved"]), (True, "not_started", False))
        code, out, _ = req(SB, "POST", "/api/apply", app(dict(FULL, email="grace@example.com"), PDF, job_id=4), cookie="; ".join(ck))
        t("  ... and applies with a ready profile", (code, out.get("code")), (200, None))

        # signed out
        code, out, _ = req(SB, "GET", "/api/profile/readiness")
        t("signed out: readiness answers", (code, out["signedIn"], out["state"], out["enforced"]), (200, False, "not_started", True))
        code, out, _ = req(SB, "POST", "/api/profile/state", {"profile": FULL, "hasResume": True})
        t("signed out: state is checked, not stored", (code, out["state"], out["saved"], out["signedIn"]), (200, "ready", True, False))
        t("signed out: still nothing kept afterwards", req(SB, "GET", "/api/profile/readiness")[1]["state"], "not_started")

        # direct POSTs, no swipe, no front end at all
        code, out, _ = req(SB, "POST", "/api/apply", app({"name": "Ada", "email": "ada@example.com"}))
        t("sandbox: name and email only is refused (direct POST)", (code, out.get("code")), (403, "profile_incomplete"))
        t("  ... and says what is missing", [m["key"] for m in out["readiness"]["missing"]], ["phone", "loc", "resume"])
        code, out, _ = req(SB, "POST", "/api/apply", app({}))
        t("sandbox: an empty profile is refused", (code, out.get("code")), (403, "profile_incomplete"))
        code, out, _ = req(SB, "POST", "/api/apply", app(FULL))
        t("sandbox: no resume is refused", (code, out.get("code")), (403, "profile_incomplete"))
        code, out, _ = req(SB, "POST", "/api/apply", app(FULL, {"name": "x.pdf", "data": "nonsense"}))
        t("sandbox: a resume that is not a real file is still refused (by the resume check)", code, 400)
        code, out, _ = req(SB, "POST", "/api/apply", app(FULL, PDF))
        t("sandbox: a ready profile with a resume file is allowed", (code, out.get("code"), bool(out.get("id")), out.get("status") != "failed"), (200, None, True, True))
        code, out, _ = req(SB, "POST", "/api/apply", app(dict(FULL, ext={"phone": "2155550100", "resume": "https://ada.example/cv.pdf"}), job_id=2))
        t("sandbox: a ready profile with a resume link is allowed", (code, out.get("code")), (200, None))

        # signed in
        code, out, ck = req(SB, "POST", "/api/auth/signup", {"email": "ada@example.com", "password": "correct horse 42", "agree": True})
        t("sign up works on the upgraded database", code, 200)
        cookie = "; ".join(ck)
        code, out, _ = req(SB, "GET", "/api/profile/readiness", cookie=cookie)
        t("a new account has nothing saved yet", (out["signedIn"], out["state"], out["saved"]), (True, "not_started", False))
        code, out, _ = req(SB, "POST", "/api/profile/state", {"profile": {"name": "Ada", "email": "ada@example.com", "street": "1 Secret St"}, "skipped": ["jobs", "nope"]}, cookie=cookie)
        t("progress is saved for the account", (code, out["state"], out["percent"], out["skipped"]), (200, "in_progress", 40, ["jobs"]))
        code, out, _ = req(SB, "GET", "/api/profile/readiness", cookie=cookie)
        t("  ... and read back", (out["state"], out["percent"], out["step"], out["skipped"]), ("in_progress", 40, "about", ["jobs"]))
        with sqlite3.connect(os.path.join(old, "uaply.db")) as c:
            stored = c.execute("SELECT profile_state FROM users WHERE email='ada@example.com'").fetchone()[0]
        t("only the readiness fields are stored (never a street address)", "Secret" in stored, False)
        code, out, _ = req(SB, "POST", "/api/apply", app({"name": "Ada", "email": "ada@example.com"}, job_id=3), cookie=cookie)
        t("signed in: not ready is refused", (code, out.get("code")), (403, "profile_incomplete"))
        code, out, _ = req(SB, "POST", "/api/profile/state", {"profile": FULL, "hasResume": True}, cookie=cookie)
        t("signed in: complete progress reads as ready", out["state"], "ready")
        code, out, _ = req(SB, "POST", "/api/apply", app(FULL, PDF, job_id=3), cookie=cookie)
        t("signed in: ready is allowed", (code, out.get("code")), (200, None))

        # the release build (dev) is unchanged: name and email are still all it asks for
        code, out, _ = req(DEV, "POST", "/api/apply", app({"name": "Ada", "email": "ada@example.com"}))
        t("dev: name and email only still applies (not enforced)", (code, out.get("code")), (200, None))
        code, out, _ = req(DEV, "POST", "/api/apply", app({"name": "", "email": "ada@example.com"}))
        t("dev: the old name check still applies", (code, "name" in (out.get("error") or "")), (400, True))
        t("dev: readiness says not enforced", req(DEV, "GET", "/api/profile/readiness")[1]["enforced"], False)
    except Exception as e:                       # report, then stop the servers below
        R.append(False)
        print("FAIL the test stopped: %r" % e)
finally:
    for p in PROCS:
        p.terminate()
    for p in PROCS:
        try:
            p.wait(10)
        except Exception:
            p.kill()

print("\n%d of %d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
