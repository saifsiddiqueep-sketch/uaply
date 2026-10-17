"""The owner's setup page (/setup): shows what is switched on and what still needs a key, and sends a test email.

Nothing here reveals a secret: it only says whether each one is set. Like /outbox it is open on this computer and, on a
public server, needs OWNER_PASSWORD.

  GET  /setup                 the checklist
  POST /api/setup/test-mail   send one test email to the owner (owner_copy, else the SMTP from address)
  POST /api/setup/save-mail, save-google, save-stripe   the Connect boxes: write the git-ignored uaply-config.json (never in a test run)
  POST /api/setup/save-ats, remove-ats                  an employer's hiring-system key, in the git-ignored employer list
  POST /api/setup/save-feed-keys   the Job feed keys box: save the USAJOBS and The Muse API keys (this computer only)
"""
import html
import re
import smtplib
from email.message import EmailMessage

import json
import os

import ats_api
import auth_api
import billing_api
import google_auth
import jobs_api
import uaply_api

CLIENT_RE = re.compile(r"^\d+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$")
# the live site's addresses, which Google must be told about (Render's own address keeps working next to the custom domain)
LIVE_ORIGINS = ["https://uaply.net", "https://www.uaply.net", "https://uaply.onrender.com"]
CALLBACK = "/api/auth/google/callback"


URL_RE = re.compile(r"https://[A-Za-z0-9./_?=&#%-]+[A-Za-z0-9/_-]")


TEST_RUN = {"ok": False, "message": "This server was started for testing (UAPLY_CONFIG_FILE=none): it never reads or writes uaply-config.json, so nothing was saved."}


def _test_run():
    """A test run ignores the owner's uaply-config.json (uaply_api.config), so saving into it would change the owner's real settings and
    still show nothing here. Tests that save point uaply_api.CONFIG_PATH at a file of their own instead."""
    return os.environ.get("UAPLY_CONFIG_FILE") == "none" and uaply_api.CONFIG_PATH == uaply_api.REAL_CONFIG_PATH


def _real(v, placeholder_starts=()):
    return isinstance(v, str) and bool(v.strip()) and not any(v.strip().lower().startswith(p) for p in placeholder_starts)


def _linkify(text):
    """Escape the text, then turn each https address in it into a link that opens in a new tab."""
    out, last = [], 0
    for m in URL_RE.finditer(text):
        out.append(html.escape(text[last:m.start()]))
        out.append('<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (html.escape(m.group(0)), html.escape(m.group(0))))
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out)


def origins(host, proto):
    """The addresses Google must be told about (Authorized JavaScript origins). On this computer Google wants the bare localhost one too."""
    base = "%s://%s" % (proto, host)
    found = [base]
    if host.split(":")[0] in ("localhost", "127.0.0.1"):
        found.append("%s://localhost" % proto)
    return list(dict.fromkeys(found))


