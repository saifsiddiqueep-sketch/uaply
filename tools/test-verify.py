"""Tests the email code that proves a password account owns its email: the email itself, wrong and right codes, expiry, limits, one-time use,
and what an unverified account may not do. Uses a stand-in mail server.
  python tools/test-verify.py"""
import email
import email.policy
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="uaply-verify-")
os.environ["UAPLY_DATA_DIR"] = TMP
os.environ["UAPLY_CONFIG_JSON"] = "{}"

import auth_api  # noqa: E402
import uaply_api  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


mail_file = os.path.join(TMP, "mail.jsonl")
port = int(os.environ.get("FAKE_SMTP_PORT", "2533"))      # the stand-in mail server; set another port when 2533 is in use
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(port), mail_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
cfg = {"delivery": "test", "smtp": {"host": "127.0.0.1", "port": port, "starttls": False, "from_addr": "uaply@example.com"}, "daily_limit": 20}
uaply_api.config = lambda: cfg
uaply_api.init("verify")
auth_api.init("verify")


def send(token):
    """What serve.py does at sign-up: make the first code and email it."""
    uid, addr, digits = auth_api.issue_code_for_token(token)
    uaply_api.send_verification_mail(uid, addr, digits)
    return digits


def stored_mail(user_id):
    """Every saved copy of mail sent to this person (subject and body together), as one string."""
    with auth_api._db() as c:
        return " ".join("%s %s" % (r["subject"], r["body"]) for r in c.execute("SELECT subject, body FROM user_mail WHERE user_id=?", (user_id,)))


def last_mail(to):
    time.sleep(0.6)
    rows = [json.loads(x) for x in open(mail_file, encoding="utf-8") if x.strip()]
    mine = [m for m in rows if m["to"] == [to]]
    return email.message_from_string(mine[-1]["raw"], policy=email.policy.default) if mine else None


