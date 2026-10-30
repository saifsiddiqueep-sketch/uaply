"""What the app says about the resume file against what a swipe right really sends. For a PDF, a Word file and a text file, by email and
by webhook, with no file, with only a resume link, and for an employer that takes applications only on its own site (a hand-off), it
checks the bytes that reached the stand-in employer, the summary the server gives the app (uaply_api._resume_summary) and the resume
line of the receipt and the owner copy. It also checks the hiring-system rule (ats_api.resume_goes) and that the upload box and the
desktop preview no longer say the file is never sent. Nothing leaves this computer: a stand-in mail server and a stand-in employer system.
  python tools/test-resume-disclosure.py [smtp port]        (default 19401)"""
import base64
import email
import email.policy
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="uaply-resume-disclosure-")
os.environ["UAPLY_DATA_DIR"] = TMP
os.environ["UAPLY_CONFIG_JSON"] = "{}"
os.environ["UAPLY_ALLOW_LOCAL_WEBHOOK"] = "1"

import ats_api  # noqa: E402
import auth_api  # noqa: E402
import emails  # noqa: E402
import jobs_api  # noqa: E402
import uaply_api  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


# ---- a stand-in employer system (webhook) ----
class Employer(http.server.BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        Employer.calls.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}"))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Employer)
threading.Thread(target=srv.serve_forever, daemon=True).start()
HOOK = "http://127.0.0.1:%d/apply" % srv.server_address[1]

# ---- a stand-in mail server ----
mail_file = os.path.join(TMP, "mail.jsonl")
smtp_port = int(sys.argv[1]) if len(sys.argv) > 1 else 19401
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(smtp_port), mail_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)

with open(os.path.join(TMP, "uaply-partners.json"), "w", encoding="utf-8") as f:
    json.dump({"employers": [
        {"name": "Mail Co", "consent": "signed partner agreement 2026-10-12", "contact": "hr@mailco.example", "url": "https://mailco.example/jobs",
         "jobs": [{"role": "Analyst", "skills": ["SQL"], "blurb": "Analyze."}]},
        {"name": "Hook Co", "consent": "signed partner agreement 2026-10-12", "webhook": HOOK, "webhook_secret": "employer-secret-456", "url": "https://hook.example/careers",
         "jobs": [{"role": "Intern", "skills": ["Python"], "type": "internship", "blurb": "Build."}]}]}, f)

cfg = {"delivery": "live", "daily_limit": 100, "smtp": {"host": "127.0.0.1", "port": smtp_port, "starttls": False, "from_addr": "uaply@example.com"}}
uaply_api.config = lambda: cfg
uaply_api.init("resume-disclosure")
auth_api.init("resume-disclosure")
jobs = {j["co"]: j for j in jobs_api.partner_jobs()}