def checks(host, proto):
    cfg = uaply_api.config()
    g = cfg.get("google") if isinstance(cfg.get("google"), dict) else {}
    s = cfg.get("smtp") if isinstance(cfg.get("smtp"), dict) else {}
    owner = uaply_api._owner_copy(cfg)
    g_id = g.get("client_id") if isinstance(g.get("client_id"), str) else ""
    g_ok = google_auth.button_enabled()
    smtp_ok = bool(s.get("host") and s.get("from_addr") and _real(s.get("password"), ("a gmail app password", "the-sending")))
    return [
        {"name": "Sign in with Google", "ok": g_ok,
         "detail": (("On. Continue with Google opens Google's own sign-in page on every device and comes back signed in." if google_auth.enabled() else
                     "Half on: only the client ID is set, so Google's pop-up button is used, which iPhones and iPads cannot use. Add the client secret "
                     "(python tools/setup-config.py here, UAPLY_CONFIG_JSON on the host) for the full-page sign-in on every device.") if g_ok else
                    ("The client ID does not look right (it should end in .apps.googleusercontent.com)." if g_id and not CLIENT_RE.match(g_id) and not g.get("auth_url") else
                     "Off. Add your Google client ID and client secret (the steps below; DEPLOY.md, section 3).")),
         "todo": ["Open https://console.cloud.google.com/auth/overview (Google Auth Platform), signed in with the Google account that should own UAply, and press Get started (create a project named UAply if asked): App name UAply, User support email your Gmail, Audience External, Contact email your Gmail, agree, Create.",
                  "Branding ( https://console.cloud.google.com/auth/branding ): App home page https://uaply.net , Privacy policy https://uaply.net/legal/privacy.html , Terms of service https://uaply.net/legal/terms.html , Authorized domains uaply.net and uaply.onrender.com (onrender.com itself is a public suffix, so Google takes the full Render address; it also adds the domains of your redirect URIs by itself). Save.",
                  "Audience ( https://console.cloud.google.com/auth/audience ): press Publish app, then Confirm. Sign-in asks only for openid and email, which Google counts as non-sensitive, so there is no review and no 100-user limit. Left in Testing, only the test users you list there could sign in.",
                  "Clients ( https://console.cloud.google.com/auth/clients ): Create client, Application type Web application, Name UAply web.",
                  "Authorized JavaScript origins (no path, no slash at the end): " + "  ".join(LIVE_ORIGINS + [o for o in origins(host, proto) if o not in LIVE_ORIGINS]) + " . Google treats localhost and 127.0.0.1 as different addresses, so open this app at localhost.",
                  "Authorized redirect URIs (exactly, with the path): " + "  ".join(o + CALLBACK for o in LIVE_ORIGINS + [o for o in origins(host, proto) if o not in LIVE_ORIGINS and not o.endswith("://localhost")]) + " .",
                  "Press Create and copy the Client ID (ends in .apps.googleusercontent.com) and the Client secret (starts with GOCSPX-). Google shows the secret in full only now: download the JSON or keep it somewhere safe. Never paste the secret into a chat or a page.",
                  "On Render (uaply-dev, Environment, UAPLY_CONFIG_JSON) add the google part with the client ID and the secret inside the existing { } (the exact line to copy is in DEPLOY.md, section 3), then Save, rebuild and deploy. The log line must say Google sign-in: on. On this computer, run python tools/setup-config.py to save both, or paste only the client ID in the Connect Google box below."] if not g_ok else []},
        {"name": "Email sending (password resets, receipts, copies)", "ok": smtp_ok,
         "detail": ("An email login is set. Use the button below to send yourself a test." if smtp_ok else
                    "Off. Until this is set, emails go only to the simulated test inbox (/outbox) and password reset links cannot reach real people."),
         "todo": ["Open https://myaccount.google.com/signinoptions/two-step-verification and turn on 2-Step Verification for the Gmail that will send UAply's email (Google requires it for app passwords).",
                  "Open https://myaccount.google.com/apppasswords, name it UAply and press Create. Google shows a 16-letter code once; copy it.",
                  "Paste that Gmail address and the code in the Connect Gmail box below. A test email goes out right away."] if not smtp_ok else []},
        {"name": "Apply instantly (employers' hiring systems)", "ok": bool(connections()),
         "detail": ("Connected: " + ", ".join("%s/%s" % c for c in connections()) + ". Their postings say Apply instantly.") if connections() else
                   "Off. No employer has connected yet, so swipe right on a real job opens the employer's own page. See EMPLOYERS.md for how an employer connects.",
         "todo": ["Ask the employer to create a Greenhouse Job Board API key or a Lever Postings API key (EMPLOYERS.md says where).",
                  "Paste it in the Connect an employer's hiring system box below, with the board name from their job-board address.",
                  "Set delivery to live in the settings (UAPLY_CONFIG_JSON on a host) so applications are really sent."] if not connections() else []},
        {"name": "Payments for Plus and Pro (Stripe)", "ok": billing_api.settings()["on"] and bool(billing_api.settings().get("webhook_secret")),
         "detail": ("On, in %s mode." % ("TEST" if billing_api.settings()["test"] else "LIVE")) if billing_api.settings()["on"] else "Off. Plans show, but Choose says payments are not switched on yet.",
         "todo": ["Create a Stripe account at https://dashboard.stripe.com/register (start in test mode).",
                  "Product catalog: add a product Plus with a monthly price of 9.99 USD and a product Pro at 19.99 USD. Copy both price ids (price_...).",
                  "Developers, API keys: copy the secret key (sk_test_...).",
                  "Developers, Webhooks: Add destination, Your account, the events " + ", ".join(billing_api.EVENTS) + ", Webhook endpoint, URL " + proto + "://" + host + "/api/billing/webhook ; copy its signing secret (whsec_...). On this computer use the Stripe CLI: stripe listen --forward-to " + host + "/api/billing/webhook.",
                  "Settings, Billing, Customer portal: turn it on so people can update their card, switch between Plus and Pro, see invoices and cancel at the end of the period.",
                  "Paste the four values in the Connect Stripe box below. The full go-live checklist (live keys, Radar rules, test cards) is in DEPLOY.md, section 4."] if not billing_api.settings()["on"] else
                 (["The webhook signing secret is missing: people could pay and never get their plan. Add STRIPE_WEBHOOK_SECRET (whsec_...)."] if not billing_api.settings().get("webhook_secret") else []) +
                 (["TEST keys on a public server: anyone can get a plan with Stripe's test card 4242 4242 4242 4242. Use live keys on the real site (DEPLOY.md, section 4)."] if billing_api.settings()["test"] and billing_api.PUBLIC else [])},
        {"name": "Copy of every application to you", "ok": bool(owner),
         "detail": ("Every swipe right is also emailed to " + owner + (" once email sending is on." if not smtp_ok else ".")) if owner else "Off. Set owner_copy to your email.",
         "todo": [] if owner else ["Run: python tools/setup-config.py and enter your email when it asks."]},
        {"name": "More jobs: USAJOBS and The Muse keys", "ok": all(feed_status().values()),
         "detail": "USAJOBS key: %s. The Muse key: %s. Without the USAJOBS key federal jobs are skipped; without The Muse key its jobs still load, but its terms ask for one." % (
             "saved" if feed_status()["usajobs"] else "not added yet", "saved" if feed_status()["muse"] else "not added yet"),
         "todo": [t for t, need in (
             ("Request a free USAJOBS key at https://developer.usajobs.gov/APIRequest/ (name, the email you will use, and what UAply does). The key arrives by email.", not feed_status()["usajobs"]),
             ("Register a free The Muse key at https://www.themuse.com/developers/api/v2 (it asks you to sign in to The Muse).", not feed_status()["muse"]),
             ("Paste them in the Job feed keys box below.", not all(feed_status().values()))) if need]},
        {"name": "AI answers in UAply Assistant (optional)", "ok": _real(cfg.get("anthropic_api_key"), ("optional", "sk-ant-...")) and str(cfg.get("anthropic_api_key")).startswith("sk-ant-"),
         "detail": "Without a key the assistant answers with the best matching help article.", "todo": []},
    ]


