---
name: handoff
description: Save where an area stands so the next chat — on either founder's laptop — can continue cheaply. Use before /clear, before switching model, after a >1h break, when context passes ~150k, when the other founder will pick this area up, or when the user types /handoff.
---

# Handoff (shared between Mohammed's and Saif's laptops)

We work in 12 shared areas (Swipe, Dashboard, Profile, Sign-in, Growth & Email, Mobile, Auto-Apply, Billing,
Release & Health, Legal & Support, Job Feeds, Employers). Chats live on each laptop, so the handoff is what makes an
area "the same chat" on both computers. It must go somewhere BOTH founders can read:

1. Write the note (under 200 words, facts only):
```
AREA: <name>   BY: <Mohammed|Saif>   DATE: <local time>
GOAL:
DONE (with evidence): commits/PRs/test output lines
NEXT: next 3 steps, in order
OPEN DECISIONS: who decides
FILES THAT MATTER: paths only
LOCKS HELD: (queue.py status) — release before leaving unless mid-merge
```
2. Post it as a comment on that area's Trello card in the "📍 Areas" list
   (`python tools/lite/trello.py update <card#> --comment "<note>"`, or the Trello connector if you have it).
   If Trello isn't set up, also save it as `HANDOFF-<area>.md` in the repo root (gitignored, never committed — the
   repo is public) and tell the user to paste it to the other founder.
3. Tell the user: "Next time in this area (either laptop): /clear, then /pickup <area word>" (e.g. /pickup feeds;
   the words are in `.claude/skills/pickup/SKILL.md`).

Never write secrets or user data into a handoff.
