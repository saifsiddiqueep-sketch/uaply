"""Profile readiness: is a profile complete enough to send real applications? (Trello card 9, first-run experience.)

The required fields are the ones an application actually carries to an employer (uaply_api.submit and autofill.py's standard fields):
  name, email     uaply_api._validate already refuses an application without them
  phone           the standard Greenhouse / Ashby / Workable field (autofill.py fills it from ext.phone)
  location        the profile's city ("loc"): shown to the recruiter and used for the location questions
  resume          a resume file uploaded in Profile setup, or an https link to one (ext.resume)
Everything else (job preferences, pay, links, GPA, work authorization, voluntary self-identification) is optional and never blocks.

States: not_started (nothing required is filled), in_progress (some), ready (all). The same rules run in the browser (shared/uaply-onboard.js)
for the "Profile N% complete" indicator, but this file decides: uaply_api.submit refuses a profile that is not ready where the rule is on.
"""
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[+()\d\s.-]{7,25}$")

# (key, label shown to the person, Profile setup step that holds it)
REQUIRED = (("name", "Full name", "about"), ("email", "Email", "about"), ("phone", "Phone number", "about"),
            ("loc", "City", "where"), ("resume", "Resume", "back"))
STEP_ORDER = ("about", "jobs", "where", "back", "final")


def _str(v, n=200):
    return v.strip()[:n] if isinstance(v, str) else ""


def filled(profile, has_resume=False):
    """{key: bool} for each required field. `profile` is the shape the app sends to /api/apply ({name, email, loc, ext: {phone, resume}})."""
    p = profile if isinstance(profile, dict) else {}
    x = p.get("ext") if isinstance(p.get("ext"), dict) else {}
    return {"name": bool(_str(p.get("name"), 100)), "email": bool(EMAIL_RE.match(_str(p.get("email")))),
            "phone": bool(PHONE_RE.match(_str(x.get("phone"), 25))), "loc": bool(_str(p.get("loc"), 100)),
            "resume": bool(has_resume) or _str(x.get("resume"), 300).startswith("https://")}


def check(profile, has_resume=False):
    """{state, percent, missing: [{key, label, step}], step: the earliest Profile setup step with something missing (or None)}."""
    f = filled(profile, has_resume)
    missing = [{"key": k, "label": label, "step": step} for k, label, step in REQUIRED if not f[k]]
    done = len(REQUIRED) - len(missing)
    state = "ready" if not missing else "not_started" if done == 0 else "in_progress"
    first = min((STEP_ORDER.index(m["step"]) for m in missing), default=None)
    return {"state": state, "percent": round(100 * done / len(REQUIRED)), "missing": missing,
            "step": STEP_ORDER[first] if first is not None else None, "required": [k for k, _, _ in REQUIRED]}


def enforced(cfg, instance):
    """Where submit refuses a profile that is not ready: the sandbox (this is a sandbox experiment), or any instance whose config sets
    "require_ready": true. "require_ready": false switches it off in the sandbox too. The release build (dev) is unchanged."""
    v = cfg.get("require_ready") if isinstance(cfg, dict) else None
    return v is True or (v is not False and instance == "sandbox")
