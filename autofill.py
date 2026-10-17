"""Autofill: answer a real job application form from the person's UAply profile.

Greenhouse publishes every job's application form (its questions, field types and options) through its public Job Board API, with no key:
  GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}?questions=true
This module reads that form and works out, question by question, what the person's profile answers. The result is a plan:

  fields   [(field name, value)]   ready to POST into the employer's Greenhouse board (only with the employer's own key: see ats_api.py)
  files    [(field, filename, type, bytes)]
  items    one entry per question: the label, whether it is required, the answer shown to the person, and whether it still needs them
  missing  the required questions the profile cannot answer (the app asks these once, in a short sheet, and remembers the answers)

How a question is answered, in order:
  1. Standard fields: first and last name, email, phone, resume file, cover letter.
  2. The person's saved answer to this same question (any earlier employer that asked it; the company's name is ignored when matching).
  3. A rule that maps the question to a profile detail: work authorization, sponsorship, LinkedIn, website, location, country, state, ZIP,
     school, degree, major, graduation date, GPA, most recent employer, job title and dates there, years of experience, earliest start,
     "how did you hear", relocation, expected pay (only when the person entered it, and only to a form that requires it), office work, former
     employee, government official, 18 or older (confirmed in the first-application agreement), and an optional "why this company"
     template the person wrote themselves.
  4. Legal acknowledgments (privacy notices, AI-use notices) are ticked only when the person switched on "Acknowledge employers' notices for me".
  5. Voluntary self-identification (gender, race, veteran, disability) is never answered. Greenhouse keeps those in separate optional sections,
     which UAply does not send; any such question inside the main form is skipped.

Ashby and SmartRecruiters show a posting's form only to the employer's own key, so ats_api.py reads those and hands them here as a plain list of
questions (plan_questions). Both planners answer each question through _answer, so the rules above are written once for every hiring system.

Greenhouse also takes a few fields its own careers page fills in without asking: the country (country_short_name), the location with its
map position (location, latitude and longitude, always together: Greenhouse ignores a location without them) and the most recent job
(employments[0][...]). Those are added whenever the profile has them.

Nothing here sends anything. Reading a public form is the same request the employer's own careers page makes.
"""
import json
import os
import re
import threading
import time
import urllib.request

import ats_api

_CACHE = {}
_LOCK = threading.Lock()
TTL = 6 * 3600
MAX_CACHED = 600

_START = {"now": "Immediately", "2w": "Within 2 weeks", "1m": "Within a month", "grad": "After graduation", "flex": "Flexible"}
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_EDU = {"High school": "High School", "Associate": "Associate's Degree", "Bachelor": "Bachelor's Degree", "Master": "Master's Degree", "Doctorate": "Doctorate"}


def read_form(board, job_id):
    """(form, HTTP status) for the job's public Greenhouse application form; form is None when it could not be read.
    Cached for six hours; a failed read is remembered for five minutes so a missing posting is not asked for on every swipe."""
    if not (isinstance(board, str) and ats_api.TOKEN_RE.match(board) and isinstance(job_id, str) and ats_api.ID_RE.match(job_id)):
        return None, 0
    key = (ats_api._base("greenhouse"), board, job_id)
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < (TTL if hit[1] is not None else 300):
            return hit[1], hit[2]
    status, form = ats_api._call(urllib.request.Request("%s/v1/boards/%s/jobs/%s?questions=true" % (key[0], board, job_id),
                                                        headers={"Accept": "application/json", "User-Agent": "UAply/1.0"}), timeout=8)
    form = form if status == 200 and isinstance(form, dict) else None
    if form:                                       # keep only what the plan needs (the posting text is large and not used here)
        form = {k: form.get(k) for k in ("questions", "location_questions", "company_name", "title", "absolute_url")}
    with _LOCK:
        if len(_CACHE) >= MAX_CACHED:
            for k in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:MAX_CACHED // 4]:
                _CACHE.pop(k, None)
        _CACHE[key] = (now, form, status)
    return form, status


