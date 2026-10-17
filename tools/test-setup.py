"""Tests the "Connect Gmail" form on the setup page: validation, what it saves, that the password is never echoed, and the messages for a
wrong password. It uses a temporary config file and a fake mail connection, so it never touches your real settings or Gmail.
  python tools/test-setup.py"""
import json
import os
import smtplib
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="uaply-setup-")
os.environ["UAPLY_DATA_DIR"] = TMP
os.environ["UAPLY_CONFIG_JSON"] = "{}"

import setup_api  # noqa: E402
import uaply_api  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


uaply_api.CONFIG_PATH = os.path.join(TMP, "uaply-config.json")
PW = "abcd efgh ijkl mnop"            # how Google shows an App Password: four groups of four


class FakeSMTP:
    mode = "ok"
    sent = []

    def __init__(self, host, port, timeout=0):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, pw):
        if FakeSMTP.mode == "auth":
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
        if FakeSMTP.mode == "drop":
            raise smtplib.SMTPServerDisconnected("closed")
        FakeSMTP.login_used = (user, pw)

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


setup_api.smtplib.SMTP = FakeSMTP

# validation: nothing is written
for label, body in [("no address", {"email": "", "password": PW}), ("a bad address", {"email": "nope", "password": PW}),
                    ("a short password", {"email": "a@gmail.com", "password": "abc"}),
                    ("a password with symbols", {"email": "a@gmail.com", "password": "abcd-efgh-ijkl-mn!!"}),
                    ("a bad copy address", {"email": "a@gmail.com", "password": PW, "copy_to": "not an email"})]:
    s, out = setup_api.save_mail(body)
    t("%s is refused and nothing is saved" % label, (s, out["ok"], os.path.exists(uaply_api.CONFIG_PATH)), (400, False, False))

