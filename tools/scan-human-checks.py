#!/usr/bin/env python3
"""Human-check scan: for every source, look at a sample of the pages a person applies on and record whether a human check (a captcha or a
challenge page) is there, and what kind of page the application is. The result is human-checks.json (at the repository root), which the server
reads to label each job's route ("Ready, one tap" where a check is likely) and to show on the owner health page (/api/feed-health).

What it does, and what it never does:
- one plain GET per page (no login, no form filled, no button pressed, no script run, no cookie kept), as UAplyApplyCheck with a link back to
  uaply.net; a check that is found is only recorded: it is never solved, bypassed or set off on purpose, and a page that answers with a
  challenge is not asked again;
- robots.txt of every host is honoured, its crawl delay too, and every redirect is checked against it before it is followed;
- polite limits per host (HOSTS below), at most 3 attempts per page, and a source whose pages fail 3 times is stopped and marked unknown;
- it reads the job list it is given (a saved /api/jobs answer, or a running server's /api/jobs) and removes nothing.

Usage: python -I tools/scan-human-checks.py JOBS.json|http://host:port [--minutes 28] [--per-source 20] [--out human-checks.json]
       [--report report.json] [--only greenhouse,lever]
"""
import argparse
import collections
import datetime
import html
import http.client
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jobs_api import RobotsTxt  # noqa: E402  (robots.txt with * and $, longest rule first)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (compatible; UAplyApplyCheck/1.0; +https://uaply.net)"
UA_TOKEN = "UAplyApplyCheck"          # the name robots.txt rules are matched against
TIMEOUT = 20
MAX_BYTES = 4 << 20                   # at most 4 MB of a page is read (after gzip)
ATTEMPTS = 3

# ---------- what a page shows ----------
# A captcha the page loads or is set up with (most run on submit, unseen unless the vendor doubts the visitor). Only a script, a widget or a
# configured site key counts: a style rule (.grecaptcha-badge) or a switched-off flag ("recaptcha":false) does not.
CAPTCHAS = {
    "recaptcha": re.compile(r"(?:google\.com|recaptcha\.net)/recaptcha/(?:api|enterprise)\.js|class=[\"'][^\"']*\bg-recaptcha\b"
                            r"|grecaptcha\.(?:execute|render|ready)\(|recaptcha[A-Za-z_]*(?:site_?key|_key)[\"']?\s*[:=]\s*[\"']6L"
                            r"|data-sitekey=[\"']6L", re.I),
    "hcaptcha": re.compile(r"hcaptcha\.com/1/(?:secure-)?api\.js|class=[\"'][^\"']*\bh-captcha\b|data-hcaptcha", re.I),
    "turnstile": re.compile(r"src=[\"']https://challenges\.cloudflare\.com/turnstile/|class=[\"'][^\"']*\bcf-turnstile\b"
                            r"|turnstile[A-Za-z_]*site_?key[\"']?\s*[:=]\s*[\"']0x|turnstile_captcha_enabled[\"']?\s*:\s*true", re.I),
    "arkose": re.compile(r"arkoselabs\.com|funcaptcha", re.I),
    "other": re.compile(r"geetest\.com|friendlycaptcha|frc-captcha|mtcaptcha", re.I),
}
# A challenge page in place of the page itself (Cloudflare, DataDome, PerimeterX, Imperva, or a plain "verify you are human").
WALL_RE = re.compile(r"<title>\s*(?:just a moment|attention required|please wait|security check|pardon our interruption)"
                     r"|cf_chl_opt|cf-challenge|challenge-platform/h/[a-z]/(?:orchestrate|jsch)|geo\.captcha-delivery\.com"
                     r"|px-captcha|_pxCaptcha|_Incapsula_Resource|verify (?:that )?you are (?:a )?human|are you a robot"
                     r"|checking (?:your browser|if the site connection is secure)", re.I)
