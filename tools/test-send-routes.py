"""c208 send routes (October 30, 2026): every listed job may carry "send_route" (sends_now / could_send / hand_off), how a right swipe
would be delivered, behind jobs_api.NEW_ROUTES (off by default). READY_ONLY_DECK exists but filters nothing. With both flags off the
list is byte-identical to the code before c208 (loaded from git), and turning READY_ONLY_DECK on changes nothing. Nothing leaves this computer:
  python tools/test-send-routes.py"""
import importlib.util
import copy
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="uaply-send-routes-")
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}", UAPLY_DATA_DIR=os.path.join(TMP, "data"), UAPLY_DNS_CHECK="off")
os.environ.pop("UAPLY_ATS_BASE_RECRUITEE", None)
R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


import jobs_api  # noqa: E402


def _base_module():
    """jobs_api.py as it was before c208 (the merge base with origin/sandbox), as its own module, or None when git cannot give it."""
    try:
        base = subprocess.run(["git", "-C", ROOT, "merge-base", "HEAD", "origin/sandbox"], capture_output=True, text=True, check=True).stdout.strip()
        src = subprocess.run(["git", "-C", ROOT, "show", base + ":jobs_api.py"], capture_output=True, check=True).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        return None
    spec = importlib.util.spec_from_loader("jobs_api_before_c208", loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = os.path.join(ROOT, "jobs_api.py")
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


NOW = time.time() * 1000
POSTED = NOW - 10 * 86400000


def job(i, **kw):
    j = dict(id="t%d" % i, title="Analyst %d" % i, company="Co %d" % i, location="Philadelphia, PA", url="https://example.com/j/%d" % i,
             posted=POSTED, desc="d" * 40, credit="via Test", apply="link", contact="", live=True)
    j.update(kw)
    return j


# (job, feed label) pairs: feed False is a partner employer's own job (its instant set by partner_jobs)
CASES = [
    ("recruitee", job(1, ats={"kind": "recruitee", "board": "curotec", "id": "data-analyst"}), "Ready"),
    ("recruitee bad slug", job(2, ats={"kind": "recruitee", "board": "curotec", "id": "bad slug!"}), "Ready"),
    ("email posting", job(3, apply="email", contact="jobs@co3.example", instant=True), "Ready"),
    ("email posting bounced", job(4, apply="email", contact="gone@co4.example", instant=True), "Ready"),
    ("greenhouse", job(5, ats={"kind": "greenhouse", "board": "acme", "id": "123"}), "Ready"),
    ("greenhouse connected", job(6, ats={"kind": "greenhouse", "board": "linked", "id": "9"}), "Ready"),
    ("lever", job(7, ats={"kind": "lever", "board": "acme", "id": "abc"}), "Ready, one tap"),
    ("ashby", job(8, ats={"kind": "ashby", "board": "acme", "id": "x1"}), "Ready"),
    ("workable", job(9, ats={"kind": "workable", "board": "acme", "id": "W1"}), "Ready"),
    ("smartrecruiters", job(10, ats={"kind": "smartrecruiters", "board": "Acme", "id": "77"}), "Ready"),
    ("usajobs", job(11, source="USAJOBS", announcement="https://www.usajobs.gov/job/1"), "Apply on their site"),
    ("careerpage", job(12, source="Co 12's careers page"), "Apply on their site"),
    ("other feed", job(13, source="Remotive"), True),
    ("partner instant", job(14, apply="direct", instant=True, contact="hr@co14.example"), False),
    ("partner link", job(15, apply="link", instant=False), False),
]
CONNS = {("greenhouse", "linked"): "secret-key"}
BLOCKED = frozenset({"gone@co4.example"})
WANT = {"recruitee": "sends_now", "recruitee bad slug": "hand_off", "email posting": "sends_now",
        "email posting bounced": "hand_off", "greenhouse": "could_send", "greenhouse connected": "sends_now", "lever": "could_send",
        "ashby": "could_send", "workable": "could_send", "smartrecruiters": "could_send", "usajobs": "hand_off", "careerpage": "hand_off",
        "other feed": "hand_off", "partner instant": "sends_now", "partner link": "hand_off"}


def run(mod, recruitee=True, full=False):
    mod.RECRUITEE_SUBMIT[0] = recruitee
    return [mod._out_job(j, NOW, CONNS, feed, BLOCKED, full=full) for _, j, feed in CASES]


def dump(rows):
    return json.dumps(rows, ensure_ascii=False).encode("utf-8")


BEFORE = copy.deepcopy([j for _, j, _ in CASES])
t("the flags exist and are off by default", (jobs_api.NEW_ROUTES[0], jobs_api.READY_ONLY_DECK[0]), (False, False))

# flags off: no label anywhere, and the bytes match the code before c208
for rec in (True, False):
    for full in (False, True):
        off = run(jobs_api, rec, full)
        t("flags off (recruitee %s, full %s): no send_route on any job" % (rec, full), [r for r in off if "send_route" in r], [])
        base = _base_module()
        if base is None:
            print("SKIP the before-c208 comparison: git could not show the base jobs_api.py")
        else:
            if hasattr(base, "NEW_ROUTES"):
                base.NEW_ROUTES[0] = False
            t("flags off (recruitee %s, full %s): byte-identical to before c208" % (rec, full), dump(off), dump(run(base, rec, full)))
        jobs_api.READY_ONLY_DECK[0] = True
        t("READY_ONLY_DECK on (recruitee %s, full %s): filters and changes nothing" % (rec, full), dump(run(jobs_api, rec, full)), dump(off))
        jobs_api.READY_ONLY_DECK[0] = False
        jobs_api.NEW_ROUTES[0] = True
        on = run(jobs_api, rec, full)
        jobs_api.NEW_ROUTES[0] = False
        t("NEW_ROUTES on (recruitee %s, full %s): every job has send_route" % (rec, full), all("send_route" in r for r in on), True)
        t("NEW_ROUTES on (recruitee %s, full %s): same jobs, same order" % (rec, full), [r["id"] for r in on], [r["id"] for r in off])
        t("NEW_ROUTES on (recruitee %s, full %s): only send_route added" % (rec, full),
          dump([{k: v for k, v in r.items() if k != "send_route"} for r in on]), dump(off))
        want = dict(WANT, recruitee="sends_now" if rec else "hand_off")
        t("NEW_ROUTES on (recruitee %s, full %s): the labels" % (rec, full), {n: r["send_route"] for (n, _, _), r in zip(CASES, on)}, want)

t("the cached jobs are never changed", [j for _, j, _ in CASES], BEFORE)
t("send_route on a bare dict", jobs_api.send_route({}), "hand_off")
t("send_route trusts instant over the system", jobs_api.send_route({"instant": True, "ats": {"kind": "lever"}}), "sends_now")

print("%d of %d passed" % (sum(R), len(R)))
print("ALL SEND-ROUTE TESTS PASSED" if all(R) else "SEND-ROUTE TESTS FAILED")
sys.exit(0 if all(R) else 1)
