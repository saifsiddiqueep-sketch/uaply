# Putting UAply online and in the app stores

**`dev` is the release build.** It has no developer bar, no test labels, no simulated sign-in, no example companies and no
simulated payments (paid plans appear only once live Stripe keys are set, section 4), and it starts every new profile blank. `sandbox` is the test bench and keeps all of that. See `CHANGELOG.md`.

## Before real users: your checklist
1. **Host the server** (section 1 below). Until then nothing is online: the phone app's address returns 404.
2. **Google sign-in (free, about 5 minutes):** see section 3 below. With the **client ID and client secret** on the server,
   "Continue with Google" opens Google's own sign-in page on every device (computer, Android, iPhone, iPad) and comes back signed in.
   Google blocks sign-in inside an app's built-in web view, so the Android and iPhone apps hide the Google button until a native Google
   sign-in plugin (and Sign in with Apple, which Apple then requires) is added. Password sign-up works everywhere.
3. **Payments (Plus $9.99, Pro $19.99 a month):** see section 4 below: Stripe live keys, two prices, the webhook and Radar rules.
4. **Email** (password resets, receipts): create a Gmail App Password (needs 2-Step Verification) or use a transactional email
   service, then run `python tools/setup-config.py`. `/setup` has a "Send test email" button. Without it, reset links only reach
   the test inbox, so a real person cannot reset a password.