# existing settings survive
with open(uaply_api.CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump({"feeds": ["greenhouse"], "google": {"client_id": "x"}, "owner_copy": "old@example.com"}, f)

s, out = setup_api.save_mail({"email": " uaply.sender@gmail.com ", "password": PW, "copy_to": "uaplytechnologies@gmail.com"})
cfg = json.load(open(uaply_api.CONFIG_PATH, encoding="utf-8"))
t("a good form saves and sends a test", (s, out["ok"], out["saved"]), (200, True, True))
t("the password is saved without spaces", cfg["smtp"]["password"], "abcdefghijklmnop")
t("Gmail's server, port and TLS are set", (cfg["smtp"]["host"], cfg["smtp"]["port"], cfg["smtp"]["starttls"]), ("smtp.gmail.com", 587, True))
t("the sender and login are the address given, trimmed", (cfg["smtp"]["user"], cfg["smtp"]["from_addr"]), ("uaply.sender@gmail.com",) * 2)
t("the copy address was updated", cfg["owner_copy"], "uaplytechnologies@gmail.com")
t("other settings were kept", (cfg["feeds"], cfg["google"]), (["greenhouse"], {"client_id": "x"}))
t("the password is never sent back", "abcdefghijklmnop" not in json.dumps(out) and PW not in json.dumps(out), True)
t("a test email went to the copy address", [m["To"] for m in FakeSMTP.sent], ["uaplytechnologies@gmail.com"])
t("the login used the saved password", FakeSMTP.login_used, ("uaply.sender@gmail.com", "abcdefghijklmnop"))

# a wrong password gives a clear message
FakeSMTP.mode = "auth"
s, out = setup_api.save_mail({"email": "uaply.sender@gmail.com", "password": PW})
t("a refused login says to use an App Password", (out["ok"], "App Password" in out["message"]), (False, True))
FakeSMTP.mode = "drop"
s, out = setup_api.save_mail({"email": "uaply.sender@gmail.com", "password": PW})
t("a dropped connection is explained, not shown as an error code", (out["ok"], "closed the connection" in out["message"]), (False, True))

# Brevo: sends from the owner's own domain with Brevo's SMTP login and key
FakeSMTP.mode = "ok"
FakeSMTP.sent = []
KEY = "xsmtpsib-" + "0123456789abcdef" * 4 + "-AbCdEfGh12345678"
s, out = setup_api.save_mail({"provider": "brevo", "email": "uaplytechnologies@uaply.net", "login": "", "password": KEY})
t("Brevo without its SMTP login is refused, with where to find it", (s, "smtp-brevo.com" in out["message"]), (400, True))
s, out = setup_api.save_mail({"provider": "brevo", "email": "uaplytechnologies@uaply.net", "login": "9a1b2c001@smtp-brevo.com", "password": "abcdefghijklmnop"})
t("a Gmail App Password is not taken as a Brevo key", (s, "xsmtpsib-" in out["message"]), (400, True))
s, out = setup_api.save_mail({"provider": "brevo", "email": "uaplytechnologies@uaply.net", "login": "9a1b2c001@smtp-brevo.com", "password": KEY, "copy_to": "uaplytechnologies@gmail.com"})
cfg_b = json.load(open(uaply_api.CONFIG_PATH, encoding="utf-8"))["smtp"]
t("Brevo is saved: its server, the login, and mail comes from the uaply.net address", (out["ok"], cfg_b["host"], cfg_b["port"], cfg_b["user"], cfg_b["from_addr"]),
  (True, "smtp-relay.brevo.com", 587, "9a1b2c001@smtp-brevo.com", "uaplytechnologies@uaply.net"))
t("...and the test email goes out from that address with Brevo's login", (FakeSMTP.sent[-1]["From"], FakeSMTP.login_used), ("uaplytechnologies@uaply.net", ("9a1b2c001@smtp-brevo.com", KEY)))
t("the key is never sent back to the page", KEY in json.dumps(out), False)
FakeSMTP.mode = "auth"
s, out = setup_api.test_mail()
t("Brevo refusing the login says where to check in Brevo", (out["ok"], "Brevo refused the login" in out["message"]), (False, True))
FakeSMTP.mode = "ok"

# the Connect Google box: only the public client ID, only a real-looking one
uaply_api.CONFIG_PATH = os.path.join(TMP, "uaply-config2.json")
s, out = setup_api.save_google({"client_id": "not a client id"})
t("a made-up client ID is refused and nothing is saved", (s, out["ok"], os.path.exists(uaply_api.CONFIG_PATH)), (400, False, False))
with open(uaply_api.CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump({"feeds": ["greenhouse"], "smtp": {"host": "smtp.gmail.com", "password": "keep-me"}}, f)
s, out = setup_api.save_google({"client_id": " 123456789012-abcdefg1234567.apps.googleusercontent.com "})
cfg2 = json.load(open(uaply_api.CONFIG_PATH, encoding="utf-8"))
t("a real-looking client ID is saved (trimmed) and other settings are kept", (s, out["saved"], cfg2["google"]["client_id"], cfg2["feeds"], cfg2["smtp"]["password"]),
  (200, True, "123456789012-abcdefg1234567.apps.googleusercontent.com", ["greenhouse"], "keep-me"))
uaply_api.CONFIG_PATH = os.path.join(TMP, "uaply-config.json")

# a server started for testing (UAPLY_CONFIG_FILE=none) never reads the owner's uaply-config.json, so it must not write it either
real_env, real_path = os.environ.get("UAPLY_CONFIG_FILE"), uaply_api.CONFIG_PATH
os.environ["UAPLY_CONFIG_FILE"] = "none"
uaply_api.CONFIG_PATH = uaply_api.REAL_CONFIG_PATH
before = os.path.exists(uaply_api.REAL_CONFIG_PATH) and os.stat(uaply_api.REAL_CONFIG_PATH).st_mtime_ns
got = [setup_api.save_google({"client_id": "123456789012-abcdefg1234567.apps.googleusercontent.com"})[0],
       setup_api.save_mail({"email": "uaply.sender@gmail.com", "password": PW})[0],
       setup_api.save_stripe({"secret_key": "sk_test_abcdefgh1234", "price_plus": "price_a", "price_pro": "price_b"})[0]]
after = os.path.exists(uaply_api.REAL_CONFIG_PATH) and os.stat(uaply_api.REAL_CONFIG_PATH).st_mtime_ns
t("a test run refuses to save Google, email or Stripe settings into the owner's real file, and the file is untouched", (got, before == after), ([409, 409, 409], True))
t("...but it still checks what was typed first (the setup page test relies on that)", setup_api.save_mail({})[1]["message"].startswith("Enter the Gmail address"), True)
uaply_api.CONFIG_PATH = real_path
if real_env is None:
    os.environ.pop("UAPLY_CONFIG_FILE", None)
else:
    os.environ["UAPLY_CONFIG_FILE"] = real_env

# without a password the test button says why
os.remove(uaply_api.CONFIG_PATH)
uaply_api.config = lambda: {"smtp": {"host": "smtp.gmail.com", "from_addr": "a@gmail.com", "user": "a@gmail.com", "password": ""}, "delivery": "test"}
s, out = setup_api.test_mail()
t("the test button says the password or key is missing", (out["ok"], "no password or key" in out["message"]), (False, True))

# the Connect an employer's hiring system box
import jobs_api  # noqa: E402
os.environ["UAPLY_DATA_DIR"] = TMP
code_copy = os.path.join(os.path.dirname(os.path.abspath(jobs_api.__file__)), "uaply-partners.json")      # the owner's real list, if any (only its date is looked at)
code_stamp = os.path.exists(code_copy) and os.stat(code_copy).st_mtime_ns
s, out = setup_api.save_ats({"kind": "workday", "board": "acme", "api_key": "abcdefgh1234"})
t("an unknown hiring system is refused", (s, out["ok"]), (400, False))
s, out = setup_api.save_ats({"kind": "greenhouse", "board": "ac/me", "api_key": "abcdefgh1234"})
t("a board name with a slash is refused", s, 400)
s, out = setup_api.save_ats({"kind": "Greenhouse", "board": "acme", "api_key": " gh-test-key-1234 "})
t("a good connection is saved (kind lower-cased, key trimmed)", (s, out["saved"], jobs_api.ats_connections().get(("greenhouse", "acme"))), (200, True, "gh-test-key-1234"))
t("the key is never in the answer or on the setup page", ("gh-test-key" in json.dumps(out), "gh-test-key" in setup_api.page("localhost:8767", "http").decode()), (False, False))
t("the page lists the connection by name only", "Greenhouse / acme" in setup_api.page("localhost:8767", "http").decode(), True)
setup_api.save_ats({"kind": "lever", "board": "acme", "api_key": "lever-test-key-1"})
setup_api.save_ats({"kind": "greenhouse", "board": "acme", "api_key": "gh-test-key-5678"})
t("saving the same board again replaces its key, other connections stay", (jobs_api.ats_connections().get(("greenhouse", "acme")), sorted(jobs_api.ats_connections())), ("gh-test-key-5678", [("greenhouse", "acme"), ("lever", "acme")]))
setup_api.remove_ats({"kind": "lever", "board": "acme"})
t("a connection can be removed", sorted(jobs_api.ats_connections()), [("greenhouse", "acme")])
s, out = setup_api.save_ats({"kind": "smartrecruiters", "board": "CityofPhiladelphia", "api_key": "sr-test-token-1234"})
s2, out2 = setup_api.save_ats({"kind": "ashby", "board": "acme", "api_key": "ashby-test-key-1"})
page = setup_api.page("localhost:8767", "http").decode()
t("Ashby and SmartRecruiters connect too, named properly in the answer and on the page",
  ((s, s2), "Real SmartRecruiters postings" in out["message"], "SmartRecruiters / CityofPhiladelphia" in page, "Ashby / acme" in page), ((200, 200), True, True, True))
t("the box offers all four systems and says where each employer makes its key",
  all(x in page for x in ('<option value="ashby">', '<option value="smartrecruiters">', "Credential Manager", "Candidates write")), True)
t("neither key is ever on the page", ("sr-test-token" in page, "ashby-test-key" in page), (False, False))
setup_api.remove_ats({"kind": "smartrecruiters", "board": "CityofPhiladelphia"})
setup_api.remove_ats({"kind": "ashby", "board": "acme"})
t("with UAPLY_DATA_DIR set the employer list is written there, and the one next to the code is never created or changed",
  (os.path.exists(os.path.join(TMP, "uaply-partners.json")), os.path.exists(code_copy) and os.stat(code_copy).st_mtime_ns), (True, code_stamp))

# the setup page is the owner's guide to switching test mode off: clickable steps, the exact addresses to give Google, and anchors the sign-in screen links to
page = setup_api.page("localhost:8767", "http").decode("utf-8")
t("the page tells Google both local addresses (Google needs the bare localhost one too)", all(("<code>%s</code>" % o) in page for o in ("http://localhost:8767", "http://localhost")), True)
t("each address has a Copy button (2 local and 3 live origins, 4 redirect URIs)", page.count('class="cp"'), 9)
t("the live site's exact redirect URIs are listed", all(("<code>%s/api/auth/google/callback</code>" % o) in page for o in ("https://uaply.net", "https://www.uaply.net", "https://uaply.onrender.com", "http://localhost:8767")), True)
t("...but never one on the bare localhost (nothing listens there)", "<code>http://localhost/api/auth/google/callback</code>" in page, False)
t("the Google and Gmail boxes have anchors for the sign-in screen's links", ('id="google"' in page, 'id="gmail"' in page), (True, True))
t("the steps are clickable links to Google's own pages", all(('href="%s"' % u) in page for u in (
    "https://console.cloud.google.com/auth/overview", "https://console.cloud.google.com/auth/clients",      # Google Auth Platform (Google's current console)
    "https://myaccount.google.com/apppasswords", "https://myaccount.google.com/signinoptions/two-step-verification")), True)
t("links open in a new tab without handing over the opener", 'target="_blank" rel="noopener noreferrer"' in page, True)
t("the page explains why a test inbox is still showing", "Why you still see the test inbox" in page, True)
evil = setup_api.page('"><script>alert(1)</script>', "http").decode("utf-8")
t("a hostile Host header is escaped, never printed as markup", ("<script>alert(1)</script>" in evil, "&lt;script&gt;" in evil), (False, True))
t("a hosted address is given as it is, without the extra localhost one", [o for o in setup_api.origins("uaply.example", "https")], ["https://uaply.example"])

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
