# Outside uptime check

Render restarts UAply when its own health check fails, but nothing outside Render watched https://uaply.net, and the phone apps load
that site, so a website outage is also an app outage. Two GitHub workflows now watch it from outside, for free and with no account to
create. A free UptimeRobot (or Better Stack) monitor can add a phone alert later (the last section); that one is a person's choice.

`/healthz` answers `{"ok": true}` (HTTP 200) in milliseconds while the server runs, and `{"ok": false, "stopping": true}` (HTTP 503) for the
few seconds a deploy stops the old copy. It reads no disk and no job boards, so a check never slows the site.

## What runs

| Workflow | When | What it does |
|---|---|---|
| **Uptime of uaply.net** (`.github/workflows/uptime.yml`) | every 10 minutes (7, 17, 27, 37, 47 and 57 past the hour) | `tools/uptime-check.py` asks `/healthz` (must say `{"ok": true}`), the home page (must answer 200 and be UAply's) and `/readyz` (the server has none yet: a 404 is a SKIP, never an alarm). When any check fails it waits 2 minutes and asks again. Only a second failure counts as down. |
| **Daily health snapshot of uaply.net** (`.github/workflows/health-snapshot.yml`) | every day at 11:23 UTC | Saves `uaply-health-DATE.json` (the checks above with response times, and the public yes/no facts of `/api/status` with the deployed commit) and `uaply-live-check-DATE.txt` (every line of `tools/live-check.py`, without the wrong logins) as a workflow artifact kept 90 days. Render deletes its logs after 7 days; these files stay. A down site is saved, never an alarm; a missing or broken script turns the run red. |

Both also have a **Run workflow** button on their page in the Actions tab, for a check right now.

**Only from `main`.** GitHub runs scheduled workflows only from the repository's default branch (`main`), and may start them a few
minutes late. Nothing runs by itself until **four files** are on `main`: `.github/workflows/uptime.yml`, `.github/workflows/health-snapshot.yml`,
`tools/uptime-check.py` and `tools/live-check.py` (both scripts use Python's standard library only). Copying only the two workflow files
is not enough: the uptime run would fail every time without opening an issue, and the snapshot run would turn red with nothing saved.

**Switched off after 60 quiet days.** In a public repository, GitHub turns scheduled workflows off after 60 days with no activity in
the repository. If the Actions tab shows a workflow as disabled, open it and press **Enable workflow**.

## What an alert looks like

- **Down:** one GitHub issue titled **uaply.net is down**, opened by github-actions. It says what failed (for example "health
  (/healthz): answered 503" or "no answer"), when it was first seen, how many checks in a row failed, a link to the check, and what to
  do: the service on Render (uaply, Events and Logs), then `DEPLOY.md`, "Running the live site". It mentions both founders, so GitHub
  emails them (and anyone watching the repository).
- **Still down:** the same issue is edited quietly at each check (the count and the time go up). No new issue, no email every check.
- **Back up:** a note ("https://uaply.net answers again ... first seen down at ..., about N minutes earlier") and the issue closes. That
  note is the second email. A later outage opens a new issue; the closed ones are the outage history.
- A deploy's few seconds never raise an alarm: the second try, 2 minutes later, passes.
- If GitHub refuses to open the issue, the run fails (red) and GitHub emails whoever last changed the workflow file.
- The first sentence says what happened: "got no answer" when nothing answered (refused, timed out, no such name), "got an error
  answer" when the site answered with an error. It says the phone apps are probably down too only when `/healthz` or the home page
  failed, not when only `/readyz` did.
- Only an issue that the check opened (github-actions) is edited or closed. An issue a person opens with the same title is left alone.
- **It is public.** The repository is public today, so anyone can read the outage issue, and anyone signed in to GitHub can download
  the daily snapshot. Both hold only what the check saw from outside (which check failed, the answer code, the times, the public
  `/api/status` facts and commit) and the "what to do" steps; nothing that is not already visible on the live site.

## Settings (no code change)

All in the repository's **Settings, Secrets and variables, Actions, Variables**, as **repository variables**:

| Variable | Value | Effect |
|---|---|---|
| `UPTIME_PAUSED` | `on` | **Silence it**: every check is skipped until the variable is removed. (Or the "..." menu on the workflow's page, **Disable workflow**.) |
| `UPTIME_HOURLY` | `on` | Check once an hour (at 7 past) instead of every 10 minutes. Only needed if the repository is made private (see "What it costs"). |
| `UPTIME_NOTIFY` | `@name @name` | Who the issue mentions. Unset, it mentions `@saifsiddiqueep-sketch @mrhphiladelphia-code`. |

To stop the emails for one open issue without pausing the check, **Unsubscribe** on that issue.

## What it costs

Nothing. The repository is public today (`gh api repos/saifsiddiqueep-sketch/uaply --jq .visibility` says `public`), and GitHub's
standard machines are free with no minute limit for public repositories.

If the repository is ever made private, that changes: GitHub then counts each run as at least one minute, every 10 minutes is about
4,300 minutes a month, and the Free plan includes 2,000 (when they run out, every workflow stops, "Check the code" too). Before making it
private, set `UPTIME_HOURLY` to `on` (about 720 minutes a month, plus about 60 for the daily snapshot), or rely on the phone monitor below.

The daily snapshot runs `tools/live-check.py`, which also sends a few requests that the site is meant to refuse or answer harmlessly: a
sign-in from a foreign site, a password reset for a made-up example.com address, a forged billing webhook, a checkout without signing in,
and one question to the help chat ("How do I apply?"). If AI answers are switched on, that question is one small paid AI call a day, and
these requests show up in the site's own counts.

## Test it

- From a computer: `python tools/uptime-check.py` (uaply.net; exit 0 up, 1 down) and `python tools/uptime-check.py --base
  http://127.0.0.1:9` (a dead address: every check FAILs).
- The issue logic, against a stand-in site and a stand-in GitHub: `python tools/test-uptime.py` (also in `tools/run-all-tests.sh`). With no
  port given it uses free ports the computer picks, so two runs at the same time do not disturb each other.
- On GitHub: **Run workflow** on "Uptime of uaply.net". A green run with "no open issue, nothing to change" in its log means it works.

## Add a phone alert (UptimeRobot, free)

A person's choice, about 5 minutes. UptimeRobot's free plan asks `https://uaply.net/healthz` every 5 minutes from outside and emails you
when it fails and again when it is back. Its phone app can also send a notification to Saif's phone (check the free plan's current
terms). Better Stack has a similar free plan. Only the owner creates the account.

### Set it up

1. Go to https://uptimerobot.com and choose **Register for FREE**. Sign up with **uaplytechnologies@gmail.com** and confirm the email.
2. **Alert contact** (the address that gets the emails): **My Settings** (or **Integrations & Team**, then **Alert contacts**). The sign-up
   email is already there; if not, **Add alert contact**, type **E-mail**, value **uaplytechnologies@gmail.com**, and confirm the email
   UptimeRobot sends to it.
3. **+ New monitor** (or **Add New Monitor**) and fill in:
   | Field | Value |
   |---|---|
   | Monitor type | **Keyword** |
   | Friendly name | `UAply health` |
   | URL | `https://uaply.net/healthz` |
   | Keyword | `"ok": true` (with the quotes and the space, exactly as the server writes it; plain `ok` would also match the 503 answer `{"ok": false}`) |
   | Alert when | **Keyword does not exist** (UptimeRobot may call it "Alert if keyword not exists") |
   | Case sensitive | off |
   | Monitoring interval | **5 minutes** (the free plan's shortest) |
   | Request timeout | 30 seconds |
   | Alert contacts to notify | tick **uaplytechnologies@gmail.com** |
4. **Create monitor**. Within 5 minutes it shows **Up** (green).
5. **For the phone:** install the UptimeRobot app, sign in with the same account and allow notifications.

### What to expect

- A deploy takes a few seconds; a 5-minute check almost never lands on it. If one does, the email says "down" and a second email says
  "up" 5 minutes later; nothing needs doing.
- A real outage: the email arrives within about 5 minutes. Check the service on Render (uaply, Events and Logs), then `DEPLOY.md`,
  "Running the live site".
- Test it once: in UptimeRobot, open the monitor, **Edit**, change the keyword to `"ok": false`, save, and wait for the "down" email.
  Put `"ok": true` back afterwards.

### Optional

- A second monitor of type **HTTP(s)** for `https://uaply.net/` (the home page itself, through Cloudflare and the domain).
- **Status pages**: a free public page at a stats.uptimerobot.com address that shows whether UAply is up; link it from the Support page
  if you like.
