"""The connect-kit outreach queue: who to invite to connect each week, and where each invitation stands. It sends nothing and contacts
nobody: it reads files and writes one file (the queue's state). A person sends the kit email (docs/employers/connect-kit.md) from the team's
own mailbox and marks it here; an employer that connects its hiring system makes every swipe right on its jobs a real application
(route 1: sent straight into the employer's own system), so route 1 grows week by week.

  python tools/outreach-queue.py                       this week's invitations (default 10), and the queue's totals
  python tools/outreach-queue.py --per-week 15         a bigger week
  python tools/outreach-queue.py --mark greenhouse:acme invited [--note "sent to talent@"]
                                                       records a step: invited, replied, connected, declined (or queued, to undo)
  python tools/outreach-queue.py --list                every employer in the queue with its state
  options: --state FILE (default docs/employers/outreach-queue.json), --swipes FILE (a decisions.jsonl from a server's records folder:
           employers people swipe right on most come first), --boards FILE (default job-boards.json), --first SYSTEM (default
           smartrecruiters: the largest share of jobs, and an Application API that applies "on behalf of the candidate")

Order: SYSTEM's boards first, then by swipes right in the last 30 days (when --swipes is given), then by US jobs. An employer already
invited, connected or declined is never offered again; one that replied stays out of the week's list until it is marked again."""
import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KINDS = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "smartrecruiters": "SmartRecruiters", "workable": "Workable"}
CAREERS = {"greenhouse": "https://job-boards.greenhouse.io/%s", "lever": "https://jobs.lever.co/%s", "ashby": "https://jobs.ashbyhq.com/%s",
           "smartrecruiters": "https://careers.smartrecruiters.com/%s", "workable": "https://apply.workable.com/%s/"}
# what the employer creates and gives (docs/employers/connect-kit.md, "Connect in five minutes")
KEY = {"greenhouse": "a Job Board API key and the board name", "lever": "a Postings API key and the site name",
       "ashby": "an API key with Candidates write and Jobs read only, and the board name",
       "smartrecruiters": "an API key (applications go in through the Application API, on behalf of the candidate)",
       "workable": "an API token with r_jobs and w_candidates only, and the subdomain"}
STATES = ("queued", "invited", "replied", "connected", "declined")
DONE = ("invited", "connected", "declined")
DEFAULT_STATE = os.path.join(ROOT, "docs", "employers", "outreach-queue.json")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def boards(path):
    rows = (load(path, {}) or {}).get("boards") or []
    return [b for b in rows if b.get("kind") in KINDS and isinstance(b.get("token"), str) and TOKEN_RE.match(b["token"])]


def swipes(path, now=None):
    """Swipes right per employer name in the last 30 days, from a server's decisions.jsonl (no person is named in it)."""
    out = {}
    if not path:
        return out
    since = (now or datetime.datetime.now(datetime.timezone.utc).timestamp()) - 30 * 86400
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(d, dict) or d.get("dir") not in ("apply", "applied", "right"):
                    continue
                if (d.get("at") or 0) / (1000 if (d.get("at") or 0) > 1e11 else 1) < since:
                    continue
                co = str(d.get("co") or "").strip().lower()
                if co:
                    out[co] = out.get(co, 0) + 1
    except OSError:
        pass
    return out


def key(b):
    return "%s:%s" % (b["kind"], b["token"].lower())


def ranked(rows, state, sw, first):
    st = state.get("employers") or {}
    def order(b):
        return (0 if b["kind"] == first else 1, -sw.get(str(b.get("name") or "").strip().lower(), 0), -(b.get("us") or 0), b.get("name") or b["token"])
    return [b for b in sorted(rows, key=order) if (st.get(key(b)) or {}).get("status", "queued") == "queued"]


def week(rows, state, sw, first, n):
    return ranked(rows, state, sw, first)[:n]


def totals(rows, state):
    st = state.get("employers") or {}
    jobs = {key(b): b.get("us") or 0 for b in rows}
    all_jobs = sum(jobs.values()) or 1
    out = {s: 0 for s in STATES}
    for b in rows:
        out[(st.get(key(b)) or {}).get("status", "queued")] += 1
    connected_jobs = sum(jobs.get(k, 0) for k, v in st.items() if (v or {}).get("status") == "connected")
    return out, connected_jobs, all_jobs


def mark(state, rows, who, status, note="", today=None):
    if status not in STATES:
        raise SystemExit("the step is one of: " + ", ".join(STATES))
    kind, _, token = who.partition(":")
    found = [b for b in rows if b["kind"] == kind and b["token"].lower() == token.lower()]
    if not found:
        raise SystemExit("no employer %s in the boards file (use system:board, for example greenhouse:acme)" % who)
    b = found[0]
    e = state.setdefault("employers", {}).setdefault(key(b), {"name": b.get("name") or b["token"], "system": KINDS[kind], "history": []})
    e["status"] = status
    e["history"].append({"on": today or datetime.date.today().isoformat(), "status": status, "note": str(note or "")[:200]})
    return e


def save(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def table(rows, sw):
    out = ["| # | Employer | System | US jobs | Swipes right (30 days) | Careers site (find the recruiting contact there) | They create |", "|---|---|---|---|---|---|---|"]
    for i, b in enumerate(rows, 1):
        out.append("| %d | %s | %s | %d | %d | %s | %s |" % (i, (b.get("name") or b["token"]).replace("|", "/"), KINDS[b["kind"]], b.get("us") or 0,
                                                       sw.get(str(b.get("name") or "").strip().lower(), 0), CAREERS[b["kind"]] % b["token"], KEY[b["kind"]]))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="The connect-kit outreach queue (it never sends anything)")
    ap.add_argument("--state", default=DEFAULT_STATE)
    ap.add_argument("--boards", default=os.path.join(ROOT, "job-boards.json"))
    ap.add_argument("--swipes", default="")
    ap.add_argument("--first", default="smartrecruiters", choices=sorted(KINDS))
    ap.add_argument("--per-week", type=int, default=10)
    ap.add_argument("--mark", nargs=2, metavar=("SYSTEM:BOARD", "STEP"))
    ap.add_argument("--note", default="")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    rows = boards(a.boards)
    state = load(a.state, {"employers": {}}) or {"employers": {}}
    if a.mark:
        e = mark(state, rows, a.mark[0], a.mark[1], a.note)
        save(a.state, state)
        print("%s (%s): %s" % (e["name"], e["system"], e["status"]))
        return 0
    sw = swipes(a.swipes)
    if a.list:
        st = state.get("employers") or {}
        for k, v in sorted(st.items()):
            print("%-40s %-16s %s" % (k, v.get("status"), (v.get("history") or [{}])[-1].get("on", "")))
        return 0
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    t, cj, aj = totals(rows, state)
    print("This week's invitations (%d). Send the kit email from the team's own mailbox, then mark each one invited:" % a.per_week)
    print(table(week(rows, state, sw, a.first, a.per_week), sw))
    print("\nQueue: " + ", ".join("%s %d" % (s, t[s]) for s in STATES) +
          ". Connected employers list %d US jobs, %.1f%% of the jobs on these five systems." % (cj, 100.0 * cj / aj))
    return 0


if __name__ == "__main__":
    sys.exit(main())
