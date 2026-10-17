"""Job ingestion back end for the sandbox and dev instances (not used by prod).

How real job apps get postings, and what this does:
  * Employers publish openings in an applicant tracking system (ATS). Greenhouse, Lever and Ashby expose public,
    read-only job-board APIs so third parties can list those openings. Aggregators keep a list of company board
    names, poll those endpoints, normalize the fields, de-duplicate, and link applicants back to the employer.
  * Indeed and ZipRecruiter do not offer an open API for reading their listings (partner programs only, and Indeed's
    terms forbid keeping copies), so they are NOT used here.
  * Remotive publishes a free remote-jobs feed on the condition that listings link back to Remotive and name it as
    the source, and that it is polled at most ~4 times a day. Both are respected below.

LEGAL STATUS OF EACH SOURCE (checked October 2026; this is not legal advice, have a lawyer confirm before launch):
  * Partner employers (uaply-partners.json): AUTHORIZED. The employer gave us the posting and agreed to receive
    applications. This is the only source whose applications UAply sends to a person.
  * Remotive: its terms call using listings "to collect signups or email addresses" a breach, and UAply collects
    emails. Never enabled by default; do not enable without written permission.
  * Jobicy: must credit Jobicy and send applicants to the original job URL, so it is LINK-OUT ONLY.
  * The Muse: terms not found. Unverified; do not enable until verified in writing.
  * Greenhouse, Lever, Ashby public boards: meant for employers' careers pages; no terms found that cover third-party
    aggregation. Unverified, LINK-OUT ONLY.
  * USAJOBS (the federal government's own API, read October 16, 2026): its terms let public data be copied, stored and
    republished, commercial use included, without OPM approval; credit and a link to the official announcement are asked
    for, and nobody may be told an application was sent when it was not. LINK-OUT ONLY, credited "via USAJOBS". Needs a
    free key (feed_keys.usajobs); without one the source is skipped with the status "no key".
  * SmartRecruiters public Posting API (City of Philadelphia): public postings of a public body, no key, no published
    terms for readers. LINK-OUT ONLY, credited "City of Philadelphia on SmartRecruiters".
  Third-party feeds are OFF unless the owner lists them under "feeds" in uaply-config.json. Jobs from a feed are never
  emailed to anyone (the recruiter address is dropped); swiping right only opens the employer's own page.

get_jobs() returns {"fetched_at", "sources", "jobs"} where each job already matches the shape the app expects.
"""
import datetime
import hashlib
import html
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import ats_api

ROOT = os.path.dirname(os.path.abspath(__file__))
UA = "UAplyDev/0.1 (local prototype)"
DEFAULT_TTL = 30 * 60
TTL = {"remotive": 6 * 3600,          # Remotive allows roughly 4 requests a day
       "jobicy": 3600,                # Jobicy asks for at most one sync pass an hour
       "usajobs": 3 * 3600,           # federal postings change slowly; two searches every three hours
       "smartrecruiters": 3600}       # the City's list once an hour (each posting's description is read far less often, see SR_DESC_TTL)
PER_SOURCE = 14
STUDENT_PER_SOURCE = 10          # internships, co-ops and part-time roles are kept first so the student tabs are not empty
OTHER_PER_SOURCE = 6
# A public body's own list (the City, the federal government) is local and is kept whole up to this many postings, student roles first,
# instead of the 14 an employer board gets. SmartRecruiters is also read no further than this (so at most this many description reads).
KEEP = {"usajobs": 120, "smartrecruiters": 120}
SR_DESC_TTL = 24 * 3600          # a SmartRecruiters posting's description is read once, then again only after a day or when the posting is re-released

# (kind, board token, display name). Boards are the employer's own public careers feed.
SOURCES = [
    ("greenhouse", "discord", "Discord"),
    ("greenhouse", "dropbox", "Dropbox"),
    ("greenhouse", "duolingo", "Duolingo"),
    ("greenhouse", "squarespace", "Squarespace"),
    ("ashby", "webflow", "Webflow"),              # moved from Greenhouse (404 there since October 2026) to Ashby
    # employers whose own public boards carried internships when checked (October 2026)
    ("greenhouse", "waymo", "Waymo"),
    ("greenhouse", "coinbase", "Coinbase"),
    ("greenhouse", "robinhood", "Robinhood"),
    ("greenhouse", "lyft", "Lyft"),
    ("greenhouse", "stripe", "Stripe"),
    ("greenhouse", "databricks", "Databricks"),
    ("greenhouse", "pinterest", "Pinterest"),
    ("greenhouse", "figma", "Figma"),
    ("greenhouse", "datadog", "Datadog"),
    ("greenhouse", "verkada", "Verkada"),
    ("greenhouse", "samsara", "Samsara"),
    ("greenhouse", "roblox", "Roblox"),
    ("greenhouse", "block", "Block"),
    ("greenhouse", "cloudflare", "Cloudflare"),
    ("greenhouse", "scaleai", "Scale AI"),
    ("greenhouse", "affirm", "Affirm"),
    ("greenhouse", "imc", "IMC Trading"),
    ("lever", "spotify", "Spotify"),
    ("ashby", "linear", "Linear"),
    ("remotive", "software-dev", "Remotive"),
    ("jobicy", "engineering", "Jobicy"),      # credit Jobicy and link to its canonical job URL
    ("jobicy", "marketing", "Jobicy"),
    ("jobicy", "data-science", "Jobicy"),
    ("muse", "Internship", "The Muse"),       # The Muse public jobs API; links go to the posting on The Muse
    ("muse", "Entry Level", "The Muse"),
    ("smartrecruiters", "CityofPhiladelphia", "City of Philadelphia"),   # the City's own public SmartRecruiters postings (no key)
    ("usajobs", "philadelphia", "USAJOBS"),   # every federal posting within 25 miles of Philadelphia (needs feed_keys.usajobs)
    ("usajobs", "students", "USAJOBS"),       # the same area, only the Students and Recent graduates hiring paths (Pathways)
]
VIA = {"greenhouse": "%s on Greenhouse", "lever": "%s on Lever", "ashby": "%s on Ashby", "smartrecruiters": "%s on SmartRecruiters",
       "jobicy": "Jobicy", "muse": "The Muse", "usajobs": "USAJOBS", "remotive": "Remotive"}       # the short credit line each source's jobs carry
