"""Every email UAply sends from its own mail account goes through send() here: one place that stamps the message, keeps to the daily
quota of the mail service, skips addresses that bounce, retries sensibly, holds mail it cannot send yet, and writes one clear log line
when something goes wrong.

Kinds of mail (the `kind` argument):
  code, reset        the 6-digit sign-up code and the password reset link: a person is waiting for them, so they always go first
  application        an application emailed to an employer who agreed to receive them (the record is kept whatever happens)
  receipt, owner_copy, support, ack
                     the applicant's confirmation, the owner's copy, a help request to the team and its acknowledgement: these can wait,
                     so they are held (not dropped) when the quota is nearly used up or the mail service is down, and sent later

The daily quota. Brevo's free plan sends 300 emails a day. UAply counts what it sent per UTC day (in mail-count.json in the data folder):
  * from `mail_priority_at` (default 250) only codes, reset links and applications go; the rest is held until the next UTC day
  * at `mail_daily_quota` (default 300) nothing more is tried that day; codes and applications then fail with an honest message
  * if the mail service itself says the quota is used up (its count can differ from ours, for example after a deploy without a disk),
    the day is marked full at once and the same rules apply
Both numbers can be set in the config (UAPLY_CONFIG_JSON) when the plan changes.

Failures (classify()):
  login        the mail service refused the SMTP login (a wrong or revoked key): nothing is retried; held mail waits for the fix
  quota        the daily sending limit: held until the next UTC day (codes and applications fail)
  recipient    the mail service refused that address for good (5xx at RCPT): the address is added to the bounce list
  unreachable, temporary
               the connection dropped, timed out, or a 4xx answer: one more try after 2 seconds, then held mail is retried every 15 minutes
               (up to 8 times) and a code or an application fails
  refused, invalid, error
               anything else: not retried
Bounces and complaints that the mail service learns about after it accepted a message (Brevo's webhook, POST /api/email/events) put the
address on the bounce list (mail-suppressed.json in the data folder): no more codes, receipts or copies go to it.

The log line, one per problem, never the message or the full address:
  [uaply] email not sent: receipt to s***@example.com: quota (421 4.7.0 daily limit reached); held until 2026-10-18 00:00 UTC
"""
import email
import email.policy
import ipaddress
import json
import os
import re
import smtplib
import sys
import threading
import time
import uuid
from email.utils import formatdate, make_msgid, parseaddr

ROOT = os.path.dirname(os.path.abspath(__file__))
PRIORITY = ("code", "reset", "application")
DEFERRABLE = ("receipt", "owner_copy", "support", "ack", "digest")   # digest: the day's "finish your application" reminder
AUTOMATIC = ("code", "reset", "receipt", "owner_copy", "ack", "digest")       # sent by a machine: auto-responders must not answer them (RFC 3834)
RETRY_SECONDS = 2
HOLD_RETRY_SECONDS = 900
MAX_TRIES = 8
SUPPRESS_DAYS = {"hard_bounce": 365, "invalid_email": 365, "blocked": 365, "spam": 365, "unsubscribed": 365, "refused": 365, "soft_bounce": 7}
SOFT_BOUNCES = 5                 # this many soft bounces within 7 days count as a bounce
QUOTA_RE = re.compile(r"quota|daily limit|sending limit|limit (?:reached|exceeded)|too many (?:messages|emails|mails)|credits?\b|exceeded", re.I)
_BAD_HEADER = re.compile(r"[\x00-\x1f\x7f\x85  ]+")

clock = time.time                # tests move time forward by replacing this
_lock = threading.RLock()
_flush_lock = threading.Lock()
QUEUE_DIR = ""                   # the instance's own records folder (set by uaply_api.init): held mail belongs to one running copy
_count_mem = {}                  # used when the data folder cannot be written


def data_root():
    return os.environ.get("UAPLY_DATA_DIR") or os.path.join(ROOT, "data")


def init(folder):
    global QUEUE_DIR
    QUEUE_DIR = folder


def header(v, n=300):
    """A header value that cannot add a header: every control character, line break and Unicode line or paragraph separator becomes a
    space (the email library would otherwise refuse the whole message, so one odd character in a name would lose the email)."""
    return " ".join(_BAD_HEADER.sub(" ", str(v or "")).split())[:n]


def mask(addr):
    """'s***@example.com': enough for the owner to recognise a domain in the log, not the person."""
    a = str(addr or "")
    if "@" not in a:
        return "(no address)"
    local, dom = a.rsplit("@", 1)
    return (local[:1] or "?") + "***@" + dom


