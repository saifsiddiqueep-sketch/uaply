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
  * Greenhouse, Lever, Ashby, Workable public boards: meant for employers' careers pages; no terms found that cover third-party
    aggregation. Unverified, LINK-OUT ONLY.
  * USAJOBS (the federal government's own API, read October 16, 2026): its terms let public data be copied, stored and
    republished, commercial use included, without OPM approval; credit and a link to the official announcement are asked
    for, and nobody may be told an application was sent when it was not. LINK-OUT ONLY, credited "via USAJOBS". Needs a
    free key (feed_keys.usajobs); without one the source is skipped with the status "no key".
  * SmartRecruiters public Posting API (City of Philadelphia): public postings of a public body, no key, no published
    terms for readers. LINK-OUT ONLY, credited "City of Philadelphia on SmartRecruiters".
  * Simplify / Pitt CSC internship lists (GitHub), Himalayas, Remote OK: added October 21, 2026, LINK-OUT ONLY and credited on the card;
    their terms, and why Remotive, Adzuna and others are not used, are in docs/job-sources.md.
  * CareerOneStop (U.S. Department of Labor; National Labor Exchange): royalty-free license; credit both DOL ETA and Minnesota DEED
    where its data shows, do not alter the data, keep the key secret. LINK-OUT ONLY. Off ("no key") until UAPLY_COS_USER_ID and
    UAPLY_COS_TOKEN are set.
  Third-party feeds are OFF unless the owner lists them under "feeds" in uaply-config.json. Jobs from a feed are never
  emailed to anyone (the recruiter address is dropped); swiping right only opens the employer's own page.

get_jobs() returns {"fetched_at", "sources", "jobs", "merged", "aged_out"} where each job already matches the shape the app expects
(the list form: a feed job without the fields no card shows, LIST_DROP, which job_full and GET /api/jobs/<id> give; get_page is the same
list a page at a time; with postedDays, and "route": "Ready" when UAply sends the application itself,
"Ready, one tap" where the employer's page is likely to ask for a human check, "Ready" otherwise; see human-checks.json). Postings older
than MAX_AGE_DAYS are left out, and the same job from two feeds is shown once ("merged" counts the copies left out).
"""
import base64
import codecs
import collections
import datetime
import hashlib
import html
import http.client
import ipaddress
import json
import os
import queue
import zlib
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import ats_api
import mailer

ROOT = os.path.dirname(os.path.abspath(__file__))
UA = "UAplyDev/0.1 (local prototype)"
DEFAULT_TTL = 30 * 60
TTL = {"remotive": 6 * 3600,          # Remotive allows roughly 4 requests a day
       "jobicy": 3600,                # Jobicy asks for at most one sync pass an hour
       "usajobs": 3 * 3600,           # federal postings change slowly; two searches every three hours
       "smartrecruiters": 3600,       # the City's list once an hour (each posting's description is read far less often, see SR_DESC_TTL)
       "simplify": 6 * 3600,          # the Simplify / Pitt CSC lists change daily; each listed posting is checked on its own board at most once a day
       "himalayas": 3 * 3600,         # no key: one public allowance shared with every caller, so a few pages every three hours
       "remoteok": 6 * 3600,          # one request for the whole list
       "careeronestop": 3 * 3600,     # 16 searches every three hours
       "careerpage": 6 * 3600}        # an employer's careers site: its sitemap every 6 hours, a page again only when its lastmod changes
PER_SOURCE = 14
STUDENT_PER_SOURCE = 10          # internships, co-ops and part-time roles are kept first so the student tabs are not empty
OTHER_PER_SOURCE = 6
# A public body's own list (the City, the federal government) is local and is kept whole up to this many postings, student roles first,
# instead of the 14 an employer board gets. SmartRecruiters is also read no further than this (so at most this many description reads).
KEEP = {"usajobs": 120, "smartrecruiters": 120, "simplify": 120, "careeronestop": 100}   # CareerOneStop: one page of 100 per search, kept whole
SR_DESC_TTL = 24 * 3600          # a SmartRecruiters posting's description is read once, then again only after a day or when the posting is re-released
# UAply launches in the Philadelphia region: a board may keep this many Pennsylvania, New Jersey or Delaware roles on top of its 14, so a
# national employer's tri-state openings are not cut just because they come after its first 14 postings. Matched on the posting's own
# location (case matters: ", PA", ", NJ", ", DE"; a German ", DE" never gets this far, see _us_ok).
LOCAL_PER_SOURCE = 10
LOCAL_RE = re.compile(r"\bPennsylvania\b|, PA\b|\bPhiladelphia\b|\bPittsburgh\b|\bKing of Prussia\b|\bConshohocken\b|\bAllentown\b|\bHarrisburg\b|"
                      r"\bNew Jersey\b|, NJ\b|\bTrenton\b|\bCamden\b|\bCherry Hill\b|\bJersey City\b|\bHoboken\b|\bPrinceton\b|\bNewark, (?:NJ|New Jersey)\b|"
                      r"\bDelaware\b|, DE\b|\bWilmington, (?:DE|Delaware)\b|[a-z] (?:PA|NJ|DE)$")
# A posting whose newest date (posted, or updated where the feed gives one) is older than this is not shown: it is most likely filled
# or forgotten. A posting with no date at all is kept (nothing says it is old). Partner employers' own postings are never aged out here:
# the employer opens and closes those itself.
MAX_AGE_DAYS = 60
DAY_MS = 86400 * 1000
# USAJOBS' search returns only announcements that are open now, each with its own closing date, so a long-open federal announcement
# (some run for months) is not stale and is not aged out.
AGE_EXEMPT = ("usajobs",)
# An hourly part-time or seasonal posting on the employer's own board is usually evergreen: one posting per store or studio, open all
# year (Insomnia Cookies: 852 of 1,063 part-time postings older than 60 days; solidcore coaches: years). Still listed on the employer's
# own board means still hiring, so those are not aged out there. An aggregator's copy still is.
EVERGREEN_KINDS = ("greenhouse", "lever", "ashby", "workable", "smartrecruiters", "careerpage")
EVERGREEN_TYPES = ("part-time", "temporary")

# (kind, board token, display name). Boards are the employer's own public careers feed.
SOURCES = [
    # The local public lists first: on a fresh start the boards are read FEED_PARALLEL at a time in this order, and with 60 sources the
    # City (120 description reads) came last and missed the first visitor's wait. They share no jobs with the boards below.
    ("smartrecruiters", "CityofPhiladelphia", "City of Philadelphia"),   # the City's own public SmartRecruiters postings (no key)
    # USAJOBS (needs a key: feed_keys.usajobs or UAPLY_USAJOBS_KEY): every federal posting around five tri-state cities, then the same areas
    # for the Students and Recent graduates hiring paths (Pathways) and for part-time schedules (both were cut by the 120 cap of a full search).
    # 15 searches, each every 3 hours = 120 requests a day (see USAJOBS_AREAS). The areas overlap on purpose; a posting is shown once.
] + [("usajobs", area + suffix, "USAJOBS") for suffix in ("", "-students", "-parttime") for area in ("philadelphia", "wilmington", "trenton", "newark", "camden")] + [
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
    ("workable", "huggingface", "Hugging Face"),  # Workable's public jobs feed (no key); most roles are remote, some US-based
    ("ashby", "linear", "Linear"),
    # Employers with Pennsylvania openings (checked October 20, 2026: total postings / of them in PA on the public board)
    ("lever", "gopuff", "Gopuff"),                # Philadelphia HQ: 810 / 44
    ("greenhouse", "perpay", "Perpay"),           # Philadelphia HQ: 22 / 22
    ("greenhouse", "motional", "Motional"),       # Pittsburgh office: 81 / 45
    ("greenhouse", "vynamic", "Vynamic"),         # Philadelphia HQ: 17 / 4
    ("greenhouse", "carvana", "Carvana"),         # 1,719 / 30 (inspection centers, customer advocates)
    ("greenhouse", "shipmonk", "ShipMonk"),       # 74 / 22 (Lehigh Valley warehouses)
    ("greenhouse", "doordashusa", "DoorDash"),    # 452 / 10
    ("greenhouse", "toast", "Toast"),             # 310 / 9
    ("greenhouse", "mongodb", "MongoDB"),         # 395 / 8
    ("greenhouse", "mejuri", "Mejuri"),           # 179 / 8 (stores)
    ("greenhouse", "charliehealth", "Charlie Health"),   # 258 / 6 (clinical)
    ("greenhouse", "strivehealth", "Strive Health"),     # 60 / 4 (clinical)
    # Large national boards with many US roles across functions: healthcare, retail, restaurants, operations, finance, support
    ("greenhouse", "oscar", "Oscar Health"),      # 248, all US
    ("greenhouse", "sweetgreen", "Sweetgreen"),   # 65
    ("greenhouse", "glossier", "Glossier"),       # 22 (stores)
    ("greenhouse", "twochairs", "Two Chairs"),    # 34 (therapists)
    ("greenhouse", "elationhealth", "Elation Health"),   # 18
    ("greenhouse", "axon", "Axon"),               # 486
    ("greenhouse", "instacart", "Instacart"),     # 123
    ("greenhouse", "airbnb", "Airbnb"),           # 182
    ("greenhouse", "chime", "Chime"),             # 71
    ("greenhouse", "brex", "Brex"),               # 261
    ("greenhouse", "point72", "Point72"),         # 215
    ("greenhouse", "gusto", "Gusto"),             # 101
    ("greenhouse", "twilio", "Twilio"),           # 133
    ("greenhouse", "reddit", "Reddit"),           # 153
    ("greenhouse", "faire", "Faire"),             # 78
    ("greenhouse", "ziprecruiter", "ZipRecruiter"),   # 43
    ("greenhouse", "wonderschool", "Wonderschool"),   # 39 (child care)
    ("lever", "zoox", "Zoox"),                    # 239, all US
    ("ashby", "ramp", "Ramp"),                    # 168, all US
    # Employers with New Jersey and Delaware openings (checked October 21, 2026: total postings / of them in NJ or DE)
    ("greenhouse", "crossriverbank", "Cross River Bank"),   # Fort Lee NJ: 36 / 28
    ("greenhouse", "legendcareers", "Legend Biotech"),      # Somerset NJ: 79 / 67
    ("workable", "thorlabs", "Thorlabs"),                   # Newton NJ: 84 / 47 (manufacturing)
    ("greenhouse", "lgelectronics", "LG Electronics"),      # Englewood Cliffs NJ: 115 / 23
    ("greenhouse", "genscript", "GenScript"),               # Piscataway NJ: 75 / 23 (labs)
    ("workable", "ascendis-pharma", "Ascendis Pharma"),     # Princeton NJ: 67 / 14
    ("greenhouse", "nice", "NICE"),                         # Hoboken NJ: 184 / 10
    ("lever", "BestEgg", "Best Egg"),                       # Wilmington DE: 10 / 9
    ("lever", "NJStateOfficeofInnovation", "New Jersey Office of Innovation"),   # the State's own public postings: 7 / 7
    ("greenhouse", "mettel", "MetTel"),                     # 20 / 6
    ("greenhouse", "fanduel", "FanDuel"),                   # Jersey City NJ: 83 / 4
    # National boards with many on-site roles in other states (clinics, warehouses, gyms, plants, launch sites)
    ("greenhouse", "mcmastercarr", "McMaster-Carr"),        # 30 (Robbinsville NJ and warehouses across the US)
    ("greenhouse", "onemedical", "One Medical"),            # 396 clinics and offices (10 in NJ)
    ("greenhouse", "tia", "Tia"),                           # 32 clinics
    ("smartrecruiters", "Equinox", "Equinox"),              # 740 clubs (97 of the first 100 in the US)
    ("smartrecruiters", "RedBull", "Red Bull"),             # 1,239 (54 of the first 100 in the US: sales and field roles)
    ("greenhouse", "lucidmotors", "Lucid Motors"),          # 445 (plant and studios)
    ("greenhouse", "rocketlab", "Rocket Lab"),              # 581
    ("greenhouse", "relativity", "Relativity Space"),       # 382
    ("greenhouse", "spacex", "SpaceX"),                     # 2,779 (32 MB, read a posting at a time)
    ("greenhouse", "flexport", "Flexport"),                 # 204
    # Part-time roles students can take: bakery stores and fitness studios (checked October 21, 2026: total / in PA, NJ or DE)
    ("lever", "insomniacookies", "Insomnia Cookies"),       # Philadelphia HQ: 1,253 / 94 (16.8 MB, read a posting at a time)
    ("lever", "solidcore", "solidcore"),                    # 253 / 29
    ("remotive", "software-dev", "Remotive"),
    ("jobicy", "engineering", "Jobicy"),      # credit Jobicy and link to its canonical job URL
    ("jobicy", "marketing", "Jobicy"),
    ("jobicy", "data-science", "Jobicy"),
    # every other Jobicy industry with US-open remote jobs (October 21, 2026): one request each, inside Jobicy's one sync pass an hour
] + [("jobicy", slug, "Jobicy") for slug in ("supporting", "admin-support", "accounting-finance", "healthcare", "education", "hr", "management",
                                            "business", "design-multimedia", "copywriting", "project-management", "legal")] + [
    ("muse", "Internship", "The Muse"),       # The Muse public jobs API; links go to the posting on The Muse
    ("muse", "Entry Level", "The Muse"),
    # CareerOneStop (U.S. Department of Labor): the National Labor Exchange, which the PA, NJ and DE state job banks run on. Needs
    # UAPLY_COS_USER_ID and UAPLY_COS_TOKEN; "no key" until then. All jobs, internships and part-time jobs posted in the last 7 days
    # around five tri-state cities, plus remote jobs nationwide: 16 searches, each every 3 hours = 128 requests a day (see COS_SEARCHES).
] + [("careeronestop", t, "CareerOneStop") for t in ("philadelphia", "wilmington", "trenton", "newark", "camden",
                                                    "philadelphia-internship", "wilmington-internship", "trenton-internship", "newark-internship", "camden-internship",
                                                    "philadelphia-parttime", "wilmington-parttime", "trenton-parttime", "newark-parttime", "camden-parttime", "remote")] + [
    # Internship lists kept on GitHub by Simplify and Pitt CSC (SimplifyJobs/Summer2027-Internships, formerly Summer2026). Only rows whose
    # apply link is a Greenhouse, Lever or SmartRecruiters posting are used, and each is read from that employer's own board first: a row
    # whose posting is gone is dropped. Credited on the card. Last: about 240 checks on a fresh start, so they never hold up the boards.
    ("simplify", "README.md", "Simplify and Pitt CSC"),             # summer internships
    ("simplify", "README-Off-Season.md", "Simplify and Pitt CSC"),  # fall, winter and spring internships and co-ops
    # Remote-job boards whose free APIs allow display with a link back (terms read October 21, 2026; see docs/job-sources.md)
    ("himalayas", "US", "Himalayas"),         # link to the job on Himalayas, apply link unchanged, never passed on to other boards
    ("himalayas", "US-intern", "Himalayas"),  # the same, internships only (935 open to the US on October 21, 2026)
    ("himalayas", "US-parttime", "Himalayas"),   # the same, part-time only (1,952)
    ("remoteok", "all", "Remote OK"),         # link back to the job on Remote OK and name Remote OK as the source
]
BOARDS_FILE = os.path.join(ROOT, "job-boards.json")   # employer boards found and checked with tools/find-boards.py (see docs/job-sources.md)
BOARD_KINDS = ("greenhouse", "lever", "ashby", "smartrecruiters", "workable")       # plus "careerpage": an employer's own careers site (see _career_pages)
BOARD_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")    # a board's name in its system's address (Lever and Ashby allow dots: "thea.energy")


def _file_boards():
    """The verified employer boards in job-boards.json, as SOURCES entries, after the hand-picked ones (which keep their place and order)."""
    try:
        with open(BOARDS_FILE, encoding="utf-8") as f:
            rows = json.load(f).get("boards") or []
    except (OSError, ValueError):
        return []
    have = {(k, t.lower()) for k, t, _ in SOURCES}
    out = []
    for r in rows:
        k, t, n = r.get("kind"), str(r.get("token") or ""), str(r.get("name") or "").strip()
        if k == "careerpage":                        # an employer's own careers site: its sitemap must be a plain public https address
            sm = str(r.get("sitemap") or "")
            if not (BOARD_TOKEN_RE.match(t) and n and _public_https(sm)) or (k, t.lower()) in have:
                continue
            CAREER_PAGES[t] = sm
        elif not (k in BOARD_KINDS and BOARD_TOKEN_RE.match(t) and ".." not in t and n and (k, t.lower()) not in have):
            continue
        have.add((k, t.lower()))
        out.append((k, t, n))
    return out


CAREER_PAGES = {}                # careerpage token -> the sitemap of the employer's careers site (from job-boards.json)


class NotPublic(OSError):
    """A careers site's address (or a redirect from it) that is not a public https address: refused before anything is sent."""


class NoAddress(OSError):
    """A name that does not resolve (perhaps only for now): nothing was sent. Not the same as NotPublic, so the dead-link check does not
    count a DNS hiccup as a dead page."""


def _public_ips(host, port=443):
    """Every address `host` has, in the order to try them, when all of them are public; NotPublic otherwise (private, loopback,
    link-local such as the cloud metadata address 169.254.169.254, shared 100.64/10, reserved, multicast, or a name that does not resolve)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as e:
        raise NoAddress("%s does not resolve" % host) from e
    out = []
    for info in infos:
        raw = str(info[4][0]).split("%")[0]
        a = ipaddress.ip_address(raw)
        if a.version == 6 and a.ipv4_mapped:
            a = a.ipv4_mapped
        if not a.is_global or a.is_multicast:
            raise NotPublic("%s is not a public address" % host)
        if raw not in out:
            out.append(raw)
    if not out:
        raise NoAddress("%s does not resolve" % host)
    return out


def _public_ip(host, port=443):
    """The first address to try for `host` (see _public_ips)."""
    return _public_ips(host, port)[0]


class _PublicConnect:
    """A connection that looks the name up once, refuses it unless every address is public (_public_ips), and connects to those very
    addresses (an https certificate is still checked against the name), so a name that answers differently a moment later changes nothing."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._create_connection = self._connect_public

    def _connect_public(self, address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
        if self._tunnel_host:                       # through a proxy: the proxy connects, but the site's own name must still be public
            _public_ip(self._tunnel_host, self._tunnel_port or 443)
            return socket.create_connection(address, timeout, source_address)
        err = None
        for ip in _public_ips(address[0], address[1]):    # each checked address in turn, as socket.create_connection would (IPv6, then IPv4)
            try:
                return socket.create_connection((ip, address[1]), timeout, source_address)
            except OSError as e:
                err = e
        raise err


class _PublicHTTPSConnection(_PublicConnect, http.client.HTTPSConnection):
    pass


class _PublicHTTPConnection(_PublicConnect, http.client.HTTPConnection):
    pass


class _PublicHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_PublicHTTPSConnection, req, context=self._context)


class _PublicHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_PublicHTTPConnection, req)


class RedirectRefused(urllib.error.HTTPError):
    """A redirect to an address that is not allowed (see _PublicRedirect): it was not followed."""


class _PublicRedirect(urllib.request.HTTPRedirectHandler):
    """A careers site's redirect is followed only to a public https address (the same rules as its first address), every hop; with
    http_ok (the dead-link check) also to a public http one. urllib's own cap on redirects (10) still applies."""
    http_ok = False

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not (_public_link(newurl) if self.http_ok else _public_https(newurl)):
            raise RedirectRefused(req.full_url, code, "a redirect to an address that is not public was not followed", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _PublicLinkRedirect(_PublicRedirect):
    http_ok = True


def _public_link(url):
    """A public http or https address: a named host (no IP address, no localhost or .local / .internal name), no user:password, and no
    port but the scheme's own (80 or 443): the only kind the dead-link check opens or follows a redirect to."""
    try:
        u = urllib.parse.urlsplit(str(url or ""))
        port = u.port
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return (u.scheme in ("http", "https") and port in (None, 80 if u.scheme == "http" else 443) and bool(host) and "." in host and not u.username
            and not re.match(r"^[\d.]+$|^\[", host) and not host.endswith((".local", ".internal", ".localhost", "localhost")))


# every request to an employer's careers site (robots.txt, the sitemap, each job page), October 22 review: urllib's own opener followed a
# redirect anywhere (http, an internal address) and connected to whatever the name resolved to
_cp_open = urllib.request.build_opener(_PublicHTTPSHandler(), _PublicRedirect()).open
# the dead-link check of every job's apply page (_link_alive): the same rules, plain http allowed
_link_open = urllib.request.build_opener(_PublicHTTPSHandler(), _PublicHTTPHandler(), _PublicLinkRedirect()).open


def _public_https(url):
    """An https address on a named public host (no IP address, no localhost, no port, no user:password): the only kind a careers-site
    sitemap, or a page it lists, may make this server fetch."""
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return (u.scheme == "https" and bool(host) and "." in host and not u.port and not u.username and not re.match(r"^[\d.]+$|^\[", host)
            and not host.endswith((".local", ".internal", ".localhost", "localhost")))


FILE_SOURCES = _file_boards()
# the public lists (Simplify, Himalayas, Remote OK, CareerOneStop) stay last so the employer boards win the same-job rule
_tail = next(i for i, s_ in enumerate(SOURCES) if s_[0] == "remotive")
SOURCES = SOURCES[:_tail] + FILE_SOURCES + SOURCES[_tail:]
# ---------- human checks on the application pages (tools/scan-human-checks.py writes human-checks.json) ----------
# For each source: whether a sample of its application pages showed a human check (a captcha, or a challenge page) - none, sometimes,
# always, or unknown - the kind of page (html-form, js-app, redirect to another system, sign-in) and the day it was sampled. A job is never
# dropped for a check: its route label says "Ready, one tap" (the person sends it with one tap in the employer's page, where a check is
# theirs to answer) instead of "Ready".
HUMAN_CHECKS_FILE = os.environ.get("UAPLY_HUMAN_CHECKS_FILE") or os.path.join(ROOT, "human-checks.json")
ROUTE_READY, ROUTE_ONE_TAP = "Ready", "Ready, one tap"
LIKELY_SHARE = 0.8               # a hiring system whose sampled boards had a check this often: its boards not yet sampled are labelled one tap
_hc = {"sources": {}, "systems": {}, "sampled": "", "share": {}, "jobs": 0}


def load_human_checks(path=None):
    """Read the scan's results (a missing or broken file: nothing known, every route "Ready"). Kept small: a tuple per source."""
    src, systems, top = {}, {}, {}
    try:
        with open(path or HUMAN_CHECKS_FILE, encoding="utf-8") as f:
            top = json.load(f)
        for k, v in (top.get("sources") or {}).items():
            hc = v.get("humanCheck") if v.get("humanCheck") in ("none", "sometimes", "always") else "unknown"
            src[str(k)] = (hc, str(v.get("formKind") or "unknown"), str(v.get("sampled") or ""), int(v.get("pages") or 0),
                           int(v.get("withCheck") or 0), ",".join(sorted(v.get("kinds") or {})))
        for k, v in (top.get("systems") or {}).items():
            seen = sum(int(v.get(b) or 0) for b in ("none", "sometimes", "always"))
            systems[str(k)] = {"sources": int(v.get("sources") or 0), "none": int(v.get("none") or 0), "sometimes": int(v.get("sometimes") or 0),
                               "always": int(v.get("always") or 0), "unknown": int(v.get("unknown") or 0),
                               "likely": seen >= 3 and (int(v.get("sometimes") or 0) + int(v.get("always") or 0)) >= LIKELY_SHARE * seen}
    except (OSError, ValueError, TypeError, AttributeError):
        src, systems, top = {}, {}, {}
    _hc.update(sources=src, systems=systems, sampled=str(top.get("sampled") or ""), share=dict(top.get("share") or {}),
               jobs=int(top.get("jobs") or 0))
    return _hc


def _human(src):
    """The scan's tuple for a source: its own (kind/token), else its feed's (a feed that mixes employers is sampled as one), else None."""
    return _hc["sources"].get("%s/%s" % (src[0], src[1])) or _hc["sources"].get(src[0])


def route_label(src):
    """The route label of a source's jobs: "Ready, one tap" where a human check is likely on the employer's page, else "Ready"."""
    h = _human(src)
    if h and h[0] in ("sometimes", "always"):
        return ROUTE_ONE_TAP
    if (not h or h[0] == "unknown") and (_hc["systems"].get(src[0]) or {}).get("likely"):
        return ROUTE_ONE_TAP                     # not sampled yet (a new board), on a system where checks are the rule
    return ROUTE_READY


load_human_checks()

FILE_TTL = 2 * 3600            # a board from job-boards.json is read every 2 hours (the hand-picked ones every 30 minutes)

VIA = {"greenhouse": "%s on Greenhouse", "lever": "%s on Lever", "ashby": "%s on Ashby", "smartrecruiters": "%s on SmartRecruiters", "workable": "%s on Workable",
       "jobicy": "Jobicy", "muse": "The Muse", "usajobs": "USAJOBS", "remotive": "Remotive",
       "himalayas": "Himalayas", "remoteok": "Remote OK",
       # the CareerOneStop license: every page showing its data credits both the U.S. Department of Labor (ETA) and Minnesota DEED
       "careeronestop": "CareerOneStop (U.S. Department of Labor ETA and Minnesota DEED)",
       "careerpage": "%s careers site"}       # the short credit line each source's jobs carry (Simplify rows: see _normalize)
MULTI = ("jobicy", "muse", "usajobs", "simplify", "careeronestop", "himalayas")
HIMALAYAS_TYPES = {"intern": "Intern", "parttime": "Part Time"}       # the employment_type filter of Himalayas' search         # several feeds share one display name
# The two USAJOBS searches (documented at developer.usajobs.gov/api-reference/get-api-search; several values are joined with ';')
USAJOBS_AREAS = {"philadelphia": ("Philadelphia, Pennsylvania", "50"), "wilmington": ("Wilmington, Delaware", "40"),
                 "trenton": ("Trenton, New Jersey", "40"), "newark": ("Newark, New Jersey", "40"), "camden": ("Camden, New Jersey", "25")}
USAJOBS_QUERIES = {}
for _area, (_place_name, _radius) in USAJOBS_AREAS.items():
    _base = {"LocationName": _place_name, "Radius": _radius, "ResultsPerPage": "500", "Fields": "Full"}
    USAJOBS_QUERIES[_area] = dict(_base)
    USAJOBS_QUERIES[_area + "-students"] = dict(_base, HiringPath="student;graduates")
    USAJOBS_QUERIES[_area + "-parttime"] = dict(_base, PositionScheduleTypeCode="2")
USAJOBS_QUERIES["students"], USAJOBS_QUERIES["parttime"] = USAJOBS_QUERIES["philadelphia-students"], USAJOBS_QUERIES["philadelphia-parttime"]   # older names
# CareerOneStop searches: (keyword, place, radius in miles). Keyword "0" means every job around a city; a nationwide search needs a real keyword.
COS_PLACES = {"philadelphia": ("Philadelphia, PA", "50"), "wilmington": ("Wilmington, DE", "40"), "trenton": ("Trenton, NJ", "40"),
              "newark": ("Newark, NJ", "40"), "camden": ("Camden, NJ", "25")}
COS_SEARCHES = {"remote": ("remote", "US", "0")}
for _area, (_place_name, _radius) in COS_PLACES.items():
    COS_SEARCHES[_area] = ("0", _place_name, _radius)
    COS_SEARCHES[_area + "-internship"] = ("internship", _place_name, _radius)
    COS_SEARCHES[_area + "-parttime"] = ("part time", _place_name, _radius)
COS_DAYS, COS_PAGE = "7", "100"
COS_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
COS_TOKEN_RE = re.compile(r"^[A-Za-z0-9+/=_.-]{16,600}$")
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
US_CITIES = ("San Francisco|New York|Seattle|Austin|Boston|Chicago|Denver|Los Angeles|Atlanta|Portland|Philadelphia|Pittsburgh|Harrisburg|Allentown|"
             "King of Prussia|Conshohocken|Trenton|Princeton|Camden|Cherry Hill|Jersey City|Hoboken|Newark|Wilmington|Dover|Baltimore|"
             "Washington,? D\\.?C|Miami|Dallas|Houston|San Antonio|Phoenix|San Diego|San Jose|Las Vegas|Nashville|Charlotte|Raleigh|Orlando|Tampa|Detroit|"
             "Columbus|Cleveland|Cincinnati|Indianapolis|Minneapolis|St\\.? Louis|Kansas City|Salt Lake City|Sacramento|New Orleans|Silicon Valley|Bay Area")
STATE_CODE = dict(zip((n.lower() for n in STATE_NAMES.split("|")), STATES))      # "new jersey" -> "NJ"
assert len(STATE_CODE) == len(STATES) == 51

# ---------- where a job is: its place's point, for "near you" and the distance filter ----------
# us-places.tsv.gz (tools/make-us-places.py, from the Census Gazetteer): about 50,000 US places, read on first use and kept as one string
# with an index of line starts (about 1.5 MB), looked up by binary search. A job gets "geo": [lat, lng] when its place names a US city,
# town, borough, CDP or township with its state ("Cherry Hill, NJ", "El Segundo, California, United States", "Abilene TX",
# "US-PA-Philadelphia"), else its ZIP code's first three digits; a remote job, and a place with no state, get none (the app's own city
# list still tries those). On October 21, 2026 the app's 90-city list placed 6,824 of 12,570 on-site jobs.
PLACES_FILE = os.path.join(ROOT, "us-places.tsv.gz")
ZIP3_FILE = os.path.join(ROOT, "autofill_zip3.json")
_places = {}


def place_key(name, st):
    """A place's lookup key: "<state>|<name>" in lower case without punctuation, Saint, Fort and Mount as st, ft and mt."""
    n = re.sub(r"[.'\u2019`]", "", str(name or "").lower().replace("&", " and "))
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    n = re.sub(r"\bsaint\b", "st", re.sub(r"\bfort\b", "ft", re.sub(r"\bmount\b", "mt", n)))
    return "%s|%s" % (str(st or "").lower(), n) if n and st else ""


def _places_table():
    if "text" not in _places:
        import array
        import gzip
        try:
            with gzip.open(PLACES_FILE, "rt", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            text = ""
        off = array.array("I", [0])
        i = text.find("\n")
        while i >= 0 and i + 1 < len(text):
            off.append(i + 1)
            i = text.find("\n", i + 1)
        try:
            with open(ZIP3_FILE, encoding="utf-8") as f:
                zip3 = {k: tuple(v) for k, v in (json.load(f).get("zip3") or {}).items()}
        except (OSError, ValueError, AttributeError):
            zip3 = {}
        _places.update(text=text, off=off if text else array.array("I"), zip3=zip3)
    return _places


def _place_point(key):
    t = _places_table()
    text, off = t["text"], t["off"]
    lo, hi = 0, len(off)
    while lo < hi:
        mid = (lo + hi) // 2
        s = off[mid]
        e = text.find("\t", s)
        k = text[s:e]
        if k < key:
            lo = mid + 1
        elif k > key:
            hi = mid
        else:
            lat, lng = text[e + 1:text.find("\n", e)].split("\t")
            return [float(lat), float(lng)]
    return None


_ST_WORD = r"(?:%s|%s)" % ("|".join(STATES), STATE_NAMES)
_PLACE_RES = [re.compile(r"^(?:US|USA)[- ,]+(%s)[- ,]+([A-Za-z][A-Za-z .'-]+)$" % "|".join(STATES)),           # US-PA-Philadelphia
              re.compile(r"^([A-Za-z][A-Za-z .'-]*?)\s*,\s*(%s)\b" % _ST_WORD, re.I),                       # Cherry Hill, NJ (19103)
              re.compile(r"^([A-Za-z][A-Za-z .'-]*?)\s+(%s)$" % "|".join(STATES))]                            # Abilene TX


# a big city named without its state ("San Francisco", "New York City", "HQ: Chicago"): its state
BIG_CITIES = {"new york": "NY", "new york city": "NY", "nyc": "NY", "manhattan": "NY", "brooklyn": "NY", "san francisco": "CA", "los angeles": "CA",
              "chicago": "IL", "austin": "TX", "boston": "MA", "seattle": "WA", "san jose": "CA", "houston": "TX", "atlanta": "GA", "dallas": "TX",
              "denver": "CO", "philadelphia": "PA", "pittsburgh": "PA", "miami": "FL", "indianapolis": "IN", "phoenix": "AZ", "san diego": "CA",
              "detroit": "MI", "minneapolis": "MN", "nashville": "TN", "charlotte": "NC", "raleigh": "NC", "baltimore": "MD", "portland": "OR",
              "salt lake city": "UT", "las vegas": "NV", "columbus": "OH", "cleveland": "OH", "cincinnati": "OH", "st louis": "MO",
              "kansas city": "MO", "new orleans": "LA", "orlando": "FL", "tampa": "FL", "sacramento": "CA", "oakland": "CA", "palo alto": "CA",
              "mountain view": "CA", "sunnyvale": "CA", "menlo park": "CA", "santa monica": "CA", "irvine": "CA", "washington": "DC",
              "washington dc": "DC", "san antonio": "TX", "fort worth": "TX", "jersey city": "NJ", "hoboken": "NJ", "princeton": "NJ",
              "boulder": "CO", "cambridge": "MA", "bay area": "CA", "san francisco bay area": "CA", "sf bay area": "CA", "silicon valley": "CA"}
_BIG_AS = {"bay area": "san francisco", "san francisco bay area": "san francisco", "sf bay area": "san francisco", "silicon valley": "san jose",
           "new york city": "new york", "nyc": "new york", "manhattan": "new york", "washington dc": "washington"}


def job_geo(loc, remote=False):
    """[lat, lng] of a job's place (two decimals, about a kilometre), or None. See PLACES_FILE."""
    if remote or not loc:
        return None
    for part in re.split(r"\s*(?:;|\||/| or |\n)\s*", str(loc))[:4]:
        part = re.sub(r"\bD\.\s?C\.?", "DC", part.strip())
        part = re.sub(r"^(?:(?:United States|USA|US)\s*[-:,]\s*|HQ\s*:\s*|.*?,\s*(?=New York City\b))", "", part)     # "USA - Corona, CA"
        part = re.sub(r"\s+(?:Office|HQ|Headquarters|-\s*Greater Area)$", "", part.strip(), flags=re.I)
        part = re.sub(r"(?:,?\s*(?:United States(?: of America)?|USA|US))+$", "", part.strip()).strip(" ,-")
        big = re.sub(r"[^a-z ]", "", part.lower()).strip()
        big = re.sub(r",?\s*(?:ny|new york|ca|california)$", "", big).strip() if big.startswith(("new york city", "bay area", "san francisco bay area")) else big
        if big in BIG_CITIES:
            pt = _place_point(place_key(_BIG_AS.get(big, big), BIG_CITIES[big]))
            if pt:
                return pt
        m = re.match(r"^(%s)-([A-Za-z][A-Za-z .'-]+)" % "|".join(STATES), part)                 # "PA-Philadelphia, UNAVAILABLE"
        if m:
            part = "%s, %s" % (m.group(2), m.group(1))
        for i, rx in enumerate(_PLACE_RES):
            m = rx.search(part)
            if not m:
                continue
            st, city = (m.group(1), m.group(2)) if i == 0 else (m.group(2), m.group(1))
            st = st.upper() if len(st) == 2 else STATE_CODE.get(st.lower(), "")
            pt = _place_point(place_key(city, st)) if st else None
            if pt:
                return pt
        z = re.search(r"\b(\d{3})\d{2}(?:-\d{4})?\b", part)
        if z and z.group(1) in _places_table()["zip3"]:
            lat, lng = _places_table()["zip3"][z.group(1)]
            return [round(lat, 2), round(lng, 2)]
    return None


# bare state names count too ("New Jersey", "Remote - Delaware"), except Georgia, which is also a country
US_STATE_WORDS = "|".join(n for n in STATE_NAMES.split("|") if n != "Georgia")
US_RE = re.compile(r"United States|\bUSA\b|\bU\.S\.|\bUS\b|, (?:%s)\b|, (?:%s)\b|\b(?:%s)\b|\b(?:%s)\b|[a-z] (?:%s)$" % (
    "|".join(STATES), STATE_NAMES, US_STATE_WORDS, US_CITIES, "|".join(STATES)))       # the last: "Abilene TX" (Lever boards write places without the comma)
# "City, Region, CC" with a country code at the end (SmartRecruiters, Workable): "Munich, BY, DE" is Germany, "Mumbai, MH, IN" India
FOREIGN_CODE_RE = re.compile(r",\s*[A-Z]{2,3}\s*,\s*(?!US\b|USA\b)[A-Z]{2}\s*$")
FOREIGN_RE = re.compile(r"Germany|Mumbai|Bangalore|Bengaluru|Hyderabad|Chennai|Pune|Delhi|Gurugram|Gurgaon|Noida|Kolkata|Tel Aviv|Bogot|Medell|Manila|Cebu|Lagos|Nairobi|Warsaw|Krak|Prague|Bucharest|Kyiv|Istanbul|Cairo|Riyadh|Shanghai|Beijing|Shenzhen|Taipei|Bangkok|Jakarta|Kuala Lumpur|Ho Chi Minh|Hanoi|Buenos Aires|São Paulo|Sao Paulo|Mexico City|Guadalajara|Monterrey|Madrid|Barcelona|Milan|Rome|Zurich|Zürich|Geneva|Vienna|Stockholm|Copenhagen|Oslo|Helsinki|Brussels|Edinburgh|Manchester|Munich|Frankfurt|Hamburg|Cologne|Stuttgart|Düsseldorf|Dusseldorf|United Kingdom|\bUK\b|\bIndia\b|Canada|Ireland|France|Spain|Brazil|(?<!New )Mexico|Poland|Netherlands|Japan|Australia|New Zealand|\bANZ\b|Singapore|EMEA|APAC|Europe|LATAM|Latin America|Berlin|London|Dublin|Toronto|Vancouver|Montreal|Sydney|Amsterdam|Lisbon|Paris|Tokyo|Seoul|Hong Kong|Israel|Dubai|Philippines|Argentina|Colombia|Chile|Vietnam|Indonesia|Malaysia|Thailand|South Africa|Nigeria|Kenya|Egypt|Turkey|Romania|Ukraine|Czech|Portugal|Italy|Sweden|Norway|Denmark|Finland|Switzerland|Belgium|Austria", re.I)
EXPLICIT_US = re.compile(r"United States|\bUSA\b|\bU\.S\.|\bUS\b")


def _us_ok(loc, remote):
    """True when a posting can be done from the United States. A location is split on ';' and '|' (one posting can list
    several cities): any part that names the US, or is a US place with no foreign word, passes. A bare 'Remote' passes only
    when no foreign place is named. (', CA' is California; 'Toronto, ON, CA' is Canada and must not pass on that.)"""
    parts = [p for p in re.split(r"[;|]", loc) if p.strip()] or [loc]
    for p in parts:
        if FOREIGN_CODE_RE.search(p):
            continue
        if EXPLICIT_US.search(p) or (US_RE.search(p) and not FOREIGN_RE.search(p)):
            return True
    return bool(remote and not FOREIGN_RE.search(loc))
SAL_RE = re.compile(r"\$\s?(\d{2,3}(?:,\d{3})+|\d{2,3}\s?[kK])\s*(?:-|–|—|to)\s*\$?\s*(\d{2,3}(?:,\d{3})+|\d{2,3}\s?[kK])")
# an hourly range written out with its unit ("$18 - $22 per hour", "$28.10–$36.50/hr", "$17 to $19 an hour", "$20-25 hourly"). Pay is never
# guessed and never converted: an hourly figure stays hourly (salUnit "hour"), a yearly one yearly, and no unit means no pay on the card
HOURLY_RE = re.compile(r"\$\s?(\d{1,3}(?:\.\d{1,2})?)\s*(?:-|–|—|to)\s*\$?\s?(\d{1,3}(?:\.\d{1,2})?)\s*(?:USD\s*)?(?:/\s?(?:hr|hour)\b|per\s+hour\b|an\s+hour\b|hourly\b)", re.I)
YRS_RE = re.compile(r"(\d{1,2})\+?\s*(?:or more\s*)?(?:years|yrs)", re.I)

_cache = {}
_lock = threading.Lock()
_disk = {"loaded": False, "dirty": False, "filled": False}   # filled: a saved list was loaded, or the first fill of an empty disk is done
_load_lock = threading.Lock()
hide_errors = False                # serve.py sets this on a hosted server: the public job list then says "unavailable right now" instead of a raw network error
DISK_MAX_AGE = 24 * 3600          # never trust a saved copy older than a day
CACHE_VERSION = 13              # raise this whenever the rules for keeping or classifying postings change: older saved copies are then ignored


def _cache_file():
    """Where the last good postings are kept, so a restart or a new deploy shows jobs at once instead of waiting
    for every employer board (UAPLY_DATA_DIR on a host, ./data on this computer; never committed)."""
    return os.path.join(os.environ.get("UAPLY_DATA_DIR") or os.path.join(ROOT, "data"), "jobs-cache.json")


def _load_disk():
    with _load_lock:                   # a second request arriving meanwhile waits for the saved list instead of finding the cache empty
        if not _disk["loaded"]:
            _read_disk()
            _disk["loaded"] = True


class _Packed:
    """A source's kept jobs as compressed JSON (about a sixth of the memory of the dicts: descriptions, blurbs and all) plus their ids,
    so a lookup by id knows which source to unpack. At 7,000 jobs the dicts were about 25 MB; packed they are about 4."""
    __slots__ = ("z", "n", "ids")

    def __init__(self, jobs=None, z=None):
        if z is None:
            z = zlib.compress(json.dumps(jobs or [], separators=(",", ":")).encode("utf-8"), 6)
        self.z = z
        if jobs is None:
            jobs = self.jobs()
        self.n = len(jobs)
        self.ids = frozenset(j.get("id") for j in jobs if isinstance(j, dict))

    def jobs(self):
        return json.loads(zlib.decompress(self.z))


class _Entry(dict):
    """A cache entry: {"at", "status", "packed": _Packed}. Reading entry["jobs"] (or .get("jobs")) unpacks a fresh list each time, so
    every caller written for plain lists keeps working; a test may still store a plain {"jobs": [...]}."""
    def __missing__(self, key):
        if key == "jobs" and "packed" in self:
            return self["packed"].jobs()
        raise KeyError(key)

    def get(self, key, default=None):
        if key == "jobs" and not dict.__contains__(self, "jobs") and "packed" in self:
            return self["packed"].jobs()
        return dict.get(self, key, default)


def _entry(at, jobs, status):
    return _Entry(at=at, status=status, packed=_Packed(jobs))


def _count(c):
    """How many jobs a cache entry holds, without unpacking it."""
    return c["packed"].n if "packed" in c else len(c.get("jobs") or [])


def _has(c, job_id):
    return job_id in c["packed"].ids if "packed" in c else any(j.get("id") == job_id for j in c.get("jobs") or [])


def _find_job(job_id):
    """The cached feed job with this id, unpacking only the source that holds it (or None)."""
    with _lock:
        entries = list(_cache.values())
    for c in entries:
        if _has(c, job_id):
            for j in c["jobs"]:
                if j.get("id") == job_id:
                    return j
    return None


def _read_disk():
    try:
        with open(_cache_file(), encoding="utf-8") as f:
            saved = json.load(f)
        if not isinstance(saved, dict) or saved.pop("_version", None) != CACHE_VERSION:
            return
        now = time.time()
        with _lock:
            for key, v in saved.items():
                kind, token, name = key.split("|", 2)
                if not isinstance(v, dict) or now - float(v.get("at", 0)) >= DISK_MAX_AGE:
                    continue
                if isinstance(v.get("z"), str):          # saved packed (base64 of the compressed list): kept packed
                    packed = _Packed(z=base64.b64decode(v["z"]))
                elif isinstance(v.get("jobs"), list):    # an older plain save
                    packed = _Packed(v["jobs"])
                else:
                    continue
                _cache.setdefault((kind, token, name), _Entry(at=float(v["at"]), status=str(v.get("status", "")), packed=packed))
            if _cache:
                _disk["filled"] = True
    except Exception:
        pass


_save_lock = threading.Lock()      # one save at a time: background refreshes finish together, and two writers of the same .tmp file could
#                                    interleave into a broken saved list (or, on Windows, fail and lose the save)


def _save_disk():
    if _idreg["dirty"]:                 # the job ids handed out (see _claim_id), saved with the list
        with _save_lock:
            _save_ids()
    if not _disk["dirty"]:
        return
    with _save_lock:
        try:
            with _lock:
                if not _disk["dirty"]:
                    return
                # packed sources are written packed (no unpacking, no copy of every job); a plain test entry is written as it is
                snap = {"|".join(k): ({"at": v["at"], "status": v["status"], "z": base64.b64encode(v["packed"].z).decode("ascii")} if "packed" in v
                                      else {"at": v["at"], "jobs": v.get("jobs") or [], "status": v["status"]}) for k, v in _cache.items()}
                snap["_version"] = CACHE_VERSION
                _disk["dirty"] = False
            path = _cache_file()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            # one source at a time: json.dump of the whole list built the entire text in memory first (46 MB at the peak of a
            # fresh start with 80 sources, October 21, 2026); written this way the largest piece is one source's jobs
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("{")
                for i, (k, v) in enumerate(snap.items()):
                    f.write(("," if i else "") + json.dumps(k) + ":" + json.dumps(v))
                f.write("}")
            os.replace(tmp, path)
            _disk["saved_at"] = time.time()
        except Exception as e:                  # jobs still work from memory; only a restart would have to wait for every feed again
            _disk["dirty"] = True               # so the next refresh tries again
            sys.stderr.write("[uaply] could not save the job cache: %s: %s\n" % (type(e).__name__, str(e)[:200]))


MAX_FEED_BYTES = 40 * 1000 * 1000    # the largest board (Databricks) answered 9.9 MB on October 17, 2026; anything past this is refused, not parsed
FEED_PARALLEL = 8                    # boards read at the same time (3 until October 21, 2026, when boards were read whole). A board read whole cost about 4x its size while it was parsed (the
#                                      bytes, the text, then Python's objects), and memory a process has used is mostly not given back: reading all of
#                                      them at once took the live server (512 MB plan) from 45 MB to 275 MB, and to 491 MB when two rounds overlapped
#                                      (Oct 17). Employer boards are now read as they arrive (_get_items), a posting at a time, so a board costs a few
#                                      hundred KB however big it is; the smaller feeds and single postings still use _get.
_feed_slots = threading.BoundedSemaphore(FEED_PARALLEL)


HOST_PARALLEL = 6                    # requests to one feed's system at the same time, over all boards: with 12 boards at once each reading
#                                      descriptions 3 or 4 at a time, SmartRecruiters reset connections and Greenhouse answers slowed to minutes
HOST_PARALLEL_BY = {"boards-api.greenhouse.io": 10, "api.lever.co": 8, "api.ashbyhq.com": 8,   # systems served from a CDN take a few more
                    "www.workable.com": 2, "apply.workable.com": 2}                               # Workable answers 429 quickly
_host_sems, _host_sems_lock = {}, threading.Lock()


class _host_slot:
    """Holds one of HOST_PARALLEL places for the address's host while a request (or a streamed answer) is in progress."""
    def __init__(self, url):
        host = urllib.parse.urlsplit(url).hostname or ""
        with _host_sems_lock:
            self.sem = _host_sems.setdefault(host, threading.BoundedSemaphore(HOST_PARALLEL_BY.get(host, HOST_PARALLEL)))

    def __enter__(self):
        self.sem.acquire()
        return self

    def __exit__(self, *exc):
        self.sem.release()
        return False


def _get(url, headers=None, as_text=False, opener=None):
    """One feed answer, parsed as JSON (or the plain text with as_text=True), refused past MAX_FEED_BYTES. opener: _cp_open for a careers
    site (every hop a public https address), else urllib's own."""
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA, "Accept": "text/plain" if as_text else "application/json"}, **(headers or {})))
    started, parts, size = time.time(), [], 0
    with _host_slot(url), (opener or urllib.request.urlopen)(req, timeout=FEED_TIMEOUT) as r:
        while True:                                     # in parts, so a feed that trickles is stopped at FEED_DEADLINE
            part = r.read(STREAM_CHUNK)
            if not part:
                break
            parts.append(part)
            size += len(part)
            if size > MAX_FEED_BYTES:
                break
            if time.time() - started > FEED_DEADLINE:
                raise TimeoutError("the feed took longer than %d s; tried again at the next refresh" % FEED_DEADLINE)
    body = b"".join(parts)
    del parts
    if len(body) > MAX_FEED_BYTES:
        raise ValueError("the answer is larger than %d MB" % (MAX_FEED_BYTES // 1000000))
    text = body.decode("utf-8", "replace")
    del body                              # the bytes go before the parse starts: one copy fewer of a board held at the peak
    return text if as_text else json.loads(text)


FEED_TIMEOUT = 20                     # seconds one network read may wait (connect, or the next part of the answer)
FEED_DEADLINE = 180                   # seconds one feed answer may take in all (SpaceX's 32 MB board takes about 10 alone, 90+ with 500 boards being read): past that it is dropped,
#                                       its download slot goes to the next feed, the last good copy stays, and it is tried again 2 minutes later
STREAM_CHUNK = 256 * 1024              # how much of a board's answer is read from the network at a time
_DEC = json.JSONDecoder()
_WS = re.compile(r"[ \t\n\r]*")


def _get_items(url, key=None):
    """The postings of one board answer, one at a time, read from the network as they arrive: the items of the list under `key` in the
    top-level object ({"jobs": [...]}: Greenhouse, Ashby, Workable), or of the top-level list itself (key None: Lever). Only the part of
    the answer not yet worked through is held (a few hundred KB), instead of the whole answer, its text and every parsed posting at once:
    Carvana's 19 MB board cost about 75 MB that way. Past MAX_FEED_BYTES the answer is refused, as in _get."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    started = time.time()
    with _host_slot(url), urllib.request.urlopen(req, timeout=FEED_TIMEOUT) as r:
        dec = codecs.getincrementaldecoder("utf-8")("replace")
        st = {"buf": "", "pos": 0, "read": 0, "done": False}

        def more():
            if st["done"]:
                return False
            chunk = r.read(STREAM_CHUNK)
            st["read"] += len(chunk)
            if time.time() - started > FEED_DEADLINE:
                raise TimeoutError("the feed took longer than %d s; tried again at the next refresh" % FEED_DEADLINE)
            if st["read"] > MAX_FEED_BYTES:
                raise ValueError("the answer is larger than %d MB" % (MAX_FEED_BYTES // 1000000))
            if not chunk:
                st["done"] = True
                st["buf"] = st["buf"][st["pos"]:] + dec.decode(b"", final=True)
            else:
                st["buf"] = st["buf"][st["pos"]:] + dec.decode(chunk)       # what was worked through is dropped here
            st["pos"] = 0
            return True

        def skip_ws():
            while True:
                st["pos"] = _WS.match(st["buf"], st["pos"]).end()
                if st["pos"] < len(st["buf"]) or not more():
                    return

        def peek():
            skip_ws()
            return st["buf"][st["pos"]] if st["pos"] < len(st["buf"]) else ""

        def take(ch):
            if peek() != ch:
                raise ValueError("unexpected answer: wanted %r" % ch)
            st["pos"] += 1

        def value():
            skip_ws()
            while True:
                try:
                    v, end = _DEC.raw_decode(st["buf"], st["pos"])
                except ValueError:
                    if more():                         # most likely cut off by the end of the chunk: read on and try again
                        continue
                    raise
                if end == len(st["buf"]) and not st["done"] and isinstance(v, (int, float)):
                    more()                             # a number at the very end of the chunk may go on in the next one
                    continue
                st["pos"] = end
                return v

        def items():
            take("[")
            if peek() == "]":
                st["pos"] += 1
                return
            while True:
                yield value()
                c = peek()
                st["pos"] += 1
                if c == "]":
                    return
                if c != ",":
                    raise ValueError("unexpected answer in a list")

        if key is None:
            yield from items()
            return
        take("{")
        if peek() == "}":
            return
        while True:
            k = value()
            take(":")
            if k == key:
                if peek() == "[":
                    yield from items()
                else:
                    value()
                return                                 # what follows the list (meta, counts) is not needed
            value()                                    # a small value before the list (Ashby's apiVersion): read and dropped
            c = peek()
            st["pos"] += 1
            if c == "}":
                return
            if c != ",":
                raise ValueError("unexpected answer in an object")


KEY_RE = re.compile(r"^[A-Za-z0-9+/=_.-]{16,200}$")      # what a feed's API key looks like (USAJOBS: about 44 letters, digits, + / =)


def feed_keys():
    """The job feeds' own API keys the owner pasted on the setup page ('feed_keys' in uaply-config.json, or in UAPLY_CONFIG_JSON on a
    host): {"usajobs": ..., "usajobs_email": ..., "muse": ...}. Only well-formed values are returned. These are secrets: never logged, never
    sent to a browser, never shown on a page (see _scrub).
    On a host the USAJOBS key can also be its own variable, UAPLY_USAJOBS_KEY (with UAPLY_USAJOBS_EMAIL, the address the key was requested
    with), so it is pasted once in the dashboard instead of inside the UAPLY_CONFIG_JSON line. A well-formed variable wins over feed_keys."""
    cfg = _cfg()
    k = cfg.get("feed_keys") if isinstance(cfg.get("feed_keys"), dict) else {}
    out = {n: k[n].strip() for n in ("usajobs", "muse") if isinstance(k.get(n), str) and KEY_RE.match(k[n].strip())}
    env_key = (os.environ.get("UAPLY_USAJOBS_KEY") or "").strip()
    if KEY_RE.match(env_key):
        out["usajobs"] = env_key
    EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")   # one plain address (the module-level one was removed as unused)
    mail = next((m.strip() for m in (os.environ.get("UAPLY_USAJOBS_EMAIL"), k.get("usajobs_email"), cfg.get("owner_copy"))
                 if isinstance(m, str) and EMAIL_RE.fullmatch(m.strip())), "")
    out["usajobs_email"] = mail or USAJOBS_EMAIL
    cid, ctok = (os.environ.get("UAPLY_COS_USER_ID") or "").strip(), (os.environ.get("UAPLY_COS_TOKEN") or "").strip()
    if COS_ID_RE.match(cid) and COS_TOKEN_RE.match(ctok):          # both, well formed, or CareerOneStop stays off ("no key")
        out["cos_user"], out["cos_token"] = cid, ctok
    return out


def _scrub(text):
    """Error text with every feed key taken out, so a key can never reach the server's log or the job list's status line."""
    keys = feed_keys()                     # read once (it reads the settings file), not once per key
    for n in ("usajobs", "muse", "cos_token", "cos_user"):
        v = keys.get(n)
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
    s = html.unescape(html.unescape(s or ""))      # a feed's text may be escaped twice ("&amp;lt;b&amp;gt;")
    # a link that emails someone ("send your resume <a href="mailto:jobs@acme.com">here</a>") keeps its address in the text, so the
    # posting's own "apply by email" sentence can be read (apply_address); a link whose words are the address already is left as it is
    s = MAILTO_LINK.sub(lambda m: m.group(2) if "@" in m.group(2) else "%s (%s)" % (m.group(2), urllib.parse.unquote(m.group(1))), s)
    s = re.sub(r"<[^>]+>", " ", s)                 # tags are taken out after the last unescape, so none can come back from an entity
    return re.sub(r"\s+", " ", s).strip()[:20000]


MAILTO_LINK = re.compile(r"""<a\b[^>]*?\bhref\s*=\s*["']?mailto:([^"'?>\s]{3,254})[^>]*>(.*?)</a\s*>""", re.I | re.S)

# ---------- apply by email (Saif, October 23, 2026): the posting's own "send your resume to" address ----------
# A posting that asks for applications by email names the employer's own channel for them. This server takes an address from a
# posting only when all of these hold (docs/apply-by-email.md); the address is then the job's "contact" and its apply is "email":
#   - it stands in a sentence that asks for applications by email ("send your resume to", "email your CV to", "applications should be
#     sent to", "to apply, email"), as the place to send them (right after "to", "at", "email" or a colon), and the sentence is not about
#     accommodations, questions, agencies, privacy, fraud or "do not";
#   - its domain is the employer's own: the domain's name (the part before .com, .org, .co.uk) is the company's name or the board's
#     name, or the domain of the employer's own careers page; a free mailbox (gmail.com and the like) or a hiring system's never is;
#   - the posting names only one such address (two different ones: neither is used).
# Nothing here sends anything. uaply_api.submit emails an application to the address only for a swipe right, with every safeguard of the
# email route (signed in and verified, the consent record, one application per person and job, the daily limits, the bounce list).
APPLY_VERB = re.compile(r"\b(?:send|e-?mail|submit|forward|direct)(?:ed|ing)?\b[^.!?;]{0,90}?\b(?:resumes?|résumés?|cvs?|c\.v\.|applications?|cover letters?|portfolios?)\b"
                        r"|\bapplications?\s+(?:should|must|can|may|will)\s+be\s+(?:sent|e-?mailed|submitted|directed|forwarded)\b"
                        r"|\bto apply\b|\bapply\s+(?:by|via|through)\s+e-?mail\b"
                        r"|\binterested (?:candidates|applicants|parties|individuals)\b[^.!?;]{0,60}\b(?:send|e-?mail|submit|forward)\b", re.I)
APPLY_NOT = re.compile(r"accommodat|disabilit|reasonable adjust|\bassist|do not|don'?t|not accept|\bno (?:phone )?calls|\bno e-?mails|unsolicited|agenc|"
                       r"question|inquir|enquir|privacy|personal (?:data|information)|data protection|unsubscribe|fraud|scam|phish|\bverif|"
                       r"\breport|complain|payroll|\bw-?2\b|referr|investor|\bpress\b|\bmedia\b", re.I)
APPLY_OBJECT = re.compile(r"(?:\bto|\bat|:|\be-?mail(?:ing)?|\bsend|\bcontact|\bvia|\bwrite|\bhere)\s*[(\[]?\s*(?:us\s+at\s*|our (?:recruiter|team|hr team|hiring team)\s+at\s*)?$", re.I)
EMAIL_IN_TEXT = re.compile(r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+)")
APPLY_LOCAL_NOT = re.compile(r"^(?:no-?reply|do-?not-?reply|privacy|accommodations?|ada|eeo|eeoc|abuse|security|legal|press|media|unsubscribe|support|help|billing|payroll|benefits)$", re.I)
FREE_MAIL = re.compile(r"(?:^|\.)(?:gmail|googlemail|yahoo|ymail|outlook|hotmail|live|msn|aol|icloud|me|mac|proton|protonmail|pm|gmx|mail|zoho|yandex|comcast|verizon|att|sbcglobal|"
                       r"bellsouth|cox|charter|earthlink|optonline|qq|163|rocketmail|fastmail|hey|tutanota|duck|mailinator)\.[a-z.]+$", re.I)
NOT_EMPLOYER_HOST = re.compile(r"(?:^|\.)(?:greenhouse\.io|lever\.co|ashbyhq\.com|smartrecruiters\.com|workable\.com|myworkdayjobs\.com|workday\.com|icims\.com|jobvite\.com|"
                               r"bamboohr\.com|recruitee\.com|breezy\.hr|applytojob\.com|paylocity\.com|ultipro\.com|adp\.com|taleo\.net|successfactors\.com|oraclecloud\.com|"
                               r"usajobs\.gov|remotive\.com|himalayas\.app|remoteok\.com|jobicy\.com|themuse\.com|careeronestop\.org|simplify\.jobs|linkedin\.com|indeed\.com|"
                               r"ziprecruiter\.com|glassdoor\.com|uaply\.net|example\.com|example\.org)$", re.I)
CO_FILLER = re.compile(r"\b(?:inc|incorporated|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|group|holdings?|plc|lp|llp|pllc|pc|the|usa|us|na)\b\.?", re.I)
_SUFFIX2 = {"co", "com", "org", "net", "ac", "gov", "edu", "ltd", "plc", "or", "ne"}


def _domain_name(host):
    """The name a domain was registered under: "acme" for jobs.acme.com and for careers.acme.co.uk ('' for a bare name)."""
    parts = [x for x in str(host or "").lower().strip(".").split(".") if x]
    if len(parts) < 2:
        return ""
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in _SUFFIX2:
        return parts[-3]
    return parts[-2]


def _alnum(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def employer_domain(addr_domain, company, board="", page_url=""):
    """True when an email domain is the employer's own (see the rules above apply_address)."""
    d = str(addr_domain or "").lower()
    if not d or FREE_MAIL.search(d) or NOT_EMPLOYER_HOST.search(d):
        return False
    label = _alnum(_domain_name(d))
    if len(label) < 2:
        return False
    whole, short = _alnum(company), _alnum(CO_FILLER.sub(" ", str(company or "")))
    names = {x for x in (whole, short, _alnum(board)) if len(x) >= 2}
    if label in names:
        return True
    try:
        page = (urllib.parse.urlsplit(page_url or "").hostname or "").lower()
    except ValueError:
        page = ""
    if page and not NOT_EMPLOYER_HOST.search(page) and _alnum(_domain_name(page)) == label:
        return True                                  # the employer's own careers page is on this domain
    # "Acme Robotics" and acmerobotics-careers.com, "Penn Medicine" and pennmedicine.org: one name starts the other, at 4 letters or more
    return any(len(n) >= 4 and len(label) >= 4 and (label.startswith(n) or n.startswith(label)) for n in names)


def apply_address(text, company, board="", page_url=""):
    """The address a posting asks applications to be emailed to, or '' (see the rules above). Nothing is sent from here."""
    t = str(text or "")
    if "@" not in t:
        return ""
    found = set()
    for m in EMAIL_IN_TEXT.finditer(t):
        addr = m.group(1).rstrip(".-").lower()
        local, _, dom = addr.partition("@")
        if not dom or "." not in dom or APPLY_LOCAL_NOT.match(local) or len(addr) > 254:
            continue
        before = t[max(0, m.start() - 300):m.start()]
        cut = max(before.rfind(". "), before.rfind("! "), before.rfind("? "), before.rfind("; "))
        sentence = before[cut + 1:] if cut >= 0 else before
        after = t[m.end():m.end() + 160]
        end = re.search(r"[.!?;](?:\s|$)", after)
        tail = after[:end.start()] if end else after
        if not APPLY_VERB.search(sentence) or not APPLY_OBJECT.search(sentence[-48:]) or APPLY_NOT.search(sentence + " " + tail):
            continue
        if not employer_domain(dom, company, board, page_url):
            continue
        found.add(addr)
    return found.pop() if len(found) == 1 else ""


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


def _hour_pay(lo, hi):
    """An hourly range as the posting gives it ([18.0, 22.5]), or None. Never a yearly figure made from it."""
    try:
        lo, hi = float(lo), float(hi)
    except (TypeError, ValueError):
        return None
    return [round(lo, 2), round(hi, 2)] if 5 <= lo < hi <= 500 else None


def _hourly(*texts):
    for t in texts:
        m = HOURLY_RE.search(t or "")
        if m:
            h = _hour_pay(m.group(1), m.group(2))
            if h:
                return h
    return None


def _iter_raw(kind, token, name):
    """The raw postings of one board, one at a time: dicts with id, title, company, loc, remote, text, url, salary_text. A generator, so a
    board's postings are worked through as they are read instead of all being held (each with up to 20,000 characters of text) first."""
    if kind == "greenhouse":
        # The list without descriptions is about an eighth of the size (SpaceX: 2.6 MB instead of 32): a posting's description is read
        # on its own (_gh_fill) only for the ones that will be kept, once, and again only when the posting's updated_at changes.
        for j in _get_items("https://boards-api.greenhouse.io/v1/boards/%s/jobs" % token, "jobs"):
            yield dict(id=j["id"], title=j["title"], company=j.get("company_name") or name,
                       loc=(j.get("location") or {}).get("name", ""), remote=None,
                       text="", url=j["absolute_url"], salary_text="",
                       posted=_ts(j.get("first_published") or j.get("updated_at")), updated=_ts(j.get("updated_at")), emp=_gh_emp(j),
                       lazy=(token, str(j["id"]), str(j.get("updated_at") or "")))
    elif kind == "lever":
        for j in _get_items("https://api.lever.co/v0/postings/%s?mode=json" % token):
            cat = j.get("categories") or {}
            yield dict(id=j["id"], title=j["text"], company=name, loc=cat.get("location", "") or "",
                       remote=(j.get("workplaceType") == "remote") or None,
                       text=_text((j.get("descriptionPlain") or "") + " " + (j.get("additionalPlain") or "")),
                       url=j["hostedUrl"], salary_text="", posted=_ts(j.get("createdAt")), emp=cat.get("commitment"),
                       fallback=(cat.get("team") or cat.get("department") or "").strip() or None)
    elif kind == "ashby":
        for j in _get_items("https://api.ashbyhq.com/posting-api/job-board/%s" % token, "jobs"):
            if j.get("isListed") is False:
                continue
            yield dict(id=j["id"], title=j["title"], company=name, loc=j.get("location", "") or "",
                       remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote" or None,
                       text=_text(j.get("descriptionPlain") or j.get("descriptionHtml")),
                       url=j["jobUrl"], salary_text="", posted=_ts(j.get("publishedAt")), emp=j.get("employmentType"),
                       fallback=(j.get("department") or j.get("team") or "").strip() or None)
    elif kind == "workable":
        # Workable's public jobs feed (no key): https://www.workable.com/api/accounts/{subdomain}?details=true lists the account's published jobs
        # with their descriptions (help.workable.com/hc/en-us/articles/115012771647, "Build a custom careers page using Workable's API"). It may
        # answer through apply.workable.com/api/v1/widget/accounts/{subdomain}, the same list. The posting id Workable's API takes is the shortcode.
        for j in _get_items("https://www.workable.com/api/accounts/%s?details=true" % urllib.parse.quote(token, safe=""), "jobs"):
            if not isinstance(j, dict) or not j.get("shortcode") or not j.get("title"):  # "state" is the region here, not a status: the feed lists published jobs only
                continue
            locs = [l for l in (j.get("locations") or []) if isinstance(l, dict) and not l.get("hidden")]
            loc = "; ".join(p for p in (", ".join(x for x in (l.get("city"), l.get("region"), l.get("country")) if x) for l in locs) if p)
            loc = loc or ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)      # one place per posting in older replies
            yield dict(id=j["shortcode"], title=j["title"], company=name, loc=loc, remote=True if j.get("telecommuting") is True else None,
                       text=_text(j.get("description") or "") + " " + _text(j.get("requirements") or ""), url=j.get("url") or j.get("shortlink") or "",
                       salary_text="", posted=_ts(j.get("published_on") or j.get("created_at")), emp=j.get("employment_type"),
                       force_type="parttime" if re.search(r"part", j.get("employment_type") or "", re.I) else
                                  ("internship" if re.search(r"intern", j.get("employment_type") or "", re.I) else None))
    elif kind == "remotive":
        for j in _get("https://remotive.com/api/remote-jobs?category=%s&limit=60" % token).get("jobs", []):
            loc = j.get("candidate_required_location") or ""
            if not re.search(r"usa|united states|worldwide|americas|north america|anywhere", loc, re.I):
                continue
            yield dict(id=j["id"], title=j["title"], company=j["company_name"], loc="Remote (%s)" % loc, remote=True,
                       text=_text(j.get("description")) + " " + " ".join(j.get("tags") or []),
                       url=j["url"], salary_text=j.get("salary") or "", posted=_ts(j.get("publication_date")), emp=j.get("job_type"))
    elif kind == "jobicy":
        data = _get("https://jobicy.com/api/v2/remote-jobs?count=30&geo=usa&industry=%s" % token)
        for j in data.get("jobs", []):
            sal = None
            lo, hi = j.get("salaryMin"), j.get("salaryMax")
            if j.get("salaryPeriod") == "yearly" and j.get("salaryCurrency") == "USD" and isinstance(lo, (int, float)) \
                    and isinstance(hi, (int, float)) and 20000 <= lo < hi <= 600000:
                sal = [int(lo), int(hi)]
            hour = _hour_pay(lo, hi) if j.get("salaryPeriod") == "hourly" and j.get("salaryCurrency") == "USD" else None
            yield dict(id=j["id"], title=j["jobTitle"], company=j["companyName"], sal_unit="hour" if hour else "",
                       loc="Remote (%s)" % re.sub(r"\s+", " ", j.get("jobGeo") or "USA").strip(), remote=True,
                       text=_text(j.get("jobDescription")), url=j["url"], salary_text="", sal=hour or sal,
                       posted=_ts(j.get("pubDate")), emp=j.get("jobType"),
                       fallback=(j.get("jobIndustry") or [None])[0])
    elif kind == "muse":
        key = feed_keys().get("muse")         # registered key (The Muse: required beyond testing; 3,600 requests an hour instead of 500)
        for page in (1, 2):
            data = _get("https://www.themuse.com/api/public/jobs?page=%d&level=%s" % (page, urllib.parse.quote(token)) +
                        ("&api_key=%s" % urllib.parse.quote(key, safe="") if key else ""))
            for j in data.get("results", []):
                locs = [l.get("name", "") for l in j.get("locations", [])]
                loc = ", ".join(locs[:2]) + (" +%d more" % (len(locs) - 2) if len(locs) > 2 else "")
                cats = [c.get("name") for c in j.get("categories", []) if c.get("name")]
                yield dict(id=j["id"], title=j["name"], company=j["company"]["name"], loc=loc or "Not listed",
                           remote=any(re.search("remote|flexible", l, re.I) for l in locs) or None,
                           text=_text(j.get("contents")), url=j["refs"]["landing_page"], salary_text="",
                           fallback=cats[0] if cats else None, posted=_ts(j.get("publication_date")), emp=j.get("levels"),
                           force_type="internship" if token == "Internship" else None)
    elif kind == "himalayas":
        # https://himalayas.app/api : link to the job on Himalayas, use applicationLink unchanged, show only on our own app, remove expired jobs
        now = time.time()
        for page in (1, 2, 3):
            country, _, only = token.partition("-")
            data = _get("https://himalayas.app/jobs/api/search?country=%s&page=%d" % (urllib.parse.quote(country, safe=""), page) +
                        ("&employment_type=%s" % urllib.parse.quote(HIMALAYAS_TYPES[only], safe="") if only in HIMALAYAS_TYPES else ""))
            for j in data.get("jobs") or []:
                if not isinstance(j, dict) or not j.get("title") or not str(j.get("guid") or "").startswith("https://himalayas.app/"):
                    continue
                if isinstance(j.get("expiryDate"), (int, float)) and j["expiryDate"] < now:
                    continue
                where = [c for c in (j.get("locationRestrictions") or []) if isinstance(c, str)]
                if where and not any(re.search(r"United States|\bUSA?\b", c) for c in where):
                    continue
                sal = None
                lo, hi = j.get("minSalary"), j.get("maxSalary")
                if j.get("currency") == "USD" and j.get("salaryPeriod") in ("annual", "yearly") and isinstance(lo, (int, float)) \
                        and isinstance(hi, (int, float)) and 20000 <= lo < hi <= 600000:
                    sal = [int(lo), int(hi)]
                hour = _hour_pay(lo, hi) if j.get("currency") == "USD" and j.get("salaryPeriod") in ("hour", "hourly") else None
                link = j.get("applicationLink") if str(j.get("applicationLink") or "").startswith("https://") else j["guid"]
                yield dict(id=j["guid"], title=j["title"], company=j.get("companyName") or "Himalayas", loc="Remote (%s)" % (", ".join(where[:3]) or "Worldwide"),
                           remote=True, text=_text(j.get("description") or j.get("excerpt")), url=link, salary_text="", sal=hour or sal, sal_unit="hour" if hour else "",
                           posted=_ts(j.get("pubDate")), emp=j.get("employmentType"),
                           fallback=next((c.replace("-", " ") for c in (j.get("categories") or []) if isinstance(c, str)), None))
    elif kind == "remoteok":
        # https://remoteok.com/api : the first entry is the legal notice (link back to the job on Remote OK, name Remote OK as the source)
        for j in _get("https://remoteok.com/api")[1:]:
            if not isinstance(j, dict) or not j.get("position") or not str(j.get("url") or "").lower().startswith("https://remoteok.com/"):
                continue
            sal = None
            lo, hi = j.get("salary_min"), j.get("salary_max")
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and 20000 <= lo < hi <= 600000:
                sal = [int(lo), int(hi)]
            yield dict(id=j.get("id") or j["url"], title=j["position"], company=j.get("company") or "Remote OK",
                       loc="Remote" + (" (%s)" % j["location"] if j.get("location") else ""), remote=True,
                       text=_text(j.get("description")) + " " + " ".join(t for t in (j.get("tags") or []) if isinstance(t, str)),
                       url="https://remoteok.com/" + str(j["url"]).split("/", 3)[3], salary_text="", sal=sal,
                       posted=_ts(j.get("date")), fallback=next((t for t in (j.get("tags") or []) if isinstance(t, str)), None))
    elif kind == "simplify":
        yield from _simplify(token, name)
    elif kind == "careerpage":
        yield from _career_pages(token, name)
    elif kind == "careeronestop":
        yield from _careeronestop(token)
    elif kind == "usajobs":
        yield from _usajobs(token)
    elif kind == "smartrecruiters":
        yield from _smartrecruiters(token, name)


def _fetch_raw(kind, token, name):
    """All raw postings of one board as a list (tools and tests; the job list itself reads them one at a time through _iter_raw)."""
    return list(_iter_raw(kind, token, name))


_sr_desc = {}            # (company, posting id) -> (when its description was read, its releasedDate): each is read once a day at most
_REUSE = object()        # "the job the last read made from this posting still stands" (see _prev_jobs)


def _prev_jobs(src):
    """The jobs a source's last read made, by id (unpacked from its packed copy): an unchanged SmartRecruiters posting or careers-site
    page is made into the same job again without reading it again. Holding each description for that cost 10 MB at 20,000 jobs
    (October 22, 2026); the jobs are already held, packed."""
    with _lock:
        c = _cache.get(src)
    try:
        return {j["id"]: j for j in c["jobs"]} if c else {}
    except (KeyError, TypeError, ValueError):
        return {}


def _sr_detail(token, pid, released, reusable=False):
    """One posting's full record (description, pay), or _REUSE when the posting was read in the last SR_DESC_TTL, was not re-released
    and its job from that read is at hand (`reusable`)."""
    key = (token, pid)
    with _lock:
        c = _sr_desc.get(key)
    if reusable and c and c[1] == released and time.time() - c[0] < SR_DESC_TTL:
        return _REUSE
    at = time.time()
    try:
        d = _get("https://api.smartrecruiters.com/v1/companies/%s/postings/%s" % (urllib.parse.quote(token, safe=""), urllib.parse.quote(pid, safe="")))
        if isinstance(d, dict):                  # keep only what _smartrecruiters reads (120 full records stayed in memory all day before)
            secs = ((d.get("jobAd") or {}).get("sections")) or {}
            # as plain text (the markup was about 40% of what was held: 184 boards x 24 descriptions, October 21)
            d = {"jobAd": {"sections": {k: {"text": _text((secs.get(k) or {}).get("text") or "")[:SR_TEXT]} for k in ("jobDescription", "qualifications", "additionalInformation")}},
                 "compensation": d.get("compensation") or {}}
    except Exception:
        d = _REUSE if reusable else None         # keep the last job if this read fails, and try again at the next hourly refresh
        at = time.time() - SR_DESC_TTL + TTL["smartrecruiters"] - 60
    with _lock:
        _sr_desc[key] = (at, released)
    return d


def _z(obj):
    return zlib.compress(json.dumps(obj, separators=(",", ":")).encode("utf-8"), 6) if obj is not None else None


def _unz(blob):
    return json.loads(zlib.decompress(blob)) if blob is not None else None


SR_WHOLE = ("CityofPhiladelphia",)    # public bodies whose whole list is kept (up to KEEP); any other SmartRecruiters company is an employer board
SR_TEXT = 2500                         # characters kept of each description section (skills, pay and the summary are read from the start)
SR_BOARD_READ = 24                     # an employer board: at most this many US postings get their description read (once a day each): its 14 plus 10 tri-state


def _smartrecruiters(token, name):
    """A company's public SmartRecruiters postings: the list page by page (100 at a time, until totalFound, at most KEEP postings),
    then each posting's own record for its description. Shapes as seen on the live API (October 16, 2026). For a company that is not a
    public body (Equinox, Red Bull ...), postings outside the US are left out before any description is read, and at most SR_BOARD_READ
    descriptions are read (it keeps 14 plus tri-state extras, like any employer board)."""
    whole = token in SR_WHOLE
    cap = KEEP["smartrecruiters"]
    base = "https://api.smartrecruiters.com/v1/companies/%s/postings" % urllib.parse.quote(token, safe="")
    items, offset = [], 0
    while len(items) < cap:
        # an employer board: one page of its US postings only (SmartRecruiters filters by country), not every country's first 120
        page = _get("%s?limit=100&offset=%d" % (base, offset) + ("" if whole else "&country=us"))
        if not whole:
            items += page.get("content") or []
            break
        got = page.get("content") or []
        items += got
        offset += len(got)
        if not got or offset >= int(page.get("totalFound") or 0):
            break
    items = [p for p in items if isinstance(p, dict) and p.get("id")]
    if not whole:                                   # US postings only, Pennsylvania, New Jersey and Delaware ones first
        items = [p for p in items if ((p.get("location") or {}).get("country") or "us").lower() == "us"]
        items.sort(key=lambda p: ((p.get("location") or {}).get("region") or "").upper() not in ("PA", "NJ", "DE"))
        items = items[:SR_BOARD_READ]
    items = items[:cap]
    prev = _prev_jobs(("smartrecruiters", token, name))
    with ThreadPoolExecutor(max_workers=4) as ex:                # four at a time: gentle on their API, and quick enough
        details = list(ex.map(lambda p: _sr_detail(token, str(p["id"]), p.get("releasedDate") or "",
                                                   _jid("smartrecruiters", p["id"]) in prev), items))
    out = []
    for p, d in zip(items, details):
        again = prev.get(_jid("smartrecruiters", p["id"])) if d is _REUSE else None
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
        hour = _hour_pay(comp.get("min"), comp.get("max")) if comp.get("currency") == "USD" and comp.get("period") == "HOURLY" else None
        kind_label = ((p.get("typeOfEmployment") or {}).get("label") or "").lower()
        force = "internship" if "intern" in kind_label else ("parttime" if "part" in kind_label else None)
        dept = re.split(r"\s[-–—]\s", (p.get("department") or {}).get("label") or "")[0].strip()      # "Law Department – Tax Unit" -> "Law Department"
        func = (p.get("function") or {}).get("label") or ""
        fallback = dept or (func if func.lower() != "other" else "") or (p.get("industry") or {}).get("label") or None
        out.append(dict(id=p["id"], title=(p.get("name") or "").strip(), company=(p.get("company") or {}).get("name") or name, country=L.get("country") or "us",
                        loc=loc or "Not listed", remote=True if L.get("remote") else None,
                        text=_text(text) or (p.get("name") or ""), url="https://jobs.smartrecruiters.com/%s/%s" % (token, p["id"]),
                        salary_text="", sal=hour or sal, sal_unit="hour" if hour else "", posted=_ts(p.get("releasedDate")), fallback=fallback, force_type=force, emp=kind_label,
                        ats_id=str(p.get("uuid") or "")))     # the Application API addresses a posting by its uuid, not by its number
        if again:
            out[-1]["_prev"] = again                              # unchanged since the last read: the same job again
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
        sal, sal_text, sal_unit = None, "", ""
        try:
            lo, hi = float(pay.get("MinimumRange") or 0), float(pay.get("MaximumRange") or 0)
            money = lambda n: "{:,.0f}".format(n) if n >= 1000 else "{:,.2f}".format(n)   # noqa: E731  (yearly in dollars, hourly with cents)
            sal_text = ("$%s - $%s %s" % (money(lo), money(hi), pay.get("Description") or "")).strip() if hi else ""
            if pay.get("RateIntervalCode") == "PA" and 20000 <= lo < hi <= 600000:
                sal = [int(lo), int(hi)]                                   # yearly pay as yearly
            elif pay.get("RateIntervalCode") == "PH" and _hour_pay(lo, hi):
                sal, sal_unit = _hour_pay(lo, hi), "hour"                 # hourly pay as hourly (never multiplied into a year)
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
                        salary_text=sal_text, sal=sal, sal_unit=sal_unit, posted=_ts(re.sub(r"\.\d+$", "", str(d.get("PublicationStartDate") or ""))), fallback=cats[0] if cats else None,
                        force_type="internship" if intern else None,
                        emp=(sched + " " + " ".join(s.get("Name", "") for s in d.get("PositionOfferingType") or [] if isinstance(s, dict) and s.get("Name") == "Temporary")).strip()))
    return out