MULTI = ("jobicy", "muse", "usajobs")         # several feeds share one display name
# The two USAJOBS searches (documented at developer.usajobs.gov/api-reference/get-api-search; several values are joined with ';')
USAJOBS_QUERIES = {
    "philadelphia": {"LocationName": "Philadelphia, Pennsylvania", "Radius": "25", "ResultsPerPage": "500", "Fields": "Full"},
    "students": {"LocationName": "Philadelphia, Pennsylvania", "Radius": "25", "ResultsPerPage": "500", "Fields": "Full", "HiringPath": "student;graduates"},
}
USAJOBS_EMAIL = "uaplytechnologies@gmail.com"   # USAJOBS wants the email the key was requested with as the User-Agent (feed_keys.usajobs_email, else owner_copy, else this)

SKILLS = [
    ("JavaScript", r"javascript|\bjs\b"), ("TypeScript", r"typescript"), ("React", r"\breact(?:\.js|js)?\b"),
    ("Node", r"\bnode(?:\.js|js)?\b"), ("Python", r"\bpython\b"), ("Java", r"\bjava\b"), ("SQL", r"\bsql\b"),
    ("PostgreSQL", r"postgres(?:ql)?"), ("AWS", r"\baws\b|amazon web services"), ("Docker", r"\bdocker\b"),
    ("Kubernetes", r"kubernetes|\bk8s\b"), ("Terraform", r"terraform"), ("Figma", r"\bfigma\b"),
    ("Excel", r"\bexcel\b"), ("Tableau", r"\btableau\b"), ("Django", r"\bdjango\b"), ("CSS", r"\bcss\b"),
    ("HTML", r"\bhtml\b"), ("Testing", r"\btesting\b|unit tests?|test automation"), ("SEO", r"\bseo\b"),
    ("Copywriting", r"copywrit"), ("Analytics", r"\banalytics\b"), ("Hiring", r"recruit(?:ing|er|ment)\b"),
    ("User research", r"user research"), ("Prototyping", r"prototyp"), ("Design systems", r"design systems?"),
    ("Roadmapping", r"roadmap"), ("Budgeting", r"\bbudget"), ("PyTorch", r"pytorch"),
]
SKILL_RES = [(n, re.compile(p, re.I)) for n, p in SKILLS]
# "recruiting" appears in nearly every company's boilerplate (equal-opportunity text, privacy notices), so "Hiring" counts as a skill only for people roles
TITLE_GATED = {"Hiring": re.compile(r"recruit|talent|people|\bhr\b|human resources|staffing|sourcer|hiring", re.I)}
REMOTE_WORD = re.compile(r"^\W*remote\b(?:\s*[-–—:,/]\s*|\s*\()?", re.I)


def _place(loc, mode):
    """The place shown next to a job's work style. A remote job whose location already begins with "Remote" would read
    "Remote - USA  Remote" on the card, so that repeated word is dropped ("USA"; a bare "Remote" becomes "United States",
    which is what the US-only rule above guarantees)."""
    m = REMOTE_WORD.match(loc or "") if mode == "remote" else None
    if m:                                                    # only a place that starts with "Remote" is changed; anything else is left exactly as listed
        rest = (loc or "")[m.end():]
        if m.group(0).rstrip().endswith("("):               # "Remote (US)": the opening bracket went with the word, so its closing one goes too
            rest = rest.replace(")", "", 1)
        loc = rest.strip(" -–—:,/") or "United States"
    return loc or "Not listed"

STATES = "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
STATE_NAMES = ("Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|District of Columbia|Florida|Georgia|Hawaii|Idaho|Illinois|"
               "Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|"
               "New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|"
               "South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming")
US_RE = re.compile(r"United States|\bUSA\b|\bU\.S\.|\bUS\b|, (?:%s)\b|, (?:%s)\b|\b(?:San Francisco|New York|Seattle|Austin|Boston|Chicago|Denver|Los Angeles|Atlanta|Portland)\b" % ("|".join(STATES), STATE_NAMES))
FOREIGN_RE = re.compile(r"Germany|United Kingdom|\bUK\b|India|Canada|Ireland|France|Spain|Brazil|Mexico|Poland|Netherlands|Japan|Australia|New Zealand|\bANZ\b|Singapore|EMEA|APAC|Europe|LATAM|Latin America|Berlin|London|Dublin|Toronto|Vancouver|Montreal|Sydney|Amsterdam|Lisbon|Paris|Tokyo|Seoul|Hong Kong|Israel|Dubai|Philippines|Argentina|Colombia|Chile|Vietnam|Indonesia|Malaysia|Thailand|South Africa|Nigeria|Kenya|Egypt|Turkey|Romania|Ukraine|Czech|Portugal|Italy|Sweden|Norway|Denmark|Finland|Switzerland|Belgium|Austria", re.I)
EXPLICIT_US = re.compile(r"United States|\bUSA\b|\bU\.S\.|\bUS\b")


def _us_ok(loc, remote):
    """True when a posting can be done from the United States. A location is split on ';' and '|' (one posting can list
    several cities): any part that names the US, or is a US place with no foreign word, passes. A bare 'Remote' passes only
    when no foreign place is named. (', CA' is California; 'Toronto, ON, CA' is Canada and must not pass on that.)"""
    parts = [p for p in re.split(r"[;|]", loc) if p.strip()] or [loc]
    for p in parts:
        if EXPLICIT_US.search(p) or (US_RE.search(p) and not FOREIGN_RE.search(p)):
            return True
    return bool(remote and not FOREIGN_RE.search(loc))
SAL_RE = re.compile(r"\$\s?(\d{2,3}(?:,\d{3})+|\d{2,3}\s?[kK])\s*(?:-|–|—|to)\s*\$?\s*(\d{2,3}(?:,\d{3})+|\d{2,3}\s?[kK])")
YRS_RE = re.compile(r"(\d{1,2})\+?\s*(?:or more\s*)?(?:years|yrs)", re.I)

_cache = {}
_lock = threading.Lock()
_disk = {"loaded": False, "dirty": False}
hide_errors = False                # serve.py sets this on a hosted server: the public job list then says "unavailable right now" instead of a raw network error
DISK_MAX_AGE = 24 * 3600          # never trust a saved copy older than a day
CACHE_VERSION = 8                # raise this whenever the rules for keeping or classifying postings change: older saved copies are then ignored


def _cache_file():
    """Where the last good postings are kept, so a restart or a new deploy shows jobs at once instead of waiting
    for every employer board (UAPLY_DATA_DIR on a host, ./data on this computer; never committed)."""
    return os.path.join(os.environ.get("UAPLY_DATA_DIR") or os.path.join(ROOT, "data"), "jobs-cache.json")


