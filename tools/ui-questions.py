"""The one-time question box in a real browser: a swipe right on an employer whose form asks every kind of question the profile cannot answer
(long text, a long searchable list, a multi-select, a month, a date, a number with its unit, a yes/no and a notice to read and accept, plus a
voluntary question that must never appear). It is answered with the keyboard and by touch, the application goes, a second employer asking the
same questions gets the saved answers without asking, and Profile setup, under Eligibility and extras, lists the answers and lets the person
change or remove one. Runs at 390x844 (phone, touch) and 1280x800 (computer, mouse and keyboard).
Starts its own stand-in hiring system (mock-ats.py) and one UAply server (dev, test mode). Nothing leaves this computer.
  python tools/ui-questions.py [first port]        (uses 2 ports from there; default 20430)"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
P = int(sys.argv[1]) if len(sys.argv) > 1 else 20430
ATS, PORT = P, P + 1
TMP = tempfile.mkdtemp(prefix="uaply-questions-")
sys.path.insert(0, ROOT)
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=TMP)
import jobs_api  # noqa: E402


def seed(data):
    os.makedirs(data, exist_ok=True)
    cache = {"_version": jobs_api.CACHE_VERSION}
    for kind, board, name in jobs_api.SOURCES:              # every feed is "fresh and empty" so nothing is fetched from the internet
        cache["%s|%s|%s" % (kind, board, name)] = {"at": time.time(), "jobs": [], "status": "0 jobs"}
    with open(os.path.join(data, "jobs-cache.json"), "w", encoding="utf-8") as f:
        json.dump(cache, f)
    ats = {"kind": "greenhouse", "board": "acme", "api_key": "gh-secret-key-123"}
    with open(os.path.join(data, "uaply-partners.json"), "w", encoding="utf-8") as f:
        json.dump({"employers": [
            {"name": "Every Kind Co", "consent": "test partner agreement", "url": "https://everykind.example/careers", "ats": ats,
             "jobs": [{"role": "Data Analyst", "skills": ["Python"], "ats_job_id": "1007", "loc": "Philadelphia, PA", "type": "internship"}]},
            {"name": "Second Co", "consent": "test partner agreement", "url": "https://second.example/careers", "ats": ats,
             "jobs": [{"role": "Data Analyst", "skills": ["Python"], "ats_job_id": "1008", "loc": "Philadelphia, PA", "type": "internship"}]}]}, f)


def get(path):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, path), timeout=30) as r:
        return json.loads(r.read())


procs = [subprocess.Popen([sys.executable, os.path.join(HERE, "mock-ats.py"), str(ATS)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]
code = 1
try:
    data = os.path.join(TMP, "dev")
    seed(data)
    cfg = {"feeds": [], "delivery": "test", "smtp": {}, "google": {}, "owner_copy": ""}
    env = dict(os.environ, UAPLY_DATA_DIR=data, UAPLY_CONFIG_JSON=json.dumps(cfg), UAPLY_ATS_BASE_GREENHOUSE="http://127.0.0.1:%d" % ATS)
    procs.append(subprocess.Popen([sys.executable, "serve.py", str(PORT), "dev", "--api"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    ids = {}
    for _ in range(60):
        try:
            ids = {"%s|%s" % (j["co"], j["role"]): j["id"] for j in get("/api/jobs")["jobs"]}
            if ids:
                break
        except Exception:
            pass
        time.sleep(0.5)
    json.dump(ids, open(os.path.join(TMP, "ids.json"), "w"))
    failed = 0
    for w, h in ((390, 844), (1280, 800)):
        env = dict(os.environ, PORT=str(PORT), IDS=os.path.join(TMP, "ids.json"), W=str(w), H=str(h))
        failed += subprocess.run(["node", os.path.join(HERE, "cdp.js"), os.path.join(HERE, "ui-questions.js")], cwd=ROOT, env=env).returncode != 0
    code = 1 if failed else 0
finally:
    for p in procs:
        p.terminate()
    time.sleep(0.5)
    shutil.rmtree(TMP, ignore_errors=True)
print("question box in the browser:", "all passed" if code == 0 else "FAILED")
sys.exit(code)