def fetch_form(board, job_id):
    """The job's public Greenhouse application form, or None."""
    return read_form(board, job_id)[0]


def norm(label, company=""):
    """The key a saved answer is stored under: lower case, the company's name replaced, punctuation and extra spaces removed."""
    s = (label or "").lower()
    if company:
        s = re.sub(re.escape(company.lower()), " {co} ", s)
    s = re.sub(r"[^a-z0-9{} ]+", " ", s)
    # cut to 160 first, then trim: a long question cut right after a word used to end in a space, the browser saved the answer
    # under that key, clean_answers() trimmed it, the two never matched, and the person was asked the same question forever
    return re.sub(r"\s+", " ", s).strip()[:160].strip()


# ------------------------------------------------------------------------------------------------------------------------------- rules
_EEO = re.compile(r"\b(gender|race|racial|ethnic|ethnicity|hispanic|latin[oax]|veteran|disabilit|sexual orientation|transgender|lgbt)", re.I)
_ACK = re.compile(r"(acknowledg|i (have )?read|i agree|i understand|i consent|confirm (receipt|that)|privacy (policy|notice)|arbitration|"
                  r"prohibits the use of|use of (unauthori[sz]ed )?ai\b|^privacy statement|code of conduct|processing of personal data|"
                  r"review the linked|^ai policy|data (privacy|protection) (notice|policy))", re.I)


def _yn(v):
    return v if v in ("yes", "no") else None


def _grad_text(ext):
    g = ext.get("grad") or ""
    m = re.match(r"^(\d{4})-(\d{2})$", g)
    return ("%s %s" % (_MONTHS[int(m.group(2)) - 1], m.group(1))) if m else None


def _first_last(name):
    first, _, last = (name or "").strip().partition(" ")
    return first, (last.strip() or first)


def _fill_template(t, job):
    if not t:
        return None
    return t.replace("{company}", job.get("co") or "the company").replace("{role}", job.get("role") or "this role")


STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
          "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
          "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
          "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
          "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
          "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
          "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico"}

_ZIP3 = None


def coords(zip_code):
    """(latitude, longitude) of the area of a US ZIP code, from the Census Bureau's public ZIP data (see autofill_zip3.json), or None."""
    global _ZIP3
    if _ZIP3 is None:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "autofill_zip3.json"), encoding="utf-8") as f:
                _ZIP3 = json.load(f)["zip3"]
        except Exception:
            _ZIP3 = {}
    z = re.sub(r"\D", "", str(zip_code or ""))[:5]
    hit = _ZIP3.get(z[:3]) if len(z) == 5 else None
    return tuple(hit) if hit else None


def _state(ext, cand):
    """The person's US state as [full name, two-letter code], from the address in Profile or the end of their city ("Philadelphia, PA")."""
    s = (ext.get("state") or "").strip()
    if not s:
        m = re.search(r",\s*([A-Za-z]{2})\b\s*$", cand.get("loc") or "")
        s = m.group(1) if m else ""
    code = s.upper() if s.upper() in STATES else next((k for k, v in STATES.items() if v.lower() == s.lower()), "")
    return [STATES[code], code] if code else None


# the countries Profile setup offers, as Greenhouse's two-letter code and the names a form's country list may use
COUNTRIES = {"US": ["United States", "United States of America", "USA", "US", "U.S."], "CA": ["Canada"],
             "GB": ["United Kingdom", "UK", "Great Britain", "England"]}


def _country(ext):
    """The person's country as a two-letter code ('US', 'CA', 'GB'), or '' for another country or none given. A profile saved before the
    country question existed counts as the United States when it has a US state or ZIP code (both are US-only in Profile setup)."""
    c = (ext.get("country") or "").strip().upper()
    if c in COUNTRIES:
        return c
    return "US" if not c and (ext.get("zip") or (ext.get("state") or "").strip()) else ""


def _city(cand):
    """The city part of the person's City in Profile ("Philadelphia, PA" gives "Philadelphia")."""
    return (cand.get("loc") or "").split(",")[0].strip()