def _load_disk():
    if _disk["loaded"]:
        return
    _disk["loaded"] = True
    try:
        with open(_cache_file(), encoding="utf-8") as f:
            saved = json.load(f)
        if not isinstance(saved, dict) or saved.pop("_version", None) != CACHE_VERSION:
            return
        now = time.time()
        with _lock:
            for key, v in saved.items():
                kind, token, name = key.split("|", 2)
                if isinstance(v, dict) and isinstance(v.get("jobs"), list) and now - float(v.get("at", 0)) < DISK_MAX_AGE:
                    _cache.setdefault((kind, token, name), {"at": float(v["at"]), "jobs": v["jobs"], "status": str(v.get("status", ""))})
    except Exception:
        pass


def _save_disk():
    if not _disk["dirty"]:
        return
    try:
        with _lock:
            snap = {"|".join(k): {"at": v["at"], "jobs": v["jobs"], "status": v["status"]} for k, v in _cache.items()}
            snap["_version"] = CACHE_VERSION
            _disk["dirty"] = False
        path = _cache_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snap, f)
        os.replace(tmp, path)
    except Exception as e:                      # jobs still work from memory; only a restart would have to wait for every feed again
        sys.stderr.write("[uaply] could not save the job cache: %s: %s\n" % (type(e).__name__, str(e)[:200]))


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA, "Accept": "application/json"}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


KEY_RE = re.compile(r"^[A-Za-z0-9+/=_.-]{16,200}$")      # what a feed's API key looks like (USAJOBS: about 44 letters, digits, + / =)


def feed_keys():
    """The job feeds' own API keys the owner pasted on the setup page ('feed_keys' in uaply-config.json, or in UAPLY_CONFIG_JSON on a
    host): {"usajobs": ..., "usajobs_email": ..., "muse": ...}. Only well-formed values are returned. These are secrets: never logged, never
    sent to a browser, never shown on a page (see _scrub)."""
    cfg = _cfg()
    k = cfg.get("feed_keys") if isinstance(cfg.get("feed_keys"), dict) else {}
    out = {n: k[n].strip() for n in ("usajobs", "muse") if isinstance(k.get(n), str) and KEY_RE.match(k[n].strip())}
    EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")   # one plain address (the module-level one was removed as unused)
    mail = next((m.strip() for m in (k.get("usajobs_email"), cfg.get("owner_copy")) if isinstance(m, str) and EMAIL_RE.fullmatch(m.strip())), "")
    out["usajobs_email"] = mail or USAJOBS_EMAIL
    return out


def _scrub(text):
    """Error text with every feed key taken out, so a key can never reach the server's log or the job list's status line."""
    for n in ("usajobs", "muse"):
        v = feed_keys().get(n)
        if v:
            text = text.replace(v, "[key]").replace(urllib.parse.quote(v, safe=""), "[key]")
    return text


ROLE_HEAD = re.compile(r"(?:About (?:the|this) (?:role|job|internship|position|opportunity|team)|The (?:role|opportunity|internship|position)|Role overview|"
                       r"Position summary|Job summary|Job description|Overview|What you.?ll (?:do|be doing)|Your role|In this role|Responsibilities)\b[:\s-]*", re.I)


def _role_summary(text, limit=650):
    """A short, readable description of the job for emails. Postings usually open with a paragraph about the company, so when the
    posting has a role section ("About the role", "What you'll do", ...) the summary starts there. It ends on a whole sentence."""
    t = text.strip()
    m = ROLE_HEAD.search(t, 0, 6000)
    if m and m.start() > 0:
        t = t[m.start():]
    if len(t) <= limit:
        return t
    cut = t[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:end + 1] if end > limit * 0.5 else cut.rsplit(" ", 1)[0] + "…")


def _text(s):
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()[:20000]


def _ts(v):
    """Posting date as epoch milliseconds (0 if the feed gives none or an unreadable one)."""
    try:
        if isinstance(v, (int, float)):
            return int(v if v > 1e11 else v * 1000)
        if isinstance(v, str) and v.strip():
            d = datetime.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=datetime.timezone.utc)
            return int(d.timestamp() * 1000)
    except Exception:
        pass
    return 0


# Benefits a posting mentions in its own text. A mention is not a guarantee, and silence is not "none": many
# postings simply do not list benefits, so the app treats these as "mentions", never as proof of absence.
PERK_RES = [
    ("health", re.compile(r"health(?:care)? (?:insurance|coverage|benefits|plans?)|medical (?:insurance|coverage|benefits|plans?)|medical,? dental", re.I)),
    ("dental", re.compile(r"\bdental\b", re.I)),
    ("vision", re.compile(r"\bvision (?:insurance|coverage|benefits|care|plans?)\b|dental,? (?:and |& )?vision|medical,? dental,? (?:and |&)?vision", re.I)),
    ("k401", re.compile(r"401\s?\(?k\)?", re.I)),
    ("match", re.compile(r"401\s?\(?k\)?[^.]{0,80}match|(?:employer|company) match|matching contributions?", re.I)),
    ("loan", re.compile(r"student loan", re.I)),
    ("stock", re.compile(r"stock options?|equity (?:grants?|compensation|package)|\bRSUs?\b|\bESPP\b|stock purchase", re.I)),
    ("pto", re.compile(r"\bPTO\b|paid time off|paid vacation|unlimited (?:vacation|time off)|vacation days", re.I)),
    ("maternity", re.compile(r"paid (?:maternity|parental)|maternity leave|parental leave", re.I)),
    ("paternity", re.compile(r"paid (?:paternity|parental)|paternity leave|parental leave", re.I)),
    ("tuition", re.compile(r"tuition (?:assistance|reimbursement|support)|education(?:al)? (?:assistance|reimbursement)", re.I)),
]


# Postings that say pay is commission only. A heuristic on the posting's own words, not a verified fact.
COMM_RE = re.compile(r"commission[- ]only|100% commission|straight commission|commission[- ]based (?:pay|compensation|position|role|only)|no base (?:salary|pay)|1099 commission", re.I)


PERK_KEYS = [k for k, _ in PERK_RES]


def _perks(text):
    return [k for k, rx in PERK_RES if rx.search(text or "")]


def _money(tok):
    tok = tok.replace(",", "").replace(" ", "")
    return int(tok[:-1]) * 1000 if tok[-1] in "kK" else int(tok)


def _salary(*texts):
    for t in texts:
        m = SAL_RE.search(t or "")
        if m:
            lo, hi = _money(m.group(1)), _money(m.group(2))
            if 20000 <= lo < hi <= 600000:
                return [lo, hi]
    return [0, 0]