# ---------- employers' own careers sites: the sitemap, then each job page's JobPosting structured data ----------
CP_UA = "UAplyBot/1.0 (+https://uaply.net; job search app; reads public JobPosting data)"
CP_PAGES = 40                    # job pages read per site per refresh (newest first; a page read before is read again only when its lastmod changes)
CP_FIRST = 14                    # ...on a site's first read (the first fill of a few hundred sites, 2 s apart per site, must stay short)
CP_WINDOW = 300                  # how far down the newest pages a site's co-ops, internships and tri-state pages are looked for
CP_STUDENT_URL = re.compile(r"co-?op|intern(?:ship)?s?\b|summer[-_ ]20\d\d", re.I)
CP_LOCAL_URL = re.compile(r"(?:^|[/_-])(?:PA|NJ|DE)(?:[/_-]|$)|(?i:pennsylvania|new-jersey|delaware|philadelphia|pittsburgh|camden)")
CP_NOMOD_TTL = 2 * 86400         # a page its sitemap gives no lastmod for (Workday) is read again after this long
CP_PARALLEL = 20                 # careers sites read at the same time, on their own threads: they wait out crawl delays, so on the
                                 # FEED_PARALLEL board readers 12 sites took 1,008 of the 4,500 reader-seconds of the first fill (October 21)
