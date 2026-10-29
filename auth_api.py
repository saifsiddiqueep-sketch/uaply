"""Accounts for the sandbox and dev instances: sign up, log in, log out, delete the account, and "who am I".

Where it keeps things: a SQLite file at data/<instance>/uaply.db (git-ignored, never committed).
  users      email (unique), salted password hash, created and last-login times, when Terms were accepted
  sessions   hashed session tokens with an expiry
  user_mail  the receipts UAply sends to applicants (simulated in test mode)
  identities "Continue with Google" logins: provider + the provider's stable user id, linked to a user
  password_resets  hashed one-time "forgot password" tokens (1 hour, single use)
  email_codes      the 6-digit code that proves a password account owns its email (10 minutes, 5 tries, single use, stored hashed)

How it keeps them safe:
  * Passwords are never stored. Only a per-user random salt and a PBKDF2-HMAC-SHA256 hash (600,000 rounds).
  * A session token is 32 random bytes. The browser holds the token in an HttpOnly cookie; the database holds only
    its SHA-256 hash, so a leaked database cannot be used to log in.
  * Login and sign-up are rate limited, unknown emails cost the same time as known ones, and the error for a bad
    login never says which part was wrong.
  * All SQL uses bound parameters.

Sign-up requires confirming the person is 18 or older and accepts the Terms and Privacy Policy (stored as terms_at).
Deleting an account needs the password again and removes the user, their sessions and their receipts; the server
also forgets their application records (see uaply_api.forget_user). App stores require in-app deletion.

Password reset: request_reset() emails a one-hour, single-use link; reset_password() sets the new password, ends every
session of that account and works for Google-only accounts too (it then gains a password).

Wrong passwords: 5 per connection and account, and 20 per account from all connections together, in 15 minutes (the second
limit holds even when a visitor makes up a new address for every try).

Email verification: a new password account gets a 6-digit code by email (email_codes above); a "Continue with Google" account
counts as verified only when Google is the authority on that address (see oauth_login).

One address, one account (docs/ACCOUNTS.md has the reasoning): every address is stored and compared only as canonical_email() makes it
(NFKC, trimmed, lower-case, plain ASCII, no spaces or control characters), the users table refuses a second row with the same address
in any letter case, and sign-up, log-in, Forgot password, the code and Google all look accounts up through that one key. Dots and
+tags are NOT folded: owner+live1@gmail.com and owner@gmail.com are two accounts, because only the inbox's owner can verify either.
A new account also needs an address that can receive mail: privacy relays always pass (tools/data/relay-domains.txt), throwaway domains
never do (tools/data/disposable-domains.txt), and on a server that sends email the domain must have a mail server or an address in DNS
(mail_domain_status, asked over DNS over HTTPS; a DNS failure never blocks anyone). At most 5 new accounts per visitor address an hour.

A hosted database (instead of this file) is a later step: this module is the stand-in that already behaves like one.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
# every domain label starts and ends with a letter or digit, so a@example..com, a@.example.com and a@-x.com are refused (item 19)
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}$")
ITER = 600000
SESSION_SECONDS = 30 * 86400
MAX_FAILS = 5
FAIL_WINDOW = 15 * 60
# Wrong passwords for one account from ALL connections together. The 5-per-connection limit above trusts the address the visitor's
# connection reports, and behind a host's proxy a visitor can make that up for every try. This second limit cannot be dodged that way.
# It is set high enough that a stranger cannot easily lock someone out, and Forgot password and Google still work during it.
MAX_EMAIL_FAILS = 20

_lock = threading.RLock()
_path = ""
_name = "default"
_fails = {}      # (ip, email) -> [timestamps of recent failed logins]
_signups = {}    # ip -> [timestamps of recent sign-ups]
_resets = {}     # ip or email -> [timestamps of recent reset requests]
RESET_SECONDS = 3600
_DUMMY_SALT = b"\x00" * 16


def cookie_name():
    return "uaply_%s_session" % _name


def init(instance):
    """Each instance (sandbox, dev) keeps its own accounts in data/<instance>/uaply.db."""
    global _path, _name
    _name = re.sub(r"[^A-Za-z0-9_-]", "", instance) or "default"
    folder = os.path.join(os.environ.get("UAPLY_DATA_DIR") or os.path.join(ROOT, "data"), _name)
    os.makedirs(folder, exist_ok=True)
    _path = os.path.join(folder, "uaply.db")
    with _lock, _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            salt BLOB NOT NULL,
            hash BLOB NOT NULL,
            created_at INTEGER NOT NULL,
            last_login INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS user_mail(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            to_addr TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL,
            at INTEGER NOT NULL);
        """)
        c.execute("""CREATE TABLE IF NOT EXISTS identities(
            provider TEXT NOT NULL,
            subject TEXT NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY(provider, subject))""")
        c.execute("""CREATE TABLE IF NOT EXISTS password_resets(
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS email_codes(
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS stripe_events(
            id TEXT PRIMARY KEY,
            at INTEGER NOT NULL)""")                     # Stripe event ids already handled (billing_api.webhook), so a resent event is done once
        c.execute(CONSENTS_TABLE)                      # the first-swipe agreement, one row each time it is given (consent_api.py)
        for col in ("terms_at INTEGER", "has_password INTEGER NOT NULL DEFAULT 1", "email_verified INTEGER NOT NULL DEFAULT 0",
                    "first_name TEXT NOT NULL DEFAULT ''", "last_name TEXT NOT NULL DEFAULT ''",
                    "plan TEXT NOT NULL DEFAULT 'free'", "plan_status TEXT NOT NULL DEFAULT ''", "plan_renews INTEGER NOT NULL DEFAULT 0",
                    "plan_cancel INTEGER NOT NULL DEFAULT 0", "stripe_customer TEXT NOT NULL DEFAULT ''", "stripe_sub TEXT NOT NULL DEFAULT ''",
                    "plan_failed INTEGER NOT NULL DEFAULT 0", "plan_interval TEXT NOT NULL DEFAULT 'month'",   # month or year (billing_api)
                    "never_send INTEGER NOT NULL DEFAULT 0",   # a test account (uaply_api.never_send)
                    # Send applications for me (Profile, Account; Terms section 3): on unless the person turns it off; off, every swipe right
                    # only saves the job to Job Tracker (uaply_api.submit). send_for_me_at: when it was last changed
                    "send_for_me INTEGER NOT NULL DEFAULT 1", "send_for_me_at INTEGER NOT NULL DEFAULT 0"):      # databases made before these columns existed
            try:
                c.execute("ALTER TABLE users ADD COLUMN " + col)
            except sqlite3.OperationalError:
                pass
        c.execute("UPDATE users SET email_verified=1 WHERE id IN (SELECT user_id FROM identities)")      # Google already verified those emails
        # A second safety net under canonical_email(): the database itself refuses two rows whose addresses differ only in letter case
        # (the plain UNIQUE above compares bytes, so it would let Alice@x.com and alice@x.com both in if some future code path forgot
        # to clean the address). A database that already holds such a pair cannot get the index; the server still starts and says so.
        try:
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_nocase ON users(email COLLATE NOCASE)")
        except sqlite3.IntegrityError:
            sys.stderr.write("[uaply] accounts: two accounts share an address in different letter case; run python tools/audit-accounts.py\n")


class _db:
    """A short-lived connection used as a context manager that commits on success."""
    def __enter__(self):
        self.c = sqlite3.connect(_path, timeout=10)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA foreign_keys=ON")
        return self.c

    def __exit__(self, et, ev, tb):
        try:
            if et is None:
                self.c.commit()
        finally:
            self.c.close()
        return False


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, ITER)


def canonical_email(v):
    """The one key an address is stored, compared and rate-limited under, or "" when it is not an address UAply accepts.

    NFKC first, so look-alike forms of the same letters (full-width letters, the Kelvin sign) become the plain letters
    they stand for and cannot open a second account; then trimmed and lower-cased (local part and domain: every mail provider people
    use treats letter case as the same mailbox). After that the address must be plain ASCII with no spaces or control characters:
    internationalised addresses (non-ASCII local parts or domains) are refused rather than guessed at, because two different
    Unicode spellings can look identical and UAply's email sending does not support them. Dots and +tags are kept as typed (see
    docs/ACCOUNTS.md): they are separate accounts."""
    if not isinstance(v, str) or len(v) > 400:
        return ""
    e = unicodedata.normalize("NFKC", v).strip()
    if any(ch.isspace() or unicodedata.category(ch).startswith("C") for ch in e):     # spaces, tabs, line breaks, NUL, zero-width marks
        return ""
    e = e.lower()
    return e if e.isascii() and len(e) <= 254 and EMAIL_RE.fullmatch(e) else ""


_clean_email = canonical_email


# ---------- a mailbox someone can keep: no throwaway domains, and a domain that can receive mail ----------
DISPOSABLE_FILE = os.path.join(ROOT, "tools", "data", "disposable-domains.txt")
RELAY_FILE = os.path.join(ROOT, "tools", "data", "relay-domains.txt")
KEEP_MSG = "Please use an email address you'll keep — temporary addresses can't be used for job applications."
_lists = {}          # file -> (mtime, frozenset of domains)