5. **Real jobs:** `render.yaml` sets `UAPLY_FEEDS=greenhouse,lever,ashby` for dev and sandbox (link-out only: UAply never emails those
   employers). Those boards are public, but their terms do not clearly cover aggregators; have your attorney confirm, or remove the
   line to switch them off. More sources (each switched on by adding its name to `UAPLY_FEEDS` or to `"feeds"` in
   `UAPLY_CONFIG_JSON`): `smartrecruiters` (City of Philadelphia, no key), `usajobs` (federal jobs; needs a free key from
   https://developer.usajobs.gov/APIRequest/, skipped with the status "no key" until then), `muse` (register a free key at
   https://www.themuse.com/developers/api/v2), `jobicy`, `remotive`. Keys go in `"feed_keys"`: on this computer paste them in the
   "Job feed keys" box at `/setup`; on Render put them in `UAPLY_CONFIG_JSON`, e.g.
   `{"feeds":["smartrecruiters","usajobs","muse","jobicy"],"feed_keys":{"usajobs":"","usajobs_email":"","muse":""}}`.
   To switch one source off by name without touching the rest: `"feeds_off":["remotive"]` (or `UAPLY_FEEDS_OFF=remotive`).
6. **Legal pages:** fill every yellow blank in `legal/` (company legal name, street address, contact and privacy email, launch date,
   DMCA agent, liability amount, governing state and county, how long records are kept, host, response time) and have a lawyer
   review them. They say "draft, not reviewed by a lawyer" until you do.
7. **Apple:** Developer Program ($99/year), a Mac or a cloud Mac build service for `mobile/ios`, App Privacy answers, a demo
   account for the reviewers, and a support URL. Apple may reject apps that only wrap a website, so show the phone features
   (reminders, vibration, share sheet).
8. **Name:** a pending trademark filing for APLY (recruitment app) overlaps "UAply". Get a clearance search before spending on
   branding. See `LEGAL-REVIEW.md`.


## 1. Website (Render)
1. Push this repository to GitHub (the `sandbox` and `dev` branches). Render reads `render.yaml` from the branch you pick for the Blueprint.
2. At render.com: sign up, then **New > Blueprint** and pick this repository. It reads `render.yaml` and creates
   `uaply-dev` and `uaply-sandbox` in Virginia (US East), each on the **Starter** plan (0.5 CPU, 512 MB; Render now also calls it `0.5c-512mb`)
   with a 1 GB disk at `/var/data` for accounts, sessions, applications, feedback and the saved job list. The free plan cannot be used: it has
   no disk (everything would vanish at each deploy), sleeps after 15 minutes and blocks email ports 465 and 587. The region cannot be changed
   later. Cost per service: Starter plus 1 GB of disk (Render shows the total before you confirm).
3. When Render asks for the secret values, enter (Render asks only this once; change them later under the service's **Environment**):
   - `ANTHROPIC_API_KEY`: your AI provider's API key (turns on AI answers in the assistant). Optional; if Render will not accept an empty
     value, type `none` (anything not starting `sk-ant-` counts as no key).
   - `OWNER_PASSWORD`: a long password of your choice for `/outbox`, `/feedback` and `/setup` (any user name). Without it those pages are off.
   - `SUPPORT_EMAIL`: the address for "Talk to a person", for example `uaplytechnologies@gmail.com`. Every help request and problem report from the
     assistant is emailed there with the person's own email as the reply address, so you answer by pressing Reply. It needs the email login in
     `UAPLY_CONFIG_JSON` (the `smtp` part, see below); without it requests are only saved on the owner's Feedback page and the chat says so.
   - `UAPLY_CONFIG_JSON`: the email login, the site address and (when you have it) the Google client ID, as one line of JSON. Example:
     `{"delivery":"test","public_url":"https://uaply.net","owner_copy":"you@example.com","smtp":{"host":"smtp-relay.brevo.com","port":587,"starttls":true,"user":"BREVO-LOGIN","password":"BREVO-SMTP-KEY","from_addr":"uaplytechnologies@uaply.net"},"google":{"client_id":"...apps.googleusercontent.com","client_secret":"GOCSPX-..."}}`.
     `public_url` makes the links in emails point at the real site. Leave out `feeds`: `render.yaml` switches the job feeds on (`UAPLY_FEEDS`),
     and a `feeds` list here would keep them on even after that line is removed. On a hosted server `/setup` only shows what is on; its
     Connect boxes refuse to save, because the settings live here. Leave it empty to stay in test mode: nothing is emailed to employers,
     sign-up codes and receipts only appear in the test inbox.
   - `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PLUS`, `STRIPE_PRICE_PRO`: `none` until you set up Stripe (section 4).
     Sandbox: test-mode keys. Dev (the real site): live keys only.
4. Your sites: `https://uaply-dev.onrender.com` and `https://uaply-sandbox.onrender.com` (Render shows the exact names).
5. Check each one: `/healthz` answers `{"ok": true}`, and the service's **Logs** show one line starting `[uaply] dev on 0.0.0.0:10000 (public)`.
   It must say `data: /var/data (persistent disk)`, `email: on` and `UAPLY_CONFIG_JSON: valid` (and, once set up, `Google sign-in: on (full-page
   sign-in on every device)` and `payments: on, LIVE mode`). `NOT a persistent disk` means the disk is not
   attached (accounts would vanish at the next deploy); `NOT VALID JSON` means the settings line has a typo and was ignored. On the very first
   start the job list takes about a minute to fill (the server reads every employer's board once); after that it is saved on the disk and a
   redeploy shows jobs at once.
6. Your address (Cloudflare): in Render, uaply-dev, Settings, Custom Domains, add `uaply.net` (Render adds `www` and redirects it). In Cloudflare,
   DNS: delete any AAAA record for `uaply.net`, add CNAME `@` and CNAME `www`, both to `uaply-dev.onrender.com` with Proxy status **DNS only**,
   and set SSL/TLS to **Full**. Back in Render press Verify; https://uaply.net works once the certificate shows as issued. Leave the MX and TXT
   (email) records alone. Add `https://uaply.net` to the Google client ID's Authorized JavaScript origins.

How deploys behave: every push to `dev` (or `sandbox`) redeploys that service. Because it has a disk, Render stops the old copy before
starting the new one, so the site is unreachable for a few seconds; the server finishes the requests in progress before it stops
(`[uaply] stopped` in the log), and the new copy answers about a second after Render starts it (measured with a filled disk). Accounts, sessions, applications and feedback survive: people stay
signed in. Render keeps a snapshot of the disk every day for at least 7 days (Disks, in the service).

Changing the API key later (for example to a business key) is only an edit of `ANTHROPIC_API_KEY` in Render's
dashboard; no code changes. `python tools/test-render.py` starts the server the way Render does and checks all of the above.

Before real users: fill the blanks in `legal/`, and keep `delivery` in test mode until partner employers have agreed.

## 2. App Store and Google Play (Capacitor, in `mobile/`)
The apps open https://uaply.net (`mobile/capacitor.config.json`, `server.url`). If the address changes, edit it there and
in `mobile/www/index.html` (`SITE`, the "can't connect" screen), then run `npx cap sync` in `mobile/`.
- **What the apps have:** the UAply icon and splash screens; interview reminders (local notifications), a vibration on each
  swipe, the share sheet; a "Can't reach UAply" screen with Try again whenever the site does not load (`server.errorPath`).
  "Continue with Google" is hidden inside the apps (Google blocks its sign-in inside app web views, and Apple would also
  require Sign in with Apple next to it); app users sign in with email and password.
- **Android (works on Windows, free):** run `powershell -ExecutionPolicy Bypass -File mobile\build-android.ps1` for a test
  `.apk`, or add `-Release` for the signed `.aab` Google Play needs. The first run downloads Java 21 and Google's Android
  command-line tools into your user folder (checksums checked) and shows Google's Android SDK license for you to accept.
  `-Release` creates your upload key `mobile\android\uaply-upload-key.jks` the first time and asks you to choose its
  password: write the password down and back up the file privately (it is git-ignored and must never be committed). The app
  targets Android 16 (API 36), which Google Play requires for new apps since August 31, 2026. Raise `versionCode` in
  `mobile/android/app/build.gradle` before each new upload.
- **iPhone (no Mac needed):** `codemagic.yaml` builds `mobile/ios` on Codemagic's cloud Mac (free plan: 500 Mac minutes a
  month), signs it and sends it to TestFlight. Before the first build: an App Store Connect API key added in Codemagic as
  "UAply ASC key", and the app's Apple ID number in `APP_STORE_APPLE_ID`. The iPhone app is iPhone-only (no iPad).
- **Accounts and fees:** Google Play developer account US$25 once (photo ID, proof of address and a real Android phone to
  verify); new personal accounts must run a closed test with at least 12 testers for 14 days in a row before going public.
  Apple Developer Program US$99 a year.
- **Review risk:** Apple can reject apps that only wrap a website (guideline 4.2). Push notifications for new matches,
  links from emails opening in the app (Universal Links) or home-screen quick actions would make that much less likely.
  Paid plans through Stripe are allowed inside the app on Apple's United States storefront only, so publish in the US only.
- **Store forms:** both stores need the privacy policy URL (`/legal/privacy.html`, blanks filled) and accurate privacy
  answers; account deletion exists in the app (Profile, Account, More account options).

## 3. Google sign-in
One OAuth client of type **Web application** does everything. With its **client ID and client secret** on the server, "Continue with
Google" sends the person to Google's own page (they pick their account there; UAply never sees their password) and Google sends them
back signed in. It is the same on computers, Android phones, iPhones and iPads, and it does not depend on third-party cookies, pop-ups or
Chrome's FedCM prompt. (Google's pop-up button is used only on your own computer when just the client ID is saved there.)

Five minutes, at https://console.cloud.google.com, signed in with the Google account that should own UAply:
1. **Google Auth Platform > Overview > Get started** (create a project named `UAply` first if asked): App name `UAply`, User support
   email your Gmail, Audience **External**, Contact email your Gmail, agree, **Create**.
2. **Branding:** App home page `https://uaply.net`, Privacy policy `https://uaply.net/legal/privacy.html`, Terms of service
   `https://uaply.net/legal/terms.html`, Authorized domains `uaply.net` and `uaply.onrender.com` (`onrender.com` itself is a public
   suffix, so Google wants the full Render address; it also adds the domains of your redirect URIs by itself). **Save**.
3. **Audience > Publish app > Confirm** (Publishing status: In production). UAply asks only for `openid` and `email`, which Google counts
   as non-sensitive: no verification review and no 100-user cap. While the app is in Testing, only the test users listed on that page
   can sign in. Optional, later: Branding > verify, so Google's page shows "UAply" and the logo instead of the address.
4. **Clients > Create client**, Application type **Web application**, Name `UAply web`. Copy each line exactly (no slash at the end of
   an origin; Google compares letter for letter, and `localhost` and `127.0.0.1` are different addresses):

   | Authorized JavaScript origins | Authorized redirect URIs |
   |---|---|
   | `https://uaply.net` | `https://uaply.net/api/auth/google/callback` |
   | `https://www.uaply.net` | `https://www.uaply.net/api/auth/google/callback` |
   | `https://uaply.onrender.com` | `https://uaply.onrender.com/api/auth/google/callback` |
   | `http://localhost:8767` | `http://localhost:8767/api/auth/google/callback` |
   | `http://localhost` | (none) |

   If Render shows your service under another address (for example `https://uaply-dev.onrender.com`), add that one too, in both
   columns. **Create**, then copy the **Client ID** (ends in `.apps.googleusercontent.com`) and the **Client secret** (starts with
   `GOCSPX-`). Download the JSON: Google shows the full secret only now (later only its last characters; **Add secret** makes a new one).
5. **Render > uaply-dev > Environment > `UAPLY_CONFIG_JSON` > Edit.** Add the `google` part inside the outer `{ }`, after a comma, so
   the whole line looks like this (your own email values stay as they are):

       {"delivery":"test","public_url":"https://uaply.net","owner_copy":"you@example.com","smtp":{"host":"smtp-relay.brevo.com","port":587,"starttls":true,"user":"BREVO-LOGIN","password":"BREVO-SMTP-KEY","from_addr":"uaplytechnologies@uaply.net"},"google":{"client_id":"123456789012-abc123.apps.googleusercontent.com","client_secret":"GOCSPX-..."}}

   **Save, rebuild, and deploy.** The log line must say `UAPLY_CONFIG_JSON: valid` and `Google sign-in: on (full-page sign-in on every
   device)`. On your own computer run `python tools/setup-config.py` to save both values (never paste the secret into a page or chat).
6. Test (Google says a new client can take from 5 minutes to a few hours to work): open https://uaply.net in a private window, Profile,
   Account, tick the 18+ box, **Continue with Google**, pick an account: you come back with "Signed in with Google". Do it once on an
   iPhone and once at https://www.uaply.net and https://uaply.onrender.com.

**If you see X, do Y**

| You see | Do this |
|---|---|
| Google's page: `Error 400: redirect_uri_mismatch` | The address in the browser + `/api/auth/google/callback` is not under Authorized redirect URIs. Google's error page shows the exact `redirect_uri` it got (Error details): copy it into the list, save, wait 5 minutes. |
| `The given origin is not allowed for the given client ID`, `origin_mismatch` or `idpiframe_initialization_failed` | The exact address (http or https, with or without www, the port) is not under Authorized JavaScript origins. Add it without a slash at the end. |
| Google's page: `Error 401: invalid_client` or `deleted_client`; or the log says `Google refused to swap the sign-in code (invalid_client)` | The client ID or secret in `UAPLY_CONFIG_JSON` is wrong, has a space in it, or the client was deleted. Copy both again (Add secret for a new secret). |
| `Access blocked: UAply has not completed the Google verification process` / `Error 403: access_denied` for everyone but you | Audience is still Testing: press **Publish app** (step 3). |
| `Error 403: org_internal` | Audience is Internal: change the user type to External. |
| `Error 403: disallowed_useragent` | Sign-in was tried inside an app's built-in browser (Instagram, the UAply phone app). Open uaply.net in Safari or Chrome. |
| Back in UAply: "That Google sign-in expired or could not be checked" | Usually the back button or a second tab. If it happens every time: the site was opened at one address but Google returned to another; make sure both are listed and `public_url` is `https://uaply.net`. |
| No Google button at all | The log says `Google sign-in: off` or `OFF: the client ID ... does not end in .apps.googleusercontent.com`: fix `UAPLY_CONFIG_JSON` (it must say `valid`). |
| FedCM `NetworkError` / "Signin is not available" in Chrome's console | Only Google's pop-up button uses FedCM, and UAply no longer uses it once the secret is set. Set the client secret (step 5). |

## 4. Payments with Stripe (Plus $9.99, Pro $19.99 a month)
People pay on Stripe's own Checkout page; UAply never sees a card number. A plan switches on only when Stripe's signed webhook says the
subscription is active, and UAply then asks Stripe itself to confirm it, so a declined, fake or stolen-and-blocked card, a forged
message, a replayed old message or a typed `?billing=success` address can never unlock a plan. A live server ignores test-mode
messages, so Stripe's test card 4242 4242 4242 4242 cannot unlock anything on the real site. Renewals: if a card fails, Stripe retries
it and the person is told to update the card; after the third failed try the plan pauses, and it comes back by itself when a payment
works. Cancel in the portal: the plan stays until the paid month ends. Deleting the account cancels the subscription at Stripe at once, before the account is removed (no refund of the current month unless you give one); if Stripe cannot be reached, the account is kept and the person is told to cancel in Manage billing first.

**First try it all in test mode (sandbox):** toggle **Test mode** in Stripe, do steps 2 to 6 below with test-mode values on
`uaply-sandbox` (webhook URL `https://uaply-sandbox.onrender.com/api/billing/webhook`), then buy a plan with Stripe's test cards
(any future date, any CVC, any ZIP):

| Card | What happens | UAply should show |
|---|---|---|
| `4242 4242 4242 4242` | Payment succeeds | the plan within seconds |
| `4000 0025 0000 3155` | Asks for 3D Secure; complete it | the plan |
| `4000 0000 0000 0002` | Declined | still Free, nothing charged |
| `4000 0000 0000 9995` | Declined, insufficient funds | still Free |
| `4000 0000 0000 0101` | CVC check fails (blocked once the CVC rule in step 7 is on) | still Free |
| `4100 0000 0000 0019` | Blocked by Radar as highest risk | still Free |
| `4000 0000 0000 0341` | Card saved, first charge fails | still Free ("Stripe has not confirmed the payment yet") |
| `4242 4242 4242 4241` (a typo) | Stripe's page says the number is invalid | nothing happens |

Then in the portal (Manage billing) cancel the plan: it says when it ends. To see a failed renewal, use a test clock (Billing,
Subscriptions, the subscription, Run simulation) with the card `4000 0000 0000 0341` set as the default.

**Going live (the real site, `uaply-dev`), in this order.** Before step 1, have your lawyer replace the "UAply is currently free"
paragraph of `legal/terms.html` with the paid-plan terms (price, monthly automatic renewal until cancelled, how to cancel online in
Manage billing, the plan lasting to the end of the paid month, your refund policy): US automatic-renewal laws require these to be shown
before the first charge.
1. **Activate the account:** Stripe Dashboard, **Activate payments** (Settings, Business): legal business details, your identity, the
   bank account for payouts, and two-step authentication. Public details: business name `UAply`, statement descriptor `UAPLY`
   (what appears on card statements; a clear one prevents "I don't recognise this" chargebacks), support email and the website
   `https://uaply.net`.
2. **Two prices** (live mode, Product catalog, Add product): `UAply Plus`, Recurring, **9.99 USD Monthly**; `UAply Pro`, Recurring,
   **19.99 USD Monthly**. Open each product and copy its **price id** (`price_...`; test-mode prices do not exist in live mode).
3. **Customer portal** (Settings, Billing, Customer portal): allow updating payment methods, showing invoice history, switching plans
   between the Plus and Pro prices, and **Cancel subscriptions: at the end of the billing period**. Save.
4. **Failed payments and emails** (Settings, Billing, Subscriptions and emails): Smart Retries on (Stripe's recommended schedule),
   **If all retries fail: cancel the subscription** (UAply then moves the account to Free), and switch on the customer emails for
   failed payments, expiring cards and successful payments (receipts).
5. **Webhook** (Developers, Webhooks, **Add destination**): Your account; the latest API version; these six events:
   `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`,
   `invoice.paid`, `invoice.payment_failed`; type **Webhook endpoint**; URL **`https://uaply.onrender.com/api/billing/webhook`**
   (the address Render shows for uaply-dev, which keeps working whatever happens to the domain). Create, then **reveal and copy the
   Signing secret** (`whsec_...`). Each endpoint, and test and live mode, has its own secret.
6. **Keys into Render** (Developers, API keys, live mode: reveal and copy the **Secret key** `sk_live_...`; not the publishable `pk_`
   key, not a restricted `rk_` key). Render, uaply-dev, Environment, add or edit:
   `STRIPE_SECRET_KEY` = `sk_live_...`, `STRIPE_WEBHOOK_SECRET` = `whsec_...`, `STRIPE_PRICE_PLUS` = the Plus `price_...`,
   `STRIPE_PRICE_PRO` = the Pro `price_...`. **Save, rebuild, and deploy.** The log line must say `payments: on, LIVE mode` and
   nothing in capitals after it (`NO WEBHOOK SECRET` or `OFF:` name what is missing). `/setup` shows the same.
7. **Radar** (Fraud and risk, Rules). On by default: block payments Stripe scores as **highest risk** (`Block if :risk_level: =
   'highest'`) and ask for 3D Secure when the bank requires it. Switch on: **Block if CVC verification fails** and **Block if postal
   code verification fails** (the "based on risk score" versions Stripe recommends, so honest typos on low-risk payments still pass).
   Custom rules need Radar for Fraud Teams (an extra fee per screened payment); worth it if fraud appears: `Request 3D Secure if
   :risk_level: = 'elevated'`, and `Block if :card_funding: = 'prepaid'` (stops most card testing, but also turns away some students
   who only have prepaid cards). UAply adds its own gate: only a signed-in account with a verified email can open Checkout.
8. **One real purchase:** buy Plus with your own card on https://uaply.net, check the plan appears, open Manage billing, cancel, and
   refund yourself in Stripe (Payments, the payment, Refund). In Developers, Webhooks, the endpoint should show every delivery as 200.
   A failed delivery shows the reason; Stripe retries it for up to three days, and UAply handles each event once.

Never put a live key in a file, a chat or the sandbox; sandbox stays on test keys.
