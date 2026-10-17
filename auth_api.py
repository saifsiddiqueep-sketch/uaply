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

A hosted database (instead of this file) is a later step: this module is the stand-in that already behaves like one.
"""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")
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
        for col in ("terms_at INTEGER", "has_password INTEGER NOT NULL DEFAULT 1", "email_verified INTEGER NOT NULL DEFAULT 0",
                    "plan TEXT NOT NULL DEFAULT 'free'", "plan_status TEXT NOT NULL DEFAULT ''", "plan_renews INTEGER NOT NULL DEFAULT 0",
                    "plan_cancel INTEGER NOT NULL DEFAULT 0", "stripe_customer TEXT NOT NULL DEFAULT ''", "stripe_sub TEXT NOT NULL DEFAULT ''",
                    "plan_failed INTEGER NOT NULL DEFAULT 0"):      # databases made before these columns existed
            try:
                c.execute("ALTER TABLE users ADD COLUMN " + col)
            except sqlite3.OperationalError:
                pass
        c.execute("UPDATE users SET email_verified=1 WHERE id IN (SELECT user_id FROM identities)")      # Google already verified those emails


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


def _clean_email(v):
    e = v.strip().lower() if isinstance(v, str) else ""
    return e if EMAIL_RE.match(e) else ""


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
            "plan": (row["plan"] if "plan" in keys and row["plan"] in ("free", "plus", "pro") else "free")}


def billing_row(user_id):
    """The stored subscription of one account, or None."""
    with _db() as c:
        r = c.execute("SELECT id, email, plan, plan_status, plan_renews, plan_cancel, plan_failed, stripe_customer, stripe_sub FROM users WHERE id=?", (user_id,)).fetchone()
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
    allowed = ("plan", "plan_status", "plan_renews", "plan_cancel", "plan_failed", "stripe_customer", "stripe_sub")
    pairs = [(k, v) for k, v in fields.items() if k in allowed]
    if not pairs:
        return
    with _db() as c:
        c.execute("UPDATE users SET %s WHERE id=?" % ", ".join("%s=?" % k for k, _ in pairs), [v for _, v in pairs] + [user_id])


def signup(email, password, ip, agree=False):
    """Returns (status, body, session_token_or_None)."""
    email = _clean_email(email)
    if not email:
        return 400, {"error": "Enter a valid email address."}, None
    if agree is not True:
        return 400, {"error": "Confirm you are 18 or older and agree to the Terms and Privacy Policy."}, None
    if not isinstance(password, str) or not (8 <= len(password) <= 128):
        return 400, {"error": "Use a password between 8 and 128 characters."}, None
    if password.lower() == email:
        return 400, {"error": "Your password cannot be your email."}, None
    with _lock:
        if len(_recent(_signups, ip, 3600)) >= 10:
            return 429, {"error": "Too many sign-ups from this connection. Try again later."}, None
        _signups[ip].append(time.time())
        salt = secrets.token_bytes(16)
        pw_hash = _hash(password, salt)
        now = int(time.time())
        try:
            with _db() as c:
                cur = c.execute("INSERT INTO users(email, salt, hash, created_at, last_login, terms_at) VALUES(?,?,?,?,?,?)",
                                (email, salt, pw_hash, now, now, now))
                uid = cur.lastrowid
                token = _new_session(c, uid)
        except sqlite3.IntegrityError:
            return 409, {"error": "That email already has an account. Log in instead."}, None
    return 200, {"user": {"id": uid, "email": email, "hasPassword": True, "emailVerified": False}}, token


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


def user_for(token):
    if not isinstance(token, str) or not (20 <= len(token) <= 100):
        return None
    with _lock, _db() as c:
        row = c.execute("SELECT u.id, u.email, u.has_password, u.email_verified, u.plan FROM sessions s JOIN users u ON u.id=s.user_id "
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

    `trusted` says the provider is the authority on this email address (for Google: a Gmail address or a Workspace account). An
    untrusted email can still sign in by the provider's account number, but it never proves ownership: it cannot be merged into an
    existing account ("email_in_use") and a new account made with it starts unverified, so the emailed code check applies.

    Linking a trusted email to a password account that never proved its email (no code entered, no reset link used): whoever chose
    that password never showed they own the address, and it may have been someone else who signed up first with this person's Gmail
    to watch the account later. So that password is removed and every other session of the account ends; the owner can add a password
    again with Forgot password. The returned user then carries passwordRemoved=True so the page can say so."""
    email = _clean_email(email)
    if not email or not isinstance(subject, str) or not subject:
        return "failed", None, None
    removed = False
    with _lock:
        with _db() as c:
            row = c.execute("SELECT u.* FROM identities i JOIN users u ON u.id=i.user_id WHERE i.provider=? AND i.subject=?",
                            (provider, subject)).fetchone()
            now = int(time.time())
            if not row:
                row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
                if row and not trusted:
                    return "email_in_use", None, None
                if not row:
                    if agree is not True:
                        return "agree", None, None
                    cur = c.execute("INSERT INTO users(email, salt, hash, created_at, last_login, terms_at, has_password, email_verified) VALUES(?,?,?,?,?,?,0,?)",
                                    (email, secrets.token_bytes(16), secrets.token_bytes(32), now, now, now, 1 if trusted else 0))
                    row = c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
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
    return None, user, token


def _check_new_password(password, email=""):
    if not isinstance(password, str) or not (8 <= len(password) <= 128):
        return "Use a password between 8 and 128 characters."
    if email and password.lower() == email:
        return "Your password cannot be your email."
    return ""


def request_reset(email, ip):
    """Start a password reset. Always answers the same way so nobody can use this to find out who has an account.
    Returns (status, body, mail) where mail is (user_id, email, token) when a link should be sent, else None."""
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
            token = secrets.token_urlsafe(32)
            now = int(time.time())
            c.execute("DELETE FROM password_resets WHERE expires_at < ? OR user_id=?", (now, row["id"]))
            c.execute("INSERT INTO password_resets(token_hash, user_id, expires_at) VALUES(?,?,?)",
                      (hashlib.sha256(token.encode()).hexdigest(), row["id"], now + RESET_SECONDS))
    return ok[0], ok[1], (row["id"], email, token)


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
        return 400, {"error": "This account signs in with Google. Use Forgot password to add a password."}
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
    """The first code, right after sign-up. Returns (user_id, email, digits)."""
    user = user_for(token)
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
        if len(_recent(_code_sends, ("u", user["id"]), 3600)) >= 3 or len(_recent(_code_sends, ("ip", ip), 3600)) >= 12:
            return 429, {"error": "Too many codes requested. Check your inbox and spam folder, or try again in an hour."}, None
        _code_sends[("u", user["id"])].append(time.time())
        _code_sends[("ip", ip)].append(time.time())
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
    digits = "".join(ch for ch in (code if isinstance(code, str) else "") if ch.isdigit())
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
