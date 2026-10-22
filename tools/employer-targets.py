"""The employers to invite first: the top N employers in UAply's feed on Greenhouse, Lever, Ashby, SmartRecruiters and Workable, by the number
of US jobs the feed reads from their board (job-boards.json, as tools/find-boards.py last counted them), each with the public careers site
where their recruiting contact can be found. It reads a file and writes a table; it sends nothing and contacts nobody.
  python tools/employer-targets.py                 prints the table
  python tools/employer-targets.py --write         also puts it into docs/employers/connect-kit.md, between its two TARGETS markers
  options: --top 50"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KINDS = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "smartrecruiters": "SmartRecruiters", "workable": "Workable"}
CAREERS = {"greenhouse": "https://job-boards.greenhouse.io/%s", "lever": "https://jobs.lever.co/%s", "ashby": "https://jobs.ashbyhq.com/%s",
           "smartrecruiters": "https://careers.smartrecruiters.com/%s", "workable": "https://apply.workable.com/%s/"}
KIT = os.path.join(ROOT, "docs", "employers", "connect-kit.md")
START, END = "<!-- TARGETS: written by tools/employer-targets.py -->", "<!-- /TARGETS -->"


def targets(top):
    boards = json.load(open(os.path.join(ROOT, "job-boards.json"), encoding="utf-8"))["boards"]
    rows = [b for b in boards if b.get("kind") in KINDS and isinstance(b.get("token"), str) and re.match(r"^[A-Za-z0-9_.-]+$", b["token"])]
    rows.sort(key=lambda b: (-(b.get("us") or 0), -(b.get("total") or 0), b.get("name") or ""))
    return rows[:top]


def table(rows):
    checked = max((b.get("checked") or "" for b in rows), default="")
    out = ["Ranked by US jobs in UAply's feed (job-boards.json, counted %s). The careers site is the employer's own public job board; their"
           " recruiting contact is usually linked from it or from the company's main site. Nothing has been sent to any of them." % checked, "",
           "| # | Employer | System | US jobs | All jobs | Careers site |", "|---|---|---|---|---|---|"]
    for i, b in enumerate(rows, 1):
        name = (b.get("name") or b["token"]).replace("|", "/")
        out.append("| %d | %s | %s | %d | %d | %s |" % (i, name, KINDS[b["kind"]], b.get("us") or 0, b.get("total") or 0, CAREERS[b["kind"]] % b["token"]))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    t = table(targets(a.top))
    if a.write:
        doc = open(KIT, encoding="utf-8").read()
        if START not in doc or END not in doc:
            sys.exit("docs/employers/connect-kit.md has no TARGETS markers")
        doc = doc[:doc.index(START) + len(START)] + "\n" + t + "\n" + doc[doc.index(END):]
        with open(KIT, "w", encoding="utf-8", newline="\n") as f:
            f.write(doc)
    sys.stdout.reconfigure(encoding="utf-8")
    print(t)


if __name__ == "__main__":
    main()
