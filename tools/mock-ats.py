"""A stand-in for the application endpoints of Greenhouse, Lever, Ashby and SmartRecruiters, for tests. It follows their public documentation: Greenhouse
checks a Basic-auth key and serves a posting's questions; Lever checks a key in the address and needs a name and email; Ashby checks a Basic-auth key, serves
the form from jobPosting.info and takes applicationForm.submit as multipart with the answers as a JSON string; SmartRecruiters checks X-SmartToken, serves
the posting's configuration and takes the candidate as JSON. Every application it accepts is kept and shown at /__received; /__reset empties it.
  python tools/mock-ats.py 8795
Greenhouse keys: board 'acme' uses 'gh-secret-key-123'. Lever keys: site 'acme' uses 'lever-key-456'. Ashby: 'ashby-key-789' (and 'ashby-readonly-key', which
may read forms but not submit: HTTP 403). SmartRecruiters: 'sr-smarttoken-012'.
Greenhouse job ids choose the scenario: 1001 only the standard fields, 1002 also a work-authorization question and 'how did you hear', 1003 a required question that
no profile can answer, 1004 a job that does not exist, 1005 an employer system that returns an error, 1006 the questions that most often stop an
application (willing to relocate, expected pay, country) plus Greenhouse's location box (location with its hidden latitude and longitude).
Like Greenhouse, it also takes country_short_name and one employments[0][...] entry; it refuses a location without its map position, an
employment entry with a missing part and a country that is not a two-letter code, so a test sees a half-sent field. Lever posting id 'slow' answers 429.
Ashby posting ids are the forms in fixtures/ashby-forms.json; 4444... refuses the form (success false), 5555... answers with a hostile body, 6666... is
blocked by the employer's application limit, 8888... answers 429 (these four use the 1111... form). SmartRecruiters uuids are the configurations in
fixtures/smartrecruiters-configurations.json; ...0004 answers 429 and ...0005 a hostile body (both use the ...0001 configuration)."""
import base64
import binascii
import email
import re
import email.policy
import json
import os
import sys
import urllib.parse
import http.server

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8795
GH_KEY, LEVER_KEY = "gh-secret-key-123", "lever-key-456"
ASHBY_KEY, ASHBY_READONLY, SR_KEY = "ashby-key-789", "ashby-readonly-key", "sr-smarttoken-012"
RECEIVED = []
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
ASHBY_FORMS = json.load(open(os.path.join(FIX, "ashby-forms.json"), encoding="utf-8"))["forms"]
SR_CONFIGS = json.load(open(os.path.join(FIX, "smartrecruiters-configurations.json"), encoding="utf-8"))["configurations"]
HOSTILE = {"message": "<script>alert(1)</script>\x00\x07 bad key ashby-key-789 sr-smarttoken-012 " + "x" * 5000, "errors": [{"code": "<b>boom</b>"}]}


def ashby_form(pid):
    """The form for an Ashby posting id; the special ids reuse the plain form."""
    if pid[:4] in ("4444", "5555", "6666", "8888"):
        return ASHBY_FORMS["11111111-1111-4111-8111-111111111111"]
    return ASHBY_FORMS.get(pid)


def sr_config(uuid_):
    if uuid_.endswith("0004") or uuid_.endswith("0005"):
        return SR_CONFIGS["aaaaaaaa-0000-4000-8000-000000000001"]
    return SR_CONFIGS.get(uuid_)


