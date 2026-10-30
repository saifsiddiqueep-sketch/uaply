"""The application intent ledger (card 46): an application that leaves UAply is on disk as "sending" before any employer, hiring system,
Recruitee or mail server is called, and again with how it ended. A server that stops mid-send leaves it "unknown" after a restart: never
sent again by itself, refused as a duplicate, counted toward the daily limit, listed by the dry run. Nothing leaves this computer (the
delivery calls are stand-ins).
  python tools/test-intent-ledger.py"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="uaply-ledger-")
os.environ["UAPLY_DATA_DIR"] = TMP
os.environ["UAPLY_CONFIG_JSON"] = "{}"
os.environ["UAPLY_ALLOW_LOCAL_WEBHOOK"] = "1"         # the stand-in webhooks below are on this computer (never called: delivery is a stand-in)

import ats_api  # noqa: E402
import auth_api  # noqa: E402
import consent_api  # noqa: E402
import jobs_api  # noqa: E402
import uaply_api  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


class Died(BaseException):
    """The server stopping mid-send (a deploy, a crash, the machine losing power): no except clause in submit() sees it."""


with open(os.path.join(TMP, "uaply-partners.json"), "w", encoding="utf-8") as f:
    json.dump({"employers": [
        {"name": "Hook Only Co", "consent": "signed partner agreement 2026-10-12", "webhook": "http://127.0.0.1:1/apply", "webhook_secret": "s1",
         "url": "https://hook.example/careers", "jobs": [{"role": "Software Intern", "skills": ["Python"], "blurb": "Build things."}]},
        {"name": "Second Hook Co", "consent": "signed partner agreement 2026-10-12", "webhook": "http://127.0.0.1:1/apply2", "webhook_secret": "s2",
         "url": "https://second.example/careers", "jobs": [{"role": "Data Intern", "skills": ["SQL"], "blurb": "Count things."}]}]}, f)

cfg = {"delivery": "live", "daily_limit": 50, "smtp": {}, "owner_copy": ""}
uaply_api.config = lambda: cfg
INST = "ledger"
uaply_api.init(INST)
auth_api.init(INST)
for i in (1, 2):
    auth_api.signup_with_code("ledger.%d@example.com" % i, "ledger pass %d" % i, "198.51.100.%d" % (20 + i), True, verified=True)
    auth_api.record_consent(i, consent_api.VERSION, "127.0.0.1", consent_api.digest(consent_api.full_text(False)), False)
LEDGER = os.path.join(TMP, INST, "applications.jsonl")
jobs = {j["co"]: j for j in jobs_api.partner_jobs()}
t("two partner jobs with a webhook (direct)", sorted((c, j["apply"]) for c, j in jobs.items()), [("Hook Only Co", "direct"), ("Second Hook Co", "direct")])

# a Recruitee posting (a careers site's own public apply endpoint), as the job feed would hold it
RJOB = {"id": 700001, "co": "Acme Recruitee", "role": "Analyst", "url": "https://acme.recruitee.com/o/analyst", "source": "Recruitee", "loc": "Remote"}
real_info = jobs_api.job_info
jobs_api.job_info = lambda i: dict(RJOB, ats={"kind": "recruitee", "board": "acme", "id": "analyst"}) if i == RJOB["id"] else real_info(i)


def rows(path=LEDGER):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except OSError:
        return []


def apply(job, user_id=1):
    email = "ledger.%d@example.com" % user_id
    payload = {"consent": True, "confirm_real": True, "match": 80,
               "job": {"id": job["id"], "co": job["co"], "role": job["role"], "url": job.get("url") or "https://example.com/x", "source": job.get("source", ""),
                       "loc": job.get("loc", ""), "contact": ""},
               "profile": {"name": "Sam Rivera", "email": email, "title": "Intern", "years": 1, "skills": ["Python"], "loc": "Philadelphia, PA",
                           "edu": "Bachelor", "ext": {"phone": "+1 215 555 0100"}}}
    return uaply_api.submit(payload, {"id": user_id, "email": email, "emailVerified": True})


real_deliver = uaply_api._deliver
real_recruitee = ats_api.recruitee_submit
CALLS = []

# 1. the crash window: the intent is on disk before the employer's system is called, then the server stops before it hears back
seen_on_disk = {}


def dies(*a, **k):
    rec = a[9]
    CALLS.append(rec["id"])
    seen_on_disk.update({r["id"]: r["status"] for r in rows()})
    raise Died()


uaply_api._deliver = dies
try:
    apply(jobs["Hook Only Co"])
    died = False
except Died:
    died = True
t("crash window: the delivery call was reached and the server stopped there", (died, len(CALLS)), (True, 1))
crashed_id = CALLS[0] if CALLS else ""
t("...the intent was on disk as \"sending\" before the employer's system was called", seen_on_disk.get(crashed_id), "sending")
t("...and no final record was written after it", [r["status"] for r in rows() if r.get("id") == crashed_id], ["sending"])

uaply_api._deliver = real_deliver
uaply_api.init(INST)                                   # the restart: everything is read again from disk
got = [a for a in uaply_api.APPS if a.get("id") == crashed_id]
t("after a restart the attempt is \"unknown\" (it may or may not have reached the employer)", [a["status"] for a in got], ["unknown"])


def counts(*a, **k):
    CALLS.append(a[9]["id"])
    return "sent", None, ["webhook"]


uaply_api._deliver = counts
CALLS.clear()
code, out = apply(jobs["Hook Only Co"])
t("...a second swipe on the same job is refused as a duplicate and nothing is sent again",
  (code, out.get("status"), out.get("was"), out.get("id"), len(CALLS)), (200, "duplicate", "unknown", crashed_id, 0))
t("...and says plainly it may or may not have reached the employer", out.get("note"), uaply_api.UNKNOWN_NOTE)
cfg["daily_limit"] = 1
code, out = apply(jobs["Second Hook Co"])
t("...it counts toward the daily sending limit like a sent one", (code, out.get("error"), len(CALLS)), (429, "Daily sending limit reached.", 0))
cfg["daily_limit"] = 50
uaply_api.APPS.append({"id": "mail-x", "at": int(time.time()), "mode": "live", "status": "unknown", "route": "email", "employerDomain": "acme.example",
                       "job": {"id": 1}, "candidate": {"email": "x@example.com"}})
t("...and toward an employer domain's share for apply by email", uaply_api._email_route_full(dict(cfg, email_domain_daily=1), "jobs@acme.example"), "domain_cap")
uaply_api.APPS.pop()

# 2. the dry run lists the unknown attempt and changes nothing
before = open(LEDGER, "rb").read()
n_apps = len(uaply_api.APPS)
listed = uaply_api.uncertain(INST)
t("dry run: lists the unknown attempt for this instance", [(r["id"], r["co"], r["mode"]) for r in listed], [(crashed_id, "Hook Only Co", "live")])
cli = subprocess.run([sys.executable, os.path.join(HERE, "recover-applications.py"), INST], capture_output=True, text=True, env=dict(os.environ, UAPLY_DATA_DIR=TMP))
t("dry run from the command line: names the instance, the count and the attempt",
  (cli.returncode, "%s: 1 unknown" % INST in cli.stdout, crashed_id in cli.stdout, "nothing changed" in cli.stdout), (0, True, True, True))
t("...and nothing changed on disk or in memory", (open(LEDGER, "rb").read() == before, len(uaply_api.APPS)), (True, n_apps))

# 3. a delivery that raises ends "failed" (in memory and on disk), not "sending" or "unknown", and a retry really sends
def raises(*a, **k):
    CALLS.append(a[9]["id"])
    raise RuntimeError("an employer system nobody expected")


uaply_api._deliver = raises
CALLS.clear()
code, out = apply(jobs["Second Hook Co"])
fid = CALLS[0] if CALLS else ""
t("failure: the send is reported as failed", (code, out.get("status")), (200, "failed"))
t("...on disk: the intent, then the failed record under the same id", [r["status"] for r in rows() if r.get("id") == fid], ["sending", "failed"])
uaply_api.init(INST)
t("...after a restart it is still failed, never unknown", [a["status"] for a in uaply_api.APPS if a.get("id") == fid], ["failed"])
uaply_api._deliver = counts
CALLS.clear()
code, out = apply(jobs["Second Hook Co"])
t("...and trying again sends it (a failure does not block a retry)", (out.get("status"), len(CALLS)), ("sent", 1))

# 4. a double tap: two swipes at once send once, and the file holds one intent and one result for that id
def slow(*a, **k):
    CALLS.append(a[9]["id"])
    time.sleep(0.4)
    return "sent", None, ["webhook"]


uaply_api._deliver = slow
CALLS.clear()
outs = []
th = [threading.Thread(target=lambda: outs.append(apply(jobs["Hook Only Co"], user_id=2))) for _ in range(2)]
for x in th:
    x.start()
for x in th:
    x.join()
t("double tap: the employer's system is called once", len(CALLS), 1)
t("...one swipe is sent, the other is a duplicate of the one in flight",
  sorted((o[1].get("status"), o[1].get("was", "")) for o in outs), [("duplicate", "sending"), ("sent", "")])
did = CALLS[0] if CALLS else ""
t("...on disk: one intent and one result for that id", [r["status"] for r in rows() if r.get("id") == did], ["sending", "sent"])
uaply_api.init(INST)
t("...after a restart: one record, sent", [a["status"] for a in uaply_api.APPS if a.get("id") == did], ["sent"])
uaply_api._deliver = real_deliver

# 5. Recruitee: the same intent before its public apply endpoint is called
CALLS.clear()


def r_dies(company, slug, *a, **k):
    CALLS.append((company, slug))
    seen_on_disk.clear()
    seen_on_disk.update({r["id"]: r["status"] for r in rows() if (r.get("job") or {}).get("id") == RJOB["id"]})
    raise Died()


ats_api.recruitee_submit = r_dies
try:
    apply(RJOB)
    died = False
except Died:
    died = True
t("Recruitee: the endpoint was reached and the server stopped there", (died, CALLS), (True, [("acme", "analyst")]))
t("...the intent was on disk as \"sending\" first", list(seen_on_disk.values()), ["sending"])
uaply_api.init(INST)
ats_api.recruitee_submit = lambda *a, **k: (CALLS.append(a[:2]), ("sent", None))[1]
code, out = apply(RJOB)
t("...after a restart it is unknown and a second swipe sends nothing", (out.get("status"), out.get("was"), len(CALLS)), ("duplicate", "unknown", 1))
ats_api.recruitee_submit = real_recruitee

# 6. older files: rows without an id, single rows, a broken last line all still load; the last line per id wins, in first-seen order
OLD = "ledger-old"
os.makedirs(os.path.join(TMP, OLD), exist_ok=True)
base = {"mode": "live", "job": {"id": 5, "co": "Old Co", "role": "Old"}, "candidate": {"email": "old@example.com"}, "to": "", "at": 1700000000}
with open(os.path.join(TMP, OLD, "applications.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps(dict(base, status="sent")) + "\n")                                  # an old row with no id
    f.write(json.dumps(dict(base, id="old1", status="handoff")) + "\n")                    # an old row with an id, written once
    f.write(json.dumps(dict(base, id="new1", status="sending")) + "\n")
    f.write(json.dumps(dict(base, id="new2", status="sending")) + "\n")
    f.write(json.dumps(dict(base, id="new1", status="sent", channels=["webhook"])) + "\n")
    f.write('{"id": "cut-short", "job": {"co": "Bro')
uaply_api.init(OLD)
t("older files: every row loads, one record per id, in the order they were made",
  [(a.get("id"), a["status"]) for a in uaply_api.APPS], [(None, "sent"), ("old1", "handoff"), ("new1", "sent"), ("new2", "unknown")])
t("...the dry run lists only the cut-off one", [r["id"] for r in uaply_api.uncertain(OLD)], ["new2"])

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