def save_google(payload):
    """The "Connect Google" box: save the public Google client ID into the git-ignored uaply-config.json on this computer. Returns (status, body)."""
    cid = (payload.get("client_id") if isinstance(payload.get("client_id"), str) else "").strip()
    if not CLIENT_RE.match(cid):
        return 400, {"ok": False, "message": "That does not look like a Google client ID. It ends in .apps.googleusercontent.com and starts with numbers and a dash."}
    if _test_run():
        return 409, dict(TEST_RUN)
    try:
        with open(uaply_api.CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    g = cfg.get("google") if isinstance(cfg.get("google"), dict) else {}
    g["client_id"] = cid
    cfg["google"] = g
    tmp = uaply_api.CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline=chr(10)) as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, uaply_api.CONFIG_PATH)
    return 200, {"ok": True, "saved": True, "message": "Saved. Reload the sign-in screen: Google's button should now appear."}


def _read_partners(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_partners(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline=chr(10)) as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def connections():
    """The connected hiring systems as (kind, board) pairs. Never the keys."""
    return sorted(jobs_api.ats_connections())


def save_ats(payload):
    """The "Connect an employer's hiring system" box: store the key the employer gave us in the git-ignored employer list on this computer. (status, body)."""
    kind = str(payload.get("kind") or "").strip().lower()
    board = str(payload.get("board") or "").strip()
    key = str(payload.get("api_key") or "").strip()
    if not ats_api.valid_connection(kind, board, key):
        return 400, {"ok": False, "message": "Choose Greenhouse, Lever, Ashby or SmartRecruiters, give the board name from the employer's job-board address (letters, numbers, - and _), and paste the key they created."}
    path = jobs_api.partners_file(for_writing=True)
    data = _read_partners(path)
    keep = [c for c in (data.get("ats_connections") or []) if isinstance(c, dict) and (c.get("kind"), c.get("board")) != (kind, board)]
    keep.append({"kind": kind, "board": board, "api_key": key})
    data["ats_connections"] = keep
    _write_partners(path, data)
    return 200, {"ok": True, "saved": True, "message": "Connected. Real %s postings from %s now say Apply instantly, and a swipe right sends the application into their system." % (ats_api.NAMES[kind], board)}


def remove_ats(payload):
    kind, board = str(payload.get("kind") or "").strip().lower(), str(payload.get("board") or "").strip()
    path = jobs_api.partners_file(for_writing=True)
    data = _read_partners(path)
    before = data.get("ats_connections") or []
    data["ats_connections"] = [c for c in before if isinstance(c, dict) and (c.get("kind"), c.get("board")) != (kind, board)]
    if len(data["ats_connections"]) != len(before):
        _write_partners(path, data)
    return 200, {"ok": True, "message": "Disconnected."}


def save_stripe(payload):
    """The "Connect Stripe" box: save the Stripe keys and the two price ids into the git-ignored uaply-config.json on this computer. (status, body)."""
    g = lambda k: (payload.get(k) if isinstance(payload.get(k), str) else "").strip()
    key, wh, plus, pro = g("secret_key"), g("webhook_secret"), g("price_plus"), g("price_pro")
    if not re.match(r"^sk_(test|live)_[A-Za-z0-9]{8,}$", key):
        return 400, {"ok": False, "message": "The secret key starts with sk_test_ (test mode) or sk_live_. Find it in Stripe, Developers, API keys."}
    if not (plus.startswith("price_") and pro.startswith("price_")):
        return 400, {"ok": False, "message": "Paste the two price ids (they start with price_) of the monthly Plus and Pro prices you made in Stripe, Product catalog."}
    if wh and not wh.startswith("whsec_"):
        return 400, {"ok": False, "message": "The webhook signing secret starts with whsec_."}
    if _test_run():
        return 409, dict(TEST_RUN)
    try:
        with open(uaply_api.CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    old = cfg.get("stripe") if isinstance(cfg.get("stripe"), dict) else {}
    cfg["stripe"] = {"secret_key": key, "webhook_secret": wh or old.get("webhook_secret", ""), "price_plus": plus, "price_pro": pro}
    tmp = uaply_api.CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline=chr(10)) as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, uaply_api.CONFIG_PATH)
    return 200, {"ok": True, "saved": True, "message": "Saved. Plus and Pro can now be bought in Profile, Plan and billing" + ("" if cfg["stripe"]["webhook_secret"] else "; add the webhook signing secret so plans switch on after payment") + "."}