def _fetch_raw(kind, token, name):
    """Return a list of raw postings: dicts with id, title, company, loc, remote, text, url, salary_text."""
    out = []
    if kind == "greenhouse":
        for j in _get("https://boards-api.greenhouse.io/v1/boards/%s/jobs?content=true" % token).get("jobs", []):
            out.append(dict(id=j["id"], title=j["title"], company=j.get("company_name") or name,
                            loc=(j.get("location") or {}).get("name", ""), remote=None,
                            text=_text(j.get("content")), url=j["absolute_url"], salary_text="",
                            posted=_ts(j.get("first_published") or j.get("updated_at"))))
    elif kind == "lever":
        for j in _get("https://api.lever.co/v0/postings/%s?mode=json" % token):
            cat = j.get("categories") or {}
            out.append(dict(id=j["id"], title=j["text"], company=name, loc=cat.get("location", "") or "",
                            remote=(j.get("workplaceType") == "remote") or None,
                            text=_text((j.get("descriptionPlain") or "") + " " + (j.get("additionalPlain") or "")),
                            url=j["hostedUrl"], salary_text="", posted=_ts(j.get("createdAt"))))
    elif kind == "ashby":
        for j in _get("https://api.ashbyhq.com/posting-api/job-board/%s" % token).get("jobs", []):
            if j.get("isListed") is False:
                continue
            out.append(dict(id=j["id"], title=j["title"], company=name, loc=j.get("location", "") or "",
                            remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote" or None,
                            text=_text(j.get("descriptionPlain") or j.get("descriptionHtml")),
                            url=j["jobUrl"], salary_text="", posted=_ts(j.get("publishedAt"))))
    elif kind == "remotive":
        for j in _get("https://remotive.com/api/remote-jobs?category=%s&limit=60" % token).get("jobs", []):
            loc = j.get("candidate_required_location") or ""
            if not re.search(r"usa|united states|worldwide|americas|north america|anywhere", loc, re.I):
                continue
            out.append(dict(id=j["id"], title=j["title"], company=j["company_name"], loc="Remote (%s)" % loc, remote=True,
                            text=_text(j.get("description")) + " " + " ".join(j.get("tags") or []),
                            url=j["url"], salary_text=j.get("salary") or "", posted=_ts(j.get("publication_date"))))
    elif kind == "jobicy":
        data = _get("https://jobicy.com/api/v2/remote-jobs?count=30&geo=usa&industry=%s" % token)
        for j in data.get("jobs", []):
            sal = None
            lo, hi = j.get("salaryMin"), j.get("salaryMax")
            if j.get("salaryPeriod") == "yearly" and j.get("salaryCurrency") == "USD" and isinstance(lo, (int, float)) \
                    and isinstance(hi, (int, float)) and 20000 <= lo < hi <= 600000:
                sal = [int(lo), int(hi)]
            out.append(dict(id=j["id"], title=j["jobTitle"], company=j["companyName"],
                            loc="Remote (%s)" % re.sub(r"\s+", " ", j.get("jobGeo") or "USA").strip(), remote=True,
                            text=_text(j.get("jobDescription")), url=j["url"], salary_text="", sal=sal,
                            posted=_ts(j.get("pubDate")),
                            fallback=(j.get("jobIndustry") or [None])[0]))
    elif kind == "muse":
        key = feed_keys().get("muse")         # registered key (The Muse: required beyond testing; 3,600 requests an hour instead of 500)
        for page in (1, 2):
            data = _get("https://www.themuse.com/api/public/jobs?page=%d&level=%s" % (page, urllib.parse.quote(token)) +
                        ("&api_key=%s" % urllib.parse.quote(key, safe="") if key else ""))
            for j in data.get("results", []):
                locs = [l.get("name", "") for l in j.get("locations", [])]
                loc = ", ".join(locs[:2]) + (" +%d more" % (len(locs) - 2) if len(locs) > 2 else "")
                cats = [c.get("name") for c in j.get("categories", []) if c.get("name")]
                out.append(dict(id=j["id"], title=j["name"], company=j["company"]["name"], loc=loc or "Not listed",
                                remote=any(re.search("remote|flexible", l, re.I) for l in locs) or None,
                                text=_text(j.get("contents")), url=j["refs"]["landing_page"], salary_text="",
                                fallback=cats[0] if cats else None, posted=_ts(j.get("publication_date")),
                                force_type="internship" if token == "Internship" else None))
    elif kind == "usajobs":
        out = _usajobs(token)
    elif kind == "smartrecruiters":
        out = _smartrecruiters(token, name)
    return out


_sr_desc = {}            # (company, posting id) -> {"at", "released", "detail"}: each description is read once a day at most


def _sr_detail(token, pid, released):
    """One posting's full record (description, pay), from the cache when it is fresh and the posting was not re-released."""
    key = (token, pid)
    with _lock:
        c = _sr_desc.get(key)
    if c and c["released"] == released and time.time() - c["at"] < SR_DESC_TTL:
        return c["detail"]
    at = time.time()
    try:
        d = _get("https://api.smartrecruiters.com/v1/companies/%s/postings/%s" % (urllib.parse.quote(token, safe=""), urllib.parse.quote(pid, safe="")))
    except Exception:
        d = c["detail"] if c else None           # keep the last description if this read fails, and try again at the next hourly refresh
        at = time.time() - SR_DESC_TTL + TTL["smartrecruiters"] - 60
    with _lock:
        _sr_desc[key] = {"at": at, "released": released, "detail": d}
    return d


