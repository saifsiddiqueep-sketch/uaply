"""Release-night proof that the sign-in gate works on a public server with real email (docs/ACCOUNTS.md, "The sign-in contract").

  python tools/live-signup-check.py --base https://uaply.net --email you@example.com --code-file code.txt [--second-email ...] [--wait 900]

It makes one account at --email through POST /api/auth/signup (first and last name "UAply Check", a generated password printed once on
this terminal and kept nowhere), and checks the answer is 200 with delivery "sent". Each time it needs something from the inbox it empties
--code-file and waits: you read the email and write the 6-digit code (or, for Forgot password, the whole reset link) into that file.
It then checks, printing PASS or FAIL with the status code for every step:
  the code confirms the address; /api/auth/me shows emailVerified true and the names; /api/jobs answers 200 signed in and 401 signed out;
  a second, unconfirmed account (--second-email, by default the same inbox with +check2) gets 403 verify and is deleted again;
  sign-in with the password; "Email me a code" (a sign-in code, again through the file); Forgot password (the reset link, through the file)
  and sign-in with the new password; and finally both accounts are deleted through /api/auth/delete, so nothing is left on the server.
It refuses to run against a server whose /api/auth/providers says testMode or signupTest (a test server sends no real email).
An address gets at most 6 codes a day, and each run sends it 2, so one inbox allows 3 runs a day. Exit code 0: every step passed."""
import argparse
import http.client
import json
import re
import secrets
import sys
import time
import urllib.parse

R = []
SITE = []             # the server being checked (set once the arguments are read)
ACCOUNTS = []          # every account this run made: {"email", "password", "jar", "gone"}, so a failed run still deletes them


def step(name, ok, status, extra=""):
    R.append(bool(ok))
    print("%s [%s] %s%s" % ("PASS" if ok else "FAIL", status, name, ("  (%s)" % extra) if extra and not ok else ""), flush=True)
    return bool(ok)


class Site:
    def __init__(self, base):
        u = urllib.parse.urlsplit(base.rstrip("/"))
        if u.scheme not in ("http", "https") or not u.hostname:
            raise SystemExit("--base must look like https://uaply.net")
        self.https = u.scheme == "https"
        self.host, self.port = u.hostname, u.port
        self.origin = "%s://%s" % (u.scheme, u.netloc)

    def call(self, method, path, body=None, jar=None):
        """(status, JSON answer or {}, the cookies it set). jar: this account's cookies, sent and updated."""
        conn = (http.client.HTTPSConnection if self.https else http.client.HTTPConnection)(self.host, self.port, timeout=60)
        h = {"Accept": "application/json", "User-Agent": "UAplyLiveSignupCheck/1"}
        if method == "POST":
            h["Origin"] = self.origin
            h["Content-Type"] = "application/json"
        if jar:
            h["Cookie"] = "; ".join("%s=%s" % kv for kv in jar.items())
        try:
            conn.request(method, path, body=json.dumps(body if body is not None else {}) if method == "POST" else None, headers=h)
            r = conn.getresponse()
            raw = r.read()
            set_cookies = [v for k, v in r.getheaders() if k.lower() == "set-cookie"]
        except (OSError, http.client.HTTPException) as e:
            return 0, {"error": "%s: %s" % (type(e).__name__, e)}, {}
        finally:
            conn.close()
        got = {}
        for c in set_cookies:
            name, _, rest = c.partition("=")
            value = rest.split(";", 1)[0]
            got[name.strip()] = value
            if jar is not None:
                if value and "max-age=0" not in c.lower():
                    jar[name.strip()] = value
                else:
                    jar.pop(name.strip(), None)
        try:
            j = json.loads(raw or b"{}")
        except ValueError:
            j = {}
        return r.status, j if isinstance(j, dict) else {}, got


def session_of(got):
    return any(k.endswith("_session") and v for k, v in got.items())


def wait_file(path, what, pattern, wait):
    """Empty `path`, ask for `what`, and wait until the file holds a match of `pattern` (its first group)."""
    print("\n>>> Write %s into %s (waiting up to %d s)\n" % (what, path, wait), flush=True)
    end = time.time() + wait
    while time.time() < end:
        try:
            with open(path, encoding="utf-8") as f:
                m = re.search(pattern, f.read())
            if m:
                return m.group(1)
        except OSError:
            pass
        time.sleep(1)
    return ""


