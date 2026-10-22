# Data safety form (Play Console > Policy > App content > Data safety)

Answers for the UAply Android app (the Trusted Web Activity of uaply.net), checked against `legal/privacy.html` (October 16, 2026) and the
code on October 21, 2026; the account answers updated on October 23 for the sign-in gate (nobody reaches anything without an account). Google counts data as **collected** when it leaves the device to UAply's server, and as **shared** when it goes
to another company. Data kept only on the phone (the street address, voluntary self-identification, device location, the resume file
between applications) is **not collected**. Re-check this table whenever `legal/privacy.html` changes, and before paid plans open. The code line behind each answer: `docs/store/data-safety-google.md`.

## Overview questions

| Question | Answer |
|---|---|
| Does your app collect or share any of the required user data types? | **Yes** |
| Is all of the user data collected by your app encrypted in transit? | **Yes** (HTTPS only; HSTS on uaply.net) |
| Which of the following methods of account creation does your app support? | **Username and password** (email and password, with a 6-digit email code) and **OAuth** (Continue with Google). An account is required: with the sign-in gate, the sign-up card is the first screen and nothing else opens without an account |
| Do you provide a way for users to request that their data is deleted? | **Yes** |
| Delete account URL | **https://uaply.net/legal/delete-account.html** |
| Do you allow users to request deletion of some or all data without deleting their account? | **Yes**: on the device, Profile > Data & privacy > Delete all my data; on the server, by email (support address on the deletion page) |
| Has your app undergone an independent security review (MASA)? | **No** |
| Is your app's data collection and sharing compliant with the Families Policy? | Not applicable (the app is 18+, not for children) |

## Data types

"Shared" is answered **Yes** for what an application sends to the employer the person applies to. Google's exemption for transfers the
user starts and expects could apply, but disclosing it is the safer answer and matches the Privacy Policy. Service providers (hosting,
email delivery, Anthropic for the help assistant's AI answers, Stripe once paid plans open) act for UAply and are not "sharing" under Google's rules.

| Category | Data type | Collected | Shared | Ephemeral | Required or optional | Purposes | Where it comes from |
|---|---|---|---|---|---|---|---|
| Personal info | Name | Yes | Yes, with employers you apply to | No | Required to apply | App functionality | Profile setup; sent with each application |
| Personal info | Email address | Yes | Yes, with employers you apply to | No | Required to apply; required for an account | App functionality, Account management, Developer communications (receipts, codes) | Profile; account sign-up; Google sign-in |
| Personal info | User IDs | Yes | No | No | Required (every user has an account) | Account management | The account number, and the Google account number if Continue with Google is used |
| Personal info | Address | Yes | Yes, with employers you apply to | No | Optional | App functionality | State, ZIP code and country only, sent with applications to fill the employer's form. The street stays on the device |
| Personal info | Phone number | Yes | Yes, with employers you apply to | No | Optional | App functionality | Profile setup |
| Personal info | Race and ethnicity | **No** | No | | | | Voluntary self-identification stays on the device and is never sent |
| Personal info | Other info | Yes | Yes, with employers you apply to | No | Optional | App functionality | Title, experience, skills, education, school, major, GPA, recent employer, headline, summary, links, work authorization and sponsorship answers, start date, answers to an employer's form questions |
| Financial info | Purchase history | **No** at launch | No | | | | Paid plans are hidden (free during early access) and the app shows no buy buttons. When paid plans open: Yes, collected, not shared (Stripe is a service provider), App functionality |
| Financial info | Credit or debit card numbers | **No** | No | | | | Typed only on Stripe's own page; UAply never receives them |
| Location | Approximate location / Precise location | **No** | No | | | | Device location (if the person allows it) is rounded to about a mile and used only on the device for the distance filter |
| Messages | Other in-app messages | Yes | No | No | Optional | App functionality, Developer communications | Help requests, problem reports and "Talk to a person" messages to the UAply team |
| App activity | App interactions | Yes | No | No | Required | App functionality, Analytics | Swipes: the listing, direction and match score with a random session ID |
| App activity | Other user-generated content | Yes | No | Yes (help questions) | Optional | App functionality | What is typed into the help assistant (not kept; sent to Anthropic only when AI answers are on); exit-survey answers (anonymous) |
| App activity | In-app search history / Installed apps / Other actions | No | | | | | |
| Files and docs | Files and docs | Yes | Yes, with employers you apply to | Yes | Optional | App functionality | The resume file goes with each application and on to the employer; the server keeps only its name and size. (If Fill from your resume, a sandbox feature today, ships: the file is also read on the server for a moment and not kept) |
| App info and performance | Crash logs / Diagnostics | No | | | | | The server logs request paths and error reasons without names or IPs on the public host; no crash or analytics SDK |
| Device or other IDs | Device or other IDs | Yes | No | No | Required | Analytics | The random session ID stored in the app (not an advertising ID, not linked to the person) |
| Web browsing, Contacts, Calendar, Photos and videos, Audio, Health and fitness | | No | | | | | Calendar export writes a file on the device; nothing is read from the calendar |

## Notes for whoever fills it in
- Sign-in cookie: one first-party session cookie; no advertising ID, no advertising or tracking SDK, no ads.
- If Hiring mode (employers) ever ships in the release build, add: company details and job posts (Other user-generated content, shared publicly on job cards).
- If paid plans open: switch Purchase history to collected (App functionality), and review the full form again.
