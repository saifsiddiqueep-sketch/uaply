"""Tests how an application reaches an employer who opted in: email with the resume attached, a signed webhook (the Indeed Apply model),
retries, failures, redirects, duplicates, test redirects, and that nothing reaches an employer who did not opt in.
  python tools/test-delivery.py"""
import base64
import email
import email.policy
import hashlib
import hmac
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="uaply-delivery-")
os.environ["UAPLY_DATA_DIR"] = TMP
os.environ["UAPLY_CONFIG_JSON"] = "{}"
os.environ["UAPLY_ALLOW_LOCAL_WEBHOOK"] = "1"

import auth_api  # noqa: E402
import jobs_api  # noqa: E402
import uaply_api  # noqa: E402

R = []
SECRET = "employer-secret-123"


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


# ---- a stand-in employer system ----
class Employer(http.server.BaseHTTPRequestHandler):
    calls = []
    script = []          # status codes to answer with, in order; the last one repeats

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        Employer.calls.append({"headers": {k.lower(): v for k, v in self.headers.items()}, "body": body, "path": self.path})
        code = Employer.script[min(len(Employer.calls) - 1, len(Employer.script) - 1)] if Employer.script else 200
        self.send_response(code)
        if code in (301, 302, 307):
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Employer)
threading.Thread(target=srv.serve_forever, daemon=True).start()
HOOK = "http://127.0.0.1:%d/apply" % srv.server_address[1]

# ---- a stand-in mail server ----
mail_file = os.path.join(TMP, "mail.jsonl")
smtp_port = int(sys.argv[1]) if len(sys.argv) > 1 else 2529           # another port can be given, so two test runs never collide
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(smtp_port), mail_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)

PDF = b"%PDF-1.4\n% a tiny test resume \x00\x01\x02 for Sam Rivera\n%%EOF\n" + os.urandom(64)
RESUME = {"name": "Sam Rivera Resume.pdf", "data": "data:application/pdf;base64," + base64.b64encode(PDF).decode()}

with open(os.path.join(TMP, "uaply-partners.json"), "w", encoding="utf-8") as f:
    json.dump({"employers": [
        {"name": "Hook Only Co", "consent": "signed partner agreement 2026-10-12", "webhook": HOOK, "webhook_secret": SECRET, "url": "https://hook.example/careers",
         "jobs": [{"role": "Software Intern", "skills": ["Python"], "type": "internship", "blurb": "Build things."}]},
        {"name": "Both Co", "consent": "signed partner agreement 2026-10-12", "contact": "jobs@both.example", "webhook": HOOK, "webhook_secret": SECRET,
         "jobs": [{"role": "Data Co-op", "skills": ["SQL"], "type": "coop", "blurb": "Analyze data."}]},
        {"name": "Email Only Co", "consent": "signed partner agreement 2026-10-12", "contact": "hr@emailonly.example", "url": "https://emailonly.example/jobs",
         "jobs": [{"role": "Part-time Tutor", "skills": ["Math"], "type": "parttime", "blurb": "Teach."}]},
        {"name": "Unsigned Hook Co", "consent": "signed 2026-10-12", "webhook": HOOK, "url": "https://nosecret.example",
         "jobs": [{"role": "Support Agent", "skills": ["Communication"], "blurb": "Help people."}]}]}, f)

cfg = {"delivery": "live", "daily_limit": 50, "smtp": {"host": "127.0.0.1", "port": smtp_port, "starttls": False, "from_addr": "uaply@example.com"}}
uaply_api.config = lambda: cfg
uaply_api.init("delivery")
auth_api.init("delivery")

jobs = {j["co"]: j for j in jobs_api.partner_jobs()}
t("four partner jobs loaded", sorted(jobs), ["Both Co", "Email Only Co", "Hook Only Co", "Unsigned Hook Co"])
t("a webhook-only employer counts as opted in (direct)", jobs["Hook Only Co"]["apply"], "direct")
t("the webhook secret and address never appear in what browsers receive", SECRET not in json.dumps(jobs_api.partner_jobs()) and HOOK not in json.dumps(jobs_api.partner_jobs()), True)


