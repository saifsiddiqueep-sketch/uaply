"""Tests the help-request path of the assistant: a "Talk to a person" or problem report is emailed to the support inbox with the person's address as
the reply address; what happens when real email is not connected or fails; the hourly cap; and that hostile input cannot inject mail headers.
Uses a stand-in mail server, so nothing real is sent.
  python tools/test-support.py"""
import email
import email.policy
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="uaply-support-")
os.environ["UAPLY_DATA_DIR"] = TMP
os.environ["UAPLY_CONFIG_JSON"] = "{}"

import chat_api  # noqa: E402
import uaply_api  # noqa: E402

R = []
SUPPORT = "uaplytechnologies@gmail.com"


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


mail_file = os.path.join(TMP, "mail.jsonl")
port = int(sys.argv[1]) if len(sys.argv) > 1 else 2534          # a free port can be given: python tools/test-support.py PORT
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(port), mail_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
SMTP = {"host": "127.0.0.1", "port": port, "starttls": False, "from_addr": "UAply <noreply@uaply.example>"}
cfg = {"delivery": "test", "smtp": dict(SMTP), "support_email": SUPPORT, "owner_copy": "owner@example.com"}
uaply_api.config = lambda: cfg
uaply_api.init("support")
chat_api.init("support")
n = [0]


def ask(payload, user=None):
    n[0] += 1
    return chat_api.feedback(payload, "10.1.0.%d" % n[0], user, notify=uaply_api.send_support_ticket)


def mails():
    time.sleep(0.5)
    if not os.path.exists(mail_file):
        return []
    rows = [json.loads(x) for x in open(mail_file, encoding="utf-8") if x.strip()]
    return [(r["to"], email.message_from_string(r["raw"], policy=email.policy.default)) for r in rows]


def body_of(m):
    return m.get_body(preferencelist=("plain",)).get_content()


