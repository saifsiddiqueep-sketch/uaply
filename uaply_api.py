"""Application delivery back end for the sandbox and dev instances (prod does not use it).

Swipe right  -> POST /api/apply    builds an application and delivers it.
Swipe left   -> POST /api/decision just records that the job was passed on. Nothing is sent to anyone.

Delivery modes (uaply-config.json, key "delivery"):
  "test"  (default) the application is written to a simulated recruiter inbox on this computer (/outbox).
                    Nothing leaves the machine, so the flow can be tested with any profile.
  "live"            if the posting lists a recruiting email AND SMTP is configured, the application is emailed to that
                    recruiter from your mail account, with Reply-To set to the candidate. The request must carry
                    confirm_real=true (the user pressed Send after reviewing it). If there is no recruiter email, the
                    result is "handoff": the employer accepts applications only on its own page, and the app opens it.
                    Direct ATS submission (Greenhouse, Lever, Ashby, SmartRecruiters) needs an API key issued by each
                    employer, so it happens only for employers who connected (ats_api.py).

Safeguards: explicit consent flag, candidate name and email required, https posting URLs only, one application per
candidate per job, a daily cap on live sends, size limits, and the server rejects cross-site requests.

Receipts: when the person swiping is signed in (auth_api.py), every new application also produces a receipt addressed
to their account email. In test mode it is stored in the simulated inbox (shown on /outbox); in live mode with SMTP
configured it is emailed to them for real.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import smtplib
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import html
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
CONFIG_PATH = os.path.join(ROOT, "uaply-config.json")
REAL_CONFIG_PATH = CONFIG_PATH                             # the owner's own settings file (tests may point CONFIG_PATH at a temporary one)
import ats_api
import autofill
import jobs_api
import auth_api
import emails

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")   # strict: one plain address, no lists or names

_lock = threading.RLock()
APPS = []
DECISIONS = []


def data_root():
    """Where records live: UAPLY_DATA_DIR on a host (a persistent disk), else ./data next to the code."""
    return os.environ.get("UAPLY_DATA_DIR") or os.path.join(ROOT, "data")


def config():
    """uaply-config.json, then UAPLY_CONFIG_JSON from the environment on top (how a host passes settings and secrets
    without a file in the repository), then SUPPORT_EMAIL if set."""
    cfg = {"delivery": "test", "daily_limit": 20, "smtp": {}}
    try:
        if not (os.environ.get("UAPLY_CONFIG_FILE") == "none" and CONFIG_PATH == REAL_CONFIG_PATH):   # the test run never uses the owner's real email or keys
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
    except Exception:
        pass
    try:
        env = json.loads(os.environ.get("UAPLY_CONFIG_JSON") or "{}")
        if isinstance(env, dict):
            cfg.update(env)
    except ValueError:
        print("UAPLY_CONFIG_JSON is not valid JSON; ignoring it", file=sys.stderr)
    if os.environ.get("SUPPORT_EMAIL"):
        cfg["support_email"] = os.environ["SUPPORT_EMAIL"]
    if cfg.get("delivery") not in ("test", "live"):
        cfg["delivery"] = "test"
    return cfg


def _smtp_ready(cfg):
    s = cfg.get("smtp") or {}
    pw = s.get("password") if isinstance(s.get("password"), str) else ""
    if s.get("user") and (not pw.strip() or pw.strip().lower().startswith("a gmail app password")):
        return False                                    # a login with no real password yet (the example text counts as none)
    return bool(s.get("host") and s.get("from_addr"))


def _redirect(cfg):
    """If set, every live application goes to this address instead of the recruiter (for safe end-to-end tests)."""
    r = cfg.get("test_recipient")
    return r.strip() if isinstance(r, str) and EMAIL_RE.match(r.strip()) else ""


def public_config():
    cfg = config()
    try:
        grace = max(0, min(30, int(cfg.get("grace_seconds", 5))))
    except (TypeError, ValueError):
        grace = 5
    return {"mode": cfg["delivery"], "canEmail": _smtp_ready(cfg), "redirect": _redirect(cfg), "ownerCopy": bool(_owner_copy(cfg)),
            "autoSend": cfg.get("auto_send", True) is not False, "graceSeconds": grace}


def append_line(path, text):
    """Add one record (one line) to a records file. If the last write was cut short (a full disk, a forced stop), the file does not end in a
    line break: one is added first, so the new record never gets glued to the broken one. Never raises; a failure is written to the server's log."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a+b") as f:
            if f.tell():
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    f.write(b"\n")
            f.write(text.encode("utf-8") + b"\n")
    except Exception as e:
        sys.stderr.write("[uaply] could not save a record to %s: %s: %s\n" % (path, type(e).__name__, str(e)[:200]))      # kept in memory only


def read_lines(path):
    """Every readable record of a records file. A broken line (a write that was cut short) is skipped instead of hiding every record after it."""
    out, bad = [], 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip():
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        bad += 1
                        continue
                    if isinstance(rec, dict):
                        out.append(rec)
    except OSError:
        pass
    if bad:
        sys.stderr.write("[uaply] skipped %d broken line(s) in %s\n" % (bad, path))
    return out


def _append(name, obj):
    append_line(os.path.join(DATA, name), json.dumps(obj))        # keep working from memory if the disk is not writable


def _load():
    for name, store in (("applications.jsonl", APPS), ("decisions.jsonl", DECISIONS)):
        store.extend(read_lines(os.path.join(DATA, name)))


hide_errors = False        # serve.py sets this on a hosted server: visitors then see a plain sentence, never a mail server's or an employer's raw error text


INSTANCE = ""


def init(instance):
    """Each instance (sandbox, dev) keeps its own records in data/<instance>/."""
    global DATA, INSTANCE
    INSTANCE = re.sub(r"[^A-Za-z0-9_-]", "", instance) or "default"
    DATA = os.path.join(data_root(), INSTANCE)
    APPS.clear()
    DECISIONS.clear()
    _load()


def _s(v, n):
    """A single-line, trimmed string (line breaks removed so nothing can inject extra mail headers)."""
    return re.sub(r"[\r\n\t]+", " ", v).strip()[:n] if isinstance(v, str) else ""


_AUTH = {"citizen": "US citizen or permanent resident", "authorized": "Authorized to work (visa, OPT or similar)",
         "none": "Not currently authorized"}
