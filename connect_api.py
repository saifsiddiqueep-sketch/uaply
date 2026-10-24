"""The employer connect page (swipe phase B, October 23, 2026): from the outreach email's link to "connected, the next application arrives in
your system" in under two minutes.

The owner makes one link per employer (POST /api/setup/connect-invite {kind, board}, owner only): /employers/connect?k=<system>&b=<board>
&e=<expiry>&s=<signature>, signed with this copy's own link key (uaply_api._link_key) and good for 30 days. The page names the system, says
where the key is made and with which rights only (docs/employers/connect-kit.md), and has one box for the key, a tick for the employer's
agreement, Test (reads their open postings with the key: nothing is sent or saved) and Connect (tests again, then keeps the key). A kept key
lives in this copy's records folder (ats-connections.json, beside the other records; never in a page, a log or an answer), and
jobs_api.ats_connections reads it with the others: that board's postings then say Apply instantly and a swipe right goes into their system.
Nothing here works without a valid, unexpired link: a stranger cannot connect a board, and a wrong key never passes the test."""
import hashlib
import hmac
import html
import json
import os
import re
import threading
import time
import urllib.parse

import ats_api
import uaply_api

DAYS = 30
_lock = threading.Lock()
STEPS = {
    "greenhouse": ("Configure, Dev Center, API Credential Management: new credential, type Job Board API", "Job Board API (it submits applications to your published jobs)"),
    "lever": ("Settings, Integrations and API, API Credentials: Generate new key under Postings API (a Super Admin)", "Postings API"),
    "ashby": ("Admin, Integrations, API Keys: create a key", "Candidates write and Jobs read only"),
    "smartrecruiters": ("Settings, Administration, Apps & Integrations, Credentials: New Credential, API Key (an Administrator)",
                        "An API key; UAply uses only its Application API calls"),
    "workable": ("Profile icon, Settings, Integrations, Apps, API Access Tokens: Generate API token (an Admin)", "r_jobs and w_candidates only"),
}


def path():
    return os.path.join(uaply_api.DATA, "ats-connections.json")


def _sig(kind, board, exp):
    msg = ("uaply-connect:%s:%s:%d" % (kind, board.lower(), int(exp))).encode("utf-8")
    return hmac.new(uaply_api._link_key(), msg, hashlib.sha256).hexdigest()[:32]


def invite(site, kind, board, now=None):
    """(status, body) for POST /api/setup/connect-invite: the link the outreach email carries for this employer."""
    if kind not in ats_api.KINDS or not isinstance(board, str) or not ats_api.TOKEN_RE.match(board):
        return 400, {"ok": False, "message": "Choose Greenhouse, Lever, Ashby, SmartRecruiters or Workable and give the board name from the employer's job-board address."}
    exp = int((now or time.time()) + DAYS * 86400)
    q = urllib.parse.urlencode({"k": kind, "b": board, "e": exp, "s": _sig(kind, board, exp)})
    return 200, {"ok": True, "url": "%s/employers/connect?%s" % ((site or "").rstrip("/"), q), "expires": exp}


def _valid(k, b, e, s, now=None):
    """(kind, board) when the link is this copy's own and not expired, else None."""
    try:
        exp = int(e)
    except (TypeError, ValueError):
        return None
    if k not in ats_api.KINDS or not isinstance(b, str) or not ats_api.TOKEN_RE.match(b) or not isinstance(s, str) or not re.fullmatch(r"[0-9a-f]{32}", s):
        return None
    if exp < (now or time.time()) or not hmac.compare_digest(s, _sig(k, b, exp)):
        return None
    return k, b


def _bad_link():
    return 403, {"ok": False, "message": "This link is not valid or has expired. Reply to the email it came in and we will send a new one."}


def test(p):
    """POST /api/employer/connect/test {k, b, e, s, key}: reads the employer's open postings with the key. Nothing is sent or saved."""
    who = _valid(p.get("k"), p.get("b"), p.get("e"), p.get("s"))
    if not who:
        return _bad_link()
    key = str(p.get("key") or "").strip()
    if not ats_api.valid_connection(who[0], who[1], key):
        return 400, {"ok": False, "message": "Paste the key exactly as %s shows it." % ats_api.NAMES[who[0]]}
    return 200, ats_api.test_connection(who[0], who[1], key)