def _smartrecruiters(token, name):
    """A company's public SmartRecruiters postings: the list page by page (100 at a time, until totalFound, at most KEEP postings),
    then each posting's own record for its description. Shapes as seen on the live API (October 16, 2026)."""
    cap = KEEP["smartrecruiters"]
    base = "https://api.smartrecruiters.com/v1/companies/%s/postings" % urllib.parse.quote(token, safe="")
    items, offset = [], 0
    while len(items) < cap:
        page = _get("%s?limit=100&offset=%d" % (base, offset))
        got = page.get("content") or []
        items += got
        offset += len(got)
        if not got or offset >= int(page.get("totalFound") or 0):
            break
    items = [p for p in items if isinstance(p, dict) and p.get("id")][:cap]
    with ThreadPoolExecutor(max_workers=4) as ex:                # four at a time: gentle on their API, and quick enough
        details = list(ex.map(lambda p: _sr_detail(token, str(p["id"]), p.get("releasedDate") or ""), items))
    out = []
    for p, d in zip(items, details):
        d = d if isinstance(d, dict) else {}
        L = p.get("location") or {}
        city, region = (L.get("city") or "").strip(), (L.get("region") or "").strip()
        loc = city + (", " + region if region and region not in city else "")
        if (L.get("country") or "us").lower() != "us":
            loc = L.get("fullLocation") or (loc + ", " + (L.get("country") or "").upper())
        secs = ((d.get("jobAd") or {}).get("sections")) or {}
        text = " ".join((secs.get(k) or {}).get("text") or "" for k in ("jobDescription", "qualifications", "additionalInformation"))
        comp = d.get("compensation") or {}
        sal = None
        if comp.get("currency") == "USD" and comp.get("period") == "YEARLY" and isinstance(comp.get("min"), (int, float)) and isinstance(comp.get("max"), (int, float)) \
                and 20000 <= comp["min"] < comp["max"] <= 600000:
            sal = [int(comp["min"]), int(comp["max"])]
        kind_label = ((p.get("typeOfEmployment") or {}).get("label") or "").lower()
        force = "internship" if "intern" in kind_label else ("parttime" if "part" in kind_label else None)
        dept = re.split(r"\s[-–—]\s", (p.get("department") or {}).get("label") or "")[0].strip()      # "Law Department – Tax Unit" -> "Law Department"
        func = (p.get("function") or {}).get("label") or ""
        fallback = dept or (func if func.lower() != "other" else "") or (p.get("industry") or {}).get("label") or None
        out.append(dict(id=p["id"], title=(p.get("name") or "").strip(), company=(p.get("company") or {}).get("name") or name,
                        loc=loc or "Not listed", remote=True if L.get("remote") else None,
                        text=_text(text) or (p.get("name") or ""), url="https://jobs.smartrecruiters.com/%s/%s" % (token, p["id"]),
                        salary_text="", sal=sal, posted=_ts(p.get("releasedDate")), fallback=fallback, force_type=force,
                        ats_id=str(p.get("uuid") or "")))     # the Application API addresses a posting by its uuid, not by its number
    return [r for r in out if r["title"]]


USA_INTERN = re.compile(r"\bintern(?:ship)?s?\b|student trainee|\bpathways\b", re.I)
USA_GRAD = re.compile(r"recent grad|graduates?\b", re.I)


def _usajobs(token):
    """One USAJOBS search (USAJOBS_QUERIES[token]). Headers as USAJOBS' Authentication guide says: Host, User-Agent = the email the key was
    requested with, Authorization-Key = the key. Field names as in the Search API reference."""
    keys = feed_keys()
    q = USAJOBS_QUERIES.get(token) or USAJOBS_QUERIES["philadelphia"]
    url = "https://data.usajobs.gov/api/search?" + "&".join("%s=%s" % (k, urllib.parse.quote(v, safe=",;")) for k, v in q.items())
    data = _get(url, {"Host": "data.usajobs.gov", "User-Agent": keys["usajobs_email"], "Authorization-Key": keys.get("usajobs", "")})
    out = []
    for item in ((data or {}).get("SearchResult") or {}).get("SearchResultItems") or []:
        d = item.get("MatchedObjectDescriptor") or {}
        det = (d.get("UserArea") or {}).get("Details") or {}
        title = d.get("PositionTitle") or ""
        if not title:
            continue
        loc = d.get("PositionLocationDisplay") or ""
        places = [p.get("LocationName", "") for p in d.get("PositionLocation") or [] if isinstance(p, dict) and p.get("LocationName")]
        if not loc or loc.lower().startswith("multiple locations"):        # "Multiple Locations": name the first two, as The Muse cards do
            loc = "; ".join(places[:2]) + (" +%d more" % (len(places) - 2) if len(places) > 2 else "") or loc
        pay = (d.get("PositionRemuneration") or [{}])[0] or {}
        sal, sal_text = None, ""
        try:
            lo, hi = float(pay.get("MinimumRange") or 0), float(pay.get("MaximumRange") or 0)
            money = lambda n: "{:,.0f}".format(n) if n >= 1000 else "{:,.2f}".format(n)   # noqa: E731  (yearly in dollars, hourly with cents)
            sal_text = ("$%s - $%s %s" % (money(lo), money(hi), pay.get("Description") or "")).strip() if hi else ""
            if pay.get("RateIntervalCode") == "PA" and 20000 <= lo < hi <= 600000:
                sal = [int(lo), int(hi)]                                   # yearly pay only; hourly pay stays in the text
        except (TypeError, ValueError):
            pass
        duties = det.get("MajorDuties")
        duties = " ".join(x for x in duties if isinstance(x, str)) if isinstance(duties, list) else (duties if isinstance(duties, str) else "")
        paths = det.get("HiringPath")
        paths = [p.lower() for p in (paths if isinstance(paths, list) else [paths]) if isinstance(p, str)]
        # Pathways: a student internship when the title or the hiring path says so; a Recent Graduates posting stays an (entry-level) job
        intern = (USA_INTERN.search(title) and not USA_GRAD.search(title)) or ("student" in paths and "graduates" not in paths and not USA_GRAD.search(title))
        sched = " ".join(s.get("Name", "") for s in d.get("PositionSchedule") or [] if isinstance(s, dict))
        cats = [c.get("Name") for c in d.get("JobCategory") or [] if isinstance(c, dict) and c.get("Name")]
        apply_uri = [u for u in d.get("ApplyURI") or [] if isinstance(u, str) and u.startswith("https://")]
        # dates come as 2026-10-01T00:00:00.0000: the 4-digit fraction is dropped so any Python version reads them (the host runs 3.12)
        out.append(dict(id=item.get("MatchedObjectId") or d.get("PositionID"), title=title, company=d.get("OrganizationName") or d.get("DepartmentName") or "USAJOBS",
                        loc=loc, remote=True if (det.get("RemoteIndicator") is True or re.search(r"remote", loc, re.I)) else None,
                        text=_text(" ".join(x for x in (det.get("JobSummary"), duties, d.get("QualificationSummary")) if isinstance(x, str))),
                        url=(apply_uri[0] if apply_uri else d.get("PositionURI") or ""), announcement=d.get("PositionURI") or "",
                        salary_text=sal_text, sal=sal, posted=_ts(re.sub(r"\.\d+$", "", str(d.get("PublicationStartDate") or ""))), fallback=cats[0] if cats else None,
                        force_type="internship" if intern else ("parttime" if re.search(r"part[- ]time", sched, re.I) else None)))
    return out


def _type(raw):
    """internship, coop, parttime or job, from the title (and the start of the text for part-time). Cheap, so it is known before the costly part."""
    t = raw["title"].lower()
    return raw.get("force_type") or ("internship" if re.search(r"\bintern(ship)?\b", t) else ("coop" if re.search(r"co-?op\b", t) else
                                     ("parttime" if re.search(r"part[- ]time", t + " " + raw["text"][:400], re.I) else "job")))


