# Closed test: 12 testers for 14 days

Google requires a new **personal** developer account to run a closed test with **at least 12 testers who stay opted in for 14 days in a
row** before it can apply for production. Testers who leave early do not count, and rejoining restarts their 14 days. Aim for 15 or more
so a few dropping out does not reset the clock. Google may also ask for more testing if testers barely use the app.

## Owner steps (Play Console)
1. **Test and release > Testing > Closed testing > Create track** (name it `UAply testers`), upload `app-release-bundle.aab`
   (`mobile/twa/README.md`), fill in the release notes below, and roll it out to the track.
2. **Testers** tab: create an email list `UAply testers` and add each tester's **Google account** email (the one signed in to the Play
   Store on their Android phone). Save, then copy the **opt-in link** ("Join on Android").
3. Send each tester the invite below with that link. Keep a list of who opted in and on which date.
4. Day 14 after the 12th tester opted in: **Dashboard > Apply for production**, answer Google's questions about the test (what was
   tested, what testers reported, what changed), then send the production release for review (usually 7 days or less).

## Release notes for the test track (500 characters max)
```
First test of UAply on Android. Swipe through real jobs, apply at connected employers, and track every application. Please use it on a few different days and tell us what is confusing or broken: Help, then Report a problem.
```

## Invite (email or message)
```
Subject: Help test UAply on Android (2 minutes, 14 days)

Hi,

UAply is a job app: you swipe right to apply to real jobs that match your profile. It is free and has no ads. Before it can go on the
Play Store, Google needs 12 people to test it for 14 days, and I would be grateful if you were one of them.

1. On your Android phone, open this link while signed in to the Google account you use for the Play Store:
   [OPT-IN LINK]
2. Tap "Become a tester", then "Download it on Google Play", and install UAply.
3. Please stay in the test for at least 14 days (do not leave the test or uninstall), and open UAply on a few different days:
   swipe through some jobs, set up your profile, look at the Dashboard. You do not have to apply to anything.
4. If something is confusing or broken, tap Help in the app, then Report a problem, or reply to this email.

Your test copy may update by itself during the 14 days. Nothing you do in the test is shown publicly.

Thank you!
```

## Reminder on day 7 (optional)
```
Thanks for testing UAply! We are halfway through the 14 days. If you can, open it once or twice this week, and please do not leave the
test yet. Anything confusing? Help, then Report a problem, or just reply here.
```
