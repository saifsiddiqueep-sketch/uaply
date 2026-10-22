"""Tests the swipe-right emails: what they say, that test mode is labelled, that nothing a person typed can inject HTML, and a real
send through the stand-in mail server (tools/fake-smtp.py).
  python tools/test-emails.py"""
import email
import email.policy
import json
import os
import subprocess
import sys
import tempfile
import time
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="uaply-emails-")
os.environ["UAPLY_DATA_DIR"] = TMP
os.environ["UAPLY_CONFIG_JSON"] = "{}"

import auth_api  # noqa: E402
import emails  # noqa: E402
import uaply_api  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


class Tags(HTMLParser):
    """Counts open and close tags, so an unbalanced email is caught."""
    VOID = {"meta", "br", "img", "hr", "input", "link"}

    def __init__(self):
        super().__init__()
        self.stack, self.bad, self.scripts = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts += 1
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.bad += 1


def ctx(status, test=True, **over):
    c = {"test": test, "status": status, "at": 1791932764, "match": 87, "to": "jobs@acme.example",
         "cand": {"name": "Sam Rivera", "email": "sam@example.com"},
         "job": {"co": "Acme Robotics", "role": "Software Engineering Intern", "loc": "Philadelphia, PA", "type": "internship", "mode": "hybrid",
                 "sal": [30000, 38000], "url": "https://acme.example/jobs/42", "desc": "Build and test the software that drives our warehouse robots."},
         "rows": [("Applicant", "Sam Rivera"), ("Email", "sam@example.com"), ("Skills", "Python, SQL"), ("Resume", "https://example.com/sam.pdf")],
         "note": "", "user_email": "sam@example.com", "base_url": "https://uaply.example", "support_email": "help@uaply.example"}
    c.update(over)
    return c


# ---- what each email says ----
for status in ("handoff", "sent", "delivered_test"):
    sub, text, page = emails.applicant_receipt(ctx(status))
    t("%s: subject starts with [TEST] in test mode" % status, sub.startswith("[TEST] "), True)
    t("%s: subject names the job and company" % status, "Software Engineering Intern" in sub and "Acme Robotics" in sub, True)
    t("%s: text has every section" % status, all(k in text for k in ("THE JOB", "ABOUT THE JOB", "WHAT A SWIPE RIGHT MEANS", "WHAT HAPPENS NEXT", "TRACK IT")), True)
    t("%s: text shows date and time, pay, type and match" % status, all(k in text for k in ("Oct 13, 2026", "UTC", "$30k to $38k a year", "Internship", "87%")), True)
    t("%s: text says what a swipe right means" % status, "Swiping right means" in text and "Swiping left only hides" in text, True)
    t("%s: says it is a test and nothing went to the employer" % status, "TEST EMAIL" in text, True)
    p = Tags()
    p.feed(page)
    t("%s: HTML tags are balanced and has no script" % status, (p.bad, len(p.stack), p.scripts), (0, 0, 0))
    t("%s: HTML links to the posting" % status, 'href="https://acme.example/jobs/42"' in page, True)

_, text, page = emails.applicant_receipt(ctx("handoff"))
t("handoff: tells the person the application is NOT complete yet", "not complete yet" in text, True)
t("handoff: has a Finish your application button", "Finish your application" in page, True)
sub, text, _ = emails.applicant_receipt(ctx("sent", test=False))
t("live mode: no [TEST] in the subject", not sub.startswith("[TEST]") and sub == "Applied: Software Engineering Intern at Acme Robotics", True)
t("live mode: no test banner", "TEST EMAIL" not in text, True)
sub, _, _ = emails.applicant_receipt(ctx("handoff", test=False))
t("live handoff subject asks the person to finish", sub, "Finish your application: Software Engineering Intern at Acme Robotics")

# ---- nothing a person or a job feed typed can inject markup or a bad link ----
evil = ctx("sent", cand={"name": "<script>alert(1)</script>", "email": "x@example.com"},
           job={"co": "Fish & Chips <b>Ltd</b>", "role": "Cook", "loc": "", "url": "javascript:alert(1)", "desc": "<img src=x onerror=alert(1)>"},
           note="<iframe src=//evil></iframe>")