def _normalize(raw, kind, name, board=None):
    title, loc, text = raw["title"], raw["loc"], raw["text"]
    remote = raw["remote"] if raw["remote"] is not None else bool(re.search(r"\bremote\b", loc, re.I))
    if not _us_ok(loc, remote):
        return None
    if FOREIGN_RE.search(title) and not EXPLICIT_US.search(loc):
        return None                                     # a region-specific role (for example "ANZ" or "Toronto") listed as just "Remote"
    if raw["url"].startswith("http://"):                # some employers list their careers page as http:// (Squarespace, Block): open it securely
        raw = dict(raw, url="https://" + raw["url"][len("http://"):])
    if not raw["url"].startswith("https://"):
        return None
    hay = (title + " ") * 2 + text
    found = []
    for skill, rx in SKILL_RES:
        if skill in TITLE_GATED and not TITLE_GATED[skill].search(title):
            continue
        n = len(rx.findall(hay))
        if n:
            found.append((n, skill))
    if found:
        skills = [s for _, s in sorted(found, key=lambda x: -x[0])[:4]]
    elif raw.get("fallback"):
        skills = [raw["fallback"]]      # no known skill in the text: score on the posting's own category
    else:
        return None
    mode = "remote" if remote else ("hybrid" if re.search(r"hybrid", loc + " " + text[:600], re.I) else "onsite")
    typ = _type(raw)
    m = YRS_RE.search(text)
    yrs = min(int(m.group(1)), 15) if m else 0
    edu = "Bachelor" if re.search(r"bachelor|\bB\.?S\.? degree", text, re.I) else "High school"
    blurb = text[:170].rsplit(" ", 1)[0] + "…" if len(text) > 170 else text
    desc = _role_summary(text)                                                    # what the emails show about the job
    jid = 100000 + int(hashlib.sha1(("%s:%s" % (kind, raw["id"])).encode()).hexdigest()[:6], 16)
    src = name if kind in ("remotive", "jobicy", "muse", "usajobs") else "%s's careers page" % raw["company"]
    # Where this posting lives in the employer's own hiring system. It is only an address (not a credential): it is used when, and only when, the
    # employer has connected with their own key (see ats_connections); otherwise it is never used and apply stays "link".
    # Ashby: the job board's own posting id is the jobPostingId its API takes. SmartRecruiters: the posting's uuid (see _smartrecruiters).
    pid = str(raw.get("ats_id") or raw["id"])
    ats = {"kind": kind, "board": board, "id": pid} if (kind in ats_api.KINDS and board and ats_api.TOKEN_RE.match(board) and ats_api.ID_RE.match(pid)) else None
    # contact is deliberately empty and apply is "link": a third-party feed never gets an application emailed to anyone
    out = dict(id=jid, co=raw["company"], role=title, loc=_place(loc, mode), mode=mode,
               sal=raw.get("sal") or _salary(raw["salary_text"], text), yrs=yrs, edu=edu, skills=skills, blurb=blurb, desc=desc,
               type=typ, url=raw["url"], source=src, contact="", apply="link", live=True, ats=ats,
               posted=raw.get("posted", 0), perks=_perks(text), comm=bool(COMM_RE.search(text)))
    # Credit every feed, on the card ("via ...") and in the application record ("credit"): each free feed asks for it, and an employer board is the employer's own
    out["via"] = VIA.get(kind, "%s").replace("%s", name)
    out["credit"] = "via USAJOBS; apply on the official announcement" if kind == "usajobs" else "via " + out["via"]
    if (raw.get("announcement") or "").startswith("https://"):
        out["announcement"] = raw["announcement"]                 # USAJOBS: the official announcement, kept next to the apply link
    return out


_refreshing = set()


def known_webhook(job_id):
    """(url, secret) the employer registered for this job, or None. Only partner employers have one."""
    partner_jobs()
    return _hooks.get(job_id)


def job_info(job_id):
    """What this server itself holds about a job (partner list or feed cache), or None. Used so an email describes the job from
    our own data rather than from whatever the browser sends."""
    for j in partner_jobs():
        if j["id"] == job_id:
            return j
    with _lock:
        for c in _cache.values():
            for j in c["jobs"]:
                if j["id"] == job_id:
                    return j
    return None


def known_contact(job_id):
    """The recruiter address this server itself holds for a job ('' if none or unknown). Only partner employers have one."""
    for j in partner_jobs():
        if j["id"] == job_id:
            return j.get("contact", "") or ""
    with _lock:
        for c in _cache.values():
            for j in c["jobs"]:
                if j["id"] == job_id:
                    return j.get("contact", "") or ""
    return ""


def _refresh_in_background(src):
    try:
        _fetch_source(src)
        _save_disk()
    finally:
        with _lock:
            _refreshing.discard(src)


def _load_source(src):
    """Serve what is cached right away, even if stale, and refresh it in the background.
    Only the very first request for a source waits for the network."""
    ttl = TTL.get(src[0], DEFAULT_TTL)
    if src[0] == "usajobs" and not feed_keys().get("usajobs"):
        return _fetch_source(src)                # no key: skipped right away, never served from an older copy
    with _lock:
        c = _cache.get(src)
        if c and time.time() - c["at"] >= ttl and src not in _refreshing:
            _refreshing.add(src)
            threading.Thread(target=_refresh_in_background, args=(src,), daemon=True).start()
    if c:
        return c["jobs"], c["status"]
    return _fetch_source(src)


def _fetch_source(src):
    kind, token, name = src
    ttl = TTL.get(kind, DEFAULT_TTL)
    if kind == "usajobs" and not feed_keys().get("usajobs"):
        with _lock:
            _cache.pop(src, None)               # a key that was removed stops the source at once (no copy is served from before)
        return [], "no key"                     # skipped, nothing fetched or cached: the source starts the moment the owner adds the key
    try:
        student, other = [], []
        for raw in _fetch_raw(kind, token, name):
            # only the first STUDENT_PER_SOURCE student roles and PER_SOURCE others can be kept below, so a posting past those is not worked
            # through at all (a big board lists hundreds; reading every one cost about 35 CPU seconds, a minute or more on a small host)
            bucket, cap = (other, PER_SOURCE) if _type(raw) == "job" else (student, STUDENT_PER_SOURCE)
            if kind in KEEP:                                     # the City and USAJOBS keep up to 120 (student roles first), so read them all
                cap = KEEP[kind]
            if len(bucket) >= cap:
                continue
            j = _normalize(raw, kind, name, token)
            if j:
                (student if j["type"] in ("internship", "coop", "parttime") else other).append(j)
        # keep the student-type roles first (a board can list hundreds of senior roles ahead of its internships)
        if kind in KEEP:
            jobs = (student + other)[:KEEP[kind]]
        else:
            jobs = student[:STUDENT_PER_SOURCE] + other[:max(OTHER_PER_SOURCE, PER_SOURCE - len(student[:STUDENT_PER_SOURCE]))]
        status = "%d jobs" % len(jobs)
    except Exception as e:                      # keep serving the last good copy if the feed is down
        c = _cache.get(src)
        jobs = c["jobs"] if c else []
        why = _scrub(str(e))                    # a feed key is never written to the log or the status line
        if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403) and kind in ("usajobs", "muse"):
            why = "the feed refused the key (HTTP %d); check it on the setup page" % e.code
        status = "error: %s" % why[:80]
        sys.stderr.write("[uaply] job feed %s failed: %s\n" % ("/".join(src), why[:200]))      # the reason is kept in the server's own log
        with _lock:
            if c:
                c["at"] = time.time() - ttl + 120   # retry in two minutes
        return jobs, status
    with _lock:
        _cache[src] = {"at": time.time(), "jobs": jobs, "status": status}
        _disk["dirty"] = True
    return jobs, status


