# Google Play listing pack

Everything the Play Console asks for, in the order you meet it, and the file that fills each screen. The app itself is built from
`mobile/twa/` (owner steps in `mobile/twa/README.md`); the ten steps from account to production are in `docs/play-store.md`.

Pictures are made by `node tools/cdp.js tools/make-play-assets.js` (example jobs and an example person, the release build's features
only) and checked by `python tools/test-play-listing.py` (exact pixel sizes, formats, text lengths). Run both again whenever the screens change.

## Checklist: Play Console screen -> file

| Console screen | Field | File | Rule (checked by the test) |
|---|---|---|---|
| Create app | App name | `text/app-name.txt` | 30 characters max |
| Create app | Default language / App or game / Free or paid | English (United States) / App / **Free** | |
| Grow > Store presence > Main store listing | App name | `text/app-name.txt` | 30 max |
| Main store listing | Short description | `text/short-description.txt` | 80 max |
| Main store listing | Full description | `text/full-description.txt` | 4000 max |
| Main store listing | App icon | `icon-512.png` | 512 x 512 PNG, 1 MB max |
| Main store listing | Feature graphic | `feature-graphic.png` | 1024 x 500, PNG without transparency |
| Main store listing | Phone screenshots (2 to 8) | `screenshots/phone/1-sign-up.png` (the sign-up card, the first screen), then `2-jobs.png` ... `6-help.png` after an example sign-up | 1080 x 1920 (9:16), no transparency |
| Main store listing | 7-inch tablet screenshots | `screenshots/tablet/1-sign-up.png` ... `6-help.png` | 1080 x 1920 (9:16), no transparency |
| Main store listing | 10-inch tablet screenshots | the same tablet files (optional) | |
| Store settings | Category, contact email, website | `app-content.md`, "Store settings" | |
| Policy > App content > Privacy policy | URL | https://uaply.net/legal/privacy.html (`app-content.md`) | |
| App content > Ads | | `app-content.md`: no ads | |
| App content > App access | Reviewer instructions, demo account | `app-content.md` | |
| App content > Content rating | IARC questionnaire | `content-rating.md` | |
| App content > Target audience | 18 and over | `app-content.md` | |
| App content > Data safety | Every question, deletion URL | `data-safety.md` (https://uaply.net/legal/delete-account.html) | |
| App content > News, COVID-19, Government, Financial, Health, Advertising ID | | `app-content.md`: none apply | |
| Test and release > Setup > App signing | Play App Signing on | `mobile/twa/README.md`, step 4 | |
| Test and release > Testing > Internal testing | The first upload: up to 100 testers by email, available within minutes | `testers.md` | |
| Test and release > Testing > Closed testing | Track, testers, release notes, invite | `testers.md` | release notes 500 max |
| Production | Countries | United States (`app-content.md`) | |

## Before you submit
- The Privacy Policy and Terms have highlighted blanks (company name, launch date, privacy email): fill them first; a reviewer opens the link.
- `UAPLY_ASSETLINKS_SHA256` is set on Render with both fingerprints and https://uaply.net/.well-known/assetlinks.json shows them.
- Paid plans stay hidden (`UAPLY_PLANS_HIDDEN=1`) so the app shows no buy buttons (Google Play's payments policy).
- The screenshots show UAply's built-in example listings (each card says "Example listing, not a real opening") so no employer's
  posting is pictured without asking. That is honest as it is; pictures of real postings can replace them later if you prefer.