# Bot-detection scripts that run quietly and show nothing to a person by themselves: recorded, not counted as a human check.
QUIET_RE = re.compile(r"/cdn-cgi/challenge-platform/scripts/|ct\.captcha-delivery\.com/c\.js|perimeterx\.net|px-cdn\.net|/akam/1\d/", re.I)
FIELD_RE = re.compile(r"<(?:input|select|textarea)\b", re.I)
A_RE = re.compile(r"<a\b([^>]*)>(.{0,300}?)</a>", re.I | re.S)
HREF_RE = re.compile(r"href=[\"']([^\"']+)[\"']", re.I)
APPLY_WORD = re.compile(r"\bapply\b|applyonline|apply[-_]?button|apply[-_]?now|mode=apply", re.I)
NOT_APPLY = re.compile(r"linkedin|indeed|refer|alert|sign ?up for|newsletter|similar jobs|how to apply", re.I)
SIGN_IN = re.compile(r"/(?:login|signin|sign-in|logon|account/create|register)\b", re.I)

SYSTEMS = (("greenhouse", ("greenhouse.io",)), ("lever", ("lever.co",)), ("ashby", ("ashbyhq.com",)),
           ("smartrecruiters", ("smartrecruiters.com",)), ("workable", ("workable.com",)), ("icims", ("icims.com",)),
           ("workday", ("myworkdayjobs.com", "myworkdaysite.com")), ("taleo", ("taleo.net",)), ("successfactors", ("successfactors.com", "sapsf.com")),
           ("jobvite", ("jobvite.com",)), ("bamboohr", ("bamboohr.com",)), ("paylocity", ("paylocity.com",)), ("adp", ("adp.com",)),
           ("ukg", ("ultipro.com", "ukg.net")), ("oracle", ("oraclecloud.com",)), ("breezy", ("breezy.hr",)), ("jazzhr", ("applytojob.com",)))


def site_of(url):
    """The hiring system a page belongs to (greenhouse, icims, ...), else its registrable domain (example.com)."""
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    for name, ends in SYSTEMS:
        if any(host == e or host.endswith("." + e) for e in ends):
            return name
    parts = host.split(".")
    return ".".join(parts[-3:] if len(parts) > 2 and len(parts[-1]) == 2 and parts[-2] in ("co", "com", "org", "gov", "ac") else parts[-2:])


def classify(status, start_url, final_url, body):
    """One page as found: {status, check (True / False / None when it could not be seen), kinds, wall, quiet, formKind}."""
    wall = bool(WALL_RE.search(body)) or (status in (403, 429) and "captcha-delivery.com" in body)
    kinds = sorted(k for k, rx in CAPTCHAS.items() if rx.search(body))
    quiet = bool(QUIET_RE.search(body))
    if wall:
        check, form = True, "unknown"
    elif status >= 400:
        check, form = None, "unknown"                 # refused or broken without a challenge: nothing can be said
    else:
        check = bool(kinds)
        i = body.lower().find("<form")
        fields = i >= 0 and len(FIELD_RE.findall(body, i)) >= 3
        if site_of(final_url) != site_of(start_url):
            form = "redirect"
            if not kinds:
                check = None              # another system's page (its form is often added by a script): whether it checks cannot be seen
        elif fields:
            form = "html-form"
        elif "<script" in body.lower():
            form = "js-app"
        else:
            form = "unknown"
    return {"status": status, "check": check, "kinds": (["wall"] if wall else []) + kinds, "quiet": quiet, "formKind": form}


def apply_link(body, base):
    """The page's link to its application (the Apply button), or None."""
    best = None
    for m in A_RE.finditer(body):
        attrs, text = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        h = HREF_RE.search(attrs)
        if not h:
            continue
        href = html.unescape(h.group(1)).strip()
        # "apply" in the button's words, class or title, or in the link's path (not its query: a company's own site linked with
        # utm_campaign=apply is not the application)
        if not (APPLY_WORD.search(HREF_RE.sub(" ", attrs) + " " + text) or APPLY_WORD.search(urllib.parse.urlsplit(href).path)):
            continue
        if NOT_APPLY.search(text + " " + href):
            continue
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        url = urllib.parse.urljoin(base, href)
        if url.split("#")[0] != base.split("#")[0]:
            if re.search(r"\bapply\b", text, re.I):
                return url                            # a link that says Apply
            best = best or url
    return best


