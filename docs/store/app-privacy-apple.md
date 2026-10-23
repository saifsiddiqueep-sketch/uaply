# App Store Connect: App Privacy, age rating and review questions, answered from the code

Every answer below rests on the line of code given next to it (`file:line`, in this repository, as of October 22, 2026; `node check.js`
fails if a cited file is gone or shorter than the line cited). The iPhone app is the Capacitor shell in `mobile/ios`, which opens
https://uaply.net (`mobile/capacitor.config.json:6`), so what the website collects is what the app collects. The Google answers are in
`docs/store/data-safety-google.md`. Anything the code cannot answer is at the bottom.

How Apple counts: data is **collected** when it leaves the device and is kept longer than needed to answer that request. **Linked to
the person** when it is kept with their name, email or account. **Tracking** means combining it with other companies' data for ads or
handing it to a data broker.

## The two opening questions
| Question | Answer | Rests on |
|---|---|---|
| Do you or your third-party partners collect data from this app? | **Yes** | Each application is stored with the profile in it: `uaply_api.py:1153` |
| Do you or your partners use data for tracking? | **No** | No ad or analytics SDK, no advertising id: the native app asks for nothing (`mobile/ios/App/App/Info.plist:5` has no usage strings and no tracking key); the server shares data only with the employer applied to |

## Data types (choose these in App Store Connect)
Purposes used: **App Functionality**, **Analytics**, **Customer Support**. Never Third-Party Advertising, Developer's Advertising or
Marketing, or Product Personalization (the "learns from your swipes" experiment is sandbox-only and works on the device:
`shared/uaply-learn.js:1`).