FEED_NAMES = {"usajobs": "USAJOBS key", "muse": "The Muse key"}


def feed_status():
    """Which job feed keys are set (in uaply-config.json or the host's UAPLY_CONFIG_JSON). Only yes or no; a key is never read back out."""
    k = uaply_api.config().get("feed_keys")
    k = k if isinstance(k, dict) else {}
    return {n: isinstance(k.get(n), str) and bool(jobs_api.KEY_RE.match(k[n].strip())) for n in FEED_NAMES}


def save_feed_keys(payload):
    """The "Job feed keys" box: save the USAJOBS and The Muse API keys (and the email the USAJOBS key was requested with) into the
    git-ignored uaply-config.json on this computer, under "feed_keys". A blank field keeps what is saved; "remove" drops a key.
    The keys are never sent back, never logged and never shown on the page again (it only says "saved"). Returns (status, body)."""
    g = lambda k: "".join((payload.get(k) if isinstance(payload.get(k), str) else "").split())      # noqa: E731  (pasted keys may carry spaces or a line break)
    new = {n: g(n) for n in FEED_NAMES if g(n)}
    mail = (payload.get("usajobs_email") if isinstance(payload.get("usajobs_email"), str) else "").strip()
    remove = [n for n in (payload.get("remove") if isinstance(payload.get("remove"), list) else []) if n in FEED_NAMES]
    for n, v in new.items():
        if not jobs_api.KEY_RE.match(v):
            return 400, {"ok": False, "message": "That does not look like a %s. Paste the whole key from the email or page it came on (letters and digits, 16 or more)." % FEED_NAMES[n]}
    if mail and not uaply_api.EMAIL_RE.match(mail):
        return 400, {"ok": False, "message": "The USAJOBS email is not a valid email address. Use the one you requested the key with."}
    if not (new or mail or remove):
        return 400, {"ok": False, "message": "Paste at least one key."}
    try:
        with open(uaply_api.CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    fk = cfg.get("feed_keys") if isinstance(cfg.get("feed_keys"), dict) else {}
    fk.update(new)
    if mail:
        fk["usajobs_email"] = mail
    for n in remove:
        fk.pop(n, None)
    cfg["feed_keys"] = fk
    tmp = uaply_api.CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline=chr(10)) as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, uaply_api.CONFIG_PATH)
    said = [FEED_NAMES[n] for n in FEED_NAMES if n in new] + (["USAJOBS email"] if mail else [])
    gone = [FEED_NAMES[n] for n in remove]
    return 200, {"ok": True, "saved": True, "message": " ".join(x for x in (
        ("Saved: %s. New jobs appear on the next refresh of the job list." % ", ".join(said)) if said else "",
        ("Removed: %s." % ", ".join(gone)) if gone else "") if x)}


BREVO_KEY_RE = re.compile(r"^xsmtpsib-[A-Za-z0-9-]{20,200}$")


