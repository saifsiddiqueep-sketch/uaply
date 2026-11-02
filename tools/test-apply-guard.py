"""Apply guard (card 191, November 2, 2026): three guards on the apply path, checked in this process with every network call mocked (nothing
leaves this computer: any attempt to open a connection is recorded and refused):
  1. sign-up test mode (uaply_api.NO_MAIL) never posts to an employer's webhook or hiring system, even with delivery "live"; the swipe is
     recorded as a simulated test delivery instead (a stand-in on this computer is still posted to, as for Recruitee)
  2. a submit that times out is "unknown", never "failed", and dup() holds it like a sent one for a day, so a retry cannot apply twice
  3. a Recruitee plan (POST /api/apply/plan) without a resume says "needs_input", never "ready"
  python tools/test-apply-guard.py"""
import json
import os
import shutil
import socket
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="uaply-applyguard-")
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}", UAPLY_DATA_DIR=TMP, UAPLY_DNS_CHECK="off", UAPLY_REQUEST_LOG="off")
for k in list(os.environ):
    if k.startswith("UAPLY_ATS_BASE_") or k in ("UAPLY_SIGNUP_TEST", "UAPLY_ALLOW_LOCAL_WEBHOOK"):
        os.environ.pop(k)
R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


# ---- the network: every way out is replaced. NET records each attempt; MODE says what the fake employer does ----
NET = []
MODE = {"ats": "refuse"}          # "refuse" (any connection is an error), "ok" (the hiring system accepts), "timeout"


class _Reply:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self, n=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_ats_open(req, timeout=None):
    NET.append(("ats", req.get_method(), req.full_url))
    if MODE["ats"] == "ok":
        return _Reply(200, json.dumps({"ok": True, "id": "cand-1", "candidate": {"id": 1}}).encode())
    if MODE["ats"] == "timeout":
        raise socket.timeout("timed out")
    raise OSError("network refused by the test")


def _fake_open(self, req, data=None, timeout=None):
    NET.append(("opener", req.get_method() if hasattr(req, "get_method") else "GET", getattr(req, "full_url", str(req))))
    raise OSError("network refused by the test")


def _fake_connect(self, *a, **k):
    NET.append(("socket", "CONNECT", repr(a)[:80]))
    raise OSError("network refused by the test")


def _fake_create_connection(*a, **k):
    NET.append(("socket", "CONNECT", repr(a)[:80]))
    raise OSError("network refused by the test")


urllib.request.OpenerDirector.open = _fake_open
urllib.request.urlopen = lambda *a, **k: _fake_open(None, a[0] if a else k.get("url"))
socket.socket.connect = _fake_connect
socket.create_connection = _fake_create_connection

import ats_api  # noqa: E402
import auth_api  # noqa: E402
import autofill  # noqa: E402
import consent_api  # noqa: E402
import jobs_api  # noqa: E402
import uaply_api  # noqa: E402

ats_api._open = _fake_ats_open

# ---- the server's view of the jobs: each test sets JOB to what jobs_api would say about the posting ----
JOB = {}
CFG = {"delivery": "live", "smtp": {}, "daily_limit": 50, "owner_copy": "", "google": {}, "grace_seconds": 0, "feeds": []}
uaply_api.config = lambda: dict(CFG)
jobs_api.job_info = lambda jid: dict(JOB.get("info") or {})
jobs_api.job_policy = lambda jid: JOB.get("policy", "link")
jobs_api.known_contact = lambda jid: JOB.get("contact", "")
jobs_api.known_webhook = lambda jid: JOB.get("hook")
jobs_api.known_ats = lambda jid: dict(JOB["ats"]) if JOB.get("ats") else None
autofill.fetch_form = lambda *a, **k: (NET.append(("form", "GET", repr(a))), None)[1]
consent_api.current = lambda *a, **k: True
auth_api.consent_for = lambda *a, **k: {}
uaply_api._receipt = lambda *a, **k: {"status": "skipped"}
uaply_api._send_owner_copy = lambda *a, **k: False