| Apple data type | Collected | Linked to the person | Tracking | Purposes | Rests on |
|---|---|---|---|---|---|
| Contact Info / **Name** | Yes | Yes | No | App Functionality | `uaply_api.py:1046`, kept in the record `uaply_api.py:1153`, required `uaply_api.py:328` |
| Contact Info / **Email Address** | Yes | Yes | No | App Functionality (account, codes, receipts, the employer's reply) | `uaply_api.py:1046`, `auth_api.py:91`, `uaply_api.py:902`, `mailer.py:5` |
| Contact Info / **Phone Number** | Yes (optional) | Yes | No | App Functionality | `uaply_api.py:226` |
| Contact Info / **Physical Address** | Yes, state, ZIP code and country only (optional) | Yes | No | App Functionality (fills the employer's form) | `uaply_api.py:255`, `uaply_api.py:256`; the street stays on the device `shared/uaply-nav.js:1483` |
| Contact Info / Other User Contact Info | **No** | | | | Links (LinkedIn, portfolio) are counted under Other Data below |
| Health and Fitness | **No** | | | | |
| Financial Info / **Payment Info** | **No** | | | | Card numbers are typed only on Stripe's page: `billing_api.py:1` |
| Financial Info / Credit Info, Other Financial Info | **No** | | | | Expected pay is sent only when the employer's own form asks for it (`uaply_api.py:1145`); counted under Other Data |
| Location / **Precise** or **Coarse** | **No** | | | | Device location is rounded to about a mile and never leaves the device: `shared/uaply-nav.js:840` |
| **Sensitive Info** | **No** | | | | Voluntary self-identification (race, gender, veteran, disability) stays on the device: `shared/uaply-nav.js:1511`, `shared/uaply-nav.js:2544`; never answered by the server `autofill.py:21` |
| Contacts | **No** | | | | No contacts code or permission |
| User Content / Emails or Text Messages | **No** | | | | No messaging between users |
| User Content / Photos or Videos, Audio Data, Gameplay Content | **No** | | | | |
| User Content / **Customer Support** | Yes (optional) | Yes when signed in or an email is left for a reply | No | Customer Support | `chat_api.py:338`, stored `chat_api.py:389` |
| User Content / **Other User Content** | Yes (optional) | Yes (resume, form answers); No (exit survey) | No | App Functionality | The resume file goes with an application (`shared/uaply-live.js:253`, `uaply_api.py:407`); the server keeps its name and size only (`uaply_api.py:1153`). Answers to an employer's questions `uaply_api.py:1083`, kept `uaply_api.py:1159`. Exit survey kept without the account `chat_api.py:375` |
| Browsing History, Search History | **No** | | | | Search and filters run on the device |
| Identifiers / **User ID** | Yes (only with an account) | Yes | No | App Functionality | Account number `auth_api.py:91`; Google's account number `auth_api.py:112` (Google is hidden inside the iPhone app: `shared/uaply-nav.js:2147`) |
| Identifiers / **Device ID** | Yes | **No** | No | Analytics | The random `uaply.session` id made by the app (`shared/uaply-live.js:164`), sent with each swipe; not an advertising id, never stored with the account (`uaply_api.py:1274`) |
| Purchases / **Purchase History** | **Depends** (see questions): Yes, linked, App Functionality, if Plus and Pro show in the app | | No | App Functionality | Plan and Stripe ids on the account `auth_api.py:134`; hidden only with `UAPLY_PLANS_HIDDEN=1` `billing_api.py:87` |
| Usage Data / **Product Interaction** | Yes | **No** | No | Analytics, App Functionality | Each swipe: job, company, role, match score, session id: `shared/uaply-live.js:855`, stored `uaply_api.py:1274` |
| Usage Data / Advertising Data, Other Usage Data | **No** | | | | |
| Diagnostics / Crash Data, Performance Data, Other | **No** | | | | No crash SDK; the public server logs method, route, status and time only (`serve.py:608`) and no visitor addresses (`serve.py:1355`) |
| Surroundings, Body | **No** | | | | |
| **Other Data Types** | Yes (optional) | Yes | No | App Functionality | Job title, education, years, skills `uaply_api.py:1046`; headline, summary, links, school, major, graduation, GPA, recent employer, work authorization, sponsorship, start date, relocation, on-site, pronouns, "why us", expected pay `uaply_api.py:246` |

## Account deletion (App Review guideline 5.1.1(v))
- In the app: Profile, Account, More account options, Delete my account (`shared/uaply-nav.js:2235`); confirm with the password, or type
  DELETE when the account has none (`shared/uaply-nav.js:2255`, `auth_api.py:531`).
- The server removes the account, sessions, receipts, Google link, application records, help messages and held mail (`serve.py:1261`,
  `auth_api.py:542`, `uaply_api.py:1250`, `chat_api.py:393`, `mailer.py:378`). A paid plan is cancelled with Stripe first
  (`billing_api.py:236`).
- Without the app: https://uaply.net/legal/delete-account.html (`legal/delete-account.html:20`).

## Age rating questionnaire
UAply is for people 18 and over: `legal/terms.html:16`, sign-up `auth_api.py:439`, the first-swipe agreement `shared/uaply-live.js:365`,
the sign-up box `shared/uaply-nav.js:2278`. The content itself has nothing that raises a rating:

| Question | Answer | Rests on |
|---|---|---|
| Cartoon or fantasy violence; realistic violence; prolonged graphic or sadistic violence | **None** | Job listings and the person's own profile only |
| Profanity or crude humor; mature or suggestive themes; horror or fear themes | **None** | Same |
| Sexual content or nudity; graphic sexual content and nudity | **None** | Same |
| Alcohol, tobacco or drug use or references | **None** | Same (an employer's listing text is its own) |
| Medical or treatment information; health or wellness topics | **None** | |
| Simulated gambling; contests; real-money gambling | **None** / **No** | |
| Unrestricted web access | **No**, to be confirmed (see questions) | The app opens uaply.net (`mobile/capacitor.config.json:6`); a posting opens one employer page (`shared/uaply-live.js:61`) |
| User-generated content, or messaging and chat between users | **No** | Help messages go only to the UAply team (`chat_api.py:338`); Hiring mode is sandbox-only (`serve.py:36`) |
| Advertising | **No** | |
| Made for Kids | **No** | `legal/terms.html:16` |

The questionnaire will give the lowest rating. If App Store Connect offers choosing a higher rating than the calculated one, choose
**18+**; either way the app itself asks every person to confirm they are 18 or older before an account or a first application.

## Other questions App Store Connect asks
| Question | Answer | Rests on |
|---|---|---|
| Export compliance: uses non-exempt encryption? | **No** (HTTPS only) | `mobile/ios/App/App/Info.plist:23` (`ITSAppUsesNonExemptEncryption` false) |
| Sign-in for the reviewer | Needed for account features; swiping works signed out. Use an account the team makes for review (never committed) | `auth_api.py:91` |
| Sign in with Apple (guideline 4.8) | Not needed today: Continue with Google is hidden inside the iPhone app | `shared/uaply-nav.js:2147` |

## Questions only a person can answer
- **Paid plans inside the iPhone app (guideline 3.1.1).** Plus and Pro open Stripe Checkout, and nothing hides them in the iPhone app
  (only Google is hidden there, `shared/uaply-nav.js:2147`). Apple requires In-App Purchase for digital subscriptions, so either launch
  free-only (`UAPLY_PLANS_HIDDEN=1`, `billing_api.py:87`) or hide plans in the iPhone shell (a code change for another card) before
  submitting. This also decides Purchase History above.
- **Location inside the iPhone app.** "Use my location" calls the browser's geolocation (`shared/uaply-nav.js:850`), but `Info.plist`
  has no `NSLocationWhenInUseUsageDescription`, so iOS will not ask and the app falls back to the city. Add the string (and keep
  Location as "not collected", since it stays on the device) or accept the fallback.
- **Privacy manifest.** There is no `PrivacyInfo.xcprivacy` in `mobile/ios/App/App`. Check in Xcode whether the Capacitor version used
  ships its own, and add the app's one if App Store Connect asks.
- **Unrestricted web access.** Confirm on a phone that an employer's page opens outside the app (Safari) or as that one page, not a
  browser the person can type any address into.
- The privacy email (the highlighted `[privacy email]` blank on the Privacy Policy and the deletion page), the Apple Developer Program
  account, the review account, and pressing Submit.
