"""Sends every API endpoint odd, wrong-typed and hostile input and reports anything that is not a polite refusal: a 5xx answer (an unhandled
crash), a hang, a dropped connection, or raw exception text in the reply. Use a throwaway server, never your real one.
  HOST=0.0.0.0 UAPLY_DATA_DIR=<empty folder> python serve.py 18795 dev --api     (hosted mode, so each request can claim its own address)
  python tools/fuzz-api.py 18795"""
import http.client
import itertools
import json
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18795
HOST = "127.0.0.1:%d" % PORT
R = []
PROBLEMS = []
counter = [0]

POSTS = ["/api/apply", "/api/decision", "/api/auth/signup", "/api/auth/login", "/api/auth/logout", "/api/auth/delete", "/api/auth/forgot",
         "/api/auth/reset", "/api/auth/change-password", "/api/auth/google/token", "/api/auth/verify", "/api/auth/resend", "/api/chat", "/api/feedback",
         "/api/profile/resume"]
GETS = ["/", "/api/jobs", "/api/apply/config", "/api/outbox", "/outbox", "/api/auth/me", "/api/auth/providers", "/api/auth/google/start",
        "/api/auth/google/callback?code=x&state=y", "/api/auth/google/callback?error=access_denied", "/api/chat/config", "/feedback", "/setup", "/healthz",
        "/?reset=%00", "/?reset=" + "a" * 5000, "/legal/", "/legal/terms.html", "/help/articles.json", "/nope", "/%", "/%zz", "/api/jobs?x=" + "b" * 9000]
WEIRD = [None, True, False, 0, -1, 2 ** 70, 1.5, "", " ", "x" * 70000, "<script>alert(1)</script>", "'; DROP TABLE users;--", "\u0000", "😀" * 50,
         [], [1, 2, 3], [[]], {}, {"a": {"b": {"c": [1, {"d": None}]}}}]
KEYS = ["email", "password", "consent", "job", "profile", "code", "token", "messages", "text", "id", "rating"]     # the single-field phase; the corrupt-a-valid-request phase below covers every field
BAD_TEXT = ("Traceback", "File \"", "Errno", "sqlite3", "KeyError", "TypeError", "AttributeError", "ValueError", "IndexError", "object has no attribute")


def t(name, ok, extra=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ("  " + extra if extra else ""))