_, _, page = emails.applicant_receipt(evil)
t("a script tag in a name is escaped", "<script>" not in page and "&lt;script&gt;" in page, True)
t("markup in a company, description or note is escaped", "<b>Ltd</b>" not in page and "<img" not in page and "<iframe" not in page, True)
t("a javascript: link is never used", "javascript:" not in page, True)
sub, text, page = emails.owner_copy(ctx("handoff"))
t("owner copy: says where the application went", "no one: Acme Robotics takes applications on its own site" in text, True)
t("owner copy: lists the applicant and the job", "Sam Rivera" in text and "THE JOB" in text and "THE APPLICANT" in text, True)

# ---- the date and time read naturally: no leading zero on the day or the hour ----
t("the applied-on time drops the zero of a one-digit day AND hour (Oct 5, 9:05 AM)", emails._when(1791191100), "Oct 5, 2026 at 9:05 AM UTC")
t("...and keeps two-digit ones and midnight as 12", (emails._when(1791932764), emails._when(1791158400)), ("Oct 13, 2026 at 11:06 PM UTC", "Oct 5, 2026 at 12:00 AM UTC"))

# ---- the test banner says what the live app would really do, from the channels the server recorded ----
R_ROWS = [("Applicant", "Sam Rivera"), ("Email", "sam@example.com"), ("Resume file", "Sam Rivera Resume.pdf (attached)")]
_, text, _ = emails.applicant_receipt(ctx("delivered_test", to="Acme Robotics hiring system (simulated)", channels=["hiring system (simulated)"]))
t("test banner, connected hiring system: says it would go into their hiring system, not an email",
  ("straight into Acme Robotics's hiring system" in text, "emailed your application" in text), (True, False))
_, text, _ = emails.applicant_receipt(ctx("delivered_test", to="Acme Robotics hiring system (simulated)", channels=["hiring system (simulated)"], preview=True))
t("test banner, sandbox preview of a public posting: says the live app would send the person to the employer's site",
  ("connects its hiring system" in text, "own site to finish" in text, "emailed your application" in text), (True, True, False))
_, text, _ = emails.applicant_receipt(ctx("delivered_test", channels=["email (simulated)"]))
t("test banner, an employer that takes email: names the address", "would have emailed your application to jobs@acme.example" in text, True)

# ---- the resume line says where the file really went (no receipt or copy carries the file itself) ----
_, text, page = emails.applicant_receipt(ctx("handoff", rows=R_ROWS))
t("hand-off receipt: the resume is to be uploaded on the employer's form, not 'attached'",
  ("Sam Rivera Resume.pdf (upload it on Acme Robotics's form)" in text, "(attached)" in text + page), (True, False))
t("hand-off receipt: dated 'Swiped right on', since nothing was applied yet", ("Swiped right on:" in text, "Applied on" in text), (True, False))
_, text, _ = emails.applicant_receipt(ctx("sent", test=False, rows=R_ROWS))
t("sent receipt: the resume went with the application", ("Sam Rivera Resume.pdf (sent to Acme Robotics with the application)" in text, "Applied on:" in text), (True, True))
sub, text, page = emails.owner_copy(ctx("sent", test=False, rows=R_ROWS))
t("owner copy: says the resume is not attached to the copy, and 'Match' instead of 'Your match'",
  ("not attached to this copy" in text, "Your match" in text + page, "Match: 87%" in text), (True, False, True))
t("owner copy, live: no [TEST] label", sub.startswith("[UAply copy]"), True)
sub, _, _ = emails.owner_copy(ctx("handoff", test=True, rows=R_ROWS))
t("owner copy, test mode: labelled [TEST]", sub.startswith("[TEST] [UAply copy]"), True)
rows = uaply_api._detail_rows({"name": "Sam", "email": "s@example.com", "ext": {"school": "Drexel University", "major": "Design", "grad": "2027-06", "gpa": 3.6}})
t("education reads as words: graduation June 2027, not 2027-06", dict(rows).get("Education"), "Drexel University, Design, graduation June 2027, GPA 3.6")