CP_MIN_DELAY = 2.0               # seconds between two requests to one careers site (more when its robots.txt asks for a crawl delay)
CP_TEXT = 4000                   # characters of a page's description kept
# a page that shows a check (a captcha, a challenge page). Cloudflare's quiet /cdn-cgi/challenge-platform/scripts/ tag on ordinary pages is
# not one (the human-check scan found it on most SmartRecruiters, Lever and Workable pages); its challenge pages load challenge-platform/h/
HUMAN_CHECK_RE = re.compile(r"g-recaptcha|h-captcha|hcaptcha|cf-challenge|challenge-platform/h/|cf_chl_|verify you are (?:a )?human|are you a robot|"
                            r"access denied|attention required", re.I)
_robots = {}                     # host -> (when read, RobotFileParser or None when robots.txt could not be read)
_cp_pages = {}                   # (site token, page address) -> (lastmod, whether it held a posting, when read)
_cp_next = {}                    # host -> the earliest time the next request may go


class RobotsTxt:
    """robots.txt read as RFC 9309 says, with the calls of urllib.robotparser.RobotFileParser (parse, can_fetch, crawl_delay). The group
    named for the bot (its name before the "/", e.g. UAplyBot) is used, else the * group; the longest rule that matches the path and query
    wins, Allow on a tie; * matches any characters and a final $ ends the path. urllib.robotparser matches neither * nor $ and takes the
    first rule in the file, so "Disallow: /jobs/*login" (iCIMS) was not honoured by it."""

    def __init__(self):
        self.allow_all = self.disallow_all = False
        self.groups = []                      # [(agents, [(allow, pattern, regex)], crawl delay or None)]

    def parse(self, lines):
        cur, in_agents = None, False
        for raw in lines:
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            k, v = (x.strip() for x in line.split(":", 1))
            k = k.lower()
            if k == "user-agent":
                if cur is None or not in_agents:
                    cur = ([], [], [None])
                    self.groups.append(cur)
                cur[0].append(v.lower())
                in_agents = True
            elif k in ("allow", "disallow") and cur is not None:
                in_agents = False
                if v:                         # an empty Disallow disallows nothing
                    end = v.endswith("$")
                    body = v[:-1] if end else v
                    rx = re.compile(".*".join(re.escape(x) for x in body.split("*")) + ("$" if end else ""))
                    cur[1].append((k == "allow", v, rx))
            elif k == "crawl-delay" and cur is not None:
                in_agents = False
                try:
                    cur[2][0] = float(v)
                except ValueError:
                    pass

    def _group(self, agent):
        name = (agent or "").split("/")[0].lower()
        mine = [g for g in self.groups if any(a != "*" and a and a in name for a in g[0])]
        return mine or [g for g in self.groups if "*" in g[0]]

    def can_fetch(self, agent, url):
        if self.disallow_all:
            return False
        if self.allow_all:
            return True
        p = urllib.parse.urlsplit(url)
        path = (p.path or "/") + ("?" + p.query if p.query else "")
        if path == "/robots.txt":
            return True
        best = None                           # (length of the rule, allow)
        for g in self._group(agent):
            for allow, pat, rx in g[1]:
                if rx.match(path) and (best is None or len(pat) > best[0] or (len(pat) == best[0] and allow)):
                    best = (len(pat), allow)
        return True if best is None else best[1]

    def crawl_delay(self, agent):
        for g in self._group(agent):
            if g[2][0] is not None:
                return g[2][0]
        return None


