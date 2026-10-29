#!/usr/bin/env python3
"""Trello sync for Workflow Lite. Cards are addressed by their board number (the #34 in the card URL).

  python tools/lite/trello.py show 34
  python tools/lite/trello.py update 34 --list "Review" --comment "PR #12 open. Tests: node check.js exit 0"
  python tools/lite/trello.py update 34 --check "Root cause written"     # ticks a checklist item by text
  python tools/lite/trello.py gh-event                                   # used by the GitHub Action

Branch naming that makes auto-sync work: c<card#>-<slug>, e.g. c34-swipe-trace.
Board defaults to UAply Team (85o0niWK); override with TRELLO_BOARD.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import DEFAULT_BOARD, die, load_env, trello  # noqa: E402


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


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show"); s.add_argument("num")
    u = sub.add_parser("update"); u.add_argument("num")
    u.add_argument("--list"); u.add_argument("--comment"); u.add_argument("--check")
    sub.add_parser("gh-event")
    a = p.parse_args()
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