def _limits(cfg):
    try:
        quota = max(1, int(cfg.get("mail_daily_quota", 300)))
    except (TypeError, ValueError):
        quota = 300
    try:
        prio = int(cfg.get("mail_priority_at", 250))
    except (TypeError, ValueError):
        prio = 250
    return quota, max(0, min(prio, quota))


def day(ts=None):
    return time.strftime("%Y-%m-%d", time.gmtime(clock() if ts is None else ts))


def next_day(ts=None):
    t = clock() if ts is None else ts
    return (int(t) // 86400 + 1) * 86400


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, type(default)) else default
    except (OSError, ValueError):
        return default


def _write_json(path, value):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = "%s.%d.tmp" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f)
        os.replace(tmp, path)
        return True
    except OSError as e:
        sys.stderr.write("[uaply] could not save %s: %s\n" % (os.path.basename(path), type(e).__name__))
        return False


# ---------- the count per UTC day ----------
def _count_path():
    return os.path.join(data_root(), "mail-count.json")


def today():
    """(emails sent today, whether the mail service said the quota is used up today)."""
    with _lock:
        st = _read_json(_count_path(), {}) or _count_mem
        if st.get("day") != day():
            return 0, False
        return int(st.get("sent") or 0), bool(st.get("full"))


def _bump(full=False):
    with _lock:
        n, was_full = today()
        prev = _read_json(_count_path(), {}) or _count_mem
        st = {"day": day(), "sent": n + (0 if full else 1), "full": was_full or full,
              # when an email last went out (kept across days and restarts): the owner's self-check in /api/status
              "last_sent": time.time() if not full else float(prev.get("last_sent") or 0)}
        _count_mem.clear()
        _count_mem.update(st)
        _write_json(_count_path(), st)


def last_sent():
    """When an email last went out through the mail service (Unix seconds), or 0 when none has."""
    with _lock:
        st = _read_json(_count_path(), {}) or _count_mem
        try:
            return float(st.get("last_sent") or 0)
        except (TypeError, ValueError):
            return 0.0


def usage(cfg):
    """For the owner's pages and tests: today's count and the two limits."""
    n, full = today()
    quota, prio = _limits(cfg)
    return {"day": day(), "sent": n, "full": full, "quota": quota, "priorityAt": prio, "held": len(_queue())}


# ---------- the bounce list ----------
def _sup_path():
    return os.path.join(data_root(), "mail-suppressed.json")


def suppressed(addr):
    """Why mail to this address is not sent ('' when it may be sent)."""
    a = str(addr or "").strip().lower()
    if not a:
        return ""
    with _lock:
        s = _read_json(_sup_path(), {}).get("blocked", {}).get(a)
    if isinstance(s, dict) and (not s.get("until") or s["until"] > clock()):
        return str(s.get("why") or "bounced")
    return ""


def blocked_addresses():
    """Every address mail is not sent to right now, read once (the job list checks the postings that take applications by email)."""
    with _lock:
        d = _read_json(_sup_path(), {}).get("blocked", {})
    now = clock()
    return frozenset(a for a, s in d.items() if isinstance(s, dict) and (not s.get("until") or s["until"] > now))


def suppress(addr, why, days=None):
    a = str(addr or "").strip().lower()
    if not a or "@" not in a:
        return False
    with _lock:
        d = _read_json(_sup_path(), {})
        d.setdefault("blocked", {})[a] = {"why": why, "at": int(clock()), "until": int(clock() + 86400 * (days or SUPPRESS_DAYS.get(why, 365)))}
        _write_json(_sup_path(), d)
    return True


def unblock(addr):
    a = str(addr or "").strip().lower()
    with _lock:
        d = _read_json(_sup_path(), {})
        gone = d.get("blocked", {}).pop(a, None) is not None
        gone = d.get("soft", {}).pop(a, None) is not None or gone
        _write_json(_sup_path(), d)
    return gone


def record_event(event, addr):
    """One event from the mail service (Brevo's webhook names). Returns 'blocked', 'soft', 'cleared', 'unblocked' or 'ignored'."""
    a = str(addr or "").strip().lower()
    if event in ("hard_bounce", "invalid_email", "blocked", "spam", "unsubscribed"):
        suppress(a, event)
        return "blocked"
    if event == "uaply_unblock":
        unblock(a)
        return "unblocked"
    if event == "soft_bounce":
        with _lock:
            d = _read_json(_sup_path(), {})
            now = clock()
            soft = [t for t in d.setdefault("soft", {}).get(a, []) if now - t < 7 * 86400] + [int(now)]
            d["soft"][a] = soft[-SOFT_BOUNCES:]
            _write_json(_sup_path(), d)
        if len(soft) >= SOFT_BOUNCES:
            suppress(a, "soft_bounce")
            return "blocked"
        return "soft"
    if event == "delivered":
        with _lock:
            d = _read_json(_sup_path(), {})
            if d.get("soft", {}).pop(a, None) is not None:
                _write_json(_sup_path(), d)
                return "cleared"
    return "ignored"


