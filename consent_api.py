"""The first-swipe agreement and its record on the account (Saif, October 23, 2026: no automatic send of any kind without it).

The box before the first swipe (shared/uaply-live.js, CONSENT_TEXT and autoText) shows these exact words. When the person agrees, the
page posts POST /api/consent {version, text, auto} and this server keeps, on the account (auth_api.record_consent): the version, the time
(this server's clock), the visitor's address (the last hop, as every limit reads it: serve.client_ip) and the SHA-256 of the text agreed
to. The text the page sends is checked against this file's own copy first, so a record always names words this server knows (and a page
that shows other words cannot make one); tools/test-consent.py checks the two copies are the same, word for word.

Nothing is sent to an employer by UAply itself (an application emailed to an employer, or put into an employer's hiring system) unless
the account's latest record is this VERSION (uaply_api.submit answers 403 "consent" otherwise). The phone app presses an employer's Submit
for the person only when that record also has auto: the separate "Automatic submit" tick, off by default (shared/uaply-nav.js).

VERSION 4, October 23, 2026, pending the lawyer (LEGAL-REVIEW.md, section 12): Reviewer 3's words (the four ways a swipe right goes, and
Send applications for me in Profile, Account to stop it), and the optional automatic submit as its own tick. Everyone who agreed to version 3
sees the box once more."""
import hashlib
import json
import os
import re

VERSION = 4

# the box's words, one entry per sentence group, as plain text: Reviewer 3's version 4 (the page adds the bold, the list, the links and the
# buttons; its heading, "Before you start swiping", is not part of the words agreed to)
TEXT = (
    "A swipe right authorizes UAply to submit your application on your behalf, using the information in your profile.",
    "The match percentage is worked out automatically from your profile to help order jobs. It never rejects you, and employers make every hiring decision. How matching works",
    "Depending on the job:",
    "Employers connected to UAply receive it straight into their hiring system.",
    "If the employer publishes an email address for applications, UAply emails your application and resume there.",
    "On hiring systems with no 'are you human' check and no rule against applying through someone else, and only if you turn on Automatic submit below, UAply fills in the form and presses Submit for you.",
    "Everywhere else, UAply fills in the employer's form and you check it and press Submit yourself.",
    "UAply never answers questions about race, gender, veteran status or disability, and never completes a security check.",
    "You are responsible for keeping your profile accurate. You can tap Undo right after a swipe.",
    "To stop UAply sending applications for you, turn off Send applications for me in Profile, Account.",
    "By continuing you agree to the Terms and Privacy Policy.",
)
# the separate tick, off by default: only with it may the phone app press an employer's Submit for the person, where that is allowed.
# Where that is comes from shared/assist-systems.json (the owner's per-system switch), so the words update themselves when a system is
# switched on: "where a hiring system allows it; none is switched on yet" today. The page builds the same words (uaply-live.js autoWhere).
AUTO_TAIL = (" Where one is, a swipe right fills the employer's form from your profile and presses Submit for you. UAply never answers voluntary "
             "self-identification questions, never ticks consent or certification boxes, and never completes a security check; if one is "
             "needed it stops and you finish.")
AUTO_AT = 7               # the tick sits after the four ways (the box's entries 0 to 6), above "UAply never answers..." and "By continuing"
NAMES = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "smartrecruiters": "SmartRecruiters", "workable": "Workable"}
SYSTEMS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared", "assist-systems.json")
_sys = {"mtime": None, "cfg": None}


def systems():
    """shared/assist-systems.json, read again whenever it changes ({} when it cannot be read)."""
    try:
        m = os.path.getmtime(SYSTEMS)
        if _sys["mtime"] != m:
            with open(SYSTEMS, encoding="utf-8") as f:
                _sys.update(cfg=json.load(f), mtime=m)
    except (OSError, ValueError):
        return {}
    return _sys["cfg"] or {}


def auto_where(cfg):
    """Where automatic submit is switched on, in the tick's words: the systems whose switch is "automatic" with the lawyer's approval and no
    measured human check (the rule of uaply-nav.js assistMode)."""
    s = (cfg or {}).get("systems") if isinstance(cfg, dict) else None
    on = [NAMES[k] for k, x in (s or {}).items() if k in NAMES and isinstance(x, dict) and x.get("mode") == "automatic"
          and x.get("counsel_approved") is True and x.get("human_check_share") == 0 and not isinstance(x.get("human_check_share"), bool)]
    return "where a hiring system allows it; " + ("switched on now: " + ", ".join(on) if on else "none is switched on yet")


def auto_text(cfg=None):
    """The Automatic submit line as the box shows it now."""
    return "Automatic submit: " + auto_where(systems() if cfg is None else cfg) + "." + AUTO_TAIL


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def full_text(auto=False):
    """The words agreed to, one entry per line in the order the box shows them: the Automatic submit line, when it was ticked, after the four
    ways."""
    return "\n".join(_norm(p) for p in TEXT[:AUTO_AT] + ((auto_text(),) if auto else ()) + TEXT[AUTO_AT:])


def digest(text):
    """SHA-256 of a text agreed to, after the same clean-up on both sides (one space between words, one paragraph per line)."""
    lines = [_norm(x) for x in str(text or "").replace("\r", "\n").split("\n")]
    return hashlib.sha256("\n".join(x for x in lines if x).encode("utf-8")).hexdigest()


def current(rec):
    """True when an account's latest record (auth_api.consent_for) is this version: UAply may then send applications itself."""
    return bool(rec and rec.get("v") == VERSION)


def auto_ok(rec):
    """True when the person also ticked Automatic submit in this version (the phone app reads it from /api/auth/me)."""
    return current(rec) and rec.get("auto") is True


def post(user, payload, ip, record):
    """POST /api/consent {version, text, auto} (or {withdraw: true}) for the signed-in, verified account `user`. `record` is
    auth_api.record_consent. Returns (status, body)."""
    if not user:
        return 401, {"error": "Sign in first.", "code": "signin"}
    p = payload if isinstance(payload, dict) else {}
    if p.get("withdraw") is True:          # the person took the agreement back: nothing is sent for them again until they agree once more
        record(user["id"], 0, ip, "", False)
        return 200, {"ok": True, "consent": None}
    try:
        version = int(p.get("version"))
    except (TypeError, ValueError):
        version = 0
    if version != VERSION:
        return 409, {"error": "This page is out of date. Reload UAply and agree to the current terms.", "code": "consent_old"}
    auto = p.get("auto") is True
    want = digest(full_text(auto))
    if digest(p.get("text")) != want:
        return 409, {"error": "This page is out of date. Reload UAply and agree to the current terms.", "code": "consent_text"}
    rec = record(user["id"], VERSION, ip, want, auto)
    return 200, {"ok": True, "consent": rec}
