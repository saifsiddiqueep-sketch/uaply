# Google Play: what happens tonight (October 23, 2026)

The order for tonight, split into what only Saif can do (his Google account, his money, his identity, his passwords) and what the bots
do. Background: `docs/play-store.md` (the ten steps), `mobile/store/play/README.md` (every Console screen and its file),
`mobile/twa/README.md` (the build). Checked against Google's help pages on October 23, 2026; the links are at the end.

## What cannot happen tonight
- **No public listing tonight.** A personal developer account made after November 13, 2023 must run a closed test with **12 testers
  opted in for 14 days in a row** before it can even apply for production, and production then goes through review (up to 7 days or
  longer). The earliest production date is about two to three weeks from the day 12 testers have opted in.
- **Identity verification may not finish tonight.** Google can ask for a government ID and a card in the legal name and reviews them;
  until the account is verified the app cannot be published to any track. If it is still pending, tonight ends after "Saif 1-4".
- **The app opens with Chrome's address bar until the next release.** uaply.net does not yet serve the web manifest, the icons,
  `/.well-known/assetlinks.json` or the account-deletion page (all four answered 404 tonight; they are in the release). Internal
  testers can still install and use it.
- **Screenshots with the sign-up card first** are made once the sign-in gate is merged into sandbox (a bot; see below). The Main store
  listing can be saved without them; it is not public until production anyway.

## Saif, in the Play Console

1. **Create the developer account** at https://play.google.com/console with **uaplytechnologies@gmail.com**, account type
   **Personal** (an Organization account needs a D-U-N-S number and skips the 12-tester rule; choose it only if UAply has one). Pay
   the **US$25** one-time fee by credit or debit card (no prepaid cards).
2. **Verify identity**: the legal name and address from the linked Google payments profile, a government ID if asked, and the developer
   email's one-time code. Google's review of the ID usually takes from a few hours to a few days.
3. **Verify an Android phone**: install the **Google Play Console** app on an Android phone, sign in with the same account, and finish
   the device check it asks for (new personal accounts must).
4. **Create the app**: name **UAply**, default language English (United States), **App**, **Free**; tick the declarations.
5. **Accept the Android SDK licence and build the bundle**, on this computer, in PowerShell, from the repository folder:

       powershell -ExecutionPolicy Bypass -File mobile\twa\build-bundle.ps1

   Answer **Yes** to Bubblewrap's JDK and Android SDK, accept Google's licence, choose the upload key's password (first time; keep it in
   the password manager and back up `mobile\android\uaply-upload-key.jks` privately), and type it again when the build asks. It writes
   `mobile\twa\app-release-bundle.aab`. (A bot cannot do this step: the licence and the key's password are Saif's.)
6. **App signing**: Test and release > Setup > App signing: keep **Play App Signing** on.
7. **Internal testing**: Test and release > Testing > **Internal testing** > Create new release, upload `app-release-bundle.aab`, release
   notes from `mobile/store/play/testers.md`, roll out. The first release can wait for review (a few hours to 7 days).
8. **Add testers**: the Testers tab, an email list with each tester's Google account (up to 100), save, copy the link, send it.
9. **Copy the two SHA-256 fingerprints** from App signing (App signing key and Upload key) and send them to the bot that sets
   `UAPLY_ASSETLINKS_SHA256` on Render (or set it yourself: Render, service uaply, Environment).
10. **Make the reviewer's demo account** (`review@uaply.net` or another inbox the team reads), verify it with its emailed code, and paste
    its email and password into Policy > App content > **App access**. Only Saif types that password.
11. **Fill the legal blanks** first if not done: `legal/privacy.html` and `legal/terms.html` each still have 7 highlighted blanks (company
    legal name, launch date, privacy email, retention, host). A reviewer opens the privacy link.

## Bots

- Done tonight on branch `play-tonight`: the listing texts and forms updated for the sign-in gate (an account is now needed, the reviewer
  gets a demo account, the testers' invite says the first screen asks to sign up), the target-API rule (Android 16, API 36), internal
  testing before the closed test, the device check, and `mobile/twa/build-bundle.ps1` (the one command above).
- When the sign-in gate is merged: regenerate every screenshot (`node tools/cdp.js tools/make-play-assets.js`) with the sign-up card
  first, phone and tablet (`0-sign-up.png` then `1-jobs.png` ... `5-help.png`, all 1080 x 1920), and run `python tools/test-play-listing.py`.
- Once Saif sends the fingerprints: `UAPLY_ASSETLINKS_SHA256` on Render (owner approval for the variable), then check
  https://uaply.net/.well-known/assetlinks.json after the release with Google's Digital Asset Links checker.
- Paste-ready answers for every App content screen: `mobile/store/play/app-content.md`, `data-safety.md`, `content-rating.md`. (The Data
  safety form is not required while the app is only on internal testing, but it is ready for the closed test.)
- After the internal test works: the closed test track, the invite, and a daily count of opted-in testers until 12 have stayed 14 days.

## Sources (October 23, 2026)
- Testing for new personal accounts: https://support.google.com/googleplay/android-developer/answer/14151465
- Target API level 36 for new apps since August 31, 2026: https://developer.android.com/google/play/requirements/target-sdk
- Fee, identity and device verification: https://support.google.com/googleplay/android-developer/answer/6112435 and
  https://support.google.com/googleplay/android-developer/answer/10841920
- Store graphics (icon 512, feature graphic 1024 x 500, screenshots 320-3840 px, at most 2:1): https://support.google.com/googleplay/android-developer/answer/9866151
- Internal testing (first release review, Data safety exemption): https://support.google.com/googleplay/android-developer/answer/9845334 and
  https://support.google.com/googleplay/android-developer/answer/10787469
- Bubblewrap's template at API 35 in July 2026: https://github.com/pwa-builder/pwabuilder/issues/6160