def _place(cand, ext):
    """The location as Greenhouse's own location box writes it: "Philadelphia, Pennsylvania, United States"."""
    state, c = _state(ext, cand), _country(ext)
    parts = [_city(cand), state[0] if state and c == "US" else "", COUNTRIES[c][0] if c else ""]
    parts = [p for p in parts if p]
    return ", ".join(parts) if (_city(cand) or state) else ", ".join(p for p in [ext.get("zip") or ""] + parts if p)


def _month(v):
    """(month, year) from a "2024-06" value, or None."""
    m = re.match(r"^(\d{4})-(0[1-9]|1[0-2])$", v or "")
    return (int(m.group(2)), int(m.group(1))) if m else None


def _month_text(v):
    m = _month(v)
    return "%s %d" % (_MONTHS[m[0] - 1], m[1]) if m else None


def _job_dates(ext):
    """"June 2024 to present" or "June 2023 to May 2024" for the most recent job, or None without a start month."""
    s = _month_text(ext.get("job_start"))
    return ("%s to %s" % (s, _month_text(ext.get("job_end")) or "present")) if s else None


def _job_text(ext):
    """The most recent job in one line ("Software Engineer at Acme, June 2024 to present"), from whatever the profile has."""
    head = " at ".join(x for x in (ext.get("job_title"), ext.get("employer")) if x)
    return ", ".join(x for x in (head, _job_dates(ext)) if x) or None


def _employed(ext):
    """Yes when the most recent job has a start month and no end month, No when it ended, otherwise only the person knows."""
    if not (ext.get("employer") and _month(ext.get("job_start"))):
        return None
    return "no" if _month(ext.get("job_end")) else "yes"


def _salary(ext):
    """Expected yearly pay as plain digits ("85000"), or None when the person left it blank (then a form that requires it asks them)."""
    try:
        n = int(float(ext.get("salary")))
    except (TypeError, ValueError):
        return None
    return str(n) if n > 0 else None


# a question that really asks for an amount (a yes/no question that only mentions pay, or a pay notice, is not one)
_SALARY = (r"(salary|compensation|pay) (expectation|requirement)|(expected|desired|target) (annual |yearly |base )?(salary|compensation|pay)|"
           r"(salary|compensation|pay) (are you|do you|would you) (expect|seek|look|want)|what (salary|compensation|pay)")


