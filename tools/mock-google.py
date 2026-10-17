"""A stand-in for Google's sign-in, for testing UAply's "Continue with Google" without a Google account. Nothing here talks to Google.

  python tools/mock-google.py [port]        (default 8790)

Full-page flow ("Continue with Google" whenever the server has the client secret):
  GET  /mock/next?email=a@b.com&sub=123&verified=1   choose who "signs in" next (&token_error=invalid_client: the next code swap fails that way)
  GET  /auth?...                                      like accounts.google.com: checks the request (S256, openid, select_account, online),
                                                      immediately "approves" and redirects back (&deny=1&err=WORD: comes back with error=WORD)
  POST /token                                         like oauth2.googleapis.com/token: checks code, secret and PKCE verifier
  GET  /mock/stats                                    how many times the key list was fetched

Google's button flow (the page gets a signed token and posts it to UAply):
  GET  /certs                                         like googleapis.com/oauth2/v3/certs: the public key list
  GET  /mock/idtoken?email=&sub=&verified=1           a correctly signed ID token {"credential": "..."}; add &bad=aud|iss|expired|tamper|none|hs256|kid|future|longlife
                                                      (or &bad=skew: expired 20 seconds ago, which must still be accepted), and &hd=example.com for a Workspace account
                                                      to get a token that must be refused

Point UAply at it with this in uaply-config.json:
  "google": {"client_id": "test.apps.googleusercontent.com", "client_secret": "test-secret",
             "auth_url": "http://127.0.0.1:8790/auth", "token_url": "http://127.0.0.1:8790/token", "certs_url": "http://127.0.0.1:8790/certs"}
"""
import base64
import hashlib
import hmac
import http.server
import json
import random
import secrets
import sys
import time
import urllib.parse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
SECRET = "test-secret"
CLIENT = "test.apps.googleusercontent.com"
NEXT = {"email": "google.user@example.com", "sub": "1001", "verified": True}
CODES = {}
STATS = {"certs": 0, "token_error": ""}                 # how often the key list was fetched; an error the next code swap answers with
PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def b64(d):
    return base64.urlsafe_b64encode(d).rstrip(b"=").decode()


def _is_prime(n):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(24):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits):
    while True:
        c = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _is_prime(c):
            return c


def _make_key():
    e = 65537
    while True:
        p, q = _prime(512), _prime(512)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e:
            return p * q, e, pow(e, -1, phi)


N, E, D = _make_key()


def sign(signing_input):
    k = (N.bit_length() + 7) // 8
    digest = hashlib.sha256(signing_input).digest()
    block = b"\x00\x01" + b"\xff" * (k - len(PREFIX) - len(digest) - 3) + b"\x00" + PREFIX + digest
    return pow(int.from_bytes(block, "big"), D, N).to_bytes(k, "big")


def id_token(email, sub, verified=True, bad="", hd=""):
    now = int(time.time())
    claims = {"iss": "https://accounts.google.com", "aud": CLIENT, "sub": sub, "email": email, "email_verified": verified,
              "name": "Test User", "iat": now, "exp": now + 3600}
    if hd:
        claims["hd"] = hd                                  # a Google Workspace account: Google is the authority on this address
    header = {"alg": "RS256", "kid": "mock-key-1", "typ": "JWT"}
    if bad == "aud":
        claims["aud"] = "someone-elses-app.apps.googleusercontent.com"
    elif bad == "iss":
        claims["iss"] = "https://evil.example"
    elif bad == "expired":
        claims["exp"] = now - 600                          # well past the minute of clock difference UAply forgives
    elif bad == "skew":
        claims["exp"] = now - 20                           # just expired: within the forgiven clock difference, so accepted
    elif bad == "longlife":
        claims["exp"] = now + 3 * 86400                    # Google's tokens last an hour; one claiming three days is refused
    elif bad == "future":
        claims["iat"] = now + 7200
        claims["exp"] = now + 10800
    elif bad == "kid":
        header["kid"] = "no-such-key"
    elif bad == "none":
        header["alg"] = "none"
    elif bad == "hs256":
        header["alg"] = "HS256"
    h, c = b64(json.dumps(header).encode()), b64(json.dumps(claims).encode())
    if bad == "none":
        return h + "." + c + "."
    if bad == "hs256":                                   # signed with a shared secret, the way an attacker would try
        return h + "." + c + "." + b64(hmac.new(b"anything", (h + "." + c).encode(), hashlib.sha256).digest())
    token = h + "." + c + "." + b64(sign((h + "." + c).encode()))
    if bad == "tamper":                                  # change the email after signing
        forged = dict(claims, email="attacker@example.com")
        token = h + "." + b64(json.dumps(forged).encode()) + "." + token.split(".")[2]
    return token


