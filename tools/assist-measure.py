"""Assisted apply, measured on real postings in one command (docs/assisted-apply.md). Nothing is ever submitted.

  python tools/assist-measure.py --phone R5GL1614C2E          the Galaxy's Chrome over USB (its own tab, its own adb forward port)
  python tools/assist-measure.py                              headless Chrome on this computer (Greenhouse refuses headless Chrome)
  options: --per 20  --systems greenhouse,lever,ashby,workable  --bridge required|all|off  --urls saved.json  --out folder  --port 20571

1. Postings: 20 per system from the systems' own public job lists (the same employers each time, in turn), unless --urls gives a saved
   list ({"greenhouse": [...], ...}). Greenhouse, Lever, Ashby and Workable publish these lists for anyone to read.
2. tools/assist-measure.js opens each application form, runs the bridge (UAplyAssist.scan, then a test person's plain answers to what
   the profile cannot answer: --bridge required, the app's default; all, the optional ones too; off, the profile alone) and the fill, and
   refuses every request that could carry an application or a file.
3. A table per system: fill rate, what the person typed in the bridge, required fields left at the form, consent boxes left for the
   person, resume, human checks, time to ready; and report.json, the per-field log, phone screenshots in --out.
adb comes from the ADB variable, else from PATH. Only this run's own tab is opened and closed, and only its own forward is removed.
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EMPLOYERS = {
    "greenhouse": ["robinhood", "imc", "figma", "discord", "verkada", "scaleai", "affirm"],
    "lever": ["spotify", "gopuff", "zoox", "BestEgg", "solidcore"],
    "ashby": ["webflow", "linear"],
    "workable": ["huggingface", "thorlabs", "ascendis-pharma"],
}
UA = {"User-Agent": "UAply-measure/1.0 (assisted apply research; no submissions)"}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def postings(system):
    """each employer's form addresses, from its public list"""
    out = []
    for co in EMPLOYERS[system]:
        try:
            if system == "greenhouse":
                jobs = get_json("https://boards-api.greenhouse.io/v1/boards/%s/jobs" % co).get("jobs", [])
                out.append(["https://job-boards.greenhouse.io/embed/job_app?for=%s&token=%s" % (co, j["id"]) for j in jobs])
            elif system == "lever":
                jobs = get_json("https://api.lever.co/v0/postings/%s?mode=json" % co)
                out.append([j["hostedUrl"].rstrip("/") + "/apply" for j in jobs if j.get("hostedUrl")])
            elif system == "ashby":
                jobs = get_json("https://api.ashbyhq.com/posting-api/job-board/%s" % co).get("jobs", [])
                out.append([j["jobUrl"].rstrip("/") + "/application" for j in jobs if j.get("jobUrl")])
            elif system == "workable":
                jobs = get_json("https://www.workable.com/api/accounts/%s?details=true" % co).get("jobs", [])
                out.append(["https://apply.workable.com/%s/j/%s/apply/" % (co, j["shortcode"]) for j in jobs if j.get("shortcode")])
        except Exception as e:
            print("  could not read %s's list on %s: %s" % (co, system, e))
    return out


def pick(lists, n):
    """n postings, taking one from each employer in turn"""
    got, i = [], 0
    while len(got) < n and any(i < len(l) for l in lists):
        for l in lists:
            if i < len(l) and len(got) < n:
                got.append(l[i])
        i += 1
    return got


def adb_path():
    a = os.environ.get("ADB") or shutil.which("adb")
    if not a:
        sys.exit("adb not found: set ADB to adb.exe (Android platform-tools)")
    return a


