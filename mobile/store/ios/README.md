# App Store listing pack (iPhone)

What App Store Connect asks for, and the file that fills it. The app is the Capacitor wrapper in `mobile/ios/` (the same site as
uaply.net); `codemagic.yaml` builds it (its App Store Connect settings wait for Saif's Apple ID number).

| App Store Connect field | File | Limit |
|---|---|---|
| Name | `text/name.txt` | 30 characters |
| Subtitle | `text/subtitle.txt` | 30 characters |
| Promotional text | `text/promotional-text.txt` | 170 characters |
| Description | `text/description.txt` | 4000 characters |
| Keywords | `text/keywords.txt` | 100 characters, comma-separated |
| Screenshots, iPhone 6.9-inch | `screenshots/6.9/1-sign-up.png` to `6-help.png` | 1320 x 2868 |
| App Review information | `review-notes.md` (the demo account is filled in App Store Connect only) | |
| App Privacy | `privacy-labels.md` | |

Screenshots: `STORE=ios node tools/cdp.js tools/make-play-assets.js` (example jobs and an example person on a sandbox server of its
own in test mode, the release build's features only). Run it again whenever the screens change.

In the iPhone app (guideline 3.1.1) the plan screen has no buy or billing buttons, only "Plans are managed on uaply.net.", and the
weekly-limit box has only OK. The offline screen is `mobile/www/index.html` (guideline 4.2: it looks like an app screen).