_START = {"now": "Right away", "2w": "Within 2 weeks", "1m": "Within a month", "grad": "After graduation", "flex": "Flexible"}
_TYPES = {"fulltime": "Full-time", "parttime": "Part-time", "internship": "Internship", "coop": "Co-op"}
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


_COUNTRIES = {"US": "United States", "CA": "Canada", "GB": "United Kingdom", "other": "Outside the United States, Canada and the United Kingdom"}


def _pick(v, allowed):
    return v if isinstance(v, str) and v in allowed else ""


def _month_value(v):
    """A "2024-06" month from Profile setup, or ""."""
    v = _s(v, 7)
    return v if re.match(r"^\d{4}-(0[1-9]|1[0-2])$", v) else ""


def _month_words(v):
    """"2024-06" as "June 2024"."""
    return "%s %s" % (_MONTHS[int(v[5:7]) - 1], v[:4]) if _month_value(v) else ""


def _https(v, n=300):
    v = _s(v, n)
    return v if v.lower().startswith("https://") and " " not in v else ""


def _linkedin(v):
    """A LinkedIn profile link: https, and really on linkedin.com (so the LinkedIn field cannot carry some other site)."""
    u = _https(v)
    host = u.split("/")[2].split(":")[0].lower() if u else ""
    return u if host == "linkedin.com" or host.endswith(".linkedin.com") else ""


def _ext(raw):
    """The optional application-profile details (phone, links, education, authorization...), each checked and capped."""
    x = raw if isinstance(raw, dict) else {}
    phone = _s(x.get("phone"), 25)
    phone = phone if re.match(r"^[+()\d\s.-]{7,25}$", phone) else ""
    grad = _s(x.get("grad"), 7)
    grad = grad if re.match(r"^\d{4}-(0[1-9]|1[0-2])$", grad) else ""
    try:
        gpa = float(x.get("gpa"))
        gpa = round(gpa, 2) if 0 <= gpa <= 4.5 else ""
    except (TypeError, ValueError):
        gpa = ""
    types = [t for t in x.get("types") if t in _TYPES] if isinstance(x.get("types"), list) else []
    zipc = _s(x.get("zip"), 10)
    state = _s(x.get("state"), 30)
    job_start, job_end = (_month_value(x.get(k)) for k in ("job_start", "job_end"))
    if job_end and (not job_start or job_end < job_start):
        job_start = job_end = ""                   # dates that cannot be right are left out, so a job is never reported as current by mistake
    try:
        salary = int(float(x.get("salary")))
        salary = salary if 0 < salary <= 10000000 else ""
    except (TypeError, ValueError, OverflowError):
        salary = ""
    return {"phone": phone, "headline": _s(x.get("headline"), 120), "summary": _s(x.get("summary"), 600),
            "resume": _https(x.get("resume")), "linkedin": _linkedin(x.get("linkedin")), "portfolio": _https(x.get("portfolio")),
            "school": _s(x.get("school"), 100), "major": _s(x.get("major"), 100), "grad": grad, "gpa": gpa,
            "employer": _s(x.get("employer"), 100), "job_title": _s(x.get("job_title"), 100), "job_start": job_start, "job_end": job_end,
            "auth": _pick(x.get("auth"), _AUTH),
            "sponsor": _pick(x.get("sponsor"), ("yes", "no")), "start": _pick(x.get("start"), _START), "types": types,
            # the common questions employers' own forms ask (used by autofill.py to fill those forms; none of them is shown to a recruiter otherwise)
            "zip": zipc if re.match(r"^\d{5}(-\d{4})?$", zipc) else "", "state": state if re.match(r"^[A-Za-z .]{2,30}$", state) else "",
            "country": _pick(x.get("country"), _COUNTRIES), "salary": salary,     # expected yearly pay: kept only when a form asked for it (see submit)
            "relocate": _pick(x.get("relocate"), ("yes", "no")), "office": _pick(x.get("office"), ("yes", "no")),
            "former": _pick(x.get("former"), ("no", "ask")), "govt": _pick(x.get("govt"), ("yes", "no")), "phd": _pick(x.get("phd"), ("yes", "no")),
            "pronouns": _s(x.get("pronouns"), 30), "ack": x.get("ack") is True, "why": _s(x.get("why"), 600)}


def _detail_rows(c, note=""):
    """Candidate details as (label, value) pairs. Empty values, and any value already said in the note, are left out."""
    x = c.get("ext") or {}
    skills = ", ".join(c.get("skills") or [])
    exp = ("%s year%s" % (c["years"], "" if c.get("years") == 1 else "s")) if c.get("years") else ""
    grad = re.match(r"^(\d{4})-(\d{2})$", x.get("grad") or "")
    grad = "graduation %s %s" % (_MONTHS[int(grad.group(2)) - 1], grad.group(1)) if grad else ""      # "graduation June 2027", not "2027-06"
    edu = ", ".join(v for v in (x.get("school"), x.get("major"), grad, ("GPA %s" % x["gpa"]) if x.get("gpa") != "" and x.get("gpa") is not None else "") if v)
    start, end = _month_words(x.get("job_start")), _month_words(x.get("job_end"))
    dates = ("%s to %s" % (start, end or "present")) if start else ""
    rows = [("Applicant", c.get("name")), ("Email", c.get("email")), ("Current or target title", c.get("title")),
            ("Experience", exp), ("Location", c.get("loc")), ("Country", _COUNTRIES.get(x.get("country"), "")), ("Skills", skills),
            ("Phone", x.get("phone")), ("Headline", x.get("headline")), ("Resume", x.get("resume")),
            ("Resume file", ("%s (attached)" % c["resume_file"]) if c.get("resume_file") else ""),
            ("LinkedIn", x.get("linkedin")), ("Portfolio", x.get("portfolio")), ("Education", edu),
            ("Most recent employer", x.get("employer")), ("Job title there", x.get("job_title")), ("Dates there", dates),
            ("Work authorization", _AUTH.get(x.get("auth"), "") + ("; needs sponsorship" if x.get("sponsor") == "yes" else "; no sponsorship needed" if x.get("sponsor") == "no" else "") if x.get("auth") else ""),
            ("Earliest start", _START.get(x.get("start"), "")),
            ("Willing to relocate", {"yes": "Yes", "no": "No"}.get(x.get("relocate"), "")),
            # expected pay is in the record only when the employer's own form asked for it (submit() leaves it out otherwise)
            ("Expected yearly pay", ("$%s" % format(x["salary"], ",")) if isinstance(x.get("salary"), int) and x["salary"] > 0 else ""),
            ("Looking for", ", ".join(_TYPES[t] for t in x.get("types", [])))]
    return [(k, str(v)) for k, v in rows if v and str(v) not in note]


