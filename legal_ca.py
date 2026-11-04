"""Canada: the server's groundwork for Canadian users, switched off unless CANADA_ENABLED is set (1, true or yes). Off, nothing here changes
anything: region() answers US for everyone, and serve.py answers 404 for /api/legal/region, /api/legal/accept and /api/legal/quebec-waitlist,
the same as an address that does not exist. The US first-swipe agreement (consent_api.py) is not touched by any of it.

  region()          where a person's documents come from: US, CA or QC (Quebec). The profile decides; the visitor's address is only a hint, and
                    when it disagrees with the profile the page asks the person to confirm their location
  DOCS              the Canadian documents a person accepts, each with its version; all drafts today (docs/legal-drafts/canada, never served)
  needs_consent()   whether the latest acceptance on the ledger (auth_api.latest_acceptance) still covers the person
  is_sensitive_ca() questions on a Canadian application that UAply must leave to the person (SIN, work permit, age, equity, disability,
                    criminal record). Not used by the apply flow yet.
The ledger itself (legal_acceptances) and the Quebec waitlist (quebec_waitlist) live with the other tables in auth_api.py."""
import os
import re
import unicodedata


def enabled():
    """True when CANADA_ENABLED is 1, true or yes. Read on every call, so a test (or a restart with the setting) can switch it."""
    return (os.environ.get("CANADA_ENABLED") or "").strip().lower() in ("1", "true", "yes")


# the documents a Canadian accepts, by id. status "draft": the words are not final and are not served (docs/legal-drafts/canada); a new
# version of any of them asks everyone who accepted an older one again (needs_consent)
DOCS = {
    "privacy-ca": {"version": 1, "status": "draft"},
    "terms-ca": {"version": 1, "status": "draft"},
    "apply-ca": {"version": 1, "status": "draft"},
    "ai-ca": {"version": 1, "status": "draft"},
    "marketing-ca": {"version": 1, "status": "draft"},
}
METHODS = ("checkbox", "swipe")
WAITLIST_WORDING = 1             # the version of the Quebec waitlist's opt-in words, kept with each address

PROVINCES = {"AB": "alberta", "BC": "british columbia", "MB": "manitoba", "NB": "new brunswick", "NL": "newfoundland and labrador",
             "NS": "nova scotia", "NT": "northwest territories", "NU": "nunavut", "ON": "ontario", "PE": "prince edward island",
             "QC": "quebec", "SK": "saskatchewan", "YT": "yukon"}
_COUNTRY = {"us": "US", "usa": "US", "united states": "US", "united states of america": "US",
            "ca": "CA", "can": "CA", "canada": "CA"}


def _plain(s):
    """Lower case, accents and curly apostrophes taken off, one space between words: Québec and quebec, numéro and numero, d’ and d'."""
    s = unicodedata.normalize("NFKD", str(s or "")).replace("’", "'").replace("‘", "'")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def country_code(v):
    """US or CA from a code or a name ("" when it is neither or empty)."""
    return _COUNTRY.get(_plain(v), "")


def province_code(v):
    """A Canadian province or territory's two letters from its code or its name ("" when it is not one)."""
    p = _plain(v)
    if p.upper() in PROVINCES:
        return p.upper()
    for code, name in PROVINCES.items():
        if p == name:
            return code
    return ""


def region(profile_country, profile_province, ip_country=None, ip_region=None):
    """{"region": "US" | "CA" | "QC", "confirm": bool}. Switched off: always US, nothing to confirm.
    The profile decides (US when it says nothing; a Canadian province with no country means Canada). The visitor's address never decides,
    except that an address in Quebec is treated as Quebec (the stricter rules win); when the address's country differs from the profile's,
    or (in Canada) its province differs, confirm is True and the page asks the person to confirm their location."""
    if not enabled():
        return {"region": "US", "confirm": False}
    prov = province_code(profile_province)
    country = country_code(profile_country) or ("CA" if prov else "US")
    if country != "CA":
        prov = ""
    ipc = country_code(ip_country) if ip_country else ""
    ipr = province_code(ip_region) if ip_region and ipc in ("", "CA") else ""
    confirm = bool((ipc and ipc != country) or (country == "CA" and ipr and ipr != prov))
    if prov == "QC" or ipr == "QC":
        return {"region": "QC", "confirm": confirm}
    return {"region": country, "confirm": confirm}


def needs_consent(latest_row, doc, version, country, province):
    """True when the person must accept `doc` (again): nothing on the ledger, another version, or the country or province on the ledger
    is not the one they now give. latest_row is auth_api.latest_acceptance(user_id, doc)."""
    if not isinstance(latest_row, dict):
        return True
    return (latest_row.get("doc") != doc or latest_row.get("version") != version
            or (latest_row.get("country") or "") != (country or "") or (latest_row.get("province") or "") != (province or ""))


# questions a Canadian application may ask that UAply leaves to the person, by category; the first that matches wins (equity questions
# that name disabilities are self-identification, before the plain disability or accommodation ones). Matched on _plain() text, so
# French accents and apostrophes do not matter; SIN and NAS are matched in capitals only (the English word "sin" is not a question).
_SENSITIVE_CAPS = (("sin", re.compile(r"\b(SIN|NAS)\b")),)
_SENSITIVE = (
    ("sin", re.compile(r"social insurance|numero d'assurance sociale|assurance sociale")),
    ("self_id", re.compile(r"self[- ]?identif|auto[- ]?identif|employment equity|equite en matiere d'emploi|designated group|groupe designe"
                           r"|indigenous|aboriginal|autochtone|first nations?|premieres nations|\bmetis\b|\binuit|visible minorit|minorite visible"
                           r"|raciali[sz]ed|\bwom[ae]n\b|\bfemmes?\b|\bgender\b|\bgenre\b|persons? with (a )?disabilit|personnes? (en situation de|ayant un) handicap"
                           r"|\bidentify as\b|vous identifiez")),
    ("disability", re.compile(r"disabilit|handicap|accommodat|mesures? d'adaptation|limitation fonctionnelle")),
    ("criminal_record", re.compile(r"criminal|background check|police (record )?check|record suspension|\bpardon|convicted|conviction"
                                   r"|vulnerable sector|casier judiciaire|antecedents judiciaires|verification des antecedents")),
    ("work_eligibility", re.compile(r"work permit|permis de travail|(eligib|entitled|authori[sz]|legally|right|allowed|permitted)\w*\b.{0,40}\bwork\b.{0,20}\bcanada"
                                    r"|(admissible|autorise|droit)\w*\b.{0,30}\btravailler au canada|permanent resident|resident permanent|citizenship|citoyennete"
                                    r"|visa sponsorship|parrainage")),
    ("dob_age", re.compile(r"date of birth|birth ?date|\bdob\b|date de naissance|\bage\b|\bhow old\b|years of age|years old|\bans ou plus\b")),
)


def is_sensitive_ca(question_text):
    """The category of a question UAply must leave to the person on a Canadian application ("sin", "self_id", "disability",
    "criminal_record", "work_eligibility", "dob_age"), or None."""
    raw = str(question_text or "")
    for cat, rx in _SENSITIVE_CAPS:
        if rx.search(raw):
            return cat
    text = _plain(raw)
    for cat, rx in _SENSITIVE:
        if rx.search(text):
            return cat
    return None