def _domain_file(path):
    """The domains in one of the tools/data lists (one per line, # starts a comment), lower-cased and without repeats. Read again whenever
    the file changes, so the owner's edits apply without a restart. A missing file is an empty list."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return frozenset()
    hit = _lists.get(path)
    if not hit or hit[0] != mtime:
        with open(path, encoding="utf-8") as f:
            names = {ln.split("#", 1)[0].strip().lower().rstrip(".") for ln in f}
        hit = (mtime, frozenset(n for n in names if n))
        _lists[path] = hit
    return hit[1]


def disposable_domains():
    return _domain_file(DISPOSABLE_FILE)


def relay_domains():
    return _domain_file(RELAY_FILE)


def _listed(email_or_domain, listed):
    """True when the domain, or a domain it sits under (x.mailinator.com, alias.anonaddy.com), is in `listed`."""
    parts = email_or_domain.rpartition("@")[2].lower().split(".")
    return any(".".join(parts[i:]) in listed for i in range(len(parts) - 1))


def is_relay(email_or_domain):
    """A privacy relay (Apple Hide My Email, Firefox Relay, DuckDuckGo, SimpleLogin, addy.io): the mail reaches the person's real inbox,
    so it is never refused, whatever the throwaway list says. Sign in with Apple hands out privaterelay.appleid.com addresses."""
    return _listed(email_or_domain, relay_domains())


def is_disposable(email_or_domain):
    """A throwaway inbox (tools/data/disposable-domains.txt) that is not also a privacy relay."""
    return not is_relay(email_or_domain) and _listed(email_or_domain, disposable_domains())


# Whether a domain can receive mail is asked over DNS over HTTPS (Python has no MX lookup of its own, and a host's port 25 must never be
# probed: Render blocks it and probing gets a server's address blocklisted). Only the domain is sent, never the address.
DOH_URLS = ("https://dns.google/resolve", "https://cloudflare-dns.com/dns-query")
DNS_SECONDS = 3.0                # per resolver
DNS_CACHE_SECONDS = 86400        # a verdict is kept a day, so a burst of sign-ups does not ask again for every one
_dns_cache = {}                  # domain -> (verdict, expires)
_dns_lock = threading.Lock()
_RTYPE = {"MX": 15, "A": 1, "AAAA": 28}


def _doh_urls():
    env = (os.environ.get("UAPLY_DOH_URLS") or "").strip()            # tests point this at a stand-in resolver
    return tuple(u.strip() for u in env.split(",") if u.strip()) if env else DOH_URLS


def _doh(domain, rtype):
    """(DNS status, answers of that type) from the first resolver that answers in time, or None when none did."""
    for base in _doh_urls():
        url = base + ("&" if "?" in base else "?") + urllib.parse.urlencode({"name": domain, "type": rtype})
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/dns-json", "User-Agent": "UAply sign-up check"})
            with urllib.request.urlopen(req, timeout=DNS_SECONDS) as r:
                j = json.loads(r.read(200000).decode("utf-8"))
            if not isinstance(j, dict) or not isinstance(j.get("Status"), int):
                continue
            return j["Status"], [a for a in (j.get("Answer") or []) if isinstance(a, dict) and a.get("type") == _RTYPE[rtype]]
        except Exception:                                    # timeout, refused, not JSON, an HTTP error: try the next resolver
            continue
    return None


def _lookup(domain):
    got = _doh(domain, "MX")
    if got is None:
        return "unknown"
    status, answers = got
    if status == 3:
        return "none"                                        # NXDOMAIN: no such domain
    if status != 0:
        return "unknown"                                     # SERVFAIL and the like: the resolver's problem, not the person's
    if any(str(a.get("data", "")).split()[-1:] != ["."] for a in answers):     # "0 ." is a null MX (RFC 7505): names no mail server
        return "ok"
    for rtype in ("A", "AAAA"):                              # no mail server named: mail goes to the domain's own address (RFC 5321 5.1)
        got = _doh(domain, rtype)
        if got is None:
            return "unknown"
        if got[0] == 0 and got[1]:
            return "ok"
    return "none"


def mail_domain_status(domain):
    """Can this domain receive mail? "ok" (a mail server, or an address mail falls back to), "none" (DNS says it does not exist, or it
    has neither), or "unknown" (no resolver answered within 3 seconds each, or one failed). Unknown always lets the person through and
    writes one line to the log: a DNS hiccup must never turn a real person away. Verdicts are remembered for a day."""
    domain = (domain or "").lower()
    if not domain:
        return "unknown"
    now = time.time()
    with _dns_lock:
        hit = _dns_cache.get(domain)
        if hit and hit[1] > now:
            return hit[0]
    verdict = _lookup(domain)
    if verdict == "unknown":
        sys.stderr.write("[uaply] sign-up: could not check whether %s receives mail (no clear answer from DNS over HTTPS); let it through\n" % domain[:100])
        sys.stderr.flush()
        return verdict
    with _dns_lock:
        if len(_dns_cache) > 20000:
            for k in [k for k, v in _dns_cache.items() if v[1] <= now] or list(_dns_cache)[:5000]:
                del _dns_cache[k]
        _dns_cache[domain] = (verdict, now + DNS_CACHE_SECONDS)
    return verdict


def mailbox_problem(email, check_dns=False):
    """Why this (canonical) address cannot have a new account, as one sentence for the person, or "" when it can. Privacy relays first:
    they always pass. Role addresses (info@, support@) are real mailboxes and pass too."""
    dom = email.rpartition("@")[2]
    if is_relay(dom):
        return ""
    if is_disposable(dom):
        return KEEP_MSG
    if check_dns and mail_domain_status(dom) == "none":
        return "We couldn't find a mail server for %s, so please check the spelling or use an email address you'll keep." % dom
    return ""


def _recent(bucket, key, window):
    now = time.time()
    lst = [t for t in bucket.get(key, []) if now - t < window]
    bucket[key] = lst
    return lst


_pruned = [0.0]


def _prune():
    """Forget rate-limit entries older than an hour, at most once a minute, so a stream of made-up emails or addresses cannot grow
    the server's memory without end. Call with _lock held."""
    now = time.time()
    if now - _pruned[0] < 60:
        return
    _pruned[0] = now
    for bucket in (_fails, _signups, _resets, _code_sends):
        for k in [k for k, v in bucket.items() if not v or now - v[-1] > 3600]:
            del bucket[k]


def _new_session(c, user_id):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    c.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    c.execute("INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES(?,?,?,?)",
              (hashlib.sha256(token.encode()).hexdigest(), user_id, now, now + SESSION_SECONDS))
    return token


def public_user(row):
    keys = row.keys()
    return {"id": row["id"], "email": row["email"], "hasPassword": bool(row["has_password"]), "emailVerified": bool(row["email_verified"]),
            "plan": (row["plan"] if "plan" in keys and row["plan"] in ("free", "plus", "pro") else "free"),
            "first": (row["first_name"] if "first_name" in keys else "") or "", "last": (row["last_name"] if "last_name" in keys else "") or "",
            "sendForMe": bool(row["send_for_me"]) if "send_for_me" in keys else True,
            "termsAt": int(row["terms_at"] or 0) if "terms_at" in keys else 0}     # when this account ticked the Terms (Data and privacy says so)


def clean_name(v):
    """A first or last name as given at sign-up: plain text, at most 60 characters, no control characters, inner spaces kept single."""
    if not isinstance(v, str):
        return ""
    v = unicodedata.normalize("NFKC", v)
    v = "".join(ch for ch in v if not unicodedata.category(ch).startswith("C"))
    return " ".join(v.split())[:60].strip()


def never_send_flag(user_id):
    """The owner's per-account switch (/setup): this account never sends to employers."""
    try:
        with _lock, _db() as c:
            r = c.execute("SELECT never_send FROM users WHERE id=?", (int(user_id),)).fetchone()
        return bool(r and r["never_send"])
    except Exception:
        return False


def set_never_send(email, on):
    """Set the switch by email; True when such an account exists."""
    with _lock, _db() as c:
        n = c.execute("UPDATE users SET never_send=? WHERE email=?", (1 if on else 0, str(email or "").strip().lower())).rowcount
    return n > 0