def apply(co, email_addr="sam@example.com", resume=RESUME, **cfg_over):
    j = jobs[co]
    cfg.update(cfg_over)
    payload = {"consent": True, "confirm_real": True, "match": 90,
               "job": {"id": j["id"], "co": j["co"], "role": j["role"], "url": j["url"] or "https://example.com/x", "source": j["source"], "loc": j["loc"], "contact": j.get("contact", "")},
               "profile": {"name": "Sam Rivera", "email": email_addr, "title": "Software Intern", "years": 1, "skills": ["Python", "SQL"], "loc": "Philadelphia, PA", "edu": "Bachelor",
                           "ext": {"phone": "+1 215 555 0100", "school": "Drexel University", "major": "Computing & Security Technology", "grad": "2026-06",
                                   "linkedin": "https://linkedin.com/in/sam"}}}
    if resume:
        payload["resume"] = resume
    return uaply_api.submit(payload, {"id": 1, "email": email_addr, "emailVerified": True})


def reset():
    Employer.calls.clear()
    Employer.script = []


# 1. webhook-only employer, with the resume
reset()
code, out = apply("Hook Only Co")
t("webhook-only: the application is sent", (code, out["status"]), (200, "sent"))
t("webhook-only: the employer's system received exactly one call", len(Employer.calls), 1)
c = Employer.calls[0] if Employer.calls else {"headers": {}, "body": b"{}"}
body = json.loads(c["body"])
ts = c["headers"].get("x-uaply-timestamp", "")
want_sig = "sha256=" + hmac.new(SECRET.encode(), (ts + ".").encode() + c["body"], hashlib.sha256).hexdigest()
t("webhook: the signature is valid", c["headers"].get("x-uaply-signature"), want_sig)
t("webhook: it carries a delivery id and timestamp", bool(c["headers"].get("x-uaply-delivery")) and ts.isdigit(), True)
t("webhook: applicant details arrive", (body["applicant"]["name"], body["applicant"]["email"], body["applicant"]["phone"], body["applicant"]["skills"]),
  ("Sam Rivera", "sam@example.com", "+1 215 555 0100", ["Python", "SQL"]))
t("webhook: education and links arrive", (body["applicant"]["education"]["school"], body["applicant"]["links"]["linkedin"]), ("Drexel University", "https://linkedin.com/in/sam"))
t("webhook: the job arrives", (body["job"]["title"], body["job"]["company"], body["job"]["type"]), ("Software Intern", "Hook Only Co", "internship"))
t("webhook: the resume file arrives byte for byte", base64.b64decode(body["resume"]["content_base64"]) == PDF and body["resume"]["name"] == "Sam Rivera Resume.pdf", True)
t("the record keeps the resume name and size but not the file", (out.get("status"), "content_base64" in json.dumps(uaply_api.APPS[-1])), ("sent", False))
t("channels recorded", uaply_api.APPS[-1]["channels"], ["webhook"])

# 2. duplicate
reset()
code, out = apply("Hook Only Co")
t("the same person applying twice is a duplicate, nothing is sent again", (out["status"], len(Employer.calls)), ("duplicate", 0))
t("...and the answer says what happened the first time, so the Applied list can show it again", out.get("was"), "sent")

# 3. email and webhook together, with the resume attached to the email
reset()
open(mail_file, "w").close()
code, out = apply("Both Co")
time.sleep(1)
everything = [json.loads(x) for x in open(mail_file, encoding="utf-8") if x.strip()]
sent = [m for m in everything if m["to"] == ["jobs@both.example"]]               # what the employer received
confirmations = [m for m in everything if m["to"] == ["sam@example.com"]]       # what the applicant received
msg = email.message_from_string(sent[0]["raw"], policy=email.policy.default) if sent else None
t("both channels: sent", (code, out["status"], uaply_api.APPS[-1]["channels"]), (200, "sent", ["email", "webhook"]))
t("both channels: the employer got the email and the webhook call", (len(sent), len(Employer.calls)), (1, 1))
t("the verified applicant also got a confirmation email", len(confirmations), 1)
atts = [p for p in msg.iter_attachments()] if msg else []
t("the email carries the resume as a real attachment", (len(atts), atts[0].get_filename() if atts else None), (1, "Sam Rivera Resume.pdf"))
t("the attachment is the same file", atts[0].get_content() == PDF if atts else False, True)
t("the email body says the resume is attached", "Resume file: Sam Rivera Resume.pdf (attached)" in msg.get_body(preferencelist=("plain",)).get_content() if msg else False, True)

# 4. email only
reset()
open(mail_file, "w").close()
code, out = apply("Email Only Co", email_addr="alex@example.com", resume=None)
time.sleep(1)
t("email-only: sent by email, no webhook call", (out["status"], uaply_api.APPS[-1]["channels"], len(Employer.calls)), ("sent", ["email"], 0))