def save_mail(payload):
    """The "Connect email" form: save how UAply sends email into the git-ignored uaply-config.json on this computer, then send a test.
    Gmail: the Gmail address and its App Password. Brevo: the address mail comes from (one whose domain Brevo has verified, such as
    an @uaply.net address), Brevo's SMTP login and an SMTP key. The password or key is never echoed back and never goes anywhere
    except that provider's own mail server. Returns (status, body)."""
    provider = "brevo" if payload.get("provider") == "brevo" else "gmail"
    addr = payload.get("email") if isinstance(payload.get("email"), str) else ""
    pw = "".join((payload.get("password") if isinstance(payload.get("password"), str) else "").split())      # Google shows it in groups of four
    login = (payload.get("login") if isinstance(payload.get("login"), str) else "").strip()
    copy_to = payload.get("copy_to") if isinstance(payload.get("copy_to"), str) else ""
    if not uaply_api.EMAIL_RE.match(addr.strip()):
        return 400, {"ok": False, "message": ("Enter the address UAply's email comes from, such as uaplytechnologies@uaply.net." if provider == "brevo"
                                              else "Enter the Gmail address that will send UAply's email.")}
    if provider == "brevo":
        if not uaply_api.EMAIL_RE.match(login):
            return 400, {"ok": False, "message": "Enter the SMTP login from Brevo (SMTP & API, SMTP tab). It looks like an email address ending in @smtp-brevo.com."}
        if not BREVO_KEY_RE.match(pw):
            return 400, {"ok": False, "message": "That does not look like a Brevo SMTP key. In Brevo, open SMTP & API, SMTP tab, and generate a new SMTP key (it starts with xsmtpsib-)."}
    elif not (12 <= len(pw) <= 64) or not pw.isalnum():
        return 400, {"ok": False, "message": "That does not look like a Gmail App Password (16 letters, shown in four groups). Create one at myaccount.google.com/apppasswords."}
    if copy_to.strip() and not uaply_api.EMAIL_RE.match(copy_to.strip()):
        return 400, {"ok": False, "message": "The address for copies is not a valid email."}
    if _test_run():
        return 409, dict(TEST_RUN)
    try:
        with open(uaply_api.CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    smtp = cfg.get("smtp") if isinstance(cfg.get("smtp"), dict) else {}
    if provider == "brevo":
        smtp.update({"host": "smtp-relay.brevo.com", "port": 587, "starttls": True, "user": login, "from_addr": addr.strip(), "password": pw})
    else:
        smtp.update({"host": "smtp.gmail.com", "port": 587, "starttls": True, "user": addr.strip(), "from_addr": addr.strip(), "password": pw})
    cfg["smtp"] = smtp
    if copy_to.strip():
        cfg["owner_copy"] = copy_to.strip()
    tmp = uaply_api.CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline=chr(10)) as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, uaply_api.CONFIG_PATH)
    status, out = test_mail()
    out["saved"] = True
    return status, out


def test_mail():
    """Send one email to the owner. Returns (status, body)."""
    cfg = uaply_api.config()
    s = cfg.get("smtp") if isinstance(cfg.get("smtp"), dict) else {}
    to = uaply_api._owner_copy(cfg) or (s.get("from_addr") or "")
    if not (s.get("host") and s.get("from_addr")):
        return 200, {"ok": False, "message": "Email sending is not set up yet. Fill in the Connect email box on this page first."}
    if not uaply_api.mail_ready():
        return 200, {"ok": False, "message": "Email sending has no password or key yet. Add one in the Connect email box on this page."}
    if not to:
        return 200, {"ok": False, "message": "No address to send the test to."}
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s["from_addr"], to, "UAply test email"
    msg.set_content("This is a test from UAply's setup page. If you can read it, UAply can send email: password resets, "
                    "receipts and your copy of every application will work.")
    try:
        with smtplib.SMTP(s["host"], int(s.get("port", 587)), timeout=20) as srv:
            if s.get("starttls", True):
                srv.starttls()
            if s.get("user"):
                srv.login(s["user"], s.get("password", ""))
            srv.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        if "brevo" in (s.get("host") or ""):
            why = (" Brevo may be blocking this computer's internet address: in Brevo, open Security, Authorized IPs, and allow it (or turn off IP blocking for SMTP)."
                   if "525" in str(e) or "ip" in str(e).lower() else "")
            return 200, {"ok": False, "message": "Brevo refused the login. Check the SMTP login and key in Brevo (SMTP & API, SMTP tab)." + why}
        return 200, {"ok": False, "message": "Gmail refused the login. Use an App Password (not your normal password), with 2-Step Verification on."}
    except smtplib.SMTPServerDisconnected:
        return 200, {"ok": False, "message": "The mail server closed the connection. Check the host and port, and that the App Password is right."}
    except (OSError, smtplib.SMTPException) as e:
        return 200, {"ok": False, "message": "Could not send: " + type(e).__name__}
    return 200, {"ok": True, "message": "Sent to " + to + ". Check that inbox."}