class H(http.server.BaseHTTPRequestHandler):
    def _json(self, code, obj, extra=()):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path == "/mock/stats":
            return self._json(200, STATS)
        if u.path == "/mock/next":
            STATS["token_error"] = q.get("token_error", "")
            NEXT.update({"email": q.get("email", NEXT["email"]), "sub": q.get("sub", NEXT["sub"]), "verified": q.get("verified", "1") == "1"})
            return self._json(200, NEXT)
        if u.path == "/certs":
            STATS["certs"] += 1
            key = {"kty": "RSA", "kid": "mock-key-1", "use": "sig", "alg": "RS256", "n": b64(N.to_bytes((N.bit_length() + 7) // 8, "big")), "e": b64(E.to_bytes(3, "big"))}
            return self._json(200, {"keys": [key]}, [("Cache-Control", "public, max-age=3600")])
        if u.path == "/mock/idtoken":
            return self._json(200, {"credential": id_token(q.get("email", NEXT["email"]), q.get("sub", NEXT["sub"]), q.get("verified", "1") == "1", q.get("bad", ""), q.get("hd", ""))})
        if u.path == "/auth":
            if q.get("client_id") != CLIENT or q.get("code_challenge_method") != "S256" or not q.get("redirect_uri"):
                return self._json(400, {"error": "bad request"})
            if q.get("deny"):
                return self._redirect(q["redirect_uri"] + "?error=" + urllib.parse.quote(q.get("err", "access_denied")) + "&state=" + q.get("state", ""))
            if q.get("access_type") != "online" or q.get("prompt") != "select_account" or "openid" not in q.get("scope", "").split():
                return self._json(400, {"error": "UAply should ask for openid, prompt=select_account and access_type=online"})
            code = secrets.token_urlsafe(16)
            CODES[code] = {"challenge": q["code_challenge"], "nonce": q.get("nonce"), "redirect": q["redirect_uri"], "who": dict(NEXT)}
            return self._redirect(q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": code, "state": q.get("state", "")}))
        self._json(404, {"error": "not found"})

    def _redirect(self, where):
        self.send_response(302)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        f = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode()).items()}
        rec = CODES.pop(f.get("code", ""), None)          # a code works once
        if STATS["token_error"]:                          # like Google when the client secret is wrong (invalid_client) or the code was reused
            err, STATS["token_error"] = STATS["token_error"], ""
            return self._json(401 if err == "invalid_client" else 400, {"error": err})
        if (self.path != "/token" or not rec or f.get("client_secret") != SECRET or f.get("client_id") != CLIENT
                or f.get("redirect_uri") != rec["redirect"] or f.get("grant_type") != "authorization_code"
                or b64(hashlib.sha256((f.get("code_verifier") or "").encode()).digest()) != rec["challenge"]):
            return self._json(400, {"error": "invalid_grant"})
        w = rec["who"]
        claims = {"iss": "https://accounts.google.com", "aud": CLIENT, "sub": w["sub"], "email": w["email"], "email_verified": w["verified"],
                  "nonce": rec["nonce"], "iat": int(time.time()), "exp": int(time.time()) + 3600}
        tok = b64(b'{"alg":"none"}') + "." + b64(json.dumps(claims).encode()) + "."
        self._json(200, {"access_token": "x", "id_token": tok, "token_type": "Bearer", "expires_in": 3600})

    def log_message(self, *a):
        pass


http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