# 4b. a name that looks like an address must never become the address the employer's Reply goes to, and the sender is named UAply
reset()
open(mail_file, "w").close()
j = jobs["Email Only Co"]
hostile = {"consent": True, "confirm_real": True, "job": {"id": j["id"], "co": j["co"], "role": j["role"], "url": j["url"], "loc": j["loc"], "contact": j["contact"]},
           "profile": {"ext": {"phone": "215-555-0100"}, "name": "Sam <attacker@evil.example>", "email": "sam.h@example.com"}}
code, out = uaply_api.submit(hostile, {"id": 3, "email": "sam.h@example.com", "emailVerified": True})
time.sleep(1)
got = [email.message_from_string(json.loads(x)["raw"], policy=email.policy.default) for x in open(mail_file, encoding="utf-8") if x.strip()]
to_employer = [m for m in got if m["To"] == "hr@emailonly.example"]
rt = to_employer[0]["Reply-To"].addresses if to_employer else ()
t("a name shaped like an address: the employer's Reply still goes only to the verified email",
  (out["status"], [a.addr_spec for a in rt], [a.display_name for a in rt]), ("sent", ["sam.h@example.com"], ["Sam <attacker@evil.example>"]))
t("the sender shows as UAply even when only a bare address is set up", [m["From"].addresses[0].display_name for m in got], ["UAply"] * len(got))

# 4c. a resume file name with accents reaches the employer as the person named it (it used to arrive as "Jos_ Garc_a CV.pdf")
reset()
open(mail_file, "w").close()
accented = {"name": "José García CV.pdf", "data": RESUME["data"]}
code, out = apply("Email Only Co", email_addr="jose@example.com", resume=accented)
time.sleep(1)
got = [email.message_from_string(json.loads(x)["raw"], policy=email.policy.default) for x in open(mail_file, encoding="utf-8") if x.strip()]
atts = [a for m in got if m["To"] == "hr@emailonly.example" for a in m.iter_attachments()]
t("an accented resume file name is kept, with the right type", [(a.get_filename(), a.get_content_type()) for a in atts], [("José García CV.pdf", "application/pdf")])
code, out = apply("Email Only Co", email_addr="jose2@example.com", resume={"name": "../../etc/pass\"wd.pdf", "data": RESUME["data"]})
t("a file name with slashes or quotes is still made safe", uaply_api.APPS[-1]["resume"]["name"], ".._.._etc_pass_wd.pdf")

# 5. retries
reset()
Employer.script = [500, 500, 200]
real_sleep = time.sleep
time.sleep = lambda s: None
try:
    code, out = apply("Hook Only Co", email_addr="retry1@example.com")
finally:
    time.sleep = real_sleep
t("a failing employer system is retried and then succeeds", (out["status"], len(Employer.calls)), ("sent", 3))

reset()
Employer.script = [400]
code, out = apply("Hook Only Co", email_addr="no-retry@example.com")
t("a 400 answer is final: one try, reported as failed", (out["status"], len(Employer.calls), "webhook: HTTP 400" in out.get("error", "")), ("failed", 1, True))

# an application whose fields have the wrong type must be tolerated, never crash the handler (the fuzz test found skills sent as a number or a dictionary)
for label, skills in (("a dictionary", {"a": 1}), ("a number", 7), ("a boolean", True), ("text", "python")):
    shape = {"consent": True, "job": {"id": 1, "co": "Acme", "role": "Intern", "url": "https://acme.example/j"},
             "profile": {"name": "Pat Doe", "email": "shape@example.com", "skills": skills, "ext": "zzz"}, "resume": RESUME}
    try:
        code, out = uaply_api.submit(shape, None)
        crashed = False
    except Exception as e:
        code, out, crashed = 0, {"error": repr(e)}, True
    t("an application whose skills are %s is accepted without a crash" % label, (crashed, code), (False, 200))

# on a hosted server a visitor must never be shown an employer's or a mail server's raw error text (serve.py sets hide_errors there)
reset()
Employer.script = [400]
uaply_api.hide_errors = True
try:
    code, out = apply("Hook Only Co", email_addr="hidden-error@example.com")
finally:
    uaply_api.hide_errors = False
t("on a hosted server a failed send says a plain sentence, with no employer detail", (out["status"], out.get("error"), "HTTP 400" in out.get("error", "")),
  ("failed", "Your application to Hook Only Co could not be sent right now. Try again in a moment.", False))
with open(os.path.join(uaply_api.DATA, "applications.jsonl"), encoding="utf-8") as f:
    last = [json.loads(x) for x in f if x.strip()][-1]