def _cfg():
    """uaply-config.json, with UAPLY_CONFIG_JSON from the environment on top (same rule as uaply_api.config)."""
    cfg = {}
    try:
        if os.environ.get("UAPLY_CONFIG_FILE") != "none":      # same rule as uaply_api.config
            with open(os.path.join(ROOT, "uaply-config.json"), encoding="utf-8") as f:
                cfg.update(json.load(f))
    except Exception:
        pass
    try:
        env = json.loads(os.environ.get("UAPLY_CONFIG_JSON") or "{}")
        if isinstance(env, dict):
            cfg.update(env)
    except ValueError:
        pass
    return cfg


def feeds_allowed():
    """Third-party feeds the owner has explicitly switched on (default: none). See the legal notes at the top.
    A source kind is on when it is listed in "feeds" (uaply-config.json / UAPLY_CONFIG_JSON) or in UAPLY_FEEDS. "feeds_off" (a list, or
    UAPLY_FEEDS_OFF=remotive,muse) switches a kind off by name and wins over both, so one line turns a feed off without touching the others:
    {"feeds_off": ["remotive"]}. The kinds: greenhouse, lever, ashby, smartrecruiters, usajobs, jobicy, muse, remotive."""
    cfg = _cfg()
    f, off = cfg.get("feeds"), cfg.get("feeds_off")
    on = {x for x in f if isinstance(x, str)} if isinstance(f, list) else set()
    on |= {x.strip().lower() for x in (os.environ.get("UAPLY_FEEDS") or "").split(",") if x.strip()}     # e.g. UAPLY_FEEDS=greenhouse,lever,ashby
    off = {x.strip().lower() for x in off if isinstance(x, str)} if isinstance(off, list) else set()
    off |= {x.strip().lower() for x in (os.environ.get("UAPLY_FEEDS_OFF") or "").split(",") if x.strip()}
    return on - off


# ---- partner employers: postings an employer gave us and who agreed to receive applications ----
_partners = {"path": None, "mtime": None, "jobs": []}
_hooks = {}          # job id -> (webhook url, secret). Kept apart from the job dicts: those go to browsers, the secret must not
_ats_jobs = {}       # partner job id -> {kind, board, id, key}: the employer's own hiring system. Same rule: the key never goes to a browser
_ats_conn = {"stamp": None, "map": {}}


def _clean(v, n):
    return re.sub(r"\s+", " ", v).strip()[:n] if isinstance(v, str) else ""


def partners_file(for_writing=False):
    """Where the employer list is kept: on a host on the persistent disk (UAPLY_DATA_DIR), else next to the code. With for_writing, the path to create.
    With UAPLY_DATA_DIR set, ONLY that folder is used. It used to fall back to the file next to the code, so a test run (which always sets
    UAPLY_DATA_DIR) read the owner's real employer list and the Connect box test wrote a test key into it; and on a host a first save went
    to the code folder, which a redeploy wipes."""
    folder = os.environ.get("UAPLY_DATA_DIR") or ROOT
    path = os.path.join(folder, "uaply-partners.json")
    return path if (for_writing or os.path.exists(path)) else None


def _file_stamp(path):
    """What tells a changed file from an unchanged one: the modification time to the nanosecond and the size. The time alone can stay the
    same across two quick writes (a busy computer, a coarse file system), so a removed connection or employer could keep being served."""
    st = os.stat(path)
    return (st.st_mtime_ns, st.st_size)


def ats_connections():
    """{(kind, board): api_key} for employers who connected their own hiring system (Greenhouse, Lever, Ashby or SmartRecruiters) with a key they created. Read from the
    UAPLY_ATS_JSON setting (a host's dashboard) and from 'ats_connections' in the employer list. Anything malformed is skipped."""
    env, path = os.environ.get("UAPLY_ATS_JSON") or "", partners_file()
    try:
        stamp = (env, path, _file_stamp(path) if path else None)
    except OSError:
        stamp = (env, path, None)
    if _ats_conn["stamp"] == stamp:
        return _ats_conn["map"]
    lists = []
    if env:
        try:
            lists.append(json.loads(env))
        except ValueError:
            pass
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                lists.append(data.get("ats_connections"))
        except Exception:
            pass
    out = {}
    for lst in lists:
        for c in (lst if isinstance(lst, list) else []):
            if isinstance(c, dict) and ats_api.valid_connection(c.get("kind"), c.get("board"), c.get("api_key")):
                out[(c["kind"], c["board"])] = c["api_key"]
    _ats_conn.update(stamp=stamp, map=out)
    return out


def partner_jobs():
    """Every job an employer gave UAply directly: the partner list plus postings made in Hiring mode (sandbox only)."""
    import employers_api           # imported here: employers_api imports uaply_api, which imports this module
    return _file_partner_jobs() + employers_api.feed_jobs()


