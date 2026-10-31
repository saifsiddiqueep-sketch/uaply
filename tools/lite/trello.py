#!/usr/bin/env python3
"""Trello sync for Workflow Lite. Cards are addressed by their board number (the #34 in the card URL).

  python tools/lite/trello.py show 34
  python tools/lite/trello.py show 191 --handoff                         # the latest handoff note too (skips other comments)
  python tools/lite/trello.py update 34 --list "Review" --comment "PR #12 open. Tests: node check.js exit 0"
  python tools/lite/trello.py update 34 --check "Root cause written"     # ticks a checklist item by text
  python tools/lite/trello.py gh-event                                   # used by the GitHub Action
  python tools/lite/trello.py areas                                      # the 12 area cards + numbers
  python tools/lite/trello.py handoff "Job Feeds — Rumman" --file note.md   # post + verify a handoff
  python tools/lite/trello.py wip "Job Feeds" . ../wt-c34                  # commit+push WIP on each worktree's own branch
  python tools/lite/trello.py decisions "Job Feeds"                          # OPEN DECISIONS still open in the last handoff

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
from _common import DEFAULT_BOARD, ENV_FILE, die, load_env, log_event, trello  # noqa: E402

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


def sign(text, limit=16000):
    """Team rule: every Trello comment ends with '— <FOUNDER> via Claude' (added once, kept inside the limit)."""
    who = (_common.founder() or "").strip()
    # no founder name (e.g. the GitHub Actions gh-event run) → say it was automatic, not "unknown"
    tag = f"— {who} via Claude" if who and who.lower() != "unknown" else "— GitHub (automatic)"
    text = text.rstrip()
    if text.endswith(tag):
        return text[:limit]
    return f"{text[:limit - len(tag) - 1]}\n{tag}"


def areas_list_ids():
    """Ids of every list that reads as '📍 Areas' (an 'Areas — old' copy counts too, so none can hide the real one)."""
    want = _norm(AREAS_LIST)
    return {lst["id"] for lst in trello("GET", f"/boards/{board()}/lists", {"fields": "name"}) or []
            if _norm(lst.get("name")) == want}


def update(num, to_list=None, comment=None, check=None):
    c = card(num)
    done = [f"#{num} {c['name'][:60]}"]
    if to_list:
        # area cards are pinned to '📍 Areas' for good; only work cards move between columns (and never into Areas)
        if c.get("idList") in areas_list_ids():
            done.append(f"(area card — stays in {AREAS_LIST}, not moved)")
        elif _norm(to_list) == _norm(AREAS_LIST):
            done.append(f"(not moved — only area cards live in {AREAS_LIST})")
        else:
            trello("PUT", f"/cards/{c['id']}", {"idList": list_id(to_list)})
            done.append(f"→ {to_list}")
            log_event("card", action="move", card=str(num), to=to_list)
    if comment:
        trello("POST", f"/cards/{c['id']}/actions/comments", {"text": sign(comment)})
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
    hit = [lst for lst in lists if _norm(lst.get("name")) == want]
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
        posted = trello("POST", f"/cards/{c['id']}/actions/comments", {"text": sign(text, MAX_COMMENT)}) or {}
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


NOTE_HEADS = re.compile(r"^(AREA|GOAL|DONE|NEXT|OPEN DECISIONS|FILES THAT MATTER|LOCKS HELD|WIP BRANCHES|UNPUSHED WORK)"
                        r"(?:\s*\([^)]*\))?\s*:")                    # exact headings only: "Next release date:" isn't one
# only a marker at the start/end counts: "to be resolved Friday" or "keep the ✅ badge?" stay open
RESOLVED = re.compile(r"^\s*(?:\[x\]|✅)|(?:\[x\]|✅)\s*$|✅\s*resolved\b|[—–-]\s*resolved\b[^—–;]*$|\(resolved[^)]*\)\s*$", re.I)


def open_decisions(text):
    """Items under OPEN DECISIONS in a handoff note that aren't marked resolved (✅, [x] or a trailing '— resolved')."""
    items, inside = [], False
    for line in (text or "").splitlines():
        bare = re.sub(r"^[\s*#_>]+", "", line)                       # "**OPEN DECISIONS:**", "## NEXT:" are headings too
        head = NOTE_HEADS.match(bare)
        if head:
            inside = head.group(1).upper() == "OPEN DECISIONS"
            line = re.sub(r"^[\s*_]+", "", bare[head.end():])
            parts = [x for x in re.split(r"\s*;\s*", line) if x.strip()] if inside else []
        elif inside and line.strip().startswith("— ") and line.strip().endswith("via Claude"):
            break                                                    # the signature ends the note
        else:
            parts = [line] if inside else []
        for x in parts:
            x = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", x).strip()
            if x and not RESOLVED.search(x) and x.lower().rstrip(".") not in ("none", "n/a", "-", "nothing"):
                items.append(x)
    return items