def _rules(cand, ext, job):
    """(pattern, resolver) pairs, most specific first. A resolver returns the wanted answer, a list of acceptable answers to try in order
    (for multiple-choice questions whose options are whole sentences), or None when only the person can answer."""
    first, last = _first_last(cand.get("name"))
    auth, spon = ext.get("auth"), ext.get("sponsor")
    state = _state(ext, cand)
    country = _country(ext)
    country_names = COUNTRIES.get(country)
    if auth in ("citizen", "authorized"):
        authorized = ["yes", "i require" if spon == "yes" else "authorized to work for any employer", "citizen" if auth == "citizen" else "authorized"]
    elif auth == "none":
        authorized = ["no", "not authorized", "i require"]
    else:
        authorized = None
    sponsor = (["no", "do not require", "not require", "will not require", "can work for any", "authorized to work for any employer", "not applicable"] if spon == "no"
               else ["yes", "i require", "will require", "require"] if spon == "yes" else None)
    opt = (["no", "not applicable", "n/a"] if auth == "citizen" else None)              # OPT questions only apply to student visa holders
    in_us = "yes" if country == "US" else "no" if (ext.get("country") or "").strip() else None
    names = [n.lower() for n in country_names] if country_names else [] if (ext.get("country") or "").strip() else ["united states", "usa", "us"]
    return [
        (r"pronounc", lambda: None),                                                      # how to pronounce a name: only the person knows
        (r"preferred (first )?name|first name|given name", lambda: first or None),
        (r"(legal|full).*name|name as it appears", lambda: cand.get("name") or None),
        (r"last name|surname|family name", lambda: last or None),
        (r"pronoun", lambda: ext.get("pronouns") or None),
        (r"linked\s*in", lambda: ext.get("linkedin") or None),
        (r"phone|mobile number|cell number", lambda: ext.get("phone") or None),
        (r"github", lambda: ext.get("portfolio") if "github.com" in (ext.get("portfolio") or "") else None),
        (r"website|portfolio|personal (site|page)|\burl\b", lambda: ext.get("portfolio") or ext.get("resume") or None),
        (r"(alternate|secondary) email", lambda: None),
        (r"\b(18|eighteen)\b.*(age|old)|of legal age|at least 18", lambda: "yes"),     # confirmed in UAply's first-application agreement
        # expected pay: early, so "your desired salary for this location" is not taken for a location question. Only an amount the person
        # entered, and only to a form that asks for one; any other question about pay is left for the person
        (_SALARY, lambda: _salary(ext)),
        (r"salary|compensation|pay expectation", lambda: None),
        (r"^(if so, )?(are|were) you (eligible|currently)[^?]*\b(opt|optional practical training)\b|\bopt extension|stem (opt )?extension", lambda: opt),
        (r"sponsor|visa (transfer|status)|h-?1b|require (work )?authori[sz]ation", lambda: sponsor),
        (r"(authori[sz]ed|eligible|legally|lawfully|right) (to )?work|work authori[sz]ation|legal authori[sz]ation", lambda: authorized),
        (r"relative.*government|government.*relative", lambda: _yn(ext.get("govt"))),
        (r"government official|public official", lambda: _yn(ext.get("govt"))),
        # "Are you currently employed?" on its own (not "employed by {company}", which is the former-employee question below)
        (r"^(are you )?(currently|presently) (employed|working)\s*\??$", lambda: _employed(ext)),
        (r"(previously|ever|currently|former|current or former).*(work|employ|intern)|(worked|employed) (for|at|by)",
         lambda: ["no", "i have not", "not previously", "never"] if ext.get("former") == "no" else None),
        (r"phd|doctoral program", lambda: _yn(ext.get("phd"))),
        (r"relocat", lambda: _yn(ext.get("relocate"))),
        (r"(work|working) (from|in|at) (the |our )?office|in[- ]office|on[- ]?site|hybrid", lambda: _yn(ext.get("office"))),
        (r"(currently )?(located|based|live|reside) in the (us|u s|united states)", lambda: in_us),
        (r"(?<!phone )\bcountry\b(?!\s*(code|calling))", lambda: country_names),
        (r"zip|postal code", lambda: ext.get("zip") or None),
        (r"\bstate\b|province|region in which you", lambda: (state + ["another state", "other state", "other us state"]) if state and country in ("US", "") else None),
        (r"(current )?location|\bcity\b|where .*(based|located|live)|address",
         lambda: ([cand["loc"]] + (state or []) + names) if cand.get("loc") else None),
        (r"\bgpa\b|grade point", lambda: str(ext["gpa"]) if ext.get("gpa") not in (None, "") else None),
        (r"graduat", lambda: _grad_text(ext)),
        (r"school|university|college|institution", lambda: ext.get("school") or None),
        (r"degree|level of education|highest education", lambda: _EDU.get(cand.get("edu") or "") or None),
        (r"major|discipline|field of study|area of study|concentration", lambda: ext.get("major") or None),
        # the dates at the most recent employer first, so "start date at your current employer" is not taken for the employer's name
        (r"dates? of employment|employment dates", lambda: _job_dates(ext)),
        (r"(employment|job|position|role) start date|start date (at|with|of|in) (your )?(current|most recent|previous|last)", lambda: _month_text(ext.get("job_start"))),
        (r"(employment|job|position|role) end date|end date (at|with|of|in) (your )?(current|most recent|previous|last)", lambda: _month_text(ext.get("job_end"))),
        (r"(current|most recent|present|previous) (employer|company)|company name", lambda: ext.get("employer") or None),
        # the title the person holds (or last held) at that employer; the title they are looking for is the next best answer
        (r"(current|most recent) (job )?title|current role|title (at|with) (your )?(current|most recent)", lambda: ext.get("job_title") or cand.get("title") or None),
        (r"(current|most recent|previous|last) (position|job|employment)\b", lambda: _job_text(ext)),
        (r"years of (relevant |professional )?experience|how many years", lambda: str(cand["years"]) if cand.get("years") else None),
        (r"start date|earliest start|when (can|could) you start|availability|notice period", lambda: _START.get(ext.get("start") or "") or None),
        (r"(how|where) did you (first )?(hear|find|learn)|where have you (heard|learned)|influenced your decision", lambda: "uaply"),
        (r"why .*(work|join|interested|apply)|what (excites|interests) you|cover letter|tell us (about )?why", lambda: _fill_template(ext.get("why"), job)),
    ]