def table(report):
    rows = ["| System | Postings (form reached) | Fill rate | Fill, required answers only | Asked in the bridge (median: required / optional) | Required left at the form (median) | of which consent boxes | Resume | Human check | Time to ready (median) |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for system, rs in report["results"].items():
        ok = [r for r in rs if not r.get("noForm") and not r.get("error")]
        if not ok:
            rows.append("| %s | %d (0) | not measurable | | | | | | %s | |" % (system, len(rs), "bot or error page" if rs else ""))
            continue
        seen = sum(r["seen"] for r in ok)
        filled = sum(r["filled"] for r in ok)
        opt = sum(r.get("fromAnswersOpt", 0) for r in ok)
        med = lambda xs: statistics.median(xs) if xs else 0
        checks = [r for r in ok if r.get("humanCheck")]
        kinds = "+".join(sorted({r.get("checkKind") or "?" for r in checks})) or "none"
        rows.append("| %s | %d (%d) | **%d%%** | %d%% | %s / %s | %s | %s | %d/%d | %d/%d %s | %.1f s |" % (
            system, len(rs), len(ok), round(100 * filled / seen) if seen else 0, round(100 * (filled - opt) / seen) if seen else 0,
            med([r.get("askedReq", 0) for r in ok]), med([r.get("asked", 0) - r.get("askedReq", 0) for r in ok]),
            med([r.get("leftReq", 0) for r in ok]), med([r.get("consentReq", 0) for r in ok]),
            sum(1 for r in ok if r.get("resumeAttached")), len(ok), len(checks), len(ok), kinds, med([r.get("readyMs", 0) for r in ok]) / 1000))
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phone", help="adb serial of the phone; omitted: headless Chrome here")
    ap.add_argument("--port", type=int, default=20571)
    ap.add_argument("--per", type=int, default=20)
    ap.add_argument("--systems", default="greenhouse,lever,ashby,workable")
    ap.add_argument("--bridge", default="required", choices=["required", "all", "off"])
    ap.add_argument("--urls")
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "uaply-assist-measure"))   # never the data folder
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    systems = [s for s in a.systems.split(",") if s]
    if a.urls:
        urls = {k: v[:a.per] for k, v in json.load(open(a.urls, encoding="utf-8")).items() if k in systems}
    else:
        urls = {s: pick(postings(s), a.per) for s in systems}
    urls_file = os.path.join(a.out, "urls.json")
    json.dump(urls, open(urls_file, "w", encoding="utf-8"), indent=1)
    print("postings: " + ", ".join("%s %d" % (k, len(v)) for k, v in urls.items()))
    env = dict(os.environ, URLS=urls_file, OUT=os.path.join(a.out, "report.json"), SHOTS=os.path.join(a.out, "shots"), BRIDGE=a.bridge, DEBUG="1", W="390", H="844")
    adb, fwd = None, "tcp:%d" % a.port
    if a.phone:
        adb = adb_path()
        subprocess.run([adb, "-s", a.phone, "forward", fwd, "localabstract:chrome_devtools_remote"], check=True)
        # this run's own Chrome tab (Chrome must be in front to open one; this brings it there with a harmless page)
        subprocess.run([adb, "-s", a.phone, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "'https://example.com/?uaply-measure'",
                        "-p", "com.android.chrome", "--es", "com.android.browser.application_id", "uaply-measure"], check=True, capture_output=True)
        time.sleep(4)
        env.update(CDP_ATTACH="127.0.0.1:%d" % a.port, CDP_TAB="uaply-measure")
    try:
        log = open(os.path.join(a.out, "measure.log"), "w", encoding="utf-8")
        p = subprocess.run(["node", os.path.join(HERE, "cdp.js"), os.path.join(HERE, "assist-measure.js")], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        log.close()
    finally:
        if a.phone:
            try:   # close only this run's tab (it ends on about:blank#uaply-assist-done), then remove only this run's forward
                for t in get_json("http://127.0.0.1:%d/json" % a.port):
                    if "uaply-assist-done" in t.get("url", "") or "uaply-measure" in t.get("url", ""):
                        urllib.request.urlopen("http://127.0.0.1:%d/json/close/%s" % (a.port, t["id"]), timeout=10).read()
            except Exception as e:
                print("  could not close the tab: %s" % e)
            subprocess.run([adb, "-s", a.phone, "forward", "--remove", fwd])
    rep_file = os.path.join(a.out, "report.json")
    if p.returncode != 0 or not os.path.exists(rep_file):
        sys.exit("the measurement failed; see " + os.path.join(a.out, "measure.log"))
    report = json.load(open(rep_file, encoding="utf-8"))
    t = table(report)
    open(os.path.join(a.out, "table.md"), "w", encoding="utf-8").write(t + "\n")
    print(t)
    print("requests refused (never sent): %d" % report.get("blocked", 0))


if __name__ == "__main__":
    main()
