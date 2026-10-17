"""End-to-end test of "Continue with Google" against tools/mock-google.py.
Start the mock (python tools/mock-google.py 8790) and a server with the mock configured (see mock-google.py), then:
  python tools/test-google.py [server_port]"""
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "8768"
B = "http://127.0.0.1:%s" % PORT
M = "http://127.0.0.1:%s" % os.environ.get("MOCK_GOOGLE_PORT", "8790")      # where tools/mock-google.py listens


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def client():
    jar = http.cookiejar.CookieJar()
    return jar, urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)


def get(op, url):
    try:
        r = op.open(url)
        return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def post(op, path, data):
    req = urllib.request.Request(B + path, data=json.dumps(data).encode(), headers={"Content-Type": "application/json", "Origin": B}, method="POST")
    try:
        r = op.open(req)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def me(op):
    return json.loads(get(op, B + "/api/auth/me")[2])["user"]


def sign_in(op, agree, who=None):
    """Walk start -> mock Google -> callback. Returns the final redirect target."""
    if who:
        get(urllib.request.build_opener(), M + "/mock/next?" + urllib.parse.urlencode(who))
    s, h, _ = get(op, B + "/api/auth/google/start" + ("?agree=1" if agree else ""))
    assert s == 302, s
    s, h2, _ = get(op, h["Location"])                     # "Google" approves and redirects back to us
    assert s == 302, s
    s, h3, _ = get(op, h2["Location"])                    # our callback
    return h3.get("Location", "")


R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


jar, a = client()
t("providers lists google", json.loads(get(a, B + "/api/auth/providers")[2])["google"], True)
t("new account without agreeing is refused", sign_in(a, False, {"email": "new1@example.com", "sub": "501", "verified": "1"}), "/?auth_error=agree")
t("...and nobody is signed in", me(a), None)
t("new account with agreeing signs in", sign_in(a, True, {"email": "new1@example.com", "sub": "501", "verified": "1"}), "/?signed_in=google")
u = me(a)
t("signed in as the Google email", (u or {}).get("email"), "new1@example.com")
t("account has no password", (u or {}).get("hasPassword"), False)
post(a, "/api/auth/logout", {})
t("logged out", me(a), None)
t("same Google login signs in again (no agree needed)", sign_in(a, False, {"email": "new1@example.com", "sub": "501", "verified": "1"}), "/?signed_in=google")
t("password login for a Google-only account fails", post(client()[1], "/api/auth/login", {"email": "new1@example.com", "password": "anything goes 1"})[0], 401)
t("email/password signup for that email says to log in", post(client()[1], "/api/auth/signup", {"email": "new1@example.com", "password": "correct horse 99", "agree": True})[0], 409)

# an existing password account: Google with the same Gmail address links to it (Google is the authority on Gmail addresses)
jar2, b = client()
post(b, "/api/auth/signup", {"email": "pw1@gmail.com", "password": "correct horse 99", "agree": True})
post(b, "/api/auth/logout", {})
t("Google with an existing account's Gmail address links and signs in (and the page is told the unconfirmed password went)",
  sign_in(b, False, {"email": "pw1@gmail.com", "sub": "502", "verified": "1"}), "/?signed_in=google&password_removed=1")
t("...into the same account; its password, never confirmed by email, is removed (whoever set it had not proven the address)", (me(b) or {}).get("hasPassword"), False)
post(b, "/api/auth/logout", {})
# a "verified" address on any other domain is not trusted to take over an existing account
post(b, "/api/auth/signup", {"email": "pw2@example.com", "password": "correct horse 99", "agree": True})
post(b, "/api/auth/logout", {})
t("Google with an existing account's non-Gmail address is refused, not linked", sign_in(b, True, {"email": "pw2@example.com", "sub": "505", "verified": "1"}), "/?auth_error=email_in_use")
t("...and nobody is signed in", me(b), None)

