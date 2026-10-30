"""What the app and the receipt say about the resume file against what really reached each hiring system, end to end through submit() and the
stand-in hiring systems (tools/mock-ats.py): Greenhouse and Ashby with and without a resume question, Lever, SmartRecruiters, and Workable with a
PDF and with a text file it does not take. For each it checks the bytes the stand-in received, the "resume" summary the server gives the app
(sent_with, unsure_with, link_with), the resume line of the receipt and the owner copy, and the message the app shows (resumeNote in
shared/uaply-live.js, run in node on the server's answer). Also: the resume link is named only when a send really carried it, the receipt's
"Resume:" (link) row says the link was not sent when no channel carried it (with or without a file), and test mode for an Ashby employer
(whose form test mode never reads) or a Greenhouse posting whose form could not be read says it cannot tell instead of claiming the file is in
the test application.
Nothing leaves this computer.
  python tools/test-resume-disclosure-ats.py [stand-in port]        (default 19403)"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="uaply-resume-ats-")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 19403
os.environ.update(UAPLY_DATA_DIR=TMP, UAPLY_CONFIG_JSON="{}")
for k in ("GREENHOUSE", "LEVER", "ASHBY", "SMARTRECRUITERS", "WORKABLE"):
    os.environ["UAPLY_ATS_BASE_" + k] = "http://127.0.0.1:%d" % PORT

import emails  # noqa: E402
import jobs_api  # noqa: E402
import uaply_api  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


CONSENT = "signed partner agreement 2026-10-12"
SYSTEMS = [("GH Files", {"kind": "greenhouse", "board": "acme", "api_key": "gh-secret-key-123"}, "1001"),
           ("GH Website", {"kind": "greenhouse", "board": "acme", "api_key": "gh-secret-key-123"}, "1010"),
           ("GH Bare", {"kind": "greenhouse", "board": "acme", "api_key": "gh-secret-key-123"}, "1011"),
           ("GH Gone", {"kind": "greenhouse", "board": "acme", "api_key": "gh-secret-key-123"}, "1004"),
           ("Lever Co", {"kind": "lever", "board": "acme", "api_key": "lever-key-456"}, "lever-posting-1"),
           ("Ashby Files", {"kind": "ashby", "board": "acmeashby", "api_key": "ashby-key-789"}, "11111111-1111-4111-8111-111111111111"),
           ("Ashby Bare", {"kind": "ashby", "board": "acmeashby", "api_key": "ashby-key-789"}, "13131313-1313-4131-8131-131313131313"),
           ("SR Co", {"kind": "smartrecruiters", "board": "CityofPhiladelphia", "api_key": "sr-smarttoken-012"}, "aaaaaaaa-0000-4000-8000-000000000001"),
           ("Works Co", {"kind": "workable", "board": "acmeworks", "api_key": "wk-token-345"}, "WK00000001")]
with open(os.path.join(TMP, "uaply-partners.json"), "w", encoding="utf-8") as f:
    json.dump({"employers": [{"name": co, "consent": CONSENT, "url": "https://%s.example/careers" % co.lower().replace(" ", ""), "ats": ats,
                              "jobs": [{"role": "Data Analyst", "skills": ["SQL"], "ats_job_id": jid, "loc": "Remote (US)", "mode": "remote"}]}
                             for co, ats, jid in SYSTEMS]}, f)
mock = subprocess.Popen([sys.executable, os.path.join(HERE, "mock-ats.py"), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
cfg = {"delivery": "live", "smtp": {}, "daily_limit": 100}
uaply_api.config = lambda: cfg
uaply_api.init("resume-ats")
JOBS = {j["co"]: j for j in jobs_api.partner_jobs()}

PDF = b"%PDF-1.4\n% Sam Rivera resume for tests\n%%EOF\n" + bytes(range(40))
TXT = "Sam Rivera\nData analyst. Python, SQL.\n".encode("utf-8")
LINK = "https://drive.example.com/sam-resume"
n = [0]


def received():
    return json.loads(urllib.request.urlopen("http://127.0.0.1:%d/__received" % PORT).read())


def apply(co, raw=PDF, mime="application/pdf", name="Sam Rivera Resume.pdf", link=LINK):
    """One swipe right from a verified account into this employer's hiring system. Returns (answer, record, what the stand-in received)."""
    n[0] += 1
    addr = "sam.ats%d@example.com" % n[0]
    j = JOBS[co]
    ext = {"phone": "+1 555 123 4567", "auth": "citizen", "sponsor": "no", "linkedin": "https://www.linkedin.com/in/samrivera"}
    if link:
        ext["resume"] = link
    p = {"consent": True, "confirm_real": True, "match": 80, "note": "",
         "job": {"id": j["id"], "co": j["co"], "role": j["role"], "url": j.get("url") or "https://example.com/x", "loc": j.get("loc", "")},
         "profile": {"name": "Sam Rivera", "email": addr, "title": "Analyst", "years": 1, "skills": ["SQL"], "loc": "Austin, TX", "edu": "Bachelor", "ext": ext},
         "resume": {"name": name, "data": "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode())} if raw else None}
    before = len(received())
    code, out = uaply_api.submit(p, {"id": n[0], "email": addr, "emailVerified": True})
    return out, uaply_api.APPS[-1], received()[before:]


def receipt_line(rec, owner=False, label="Resume file"):
    ctx = uaply_api._mail_ctx(cfg, rec, rec.get("note", ""), "x@example.com")
    _, text, _ = (emails.owner_copy if owner else emails.applicant_receipt)(ctx)
    m = re.search(r"^\s*%s: (.*)$" % re.escape(label), text, re.M)
    return m.group(1).strip() if m else ""


def link_line(rec, owner=False):
    """The receipt's "Resume:" row (the resume link) under what was shared."""
    return receipt_line(rec, owner, "Resume")


# the app's own message, from the same function the app runs (shared/uaply-live.js resumeNote), on the server's answer
live = open(os.path.join(ROOT, "shared", "uaply-live.js"), encoding="utf-8").read()
a = live.index("function resumeNote(j,co){")
RESUME_NOTE = live[a:live.index("\n  }\n", a) + 4]
NOTES = []


def note_later(label, out, co):
    NOTES.append((label, {"status": out["status"], "resume": out.get("resume"), "resume_link": out.get("resume_link")}, co))


def S(file, link=(), unsure=(), name="Sam Rivera Resume.pdf", size=len(PDF), mime="application/pdf"):
    return {"name": name, "size": size, "type": mime, "sent_with": list(file), "unsure_with": list(unsure), "link_with": list(link), "handoff": False}


try:
    # Greenhouse with a resume question: the file goes into it
    out, rec, got = apply("GH Files")
    gh = ["hiring system (greenhouse)"]
    t("Greenhouse, resume question: sent, and the stand-in got the file", (out["status"], [(g["system"], g["files"].get("resume")) for g in got]),
      ("sent", [("greenhouse", {"filename": "Sam Rivera Resume.pdf", "type": "application/pdf", "bytes": len(PDF)})]))
    t("Greenhouse, resume question: the app is told the file went (the link went nowhere: no question takes it)", out.get("resume"), S(gh))
    t("Greenhouse, resume question: the receipt says it was sent", receipt_line(rec), "Sam Rivera Resume.pdf (sent to GH Files with the application)")
    t("Greenhouse, resume question: the link went nowhere, and the receipt's link row says so", (LINK in json.dumps(got), link_line(rec)),
      (False, LINK + " (not sent: GH Files's form has no place for it)"))
    note_later("Greenhouse, resume question", out, "GH Files")

    # Greenhouse with no resume question but a website question: no file, and the link goes as the website answer (no portfolio link)
    out, rec, got = apply("GH Website")
    g = got[0] if got else {"files": {}, "fields": {}}
    t("Greenhouse, no resume question: sent with no file, and the link is the website answer", (out["status"], g["files"], g["fields"].get("question_110")), ("sent", {}, LINK))
    t("Greenhouse, no resume question: the app is told no file went, and that the link did", out.get("resume"), S([], link=gh))
    t("Greenhouse, no resume question: the receipt says the file was not sent and the link went instead", receipt_line(rec),
      "Sam Rivera Resume.pdf (not sent: GH Website's form does not take this file; your resume link went instead)")
    t("...and the owner copy says the same of the applicant's link", receipt_line(rec, owner=True),
      "Sam Rivera Resume.pdf (not sent: GH Website's form does not take this file; their resume link went instead)")
    t("Greenhouse, website question: the receipt's link row lists the link as shared", (out.get("resume_link"), link_line(rec)), ({"link_with": gh, "unsure_with": []}, LINK))
    note_later("Greenhouse, website question", out, "GH Website")

    # Greenhouse with no resume question and nothing that carries a link: neither goes, and nothing claims the link went
    out, rec, got = apply("GH Bare")
    g = got[0] if got else {"files": {}, "fields": {}}
    t("Greenhouse, bare form: sent with no file and the link nowhere in what it got", (out["status"], g["files"], LINK in json.dumps(g["fields"])), ("sent", {}, False))
    t("Greenhouse, bare form: the app is told neither went", out.get("resume"), S([]))
    t("Greenhouse, bare form: the receipt names no link (it used to say 'your resume link goes instead if you added one')", receipt_line(rec),
      "Sam Rivera Resume.pdf (not sent: GH Bare's form does not take this file)")
    t("Greenhouse, bare form: the receipt and the owner copy no longer list the link as shared (it used to read 'Resume: <link>')",
      (link_line(rec), link_line(rec, owner=True)), (LINK + " (not sent: GH Bare's form has no place for it)",) * 2)
    note_later("Greenhouse, bare form", out, "GH Bare")

    # only a link, no file, into the same bare form: the server says the link did not go, and so do the receipt and the app
    out, rec, got = apply("GH Bare", raw=None)
    g = got[0] if got else {"files": {}, "fields": {}}
    t("Greenhouse, bare form, link only: sent, the link nowhere in what it got", (out["status"], LINK in json.dumps(g)), ("sent", False))
    t("Greenhouse, bare form, link only: no file summary, and the link summary says it did not go", (out.get("resume"), out.get("resume_link")),
      (None, {"link_with": [], "unsure_with": []}))
    t("Greenhouse, bare form, link only: the receipt's link row says so, and there is no file line", (link_line(rec), receipt_line(rec)),
      (LINK + " (not sent: GH Bare's form has no place for it)", ""))
    note_later("Greenhouse, bare form, link only", out, "GH Bare")

    # Lever always takes the file, and lists the resume link
    out, rec, got = apply("Lever Co")
    g = got[0] if got else {"files": {}, "fields": {}}
    t("Lever: the stand-in got the file and the link", (out["status"], g["files"].get("resume", {}).get("bytes"), g["fields"].get("urls[Resume link]")), ("sent", len(PDF), LINK))
    t("Lever: the app is told both went", out.get("resume"), S(["hiring system (lever)"], link=["hiring system (lever)"]))
    t("Lever: the receipt lists the link as shared", link_line(rec), LINK)
    note_later("Lever", out, "Lever Co")
    out, rec, got = apply("Lever Co", raw=None)
    t("Lever, link only: the link went, and the receipt lists it", (out.get("resume_link"), link_line(rec)), ({"link_with": ["hiring system (lever)"], "unsure_with": []}, LINK))
    note_later("Lever, link only", out, "Lever Co")

    # Ashby with a resume field, and without one
    out, rec, got = apply("Ashby Files")
    g = got[0] if got else {"files": {}, "values": {}}
    t("Ashby, resume field: the stand-in got the file in it", (out["status"], g["values"].get("_systemfield_resume"), g["files"].get("resume_1", {}).get("bytes")), ("sent", "resume_1", len(PDF)))
    t("Ashby, resume field: the app is told the file went", out.get("resume"), S(["hiring system (ashby)"]))
    out, rec, got = apply("Ashby Bare")
    g = got[0] if got else {"files": {}, "values": {}}
    t("Ashby, no resume field: sent with no file and no link", (out["status"], g["files"], LINK in json.dumps(g["values"])), ("sent", {}, False))
    t("Ashby, no resume field: the app is told neither went", out.get("resume"), S([]))
    t("Ashby, no resume field: the receipt says the file was not sent, and names no link", receipt_line(rec), "Sam Rivera Resume.pdf (not sent: Ashby Bare's form does not take this file)")
    t("Ashby, no resume field: the receipt's link row says the link was not sent", link_line(rec), LINK + " (not sent: Ashby Bare's form has no place for it)")
    note_later("Ashby, no resume field", out, "Ashby Bare")

    # SmartRecruiters always takes the file (the link goes only when there is no file)
    out, rec, got = apply("SR Co")
    g = got[0]["body"] if got else {}
    t("SmartRecruiters: the stand-in got the file", (out["status"], (g.get("resume") or {}).get("fileContent")), ("sent", "(%d bytes)" % len(PDF)))
    t("SmartRecruiters: the app is told the file went", out.get("resume"), S(["hiring system (smartrecruiters)"]))
    t("SmartRecruiters: with the file, the link is not in the message, and the receipt's link row says so", (LINK in json.dumps(got), link_line(rec)),
      (False, LINK + " (not sent: SR Co's form has no place for it)"))

    # Workable: a PDF goes; a text file is left out and the link goes in the cover letter. This is the hiring system submit() names for the
    # channel ("kind"): if it named another, the text file would be reported as having gone with it.
    wk = ["hiring system (workable)"]
    out, rec, got = apply("Works Co")
    c = got[0]["body"]["candidate"] if got else {}
    t("Workable, PDF: the stand-in got the file", (out["status"], (c.get("resume") or {}).get("data")), ("sent", "(%d bytes)" % len(PDF)))
    t("Workable, PDF: the app is told the file went", out.get("resume"), S(wk))
    out, rec, got = apply("Works Co", TXT, "text/plain", "Sam Rivera Resume.txt")
    c = got[0]["body"]["candidate"] if got else {}
    t("Workable, text file: sent with no file, the link in the cover letter", (out["status"], "resume" in c, ("Resume: " + LINK) in c.get("cover_letter", "")), ("sent", False, True))
    t("Workable, text file: submit() reports it as not sent (the 'kind' of the channel is Workable)", out.get("resume"),
      S([], link=wk, name="Sam Rivera Resume.txt", size=len(TXT), mime="text/plain"))
    t("Workable, text file: the record keeps the same", rec["resume_to"], {"file": [], "unsure": [], "link": wk, "link_unsure": []})
    t("Workable, text file: the receipt says it was not sent and the link went instead", receipt_line(rec),
      "Sam Rivera Resume.txt (not sent: Works Co's form does not take this file; your resume link went instead)")
    t("Workable, text file: the receipt lists the link as shared", link_line(rec), LINK)
    note_later("Workable, text file", out, "Works Co")
    out, rec, got = apply("Works Co", TXT, "text/plain", "Sam Rivera Resume.txt", link="")
    t("Workable, text file and no link: neither went, and the receipt names no link", (out.get("resume")["sent_with"], out.get("resume")["link_with"], receipt_line(rec)),
      ([], [], "Sam Rivera Resume.txt (not sent: Works Co's form does not take this file)"))

    # test mode: an Ashby employer's form is never read (test mode must not use the employer's key), so whether the file would go is unknown
    cfg["delivery"] = "test"
    before = len(received())
    out, rec, got = apply("Ashby Files")
    t("test mode, Ashby: simulated, nothing reached the stand-in", (out["status"], rec["channels"], len(received()) - before), ("delivered_test", ["hiring system (simulated)"], 0))
    t("test mode, Ashby: the app is told it cannot be known, not that the file is in the test application", out.get("resume"), S([], unsure=["hiring system (simulated)"]))
    t("test mode, Ashby: the receipt says so", receipt_line(rec),
      "Sam Rivera Resume.pdf (not known: UAply did not read Ashby Files's form in test mode, so it cannot tell whether the file would go)")
    t("test mode, Ashby: the link row says that is not known either", link_line(rec),
      LINK + " (not known: UAply did not read Ashby Files's form in test mode, so it cannot tell whether the link would go)")
    note_later("test mode, Ashby", out, "Ashby Files")
    # a connected Greenhouse form is read in test mode too, so its answer stays exact
    out, rec, got = apply("GH Bare")
    t("test mode, Greenhouse bare form: read, so it says the file is not in the test application", (out.get("resume")["sent_with"], out.get("resume")["unsure_with"], receipt_line(rec)),
      ([], [], "Sam Rivera Resume.pdf (not in the test application: GH Bare's form does not take this file)"))
    note_later("test mode, Greenhouse bare form", out, "GH Bare")
    # a connected Greenhouse posting whose form cannot be read (gone from the board): test mode does read Greenhouse forms, so the reason given
    # must not be "test mode does not read it"; it is only that the form was not read
    out, rec, got = apply("GH Gone")
    t("test mode, Greenhouse form not readable: simulated, and the app is told it cannot be known", (out["status"], out.get("resume")),
      ("delivered_test", S([], unsure=["hiring system (simulated)"])))
    t("test mode, Greenhouse form not readable: the receipt says the form was not read, not that test mode skips it", receipt_line(rec),
      "Sam Rivera Resume.pdf (not known: UAply did not read GH Gone's form in test mode, so it cannot tell whether the file would go)")
    note_later("test mode, Greenhouse form not readable", out, "GH Gone")
    out, rec, got = apply("Works Co", TXT, "text/plain", "Sam Rivera Resume.txt")
    t("test mode, Workable text file: not in the test application, the link is", receipt_line(rec),
      "Sam Rivera Resume.txt (not in the test application: Works Co's form does not take this file; your resume link is in it instead)")
    cfg["delivery"] = "live"

    # the message the app shows for each of these, from resumeNote itself
    js = RESUME_NOTE + "\nconst cases=" + json.dumps([[c[1], c[2]] for c in NOTES]) + ";console.log(JSON.stringify(cases.map(c=>resumeNote(c[0],c[1]))));"
    shown = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30).stdout or "[]")
    want = {"Greenhouse, resume question": " Your resume file (Sam Rivera Resume.pdf) went with it.",
            "Greenhouse, website question": " Your resume file was not sent: GH Website's form does not take it. Your resume link went instead.",
            "Greenhouse, bare form": " Your resume file was not sent: GH Bare's form does not take it.",
            "Greenhouse, bare form, link only": " Your resume link was not sent: GH Bare's form has no place for it.",
            "Lever, link only": "",
            "Lever": " Your resume file (Sam Rivera Resume.pdf) went with it.",
            "Ashby, no resume field": " Your resume file was not sent: Ashby Bare's form does not take it.",
            "Workable, text file": " Your resume file was not sent: Works Co's form does not take it. Your resume link went instead.",
            "test mode, Ashby": " UAply did not read Ashby Files's form in test mode, so it cannot tell whether your resume file (Sam Rivera Resume.pdf) would go with it.",
            "test mode, Greenhouse form not readable": " UAply did not read GH Gone's form in test mode, so it cannot tell whether your resume file (Sam Rivera Resume.pdf) would go with it.",
            "test mode, Greenhouse bare form": " Your resume file is not in the test application: GH Bare's form does not take it."}
    for (label, _, _), msg in zip(NOTES, shown + [None] * (len(NOTES) - len(shown))):
        t("the app's message, %s" % label, msg, want[label])
finally:
    mock.terminate()

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