def decisions_cmd(query):
    """Print the still-open decisions from the area card's latest handoff, ready to paste under OPEN DECISIONS."""
    miss = missing_keys()
    if miss:
        raise HandoffError(_keys_msg(miss))
    try:
        c = match_area(query, area_cards())
        acts = trello("GET", f"/cards/{c['id']}/actions", {"filter": "commentCard", "limit": "50"}) or []
    except Exception as e:  # noqa: BLE001
        raise HandoffError(_explain(e)) from e
    notes = [x["data"]["text"] for x in acts if x["data"]["text"].lstrip().startswith("AREA:")]
    if not notes:
        print(f"(no earlier handoff on {c['name']} — nothing to carry forward)")
        return
    items = open_decisions(notes[0])
    print(f"Carried from the last handoff on {c['name']} ({len(items)} open):")
    for x in items:
        print(f"- {x}")


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
    s = sub.add_parser("show"); s.add_argument("num"); s.add_argument("--handoff", "--last-comment", dest="handoff", action="store_true")
    u = sub.add_parser("update"); u.add_argument("num")
    u.add_argument("--list"); u.add_argument("--comment"); u.add_argument("--check")
    sub.add_parser("gh-event")
    h = sub.add_parser("handoff", help="post a handoff note to an area card and verify it")
    h.add_argument("area", help='area name or chat title, e.g. "Job Feeds — Rumman"')
    h.add_argument("--file", required=True, help="note file (UTF-8; avoids shell quoting)")
    sub.add_parser("areas", help="list the area cards")
    w = sub.add_parser("wip", help="commit + push uncommitted work on each worktree's own branch (handoff step 0)")
    w.add_argument("area"); w.add_argument("worktrees", nargs="*", help="worktree folders this area used (default: .)")
    d = sub.add_parser("decisions", help="OPEN DECISIONS from the area's last handoff that aren't resolved")
    d.add_argument("area")
    a = p.parse_args()
    if a.cmd == "wip":
        import handoff_wip  # noqa: E402 — git only, no Trello keys needed
        area = re.split(r"\s+[—–]\s+", a.area.strip(), maxsplit=1)[0]     # drop the " — Rumman" chat suffix
        rc = handoff_wip.wip(area, a.worktrees)
        log_event("handoff", action="wip", area=area, ok=rc == 0)
        sys.exit(rc)
    if a.cmd in ("handoff", "areas", "decisions"):
        try:
            if a.cmd == "handoff":
                print(handoff(a.area, a.file))
                log_event("handoff", action="post", area=a.area.split(" ")[0], ok=True)
            elif a.cmd == "decisions":
                decisions_cmd(a.area)
            else:
                areas_cmd()
        except HandoffError as e:
            if a.cmd == "handoff":
                log_event("handoff", action="post", area=a.area.split(" ")[0], ok=False)
            print(f"NOT POSTED ✗ {e}" if a.cmd == "handoff" else f"FAILED ✗ {e}", file=sys.stderr)
            sys.exit(e.code)
        except Exception as e:  # noqa: BLE001
            if a.cmd == "handoff":
                log_event("handoff", action="post", area=a.area.split(" ")[0], ok=False)
            print(f"NOT POSTED ✗ {_explain(e)}", file=sys.stderr)
            sys.exit(1)
        return
    try:
        if a.cmd == "show":
            c = card(a.num); print(f"#{a.num} {c['name']}  {c['shortUrl']}")
            if a.handoff:
                # newest comment in the /handoff format (starts "AREA:"), so later notes don't hide it
                acts = trello("GET", f"/cards/{c['id']}/actions", {"filter": "commentCard", "limit": "50"}) or []
                notes = [x["data"]["text"] for x in acts if x["data"]["text"].lstrip().startswith("AREA:")]
                print(notes[0] if notes else "(no handoff yet)")
        elif a.cmd == "update":
            update(a.num, a.list, a.comment, a.check)
        else:
            gh_event()
    except Exception as e:
        die(f"Trello: FAILED — {e}. Nothing was changed on that step; do not report it as done.")


if __name__ == "__main__":
    main()
