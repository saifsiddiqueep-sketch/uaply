"""Tests the check made when someone swipes right on a feed job (card 95, jobs_api.still_open): a posting the employer has closed is not
sent or handed off, the person is told so, and the job leaves everyone's list; a posting that cannot be checked (a bot check, a time-out)
goes on exactly as before; answers are kept for a while; partner and connected employers' jobs are not asked about. Nothing is read from
the internet: the hiring system is the stand-in (tools/mock-ats.py: Greenhouse posting 1004 does not exist, every other one does).
  python tools/test-still-open.py"""
import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="uaply-stillopen-")


def _free_port():
    s_ = socket.socket()
    s_.bind(("127.0.0.1", 0))
    p_ = s_.getsockname()[1]
    s_.close()
    return p_


PORT = int(sys.argv[1]) if len(sys.argv) > 1 else _free_port()
BASE = "http://127.0.0.1:%d" % PORT
os.environ.update(UAPLY_DATA_DIR=TMP, UAPLY_CONFIG_JSON="{}", UAPLY_ATS_BASE_GREENHOUSE=BASE,
                  UAPLY_ATS_JSON=json.dumps([{"kind": "lever", "board": "acme", "api_key": "lever-key-456"}]))
os.environ.pop("UAPLY_OPEN_CHECK", None)

import jobs_api  # noqa: E402
import uaply_api  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


class Slow(http.server.BaseHTTPRequestHandler):
    """A hiring system that takes far longer to answer than a swipe waits."""
    def do_GET(self):
        time.sleep(3)
        try:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")
        except OSError:                  # the swipe gave up long ago and closed the connection
            pass

    def log_message(self, *a):
        pass


