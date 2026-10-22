# Outside uptime check (UptimeRobot, free)

Render restarts UAply when its own health check fails, but it cannot tell you when the whole service, the domain or Cloudflare is down.
An outside check can: UptimeRobot's free plan asks `https://uaply.net/healthz` every 5 minutes from outside and emails you when it fails
and again when it is back. It costs nothing and needs no change to UAply. Only the owner creates the account (about 5 minutes).

`/healthz` answers `{"ok": true}` (HTTP 200) in milliseconds while the server runs, and `{"ok": false, "stopping": true}` (HTTP 503) for the
few seconds a deploy stops the old copy. It reads no disk and no job boards, so a check never slows the site.

## Set it up

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

## What to expect

- A deploy takes a few seconds; a 5-minute check almost never lands on it. If one does, the email says "down" and a second email says
  "up" 5 minutes later; nothing needs doing.
- A real outage: the email arrives within about 5 minutes. Check the service on Render (uaply, Events and Logs), then `DEPLOY.md`,
  "Running the live site".
- Test it once: in UptimeRobot, open the monitor, **Edit**, change the keyword to `"ok": false`, save, and wait for the "down" email.
  Put `"ok": true` back afterwards.

## Optional

- A second monitor of type **HTTP(s)** for `https://uaply.net/` (the home page itself, through Cloudflare and the domain).
- **Status pages**: a free public page at a stats.uptimerobot.com address that shows whether UAply is up; link it from the Support page
  if you like.
