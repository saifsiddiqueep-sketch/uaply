#!/usr/bin/env python3
"""Trello sync for Workflow Lite. Cards are addressed by their board number (the #34 in the card URL).

  python tools/lite/trello.py show 34
  python tools/lite/trello.py update 34 --list "Review" --comment "PR #12 open. Tests: node check.js exit 0"
  python tools/lite/trello.py update 34 --check "Root cause written"     # ticks a checklist item by text
  python tools/lite/trello.py gh-event                                   # used by the GitHub Action
  python tools/lite/trello.py areas                                      # the 12 area cards + numbers
  python tools/lite/trello.py handoff "Job Feeds — Rumman" --file note.md   # post + verify a handoff

Branch naming that makes auto-sync work: c<card#>-<slug>, e.g. c34-swipe-trace.
Board defaults to UAply Team Board (TUiuK5fz); override with TRELLO_BOARD.
"""
import argparse
import json
import os
import re
import socket
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import _common  # noqa: E402
from _common import DEFAULT_BOARD, ENV_FILE, die, load_env, trello  # noqa: E402

AREAS_LIST = "📍 Areas"
MAX_COMMENT = 16000


def board():
    load_env()
    return os.environ.get("TRELLO_BOARD", DEFAULT_BOARD)


def card(num):
    return trello("GET", f"/boards/{board()}/cards/{num}", {"fields": "name,idList,shortUrl,closed"})


def list_id(name):
    for lst in trello("GET", f"/boards/{board()}/lists", {"fields": "name"}):
        if lst["name"].strip().lower() == name.strip().lower():
            return lst["id"]
    die(f"No list named '{name}' on board {board()}")


def update(num, to_list=None, comment=None, check=None):
    c = card(num)
    done = [f"#{num} {c['name'][:60]}"]
    if to_list:
        trello("PUT", f"/cards/{c['id']}", {"idList": list_id(to_list)})
        done.append(f"→ {to_list}")
    if comment:
        trello("POST", f"/cards/{c['id']}/actions/comments", {"text": comment[:16000]})
        done.append("+comment")
    if check:
        hit = False
        for cl in trello("GET", f"/cards/{c['id']}/checklists"):
            for item in cl["checkItems"]:
                if check.lower() in item["name"].lower():
                    trello("PUT", f"/cards/{c['id']}/checkItem/{item['id']}", {"state": "complete"})
                    done.append(f"✓ {item['name'][:40]}")
                    hit = True
        if not hit:
            done.append(f"(no checklist item matched '{check}')")
    print(" ".join(done))


def card_from(text):
    m = re.search(r"(?:^|[/\s\[#-])c(\d{1,5})(?=-|\b)", text or "", re.I) or re.search(r"#(\d{1,5})\b", text or "")
    return m.group(1) if m else None


