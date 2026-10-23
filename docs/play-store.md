# Google Play: from website to production in ten steps

The Android app is the website running inside Chrome as a full-screen app (a Trusted Web Activity), so Google sign-in, payments and the
swipe work exactly as on uaply.net. From the plan of October 21, 2026 ("UAply Swipe Readiness and Play Store Plan", section 2).

| # | Step | Who | State | Where |
|---|---|---|---|---|
| 1 | Site installable: manifest, icons, offline screen, service worker | Bot | Done, in sandbox | `shared/uaply.webmanifest`, `shared/uaply-sw.js`, `shared/uaply-offline.html` |
| 2 | Android ownership file served, waiting only for the key fingerprints | Bot | Done, in sandbox | `/.well-known/assetlinks.json` from `UAPLY_ASSETLINKS_SHA256` (`serve.py`) |
| 3 | Account deletion page, linked from Privacy and Support | Bot | Done, in sandbox | `legal/delete-account.html` |
| 4 | Release to uaply.net so Google can read the manifest and the ownership file from the real address | Reviewers, then the owner | Next release | `dev` branch, Render service `uaply` |
| 5 | Store listing pack: app name, short and full description, 512 px icon, 1024 x 500 feature graphic, phone and tablet screenshots, Data safety answers, content rating answers, privacy policy link, deletion page link | Bot | Done, in sandbox | `mobile/store/play/` (its README maps each Console screen to a file) |
| 6 | Google Play developer account under uaplytechnologies@gmail.com: identity verification (a government ID and a card in the legal name), the developer email's one-time code, and proof of access to an Android phone with the Play Console app | Owner, US$25 once | Tonight (October 23); tonight's order is in `docs/play-tonight.md` | play.google.com/console |
| 7 | Build the app bundle with Bubblewrap (it must target Android 16, API level 36: Google Play's rule for new apps since August 31, 2026), turn on Play App Signing, keep two backups of the upload key | Bot builds, owner accepts the SDK licence and keeps the key | After step 6 | `mobile/twa/README.md` |
| 8 | Put both key fingerprints into the Render variable so the ownership file goes live, then verify with Google's checker | Bot | After step 7 | `UAPLY_ASSETLINKS_SHA256`, `mobile/twa/README.md` step 4 |
| 9 | Internal testing first (up to 100 testers, no review wait), then the closed test: 12 testers opted in for 14 days in a row (a personal account made after November 13, 2023 cannot apply for production before); invite text prepared | Owner and testers | 14 days | `mobile/store/play/testers.md` |
| 10 | Apply for production; review usually takes under 7 days | Owner | After step 9 | Play Console, Dashboard |

Store pictures: the screenshots must show the sign-up card first now that the sign-in gate is on. `tools/make-play-assets.js` is run
again from the gate's sandbox once it is merged (every phone and tablet screenshot is regenerated, with the sign-up card as the first).

Two rules that keep the listing safe:
- **No buy buttons inside the app.** The free-only switch (`UAPLY_PLANS_HIDDEN=1`) already guarantees it; Google Play's payments policy
  would otherwise require Google Play Billing for in-app subscriptions.
- **Google-only accounts must be able to sign in inside the app.** Email codes work everywhere, and the sign-in gate covers it.
- **The reviewer needs a working account.** Everything is behind sign-in, so App access carries a demo account the owner makes
  (`mobile/store/play/app-content.md`).