def call(method, path, body=None, raw=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    counter[0] += 1
    n = counter[0]
    h = {"Origin": "http://" + HOST, "X-Forwarded-For": "10.%d.%d.%d" % (n >> 16 & 255, n >> 8 & 255, n & 255)}      # a new client address each time, so rate limits do not hide what comes after them
    h.update(headers or {})
    data = raw
    if body is not None:
        data = json.dumps(body)
    if data is not None:
        h["Content-Type"] = "application/json"
    try:
        c.request(method, path, body=data.encode("utf-8", "surrogatepass") if isinstance(data, str) else data, headers=h)
        r = c.getresponse()
        return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        if data is not None and len(data) > 40000 and type(e).__name__ in ("ConnectionAbortedError", "ConnectionResetError", "BrokenPipeError"):
            return 413, ""            # the server refused an oversized body early and closed the line while we were still sending: that is the correct refusal
        return "ERR %s" % type(e).__name__, ""
    finally:
        c.close()


def judge(label, status, body):
    if not isinstance(status, int) or status >= 500:
        PROBLEMS.append("%s -> %s %s" % (label, status, body[:90].replace("\n", " ")))
    elif any(b in body for b in BAD_TEXT):
        PROBLEMS.append("%s -> %s leaks text: %s" % (label, status, next(b for b in BAD_TEXT if b in body)))


sent = 0
# 1. every GET, including broken addresses
for p in GETS:
    s, b = call("GET", p)
    judge("GET " + p[:40], s, b)
    sent += 1
# 2. every POST with bodies that are not JSON objects at all
for p in POSTS:
    for raw in ["", "null", "[]", "[1,2]", "123", '"text"', "{", "{'a':1}", '{"a":', "ÿþ", "{}" + " " * 10]:
        s, b = call("POST", p, raw=raw)
        judge("POST %s raw %r" % (p, raw[:12]), s, b)
        sent += 1
# 3. every POST with each known field set to each odd value
for p in POSTS:
    for k, v in itertools.product(KEYS, WEIRD):
        s, b = call("POST", p, body={k: v})
        judge("POST %s {%s: %s}" % (p, k, json.dumps(v)[:24]), s, b)
        sent += 1
# 4. a few full-shaped requests with the wrong inner types
SHAPES = [{"consent": True, "job": "x", "profile": 5}, {"consent": True, "job": {"id": "a", "co": 1, "role": [], "url": 3}, "profile": {"name": [], "email": {}, "skills": "x"}},
          {"consent": True, "job": {"id": 1, "co": "A", "role": "B", "url": "https://x.example"}, "profile": {"name": "N", "email": "n@example.com", "skills": {"a": 1}, "ext": "zzz"}},
          {"consent": True, "job": {"id": 1}, "profile": {"ext": {"resume": {"name": 1, "type": 2, "data": 3}}}},
          {"id": 7, "decision": {"x": 1}}, {"id": "7", "decision": "applied", "match": "high"}]
for sh in SHAPES:
    for p in ("/api/apply", "/api/decision"):
        s, b = call("POST", p, body=sh)
        judge("POST %s shape %s" % (p, json.dumps(sh)[:40]), s, b)
        sent += 1
# 4b. start from a valid request for each endpoint, signed in as a real account, and corrupt one field at a time (or remove it)
import copy


def session_cookie():
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    c.request("POST", "/api/auth/signup", body=json.dumps({"email": "fuzz@example.com", "password": "correct horse 99", "agree": True}),
              headers={"Origin": "http://" + HOST, "Content-Type": "application/json", "X-Forwarded-For": "10.250.0.1"})
    r = c.getresponse()
    r.read()
    cookie = (r.getheader("Set-Cookie") or "").split(";")[0]
    c.close()
    return cookie


GONE = object()


def paths(obj, prefix=()):
    yield prefix
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from paths(v, prefix + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from paths(v, prefix + (i,))


def mutated(base, path, val):
    out = copy.deepcopy(base)
    node = out
    for step in path[:-1]:
        node = node[step]
    if val is GONE:
        if isinstance(node, dict):
            node.pop(path[-1], None)
        else:
            node[path[-1]] = None
    else:
        node[path[-1]] = copy.deepcopy(val)
    return out


APPLY = {"consent": True, "note": "hello", "resume": None,
         "job": {"id": 1, "co": "Acme", "role": "Intern", "url": "https://acme.example/j", "loc": "Austin, TX", "contact": "", "source": "feed", "type": "internship",
                 "mode": "remote", "sal": [1, 2], "blurb": "b"},
         "profile": {"name": "Pat Doe", "email": "fuzz@example.com", "title": "Dev", "loc": "Austin", "edu": "Bachelor", "years": 3, "skills": ["a", "b"],
                     "ext": {"phone": "+1 555", "linkedin": "https://www.linkedin.com/in/x", "portfolio": "https://x.example", "summary": "s", "resume": "https://x.example/cv"}}}
BASES = {"/api/apply": APPLY,
         "/api/decision": {"dir": "apply", "jobId": 1, "session": "s", "co": "Acme", "role": "Intern", "pct": 80},
         "/api/auth/signup": {"email": "fz1@example.com", "password": "correct horse 99", "agree": True},
         "/api/auth/login": {"email": "fuzz@example.com", "password": "correct horse 99"},
         "/api/auth/forgot": {"email": "fuzz@example.com"},
         "/api/auth/reset": {"token": "abc", "password": "another pass 123"},
         "/api/auth/change-password": {"current": "correct horse 99", "password": "another pass 123", "new": "another pass 123"},
         "/api/auth/verify": {"code": "123456"},
         "/api/auth/google/token": {"credential": "a.b.c", "agree": True},
         "/api/chat": {"messages": [{"role": "user", "text": "How do I apply?"}], "page": "services", "articles": ["apply"]},
         "/api/feedback": {"rating": 5, "text": "great", "email": "a@b.co", "page": "x", "topic": "t", "source": "chat", "helpful": True, "followup": "y", "articles": ["a"]}}
cookie = session_cookie()
mut = 0
for p, base in BASES.items():
    for path in paths(base):
        if not path:
            continue
        for val in WEIRD + [GONE]:
            body = mutated(base, path, val)
            s, b = call("POST", p, body=body, headers={"Cookie": cookie})
            judge("POST %s with %s = %s" % (p, ".".join(str(x) for x in path), "<removed>" if val is GONE else json.dumps(val)[:20]), s, b)
            sent += 1
            mut += 1
print("   (%d corrupted-but-realistic requests among them)" % mut)

# 5. odd headers and methods
for hdr in ({"Cookie": "a" * 9000}, {"Cookie": "uaply_dev_session=" + "z" * 300}, {"Authorization": "Basic !!!"}, {"X-Forwarded-For": "999.1.1.1, <b>"}, {"Content-Length": "abc"}):
    s, b = call("POST", "/api/auth/login", body={"email": "a@b.co", "password": "x"}, headers=hdr)
    judge("headers %s" % list(hdr)[0], s, b)
    sent += 1
for m in ("PUT", "DELETE", "PATCH", "OPTIONS", "TRACE"):
    s, b = call(m, "/api/auth/login", body={})
    judge("method " + m, s if s != 501 and s != 405 and s != 404 else 400, b)
    sent += 1

t("%d odd requests sent" % sent, sent > 1000)
t("none caused a 5xx answer, a hang, a dropped connection or raw exception text", not PROBLEMS, "(%d problems)" % len(PROBLEMS))
for line in PROBLEMS[:25]:
    print("   ! " + line)
s, _ = call("GET", "/healthz")
t("the server still answers afterwards", s == 200)
print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