def apply_url(job):
    """Where a person applies for this job: the hiring system's own application page, else the job's page (its Apply link is followed)."""
    a = job.get("ats") or {}
    k, b, i, q = a.get("kind"), a.get("board"), a.get("id"), urllib.parse.quote
    if k and b and i:
        if k == "greenhouse":            # the form is on the job's page (an employer's own site embeds this same form)
            return "https://job-boards.greenhouse.io/%s/jobs/%s" % (q(b), q(i)), False
        if k == "lever":
            return "https://jobs.lever.co/%s/%s/apply" % (q(b), q(i)), False
        if k == "ashby":
            return "https://jobs.ashbyhq.com/%s/%s/application" % (q(b), q(i)), False
        if k == "smartrecruiters":       # the "I'm interested" button opens this page
            return "https://jobs.smartrecruiters.com/oneclick-ui/company/%s/publication/%s?dcr_ci=%s" % (q(b), q(i), q(b)), False
        if k == "workable":
            return "https://apply.workable.com/%s/j/%s/apply/" % (q(b), q(i)), False
    return from_url(job.get("url") or "")


def from_url(url):
    """(application page, follow its Apply link?) for a job's own address."""
    p = urllib.parse.urlsplit(url)
    host, path = (p.hostname or "").lower(), p.path.rstrip("/")
    seg = [s for s in path.split("/") if s]
    if host == "jobs.lever.co" and len(seg) == 2:
        return "https://jobs.lever.co/%s/%s/apply" % tuple(seg), False
    if host == "jobs.ashbyhq.com" and len(seg) == 2:
        return "https://jobs.ashbyhq.com/%s/%s/application" % tuple(seg), False
    if host == "apply.workable.com" and len(seg) >= 3 and seg[-2] == "j":
        return "https://apply.workable.com%s/apply/" % path, False
    if host.endswith("greenhouse.io") and "jobs" in seg:
        return url, False
    return url, True


def source_key(job, cp_hosts):
    """The source a job came from, as the health page names it (kind/token, or the kind for a feed that mixes many employers)."""
    a = job.get("ats")
    if a and a.get("kind") in ("greenhouse", "lever", "ashby", "smartrecruiters", "workable") and a.get("board"):
        return "%s/%s" % (a["kind"], a["board"])
    via = job.get("via") or ""
    if via.endswith(" careers site"):
        host = (urllib.parse.urlsplit(job.get("url") or "").hostname or "").lower()
        return "careerpage/" + cp_hosts.get(host, host)
    feeds = {"Jobicy": "jobicy", "The Muse": "muse", "Himalayas": "himalayas", "Remote OK": "remoteok", "Remotive": "remotive",
             "USAJOBS": "usajobs", "CareerOneStop": "careeronestop"}
    if via in feeds:
        return feeds[via]
    if " on " in via:
        return "simplify"                         # Simplify's lists: each row links to the employer's own posting
    return "other"


# ---------- polite fetching ----------
# per hiring system: (requests at once, seconds between two requests to the host). Any other host: one at a time, 2 s apart (as the careers-site
# reader). A robots.txt crawl delay makes it one at a time and at least that far apart.
HOSTS = {"greenhouse": (6, 0.1), "ashby": (6, 0.1), "lever": (3, 0.2), "smartrecruiters": (3, 0.3), "workable": (2, 0.6)}
OTHER = (1, 2.0)


class Lane:
    def __init__(self, parallel, gap):
        self.sem, self.gap, self.lock, self.next_at = threading.Semaphore(parallel), gap, threading.Lock(), 0.0

    def turn(self):
        with self.lock:
            now = time.monotonic()
            at = max(now, self.next_at)
            self.next_at = at + self.gap
        if at > now:
            time.sleep(at - now)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None                             # every redirect is checked against robots.txt here before it is followed


OPENER = urllib.request.build_opener(NoRedirect)
FOLLOW = urllib.request.build_opener()
_lanes, _robots, _guard = {}, {}, threading.Lock()
REFUSED_STOP = 10                     # refusals in a row (HTTP 401/403 with no challenge) after which a host is not asked again in this run
_refused = {}                         # host -> refusals in a row


def _public(url):
    p = urllib.parse.urlsplit(url)
    host = (p.hostname or "").lower()
    return (p.scheme in ("https", "http") and "." in host and not p.username and not p.port and host != "localhost"
            and not re.fullmatch(r"[\d.]+|\[?[0-9a-f:]+\]?", host) and not host.endswith((".local", ".internal", ".localhost")))