def clear(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("")


def password():
    return "Ck-" + secrets.token_urlsafe(18)


def delete(site, acct):
    """Delete one account this run made (signing in first when it has no session), then check it is gone."""
    if acct["gone"]:
        return
    if not any(k.endswith("_session") for k in acct["jar"]):
        site.call("POST", "/api/auth/login", {"email": acct["email"], "password": acct["password"]}, acct["jar"])
    s, j, _ = site.call("POST", "/api/auth/delete", {"password": acct["password"]}, acct["jar"])
    step("delete %s through /api/auth/delete" % acct["email"], s == 200 and j.get("ok") is not False, s, j.get("error", ""))
    s2, j2, _ = site.call("POST", "/api/auth/login", {"email": acct["email"], "password": acct["password"]})
    acct["gone"] = step("...and it is gone: signing in to it answers 401", s2 == 401, s2, j2.get("error", ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", required=True, help="the server, e.g. https://uaply.net")
    ap.add_argument("--email", required=True, help="a real inbox you can read")
    ap.add_argument("--code-file", required=True, help="the file you write each code (or the reset link) into")
    ap.add_argument("--second-email", default="", help="the unconfirmed second account (default: --email with +check2)")
    ap.add_argument("--wait", type=int, default=900, help="seconds to wait for each code (default 900)")
    a = ap.parse_args()
    email = a.email.strip()
    local, at, domain = email.partition("@")
    if not at or not local or "." not in domain:
        raise SystemExit("--email must be a full address")
    second = (a.second_email or "%s+check2@%s" % (local.split("+", 1)[0], domain)).strip()
    if second.lower() == email.lower():
        raise SystemExit("--second-email must differ from --email")
    site = Site(a.base)
    SITE.append(site)
    clear(a.code_file)

    s, prov, _ = site.call("GET", "/api/auth/providers")
    if s != 200:
        step("GET /api/auth/providers answers", False, s, prov.get("error", ""))
        return 1
    if prov.get("testMode") or prov.get("signupTest"):
        print("REFUSED: %s reports testMode: it sends no real email, so this check proves nothing there. Nothing was created." % site.origin)
        return 2
    step("providers: not a test server, and Email me a code is offered", prov.get("codeSignin") is True, s, "codeSignin missing: is email set up?")
    s, j, _ = site.call("GET", "/api/jobs")
    step("signed out, /api/jobs answers 401 signin", s == 401 and j.get("code") == "signin", s, j.get("error", ""))

    # ---- 1. sign-up, and the emailed code confirms the address ----
    acct = {"email": email, "password": password(), "jar": {}, "gone": False}
    print("\nGenerated password for %s (shown once, kept nowhere): %s\n" % (email, acct["password"]), flush=True)
    s, j, got = site.call("POST", "/api/auth/signup", {"email": email, "password": acct["password"], "first": "UAply", "last": "Check", "agree": True}, acct["jar"])
    if s == 200:
        ACCOUNTS.append(acct)
    if not step("sign-up answers 200 with delivery \"sent\" and a session", s == 200 and j.get("delivery") == "sent" and session_of(got), s,
                "delivery=%r %s" % (j.get("delivery"), j.get("error", ""))):
        return 1
    code = wait_file(a.code_file, "the 6-digit code from the email \"NNNNNN is your UAply verification code\" sent to %s" % email, r"\b(\d{6})\b", a.wait)
    s, j, _ = site.call("POST", "/api/auth/verify", {"code": code}, acct["jar"])
    step("the code confirms the address (POST /api/auth/verify)", s == 200 and j.get("ok") is True, s, j.get("error", "") or ("no code in the file" if not code else ""))
    s, j, _ = site.call("GET", "/api/auth/me", jar=acct["jar"])
    u = j.get("user") or {}
    step("/api/auth/me: emailVerified true, first \"UAply\", last \"Check\"", s == 200 and (u.get("emailVerified"), u.get("first"), u.get("last")) == (True, "UAply", "Check"),
         s, "got %r" % ({k: u.get(k) for k in ("emailVerified", "first", "last")},))
    s, j, _ = site.call("GET", "/api/jobs", jar=acct["jar"])
    step("signed in and confirmed, /api/jobs answers 200 with the job list", s == 200 and isinstance(j.get("jobs"), list), s, j.get("error", ""))
    s, j, _ = site.call("GET", "/api/jobs")
    step("...and still 401 signin signed out", s == 401 and j.get("code") == "signin", s, j.get("error", ""))

    # ---- 2. a second account that never confirms: 403 verify, then deleted ----
    b = {"email": second, "password": password(), "jar": {}, "gone": False}
    print("\nSecond account %s, password (shown once): %s\nIts verification email will arrive too: ignore it.\n" % (second, b["password"]), flush=True)
    s, j, got = site.call("POST", "/api/auth/signup", {"email": second, "password": b["password"], "first": "UAply", "last": "Check", "agree": True}, b["jar"])
    if s == 200:
        ACCOUNTS.append(b)
    step("the second, unconfirmed account is made (200, signed in)", s == 200 and session_of(got), s, j.get("error", ""))
    s, j, _ = site.call("GET", "/api/jobs", jar=b["jar"])
    step("...its /api/jobs answers 403 verify (\"Confirm your email first.\")", s == 403 and j.get("code") == "verify", s, j.get("error", ""))
    delete(site, b)

    # ---- 3. sign in with the password ----
    s, j, _ = site.call("POST", "/api/auth/logout", {}, acct["jar"])
    step("sign out", s == 200, s, j.get("error", ""))
    s, j, got = site.call("POST", "/api/auth/login", {"email": email, "password": acct["password"]}, acct["jar"])
    step("sign in with the password", s == 200 and session_of(got) and (j.get("user") or {}).get("emailVerified") is True, s, j.get("error", ""))

    # ---- 4. Email me a code ----
    site.call("POST", "/api/auth/logout", {}, acct["jar"])
    clear(a.code_file)
    s, j, _ = site.call("POST", "/api/auth/code/send", {"email": email}, acct["jar"])
    step("Email me a code: POST /api/auth/code/send answers 200", s == 200, s, "%s %s" % (j.get("code", ""), j.get("error", "")))
    code2 = wait_file(a.code_file, "the 6-digit code from the email \"NNNNNN is your UAply sign-in code\" sent to %s" % email, r"\b(\d{6})\b", a.wait)
    s, j, got = site.call("POST", "/api/auth/code/verify", {"email": email, "code": code2}, acct["jar"])
    step("...the sign-in code signs in (POST /api/auth/code/verify)", s == 200 and session_of(got), s, j.get("error", "") or ("no code in the file" if not code2 else ""))
    s, j, _ = site.call("GET", "/api/auth/me", jar=acct["jar"])
    step("...as this account", s == 200 and ((j.get("user") or {}).get("email") or "").lower() == email.lower(), s)

    # ---- 5. Forgot password ----
    clear(a.code_file)
    s, j, _ = site.call("POST", "/api/auth/forgot", {"email": email})
    step("Forgot password: POST /api/auth/forgot answers 200 and says it was sent", s == 200 and j.get("ok") is not False, s,
         "%s %s" % (j.get("delivery", ""), j.get("error", "")))
    token = wait_file(a.code_file, "the whole reset link from the email \"Reset your UAply password\" sent to %s" % email,
                      r"(?:reset=|^)\s*([A-Za-z0-9_-]{20,})", a.wait)
    new_pw = password()
    s, j, _ = site.call("POST", "/api/auth/reset", {"token": token, "password": new_pw})
    if s == 200:
        acct["password"] = new_pw
        acct["jar"].clear()
        print("\nNew password for %s after the reset (shown once, kept nowhere): %s\n" % (email, new_pw), flush=True)
    step("...the link's token sets a new password (POST /api/auth/reset)", s == 200, s, j.get("error", "") or ("no link in the file" if not token else ""))
    s, j, got = site.call("POST", "/api/auth/login", {"email": email, "password": new_pw}, acct["jar"])
    step("...and the new password signs in", s == 200 and session_of(got), s, j.get("error", ""))
    return 0


if __name__ == "__main__":
    rc = 1
    try:
        rc = main()
    except KeyboardInterrupt:
        print("\nStopped: deleting what this run made.")
    finally:
        if ACCOUNTS and SITE:
            print("\n---- clean-up: delete every account this run made ----", flush=True)
            for acct in ACCOUNTS:
                delete(SITE[0], acct)
        print("\n%d / %d" % (sum(R), len(R)))
    sys.exit(2 if rc == 2 else (0 if R and all(R) and rc == 0 else 1))
