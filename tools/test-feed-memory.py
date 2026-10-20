"""How much memory reading every job board takes, on boards as big as the real ones. No network.
  python tools/test-feed-memory.py                 boards made up here, each the size the real one had on October 17, 2026 (68 MB in all)
  python tools/test-feed-memory.py --boards DIR    recorded answers instead: DIR/gh-<board>.json, lever-<board>.json, ashby-<board>.json,
                                                   workable-<board>.json (save them with curl from the addresses in jobs_api._fetch_raw)
Why: Render's Starter plan has 512 MB. On October 17 the live server sat at about 45 MB, jumped to about 275 MB the moment it read the
boards, and one copy reached 491 MB after a second refresh (memory a Python process has used is mostly not given back). Reading 24 boards
with up to 16 at once (and one background thread per stale board after a redeploy) was the high-water mark.
Each scenario runs in its own fresh Python process (only jobs_api loaded), so one cannot raise the next one's numbers:
  cold     an empty disk: the first visitor's request reads every board
  refresh  a redeploy whose saved job list is older than its 30 minutes: the list is served at once and every board refreshes behind it
For each: the peak of Python's own allocations (tracemalloc, in one run) and the process's peak memory (in a second run without
tracemalloc, which itself costs memory). Passes when every peak stays under LIMIT_MB and the refresh scenario answered at once."""
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIMIT_MB = 350                      # the brief for launch week: well under the plan's 512 MB, with room for requests on top
# The size in bytes of each board's answer as read on October 17, 2026 (curl, content=true). Workable's answered with a redirect page.
SIZES = {"gh-databricks": 9851537, "gh-cloudflare": 7570351, "gh-stripe": 5704838, "gh-datadog": 5423884, "gh-samsara": 4407135,
         "gh-verkada": 3773269, "gh-block": 3449237, "gh-waymo": 2903208, "gh-roblox": 2567055, "gh-coinbase": 2497078,
         "gh-affirm": 2321223, "gh-scaleai": 2156181, "gh-robinhood": 1953522, "gh-pinterest": 1859076, "gh-lyft": 1690681,
         "gh-figma": 1651143, "gh-imc": 1214228, "gh-duolingo": 762838, "gh-dropbox": 411026, "gh-discord": 405085,
         "gh-squarespace": 328959, "lever-spotify": 791140, "ashby-webflow": 437195, "ashby-linear": 397002,
         # the 31 boards added on October 20, 2026, at the size they answered that day (Carvana is the largest board UAply reads)
         "gh-carvana": 18777519, "gh-doordashusa": 8412796, "gh-axon": 8032352, "gh-mongodb": 4436423, "gh-toast": 3924689,
         "gh-charliehealth": 3369628, "gh-airbnb": 2609305, "gh-oscar": 2555113, "gh-brex": 2540530, "gh-mejuri": 2335330,
         "gh-reddit": 2078111, "gh-strivehealth": 2021153, "gh-twilio": 1890764, "gh-point72": 1598630, "gh-instacart": 1499607,
         "gh-gusto": 1422711, "gh-chime": 1220483, "gh-motional": 1090329, "gh-shipmonk": 1055235, "gh-faire": 1028700,
         "gh-sweetgreen": 723729, "gh-ziprecruiter": 444256, "gh-twochairs": 332578, "gh-glossier": 278838, "gh-vynamic": 276452,
         "gh-perpay": 246496, "gh-wonderschool": 245434, "gh-elationhealth": 157040, "lever-gopuff": 8127467, "lever-zoox": 2454408,
         "ashby-ramp": 2847202}
R = []


def t(name, ok):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name)


# ---------- made-up boards, shaped like the real answers ----------
PARA = ("<p>We’re looking for people who care about craft • You’ll work with Python, SQL, React and AWS on systems used by "
        "millions of customers. Benefits include medical, dental and vision insurance, 401(k) matching, paid parental leave and "
        "tuition reimbursement. The base salary range for this role is $120,000 - $180,000.</p>\n<ul><li>Design and build "
        "services</li><li>Write tests and reviews</li><li>Mentor teammates</li></ul>\n")
TITLES = ["Software Engineering Intern", "Senior Software Engineer, Payments", "Data Scientist", "Product Designer", "Marketing Manager",
          "Staff Engineer, Infrastructure", "Recruiter", "Account Executive", "Data Engineer, New Grad", "Security Engineer"]
PLACES = ["San Francisco, CA", "New York, NY", "Remote - US", "Seattle, WA", "London, UK", "Toronto, Canada", "Austin, TX"]


# posted five days before the run, so the 60-day rule (jobs_api.MAX_AGE_DAYS) never ages the made-up boards out
RECENT = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5 * 86400))