# ---------- sending ----------
def stamp(msg, kind):
    """Date and Message-ID (spam filters mark mail without them; Python does not add them), and Auto-Submitted for automatic mail."""
    if "Date" not in msg:
        msg["Date"] = formatdate(clock(), usegmt=True)
    if "Message-ID" not in msg:
        dom = parseaddr(str(msg.get("From") or ""))[1].rpartition("@")[2] or "uaply.net"
        msg["Message-ID"] = make_msgid("uaply", domain=dom)
    if kind in AUTOMATIC and "Auto-Submitted" not in msg:
        msg["Auto-Submitted"] = "auto-generated"
    return msg


def test_run_blocks(host):
    """A test run (UAPLY_CONFIG_FILE=none) only ever talks to a mail server on this computer (tools/fake-smtp.py): SMTP does not go through
    the closed proxy that keeps the test suite offline, so a real host such as Brevo's is refused here instead of being sent to."""
    if os.environ.get("UAPLY_CONFIG_FILE") != "none":
        return False
    h = str(host or "").strip().strip("[]").lower()
    if h == "localhost":
        return False
    try:
        return not ipaddress.ip_address(h).is_loopback
    except ValueError:
        return True


def _smtp(cfg, msg):
    s = cfg["smtp"]
    if test_run_blocks(s.get("host")):
        raise ValueError("test run: the mail server is not on this computer, nothing sent")
    with smtplib.SMTP(s["host"], int(s.get("port", 587)), timeout=20) as srv:
        if s.get("starttls", True):
            srv.starttls()
        if s.get("user"):
            srv.login(s["user"], s.get("password", ""))
        srv.send_message(msg)


def _text(v):
    return (v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v or "")).replace("\r", " ").replace("\n", " ").strip()[:160]


def classify(e):
    """(kind of failure, 'code text' for the log)."""
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return "login", "%s %s" % (e.smtp_code, _text(e.smtp_error))
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        code, text = next(iter(e.recipients.values()), (0, b""))
        detail = "%s %s" % (code, _text(text))
        if QUOTA_RE.search(_text(text)):
            return "quota", detail
        return ("temporary" if 400 <= int(code or 0) < 500 else "recipient"), detail
    if isinstance(e, smtplib.SMTPResponseException):
        detail = "%s %s" % (e.smtp_code, _text(e.smtp_error))
        if QUOTA_RE.search(_text(e.smtp_error)):
            return "quota", detail
        return ("temporary" if 400 <= int(e.smtp_code or 0) < 500 else "refused"), detail
    if isinstance(e, (smtplib.SMTPServerDisconnected, OSError)):
        return "unreachable", type(e).__name__
    if isinstance(e, ValueError):
        return "invalid", _text(str(e))
    return "error", type(e).__name__


def _recipients(msg):
    return [a for _, a in email.utils.getaddresses([str(v) for v in (msg.get_all("To") or [])]) if a]


def _log(kind, to, why, detail, then):
    sys.stderr.write("[uaply] email not sent: %s to %s: %s%s; %s\n" % (kind, mask(to), why, (" (%s)" % detail) if detail else "", then))
    sys.stderr.flush()


def _when(ts):
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts))


def send(cfg, msg, kind, user=None, mail_row=None):
    """Send one message. Returns (status, why):
         ('sent', '')
         ('held', why)        not sent yet, kept and sent later (only the kinds that can wait)
         ('suppressed', why)  the address is on the bounce list; nothing was tried
         ('failed', why)      not sent and not kept (codes, reset links, applications: the caller tells the person)
    `user` and `mail_row` are kept with held mail, so deleting the account also drops it and the stored copy can be marked sent later."""
    stamp(msg, kind)
    to = (_recipients(msg) or [""])[0]
    why = suppressed(to)
    if why:
        _log(kind, to, "the address is on the bounce list", why, "not tried")
        return "suppressed", why
    quota, prio = _limits(cfg)
    n, full = today()
    if kind in DEFERRABLE and (full or n >= prio):
        until = next_day()
        hold(msg, kind, to, user, mail_row, until, "daily limit")
        _log(kind, to, "daily limit", "%d of %d sent today; %d kept for codes and applications" % (n, quota, quota - prio) if not full else
             "the mail service said the quota is used up", "held until %s" % _when(until))
        return "held", "quota"
    if full or n >= quota:
        _log(kind, to, "quota", "%d of %d sent today" % (n, quota) if not full else "the mail service said the quota is used up", "not sent")
        return "failed", "quota"
    for i in range(2):
        started = time.monotonic()
        try:
            _smtp(cfg, msg)
            _bump()
            return "sent", ""
        except Exception as e:                         # every failure ends here: never an unhandled error from a mail server
            why, detail = classify(e)
        # one more try for a dropped connection or a 4xx answer, but only when the first one failed fast: a person may be waiting,
        # and a mail server that timed out once (20 seconds) is not asked again in the same request
        if i == 0 and why in ("unreachable", "temporary") and time.monotonic() - started < 5:
            time.sleep(RETRY_SECONDS)
            continue
        break
    if why == "quota":
        _bump(full=True)
    if why == "recipient":
        suppress(to, "refused")
    if kind in DEFERRABLE and why in ("quota", "login", "unreachable", "temporary"):
        until = next_day() if why == "quota" else clock() + HOLD_RETRY_SECONDS
        hold(msg, kind, to, user, mail_row, until, why)
        _log(kind, to, why, detail, "held until %s" % _when(until))
        return "held", why
    _log(kind, to, why, detail, "not sent" + (": the SMTP key in UAPLY_CONFIG_JSON (smtp.password) is wrong or was revoked" if why == "login" else ""))
    return "failed", why


