"""Finds employers' public job boards on Greenhouse, Lever, Ashby, SmartRecruiters and Workable, checks each one live, and writes the
candidates to a review file. Read-only: it only reads the same public, keyless endpoints the job list reads.

  python tools/find-boards.py --names tools/data/board-seeds.txt            company names or domains, one per line (# comments)
  python tools/find-boards.py --simplify                                     every company on the Simplify / Pitt CSC lists (their links name the board)
  python tools/find-boards.py Comcast "Cross River Bank" toasttab.com        names on the command line
  options: --out FILE (default tools/data/board-candidates.json)  --min-us N (default 5)  --workers N (default 8)

For a name it tries slugs on every system: the name squashed ("crossriverbank"), hyphenated ("cross-river-bank"), with "inc"/"hq"/"careers"
added or a trailing Inc/LLC/Corp taken off, and a domain's first label ("toasttab.com" -> "toasttab"). For the Simplify lists the board
token is read from each posting's own link, so nothing is guessed. Each board found is counted: postings, US postings, Pennsylvania /
New Jersey / Delaware postings, answer size. A board already in jobs_api.SOURCES is marked "known". The review file lists every board
with at least --min-us US postings, most tri-state jobs first; nothing is added to the app by this tool."""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("UAPLY_CONFIG_FILE", "none")
os.environ.setdefault("UAPLY_DATA_DIR", os.path.join(os.environ.get("TEMP", "/tmp"), "uaply-find-boards"))
import jobs_api as J  # noqa: E402

UA = "UAplyDev/0.1 (board check; +https://uaply.net)"
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
TRI_RE = re.compile(r"\bPennsylvania\b|\bNew Jersey\b|\bDelaware\b|, (?:PA|NJ|DE)\b|[a-z] (?:PA|NJ|DE)$|\bPhiladelphia\b|\bPittsburgh\b|\bTrenton\b|"
                    r"\bCamden\b|\bCherry Hill\b|\bJersey City\b|\bHoboken\b|\bPrinceton\b|\bWilmington, (?:DE|Delaware)\b")
SUFFIX_RE = re.compile(r"\b(?:inc|llc|ltd|corp|corporation|co|company|group|holdings|the)\b\.?", re.I)


import threading  # noqa: E402

PER_HOST_GAP = 0.25                   # seconds between two requests to the same system (about 4 a second): the first run at 12 at once got HTTP 429
_host_next, _host_lock = {}, threading.Lock()


def _wait_turn(host):
    with _host_lock:
        now = time.time()
        at = max(now, _host_next.get(host, 0.0))
        _host_next[host] = at + (1.5 if "workable" in host else PER_HOST_GAP)      # Workable answers 429 at a few requests a second
    if at > now:
        time.sleep(at - now)