def make_board(path, kind, size, seed):
    rnd = random.Random(seed)
    jobs, total, i = [], 0, 0
    while total < size:
        reps = rnd.randint(8, 22)
        body = "".join(PARA for _ in range(reps))
        title, place = rnd.choice(TITLES), rnd.choice(PLACES)
        if kind == "gh":
            j = {"absolute_url": "https://boards.greenhouse.io/x/jobs/%d" % (seed * 10000 + i), "data_compliance": [], "internal_job_id": i,
                 "location": {"name": place}, "metadata": None, "id": seed * 10000 + i, "updated_at": RECENT,
                 "requisition_id": "R%d" % i, "title": title, "company_name": "Board %d" % seed, "first_published": RECENT,
                 "language": "en", "content": html.escape(body), "departments": [{"id": 1, "name": "Engineering"}], "offices": [{"id": 1, "name": place}]}
        elif kind == "lever":
            j = {"id": "lv-%d-%d" % (seed, i), "text": title, "categories": {"location": place, "team": "Engineering"}, "workplaceType": "onsite",
                 "descriptionPlain": re.sub(r"<[^>]+>", " ", body), "description": body, "additionalPlain": "", "additional": "",
                 "hostedUrl": "https://jobs.lever.co/x/%d" % i, "createdAt": int(time.time() * 1000) - 5 * 86400000}
        else:
            j = {"id": "ab-%d-%d" % (seed, i), "title": title, "location": place, "isRemote": "Remote" in place, "isListed": True,
                 "descriptionPlain": re.sub(r"<[^>]+>", " ", body), "descriptionHtml": body, "jobUrl": "https://jobs.ashbyhq.com/x/%d" % i,
                 "publishedAt": RECENT}
        s = json.dumps(j, ensure_ascii=False)
        jobs.append(s)
        total += len(s.encode("utf-8")) + 1
        i += 1
    text = "[" + ",".join(jobs) + "]" if kind == "lever" else '{"jobs":[' + ",".join(jobs) + "]}"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