def _detail_text(c, note=""):
    """Candidate details as plain lines for the recruiter email and the test inbox (empty if none were given)."""
    lines = ["%s: %s" % kv for kv in _detail_rows(c, note)]
    return ("\n\nApplication details\n" + "\n".join(lines)) if lines else ""


def _application_text(c, job, note=""):
    """The application as the recruiter reads it: the applicant's details. A cover note is included only if one was written."""
    body = note.strip() or "%s applied for the %s position at %s through UAply." % (c["name"], job["role"], job["co"])
    return body + _detail_text(c, note)


def _validate(p):
    if p.get("consent") is not True:
        return "Consent is required to send an application."
    job, prof = p.get("job"), p.get("profile")
    if not isinstance(job, dict) or not isinstance(prof, dict):
        return "Missing job or profile."
    try:
        int(job.get("id"))
    except (TypeError, ValueError):
        return "Invalid job."
    if not _s(job.get("url"), 600).startswith("https://"):
        return "The posting link must be https."
    if not _s(job.get("co"), 200) or not _s(job.get("role"), 200):
        return "Missing company or role."
    if not _s(prof.get("name"), 100):
        return "Add your name in Profile setup, under About you, first."
    if not EMAIL_RE.match(_s(prof.get("email"), 200)):
        return "Add a valid email in Profile setup, under About you, so the recruiter can reply."
    note = p.get("note", "")                       # optional: the application is the profile, not a message
    if note is not None and (not isinstance(note, str) or len(note) > 4000):
        return "The note must be at most 4000 characters."
    return None


def _simulated_recipient(co):
    return "recruiting@%s.example" % (re.sub(r"[^a-z0-9]", "", co.lower()) or "company")


_RESUME_KINDS = {"pdf": (b"%PDF", "application", "pdf"), "doc": (b"\xd0\xcf\x11\xe0", "application", "msword"),
                 "docx": (b"PK\x03\x04", "application", "vnd.openxmlformats-officedocument.wordprocessingml.document"),
                 "txt": (None, "text", "plain"), "md": (None, "text", "plain")}


def _resume(raw):
    """The resume file the person uploaded in Profile setup, under Background and links, as (details, bytes). Returns (None, None) when there is
    none and raises ValueError when it is not a real PDF, Word or text file under 1 MB (checked by content, not just the name)."""
    if not raw:
        return None, None
    if not isinstance(raw, dict):
        raise ValueError("bad resume")
    # letters of any language stay ("José García CV.pdf" reaches the employer as it is); slashes, quotes and other symbols become _
    name = re.sub(r"[^\w. -]", "_", _s(raw.get("name"), 120)).strip() or "resume.pdf"
    m = re.match(r"^data:[\w/+.-]+;base64,([A-Za-z0-9+/=]+)$", raw.get("data") if isinstance(raw.get("data"), str) else "")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if not m or ext not in _RESUME_KINDS:
        raise ValueError("bad resume")
    data = base64.b64decode(m.group(1), validate=True)
    magic, maintype, subtype = _RESUME_KINDS[ext]
    if not 20 <= len(data) <= 1048576 or (magic and not data.startswith(magic)):
        raise ValueError("bad resume")
    if not magic:
        data.decode("utf-8")                                   # a text resume must really be text
    return {"name": name, "size": len(data), "type": "%s/%s" % (maintype, subtype)}, data


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None                                            # a webhook that redirects is a failure, never followed


def _webhook_payload(rec, resume_bytes):
    c, j = rec["candidate"], rec["job"]
    x = c.get("ext") or {}
    out = _webhook_body(rec, resume_bytes, c, j, x)
    if isinstance(x.get("salary"), int) and x["salary"] > 0:      # only when this employer's own application form asked for it
        out["applicant"]["expected_yearly_pay_usd"] = x["salary"]
    return out


def _webhook_body(rec, resume_bytes, c, j, x):
    return {"id": rec["id"], "event": "application.created", "source": "UAply", "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(rec["at"])),
            "job": {"id": j["id"], "title": j["role"], "company": j["co"], "location": j["loc"], "url": j["url"], "type": j.get("type"), "work_style": j.get("mode")},
            "applicant": {"name": c["name"], "email": c["email"], "phone": x.get("phone", ""), "title": c.get("title", ""), "location": c.get("loc", ""),
                          "years_experience": c.get("years", 0), "skills": c.get("skills", []), "headline": x.get("headline", ""), "summary": x.get("summary", ""),
                          "education": {"level": c.get("edu", ""), "school": x.get("school", ""), "major": x.get("major", ""), "graduation": x.get("grad", ""), "gpa": x.get("gpa", "")},
                          "links": {"resume": x.get("resume", ""), "linkedin": x.get("linkedin", ""), "portfolio": x.get("portfolio", "")},
                          "work_authorization": x.get("auth", ""), "needs_sponsorship": x.get("sponsor", ""), "earliest_start": x.get("start", ""),
                          "country": x.get("country", ""), "willing_to_relocate": x.get("relocate", ""),
                          "most_recent_employer": x.get("employer", ""),
                          "most_recent_job": {"employer": x.get("employer", ""), "title": x.get("job_title", ""), "start": x.get("job_start", ""),
                                              "end": x.get("job_end", ""), "current": bool(x.get("job_start")) and not x.get("job_end")}},
            "message": rec.get("note", ""), "match_percent": rec.get("match", 0),
            "resume": ({"name": rec["resume"]["name"], "type": rec["resume"]["type"], "size": rec["resume"]["size"],
                        "content_base64": base64.b64encode(resume_bytes).decode("ascii")} if resume_bytes and rec.get("resume") else None)}


