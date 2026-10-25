# App Review information (App Store Connect > the version > App Review Information)

Paste the "Notes" block below into the Notes field. Fill the sign-in fields with a demo account made for the reviewer on uaply.net
(never a real person's account, never the owner's). Do not commit the demo password here or anywhere in the repo.

| Field | Value |
|---|---|
| Sign-in required | **Yes** (the sign-up card is the first screen; nothing else opens without an account) |
| User name | `[DEMO ACCOUNT EMAIL: Saif fills in]` |
| Password | `[DEMO ACCOUNT PASSWORD: Saif fills in, in App Store Connect only]` |
| Contact | Saif Siddique, the support address on https://uaply.net/legal/ |

## Notes (paste as is, after filling the account fields)

UAply is a job search app: one job card at a time, swipe right to apply, swipe left to pass. A demo account is provided above; it is
already signed up, so it opens on the job cards.

What the app does natively on iPhone, beyond showing uaply.net:
1. Filled employer forms. For a job whose employer takes applications only on its own site, a swipe right opens the employer's
   application form inside the app, already filled in from the person's UAply profile (name, email, phone, links, work authorization,
   resume file), for the person to check and submit. UAply never answers voluntary self-identification questions and never completes
   a security check.
2. Share. Any job card can be shared with the iPhone share sheet (Share in the card's menu).
3. Exports. Job Tracker exports every application as a spreadsheet (CSV) and interview times as a calendar file (.ics), written to the
   phone and handed to the share sheet (Save to Files, Mail, Calendar).
4. Interview reminders as local notifications (asked for only when the person adds an interview time), and light haptics on a swipe.
5. Its own offline screen: in airplane mode the app shows "You are offline" with a Retry button, and opens again by itself when the
   connection comes back.

Purchases: UAply is free during early access. The iPhone app sells nothing and shows no buy, upgrade or manage-billing buttons; the
plan screen says only "Plans are managed on uaply.net." (guideline 3.1.1).

Sign-in: email and password with a 6-digit code sent to the email. Continue with Google is hidden in the iPhone app (so Sign in with
Apple is not required, guideline 4.8). Accounts can be deleted in the app: Profile > Account > Delete my account (guideline 5.1.1(v)).

Age: 18 and older (the sign-up card asks the person to confirm it).

To look around without contacting a real employer, swipe left (pass), or tap Undo right after a swipe right.
