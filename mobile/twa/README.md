# UAply for Google Play (Trusted Web Activity)

This folder makes the Play Store app as a **Trusted Web Activity (TWA)**: a small Android app that opens https://uaply.net full screen in
the phone's own Chrome. Because it is real Chrome (not a built-in web view), **Continue with Google, Stripe Checkout, cookies and the
app's storage work exactly as on the website**, and every website deploy reaches the app at once with no new upload.

Only `twa-manifest.json`, this README and `.gitignore` are kept in git. `bubblewrap update` generates the Android project (`app/`,
`gradle/`, `build.gradle` ...) from `twa-manifest.json`; those files are ignored and can be rebuilt at any time. The older Capacitor
project in `mobile/android` uses the same package name (`com.uaply.app`) and the same upload key: upload one or the other to Play,
not both (this one is the recommended one).

What the website already provides (nothing to do): the web manifest (`/uaply.webmanifest`), the icons, a service worker with an offline and
"starting up" screen, HTTPS, the account-deletion page (`/legal/delete-account.html`) and `/.well-known/assetlinks.json`, which lists
the keys from the `UAPLY_ASSETLINKS_SHA256` setting on Render.

## Owner steps

### 1. Tools (once, on your computer)
1. Install Node.js 20 or newer (https://nodejs.org, the LTS installer).
2. In PowerShell: `npm install -g @bubblewrap/cli`
3. `cd` into this folder (`mobile\twa`) and run `bubblewrap doctor`. The first time, Bubblewrap offers to download its own JDK 17 and
   the Android command-line tools: answer **Yes** to both and accept Google's Android SDK licence when it is shown (only you can accept
   it). Run `bubblewrap doctor` again until it says everything is OK.

### 2. The upload key (once)
The app is signed with an **upload key**. If `mobile\android\uaply-upload-key.jks` already exists (made by
`mobile\build-android.ps1 -Release`), use it: `twa-manifest.json` already points there (alias `upload`). Otherwise create it with the
JDK Bubblewrap downloaded (it is under `%USERPROFILE%\.bubblewrap\jdk\`):

    keytool -genkeypair -keystore ..\android\uaply-upload-key.jks -alias upload -keyalg RSA -keysize 2048 -validity 10000 -storetype PKCS12 -dname "CN=UAply, O=UAply, C=US"

Choose a long password, keep it in your password manager, and back the `.jks` file up somewhere private (never in git, never only in
this folder). Without both you cannot upload updates (Google can reset a lost upload key, but it takes days).

### 3. Build the app bundle
1. In `mobile\twa`: `bubblewrap update --skipVersionUpgrade` (generates the Android project from `twa-manifest.json`).
2. Check `app\build.gradle`: `targetSdkVersion` must be **36 or higher** (Google Play's rule since August 31, 2026). If it is lower,
   run `npm install -g @bubblewrap/cli@latest` and step 1 again; do not edit the generated files by hand (`update` overwrites them).
3. `bubblewrap build`. It asks for the key's passwords and writes `app-release-bundle.aab` (for Play) and `app-release-signed.apk`
   (to try on your own phone: `bubblewrap install`).
4. For every later upload: raise `appVersionCode` (and `appVersion`) in `twa-manifest.json`, run `bubblewrap update --skipVersionUpgrade`,
   then `bubblewrap build`. (Or let `bubblewrap update` raise them for you by leaving out `--skipVersionUpgrade`.)

### 4. Play Console
1. Create the app (name **UAply**, app, free), then **Test and release > Setup > App signing**: keep **Play App Signing** on (Google
   holds the signing key; you keep only the upload key).
2. **Test and release > Testing > Closed testing**: create a track, upload `app-release-bundle.aab`, add your testers' Google
   accounts. A personal developer account needs **at least 12 testers opted in for 14 days in a row** before it can apply for
   production.
3. Back in **App signing**, copy the two **SHA-256 certificate fingerprints**: the *App signing key certificate* (the app people
   install from Play) and the *Upload key certificate* (a build you install by hand).
4. Render dashboard, service **uaply**, **Environment**: add `UAPLY_ASSETLINKS_SHA256` with both, comma-separated, for example
   `AB:CD:...:EF,12:34:...:56`, then **Save, rebuild, and deploy**. No new app build is needed when a key changes.
5. Check https://uaply.net/.well-known/assetlinks.json shows both fingerprints and the package `com.uaply.app`, and test it with
   Google's checker: https://developers.google.com/digital-asset-links/tools/generator (site `uaply.net`, package `com.uaply.app`,
   the app signing fingerprint). If the link is wrong, the app still works but shows Chrome's address bar at the top.
6. **App content**: Data safety form (account deletion URL: `https://uaply.net/legal/delete-account.html`), privacy policy URL
   (`https://uaply.net/legal/privacy.html`), content rating, target audience 18+, and the app access note with a reviewer account.

## Settings in twa-manifest.json worth knowing
- `fallbackType: "customtabs"`: on a phone without a TWA-capable browser the app opens in another browser's Custom Tab. Never set
  it to `"webview"`: Google refuses sign-in inside a web view (`disallowed_useragent`).
- `enableNotifications: false`: UAply sends no web push notifications, so the app asks for no notification permission.
- `host` / `startUrl`: the app opens `https://uaply.net/`. A page on another site (Google sign-in, Stripe Checkout, an employer's
  application page) shows inside the app with a small address bar at the top, which goes away again when it comes back to uaply.net.