USER = {"id": "u-guard", "email": "sam@example.com", "emailVerified": True, "first": "Sam", "last": "Lee"}
LEVER = {"kind": "lever", "board": "acme", "id": "abc-123", "key": "lever-key-456"}
HOOK = ("https://hooks.acme.example/uaply", "hook-secret")


def swipe(jid, plan_only=False, resume=None):
    p = {"consent": True, "confirm_real": True, "match": 80,
         "job": {"id": jid, "co": "Acme", "role": "Marketing Intern", "url": "https://acme.example/jobs/%d" % jid, "loc": "Philadelphia, PA"},
         "profile": {"name": "Sam Lee", "email": "sam@example.com", "ext": {"phone": "215-555-0100"}}}
    if plan_only:
        p["plan_only"] = True
    if resume is not None:
        p["resume"] = resume
    return uaply_api.submit(p, dict(USER), "https://sandbox.example")


def reset(**job):
    JOB.clear()
    JOB.update(job)
    del NET[:]


try:
    # ---------- 1. sign-up test mode: nothing reaches an employer's webhook or hiring system ----------
    uaply_api.NO_MAIL = True
    MODE["ats"] = "ok"            # if anything were posted, the fake hiring system would accept it: only the guard can stop it
    reset(policy="direct", ats=LEVER, hook=HOOK)
    s, out = swipe(500001)
    t("test mode, live delivery, webhook + Lever: answered 200", s, 200)
    t("...recorded as a simulated test delivery, not sent", (out.get("status"), out.get("simulated")), ("delivered_test", True))
    t("...nothing was posted anywhere (no hiring system, no webhook, no socket)", NET, [])
    reset(policy="direct", hook=HOOK)
    s, out = swipe(500002)
    t("test mode, webhook only: simulated, nothing posted", (s, out.get("status"), NET), (200, "delivered_test", []))
    reset(policy="direct", ats={"kind": "ashby", "board": "acmeashby", "id": "post-1", "key": "ashby-key-789"})
    s, out = swipe(500003)
    t("test mode, Ashby: the employer's form is not even read with their key, nothing posted", (s, out.get("status"), NET), (200, "delivered_test", []))
    reset(policy="link", info={"ats": {"kind": "recruitee", "board": "acme", "id": "marketing-intern"}})
    s, out = swipe(500004)
    t("test mode, Recruitee: simulated, nothing posted (the guard that was already there)", (s, out.get("status"), NET), (200, "delivered_test", []))
    # the second guard, in _deliver itself (in case another caller ever reaches it in test mode)
    reset()
    rec = {"id": "guard-direct", "at": int(time.time()), "candidate": {"name": "Sam Lee", "email": "sam@example.com", "ext": {}},
           "job": {"id": 500005, "role": "Intern", "co": "Acme", "loc": "", "url": "https://acme.example/jobs/1"}, "resume": None}
    st, err, ch = uaply_api._deliver(CFG, "", rec["candidate"], rec["job"], "", "", None, None, HOOK, rec, dict(LEVER))
    t("test mode, _deliver called straight: posts nothing", NET, [])
    t("...and claims nothing was sent", st != "sent" and ch == [], True)
    # a stand-in hiring system on this computer is still posted to (the browser tests in sign-up test mode use one)
    os.environ["UAPLY_ATS_BASE_LEVER"] = "http://127.0.0.1:9"
    reset(policy="direct", ats=LEVER)
    s, out = swipe(500006)
    t("test mode, Lever pointed at a stand-in on this computer: posted there, sent", (out.get("status"), [n[0] for n in NET]), ("sent", ["ats"]))
    t("...to 127.0.0.1 only", all(n[2].startswith("http://127.0.0.1:9/") for n in NET), True)
    os.environ.pop("UAPLY_ATS_BASE_LEVER")

    # control: outside test mode the same swipe does reach the (fake) hiring system, so the checks above prove the guard
    uaply_api.NO_MAIL = False
    reset(policy="direct", ats=LEVER)
    s, out = swipe(500007)
    t("control, not test mode: the Lever posting is sent into the hiring system", (out.get("status"), [n[:2] for n in NET]), ("sent", [("ats", "POST")]))

    # ---------- 2. a timeout is "unknown", and a retry is held ----------
    MODE["ats"] = "timeout"
    reset()
    st, why = ats_api.submit("lever", "acme", "abc-123", "lever-key-456", {"name": "Sam Lee", "email": "sam@example.com", "ext": {}}, "", None, None)
    t("ats_api.submit: a Lever submit that times out is 'unknown', not 'failed'", (st, why), ("unknown", ats_api.UNCONFIRMED))
    st, why = ats_api.recruitee_submit("acme", "marketing-intern", {"name": "Sam Lee", "email": "sam@example.com", "ext": {}}, None, None)
    t("ats_api.recruitee_submit: a timeout is 'unknown'", st, "unknown")
    MODE["ats"] = "refuse"
    st, _ = ats_api.submit("lever", "acme", "abc-123", "lever-key-456", {"name": "Sam Lee", "email": "sam@example.com", "ext": {}}, "", None, None)
    t("...any network failure on the submit is 'unknown' too (it may have arrived)", st, "unknown")

    MODE["ats"] = "timeout"
    reset(policy="direct", ats=LEVER)
    s, out = swipe(500010)
    t("swipe whose submit times out: recorded 'unknown'", (s, out.get("status")), (200, "unknown"))
    t("...the person is told it could not be confirmed and to check their email", (out.get("code"), "could not" in out.get("error", "").lower() or
      "did not confirm" in out.get("error", ""), "Check your email" in out.get("error", "")), ("unconfirmed", True, True))
    rec = next(a for a in uaply_api.APPS if a["job"]["id"] == 500010)
    t("...the stored record says 'unknown'", rec["status"], "unknown")
    posts = len(NET)
    MODE["ats"] = "ok"
    s, out = swipe(500010)
    t("retry of the same swipe: a duplicate of the 'unknown' one, not sent again", (out.get("status"), out.get("was")), ("duplicate", "unknown"))
    t("...nothing more was posted to the hiring system", len(NET), posts)
    rec["at"] -= uaply_api.UNKNOWN_HOLD - 3600
    s, out = swipe(500010)
    t("still held 23 hours later", out.get("status"), "duplicate")
    rec["at"] -= 7200
    s, out = swipe(500010)
    t("after a day (the person was told to check their email) the swipe may be sent again", out.get("status"), "sent")
    reset(policy="direct", ats=LEVER)
    MODE["ats"] = "ok"
    uaply_api.APPS.append(dict(rec, id="failed-one", status="failed", at=int(time.time()), job=dict(rec["job"], id=500011)))
    s, out = swipe(500011)
    t("a plain 'failed' one is still retried at once (unchanged)", out.get("status"), "sent")

    # ---------- 3. a Recruitee plan without a resume is never "ready" ----------
    MODE["ats"] = "refuse"
    reset(policy="link", info={"ats": {"kind": "recruitee", "board": "acme", "id": "marketing-intern"}})
    s, out = swipe(500020, plan_only=True)
    t("Recruitee plan, no resume: needs_input with the reason", (s, out.get("status"), out.get("reasons")), (200, "needs_input", ["resume"]))
    s, out = swipe(500020, plan_only=True, resume={"name": "cv.pdf", "present": True})
    t("Recruitee plan, resume on the device: ready", (s, out.get("status")), (200, "ready"))
    t("...a plan posts nothing", NET, [])
    reset(policy="direct", ats=LEVER)
    s, out = swipe(500021, plan_only=True)
    t("a connected Lever posting's plan is unchanged (ready)", out.get("status"), "ready")
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print("%d/%d passed" % (sum(R), len(R)))
if all(R):
    print("ALL APPLY GUARD TESTS PASSED")
sys.exit(0 if all(R) else 1)