_HEARD = ("uaply", "job board", "online job board", "job board (e.g. indeed, linkedin)", "online", "internet", "website", "other")


def _option(values, want, multi=False):
    """The option whose label matches what is wanted: exact, then whole word, then (yes/no) by first word. Returns the option's value or None."""
    opts = [(str(v.get("label", "")).strip(), v.get("value")) for v in values if isinstance(v, dict)]
    if not opts or want in (None, ""):
        return None
    wants = list(_HEARD) if want == "uaply" else [str(want)]
    for w in wants:
        wl = w.lower()
        for label, value in opts:
            if label.lower() == wl:
                return value
    for w in wants:
        for label, value in opts:
            if re.search(r"\b%s\b" % re.escape(w.lower()), label.lower()):
                return value
    if want in ("yes", "no"):
        for label, value in opts:
            if label.lower().startswith(want):
                return value
    if re.match(r"^[A-Z][a-z]+ \d{4}$", str(want)):           # a graduation date: an option naming that year (and month if it says one)
        month, year = str(want).split()
        for label, value in opts:
            if year in label and month.lower()[:3] in label.lower():
                return value
        for label, value in opts:
            if year in label:
                return value
    return None


def _label_of(values, value):
    for v in values or []:
        if isinstance(v, dict) and v.get("value") == value:
            return str(v.get("label", ""))
    return str(value)


def _answer(label, key, kind, values, answers, rules, ext, req=True):
    """One question answered from the person's saved answer to it, or else from the profile (legal notices only with "acknowledge for me").
    kind: select or multi (values are [{label, value}] and the option's value is returned), boolean, number, date, or anything else for text.
    Returns (value, what to show the person, came from a saved answer, is the person's expected pay) or None when only the person can answer.
    Expected pay is given only to a question the form requires; an optional pay box stays blank. Shared by every hiring system, so the rules
    table above is the one place that decides what a profile answers."""
    want = answers.get(key)
    saved = want not in (None, "")
    pay = False
    if not saved:
        if _ACK.search(label):
            want = "yes" if ext.get("ack") is True else None
        else:
            want = None
            for rx, fn in rules:
                if rx.search(label):
                    want, pay = fn(), rx.pattern == _SALARY
                    break
            if pay and not req:
                want = None
    if want in (None, "", []):
        return None
    tries = want if isinstance(want, list) else [want]
    if kind in ("select", "multi"):
        val = None
        for w in tries:
            val = _option(values, w)
            if val is not None:
                break
        if val is None and tries[0] == "yes" and _ACK.search(label):      # "I acknowledge", "I agree", or a single box to tick
            val = (_option(values, "acknowledge") or _option(values, "agree") or _option(values, "understand") or _option(values, "consent")
                   or (values[0].get("value") if len(values) == 1 and isinstance(values[0], dict) else None))
        return None if val is None else (val, _label_of(values, val), saved, pay)
    w = str(tries[0]).strip()
    if kind == "boolean":                       # a yes/no box: only a plain yes or no counts, never a sentence that happens to start with one
        yn = {"yes": True, "true": True, "no": False, "false": False}.get(w.lower())
        return None if yn is None else (yn, "Yes" if yn else "No", saved, pay)
    if kind == "number":
        if not re.match(r"^-?\d+(\.\d+)?$", w):
            return None
        return (float(w) if "." in w else int(w)), w, saved, pay
    if kind == "date":                          # only a whole date is sent; "June 2027" is not one, so the person is asked
        return (w, w, saved, pay) if re.match(r"^\d{4}-\d{2}-\d{2}$", w) else None
    text = ("UAply" if w == "uaply" else "Yes" if w == "yes" else "No" if w == "no" else w)[:2000]
    return text, (text if len(text) < 80 else text[:77] + "..."), saved, pay


