# Google Play: Data safety, account deletion, target age and content rating, answered from the code

Every answer below rests on the line of code given next to it (`file:line`, in this repository, as of October 22, 2026; `node check.js`
fails if a cited file is gone or shorter than the line cited). `mobile/store/play/data-safety.md` is the same form laid out the way the
Play Console shows it; this file is the evidence behind it. Where the two differ, this one was checked against the code last, and the
differences are listed at the end. Anything the code cannot answer is in "Questions only a person can answer" at the bottom.

How Google counts: data is **collected** when the app sends it off the device (here: to UAply's server), **shared** when it goes to
another company. Data that stays on the phone is not collected. Service providers working for UAply (the host, the email service,
Stripe, the AI provider) are not "sharing" under Google's rules.

Which app: the Play listing plan is the Trusted Web Activity of uaply.net (`mobile/twa/twa-manifest.json:3`), so the app is the website.
The older Capacitor app (`mobile/android`) adds **assisted apply** (it fills the employer's own form on the phone,
`mobile/android/app/src/main/AndroidManifest.xml:25`). If the Capacitor app is the one uploaded, read the "Assisted apply" notes in
the table too.

## Overview questions

| Question | Answer | Rests on |
|---|---|---|
| Does your app collect or share any of the required user data types? | **Yes** | Applications are stored on the server with the profile in them: `uaply_api.py:1153` |
| Is all of the user data collected by your app encrypted in transit? | **Yes** | The app only loads `https://uaply.net` (`mobile/twa/twa-manifest.json:3`, `mobile/capacitor.config.json:6`, `cleartext: false`); the server sends HSTS behind HTTPS (`serve.py:1352`) |
| Account creation methods | **Username and password** (email and password, the email proved with a 6-digit code) and **OAuth** (Continue with Google, on the website and the TWA; hidden inside the Capacitor shell, `shared/uaply-nav.js:2151`). An account is optional: swiping and applying work signed out | `auth_api.py:91` (users), `auth_api.py:112` (Google identities), `google_auth.py:145` (scope `openid email` only) |
| Do you provide a way for users to request that their data is deleted? | **Yes** | In the app: `shared/uaply-nav.js:2235`; server route `serve.py:1261` |
| Delete account URL | **https://uaply.net/legal/delete-account.html** | `legal/delete-account.html:6` |
| Can users ask for some data to be deleted without deleting the account? | **Yes**: on the device, Profile, Data and privacy, Delete all my data (`shared/uaply-nav.js:1937`); anything on the server by email (the deletion page) | `legal/delete-account.html:20` |
| Independent security review (MASA)? | **No** | Nothing in the repository |
| Families Policy | **Not applicable**: the app is for adults (18+) | `legal/terms.html:16`, `auth_api.py:439` |

## Data types

| Category / type | Collected | Shared | Ephemeral | Required? | Purposes | Rests on |
|---|---|---|---|---|---|---|
| Personal info / **Name** | Yes | Yes, with the employer applied to (only employers who agreed to receive applications) | No | Required to apply | App functionality | `uaply_api.py:1046` (kept in the application record, `uaply_api.py:1153`); minimum to apply `uaply_api.py:328` |
| Personal info / **Email address** | Yes | Yes, with the employer applied to | No | Required to apply and for an account | App functionality, Account management, Developer communications (codes, receipts, reminders) | `uaply_api.py:1046`, `auth_api.py:91`, receipts `uaply_api.py:902`, mail kinds `mailer.py:5` |
| Personal info / **User IDs** | Yes | No | No | Optional (only with an account) | Account management | Account number `auth_api.py:91`; Google's account number `auth_api.py:112` |
| Personal info / **Address** | Yes: state, ZIP code and country only | Yes, with the employer applied to | No | Optional | App functionality (fills the employer's form) | `uaply_api.py:255` (zip, state, country). The street stays on the device: `shared/uaply-nav.js:1483`. **Assisted apply (Capacitor app only):** the street is typed into the employer's own page on the phone (`shared/uaply-nav.js:1831`), see the questions below |
| Personal info / **Phone number** | Yes | Yes, with the employer applied to | No | Optional (a phone or a resume is needed to apply) | App functionality | `uaply_api.py:226`, `uaply_api.py:328` |
| Personal info / **Race and ethnicity**, **Sexual orientation**, **Other info: gender, veteran, disability** | **No** | No | | | | Voluntary self-identification is kept on the device and never sent: `shared/uaply-nav.js:1511`, `shared/uaply-nav.js:2544`, assisted apply skips it `shared/uaply-nav.js:1811`, the server never answers it `autofill.py:21` |
| Personal info / **Other info** | Yes | Yes, with the employer applied to | No | Optional | App functionality | Title, location, education, years, skills `uaply_api.py:1046`; headline, summary, links, school, major, graduation, GPA, recent employer and dates, work authorization, sponsorship, start date, relocation, on-site, pronouns, "why us" `uaply_api.py:246`; answers to an employer's form questions `uaply_api.py:1083` (kept in the record `uaply_api.py:1159`). Expected pay only when that employer's form asks: `uaply_api.py:1145` |
| Financial info / **Purchase history** | **Depends on a person's decision** (see questions). If Plus and Pro are shown: Yes, not shared (Stripe is a service provider), App functionality, Optional | No | No | Optional | App functionality | Plan, Stripe customer and subscription ids on the account: `auth_api.py:134`; plans hidden only when `UAPLY_PLANS_HIDDEN=1`: `billing_api.py:87` |
| Financial info / **Credit or debit card numbers** | **No** | No | | | | Typed only on Stripe's own page: `billing_api.py:1` |
| Location / **Approximate** or **Precise** | **No** | No | | | | Device location is rounded to about a mile and stays on the device: `shared/uaply-nav.js:840`, stored only in local storage `shared/uaply-nav.js:844` |
| Messages / **Other in-app messages** | Yes | No | No | Optional | App functionality, Developer communications | Help requests, problem reports and "Talk to a person": `chat_api.py:338` (stored `chat_api.py:389`) |
| App activity / **App interactions** | Yes | No | No | Required (sent with every swipe while the server is reachable) | App functionality, Analytics | Swipe direction, job, company, role, match score and a random session id: `shared/uaply-live.js:855`, stored `uaply_api.py:1274` |
| App activity / **Other user-generated content** | Yes | No | Yes (help questions) | Optional | App functionality | Questions typed into the help assistant are not stored (`chat_api.py:13`); they reach the AI provider only when AI answers are on and the person agreed (`shared/uaply-chat.js:173`, `chat_api.py:198`). Exit-survey answers are stored without the account: `chat_api.py:375` |
| Files and docs / **Files and docs** | Yes | Yes, with the employer applied to | Yes | Optional | App functionality | The resume file goes with an application (`shared/uaply-live.js:253`, checked `uaply_api.py:407`, delivered `uaply_api.py:530`); the record keeps only its name, size and type (`uaply_api.py:1153`, `"resume": resume_meta`) |
| App info and performance / **Crash logs**, **Diagnostics** | **No** | | | | | No crash or analytics SDK (only `INTERNET` permission, `mobile/android/app/src/main/AndroidManifest.xml:42`). The public server logs method, route, status and time, never the address (`serve.py:608`, `serve.py:1355`) |
| Device or other IDs | Yes | No | No | Required | Analytics | The random `uaply.session` id made by the app (`shared/uaply-live.js:164`); not an advertising id and not tied to the account (`uaply_api.py:1274` stores no user) |
| Web browsing, Contacts, Calendar, Photos and videos, Audio, Health and fitness, In-app search history, Installed apps | **No** | | | | | No such permission or code: `mobile/android/app/src/main/AndroidManifest.xml:42`; notifications off `mobile/twa/twa-manifest.json:15` |

Also true, for the free-text boxes in the Console:
- Sign-in is one first-party session cookie (`serve.py:766`) plus a "known device" cookie after a code sign-in (`serve.py:774`). No
  advertising id, no ads, no tracking SDK.
- A signed-out swipe right still keeps an application record on the server, even when nothing is sent and the person is handed to the
  employer's page (`uaply_api.py:1171`). That is "collected", not "shared".
- Addresses that bounce are kept on a do-not-send list for up to a year (`mailer.py:29`, `mailer.py:53`), so the deleted account's
  address can stay on it.

## Account deletion (Data safety, "Delete account URL")
- **In the app:** Profile, Account, More account options, Delete my account (`shared/uaply-nav.js:2235`); password, or type DELETE when
  the account has no password (`shared/uaply-nav.js:2255`, `auth_api.py:531`).
- **What the server removes:** the account, its sessions, receipts, Google link and codes (`auth_api.py:542` with cascades from
  `auth_api.py:91`), its application records (`uaply_api.py:1250`), help messages sent while signed in (`chat_api.py:393`), mail still
  waiting to go (`mailer.py:378`). A paid plan is cancelled with Stripe first, or the account is kept and the person told why
  (`billing_api.py:236`). Route: `serve.py:1261`.
- **Without the app:** https://uaply.net/legal/delete-account.html (`legal/delete-account.html:20`), linked from the Privacy Policy
  (`legal/privacy.html:72`), Support (`legal/support.html:28`), the legal index (`legal/index.html:14`) and the help assistant's
  "Deleting my account or my data" answer (`help/articles.json`, article `delete`).

## Target audience and content (Policy, App content)
| Screen | Answer | Rests on |
|---|---|---|
| Target age group | **18 and over** only | `legal/terms.html:16`; sign-up `auth_api.py:439`; first swipe `shared/uaply-live.js:365`; sign-up box `shared/uaply-nav.js:2278` |
| Does the app appeal to children? | **No** | Job search for US adults: `legal/terms.html:16` |
| Ads | **No** | No ad SDK or ad code (`mobile/android/app/src/main/AndroidManifest.xml:42`) |
| Advertising ID | **No** | Same |
| News, COVID-19, Government, Financial features, Health | **No** to each | No such feature in the code; USAJOBS listings are public data |

## Content rating questionnaire (IARC)
Category **All Other App Types**. Every content question (violence, sexuality, profanity, drugs, gambling, fear) is **No**: the app shows
job listings written by employers and the person's own profile. The interaction questions:

| Question | Answer | Rests on |
|---|---|---|
| Users interact or exchange content with each other? | **No** | No messages between users in the release build; help messages go only to the UAply team (`chat_api.py:338`). Hiring mode (employers posting jobs) is sandbox-only (`serve.py:36`) |
| Shares the user's location with other users? | **No** | Location stays on the device: `shared/uaply-nav.js:840` |
| Digital purchases? | **No** if plans stay hidden; **Yes** if Plus and Pro are shown (see questions) | `billing_api.py:87` |
| Web browser or search engine? | **No** | It opens uaply.net (`mobile/twa/twa-manifest.json:3`); a posting opens the employer's one page |

Expected result: IARC 3+ / Everyone. That rating does not change who the app is for: Target audience sets **18 and over**, as the Terms
require. The full Console wording is in `mobile/store/play/content-rating.md`.

## Differences from `mobile/store/play/data-safety.md`
1. **Purchase history** there says "No at launch, paid plans are hidden". The code hides them only when `UAPLY_PLANS_HIDDEN=1` is set
   (`billing_api.py:87`); the handoff notes say payments are on (test mode) on the live site. Settle this before submitting.
2. **Address**: correct for the TWA. For the Capacitor app, assisted apply also puts the street into the employer's form on the phone
   (`shared/uaply-nav.js:1831`).
3. Nothing else differs.

## Questions only a person can answer
- Which Android build goes to Play: the TWA (recommended in `mobile/twa/README.md`) or the Capacitor app with assisted apply?
- Will Plus and Pro be visible at launch (`UAPLY_PLANS_HIDDEN` on Render)? That decides Purchase history and the digital-purchases answer.
- The privacy email for the deletion page and the Privacy Policy (the highlighted blank `[privacy email]`; the legal-blanks task).
- The Play Console account, the reviewer's demo account, and pressing Submit.