def _post_webhook(url, secret, payload):
    """POST one application as signed JSON to the address an employer registered (the way Indeed Apply delivers). The employer's
    system must answer 2xx; a failure is retried up to three times. Returns (ok, reason)."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    headers = {"Content-Type": "application/json", "User-Agent": "UAply/1.0", "X-UAply-Delivery": payload["id"], "X-UAply-Timestamp": ts}
    if secret:                                                 # the signature covers the timestamp and the body, so a replay can be spotted
        headers["X-UAply-Signature"] = "sha256=" + hmac.new(secret.encode(), (ts + ".").encode() + body, hashlib.sha256).hexdigest()
    opener = urllib.request.build_opener(_NoRedirect)
    reason = "no attempt"
    for wait in (0, 1, 3):
        if wait:
            time.sleep(wait)
        try:
            with opener.open(urllib.request.Request(url, data=body, headers=headers, method="POST"), timeout=10) as r:
                if 200 <= r.status < 300:
                    return True, ""
                reason = "HTTP %d" % r.status
        except urllib.error.HTTPError as e:
            reason = "HTTP %d" % e.code
            if 400 <= e.code < 500 and e.code not in (408, 429):
                break                                          # the employer's system said no; trying again will not change that
        except Exception as e:
            reason = type(e).__name__
    return False, reason


def _from(cfg):
    """The sender of every UAply email. A bare address (what /setup saves) gets the name "UAply", so inboxes show UAply as the sender
    instead of the part before the @; an address that already carries a name is used as it is."""
    v = (cfg.get("smtp") or {}).get("from_addr") or ""
    name, addr = parseaddr(v)
    return v if name or not addr else formataddr(("UAply", addr))


def _send_email(cfg, to, cand, job, note, original="", resume=None):
    s = cfg["smtp"]
    msg = EmailMessage()
    msg["From"] = _from(cfg)
    msg["To"] = to
    # the name is quoted, so a name such as "Sam <someone@else.example>" can never become the address the employer's Reply goes to
    msg["Reply-To"] = formataddr((cand["name"], cand["email"]))
    test = _redirect(cfg) == to
    msg["Subject"] = "%sApplication: %s - %s" % ("[TEST] " if test else "", job["role"], cand["name"])
    extra = ("\nTest redirect: this would have gone to %s.\n" % (original or "the company's application page")) if test else ""
    msg.set_content("%s\n\n--\nSent through UAply on behalf of %s <%s>.\nPosting: %s\n%s" % (_application_text(cand, job, note), cand["name"], cand["email"], job["url"], extra))
    if resume:                                                 # the resume the person uploaded goes along as a real attachment
        meta, data = resume
        maintype, subtype = meta["type"].split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=meta["name"])
    with smtplib.SMTP(s["host"], int(s.get("port", 587)), timeout=20) as srv:
        if s.get("starttls", True):
            srv.starttls()
        if s.get("user"):
            srv.login(s["user"], s.get("password", ""))
        srv.send_message(msg)


def _deliver(cfg, target, cand, job, note, contact, resume_meta, resume_bytes, hook, rec, ats=None):
    """Send one application over every channel the employer opted into: email, a signed webhook, or both. The application counts as
    sent when at least one channel accepted it. Returns (status, error_text_or_None, channels_that_worked)."""
    done, errors = [], []
    if target:
        try:
            _send_email(cfg, target, cand, job, note, contact, (resume_meta, resume_bytes) if resume_meta else None)
            done.append("email")
        except Exception as e:
            errors.append("email: %s" % str(e)[:120])
    if hook:
        ok, why = _post_webhook(hook[0], hook[1], _webhook_payload(rec, resume_bytes))
        if ok:
            done.append("webhook")
        else:
            errors.append("webhook: %s" % why)
    manual = ""
    if ats:                                    # straight into the employer's own hiring system, with the key they gave us
        st, why = ats_api.submit(ats["kind"], ats["board"], ats["id"], ats["key"], cand, note, resume_meta, resume_bytes)
        if st == "sent":
            done.append("hiring system (%s)" % ats["kind"])
        elif st == "needs_manual":
            manual = why
        else:
            errors.append("%s: %s" % (ats["kind"], why))
    if not done and manual and not errors:     # nothing was sent because the posting asks something the profile cannot answer: finish on the employer's page
        sys.stderr.write("[uaply] application %s needs a manual finish: %s\n" % (rec["id"], manual))
        return "handoff", None, []
    return ("sent" if done else "failed"), ("; ".join(errors) if errors else None), done


def _owner_copy(cfg):
    """The owner's own address, if set in the config under 'owner_copy'. Every application is also emailed there."""
    r = cfg.get("owner_copy")
    return r.strip() if isinstance(r, str) and EMAIL_RE.match(r.strip()) else ""


def _site_base(cfg, site=""):
    """The public address of this site for links in emails ('' when it only runs on this computer). The configured public_url wins;
    otherwise the address the person is using (serve.py passes it), so a host such as Render gets its link without extra settings.
    Only an https address is ever put in an email."""
    g = cfg.get("google") if isinstance(cfg.get("google"), dict) else {}
    for v in (cfg.get("public_url"), g.get("public_url"), site):
        if isinstance(v, str) and v.startswith("https://") and " " not in v:
            return v.rstrip("/")
    return ""


def _mail_ctx(cfg, rec, note, user_email="", site=""):
    """Everything emails.py needs to write the receipt or the owner copy of one application."""
    return {"test": rec["mode"] != "live", "status": rec["status"], "cand": rec["candidate"], "job": rec["job"], "at": rec["at"],
            "match": rec.get("match", 0), "to": rec.get("to", ""), "rows": _detail_rows(rec["candidate"], note), "note": note,
            "channels": rec.get("channels") or [], "user_email": user_email, "base_url": _site_base(cfg, site), "support_email": _s(cfg.get("support_email"), 120),
            "preview": rec.get("preview") is True}


def _copy_message(cfg, rec):
    """The owner's copy of one application, as plain text plus an HTML version (built apart from sending so it can be tested)."""
    subject, text, page = emails.owner_copy(_mail_ctx(cfg, rec, rec.get("note", "")))
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = _from(cfg), _owner_copy(cfg), subject
    msg.set_content(text)
    msg.add_alternative(page, subtype="html")
    return msg


def _send_owner_copy(cfg, rec):
    """Best effort: a failed copy never affects the application itself. Returns True when the copy was sent."""
    owner = _owner_copy(cfg)
    if not owner or not _smtp_ready(cfg) or (rec["status"] == "sent" and rec.get("to", "").lower() == owner.lower()):
        return False                       # nothing to do, or the owner already received the application itself
    try:
        s = cfg["smtp"]
        with smtplib.SMTP(s["host"], int(s.get("port", 587)), timeout=20) as srv:
            if s.get("starttls", True):
                srv.starttls()
            if s.get("user"):
                srv.login(s["user"], s.get("password", ""))
            srv.send_message(_copy_message(cfg, rec))
        return True
    except Exception as e:
        sys.stderr.write("[uaply] the owner's copy of application %s was not sent: %s: %s\n" % (rec.get("id"), type(e).__name__, str(e)[:200]))
        return False