def ashby_check(form, sub, files):
    """Problems with an Ashby submission, the way Ashby reports them ("errors": a list of strings). Checks what the documentation says: every path is on
    the form, every required field is answered, a file field's value names a file part, a select's value is one of its options."""
    fields = {}
    for sec in form["applicationFormDefinition"]["sections"]:
        for e in sec.get("fields") or sec.get("fieldEntries") or []:
            fields[e["field"]["path"]] = e
    errs, got = [], {}
    for s in sub:
        if not isinstance(s, dict) or set(s) != {"path", "value"}:
            errs.append("each fieldSubmission needs exactly path and value")
            continue
        e = fields.get(s["path"])
        if not e:
            errs.append("unknown field path %s" % s["path"])
            continue
        t, v = e["field"]["type"], s["value"]
        opts = [o["value"] for o in e["field"].get("selectableValues") or []]
        ok = {"File": lambda: isinstance(v, str) and v in files, "ValueSelect": lambda: v in opts,
              "MultiValueSelect": lambda: isinstance(v, list) and v and all(x in opts for x in v), "Boolean": lambda: isinstance(v, bool),
              "Number": lambda: isinstance(v, (int, float)) and not isinstance(v, bool)}.get(t, lambda: isinstance(v, str) and v != "")()
        if not ok:
            errs.append("invalid value for %s (%s)" % (s["path"], t))
        got[s["path"]] = v
    for p, e in fields.items():
        if e.get("isRequired", True) and p not in got:
            errs.append("missing required field %s" % p)
    return errs, got


def sr_check(cfg, body):
    """Problems with a SmartRecruiters application, checked against the posting's configuration as the Application API reference describes it."""
    errs = []
    for k in ("firstName", "lastName", "email"):
        if not isinstance(body.get(k), str) or not body[k].strip():
            errs.append("%s is required" % k)
    loc = body.get("location")
    if loc is not None and not (isinstance(loc, dict) and loc.get("city") and loc.get("countryCode")):
        errs.append("location needs city and countryCode")
    for ed in body.get("education") or []:
        if not (ed.get("institution") and ed.get("degree")):
            errs.append("education needs institution and degree")
    r = body.get("resume")
    if r is not None:
        try:
            ok = bool(r.get("fileName") and r.get("mimeType") and base64.b64decode(r.get("fileContent") or "", validate=True))
        except (binascii.Error, ValueError, AttributeError):
            ok = False
        if not ok:
            errs.append("resume needs fileName, mimeType and base64 fileContent")
    qs = {q["id"]: {f["id"]: f for f in q["fields"]} for q in cfg["questions"]}
    answered = {}
    for a in body.get("answers") or []:
        fields = qs.get(a.get("id"))
        if fields is None:
            errs.append("unknown question %s" % a.get("id"))
            continue
        for rec in a.get("records") or []:
            for fid, vals in (rec.get("fields") or {}).items():
                f = fields.get(fid)
                if not f or f["type"] == "INFORMATION":
                    errs.append("unknown field %s" % fid)
                    continue
                if f.get("complianceType") == "DIVERSITY":
                    errs.append("a voluntary diversity question was answered (%s)" % fid)     # UAply must never do this
                if not isinstance(vals, list) or not vals or not all(isinstance(v, str) for v in vals):
                    errs.append("answer values must be a list of strings (%s)" % fid)
                    continue
                ids = [v["id"] for v in f.get("values") or []]
                if ids and not all(v in ids for v in vals):
                    errs.append("not an option of %s" % fid)
                answered[fid] = vals
    for q in cfg["questions"]:
        for f in q["fields"]:
            if f.get("required") and f["type"] != "INFORMATION" and f.get("complianceType") != "DIVERSITY" and f["id"] not in answered:
                errs.append("missing required answer %s" % f["id"])
    need = sorted(s["scope"] for s in (cfg.get("consentSettings") or {}).get("scopes", []) if s.get("required"))
    given = body.get("consentDecisions")
    if need and not (isinstance(given, dict) and all(given.get(s) is True for s in need)):
        errs.append("consent is required for %s" % ", ".join(need))
    if isinstance(given, dict) and any(s not in need for s in given):
        errs.append("an optional consent was ticked")                                   # UAply never ticks the optional ones
    return errs, answered