def plan_questions(questions, cand, job, note="", resume_meta=None, answers=None, company=""):
    """Work out an application for a hiring system whose form arrives as a plain list of questions (Ashby, SmartRecruiters). Each question is
    {"id", "label", "req", "kind", "options": [{label, value}], "role", "voluntary"}:
      kind      text, textarea, select, multi, boolean, number, date, file, or "other" for a type UAply does not know how to fill
      role      for the standard fields: name, first, last, email, phone, resume, cover (the person's message). Others use the rules.
      voluntary true for self-identification (gender, race, veteran, disability): never answered, whatever the label says
    Returns {"values": [(id, value)], "resume": [ids that take the resume file], "items", "missing", "filled", "total", "required"},
    with items and missing in the same shape plan_greenhouse gives, so the app asks a missing question the same way for every system."""
    ext = cand.get("ext") or {}
    answers = answers if isinstance(answers, dict) else {}
    rules = [(re.compile(p, re.I), f) for p, f in _rules(cand, ext, job)]
    first, last = _first_last(cand.get("name"))
    values, resume, items, missing = [], [], [], []
    salary_sent = False
    for q in questions:
        label = re.sub(r"\s+", " ", str(q.get("label") or "")).strip()
        req, kind, role, opts = bool(q.get("req")), q.get("kind") or "text", q.get("role") or "", q.get("options") or []
        key = norm(label, company)
        if q.get("voluntary") or _EEO.search(label):          # voluntary self-identification: never answered
            items.append({"q": label, "key": key, "req": req, "a": "", "need": False, "skip": "voluntary"})
            continue
        val = shown = None
        if role == "name":
            val = cand.get("name") or None
        elif role == "first":
            val = first or None
        elif role == "last":
            val = last or None
        elif role == "email":
            val = cand.get("email") or None
        elif role == "phone":
            val = ext.get("phone") or answers.get(key) or None    # the profile's number, or the one the person typed when this was asked
        elif role == "resume":
            if resume_meta:
                resume.append(q["id"])
                shown = resume_meta["name"]
        elif role == "cover":
            val = note or _fill_template(ext.get("why"), job) or ext.get("summary") or None
            if val:
                shown = "Your message to the hiring manager" if note else "Your 'why you want to work there' text" if ext.get("why") else "Your About you text"
        elif kind not in ("file", "other"):                   # a file other than the resume, or a type UAply cannot fill, is left to the person
            got = _answer(label, key, kind, opts, answers, rules, ext, req)
            if got is not None:
                val, shown, saved, pay = got
                if kind == "multi":
                    val = [val]
                if saved:
                    shown = shown + "  (your saved answer)"
                elif pay:
                    salary_sent = True                      # the receipt lists expected pay only for an employer whose form asked for it
        if val not in (None, "", []):
            values.append((q["id"], val))
            if shown is None:
                shown = str(val) if len(str(val)) < 80 else str(val)[:77] + "..."
        ok = shown is not None
        need = req and not ok
        # how the app asks it: "file" tells the person to upload a resume; "other" cannot be asked in the app at all (a file other than the
        # resume, or a type UAply cannot fill), so the person finishes on the employer's page
        sheet = ("file" if role == "resume" else "other" if kind in ("file", "other") else kind if kind in ("text", "textarea", "select", "multi")
                 else "select" if kind == "boolean" else "text")
        item = {"q": label, "key": key, "req": req, "a": shown if ok else "", "need": need, "kind": sheet}
        if need:
            if sheet in ("select", "multi"):
                item["opts"] = ["Yes", "No"] if kind == "boolean" else [str(o.get("label", "")) for o in opts[:60] if isinstance(o, dict)]
            missing.append(item)
        items.append(item)
    total = sum(1 for i in items if not i.get("skip"))
    return {"values": values, "resume": resume, "items": items, "missing": missing, "total": total, "salary_sent": salary_sent,
            "filled": sum(1 for i in items if not i.get("skip") and i["a"]), "required": sum(1 for i in items if i["req"] and not i.get("skip"))}


