#!/usr/bin/env bash
# Runs every check on this computer with throwaway data and its own servers, then prints one summary.
#   bash tools/run-all-tests.sh
# Needs Node, Python 3 and Google Chrome or Chromium (found by tools/cdp.js; set UAPLY_CHROME=/path/to/chrome to choose one). It never touches your real data/ folder or uaply-config.json secrets
# (it ignores uaply-config.json by pointing UAPLY_CONFIG_JSON at its own settings).
cd "$(dirname "$0")/.." || exit 1
TMP="${TMPDIR:-/tmp}/uaply-tests-$$"
mkdir -p "$TMP"
FAILS=0
PIDS=""
trap 'for p in $PIDS; do kill "$p" 2>/dev/null; done; rm -rf "$TMP"' EXIT

step() { printf "\n== %s\n" "$1"; }
run() {   # run <label> <command...>: pass if exit 0
  local label="$1"; shift
  if out=$(timeout 600 "$@" 2>&1); then          # no single check may hang the run (a sleeping computer once froze one for hours)
    n=$(echo "$out" | grep -Eo '^[0-9]+ / [0-9]+$' | tail -1)          # the test's own "passed / total" line, so the count here is never stale
    printf "  PASS  %s%s\n" "$label" "${n:+ ($n)}"
  else printf "  FAIL  %s\n" "$label"; echo "$out" | tail -15 | sed 's/^/        /'; FAILS=$((FAILS+1)); fi
}
start() { ( "$@" >/dev/null 2>&1 & echo $! ) ; }
wait_port() { for _ in $(seq 1 60); do curl -s -o /dev/null "http://127.0.0.1:$1/healthz" 2>/dev/null && return 0; curl -s -o /dev/null "http://127.0.0.1:$1/" 2>/dev/null && return 0; sleep 0.5; done; return 1; }
# a config that switches the real-jobs feed on and nothing else (so the run never uses your own keys)
FEEDS='{"feeds":["greenhouse","lever","ashby"],"delivery":"test","smtp":{},"google":{},"owner_copy":"","anthropic_api_key":""}'
unset ANTHROPIC_API_KEY
# never read uaply-config.json (your real email login, keys and copy address): every server and test below uses only its own settings
export UAPLY_CONFIG_FILE=none

step "Static checks (syntax of every script, Python lint, JSON, legal pages, release flags, hosted builds)"
run "node check.js" node check.js
run "audit of every file (JSON, Python, JS, HTML, links, XML, images, secrets, git hygiene)" python tools/audit-files.py
run "every page and email renders, every script parses, no line break JavaScript would join, shell scripts parse" python tools/test-pages.py
run "taps and focus: the one rule (shared/uaply-focus.css) word for word in every page UAply serves" python tools/test-focus.py
run "phone apps' native settings: iPhone portrait only, the privacy manifest in the app, Android backup off, the Back and export plugins in both builds" python tools/test-mobile-native.py
run "taps and focus in Chrome at phone size: no default tap highlight anywhere, no ring after a tap, a keyboard ring, the starting-up retries" env W=390 H=844 node tools/cdp.js tools/ui-focus.js
run "assisted apply on a mock form of each hiring system: every field lands, nothing voluntary, never Submit; filled from only what the scan saw" env W=390 H=844 node tools/cdp.js tools/test-assist.js
run "assisted apply against hostile pages: a page's own UAplyAssist, a redirect to another site and a look-alike host receive nothing" env W=390 H=844 node tools/cdp.js tools/test-assist-hostile.js
run "Google Play listing pack: picture sizes and formats, text lengths, the Data safety and App content answers" python tools/test-play-listing.py
if python -m ruff --version >/dev/null 2>&1; then run "Python syntax errors and undefined names (Ruff)" python -m ruff check --select E9,F63,F7,F82 .; fi