try:
    # sign up: unverified, a code is emailed
    s, out, tok = auth_api.signup("verify1@example.com", "correct horse 99", "10.0.0.1", True)
    t("a new password account starts unverified", out["user"]["emailVerified"], False)
    code = send(tok)
    t("the code is six digits", bool(re.fullmatch(r"[0-9]{6}", code)), True)
    msg = last_mail("verify1@example.com")
    t("the code is emailed, and the subject starts with it", bool(msg) and msg["Subject"].startswith(code), True)
    t("the email body contains the code", bool(msg) and code in msg.get_body(preferencelist=("plain",)).get_content(), True)
    with auth_api._db() as c:
        row = c.execute("SELECT code_hash FROM email_codes").fetchone()
    t("only a hash of the code is stored", code not in row["code_hash"] and len(row["code_hash"]) == 64, True)
    uid1 = auth_api.user_for(tok)["id"]
    t("once really emailed, the code is not kept in the saved copy of the email (subject or body)", code in stored_mail(uid1), False)
    t("the saved copy still says a verification email was sent", "verification code" in stored_mail(uid1).lower(), True)
    # with no real email connected (this computer's test inbox) the code MUST be kept, or nobody could ever read it
    saved_smtp = cfg["smtp"]
    cfg["smtp"] = {}
    s, out, tok_t = auth_api.signup("testinbox@example.com", "correct horse 99", "10.0.0.20", True)
    code_t = send(tok_t)
    t("in the test inbox (no real email connected) the code is kept so it can be read there", code_t in stored_mail(auth_api.user_for(tok_t)["id"]), True)
    cfg["smtp"] = saved_smtp
    # a failed real send must not leave the code behind either
    saved_send = uaply_api._send_receipt
    def _boom(*a, **k):
        raise OSError("mail server down")
    uaply_api._send_receipt = _boom
    s, out, tok_f = auth_api.signup("failedsend@example.com", "correct horse 99", "10.0.0.21", True)
    code_f = send(tok_f)
    t("even when the real send fails, the code is not kept in the saved copy", code_f in stored_mail(auth_api.user_for(tok_f)["id"]), False)
    uaply_api._send_receipt = saved_send

    # wrong, then right
    wrong = "%06d" % ((int(code) + 1) % 1000000)
    s, out = auth_api.verify_code(tok, wrong, "10.0.0.1")
    t("a wrong code is refused and says how many tries are left", (s, out.get("triesLeft")), (400, 4))
    s, out = auth_api.verify_code(tok, "12", "10.0.0.1")
    t("a code that is not six digits is refused without using a try", (s, auth_api.verify_code(tok, wrong, "10.0.0.1")[1].get("triesLeft")), (400, 3))
    s, out = auth_api.verify_code(tok, code[:3] + " " + code[3:], "10.0.0.1")
    t("the right code works (a space in the middle is fine)", (s, out.get("ok")), (200, True))
    t("the account is now verified", auth_api.user_for(tok)["emailVerified"], True)
    t("a code works only once", auth_api.verify_code(tok, code, "10.0.0.1")[1].get("already"), True)
    with auth_api._db() as c:
        t("the code is deleted after use", c.execute("SELECT COUNT(*) FROM email_codes WHERE user_id=?", (uid1,)).fetchone()[0], 0)

    # five wrong tries end the code
    s, out, tok2 = auth_api.signup("verify2@example.com", "correct horse 99", "10.0.0.2", True)
    code2 = send(tok2)
    wrong2 = "%06d" % ((int(code2) + 7) % 1000000)
    results = [auth_api.verify_code(tok2, wrong2, "10.0.0.2") for _ in range(5)]
    t("five wrong tries use up the code", [r[1].get("triesLeft") for r in results[:4]] + [bool(results[4][1].get("expired"))], [4, 3, 2, 1, True])
    s, out = auth_api.verify_code(tok2, code2, "10.0.0.2")
    t("after that even the right code is refused until a new one is sent", (s, bool(out.get("expired"))), (400, True))

    # resend: a new code replaces the old one
    s, out, mail = auth_api.resend_code(tok2, "10.0.0.2")
    t("a resend gives a new code", (s, mail is not None and mail[2] != code2), (200, True))
    new2 = mail[2]
    t("the old code no longer works", auth_api.verify_code(tok2, code2, "10.0.0.2")[0] if code2 != new2 else 400, 400)
    t("the new code works", auth_api.verify_code(tok2, new2, "10.0.0.2")[0], 200)

    # expiry
    s, out, tok3 = auth_api.signup("verify3@example.com", "correct horse 99", "10.0.0.3", True)
    code3 = send(tok3)
    with auth_api._db() as c:
        c.execute("UPDATE email_codes SET expires_at=? WHERE 1=1 AND user_id=(SELECT id FROM users WHERE email='verify3@example.com')", (int(time.time()) - 5,))
    s, out = auth_api.verify_code(tok3, code3, "10.0.0.3")
    t("an expired code is refused and says so", (s, bool(out.get("expired"))), (400, True))

    # resend limits
    s, out, tok4 = auth_api.signup("verify4@example.com", "correct horse 99", "10.0.0.4", True)
    send(tok4)
    statuses = [auth_api.resend_code(tok4, "10.0.0.4")[0] for _ in range(4)]
    t("only three codes can be requested an hour", statuses, [200, 200, 200, 429])

    # signed out
    t("checking a code while signed out is refused", auth_api.verify_code("x" * 40, "123456", "10.0.0.5")[0], 401)

    # what an unverified account may not do
    job = {"id": 500001, "co": "Acme", "role": "Intern", "url": "https://acme.example/j", "loc": "Remote", "type": "internship"}
    s, out, tok5 = auth_api.signup("unverified@example.com", "correct horse 99", "10.0.0.6", True)
    u5 = auth_api.user_for(tok5)
    code_, res = uaply_api.submit({"consent": True, "job": job, "profile": {"ext": {"phone": "215-555-0100"}, "name": "Una Verified", "email": "unverified@example.com"}}, u5)
    t("an unverified account can still swipe, but gets no confirmation email", (code_, res["receipt"]["status"]), (200, "unverified"))
    time.sleep(0.5)
    t("no email was sent to the unverified address", last_mail("unverified@example.com"), None)
    # with no real email connected nothing leaves the server: the confirmation is only saved in the test inbox, so an unverified account gets it too
    saved_smtp_u = cfg["smtp"]
    cfg["smtp"] = {}
    code_n, res_n = uaply_api.submit({"consent": True, "job": dict(job, id=500009), "profile": {"ext": {"phone": "215-555-0100"}, "name": "Una Verified", "email": "unverified@example.com"}}, u5)
    cfg["smtp"] = saved_smtp_u
    t("with no real email connected, an unverified account's swipe is saved in the test inbox", (code_n, res_n["receipt"]["status"]), (200, "delivered_test"))
    t("and that saved copy is labelled as a test", "[TEST]" in stored_mail(u5["id"]), True)
    # the same account once verified
    auth_api.verify_code(tok5, "000000", "10.0.0.6")           # a wrong try, to show it does not matter
    uid, addr, dg = auth_api.issue_code_for_token(tok5)
    auth_api.verify_code(tok5, dg, "10.0.0.6")
    u5 = auth_api.user_for(tok5)
    code_, res = uaply_api.submit({"consent": True, "job": dict(job, id=500002), "profile": {"ext": {"phone": "215-555-0100"}, "name": "Una Verified", "email": "unverified@example.com"}}, u5)
    t("once verified, a swipe sends the confirmation email", (res["receipt"]["status"], bool(last_mail("unverified@example.com"))), ("sent", True))

    # a reset link also proves the email
    s, out, tok6 = auth_api.signup("viaReset@example.com", "correct horse 99", "10.0.0.7", True)
    s, out, mail = auth_api.request_reset("viaReset@example.com", "10.0.0.7")
    s, out = auth_api.reset_password(mail[2], "another pass 12345", "10.0.0.7")
    s, out, tok7 = auth_api.login("viaReset@example.com", "another pass 12345", "10.0.0.7")
    t("using an emailed reset link proves the email too", out["user"]["emailVerified"], True)

    # a Google sign-in is verified from the start, and an old unverified account becomes verified by it
    err, user, tok8 = auth_api.oauth_login("google", "g-1", "googler@example.com", True)
    t("an account made with Google is verified", user["emailVerified"], True)

    # deleting an account removes what the sign-in features stored about it (the privacy policy promises this)
    def count(sql, *a):
        with auth_api._db() as c:
            return c.execute(sql, a).fetchone()[0]
    s, out, tok9 = auth_api.signup("deleteme@example.com", "correct horse 99", "10.0.0.8", True)
    send(tok9)
    uid9 = auth_api.user_for(tok9)["id"]
    t("before deleting, the account has a pending code, a session and a saved email", (count("SELECT COUNT(*) FROM email_codes WHERE user_id=?", uid9),
      count("SELECT COUNT(*) FROM sessions WHERE user_id=?", uid9), count("SELECT COUNT(*) FROM user_mail WHERE user_id=?", uid9)), (1, 1, 1))
    s, out, gone = auth_api.delete_account(tok9, "correct horse 99", "10.0.0.8")
    t("a password account is deleted with its password", (s, gone), (200, uid9))
    t("its code, sessions and saved email went with it", (count("SELECT COUNT(*) FROM email_codes WHERE user_id=?", uid9), count("SELECT COUNT(*) FROM sessions WHERE user_id=?", uid9),
      count("SELECT COUNT(*) FROM user_mail WHERE user_id=?", uid9)), (0, 0, 0))
    gid = user["id"]
    t("before deleting, the Google account has its Google identity", count("SELECT COUNT(*) FROM identities WHERE user_id=?", gid), 1)
    s, out, gone2 = auth_api.delete_account(tok8, "", "10.0.0.9", "DELETE")
    t("a Google account is deleted by typing DELETE", (s, gone2), (200, gid))
    t("its Google identity and sessions went with it", (count("SELECT COUNT(*) FROM identities WHERE user_id=?", gid), count("SELECT COUNT(*) FROM sessions WHERE user_id=?", gid)), (0, 0))
finally:
    proc.terminate()

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