def plan_greenhouse(form, cand, job, note="", resume_meta=None, resume_bytes=None, answers=None):
    """Work out the whole application for one Greenhouse form. See the module notes for the result's shape."""
    ext = cand.get("ext") or {}
    answers = answers if isinstance(answers, dict) else {}
    company = (form.get("company_name") or job.get("co") or "").strip()
    rules = [(re.compile(p, re.I), f) for p, f in _rules(cand, ext, job)]
    first, last = _first_last(cand.get("name"))
    fields, files, items, missing = [], [], [], []
    done = set()
    salary_sent = False
    # the map position Greenhouse keeps with a location, from the person's US ZIP code (or the one they typed when it was asked)
    zip_code = ext.get("zip") or answers.get("zip") or ""
    geo = coords(zip_code) if _country(dict(ext, zip=zip_code)) == "US" else None
    place = _place(cand, dict(ext, zip=zip_code)) if geo else ""

    def put(name, value):
        if value in (None, "") or name in done:
            return False
        fields.append((name, str(value)))
        done.add(name)
        return True

    for q in list(form.get("questions") or []) + list(form.get("location_questions") or []):
        label = re.sub(r"\s+", " ", str(q.get("label") or "")).strip()
        req = bool(q.get("required"))
        key = norm(label, company)
        fl = [f for f in (q.get("fields") or []) if isinstance(f, dict) and f.get("name")]
        if not fl:
            continue
        shown, ok, kind = "", False, "text"
        if _EEO.search(label):                                # voluntary self-identification: never answered
            items.append({"q": label, "key": key, "req": req, "a": "", "need": False, "skip": "voluntary"})
            continue
        for f in fl:
            name, ftype, values = f["name"], f.get("type") or "", f.get("values") or []
            kind = "file" if ftype == "input_file" else "textarea" if ftype == "textarea" else "multi" if ftype == "multi_value_multi_select" else "select" if ftype.startswith("multi_value") else "text"
            if name in done:
                ok = True
                continue
            if name == "first_name":
                ok = put(name, first) or ok; shown = first
            elif name == "last_name":
                ok = put(name, last) or ok; shown = last
            elif name == "email":
                ok = put(name, cand.get("email")) or ok; shown = cand.get("email") or ""
            elif name == "phone":
                ph = ext.get("phone") or answers.get(key)          # the profile's number, or the one the person typed when this was asked
                ok = put(name, ph) or ok; shown = ph or ""
            elif name == "resume" and ftype == "input_file":
                if resume_bytes and resume_meta:
                    files.append(("resume", resume_meta["name"], resume_meta["type"], resume_bytes))
                    done.add(name); ok = True; shown = resume_meta["name"]
            elif name == "cover_letter" and ftype == "input_file":
                ok = ok or not req
            elif name == "resume_text":
                if not resume_bytes:
                    t = ext.get("summary") or ext.get("headline")
                    if put(name, t):
                        ok = True; shown = "Your About you text"
                else:
                    ok = True
            elif name == "cover_letter_text":
                t = note or _fill_template(ext.get("why"), job) or ext.get("summary")
                if put(name, t):
                    ok = True; shown = "Your message to the hiring manager" if note else "Your 'why you want to work there' text" if ext.get("why") else "Your About you text"
                else:
                    ok = ok or not req
            elif ftype == "input_hidden":
                if name in ("latitude", "longitude"):              # set by the location box on the employer's page: worked out from the ZIP code
                    if geo and put(name, geo[0] if name == "latitude" else geo[1]):
                        ok = True; shown = "From your ZIP code"
                else:
                    ok = ok or not req
            elif name == "location":                               # Greenhouse keeps a location only with its map position, so both come from the ZIP code
                if geo and put(name, place):
                    ok = True; shown = place
            else:
                got = _answer(label, key, kind, values, answers, rules, ext, req)
                if got is None:
                    continue
                val, said, saved, pay = got
                if put(name + ("[]" if kind == "multi" and not name.endswith("[]") else ""), val):
                    ok = True; shown = said
                if ok and saved:
                    shown = shown + "  (your saved answer)"
                if ok and pay and not saved:
                    salary_sent = True                      # the receipt lists expected pay only for an employer whose form asked for it
        need = req and not ok
        f0 = fl[0]
        kind = {"input_file": "file", "textarea": "textarea", "multi_value_multi_select": "multi", "multi_value_single_select": "select"}.get(f0.get("type"), "text")
        hidden = f0.get("type") == "input_hidden"
        if hidden or (f0.get("name") == "location" and need):  # never asked as such: if the ZIP code is missing, that is what is asked
            if need and not any(m["key"] == "zip" for m in missing):
                missing.append({"q": "Your ZIP code (the employer's form uses it for your location)", "key": "zip", "req": True, "a": "", "need": True, "kind": "text"})
            items.append({"q": label, "key": key, "req": req, "a": shown, "need": False, "skip": "hidden"} if hidden else
                         {"q": label, "key": key, "req": req, "a": "", "need": True, "kind": kind})
            continue
        item = {"q": label, "key": key, "req": req, "a": shown if ok else "", "need": need, "kind": kind}
        if need:
            if kind in ("select", "multi"):
                item["opts"] = [str(v.get("label", "")) for v in (f0.get("values") or [])[:60] if isinstance(v, dict)]
            missing.append(item)
        items.append(item)
    # what Greenhouse's own careers page sends without asking: the country, the location with its map position (all three or none,
    # since Greenhouse ignores a location without coordinates) and the most recent job
    put("country_short_name", _country(ext))
    if geo:
        put("location", place)
        put("latitude", geo[0])
        put("longitude", geo[1])
    start = _month(ext.get("job_start"))
    if ext.get("employer") and ext.get("job_title") and start:
        end = _month(ext.get("job_end"))
        put("employments[0][company_name]", ext["employer"])
        put("employments[0][title]", ext["job_title"])
        put("employments[0][start_date][month]", start[0])
        put("employments[0][start_date][year]", start[1])
        if end:
            put("employments[0][end_date][month]", end[0])
            put("employments[0][end_date][year]", end[1])
        else:
            put("employments[0][current]", "true")
    total = sum(1 for i in items if not i.get("skip"))
    filled = sum(1 for i in items if not i.get("skip") and i["a"])
    return {"fields": fields, "files": files, "items": items, "missing": missing, "filled": filled, "total": total,
            "required": sum(1 for i in items if i["req"] and not i.get("skip")), "company": company, "salary_sent": salary_sent}


def public_plan(plan):
    """What the browser may see: the questions and answers, never the raw field names or files."""
    return {"filled": plan["filled"], "total": plan["total"], "required": plan["required"],
            "items": [{k: i[k] for k in ("q", "key", "req", "a", "need", "kind", "opts", "skip") if k in i} for i in plan["items"]],
            "missing": [{k: i[k] for k in ("q", "key", "req", "kind", "opts") if k in i} for i in plan["missing"]]}


def clean_answers(raw):
    """Saved answers sent by the browser: at most 80, short keys and values, plain text only."""
    out = {}
    if isinstance(raw, dict):
        for k, v in list(raw.items())[:80]:
            if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                out[norm(k)] = re.sub(r"[\r\t]+", " ", v).strip()[:2000]
    return out
