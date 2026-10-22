"""Apply-path proof for every source: opens a sample of each source's "Finish applying" links (the employer's own page for a hand-off job)
and reports how many answer, how many are gone, and which sources are over the 10% dead limit.
  python tools/check-apply-links.py --base http://127.0.0.1:8767          the job list of a running local server
  python tools/check-apply-links.py --answer saved-jobs.json               a saved /api/jobs answer
  options: --per 20 (links per source)  --out FILE (JSON results; default: print only)
A posting on Greenhouse, Lever or SmartRecruiters is checked on the hiring system's public API (their job pages refuse anything but a
browser); Ashby and Workable postings are alive while their board lists them; any other page is opened: alive when it answers, dead on
404/410 or a "no longer open" page; a bot check, a rate limit or a time-out is "unknown" and never counted against a source
(jobs_api.job_alive, the same rule the hosted server applies every day)."""
import argparse
import collections
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("UAPLY_CONFIG_FILE", "none")
os.environ.setdefault("UAPLY_DATA_DIR", os.path.join(os.environ.get("TEMP", "/tmp"), "uaply-link-check"))
import jobs_api as J  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base")
    ap.add_argument("--answer")
    ap.add_argument("--per", type=int, default=20)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.answer:
        with open(a.answer, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(urllib.request.urlopen((a.base or "http://127.0.0.1:8767").rstrip("/") + "/api/jobs", timeout=300).read())
    by = collections.defaultdict(list)
    for j in data.get("jobs") or []:
        if str(j.get("url") or "").startswith("https://"):
            by[j.get("via") or j.get("source") or "?"].append(j)
    picks = [(src, j) for src, js in by.items() for j in js[:a.per]]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=12) as ex:
        alive = list(ex.map(lambda p: J.job_alive(p[1]), picks))
    res = collections.defaultdict(lambda: {"ok": 0, "dead": 0, "unknown": 0, "dead_urls": []})
    for (src, j), al in zip(picks, alive):
        r = res[src]
        if al is True:
            r["ok"] += 1
        elif al is False:
            r["dead"] += 1
            r["dead_urls"].append(j["url"])
        else:
            r["unknown"] += 1
    over = {s: r for s, r in res.items() if (r["ok"] + r["dead"]) >= 10 and r["dead"] / (r["ok"] + r["dead"]) > J.LINK_FAIL_LIMIT}
    total = collections.Counter()
    for r in res.values():
        total.update(ok=r["ok"], dead=r["dead"], unknown=r["unknown"])
    print("checked %d links of %d sources in %.0f s: %d alive, %d dead, %d could not tell (blocked or slow)" % (
        len(picks), len(res), time.time() - t0, total["ok"], total["dead"], total["unknown"]))
    print("sources over the %d%% dead limit: %d" % (int(J.LINK_FAIL_LIMIT * 100), len(over)))
    for s, r in sorted(over.items()):
        print("  %-60s %d dead of %d" % (s[:60], r["dead"], r["ok"] + r["dead"]))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump({"checked": time.strftime("%Y-%m-%d %H:%M"), "per_source": res, "over_limit": sorted(over)}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