def billing_row(user_id):
    """The stored subscription of one account, or None."""
    with _db() as c:
        r = c.execute("SELECT id, email, plan, plan_status, plan_renews, plan_cancel, plan_failed, plan_interval, stripe_customer, stripe_sub FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(r) if r else None


EVENT_DAYS = 30          # Stripe resends an event for up to 3 days; ids are kept ten times that long, then forgotten


def stripe_event_seen(event_id):
    """True if this Stripe event id was already handled."""
    with _db() as c:
        return c.execute("SELECT 1 FROM stripe_events WHERE id=?", (str(event_id)[:255],)).fetchone() is not None


def remember_stripe_event(event_id):
    """Record a handled Stripe event id (and forget ids older than EVENT_DAYS)."""
    now = int(time.time())
    with _db() as c:
        c.execute("INSERT OR IGNORE INTO stripe_events(id, at) VALUES(?,?)", (str(event_id)[:255], now))
        c.execute("DELETE FROM stripe_events WHERE at<?", (now - EVENT_DAYS * 86400,))


def find_billing(customer="", sub=""):
    """The account id for a Stripe customer or subscription id, or None."""
    with _db() as c:
        r = c.execute("SELECT id FROM users WHERE (stripe_customer!='' AND stripe_customer=?) OR (stripe_sub!='' AND stripe_sub=?)", (customer or "-", sub or "-")).fetchone()
    return r["id"] if r else None


def set_billing(user_id, **fields):
    """Update the subscription fields of one account (only the known columns)."""
    allowed = ("plan", "plan_status", "plan_renews", "plan_cancel", "plan_failed", "plan_interval", "stripe_customer", "stripe_sub")
    pairs = [(k, v) for k, v in fields.items() if k in allowed]
    if not pairs:
        return
    with _db() as c:
        c.execute("UPDATE users SET %s WHERE id=?" % ", ".join("%s=?" % k for k, _ in pairs), [v for _, v in pairs] + [user_id])


# A campus, a library or a phone network puts many people behind one address: 5 sign-ups an hour per address turned students away
# (October 22). The address is the host's last hop (serve.client_ip), which a script cannot change, so the per-address caps can be generous;
# the same email tried again and again from one address is capped on its own.
SIGNUPS_PER_HOUR = 40           # sign-up tries per visitor address and hour on a public server (serve.py passes it)
SIGNUPS_PER_HOUR_LOCAL = 10     # the owner's own computer, where every request comes from 127.0.0.1 (tests, the browser checks)
PER_IP_EMAIL_PER_HOUR = 5       # sign-up tries, and codes sent, for one email from one address in an hour
CODES_PER_IP_PER_HOUR = 80      # verification codes sent per visitor address and hour (one account still gets at most 3 an hour)
SIGNUP_LIMIT_MSG = ("Many accounts were made from this network in the last hour (a campus or office shares one address). Wait an hour and "
                    "try again, or sign in if you already have an account.")
SIGNUP_EMAIL_LIMIT_MSG = ("This email was tried several times in the last hour. Check your inbox and spam folder for the 6-digit code, or sign "
                          "in if the account exists (Forgot password? sets a new password). You can try again in an hour.")


def signup(email, password, ip, agree=False, check_dns=False, per_hour=None):
    """Returns (status, body, session_token_or_None). check_dns (serve.py: on a public server that sends email) also refuses a domain
    DNS says cannot receive mail, before any code is sent; it runs outside the lock, so a slow resolver holds up nobody else.
    per_hour caps sign-up tries per visitor address (`ip` is the X-Forwarded-For address on a public server, as for the lock-out)."""
    return signup_with_code(email, password, ip, agree, check_dns, per_hour)[:3]


def signup_with_code(email, password, ip, agree=False, check_dns=False, per_hour=None, first="", last="", verified=False):
    """signup() that also makes the first 6-digit code in the SAME locked transaction that creates the account. Returns
    (status, body, token, mail) where mail is (user_id, email, digits) to send, or None.
    first, last: the names typed at sign-up, kept on the account (/api/auth/me). verified: the test-mode switch (serve.py
    UAPLY_SIGNUP_TEST, never on a public server): the account is made already verified and no code is made or sent.

    Why one step: a "Continue with Google" for the same Gmail address can arrive between "account created" and "code made". Google is
    the authority there, so oauth_login (under the same lock) removes the unproven password and ends this new session; asking for the
    code afterwards found no session and the sign-up answered 500. Made together, the Google sign-in can only come before (this
    sign-up is then told the address is taken) or after (the code it removes is simply dead), never in between."""
    email = _clean_email(email)
    if not email:
        return 400, {"error": "Enter a valid email address."}, None, None
    if agree is not True:
        return 400, {"error": "Confirm you are 18 or older and agree to the Terms and Privacy Policy."}, None, None
    if not isinstance(password, str) or not (8 <= len(password) <= 128):
        return 400, {"error": "Use a password between 8 and 128 characters."}, None, None
    if password.lower() == email:
        return 400, {"error": "Your password cannot be your email."}, None, None
    problem = mailbox_problem(email, check_dns)
    if problem:
        return 400, {"error": problem, "code": "mailbox"}, None, None
    with _lock:
        if len(_recent(_signups, (ip, email), 3600)) >= PER_IP_EMAIL_PER_HOUR:
            return 429, {"error": SIGNUP_EMAIL_LIMIT_MSG, "code": "signup_email_limit"}, None, None
        if len(_recent(_signups, ip, 3600)) >= (per_hour or SIGNUPS_PER_HOUR_LOCAL):
            return 429, {"error": SIGNUP_LIMIT_MSG, "code": "signup_limit"}, None, None
        _signups[ip].append(time.time())
        _signups[(ip, email)].append(time.time())
        salt = secrets.token_bytes(16)
        pw_hash = _hash(password, salt)
        now = int(time.time())
        first, last = clean_name(first), clean_name(last)
        try:
            with _db() as c:
                cur = c.execute("INSERT INTO users(email, salt, hash, created_at, last_login, terms_at, first_name, last_name, email_verified) "
                                "VALUES(?,?,?,?,?,?,?,?,?)", (email, salt, pw_hash, now, now, now, first, last, 1 if verified else 0))
                uid = cur.lastrowid
                token = _new_session(c, uid)
                digits = None if verified else _new_code(c, uid)
            if not verified:
                _count_site_code()                      # its first code email counts toward the site's hour (never refused here)
        except sqlite3.IntegrityError:
            return 409, {"error": "That email already has an account. Sign in instead."}, None, None
    user = {"id": uid, "email": email, "hasPassword": True, "emailVerified": bool(verified), "plan": "free", "first": first, "last": last}
    return 200, {"user": user}, token, (None if verified else (uid, email, digits))


def login(email, password, ip):
    email = _clean_email(email)
    bad = (401, {"error": "Wrong email or password."}, None)
    if not email or not isinstance(password, str) or not (1 <= len(password) <= 128):
        return bad
    key, every = (ip, email), ("*", email)
    with _lock:
        _prune()
        if len(_recent(_fails, key, FAIL_WINDOW)) >= MAX_FAILS or len(_recent(_fails, every, FAIL_WINDOW)) >= MAX_EMAIL_FAILS:
            return 429, {"error": "Too many tries. Wait a few minutes and try again, or use Forgot password."}, None
        with _db() as c:
            row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        salt = bytes(row["salt"]) if row else _DUMMY_SALT          # same work whether or not the email exists
        ok = hmac.compare_digest(_hash(password, salt), bytes(row["hash"]) if row else b"\x01" * 32) and row is not None
        if not ok:
            _fails[key].append(time.time())
            _fails[every].append(time.time())
            return bad
        _fails.pop(key, None)
        with _db() as c:
            c.execute("UPDATE users SET last_login=? WHERE id=?", (int(time.time()), row["id"]))
            token = _new_session(c, row["id"])
    return 200, {"user": public_user(row)}, token


def set_send_for_me(token, on):
    """POST /api/auth/send-for-me {on}: the signed-in account's Send applications for me switch (Profile, Account). Off, every swipe right
    only saves the job to Job Tracker: nothing is sent to any employer for this person (uaply_api.submit). Returns (status, body)."""
    user = user_for(token)
    if not user:
        return 401, {"error": "Sign in first.", "code": "signin"}
    if not isinstance(on, bool):
        return 400, {"error": "Say on or off."}
    with _lock, _db() as c:
        c.execute("UPDATE users SET send_for_me=?, send_for_me_at=? WHERE id=?", (1 if on else 0, int(time.time()), user["id"]))
    return 200, {"ok": True, "sendForMe": on}


# made with the other tables in init(), and again (if missing) by the two functions that use it, so a database made before the table
# existed, or one a caller opened without init(), never answers "no such table: consents" to a swipe right (uaply_api.submit reads it)
CONSENTS_TABLE = """CREATE TABLE IF NOT EXISTS consents(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            at INTEGER NOT NULL,
            ip TEXT NOT NULL,
            text_sha256 TEXT NOT NULL,
            auto INTEGER NOT NULL DEFAULT 0,
            authorize INTEGER NOT NULL DEFAULT 0,
            accurate INTEGER NOT NULL DEFAULT 0)"""


def _consent_cols(c):
    """The consents table, with the version 6 ticks' columns on a database made before them."""
    c.execute(CONSENTS_TABLE)
    have = {r[1] for r in c.execute("PRAGMA table_info(consents)").fetchall()}
    for col in ("authorize", "accurate"):
        if col not in have:
            c.execute("ALTER TABLE consents ADD COLUMN %s INTEGER NOT NULL DEFAULT 0" % col)
CONSENT_ROWS = 20                # the most agreements kept per account (the latest one counts; older ones show what was agreed before)


# the profile kept on the account (Saif, October 24, P0: a Google sign-in, a second device or a cleared browser lost the profile setup,
# which lived on the device only): one row per account, {key: {v, at}} where at is the device's time of that field's last change; a
# merge keeps the newer of each field. Voluntary self-identification answers and the resume file itself are never part of it.
PROFILES_TABLE = """CREATE TABLE IF NOT EXISTS profiles(
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            data TEXT NOT NULL,
            at INTEGER NOT NULL)"""
PROFILE_MAX = 200000             # bytes of one account's kept profile
PROFILE_KEY_RE = re.compile(r"^[pa]\.[A-Za-z][A-Za-z0-9_]{0,40}$")


def profile_get(user_id):
    """The account's kept profile {key: {v, at}} ({} when there is none)."""
    with _lock, _db() as c:
        c.execute(PROFILES_TABLE)
        row = c.execute("SELECT data FROM profiles WHERE user_id=?", (int(user_id),)).fetchone()
    try:
        d = json.loads(row["data"]) if row else {}
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def profile_clear(user_id):
    """Forget the account's kept profile (Delete all my data, on a signed-in device): the next sign-in starts from nothing."""
    with _lock, _db() as c:
        c.execute(PROFILES_TABLE)
        c.execute("DELETE FROM profiles WHERE user_id=?", (int(user_id),))
    return True


def profile_merge(user_id, fields):
    """Merge a device's fields into the account's kept profile, the newer of each field winning. Returns (ok, merged or reason)."""
    if not isinstance(fields, dict):
        return False, "fields"
    clean = {}
    for k, x in fields.items():
        if isinstance(k, str) and PROFILE_KEY_RE.match(k) and k != "a.eeo" and isinstance(x, dict) and isinstance(x.get("at"), (int, float)):
            clean[k] = {"v": x.get("v"), "at": int(x["at"])}
    uid = int(user_id)
    with _lock, _db() as c:
        c.execute(PROFILES_TABLE)
        row = c.execute("SELECT data FROM profiles WHERE user_id=?", (uid,)).fetchone()
        try:
            cur = json.loads(row["data"]) if row else {}
        except ValueError:
            cur = {}
        cur = cur if isinstance(cur, dict) else {}
        for k, x in clean.items():
            if k not in cur or x["at"] >= int((cur.get(k) or {}).get("at") or 0):
                cur[k] = x
        data = json.dumps(cur, separators=(",", ":"))
        if len(data.encode("utf-8")) > PROFILE_MAX:
            return False, "too large"
        c.execute("INSERT INTO profiles(user_id, data, at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, at=excluded.at",
                  (uid, data, int(time.time())))
    return True, cur


def record_consent(user_id, version, ip, text_sha256, auto=False, authorize=False, accurate=False):
    """Keep one first-swipe agreement on the account (consent_api.py): its version, the time on this server's clock, the visitor's address
    (the last hop, as every limit reads it) and the SHA-256 of the exact words agreed to. Version 0 records that the person took it back.
    The rows go with the account when it is deleted. Returns consent_for(user_id)."""
    uid = int(user_id)
    with _lock, _db() as c:
        _consent_cols(c)
        c.execute("INSERT INTO consents(user_id, version, at, ip, text_sha256, auto, authorize, accurate) VALUES(?,?,?,?,?,?,?,?)",
                  (uid, int(version), int(time.time()), str(ip or "")[:64], str(text_sha256 or "")[:64], 1 if auto else 0, 1 if authorize else 0, 1 if accurate else 0))
        c.execute("DELETE FROM consents WHERE user_id=? AND id NOT IN (SELECT id FROM consents WHERE user_id=? ORDER BY id DESC LIMIT ?)",
                  (uid, uid, CONSENT_ROWS))
    return consent_for(uid)


def consent_for(user_id):
    """The account's latest agreement {v, at, auto}, or None (never agreed, or took it back)."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    with _lock, _db() as c:
        _consent_cols(c)
        row = c.execute("SELECT version, at, auto, authorize, accurate FROM consents WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
    if not row or not row["version"]:
        return None
    return {"v": int(row["version"]), "at": int(row["at"]), "auto": bool(row["auto"]), "authorize": bool(row["authorize"]), "accurate": bool(row["accurate"])}


def user_by_id(user_id):
    """The account with this id ({id, email, emailVerified, ...}), or None when there is none (deleted, or not a number)."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    with _lock, _db() as c:
        row = c.execute("SELECT id, email, has_password, email_verified, plan, first_name, last_name, send_for_me, terms_at FROM users WHERE id=?", (uid,)).fetchone()
    return public_user(row) if row else None


def user_for(token):
    if not isinstance(token, str) or not (20 <= len(token) <= 100):
        return None
    with _lock, _db() as c:
        row = c.execute("SELECT u.id, u.email, u.has_password, u.email_verified, u.plan, u.first_name, u.last_name, u.send_for_me, u.terms_at FROM sessions s JOIN users u ON u.id=s.user_id "
                        "WHERE s.token_hash=? AND s.expires_at>?",
                        (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
    return public_user(row) if row else None


def delete_account(token, password, ip, confirm="", before_delete=None):
    """Delete the signed-in account after re-checking the password (or, for an account made with Google that has no
    password, after typing DELETE). Returns (status, body, deleted_user_id_or_None).
    before_delete(user_id), if given, runs once the password is right and before anything is removed (serve.py passes the Stripe
    cancellation, billing_api.cancel_on_delete). If it returns an error sentence, the account is kept and the person is told why."""
    user = user_for(token)
    if not user:
        return 401, {"error": "You are not signed in."}, None
    key = (ip, user["email"])
    with _lock:
        if len(_recent(_fails, key, FAIL_WINDOW)) >= MAX_FAILS:
            return 429, {"error": "Too many tries. Wait a few minutes and try again."}, None
        with _db() as c:
            row = c.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        if row and not row["has_password"]:
            if confirm != "DELETE":
                return 400, {"error": "Type DELETE to confirm."}, None
        elif not row or not isinstance(password, str) or not hmac.compare_digest(_hash(password, bytes(row["salt"])), bytes(row["hash"])):
            _fails[key].append(time.time())
            return 401, {"error": "That password is not right."}, None
    if before_delete:                                    # outside the lock: it may wait on Stripe for a few seconds
        problem = before_delete(user["id"])
        if problem:
            return 409, {"error": problem, "code": "billing"}, None
    with _lock:
        with _db() as c:
            c.execute("DELETE FROM users WHERE id=?", (user["id"],))      # sessions and receipts go with it (ON DELETE CASCADE)
    return 200, {"ok": True}, user["id"]


def logout(token):
    if isinstance(token, str) and token:
        with _lock, _db() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))


def add_mail(user_id, to_addr, subject, body, status):
    with _lock, _db() as c:
        c.execute("INSERT INTO user_mail(user_id, to_addr, subject, body, status, at) VALUES(?,?,?,?,?,?)",
                  (user_id, to_addr, subject[:200], body[:8000], status, int(time.time())))


def mark_mail_sent(user_id, to_addr):
    """A receipt that was held (the daily email limit, the mail service down) went out later: its stored copy now says sent."""
    with _lock, _db() as c:
        row = c.execute("SELECT id FROM user_mail WHERE user_id=? AND to_addr=? AND status='held' ORDER BY id LIMIT 1", (user_id, to_addr)).fetchone()
        if row:
            c.execute("UPDATE user_mail SET status='sent' WHERE id=?", (row[0],))
        return bool(row)


def mail_list(limit=50):
    with _lock, _db() as c:
        return [dict(r) for r in c.execute("SELECT to_addr, subject, body, status, at FROM user_mail ORDER BY id DESC LIMIT ?", (limit,))]


def counts():
    with _lock, _db() as c:
        return {"users": c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "mail": c.execute("SELECT COUNT(*) FROM user_mail").fetchone()[0]}


def oauth_login(provider, subject, email, agree=False, trusted=True):
    """Sign in (or sign up) with an identity a provider has already proven. Returns (error_code_or_None, user_or_None, token).

    Known identity: sign in. Trusted email that already has an account: link the identity to it and sign in. Otherwise create an
    account with no password (has_password=0); that needs `agree` (18 or older, Terms and Privacy Policy).

    The account is found by the provider's permanent account number first, so a Google account whose email later changes keeps
    signing into the same UAply account and never makes a second one. The email is only used (as canonical_email) when that number
    is new, and then it either joins the one account that already has that exact address or makes the only one.

    `trusted` says the provider is the authority on this email address (for Google: a Gmail address or a Workspace account). An
    untrusted email can still sign in by the provider's account number, but it never proves ownership: it cannot be merged into an
    existing account ("email_in_use") and a new account made with it starts unverified, so the emailed code check applies.

    Linking a trusted email to a password account that never proved its email (no code entered, no reset link used): whoever chose
    that password never showed they own the address, and it may have been someone else who signed up first with this person's Gmail
    to watch the account later. So that password is removed and every other session of the account ends; the owner can add a password
    again with Forgot password. The returned user then carries passwordRemoved=True so the page can say so.

    Joining an account whose address was never proven (email_verified 0: opened with a password, with no password, or by a sign-in Google
    did not vouch for) needs this person's own 18+ / Terms tick (`agree`; "agree" otherwise), and terms_at then becomes that tick: whoever
    opened the account ticked the box for themselves, not for the address's owner (login_with_code follows the same rule).

    The returned user carries created=True only when this call made the account (so a page never calls an older account new)."""
    email = _clean_email(email)
    if not email or not isinstance(subject, str) or not subject:
        return "failed", None, None
    removed = created = False
    with _lock:
        with _db() as c:
            row = c.execute("SELECT u.* FROM identities i JOIN users u ON u.id=i.user_id WHERE i.provider=? AND i.subject=?",
                            (provider, subject)).fetchone()
            now = int(time.time())
            if not row:
                row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
                if row and not trusted:
                    return "email_in_use", None, None
                ticked = False
                if row and not row["email_verified"]:      # an account nobody has proven this address for: the owner's own tick first
                    if agree is not True:
                        return "agree", None, None
                    ticked = True
                if not row:
                    if agree is not True:
                        return "agree", None, None
                    if is_disposable(email):                # a Google account can be registered with a throwaway address too
                        return "disposable", None, None
                    cur = c.execute("INSERT INTO users(email, salt, hash, created_at, last_login, terms_at, has_password, email_verified) VALUES(?,?,?,?,?,?,0,?)",
                                    (email, secrets.token_bytes(16), secrets.token_bytes(32), now, now, now, 1 if trusted else 0))
                    row = c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
                    created = True
                if ticked:
                    c.execute("UPDATE users SET terms_at=? WHERE id=?", (now, row["id"]))       # this person's own tick, not the opener's
                if trusted and row["has_password"] and not row["email_verified"]:     # a password nobody proved belongs to this address's owner
                    c.execute("UPDATE users SET salt=?, hash=?, has_password=0 WHERE id=?", (secrets.token_bytes(16), secrets.token_bytes(32), row["id"]))
                    for table in ("sessions", "password_resets", "email_codes"):
                        c.execute("DELETE FROM %s WHERE user_id=?" % table, (row["id"],))
                    removed = True
                c.execute("INSERT OR IGNORE INTO identities(provider, subject, user_id, email, created_at) VALUES(?,?,?,?,?)",
                          (provider, subject, row["id"], email, now))
                if trusted:
                    c.execute("UPDATE users SET email_verified=1 WHERE id=?", (row["id"],))      # the provider is the authority on this address: it vouched that this person owns it
                row = c.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
            c.execute("UPDATE users SET last_login=? WHERE id=?", (now, row["id"]))
            token = _new_session(c, row["id"])
    user = public_user(row)
    if removed:
        user["passwordRemoved"] = True
    if created:
        user["created"] = True
    return None, user, token


def _check_new_password(password, email=""):
    if not isinstance(password, str) or not (8 <= len(password) <= 128):
        return "Use a password between 8 and 128 characters."
    if email and password.lower() == email:
        return "Your password cannot be your email."
    return ""


def request_reset(email, ip, defer=False):
    """Start a password reset. Always answers the same way so nobody can use this to find out who has an account.
    Returns (status, body, mail) where mail is (user_id, email, token) when a link should be sent, else None.
    defer (serve.py, item 20): the token is not written here; mail is (user_id, email, None) and issue_reset_token writes it on the
    background thread that sends the email, so an address with an account does no more work before the answer than one without."""
    ok = (200, {"ok": True, "message": "If that email has an account, a reset link is on its way. It works for one hour."})
    email = _clean_email(email)
    if not email:
        return 400, {"error": "Enter a valid email address."}, None
    with _lock:
        if len(_recent(_resets, ip, 3600)) >= 6 or len(_recent(_resets, email, 3600)) >= 3:
            return 429, {"error": "Too many reset requests. Try again in an hour."}, None
        _resets[ip].append(time.time())
        _resets[email].append(time.time())
        with _db() as c:
            row = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if not row:
                return ok[0], ok[1], None
            if defer:
                return ok[0], ok[1], (row["id"], email, None)
            token = secrets.token_urlsafe(32)
            now = int(time.time())
            c.execute("DELETE FROM password_resets WHERE expires_at < ? OR user_id=?", (now, row["id"]))
            c.execute("INSERT INTO password_resets(token_hash, user_id, expires_at) VALUES(?,?,?)",
                      (hashlib.sha256(token.encode()).hexdigest(), row["id"], now + RESET_SECONDS))
    return ok[0], ok[1], (row["id"], email, token)


def issue_reset_token(user_id):
    """The reset link's token for a request_reset(..., defer=True) answer, written just before it is emailed: (user_id, email, token),
    or None when the account is gone by then."""
    with _lock, _db() as c:
        row = c.execute("SELECT id, email FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return None
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        c.execute("DELETE FROM password_resets WHERE expires_at < ? OR user_id=?", (now, row["id"]))
        c.execute("INSERT INTO password_resets(token_hash, user_id, expires_at) VALUES(?,?,?)",
                  (hashlib.sha256(token.encode()).hexdigest(), row["id"], now + RESET_SECONDS))
    return row["id"], row["email"], token


def reset_password(token, new_password, ip):
    """Use a reset link. Returns (status, body). Every session of the account is ended."""
    err = _check_new_password(new_password)
    if err:
        return 400, {"error": err}
    if not isinstance(token, str) or not (20 <= len(token) <= 100):
        return 400, {"error": "That reset link is not valid. Ask for a new one."}
    key = (ip, "reset")
    with _lock:
        if len(_recent(_fails, key, FAIL_WINDOW)) >= MAX_FAILS:
            return 429, {"error": "Too many tries. Wait a few minutes and try again."}
        th = hashlib.sha256(token.encode()).hexdigest()
        with _db() as c:
            row = c.execute("SELECT r.user_id, u.email, u.email_verified FROM password_resets r JOIN users u ON u.id=r.user_id "
                            "WHERE r.token_hash=? AND r.expires_at>?", (th, int(time.time()))).fetchone()
        if not row:
            _fails[key].append(time.time())
            return 400, {"error": "That reset link has expired or was already used. Ask for a new one."}
        if new_password.lower() == row["email"]:
            return 400, {"error": "Your password cannot be your email."}
        salt = secrets.token_bytes(16)
        pw_hash = _hash(new_password, salt)
        with _db() as c:
            c.execute("UPDATE users SET salt=?, hash=?, has_password=1, email_verified=1 WHERE id=?", (salt, pw_hash, row["user_id"]))   # the link went to their inbox
            c.execute("DELETE FROM password_resets WHERE user_id=?", (row["user_id"],))
            c.execute("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
            if not row["email_verified"]:
                # Until now nobody had proven this address. A Google login linked to it could only be one Google was not the authority
                # for (a trusted one would have verified the account), so it may belong to whoever held the address before. The person
                # who just used the emailed link does own it: that Google login no longer opens this account.
                c.execute("DELETE FROM identities WHERE user_id=?", (row["user_id"],))
    return 200, {"ok": True, "email": row["email"]}


def change_password(token, current, new_password, ip):
    """Signed-in change: needs the current password. Other sessions end; this one stays. Returns (status, body)."""
    user = user_for(token)
    if not user:
        return 401, {"error": "You are not signed in."}
    if not user["hasPassword"]:
        how = "with a code sent to your email" + (" or with Google" if google_linked(user["id"]) else "")
        return 400, {"error": "This account has no password: you sign in %s. Use Forgot password to add one." % how, "code": "no_password"}
    err = _check_new_password(new_password, user["email"])
    if err:
        return 400, {"error": err}
    key = (ip, user["email"])
    with _lock:
        if len(_recent(_fails, key, FAIL_WINDOW)) >= MAX_FAILS:
            return 429, {"error": "Too many tries. Wait a few minutes and try again."}
        with _db() as c:
            row = c.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        if not isinstance(current, str) or not hmac.compare_digest(_hash(current, bytes(row["salt"])), bytes(row["hash"])):
            _fails[key].append(time.time())
            return 401, {"error": "Your current password is not right."}
        salt = secrets.token_bytes(16)
        keep = hashlib.sha256(token.encode()).hexdigest()
        with _db() as c:
            c.execute("UPDATE users SET salt=?, hash=? WHERE id=?", (salt, _hash(new_password, salt), user["id"]))
            c.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user["id"], keep))
    return 200, {"ok": True}


# ---------- proving the email is theirs: a 6-digit code ----------
CODE_SECONDS = 600
MAX_CODE_TRIES = 5
_code_sends = {}     # ("u", user id) or ("ip", address) -> timestamps of recent code emails


def _new_code(c, user_id):
    """Make a fresh code (replacing any older one), store only its hash, and return the digits."""
    digits = "%06d" % secrets.randbelow(1000000)
    salt = secrets.token_hex(8)
    c.execute("INSERT OR REPLACE INTO email_codes(user_id, code_hash, salt, expires_at, attempts) VALUES(?,?,?,?,0)",
              (user_id, hashlib.sha256((salt + digits).encode()).hexdigest(), salt, int(time.time()) + CODE_SECONDS))
    return digits


def issue_code_for_token(token):
    """A code for the account this session belongs to. Returns (user_id, email, digits), or None when the session has ended (a Google
    sign-in for the same address can end it at any moment). serve.py's sign-up uses signup_with_code instead."""
    user = user_for(token)
    if not user:
        return None
    with _lock, _db() as c:
        return user["id"], user["email"], _new_code(c, user["id"])


def resend_code(token, ip):
    """Send a new code. Returns (status, body, mail) where mail is (user_id, email, digits) when an email should go out."""
    user = user_for(token)
    if not user:
        return 401, {"error": "You are not signed in."}, None
    if user["emailVerified"]:
        return 200, {"ok": True, "already": True}, None
    with _lock:
        busy = _site_code_refusal(ip)                     # an account still unproven: anyone can make one, so its session is no pass
        if busy:
            return 429, busy, None
        if (len(_recent(_code_sends, ("u", user["id"]), 3600)) >= 3 or len(_recent(_code_sends, ("ip", ip), 3600)) >= CODES_PER_IP_PER_HOUR
                or len(_recent(_code_sends, ("ipe", ip, user["email"]), 3600)) >= PER_IP_EMAIL_PER_HOUR):
            return 429, {"error": "Several codes were already sent in the last hour. Check your inbox and spam folder for the newest one (only "
                         "the newest works), or try again in an hour."}, None
        for k in (("u", user["id"]), ("ip", ip), ("ipe", ip, user["email"])):
            _code_sends.setdefault(k, []).append(time.time())
        _count_site_code(ip)
        with _db() as c:
            digits = _new_code(c, user["id"])
    return 200, {"ok": True, "message": "A new code is on its way. The old one no longer works."}, (user["id"], user["email"], digits)


def verify_code(token, code, ip):
    """Check the code the person typed. Returns (status, body). Five wrong tries end that code; a new one must be requested."""
    user = user_for(token)
    if not user:
        return 401, {"error": "You are not signed in."}
    if user["emailVerified"]:
        return 200, {"ok": True, "already": True}
    digits = _code_digits(code)
    if len(digits) != 6:
        return 400, {"error": "Enter the 6-digit code from your email."}
    with _lock:
        key = (ip, "verify")
        if len(_recent(_fails, key, FAIL_WINDOW)) >= 20:
            return 429, {"error": "Too many tries. Wait a few minutes and try again."}
        with _db() as c:
            row = c.execute("SELECT * FROM email_codes WHERE user_id=?", (user["id"],)).fetchone()
            if not row or row["expires_at"] < int(time.time()):
                return 400, {"error": "That code has expired. Send a new one.", "expired": True}
            if row["attempts"] >= MAX_CODE_TRIES:
                c.execute("DELETE FROM email_codes WHERE user_id=?", (user["id"],))
                return 429, {"error": "Too many wrong tries. Send a new code.", "expired": True}
            if not hmac.compare_digest(hashlib.sha256((row["salt"] + digits).encode()).hexdigest(), row["code_hash"]):
                left = MAX_CODE_TRIES - row["attempts"] - 1
                _fails[key].append(time.time())
                if left <= 0:
                    c.execute("DELETE FROM email_codes WHERE user_id=?", (user["id"],))
                    return 400, {"error": "That code is not right, and there are no tries left. Send a new code.", "expired": True}
                c.execute("UPDATE email_codes SET attempts=attempts+1 WHERE user_id=?", (user["id"],))
                return 400, {"error": "That code is not right. %d %s left." % (left, "try" if left == 1 else "tries"), "triesLeft": left}
            c.execute("UPDATE users SET email_verified=1 WHERE id=?", (user["id"],))
            c.execute("DELETE FROM email_codes WHERE user_id=?", (user["id"],))
    return 200, {"ok": True}



# /* sign-up v2 */ ----------------------------------------------------------------------------------------------------------------
# Sign up and sign in with no password: an emailed 6-digit code proves the inbox and signs the person in. serve.py calls these only when
# CODE_SIGNIN is on (the sandbox instance); dev and the live site never reach them. New functions and a short-lived name hint only;
# nothing above this block was changed.
#
# Why no session at sign-up: if "Create my account" signed the person in at once, anyone could open an account on someone else's
# address and stay signed in to it. Here the session only starts when the code from that inbox is typed in (login_with_code).
CODE_SENDS_PER_EMAIL = 3         # code emails per address and hour, whether or not the address has an account (so a 429 reveals nothing)
CODE_LOGIN_FAILS = 20            # codes that did not sign in, from one visitor address in FAIL_WINDOW (that connection only, never the account)
CODE_LIMIT_MSG = ("Too many sign-ups or codes in the last hour, from this connection or for this email. Try again later, or use "
                  "Continue with Google.")       # one sentence for both causes, the same for every address (item 15)
# Every code email the site sends in an hour, from every route and every visitor together (UAPLY_CODE_SENDS_PER_HOUR, default 500): a
# ceiling on how much mail anyone can make UAply send to other people's inboxes, whatever addresses or connections they use.
try:
    CODE_SENDS_SITE_PER_HOUR = max(1, int(os.environ.get("UAPLY_CODE_SENDS_PER_HOUR") or 500))
except ValueError:
    CODE_SENDS_SITE_PER_HOUR = 500
CODE_BUSY_MSG = "UAply is sending a lot of sign-in codes right now. Try again in a few minutes, or use Continue with Google."
# No one visitor may use more than its share of that hour: SITE_SHARE_PERCENT of it, but never less than the CODES_PER_IP_PER_HOUR one
# connection may send anyway (so a campus behind one address keeps its 80; at the default 500 the share is 80). For the share an IPv6
# visitor counts by its /64 (share_key): one home or server is given a whole /64 and could otherwise use the hour up from fresh addresses.
# The per-connection limits count each address on its own. A device that signed in to the address with a code before (the known-device
# cookie), or that is signed in to that address's verified account right now, is never held back by the site's hour or by this share:
# the owner of an account can always get a code. The site-wide cap stays the backstop against abuse.
SITE_SHARE_PERCENT = 5


def site_share():
    """How many of the site's hourly code emails one visitor (an IPv4 address, or an IPv6 /64) may use."""
    return max(CODES_PER_IP_PER_HOUR, CODE_SENDS_SITE_PER_HOUR * SITE_SHARE_PERCENT // 100)


def share_key(ip):
    """The visitor as the site's share counts it: an IPv4 address as it is, an IPv6 address by its /64 ("2001:db8:1:2::/64"), an IPv4
    address written as IPv6 (::ffff:198.51.100.7) as the IPv4 address."""
    try:
        a = ipaddress.ip_address(str(ip))
    except ValueError:
        return ip
    if a.version == 6:
        return str(a.ipv4_mapped) if a.ipv4_mapped else str(ipaddress.ip_network("%s/64" % a, strict=False))
    return str(a)


def _site_code_refusal(ip=None):
    """The site-wide hourly cap on code emails, and one address's share of it: None while there is room, else the 429 body. Call with
    _lock held."""
    if len(_recent(_code_sends, ("site",), 3600)) >= CODE_SENDS_SITE_PER_HOUR:
        return {"error": CODE_BUSY_MSG, "code": "code_busy"}
    if ip is not None and len(_recent(_code_sends, ("site-ip", share_key(ip)), 3600)) >= site_share():
        return {"error": CODE_LIMIT_MSG, "code": "code_limit"}
    return None


def _count_site_code(ip=None):
    """One more code email toward the site-wide hour (and, with ip, toward that address's share). Call with _lock held. "Email me a code"
    for an address with no account counts too (it sends nothing), so the answers stay the same whether or not an address has an account."""
    now = time.time()
    _code_sends.setdefault(("site",), []).append(now)
    if ip is not None:
        _code_sends.setdefault(("site-ip", share_key(ip)), []).append(now)


def _signed_in_as(row, token):
    """True when `token` is a live session of the verified account in `row` (the person is signed in to that very address)."""
    if not token:
        return False
    u = user_for(token)                 # looked up whether or not the address has an account, so the time taken says nothing about that
    return bool(row and u and u["id"] == row["id"] and u.get("emailVerified"))
# One answer for every code that does not sign in: wrong digits, a code that ran out of time or tries, an address with no code or no account.
# How many tries are left stays on the server, so a wrong code never tells a stranger whether the address has an account.
WRONG_CODE_MSG = "That code is not right, or it has expired. Check the newest email from UAply, or press Resend code."
# How many codes can be guessed at: each code takes at most MAX_CODE_TRIES (5) wrong tries, and at most CODE_SENDS_PER_EMAIL_DAY (6) codes
# go to one address a day (every route that emails a code counts), so at most 30 guesses a day (about 1 in 33,000), plus 10 at the
# owner's 2 spare codes. That bound comes from the codes themselves, so nothing here refuses a code that was just emailed and still has
# tries left, and a guess at an address with no live code is not counted against the address at all (only against the guesser's own
# connection). The owner's own device (one that signed in to this address with a code before: serve.py's known-device cookie) keeps
# CODE_SENDS_KNOWN_DAY spare codes a day, so a stranger who uses up an address's codes for the day cannot keep its owner out.
DAY = 86400
CODE_SENDS_PER_EMAIL_DAY = 6
CODE_SENDS_KNOWN_DAY = 2
KNOWN_SECONDS = 90 * DAY         # how long a device stays "known" for its address (the cookie's Max-Age)
_code_day = {}       # ("send", email) or ("known", email) -> timestamps in the last day (its own bucket: _prune forgets keys after an hour)
_code_day_pruned = [0.0]


def _code_digits(code):
    """The digits of a typed code as plain 0-9: full-width (U+FF10..) and Arabic-Indic (U+0660..) digits count as the digits they are,
    so a right code typed on a Japanese, Chinese or Arabic keyboard is not a wrong try (item 17). Anything that is not a digit is dropped."""
    out = []
    for ch in (code if isinstance(code, str) else "")[:64]:
        d = unicodedata.decimal(ch, None)
        if d is not None:
            out.append(str(d))
    return "".join(out)


CODE_DAY_MAX = 20000     # day counters kept at most (item 13); the site's hour of code emails already keeps them far below this


def _code_day_recent(key):
    """The last day's timestamps for `key` (and, at most once a minute, every key quiet for a day is forgotten). Call with _lock held."""
    now = time.time()
    if now - _code_day_pruned[0] >= 60 or now < _code_day_pruned[0]:
        _code_day_pruned[0] = now
        for k in [k for k, v in _code_day.items() if not v or now - v[-1] > DAY]:
            del _code_day[k]
    if key not in _code_day and len(_code_day) >= CODE_DAY_MAX:
        # full: the counters quiet for longest go first (a tenth at a time), whoever's address they are, so the answer to the next
        # request never depends on whether an address has an account
        for k in sorted(_code_day, key=lambda k: _code_day[k][-1] if _code_day[k] else 0)[:max(1, CODE_DAY_MAX // 10)]:
            del _code_day[k]
    return _recent(_code_day, key, DAY)


def _day_msg(wait):
    """The daily cap, said honestly: how long until this address can be sent a code again."""
    hours = max(1, int(-(-max(0, wait) // 3600)))
    return ("Too many codes were sent to this email today, so a new one can be sent in about %s. The newest code still works for 10 minutes "
            "after it was sent." % ("an hour" if hours == 1 else "%d hours" % hours))


def _known_value(row):
    """The known-device cookie value for this account: its id and an HMAC keyed by the account's own random salt (never sent anywhere,
    and replaced whenever the password changes or is removed), so it needs no new table and survives a restart."""
    return "%d.%s" % (row["id"], hmac.new(bytes(row["salt"]), b"uaply-known-device", hashlib.sha256).hexdigest()[:32])


def known_device(user_id):
    """The value serve.py puts in the known-device cookie after a code sign-in, or ''."""
    with _db() as c:
        row = c.execute("SELECT id, salt FROM users WHERE id=?", (user_id,)).fetchone()
    return _known_value(row) if row else ""


def _is_known(row, device):
    return bool(row) and isinstance(device, str) and 0 < len(device) < 100 and hmac.compare_digest(device, _known_value(row))


def _code_send_refusal(email, ip, user_id=None, known=False):
    """None (and the email counted) when one more code email may go to `email` from `ip`, else the 429 body. Call with _lock held.

    Every check is the same for an address with or without an account, so the answer never says which it is. user_id: the account at
    that address, when there is one; its code emails are also counted under ("u", user_id), the key resend_code reads, so Create my account,
    Email me a code and Resend share one limit of 3 an hour for that account. known: the request comes from a device that signed in to this
    address with a code before, or one signed in to its verified account right now; it is never held back by the site's hour or one
    address's share of it, and when the address's hourly or daily allowance is used up it may still send CODE_SENDS_KNOWN_DAY a day."""
    now = time.time()
    busy = None if known else _site_code_refusal(ip)
    if busy:
        return busy
    # the same limits as resend_code: 80 an hour per visitor address (serve.client_ip, the host's last hop), 5 an hour per address and email
    if len(_recent(_code_sends, ("ip", ip), 3600)) >= CODES_PER_IP_PER_HOUR or len(_recent(_code_sends, ("ipe", ip, email), 3600)) >= PER_IP_EMAIL_PER_HOUR:
        return {"error": CODE_LIMIT_MSG, "code": "code_limit"}
    day = _code_day_recent(("send", email))
    hour_full = len(_recent(_code_sends, ("e", email), 3600)) >= CODE_SENDS_PER_EMAIL or \
        (user_id is not None and len(_recent(_code_sends, ("u", user_id), 3600)) >= CODE_SENDS_PER_EMAIL)
    day_full = len(day) >= CODE_SENDS_PER_EMAIL_DAY
    if hour_full or day_full:
        spare = _code_day_recent(("known", email)) if known else None
        if spare is None or len(spare) >= CODE_SENDS_KNOWN_DAY:
            if day_full:
                return {"error": _day_msg(day[-CODE_SENDS_PER_EMAIL_DAY] + DAY - now), "code": "code_day"}
            return {"error": CODE_LIMIT_MSG, "code": "code_limit"}
        spare.append(now)                            # the owner's own device: one of today's spare codes
    else:
        day.append(now)
    _code_sends.setdefault(("ip", ip), []).append(now)
    _code_sends.setdefault(("ipe", ip, email), []).append(now)
    _code_sends.setdefault(("e", email), []).append(now)
    if user_id is not None:
        _code_sends.setdefault(("u", user_id), []).append(now)
    _count_site_code(None if known else ip)      # the owner's own device does not use up its address's share for the others there
    return None


def note_code_sent(email):
    """A code went to `email` by another route on the sandbox (today's password sign-up): it counts toward the day's cap too."""
    with _lock:
        _code_day_recent(("send", _clean_email(email) or str(email))).append(time.time())


def resend_code_daily(token, ip):
    """resend_code (Resend on a signed-in, unconfirmed card) with the day's cap of codes per address on top (serve.py, sandbox only), so
    every route that emails a code shares the bound on guesses. resend_code itself is unchanged."""
    user = user_for(token)
    if not user or user["emailVerified"]:
        return resend_code(token, ip)
    with _lock:                                      # an RLock: resend_code takes it again
        day = _code_day_recent(("send", user["email"]))
        if len(day) >= CODE_SENDS_PER_EMAIL_DAY:
            return 429, {"error": _day_msg(day[-CODE_SENDS_PER_EMAIL_DAY] + DAY - time.time()), "code": "code_day"}, None
        status, body, mail = resend_code(token, ip)
        if mail:
            day.append(time.time())
    return status, body, mail


def signup_passwordless(email, ip, agree=False, check_dns=False, per_hour=None, device="", session="", first="", last=""):
    """Create my account with no password. Returns (status, body, mail) where mail is (user_id, email, digits) to send, or None.

    A new address gets an account with no usable password (has_password=0, the same kind "Continue with Google" makes), terms_at set to
    now (the 18+ / Terms box was ticked) and email_verified=0; no session yet. An address that already has an account gets a sign-in
    code instead, and the answer is the same either way, so this cannot be used to find out who has an account: every request counts
    toward the connection's sign-up limit, the checks run in the same order for both, and the connection's sign-up limit and code limit
    give one and the same 429 answer. device: the known-device cookie; session: the session cookie (see _code_send_refusal)."""
    email = _clean_email(email)
    if not email:
        return 400, {"error": "Enter a valid email address."}, None
    if agree is not True:
        return 400, {"error": "Confirm you are 18 or older and agree to the Terms and Privacy Policy."}, None
    problem = mailbox_problem(email, check_dns)
    if problem:
        return 400, {"error": problem, "code": "mailbox"}, None
    with _lock:
        _prune()
        with _db() as c:
            row = c.execute("SELECT id, salt FROM users WHERE email=?", (email,)).fetchone()
        if len(_recent(_signups, ip, 3600)) >= (per_hour or SIGNUPS_PER_HOUR_LOCAL):
            return 429, {"error": CODE_LIMIT_MSG, "code": "code_limit"}, None
        refusal = _code_send_refusal(email, ip, row["id"] if row else None, _is_known(row, device) or _signed_in_as(row, session))
        if refusal:
            return 429, refusal, None
        _signups.setdefault(ip, []).append(time.time())
        now = int(time.time())
        try:
            with _db() as c:
                if row:
                    uid = row["id"]
                else:
                    cur = c.execute("INSERT INTO users(email, salt, hash, created_at, last_login, terms_at, has_password, email_verified, first_name, last_name) "
                                    "VALUES(?,?,?,?,?,?,0,0,?,?)", (email, secrets.token_bytes(16), secrets.token_bytes(32), now, now, now,
                                                                    clean_name(first), clean_name(last)))
                    uid = cur.lastrowid
                digits = _new_code(c, uid)
        except sqlite3.IntegrityError:               # a sign-up for the same address won the race: send that account a sign-in code
            with _db() as c:
                uid = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
                digits = _new_code(c, uid)
    # (the 4th part says which email: "signin" for an address that already had an account, "confirm" for a new one; the answer is the same)
    return 200, {"ok": True, "email": email}, (uid, email, digits, "signin" if row else "confirm")


def send_login_code(email, ip, device="", defer=False, session=""):
    """Email me a code, on the sign-in card. Always answers the same way (like request_reset), so nobody can use it to find out who has
    an account. Returns (status, body, mail) where mail is (user_id, email, digits) only when the address has an account. device: the
    known-device cookie; session: the session cookie (see _code_send_refusal).

    defer (serve.py): the code is not made here; mail is (user_id, email, None) and issue_login_code makes it on the background thread
    that emails it, so an address with an account does no more work before the answer than one without (no database write, no email)."""
    email = _clean_email(email)
    if not email:
        return 400, {"error": "Enter a valid email address."}, None
    with _lock:
        _prune()
        with _db() as c:
            row = c.execute("SELECT id, salt FROM users WHERE email=?", (email,)).fetchone()
        refusal = _code_send_refusal(email, ip, row["id"] if row else None, _is_known(row, device) or _signed_in_as(row, session))
        if refusal:
            return 429, refusal, None
        if not row:
            return 200, {"ok": True}, None
        if defer:
            return 200, {"ok": True}, (row["id"], email, None)
        with _db() as c:
            digits = _new_code(c, row["id"])
    return 200, {"ok": True}, (row["id"], email, digits)


def issue_login_code(user_id):
    """The code for a send_login_code(..., defer=True) answer, made just before it is emailed: (user_id, email, digits), or None when the
    account is gone by then."""
    with _lock, _db() as c:
        row = c.execute("SELECT email FROM users WHERE id=?", (user_id,)).fetchone()
        return (user_id, row["email"], _new_code(c, user_id)) if row else None


def login_with_code(email, code, ip, agree=False):
    """Sign in with the emailed code (after signup_passwordless or send_login_code). Returns (status, body, session_token_or_None).

    The code proves the person owns the inbox (the same power as a Forgot password link), so it also works for password and Google
    accounts. body["user"]["new"] is True for an account that has never been signed in to (made by signup_passwordless and confirmed
    just now), so the page says "Account created" only then.

    Every code that does not sign in gets the one answer WRONG_CODE_MSG (400), whether the digits are wrong, the code ran out of time or
    tries, or the address has no code or no account. Five wrong tries end a code. Only the guesser's own connection is ever locked (20 in
    15 minutes): nothing a stranger sends can stop the owner's freshly emailed code from working (the bound is CODE_SENDS_PER_EMAIL_DAY).

    As in oauth_login and reset_password: a password nobody had proven belonged to this address's owner is removed (whoever chose it
    may have signed up first with this person's address), every other session ends, and a Google sign-in Google was not the authority
    for no longer opens this account.

    An address that was never proven (email_verified 0) is finished only with `agree` True (the 18+ / Terms box ticked by the person
    typing the code), and terms_at is then set to that tick: whoever opened the account (with no password, with a password, or with a
    Google login Google does not vouch for) may not be the inbox's owner, so their tick is not taken as the owner's. Without it the
    answer is needsAgree, after the code is checked (so it reveals nothing to someone without the code), and the code stays usable for
    the ticked retry. body["user"]["googleRemoved"] is True when a Google sign-in was taken off the account here."""
    email = _clean_email(email)
    digits = _code_digits(code)
    if not email:
        return 400, {"error": "Enter a valid email address."}, None
    if len(digits) != 6:
        return 400, {"error": "Enter the 6-digit code from your email."}, None
    wrong = {"error": WRONG_CODE_MSG, "code": "wrong_code"}
    key = (ip, "codelogin")
    with _lock:
        _prune()
        if len(_recent(_fails, key, FAIL_WINDOW)) >= CODE_LOGIN_FAILS:
            return 429, {"error": "Too many tries. Wait a few minutes and try again."}, None
        with _db() as c:
            row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            rec = c.execute("SELECT * FROM email_codes WHERE user_id=?", (row["id"],)).fetchone() if row else None
            if not rec or rec["expires_at"] < int(time.time()) or rec["attempts"] >= MAX_CODE_TRIES:
                if rec:
                    c.execute("DELETE FROM email_codes WHERE user_id=?", (row["id"],))
                _fails.setdefault(key, []).append(time.time())      # no live code: not a guess at anyone's code, so only this connection counts it
                return 400, wrong, None
            if not hmac.compare_digest(hashlib.sha256((rec["salt"] + digits).encode()).hexdigest(), rec["code_hash"]):
                _fails.setdefault(key, []).append(time.time())
                if rec["attempts"] + 1 >= MAX_CODE_TRIES:
                    c.execute("DELETE FROM email_codes WHERE user_id=?", (row["id"],))
                else:
                    c.execute("UPDATE email_codes SET attempts=attempts+1 WHERE user_id=?", (row["id"],))
                return 400, wrong, None
            uid = row["id"]
            linked = c.execute("SELECT 1 FROM identities WHERE user_id=?", (uid,)).fetchone() is not None
            new = not row["email_verified"] and not row["has_password"] and not linked
            # whoever opened an unproven account ticked the box for themselves, not for the inbox's owner: the owner ticks it here
            needs_tick = not row["email_verified"]
            if needs_tick and agree is not True:
                return 400, {"error": "This finishes a new UAply account. Tick the box to confirm you are 18 or older and agree, and it is done." if new else
                             "Tick the box to confirm you are 18 or older and agree, and you are signed in.", "needsAgree": True}, None
            removed = bool(row["has_password"]) and not row["email_verified"]
            if removed:
                c.execute("UPDATE users SET salt=?, hash=?, has_password=0 WHERE id=?", (secrets.token_bytes(16), secrets.token_bytes(32), uid))
            g_removed = False
            if not row["email_verified"]:
                # the inbox's owner has just proven it for the first time: whatever got in before them (a password nobody had proven, a Google
                # sign-in Google was not the authority for) is shut out, and every session they had ends, as in reset_password
                g_removed = c.execute("DELETE FROM identities WHERE user_id=?", (uid,)).rowcount > 0
                for table in ("sessions", "password_resets"):
                    c.execute("DELETE FROM %s WHERE user_id=?" % table, (uid,))
            if needs_tick:
                c.execute("UPDATE users SET terms_at=? WHERE id=?", (int(time.time()), uid))   # this person's own tick
            c.execute("DELETE FROM email_codes WHERE user_id=?", (uid,))
            c.execute("UPDATE users SET email_verified=1, last_login=? WHERE id=?", (int(time.time()), uid))
            token = _new_session(c, uid)
            row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        _fails.pop(key, None)
    user = public_user(row)
    user["new"] = new
    if removed:
        user["passwordRemoved"] = True
    if g_removed:
        user["googleRemoved"] = True                 # the card stops offering Google to this person (it would answer email_in_use)
    return 200, {"user": user}, token


def oauth_login_ticked(provider, subject, email, agree=False, trusted=True):
    """oauth_login as the sandbox calls it (serve.py, CODE_SIGNIN): a Google login Google vouches for that would join an account whose address
    was never proven (someone else may have opened it, ticking 18+ / Terms for themselves) needs the person's own tick ("agree_owner" otherwise:
    Google has just shown this person owns the address, so the page may say the address has an account that was never finished),
    and terms_at then becomes that tick, the same rule login_with_code follows. oauth_login itself is unchanged (dev and the live site).
    user["finished"] is True when that account had never been signed in to (no password, no other sign-in: what login_with_code calls
    new), so the page says "Account created" for it, as the code would."""
    clean = _clean_email(email)
    with _lock:                                      # one lock for the check and the sign-in (an RLock: oauth_login takes it again)
        with _db() as c:
            known = c.execute("SELECT 1 FROM identities WHERE provider=? AND subject=?", (provider, subject)).fetchone() is not None
            row = c.execute("SELECT id, email_verified, has_password FROM users WHERE email=?", (clean,)).fetchone() if clean else None
            linked = bool(row) and c.execute("SELECT 1 FROM identities WHERE user_id=?", (row["id"],)).fetchone() is not None
        joins_unproven = bool(trusted and not known and row and not row["email_verified"])
        if joins_unproven and agree is not True:
            return "agree_owner", None, None
        err, user, token = oauth_login(provider, subject, email, agree, trusted)
        if not err and joins_unproven:
            with _db() as c:
                c.execute("UPDATE users SET terms_at=? WHERE id=?", (int(time.time()), user["id"]))
            if not row["has_password"] and not linked:
                user["finished"] = True
    return err, user, token


# After a "Continue with Google" round trip the page needs one fact the redirect cannot carry: whether the account was made just now
# (so it says "Account created" and asks the questions, or "You're signed in"). Kept in memory for 10 minutes, never written to the
# database. Google is asked for "openid email" only, so no name comes from Google (asking for its "profile" scope is a question for Saif).
NAME_HINT_SECONDS = 600
_google_hints = {}   # user id -> (new, expires)


def google_linked(user_id):
    """True when a Google login opens this account (an identities row)."""
    try:
        with _lock, _db() as c:
            return c.execute("SELECT 1 FROM identities WHERE user_id=? AND provider='google' LIMIT 1", (int(user_id),)).fetchone() is not None
    except (TypeError, ValueError, sqlite3.Error):
        return False


def remember_google(user_id, new):
    now = time.time()
    with _lock:
        for k in [k for k, v in _google_hints.items() if v[1] < now]:
            del _google_hints[k]
        if len(_google_hints) < 5000:
            _google_hints[user_id] = (bool(new), now + NAME_HINT_SECONDS)


def google_hint(user_id):
    """{"new"} from this account's Google sign-in in the last 10 minutes, or None."""
    with _lock:
        h = _google_hints.get(user_id)
    return {"new": h[0]} if h and h[1] > time.time() else None
# /* end sign-up v2 */ ------------------------------------------------------------------------------------------------------------