def gh_event():
    """Called from .github/workflows/trello-sync.yml. Zero model tokens: plain GitHub Action."""
    ev = json.load(open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8"))
    pr = ev.get("pull_request") or {}
    num = card_from(pr.get("head", {}).get("ref", "")) or card_from(pr.get("title", ""))
    if not num:
        print("No card number in branch/title (use c<card#>-slug). Skipping.")
        return
    base, url = pr.get("base", {}).get("ref"), pr.get("html_url")
    action, merged = ev.get("action"), pr.get("merged")
    if action in ("opened", "reopened", "ready_for_review"):
        update(num, "Review", f"🔀 PR opened into `{base}`: {url}")
    elif action == "closed" and merged and base == "sandbox":
        update(num, None, f"✅ Merged to sandbox: {url} (sha {pr.get('merge_commit_sha', '')[:7]})")
    elif action == "closed" and merged and base == "dev":
        update(num, "Done", f"🚀 Released to LIVE: {url}")
    elif action == "closed":
        update(num, None, f"✖ PR closed without merge: {url}")


# ---- handoff: area name -> card, post, read back -------------------------------------------
class HandoffError(Exception):
    """One-line, plain-English reason. code 2 = couldn't pick the area, 1 = anything else."""
    def __init__(self, msg, code=1):
        super().__init__(msg)
        self.code = code


def _norm(text):
    """'Job Feeds — Rumman' -> 'job feeds'; '&' == 'and'; emoji/punctuation ignored."""
    t = (text or "").strip()
    t = re.split(r"\s+[—–]\s+|\s+-\s+", t, maxsplit=1)[0]   # drop ' — Rumman' laptop/person suffix
    t = t.lower().replace("&", " and ")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def missing_keys():
    load_env()
    return [k for k in ("TRELLO_KEY", "TRELLO_TOKEN") if not os.environ.get(k)]


def _keys_msg(missing):
    lines = " and ".join(f"'{k}=<your {k.split('_')[1].lower()}>'" for k in missing)
    return (f"Trello keys missing — add the line {lines} to {ENV_FILE} "
            f"(get them at https://trello.com/power-ups/admin → your key → Token), then retry")


def _explain(e):
    """Turn any exception from trello() into one plain-English line."""
    if isinstance(e, HandoffError):
        return str(e)
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 401:
            return (f"Trello said 401 — your TRELLO_TOKEN was revoked or expired (or TRELLO_KEY is wrong). "
                    f"Make a new token and replace the TRELLO_TOKEN= line in {ENV_FILE}")
        if e.code == 404:
            return f"Trello said 404 — board {board()} or the card wasn't found, or your Trello user isn't on the board"
        if e.code == 429:
            return "Trello said 429 — too many requests; wait a minute and retry"
        return f"Trello said HTTP {e.code} ({e.reason}) — retry; if it repeats, run python tools/lite/doctor.py"
    if isinstance(e, (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError)):
        return "Can't reach api.trello.com — you look offline (or a firewall/VPN is blocking it); reconnect and retry"
    if isinstance(e, RuntimeError) and "not set" in str(e):
        return _keys_msg(missing_keys() or ["TRELLO_KEY", "TRELLO_TOKEN"])
    return f"Unexpected Trello problem: {type(e).__name__}: {str(e)[:150]}"


def area_cards():
    """Open cards in the '📍 Areas' list, in board order."""
    lists = trello("GET", f"/boards/{board()}/lists", {"fields": "name"}) or []
    want = _norm(AREAS_LIST)
    hit = [l for l in lists if _norm(l.get("name")) == want]
    if not hit:
        raise HandoffError(f"No list named '{AREAS_LIST}' on board {board()} — someone renamed or archived it; "
                           f"restore it in Trello")
    cards = trello("GET", f"/lists/{hit[0]['id']}/cards", {"fields": "name,idShort,shortUrl,closed"}) or []
    return [c for c in cards if not c.get("closed")]


def match_area(query, cards):
    """Fuzzy-but-safe: exact → unique prefix → unique contains → all-words. Never guesses between two."""
    q = _norm(query)
    if q.isdigit():
        hits = [c for c in cards if str(c.get("idShort")) == q]
        if len(hits) == 1:
            return hits[0]
    names = [(c, _norm(c["name"])) for c in cards]
    stages = [
        lambda n: n == q,
        lambda n: len(q) >= 3 and n.startswith(q),
        lambda n: len(q) >= 3 and q in n,
        lambda n: len(q) >= 3 and set(q.split()) <= set(n.split()),
    ]
    for test in stages:
        hits = [c for c, n in names if test(n)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise HandoffError(f"'{query}' matches more than one area ({', '.join(c['name'] for c in hits)}). "
                               f"Use one of: {_valid(cards)}", code=2)
    raise HandoffError(f"No area matches '{query}'. Use one of: {_valid(cards)}", code=2)


def _valid(cards):
    return "; ".join(c["name"] for c in cards)


def read_note(path):
    p = Path(path)
    if not p.is_file():
        raise HandoffError(f"Note file not found: {path}")
    text = _common._read_text_any(p).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise HandoffError(f"Note file is empty: {path}")
    if len(text) > MAX_COMMENT:
        raise HandoffError(f"Note is {len(text)} characters; Trello's limit is {MAX_COMMENT}. Shorten it and retry")
    return text


def handoff(query, note_file):
    """Returns the success line. Raises HandoffError with a plain-English reason on ANY failure."""
    text = read_note(note_file)
    miss = missing_keys()
    if miss:
        raise HandoffError(_keys_msg(miss))
    try:
        cards = area_cards()
        c = match_area(query, cards)
        posted = trello("POST", f"/cards/{c['id']}/actions/comments", {"text": text}) or {}
        new_id = posted.get("id")
        if not new_id:
            raise HandoffError(f"Trello accepted the request but returned no comment id for '{c['name']}' — "
                               f"treat as NOT posted; retry")
        back = trello("GET", f"/cards/{c['id']}/actions", {"filter": "commentCard", "limit": "50"}) or []
        if not any(a.get("id") == new_id for a in back):
            raise HandoffError(f"Posted to '{c['name']}' but the comment isn't there when read back — "
                               f"treat as NOT posted; open {c.get('shortUrl', 'the card')} and check, then retry")
    except Exception as e:  # noqa: BLE001 — every failure must become a clear line
        if isinstance(e, HandoffError):
            raise
        raise HandoffError(_explain(e)) from e
    return f"POSTED ✓ {c['name']} {c.get('shortUrl', '')}".rstrip()


def areas_cmd():
    miss = missing_keys()
    if miss:
        raise HandoffError(_keys_msg(miss))
    try:
        cards = area_cards()
    except Exception as e:  # noqa: BLE001
        raise HandoffError(_explain(e)) from e
    for c in cards:
        print(f"#{c.get('idShort', '?'):<4} {c['name']}")
    print(f"({len(cards)} areas in '{AREAS_LIST}')")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show"); s.add_argument("num")
    u = sub.add_parser("update"); u.add_argument("num")
    u.add_argument("--list"); u.add_argument("--comment"); u.add_argument("--check")
    sub.add_parser("gh-event")
    h = sub.add_parser("handoff", help="post a handoff note to an area card and verify it")
    h.add_argument("area", help='area name or chat title, e.g. "Job Feeds — Rumman"')
    h.add_argument("--file", required=True, help="note file (UTF-8; avoids shell quoting)")
    sub.add_parser("areas", help="list the area cards")
    a = p.parse_args()
    if a.cmd in ("handoff", "areas"):
        try:
            if a.cmd == "handoff":
                print(handoff(a.area, a.file))
            else:
                areas_cmd()
        except HandoffError as e:
            print(f"NOT POSTED ✗ {e}" if a.cmd == "handoff" else f"FAILED ✗ {e}", file=sys.stderr)
            sys.exit(e.code)
        except Exception as e:  # noqa: BLE001
            print(f"NOT POSTED ✗ {_explain(e)}", file=sys.stderr)
            sys.exit(1)
        return
    try:
        if a.cmd == "show":
            c = card(a.num); print(f"#{a.num} {c['name']}  {c['shortUrl']}")
        elif a.cmd == "update":
            update(a.num, a.list, a.comment, a.check)
        else:
            gh_event()
    except Exception as e:
        die(f"Trello: FAILED — {e}. Nothing was changed on that step; do not report it as done.")


if __name__ == "__main__":
    main()
