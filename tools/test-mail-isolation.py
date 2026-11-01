"""A test run never reaches a real mail server (card 219). The suite keeps HTTP offline through a closed proxy, but SMTP is a plain socket
that ignores proxies, so mailer.test_run_blocks refuses every mail server that is not on this computer whenever UAPLY_CONFIG_FILE=none.
  python tools/test-mail-isolation.py [port]      (port for the stand-in mail server, default 18971)"""
import json
import os
import smtplib
import subprocess
import sys
import tempfile
import time
from email.message import EmailMessage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="uaply-mail-iso-")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18971
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=TMP, UAPLY_CONFIG_JSON="{}")

import mailer      # noqa: E402
import setup_api   # noqa: E402
import uaply_api   # noqa: E402

FAILS = []


def t(name, got, want):
    ok = got == want
    print(("  ok    " if ok else "  FAIL  ") + name + ("" if ok else "  (got %r, want %r)" % (got, want)))
    if not ok:
        FAILS.append(name)


def msg(to="dana.lee@example.com"):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = "uaply@example.com", to, "Your UAply code"
    m.set_content("123456")
    return m


BREVO = {"delivery": "live", "daily_limit": 300,
         "smtp": {"host": "smtp-relay.brevo.com", "port": 587, "user": "u@example.com", "password": "not-a-real-key", "from_addr": "uaply@example.com"}}

# ---------- the rule ----------
t("a test run refuses Brevo, Gmail, a private address and an empty host",
  [mailer.test_run_blocks(h) for h in ("smtp-relay.brevo.com", "smtp.gmail.com", "10.0.0.5", "", None)], [True] * 5)
t("...and allows only this computer: 127.0.0.1, 127.5.5.5, localhost, ::1, [::1]",
  [mailer.test_run_blocks(h) for h in ("127.0.0.1", "127.5.5.5", "LOCALHOST", "::1", "[::1]")], [False] * 5)
os.environ["UAPLY_CONFIG_FILE"] = "x"
t("outside a test run (no UAPLY_CONFIG_FILE=none) nothing is refused: the live site keeps sending through Brevo",
  mailer.test_run_blocks("smtp-relay.brevo.com"), False)
os.environ["UAPLY_CONFIG_FILE"] = "none"

# ---------- a mock transport: no socket is ever opened to a real host ----------
calls = []


class Recorder:
    def __init__(self, host, port, timeout=None):
        calls.append(host)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, *a):
        pass

    def send_message(self, m):
        pass


real_smtp, smtplib.SMTP = smtplib.SMTP, Recorder
try:
    st = mailer.send(BREVO, msg(), "code")
    t("a code with live Brevo settings in a test run is not sent ('failed', 'invalid') and no connection is opened",
      (st, calls), (("failed", "invalid"), []))
    st = mailer.send(BREVO, msg(), "receipt")
    t("...a receipt (a kind that can wait) is not held for a retry either, and still no connection", (st[0], calls), ("failed", []))
    loc = dict(BREVO, smtp=dict(BREVO["smtp"], host="127.0.0.1", port=PORT))
    t("the same settings pointed at this computer go through the transport", (mailer.send(loc, msg(), "code"), calls), (("sent", ""), ["127.0.0.1"]))
    del calls[:]
    os.environ["UAPLY_CONFIG_JSON"] = json.dumps(BREVO)
    s, out = setup_api.test_mail()
    t("the setup page's Send a test email refuses Brevo in a test run, without a connection",
      (s, out["ok"], "started for testing" in out["message"], calls), (200, False, True, []))
finally:
    smtplib.SMTP = real_smtp
    os.environ["UAPLY_CONFIG_JSON"] = "{}"

# ---------- end to end: the local inbox still receives codes ----------
box = os.path.join(TMP, "mail.jsonl")
srv = subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(PORT), box], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    loc = {"delivery": "live", "daily_limit": 300, "smtp": {"host": "127.0.0.1", "port": PORT, "starttls": False, "from_addr": "uaply@example.com"}}
    st = None
    for _ in range(50):                                 # the stand-in needs a moment to listen
        st = mailer.send(loc, msg("code.check@example.com"), "code")
        if st[0] == "sent":
            break
        time.sleep(0.1)
    rows = [json.loads(x) for x in open(box, encoding="utf-8")] if os.path.exists(box) else []
    t("a code sent to the stand-in mail server on this computer arrives in its inbox",
      (st, any("code.check@example.com" in json.dumps(r) for r in rows)), (("sent", ""), True))
    os.environ["UAPLY_CONFIG_JSON"] = json.dumps({"smtp": {"host": "127.0.0.1", "port": PORT, "starttls": False, "from_addr": "uaply@example.com"}})
    t("uaply_api still counts a local mail server as ready in a test run", uaply_api.mail_ready(), True)
finally:
    srv.kill()
    os.environ["UAPLY_CONFIG_JSON"] = "{}"

print("\n%s" % ("ALL PASSED" if not FAILS else "%d FAILED" % len(FAILS)))
sys.exit(1 if FAILS else 0)