# ---------- the measuring child: python tools/test-feed-memory.py --child SCENARIO BOARDS_DIR DATA_DIR trace|rss ----------
def peak_rss_mb():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        k = ctypes.WinDLL("kernel32")
        k.GetCurrentProcess.restype = wintypes.HANDLE
        gpmi = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        gpmi.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        gpmi(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return c.PeakWorkingSetSize / 1e6
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3          # kilobytes on Linux


def rss_now_mb():
    try:
        with open("/proc/self/status") as f:
            return int(re.search(r"VmRSS:\s+(\d+)", f.read()).group(1)) / 1e3
    except OSError:
        return None


def child(scenario, boards, data, mode):
    os.environ.update(UAPLY_DATA_DIR=data, UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}", UAPLY_FEEDS="greenhouse,lever,ashby,workable")
    os.environ.pop("UAPLY_FEEDS_OFF", None)
    sys.path.insert(0, ROOT)
    import io
    import urllib.request
    import threading
    import jobs_api as J
    reads = {}

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        reads[url] = reads.get(url, 0) + 1
        m = (re.search(r"greenhouse\.io/v1/boards/([^/]+)/", url) and ("gh", re.search(r"boards/([^/]+)/", url).group(1))) or \
            (re.search(r"lever\.co/v0/postings/([^?]+)", url) and ("lever", re.search(r"postings/([^?]+)", url).group(1))) or \
            (re.search(r"ashbyhq\.com/posting-api/job-board/(.+)$", url) and ("ashby", re.search(r"job-board/(.+)$", url).group(1))) or \
            (re.search(r"workable\.com/api/accounts/([^?]+)", url) and ("workable", re.search(r"accounts/([^?]+)", url).group(1)))
        path = os.path.join(boards, "%s-%s.json" % m) if m else ""
        if not path or not os.path.exists(path):
            raise urllib.error.URLError("no recorded answer for %s" % url)
        time.sleep(0.2 + os.path.getsize(path) / 20e6)            # about what the network takes (20 MB/s), so boards overlap as they do live
        with open(path, "rb") as f:
            data_bytes = f.read()
        r = io.BytesIO(data_bytes)
        del data_bytes
        return r
    import urllib.error
    urllib.request.urlopen = fake_urlopen
    if mode == "trace":
        import tracemalloc
        tracemalloc.start()
    t0 = time.time()
    answered = None
    if scenario == "cold":                   # the first visitor and two more who arrive while the boards are being read
        outs = []
        visitors = [threading.Thread(target=lambda: outs.append(J.get_jobs())) for _ in range(3)]
        for v in visitors:
            v.start()
            time.sleep(0.5)
        for v in visitors:
            v.join()
        out = outs[0]
        answered = time.time() - t0
    else:                                    # refresh: a saved copy two hours old (inside the day it may be used, past its 30 minutes)
        with open(os.path.join(data, "jobs-cache.json"), encoding="utf-8") as f:
            saved = json.load(f)
        for k, v in saved.items():
            if isinstance(v, dict):
                v["at"] = time.time() - 7200
        with open(os.path.join(data, "jobs-cache.json"), "w", encoding="utf-8") as f:
            json.dump(saved, f)
        out = J.get_jobs()
        answered = time.time() - t0
        while True:                          # wait until every background refresh has finished
            with J._lock:
                busy = bool(J._refreshing)
            if not busy:
                break
            time.sleep(0.05)
    took = time.time() - t0
    res = {"scenario": scenario, "jobs": len(out["jobs"]), "answered_s": round(answered, 2), "took_s": round(took, 1),
           "sources_ok": sum(1 for v in out["sources"].values() if re.match(r"\d+ jobs", v)), "most_reads_of_one_board": max(reads.values() or [0])}
    if mode == "trace":
        import tracemalloc
        res["trace_peak_mb"] = round(tracemalloc.get_traced_memory()[1] / 1e6, 1)
    else:
        res["rss_peak_mb"] = round(peak_rss_mb(), 1)
        now = rss_now_mb()
        if now:
            res["rss_after_mb"] = round(now, 1)
    print(json.dumps(res))


def main():
    args = sys.argv[1:]
    if args[:1] == ["--child"]:
        return child(*args[1:5])
    tmp = tempfile.mkdtemp(prefix="uaply-feedmem-")
    try:
        if args[:1] == ["--boards"]:
            boards = os.path.abspath(args[1])
            print("recorded answers from %s" % boards)
        else:
            boards = os.path.join(tmp, "boards")
            os.makedirs(boards)
            for n, (name, size) in enumerate(sorted(SIZES.items())):
                make_board(os.path.join(boards, name + ".json"), name.split("-")[0], size, n + 1)
            print("made up %d boards, %.0f MB in all" % (len(SIZES), sum(os.path.getsize(os.path.join(boards, f)) for f in os.listdir(boards)) / 1e6))
        data = os.path.join(tmp, "data")
        os.makedirs(data)
        results = {}
        for scenario in ("cold", "refresh"):
            for mode in ("rss", "trace"):
                if scenario == "cold" and os.path.exists(os.path.join(data, "jobs-cache.json")):
                    os.remove(os.path.join(data, "jobs-cache.json"))
                r = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", scenario, boards, data, mode],
                                   capture_output=True, text=True, timeout=900)
                line = (r.stdout.strip().splitlines() or ["{}"])[-1]
                try:
                    got = json.loads(line)
                except ValueError:
                    got = {}
                if not got:
                    print(r.stdout[-2000:], r.stderr[-2000:])
                results.setdefault(scenario, {}).update(got)
            # leave a saved copy in place for the refresh scenario
        for scenario, r in results.items():
            print("  %-8s %s" % (scenario, json.dumps(r)))
        cold, ref = results.get("cold", {}), results.get("refresh", {})
        t("cold: every board was read (%s of them with jobs, %s jobs)" % (cold.get("sources_ok"), cold.get("jobs")), (cold.get("sources_ok") or 0) >= 20)
        t("cold: three visitors during the first fill read each board once between them (%s)" % cold.get("most_reads_of_one_board"),
          cold.get("most_reads_of_one_board") == 1)
        for scenario, r in (("cold", cold), ("refresh", ref)):
            t("%s: Python's own allocations peak under %d MB (%s MB)" % (scenario, LIMIT_MB, r.get("trace_peak_mb")), (r.get("trace_peak_mb") or 1e9) < LIMIT_MB)
            t("%s: the process's peak memory stays under %d MB (%s MB)" % (scenario, LIMIT_MB, r.get("rss_peak_mb")), (r.get("rss_peak_mb") or 1e9) < LIMIT_MB)
        # The first visitor on an empty disk waits at most FIRST_WAIT (90 s); with 55 boards some finish after that and are only in the saved
        # copy, so the refresh (which serves that copy) can show more jobs than the cold answer did, never fewer.
        t("refresh: the saved list answered at once (%s s, %s jobs; cold %s) while every board refreshed behind it (%s s)" % (
          ref.get("answered_s"), ref.get("jobs"), cold.get("jobs"), ref.get("took_s")),
          (ref.get("answered_s") or 99) < 3 and (ref.get("jobs") or 0) >= (cold.get("jobs") or 1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(sum(R), "/", len(R))
    sys.exit(0 if all(R) else 1)


if __name__ == "__main__":
    main()