# ---------- mail held for later ----------
def _queue_path():
    return os.path.join(QUEUE_DIR or os.path.join(data_root(), "default"), "mail-held.json")


def _queue():
    with _lock:
        return _read_json(_queue_path(), [])


def hold(msg, kind, to, user, mail_row, until, why, tries=0, ident=None):
    with _lock:
        q = _queue()
        q.append({"id": ident or uuid.uuid4().hex[:12], "kind": kind, "to": to, "user": user, "row": mail_row, "after": int(until),
                  "why": why, "tries": tries, "at": int(clock()), "raw": msg.as_string()})
        _write_json(_queue_path(), q)


def _drop(ident):
    with _lock:
        _write_json(_queue_path(), [e for e in _queue() if e.get("id") != ident])


def forget_user(user_id):
    """Held mail for an account that was deleted is dropped with it."""
    if not user_id:
        return 0
    with _lock:
        q = _queue()
        keep = [e for e in q if e.get("user") != user_id]
        if len(keep) != len(q):
            _write_json(_queue_path(), keep)
        return len(q) - len(keep)


def flush(cfg, on_sent=None):
    """Send held mail that is due, while today's count is under the priority line. Returns how many were sent. One flush at a time."""
    if not _flush_lock.acquire(blocking=False):
        return 0
    sent = 0
    try:
        quota, prio = _limits(cfg)
        while True:
            n, full = today()
            if full or n >= prio:
                break
            due = sorted((e for e in _queue() if e.get("after", 0) <= clock()), key=lambda e: e.get("after", 0))
            if not due:
                break
            e = due[0]
            if suppressed(e.get("to")):
                _drop(e["id"])
                _log(e.get("kind"), e.get("to"), "the address is on the bounce list", suppressed(e.get("to")), "held mail dropped")
                continue
            msg = email.message_from_string(e["raw"], policy=email.policy.default)
            try:
                _smtp(cfg, msg)
            except Exception as ex:
                why, detail = classify(ex)
                _drop(e["id"])
                if why == "quota":
                    _bump(full=True)
                if why in ("quota", "login", "unreachable", "temporary") and e.get("tries", 0) + 1 < MAX_TRIES:
                    until = next_day() if why == "quota" else clock() + HOLD_RETRY_SECONDS * (e.get("tries", 0) + 1)
                    hold(msg, e["kind"], e["to"], e.get("user"), e.get("row"), until, why, e.get("tries", 0) + 1, e["id"])
                    _log(e["kind"], e["to"], why, detail, "held mail kept, next try %s" % _when(until))
                    if why in ("quota", "login"):
                        break
                else:
                    _log(e["kind"], e["to"], why, detail, "held mail dropped after %d tries" % (e.get("tries", 0) + 1))
                continue
            _bump()
            _drop(e["id"])
            sent += 1
            if on_sent:
                try:
                    on_sent(e)
                except Exception:
                    pass
    finally:
        _flush_lock.release()
    if sent:
        sys.stderr.write("[uaply] sent %d held email(s)\n" % sent)
    return sent


def start_worker(get_cfg, on_sent=None, every=300):
    """A background thread that sends held mail when it is due (every 5 minutes)."""
    def run():
        while True:
            time.sleep(every)
            try:
                cfg = get_cfg()
                if (cfg.get("smtp") or {}).get("host"):
                    flush(cfg, on_sent)
            except Exception as e:
                sys.stderr.write("[uaply] sending held mail failed: %s\n" % type(e).__name__)
    t = threading.Thread(target=run, daemon=True, name="uaply-mail")
    t.start()
    return t