slow = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Slow)
threading.Thread(target=slow.serve_forever, daemon=True).start()
mock = subprocess.Popen([sys.executable, os.path.join(HERE, "mock-ats.py"), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
cfg = {"delivery": "test", "smtp": {}, "daily_limit": 50}
uaply_api.config = lambda: cfg
uaply_api.init("stillopen")


def gh(pid, role):
    """A Greenhouse posting as the job feed keeps it (board 'acme' on the stand-in)."""
    return jobs_api._normalize(dict(id=pid, title=role, company="Acme", loc="Remote - USA", remote=True, text="Python required.",
                                    url="https://boards.greenhouse.io/acme/jobs/%s" % pid, salary_text="", posted=0), "greenhouse", "Acme", "acme")


def swipe(j, email):
    return uaply_api.submit({"consent": True, "confirm_real": True, "job": {"id": j["id"], "co": j["co"], "role": j["role"], "url": j["url"], "loc": j["loc"]},
                             "profile": {"ext": {"phone": "215-555-0100"}, "name": "Sam Rivera", "email": email}}, None)


def listed():
    return {x["id"] for x in jobs_api.get_jobs()["jobs"]}


def listed_json():
    return {x["id"] for x in json.loads(jobs_api.get_json())["jobs"]}


try:
    closed, open_, unknown, slowj = gh("1004", "Closed Role"), gh("1001", "Open Role"), gh("1002", "Unknown Role"), gh("1010", "Slow Role")
    lev = jobs_api._normalize(dict(id="p1", title="Connected Role", company="Acme", loc="Remote - USA", remote=True, text="Python required.",
                                   url="https://jobs.lever.co/acme/p1", salary_text="", posted=0), "lever", "Acme", "acme")
    GH, LV = ("greenhouse", "acme", "Acme"), ("lever", "acme", "Acme")
    jobs_api._cache[GH] = {"at": time.time(), "jobs": [closed, open_, unknown, slowj], "status": "4 jobs"}
    jobs_api._cache[LV] = {"at": time.time(), "jobs": [lev], "status": "1 jobs"}
    jobs_api.SOURCES = [GH, LV]
    jobs_api.feeds_allowed = lambda: {"greenhouse", "lever"}
    jobs_api._load_source = lambda src: (jobs_api._cache[src]["jobs"], "ok")
    t("posting addresses follow the stand-in setting (and Recruitee's {base}/{company} form); real ones otherwise",
      (jobs_api._posting_url("greenhouse", "acme", "1004"), jobs_api._posting_url("lever", "acme", "p1")),
      (BASE + "/v1/boards/acme/jobs/1004", "https://api.lever.co/v0/postings/acme/p1"))
    os.environ["UAPLY_ATS_BASE_RECRUITEE"] = "http://127.0.0.1:9"
    t("...Recruitee", jobs_api._posting_url("recruitee", "curotec", "data-analyst"), "http://127.0.0.1:9/curotec/api/offers/data-analyst")
    os.environ["UAPLY_ATS_BASE_RECRUITEE"] = "https://evil.example"
    t("...and anything but this computer in that setting is ignored", jobs_api._posting_url("recruitee", "curotec", "x"), "https://curotec.recruitee.com/api/offers/x")
    os.environ.pop("UAPLY_ATS_BASE_RECRUITEE")

    t("all four postings are listed to begin with", {closed["id"], open_["id"], unknown["id"], slowj["id"]} <= listed(), True)
    t("off unless serve.py turns it on (a hosted server): no check, the swipe goes on", (jobs_api.open_check_on, jobs_api.still_open(closed["id"])), (False, None))
    code, out = swipe(closed, "off@example.com")
    t("...so a closed posting swiped with the check off is a hand-off, as before", (code, out.get("status")), (200, "handoff"))

    jobs_api.open_check_on = True
    n_apps, v0 = len(uaply_api.APPS), jobs_api._version[0]
    started = time.time()
    code, out = swipe(closed, "closed@example.com")
    t("closed posting: refused with a plain sentence, code 'closed', nothing sent or recorded",
      (code, out.get("code"), out.get("error"), len(uaply_api.APPS)),
      (410, "closed", "This job has closed, so nothing was sent. We've taken it off your list.", n_apps))
    t("...answered in well under the swipe's wait", time.time() - started < jobs_api.OPEN_CHECK_WAIT, True)
    t("...the job is hidden for everyone (its source's dead_ids, the job list's version raised)",
      (closed["id"] in jobs_api._links[GH]["dead_ids"], jobs_api._version[0] > v0), (True, True))
    t("...the record has the shape check_links makes", sorted(jobs_api._links[GH]), sorted(["at", "ok", "dead", "unknown", "dead_ids", "checked_ids", "off"]))
    t("...it is gone from /api/jobs (the list and its encoded copy), the others stay",
      (closed["id"] in listed(), closed["id"] in listed_json(), open_["id"] in listed(), unknown["id"] in listed()), (False, False, True, True))
    t("...the source is not counted against (only the background check counts dead links)", (jobs_api._links[GH]["dead"], jobs_api._links[GH]["off"]), (0, False))

    code, out = swipe(open_, "open@example.com")
    t("open posting: the swipe goes on exactly as before (a hand-off for a feed job)", (code, out.get("status"), jobs_api.still_open(open_["id"])), (200, "handoff", True))

    # cannot tell: the hiring system cannot be reached (nothing listens on port 1)
    os.environ["UAPLY_ATS_BASE_GREENHOUSE"] = "http://127.0.0.1:1"
    code, out = swipe(unknown, "unknown@example.com")
    t("cannot tell (the system is unreachable): sent as before, still listed", (code, out.get("status"), unknown["id"] in listed()), (200, "handoff", True))
    t("...the answer kept is 'cannot tell'", jobs_api._open_seen[unknown["id"]][1], None)
    t("answers are reused: the closed one is still closed with the system unreachable (nothing asked again)", jobs_api.still_open(closed["id"]), False)
    code, out = swipe(closed, "closed2@example.com")
    t("...and a second swipe on it is refused the same way", (code, out.get("code")), (410, "closed"))

    # a system slower than the wait: the swipe does not wait for it
    os.environ["UAPLY_ATS_BASE_GREENHOUSE"] = "http://127.0.0.1:%d" % slow.server_address[1]
    jobs_api.OPEN_CHECK_WAIT = 0.5
    started = time.time()
    t("a slow system: the check gives up after the short wait ('cannot tell')", (jobs_api.still_open(slowj["id"]), time.time() - started < 1.5), (None, True))
    jobs_api.OPEN_CHECK_WAIT = 3
    os.environ["UAPLY_ATS_BASE_GREENHOUSE"] = BASE           # (the hand-off itself reads the posting's form: the stand-in answers that at once)
    code, out = swipe(slowj, "slow@example.com")
    t("...and the swipe goes on as before, still listed", (code, out.get("status"), slowj["id"] in listed()), (200, "handoff", True))

    jobs_api._open_seen.pop(lev["id"], None)
    t("an employer who connected its hiring system: not asked (that send stays as it is)", jobs_api.still_open(lev["id"]), None)
    t("a job this server does not hold (an example listing, a partner's id): not asked", jobs_api.still_open(7), None)
    os.environ["UAPLY_OPEN_CHECK"] = "0"
    jobs_api._open_seen.clear()
    t("UAPLY_OPEN_CHECK=0 switches it off", jobs_api.still_open(closed["id"]), None)
    os.environ.pop("UAPLY_OPEN_CHECK")
    code, out = uaply_api.submit({"plan_only": True, "consent": True, "job": {"id": closed["id"], "co": "Acme", "role": "Closed Role", "url": closed["url"]},
                                  "profile": {"ext": {"phone": "215-555-0100"}, "name": "Sam Rivera", "email": "plan@example.com"}}, None)
    t("a plan (the card's readiness) is not a swipe: not asked", (out.get("code") != "closed", closed["id"] in jobs_api._open_seen), (True, False))
finally:
    mock.terminate()
    slow.shutdown()

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
