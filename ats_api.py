"""Delivery straight into an employer's own hiring system (applicant tracking system, "ATS") through its official application endpoint.

This is the only way an application can reach an employer's system by itself. Greenhouse, Lever and the others document an application endpoint, and every
one of them needs a key that the EMPLOYER's own administrator creates and hands over. So this runs only for employers who connected with their key
(see EMPLOYERS.md); for every other job UAply sends the person to the employer's own page and sends nothing.

  greenhouse  POST {base}/v1/boards/{board}/jobs/{id}   Basic auth with the employer's Job Board API key; multipart first_name, last_name, email, phone,
              resume, answers to the posting's questions. The form is read and answered by autofill.py (the same public form the employer's careers
              page shows); a required question that neither the profile nor the person's saved answers can answer means nothing is sent, and the app
              asks the person that question once.
  lever       POST {base}/v0/postings/{site}/{id}?key=KEY   multipart name, email, phone, org, urls[...], comments, resume. Lever's API carries no
              custom questions.
  ashby       POST {base}/jobPosting.info  {"jobPostingId"}   reads the posting's application form (needs the key: Ashby's public job board does
              not include the form). Then POST {base}/applicationForm.submit, multipart: jobPostingId, applicationForm (a JSON string
              {"fieldSubmissions": [{"path", "value"}]}) and one part per file, named by the value of the field that refers to it. Both calls use
              Basic auth with the key as the user name. Ashby answers HTTP 200 with "success": false and "errors" when it refuses a form.
  smartrecruiters
              GET {base}/postings/{uuid}/configuration   the posting's screening questions and consent settings; then POST {base}/postings/{uuid}/
              candidates with JSON firstName, lastName, email, phoneNumber, location, web, education, resume (the file in base64), answers
              ([{"id", "records": [{"fields": {field id: [values]}}]}]), messageToHiringManager and consentDecisions. The key goes in X-SmartToken.

Ashby and SmartRecruiters forms are answered by autofill.plan_questions, the same rules Greenhouse uses, and the same promise: a required question
that neither the profile nor a saved answer can answer means nothing is sent. Voluntary diversity questions are never answered.

Every call: HTTPS only, no redirects followed, 20 second limit, a capped reply, and the key is never written to a log or an error message.
"""
import base64
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

KINDS = ("greenhouse", "lever", "ashby", "smartrecruiters")
NAMES = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "smartrecruiters": "SmartRecruiters"}
_BASES = {"greenhouse": "https://boards-api.greenhouse.io", "lever": "https://api.lever.co", "ashby": "https://api.ashbyhq.com",
          "smartrecruiters": "https://api.smartrecruiters.com"}
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
KEY_RE = re.compile(r"^[A-Za-z0-9_.:+/=-]{8,200}$")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _base(kind):
    """The address of the ATS. Tests may point it at this computer (UAPLY_ATS_BASE_GREENHOUSE, _LEVER, _ASHBY, _SMARTRECRUITERS); anything else
    in that variable is ignored."""
    v = os.environ.get("UAPLY_ATS_BASE_" + kind.upper(), "")
    if re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$", v):
        return v
    return _BASES[kind]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_open = urllib.request.build_opener(_NoRedirect).open


def valid_connection(kind, board, key):
    return kind in KINDS and isinstance(board, str) and bool(TOKEN_RE.match(board)) and isinstance(key, str) and bool(KEY_RE.match(key))


