"""tools/outreach-queue.py: the week's invitations are ranked as documented, a marked employer leaves the list, the totals count connected
jobs, and the tool can never send anything (no mail, web or socket module, and it runs with the network taken away).
  python tools/test-outreach-queue.py"""
import importlib.util
import io
import json
import os
import re
import shutil
import socket
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


SRC = open(os.path.join(HERE, "outreach-queue.py"), encoding="utf-8").read()
imports = set(re.findall(r"^\s*(?:import|from)\s+([A-Za-z_.]+)", SRC, re.M))
t("it imports no module that can send (mail, web, sockets, subprocesses)", sorted(imports & {"smtplib", "socket", "urllib", "urllib.request", "http", "http.client",
                                                                                            "requests", "subprocess", "email", "ssl", "ftplib"}), [])

spec = importlib.util.spec_from_file_location("outreach_queue", os.path.join(HERE, "outreach-queue.py"))
oq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oq)

TMP = tempfile.mkdtemp(prefix="uaply-outreach-")
try:
    boards = {"boards": [
        {"kind": "greenhouse", "token": "bigco", "name": "Big Co", "us": 900},
        {"kind": "greenhouse", "token": "smallco", "name": "Small Co", "us": 40},
        {"kind": "lever", "token": "leverco", "name": "Lever Co", "us": 300},
        {"kind": "smartrecruiters", "token": "CityCo", "name": "City Co", "us": 120},
        {"kind": "workable", "token": "wkco", "name": "Work Co", "us": 10},
        {"kind": "careerpage", "token": "own-site", "name": "Own Site", "us": 5000},       # not one of the five systems: never in the queue
        {"kind": "ashby", "token": "bad token!", "name": "Bad", "us": 1}]}                 # an odd board name: left out
    bpath, spath, dpath = os.path.join(TMP, "boards.json"), os.path.join(TMP, "state.json"), os.path.join(TMP, "decisions.jsonl")
    json.dump(boards, open(bpath, "w", encoding="utf-8"))
    now = 1792800000
    with open(dpath, "w", encoding="utf-8") as f:
        for i in range(5):
            f.write(json.dumps({"at": now - 3600, "dir": "apply", "jobId": 1, "co": "Small Co", "role": "x", "pct": 50}) + "\n")
        f.write(json.dumps({"at": now - 40 * 86400, "dir": "apply", "jobId": 2, "co": "Lever Co"}) + "\n")      # older than 30 days
        f.write(json.dumps({"at": now - 60, "dir": "pass", "jobId": 3, "co": "Lever Co"}) + "\n")              # a swipe left
    rows = oq.boards(bpath)
    t("only the five hiring systems' boards, with a plain board name", sorted(oq.key(b) for b in rows),
      ["greenhouse:bigco", "greenhouse:smallco", "lever:leverco", "smartrecruiters:cityco", "workable:wkco"])
    sw = oq.swipes(dpath, now=now)
    t("swipes right in the last 30 days, per employer (no swipe left, nothing older)", sw, {"small co": 5})
    order = [oq.key(b) for b in oq.week(rows, {"employers": {}}, sw, "smartrecruiters", 10)]
    t("the week: SmartRecruiters first, then the most swiped-on, then by US jobs",
      order, ["smartrecruiters:cityco", "greenhouse:smallco", "greenhouse:bigco", "lever:leverco", "workable:wkco"])
    t("...and --per-week caps it", len(oq.week(rows, {"employers": {}}, sw, "smartrecruiters", 2)), 2)
    real = socket.socket
    socket.socket = None          # the network is gone: the tool must not need it
    try:
        out = io.StringIO()
        with redirect_stdout(out):
            rc = oq.main(["--boards", bpath, "--state", spath, "--mark", "smartrecruiters:cityco", "invited", "--note", "kit sent to talent@"])
            rc2 = oq.main(["--boards", bpath, "--state", spath, "--mark", "greenhouse:bigco", "connected"])
            out.truncate(0)
            rc3 = oq.main(["--boards", bpath, "--state", spath, "--swipes", dpath, "--per-week", "3"])
    finally:
        socket.socket = real
    text = out.getvalue()
    t("marking and the week's list run with no network", (rc, rc2, rc3), (0, 0, 0))
    st = json.load(open(spath, encoding="utf-8"))
    t("a mark is kept with the day and the note", (st["employers"]["smartrecruiters:cityco"]["status"], st["employers"]["smartrecruiters:cityco"]["history"][-1]["note"]),
      ("invited", "kit sent to talent@"))
    t("an invited or connected employer is not offered again", ("City Co" in text.split("Queue:")[0], "Big Co" in text.split("Queue:")[0]), (False, False))
    t("the totals count the connected employer's jobs (900 of 1370)", bool(re.search(r"connected 1\b.*Connected employers list 900 US jobs, 65\.7%", text)), True)
    t("the list says what each employer creates", "an API token with r_jobs and w_candidates only" in text or "a Job Board API key" in text, True)
    try:
        oq.main(["--boards", bpath, "--state", spath, "--mark", "greenhouse:nobody", "invited"])
        bad = "accepted"
    except SystemExit as e:
        bad = "refused" if "no employer" in str(e) else str(e)
    t("an employer not in the boards file cannot be marked", bad, "refused")
    try:
        oq.main(["--boards", bpath, "--state", spath, "--mark", "greenhouse:smallco", "emailed"])
        bad2 = "accepted"
    except SystemExit as e:
        bad2 = "refused" if "one of" in str(e) else str(e)
    t("a step that is not one of queued, invited, replied, connected, declined is refused", bad2, "refused")
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
