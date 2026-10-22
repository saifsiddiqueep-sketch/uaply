"""One email address is one account, always. Starts its own throwaway servers (a stand-in Google on PORT+1, a stand-in DNS-over-HTTPS
resolver on PORT+2, UAply on PORT, public as the live site runs it) and stops them at the end:
  python tools/test-accounts.py [port]          (default 20480; uses that port and the next two)
  UAPLY_TEST_REAL_DNS=1 python tools/test-accounts.py     also asks the real dns.google and Cloudflare about gmail.com (opt-in)
Checks:
  1. the canonical key: letter case, spaces around, full-width and other look-alike letters, control characters, spaces, non-ASCII
  2. +tags and Gmail dots are separate accounts (docs/ACCOUNTS.md says why)
  3. the database itself refuses a second row that differs only in letter case
  4. races: 20 sign-ups for one address at the same instant (threads in one server, separate processes on one file, and over HTTP)
  5. Google: an existing password account (unverified, verified), an untrusted address, a Workspace account, an email Google has not
     verified, and a Google account whose email later changes: never a second account
  6. Alice@Example.com, alice@example.com and ALICE@EXAMPLE.COM: sign-up, log-in, Forgot password and the email code reach one account
  7. delete the account, then sign up again with the same address: a fresh, empty account
  8. a mailbox the person can keep: throwaway domains refused, privacy relays always pass, the list files load without repeats, the DNS
     check (no mail server, no such domain, a slow or failing resolver never blocks, the second resolver, the day-long memory), Gmail,
     Yahoo, Outlook, school and work addresses pass; at most five new accounts an hour per visitor address
  9. Stripe events find an account by its number only when the address matches too
 10. tools/audit-accounts.py finds duplicates and changes nothing"""
import hashlib
import http.client
import http.server
import itertools
import json
import multiprocessing
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


# ---------- a stand-in DNS-over-HTTPS resolver (the JSON form dns.google and Cloudflare answer in) that answers from a table ----------
DNS_TABLE = {
    # domain: (status, MX, has A); anything not listed answers NXDOMAIN (status 3)
    "gmail.com": (0, True, True), "yahoo.com": (0, True, True), "outlook.com": (0, True, True), "hotmail.com": (0, True, True),
    "icloud.com": (0, True, True), "temple.edu": (0, True, True), "students.upenn.edu": (0, True, False), "acme-robotics.co.uk": (0, True, True),
    "example.com": (0, "null", True),                   # the real example.com: "MX 0 ." and an address
    "corp-mail.org": (0, True, True), "work-place.org": (0, True, True), "uaply.net": (0, True, True),
    "a-record-only.org": (0, False, True),              # no MX, but an address: mail falls back to it (RFC 5321)
    "null-mx-with-a.org": (0, "null", True),            # "MX 0 ." plus an address: treated like an address-only domain (lenient)
    "parked-nothing.org": (0, False, False),            # exists, but no mail server and no address
    "servfail.org": (2, False, False),                  # the resolver fails: never block
    "slow-dns.org": ("slow", False, False),             # answers after 4 seconds: never block, give up after 3
    "second-only.org": ("second", True, True),          # the first resolver fails, the second answers
}
DNS_HITS = {}