def _send_receipt(cfg, to, subject, body, page=None, reply_to=None):
    s = cfg["smtp"]
    msg = EmailMessage()
    msg["From"] = _from(cfg)
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to and EMAIL_RE.match(reply_to):             # pressing Reply answers this address (only a plain, valid address is ever used)
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    if page:
        msg.add_alternative(page, subtype="html")
    with smtplib.SMTP(s["host"], int(s.get("port", 587)), timeout=20) as srv:
        if s.get("starttls", True):
            srv.starttls()
        if s.get("user"):
            srv.login(s["user"], s.get("password", ""))
        srv.send_message(msg)


def send_system_mail(user_id, to, subject, body, secret=False, stored_subject=None, redacted="(the link was emailed and is not kept here)", page=None):
    """Mail UAply itself sends to a person (password reset links, verification codes). Real email when SMTP is set up (whatever the
    delivery mode, since that setting is about recruiters), otherwise it lands in the simulated test inbox. `secret` keeps the secret
    out of the stored copy whenever a real email was attempted: the body is replaced by `redacted` and the subject by `stored_subject`,
    so a reset link or a code is never kept after it leaves. Only the test inbox (no real email connected) keeps it, because showing it
    there is its whole purpose. Never raises. Returns "sent", "failed" or "delivered_test"."""
    cfg = config()
    status = "delivered_test"
    if _smtp_ready(cfg):
        try:
            _send_receipt(cfg, to, subject, body, page)
            status = "sent"
        except Exception as e:
            status = "failed"
            sys.stderr.write("[uaply] sending mail failed: %s: %s\n" % (type(e).__name__, str(e)[:200]))      # the reason for the owner; the person only sees "could not send"
    keep_secret = secret and status != "delivered_test"
    try:
        auth_api.add_mail(user_id, to, (stored_subject or subject) if keep_secret else subject, redacted if keep_secret else body, status)
    except Exception:
        pass
    return status


SUPPORT_PER_HOUR = 60            # at most this many help emails an hour reach the team; the rest are still saved on the Feedback page
_support_times = []


def support_address(cfg):
    """Where help requests go: 'support_email' in the config, else the owner's own address. '' when neither is set."""
    v = cfg.get("support_email")
    if isinstance(v, str) and EMAIL_RE.match(v.strip()):
        return v.strip()
    return _owner_copy(cfg)


def send_support_ticket(rec, user=None):
    """Email a help request from the assistant to the team, with the person's email as the reply address so pressing Reply answers them.
    Returns "emailed" (the team got it by email), "failed" (the mail server refused it) or "saved" (no real email is connected, or the hourly
    limit was reached: the request is still on the Feedback page). A short acknowledgement goes to the person only when UAply has already
    proven the address is theirs (a verified account), so nobody can use this to make UAply email a stranger."""
    cfg = config()
    to = support_address(cfg)
    if not to or not _smtp_ready(cfg):
        return "saved"
    now = time.time()
    with _lock:
        _support_times[:] = [t for t in _support_times if now - t < 3600]
        if len(_support_times) >= SUPPORT_PER_HOUR:
            return "saved"
        _support_times.append(now)
    subject, body = emails.support_ticket(rec, user["email"] if user else "")
    try:
        _send_receipt(cfg, to, subject, body, reply_to=rec.get("email") or None)
    except Exception as e:
        sys.stderr.write("[uaply] sending the help request to the team failed: %s: %s\n" % (type(e).__name__, str(e)[:200]))
        return "failed"
    if user and user.get("emailVerified") and rec.get("email") and user["email"].lower() == rec["email"].lower():
        try:
            ack_subject, ack_body = emails.support_ack(rec)
            _send_receipt(cfg, user["email"], ack_subject, ack_body, reply_to=to)
        except Exception as e:
            sys.stderr.write("[uaply] sending the acknowledgement failed: %s: %s\n" % (type(e).__name__, str(e)[:200]))
    return "emailed"


def send_verification_mail(user_id, to, digits):
    """Email the 6-digit code that proves an email address is the person's own (plain text and a branded HTML version). The code is never
    kept in the stored copy once emailed."""
    subject, text, page = emails.verification_email(digits)
    return send_system_mail(user_id, to, subject, text, secret=True, page=page,
                            stored_subject="Your UAply verification code", redacted="(the code was emailed and is not kept here)")


def mail_ready():
    """True when UAply can send real email (an SMTP login is configured)."""
    return _smtp_ready(config())


def _receipt(cfg, user, cand, job, note, rec, site=""):
    """Email the signed-in applicant a copy of what happened. Never raises: a receipt problem must not undo an application."""
    to = user["email"]
    subject, body, page = emails.applicant_receipt(_mail_ctx(cfg, rec, note, user["email"], site))
    status = "delivered_test"
    if _smtp_ready(cfg):                      # the receipt goes only to the applicant's own address, so it is safe to send in test mode too
        try:
            _send_receipt(cfg, to, subject, body, page)
            status = "sent"
        except Exception as e:
            status = "failed"
            sys.stderr.write("[uaply] the applicant's confirmation was not sent: %s: %s\n" % (type(e).__name__, str(e)[:200]))
    elif cfg["delivery"] == "live":
        status = "not_configured"
    try:
        auth_api.add_mail(user["id"], to, subject, body, status)
    except Exception:
        pass
    return {"to": to, "status": status}