def _raw(url, follow=False):
    """(status, headers, text) of one plain GET, no redirect followed (robots.txt: followed). Raises OSError on a network failure."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                                               "Accept-Encoding": "gzip", "Accept-Language": "en-US,en;q=0.8"})
    try:
        r = (FOLLOW if follow else OPENER).open(req, timeout=TIMEOUT)
        status = r.status
    except urllib.error.HTTPError as e:
        r, status = e, e.code
    try:
        gz = (r.headers.get("Content-Encoding") or "").lower() == "gzip"
        z = zlib.decompressobj(31) if gz else None
        out, size = [], 0
        while size < MAX_BYTES:
            chunk = r.read(65536)
            if not chunk:
                break
            if z:
                chunk = z.decompress(chunk, MAX_BYTES - size)
            out.append(chunk)
            size += len(chunk)
        return status, r.headers, b"".join(out).decode("utf-8", "replace")
    finally:
        r.close()


def _lane(host):
    with _guard:
        if host not in _lanes:
            sysname = site_of("https://%s/" % host)
            par, gap = HOSTS.get(sysname, OTHER)
            rp = _robots.get(host)
            delay = rp.crawl_delay(UA_TOKEN) if rp else None
            if delay:
                par, gap = 1, max(gap, float(delay))
            _lanes[host] = Lane(par, gap)
        return _lanes[host]


def _robots_for(host):
    """The host's robots.txt (read once). Unreachable or refused (401/403): nothing is read from that host."""
    with _guard:
        if host in _robots:
            return _robots[host]
    rp = RobotsTxt()
    try:
        status, _, text = _raw("https://%s/robots.txt" % host, follow=True)
        if status in (401, 403) or status >= 500:
            rp.disallow_all = True
        elif status < 300:
            rp.parse(text.splitlines())
        else:
            rp.allow_all = True
    except (OSError, ValueError, http.client.HTTPException):
        rp.disallow_all = True
    with _guard:
        _robots.setdefault(host, rp)
        return _robots[host]


def fetch(url, deadline):
    """A plain GET of a page, following up to 5 redirects that robots.txt allows. {url, status, text} or {url, robots: True} when robots.txt
    closes the page (or a redirect's target), {url, failed: reason} after ATTEMPTS failures."""
    for _ in range(6):
        if not _public(url):
            return {"url": url, "failed": "not a public address"}
        host = urllib.parse.urlsplit(url).hostname.lower()
        rp = _robots_for(host)
        if not rp.can_fetch(UA_TOKEN, url):
            return {"url": url, "robots": True}
        if _refused.get(host, 0) >= REFUSED_STOP:
            return {"url": url, "failed": "the host refused this scan"}     # it said no 10 times in a row: it is left alone
        lane, err = _lane(host), ""
        for attempt in range(ATTEMPTS):
            if time.monotonic() > deadline:
                return {"url": url, "failed": "out of time"}
            with lane.sem:
                lane.turn()
                try:
                    status, headers, text = _raw(url)
                except (OSError, ValueError, http.client.HTTPException) as e:
                    status, err = None, type(e).__name__
            if status is None:
                time.sleep(2 * (attempt + 1))
                continue
            if status in (429, 502, 503, 504) and not WALL_RE.search(text) and "captcha-delivery.com" not in text:
                err = "HTTP %d" % status                # busy: wait as asked (at most 30 s) and ask again
                try:
                    wait = min(30.0, float(headers.get("Retry-After") or 0)) or 3.0 * (attempt + 1)
                except ValueError:
                    wait = 3.0 * (attempt + 1)
                time.sleep(wait)
                continue
            break
        else:
            return {"url": url, "failed": err}
        with _guard:
            refused = status in (401, 403) and not WALL_RE.search(text) and "captcha-delivery.com" not in text
            _refused[host] = _refused.get(host, 0) + 1 if refused else 0
        if status in (301, 302, 303, 307, 308) and headers.get("Location"):
            url = urllib.parse.urljoin(url, headers["Location"])
            continue
        return {"url": url, "status": status, "text": text}
    return {"url": url, "failed": "too many redirects"}