t("the real reason is still kept in the owner's own record", "HTTP 400" in last.get("error", ""), True)

reset()
Employer.script = [302]
code, out = apply("Hook Only Co", email_addr="redirect@example.com")
t("a redirect is never followed and counts as a failure", out["status"], "failed")

reset()
Employer.script = [500]
time.sleep = lambda s: None
try:
    code, out = apply("Hook Only Co", email_addr="down@example.com")
finally:
    time.sleep = real_sleep
t("an employer system that stays down: three tries, then failed", (out["status"], len(Employer.calls)), ("failed", 3))

# an unexpected error while sending must end as "failed", never stay on "sending" (that blocked every retry as a duplicate)
reset()
real_post = uaply_api._post_webhook


def broken(*a, **k):
    raise KeyError("something nobody expected")
uaply_api._post_webhook = broken
try:
    code, out = apply("Hook Only Co", email_addr="crash@example.com")
    crashed = False
except Exception:
    code, out, crashed = 0, {}, True
uaply_api._post_webhook = real_post
t("an unexpected error while sending is reported as failed, not a crash", (crashed, out.get("status")), (False, "failed"))
code, out = apply("Hook Only Co", email_addr="crash@example.com")
t("...and trying again really sends it (not refused as a duplicate)", (out["status"], len(Employer.calls)), ("sent", 1))

# 6. no secret: still sent, but unsigned
reset()
code, out = apply("Unsigned Hook Co", email_addr="nosecret@example.com", resume=None)
t("with no secret the call is sent unsigned", (out["status"], "x-uaply-signature" in Employer.calls[0]["headers"]), ("sent", False))

# 7. a test redirect never reaches the employer's system
reset()
code, out = apply("Hook Only Co", email_addr="redir@example.com", test_recipient="owner@example.com")
cfg.pop("test_recipient", None)
t("a test redirect never calls the employer's webhook", (len(Employer.calls), out["status"]), (0, "sent"))

# 8. test mode never calls out
reset()
code, out = apply("Hook Only Co", email_addr="testmode@example.com", delivery="test")
cfg["delivery"] = "live"
# Hook Only Co gave no email address, so the live app would only call its webhook: test mode must say the same (it used to claim an email to a made-up address)
t("test mode simulates exactly the channels the live app would use and calls nothing", (out["status"], len(Employer.calls), uaply_api.APPS[-1]["channels"], out["to"]),
  ("delivered_test", 0, ["webhook (simulated)"], "Hook Only Co's own system (simulated)"))
code, out = apply("Both Co", email_addr="testmode@example.com", delivery="test")
cfg["delivery"] = "live"
t("test mode, an employer with email and a webhook: both simulated, to its real address", (out["status"], uaply_api.APPS[-1]["channels"], out["to"]),
  ("delivered_test", ["email (simulated)", "webhook (simulated)"], "jobs@both.example"))
code, out = apply("Email Only Co", email_addr="testmode@example.com", delivery="test")
cfg["delivery"] = "live"
t("test mode, an employer that takes email: email simulated", (out["status"], uaply_api.APPS[-1]["channels"], out["to"]), ("delivered_test", ["email (simulated)"], "hr@emailonly.example"))

# 9. resumes that are not real are refused
reset()
for label, bad in [("wrong content for a PDF", {"name": "x.pdf", "data": "data:application/pdf;base64," + base64.b64encode(b"this is not a pdf, it has no header").decode()}),
                   ("a program", {"name": "run.exe", "data": RESUME["data"]}),
                   ("over 1 MB", {"name": "big.pdf", "data": "data:application/pdf;base64," + base64.b64encode(b"%PDF" + os.urandom(1100000)).decode()}),
                   ("not base64", {"name": "x.pdf", "data": "data:application/pdf;base64,@@@@"})]:
    code, out = apply("Hook Only Co", email_addr="bad-%s@example.com" % label.split()[0], resume=bad)
    t("a resume that is %s is refused" % label, (code, len(Employer.calls)), (400, 0))

# 9b. a direct send needs a verified account whose email is the one on the application
reset()
jh = jobs["Hook Only Co"]
base_payload = {"consent": True, "confirm_real": True, "job": {"id": jh["id"], "co": jh["co"], "role": jh["role"], "url": "https://hook.example/careers", "loc": "", "contact": ""},
                "profile": {"ext": {"phone": "215-555-0100"}, "name": "Pat Doe", "email": "pat@example.com"}}