def submit(p, user=None, site=""):
    """Returns (http_status, dict). `user` is the signed-in account ({id, email}) or None. `site` is the address the person is using
    (for the link in their receipt)."""
    err = _validate(p)
    if err:
        return 400, {"error": err}
    cfg = config()
    mode = cfg["delivery"]
    job = {k: _s(p["job"].get(k), 600) for k in ("co", "role", "url", "source", "loc", "contact")}
    job["id"] = int(p["job"]["id"])
    known = jobs_api.job_info(job["id"]) or {}            # what this server holds about the job beats what the browser says
    pj = p["job"]
    job["type"] = _pick(known.get("type") or pj.get("type"), ("job", "parttime", "internship", "coop")) or "job"
    job["mode"] = _pick(known.get("mode") or pj.get("mode"), ("remote", "hybrid", "onsite"))
    sal = known.get("sal") or pj.get("sal")
    job["sal"] = [int(sal[0]), int(sal[1])] if isinstance(sal, list) and len(sal) == 2 and all(isinstance(x, (int, float)) for x in sal) else [0, 0]
    job["desc"] = _s(known.get("desc") or known.get("blurb") or pj.get("blurb"), 900)
    # where the posting came from ("via USAJOBS; apply on the official announcement"), from this server's own copy only: kept in the record and named in the receipt
    if known.get("credit"):
        job["via"] = _s(known.get("credit"), 200)
    if _https(known.get("announcement")):
        job["announcement"] = _https(known.get("announcement"))
    prof = p["profile"]
    cand = {"name": _s(prof.get("name"), 100), "email": _s(prof.get("email"), 200).lower(),
            "title": _s(prof.get("title"), 100), "loc": _s(prof.get("loc"), 100), "edu": _s(prof.get("edu"), 40)}
    try:
        cand["years"] = max(0, min(60, int(prof.get("years") or 0)))
    except (TypeError, ValueError):
        cand["years"] = 0
    skills = prof.get("skills")                                    # a client can send anything here; only a list is used
    cand["skills"] = [_s(x, 40) for x in (skills if isinstance(skills, list) else [])[:30] if isinstance(x, str)]
    cand["ext"] = _ext(prof.get("ext"))
    try:
        resume_meta, resume_bytes = _resume(p.get("resume"))
    except (ValueError, TypeError):
        return 400, {"error": "Your resume file could not be used. Replace it in Profile setup, under Background and links, with a PDF, Word or text file under 1 MB."}
    if resume_meta:
        cand["resume_file"] = resume_meta["name"]
    note = (p.get("note") or "").strip()

    if known.get("emp") and known.get("closed"):
        return 410, {"error": "%s is not taking applications for this job right now." % known.get("co", "This employer")}
    # Never email an address the browser sends: only the recruiter address this server found in the job feed itself.
    claimed = job["contact"] if EMAIL_RE.match(job["contact"] or "") else ""
    contact = claimed if claimed and claimed.lower() == jobs_api.known_contact(job["id"]).lower() else ""
    if known.get("emp"):
        contact = known.get("contact") or ""     # a Hiring mode posting: its verified account email, which browsers never receive
    policy = jobs_api.job_policy(job["id"])      # 'direct' (employer opted in), 'link' (employer's own page) or 'unknown' (example)
    if policy == "unknown" and job["id"] >= 100000:
        # a real posting (examples have small numbers) that this server no longer lists, for example one that left the employer's board:
        # nothing can be sent to anyone, so it is a hand-off in test mode too (test mode used to report it as delivered)
        policy = "link"
    hook = jobs_api.known_webhook(job["id"]) if policy == "direct" else None      # the HTTPS address the employer registered, if any
    ats = jobs_api.known_ats(job["id"]) if policy == "direct" else None           # the employer's own hiring system and key, if they connected
    answers = autofill.clean_answers(p.get("answers"))      # the person's own answers to questions employers' forms asked before

    def dup():
        for a in APPS:
            if a["job"]["id"] == job["id"] and a["candidate"]["email"] == cand["email"] and a["status"] != "failed":
                # "was" is what happened the first time, so the app can show it again (after an undo, or on another device)
                return 200, {"status": "duplicate", "id": a["id"], "to": a.get("to", ""), "mode": a["mode"], "was": a["status"]}
        return None

    with _lock:
        seen = dup()
    if seen:
        return seen
    if mode == "live" and policy == "direct":
        # an application sent straight to an employer carries the person's email as the reply address, so that address must be proven theirs
        if not user:                                       # nobody is signed in: there is no email to verify yet, so say what to do first
            return 403, {"error": "Sign in first (Profile, Account) and verify your email, so %s can trust your address." % job["co"], "code": "signin"}
        if not user.get("emailVerified"):
            return 403, {"error": "Verify your email first (Profile, Account) so the employer can trust your address.", "code": "verify"}
        if cand["email"] != user["email"].lower():
            return 400, {"error": "Use your account email in Profile setup, under About you, so the employer replies to an address you verified."}
        if p.get("confirm_real") is not True:
            return 400, {"error": "Live sending needs the user to review and press Send."}

    # Autofill: read the job's real application form (Greenhouse publishes it) and answer it from the profile and saved answers.
    #   - an employer that connected its Greenhouse: anything the form requires that the profile cannot answer is asked first, then it all goes in
    #   - the sandbox, in test mode: the same, for every Greenhouse posting, and the filled form goes to the test inbox (nothing reaches the employer)
    #   - every other posting: the filled answers come back with the hand-off, so finishing on the employer's page is quick
    #   - an employer that connected its Ashby or SmartRecruiters: the same as Greenhouse, but read with their key, and only for a live send
    ref = known.get("ats") if isinstance(known.get("ats"), dict) else None
    gh = ats if (ats and ats.get("kind") == "greenhouse") else (ref if ref and ref.get("kind") == "greenhouse" else None)
    preview = (mode == "test" and policy == "link" and gh is not None and
               (cfg.get("autofill_preview") is True or (INSTANCE == "sandbox" and cfg.get("autofill_preview") is not False)))
    plan = None
    if gh and (policy in ("direct", "link") or preview) and not _redirect(cfg):
        form = autofill.fetch_form(gh["board"], gh["id"])
        plan = autofill.plan_greenhouse(form, cand, job, note, resume_meta, resume_bytes, answers) if form else None
    elif ats and ats.get("kind") in ("ashby", "smartrecruiters") and policy == "direct" and mode == "live" and not _redirect(cfg):
        # Ashby and SmartRecruiters show a posting's form only to the employer's key, so it is read only for a live send to an employer who
        # connected (never in test mode, which must not use an employer's key). A question the app cannot ask (a file other than the resume, a
        # type UAply cannot fill) is not asked: the send then reports it and the person finishes on the employer's page.
        plan = ats_api.plan(ats["kind"], ats["id"], ats["key"], cand, job, note, resume_meta if resume_bytes else None, answers)
        if plan and any(m.get("kind") == "other" for m in plan["missing"]):
            plan = dict(plan, missing=[])
    if plan and plan["missing"] and (preview or (policy == "direct" and ats)):
        pub = autofill.public_plan(plan)
        return 200, {"status": "needs_answers", "mode": mode, "questions": pub["missing"], "filled": pub["filled"], "total": pub["total"]}
    summary = ({"filled": plan["filled"], "total": plan["total"],
                "items": [{"q": i["q"][:160], "a": i["a"][:200]} for i in plan["items"] if i["a"] and not i.get("skip")][:40]} if plan else None)
    if cand["ext"]["salary"] and not (plan and plan.get("salary_sent")):
        # expected pay goes only to an employer whose own form asks for it: otherwise it is not sent, kept or listed in the receipt
        cand["ext"] = dict(cand["ext"], salary="")

    send_args = None
    with _lock:
        seen = dup()                                       # checked again: a second tap may have landed while the form was being read
        if seen:
            return seen
        rec = {"id": uuid.uuid4().hex[:12], "at": int(time.time()), "mode": mode, "job": job, "candidate": cand,
               "note": note, "match": int(p.get("match") or 0), "to": "", "simulated": False, "status": "",
               "user": user["id"] if user else None, "resume": resume_meta, "channels": []}
        if summary:
            rec["autofill"] = summary
        if preview and plan:
            # the sandbox shows exactly what would go into the employer's hiring system once they connect; nothing is sent to them
            rec["to"] = "%s hiring system (simulated)" % job["co"]
            rec["simulated"] = rec["preview"] = True             # "preview": this employer has not connected, so the live app would hand off
            rec["status"] = "delivered_test"
            rec["channels"] = ["hiring system (simulated)"]
            APPS.append(rec)
            _append("applications.jsonl", rec)
        elif policy == "link" or (policy == "unknown" and mode == "live"):
            # a third-party listing, or an example in live mode: UAply never sends an application to anyone here.
            # The person is pointed to the employer's own application page instead.
            rec["status"] = "handoff"
            APPS.append(rec)
            _append("applications.jsonl", rec)
        elif mode == "test":
            # the same channels the live app would use: email only when the employer gave an address (or, for an example listing, has no
            # other channel), otherwise their hiring system or their webhook. The test inbox and the Applied list then say where it would go.
            by_mail = bool(contact) or not (hook or ats)
            rec["to"] = (contact or _simulated_recipient(job["co"])) if by_mail else (
                "%s hiring system (simulated)" % job["co"] if ats else "%s's own system (simulated)" % job["co"])
            rec["simulated"] = True
            rec["status"] = "delivered_test"
            rec["channels"] = (["email (simulated)"] if by_mail else []) + (["webhook (simulated)"] if hook else []) + (["hiring system (simulated)"] if ats else [])
            APPS.append(rec)
            _append("applications.jsonl", rec)
        else:
            target = _redirect(cfg) or contact
            hook = None if _redirect(cfg) else hook          # a test redirect must never reach a real employer's system
            ats = None if _redirect(cfg) else ats
            if (target and _smtp_ready(cfg)) or hook or ats:
                today = time.time() - 86400
                sent_today = sum(1 for a in APPS if a["mode"] == "live" and a["status"] in ("sent", "sending") and a["at"] > today)
                if sent_today >= int(cfg.get("daily_limit", 20)):
                    return 429, {"error": "Daily sending limit reached."}
                rec["to"], rec["status"] = target, "sending"      # reserved now, so a double tap cannot send twice
                APPS.append(rec)
                send_args = (cfg, target if _smtp_ready(cfg) else "", dict(cand, answers=answers, job={"co": job["co"], "role": job["role"]}) if ats else cand,
                             job, note, contact,
                             resume_meta, resume_bytes, hook, rec, ats)
            else:
                if target:                     # an employer who agreed to receive email, but this server cannot send email: tell the owner
                    sys.stderr.write("[uaply] application %s to %s became a hand-off because no email account is set up (see /setup)\n" % (rec["id"], job["co"]))
                rec["status"] = "handoff"
                APPS.append(rec)
                _append("applications.jsonl", rec)
    if send_args:                                                  # the slow network calls happen outside the lock
        try:
            status, err, channels = _deliver(*send_args)
        except Exception as e:     # never leave the record on "sending": that would block every retry as a duplicate and count toward the daily cap
            status, err, channels = "failed", "unexpected problem (%s)" % type(e).__name__, []
        with _lock:
            rec["status"], rec["channels"] = status, channels
            if err:
                rec["error"] = err
            _append("applications.jsonl", rec)
    out = {"status": rec["status"], "id": rec["id"], "to": rec["to"], "mode": mode, "simulated": rec["simulated"], "copied": False}
    if summary:
        out["plan"] = summary
    if rec.get("error"):
        sys.stderr.write("[uaply] delivery of application %s failed: %s\n" % (rec["id"], rec["error"]))      # the real reason stays in the server's own log and applications.jsonl
        # say "email" only when email was the way it went; an application for a hiring system or a webhook is not an email
        what = "The email" if all(e.startswith("email:") for e in rec["error"].split("; ")) else "Your application to %s" % job["co"]
        out["error"] = ("%s could not be sent right now. Try again in a moment." % what if hide_errors
                        else "%s could not be sent: %s" % (what, rec["error"]))
    if user and rec["status"] in ("delivered_test", "sent", "handoff"):
        # A real confirmation goes only to an address the person has proven is theirs (otherwise anyone could make UAply email a stranger).
        # With no real email connected nothing leaves this server: the confirmation is only saved in the test inbox, so it is made for any account.
        out["receipt"] = (_receipt(cfg, user, cand, job, note, rec, site) if user.get("emailVerified") or not _smtp_ready(cfg)
                          else {"to": user["email"], "status": "unverified"})
    # the owner's copy: skipped when the person who swiped already got their own confirmation at that same address (one swipe, one email)
    already = out.get("receipt", {}).get("status") == "sent" and user and user["email"].lower() == _owner_copy(cfg).lower()
    if rec["status"] != "failed" and not already:
        out["copied"] = _send_owner_copy(cfg, rec)
    return 200, out


