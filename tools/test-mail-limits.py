"""Tests the email system as a mail service like Brevo sees it: what every message carries (Date, Message-ID, plain text beside HTML,
no header a person could add, sizes, links, no [TEST] on the live site), the daily quota guard (codes first from 250, receipts and copies
held until the next UTC day, nothing tried at 300), the answers to a refused login, a used-up quota, a refused address and a dropped
connection, the one log line per problem, held mail sent the next day, and the bounce webhook (POST /api/email/events) end to end.
  python tools/test-mail-limits.py [smtp-port] [server-port]      (default 2538 and 18799; the server also uses server-port + 1)"""
import base64
import email
import email.policy
import http.client
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="uaply-mail-limits-")
os.environ["UAPLY_DATA_DIR"] = TMP
os.environ["UAPLY_CONFIG_JSON"] = "{}"

import auth_api  # noqa: E402
import emails  # noqa: E402
import mailer  # noqa: E402
import uaply_api  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


SMTP_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 2538
SERVER_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 18799
MAIL = os.path.join(TMP, "mail.jsonl")
CONTROL = os.path.join(TMP, "control.json")


def control(**c):
    with open(CONTROL, "w", encoding="utf-8") as f:
        json.dump(c, f)


def mails():
    try:
        with open(MAIL, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except OSError:
        return []


def parse(m):
    return email.message_from_string(m["raw"], policy=email.policy.default)


class Log:
    """Catches what mailer.py writes to the server's log."""
    def __enter__(self):
        self.old, self.buf = sys.stderr, io.StringIO()
        sys.stderr = self.buf
        return self

    def __exit__(self, *a):
        sys.stderr = self.old
        self.lines = [ln for ln in self.buf.getvalue().splitlines() if ln.strip()]


control()
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(SMTP_PORT), MAIL, CONTROL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
server = None
try:
    time.sleep(1.5)
    SMTP = {"host": "127.0.0.1", "port": SMTP_PORT, "starttls": False, "from_addr": "uaplytechnologies@uaply.net", "user": "login@smtp-brevo.com", "password": "not-a-real-key"}
    cfg = {"delivery": "test", "smtp": dict(SMTP), "owner_copy": "owner@example.com", "support_email": "help@example.com", "daily_limit": 20,
           "public_url": "https://uaply.onrender.com"}
    uaply_api.config = lambda: cfg
    uaply_api.init("limits")
    auth_api.init("limits")
    mailer.RETRY_SECONDS = 0.1
    real_clock = time.time

    def account(addr, ip):
        s, out, tok = auth_api.signup(addr, "correct horse 99", ip, True)
        uid, a, digits = auth_api.issue_code_for_token(tok)
        auth_api.verify_code(tok, digits, ip)
        return auth_api.user_for(tok), tok

    user, tok = account("sam@example.com", "127.0.0.1")
    JOB = {"id": 424242, "co": "Acme Robotics", "role": "Software Engineering Intern", "url": "https://acme.example/jobs/42", "source": "Acme careers",
           "loc": "Philadelphia, PA", "type": "internship", "mode": "hybrid", "sal": [30000, 38000], "blurb": "Build and test the software that drives our robots."}
    n_job = [500000]

    def swipe(profile=None, job=None, who=None):
        n_job[0] += 1
        j = dict(JOB, id=n_job[0], **(job or {}))
        p = {"consent": True, "job": j, "profile": profile or {"name": "Sam Rivera", "email": "sam@example.com", "skills": ["Python"], "ext": {"phone": "215-555-0100"}}, "match": 80}
        return uaply_api.submit(p, who or user, "https://uaply.onrender.com")

    # ---------- 1. what every message carries ----------
    code, out = swipe()
    time.sleep(0.5)
    sent = mails()
    rec = next((parse(m) for m in sent if m["to"] == ["sam@example.com"]), None)
    own = next((parse(m) for m in sent if m["to"] == ["owner@example.com"]), None)
    t("a swipe sends the receipt and the owner copy", (out["receipt"]["status"], out["copied"], bool(rec), bool(own)), ("sent", True, True, True))
    for label, m in (("receipt", rec), ("owner copy", own)):
        if not m:
            continue
        t("%s: From is 'UAply <uaplytechnologies@uaply.net>'" % label, str(m["From"]), "UAply <uaplytechnologies@uaply.net>")
        t("%s: has a Date and a Message-ID on uaply.net (spam filters mark mail without them)" % label,
          (bool(m["Date"]), bool(re.match(r"^<[^@>]+@uaply\.net>$", str(m["Message-ID"])))), (True, True))
        t("%s: Auto-Submitted: auto-generated (auto-responders do not answer it)" % label, str(m["Auto-Submitted"]), "auto-generated")
        t("%s: a plain-text part beside the HTML" % label, [p.get_content_type() for p in m.walk() if not p.is_multipart()], ["text/plain", "text/html"])
        html_part = m.get_body(preferencelist=("html",)).get_content()
        t("%s: the HTML is under 100 KB (Gmail clips longer messages)" % label, len(html_part.encode("utf-8")) < 100000, True)
        links = re.findall(r'href="([^"]+)"', html_part)
        t("%s: every link is https" % label, all(u.startswith("https://") for u in links), True)
        t("%s: no unsubscribe header (transactional mail does not need one)" % label, m["List-Unsubscribe"], None)
    if rec:
        body = rec.get_body(preferencelist=("plain",)).get_content()
        t("receipt: links to the live site (public_url), never 127.0.0.1", ("https://uaply.onrender.com" in body, "127.0.0.1" in body), (True, False))
        t("receipt: no Reply-To (a reply reaches UAply's own inbox)", rec["Reply-To"], None)

    # a name, a job title or a company with line breaks or other control characters can never add a header, and never loses the email
    before = len(mails())
    nasty = "Sam Bcc: evil@attacker.example\x0b\x00 Rivera"
    code, out = swipe(profile={"ext": {"phone": "215-555-0100"}, "name": nasty, "email": "sam@example.com", "skills": ["Python"]},
                      job={"role": "Intern\x85Bcc: evil@attacker.example", "co": "Acme\x0cBcc: x@attacker.example"})
    time.sleep(0.5)
    new = [parse(m) for m in mails()[before:]]
    t("hostile characters in a name, a title and a company: the receipt and the copy still go out", (out["receipt"]["status"], out["copied"], len(new)), ("sent", True, 2))
    allowed = {"From", "To", "Subject", "Reply-To", "Date", "Message-ID", "Auto-Submitted", "Content-Type", "Content-Transfer-Encoding", "MIME-Version"}
    t("...with no Bcc and no header beyond the ones UAply sets", [sorted(set(m.keys()) - allowed) for m in new], [[], []])
    t("...and subjects on one line, without control characters", all(not re.search(r"[\x00-\x1f\x7f\x85  ]", str(m["Subject"])) for m in new), True)
    msg = uaply_api._application_message(cfg, "hr@employer.example", {"name": nasty, "email": "sam@example.com", "title": "", "loc": "", "edu": "", "years": 0,
                                                                     "skills": [], "ext": uaply_api._ext({})},
                                         {"role": "Intern Bcc: evil@attacker.example", "co": "Acme", "url": "https://acme.example/j", "loc": ""}, "")
    raw = msg.as_string()
    t("employer email: the Reply-To is the applicant's own address, the name on one line", (msg["Reply-To"].addresses[0].addr_spec, " " in str(msg["Reply-To"])),
      ("sam@example.com", False))
    t("employer email: no Bcc header anywhere", "\nBcc:" in raw, False)
    s_, text_, page_ = emails.verification_email("123456")
    t("the code email is small and has both parts", (len(page_) < 5000, "123456" in text_ and "123456" in page_), (True, True))

    # ---------- 2. no [TEST] on the live site for a hand-off ----------
    rec_h = {"mode": "test", "status": "handoff", "candidate": {"name": "Sam", "email": "sam@example.com"}, "job": dict(JOB), "at": 1791932764, "note": ""}
    uaply_api.PUBLIC = True
    sub_live, text_live, _ = emails.applicant_receipt(uaply_api._mail_ctx(cfg, rec_h, ""))
    sub_copy, _, _ = emails.owner_copy(uaply_api._mail_ctx(cfg, rec_h, ""))
    t("live site, a hand-off in test mode: no [TEST] and no test banner (nothing differs from live mode)",
      (sub_live.startswith("[TEST]"), "TEST EMAIL" in text_live, sub_copy.startswith("[TEST]")), (False, False, False))
    sub_t, _, _ = emails.applicant_receipt(uaply_api._mail_ctx(cfg, dict(rec_h, status="delivered_test"), ""))
    t("live site, a simulated delivery: still labelled [TEST] (nothing reached the employer)", sub_t.startswith("[TEST]"), True)
    uaply_api.PUBLIC = False
    sub_l, _, _ = emails.applicant_receipt(uaply_api._mail_ctx(cfg, rec_h, ""))
    t("the owner's own computer keeps the [TEST] label on every test-mode email", sub_l.startswith("[TEST]"), True)

    # ---------- 3. the daily quota guard ----------
    def set_count(n, full=False):
        with open(os.path.join(TMP, "mail-count.json"), "w", encoding="utf-8") as f:
            json.dump({"day": mailer.day(), "sent": n, "full": full}, f)

    set_count(249)
    before = len(mails())
    code, out = swipe(who=dict(user))
    t("at 249 sent today: the receipt still goes (250th), the owner copy is held", (out["receipt"]["status"], out["copied"], mailer.today()[0]), ("sent", False, 250))
    with Log() as lg:
        code, out = swipe()
    t("at 250: the receipt is held, not lost, and the swipe itself worked", (code, out["status"], out["receipt"]["status"]), (200, "handoff", "held"))
    t("...one log line each for the receipt and the copy, saying why and until when",
      [bool(re.match(r"^\[uaply\] email not sent: (receipt|owner_copy) to (s|o)\*\*\*@example\.com: daily limit \(250 of 300 sent today; 50 kept for codes and applications\); held until \d{4}-\d\d-\d\d 00:00 UTC$", ln)) for ln in lg.lines],
      [True, True])
    stored = auth_api.mail_list(1)[0]
    t("the stored copy of the receipt says held, with a note why", (stored["status"], stored["body"].startswith("(Held: UAply's email was at its daily limit")), ("held", True))
    held = mailer._queue()
    t("three emails are held (the copy at 249, the receipt and the copy at 250); none was sent", (len(held), sorted(e["kind"] for e in held), len(mails()) - before),
      (3, ["owner_copy", "owner_copy", "receipt"], 1))
    s2, out2, tok2 = auth_api.signup("newperson@example.com", "correct horse 99", "127.0.0.9", True)
    uid2, addr2, digits2 = auth_api.issue_code_for_token(tok2)
    t("at 250: a sign-up code still goes first", (uaply_api.send_verification_mail(uid2, addr2, digits2), mailer.today()[0]), ("sent", 251))
    before = len(mails())
    st = uaply_api.send_support_ticket({"id": "t1", "topic": "contact", "text": "Help me", "email": "newperson@example.com", "at": time.time()})
    t("at 251: a help request to the team is held (it is on the Feedback page already)", (st, len(mails()) - before), ("held", 0))
    set_count(300)
    with Log() as lg:
        st = uaply_api.send_verification_mail(uid2, addr2, digits2)
    t("at 300: nothing is tried; the code answer says the problem is on UAply's side", (st, len(mails()) - before), ("busy", 0))
    t("...with one log line", lg.lines, ["[uaply] email not sent: code to n***@example.com: quota (300 of 300 sent today); not sent"])
    try:
        uaply_api._send_email(cfg, "hr@employer.example", {"name": "Sam", "email": "sam@example.com", "title": "", "loc": "", "edu": "", "years": 0, "skills": [],
                                                           "ext": uaply_api._ext({})}, dict(JOB), "")
        why = "sent"
    except uaply_api.MailNotSent as e:
        why = str(e)
    t("at 300: an application email to an employer is not sent and says why", why, "the daily email limit is reached")
    mailer.clock = lambda: real_clock() + 3600            # later the same day: still over the line, nothing held is sent
    t("later the same day nothing held is sent", uaply_api.flush_mail(), 0)
    mailer.clock = lambda: mailer.next_day(real_clock()) + 60       # just after midnight UTC
    before = len(mails())
    n = uaply_api.flush_mail()
    got = [m["to"][0] for m in mails()[before:]]
    t("the next UTC day: every held email is sent", (n, sorted(got)), (4, ["help@example.com", "owner@example.com", "owner@example.com", "sam@example.com"]))
    t("...the queue is empty and the new day's count is 4", (len(mailer._queue()), mailer.today()), (0, (4, False)))
    t("...and the stored receipt now says sent", [m["status"] for m in auth_api.mail_list(5) if m["to_addr"] == "sam@example.com"][0], "sent")
    mailer.clock = time.time

    # ---------- 4. when the mail service refuses ----------
    set_count(0)
    control(auth="535 5.7.8 Authentication failed")
    with Log() as lg:
        st = uaply_api.send_verification_mail(uid2, addr2, digits2)
    t("a refused login (a wrong or revoked SMTP key): the code answer is 'busy' (our side), not 'check your address'", st, "busy")
    t("...one log line that names the fix", lg.lines, ["[uaply] email not sent: code to n***@example.com: login (535 5.7.8 Authentication failed); not sent: "
                                                       "the SMTP key in UAPLY_CONFIG_JSON (smtp.password) is wrong or was revoked"])
    with Log() as lg:
        code, out = swipe()
    t("...a receipt is held for a retry in 15 minutes, the application itself is done", (out["status"], out["receipt"]["status"], len(mailer._queue())), ("handoff", "held", 2))
    control()
    mailer.clock = lambda: real_clock() + 16 * 60
    before = len(mails())
    t("once the key is fixed, the held receipt and copy go out on the next round", (uaply_api.flush_mail(), len(mails()) - before), (2, 2))
    mailer.clock = time.time

    control(data="421 4.7.0 Daily sending quota exceeded for this account")
    with Log() as lg:
        code, out = swipe()
    t("the mail service says the quota is used up: the receipt is held until the next day", (out["receipt"]["status"], all("held until" in ln and "00:00 UTC" in ln for ln in lg.lines)), ("held", True))
    t("...and the day is marked full, so a code is not even tried", (mailer.today()[1], uaply_api.send_verification_mail(uid2, addr2, digits2)), (True, "busy"))
    control()
    set_count(0)
    for e in mailer._queue():
        mailer._drop(e["id"])

    control(rcpt={"gone@example.com": "550 5.1.1 The email account that you tried to reach does not exist"})
    s3, out3, tok3 = auth_api.signup("gone@example.com", "correct horse 99", "127.0.0.10", True)
    uid3, addr3, digits3 = auth_api.issue_code_for_token(tok3)
    with Log() as lg:
        st = uaply_api.send_verification_mail(uid3, addr3, digits3)
    t("an address the mail service refuses for good: 'failed' (check the address)", st, "failed")
    t("...it goes on the bounce list", mailer.suppressed("gone@example.com"), "refused")
    control()
    before = len(mails())
    t("...so the next code to it is not even tried: 'bounced'", (uaply_api.send_verification_mail(uid3, addr3, digits3), len(mails()) - before), ("bounced", 0))

    control(data_once=["451 4.3.0 Temporary failure, try again"])
    before = len(mails())
    t("a one-time 451: tried once more after a moment, and the code arrives", (uaply_api.send_verification_mail(uid2, addr2, digits2), len(mails()) - before), ("sent", 1))
    good_port = cfg["smtp"]["port"]
    cfg["smtp"]["port"] = 1                                # nothing listens there: the connection is refused
    with Log() as lg:
        code, out = swipe()
    cfg["smtp"]["port"] = good_port
    t("the mail service cannot be reached: the application is done, the receipt held for a retry", (out["status"], out["receipt"]["status"]), ("handoff", "held"))
    t("...one line per email, saying 'unreachable'", [("unreachable" in ln) for ln in lg.lines], [True, True])

    # deleting the account drops what is still held for it
    t("deleting an account drops its held mail", (uaply_api.forget_user(user["id"]) >= 0, [e for e in mailer._queue() if e.get("user") == user["id"]]), (True, []))

    # ---------- 5. the bounce webhook, through the real server ----------
    for e in mailer._queue():
        mailer._drop(e["id"])
    SECRET = "brevo-events-" + "x" * 24
    sdir = os.path.join(TMP, "srv")
    os.makedirs(sdir, exist_ok=True)
    env = dict(os.environ, UAPLY_DATA_DIR=sdir, UAPLY_CONFIG_FILE="none",
               UAPLY_CONFIG_JSON=json.dumps({"smtp": dict(SMTP, user=""), "owner_copy": "", "email_events_secret": SECRET, "feeds": []}))
    server_log = open(os.path.join(TMP, "server.log"), "w+", encoding="utf-8")      # a file, not a pipe: a full pipe would stop the server
    server = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(SERVER_PORT), "dev", "--api"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=server_log)
    for _ in range(60):
        try:
            http.client.HTTPConnection("127.0.0.1", SERVER_PORT, timeout=2).request("GET", "/healthz")
            break
        except OSError:
            time.sleep(0.25)

    def post(path, body, auth=None, origin=True):
        h = {"Host": "127.0.0.1:%d" % SERVER_PORT, "Content-Type": "application/json"}
        if origin:
            h["Origin"] = "http://127.0.0.1:%d" % SERVER_PORT
        if auth:
            h["Authorization"] = auth
        c = http.client.HTTPConnection("127.0.0.1", SERVER_PORT, timeout=30)
        c.request("POST", path, body=body if isinstance(body, bytes) else json.dumps(body), headers=h)
        r = c.getresponse()
        data = r.read()
        ck = r.getheader("Set-Cookie") or ""
        c.close()
        try:
            return r.status, json.loads(data), ck
        except ValueError:
            return r.status, data, ck

    def basic(pw):
        return "Basic " + base64.b64encode(("uaply:" + pw).encode()).decode()

    ev = {"event": "hard_bounce", "email": "bouncer@example.com", "id": 1, "date": "2026-10-17 20:00:00", "ts": 1791230000,
          "message-id": "<x@uaply.net>", "reason": "550 5.1.1 user unknown", "tags": []}
    t("the webhook without the secret is refused (401)", post("/api/email/events", ev, origin=False)[0], 401)
    t("...with a wrong secret too, as a bearer token or a URL password", (post("/api/email/events", ev, "Bearer nope", False)[0],
                                                                         post("/api/email/events", ev, basic("nope"), False)[0]), (401, 401))
    s, out, _ = post("/api/email/events", ev, "Bearer " + SECRET, origin=False)
    t("Brevo's hard_bounce with the bearer token is recorded (no Origin header needed)", (s, out.get("recorded")), (200, {"blocked": 1}))
    s, out, _ = post("/api/email/events", [{"event": "spam", "email": "complainer@example.com"}, {"event": "opened", "email": "x@example.com"},
                                            {"event": "blocked", "email": "not an address"}], basic(SECRET), origin=False)
    t("a list of events with the URL password: the complaint is recorded, the rest ignored", (s, out.get("recorded")), (200, {"blocked": 1, "ignored": 1}))
    soft = [post("/api/email/events", {"event": "soft_bounce", "email": "full@example.com"}, "Bearer " + SECRET, False)[1]["recorded"] for _ in range(5)]
    t("five soft bounces in a week count as a bounce", soft[-1], {"blocked": 1})
    t("a body that is not JSON is refused", (post("/api/email/events", b"not json", "Bearer " + SECRET, False)[0],
                                          post("/api/email/events", "just a string", "Bearer " + SECRET, False)[0]), (400, 400))
    before = len(mails())
    s, out, ck = post("/api/auth/signup", {"email": "bouncer@example.com", "password": "correct horse 99", "agree": True})
    time.sleep(0.5)
    t("signing up with a bouncing address: the account is made, no code is sent, the answer says 'bounced'", (s, out.get("delivery"), len(mails()) - before), (200, "bounced", 0))
    s, out, _ = post("/api/email/events", {"event": "uaply_unblock", "email": "bouncer@example.com"}, "Bearer " + SECRET, False)
    t("the owner can take an address off the list with the same secret", out.get("recorded"), {"unblocked": 1})
    c = http.client.HTTPConnection("127.0.0.1", SERVER_PORT, timeout=10)
    c.request("GET", "/api/status")
    st = json.loads(c.getresponse().read())
    c.close()
    t("/api/status says bounce events are on (yes/no only)", (st.get("email"), st.get("emailEvents")), (True, True))
    server.terminate()
    server.wait(timeout=20)
    server = None
    server_log.seek(0)
    err = server_log.read()
    server_log.close()
    t("the start-up line says email: on (bounce events: on)", "email: on (bounce events: on)" in err, True)
    t("the log names the bouncing addresses masked, never in full", ("b***@example.com is on the bounce list (hard_bounce)" in err, "bouncer@example.com" in err), (True, False))
    env2 = dict(env, UAPLY_CONFIG_JSON=json.dumps({"smtp": dict(SMTP, user=""), "feeds": []}))
    server = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(SERVER_PORT + 1), "dev", "--api"], cwd=ROOT, env=env2,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            http.client.HTTPConnection("127.0.0.1", SERVER_PORT + 1, timeout=2).request("GET", "/healthz")
            break
        except OSError:
            time.sleep(0.25)
    c = http.client.HTTPConnection("127.0.0.1", SERVER_PORT + 1, timeout=10)
    c.request("POST", "/api/email/events", body=json.dumps(ev), headers={"Content-Type": "application/json", "Authorization": "Bearer " + SECRET})
    t("without email_events_secret in the config the endpoint does not exist (404)", c.getresponse().status, 404)
    c.close()
finally:
    if server:
        server.terminate()
        try:
            server.wait(timeout=20)
        except Exception:
            server.kill()
    proc.terminate()
    proc.wait()

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