def _load():
    try:
        with open(path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data):
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path())


def _used(s):
    return isinstance(s, str) and s in (_load().get("used_links") or [])


USED = (409, {"ok": False, "used": True, "message": "This link was already used. Ask us for a new link: reply to the email it came in."})


def drop_pending(kind, board, key):
    """Their system refused a pending key (401 or 403 on its first send): it was mistyped, so it is removed and that board's postings are
    hand-offs again. A connected key is never dropped here. True when removed. Never raises."""
    try:
        with _lock:
            data = _load()
            rows = data.get("ats_connections") or []
            keep = [c for c in rows if not (isinstance(c, dict) and (c.get("kind"), c.get("board")) == (kind, board) and c.get("api_key") == key and c.get("status") == "pending")]
            if len(keep) == len(rows):
                return False
            data["ats_connections"] = keep
            _write(data)
            return True
    except Exception:
        return False


def promote(kind, board, key):
    """A real application reached their system with this key: a pending connection is now connected. Never raises."""
    try:
        with _lock:
            data = _load()
            hit = False
            for c in data.get("ats_connections") or []:
                if isinstance(c, dict) and (c.get("kind"), c.get("board")) == (kind, board) and c.get("api_key") == key and c.get("status") == "pending":
                    c["status"], c["checked_at"], hit = "connected", int(time.time()), True
            if hit:
                _write(data)
    except Exception:
        pass


def save(p):
    """POST /api/employer/connect/save {k, b, e, s, key, agree}: tests the key, then keeps it. One connect per link; a key that could not be
    checked (Greenhouse and Lever keys only work on a send; SmartRecruiters with no open posting) is kept as "pending" until the first real
    application gets through; a new key never replaces one that already works. (status, body)"""
    who = _valid(p.get("k"), p.get("b"), p.get("e"), p.get("s"))
    if not who:
        return _bad_link()
    if _used(p.get("s")):
        return USED
    kind, board = who
    key = str(p.get("key") or "").strip()
    if p.get("agree") is not True:
        return 400, {"ok": False, "message": "Tick the box to agree that UAply sends you the applications people choose to send."}
    if not ats_api.valid_connection(kind, board, key):
        return 400, {"ok": False, "message": "Paste the key exactly as %s shows it." % ats_api.NAMES[kind]}
    tr = ats_api.test_connection(kind, board, key)
    if not tr.get("ok"):
        return 400, {"ok": False, "message": tr.get("message") or "The key did not work."}
    checked = tr.get("keyChecked") is True
    name = ats_api.NAMES[kind]
    with _lock:
        data = _load()
        if p.get("s") in (data.get("used_links") or []):
            return USED
        rows = [c for c in (data.get("ats_connections") or []) if isinstance(c, dict)]
        old = [c for c in rows if (c.get("kind"), c.get("board")) == (kind, board)]
        if any(c.get("status", "connected") != "pending" and c.get("api_key") != key for c in old):
            return 409, {"ok": False, "message": "Your %s is already connected to UAply with a key that works, so it was kept. To change keys, "
                                                 "revoke the old one in %s and ask us for a new link." % (board, name)}
        keep = [c for c in rows if (c.get("kind"), c.get("board")) != (kind, board)]
        keep.append({"kind": kind, "board": board, "api_key": key, "at": int(time.time()), "agreed": True, "status": "connected" if checked else "pending"})
        data["ats_connections"] = keep
        data["used_links"] = (data.get("used_links") or []) + [p.get("s")]
        _write(data)
    if not checked:
        return 200, {"ok": True, "pending": True, "message": "Saved, pending. %s keys can only be checked by a real application, so the connection shows "
                                                             "as pending until the first one from UAply arrives in %s. To stop, revoke the key in %s." % (name, name, name)}
    return 200, {"ok": True, "message": "Connected. The next application from UAply to your %s jobs arrives in %s as a new candidate on the right job. "
                                        "To stop, revoke the key in %s." % (board, ats_api.NAMES[kind], ats_api.NAMES[kind])}