def _line_user(line):
    """The account a stored application line belongs to (None for a broken line, which is kept as it is: it cannot be read either way)."""
    try:
        rec = json.loads(line)
        return rec.get("user") if isinstance(rec, dict) else None
    except ValueError:
        return None


def forget_user(user_id):
    """Remove every application record made while signed in as this account (used when the account is deleted)."""
    if not user_id:
        return 0
    with _lock:
        keep = [a for a in APPS if a.get("user") != user_id]
        gone = len(APPS) - len(keep)
        APPS[:] = keep
        path = os.path.join(DATA, "applications.jsonl")
        try:
            if os.path.exists(path):
                with open(path, encoding="utf-8", errors="replace") as f:
                    lines = [ln if ln.endswith("\n") else ln + "\n" for ln in f if ln.strip() and _line_user(ln) != user_id]
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                os.replace(tmp, path)
        except Exception:
            pass
    return gone


def record_decision(p):
    d = p.get("dir")
    if d not in ("apply", "pass"):
        return 400, {"error": "Bad decision."}
    try:
        rec = {"at": int(time.time()), "dir": d, "jobId": int(p.get("jobId")), "session": _s(p.get("session"), 64),
               "co": _s(p.get("co"), 200), "role": _s(p.get("role"), 200), "pct": max(0, min(100, int(p.get("pct") or 0)))}
    except (TypeError, ValueError):
        return 400, {"error": "Bad decision."}
    with _lock:
        DECISIONS.append(rec)
        _append("decisions.jsonl", rec)
    return 200, {"ok": True}