class DoH(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        name, rtype = (q.get("name") or [""])[0].lower(), (q.get("type") or [""])[0]
        DNS_HITS[name] = DNS_HITS.get(name, 0) + 1
        status, mx, a = DNS_TABLE.get(name, (3, False, False))
        if u.path == "/broken" or (u.path == "/first" and status == "second"):
            self.send_response(503)
            self.end_headers()
            return
        if status == "slow":
            time.sleep(4)
            status = 0
        if status == "second":
            status = 0
        ans = []
        if status == 0 and rtype == "MX" and mx:
            ans.append({"name": name + ".", "type": 15, "TTL": 300, "data": "0 ." if mx == "null" else "10 mx.%s." % name})
        if status == 0 and rtype == "A" and a:
            ans.append({"name": name + ".", "type": 1, "TTL": 300, "data": "192.0.2.10"})
        body = json.dumps({"Status": status, "Answer": ans} if ans else {"Status": status}).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/dns-json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass                                            # the asker gave up (the slow case)

    def log_message(self, *a):
        pass


# ---------- separate processes signing up the same address on one database file ----------
def _proc_signup(data_dir, barrier, n, q):
    os.environ["UAPLY_DATA_DIR"] = data_dir
    import auth_api as a
    a.init("race")
    barrier.wait(60)
    q.put(a.signup("Race.Proc@Example.com", "process pass %d" % n, "198.18.9.%d" % n, True)[0])


def main():
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20480
    MPORT, DPORT = PORT + 1, PORT + 2
    ADDR = "127.0.0.2"
    SITE = "uaply.net"
    TMP = tempfile.mkdtemp(prefix="uaply-accounts-")
    DOH = "http://127.0.0.1:%d/first,http://127.0.0.1:%d/resolve" % (DPORT, DPORT)       # two resolvers, as on the live site
    os.environ.update(UAPLY_DATA_DIR=os.path.join(TMP, "unit"), UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}", UAPLY_DOH_URLS=DOH)
    import auth_api
    canon = getattr(auth_api, "canonical_email", auth_api._clean_email)
    auth_api.init("unit")
    doh = http.server.ThreadingHTTPServer(("127.0.0.1", DPORT), DoH)
    doh.daemon_threads = True
    threading.Thread(target=doh.serve_forever, daemon=True).start()
    PROCS = []
    ctr = itertools.count(0)                             # one made-up visitor address per request (next() on a count is safe across threads)

    class _Ips:
        def __next__(self):
            i = next(ctr)
            return "198.19.%d.%d" % (i // 250, i % 250 + 1)
    ips = _Ips()

    def db_count(path, where="1=1", args=()):
        with sqlite3.connect(path) as c:
            return c.execute("SELECT COUNT(*) FROM users WHERE " + where, args).fetchone()[0]

    UNIT_DB = os.path.join(TMP, "unit", "unit", "uaply.db")
    try:
        # ---------- 1. the canonical key ----------
        same = [("Alice@Example.com", "lower case"), ("  alice@example.com\t", "spaces and a tab around it trimmed"),
                ("ALICE@EXAMPLE.COM", "all capitals"), ("alice@EXAMPLE.com", "the domain lower-cased"), ("alice@example.com\n", "a line break at the end trimmed"),
                ("\u00a0alice@example.com", "a no-break space in front trimmed"),
                ("\uff41\uff4c\uff49\uff43\uff45\uff20\uff45\uff58\uff41\uff4d\uff50\uff4c\uff45\uff0e\uff43\uff4f\uff4d", "full-width letters (NFKC)"),
                ("\uff21lice@example.com", "one full-width capital (NFKC)")]
        for raw, why in same:
            t("canonical key: %s -> alice@example.com" % why, canon(raw), "alice@example.com")
        t("canonical key: the Kelvin sign K is the letter k", canon("\u212aate@example.com"), "kate@example.com")
        for raw, why in [("ali ce@example.com", "a space inside"), ("alice\x00@example.com", "a NUL"), ("alice@exa\x7fmple.com", "DEL"),
                         ("al\u200bice@example.com", "a zero-width space"), ("alice\u00ad@example.com", "a soft hyphen"),
                         ("al\u00efce@example.com", "a non-ASCII letter in the local part"), ("alice@ex\u00e4mple.com", "a non-ASCII domain"),
                         ("\u0430lice@example.com", "a Cyrillic look-alike a"), ("alice\r\n@example.com", "a line break inside"),
                         ("alice@@example.com", "two @"), ("a" * 65 + "@example.com", "a 65-character local part"), (None, "not text"),
                         ("x" * 500, "500 characters")]:
            t("canonical key: %s is refused" % why, canon(raw), "")
        t("canonical key: a +tag is kept", canon("Owner+Live1@Gmail.com"), "owner+live1@gmail.com")
        t("canonical key: Gmail dots are kept", canon("O.W.N.E.R@gmail.com"), "o.w.n.e.r@gmail.com")

        # ---------- 2. +tags and dots are separate accounts; 6. case variants, in the module ----------
        s, out, tok_a = auth_api.signup("Alice@Example.com", "alice pass 123", next(ips), True)
        t("sign-up as Alice@Example.com is stored as alice@example.com", (s, out.get("user", {}).get("email")), (200, "alice@example.com"))
        uid_a = out["user"]["id"]
        t("sign-up again as alice@example.com, ALICE@EXAMPLE.COM, full-width or with spaces: refused as taken (409), no second account",
          [auth_api.signup(v, "other pass 123", next(ips), True)[0] for v in ("alice@example.com", "ALICE@EXAMPLE.COM", " Alice@Example.COM ",
                                                                                 "\uff41\uff4c\uff49\uff43\uff45@example.com")], [409] * 4)
        t("...one account for that address in the file", db_count(UNIT_DB, "lower(email)='alice@example.com'"), 1)
        ids = {}
        for v in ("owner@gmail.com", "owner+live1@gmail.com", "owner+live2@gmail.com", "o.w.n.e.r@gmail.com", "owner@googlemail.com"):
            s, out, _ = auth_api.signup(v, "owner pass 123", next(ips), True)
            ids[v] = out.get("user", {}).get("id") if s == 200 else s
        t("owner@gmail.com, owner+live1, owner+live2, o.w.n.e.r and owner@googlemail.com are five separate accounts",
          len(set(ids.values())) == 5 and all(isinstance(x, int) for x in ids.values()), True)

        # ---------- 3. the database refuses a letter-case twin ----------
        try:
            with sqlite3.connect(UNIT_DB) as c:
                c.execute("INSERT INTO users(email, salt, hash, created_at, last_login) VALUES('ALICE@example.com', x'00', x'00', 0, 0)")
            twin = "inserted"
        except sqlite3.IntegrityError:
            twin = "refused"
        t("the database itself refuses ALICE@example.com next to alice@example.com (a code path that forgot to clean it)", twin, "refused")

        # ---------- 6. the four paths with case variants ----------
        logins = [auth_api.login(v, "alice pass 123", "198.18.200.1") for v in ("alice@example.com", "ALICE@EXAMPLE.COM", "Alice@Example.com",
                                                                               "\uff21lice@example.com")]
        t("log-in as alice@, ALICE@, Alice@ and full-width: all four open account %d" % uid_a,
          [(s, (o.get("user") or {}).get("id")) for s, o, _ in logins], [(200, uid_a)] * 4)
        wrong = [auth_api.login(v, "nope nope", "198.18.200.2")[0] for v in ("alice@example.com", "ALICE@EXAMPLE.COM", "Alice@Example.com",
                                                                           "alice@EXAMPLE.com", "aLiCe@example.com", "alice@example.com")]
        t("wrong passwords under five spellings count against one address: the sixth try is held back", wrong, [401] * 5 + [429])
        uid, addr, digits = auth_api.issue_code_for_token(tok_a)
        t("the email code for Alice@Example.com goes to alice@example.com", (uid, addr), (uid_a, "alice@example.com"))
        tok_caps = logins[1][2]
        t("the code typed in a session opened as ALICE@EXAMPLE.COM verifies the same account", auth_api.verify_code(tok_caps, digits, "198.18.200.3")[0], 200)
        t("...and the first session (Alice@Example.com) sees it verified", (auth_api.user_for(tok_a) or {}).get("emailVerified"), True)
        resets = [auth_api.request_reset(v, "198.18.201.%d" % i) for i, v in enumerate(("Alice@Example.com", "alice@example.com", "ALICE@EXAMPLE.COM"))]
        t("Forgot password as Alice@, alice@ and ALICE@: each link is for account %d at alice@example.com" % uid_a,
          [(m[0], m[1]) if m else None for _, _, m in resets], [(uid_a, "alice@example.com")] * 3)
        t("...and the limit of three an hour counts them as one address (a fourth spelling is held back)",
          auth_api.request_reset(" aLIce@example.COM ", "198.18.201.9")[0], 429)
        t("the newest link resets the password", auth_api.reset_password(resets[-1][2][2], "brand new pass 1", "198.18.201.10")[0], 200)
        s, _, tok_a = auth_api.login("\uff41lice@example.com", "brand new pass 1", "198.18.201.11")
        t("...and the new password works from a full-width spelling", s, 200)

        # ---------- 4a. 20 threads in one process ----------
        go = threading.Barrier(20)
        got = []

        def one(n):
            go.wait()
            got.append(auth_api.signup("Race.Thread@Example.com" if n % 2 else "race.thread@example.com", "thread pass %d" % n, "198.18.50.%d" % n, True)[0])
        th = [threading.Thread(target=one, args=(n,)) for n in range(20)]
        for x in th:
            x.start()
        for x in th:
            x.join(120)
        t("20 sign-ups for one address at the same instant (threads): exactly one succeeds, 19 are told it is taken", sorted(got), [200] + [409] * 19)
        t("...one account in the file", db_count(UNIT_DB, "email='race.thread@example.com'"), 1)

        # ---------- 4b. 20 separate processes on one file (the database's own rule, no shared lock) ----------
        os.environ["UAPLY_DATA_DIR"] = os.path.join(TMP, "procs")
        auth_api.init("race")                               # make the file and its tables first
        os.environ["UAPLY_DATA_DIR"] = os.path.join(TMP, "unit")
        auth_api.init("unit")
        mp = multiprocessing.get_context("spawn")
        bar, q = mp.Barrier(20), mp.Queue()
        ps = [mp.Process(target=_proc_signup, args=(os.path.join(TMP, "procs"), bar, n, q)) for n in range(20)]
        for p in ps:
            p.start()
        codes = []
        for _ in ps:
            try:
                codes.append(q.get(timeout=180))
            except Exception:
                codes.append("timeout")
        for p in ps:
            p.join(30)
        t("20 sign-ups for one address at the same instant (20 processes, one file): exactly one succeeds", sorted(codes, key=str), [200] + [409] * 19)
        t("...one account in the file", db_count(os.path.join(TMP, "procs", "race", "uaply.db"), "email='race.proc@example.com'"), 1)

        # ---------- 8. a mailbox the person can keep ----------
        listed = auth_api.disposable_domains()
        with open(os.path.join(HERE, "data", "disposable-domains.txt"), encoding="utf-8") as f:
            lines = [ln.split("#", 1)[0].strip() for ln in f]
        entries = [x for x in lines if x]
        t("the throwaway list file loads (more than 100 domains)", len(listed) > 100, True)
        t("...every entry is written once (no repeats)", sorted(x for x in set(entries) if entries.count(x) > 1), [])
        t("...the loaded list has no repeats either and matches the file", (len(listed), set(entries)), (len(set(entries)), set(listed)))
        t("...every entry is a plain lower-case domain", [x for x in entries if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", x)], [])
        keep = ("gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com", "icloud.com", "aol.com", "proton.me",
                "protonmail.com", "temple.edu", "upenn.edu", "phila.gov", "comcast.net")
        t("...and holds no address people keep (Gmail, Yahoo, Outlook, iCloud, AOL, Proton, schools, work)", [d for d in keep if auth_api.is_disposable("x@" + d)], [])
        for d in ("mailinator.com", "guerrillamail.com", "10minutemail.com", "temp-mail.org", "yopmail.com", "sharklasers.com", "getnada.com",
                  "dispostable.com", "trashmail.com", "maildrop.cc"):
            s, out, _ = auth_api.signup("someone@" + d, "throwaway pass 1", next(ips), True)
            t("sign-up with a %s address is refused, kindly" % d, (s, out.get("error")), (400, auth_api.KEEP_MSG))
        t("...and a subdomain of one too (box.mailinator.com)", auth_api.signup("me@box.mailinator.com", "throwaway pass 1", next(ips), True)[0], 400)
        t("...upper case does not slip past it (ME@YOPMAIL.COM)", auth_api.signup("ME@YOPMAIL.COM", "throwaway pass 1", next(ips), True)[0], 400)
        t("...and a lookalike that is not on the list is not caught by accident (notyopmail.com is its own domain)", auth_api.is_disposable("a@notyopmail.com"), False)
        t("Google cannot make a new account with a throwaway address either",
          auth_api.oauth_login("google", "disp-1", "someone@mailinator.com", True, False)[0], "disposable")

        # Google and an account whose address was never proven: the owner's own 18+ / Terms tick first; and a real "created" flag
        err, gu, _ = auth_api.oauth_login("google", "made-1", "made.by.google@gmail.com", True, True)
        t("Google making a new account says so: created", (err, (gu or {}).get("created")), (None, True))
        err, gu, _ = auth_api.oauth_login("google", "made-1", "made.by.google@gmail.com", True, True)
        t("...and the next Google sign-in to it (seconds later) does not: no created flag", (err, "created" in (gu or {})), (None, False))
        s, out, _ = auth_api.signup("opened.by.someone@gmail.com", "someone else 1", next(ips), True)
        with sqlite3.connect(auth_api._path) as c:
            c.execute("UPDATE users SET terms_at=? WHERE email=?", (int(time.time()) - 3600, "opened.by.someone@gmail.com"))
        err, gu, gt = auth_api.oauth_login("google", "owner-1", "opened.by.someone@gmail.com", False, True)
        t("Google joining an account nobody proved the address for, without the owner's tick: asks for it, signs nobody in", (err, gt), ("agree", None))
        with sqlite3.connect(auth_api._path) as c:
            has_pw = c.execute("SELECT has_password FROM users WHERE email=?", ("opened.by.someone@gmail.com",)).fetchone()[0]
        t("...and changes nothing (the password is still there until the owner ticks)", has_pw, 1)
        before = int(time.time())
        err, gu, gt = auth_api.oauth_login("google", "owner-1", "opened.by.someone@gmail.com", True, True)
        with sqlite3.connect(auth_api._path) as c:
            ta = c.execute("SELECT terms_at FROM users WHERE email=?", ("opened.by.someone@gmail.com",)).fetchone()[0]
        t("...with the tick: joined, the unproven password removed, not called created, and the tick on record is the owner's",
          (err, bool(gt), (gu or {}).get("passwordRemoved"), "created" in (gu or {}), ta >= before), (None, True, True, False, True))
        err, gu, gt = auth_api.oauth_login("google", "owner-1", "opened.by.someone@gmail.com", False, True)
        t("...after that the same Google account signs in with no tick (the address is proven now)", (err, bool(gt)), (None, True))
        dash = chr(0x2014)
        t("the refusal is the one kind sentence", auth_api.KEEP_MSG,
          "Please use an email address you'll keep " + dash + " temporary addresses can't be used for job applications.")
        relays = auth_api.relay_domains()
        t("the privacy relay list loads: Apple Hide My Email, DuckDuckGo, Firefox Relay, SimpleLogin, addy.io",
          {"privaterelay.appleid.com", "duck.com", "mozmail.com", "simplelogin.co", "simplelogin.com", "anonaddy.me", "anonaddy.com", "addy.io"} <= relays, True)
        for v in ("abc123xyz@privaterelay.appleid.com", "quiet.fox@duck.com", "x7k2@mozmail.com", "me.alias@simplelogin.co", "jobs@me.anonaddy.com",
                  "jobs@addy.io", "info@acme-robotics.co.uk", "support@temple.edu"):
            t("sign-up with %s passes (a privacy relay or a role address), even with the DNS check on" % v,
              auth_api.signup(v, "relay pass 123", next(ips), True, True)[0], 200)
        extra = os.path.join(TMP, "throwaway-with-a-relay.txt")
        with open(extra, "w", encoding="utf-8") as f:
            f.write("mailinator.com\nduck.com\nmailinator.com\n")
        real_file, auth_api.DISPOSABLE_FILE = auth_api.DISPOSABLE_FILE, extra
        t("a relay wrongly added to the throwaway list still passes (the relay list is asked first); repeats in the file are dropped",
          (auth_api.is_disposable("a@duck.com"), auth_api.is_disposable("a@mailinator.com"), len(auth_api.disposable_domains())), (False, True, 2))
        auth_api.DISPOSABLE_FILE = real_file

        status = {d: auth_api.mail_domain_status(d) for d in ("gmail.com", "yahoo.com", "outlook.com", "temple.edu", "students.upenn.edu",
                                                              "acme-robotics.co.uk", "a-record-only.org", "null-mx-with-a.org")}
        t("DNS: Gmail, Yahoo, Outlook, a school, a school with mail only (MX, no address), a work domain, an address-only domain: all can receive mail",
          status, dict.fromkeys(status, "ok"))
        t("DNS: a domain that does not exist cannot", auth_api.mail_domain_status("no-such-domain-here.org"), "none")
        t("DNS: a domain with no mail server and no address cannot", auth_api.mail_domain_status("parked-nothing.org"), "none")
        t("DNS: a resolver failure (SERVFAIL) is 'unknown', which never blocks", auth_api.mail_domain_status("servfail.org"), "unknown")
        t("DNS: when the first resolver fails, the second one answers", auth_api.mail_domain_status("second-only.org"), "ok")
        before = DNS_HITS.get("gmail.com", 0)
        again = [auth_api.mail_domain_status("gmail.com") for _ in range(5)]
        t("DNS: a verdict is remembered (five more sign-ups at gmail.com ask the resolver nothing)", (again, DNS_HITS.get("gmail.com", 0) - before), (["ok"] * 5, 0))
        t("DNS: ...for a day", 86000 < auth_api._dns_cache["gmail.com"][1] - time.time() <= 86400, True)
        os.environ["UAPLY_DOH_URLS"] = "http://127.0.0.1:%d/resolve" % DPORT
        t0 = time.monotonic()
        slow = auth_api.mail_domain_status("slow-dns.org")
        took = time.monotonic() - t0
        t("DNS: a resolver slower than 3 seconds is 'unknown' (never blocks) and is given up on after 3 seconds", (slow, 2.5 < took < 3.9), ("unknown", True))
        t("DNS: ...and 'unknown' is not remembered (the next sign-up asks again)", "slow-dns.org" in auth_api._dns_cache, False)
        os.environ["UAPLY_DOH_URLS"] = "http://127.0.0.1:%d/resolve" % (PORT + 19)          # nothing listens there
        t("DNS: an unreachable resolver is 'unknown' too", auth_api.mail_domain_status("unreached.org"), "unknown")
        os.environ["UAPLY_DOH_URLS"] = DOH
        s, out, _ = auth_api.signup("someone@no-such-domain-here.org", "dns pass 123", next(ips), True, True)
        t("sign-up with the DNS check refuses a domain that does not exist, and says why", (s, "no-such-domain-here.org" in out.get("error", "")), (400, True))
        t("...but the same address passes when the check is off (the owner's own computer, no email connected)",
          auth_api.signup("someone@no-such-domain-here.org", "dns pass 123", next(ips), True, False)[0], 200)
        t("...and a slow resolver lets a real person through", auth_api.signup("real.person@slow-dns.org", "dns pass 123", next(ips), True, True)[0], 200)
        for v in ("jane.doe@gmail.com", "jane@yahoo.com", "jane@outlook.com", "jdoe@temple.edu", "jdoe@students.upenn.edu", "jane@acme-robotics.co.uk"):
            t("sign-up with the DNS check: %s passes" % v, auth_api.signup(v, "dns pass 123", next(ips), True, True)[0], 200)
        t("the DNS check never talks to a mail server (no SMTP probe on port 25 anywhere in auth_api)",
          bool(re.search(r"smtplib|, 25\)|:25\b", open(os.path.join(ROOT, "auth_api.py"), encoding="utf-8").read())), False)
        if os.environ.get("UAPLY_TEST_REAL_DNS") == "1":       # opt-in: ask dns.google and Cloudflare for real
            os.environ.pop("UAPLY_DOH_URLS", None)
            auth_api._dns_cache.clear()
            t("real DNS over HTTPS: gmail.com receives mail", auth_api.mail_domain_status("gmail.com"), "ok")
            t("real DNS over HTTPS: a made-up domain does not", auth_api.mail_domain_status("no-such-domain-uaply-%d.com" % os.getpid()), "none")
            os.environ["UAPLY_DOH_URLS"] = DOH

        # ---------- 9. Stripe: the account number counts only with the matching address ----------
        import billing_api
        a1 = auth_api.billing_row(uid_a)
        t("a Stripe object naming account %d with its own address finds it" % uid_a, billing_api._uid({"uaply_user": str(uid_a), "uaply_email": "alice@example.com"}, "", ""), uid_a)
        t("...in any letter case", billing_api._uid({"uaply_user": str(uid_a), "uaply_email": "ALICE@Example.com"}, "", ""), uid_a)
        t("a Stripe object naming account %d with ANOTHER address (a number reused after the accounts file was lost) finds nobody" % uid_a,
          billing_api._uid({"uaply_user": str(uid_a), "uaply_email": "someone.else@example.com"}, "", ""), None)
        t("an older object with only the number still works (nothing paid is lost)", billing_api._uid({"uaply_user": str(uid_a)}, "", ""), uid_a)
        sent = {}
        billing_api._stripe = lambda m, p, params=None: (sent.update(params or {}), (200, {"url": "https://checkout.stripe.com/x"}))[1]
        billing_api.settings = lambda: {"on": True, "test": True, "price_plus": "price_p", "price_pro": "price_q", "secret_key": "sk_test_x"}
        billing_api.checkout(dict(auth_api.user_for(tok_a), emailVerified=True), "plus", "https://uaply.net")
        t("checkout sends the account's address with its number (session and subscription)",
          (sent.get("metadata[uaply_email]"), sent.get("subscription_data[metadata][uaply_email]")), ("alice@example.com", "alice@example.com"))
        del a1

        # ---------- 10. the audit tool ----------
        clean = subprocess.run([sys.executable, os.path.join(HERE, "audit-accounts.py"), os.path.join(TMP, "unit")], capture_output=True, text=True)
        t("audit-accounts.py on this test's accounts: no problems (exit 0), and it notes the owner@gmail.com inbox with several accounts",
          (clean.returncode, "one inbox, several accounts" in clean.stdout, "o***@gmail.com" in clean.stdout), (0, True, True))
        bad_dir = os.path.join(TMP, "old")
        os.makedirs(os.path.join(bad_dir, "dev"))
        bad_db = os.path.join(bad_dir, "dev", "uaply.db")
        with sqlite3.connect(bad_db) as c:                 # a file from before the letter-case index, with a twin pair and a stray row
            c.execute("CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, salt BLOB, hash BLOB, created_at INTEGER, last_login INTEGER)")
            c.execute("CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER, created_at INTEGER, expires_at INTEGER)")
            c.executemany("INSERT INTO users(email, salt, hash, created_at, last_login) VALUES(?,x'00',x'00',0,0)",
                          [("bob@example.com",), ("Bob@Example.com",), ("carol@example.com",)])
            c.execute("INSERT INTO sessions VALUES('x', 99, 0, 0)")
        before = hashlib.sha256(open(bad_db, "rb").read()).hexdigest()
        res = subprocess.run([sys.executable, os.path.join(HERE, "audit-accounts.py"), bad_dir], capture_output=True, text=True)
        t("audit-accounts.py on an old file with Bob@ and bob@: exit 1, one DUPLICATE, the NOT CANONICAL row and the ORPHAN session",
          (res.returncode, res.stdout.count("DUPLICATE"), "NOT CANONICAL  account 2" in res.stdout, "ORPHAN  sessions" in res.stdout), (1, 1, True, True))
        t("...addresses are masked unless --full", ("b***@example.com" in res.stdout, "bob@example.com" in res.stdout), (True, False))
        t("...and the file is unchanged byte for byte (read-only)", hashlib.sha256(open(bad_db, "rb").read()).hexdigest(), before)
        os.environ["UAPLY_DATA_DIR"] = bad_dir
        try:
            auth_api.init("dev")
            started = True
        except Exception:
            started = False
        os.environ["UAPLY_DATA_DIR"] = os.path.join(TMP, "unit")
        auth_api.init("unit")
        t("a server whose old file already holds such a pair still starts (and says to run the audit)", started, True)

        # ================= over HTTP, as the live site runs =================
        DATA = os.path.join(TMP, "http")
        CFG = {"feeds": [], "smtp": {}, "owner_copy": "", "public_url": "https://uaply.net",
               "google": {"client_id": "test.apps.googleusercontent.com", "client_secret": "test-secret", "public_url": "https://uaply.net",
                          "auth_url": "http://127.0.0.1:%d/auth" % MPORT, "token_url": "http://127.0.0.1:%d/token" % MPORT,
                          "certs_url": "http://127.0.0.1:%d/certs" % MPORT}}
        PROCS.append(subprocess.Popen([sys.executable, os.path.join(HERE, "mock-google.py"), str(MPORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        env = dict(os.environ, HOST=ADDR, UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=DATA, OWNER_PASSWORD="ownerpw", UAPLY_CONFIG_JSON=json.dumps(CFG),
                   UAPLY_DNS_CHECK="on", UAPLY_DOH_URLS=DOH)
        env.pop("ANTHROPIC_API_KEY", None)
        log_path = os.path.join(TMP, "server.log")
        log = open(log_path, "w", encoding="utf-8")
        PROCS.append(subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(PORT), "dev", "--api"], cwd=ROOT, env=env,
                                      stdout=subprocess.DEVNULL, stderr=log))

        def req(method, path, body=None, cookie="", xff=None):
            h = {"Host": SITE, "X-Forwarded-Proto": "https", "X-Forwarded-For": (xff or next(ips)) + ", 10.0.0.1", "Origin": "https://" + SITE}
            if cookie:
                h["Cookie"] = cookie
            if body is not None:
                h["Content-Type"] = "application/json"
            c = http.client.HTTPConnection(ADDR, PORT, timeout=180)
            c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
            r = c.getresponse()
            raw = r.read()
            ck = r.msg.get_all("Set-Cookie") or []
            c.close()
            try:
                data = json.loads(raw)
            except ValueError:
                data = None
            tok = next((m.group(1) for m in (re.match(r"uaply_dev_session=([^;]+)", x) for x in ck) if m), "")
            return r.status, data or {}, ("uaply_dev_session=" + tok if tok else "")

        for _ in range(80):
            try:
                if req("GET", "/healthz")[0] == 200:
                    break
            except OSError:
                time.sleep(0.25)
        time.sleep(1.5)                                       # the stand-in Google makes its signing key first

        def signup(email, pw="http pass 123"):
            return req("POST", "/api/auth/signup", {"email": email, "password": pw, "agree": True})

        def me(cookie):
            return req("GET", "/api/auth/me", cookie=cookie)[1].get("user")

        def gtoken(email, sub, **extra):
            q = dict(email=email, sub=sub, **extra)
            return json.loads(urllib.request.urlopen("http://127.0.0.1:%d/mock/idtoken?%s" % (MPORT, urllib.parse.urlencode(q))).read())["credential"]

        def google(email, sub, agree=True, cred=None, **extra):
            return req("POST", "/api/auth/google/token", {"credential": cred or gtoken(email, sub, **extra), "agree": agree})

        HDB = os.path.join(DATA, "dev", "uaply.db")

        def count(email):
            return db_count(HDB, "lower(email)=?", (email.lower(),))

        def identities(sub):
            with sqlite3.connect(HDB) as c:
                return [r[0] for r in c.execute("SELECT user_id FROM identities WHERE provider='google' AND subject=?", (sub,))]

        def code_for(email):
            with sqlite3.connect(HDB) as c:
                row = c.execute("SELECT subject FROM user_mail WHERE to_addr=? ORDER BY id DESC LIMIT 1", (email,)).fetchone()
            m = re.match(r"\s*(\d{6})", row[0] if row else "")
            return m.group(1) if m else ""

        # 6 over HTTP
        s, out, ck = signup("Hal@Example.com")
        hal = out.get("user", {}).get("id")
        t("HTTP: sign-up as Hal@Example.com", (s, out.get("user", {}).get("email")), (200, "hal@example.com"))
        t("HTTP: hal@, HAL@ and full-width sign-ups are refused as taken",
          [signup(v)[0] for v in ("hal@example.com", "HAL@EXAMPLE.COM", "\uff48al@example.com")], [409, 409, 409])
        t("HTTP: log-in as hal@, HAL@, Hal@ and full-width opens the one account",
          [(lambda r: (r[0], r[1].get("user", {}).get("id")))(req("POST", "/api/auth/login", {"email": v, "password": "http pass 123"}))
           for v in ("hal@example.com", "HAL@EXAMPLE.COM", "Hal@Example.com", "\uff28al@example.com")], [(200, hal)] * 4)

        # 4c: 20 at once over HTTP, each from its own address (the per-connection sign-up limit is not what stops them)
        res = []
        go2 = threading.Barrier(20)

        def web(n):
            go2.wait()
            res.append(signup(("Race.Web@Example.com", "race.web@example.com", "RACE.WEB@EXAMPLE.COM")[n % 3], "web pass %d" % n)[0])
        th = [threading.Thread(target=web, args=(n,)) for n in range(20)]
        for x in th:
            x.start()
        for x in th:
            x.join(240)
        t("HTTP: 20 sign-ups for one address (three spellings) at the same instant: exactly one succeeds", sorted(res), [200] + [409] * 19)
        t("HTTP: ...one account in the file", count("race.web@example.com"), 1)

        # a password sign-up and a Google sign-in for the same new Gmail address at the same instant, ten of each, eight rounds (a Google
        # sign-in landing between "account made" and "first code made" once answered the sign-up with 500: both are one locked step now)
        rounds = []
        for k in range(8):
            res2 = []
            go3 = threading.Barrier(20)
            addr = "mixed.race%d@gmail.com" % k
            creds = [gtoken(addr, "mix-sub-%d" % k) for _ in range(10)]      # made before the start line: only UAply is raced

            def mixed(n):
                go3.wait()
                r = signup(addr.replace("mixed", "Mixed")) if n % 2 else google(addr, "mix-sub-%d" % k, cred=creds[n // 2])
                res2.append(r[0])
            th = [threading.Thread(target=mixed, args=(n,)) for n in range(20)]
            for x in th:
                x.start()
            for x in th:
                x.join(240)
            rounds.append((count(addr), len(identities("mix-sub-%d" % k)), sorted(set(res2) - {200, 409})))
        t("HTTP: ten password sign-ups and ten Google sign-ins for one new Gmail address at once, eight times: one account, one Google link, "
          "only 200 or 409 answers", rounds, [(1, 1, [])] * 8)

        # 5. Google linking
        s, out, att = signup("Link.Me@Gmail.com")
        pid = out.get("user", {}).get("id")
        s, out, _ = google("LINK.ME@gmail.com", "g-link")
        t("Google (trusted Gmail) + an UNVERIFIED password account with that address in other letter case: joins it, password removed",
          (s, out.get("user", {}).get("id"), out.get("passwordRemoved"), count("link.me@gmail.com")), (200, pid, True, 1))
        t("...the one who set that password is signed out", me(att), None)
        s, out, vck = signup("Proven.Two@Gmail.com")
        vid = out.get("user", {}).get("id")
        req("POST", "/api/auth/verify", {"code": code_for("proven.two@gmail.com")}, cookie=vck)
        s, out, _ = google("PROVEN.TWO@GMAIL.COM", "g-proven")
        t("Google + a VERIFIED password account: joins it and keeps the password, still one account",
          (s, out.get("user", {}).get("id"), out.get("user", {}).get("hasPassword"), count("proven.two@gmail.com")), (200, vid, True, 1))
        signup("dana@corp-mail.org")
        s, out, _ = google("Dana@Corp-Mail.org", "g-dana")
        t("Google with an address Google is not the authority on + an unverified password account: refused, no second account, no link",
          (s, out.get("code"), count("dana@corp-mail.org"), identities("g-dana")), (400, "email_in_use", 1, []))
        s, out, eck = signup("erin@corp-mail.org")
        req("POST", "/api/auth/verify", {"code": code_for("erin@corp-mail.org")}, cookie=eck)
        s, out, _ = google("erin@corp-mail.org", "g-erin")
        t("...the same for a verified password account", (s, out.get("code"), count("erin@corp-mail.org"), identities("g-erin")), (400, "email_in_use", 1, []))
        s, out, _ = signup("Wes@Work-Place.org")
        wid = out.get("user", {}).get("id")
        s, out, _ = google("wes@work-place.org", "g-wes", hd="work-place.org")
        t("a Google Workspace account (Google is the authority there) joins the unverified password account, one account",
          (s, out.get("user", {}).get("id"), out.get("passwordRemoved"), count("wes@work-place.org")), (200, wid, True, 1))
        s, out, _ = google("Hal@Example.com", "g-unverified", verified="0")
        t("an email Google has not verified is refused and links nothing", (s, out.get("code"), identities("g-unverified"), count("hal@example.com")), (400, "unverified", [], 1))
        s, out, _ = google("only.google@gmail.com", "g-only")
        gid = out.get("user", {}).get("id")
        t("a Google-only account, then a password sign-up with that address in capitals: refused as taken", signup("ONLY.GOOGLE@GMAIL.COM")[0], 409)
        s, out, _ = google("before.change@gmail.com", "g-moves")
        mid = out.get("user", {}).get("id")
        s, out, _ = google("after.change@gmail.com", "g-moves")
        t("a Google account whose email changes keeps signing into the same account, no new one",
          (s, out.get("user", {}).get("id"), count("after.change@gmail.com")), (200, mid, 0))
        s, out, _ = signup("after.change@gmail.com")
        other = out.get("user", {}).get("id")
        s, out, _ = google("after.change@gmail.com", "g-moves")
        t("...even when someone has since made an account with the new address: Google still opens the first account, the other is untouched",
          (out.get("user", {}).get("id"), identities("g-moves"), count("after.change@gmail.com"), s), (mid, [mid], 1, 200))
        s, out, _ = google("moved.away@corp-mail.org", "g-moves")
        t("...and when it changes to an address Google is not the authority on: same account", out.get("user", {}).get("id"), mid)
        del gid, other

        # 7. delete, then sign up again
        s, out, dck = signup("Del.Me@Example.com", "first pass 123")
        d1 = out.get("user", {}).get("id")
        t("delete the account (password)", req("POST", "/api/auth/delete", {"password": "first pass 123"}, cookie=dck)[0], 200)
        t("...its session is gone", me(dck), None)
        s, out, d2ck = signup("del.me@example.com", "second pass 123")
        d2 = out.get("user", {}).get("id")
        t("sign up again with the same address: works, and it is a NEW account number", (s, isinstance(d2, int) and d2 != d1), (200, True))
        u2 = me(d2ck) or {}
        t("...fresh: unverified, free plan, one account for the address", (u2.get("emailVerified"), u2.get("plan"), count("del.me@example.com")), (False, "free", 1))
        t("...the old password does not open it; the new one does",
          [req("POST", "/api/auth/login", {"email": "del.me@example.com", "password": p})[0] for p in ("first pass 123", "second pass 123")], [401, 200])
        s, out, gck = google("gone.google@gmail.com", "g-gone")
        g1 = out.get("user", {}).get("id")
        t("delete a Google account (type DELETE)", req("POST", "/api/auth/delete", {"confirm": "DELETE"}, cookie=gck)[0], 200)
        t("...its Google link went with it", identities("g-gone"), [])
        s, out, _ = google("gone.google@gmail.com", "g-gone", agree=False)
        t("Google again: treated as new (asks for the 18+ and Terms box first)", out.get("code"), "agree")
        s, out, _ = google("gone.google@gmail.com", "g-gone")
        t("...and then a NEW account number, one account for the address", (s, out.get("user", {}).get("id") not in (None, g1), count("gone.google@gmail.com")), (200, True, 1))

        # 8 over HTTP: throwaway domains and DNS
        s, out, _ = signup("jobs@mailinator.com")
        t("HTTP: sign-up with a throwaway address: refused with the kind sentence", (s, out.get("error")), (400, auth_api.KEEP_MSG))
        t("HTTP: a privacy relay (Apple Hide My Email) passes, even though DNS here knows nothing about it",
          signup("abc123@privaterelay.appleid.com")[0], 200)
        s, out, _ = google("someone@yopmail.com", "g-yop")
        t("HTTP: Google with a throwaway address: refused with the same sentence", (s, out.get("error")), (400, auth_api.KEEP_MSG))
        s, out, _ = signup("typo@no-such-domain-here.org")
        t("HTTP: a domain DNS says does not exist is refused before any code is sent", (s, count("typo@no-such-domain-here.org")), (400, 0))
        t("HTTP: a slow resolver never blocks a real person", signup("patient@slow-dns.org")[0], 200)
        t("HTTP: Gmail, Yahoo, Outlook, school and work addresses all pass",
          [signup(v)[0] for v in ("pat.doe@gmail.com", "pat@yahoo.com", "pat@outlook.com", "pdoe@temple.edu", "pat@acme-robotics.co.uk")], [200] * 5)

        # 4 again: at most SIGNUPS_PER_HOUR (40: a campus shares one address) sign-up tries an hour from one visitor address (the host's last
        # hop, serve.client_ip, as for the lock-out); tools/test-public-auth.py checks forged headers and the per-email cap
        n = auth_api.SIGNUPS_PER_HOUR
        burst = [req("POST", "/api/auth/signup", {"email": "limit%d@gmail.com" % i, "password": "limit pass 123", "agree": True}, xff="203.0.113.50")
                 for i in range(n + 1)]
        t("HTTP: %d sign-ups from one visitor address in an hour work, then a kind refusal" % n,
          ([b[0] for b in burst], burst[-1][1].get("error")), ([200] * n + [429], auth_api.SIGNUP_LIMIT_MSG))
        t("HTTP: ...another visitor is not affected", signup("limit.other@gmail.com")[0], 200)
        log.flush()
        crashes = open(log_path, encoding="utf-8", errors="replace").read().count("Traceback")
        t("HTTP: the server logged no crash during all of this", crashes, 0)

        bad = subprocess.run([sys.executable, os.path.join(HERE, "audit-accounts.py"), DATA], capture_output=True, text=True)
        t("audit-accounts.py on everything this test did over HTTP: no problems", (bad.returncode, "OK: every address is one account" in bad.stdout), (0, True))
    finally:
        doh.shutdown()
        for p in PROCS:
            try:
                p.terminate()
                p.wait(10)
            except Exception:
                pass
    print(sum(R), "/", len(R))
    return 0 if all(R) else 1


if __name__ == "__main__":
    sys.exit(main())