def get_json(url, tries=4):
    """One public answer, at most about 4 requests a second per system, waiting and trying again when the system says 429 (too many)."""
    host = urllib.parse.urlsplit(url).hostname or ""
    for attempt in range(tries):
        _wait_turn(host)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read(J.MAX_FEED_BYTES + 1)
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == tries - 1:
                raise
            wait = e.headers.get("Retry-After") if e.headers else None
            time.sleep(min(60, float(wait)) if wait and wait.isdigit() else 5 * (attempt + 1))
            with _host_lock:                  # the whole system slows down a little after a 429
                _host_next[host] = time.time() + PER_HOST_GAP * 4
    if len(body) > J.MAX_FEED_BYTES:
        raise ValueError("over the %d MB cap" % (J.MAX_FEED_BYTES // 1000000))
    return json.loads(body.decode("utf-8", "replace")), len(body)


def count(kind, token):
    """(total, us, tri, bytes, name) for one board, or None when it does not exist / has nothing."""
    q = urllib.parse.quote(token, safe="")
    if kind == "greenhouse":
        d, n = get_json("https://boards-api.greenhouse.io/v1/boards/%s/jobs" % q)
        jobs = d.get("jobs") or []
        locs = [((j.get("location") or {}).get("name") or "") for j in jobs]
        name = next((j.get("company_name") for j in jobs if j.get("company_name")), "")
    elif kind == "lever":
        d, n = get_json("https://api.lever.co/v0/postings/%s?mode=json" % q)
        jobs = d if isinstance(d, list) else []
        locs = [((j.get("categories") or {}).get("location") or "") for j in jobs]
        name = ""
    elif kind == "ashby":
        d, n = get_json("https://api.ashbyhq.com/posting-api/job-board/%s" % q)
        jobs = [j for j in (d.get("jobs") or []) if j.get("isListed") is not False]
        locs = [(j.get("location") or "") for j in jobs]
        name = ""
    elif kind == "smartrecruiters":
        d, n = get_json("https://api.smartrecruiters.com/v1/companies/%s/postings?limit=100" % q)
        jobs = d.get("content") or []
        total = int(d.get("totalFound") or 0)
        us = [j for j in jobs if ((j.get("location") or {}).get("country") or "").lower() == "us"]
        tri = [j for j in us if ((j.get("location") or {}).get("region") or "").upper() in ("PA", "NJ", "DE")]
        if not total:
            return None
        share = total / max(1, len(jobs))                   # the first page of 100 stands for the whole list
        name = next(((j.get("company") or {}).get("name") for j in jobs if (j.get("company") or {}).get("name")), "")
        return total, int(len(us) * share), int(len(tri) * share), n, name
    elif kind == "icims":
        # an employer's iCIMS careers site: its robots.txt must allow the sitemap; counted are its job pages changed in the last 60 days
        host = "careers-%s.icims.com" % token.lower()
        sm = "https://%s/sitemap.xml" % host
        try:
            robots = get_text("https://%s/robots.txt" % host)
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                robots = ""
            else:
                raise
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(robots.splitlines())
        if not rp.can_fetch(J.CP_UA, sm) or J.HUMAN_CHECK_RE.search(robots):
            return None
        xml, sm = get_text(sm, final=True)                # the address it ends at after redirects (careers-x -> externalcareers-x)
        now = time.time() * 1000
        recent = [m for m in re.findall(r"<url>(.*?)</url>", xml, re.S) if "/jobs/" in m and
                  (not re.search(r"<lastmod>(.*?)</lastmod>", m) or now - J._ts(re.search(r"<lastmod>(.*?)</lastmod>", m).group(1)) < 60 * 86400000)]
        if not recent:
            return None
        return len(recent), len(recent), 0, len(xml), "", sm
    elif kind == "workable":
        d, n = get_json("https://www.workable.com/api/accounts/%s" % q)
        jobs = d.get("jobs") or []
        locs = [", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x) for j in jobs]
        name = d.get("name") or ""
    else:
        return None
    if not jobs:
        return None
    us = [l for l in locs if J._us_ok(l, bool(re.search(r"remote", l, re.I)))]
    return len(jobs), len(us), sum(1 for l in us if TRI_RE.search(l)), n, name


def get_text(url, final=False):
    host = urllib.parse.urlsplit(url).hostname or ""
    _wait_turn(host)
    req = urllib.request.Request(url, headers={"User-Agent": J.CP_UA, "Accept": "text/html,application/xml,*/*"})
    with urllib.request.urlopen(req, timeout=25) as r:
        text = r.read(J.MAX_FEED_BYTES).decode("utf-8", "replace")
        return (text, r.geturl()) if final else text


def slugs(name):
    """The board tokens a company is likely to use."""
    n = name.strip()
    if re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", n, re.I):                # a domain: its first label
        n = n.split(".")[-2] if n.count(".") >= 1 else n
        return [n.lower()]
    base = re.sub(r"[^A-Za-z0-9 &-]", "", n)
    short = SUFFIX_RE.sub(" ", base).replace("&", " and ")
    words = [w for w in re.split(r"[\s-]+", short) if w]
    out = []
    for w in (words, [x for x in re.split(r"[\s-]+", base.replace("&", "and")) if x]):
        if not w:
            continue
        out += ["".join(w).lower(), "-".join(w).lower(), "".join(w).lower() + "inc", "".join(w).lower() + "careers"]   # boards ignore letter case
        if len(w) > 1:
            out.append(w[0].lower())
    seen, uniq = set(), []
    for s in out:
        if s and TOKEN_RE.match(s) and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


SIMPLIFY_LINK = [("greenhouse", re.compile(r'https://(?:job-)?boards(?:\.eu)?\.greenhouse\.io/([A-Za-z0-9_-]+)/')),
                 ("lever", re.compile(r'https://jobs\.lever\.co/([A-Za-z0-9_.-]+)/')),
                 ("ashby", re.compile(r'https://jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)')),
                 ("smartrecruiters", re.compile(r'https://jobs\.smartrecruiters\.com/([A-Za-z0-9_-]+)/')),
                 ("workable", re.compile(r'https://apply\.workable\.com/([A-Za-z0-9_-]+)/'))]


SIMPLIFY_LISTINGS = ["https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
                     "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json"]


def simplify_boards():
    """Every (kind, token, company) a Simplify / Pitt CSC list links to: the full listings files behind the README tables (internships,
    off-season and new-grad roles, open and closed: a closed posting's board may have other jobs), then the README pages themselves."""
    found = {}
    for url in SIMPLIFY_LISTINGS:
        try:
            rows = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read().decode("utf-8", "replace"))
        except Exception as e:
            print("could not read %s: %s" % (url, e), file=sys.stderr)
            continue
        for row in rows if isinstance(rows, list) else []:
            link = str(row.get("url") or "") if isinstance(row, dict) else ""
            for kind, rx in SIMPLIFY_LINK:
                m = rx.match(link)
                if m:
                    tok = urllib.parse.unquote(m.group(1))
                    if TOKEN_RE.match(tok):
                        found.setdefault((kind, tok.lower()), str(row.get("company_name") or tok))
                    break
        del rows
    for page in ("README.md", "README-Off-Season.md", "README-Inactive.md"):
        try:
            text = urllib.request.urlopen(urllib.request.Request(J.SIMPLIFY_REPO + page, headers={"User-Agent": UA}), timeout=60).read().decode("utf-8", "replace")
        except Exception as e:
            print("could not read %s: %s" % (page, e), file=sys.stderr)
            continue
        company = ""
        for tr in re.findall(r"<tr>(.*?)</tr>", text, re.S):
            cells = re.findall(r"<td>(.*?)</td>", tr, re.S)
            if not cells:
                continue
            name = re.sub(r"<[^>]+>", "", cells[0]).replace("\U0001f525", "").strip()
            company = company if name in ("↳", "") else name
            for kind, rx in SIMPLIFY_LINK:
                for tok in rx.findall(tr):
                    tok = urllib.parse.unquote(tok)
                    if TOKEN_RE.match(tok):
                        found.setdefault((kind, tok.lower()), company)
    return found


# Staffing agencies post other companies' openings under their own name (and often the same opening many times): not added in bulk
STAFFING_RE = re.compile(r"\b(?:staffing|recruit(?:ing|ers|ment)?|talent (?:solutions|partners)|workforce solutions|placement|manpower|"
                         r"mindlance|marlabs|infotech|tech ?tammina|sonsoft|jobsbridge|integrated resources|pioneer data|amnet|"
                         r"national software management|worldwide techservices|iflip|kanshe|roljobs|qode|sqa services|mthree|jobs for humanity|"
                         r"collabera|tec ?tammina|krg technology|stem ?xpert|avance consulting|atria group|prosidian|it services|"
                         r"consulting services|consultancy services|tech solutions|infosys|wipro|tata consultancy|cognizant technology|hcl|"
                         r"randstad|adecco|kelly services|robert half|insight global|teksystems|aerotek|apex systems|kforce|cybercoders)\b", re.I)


def add_reviewed(review_files, min_us, boards_file, limit=None):
    """Adds every board in the review files with at least min_us US postings that is not in the app yet (and not a staffing agency) to
    job-boards.json, most PA / NJ / DE postings first, then most US postings. Returns how many were added."""
    try:
        with open(boards_file, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {"boards": []}
    rows = data.setdefault("boards", [])
    have = {(k, t.lower()) for k, t, _ in J.SOURCES} | {(r["kind"], r["token"].lower()) for r in rows}
    added = 0
    cands = []
    for path in review_files:
        with open(path, encoding="utf-8") as f:
            cands += json.load(f).get("candidates") or []
    checked = time.strftime("%Y-%m-%d")
    if True:
        for c in sorted(cands, key=lambda r: (-r.get("tri", 0), -r.get("us", 0))):
            if limit is not None and added >= limit:
                break
            key = (c["kind"], c["token"].lower())
            name = J._clean_company(c.get("name") or c.get("for") or c["token"], c["token"])
            if c["kind"] == "careerpage" and ("careerpage-name", name.lower()) in have:
                continue                                 # two slugs for one employer's site (careers-northside / careers-northsidehospital)
            if c["kind"] == "careerpage":
                have.add(("careerpage-name", name.lower()))
            if key in have or c.get("us", 0) < min_us or STAFFING_RE.search(name) or not TOKEN_RE.match(c["token"]):
                continue
            have.add(key)
            row = {"kind": c["kind"], "token": c["token"], "name": name, "total": c.get("total"), "us": c.get("us"), "tri": c.get("tri"), "checked": checked}
            if c.get("sitemap"):
                row["sitemap"] = c["sitemap"]           # a careers site: read from its sitemap and the job pages' JobPosting data
            rows.append(row)
            added += 1
    rows.sort(key=lambda r: (-(r.get("tri") or 0), -(r.get("us") or 0), r["name"].lower()))   # read in this order on a fresh start: tri-state first
    data["note"] = ("Employer boards found and checked live with tools/find-boards.py (counts on the day checked). Read by jobs_api.py after "
                    "the hand-picked boards in SOURCES. Remove a row to stop reading a board.")
    with open(boards_file, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", nargs="+", metavar="REVIEW_FILE", help="add the reviewed candidates to job-boards.json instead of probing")
    ap.add_argument("--limit", type=int, help="with --add: at most this many new boards (most tri-state, then most US postings first)")
    ap.add_argument("names", nargs="*")
    ap.add_argument("--names", dest="names_file")
    ap.add_argument("--simplify", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "data", "board-candidates.json"))
    ap.add_argument("--min-us", type=int, default=5)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--resume", default=os.path.join(HERE, "data", "board-probed.json"),
                    help="file of (system, board) pairs already probed: those probed in the last 30 days are skipped ('' to probe all)")
    a = ap.parse_args()
    if a.add:
        n = add_reviewed(a.add, a.min_us, J.BOARDS_FILE, a.limit)
        print("added %d boards to %s" % (n, J.BOARDS_FILE))
        return
    probes = {}                                   # (kind, token) -> company name it was tried for
    names = list(a.names)
    if a.names_file:
        with open(a.names_file, encoding="utf-8") as f:
            names += [l.split("#", 1)[0].strip() for l in f if l.split("#", 1)[0].strip()]
    if a.simplify:                                  # exact boards first: nothing is guessed
        for k, v in simplify_boards().items():
            probes.setdefault(k, v)
    for n in names:
        for s in slugs(n):
            for kind in ("greenhouse", "lever", "ashby", "smartrecruiters", "workable") + (("icims",) if "-" not in s else ()):
                probes.setdefault((kind, s.lower()), n)
    known = {(k, t.lower()) for k, t, _ in J.SOURCES}
    done = {}
    if a.resume:
        try:
            with open(a.resume, encoding="utf-8") as f:
                done = json.load(f)
        except (OSError, ValueError):
            done = {}
        cutoff = time.time() - 30 * 86400
        before = len(probes)
        probes = {k: v for k, v in probes.items() if done.get("%s|%s" % k, 0) < cutoff}
        print("resuming: %d of %d pairs were probed in the last 30 days and are skipped" % (before - len(probes), before), flush=True)
    print("probing %d (system, board) pairs for %d names%s" % (len(probes), len(names), " and the Simplify lists" if a.simplify else ""), flush=True)

    def one(item):
        (kind, token), company = item
        try:
            c = count(kind, token)
        except urllib.error.HTTPError as e:
            return None if e.code in (404, 410, 400) else {"kind": kind, "token": token, "for": company, "error": "HTTP %d" % e.code}
        except Exception as e:
            return {"kind": kind, "token": token, "for": company, "error": str(e)[:80]}
        if not c:
            return None
        total, us, tri, size, name = c[:5]
        row = {"kind": kind, "token": token, "for": company, "name": J._clean_company(name, company) or company, "total": total, "us": us,
               "tri": tri, "bytes": size, "known": (kind, token.lower()) in known}
        if kind == "icims":                              # added as an employer's careers site, read from its sitemap and pages
            row.update(kind="careerpage", sitemap=c[5], known=("careerpage", token.lower()) in known)
        return row

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        rows = [r for r in ex.map(one, probes.items()) if r]
    if a.resume:
        now = time.time()
        failed = {(r["kind"] if r["kind"] != "careerpage" else "icims", r["token"]) for r in rows if "error" in r}
        done.update({"%s|%s" % k: now for k in probes if k not in failed})        # an error (429, time-out) is tried again next run
        with open(a.resume, "w", encoding="utf-8", newline="\n") as f:
            json.dump(done, f)
    found = [r for r in rows if "error" not in r]
    keep = sorted([r for r in found if r["us"] >= a.min_us], key=lambda r: (-r["tri"], -r["us"]))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"checked": time.strftime("%Y-%m-%d %H:%M"), "probed": len(probes), "found": len(found), "min_us": a.min_us,
                   "candidates": keep, "errors": [r for r in rows if "error" in r][:200]}, f, indent=1)
    new = [r for r in keep if not r["known"]]
    print("%d boards found (%d with %d+ US jobs, %d not in the app yet) in %.0f s; review file: %s" % (len(found), len(keep), a.min_us, len(new), time.time() - t0, a.out))
    for r in new[:40]:
        print("  %-16s %-36s total=%-5d us=%-5d tri=%-4d %s" % (r["kind"], r["token"], r["total"], r["us"], r["tri"], r["name"]))


if __name__ == "__main__":
    main()