def _robots_for(host):
    """The site's robots.txt rules (read once a day). None when robots.txt cannot be read: the site is then not read at all."""
    got = _robots.get(host)
    if got and time.time() - got[0] < 24 * 3600:
        return got[1]
    rp, soon = RobotsTxt(), False
    try:
        rp.parse(_cp_fetch("https://%s/robots.txt" % host, robots_ok=True).splitlines())
    except urllib.error.HTTPError as e:
        rp = rp if e.code in (404, 410) else None   # no robots.txt (404): everything allowed, as the robots convention says
        soon = e.code == 429 or e.code >= 500       # busy or broken for now: asked again in ROBOTS_RETRY, not after a day
        if rp is not None:
            rp.parse([])
    except Exception:
        rp, soon = None, True                       # a time-out or a dropped connection (on October 21, 31 sites lost a day to one)
    _robots[host] = (time.time() - (24 * 3600 - ROBOTS_RETRY if soon else 0), rp)
    return rp


ROBOTS_RETRY = 10 * 60           # seconds before a robots.txt that could not be read for a passing reason is asked for again


def _cp_fetch(url, robots_ok=False):
    """One page of a careers site: only a public https address, only what its robots.txt allows this bot, never sooner than the site's
    crawl delay after the last request to it. Returns the text; raises on an error or a human check."""
    _cp_turn(url, robots_ok)
    text = _get(url, {"User-Agent": CP_UA, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8"}, as_text=True, opener=_cp_open)
    if HUMAN_CHECK_RE.search(text[:20000]):
        raise PermissionError("the page shows a human check")          # never answered: the site is marked as needing a person
    return text


def _cp_blocks(url, tag="url"):
    """A careers site's sitemap read as it arrives, as _cp_fetch reads a page (robots.txt, crawl delay, human check): the inside of each
    <url>...</url> block, one at a time. A big site's sitemap is megabytes (on October 21, twenty sites starting at once held 25 MB of
    sitemaps whole); this holds one part of it."""
    _cp_turn(url)
    buf, checked = "", False
    dec = codecs.getincrementaldecoder("utf-8")("replace")
    close, rx = "</%s>" % tag, re.compile(r"<%s>(.*?)</%s>" % (tag, tag), re.S)
    for part in _get_parts(url, {"User-Agent": CP_UA, "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8"}, opener=_cp_open):
        buf += dec.decode(part)
        if not checked and (len(buf) >= 20000 or close in buf):
            if HUMAN_CHECK_RE.search(buf[:20000]):
                raise PermissionError("the page shows a human check")
            checked = True
        end = buf.rfind(close)
        if end >= 0:
            cut = end + len(close)
            for b in rx.findall(buf, 0, cut):
                yield b
            buf = buf[cut:]
    buf += dec.decode(b"", final=True)
    if not checked and HUMAN_CHECK_RE.search(buf[:20000]):
        raise PermissionError("the page shows a human check")
    for b in rx.findall(buf):
        yield b


def _get_parts(url, headers, opener=None):
    """An answer's bytes as they arrive (STREAM_CHUNK at a time), refused past MAX_FEED_BYTES or FEED_DEADLINE."""
    req = urllib.request.Request(url, headers=headers)
    started, size = time.time(), 0
    with _host_slot(url), (opener or urllib.request.urlopen)(req, timeout=FEED_TIMEOUT) as r:
        while True:
            part = r.read(STREAM_CHUNK)
            if not part:
                return
            size += len(part)
            if size > MAX_FEED_BYTES:
                raise ValueError("the answer is larger than %d MB" % (MAX_FEED_BYTES // 1000000))
            if time.time() - started > FEED_DEADLINE:
                raise TimeoutError("the answer took longer than %d s; tried again at the next refresh" % FEED_DEADLINE)
            yield part


def _cp_turn(url, robots_ok=False):
    """Before any request to a careers site: a public https address, robots.txt allows it, and the site's crawl delay has passed."""
    if not _public_https(url):
        raise ValueError("not a public https address")
    host = urllib.parse.urlsplit(url).hostname.lower()
    if not robots_ok:
        rp = _robots_for(host)
        if rp is None or not rp.can_fetch(CP_UA, url):
            raise PermissionError("robots.txt does not allow it")
        delay = max(CP_MIN_DELAY, float(rp.crawl_delay(CP_UA) or 0))
    else:
        delay = CP_MIN_DELAY
    with _lock:
        wait = _cp_next.get(host, 0) - time.time()
        _cp_next[host] = max(time.time(), _cp_next.get(host, 0)) + delay
    if wait > 0:
        time.sleep(min(wait, 60))


def _ld_postings(html_text):
    """Every schema.org JobPosting in a page's JSON-LD blocks (a single object, a list, or an @graph)."""
    out = []
    for block in re.findall(r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", html_text, re.S | re.I):
        try:
            data = json.loads(html.unescape(block.strip()) if block.strip().startswith("&") else block.strip())
        except ValueError:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                t = x.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    out.append(x)
                stack.extend(v for k, v in x.items() if k == "@graph")
    return out


_STATE_BY_NAME = {n.lower(): n for n in STATE_NAMES.split("|")}
_CITY_ST_RE = re.compile(r"\b([A-Z][a-z]+(?:[ .'-][A-Z][a-z]+){0,3}), (%s)\b" % "|".join(STATES))


def _wd_place(page_url, text):
    """A Workday posting's place: its address names a building ("Christiana Main Building"), so the place is read from the page's own
    address (/job/Newark-DE/..., /job/US-PA-Philadelphia/..., /job/Elkton-Maryland/...), else the first "City, ST" of its description.
    None when neither says."""
    m = re.search(r"/job/([^/]+)/", page_url)
    seg = urllib.parse.unquote(m.group(1)) if m else ""
    w = [x for x in re.split(r"[-_ ]+", seg) if x]
    if w and w[0].lower() == "remote" or (len(w) <= 2 and "remote" in (x.lower() for x in w)):
        return "Remote"
    if len(w) >= 3 and w[0].upper() in ("US", "USA") and w[1].upper() in STATES:
        return "%s, %s" % (" ".join(w[2:]), w[1].upper())
    if len(w) >= 2 and w[-1] in STATES:
        return "%s, %s" % (" ".join(w[:-1]), w[-1])
    for k in (3, 2, 1):
        if len(w) > k and " ".join(w[-k:]).lower() in _STATE_BY_NAME:
            return "%s, %s" % (" ".join(w[:-k]), _STATE_BY_NAME[" ".join(w[-k:]).lower()])
    c = _CITY_ST_RE.search(text[:1500])
    return "%s, %s" % (c.group(1), c.group(2)) if c else None


def _cp_clean(page_url):
    """A careers-site page's address as the job keeps it (iCIMS' in_iframe=1 taken off)."""
    return re.sub(r"([?&])in_iframe=1&?", r"\1", page_url).rstrip("?&")


def _ld_raw(p, page_url, name):
    """A raw posting from one JobPosting, or None (no title, or valid only until a date already past)."""
    title = _text(p.get("title") or "").strip()
    if not title:
        return None
    if _ts(p.get("validThrough")) and _ts(p.get("validThrough")) < time.time() * 1000:
        return None
    org = p.get("hiringOrganization") or {}
    company = (org.get("name") if isinstance(org, dict) else str(org)) or name
    if (urllib.parse.urlsplit(page_url).hostname or "").lower().endswith(".myworkdayjobs.com") and name:
        company = name               # Workday names the legal entity with its code ("1215 Campbell Soup Supply Co. LLC"): the site's own name
    locs = p.get("jobLocation") or []
    locs = locs if isinstance(locs, list) else [locs]
    places, country = [], ""
    for L in locs:
        a = (L or {}).get("address") if isinstance(L, dict) else None
        if isinstance(a, dict):
            c = a.get("addressCountry")
            country = country or (c.get("name") if isinstance(c, dict) else str(c or ""))
            places.append(", ".join(x for x in (a.get("addressLocality"), a.get("addressRegion")) if isinstance(x, str) and x))
    remote = str(p.get("jobLocationType") or "").upper() == "TELECOMMUTE"
    if (urllib.parse.urlsplit(page_url).hostname or "").lower().endswith(".myworkdayjobs.com"):
        # Workday marks every posting TELECOMMUTE (a hospital's night-shift nurse too) and its address names a building
        wp = _wd_place(page_url, _text(p.get("description") or ""))
        remote = wp == "Remote" or bool(re.search(r"\bremote\b", title, re.I))
        if wp:
            places = [wp]
    sal, cp_unit = None, ""
    bs = p.get("baseSalary") if isinstance(p.get("baseSalary"), dict) else {}
    v = bs.get("value") if isinstance(bs.get("value"), dict) else {}
    try:
        lo, hi = float(v.get("minValue")), float(v.get("maxValue"))
        if bs.get("currency") == "USD" and str(v.get("unitText") or "").upper() == "YEAR" and 20000 <= lo < hi <= 600000:
            sal = [int(lo), int(hi)]
        elif bs.get("currency") == "USD" and str(v.get("unitText") or "").upper() == "HOUR" and _hour_pay(lo, hi):
            sal, cp_unit = _hour_pay(lo, hi), "hour"
    except (TypeError, ValueError):
        pass
    clean = _cp_clean(page_url)
    return dict(id=clean, title=title, company=str(company).strip(), loc="; ".join(x for x in places if x) or ("Remote" if remote else ""),
                remote=True if remote else None, text=_text(p.get("description") or "")[:CP_TEXT], url=clean, salary_text="", sal=sal, sal_unit=cp_unit,
                posted=_ts(p.get("datePosted")), emp=p.get("employmentType"), country=country or "us",
                # a clinical or store role often names no skill UAply scores on: its category (or the employer's industry) stands in
                fallback=str(p.get("occupationalCategory") or p.get("industry") or "").strip()[:60] or "General")


def _career_pages(token, name):
    """One employer's careers site: its sitemap (job pages and their lastmod), then the newest CP_PAGES job pages from the last 60 days,
    each page's JobPosting data read once and again only when its lastmod changes. Only pages on the sitemap's own host are read."""
    sm = CAREER_PAGES.get(token)
    if not sm:
        raise ValueError("no sitemap for this site")
    host = urllib.parse.urlsplit(sm).hostname.lower()
    now = time.time() * 1000
    pages = []
    for block in _cp_blocks(sm):
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block, re.S)
        mod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.S)
        if not loc:
            continue
        u = html.unescape(loc.group(1))
        lm = mod.group(1) if mod else ""
        ph = (urllib.parse.urlsplit(u).hostname or "").lower()
        # pages on the sitemap's own site: the same host, or another host of the same domain (an iCIMS site moves its pages from
        # careers-x.icims.com to externalcareers-x.icims.com); each page host's own robots.txt is read before any page of it
        if not (ph == host or ph.endswith("." + ".".join(host.split(".")[-2:]))) or not _public_https(u) or not re.search(r"/jobs?/|/job/|/careers?/|/position", u, re.I):
            continue
        if lm and now - _ts(lm) > MAX_AGE_DAYS * DAY_MS:
            continue
        pages.append((_ts(lm), lm, u))
    pages.sort(key=lambda x: x[0], reverse=True)        # stable: a sitemap with no lastmod (Workday) keeps its own order, newest first
    # then, of the newest CP_WINDOW, co-ops and internships first and Pennsylvania / New Jersey / Delaware ones next, as the page's own
    # address says (/job/Philadelphia-PA/Engineering-Co-op_R123): the few pages a site's first read takes are the ones UAply needs most
    pages[:CP_WINDOW] = sorted(pages[:CP_WINDOW], key=lambda x: (not CP_STUDENT_URL.search(x[2]), not CP_LOCAL_URL.search(x[2])))
    first = not any(k[0] == token for k in list(_cp_pages))
    pages = pages[:CP_FIRST if first else CP_PAGES]
    prev = _prev_jobs(("careerpage", token, name))
    for _, lm, u in pages:
        got = _cp_pages.get((token, u))
        fresh = got and got[0] == lm and (lm or time.time() - got[2] < CP_NOMOD_TTL)
        again = prev.get(_jid("careerpage", _cp_clean(u))) if fresh and got[1] else None
        if fresh and not got[1]:
            continue                                      # held no posting (or robots.txt / a human check): left alone until it changes
        if again:
            yield {"_prev": again, "id": _cp_clean(u), "title": again["role"], "loc": again["loc"], "posted": again.get("posted"),
                   "updated": again.get("updated"), "url": again["url"], "text": ""}
            continue
        try:
            ps = _ld_postings(_cp_fetch(u))
        except PermissionError:                       # robots.txt says no, or a human check: left alone until the page changes
            with _lock:
                _cp_pages[(token, u)] = (lm, None, time.time())
            continue
        except Exception:
            continue
        raw = _ld_raw(ps[0], u, name) if ps else None
        us = bool(raw) and str(raw.get("country") or "us").strip().lower() in ("us", "usa", "united states", "united states of america")
        with _lock:                                   # the job made from it is in the source's packed copy (see _prev_jobs); a posting
            _cp_pages[(token, u)] = (lm, us, time.time())     # outside the US is not read again until its page changes
        if raw:
            # the sitemap's lastmod is the page's last change: an evergreen hospital posting keeps its first datePosted for months
            yield dict(raw, posted=raw.get("posted") or _ts(lm), updated=max(_ts(lm), raw.get("updated") or 0))
    with _lock:                                           # forget pages the sitemap no longer lists
        listed = {u for _, _, u in pages}
        for key in [k for k in _cp_pages if k[0] == token and k[1] not in listed]:
            del _cp_pages[key]


def _careeronestop(token):
    """One CareerOneStop job search (COS_SEARCHES[token]), as its List Jobs API documents it (careeronestop.org/Developers/WebAPI/Jobs/
    list-jobs.aspx): GET /v1/jobsearch/{userId}/{keyword}/{location}/{radius}/{sortColumns}/{sortOrder}/{startRecord}/{pageSize}/{days}
    with "Authorization: Bearer <token>". The answer is {"JobCount", "Jobs": [{"JvId", "JobTitle", "Company", "DescriptionSnippet",
    "AcquisitionDate", "URL", "Location", "Fc"}]}; field names are matched without regard to case, and a posting without a title or an
    https link is skipped. Titles, companies and places are shown as given (the license forbids altering the data)."""
    keys = feed_keys()
    keyword, place, radius = COS_SEARCHES.get(token) or COS_SEARCHES["philadelphia"]
    q = lambda v: urllib.parse.quote(v, safe="")              # noqa: E731
    url = "https://api.careeronestop.org/v1/jobsearch/%s/%s/%s/%s/acquisitiondate/DESC/0/%s/%s" % (
        q(keys.get("cos_user", "")), q(keyword), q(place), q(radius), COS_PAGE, COS_DAYS)
    data = _get(url, {"Authorization": "Bearer " + keys.get("cos_token", "")})
    low = {str(k).lower(): v for k, v in (data or {}).items()} if isinstance(data, dict) else {}
    for j in low.get("jobs") or []:
        if not isinstance(j, dict):
            continue
        f = {str(k).lower(): v for k, v in j.items()}
        title, link = str(f.get("jobtitle") or "").strip(), str(f.get("url") or "").strip()
        if not title or not link.startswith("https://"):
            continue
        loc = str(f.get("location") or "").strip()
        yield dict(id=f.get("jvid") or link, title=title, company=str(f.get("company") or "").strip() or "Employer not named",
                   loc=loc or ("Remote" if token == "remote" else place), remote=True if token == "remote" or re.search(r"\bremote\b", loc, re.I) else None,
                   text=_text(f.get("descriptionsnippet") or ""), url=link, salary_text="", posted=_ts(f.get("acquisitiondate")),
                   fallback="Jobs")


def _newest(j):
    """The newest date a posting carries (epoch ms; 0 when it has none): posted, or updated where the feed gives that too."""
    return max(j.get("posted") or 0, j.get("updated") or 0)


def _too_old(j, now_ms):
    """True when the posting's newest date is more than MAX_AGE_DAYS ago. No date at all is not 'old'."""
    newest = _newest(j)
    return bool(newest) and now_ms - newest > MAX_AGE_DAYS * DAY_MS


def _days(ms, now_ms):
    return max(0, int((now_ms - ms) // DAY_MS))


INTERNED = ("co", "loc", "mode", "type", "jobType", "edu", "source", "apply", "via", "credit")


def _with_age(j, now_ms, drop=()):
    """A copy of a job with postedDays (whole days since it was posted) and, when the feed gives a later update, updatedDays. The cached
    job itself is shared by every request, so it is never changed here. `drop`: fields left out of the copy."""
    out = {k: v for k, v in j.items() if k not in drop} if drop else dict(j)
    if j.get("posted"):
        out["postedDays"] = _days(j["posted"], now_ms)
    if j.get("updated"):
        out["updatedDays"] = _days(j["updated"], now_ms)
    return out


_CO_SUFFIX = re.compile(r"\b(?:inc|llc|ltd|corp|corporation|co|company|the)\b")


def _norm(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def _same_job_key(j):
    """Two postings from two different feeds are the same job when company, title and place match after letter case, punctuation, spacing
    and company suffixes (Inc, LLC, Corp ...) are set aside: the same opening reached through two feeds (see get_jobs)."""
    return (_norm(_CO_SUFFIX.sub(" ", (j.get("co") or "").lower())), _norm(j.get("role")), _norm(j.get("loc")))


# Job type (jobType on every job): one of these six. The feed's own field is read first; the title (and, for part-time, the start of
# the text) is the fallback. "Full-time" is what most hiring systems fill in by default, interns included, so a title that says
# intern, co-op, part-time, contract, seasonal or temporary wins over a plain "Full-time" field.
JOB_TYPES = ("full-time", "part-time", "internship", "co-op", "contract", "temporary")
LEGACY_TYPE = {"internship": "internship", "co-op": "coop", "part-time": "parttime"}     # the older `type` field (the service tabs); anything else is "job"
FORCE_TO_JOBTYPE = {"internship": "internship", "coop": "co-op", "parttime": "part-time"}
TITLE_TYPES = [("co-op", re.compile(r"\bco-?op\b", re.I)),
               ("internship", re.compile(r"\binterns?\b|\binternships?\b", re.I)),
               ("part-time", re.compile(r"\bpart[- ]time\b", re.I)),
               ("temporary", re.compile(r"\bseasonal\b|\btemporary\b|\(temp\)|\btemp\s*[-–—:]", re.I)),
               # "Contract Manager" is a full-time job about contracts: only a bracketed or trailing "Contract", 1099 or contract-to-hire counts
               ("contract", re.compile(r"\((?:[^)]*[\s,/])?contract(?:or)?(?:[\s,/][^)]*)?\)|[-–—:,|]\s*contract(?:or)?\s*$|\b1099\b|\bcontract[- ]to[- ]hire\b", re.I))]


# Board names that carry a careers-site label: "Perpay - Career's Page", "Point72 ", "DRW - University Jobs", "Hometap Jobs",
# "ATOMS Careers page", "Astera Labs Early Career - North America 2027", "MORSE Corp Co-op Opportunities", "Jobs at Acme".
# A label is only taken off the end (or "Jobs at" off the start) when a name is left: "CourseCareers" and "Jobs for Humanity" stay.
CO_TAIL = re.compile(r"(?:\s*[-–—|:,]\s*|\s+)(?:(?:university|campus|early|student|internship|intern|co-?op)\s+)?"
                     r"(?:careers?(?:'s)?(?:\s+(?:page|site|portal|board))?|jobs?(?:\s+(?:page|board|site))?|job\s+board|opportunities|openings|"
                     r"hiring|recruiting|early\s+careers?(?:\b.*)?|university\s+recruiting(?:\b.*)?)\s*$", re.I)
CO_HEAD = re.compile(r"^\s*(?:jobs|careers)\s+(?:at|with)\s+", re.I)


def _clean_company(name, fallback=""):
    """A company name without the careers-site label a board added to it, spaces trimmed (see CO_TAIL). Empty: the fallback."""
    n = re.sub(r"\s+", " ", str(name or "")).strip()
    for _ in range(3):                                  # "Acme University Jobs - Careers Page": labels can be stacked
        m = CO_HEAD.match(n)
        cut = n[m.end():].strip() if m else n
        cut = CO_TAIL.sub("", cut).strip(" -–—|:,")
        if cut == n or not re.search(r"[A-Za-z0-9]", cut):
            break
        n = cut
    if not n or re.fullmatch(r"(?:careers?|jobs?|job board)(?:\s+page)?", n, re.I):     # nothing but a label: the board's own name
        n = re.sub(r"\s+", " ", str(fallback or "")).strip() or n
    return n


# Licensed and degree-gated roles, by title (checked against the live feeds' titles, October 2026). The lowest level a person can hold
# the job with: a Registered Nurse can be licensed with an associate degree, a therapist or counselor needs a master's, a psychologist,
# pharmacist, physician, dentist, physical therapist or lawyer a doctorate.
EDU_BY_TITLE = [
    ("Doctorate", re.compile(r"\bpsychologist|\bpsychiatrist\b|\bphysicians?\b(?!\s+assistant)|\bpharmacists?\b|\bdentists?\b|\bphysical therapist|"
                             r"\bDPT\b|\bPharmD\b|\battorneys?\b|\blawyers?\b|\bsolicitor\b|\bassociate general counsel|\bveterinarian|\boptometrist|"
                             r"\bresearch scientist\b.*\bph\.?d|\bph\.?d\b", re.I)),
    ("Master", re.compile(r"\bnurse practitioner|\bphysician assistant|\bPA-C\b|\bCRNA\b|\bLCSW\b|\bLICSW\b|\bLPCC?\b|\bLMFT\b|\bLMHC\b|\bLCPC\b|"
                          r"\b(?:licensed|clinical|mental health|staff|primary|outpatient|family|child|telehealth|bilingual)\s+(?:\w+\s+)?(?:therapist|counselor|social worker|clinician)|"
                          r"\bpsychotherapist|\btherapist\b|\bsocial worker\b|\bspeech[- ]language pathologist|\bSLP\b|\boccupational therapist|\bdietitian|"
                          r"\bMBA\b|\bmaster'?s\b", re.I)),
    ("Associate", re.compile(r"\bregistered nurse|\bRN\b|\bLPN\b|\bLVN\b|\bnurse\b|\bradiolog\w* tech|\bsonographer|\brespiratory therapist|"
                             r"\bdental hygienist|\bsurgical tech|\bmedical lab(?:oratory)? tech", re.I)),
]
EDU_RANK = {"High school": 0, "Associate": 1, "Bachelor": 2, "Master": 3, "Doctorate": 4}
EDU_TEXT = [  # what the text requires (a "preferred" degree is not a requirement)
    ("Doctorate", re.compile(r"(?:\bmust (?:have|hold|possess)|\brequires?|\brequired:?)\s+(?:an?\s+|the\s+)?(?:ph\.?d|doctoral degree|doctorate|pharm\.?d|psy\.?d|J\.D\.|M\.D\.|juris doctor)|"
                              r"(?:\bph\.?d\b|\bdoctoral degree|\bdoctorate\b|\bpharm\.?d\b|\bpsy\.?d\b|\bJ\.D\.|\bM\.D\.|\bjuris doctor)[^.;]{0,40}?\b(?:is |are )?(?:required|needed|necessary)\b", re.I)),
    ("Master", re.compile(r"(?:\bmust (?:have|hold|possess)|\brequires?|\brequired:?)\s+(?:an?\s+)?(?:master'?s|MSW|MBA|graduate degree)|"
                          r"(?:\bmaster'?s degree|\bMSW\b|\bMBA\b|\bgraduate degree)[^.;]{0,40}?\b(?:is |are )?(?:required|needed|necessary)\b", re.I)),
    ("Bachelor", re.compile(r"\bbachelor'?s?\b|\bB\.?S\.? degree|\bB\.?A\.? degree|\b4[- ]year degree|\bfour[- ]year degree|\bundergraduate degree|\bcollege degree|"
                            r"\b(?:BS|BA|B\.S\.|B\.A\.)(?=,|\s*/|\s+(?:or|in)\b)", re.I)),
    ("Associate", re.compile(r"\bassociate'?s? degree|\btwo[- ]year degree|\b(?:active|current|valid|unrestricted)\s+(?:state\s+)?(?:RN|LPN|LVN|nursing|clinical|professional|medical|pharmacy|therapy|counseling|social work)\s+(?:\w+\s+){0,2}licen[sc]e\b", re.I)),
]
# an internship or co-op asks what a student is studying for, not what they hold: graduate-only ones are marked (ranked after the others)
GRAD_TITLE = re.compile(r"\bph\.?d\b|\bdoctoral\b|\bMBA\b|\bmaster'?s\b|\bgraduate (?:student|intern|research)|\bpostdoc", re.I)
GRAD_TEXT = re.compile(r"(?:pursuing|enrolled in|candidate for|working toward|studying for|currently in)\s+(?:a|an|your)?\s*(?:ph\.?d|doctoral|doctorate|master'?s|MBA|graduate)", re.I)
UNDERGRAD_TEXT = re.compile(r"\bundergrad|\bbachelor|\bB\.?S\.?\b|\bB\.?A\.?\b|\bsophomore|\bjunior year|\brising (?:junior|senior|sophomore)|\bfreshm[ae]n|\bassociate'?s? degree|\bhigh school", re.I)


def _grad_only(title, text):
    """True for an internship or co-op only graduate students can take (a PhD, master's or MBA program in the title, or the text asks
    for one and never mentions undergraduates)."""
    return bool(GRAD_TITLE.search(title) or (GRAD_TEXT.search(text) and not UNDERGRAD_TEXT.search(text)))


def _edu(title, text, jtype="full-time"):
    """The education level a job needs (High school, Associate, Bachelor, Master, Doctorate): a licensed or degree-gated title first,
    then what the text requires. For an internship or co-op it is what a student must have finished: High school for an undergraduate
    one, Bachelor for a graduate-only one."""
    if jtype in ("internship", "co-op"):
        return "Bachelor" if _grad_only(title, text) else "High school"
    by_title = next((lvl for lvl, rx in EDU_BY_TITLE if rx.search(title)), "High school")
    by_text = next((lvl for lvl, rx in EDU_TEXT if rx.search(text)), "High school")
    return max(by_title, by_text, key=lambda lvl: EDU_RANK[lvl])


GH_WHOLE_MAX = 80               # a Greenhouse board listing at most this many postings is read whole (one answer) when descriptions are needed
GH_DESC_READ = 3                 # descriptions of one Greenhouse board read at the same time (FEED_PARALLEL boards at once: up to 36 requests)
LAZY_WAVES = 3                   # rounds of description reads for one board: places a posting could not fill go to the next ones
_gh_seen = {}                    # (board, posting id) -> the updated_at its kept job was made from
_gh_skip = {}                    # (board, posting id) -> the updated_at of a posting read and not kept (read again only when it changes)


def _gh_fill(raws, prev, listed_n=0):
    """For Greenhouse postings that will be kept: the job made last time when the posting has not changed since (same updated_at), else
    the raw posting with its description, department and custom fields read from the single-posting address. Returns a list matching
    raws: a kept job (dict with "co") to reuse as is, or a raw posting to normalize, or None when the posting could not be read."""
    # a small board with several descriptions to read: one answer with every description costs less than a request per posting
    need = [r for r in raws if not (prev.get(_jid("greenhouse", r["id"])) is not None and _gh_seen.get(r["lazy"][:2]) == r["lazy"][2])]
    bulk = {}
    if need and len(need) > 2 and listed_n <= GH_WHOLE_MAX:
        try:
            board = need[0]["lazy"][0]
            for j in _get_items("https://boards-api.greenhouse.io/v1/boards/%s/jobs?content=true" % urllib.parse.quote(board, safe=""), "jobs"):
                if str(j.get("id")) in {r["lazy"][1] for r in need}:
                    bulk[str(j["id"])] = {"content": j.get("content"), "departments": j.get("departments"), "metadata": j.get("metadata")}
        except Exception:
            bulk = {}

    def one(raw):
        board, pid, upd = raw["lazy"]
        old = prev.get(_jid("greenhouse", raw["id"]))
        if old is not None and _gh_seen.get((board, pid)) == upd:
            return old
        j = bulk.get(pid)
        if j is None:
            try:
                j = _get("https://boards-api.greenhouse.io/v1/boards/%s/jobs/%s" % (urllib.parse.quote(board, safe=""), urllib.parse.quote(pid, safe="")))
            except Exception:
                return old                       # keep the last good job if the description cannot be read this time
        if not isinstance(j, dict):
            return old
        out = dict(raw, text=_text(j.get("content")), emp=_gh_emp(j) or raw.get("emp"), fallback=_dept(j.get("departments")))
        out.pop("lazy", None)
        out["_seen"] = (board, pid, upd)
        return out
    with ThreadPoolExecutor(max_workers=GH_DESC_READ) as ex:
        return list(ex.map(one, raws))


def _jid(kind, raw_id):
    """A job's id in the app: the same number for the same posting every time (also when a list such as Simplify's points to it)."""
    return _claim_id("%s:%s" % (kind, raw_id), 100000)


# ---- job ids that never collide (October 22, 2026) ----
# An id is 100000 plus the first 6 hex digits of a hash of the posting's key: about 16.7 million values, so 20,000 postings share an id
# about 12 times. The list kept only the first posting with an id (the second was never shown), and a swipe saved under that id
# could later point at a different job. Now every id handed out is kept with a fingerprint of its posting (ID_FILE, beside the saved job
# list), and a second posting whose 6 digits are taken gets 7, then 8 ... up to 13 digits, the first free one. An id once given to a
# posting stays its own, also after a restart, so every id that never collided is exactly what it was before (saved swipes still match).
ID_FILE = "job-ids.json"
ID_KEEP_DAYS = 180                   # an id no posting has used for this long is forgotten (jobs leave the list after 60 days)
ID_HEX, ID_HEX_MAX = 6, 13           # 13 hex digits stay below 2**53, so the browser reads every id exactly
_idreg = {"loaded": False, "dirty": False, "ids": {}}     # ids: id -> one int, the posting's fingerprint << 16 | the day it was last handed out
#                                                            (one int, not a pair: tens of thousands of postings are read, kept or not)
_id_lock = threading.Lock()


def _ids_file():
    return os.path.join(os.path.dirname(_cache_file()), ID_FILE)


def _ids_load():
    """(called with _id_lock held) the ids handed out before this start, once"""
    if _idreg["loaded"]:
        return
    _idreg["loaded"] = True
    try:
        with open(_ids_file(), encoding="utf-8") as f:
            saved = json.load(f)
        got = saved.get("ids") if isinstance(saved, dict) else None
        if isinstance(got, dict):
            for k, v in got.items():
                if isinstance(v, int):
                    _idreg["ids"].setdefault(int(k), v)
    except (OSError, ValueError, TypeError):
        pass


def _claim_id(key, base):
    """The id of the posting `key` ("greenhouse:4012345", "partner:Acme:Barista"): base + the first 6 hex digits of its hash, unless
    another posting has those, then the first free longer prefix. The same key always gets the same id."""
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    fp, day = int(h[:ID_HEX_MAX], 16), int(time.time() // 86400) & 0xFFFF
    with _id_lock:
        _ids_load()
        ids = _idreg["ids"]
        for n in range(ID_HEX, ID_HEX_MAX + 1):
            jid = base + int(h[:n], 16)
            got = ids.get(jid)
            if got is None or got >> 16 == fp:
                if got is None or got & 0xFFFF != day:
                    ids[jid] = fp << 16 | day
                    _idreg["dirty"] = True
                return jid
    return base + int(h[:ID_HEX_MAX], 16)       # (13 digits taken by another posting: never seen, and 2**52 makes it so)


def _save_ids():
    """Write the ids handed out (beside the saved job list), dropping ones unused for ID_KEEP_DAYS. Called with every save of the list."""
    with _id_lock:
        if not _idreg["dirty"]:
            return
        today = int(time.time() // 86400) & 0xFFFF
        for k in [k for k, v in _idreg["ids"].items() if (today - (v & 0xFFFF)) % 0x10000 > ID_KEEP_DAYS]:
            del _idreg["ids"][k]
        snap = {str(k): v for k, v in _idreg["ids"].items()}
        _idreg["dirty"] = False
    path = _ids_file()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "ids": snap}, f, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError as e:
        with _id_lock:
            _idreg["dirty"] = True
        sys.stderr.write("[uaply] could not save the job ids: %s\n" % type(e).__name__)


def _dept(departments):
    """Greenhouse's first department name ("Store Operations", "Clinical"), or None."""
    for d in departments or []:
        if isinstance(d, dict) and str(d.get("name") or "").strip():
            return str(d["name"]).strip()[:60]
    return None


def _gh_emp(j):
    """Greenhouse has no standard employment-type field; many employers add one as a custom field ("Employment Type", "Time Type")."""
    for m in j.get("metadata") or []:
        if isinstance(m, dict) and re.search(r"employ|job type|time type|worker type|schedule|commitment", str(m.get("name") or ""), re.I):
            return m.get("value") if isinstance(m.get("value"), (str, list)) else ""
    return ""


def _emp_type(v):
    """A feed's own employment-type value (Lever "Intern", Ashby "PartTime", SmartRecruiters "Full-time", USAJOBS "Part-time Temporary",
    Himalayas "Contractor" ...) as one of JOB_TYPES, or "" when it says nothing usable."""
    if isinstance(v, (list, tuple)):
        v = " ".join(str(x.get("name") or x.get("label") or "") if isinstance(x, dict) else str(x) for x in v)
    s = re.sub(r"[_\s]+", " ", re.sub(r"([a-z])([A-Z])", r"\1 \2", str(v or ""))).lower()
    for t, rx in (("co-op", r"\bco ?-?op\b"), ("internship", r"\bintern"), ("part-time", r"\bpart\b|\bpart-time\b|\bparttime\b"),
                  ("contract", r"\bcontract|\bfreelance"), ("temporary", r"\btemp|\bseasonal|\bintermittent"), ("full-time", r"\bfull|\bpermanent|\bregular")):
        if re.search(rx, s):
            return t
    return ""


PT_WORDS = re.compile(r"\bpart[- ]time\b(?![- ]?(?:and|or|/)\s*full)|\bPT\b(?=\s*(?:position|role|schedule|shift))|\bweekend (?:and evening )?shifts\b", re.I)
PT_HOURS = re.compile(r"(?:(\d{1,2})\s*(?:-|–|to)\s*)?(\d{1,2})\+?\s*(?:hours|hrs)\s*(?:per|a|each|/)\s*week", re.I)
FT_WORDS = re.compile(r"\bfull[- ]time\b(?![- ]?(?:and|or|/)\s*part)|\b40\s*(?:hours|hrs)\s*(?:per|a|/)\s*week", re.I)


def _part_time_text(text):
    """True when the start of a posting describes a part-time schedule: "part-time" (not "full-time or part-time"), or hours a week of
    30 or fewer ("15-25 hours per week", "up to 20 hrs/week"), and it does not also say full-time first."""
    # "full-time or part-time" / "part-time and full-time" says neither: taken out before looking
    head = re.sub(r"\b(?:full|part)[- ]time\s*(?:,|and|or|/|&)\s*(?:full|part)[- ]time\b", " ", text[:1500], flags=re.I)
    pt, ft = PT_WORDS.search(head), FT_WORDS.search(head)
    if pt and not (ft and ft.start() < pt.start()):
        return True
    hours = [int(m.group(2)) for m in PT_HOURS.finditer(head)]
    return bool(hours) and max(hours) <= 30 and not ft


def _job_type(raw):
    """One of JOB_TYPES for a raw posting: a type the feed forced (USAJOBS Pathways, The Muse's Internship level), then the feed's own
    field, then the title, then "part-time" near the start of the text, then the list's own kind (an internship list), else full-time."""
    if raw.get("_prev"):
        return raw["_prev"].get("jobType") or "full-time"
    forced = FORCE_TO_JOBTYPE.get(raw.get("force_type") or "")
    if forced:
        return forced
    feed = _emp_type(raw.get("emp"))
    title = raw.get("title") or ""
    by_title = next((t for t, rx in TITLE_TYPES if rx.search(title)), "")
    if by_title in ("internship", "co-op"):              # interns are often entered as temporary or contract workers: the title says what it is
        return "co-op" if feed == "co-op" else by_title
    if feed and feed != "full-time":
        return feed
    if by_title:
        return by_title
    if feed == "full-time":
        return "full-time"
    if _part_time_text(raw.get("text") or ""):
        return "part-time"
    return raw.get("default_type") or "full-time"


def _type(raw):
    """The older type field (internship, coop, parttime or job) the service tabs use, from _job_type. Cheap, so it is known before the costly part."""
    return LEGACY_TYPE.get(_job_type(raw), "job")


def _normalize(raw, kind, name, board=None):
    if raw.get("_prev"):
        return raw["_prev"]                             # an unchanged posting: the job its last read made (see _prev_jobs)
    list_credit = raw.get("list_credit")
    if list_credit:                                     # a Simplify / Pitt CSC row: it is the employer's own posting, read from its own board
        kind, board, name = raw["ats_kind"], raw["board"], raw["company"]
    title, loc, text = raw["title"], raw["loc"], raw["text"]
    if str(raw.get("country") or "us").strip().lower() not in ("us", "usa", "united states", "united states of america"):
        return None
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
    jtype = _job_type(raw)
    typ = LEGACY_TYPE.get(jtype, "job")
    m = YRS_RE.search(text)
    yrs = min(int(m.group(1)), 15) if m else 0
    edu = _edu(title, text, jtype)
    blurb = text[:170].rsplit(" ", 1)[0] + "…" if len(text) > 170 else text
    desc = _role_summary(text)                                                    # what the emails show about the job
    jid = _jid(kind, raw["id"])
    company = _clean_company(raw["company"], name)
    src = name if kind in ("remotive", "jobicy", "muse", "usajobs", "himalayas", "remoteok", "careeronestop") else "%s's careers page" % company
    if kind == "careerpage":
        name = company                                    # credited as "<the employer> careers site"
    # Where this posting lives in the employer's own hiring system. It is only an address (not a credential): it is used when, and only when, the
    # employer has connected with their own key (see ats_connections); otherwise it is never used and apply stays "link".
    # Ashby: the job board's own posting id is the jobPostingId its API takes. SmartRecruiters: the posting's uuid (see _smartrecruiters).
    pid = str(raw.get("ats_id") or raw["id"])
    ats = {"kind": kind, "board": board, "id": pid} if (kind in ats_api.KINDS and board and ats_api.TOKEN_RE.match(board) and ats_api.ID_RE.match(pid)) else None
    # contact and apply "email": only when the posting itself asks for applications by email at the employer's own address (apply_address,
    # October 23, 2026). Every other feed posting keeps contact empty and apply "link": nothing is emailed to anyone for it.
    contact = apply_address(text, company, board or "", raw["url"])
    # pay as the posting gives it: a yearly range, or an hourly one with its unit; nothing at all ([0, 0], "Pay not listed") otherwise
    sal, sal_unit = raw.get("sal"), (raw.get("sal_unit") or "") if raw.get("sal") else ""
    if not sal:
        sal = _salary(raw["salary_text"], text)
        if not sal[1]:
            hour = _hourly(raw["salary_text"], text)
            if hour:
                sal, sal_unit = hour, "hour"
    out = dict(id=jid, co=company, role=title, loc=_place(loc, mode), mode=mode,
               sal=sal, yrs=yrs, edu=edu, skills=skills, blurb=blurb, desc=desc,
               type=typ, jobType=jtype, url=raw["url"], source=src, contact=contact, apply="email" if contact else "link", live=True, ats=ats,
               posted=_ts(raw.get("posted")), perks=_perks(text), comm=bool(COMM_RE.search(text)))
    if sal_unit == "hour":
        out["salUnit"] = "hour"                                   # the card says "per hour"; nothing compares it with a yearly minimum
    if contact:
        out["instant"] = True                                     # the card says "Apply instantly": a swipe right emails the application
    if jtype in ("internship", "co-op") and _grad_only(title, text):
        out["gradOnly"] = True                                    # the Internship and Co-op stacks show undergraduate roles first
    pt = job_geo(loc, mode == "remote")
    if pt:
        out["geo"] = pt                                           # where it is, for "near you" (see PLACES_FILE)
    # dates in epoch ms whatever the caller gave (_ts: seconds are converted): a date in seconds reads as January 1970, and the 60-day rule
    # (MAX_AGE_DAYS) would drop the posting without a word
    if _ts(raw.get("updated")) > out["posted"]:
        out["updated"] = _ts(raw.get("updated"))                  # Greenhouse: the employer touched the posting after first publishing it
    # Credit every feed, on the card ("via ...") and in the application record ("credit"): each free feed asks for it, and an employer board is the employer's own
    out["via"] = VIA.get(kind, "%s").replace("%s", name) + (", listed by " + list_credit if list_credit else "")
    out["credit"] = "via USAJOBS; apply on the official announcement" if kind == "usajobs" else "via " + out["via"]
    if (raw.get("announcement") or "").startswith("https://"):
        out["announcement"] = raw["announcement"]                 # USAJOBS: the official announcement, kept next to the apply link
    # the same few strings repeat across thousands of jobs (a board's name, credit and places, the work style, type and level): one copy each
    for k in INTERNED:
        if isinstance(out.get(k), str):
            out[k] = sys.intern(out[k])
    out["skills"] = [sys.intern(x) if isinstance(x, str) else x for x in out.get("skills") or []]
    return out


_refreshing = {}          # source -> threading.Event, set when the read in progress is done (see _start_refresh)


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
    return _find_job(job_id)


def known_contact(job_id):
    """The address this server itself holds for a job ('' if none or unknown): a partner employer's recruiting address, or the address a
    posting asks applications to be emailed to (apply_address), unless that employer connected its hiring system (which takes it instead)."""
    for j in partner_jobs():
        if j["id"] == job_id:
            return j.get("contact", "") or ""
    j = _find_job(job_id)
    if not j or j.get("apply") != "email" or _connected(j, ats_connections()):
        return ""
    return j.get("contact", "") or ""


FIRST_WAIT = 8                   # seconds the very first request on an empty disk waits for a board (every later request waits for none)
_failed = {}                     # source -> (when, status) of a read that failed with no copy to fall back on: not tried again for 2 minutes


def _trim():
    """Hand memory freed after reading the boards back to the system (Linux, glibc). Without it the process keeps its high-water mark."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


SAVE_EVERY = 30                  # seconds: while many boards are being read, the saved copy is written at most this often (and after the last one)


def _refresh_in_background(src, done):
    try:
        _fetch_source(src)
        with _lock:
            others = len(_refreshing) > 1
        if not others or time.time() - _disk.get("saved_at", 0) >= SAVE_EVERY:
            _save_disk()
    finally:
        with _lock:
            _refreshing.pop(src, None)
            last = not _refreshing
        done.set()
        if last:
            _save_disk()                         # the last board of a round: whatever a skipped save left unwritten goes to disk now
            _trim()


FAIL_LIMIT = 3                   # refreshes in a row that may fail before a source is switched off
OFF_FOR = 24 * 3600              # ...for this long; then it is tried again (a board that came back recovers by itself)
_health = {}                     # source -> {"ok", "fail", "last_ok", "last_error", "error", "jobs", "ms", "off_until", "retry"}


def last_feed_ok():
    """When any job board was last read successfully (Unix seconds), or 0 when none has been since this copy started (the owner's
    self-check in /api/status)."""
    with _lock:
        return max([float(h.get("last_ok") or 0) for h in _health.values()] or [0])


def _note_health(src, ok, jobs=0, error="", ms=0):
    with _lock:
        h = _health.setdefault(src, {"ok": 0, "fail": 0, "streak": 0, "last_ok": 0, "last_error": 0, "error": "", "jobs": 0, "ms": 0, "off_until": 0})
        h["ms"] = ms
        if ok:
            h.update(ok=h["ok"] + 1, streak=0, last_ok=time.time(), jobs=jobs, off_until=0)
            h.pop("retry", None)
        else:
            h.update(fail=h["fail"] + 1, streak=h["streak"] + 1, last_error=time.time(), error=error[:120])
            if h["streak"] >= FAIL_LIMIT and not h["off_until"]:
                h["off_until"] = time.time() + OFF_FOR
                h["retry"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(h["off_until"]))
                sys.stderr.write("[uaply] job feed %s switched off after %d failed refreshes (tried again %s)\n" % ("/".join(src), FAIL_LIMIT, h["retry"]))


def _disabled(src):
    h = _health.get(src)
    if not h or not h.get("off_until"):
        return False
    if time.time() >= h["off_until"]:          # its day is over: one more try (a failure switches it off again at once)
        h["off_until"], h["streak"] = 0, FAIL_LIMIT - 1
        return False
    return True


LINK_SAMPLE = 20                 # links of one source checked per round
LINK_FAIL_LIMIT = 0.10           # more than this share of a source's checked links dead (with at least 10 checked): the source is switched off
LINK_EVERY = 24 * 3600           # each source's links are checked again after this long
LINK_PAUSE = 60                  # seconds between two sources in the background check (gentle on employers' sites)
LINK_UA = "Mozilla/5.0 (compatible; UAplyLinkCheck/1.0; +https://uaply.net)"
link_check_on = False            # serve.py turns the background check on for a hosted server (UAPLY_LINK_CHECK=0 keeps it off)
_links = {}                      # source -> {"at", "ok", "dead", "unknown", "dead_ids": set of job ids, "off": bool}
_link_thread = []


def _link_alive(url):
    """True: the page answers (a person can open it); False: it is gone (404/410, or the board's own "no longer open" page), or it is not
    a public page (an internal or metadata address, or a redirect to one: never opened or followed, _link_open); None: cannot tell
    (blocked by a bot check, rate-limited, a time-out): never counted against a source."""
    if not _public_link(url):
        return False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": LINK_UA, "Accept": "text/html,*/*"})
        with _link_open(req, timeout=15) as r:
            final = r.geturl() or url
            body = r.read(20000).decode("utf-8", "replace").lower()
        if re.search(r"[?&]error=true\b", final) or "job not found" in body or "no longer accepting applications" in body or \
                "this job is no longer available" in body or "the job you are looking for is no longer open" in body or "posting has been closed" in body:
            return False                         # Greenhouse sends a closed posting to its board with ?error=true; others say so on the page
        return True
    except RedirectRefused:
        return False
    except urllib.error.HTTPError as e:
        return False if e.code in (404, 410) else None
    except urllib.error.URLError as e:
        return False if isinstance(e.reason, NotPublic) else None
    except Exception:
        return None


ATS_POSTING = {"greenhouse": "https://boards-api.greenhouse.io/v1/boards/%s/jobs/%s", "lever": "https://api.lever.co/v0/postings/%s/%s",
               "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/%s/postings/%s"}


def job_alive(j):
    """Whether a job's apply page is still there. A posting on Greenhouse, Lever or SmartRecruiters is asked of the hiring system's own
    public API (its job pages turn away anything that is not a browser, with a 403): found = alive, 404/410 = gone. Ashby and Workable
    have no single-posting address: a posting on their boards is alive while the board lists it (it was read at most a few hours ago).
    Any other page is opened (_link_alive)."""
    a = j.get("ats") if isinstance(j.get("ats"), dict) else None
    if a and a.get("kind") in ATS_POSTING and BOARD_TOKEN_RE.match(str(a.get("board") or "")):
        pid = str(a["id"]) if a.get("kind") != "smartrecruiters" else str(j.get("url", "")).rstrip("/").rsplit("/", 1)[-1]
        try:
            _get(ATS_POSTING[a["kind"]] % (urllib.parse.quote(a["board"], safe=""), urllib.parse.quote(pid, safe="")))
            return True
        except urllib.error.HTTPError as e:
            return False if e.code in (404, 410) else None
        except Exception:
            return None
    if a and a.get("kind") in ("ashby", "workable"):
        return True
    return _link_alive(str(j.get("url") or ""))


def check_links(src, sample=LINK_SAMPLE):
    """Opens up to `sample` of a source's kept jobs' apply links (the ones not checked yet first), records which are dead, hides those jobs,
    and switches the source off when more than LINK_FAIL_LIMIT of its checked links are dead. Returns the source's link record."""
    with _lock:
        c = _cache.get(src)
        jobs = list(c["jobs"]) if c else []
        rec = _links.setdefault(src, {"at": 0, "ok": 0, "dead": 0, "unknown": 0, "dead_ids": set(), "checked_ids": set(), "off": False})
    fresh = [j for j in jobs if j["id"] not in rec["checked_ids"]] or jobs
    picks = [j for j in fresh if str(j.get("url") or "").startswith("https://")][:sample]
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(job_alive, picks))
    with _lock:
        for j, alive in zip(picks, results):
            rec["checked_ids"].add(j["id"])
            if alive is True:
                rec["ok"] += 1
                rec["dead_ids"].discard(j["id"])
            elif alive is False:
                rec["dead"] += 1
                rec["dead_ids"].add(j["id"])
            else:
                rec["unknown"] += 1
        rec["at"] = time.time()
        live_ids = {j["id"] for j in jobs}
        rec["checked_ids"] &= live_ids             # jobs no longer listed are forgotten
        rec["dead_ids"] &= live_ids
        counted = rec["ok"] + rec["dead"]
        rec["off"] = counted >= 10 and rec["dead"] / counted > LINK_FAIL_LIMIT
        _version[0] += 1
    if rec["off"]:
        h = _health.setdefault(src, {"ok": 0, "fail": 0, "streak": 0, "last_ok": 0, "last_error": 0, "error": "", "jobs": 0, "ms": 0, "off_until": 0})
        h["off_until"] = time.time() + OFF_FOR
        h["retry"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(h["off_until"]))
        h["error"] = "%d of %d apply links checked were dead (over %d%%)" % (rec["dead"], counted, int(LINK_FAIL_LIMIT * 100))
        sys.stderr.write("[uaply] job feed %s switched off: %s\n" % ("/".join(src), h["error"]))
    return rec


def _link_loop():
    """The background check (hosted server only): the source checked longest ago, one at a time, LINK_PAUSE apart."""
    while True:
        time.sleep(LINK_PAUSE)
        try:
            with _lock:
                due = [s_ for s_ in _cache if time.time() - _links.get(s_, {}).get("at", 0) > LINK_EVERY and _count(_cache[s_])]
            if due:
                check_links(min(due, key=lambda s_: _links.get(s_, {}).get("at", 0)))
        except Exception as e:
            sys.stderr.write("[uaply] link check: %s: %s\n" % (type(e).__name__, str(e)[:200]))


def _start_link_check():
    if link_check_on and not _link_thread and os.environ.get("UAPLY_LINK_CHECK", "1") != "0":
        th = threading.Thread(target=_link_loop, daemon=True)
        _link_thread.append(th)
        th.start()


def feed_health():
    """Owner-only health of every source (/api/feed-health): jobs kept, successes, failures, the last success and error, the time the last
    read took, and whether it is switched off. Only counts and the source's own name, never a key or an address."""
    out = []
    with _lock:
        for src in SOURCES:
            h = dict(_health.get(src) or {})
            c = _cache.get(src)
            out.append({"source": "/".join(src[:2]), "name": src[2], "jobs": _count(c) if c else 0, "status": c["status"] if c else "",
                        "ok": h.get("ok", 0), "failures": h.get("fail", 0), "inARow": h.get("streak", 0), "lastOk": int(h.get("last_ok", 0)),
                        "lastError": int(h.get("last_error", 0)), "error": h.get("error", ""), "ms": h.get("ms", 0),
                        "off": bool(h.get("off_until")) and time.time() < h["off_until"], "retry": h.get("retry", ""),
                        "applyPath": ("assisted hand-off (the employer's own careers site)" if src[0] == "careerpage" else "hand-off (the employer's own page)"),
                        "humanCheck": (_human(src) or ("unknown",))[0], "formKind": (_human(src) or ("", "unknown"))[1],
                        "checkSampled": (_human(src) or ("", "", ""))[2], "checkPages": (_human(src) or (0, 0, 0, 0))[3],
                        "withCheck": (_human(src) or (0, 0, 0, 0, 0))[4], "checkKinds": (_human(src) or ("",) * 6)[5],
                        "route": route_label(src),
                        "links": {"checked": (_links.get(src) or {}).get("ok", 0) + (_links.get(src) or {}).get("dead", 0),
                                  "dead": (_links.get(src) or {}).get("dead", 0), "unknown": (_links.get(src) or {}).get("unknown", 0),
                                  "lastChecked": int((_links.get(src) or {}).get("at", 0))}})
    return {"sources": out, "count": len(out), "off": [x["source"] for x in out if x["off"]], "jobs": sum(x["jobs"] for x in out),
            "memoryMB": _rss_mb(),
            "humanChecks": {"sampled": _hc["sampled"], "jobsSampled": _hc["jobs"], "share": dict(_hc["share"]),
                            "systems": {k: dict(v) for k, v in _hc["systems"].items()},
                            "sources": collections.Counter(x["humanCheck"] for x in out),
                            "oneTap": sum(1 for x in out if x["route"] == ROUTE_ONE_TAP)}}


MEM_SOFT_CAP_MB = 300            # Render Starter has 512 MB: past this, no new board read starts until memory is back under it


def _rss_mb():
    """This process's resident memory in MB on Linux (the host), or None where it cannot be read."""
    try:
        with open("/proc/self/status") as f:
            return int(re.search(r"VmRSS:\s+(\d+)", f.read()).group(1)) // 1024
    except (OSError, AttributeError, ValueError):
        return None


def _start_refresh(src):
    """Read one board in a background thread unless it is already being read. Call with _lock held. Returns the event set when it is done.
    Every read of a board goes through here, so a board is never read twice at once (on October 17 every visitor who arrived during the first
    fill read the missing boards again, alongside the warm-up)."""
    ev = _refreshing.get(src)
    if ev is None:
        rss = _rss_mb()
        if rss is not None and rss > MEM_SOFT_CAP_MB and _cache.get(src):      # a board with a copy waits for memory to come back down
            done = threading.Event()
            done.set()
            return done
        ev = _refreshing[src] = threading.Event()
        # queued for FEED_PARALLEL reader threads, in the order asked (SOURCES order on a fresh start): with 500 sources a thread
        # each, all waiting for a slot, cost about 30 MB of thread stacks
        slow = src[0] == "careerpage"
        pool, q, size = (_slow_readers, _to_read_slow, CP_PARALLEL) if slow else (_readers, _to_read, FEED_PARALLEL)
        while len(pool) < size:
            th = threading.Thread(target=_reader, args=(q,), daemon=True)
            pool.append(th)
            th.start()
        q.put((src, ev))
    return ev


_to_read = queue.Queue()         # (source, event) waiting to be read
_readers = []                    # the reader threads (started on first use, FEED_PARALLEL of them)
_to_read_slow = queue.Queue()    # the same for careers sites (CP_PARALLEL threads of their own)
_cp_slots = threading.BoundedSemaphore(CP_PARALLEL)
_slow_readers = []


def _reader(q=_to_read):
    while True:
        src, ev = q.get()
        try:
            _refresh_in_background(src, ev)
        except Exception as e:                   # never lose a reader thread
            log_line = "[uaply] job feed reader: %s: %s\n" % (type(e).__name__, _scrub(str(e))[:200])
            sys.stderr.write(log_line)


FILE_SET = set(FILE_SOURCES)


def _ttl(src):
    """How old a board's copy may get before it is read again: its kind's TTL (2 hours for a job-boards.json board), moved by up to
    a quarter either way by a hash of its name, so a few hundred boards do not all come due in the same minute."""
    base = FILE_TTL if src in FILE_SET else TTL.get(src[0], DEFAULT_TTL)
    h = int(hashlib.sha1("|".join(src).encode()).hexdigest()[:4], 16) / 65535.0
    return base * (0.75 + 0.5 * h)


def _load_source(src):
    """Serve what is cached right away, even if stale, and refresh it in the background. Never makes a visitor wait for a board while the
    saved list has anything to show (a board that is new, or failed last time, shows up at the next request). Only on an empty disk (the
    very first start) does the first request wait for the boards, as there is nothing else to show."""
    ttl = _ttl(src)
    if _no_key(src[0]):
        return _fetch_source(src)                # no key: skipped right away, never served from an older copy
    if _disabled(src):
        with _lock:
            c = _cache.get(src)
        return (c["jobs"] if c else []), "off: failed %d refreshes in a row; tried again %s" % (FAIL_LIMIT, _health[src].get("retry", ""))
    with _lock:
        c = _cache.get(src)
        if c:
            if time.time() - c["at"] >= ttl:
                _start_refresh(src)
            return c["jobs"], c["status"]
        f = _failed.get(src)
        if f and time.time() - f[0] < 120:
            return [], f[1]
        ev = _start_refresh(src)
        if _disk["filled"]:                      # the saved list has the other boards: do not hold this visitor up for this one
            return [], "loading"
    # every visitor of the first fill shares one deadline (FIRST_WAIT from the first wait), so the boards are waited for together
    with _lock:
        until = _disk.setdefault("first_wait_until", time.time() + FIRST_WAIT)
    ev.wait(max(0.0, until - time.time()))
    with _lock:
        c = _cache.get(src)
        f = _failed.get(src)
    return (c["jobs"], c["status"]) if c else ([], f[1] if f else "loading")


def _start_missing(sources):
    """On the very first fill, start reading every board that has nothing saved, all at once (FEED_PARALLEL of them actually download
    at a time), so the sources can then be collected one after another without a thread per source per visitor."""
    if _disk["filled"]:
        return
    keys = feed_keys()                     # read before the lock: it reads and parses the settings file
    by_kind = {}
    for src in sources:                    # each kind keeps its own order (tri-state boards first)
        by_kind.setdefault(src[0], []).append(src)
    lanes = list(by_kind.values())
    order = [lane[i] for i in range(max((len(x) for x in lanes), default=0)) for lane in lanes if i < len(lane)]
    with _lock:
        for src in order:
            if not _no_key(src[0], keys) and src not in _cache and not (src in _failed and time.time() - _failed[src][0] < 120):
                _start_refresh(src)


# ---------- the Simplify / Pitt CSC internship lists (GitHub) ----------
SIMPLIFY_REPO = "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/"
SIMPLIFY_CHECK_TTL = 24 * 3600         # each listed posting is read from its own board at most once a day
# The apply links UAply can check on the employer's own public board, and the board API address each one is read from. The pieces are
# matched strictly (letters, digits, - _ . and numeric or uuid ids) and only ever put into these fixed API hosts: a list row can never
# make the server fetch an address of its choosing.
SIMPLIFY_ATS = [
    ("greenhouse", re.compile(r"^https://(?:job-)?boards\.greenhouse\.io/([A-Za-z0-9_-]{1,80})/jobs/(\d{1,20})(?:[/?#]|$)"),
     "https://boards-api.greenhouse.io/v1/boards/%s/jobs/%s"),
    ("lever", re.compile(r"^https://jobs\.lever\.co/([A-Za-z0-9_.-]{1,80})/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:[/?#]|$)"),
     "https://api.lever.co/v0/postings/%s/%s?mode=json"),
    ("smartrecruiters", re.compile(r"^https://jobs\.smartrecruiters\.com/([A-Za-z0-9_-]{1,80})/(\d{6,20})(?:[-/?#]|$)"),
     "https://api.smartrecruiters.com/v1/companies/%s/postings/%s"),
]
_simplify_checked = {}                 # (kind, board, posting id) -> {"at", "raw", "lists"}: raw is None when the posting is gone from its board
SIMPLIFY_TEXT = 4000                   # characters of a checked posting kept (skills, pay, schedule and the summary are read from the start)
SIMPLIFY_FIELDS = ("id", "title", "company", "loc", "remote", "text", "url", "salary_text", "posted", "updated", "emp", "ats_id", "country")


def _simplify_rows(text):
    """The open rows of one README table: (company, title, location, apply link, age in days). A row marked closed (a lock) or with no
    apply link is left out; a company cell of "↳" repeats the company above."""
    rows, company = [], ""
    for tr in re.findall(r"<tr>(.*?)</tr>", text, re.S):
        cells = re.findall(r"<td>(.*?)</td>", tr, re.S)
        if len(cells) < 5:
            continue
        name = _text(cells[0]).replace("\U0001f525", "").strip()
        company = company if name in ("↳", "") else name
        if "\U0001f512" in tr:
            continue
        # the summer list has 5 columns, the off-season one 6 (a Terms column): the apply cell is the one with the Apply button, the age is last
        apply_cell = next((c for c in cells if 'alt="Apply"' in c), "")
        link = re.search(r'<a href="(https://[^"]+)"', apply_cell)
        age = re.match(r"\s*(\d+)\s*(d|mo)\b", _text(cells[-1]))
        if not link or not age or not company:
            continue
        days = int(age.group(1)) * (30 if age.group(2) == "mo" else 1)
        place = "; ".join(p for p in (_text(x).strip() for x in re.split(r"<br\s*/?>|</br>", re.sub(r"<summary>.*?</summary>", "", cells[2], flags=re.S))) if p)
        rows.append((company, _text(cells[1]).strip(), place, html.unescape(link.group(1)).split("?", 1)[0], days))
    return rows


def _simplify_check(kind, board, pid, api):
    """The posting as its own board shows it (a raw posting), or None when the board no longer has it. Cached for SIMPLIFY_CHECK_TTL."""
    key = (kind, board, pid)
    with _lock:
        c = _simplify_checked.get(key)
    if c and time.time() - c["at"] < SIMPLIFY_CHECK_TTL:
        return c["raw"]
    raw = None
    try:
        j = _get(api % (urllib.parse.quote(board, safe=""), urllib.parse.quote(pid, safe="")))
        if kind == "greenhouse" and isinstance(j, dict) and j.get("id"):
            raw = dict(id=j["id"], title=j.get("title") or "", company=j.get("company_name") or "", loc=(j.get("location") or {}).get("name", ""),
                       remote=None, text=_text(j.get("content")), url=j.get("absolute_url") or "", salary_text="",
                       posted=_ts(j.get("first_published") or j.get("updated_at")), updated=_ts(j.get("updated_at")), emp=_gh_emp(j))
        elif kind == "lever" and isinstance(j, dict) and j.get("id"):
            cat = j.get("categories") or {}
            raw = dict(id=j["id"], title=j.get("text") or "", company="", loc=cat.get("location", "") or "", remote=(j.get("workplaceType") == "remote") or None,
                       text=_text((j.get("descriptionPlain") or "") + " " + (j.get("additionalPlain") or "")), url=j.get("hostedUrl") or "",
                       salary_text="", posted=_ts(j.get("createdAt")), emp=cat.get("commitment"))
        elif kind == "smartrecruiters" and isinstance(j, dict) and j.get("id") and j.get("active") is not False:
            L = j.get("location") or {}
            secs = ((j.get("jobAd") or {}).get("sections")) or {}
            raw = dict(id=j["id"], title=j.get("name") or "", company=(j.get("company") or {}).get("name") or "",
                       loc=", ".join(x for x in (L.get("city"), L.get("region"), (L.get("country") or "").upper()) if x), remote=True if L.get("remote") else None,
                       text=_text(" ".join((secs.get(k) or {}).get("text") or "" for k in ("jobDescription", "qualifications", "additionalInformation"))),
                       country=L.get("country") or "us",
                       url="https://jobs.smartrecruiters.com/%s/%s" % (board, j["id"]), salary_text="", posted=_ts(j.get("releasedDate")),
                       emp=((j.get("typeOfEmployment") or {}).get("label") or ""), ats_id=str(j.get("uuid") or ""))
        ok = True
    except urllib.error.HTTPError as e:
        ok = e.code in (404, 410)              # gone from the board: remembered as gone; any other error is tried again next time
    except Exception:
        ok = False
    if ok:
        if raw:                                # only what _simplify and _normalize read, and the start of the text (a posting can be 20,000 characters)
            raw = {k: raw[k] for k in SIMPLIFY_FIELDS if k in raw}
            raw["text"] = (raw.get("text") or "")[:SIMPLIFY_TEXT]
        with _lock:
            _simplify_checked[key] = {"at": time.time(), "raw": raw, "lists": set()}
    return raw


def _simplify_forget(token, keys_now):
    """After one list is read: entries this list no longer names lose it, and an entry no list names, or checked more than two days ago,
    is dropped (the map used to keep every posting ever checked)."""
    now = time.time()
    with _lock:
        for key in list(_simplify_checked):
            e = _simplify_checked[key]
            lists = e.setdefault("lists", set())
            if key in keys_now:
                lists.add(token)
            else:
                lists.discard(token)
            if not lists or now - e["at"] > 2 * SIMPLIFY_CHECK_TTL:
                del _simplify_checked[key]


def _simplify(token, name):
    """Open, recent (60 days at most), US rows of one Simplify / Pitt CSC README whose apply link is a Greenhouse, Lever or SmartRecruiters
    posting, each read from that board (newest rows first, at most KEEP["simplify"] checks). Rows on other systems cannot be checked and
    are left out. The README is plain text (about 1-2 MB): parsed and dropped before any check starts."""
    text = _get(SIMPLIFY_REPO + token, as_text=True)
    rows = _simplify_rows(text)
    del text
    todo, seen = [], set()
    for company, title, place, link, days in sorted(rows, key=lambda r: r[4]):
        if days > MAX_AGE_DAYS or not _us_ok(place, bool(re.search(r"\bremote\b", place, re.I))):
            continue
        for kind, rx, api in SIMPLIFY_ATS:
            m = rx.match(link)
            if m and (kind, m.group(1), m.group(2)) not in seen:
                seen.add((kind, m.group(1), m.group(2)))
                todo.append((company, kind, m.group(1), m.group(2), api))
                break
        if len(todo) >= KEEP["simplify"]:
            break
    with ThreadPoolExecutor(max_workers=4) as ex:                # four at a time, as for SmartRecruiters
        found = list(ex.map(lambda t: _simplify_check(t[1], t[2], t[3], t[4]), todo))
    _simplify_forget(token, {(k, b, i) for _, k, b, i, _ in todo})
    default = "internship" if token == "README.md" else None     # the summer list is internships only; the off-season one mixes co-ops in
    for (company, kind, board, pid, _), raw in zip(todo, found):
        if raw and raw["title"] and raw["url"].startswith("https://"):
            yield dict(raw, company=raw["company"] or company, ats_kind=kind, board=board, list_credit=name,
                       default_type=default or ("co-op" if re.search(r"\bco-?op\b", raw["title"], re.I) else "internship"))


def _no_key(kind, keys=None):
    """True for a feed that needs a key the owner has not added: USAJOBS (UAPLY_USAJOBS_KEY or feed_keys), CareerOneStop (both
    UAPLY_COS_USER_ID and UAPLY_COS_TOKEN). `keys`: feed_keys() already read (it reads uaply-config.json), for a caller checking many."""
    if kind not in ("usajobs", "careeronestop"):
        return False
    keys = feed_keys() if keys is None else keys
    return not keys.get("usajobs" if kind == "usajobs" else "cos_token")


def _fetch_source(src):
    kind, token, name = src
    ttl = _ttl(src)
    started = time.time()
    if _no_key(kind):
        with _lock:
            _cache.pop(src, None)               # a key that was removed stops the source at once (no copy is served from before)
        return [], "no key"                     # skipped, nothing fetched or cached: the source starts the moment the owner adds the key
    try:
        student, other, local, old = [], [], [], 0
        now_ms = time.time() * 1000
        keep = KEEP.get(kind) if (kind != "smartrecruiters" or token in SR_WHOLE) else None   # a whole public list, or None for an employer board
        lazy, listed = [], set()
        # at most FEED_PARALLEL boards downloaded and parsed at once (memory, see FEED_PARALLEL); careers sites have places of their own:
        # holding a board's place through 2-second crawl delays, 16 of them kept the boards waiting (14 boards in the first 70 s)
        with (_cp_slots if kind == "careerpage" else _feed_slots):
            for raw in _iter_raw(kind, token, name):
                if kind not in AGE_EXEMPT and _too_old(raw, now_ms) and not (kind in EVERGREEN_KINDS and _job_type(raw) in EVERGREEN_TYPES):
                    # (before the caps, so a stale posting never takes a fresh one's place)
                    old += 1
                    continue
                if raw.get("lazy"):                  # Greenhouse: pick the postings to keep from the list, read their descriptions after
                    listed.add(raw["lazy"][1])
                    if not _us_ok(raw["loc"], bool(re.search(r"\bremote\b", raw["loc"], re.I))) or _gh_skip.get(raw["lazy"][:2]) == raw["lazy"][2]:
                        continue                     # not a US job, or read before and not kept (no skill to score it on) and unchanged since
                    lazy.append(raw)                 # every eligible posting, in board order (small: no description yet)
                    continue
                # only the first STUDENT_PER_SOURCE student roles and PER_SOURCE others can be kept below, so a posting past those is not worked
                # through at all (a big board lists hundreds; reading every one cost about 35 CPU seconds, a minute or more on a small host)
                bucket, cap = (other, PER_SOURCE) if _type(raw) == "job" else (student, STUDENT_PER_SOURCE)
                if keep:                                             # the City and USAJOBS keep up to 120 (student roles first), so read them all
                    cap = keep
                if len(bucket) >= cap:
                    # past the caps only a Pennsylvania, New Jersey or Delaware role is still worked through, up to LOCAL_PER_SOURCE of them
                    if not keep and len(local) < LOCAL_PER_SOURCE and LOCAL_RE.search(raw.get("loc") or ""):
                        j = _normalize(raw, kind, name, token)
                        if j:
                            local.append(j)
                    continue
                j = _normalize(raw, kind, name, token)
                if j:
                    (student if j["type"] in ("internship", "coop", "parttime") else other).append(j)
            if lazy:
                # in waves: as many postings as there are places left (by the type the list shows), their descriptions read, then
                # another wave only for places a posting could not fill (nothing to score it on) - no spare description is read
                prev = {j["id"]: j for j in (_cache.get(src) or {}).get("jobs", [])}
                # the same split the board's jobs get below: student roles first, the rest of the 14 (at least 6) for other jobs
                n_st = min(STUDENT_PER_SOURCE, sum(1 for r in lazy if _type(r) != "job"))
                n_ot = max(OTHER_PER_SOURCE, PER_SOURCE - n_st)
                for _wave in range(LAZY_WAVES):
                    room = {"other": n_ot - len(other), "student": STUDENT_PER_SOURCE - len(student), "local": LOCAL_PER_SOURCE - len(local)}
                    batch, rest = [], []
                    for raw in lazy:                 # a posting not taken this wave stays for the next one
                        b = "other" if _type(raw) == "job" else "student"
                        if room[b] > 0:
                            room[b] -= 1
                            batch.append(raw)
                        elif room["local"] > 0 and LOCAL_RE.search(raw["loc"] or ""):
                            room["local"] -= 1
                            batch.append(raw)
                        else:
                            rest.append(raw)
                    lazy = rest
                    if not batch:
                        break
                    for raw, f in zip(batch, _gh_fill(batch, prev, len(listed))):
                        if f is None:
                            continue
                        if "role" in f:              # the job made last time, unchanged
                            j = f
                        else:
                            j = _normalize(f, kind, name, token)
                            seen = f.get("_seen")
                            if seen:
                                (_gh_seen if j else _gh_skip)[seen[:2]] = seen[2]
                        if not j:
                            continue
                        bucket, cap = (other, PER_SOURCE) if j["type"] == "job" else (student, STUDENT_PER_SOURCE)
                        if len(bucket) < cap:
                            bucket.append(j)
                        elif len(local) < LOCAL_PER_SOURCE and LOCAL_RE.search(j["loc"]):
                            local.append(j)
                with _lock:                          # forget postings no longer on the board
                    for m in (_gh_seen, _gh_skip):
                        for key in [k for k in m if k[0] == token and k[1] not in listed]:
                            del m[key]
        # keep the student-type roles first (a board can list hundreds of senior roles ahead of its internships)
        if keep:
            jobs = (student + other)[:keep]
        else:
            n_other = max(OTHER_PER_SOURCE, PER_SOURCE - len(student[:STUDENT_PER_SOURCE]))
            jobs = student[:STUDENT_PER_SOURCE] + other[:n_other]
            # tri-state roles cut by the split above go first among the extras, then the ones found past the caps
            spill = [j for j in other[n_other:] if LOCAL_RE.search(j["loc"])]
            jobs += (spill + local)[:LOCAL_PER_SOURCE]
        status = "%d jobs" % len(jobs) + ("; %d older than %d days left out" % (old, MAX_AGE_DAYS) if old else "")
    except Exception as e:                      # keep serving the last good copy if the feed is down
        c = _cache.get(src)
        jobs = c["jobs"] if c else []
        why = _scrub(str(e))                    # a feed key is never written to the log or the status line
        if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403) and kind in ("usajobs", "muse"):
            why = "the feed refused the key (HTTP %d); check it on the setup page" % e.code
        status = "error: %s" % why[:80]
        sys.stderr.write("[uaply] job feed %s failed: %s\n" % ("/".join(src), why[:200]))      # the reason is kept in the server's own log
        _note_health(src, False, error=why, ms=int((time.time() - started) * 1000))
        _version[0] += 1
        with _lock:
            if c:
                c["at"] = time.time() - ttl + 120   # retry in two minutes
            else:
                _failed[src] = (time.time(), status)   # nothing to fall back on: say so, and try again in two minutes (not at every request)
        return jobs, status
    _note_health(src, True, jobs=len(jobs), ms=int((time.time() - started) * 1000))
    packed = _entry(time.time(), jobs, status)       # kept packed; the list itself is only returned to the caller
    with _lock:
        _version[0] += 1
        _cache[src] = packed
        _failed.pop(src, None)
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
    {"feeds_off": ["remotive"]}. The kinds: greenhouse, lever, ashby, smartrecruiters, workable, usajobs, jobicy, muse, remotive."""
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
    """{(kind, board): api_key} for employers who connected their own hiring system (Greenhouse, Lever, Ashby, SmartRecruiters or Workable) with a key they created. Read from the
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
        # the employer's own hiring system (Greenhouse, Lever, Ashby, SmartRecruiters or Workable) and the key they created for it: applications to their jobs go straight in
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
            jid = _claim_id("partner:%s:%s" % (name, role), 200000)      # the same id as before unless another posting has it (_claim_id)
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
    """How an application to this job may be handled: 'direct' (the employer opted in), 'email' (the posting itself asks for applications
    by email at the employer's own address: apply_address), 'link' (send the person to the employer's own page; nothing is emailed) or
    'unknown' (an example listing). An address on the bounce list (it bounced, or its owner asked UAply to stop) is 'link' again."""
    for j in partner_jobs():
        if j["id"] == job_id:
            return j["apply"]
    conns = ats_connections()
    j = _find_job(job_id)
    if j:
        # a real posting whose employer connected their hiring system with their own key can be applied to instantly
        if _connected(j, conns):
            return "direct"
        return "email" if j.get("apply") == "email" and j.get("contact") and not mailer.suppressed(j["contact"]) else "link"
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
    j = _find_job(job_id)
    if j and _connected(j, conns):
        return {"kind": j["ats"]["kind"], "board": j["ats"]["board"], "id": j["ats"]["id"], "key": conns[(j["ats"]["kind"], j["ats"]["board"])]}
    return None


_LOAD_SOURCE = _load_source


def get_jobs():
    """The job list as one dict (see the module notes): each job a copy with postedDays (and updatedDays), a feed job without its email
    description, a connected employer's posting marked as applied to directly."""
    meta, conns, now_ms, blocked = {}, ats_connections(), time.time() * 1000, mailer.blocked_addresses()
    jobs = [_out_job(j, now_ms, conns, feed, blocked) for j, feed in _collect(meta, now_ms)]
    return dict(meta, jobs=jobs)


def apply_classes():
    """How many listed jobs take each way of applying (for /api/status), counted one job at a time (no copy of the list). "email" counts
    partner employers that take email and postings that ask for applications by email ("postingEmail" is those postings alone)."""
    meta, conns, now_ms, blocked = {}, ats_connections(), time.time() * 1000, mailer.blocked_addresses()
    c = {"ats": 0, "email": 0, "webhook": 0, "handoff": 0, "postingEmail": 0}
    for j, feed in _collect(meta, now_ms):
        o = _out_job(j, now_ms, conns, feed, blocked)
        inst = bool(o.get("instant"))
        c["ats"] += inst and not o.get("contact") and not o.get("webhook")
        c["email"] += inst and bool(o.get("contact"))
        c["postingEmail"] += o.get("apply") == "email"
        c["webhook"] += inst and bool(o.get("webhook"))
        c["handoff"] += not inst
    return c


# What the list form (/api/jobs, get_jobs) leaves out of a feed job, because no card shows it (measured October 23, 2026 on 14,326 jobs:
# 13.3 MB of JSON): the 650-character description (only the emails use it, from this server's own copy), the record's credit line ("via
# ..." again, which the server takes from its own copy, never the browser's), the update date and its age, the official announcement
# (both read from this server's copy for the receipt), and of the employer-system reference only its kind (the app asks
# job.ats.kind === "greenhouse"; the board and posting id stay here). GET /api/jobs/<id> answers the whole job (job_full).
LIST_DROP = ("desc", "credit", "updated", "updatedDays", "announcement")


def _out_job(j, now_ms, conns, feed, blocked=frozenset(), full=False):
    """`feed`: False for a partner employer's job, else its feed's route label (or True). `blocked`: the addresses on the bounce list
    (mailer.blocked_addresses): a posting whose application address is on it is a hand-off again. full: every field (the per-job route)."""
    out = _with_age(j, now_ms, drop=("desc",) if feed and not full else ())
    if feed and out.get("apply") == "email" and str(out.get("contact") or "").lower() in blocked:
        out.update(contact="", apply="link", instant=False)          # it bounced, or its owner asked UAply to stop: finish on their site
    if conns and _connected(out, conns):        # marked on the copy, so the shared cache stays as fetched
        out.update(apply="direct", instant=True, contact="")          # their own hiring system takes it: never also an email
    # sent in UAply (a connected system, or an email to the employer): "Ready"; a hand-off: its source's label
    out["route"] = ROUTE_READY if out.get("instant") or not isinstance(feed, str) else feed
    if feed and not full:
        for k in LIST_DROP:
            out.pop(k, None)
        if isinstance(out.get("ats"), dict):
            out["ats"] = {"kind": out["ats"].get("kind")}       # a new dict: the cached job keeps its whole reference
    return out


def job_full(job_id):
    """One listed job with every field the list form leaves out (LIST_DROP), as the app would get it, or None. A feed job is looked up in
    the cache, a partner employer's job in the partner list (an employer's account email never goes out, as in the list)."""
    now_ms, conns = time.time() * 1000, ats_connections()
    for pj in partner_jobs():
        if pj["id"] == job_id:
            return _out_job({k: v for k, v in pj.items() if k != "contact"} if pj.get("emp") else pj, now_ms, conns, False)
    j = _find_job(job_id)
    if not j:
        return None
    src = next((s for s in SOURCES if _has(_cache.get(s) or {}, job_id)), None)
    return _out_job(j, now_ms, conns, route_label(src) if src else True, mailer.blocked_addresses(), full=True)


def _collect(meta, now_ms):
    """The jobs to show, yielded one at a time as (job, is it a feed job) in order, one source unpacked at a time (never the whole list
    at once); the list's other fields (sources, merged, aged_out, pending, fetched_at) are put in `meta` once every source is through."""
    _load_disk()
    allowed = feeds_allowed()
    sources = [s for s in SOURCES if s[0] in allowed]
    # One after another, not a thread per source: with 80 sources and three visitors on a fresh start that was 240 threads waiting
    # (about 30 MB of the 135 MB peak, October 21, 2026). The boards themselves are read in the background (_start_refresh).
    if _load_source is _LOAD_SOURCE:                 # (a test that stands in its own _load_source reads nothing)
        _start_missing(sources)
        _start_link_check()
    seen, same, summary = set(), {}, {}            # same: a job's _same_job_key -> the source that listed it first
    merged = aged = 0
    partners = partner_jobs()
    for pj in partners:
        seen.add(pj["id"])
        same[_same_job_key(pj)] = "partner"  # a feed's copy of a partner's posting is dropped below: the partner's own one can really be applied to
        yield ({k: v for k, v in pj.items() if k != "contact"} if pj.get("emp") else pj, False)    # an employer's account email stays on this server
    summary["Partner employers"] = "%d jobs" % len(partners)
    # Feeds in SOURCES order, so when two feeds carry the same job the employer's own board (listed first) is the copy that is kept.
    # Only copies from two different feeds are merged: one employer listing a title twice in one place (the City's two "Technical Support
    # Specialist" postings are for different departments) keeps both, as they can be two openings.
    for src in sources:
        js, status = _load_source(src)               # one source unpacked at a time
        summary[src[2] + ("/" + src[1] if src[0] in MULTI else "")] = "unavailable right now" if hide_errors and status.startswith("error") else status
        dead = (_links.get(src) or {}).get("dead_ids") or ()
        route = route_label(src)                     # yielded in place of True: a feed job, and the label of its route
        for j in js:
            if j["id"] in seen or j["id"] in dead:      # a job whose apply link was found dead is not shown (check_links)
                continue
            if src[0] not in AGE_EXEMPT and _too_old(j, now_ms) and not (src[0] in EVERGREEN_KINDS and j.get("jobType") in EVERGREEN_TYPES):
                # (a saved copy can be up to a day old: one that turned 60 days since goes now)
                aged += 1
                continue
            key = _same_job_key(j)
            if same.get(key, src) != src:
                merged += 1
                continue
            seen.add(j["id"])
            same.setdefault(key, src)
            # a feed job's 650-character description is only for the emails (the server reads it from its own copy, job_info): it was
            # half of the list's size, so the app is sent the card's blurb only (see _out_job)
            yield (j, route)
        del js
    _disk["filled"] = True
    if not sources:
        summary["Third-party feeds"] = "off (not verified as permitted)"
    _save_disk()
    pending = sum(1 for v in summary.values() if v == "loading")
    meta.update({"fetched_at": int(time.time()), "sources": summary, "merged": merged, "aged_out": aged, "pending": pending})


JSON_MEMO_S = 20                 # seconds the encoded job list is reused while nothing changed (a few thousand jobs are megabytes to encode)
_json_memo = {"key": None, "at": 0.0, "gz": b"", "pending": 0, "blocks": [], "kinds": [], "meta": {}, "stamp": 0}
PAGE_SIZE, PAGE_MAX = 200, 1000  # the paged form (get_page): jobs per page when none is asked for, and the most one page may hold
PAGE_BLOCK = 250                 # jobs per compressed block of the memo (a page unpacks only the blocks it needs)
PAGE_TYPES = ("job", "parttime", "internship", "coop")      # the deck's stacks (a job's "type"), the paged form's type filter
_json_lock = threading.Lock()
_version = [0]                   # raised whenever a source's copy or status changes


def get_json(compressed=False):
    """The job list as JSON bytes (gzip-compressed with compressed=True), encoded once and reused for up to JSON_MEMO_S seconds while no
    source, partner posting or connected hiring system changed: every visitor's request used to build and encode the whole list again."""
    import gzip
    m = _memo()
    return m["gz"] if compressed else gzip.decompress(m["gz"])


def get_page(size=None, page=None, cursor=None, types=None):
    """One page of the job list as JSON bytes: {"jobs": [...], "total", "page", "size", "next", and the list's other fields (sources,
    merged, aged_out, pending, fetched_at)}. The same jobs in the same order as get_json, cut from the same memo (nothing is encoded again).
    size: jobs per page (PAGE_SIZE, at most PAGE_MAX). page: 1 for the first. cursor: the "next" of the page before, which carries on where
    it ended even if the list was rebuilt meanwhile ("changed": true then, and the app keeps telling jobs apart by id). types: a job's
    "type" values to keep (PAGE_TYPES), all when empty; "total" counts the jobs that pass it."""
    m = _memo()
    with _json_lock:
        blocks, kinds, meta, stamp = m["blocks"], m["kinds"], m["meta"], m["stamp"]
    try:
        size = min(PAGE_MAX, max(1, int(size))) if size not in (None, "") else PAGE_SIZE
    except (TypeError, ValueError):
        size = PAGE_SIZE
    want = {t for t in (types or ()) if t in PAGE_TYPES}
    sel = [i for i, k in enumerate(kinds) if k in want] if want else range(len(kinds))
    changed, start = False, 0
    if cursor:
        try:
            cs, pos = (int(x) for x in str(cursor).split(".", 1))
        except ValueError:
            cs, pos = stamp, 0
        changed = cs != stamp
        import bisect
        start = bisect.bisect_left(sel, pos)                     # the first job at or after where the page before ended
        page = None
    else:
        try:
            page = max(1, int(page)) if page not in (None, "") else 1
        except (TypeError, ValueError):
            page = 1
        start = (page - 1) * size
    chosen = sel[start:start + size]
    lines, opened = [], {}
    for i in chosen:
        b = i // PAGE_BLOCK
        if b not in opened:
            opened[b] = zlib.decompress(blocks[b]).split(b"\n")
        lines.append(opened[b][i % PAGE_BLOCK])
    nxt = "%d.%d" % (stamp, chosen[-1] + 1) if chosen and start + size < len(sel) else None
    head = dict(meta, total=len(sel), page=page, size=size, next=nxt)
    if changed:
        head["changed"] = True
    return b'{"jobs":[' + b",".join(lines) + b"]," + json.dumps(head, separators=(",", ":"))[1:].encode("utf-8")


def _memo():
    """The encoded job list (see get_json), rebuilt when it is out of date: the whole list gzip-compressed, and the same jobs in blocks of
    PAGE_BLOCK (zlib, one job per line) with each job's type, for get_page."""
    pj = partner_jobs()
    blocked = mailer.blocked_addresses()        # an address that bounced or asked UAply to stop: its postings are hand-offs again at once
    key = (_version[0], tuple((j.get("id"), j.get("closed"), j.get("posted"), j.get("role")) for j in pj), tuple(sorted(ats_connections())), hide_errors,
           hash(blocked))
    with _json_lock:
        m = _json_memo
        age = time.time() - m["at"]
        # while sources are still loading (a fresh start) the list changes all the time: it is rebuilt at most every 3 seconds, however many
        # visitors' apps ask again meanwhile; once everything is in, it is reused until something changes (or JSON_MEMO_S passes)
        reuse = bool(m["gz"]) and ((m.get("pending") and age <= 3) or (not m.get("pending") and m["key"] == key and age <= JSON_MEMO_S))
        if not reuse:
            # written one job at a time straight into the compressor: no copy of the whole list, no megabytes of text at once (at 7,000
            # jobs the copies and the text were about 30 MB on top of the jobs themselves); only the compressed list is kept
            # Compact JSON (no spaces after , and :): about 7% fewer bytes to parse on a phone, the same once compressed.
            meta, conns, now_ms = {}, ats_connections(), time.time() * 1000
            z = zlib.compressobj(5, zlib.DEFLATED, 31)          # 31: a gzip stream
            parts, blocks, block, kinds = [z.compress(b'{"jobs":[')], [], [], []
            for i, (j, feed) in enumerate(_collect(meta, now_ms)):
                line = json.dumps(_out_job(j, now_ms, conns, feed, blocked), separators=(",", ":")).encode("utf-8")
                parts.append(z.compress((b"," if i else b"") + line))
                block.append(line)                               # (JSON text never holds a raw line break: one job per line)
                kinds.append(sys.intern(j.get("type") or "job"))
                if len(block) == PAGE_BLOCK:
                    blocks.append(zlib.compress(b"\n".join(block), 5))
                    block = []
            if block:
                blocks.append(zlib.compress(b"\n".join(block), 5))
            parts.append(z.compress(b"]," + json.dumps(meta, separators=(",", ":"))[1:].encode("utf-8")) + z.flush())     # the list's other fields after the jobs
            m.update(key=(_version[0],) + key[1:], at=time.time(), gz=b"".join(parts), pending=meta.get("pending", 0),
                     blocks=blocks, kinds=kinds, meta=meta, stamp=m["stamp"] + 1)
            del parts, block
        return m