# attacks and failures
jar3, c = client()
t("unverified Google email is refused", sign_in(c, True, {"email": "u@example.com", "sub": "503", "verified": "0"}), "/?auth_error=unverified")
s, h, _ = get(c, B + "/api/auth/google/start?agree=1")
g, h2, _ = get(c, h["Location"])
code_url = h2["Location"]
forged = code_url.replace("state=", "state=x")
t("forged state is refused", get(c, forged)[1].get("Location"), "/?auth_error=expired")
get(urllib.request.build_opener(), M + "/mock/next?email=ok1%40example.com&sub=601&verified=1")
s, h, _ = get(c, B + "/api/auth/google/start?agree=1")
g, h2, _ = get(c, h["Location"])
t("first use of a code works", get(c, h2["Location"])[1].get("Location"), "/?signed_in=google")
t("replaying the same callback is refused", get(c, h2["Location"])[1].get("Location"), "/?auth_error=expired")
other_jar, d = client()
s, h, _ = get(c, B + "/api/auth/google/start?agree=1")
g, h2, _ = get(c, h["Location"])
t("callback from a different browser (no state cookie) is refused", get(d, h2["Location"])[1].get("Location"), "/?auth_error=expired")
s, h, _ = get(c, B + "/api/auth/google/start?agree=1")
deny = h["Location"] + "&deny=1"
g, h2, _ = get(c, deny)
t("cancelling on Google's page is handled", get(c, h2["Location"])[1].get("Location"), "/?auth_error=cancelled")
t("callback with no parameters is refused", get(client()[1], B + "/api/auth/google/callback")[1].get("Location"), "/?auth_error=expired")
s, h, _ = get(c, B + "/api/auth/google/start?agree=1")
g, h2, _ = get(c, h["Location"] + "&deny=1&err=admin_policy_enforced")
t("Google sending back a setup error (not Cancel) says sign-in did not work, not 'cancelled'", get(c, h2["Location"])[1].get("Location"), "/?auth_error=failed")

# what UAply asks Google for (Google's own best practice for a sign-in-only web app)
s, h, _ = get(client()[1], B + "/api/auth/google/start")
q = urllib.parse.parse_qs(urllib.parse.urlparse(h["Location"]).query)
t("the request to Google uses PKCE with S256, a state and a nonce", (q.get("code_challenge_method"), len(q.get("code_challenge", [""])[0]), bool(q.get("state")), bool(q.get("nonce"))), (["S256"], 43, True, True))
t("...asks only for openid and email, with the account chooser and no long-lived access", (q.get("scope"), q.get("prompt"), q.get("access_type"), q.get("response_type")),
  (["openid email"], ["select_account"], ["online"], ["code"]))
t("...and names this very address as the way back (Google compares it letter for letter)", q.get("redirect_uri"), [B + "/api/auth/google/callback"])
t("the state cookie is HttpOnly, SameSite=Lax, limited to the Google paths and to 10 minutes",
  all(x in h.get("Set-Cookie", "") for x in ("HttpOnly", "SameSite=Lax", "Path=/api/auth/google", "Max-Age=600")), True)
jar5, f = client()
t("a wrong client secret on the server (Google answers invalid_client) ends in a clear failure, nobody signed in",
  (sign_in(f, True, {"email": "badsecret@example.com", "sub": "701", "verified": "1", "token_error": "invalid_client"}), me(f)), ("/?auth_error=failed", None))
t("...and the next try, once the secret is right, works", sign_in(f, True, {"email": "badsecret@example.com", "sub": "701", "verified": "1"}), "/?signed_in=google")

# deleting a Google-only account
jar4, e = client()
sign_in(e, True, {"email": "del1@example.com", "sub": "504", "verified": "1"})
t("delete without typing DELETE is refused", post(e, "/api/auth/delete", {})[0], 400)
t("delete with a wrong confirmation is refused", post(e, "/api/auth/delete", {"confirm": "yes"})[0], 400)
t("delete with DELETE works", post(e, "/api/auth/delete", {"confirm": "DELETE"})[0], 200)
t("...and the session is gone", me(e), None)
t("signing in again makes a new account only with agreeing", sign_in(e, False, {"email": "del1@example.com", "sub": "504", "verified": "1"}), "/?auth_error=agree")

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