AGGREGATORS = ("jobicy", "muse", "himalayas", "remoteok", "remotive")     # boards that send a person on to the employer's own page
IFRAME_RE = re.compile(r"<iframe\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.I)


def scan_job(job, deadline, kind=""):
    """One posting's application, as a person would reach it: the page, and for a job page its Apply link (one hop; a frame of the same
    site on the way, as iCIMS shows its job pages)."""
    start, follow = apply_url(job)
    r = fetch(start, deadline)
    if r.get("failed"):
        return None
    if r.get("robots"):
        return {"status": 0, "check": None, "kinds": [], "quiet": False, "formKind": "unknown", "note": "robots.txt closes the page"}
    page = classify(r["status"], start, r["url"], r["text"])
    if page["check"] is None and r["status"] >= 400:
        return dict(page, note="refused (HTTP %d, no challenge): not a human check" % r["status"])
    if not follow or page["check"] is None or page["kinds"]:
        return page
    base, text = r["url"], r["text"]
    nxt = apply_link(text, base)
    if not nxt:
        frames = [urllib.parse.urljoin(base, html.unescape(f)) for f in IFRAME_RE.findall(text)]
        src = next((f for f in frames if site_of(f) == site_of(base) and f.split("#")[0] != base), "")
        if src:
            r1 = fetch(src, deadline)
            if r1.get("text") is not None:
                p1 = classify(r1["status"], start, r1["url"], r1["text"])
                if p1["check"] is None or p1["kinds"]:
                    return p1
                page, base, text = p1, r1["url"], r1["text"]
                nxt = apply_link(text, base)
    if nxt and kind in AGGREGATORS and site_of(nxt) == site_of(base):
        nxt = None                                    # the board's own button, not the employer's page
    if not nxt:
        if kind in AGGREGATORS:
            return dict(page, check=None, formKind="redirect", note="the employer's page opens from the board's own button (a script)")
        if page["formKind"] == "js-app":           # a job page whose Apply step a script draws (Workday): that step cannot be seen
            return dict(page, check=None, note="the apply step is drawn by a script (not seen by a plain GET)")
        return page
    to, _ = from_url(nxt)
    r2 = fetch(to, deadline)
    if r2.get("robots"):
        sign_in = bool(SIGN_IN.search(urllib.parse.urlsplit(r2["url"]).path))
        return dict(page, check=None, formKind="sign-in" if sign_in else "redirect",
                    note="the apply step is closed to robots" + (" (a sign-in page)" if sign_in else ""))
    if r2.get("failed"):
        return dict(page, check=None, note="the apply step did not answer")
    p2 = classify(r2["status"], base, r2["url"], r2["text"])
    if SIGN_IN.search(urllib.parse.urlsplit(r2["url"]).path) and p2["formKind"] != "redirect":
        p2["formKind"] = "sign-in"
    elif site_of(r2["url"]) != site_of(start) and p2["check"] is not None:
        p2["formKind"] = "redirect"
    return dict(p2, quiet=p2["quiet"] or page["quiet"], to=site_of(r2["url"]))


def summarize(pages):
    """A source's result from its sampled pages: humanCheck none / sometimes / always / unknown, the commonest formKind, counts."""
    seen = [p for p in pages if p and p.get("check") is not None]
    k = sum(1 for p in seen if p["check"])
    hc = "unknown" if not seen else "none" if not k else "always" if k == len(seen) else "sometimes"
    forms = collections.Counter(p["formKind"] for p in pages if p and p.get("formKind") != "unknown")
    kinds = collections.Counter(x for p in seen for x in p["kinds"])
    to = collections.Counter(p["to"] for p in pages if p and p.get("to"))
    notes = collections.Counter(p["note"] for p in pages if p and p.get("note"))
    out = {"humanCheck": hc, "formKind": forms.most_common(1)[0][0] if forms else "unknown", "pages": len(seen), "withCheck": k,
           "kinds": dict(kinds), "quiet": sum(1 for p in pages if p and p.get("quiet")), "failed": sum(1 for p in pages if not p)}
    if to:
        out["to"] = dict(to.most_common(5))
    if notes:
        out["note"] = notes.most_common(1)[0][0]
    return out


def sample(jobs, n):
    """n postings spread over the source's list (all of them when it has fewer)."""
    if len(jobs) <= n:
        return list(jobs)
    step = len(jobs) / n
    return [jobs[int(i * step)] for i in range(n)]


def tables(results):
    """The file's contents from every source's result: by hiring system (sources in each bucket, the jobs they hold, pages, kinds found,
    form kinds) and the share of all jobs in each bucket."""
    systems = collections.OrderedDict()
    for key, r in sorted(results.items(), key=lambda kv: kv[1].get("system") or ""):
        g = r.get("system") or key.split("/")[0]
        s = systems.setdefault(g, {"sources": 0, "jobs": 0, "none": 0, "sometimes": 0, "always": 0, "unknown": 0,
                                   "jobsBy": {"none": 0, "sometimes": 0, "always": 0, "unknown": 0}, "pages": 0, "kinds": collections.Counter(),
                                   "formKind": collections.Counter(), "perSource": r.get("perSource", 0)})
        n = int(r.get("jobs") or 0)
        s["sources"] += 1
        s["jobs"] += n
        s[r["humanCheck"]] += 1
        s["jobsBy"][r["humanCheck"]] += n
        s["pages"] += r["pages"]
        s["kinds"].update(r["kinds"])
        s["formKind"][r["formKind"]] += 1
    for s in systems.values():
        s["kinds"], s["formKind"] = dict(s["kinds"]), dict(s["formKind"])
    share = collections.Counter()
    for r in results.values():
        share[r["humanCheck"]] += int(r.get("jobs") or 0)
    return {"note": "Human-check scan (tools/scan-human-checks.py): a sample of each source's application pages, one plain GET each, robots.txt "
                    "honoured. humanCheck: none / sometimes / always / unknown over the pages seen; formKind: html-form, js-app, redirect "
                    "(to another system), sign-in. A check is only recorded, never solved or bypassed; no job is removed because of one.",
            "ua": UA, "jobs": sum(share.values()), "share": {k: share[k] for k in ("none", "sometimes", "always", "unknown")},
            "systems": systems, "sources": dict(sorted(results.items()))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs")
    ap.add_argument("--minutes", type=float, default=28.0)
    ap.add_argument("--per-source", type=int, default=20)
    ap.add_argument("--out", default=os.path.join(ROOT, "human-checks.json"))
    ap.add_argument("--report", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--merge", action="store_true", help="keep the results already in --out for sources not in this job list")
    ap.add_argument("--skip-known", action="store_true", help="with --merge: scan only the sources --out has no result for yet")
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    deadline = t0 + a.minutes * 60
    if a.jobs.startswith("http"):
        with urllib.request.urlopen(a.jobs.rstrip("/") + "/api/jobs", timeout=600) as r:
            data = json.loads(r.read())
    else:
        with open(a.jobs, encoding="utf-8") as f:
            data = json.load(f)
    jobs = data["jobs"] if isinstance(data, dict) else data
    with open(os.path.join(ROOT, "job-boards.json"), encoding="utf-8") as f:
        rows = json.load(f)["boards"]
    cp_hosts = {(urllib.parse.urlsplit(r["sitemap"]).hostname or "").lower(): r["token"] for r in rows if r.get("kind") == "careerpage" and r.get("sitemap")}
    by_src = collections.OrderedDict()
    for j in jobs:
        if j.get("instant") or j.get("apply") == "direct" or not j.get("url"):
            continue                                       # applied to in UAply itself: no page to look at
        by_src.setdefault(source_key(j, cp_hosts), []).append(j)
    if a.merge and a.skip_known and os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as f:
            have = json.load(f).get("sources") or {}
        by_src = collections.OrderedDict((k, v) for k, v in by_src.items() if k not in have or have[k].get("humanCheck") == "unknown"
                                         and "not reached" in (have[k].get("note") or ""))
    only = set(x for x in a.only.split(",") if x)
    if only:
        by_src = collections.OrderedDict((k, v) for k, v in by_src.items() if k.split("/")[0] in only)
    # one group of workers per hiring system, sized to its host limit, so a slow host never holds up the others
    groups = collections.defaultdict(list)
    for key, js in by_src.items():
        groups[site_of(apply_url(js[0])[0]) if key.split("/")[0] in HOSTS else "other"].append(key)
    budget = max(60.0, (deadline - time.monotonic()) * 0.9)
    quota = {}
    for g, keys in groups.items():
        par, gap = HOSTS.get(g, OTHER)
        if g in HOSTS:
            host = urllib.parse.urlsplit(apply_url(by_src[keys[0]][0])[0]).hostname
            rp = _robots_for(host)
            delay = rp.crawl_delay(UA_TOKEN)
            if delay:
                par, gap = 1, max(gap, float(delay))
            per = max(gap, 0.45 / par)                    # seconds per request on that host, at best
            quota[g] = max(3, min(a.per_source, int(budget / per / len(keys))))
        else:
            quota[g] = a.per_source                       # many hosts, each with its own lane
    results, lock = {}, threading.Lock()
    sampled = datetime.date.today().isoformat()
    ckpt, before = a.out + ".partial", 0.0
    try:                                               # a scan stopped earlier today: its finished sources are kept, not read again
        with open(ckpt, encoding="utf-8") as f:
            saved = json.load(f)
        if saved.get("sampled") == sampled:
            results.update(saved.get("sources") or {})
            before = float(saved.get("minutes") or 0)
            for g in groups:
                groups[g] = [k for k in groups[g] if k not in results]
            print("picking up a stopped scan: %d sources already done (%.1f min)" % (len(results), before), flush=True)
    except (OSError, ValueError):
        pass

    def describe(key):                                 # the source's hiring system, its jobs and the sample size of its system
        js = by_src[key]
        g = site_of(apply_url(js[0])[0]) if key.split("/")[0] in HOSTS else (key.split("/")[0] + ":" + site_of(apply_url(js[0])[0]))
        return {"system": g, "jobs": len(js), "perSource": quota.get(g if g in quota else "other", a.per_source)}

    def checkpoint():
        with lock:
            snap = dict(results)
        tmp = ckpt + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"sampled": sampled, "minutes": round(before + (time.monotonic() - t0) / 60, 1), "sources": snap}, f)
        os.replace(tmp, ckpt)

    def run(g, keys):
        while True:
            with lock:
                if not keys:
                    return
                key = keys.pop(0)
            pages, fails = [], 0
            for j in sample(by_src[key], quota[g]):
                if time.monotonic() > deadline:
                    break
                p = scan_job(j, deadline, key.split("/")[0])
                if p is None and time.monotonic() > deadline:
                    break                                 # out of time, not a failure of the source
                pages.append(p)
                fails += p is None
                if fails >= ATTEMPTS:
                    break                                 # 3 pages that never answered: this source is stopped (unknown unless some were seen)
            s = summarize(pages)
            s["sampled"] = sampled
            if fails >= ATTEMPTS and not s["pages"]:
                s["note"] = s.get("note") or "stopped after %d failures" % ATTEMPTS
            s.update(describe(key))
            with lock:
                results[key] = s

    threads = []
    for g, keys in groups.items():
        par = HOSTS.get(g, (8, 0))[0] if g in HOSTS else 12
        keys = list(keys)
        for _ in range(par):
            th = threading.Thread(target=run, args=(g, keys), daemon=True)
            th.start()
            threads.append(th)
    last = 0
    while any(th.is_alive() for th in threads):
        time.sleep(1)
        if time.monotonic() - last > 60:
            last = time.monotonic()
            print("%5.1f min  %d of %d sources done" % (before + (last - t0) / 60, len(results), len(by_src)), flush=True)
            checkpoint()
        if time.monotonic() > deadline + 60:
            break
    for key in by_src:
        results.setdefault(key, {"humanCheck": "unknown", "formKind": "unknown", "pages": 0, "withCheck": 0, "kinds": {}, "quiet": 0,
                                 "failed": 0, "sampled": sampled, "note": "not reached in the time allowed"})
    for key in by_src:                                # each source's hiring system and job count, so a later --merge can add up the tables
        results[key].update(describe(key))
    if a.merge and os.path.exists(a.out):             # sources scanned before and not in this job list keep their results
        with open(a.out, encoding="utf-8") as f:
            old = json.load(f).get("sources") or {}
        results = dict(old, **results)
    out = tables(results)
    out.update(sampled=sampled, minutes=round(before + (time.monotonic() - t0) / 60, 1))
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, sort_keys=False)
        f.write("\n")
    try:
        os.remove(ckpt)
    except OSError:
        pass
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump({"quota": quota, "systems": out["systems"], "share": out["share"], "minutes": out["minutes"]}, f, indent=1)
    print("done in %.1f min: %d sources, %d jobs; jobs by bucket %s" % (out["minutes"], len(results), out["jobs"], out["share"]))
    for g, s in out["systems"].items():
        print("  %-28s sources %4d  none %4d  sometimes %3d  always %4d  unknown %3d  jobs %5d  pages %5d  %s %s" % (
            g, s["sources"], s["none"], s["sometimes"], s["always"], s["unknown"], s["jobs"], s["pages"], s["kinds"], s["formKind"]))
    return out


if __name__ == "__main__":
    socket.setdefaulttimeout(TIMEOUT)
    main()