def _multipart(fields, files):
    """fields: [(name, text)], files: [(name, filename, content_type, bytes)] -> (body bytes, content-type header)."""
    boundary = "----uaply" + uuid.uuid4().hex
    out = []
    for name, value in fields:
        out.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (boundary, name, value)).encode("utf-8"))
    for name, filename, ctype, data in files:
        safe = re.sub(r'[^A-Za-z0-9._ -]', "_", filename)
        out.append(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\nContent-Type: %s\r\n\r\n' % (boundary, name, safe, ctype)).encode("utf-8"))
        out.append(data)
        out.append(b"\r\n")
    out.append(("--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(out), "multipart/form-data; boundary=" + boundary


def _call(req, timeout=20):
    """Returns (status, parsed_json_or_None). Never raises: a network failure comes back as status 0."""
    try:
        with _open(req, timeout=timeout) as r:
            raw = r.read(200000)
            status = r.status
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read(20000)
    except Exception:
        return 0, None
    try:
        return status, json.loads(raw.decode("utf-8"))
    except Exception:
        return status, None


def _short(body, key=""):
    """A short, key-free reason from an ATS error reply. The reply is the other side's text, so it is cut short, stripped of control characters,
    and the key is blanked out in case a misbehaving system echoes it back."""
    if isinstance(body, dict):
        info = body.get("errorInfo") if isinstance(body.get("errorInfo"), dict) else {}
        for v in (body.get("error"), body.get("message"), body.get("errors"), info.get("message"), info.get("code")):
            if isinstance(v, list) and v:
                v = v[0].get("message") or v[0].get("code") if isinstance(v[0], dict) else v[0]
            if isinstance(v, (str, int, float)) and str(v).strip():
                s = re.sub(r"[\x00-\x1f\x7f<>]+", " ", str(v)[:400])
                if key:
                    s = s.replace(key, "[key]")
                return re.sub(r"\s+", " ", s).strip()[:120]
    return ""


def _basic(key):
    return "Basic " + base64.b64encode((key + ":").encode("utf-8")).decode("ascii")


_FORMS = {}            # (kind, base, posting, a fingerprint of the key) -> (when, form, status, why): the key itself is never kept here
_FORMS_LOCK = threading.Lock()


def _cached_form(kind, posting, key, read):
    """(form or None, HTTP status, short reason). A posting's form read with the employer's key, kept for six hours (a failed read for five minutes), so the question check before a swipe
    and the send right after it read the form once. The cache is keyed by a fingerprint of the key, so a corrected key is tried at once."""
    ck = (kind, _base(kind), posting, hashlib.sha256(key.encode("utf-8")).hexdigest()[:16])
    now = time.time()
    with _FORMS_LOCK:
        hit = _FORMS.get(ck)
        if hit and now - hit[0] < (6 * 3600 if hit[1] is not None else 300):
            return hit[1], hit[2], hit[3]
    form, status, why = read()
    with _FORMS_LOCK:
        if len(_FORMS) >= 600:
            for k in sorted(_FORMS, key=lambda k: _FORMS[k][0])[:150]:
                _FORMS.pop(k, None)
        if form is not None or status not in (0, 401, 403, 429):      # a key, network or rate problem is not remembered: the next swipe asks again
            _FORMS[ck] = (now, form, status, why)
    return form, status, why


# ---------------------------------------------------------------- Greenhouse ----------------------------------------------------------------
def _greenhouse(board, job_id, key, cand, note, resume_meta, resume_bytes):
    import autofill                                            # here, not at the top: autofill imports this module
    base = _base("greenhouse")
    form, status = autofill.read_form(board, job_id)
    if not form:
        return "failed", "could not read the job's application form (HTTP %s)" % status
    plan = autofill.plan_greenhouse(form, cand, {"co": form.get("company_name") or "", "role": form.get("title") or ""}, note,
                                    resume_meta, resume_bytes, cand.get("answers"))
    if plan["missing"]:
        return "needs_manual", "required questions UAply cannot answer from the profile: " + "; ".join(m["q"][:60] for m in plan["missing"][:5])
    fields, files = plan["fields"], plan["files"]
    body, ctype = _multipart(fields, files)
    token = base64.b64encode((key + ":").encode("utf-8")).decode("ascii")
    status, reply = _call(urllib.request.Request("%s/v1/boards/%s/jobs/%s" % (base, board, job_id), data=body, method="POST",
                                                 headers={"Content-Type": ctype, "Authorization": "Basic " + token, "Accept": "application/json"}))
    if status in (200, 201):
        return "sent", ""
    if status in (401, 403):
        return "failed", "Greenhouse refused the key for this board (HTTP %s)" % status
    return "failed", "Greenhouse did not accept the application (HTTP %s) %s" % (status, _short(reply))


# ---------------------------------------------------------------- Lever -----------------------------------------------------------------------
def _lever(site, posting_id, key, cand, note, resume_meta, resume_bytes):
    base = _base("lever")
    ext = cand.get("ext") or {}
    comments = "\n\n".join(x for x in ((note or "").strip(), (ext.get("summary") or "").strip(), "Applied through UAply.") if x)
    fields = [("name", cand.get("name") or ""), ("email", cand.get("email") or ""), ("source", "UAply")]
    if ext.get("phone"):
        fields.append(("phone", ext["phone"]))
    if ext.get("employer"):
        fields.append(("org", ext["employer"]))
    if ext.get("linkedin"):
        fields.append(("urls[LinkedIn]", ext["linkedin"]))
    if ext.get("portfolio"):
        fields.append(("urls[Portfolio]", ext["portfolio"]))
    if ext.get("resume"):
        fields.append(("urls[Resume link]", ext["resume"]))
    fields.append(("comments", comments))
    files = [("resume", resume_meta["name"], resume_meta["type"], resume_bytes)] if resume_bytes and resume_meta else []
    body, ctype = _multipart(fields, files)
    url = "%s/v0/postings/%s/%s?key=%s" % (base, site, posting_id, urllib.parse.quote(key, safe=""))
    status, reply = _call(urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": ctype, "Accept": "application/json"}))
    if status == 200:
        return "sent", ""
    if status in (401, 403):
        return "failed", "Lever refused the key for this site (HTTP %s)" % status
    if status == 429:
        return "failed", "Lever is limiting applications for a moment (HTTP 429)"
    return "failed", "Lever did not accept the application (HTTP %s) %s" % (status, _short(reply))


# ---------------------------------------------------------------- Ashby -----------------------------------------------------------------------
# Field types from Ashby's guide "Creating a custom careers page" and its API reference: String, Email, Phone, SocialLink, LongText, ValueSelect
# (the option's value), MultiValueSelect (a list of values), Boolean, Number, Date, File. Anything else (Score, Location, a new type) is left to
# the person: if it is required, nothing is sent.
_ASHBY_KINDS = {"String": "text", "Email": "text", "Phone": "text", "SocialLink": "text", "LongText": "textarea", "ValueSelect": "select",
                "MultiValueSelect": "multi", "Boolean": "boolean", "Number": "number", "Date": "date", "File": "file"}


def _ashby_form(posting_id, key):
    def read():
        status, reply = _call(urllib.request.Request(_base("ashby") + "/jobPosting.info", data=json.dumps({"jobPostingId": posting_id}).encode("utf-8"),
                                                     method="POST", headers={"Content-Type": "application/json", "Accept": "application/json",
                                                                             "Authorization": _basic(key)}))
        r = reply.get("results") if isinstance(reply, dict) else None
        if status == 200 and isinstance(r, dict) and reply.get("success") is True and isinstance(r.get("applicationFormDefinition"), dict):
            return {"definition": r["applicationFormDefinition"], "title": str(r.get("title") or "")}, 200, ""
        return None, status, _short(reply, key)
    return _cached_form("ashby", posting_id, key, read)


def _ashby_questions(definition):
    """Ashby's form definition as plain questions for autofill.plan_questions. The guide lists each section's entries under "fields"; some
    replies call them "fieldEntries", so both are read."""
    out = []
    for sec in definition.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        for entry in (sec.get("fields") or sec.get("fieldEntries") or []):
            f = entry.get("field") if isinstance(entry, dict) else None
            if not isinstance(f, dict) or not isinstance(f.get("path"), str) or not f["path"]:
                continue
            path, ftype, title = f["path"], str(f.get("type") or ""), str(f.get("title") or f.get("humanReadablePath") or "")
            # the person's own email and phone go only into the form's own email and phone fields, never into, say, a referee's phone number
            plain = re.sub(r"[^a-z]", "", title.lower())
            role = ("name" if path == "_systemfield_name" else
                    "email" if path == "_systemfield_email" or (ftype == "Email" and plain in ("email", "emailaddress")) else
                    "resume" if path == "_systemfield_resume" or (ftype == "File" and re.search(r"\b(resume|cv)\b", title, re.I)) else
                    "phone" if path == "_systemfield_phone" or (ftype == "Phone" and plain in ("phone", "phonenumber", "mobile", "mobilenumber")) else "")
            opts = [{"label": str(v.get("label", "")), "value": v.get("value")} for v in (f.get("selectableValues") or []) if isinstance(v, dict)]
            out.append({"id": path, "label": title, "req": entry.get("isRequired", True) is not False, "kind": _ASHBY_KINDS.get(ftype, "other"),
                        "options": opts, "role": role})
    return out


def _ashby_plan(posting_id, key, cand, job, note, resume_meta, answers):
    """(plan or None, why it could not be read) for one Ashby posting."""
    import autofill
    form, status, why = _ashby_form(posting_id, key)
    if not form:
        if status in (401, 403):
            return None, "Ashby refused the key (HTTP %s)" % status
        return None, "could not read the job's application form from Ashby (HTTP %s) %s" % (status, why)
    return autofill.plan_questions(_ashby_questions(form["definition"]), cand, dict(job, role=job.get("role") or form["title"]), note,
                                   resume_meta, answers, job.get("co") or ""), ""


def _ashby(posting_id, key, cand, note, resume_meta, resume_bytes):
    job = cand.get("job") if isinstance(cand.get("job"), dict) else {}           # the company and role, for the person's "why" template
    plan, why = _ashby_plan(posting_id, key, cand, job, note, resume_meta if resume_bytes else None, cand.get("answers"))
    if not plan:
        return "failed", why
    if plan["missing"]:
        return "needs_manual", "required questions UAply cannot answer from the profile: " + "; ".join(m["q"][:60] for m in plan["missing"][:5])
    subs, files = [{"path": p, "value": v} for p, v in plan["values"]], []
    for i, path in enumerate(plan["resume"]):          # the field's value names the file part that carries the file
        subs.append({"path": path, "value": "resume_%d" % (i + 1)})
        files.append(("resume_%d" % (i + 1), resume_meta["name"], resume_meta["type"], resume_bytes))
    body, ctype = _multipart([("jobPostingId", posting_id), ("applicationForm", json.dumps({"fieldSubmissions": subs})),
                              ("utmData", json.dumps({"utm_source": "UAply"}))], files)
    status, reply = _call(urllib.request.Request(_base("ashby") + "/applicationForm.submit", data=body, method="POST",
                                                 headers={"Content-Type": ctype, "Authorization": _basic(key), "Accept": "application/json"}))
    if status in (401, 403):
        return "failed", "Ashby refused the key (HTTP %s)" % status
    if status == 429:
        return "failed", "Ashby is limiting applications for a moment (HTTP 429)"
    if status == 200 and isinstance(reply, dict) and reply.get("success") is True:
        res = reply.get("results") if isinstance(reply.get("results"), dict) else {}
        if reply.get("blocked") is True or res.get("blocked") is True:     # the employer's limit on applications per person
            return "failed", "Ashby blocked this application (the employer limits how many applications one person may send)"
        return "sent", ""
    return "failed", "Ashby did not accept the application (HTTP %s) %s" % (status, _short(reply, key))


# ---------------------------------------------------------------- SmartRecruiters -------------------------------------------------------------
# Field types from SmartRecruiters' Application API reference: INPUT_TEXT, TEXTAREA, SINGLE_SELECT, RADIO, MULTI_SELECT, CHECKBOX, INFORMATION
# (text to show, nothing to answer). A field with complianceType DIVERSITY is voluntary and is never answered.
_SR_KINDS = {"INPUT_TEXT": "text", "TEXTAREA": "textarea", "SINGLE_SELECT": "select", "RADIO": "select", "MULTI_SELECT": "multi", "CHECKBOX": "multi"}
_SR_CONSENT = "I consent to the employer's privacy policy so they can process my application"


def _sr_form(uuid_, key):
    def read():
        status, reply = _call(urllib.request.Request("%s/postings/%s/configuration" % (_base("smartrecruiters"), uuid_),
                                                     headers={"X-SmartToken": key, "Accept": "application/json", "Accept-Language": "en"}))
        if status == 200 and isinstance(reply, dict) and isinstance(reply.get("questions", []), list):
            return {k: reply.get(k) for k in ("questions", "consentSettings", "privacyPolicies")}, 200, ""
        return None, status, _short(reply, key)
    return _cached_form("smartrecruiters", uuid_, key, read)


def _sr_questions(form):
    """The configuration's screening questions as plain questions, one per field ("qid/fid"), plus the consent the employer requires."""
    out = []
    for q in form.get("questions") or []:
        if not isinstance(q, dict) or not isinstance(q.get("id"), str):
            continue
        fields = [f for f in (q.get("fields") or []) if isinstance(f, dict) and isinstance(f.get("id"), str) and f.get("type") != "INFORMATION"]
        for f in fields:
            label = str(q.get("label") or "")
            if len(fields) > 1 and f.get("label") and f.get("label") != label:
                label = (label + " - " + str(f["label"])).strip(" -")
            opts = [{"label": str(v.get("label", "")), "value": v.get("id")} for v in (f.get("values") or []) if isinstance(v, dict)]
            out.append({"id": q["id"] + "/" + f["id"], "label": label, "req": f.get("required") is True, "kind": _SR_KINDS.get(f.get("type"), "other"),
                        "options": opts, "voluntary": f.get("complianceType") == "DIVERSITY"})
    scopes = [s for s in ((form.get("consentSettings") or {}).get("scopes") or []) if isinstance(s, dict) and s.get("required") is True and s.get("scope")]
    if scopes:          # a required consent is a question like any other: ticked only with "acknowledge for me" or the person's own answer
        out.append({"id": "consent", "label": _SR_CONSENT, "req": True, "kind": "select",
                    "options": [{"label": "I consent", "value": "yes"}, {"label": "No", "value": "no"}], "scopes": [s["scope"] for s in scopes]})
    return out


def _sr_plan(uuid_, key, cand, job, note, resume_meta, answers):
    import autofill
    form, status, why = _sr_form(uuid_, key)
    if not form:
        if status in (401, 403):
            return None, None, "SmartRecruiters refused the key (HTTP %s)" % status
        return None, None, "could not read the job's screening questions from SmartRecruiters (HTTP %s) %s" % (status, why)
    qs = _sr_questions(form)
    return autofill.plan_questions(qs, cand, job, note, resume_meta, answers, job.get("co") or ""), qs, ""


def _sr_body(plan, qs, cand, note, resume_meta, resume_bytes):
    """The candidate record SmartRecruiters' Application API takes."""
    import autofill
    ext = cand.get("ext") or {}
    first, last = autofill._first_last(cand.get("name"))
    body = {"firstName": first, "lastName": last, "email": cand.get("email") or ""}
    if ext.get("phone"):
        body["phoneNumber"] = ext["phone"]
    state = autofill._state(ext, cand)
    city = re.split(r",", cand.get("loc") or "")[0].strip()
    if city and state and not re.search(r"remote", city, re.I):          # city and country code are required whenever a location is sent
        body["location"] = {"city": city, "region": state[0], "regionCode": state[1], "country": "United States", "countryCode": "us"}
    web = {k: v for k, v in (("linkedIn", ext.get("linkedin")), ("website", ext.get("portfolio"))) if v}
    if web:
        body["web"] = web
    degree = autofill._EDU.get(cand.get("edu") or "")
    if ext.get("school") and degree:                                 # institution and degree are both required in an education entry
        body["education"] = [dict({"institution": ext["school"], "degree": degree}, **({"major": ext["major"]} if ext.get("major") else {}))]
    if resume_bytes and resume_meta:
        body["resume"] = {"fileName": re.sub(r'[^A-Za-z0-9._ -]', "_", resume_meta["name"])[:100], "mimeType": resume_meta["type"],
                          "fileContent": base64.b64encode(resume_bytes).decode("ascii")}
    elif ext.get("resume"):
        note = ((note or "") + "\n\nResume: " + ext["resume"]).strip()
    msg = "\n\n".join(x for x in ((note or "").strip(), (ext.get("summary") or "").strip(), "Applied through UAply.") if x)
    body["messageToHiringManager"] = msg[:4000]
    grouped, consent = {}, None
    for qid, val in plan["values"]:
        if qid == "consent":
            consent = val == "yes"
            continue
        q, f = qid.split("/", 1)
        grouped.setdefault(q, {})[f] = [str(v) for v in val] if isinstance(val, list) else [str(val)]
    body["answers"] = [{"id": q, "records": [{"fields": fs}]} for q, fs in grouped.items()]
    scopes = next((q["scopes"] for q in qs if q["id"] == "consent"), [])
    if scopes and consent is not None:
        body["consentDecisions"] = {s: consent for s in scopes}         # only the scopes the employer requires; optional ones are never ticked
    return body


def _smartrecruiters(uuid_, key, cand, note, resume_meta, resume_bytes):
    if not UUID_RE.match(uuid_):
        return "failed", "SmartRecruiters needs the posting's uuid (the long id with dashes), not its number"
    job = cand.get("job") if isinstance(cand.get("job"), dict) else {}
    plan, qs, why = _sr_plan(uuid_, key, cand, job, note, resume_meta if resume_bytes else None, cand.get("answers"))
    if not plan:
        return "failed", why
    if plan["missing"]:
        return "needs_manual", "required questions UAply cannot answer from the profile: " + "; ".join(m["q"][:60] for m in plan["missing"][:5])
    body = json.dumps(_sr_body(plan, qs, cand, note, resume_meta, resume_bytes)).encode("utf-8")
    status, reply = _call(urllib.request.Request("%s/postings/%s/candidates" % (_base("smartrecruiters"), uuid_), data=body, method="POST",
                                                 headers={"Content-Type": "application/json", "Accept": "application/json", "X-SmartToken": key}))
    if status in (200, 201):
        return "sent", ""
    if status in (401, 403):
        return "failed", "SmartRecruiters refused the key (HTTP %s)" % status
    if status == 429:
        return "failed", "SmartRecruiters is limiting applications for a moment (HTTP 429)"
    return "failed", "SmartRecruiters did not accept the application (HTTP %s) %s" % (status, _short(reply, key))


def plan(kind, job_id, key, cand, job, note, resume_meta, answers):
    """The filled form for a posting whose form can be read only with the employer's key (Ashby, SmartRecruiters), or None. uaply_api uses it
    before a swipe is sent, so a missing required answer is asked of the person once, the same way as for Greenhouse."""
    if not isinstance(job_id, str) or not ID_RE.match(job_id) or not isinstance(key, str) or not KEY_RE.match(key):
        return None
    try:
        if kind == "ashby":
            return _ashby_plan(job_id, key, cand, job, note, resume_meta, answers)[0]
        if kind == "smartrecruiters" and UUID_RE.match(job_id):
            return _sr_plan(job_id, key, cand, job, note, resume_meta, answers)[0]
    except Exception:
        pass
    return None


def submit(kind, board, job_id, key, cand, note, resume_meta, resume_bytes):
    """Send one application into the employer's hiring system. Returns (status, reason): "sent", "needs_manual" (nothing was sent: the posting
    has required questions the profile cannot answer, so the person finishes on the employer's page) or "failed"."""
    if not valid_connection(kind, board, key) or not isinstance(job_id, str) or not ID_RE.match(job_id):
        return "failed", "this connection is not set up correctly"
    try:
        if kind == "greenhouse":
            return _greenhouse(board, job_id, key, cand, note, resume_meta, resume_bytes)
        if kind == "ashby":
            return _ashby(job_id, key, cand, note, resume_meta, resume_bytes)
        if kind == "smartrecruiters":
            return _smartrecruiters(job_id, key, cand, note, resume_meta, resume_bytes)
        return _lever(board, job_id, key, cand, note, resume_meta, resume_bytes)
    except Exception as e:                                   # never let one employer's system break the swipe
        return "failed", "unexpected problem (%s)" % type(e).__name__