# ---- a real send through the stand-in mail server ----
mail_file = os.path.join(TMP, "mail.jsonl")
port = int(sys.argv[1]) if len(sys.argv) > 1 else 2527                # another port can be given, so two test runs never collide
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(port), mail_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(1.5)
    cfg = {"delivery": "test", "smtp": {"host": "127.0.0.1", "port": port, "starttls": False, "from_addr": "uaply@example.com"},
           "owner_copy": "owner@example.com", "support_email": "help@uaply.example", "daily_limit": 20}
    uaply_api.config = lambda: cfg
    uaply_api.init("emailtest")
    auth_api.init("emailtest")
    s, out, tok = auth_api.signup("sam@example.com", "correct horse 99", "127.0.0.1", True)
    uid, addr, digits = auth_api.issue_code_for_token(tok)                     # a real person verifies their email with the emailed code
    auth_api.verify_code(tok, digits, "127.0.0.1")
    user = auth_api.user_for(tok)
    payload = {"consent": True, "job": {"id": 424242, "co": "Acme Robotics", "role": "Software Engineering Intern", "url": "https://acme.example/jobs/42",
                                         "source": "Acme careers", "loc": "Philadelphia, PA", "type": "internship", "mode": "hybrid", "sal": [30000, 38000],
                                         "blurb": "Build and test the software that drives our warehouse robots."},
               "profile": {"ext": {"phone": "215-555-0100"}, "name": "Sam Rivera", "email": "sam@example.com", "skills": ["Python", "SQL"]}, "match": 87}
    def mails():
        return [json.loads(x) for x in open(mail_file, encoding="utf-8") if x.strip()] if os.path.exists(mail_file) else []
    code, res = uaply_api.submit(payload, user)
    time.sleep(1)
    sent = mails()
    t("swiping right in test mode answers ok", code, 200)
    # a job that takes applications on the employer's own site: no "finish your application" email per swipe (October 22: one swipe
    # could send two emails, 20 swipes forty); it waits for the day's reminder
    t("a hand-off swipe sends only the owner copy now; the person's 'finish your application' waits for the day's reminder",
      (sorted(sum((m["to"] for m in sent), [])), res.get("receipt", {}).get("status"), uaply_api.finish_waiting(user["id"])), (["owner@example.com"], "digest", 1))
    owner = next((m for m in sent if m["to"] == ["owner@example.com"]), None)
    t("the owner copy is labelled as a copy and shows the job", bool(owner) and "[UAply copy]" in owner["raw"] and "warehouse robots" in owner["raw"], True)
    payload_b = dict(payload, job=dict(payload["job"], id=424250, co="Beta Labs", role="Data Intern", url="https://beta.example/jobs/7"))
    uaply_api.submit(payload_b, user)
    uaply_api.submit(payload_b, user)                                           # the same job again is listed once
    n0 = len(mails())
    t("before the hold is over nothing more is sent (one swiping session becomes one email)", (uaply_api.send_finish_digests(time.time() + 60), len(mails()) - n0), (0, 0))
    t("...after it, one reminder goes, listing both jobs once each", uaply_api.send_finish_digests(time.time() + uaply_api.DIGEST_HOLD + 60), 1)
    time.sleep(1)
    dig = [m for m in mails()[n0:] if m["to"] == ["sam@example.com"]]
    t("exactly one reminder reached the person", len(dig), 1)
    if dig:
        msg = email.message_from_string(dig[0]["raw"], policy=email.policy.default)
        body = msg.get_body(preferencelist=("plain",)).get_content()
        t("the reminder subject says TEST and counts the jobs", msg["Subject"], "[TEST] Finish your applications: 2 jobs waiting on the employers' sites")
        t("the reminder has a plain-text and an HTML version", [p.get_content_type() for p in msg.walk() if not p.is_multipart()], ["text/plain", "text/html"])
        t("the reminder lists each job once with its link", (body.count("Software Engineering Intern at Acme Robotics"), body.count("Data Intern at Beta Labs"),
                                                             "https://acme.example/jobs/42" in body and "https://beta.example/jobs/7" in body), (1, 1, True))
        t("the reminder is recorded in the test inbox with status sent", auth_api.mail_list(5)[0]["status"], "sent")
    uaply_api.submit(dict(payload, job=dict(payload["job"], id=424251)), user)
    t("another hand-off the same day waits: at most one reminder a day", uaply_api.send_finish_digests(time.time() + uaply_api.DIGEST_HOLD + 120), 0)
    t("...and goes the next day", uaply_api.send_finish_digests(time.time() + uaply_api.DIGEST_EVERY + uaply_api.DIGEST_HOLD + 120), 1)
    time.sleep(0.5)
    # when the person who swipes IS the owner address, one swipe sends one email (not a confirmation plus a copy)
    n_before = len([1 for x in open(mail_file, encoding="utf-8") if x.strip()])
    s2, out2, tok2 = auth_api.signup("owner@example.com", "correct horse 99", "127.0.0.2", True)
    uid2, addr2, digits2 = auth_api.issue_code_for_token(tok2)
    auth_api.verify_code(tok2, digits2, "127.0.0.2")
    user2 = auth_api.user_for(tok2)
    payload2 = dict(payload, job=dict(payload["job"], id=424243), profile={"ext": {"phone": "215-555-0100"}, "name": "Owner Person", "email": "owner@example.com"})
    code2, res2 = uaply_api.submit(payload2, user2)
    time.sleep(1)
    new = [json.loads(x) for x in open(mail_file, encoding="utf-8") if x.strip()][n_before:]
    t("owner swipes a hand-off: one email at the swipe (the copy), and its reminder waits for the day's email", (len(new), res2["copied"], uaply_api.finish_waiting(user2["id"])), (1, True, 1))
    sams = lambda: [m for m in auth_api.mail_list(20) if m["to_addr"] == "sam@example.com"]      # noqa: E731
    # with no public_url set (a fresh host), the reminder links to the https address the person is using; a plain http address is never linked
    day = time.time() + 3 * uaply_api.DIGEST_EVERY
    uaply_api.submit(dict(payload, job=dict(payload["job"], id=424244)), user, "https://uaply-dev.onrender.com")
    uaply_api.send_finish_digests(day)
    t("no public_url: the reminder links to the https site the person used", "Mark each one as applied once you finish it. https://uaply-dev.onrender.com" in sams()[0]["body"], True)
    uaply_api.submit(dict(payload, job=dict(payload["job"], id=424245)), user, "http://127.0.0.1:8767")
    uaply_api.send_finish_digests(day + 2 * uaply_api.DIGEST_EVERY)
    t("...and an http address (this computer) is never put in an email", ("127.0.0.1" in sams()[0]["body"], "Finish your application" in sams()[0]["subject"]), (False, True))
    # a receipt for an application UAply really sends is unchanged: still one per swipe, at once (the partner email employer below)
    t("the reminder is held by the daily limit like other mail that can wait", "digest" in __import__("mailer").DEFERRABLE, True)

    # ---- Mark as applied reaches the server, and the reminder is sent outside the lock every swipe takes (October 22) ----
    def waiting_ids(u):
        return [i["id"] for i in (uaply_api._digest_load().get(str(u["id"])) or {}).get("items") or []]
    job = lambda n: dict(payload["job"], id=n)                                                      # noqa: E731
    uaply_api.send_finish_digests(day + 6 * uaply_api.DIGEST_EVERY)                                 # (nothing left waiting from above)
    uaply_api.submit(dict(payload, job=job(424260)), user)
    uaply_api.submit(dict(payload, job=job(424261)), user)
    t("Mark as applied takes that job out of the waiting reminder", (uaply_api.mark_applied(user["id"], 424260), waiting_ids(user)), (1, [424261]))
    uaply_api._queue_finish(user, {"job": job(424260), "mode": "test"})      # (submit itself sends one application per job and person)
    t("...and a later hand-off of the same job does not put it back", waiting_ids(user), [424261])
    uaply_api.submit(dict(payload, job=job(424262), marked=True), user)
    t("a swipe whose record carries the mark (marked: true) is never put in a reminder", waiting_ids(user), [424261])
    uaply_api.mark_applied(user["id"], 424260, False)
    uaply_api._queue_finish(user, {"job": job(424260), "mode": "test"})
    t("Undo: after it, a hand-off of that job is reminded again", waiting_ids(user), [424261, 424260])
    t("a job id that is not a number is refused", uaply_api.mark_applied(user["id"], "x"), None)
    import threading
    gate, inside, got = threading.Event(), threading.Event(), []
    real_send = uaply_api._send_receipt

    def slow_send(*a, **k):
        if k.get("kind") == "digest":                       # the mail service takes its time with the reminder
            inside.set()
            gate.wait(15)
        return real_send(*a, **k)
    uaply_api._send_receipt = slow_send
    try:
        th = threading.Thread(target=lambda: got.append(uaply_api.send_finish_digests(day + 9 * uaply_api.DIGEST_EVERY)))
        th.start()
        inside.wait(10)
        t0 = time.time()
        uaply_api.submit(dict(payload, job=job(424270)), user)                    # a swipe while the reminder is on its way
        took = time.time() - t0
        uaply_api.mark_applied(user["id"], 424261)                                 # and a mark of a job in that reminder
        gate.set()
        th.join(20)
    finally:
        uaply_api._send_receipt = real_send
        gate.set()
    t("a swipe made while a reminder is being sent does not wait for the mail service (%.2f s)" % took, took < 3, True)
    t("...the reminder went", got, [1])
    t("...and the job swiped meanwhile waits for the next one: not lost, not counted as sent", waiting_ids(user), [424270])
    t("two senders at once: the second one sends nothing (one at a time)",
      uaply_api._digest_send_lock.acquire(blocking=False) and (uaply_api.send_finish_digests(day + 20 * uaply_api.DIGEST_EVERY), uaply_api._digest_send_lock.release())[0] == 0, True)

    # ---- marks are kept only for jobs in the person's reminder, capped; a deleted account gets no reminder (October 22 review) ----
    before = open(uaply_api._digest_path(), encoding="utf-8").read()
    t("a mark of a job that is not in the reminder changes nothing and writes nothing", (uaply_api.mark_applied(user["id"], 515151), open(uaply_api._digest_path(), encoding="utf-8").read() == before),
      (len(waiting_ids(user)), True))
    t("...an Undo of a job never marked writes nothing either", (uaply_api.mark_applied(user["id"], 515152, False), open(uaply_api._digest_path(), encoding="utf-8").read() == before),
      (len(waiting_ids(user)), True))
    t("...and an account with no reminder at all gets no entry", (uaply_api.mark_applied(987654, 424260), "987654" in uaply_api._digest_load()), (0, False))
    for n in range(uaply_api.MARKED_MAX + 15):
        uaply_api._queue_finish(user, {"job": job(600000 + n), "mode": "test"})
        uaply_api.mark_applied(user["id"], 600000 + n)
    kept = uaply_api._digest_load()[str(user["id"])]["marked"]
    t("at most %d marks are kept per account, the newest" % uaply_api.MARKED_MAX, (len(kept), kept[-1]), (uaply_api.MARKED_MAX, 600000 + uaply_api.MARKED_MAX + 14))
    s3, out3, tok3 = auth_api.signup("gone@example.com", "correct horse 99", "127.0.0.3", True)
    uid3, addr3, digits3 = auth_api.issue_code_for_token(tok3)
    auth_api.verify_code(tok3, digits3, "127.0.0.3")
    user3 = auth_api.user_for(tok3)
    t("(an account to delete, verified)", bool(user3 and user3["emailVerified"]), True)
    st, _x, _y = auth_api.delete_account(tok3, "correct horse 99", "127.0.0.3", before_delete=lambda _uid: None)
    uaply_api.forget_user(user3["id"])                                       # what deleting an account does
    uaply_api._queue_finish(user3, {"job": job(424299), "mode": "test"})     # a swipe that was in flight puts the entry back afterwards
    t("(the deleted account's entry came back from the swipe in flight)", (st, str(user3["id"]) in uaply_api._digest_load()), (200, True))
    gone_before = len([m for m in mails() if "gone@example.com" in json.dumps(m["to"])])
    uaply_api.send_finish_digests(day + 40 * uaply_api.DIGEST_EVERY)
    t("the reminder looks at the account again right before sending: a deleted one gets nothing, and its entry goes",
      (len([m for m in mails() if "gone@example.com" in json.dumps(m["to"])]) - gone_before, str(user3["id"]) in uaply_api._digest_load()), (0, False))
finally:
    proc.terminate()

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