def std(required_phone=False):
    return [
        {"required": True, "label": "First Name", "fields": [{"name": "first_name", "type": "input_text", "values": []}]},
        {"required": True, "label": "Last Name", "fields": [{"name": "last_name", "type": "input_text", "values": []}]},
        {"required": True, "label": "Email", "fields": [{"name": "email", "type": "input_text", "values": []}]},
        {"required": required_phone, "label": "Phone", "fields": [{"name": "phone", "type": "input_text", "values": []}]},
        {"required": True, "label": "Resume/CV", "fields": [{"name": "resume", "type": "input_file", "values": []}, {"name": "resume_text", "type": "textarea", "values": []}]},
        {"required": False, "label": "Cover Letter", "fields": [{"name": "cover_letter", "type": "input_file", "values": []}, {"name": "cover_letter_text", "type": "textarea", "values": []}]},
    ]


def questions_for(job_id):
    q = std()
    if job_id == "1002":
        q += [{"required": False, "label": "LinkedIn Profile", "fields": [{"name": "question_100", "type": "input_text", "values": []}]},
              {"required": True, "label": "Are you legally authorized to work in the United States?",
               "fields": [{"name": "question_101", "type": "multi_value_single_select", "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}]}]},
              {"required": True, "label": "Will you now or in the future require sponsorship for employment visa status?",
               "fields": [{"name": "question_102", "type": "multi_value_single_select", "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}]}]},
              {"required": True, "label": "How did you hear about this job?",
               "fields": [{"name": "question_103", "type": "multi_value_single_select", "values": [{"label": "Employee referral", "value": 7}, {"label": "Job board", "value": 8}, {"label": "Other", "value": 9}]}]},
              {"required": False, "label": "Personal website", "fields": [{"name": "question_104", "type": "input_text", "values": []}]}]
    if job_id == "1003":
        q += [{"required": True, "label": "What is your favorite color and why?", "fields": [{"name": "question_200", "type": "textarea", "values": []}]}]
    if job_id == "1006":
        q += [{"required": True, "label": "Are you willing to relocate?",
               "fields": [{"name": "question_300", "type": "multi_value_single_select", "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}]}]},
              {"required": True, "label": "What are your salary expectations?", "fields": [{"name": "question_301", "type": "input_text", "values": []}]},
              {"required": True, "label": "Which country do you currently live in?",
               "fields": [{"name": "question_302", "type": "multi_value_single_select", "values": [{"label": "United States of America", "value": 11}, {"label": "Canada", "value": 12}, {"label": "Other", "value": 13}]}]}]
    return q


def location_questions_for(job_id):
    if job_id != "1006":
        return []
    return [{"required": True, "label": "Location", "fields": [{"name": "location", "type": "input_text", "values": []}]},
            {"required": True, "label": "Latitude", "fields": [{"name": "latitude", "type": "input_hidden", "values": []}]},
            {"required": True, "label": "Longitude", "fields": [{"name": "longitude", "type": "input_hidden", "values": []}]}]


def check_extras(fields):
    """What Greenhouse's careers page sends without asking, checked the way a test needs: '' when fine, or why it would be refused."""
    geo = [k for k in ("location", "latitude", "longitude") if k in fields]
    if geo and len(geo) != 3:
        return "location, latitude and longitude go together (got %s)" % ", ".join(geo)
    if "country_short_name" in fields and not re.match(r"^[A-Z]{2}$", fields["country_short_name"]):
        return "country_short_name must be a two-letter code"
    emp = {k[len("employments[0]"):]: v for k, v in fields.items() if k.startswith("employments[")}
    if emp:
        need = ["[company_name]", "[title]", "[start_date][month]", "[start_date][year]"]
        ended = "[end_date][month]" in emp and "[end_date][year]" in emp
        if any(not emp.get(k) for k in need) or not (ended or emp.get("[current]") == "true") or (ended and emp.get("[current]")):
            return "an employment needs company_name, title, start_date and either end_date or current"
    return ""


def employments(fields):
    emp = {k[len("employments[0]"):]: v for k, v in fields.items() if k.startswith("employments[0]")}
    return [emp] if emp else []


def parse_multipart(ctype, body):
    msg = email.message_from_bytes(b"Content-Type: " + ctype.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + body, policy=email.policy.default)
    fields, files = {}, {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        fn = part.get_filename()
        if fn:
            files[name] = {"filename": fn, "type": part.get_content_type(), "bytes": len(part.get_payload(decode=True) or b"")}
        else:
            fields[name] = part.get_content()
    return fields, files


class H(http.server.BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        parts = u.path.strip("/").split("/")
        if u.path == "/__received":
            return self._json(200, RECEIVED)
        if u.path == "/__reset":
            RECEIVED.clear()
            return self._json(200, {"ok": True})
        if len(parts) == 3 and parts[0] == "postings" and parts[2] == "configuration":       # SmartRecruiters: a posting's configuration
            if self.headers.get("X-SmartToken") != SR_KEY:
                return self._json(401, {"id": "e1", "code": "INVALID_API_KEY_ERROR", "message": "Authentication data missing"})
            cfg = sr_config(parts[1])
            if cfg is None:
                return self._json(404, {"id": "e2", "code": "RESOURCE_NOT_FOUND_ERROR", "message": "Posting not found"})
            return self._json(200, cfg)
        if len(parts) == 5 and parts[:2] == ["v1", "boards"] and parts[3] == "jobs":
            job_id = parts[4]
            if job_id == "1004":
                return self._json(404, {"error": "Job not found"})
            return self._json(200, {"id": int(job_id), "title": "Test job", "questions": questions_for(job_id), "location_questions": location_questions_for(job_id),
                                    "compliance": [], "demographic_questions": {}})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        parts = u.path.strip("/").split("/")
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        ctype = self.headers.get("Content-Type") or ""
        if len(parts) == 5 and parts[:2] == ["v1", "boards"] and parts[3] == "jobs":
            want = "Basic " + base64.b64encode((GH_KEY + ":").encode()).decode()
            if self.headers.get("Authorization") != want:
                return self._json(401, {"error": "Invalid or missing API key"})
            if parts[4] == "1005":
                return self._json(500, {"error": "The employer's system is having a problem"})
            fields, files = parse_multipart(ctype, body)
            if not fields.get("first_name") or not fields.get("email"):
                return self._json(422, {"error": "first_name and email are required"})
            why = check_extras(fields)
            if why:
                return self._json(422, {"error": why})
            RECEIVED.append({"system": "greenhouse", "board": parts[2], "job": parts[4], "fields": fields, "files": files, "employments": employments(fields)})
            return self._json(200, {"success": "Application submitted"})
        if len(parts) == 4 and parts[:2] == ["v0", "postings"]:
            q = urllib.parse.parse_qs(u.query)
            if (q.get("key") or [""])[0] != LEVER_KEY:
                return self._json(401, {"ok": False, "error": "Unauthorized"})
            if parts[3] == "slow":
                return self._json(429, {"ok": False, "error": "Too many requests"})
            fields, files = parse_multipart(ctype, body)
            if not fields.get("name") or "@" not in fields.get("email", ""):
                return self._json(400, {"ok": False, "error": "Missing name or email"})
            RECEIVED.append({"system": "lever", "site": parts[2], "posting": parts[3], "fields": fields, "files": files})
            return self._json(200, {"ok": True, "applicationId": "app-%d" % len(RECEIVED)})
        if u.path in ("/jobPosting.info", "/applicationForm.submit"):                         # Ashby
            auth = self.headers.get("Authorization") or ""
            keys = {"Basic " + base64.b64encode((k + ":").encode()).decode(): k for k in (ASHBY_KEY, ASHBY_READONLY)}
            if auth not in keys:
                return self._json(401, {"success": False, "errorInfo": {"code": "invalid_api_key", "message": "Invalid API key"}})
            if u.path == "/jobPosting.info":
                if not ctype.startswith("application/json"):
                    return self._json(200, {"success": False, "errors": ["the body must be JSON"]})
                pid = (json.loads(body or b"{}") or {}).get("jobPostingId") or ""
                form = ashby_form(pid)
                if not form:
                    return self._json(200, {"success": False, "errors": ["job_posting_not_found"]})
                return self._json(200, {"success": True, "results": dict(form, id=pid, descriptionPlain="A long posting text.")})
            if keys[auth] == ASHBY_READONLY:
                return self._json(403, {"success": False, "errorInfo": {"code": "missing_endpoint_permission", "message": "The key lacks candidatesWrite"}})
            if not ctype.startswith("multipart/form-data"):                     # Ashby: requests that are not multipart do not work here
                return self._json(200, {"success": False, "errors": ["Content-Type must be multipart/form-data"]})
            fields, files = parse_multipart(ctype, body)
            pid = fields.get("jobPostingId") or ""
            form = ashby_form(pid)
            if not form:
                return self._json(200, {"success": False, "errors": ["job_posting_not_found"]})
            if pid.startswith("8888"):
                return self._json(429, {"success": False, "errors": ["rate_limit_exceeded"]})
            if pid.startswith("5555"):
                return self._json(500, HOSTILE)
            if pid.startswith("4444"):
                return self._json(200, {"success": False, "errors": ["invalid_input: the employer's system refused this form"]})
            try:
                sub = json.loads(fields.get("applicationForm") or "")["fieldSubmissions"]
                assert isinstance(sub, list)
            except Exception:
                return self._json(200, {"success": False, "errors": ["applicationForm must be a JSON string with fieldSubmissions"]})
            errs, got = ashby_check(form, sub, files)
            if errs:
                return self._json(200, {"success": False, "errors": errs})
            RECEIVED.append({"system": "ashby", "posting": pid, "values": got, "files": files, "utm": fields.get("utmData")})
            res = {"submittedFormInstance": {"id": "sfi-%d" % len(RECEIVED), "formDefinition": form["applicationFormDefinition"], "submittedValues": got}}
            if pid.startswith("6666"):
                return self._json(200, {"success": True, "blocked": True, "results": dict(res, formMessages={"blockMessageForCandidateHtml": "<p>Limit reached</p>"})})
            return self._json(200, {"success": True, "results": res})
        if len(parts) == 3 and parts[0] == "postings" and parts[2] == "candidates":           # SmartRecruiters: a new application
            if self.headers.get("X-SmartToken") != SR_KEY:
                return self._json(401, {"id": "e1", "code": "INVALID_API_KEY_ERROR", "message": "Authentication data missing"})
            cfg = sr_config(parts[1])
            if cfg is None:
                return self._json(404, {"id": "e2", "code": "RESOURCE_NOT_FOUND_ERROR", "message": "Posting not found"})
            if parts[1].endswith("0004"):
                return self._json(429, {"id": "e3", "code": "TRAFFIC_LOCKED", "message": "Too many requests"})
            if parts[1].endswith("0005"):
                return self._json(500, HOSTILE)
            if not ctype.startswith("application/json"):
                return self._json(400, {"id": "e4", "code": "INVALID_REQUEST", "message": "The body must be JSON"})
            try:
                cand = json.loads(body)
                assert isinstance(cand, dict)
            except Exception:
                return self._json(400, {"id": "e4", "code": "INVALID_REQUEST", "message": "The body must be JSON"})
            errs, answered = sr_check(cfg, cand)
            if errs:
                return self._json(400, {"id": "e5", "code": "DATA_VALIDATION_ERROR", "message": "; ".join(errs)})
            if cand.get("resume"):
                cand["resume"] = dict(cand["resume"], fileContent="(%d bytes)" % len(base64.b64decode(cand["resume"]["fileContent"])))
            RECEIVED.append({"system": "smartrecruiters", "posting": parts[1], "body": cand, "answered": answered})
            return self._json(200, {"id": "cand-%d" % len(RECEIVED), "createdOn": "2026-10-17T12:00:00Z", "candidatePortalUrl": "https://example.org/portal"})
        return self._json(404, {"error": "not found"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