def page(host, proto):
    e = html.escape
    rows = []
    found = checks(host, proto)
    for c in found:
        todo = "".join("<li>%s</li>" % _linkify(t) for t in c["todo"])
        rows.append('<article><header><span class="b %s">%s</span><b>%s</b></header><p class="m">%s</p>%s</article>' % (
            "ok" if c["ok"] else "no", "ON" if c["ok"] else "TO DO", e(c["name"]), e(c["detail"]), ("<ol>%s</ol>" % todo) if todo else ""))
    if not (found[0]["ok"] and found[1]["ok"]):          # Google sign-in and real email are the two things that turn test mode into the real thing
        rows.insert(0, '<article><b>Why you still see the test inbox and a test sign-in</b><p class="m">Until the first two items below are connected, this computer cannot show Google\'s real account chooser '
                       'and cannot send real email, so sign-up codes and receipts are saved in the <a href="/outbox">test inbox</a> instead. Connect both and the app behaves like the live site: '
                       'Google\'s own "Continue with Google" button, and real emails in real inboxes.</p></article>')
    conn_html = "".join('<p class="m">%s / %s <button type="button" class="rm" data-k="%s" data-b="%s">Disconnect</button></p>' % (e(ats_api.NAMES.get(k, k)), e(b), e(k), e(b)) for k, b in connections()).replace("%", "%%")
    fs = feed_status()
    feeds_html = ("".join('<p class="m">%s: <b>%s</b>%s</p>' % (e(label), "saved" if fs[n] else "not added yet",
                                                                 (' <button type="button" class="fx" data-n="%s">Remove</button>' % n) if fs[n] else "")
                          for n, label in FEED_NAMES.items())).replace("%", "%%")
    feeds_help = _linkify("USAJOBS lists every federal job near Philadelphia, internships included: request a free key at https://developer.usajobs.gov/APIRequest/ "
                          "(it arrives by email; give the email you used below). The Muse asks every app to register: get a key at https://www.themuse.com/developers/api/v2 . "
                          "Keys are saved only in uaply-config.json on this computer and are never shown again. On a hosted server, put them in UAPLY_CONFIG_JSON "
                          "as feed_keys instead.").replace("%", "%%")
    here = origins(host, proto)
    every = here + [o for o in LIVE_ORIGINS if o not in here]
    copy = '<p><code>%s</code> <button type="button" class="cp" data-v="%s">Copy</button></p>'
    origin_html = (''.join(copy % (e(o), e(o)) for o in every) + '<p class="m">Authorized redirect URIs:</p>' +
                   ''.join(copy % (e(o + CALLBACK), e(o + CALLBACK)) for o in every if not o.endswith("://localhost"))).replace("%", "%%")
    try:
        n = auth_api.counts()
    except Exception:
        n = {"users": 0, "mail": 0}
    return ("""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>UAply setup</title><style>
:root{--bg:#FDF0F2;--surface:#FFFFFF;--ink:#2A1218;--muted:#7B5560;--line:#F3DADF;--accent:#C92A55;--good:#1E7A4C}
@media (prefers-color-scheme: dark){:root{--bg:#190B10;--surface:#26131A;--ink:#FBE9EE;--muted:#C79BA6;--line:#40222B;--accent:#FF7A98;--good:#5FD39A}}
body{margin:0;padding:16px;background:var(--bg);color:var(--ink);font:15px/1.5 'DM Sans','Segoe UI',system-ui,sans-serif}
main{max-width:760px;margin:auto;display:flex;flex-direction:column;gap:12px}h1{margin:0;font-size:22px}.m{color:var(--muted);margin:6px 0 0}
article{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:12px 14px}
header{display:flex;gap:8px;align-items:center}.b{font:700 11px ui-monospace,Menlo,monospace;padding:2px 7px;border-radius:6px;color:#fff}
.b.ok{background:var(--good)}.b.no{background:var(--accent)}ol{margin:8px 0 0;padding-left:20px}li{margin:4px 0}
button{font:inherit;padding:8px 14px;border-radius:10px;border:1px solid var(--line);background:var(--surface);color:var(--ink);cursor:pointer}
code{background:var(--bg);padding:1px 5px;border-radius:5px}
</style></head><body><main><h1>UAply setup</h1><p class="m">What is switched on, and what still needs a key. Secrets are never shown here.</p>
%s
<article id="google"><b>Connect Google sign-in</b><p class="m">Google needs to be told which addresses may use sign-in. Add each of these under Authorized JavaScript origins (and the same followed by /api/auth/google/callback under Authorized redirect URIs):</p>@@ORIGINS@@
<p class="m">Then paste the Client ID from Google Auth Platform, Clients (the long address ending in .apps.googleusercontent.com). It is public, so it is safe to paste here. It is saved only on this computer. The client secret (GOCSPX-...) never goes in a page: on this computer run python tools/setup-config.py, and on the hosted site put it in UAPLY_CONFIG_JSON. With the secret, every device uses Google's full-page sign-in.</p>
<p><input id="gi" type="text" placeholder="123456789-abc.apps.googleusercontent.com" style="width:340px;max-width:90vw;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p><button id="gs" type="button">Save Google client ID</button> <span id="gr" class="m" role="status"></span></p></article>
<article id="gmail"><b>Connect email (Brevo or Gmail)</b><p class="m">How UAply sends sign-up codes, receipts and applications. <b>Brevo</b> sends from your own domain (for example uaplytechnologies@uaply.net): paste that address, Brevo's SMTP login and an SMTP key from Brevo, SMTP &amp; API, SMTP tab. <b>Gmail</b>: paste the Gmail address and its App Password (a 16-letter code from myaccount.google.com/apppasswords, not your normal password). It is saved only in uaply-config.json on this computer, which is never uploaded, and a test email is sent right away.</p>
<p><select id="gv" aria-label="Email provider" style="padding:8px;border:1px solid var(--line);border-radius:8px"><option value="brevo">Brevo (your own domain)</option><option value="gmail">Gmail</option></select></p>
<p><input id="ge" type="email" placeholder="Send from, e.g. uaplytechnologies@uaply.net" style="width:280px;max-width:90vw;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p id="glw"><input id="gl" type="text" placeholder="Brevo SMTP login (ends in @smtp-brevo.com)" autocomplete="off" style="width:280px;max-width:90vw;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p><input id="gp" type="password" placeholder="Brevo SMTP key or Gmail App Password" autocomplete="off" style="width:280px;max-width:90vw;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p><input id="gc" type="email" placeholder="Send copies and tests to (optional)" style="width:280px;max-width:90vw;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p><button id="sv" type="button">Save and send a test email</button> <span id="sr" class="m" role="status"></span></p></article>
<article id="ats"><b>Connect an employer's hiring system</b><p class="m">For an employer that uses Greenhouse, Lever, Ashby or SmartRecruiters and gave you the key they created. Their real postings then say <b>Apply instantly</b>. The key is saved only in uaply-partners.json on this computer and is never shown again.</p>
<p class="m">Where the employer makes the key: <b>Greenhouse</b> Configure, Dev Center, API Credential Management (a Job Board API key). <b>Lever</b> Settings, Integrations and API (a Postings API key, made by a Super Admin). <b>Ashby</b> Admin, Integrations, API Keys (a key with the Candidates write and Jobs read permissions). <b>SmartRecruiters</b> Settings, Admin, Credential Manager (an Application API key). The board name is the one in the employer's job-board address: boards.greenhouse.io/<i>board</i>, jobs.lever.co/<i>site</i>, jobs.ashbyhq.com/<i>board</i> or jobs.smartrecruiters.com/<i>company</i>.</p>
<p><select id="ak" aria-label="Hiring system" style="padding:8px;border:1px solid var(--line);border-radius:8px"><option value="greenhouse">Greenhouse</option><option value="lever">Lever</option><option value="ashby">Ashby</option><option value="smartrecruiters">SmartRecruiters</option></select>
<input id="ab" type="text" placeholder="Board name, e.g. acme" style="width:200px;max-width:50vw;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p><input id="aa" type="password" placeholder="The employer's API key" autocomplete="off" style="width:280px;max-width:90vw;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p><button id="as" type="button">Connect</button> <span id="ar" class="m" role="status"></span></p>
@@CONNS@@</article>
<article id="billing"><b>Connect Stripe (Plus and Pro)</b><p class="m">Saved only in uaply-config.json on this computer. Card numbers never reach UAply; people pay on Stripe's page.</p>
<p><input id="ss" type="password" placeholder="Secret key sk_test_..." autocomplete="off" style="width:280px;max-width:90vw;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p><input id="sw" type="password" placeholder="Webhook signing secret whsec_..." autocomplete="off" style="width:280px;max-width:90vw;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p><input id="sp1" type="text" placeholder="Plus price id price_..." style="width:200px;padding:8px;border:1px solid var(--line);border-radius:8px"> <input id="sp2" type="text" placeholder="Pro price id price_..." style="width:200px;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p><button id="sb" type="button">Save Stripe</button> <span id="sbr" class="m" role="status"></span></p></article>
<article id="feeds"><b>Job feed keys</b><p class="m">@@FEEDHELP@@</p>
@@FEEDS@@
<p><input id="fu" type="password" placeholder="USAJOBS API key" autocomplete="off" style="width:280px;max-width:90vw;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p><input id="fe" type="email" placeholder="Email you requested the USAJOBS key with (optional)" style="width:280px;max-width:90vw;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p><input id="fm" type="password" placeholder="The Muse API key" autocomplete="off" style="width:280px;max-width:90vw;padding:8px;border:1px solid var(--line);border-radius:8px"></p>
<p><button id="fs" type="button">Save feed keys</button> <span id="fr" class="m" role="status"></span></p></article>
<article><b>Send a test email</b><p class="m">Sends one message to your copy address so you can see that real email works.</p>
<p><button id="t" type="button">Send test email</button> <span id="r" class="m" role="status"></span></p></article>
<p class="m">%d accounts and %d emails recorded on this server. <a href="/outbox">Test inbox</a></p></main>
<script>document.getElementById('t').onclick=function(){var r=document.getElementById('r');r.textContent='Sending...';
fetch('/api/setup/test-mail',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(function(x){return x.json()}).then(function(j){r.textContent=j.message||j.error||'Done'}).catch(function(){r.textContent='Could not reach the server.'})}
document.getElementById('gs').onclick=function(){var r=document.getElementById('gr');r.textContent='Saving...';
fetch('/api/setup/save-google',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:document.getElementById('gi').value})}).then(function(x){return x.json()}).then(function(j){r.textContent=j.message||j.error||'Done'}).catch(function(){r.textContent='Could not reach the server.'})}
document.getElementById('sv').onclick=function(){var r=document.getElementById('sr'),g=function(i){return document.getElementById(i).value};r.textContent='Saving...';
fetch('/api/setup/save-mail',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:g('gv'),email:g('ge'),login:g('gl'),password:g('gp'),copy_to:g('gc')})}).then(function(x){return x.json()}).then(function(j){if(j.saved)document.getElementById('gp').value='';r.textContent=j.message||j.error||'Done'}).catch(function(){r.textContent='Could not reach the server.'})}
;(function(){var v=document.getElementById('gv'),w=document.getElementById('glw');function sync(){w.hidden=v.value!=='brevo'}v.onchange=sync;sync()})();
document.getElementById('as').onclick=function(){var r=document.getElementById('ar'),g=function(i){return document.getElementById(i).value};r.textContent='Saving...';
fetch('/api/setup/save-ats',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:g('ak'),board:g('ab'),api_key:g('aa')})}).then(function(x){return x.json()}).then(function(j){if(j.saved){document.getElementById('aa').value='';setTimeout(function(){location.reload()},900)}r.textContent=j.message||j.error||'Done'}).catch(function(){r.textContent='Could not reach the server.'})}
document.querySelectorAll('.rm').forEach(function(b){b.onclick=function(){fetch('/api/setup/remove-ats',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:b.getAttribute('data-k'),board:b.getAttribute('data-b')})}).then(function(){location.reload()})}})
document.getElementById('sb').onclick=function(){var r=document.getElementById('sbr'),g=function(i){return document.getElementById(i).value};r.textContent='Saving...';
fetch('/api/setup/save-stripe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({secret_key:g('ss'),webhook_secret:g('sw'),price_plus:g('sp1'),price_pro:g('sp2')})}).then(function(x){return x.json()}).then(function(j){if(j.saved){document.getElementById('ss').value='';document.getElementById('sw').value=''}r.textContent=j.message||j.error||'Done'}).catch(function(){r.textContent='Could not reach the server.'})}
document.getElementById('fs').onclick=function(){var r=document.getElementById('fr'),g=function(i){return document.getElementById(i).value};r.textContent='Saving...';
fetch('/api/setup/save-feed-keys',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({usajobs:g('fu'),usajobs_email:g('fe'),muse:g('fm')})}).then(function(x){return x.json()}).then(function(j){if(j.saved){document.getElementById('fu').value='';document.getElementById('fm').value='';setTimeout(function(){location.reload()},900)}r.textContent=j.message||j.error||'Done'}).catch(function(){r.textContent='Could not reach the server.'})}
document.querySelectorAll('.fx').forEach(function(b){b.onclick=function(){fetch('/api/setup/save-feed-keys',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({remove:[b.getAttribute('data-n')]})}).then(function(){location.reload()})}})
document.querySelectorAll('.cp').forEach(function(b){b.onclick=function(){var v=b.getAttribute('data-v');(navigator.clipboard?navigator.clipboard.writeText(v):Promise.reject()).then(function(){b.textContent='Copied'},function(){b.textContent='Select the address and copy it'})}})</script>
</body></html>""".replace("@@ORIGINS@@", origin_html).replace("@@CONNS@@", conn_html).replace("@@FEEDS@@", feeds_html).replace("@@FEEDHELP@@", feeds_help) % ("".join(rows), n["users"], n["mail"])).encode("utf-8")