def _file_partner_jobs():
    """Jobs from uaply-partners.json. Each employer must record how it consented. An employer with a contact address
    receives applications directly; without one it is link-out only. partners.example.json is documentation only and is
    never served as jobs."""
    # on a host, keep the real list on the persistent disk (UAPLY_DATA_DIR) so it is never in the repository
    path = partners_file()
    if not path:
        return []
    try:
        mtime = _file_stamp(path)
        if _partners["path"] == path and _partners["mtime"] == mtime:
            return _partners["jobs"]
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _partners["jobs"]
    out = []
    new_hooks, new_ats = {}, {}
    for e in data.get("employers", []) if isinstance(data, dict) else []:
        name, consent = _clean(e.get("name"), 100), _clean(e.get("consent"), 300)
        if not name or not consent or consent.lower().startswith("placeholder"):
            continue                                   # no recorded consent (or the example text still in place), no listing
        # the employer's own hiring system (Greenhouse, Lever, Ashby or SmartRecruiters) and the key they created for it: applications to their jobs go straight in
        a = e.get("ats") if isinstance(e.get("ats"), dict) else {}
        ats_cfg = a if ats_api.valid_connection(a.get("kind"), a.get("board"), a.get("api_key")) else None
        contact = _clean(e.get("contact"), 120)
        contact = contact if re.match(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", contact) else ""
        # Indeed-style delivery: an HTTPS address the employer registered; each application is POSTed there as signed JSON
        hook_url = _clean(e.get("webhook"), 400)
        local_ok = os.environ.get("UAPLY_ALLOW_LOCAL_WEBHOOK") == "1" and re.match(r"^http://(127\.0\.0\.1|localhost)[:/]", hook_url)
        hook = (hook_url, _clean(e.get("webhook_secret"), 200)) if (hook_url.startswith("https://") or local_ok) and " " not in hook_url else None
        for j in e.get("jobs", []):
            raw_skills = j.get("skills")
            role, skills = _clean(j.get("role"), 120), [_clean(s, 40) for s in (raw_skills if isinstance(raw_skills, list) else [])[:6] if _clean(s, 40)]
            if not role or not skills:
                continue
            url = _clean(j.get("url") or e.get("url"), 400)
            sal = j.get("sal") if isinstance(j.get("sal"), list) and len(j["sal"]) == 2 else [0, 0]
            try:
                sal = [max(0, int(sal[0])), max(0, int(sal[1]))]
            except (TypeError, ValueError):
                sal = [0, 0]
            jid = 200000 + int(hashlib.sha1(("partner:%s:%s" % (name, role)).encode()).hexdigest()[:6], 16)
            if hook:
                new_hooks[jid] = hook
            ats_id = _clean(j.get("ats_job_id"), 80)
            ats = {"kind": ats_cfg["kind"], "board": ats_cfg["board"], "id": ats_id, "key": ats_cfg["api_key"]} if (ats_cfg and ats_api.ID_RE.match(ats_id)) else None
            if ats:
                new_ats[jid] = ats
            out.append(dict(
                id=jid,
                co=name, role=role, loc=_clean(j.get("loc"), 80) or "Not listed",
                mode=j.get("mode") if j.get("mode") in ("remote", "hybrid", "onsite") else "remote", sal=sal,
                yrs=min(15, max(0, int(j.get("yrs") or 0))) if str(j.get("yrs") or 0).isdigit() else 0,
                edu=j.get("edu") if j.get("edu") in ("High school", "Associate", "Bachelor", "Master", "Doctorate") else "High school",
                skills=skills, blurb=_clean(j.get("blurb"), 220),
                type=j.get("type") if j.get("type") in ("job", "parttime", "internship", "coop") else "job",
                url=url if url.startswith("https://") else "", source="Direct from %s (partner employer)" % name,
                contact=contact, apply="direct" if (contact or hook or ats) else "link", webhook=bool(hook), partner=True, live=True,
                instant=bool(contact or hook or ats),       # the card says "Apply instantly": swipe right really sends the application
                # optional filter data the employer can give: "posted" (a date), "perks" (keys from PERK_RES), "commission_only"
                posted=_ts(j.get("posted")),
                perks=sorted(set([p for p in (j.get("perks") or []) if p in PERK_KEYS] + _perks(j.get("blurb") or ""))),
                comm=j.get("commission_only") is True or bool(COMM_RE.search(j.get("blurb") or ""))))
    _partners.update(path=path, mtime=mtime, jobs=out)
    _hooks.clear()
    _hooks.update(new_hooks)
    _ats_jobs.clear()
    _ats_jobs.update(new_ats)
    return out


def job_policy(job_id):
    """How an application to this job may be handled: 'direct' (the employer opted in), 'link' (send the person to the
    employer's own page; nothing is emailed) or 'unknown' (an example listing)."""
    for j in partner_jobs():
        if j["id"] == job_id:
            return j["apply"]
    conns = ats_connections()
    with _lock:
        for c in _cache.values():
            for j in c["jobs"]:
                if j["id"] == job_id:
                    # a real posting whose employer connected their hiring system with their own key can be applied to instantly
                    return "direct" if _connected(j, conns) else "link"
    return "unknown"


def _connected(job, conns):
    """True when this feed posting's employer connected their hiring system (so a swipe right can send the application into it)."""
    a = job.get("ats") if isinstance(job, dict) else None
    return bool(a and (a.get("kind"), a.get("board")) in conns)


def known_ats(job_id):
    """{kind, board, id, key} for the hiring system this server may send an application to for this job, or None. Either a partner employer that gave
    its key with its jobs, or a real posting whose employer connected. Only this server ever holds the key; browsers get only a yes in 'instant'."""
    partner_jobs()
    a = _ats_jobs.get(job_id)
    if a:
        return dict(a)
    conns = ats_connections()
    with _lock:
        for c in _cache.values():
            for j in c["jobs"]:
                if j["id"] == job_id and _connected(j, conns):
                    return {"kind": j["ats"]["kind"], "board": j["ats"]["board"], "id": j["ats"]["id"], "key": conns[(j["ats"]["kind"], j["ats"]["board"])]}
    return None


def get_jobs():
    _load_disk()
    allowed = feeds_allowed()
    sources = [s for s in SOURCES if s[0] in allowed]
    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(_load_source, sources))
    jobs, seen, summary = [], set(), {}
    for pj in partner_jobs():
        seen.add(pj["id"])
        jobs.append({k: v for k, v in pj.items() if k != "contact"} if pj.get("emp") else pj)    # an employer's account email stays on this server
    summary["Partner employers"] = "%d jobs" % len(jobs)
    for src, (js, status) in zip(sources, results):
        summary[src[2] + ("/" + src[1] if src[0] in MULTI else "")] = "unavailable right now" if hide_errors and status.startswith("error") else status
        for j in js:
            if j["id"] not in seen:
                seen.add(j["id"])
                jobs.append(j)
    if not sources:
        summary["Third-party feeds"] = "off (not verified as permitted)"
    conns = ats_connections()
    if conns:           # a posting whose employer connected is marked here, on a copy, so the shared cache stays as fetched
        jobs = [dict(j, apply="direct", instant=True) if _connected(j, conns) else j for j in jobs]
    _save_disk()
    return {"fetched_at": int(time.time()), "sources": summary, "jobs": jobs}


def get_json():
    return json.dumps(get_jobs()).encode("utf-8")