def page(k, b, e, s):
    """GET /employers/connect: the employer's page."""
    who = _valid(k, b, e, s)
    esc = html.escape
    if who and _used(s):
        body = "<h1>This link was already used</h1><p>Each link connects once. Ask us for a new link: reply to the email it came in.</p>"
        script = ""
    elif not who:
        body = "<h1>This link is not valid</h1><p>It may have expired. Reply to the email it came in and we will send a new one.</p>"
        script = ""
    else:
        kind, board = who
        name, (where, rights) = ats_api.NAMES[kind], STEPS[kind]
        body = ('<h1>Connect %s to UAply</h1>'
                '<p>When someone in UAply chooses one of your <b>%s</b> jobs, their application arrives in %s as a new candidate on the right job: '
                'their details, their resume as a file and the answers to your own questions. UAply never sends voluntary self-identification answers, '
                'and uses the key only to read your application form and submit applications people chose to send you.</p>'
                '<ol><li>In %s: %s. Give it these rights: %s.</li><li>Paste the key here, press Test, then Connect.</li></ol>'
                '<label for="key">%s key</label><input id="key" type="password" autocomplete="off" spellcheck="false">'
                '<label class="chk"><input id="agree" type="checkbox"> I may connect our %s, and I agree that UAply sends us the applications people choose to send.</label>'
                '<div class="acts"><button id="test" type="button" class="ghost">Test</button><button id="go" type="button">Connect</button></div>'
                '<p id="msg" role="status"></p>' % (esc(name), esc(board), esc(name), esc(name), esc(where), esc(rights), esc(name), esc(name)))
        args = json.dumps({"k": kind, "b": board, "e": e, "s": s})
        script = ("<script>(function(){var A=%s,m=document.getElementById('msg');function call(p,x){var b=Object.assign({},A,x);"
                  "return fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j}})})"
                  ".catch(function(){return {ok:false,j:{message:'Could not reach UAply. Try again.'}}})}"
                  "function key(){return document.getElementById('key').value.trim()}"
                  "document.getElementById('test').onclick=function(){m.textContent='Testing...';call('/api/employer/connect/test',{key:key()}).then(function(r){m.textContent=(r.j&&r.j.message)||'Done.'})};"
                  "document.getElementById('go').onclick=function(){var g=this;g.disabled=true;m.textContent='Connecting...';"
                  "call('/api/employer/connect/save',{key:key(),agree:document.getElementById('agree').checked}).then(function(r){m.textContent=(r.j&&r.j.message)||'Done.';"
                  "if(r.ok){document.body.classList.add('done')}else g.disabled=false})}})();</script>" % args)
    return uaply_api.ui_rules.with_focus("""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Connect to UAply</title><style>
:root{--bg:#FDF0F2;--surface:#FFFFFF;--ink:#2A1218;--muted:#7B5560;--line:#F3DADF;--accent:#C92A55;--on-accent:#FFFFFF}
@media (prefers-color-scheme: dark){:root{--bg:#190B10;--surface:#26131A;--ink:#FBE9EE;--muted:#C79BA6;--line:#40222B;--accent:#FF7A98;--on-accent:#190B10}}
body{margin:0;padding:16px;background:var(--bg);color:var(--ink);font:16px/1.5 'DM Sans','Segoe UI',system-ui,sans-serif}
main{max-width:600px;margin:6vh auto;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:20px;display:flex;flex-direction:column;gap:10px}
h1{margin:0;font-size:22px}p,ol{margin:0}label{font-weight:700}input[type=password]{font:inherit;padding:12px;border:1px solid var(--line);border-radius:12px;background:var(--bg);color:var(--ink)}
.chk{font-weight:400;display:flex;gap:10px;align-items:flex-start}.chk input{min-width:22px;min-height:22px;margin-top:2px}
.acts{display:flex;gap:8px;flex-wrap:wrap}button{font:inherit;font-weight:700;padding:12px 16px;border-radius:12px;border:0;background:var(--accent);color:var(--on-accent);min-height:44px}
button.ghost{background:transparent;color:var(--ink);border:1px solid var(--line)}#msg{color:var(--muted)}</style></head><body><main>""" + body + "</main>" + script + "</body></html>")