code, out = uaply_api.submit(base_payload, {"id": 7, "email": "pat@example.com", "emailVerified": False})
t("an unverified account cannot send directly to an employer", (code, out.get("code"), len(Employer.calls)), (403, "verify", 0))
code, out = uaply_api.submit(base_payload, None)
t("no account at all cannot send directly either, and is told to sign in first", (code, out.get("code"), len(Employer.calls), out.get("error", "").startswith("Sign in first")), (403, "signin", 0, True))
code, out = uaply_api.submit(base_payload, {"id": 7, "email": "someone.else@example.com", "emailVerified": True})
t("a verified account must use its own email on the application", (code, len(Employer.calls)), (400, 0))
code, out = uaply_api.submit(base_payload, {"id": 7, "email": "Pat@Example.com", "emailVerified": True})
t("a verified account with the matching email sends (case does not matter)", (code, out["status"], len(Employer.calls)), (200, "sent", 1))

# 10. an employer who did not opt in can never be sent anything
reset()
open(mail_file, "w").close()
fid = 123456789
with jobs_api._lock:
    jobs_api._cache[("greenhouse", "x", "X")] = {"at": time.time(), "status": "1 jobs", "jobs": [{"id": fid, "co": "Feed Co", "role": "Engineer", "contact": "recruiter@feed.example", "apply": "link"}]}
payload = {"consent": True, "confirm_real": True, "job": {"id": fid, "co": "Feed Co", "role": "Engineer", "url": "https://feed.example/j/1", "loc": "Austin, TX", "contact": "recruiter@feed.example"},
           "profile": {"ext": {"phone": "215-555-0100"}, "name": "Sam Rivera", "email": "sam@example.com"}, "resume": RESUME}
code, out = uaply_api.submit(payload, None)
time.sleep(0.5)
t("a feed job (employer never opted in) is a hand-off: nothing is emailed or posted", (out["status"], len(Employer.calls), len([x for x in open(mail_file) if x.strip()])), ("handoff", 0, 0))

# 11. a real posting that this server no longer lists (it left the employer's board): a hand-off in both modes, never "delivered"
gone = {"consent": True, "confirm_real": True, "job": {"id": 4242424, "co": "Vanished Co", "role": "Gone Intern", "url": "https://boards.greenhouse.io/vanished/jobs/1"},
        "profile": {"ext": {"phone": "215-555-0100"}, "name": "Sam Rivera", "email": "gone@example.com"}}
for mode in ("live", "test"):
    cfg["delivery"] = mode
    code, out = uaply_api.submit(dict(gone, profile=dict(gone["profile"], email="gone-%s@example.com" % mode)), None)
    t("%s mode: a posting no longer listed is a hand-off, sent to no one" % mode, (out["status"], out["to"]), ("handoff", ""))
cfg["delivery"] = "live"
code, out = uaply_api.submit({"consent": True, "job": {"id": 7, "co": "Example Co", "role": "Example", "url": "https://example.com/x"},
                              "profile": {"ext": {"phone": "215-555-0100"}, "name": "Sam Rivera", "email": "example@example.com"}}, None)
t("an example listing (small number) in live mode is still only a hand-off", out["status"], "handoff")

# 9c. the app's minimum to apply, on the server too (October 22): a phone number or a resume, else nothing is sent or recorded
reset()
n_apps = len(uaply_api.APPS)
bare = dict(base_payload, profile={"name": "Pat Doe", "email": "pat@example.com"})
code, out = uaply_api.submit(bare, {"id": 7, "email": "pat@example.com", "emailVerified": True})
t("no phone and no resume: refused with a plain sentence, nothing sent or recorded",
  (code, out.get("error"), len(Employer.calls), len(uaply_api.APPS) - n_apps), (400, uaply_api.NEEDS_PHONE_OR_RESUME, 0, 0))
code, out = uaply_api.submit(dict(bare, profile=dict(bare["profile"], ext={"phone": "12"})), None)
t("...a phone that is not a phone number counts as none", (code, out.get("error")), (400, uaply_api.NEEDS_PHONE_OR_RESUME))
code, out = uaply_api.submit(dict(bare, profile=dict(bare["profile"], ext={"resume": "https://example.com/pat-cv.pdf"})), None)
t("a resume link is enough", code, 200)
code, out = uaply_api.submit(dict(bare, resume=RESUME), None)
t("a resume file is enough", code, 200)
code, out = uaply_api.submit(dict(bare, plan_only=True), None)
t("a plan (reading the form, nothing sent) may still be asked without them", code, 200)

proc.terminate()
srv.shutdown()
print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