PDF = b"%PDF-1.4\n% Sam Rivera resume for tests\n%%EOF\n" + bytes(range(40))
DOCX = b"PK\x03\x04" + b"word/document.xml Sam Rivera resume for tests" + bytes(range(30))
TXT = "Sam Rivera\nData analyst. Python, SQL.\n".encode("utf-8")
KINDS = [("PDF", "Sam Rivera Resume.pdf", PDF, "application/pdf"),
         ("Word", "Sam Rivera Resume.docx", DOCX, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
         ("text", "Sam Rivera Resume.txt", TXT, "text/plain")]
n = [0]


def data_url(raw, mime):
    return "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode())


def apply(co, resume=None, link="", job=None):
    """One swipe right from a verified account, each with its own email so none is a duplicate. Returns (http, answer, record)."""
    n[0] += 1
    addr = "sam%d@example.com" % n[0]
    j = job or jobs[co]
    payload = {"consent": True, "confirm_real": True, "match": 80,
               "job": {"id": j["id"], "co": j["co"], "role": j["role"], "url": j.get("url") or "https://example.com/x", "loc": j.get("loc", ""), "contact": j.get("contact", "")},
               "profile": {"name": "Sam Rivera", "email": addr, "title": "Analyst", "skills": ["SQL"], "ext": {"resume": link} if link else {}}}
    if resume:
        payload["resume"] = resume
    code, out = uaply_api.submit(payload, {"id": n[0], "email": addr, "emailVerified": True})
    return code, out, uaply_api.APPS[-1], addr


def mails_to(addr):
    time.sleep(0.8)
    got = [json.loads(x) for x in open(mail_file, encoding="utf-8") if x.strip()]
    return [email.message_from_string(m["raw"], policy=email.policy.default) for m in got if addr in m["to"]]


def receipt_line(rec, owner=False):
    """The resume line of the receipt (or the owner copy) for this record, built the way the server builds it."""
    ctx = uaply_api._mail_ctx(cfg, rec, rec.get("note", ""), "x@example.com")
    _, text, _ = (emails.owner_copy if owner else emails.applicant_receipt)(ctx)
    m = re.search(r"Resume file: (.*)", text)
    return m.group(1).strip() if m else ""


# 1. PDF, Word and text files by email: the bytes the employer receives, the summary the app shows, the receipt
for label, name, raw, mime in KINDS:
    open(mail_file, "w").close()
    code, out, rec, addr = apply("Mail Co", {"name": name, "data": data_url(raw, mime)})
    msgs = mails_to("hr@mailco.example")
    atts = [a for m in msgs for a in m.iter_attachments()]
    t("%s by email: sent" % label, (code, out["status"], rec["channels"]), (200, "sent", ["email"]))
    t("%s by email: the employer gets exactly this file, byte for byte" % label,
      [(a.get_filename(), a.get_content_type(), a.get_payload(decode=True) == raw) for a in atts], [(name, mime, True)])
    t("%s by email: the app is told the file went by email" % label, out.get("resume"),
      {"name": name, "size": len(raw), "type": mime, "sent_with": ["email"], "unsure_with": [], "link_with": [], "handoff": False})
    t("%s by email: the receipt says it was sent to the employer" % label, receipt_line(rec), "%s (sent to Mail Co with the application)" % name)
    t("%s by email: the owner copy says the same, and that the copy has no file" % label, receipt_line(rec, owner=True),
      "%s (sent to Mail Co with the application; not attached to this copy)" % name)
    t("%s by email: the record keeps the name and size, never the file" % label, ("data" in rec["resume"], base64.b64encode(raw).decode()[:20] in json.dumps(rec)), (False, False))

# 2. the same three by webhook: the file is in the signed JSON the employer's system receives
for label, name, raw, mime in KINDS:
    Employer.calls.clear()
    code, out, rec, addr = apply("Hook Co", {"name": name, "data": data_url(raw, mime)})
    body = Employer.calls[0] if Employer.calls else {}
    got = body.get("resume") or {}
    t("%s by webhook: the employer's system gets exactly this file" % label,
      (got.get("name"), got.get("type"), base64.b64decode(got.get("content_base64") or "") == raw), (name, mime, True))
    t("%s by webhook: the app is told the file went by webhook" % label, ((out.get("resume") or {}).get("sent_with"), out["status"]), (["webhook"], "sent"))

# 3. no file: nothing is attached, the app is told nothing about a file, and the email has no resume file line
open(mail_file, "w").close()
code, out, rec, addr = apply("Mail Co")
msgs = mails_to("hr@mailco.example")
body = msgs[0].get_body(preferencelist=("plain",)).get_content() if msgs else ""
t("no file: sent with no attachment", (out["status"], [a.get_filename() for m in msgs for a in m.iter_attachments()]), ("sent", []))
t("no file: the answer carries no resume summary", "resume" in out, False)
t("no file: neither the email nor the receipt mentions a resume file", ("Resume file" in body, receipt_line(rec)), (False, ""))

# 4. only a resume link: the link is in the email, no file is attached
open(mail_file, "w").close()
code, out, rec, addr = apply("Mail Co", link="https://drive.example.com/sam-resume")
msgs = mails_to("hr@mailco.example")
body = msgs[0].get_body(preferencelist=("plain",)).get_content() if msgs else ""
t("resume link only: the link is in what the employer reads", "Resume: https://drive.example.com/sam-resume" in body, True)
t("resume link only: nothing attached, no file line", ([a.get_filename() for m in msgs for a in m.iter_attachments()], "Resume file" in body, "resume" in out), ([], False, False))

# 5. an employer that takes applications only on its own site (a hand-off): nothing goes to it, and every message says so
open(mail_file, "w").close()
Employer.calls.clear()
gone = {"id": 4343434, "co": "Own Site Co", "role": "Data Intern", "url": "https://boards.greenhouse.io/ownsite/jobs/1"}
code, out, rec, addr = apply("", {"name": "Sam Rivera Resume.pdf", "data": data_url(PDF, "application/pdf")}, job=gone)
t("hand-off: nothing was sent to anyone", (out["status"], rec["channels"], len(Employer.calls), mails_to("ownsite")), ("handoff", [], 0, []))
t("hand-off: the app is told the file was not sent and the person uploads it there", ((out.get("resume") or {}).get("handoff"), (out.get("resume") or {}).get("sent_with")), (True, None))
t("hand-off: the receipt says to upload it on the employer's form", receipt_line(rec), "Sam Rivera Resume.pdf (upload it on Own Site Co's form)")
t("hand-off: the owner copy says the applicant uploads it", receipt_line(rec, owner=True), "Sam Rivera Resume.pdf (the applicant uploads it on Own Site Co's form)")

# 6. test mode: the simulated application includes the file, and says so
cfg["delivery"] = "test"
code, out, rec, addr = apply("Mail Co", {"name": "Sam Rivera Resume.pdf", "data": data_url(PDF, "application/pdf")})
t("test mode: the simulated email carries the file, and the app is told", (out["status"], (out.get("resume") or {}).get("sent_with")), ("delivered_test", ["email (simulated)"]))
t("test mode: the receipt says it is in the test application", receipt_line(rec), "Sam Rivera Resume.pdf (included in the test application)")
cfg["delivery"] = "live"

# 7. hiring systems: which ones carry the file itself (what the app and the receipt then say)
t("Workable takes a PDF or Word file", (ats_api.resume_goes("workable", None, "application/pdf"), ats_api.resume_goes("workable", None, KINDS[1][3])), (True, True))
t("Workable does not take a text file", ats_api.resume_goes("workable", None, "text/plain"), False)
t("Lever and SmartRecruiters always take the file", (ats_api.resume_goes("lever", None, "text/plain"), ats_api.resume_goes("smartrecruiters", None, "application/pdf")), (True, True))
t("Greenhouse takes it only into the form's resume question",
  (ats_api.resume_goes("greenhouse", {"files": [("resume", "a.pdf", "application/pdf", b"x")]}, "application/pdf"), ats_api.resume_goes("greenhouse", {"files": []}, "application/pdf")), (True, False))
t("Ashby takes it only into the form's resume question",
  (ats_api.resume_goes("ashby", {"resume": ["_systemfield_resume"]}, "application/pdf"), ats_api.resume_goes("ashby", {"resume": []}, "application/pdf")), (True, False))
t("Greenhouse or Ashby with no form read (an Ashby form in test mode): not known, never assumed",
  (ats_api.resume_goes("ashby", None, "application/pdf"), ats_api.resume_goes("greenhouse", None, "application/pdf")), (None, None))
L = "https://drive.example.com/cv"
t("the resume link: Lever always; Workable and SmartRecruiters when the file does not go; elsewhere only as a form's answer",
  (ats_api.link_goes("lever", None, True, L), ats_api.link_goes("workable", None, False, L), ats_api.link_goes("workable", {"values": []}, True, L),
   ats_api.link_goes("greenhouse", {"fields": [("question_9", L)]}, False, L), ats_api.link_goes("ashby", {"values": [("q", "x")]}, False, L),
   ats_api.link_goes("ashby", None, None, L), ats_api.link_goes("lever", None, True, "")), (True, True, False, True, False, None, False))
wk = {"status": "sent", "channels": ["hiring system (workable)"], "resume": {"name": "cv.txt", "size": 40, "type": "text/plain"}, "candidate": {"ext": {"resume": L}}}
wk["resume_to"] = uaply_api._resume_to(wk, None, "workable")
t("a text file sent into Workable is reported as not sent, and its link as sent", (uaply_api._resume_summary(wk)["sent_with"], uaply_api._resume_summary(wk)["link_with"]), ([], ["hiring system (workable)"]))
wk_rows = emails._resume_rows([("Resume file", "cv.txt (attached)")], "sent", "Work Co", resume=uaply_api._resume_summary(wk))
t("...and the receipt says so instead of claiming it went along", wk_rows, [("Resume file", "cv.txt (not sent: Work Co's form does not take this file; your resume link went instead)")])
gh = {"status": "sent", "channels": ["hiring system (greenhouse)"], "resume": {"name": "cv.pdf", "size": 40, "type": "application/pdf"}, "candidate": {"ext": {"resume": L}}}
gh["resume_to"] = uaply_api._resume_to(gh, {"files": [], "fields": [("first_name", "Sam")]}, "greenhouse")
t("a Greenhouse form with no resume question and nothing that takes the link: the receipt names no link",
  emails._resume_rows([("Resume file", "cv.pdf (attached)")], "sent", "GH Co", resume=uaply_api._resume_summary(gh)), [("Resume file", "cv.pdf (not sent: GH Co's form does not take this file)")])
t("...and its link row says the link was not sent, instead of listing it under what was shared",
  emails._resume_rows([("Resume", L)], "sent", "GH Co", resume=uaply_api._resume_summary(gh), link=uaply_api._link_summary(gh)),
  [("Resume", L + " (not sent: GH Co's form has no place for it)")])
lo = {"status": "sent", "channels": ["hiring system (greenhouse)"], "candidate": {"ext": {"resume": L}}}
lo["resume_to"] = uaply_api._resume_to(lo, {"files": [], "fields": [("first_name", "Sam")]}, "greenhouse")
t("only a link into that form: no file summary, and the link summary says it did not go", (uaply_api._resume_summary(lo), uaply_api._link_summary(lo)),
  (None, {"link_with": [], "unsure_with": []}))
lt = {"status": "delivered_test", "channels": ["hiring system (simulated)"], "candidate": {"ext": {"resume": L}}}
lt["resume_to"] = uaply_api._resume_to(lt, None, "ashby")
t("only a link, test mode, a form that was not read: the link row says that is not known",
  emails._resume_rows([("Resume", L)], "delivered_test", "Ash Co", link=uaply_api._link_summary(lt)),
  [("Resume", L + " (not known: UAply did not read Ash Co's form in test mode, so it cannot tell whether the link would go)")])
le = {"status": "sent", "channels": ["email"], "candidate": {"ext": {"resume": L}}}
le["resume_to"] = uaply_api._resume_to(le, None, "")
t("only a link, by email: the link went, and the row is left as it is", emails._resume_rows([("Resume", L)], "sent", "Mail Co", link=uaply_api._link_summary(le)), [("Resume", L)])
old = {"status": "sent", "channels": ["email"], "resume": {"name": "cv.pdf", "size": 40, "type": "application/pdf"}}
t("a record made before this was kept still reads as sent with the application", emails._resume_rows([("Resume file", "cv.pdf (attached)")], "sent", "Co", resume=uaply_api._resume_summary(old)),
  [("Resume file", "cv.pdf (sent to Co with the application)")])

# 8. the words in the app: no sentence says the resume file is never sent, and both places use the one shared sentence
nav = open(os.path.join(ROOT, "shared", "uaply-nav.js"), encoding="utf-8").read()
t("no sentence says the resume file is never sent or stays on the device only",
  re.findall(r"[^.'\"]*(?:never sent|never shared|not sent)[^.'\"]*resume file[^.'\"]*|resume file \(it stays on this device", nav, re.I), [])
t("the upload box and the desktop preview both use resumeShare()", (nav.count('getElementById("resShare").textContent=resumeShare()'), nav.count("E(resumeShare())")), (1, 1))
t("the preview takes the resume link as the swipe does (resumeLinkOf, the saved value), never the box as typed",
  ("rf=resumeFile(),rl=resumeLinkOf();" in nav, 'fv("pResUrl")' in nav), (True, False))
t("the swipe, the upload box and the preview read the same file (resumeFile)", ("w.__uaplyResume=resumeFile;" in nav, "rf=resumeFile()" in nav), (True, True))
t("with only a link, the box does not promise that employers get it: a hiring system's form takes it only where it has a place for it",
  ("employers get your resume link instead" in nav, "to an employer's hiring system when its form has a place for it" in nav), (False, True))
t("street address and voluntary answers are still listed as never sent", "Never sent: your street address and your voluntary answers." in nav, True)

proc.terminate()
srv.shutdown()
print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