def stats():
    with _lock:
        right = sum(1 for d in DECISIONS if d["dir"] == "apply")
        left = sum(1 for d in DECISIONS if d["dir"] == "pass")
        sessions = len({d["session"] for d in DECISIONS if d["session"]})
        return {"right": right, "left": left, "sessions": sessions, "applications": len(APPS)}


def outbox_json():
    st = stats()                       # takes the lock itself, so call it before taking the lock again
    with _lock:
        return {"stats": st, "applications": list(reversed(APPS))[:100]}


def _autofill_html(af):
    """The employer's own application form as UAply filled it in (question and answer), for the test inbox."""
    if not isinstance(af, dict) or not af.get("items"):
        return ""
    e = html.escape
    rows = "".join("<tr><td>%s</td><td>%s</td></tr>" % (e(i.get("q", "")), e(i.get("a", ""))) for i in af["items"])
    return ('<details open><summary>Employer\'s application form, filled in by UAply: %d of %d answers</summary>'
            '<table class="af">%s</table></details>' % (af.get("filled", 0), af.get("total", 0), rows))


def outbox_html():
    e = html.escape
    st = stats()
    with _lock:
        apps = list(reversed(APPS))[:50]
    rows = []
    for a in apps:
        j, c = a["job"], a["candidate"]
        badge = {"delivered_test": "TEST", "sent": "SENT", "handoff": "HANDOFF", "failed": "FAILED"}.get(a["status"], a["status"].upper())
        rows.append(
            '<article><header><span class="b">%s</span><b>%s</b> to %s%s<time>%s</time></header>'
            '<p class="m">From %s &lt;%s&gt; · %s, %s yrs · match %d%% · <a href="%s" target="_blank" rel="noopener noreferrer">posting</a></p>'
            '<pre>%s</pre>%s</article>' % (
                e(badge), e(j["role"]), e(j["co"]), (" &lt;%s&gt;" % e(a["to"])) if a["to"] else "",
                time.strftime("%b %d, %H:%M", time.localtime(a["at"])),
                e(c["name"]), e(c["email"]), e(c["title"] or "candidate"), c["years"], a["match"], e(j["url"]), e(_application_text(c, j, a["note"])),
                _autofill_html(a.get("autofill"))))
    body = "".join(rows) or "<p class='m'>No applications yet. Swipe right on a job in the sandbox or dev app.</p>"
    try:
        mails = auth_api.mail_list(30)
    except Exception:
        mails = []
    mail_badge = {"delivered_test": "TEST", "sent": "SENT", "failed": "FAILED", "not_configured": "NOT SENT"}
    receipts = "<h2 style='margin:12px 0 0;font-size:18px'>Receipts to applicants</h2><p class='m'>What signed-in applicants receive at their own email after each swipe right.</p>" + (
        "".join('<article><header><span class="b">%s</span><b>%s</b> to %s<time>%s</time></header><pre>%s</pre></article>' % (
            e(mail_badge.get(m["status"], m["status"].upper())), e(m["subject"]), e(m["to_addr"]),
            time.strftime("%b %d, %H:%M", time.localtime(m["at"])), e(m["body"])) for m in mails)
        or "<p class='m'>No receipts yet. Sign in to UAply, then swipe right on a job.</p>")
    return ("""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>UAply test inbox</title><style>
:root{--bg:#FDF0F2;--surface:#FFFFFF;--ink:#2A1218;--muted:#7B5560;--line:#F3DADF;--accent:#C92A55}
@media (prefers-color-scheme: dark){:root{--bg:#190B10;--surface:#26131A;--ink:#FBE9EE;--muted:#C79BA6;--line:#40222B;--accent:#FF7A98}}
body{margin:0;padding:16px;background:var(--bg);color:var(--ink);font:15px/1.45 'DM Sans','Segoe UI',system-ui,sans-serif}
main{max-width:760px;margin:auto;display:flex;flex-direction:column;gap:12px}h1{margin:0;font-size:22px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.stats div{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px;text-align:center}
.stats b{display:block;font-size:22px}.stats small,.m{color:var(--muted)}
article{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:12px}
header{display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center}header time{margin-left:auto;color:var(--muted);font-size:13px}
.b{font:700 11px ui-monospace,Menlo,monospace;padding:2px 7px;border-radius:6px;background:var(--accent);color:#fff}
pre{white-space:pre-wrap;margin:8px 0 0;font:inherit;background:var(--bg);border-radius:10px;padding:10px}a{color:var(--accent)}
details{margin-top:8px}summary{cursor:pointer;font-weight:700}.af{width:100%%;border-collapse:collapse;margin-top:6px;font-size:13.5px}
.af td{border-top:1px solid var(--line);padding:6px 4px;vertical-align:top}.af td:first-child{color:var(--muted);width:55%%}
</style></head><body><main><h1>UAply test inbox</h1><p class="m">Simulated recruiter inbox. In test mode nothing leaves this computer.</p>
<div class="stats"><div><b>%d</b><small>Swipes right</small></div><div><b>%d</b><small>Swipes left</small></div><div><b>%d</b><small>Applications</small></div><div><b>%d</b><small>Testers</small></div></div>
%s%s</main></body></html>""" % (st["right"], st["left"], st["applications"], st["sessions"], body, receipts)).encode("utf-8")