step "Servers"
mkdir -p "$TMP/sb" "$TMP/dv" "$TMP/pub" "$TMP/smtp" "$TMP/g"
export UAPLY_CONFIG_JSON="$FEEDS"
# both in sign-up test mode (UAPLY_SIGNUP_TEST=1, allowed because they bind 127.0.0.1): behind the sign-in gate a browser test signs a
# fresh person up first (tools/gate-signup.js) and is confirmed at once; codes and receipts still land in the test inbox (/outbox)
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/sb" UAPLY_SIGNUP_TEST=1 start python serve.py 18766 sandbox --api)"
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/dv" UAPLY_SIGNUP_TEST=1 start python serve.py 18767 dev --api)"
wait_port 18766 && wait_port 18767 && echo "  sandbox on 18766, dev on 18767" || { echo "  FAIL  servers did not start"; exit 1; }
# sign-up v2: the sandbox shows the no-password card; this second sandbox has it off (UAPLY_CODE_SIGNIN=0), for the tests of today's password card
mkdir -p "$TMP/sboff"
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/sboff" UAPLY_CODE_SIGNIN=0 start python serve.py 18770 sandbox --api)"
wait_port 18770 && echo "  sandbox with today's sign-in card on 18770"
# wait for the real-jobs feed to be ready on dev
# the job list needs an account now: one test sign-up on dev (test mode signs it in at once), and its cookie for the count
curl -s -c "$TMP/dv.jar" -o /dev/null -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:18767' -d '{"email":"runner.feeds@example.com","password":"Runner-feeds-pw9","first":"Run","last":"Ner","agree":true}' http://127.0.0.1:18767/api/auth/signup
for _ in $(seq 1 120); do n=$(curl -s -b "$TMP/dv.jar" http://127.0.0.1:18767/api/jobs | python -c "import sys,json; print(len(json.load(sys.stdin)['jobs']))" 2>/dev/null); [ "${n:-0}" -gt 100 ] && break; sleep 1; done
echo "  real postings on dev: ${n:-0}"

step "Job feed rules (US-only, no foreign roles, classification)"
run "job rules and descriptions" python tools/test-jobs.py
run "job ids never collide: 20,000 postings with forced pairs, none lost, the same ids after a restart" python tools/test-job-ids.py

step "Email codes that prove an email is real"
run "verification codes: expiry, tries, resends, gates" python tools/test-verify.py
run "sign-up v2: no password, an emailed code, the 18+ tick recorded; the sandbox only, dev unchanged" python tools/test-signup-flow.py 18791

step "Delivery to employers (email with resume, signed webhook, retries, opt-in only) and the Connect Gmail form"
run "delivery channels" python tools/test-delivery.py
run "Connect Gmail form" python tools/test-setup.py

step "Swipe-right emails (content, test label, safety, real send)"
run "receipt and owner copy emails" python tools/test-emails.py
run "email as the mail service sees it: headers, daily quota (250/300), refusals, held mail, bounce webhook" python tools/test-mail-limits.py 0 18799
run "help requests from the assistant reach the support inbox" python tools/test-support.py
run "the sign-in contract: password sign-up with names, the code to verify and to sign in, the gate, the test mode, items 12 to 23" python tools/test-signin-contract.py 18964
run "the consent record: the box's words are the server's, kept on the account with the time, the address and their SHA-256; nothing is sent without it" python tools/test-consent.py 18970
run "apply by email: only a posting's own \"send your resume to\" address at the employer's domain; reply-to, receipt, limits, the stop link, bounces, test mode" python tools/test-email-route.py 18973
run "the outreach queue: who to invite each week, and it can never send" python tools/test-outreach-queue.py
run "Recruitee: a swipe right through the careers site's own apply endpoint, the switch, the consent record, Send applications for me" python tools/test-recruitee.py
run "the employer connect page: from the outreach link to Connected in under two minutes, then the next swipe arrives in their system" python tools/ui-connect.py
run "the Help chat sends to the AI only after the person said Continue (checked on the server)" python tools/test-chat.py
run "applications go straight into employers' hiring systems (Greenhouse, Lever)" python tools/test-ats.py
run "applications go straight into an employer's Ashby" python tools/test-ats-ashby.py
run "applications go straight into an employer's SmartRecruiters" python tools/test-ats-smartrecruiters.py
run "applications go straight into an employer's Workable" python tools/test-ats-workable.py
run "swipe right to apply instantly, end to end" python tools/test-ats-flow.py
run "paid plans: Stripe checkout, signed webhook, limits" python tools/test-billing.py
run "the public address (UAPLY_PUBLIC_URL): 301 to uaply.net for pages only, never /api/ or /healthz, canonical links, sitemap, plans hidden" python tools/test-public-url.py 18820
run "Stripe Checkout form filler of ui-live.js: card fields inside another site's iframe, Save my info, a decline, test cards only" node tools/cdp.js tools/ui-stripe-form.js
run "autofill: real employers' forms answered from the profile, questions asked once" python tools/test-autofill.py
run "Hiring mode: company, postings, feed, applicants (sandbox only)" python tools/test-employers.py
run "job feeds: USAJOBS, City of Philadelphia, keys, feeds_off, via credit" python tools/test-feeds.py 18784
run "swipe learning: the math, the worked example, the replay test" python tools/test-learn.py
run "fill from your resume: six resumes, layouts, dates, refused files, the endpoint" python tools/test-resume.py 18798
run "the server as Render runs it: start, stop mid-request, restart on the same disk" python tools/test-render.py 18782
run "the owner's self-check in /api/status: last job board read, last email sent, disk room, warnings; owner only" python tools/test-self-check.py 18960
run "reading every job board stays under 110 MB, the first visitor never waits for every board, a redeploy answers from the saved list at once" python tools/test-feed-memory.py
run "job types per feed, the Job type filter, the Simplify / Pitt CSC lists" python tools/test-job-types.py 18840
run "the whole US with PA, NJ, DE first: places, the city table, CareerOneStop, the distance filter" python tools/test-tristate.py 18842
run "job quality: company names, education, graduate-only internships, part-time, slow feeds, the internship order" python tools/test-quality.py 18844
run "many sources: job-boards.json, per-source health, switching a failing board off, spread refreshes, find-boards" python tools/test-sources-health.py
run "employers' careers sites: sitemap, JobPosting data, robots.txt, human checks, the packed cache and saved list" python tools/test-career-pages.py
run "human checks on application pages: captchas and challenge pages found (never solved), robots.txt with * and $, the route label, no job removed" python tools/test-human-checks.py
run "where a job is: every US city, town and township with its state, the app using it for near you, every ZIP3 for home, co-ops first on careers sites" python tools/test-placement.py
run "a long-running local server: files added to shared/ are served without a restart, no escape from shared/, a stale-code header and log line (local only)" python tools/test-stale-server.py
run "backups: pack the data folder, restore it, refuse damaged ones, encrypt, upload to a private GitHub repository" python tools/test-backup.py 18806
# one size per line: each takes about four minutes on fresh servers, and run() stops any single check at ten
run "every path from swipe right to inbox, replayed in a browser (375x812)" env SIZES=375x812 python tools/ui-apply-paths.py
run "every path from swipe right to inbox, replayed in a browser (390x844)" env SIZES=390x844 python tools/ui-apply-paths.py
run "every path from swipe right to inbox, replayed in a browser (1280x800)" env SIZES=1280x800 python tools/ui-apply-paths.py
run "the swipe guarantee: resume to profile, then swipe right into Greenhouse, Lever, Ashby, SmartRecruiters, Workable, an email employer and a hand-off; a question box, a file it cannot ask, the weekly limit" python tools/test-swipe-e2e.py 18830
run "the one-time question box: every kind of question, phone and computer" python tools/ui-questions.py
mkdir -p "$TMP/tk"
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/tk" UAPLY_CONFIG_JSON='{"feeds":[],"smtp":{},"owner_copy":""}' start python serve.py 18846 sandbox --api)"
wait_port 18846
run "Job Tracker keeps every row: a reload 31 days later, 500 swipes, 1,000 passes and one more" env W=390 H=844 PORT=18846 node tools/cdp.js tools/ui-tracker-keep.js

step "Accounts, applying, reset and setup (back end)"
run "sandbox reset/setup/accounts" python tools/test-reset.py 18766
run "dev reset/setup/accounts" python tools/test-reset.py 18767

step "Screens in a real browser (iPhone size)"
run "dev: release checks, no test or developer content anywhere" env W=390 H=844 PORT=18767 node tools/cdp.js tools/ui-release.js
run "hosted copies (no server): Account, Plan, swipe right and help say it is a preview, never 'cannot reach'" env W=390 H=844 PREVIEW_PORT=18786 node tools/cdp.js tools/ui-preview.js
run "dev: every screen and button" env REL=1 PORT=18767 node tools/cdp.js tools/ui-sweep.js
run "dev: forgot password, emailed link, new password, change password" env PORT=18767 node tools/cdp.js tools/ui-reset.js
run "nothing is cut off at 320 to 430 px" env PORT=18767 node tools/ui-widths.js
run "sandbox: every screen and button" env PORT=18766 node tools/cdp.js tools/ui-sweep.js
run "dev: every way of swiping, and what each sends (LinkedIn, resume, one email)" env W=390 H=844 PORT=18767 node tools/cdp.js tools/ui-swipes.js
run "dev: the app copes when the server fails, goes offline or sends garbage" env W=390 H=844 PORT=18767 node tools/cdp.js tools/ui-errors.js
run "the installable website: Chrome can install it; its offline screen when the server is down, during a deploy (502) and offline, never for a slow page" node tools/cdp.js tools/ui-installable.js
run "dev: skill chips, the empty Add button and the file downloads" env W=390 H=844 PORT=18767 node tools/cdp.js tools/ui-effects.js
run "dev in the phone apps (a stand-in Capacitor): Android Back goes back one screen and leaves only on a second press; the export buttons share a file, or copy and say so" env W=390 H=844 PORT=18767 node tools/cdp.js tools/ui-native-back-export.js
run "sandbox in the phone apps: the same" env W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-native-back-export.js
run "sandbox: the first-application agreement shows once, swipes throw no error" env W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-consent-once.js
run "dev: the first-application agreement shows once, swipes throw no error" env W=390 H=844 PORT=18767 node tools/cdp.js tools/ui-consent-once.js
run "sandbox: every profile checklist item lands on its field" env W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-checklist.js
run "sandbox: hostile text in every form never runs, and the owner's inbox escapes it" env W=390 H=844 PORT=18770 node tools/cdp.js tools/ui-inject.js
run "dev: hostile text in every form never runs, and the owner's inbox escapes it" env W=390 H=844 PORT=18767 node tools/cdp.js tools/ui-inject.js
run "sandbox: the setup page's script runs, and Connect email switches between Brevo and Gmail" env PORT=18766 node tools/cdp.js tools/ui-setup.js
run "dev on a big iPhone (440x956): every menu item tapped by touch, nothing covers a button, 7 kinds of real swipes" env W=440 H=956 PORT=18767 node tools/cdp.js tools/ui-phone.js
run "dev on a small iPhone (375x667): the same" env W=375 H=667 PORT=18767 node tools/cdp.js tools/ui-phone.js
run "sandbox on a turned short phone (667x375): the same, and the Help button never lies over the sign-up card" env LANDSCAPE=1 W=667 H=375 PORT=18766 node tools/cdp.js tools/ui-phone.js
run "sandbox on a turned phone (844x390): the same" env LANDSCAPE=1 W=844 H=390 PORT=18766 node tools/cdp.js tools/ui-phone.js
for sz in 390x844 375x667 440x956 1280x800; do
  run "dev at ${sz}: Pass, Undo and Apply fully visible above the bottom bar on first open, after Agree and after a swipe" env W="${sz%x*}" H="${sz#*x}" PORT=18767 node tools/cdp.js tools/ui-buttons-bar.js
  run "sandbox at ${sz}: the same" env W="${sz%x*}" H="${sz#*x}" PORT=18766 node tools/cdp.js tools/ui-buttons-bar.js
done
run "sandbox: learns from swipes (remote first, explore card, reset)" env W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-learn.js
run "sandbox: always jobs (narrow filters still fill the deck, marked outside your filters; minimum match is a filter; the learner's match band; empty only when all swiped)" env W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-always-jobs.js
run "sandbox: fill from your resume (fills empty fields, keeps typed ones, Replace, errors, fits the phone)" env W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-resume.js
run "dev: the stranger-walk fixes (messages fit the phone, Save and continue, LinkedIn links, empty deck, restore, Sign in wording, a restarting server, help, rating)" env W=390 H=844 PORT=18767 CDP_LIMIT_MS=600000 node tools/cdp.js tools/ui-walk.js
run "dev on a laptop (1280x800): one centred column about 960 px wide, Account and Plan & billing in its middle" env W=1280 H=800 PORT=18767 CDP_LIMIT_MS=600000 node tools/cdp.js tools/ui-walk.js
for sz in 390x844 1280x800; do
  run "sandbox at ${sz}: the deck reads the job list a page at a time (200 at sign-in, the next near the end, each stack its own, no job twice, Job Tracker, a far shared job)" env W="${sz%x*}" H="${sz#*x}" PORT=18766 node tools/cdp.js tools/ui-deck-pages.js
done
run "dev: starts without waiting on the font site, and a reload before the job list arrives keeps every swipe" env W=390 H=844 PORT=18767 node tools/cdp.js tools/ui-boot.js
run "sandbox: the same" env W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-boot.js
for sz in 390x844 1280x800; do
  run "dev at ${sz}: a signed-out first visit leaves a clean console (no 4xx, no console error)" env W="${sz%x*}" H="${sz#*x}" PORT=18767 node tools/cdp.js tools/ui-clean-load.js
  run "sandbox at ${sz}: the same (Hiring mode asks for a company only with a session)" env W="${sz%x*}" H="${sz#*x}" PORT=18766 node tools/cdp.js tools/ui-clean-load.js
done
for sz in 390x844 1280x800; do
  run "sandbox at ${sz}: a student's target titles never empty a section (internships and co-ops never filtered by title; 'Showing all roles' with Filters)" env W="${sz%x*}" H="${sz#*x}" PORT=18766 node tools/cdp.js tools/ui-title-filter.js
done
for sz in 390x844 1280x720; do
  run "sandbox at ${sz}: Share this job (the card's icon and nothing else changed, the ?job= link, the friend's landing, a job no longer listed, the Not sent yet row)" env W="${sz%x*}" H="${sz#*x}" PORT=18766 node tools/cdp.js tools/ui-share.js
done
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/ph" UAPLY_PLANS_HIDDEN=1 UAPLY_CONFIG_JSON='{"feeds":[],"smtp":{},"owner_copy":""}' start python serve.py 18832 dev --api)"
wait_port 18832
run "a free-only launch (UAPLY_PLANS_HIDDEN=1): Plan & billing shows Free and coming soon, no Choose buttons; dev without it still offers them" env W=390 H=844 PORT=18832 SHOWN_PORT=18767 node tools/cdp.js tools/ui-plans-hidden.js
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/mv" UAPLY_PUBLIC_URL=https://uaply.test UAPLY_CONFIG_JSON='{"feeds":[],"smtp":{},"owner_copy":""}' start python serve.py 18833 dev --api)"
wait_port 18833
run "the old address's 'UAply has moved' page: straight on with nothing to keep, a backup first with a profile, Restore once on the new address" env W=390 H=844 PORT=18833 NEW_PORT=18767 node tools/cdp.js tools/ui-moved.js
run "sandbox: a bare ?signed_in=google link claims nothing; the privacy-shields notice only after a real Google round trip" env W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-signed-in-link.js

step "Google sign-in (against a stand-in Google)"
PIDS="$PIDS $(start python tools/mock-google.py 8790)"
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/g" UAPLY_CONFIG_JSON='{"google":{"client_id":"test.apps.googleusercontent.com","client_secret":"test-secret","auth_url":"http://127.0.0.1:8790/auth","token_url":"http://127.0.0.1:8790/token","certs_url":"http://127.0.0.1:8790/certs"}}' start python serve.py 18768 dev --api)"
wait_port 18768
run "Google sign-in, attacks and failures" python tools/test-google.py 18768
run "Continue with Google button: tokens, forged tokens, linking, cookies" python tools/test-google-token.py 18768
run "sign-up and email-code screens in a browser, Google button area" env W=390 H=844 PORT=18768 node tools/cdp.js tools/ui-verify.js
run "Continue with Google on an iPhone (full-page sign-in), and hidden inside the phone apps" env W=390 H=844 PORT=18768 MOCK_GOOGLE_PORT=8790 node tools/cdp.js tools/ui-google-ios.js
# sign-up v2 in a browser: a sandbox with the stand-in Google and the test inbox (each run sends a few codes, so it gets its own server)
mkdir -p "$TMP/sg"
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/sg" UAPLY_CONFIG_JSON='{"delivery":"test","smtp":{},"feeds":[],"owner_copy":"","google":{"client_id":"test.apps.googleusercontent.com","client_secret":"test-secret","auth_url":"http://127.0.0.1:8790/auth","token_url":"http://127.0.0.1:8790/token","certs_url":"http://127.0.0.1:8790/certs"}}' start python serve.py 18769 sandbox --api)"
wait_port 18769
run "sandbox sign-up card on a laptop (1280x720): the order, the password box, the code, the questions, sign-in by password and by code, Google, hostile text" env W=1280 H=720 PORT=18769 MOCK_GOOGLE_PORT=8790 CDP_LIMIT_MS=900000 node tools/cdp.js tools/ui-signup.js
# the phone run gets a server of its own (each run makes several accounts, and this computer may make 10 an hour)
mkdir -p "$TMP/sg2"
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/sg2" UAPLY_CONFIG_JSON='{"delivery":"test","smtp":{},"feeds":[],"owner_copy":"","google":{"client_id":"test.apps.googleusercontent.com","client_secret":"test-secret","auth_url":"http://127.0.0.1:8790/auth","token_url":"http://127.0.0.1:8790/token","certs_url":"http://127.0.0.1:8790/certs"}}' start python serve.py 18847 sandbox --api)"
wait_port 18847
run "sandbox sign-up card on a phone (390x844): 16 px gutters and the same flow" env W=390 H=844 PORT=18847 MOCK_GOOGLE_PORT=8790 CDP_LIMIT_MS=900000 node tools/cdp.js tools/ui-signup.js
# the sign-in gate (October 22, Saif): signed out, only the card; nothing behind it by scrolling, keys, #hash or the app's own buttons
mkdir -p "$TMP/gate"
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/gate" UAPLY_SIGNUP_TEST=1 UAPLY_CONFIG_JSON='{"delivery":"test","smtp":{},"feeds":[],"owner_copy":""}' start python serve.py 18848 sandbox --api)"
wait_port 18848
run "the sign-in gate on a phone (390x844): only the card, its links open, sign-up to the questions, Sign out brings it back" env W=390 H=844 PORT=18848 node tools/cdp.js tools/ui-gate.js
run "the sign-in gate on a laptop (1280x800): the same" env W=1280 H=800 PORT=18848 node tools/cdp.js tools/ui-gate.js
run "pay as the posting gives it (390x844): yearly per year, hourly per hour, none Pay not listed; on the card, Job Tracker, Share rows and the receipt" env W=390 H=844 PORT=18848 node tools/cdp.js tools/ui-pay.js
run "pay as the posting gives it on a laptop (1280x800): the same" env W=1280 H=800 PORT=18848 node tools/cdp.js tools/ui-pay.js
run "one pay question, per year or per hour (390x844): step 3 asks it once, kept across a reload, step 5 asks no second one, hourly and yearly matched on one scale" env W=390 H=844 PORT=18848 node tools/cdp.js tools/ui-pay-unit.js
run "one pay question on a laptop (1280x800): the same" env W=1280 H=800 PORT=18848 node tools/cdp.js tools/ui-pay-unit.js
run "Profile setup asks each thing once (390x844): no step-5 relocate or office question (from Work style), Summary, Location and pay, one resume picker up to 1 MB, the sign-up agreement in Data & privacy, the message in a cover letter box" env W=390 H=844 PORT=18848 node tools/cdp.js tools/ui-profile-polish.js
run "Profile setup asks each thing once on a laptop (1280x800): the same" env W=1280 H=800 PORT=18848 node tools/cdp.js tools/ui-profile-polish.js

step "Public server behind HTTPS (how a real host runs it)"
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/pub" HOST=0.0.0.0 OWNER_PASSWORD=ownerpw UAPLY_CONFIG_JSON='{}' start python serve.py 18772 dev --api)"
wait_port 18772
run "cookies, headers, owner pages, path traversal, limits" python tools/test-public.py 18772
run "sign-in as the live site runs it (uaply.net, www, onrender.com): cookies, same-site check, Google tokens and linking, restart, lock-out, codes" python tools/test-public-auth.py 18780
run "one address, one account: letter case, look-alikes, races, Google linking, delete and sign up again, throwaway and dead domains, the audit tool" python tools/test-accounts.py 18800

step "Real email sending (against a stand-in mail server)"
PIDS="$PIDS $(start python tools/fake-smtp.py 12525 "$TMP/smtp/mail.jsonl")"
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/smtp" HOST=0.0.0.0 OWNER_PASSWORD=ownerpw UAPLY_CONFIG_JSON='{"smtp":{"host":"127.0.0.1","port":12525,"starttls":false,"from_addr":"uaply@example.com"},"owner_copy":"owner@example.com"}' start python serve.py 18773 dev --api)"
wait_port 18773
run "password reset email, link, single use, no stored link" python tools/test-smtp.py 18773 "$TMP/smtp/mail.jsonl"

step "A burst of visitors (300 at once, sign-ups, a password-guessing attack)"
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/stress" UAPLY_CONFIG_JSON='{"feeds":[],"smtp":{},"owner_copy":""}' start python serve.py 18774 dev --api)"
wait_port 18774
run "simultaneous reads, sign-ups and wrong passwords: no errors, lock-out holds" python tools/stress.py 18774

step "Hostile input (every endpoint, wrong types, injection strings, odd headers)"
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/fuzz" HOST=0.0.0.0 OWNER_PASSWORD=ownerpw UAPLY_CONFIG_JSON='{"feeds":[],"smtp":{},"owner_copy":""}' start python serve.py 18775 dev --api)"
wait_port 18775
run "no crash, hang or leaked error text across every endpoint" python tools/fuzz-api.py 18775

step "The after-deploy checks (live-check.py, ui-live.js), against local servers only: this suite never touches the live site"
# one server with everything off (as the live site was before the owner's keys) and one with email, Google and payments on through stand-ins
LP="${LIVE_CHECK_PORT:-18810}"                 # uses LP to LP+4
mkdir -p "$TMP/lc-off" "$TMP/lc-on"
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/lc-off" HOST=0.0.0.0 OWNER_PASSWORD=ownerpw UAPLY_CONFIG_JSON="$FEEDS" start python serve.py "$LP" dev --api)"
PIDS="$PIDS $(start python tools/mock-google.py $((LP+2)))"
PIDS="$PIDS $(start python tools/fake-smtp.py $((LP+3)) "$TMP/lc-on/mail.jsonl")"
PIDS="$PIDS $(start python tools/mock-stripe.py $((LP+4)))"
LC_ON='{"feeds":["greenhouse","lever","ashby"],"delivery":"test","owner_copy":"","anthropic_api_key":"","smtp":{"host":"127.0.0.1","port":'$((LP+3))',"starttls":false,"from_addr":"uaply@example.com"},"google":{"client_id":"test.apps.googleusercontent.com","client_secret":"test-secret","auth_url":"http://127.0.0.1:'$((LP+2))'/auth","token_url":"http://127.0.0.1:'$((LP+2))'/token","certs_url":"http://127.0.0.1:'$((LP+2))'/certs"}}'
PIDS="$PIDS $(UAPLY_DATA_DIR="$TMP/lc-on" HOST=0.0.0.0 OWNER_PASSWORD=ownerpw UAPLY_STRIPE_BASE="http://127.0.0.1:$((LP+4))" STRIPE_SECRET_KEY=sk_test_mockkey123456 STRIPE_WEBHOOK_SECRET=whsec_testsecret STRIPE_PRICE_PLUS=price_plus1 STRIPE_PRICE_PRO=price_pro1 UAPLY_CONFIG_JSON="$LC_ON" start python serve.py $((LP+1)) dev --api)"
wait_port "$LP" && wait_port $((LP+1))
# the job list needs an account now and these two are public (no test mode): the owner's feed health counts the postings instead
fh() { curl -s -u owner:ownerpw "http://127.0.0.1:$1/api/feed-health" | python -c "import sys,json; print(sum(s.get('jobs',0) for s in json.load(sys.stdin)['sources']))" 2>/dev/null; }
for _ in $(seq 1 120); do n=$(fh "$LP"); m=$(fh $((LP+1))); [ "${n:-0}" -gt 100 ] && [ "${m:-0}" -gt 100 ] && break; sleep 1; done
run "live-check.py, everything off: every PASS/FAIL/SKIP line as the live site gets it" python tools/live-check.py --base "http://127.0.0.1:$LP"
run "live-check.py, email, Google and payments on (stand-ins), all of them required" python tools/live-check.py --base "http://127.0.0.1:$((LP+1))" --expect email,google,payments --google-host "127.0.0.1:$((LP+2))"
run "ui-live.js, everything off: agreement, Got it, a swipe, Account says email is off, no Google, early access, help" node tools/cdp.js tools/ui-live.js --base "http://127.0.0.1:$LP"
run "ui-live.js, all on: Google button and redirect, buy buttons, sign-up by email code, Applied list" node tools/cdp.js tools/ui-live.js --base "http://127.0.0.1:$((LP+1))" --google-host "127.0.0.1:$((LP+2))" --email live.check+one@example.com --code-file "$TMP/lc-on/mail.jsonl"

printf "\n"
if [ "$FAILS" -eq 0 ]; then echo "ALL TESTS PASSED"; else echo "$FAILS test group(s) FAILED"; fi
exit "$FAILS"