try:
    # 1. "Talk to a person" with an email: emailed to the support inbox, reply address is the person
    s, out = ask({"topic": "contact", "source": "chat", "text": "I can't verify my email, the code never arrives.", "email": "Sam.Rivera@Gmail.com", "followup": True, "page": "account"})
    t("a help request is accepted and says it was emailed", (s, out["ok"], out["delivery"]), (200, True, "emailed"))
    got = mails()
    t("exactly one email went out, to the support inbox", [to for to, _ in got], [[SUPPORT]])
    m = got[0][1]
    t("pressing Reply answers the person (Reply-To is their address)", str(m["Reply-To"]), "sam.rivera@gmail.com")
    t("the subject says it is a help request and starts with their words", m["Subject"].startswith("[UAply help] I can't verify my email"), True)
    b = body_of(m)
    t("the body has their message, their address, the ticket number and the screen", all(x in b for x in ("I can't verify my email", "sam.rivera@gmail.com", out["id"], "account")), True)
    t("it is plain text, never HTML", m.get_content_type(), "text/plain")
    rec = chat_api.FEEDBACK[-1]
    t("the request is also saved for the Feedback page, marked as emailed", (rec["id"], rec["delivery"]), (out["id"], "emailed"))
    with open(os.path.join(chat_api.DATA, "feedback.jsonl"), encoding="utf-8") as f:
        t("...and written to the feedback file with the same status", json.loads(f.read().strip().split("\n")[-1])["delivery"], "emailed")

    # 2. a problem report with no email: still goes to the team, but says it cannot be answered
    s, out = ask({"topic": "bug", "source": "chat", "text": "What happened: swipe did nothing\nTrying to: apply"})
    t("a problem report without an email is still emailed to the team", (s, out["delivery"]), (200, "emailed"))
    m = mails()[-1][1]
    t("it has no reply address and the email says so", (m["Reply-To"], "cannot be answered by email" in body_of(m)), (None, True))
    t("the subject says it is a problem", m["Subject"].startswith("[UAply problem]"), True)

    # 3. what is NOT emailed
    before = len(mails())
    s, out = ask({"topic": "nudge", "rating": 5, "source": "nudge"})
    t("a plain star rating is only saved, not emailed", (out["delivery"], len(mails())), ("saved", before))
    s, out = ask({"topic": "general", "rating": 4, "text": "Nice app", "source": "chat"})
    t("general feedback with no request for a reply is only saved", (out["delivery"], len(mails())), ("saved", before))
    s, out = ask({"topic": "general", "rating": 2, "text": "Jobs are slow to load", "email": "fan@example.com", "followup": True, "source": "chat"})
    t("general feedback where the person asked for a reply IS emailed", (out["delivery"], len(mails())), ("emailed", before + 1))

    # 4. input that is not a request at all
    t("a contact request without a message is refused", ask({"topic": "contact", "email": "a@b.co", "followup": True})[0], 400)
    t("a contact request without an email is refused", ask({"topic": "contact", "text": "help"})[0], 400)
    before = len(mails())
    s, out = ask({"topic": "contact", "text": "hello\r\nBcc: attacker@example.com", "email": "a@b.co\r\nBcc: attacker@example.com", "followup": True})
    t("an email address with a line break in it is refused and nothing is sent", (s, len(mails())), (400, before))

    # 5. a line break in the message cannot add a mail header; HTML stays plain text
    before = len(mails())
    s, out = ask({"topic": "contact", "text": "line one\r\nBcc: attacker@example.com\r\nSubject: spoofed\n<script>alert(1)</script>", "email": "safe@example.com", "followup": True})
    got = mails()
    m = got[-1][1]
    t("a message with fake header lines sends exactly one email to support only", (len(got), got[-1][0]), (before + 1, [SUPPORT]))
    t("...no extra header was created: one Subject, no Bcc, and the subject stayed on one line", (m["Bcc"], len(m.get_all("Subject")), "\n" in (m["Subject"] or "")), (None, 1, False))
    t("...the script text arrives as plain words", "<script>alert(1)</script>" in body_of(m) and m.get_content_type() == "text/plain", True)

    # 6. the acknowledgement goes only to an address UAply has proven is the person's
    verified = {"id": 7, "email": "proven@example.com", "emailVerified": True}
    unverified = {"id": 8, "email": "unproven@example.com", "emailVerified": False}
    before = len(mails())
    ask({"topic": "contact", "text": "Please help with my account", "email": "proven@example.com", "followup": True}, verified)
    got = mails()[before:]
    t("a verified person gets the team email plus an acknowledgement", sorted(to[0] for to, _ in got), sorted([SUPPORT, "proven@example.com"]))
    ack = [m for to, m in got if to == ["proven@example.com"]][0]
    t("...the acknowledgement quotes their message and replies go to the team", ("Please help with my account" in body_of(ack), str(ack["Reply-To"])), (True, SUPPORT))
    t("...and the team email says who they are signed in as", "Signed in to UAply as: proven@example.com" in body_of([m for to, m in got if to == [SUPPORT]][0]), True)
    before = len(mails())
    ask({"topic": "contact", "text": "Help me", "email": "unproven@example.com", "followup": True}, unverified)
    t("an unverified person gets no acknowledgement (nobody can make UAply email a stranger)", [to for to, _ in mails()[before:]], [[SUPPORT]])
    before = len(mails())
    ask({"topic": "contact", "text": "Help me", "email": "someone.else@example.com", "followup": True}, verified)
    t("a verified person giving a different address gets no acknowledgement either", [to for to, _ in mails()[before:]], [[SUPPORT]])

    # 7. where it goes when there is no explicit support address, and when there is nowhere
    saved_cfg = dict(cfg)
    cfg.pop("support_email")
    before = len(mails())
    s, out = ask({"topic": "contact", "text": "Using the owner address", "email": "z@example.com", "followup": True})
    t("with no support address set it goes to the owner's address", (out["delivery"], mails()[-1][0]), ("emailed", ["owner@example.com"]))
    cfg.pop("owner_copy")
    before = len(mails())
    s, out = ask({"topic": "contact", "text": "Nowhere to go", "email": "z@example.com", "followup": True})
    t("with no address at all it is saved, not lost, and nothing is sent", (s, out["delivery"], len(mails())), (200, "saved", before))
    cfg.update(saved_cfg)

    # 8. real email not connected, or failing
    cfg["smtp"] = {}
    before = len(mails())
    s, out = ask({"topic": "contact", "text": "Mail is off here", "email": "z@example.com", "followup": True})
    t("with no real email connected the request is saved (and says so), nothing is sent", (s, out["delivery"], len(mails())), (200, "saved", before))
    cfg["smtp"] = dict(SMTP)
    real_send = uaply_api._send_receipt

    def boom(*a, **k):
        raise OSError("mail server down")
    uaply_api._send_receipt = boom
    s, out = ask({"topic": "contact", "text": "Mail server is failing", "email": "z@example.com", "followup": True})
    uaply_api._send_receipt = real_send
    t("when the mail server fails the request is still saved and the answer says it failed", (s, out["delivery"], chat_api.FEEDBACK[-1]["delivery"]), (200, "failed", "failed"))

    # 9. the hourly cap protects the inbox
    uaply_api._support_times.clear()
    uaply_api.SUPPORT_PER_HOUR = 2
    results = [ask({"topic": "contact", "text": "Flood %d" % i, "email": "flood@example.com", "followup": True})[1]["delivery"] for i in range(4)]
    uaply_api.SUPPORT_PER_HOUR = 60
    t("after the hourly cap further requests are saved, not emailed", results, ["emailed", "emailed", "saved", "saved"])

    # 10. the owner's Feedback page tells the truth about each request
    page = chat_api.feedback_html().decode("utf-8")
    t("the Feedback page shows which requests reached the team by email", all(x in page for x in ("emailed to the team", "NOT emailed (the mail server refused it)", "not emailed (no real email connected)")), True)

    # 11. "Take me there" under an answer: the release build (dev) uses an article's release destination when it has one
    def go_of(art_id, release):
        chat_api.RELEASE, chat_api._help["mtime"] = release, None
        return [a["go"] for a in chat_api.articles() if a["id"] == art_id][0]
    t("distance: the sandbox goes to Filters (its commute slider), the release build to Profile setup, Where and pay",
      (go_of("distance", False), go_of("distance", True)), ("prof:filters", "prof:where"))
    t("an article with no release destination keeps its own in the release build", go_of("resume", True), "prof:back")
    real_path = chat_api.HELP_PATH
    bad_file = os.path.join(TMP, "articles.json")
    with open(bad_file, "w", encoding="utf-8") as f:
        f.write('{"articles": [ {"id": "x", ')                 # a typo while editing the file
    chat_api.HELP_PATH = bad_file
    t("a broken help file keeps the last good articles instead of leaving the assistant empty", len(chat_api.articles()) > 10, True)
    chat_api.HELP_PATH, chat_api.RELEASE, chat_api._help["mtime"] = real_path, False, None

    # 12. pricing questions, however they are put, reach Plans and billing; in the release build the answer leads with the price
    chat_api.RELEASE, chat_api._help["mtime"] = True, None
    asks = ["How much does it cost?", "pricing", "fees", "Is it expensive?", "Do you charge?", "monthly fee", "how much money", "Is UAply free?"]
    t("every way of asking about price finds Plans and billing", [q for q in asks if not (chat_api.search(q) and chat_api.search(q)[0]["id"] == "plans")], [])
    ans = chat_api._from_articles("pricing")["answer"]
    t("the release build's pricing answer starts with what it costs today and names the coming prices",
      (ans.startswith("UAply is free during early access"), "$9.99" in ans and "$19.99" in ans), (True, True))
    chat_api.RELEASE, chat_api._help["mtime"] = False, None
finally:
    proc.terminate()

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
