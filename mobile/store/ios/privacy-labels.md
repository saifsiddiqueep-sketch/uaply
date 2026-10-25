# App Privacy answers (App Store Connect > App Privacy)

Drafted from `legal/privacy.html` (last updated October 23, 2026) and `../play/data-safety.md` on October 25, 2026. Apple counts data
as **collected** when it leaves the device to UAply's server or a partner; data kept only on the phone (street address, voluntary
self-identification, device location, the resume file between applications) is **not collected**. Re-check whenever
`legal/privacy.html` changes, before paid plans open, and if Hiring mode ships in the release build. Saif reviews before submitting.

## First answers

| Question | Answer |
|---|---|
| Do you or your third-party partners collect data from this app? | **Yes** |
| Tracking (linked with other companies' data for advertising, or shared with data brokers)? | **No**. No ads, no tracking SDK, no advertising ID, so no App Tracking Transparency prompt |
| Privacy Policy URL | https://uaply.net/legal/privacy.html |
| Account deletion | In the app: Profile > Account > Delete my account; also https://uaply.net/legal/delete-account.html |

## Data types (each one: **Linked to the user: Yes**, **Used for tracking: No**)

| Apple category | Data type | Purposes | What it is |
|---|---|---|---|
| Contact Info | Name | App Functionality | Sent with each application to the employer applied to |
| Contact Info | Email Address | App Functionality, Developer's Communications | Account sign-in, the 6-digit code, receipts; sent with applications |
| Contact Info | Phone Number | App Functionality | Optional; sent with applications |
| Contact Info | Physical Address | App Functionality | State, ZIP code and country only (the street stays on the phone), to fill the employer's form |
| Contact Info | Other User Contact Info | App Functionality | LinkedIn and portfolio links |
| User Content | Other User Content | App Functionality | Profile details (title, skills, education, employer, headline, summary), answers to employers' form questions, the optional message to the employer, the resume file (sent with each application; the server keeps only its name and size) |
| User Content | Customer Support | App Functionality | Help requests, problem reports, Talk to a person messages, feedback, help assistant questions (sent to Anthropic only when AI answers are on, and not kept) |
| Identifiers | User ID | App Functionality | The account number (and the Google account number for accounts made with Google on the website) |
| Usage Data | Product Interaction | App Functionality, Analytics | Swipes (the listing, direction and match score) with a random session ID |
| Sensitive Info | Sensitive Info | App Functionality | Work authorization and sponsorship answers (optional), only to include in applications |
| Other Data | Other Data Types | App Functionality | The agreement record (version, time, internet address, fingerprint of the words) |

## Not collected

Location (device location is rounded and used only on the phone, for distance), Health and Fitness, Financial Info (free in early
access; card numbers are typed only on Stripe's page on the website, never in the app), Contacts, Browsing History, Search History,
Diagnostics (no crash or analytics SDK), Purchases (when paid plans open: Purchase History, App Functionality, linked, no tracking).
Voluntary self-identification (race, gender, veteran status, disability) stays on the phone and is never sent.

## Notes
- Exit survey answers are saved without name, email or account ID: list them under Other User Content as **Not linked**.
- If Hiring mode ships: add company details and job posts (Other User Content, linked, App Functionality).
