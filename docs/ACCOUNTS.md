# Accounts: one email address is one account

Written October 17, 2026 (Bot 4, sign-in and payments). The code is `auth_api.py` (`canonical_email`, `signup`, `oauth_login`,
`mailbox_problem`), `google_auth.py` (`_identity`) and `billing_api.py` (`_ref_uid`). The proof is `tools/test-accounts.py`; the check
for a live disk is `tools/audit-accounts.py`.

## The sign-in contract (Saif, October 22, 2026: read this first when building the card or the gate)

Three decisions: **(a)** sign-up is email, first name, last name and a password; the emailed 6-digit code verifies the address after
sign-up and is the other way to sign in ("Email me a code"). **(b)** Nobody reaches site data without an account. **(c)** A test server
can make filler accounts at once. Code sign-in and the gate run wherever the server runs (sandbox, dev, the live site); a public server
that cannot send email still refuses to pretend to send codes. Every answer is JSON; every POST needs this site's own `Origin`; the
session is the HttpOnly cookie `uaply_<instance>_session` (`SameSite=Lax`, `Secure` behind HTTPS).

| Route | Send | Answer |
|---|---|---|
| `GET /api/auth/providers` | | Google's settings, plus `codeSignin: true` when "Email me a code" can be offered (absent on a public server without email) and `signupTest: true` only in test mode (absent on a public server, always). |
| `POST /api/auth/signup` | `{email, password, first, last, agree: true}` | **200** `{user: {id, email, hasPassword: true, emailVerified: false, plan, first, last}, delivery: "sent" or "delivered_test"}` and the session cookie: signed in at once. The 6-digit verification code is emailed **after** the answer. **400** `{error}` (an address that cannot exist, no tick, a password under 8 or over 128 characters or equal to the email, `code: "mailbox"` for a throwaway or dead domain). **409** "That email already has an account. Sign in instead." **429** `{error, code: "signup_limit" or "signup_email_limit"}`, the same words for every address. `first` and `last` are cleaned and cut to 60 characters; the server accepts them empty, the card requires them. |
| `POST /api/auth/verify` | `{code}` with the session | **200** `{ok: true}` (the address is verified), **400** `{error}` (wrong: tries left; `expired: true`: send a new one), **429**. Full-width and Arabic-Indic digits count as the digits they are. |
| `POST /api/auth/resend` | with the session | **200** `{ok, message}`; **429** `{error}` (3 an hour per account, 6 a day per address, the site's hour). |
| `POST /api/auth/login` | `{email, password}` | **200** `{user}` and the cookie; **401** "Wrong email or password."; **429** lock-out. |
| `POST /api/auth/code/send` | `{email}` | **200** `{ok: true}`, the same for every address; an address with an account gets a **sign-in** code ("This code signs in to your UAply account. UAply will never ask you for it. If it was not you, ignore this email."). **429** `{error, code: "code_limit" / "code_day" / "code_busy"}`. **503** `{code: "mail_off"}` on a public server without email. |
| `POST /api/auth/code/verify` | `{email, code, agree?}` | **200** `{user: {..., new}}` and the cookie (and the known-device cookie); **400** one plain answer for every wrong code; `needsAgree: true` when an account no one proved yet needs this person's own 18+ / Terms tick. |
| `POST /api/auth/forgot` | `{email}` | **200** the same answer either way; the link is emailed after the answer. A public server without email: `{ok: false, delivery: "unavailable"}`. |
| `POST /api/auth/reset`, `change-password`, `logout`, `delete` | as before | `change-password` on an account with no password: **400** `code: "no_password"`, "This account has no password: you sign in with a code sent to your email (or with Google). Use Forgot password to add one." |
| `POST /api/auth/google/token`; `GET /api/auth/google/start`, `/callback` | Google's token or the redirect | Joining an account whose address nobody proved needs `agree: true`: **400** `code: "agree_owner"` (the redirect: `/?auth_error=agree_owner`). |
| `GET /api/auth/me` | | `{user: null}`, or `{user: {id, email, hasPassword, emailVerified, plan, first, last, googleLinked, google?: {new}}}`. |
| `POST /api/auth/signup` with `passwordless: true` | `{email, agree: true, first?, last?}` | Still answers (the sandbox's no-password card): **200** `{ok: true, email}` either way and a code to type in `/api/auth/code/verify`. |

**The gate.** Without a session these answer **401** `{"error": "Sign in first.", "code": "signin"}`: `GET /api/jobs`,
`GET /api/employer/logo/*`, and `POST /api/apply`, `/api/apply/plan`, `/api/apply/mark`, `/api/decision`, `/api/chat`, `/api/feedback`,
`/api/profile/resume`, `/api/employer/company`, `/api/employer/job`, `/api/employer/job/status`, `/api/employer/applicant`,
`/api/employer/import` (`/api/employer/me` answers its own "sign in" itself). Open without a session: `/` and the page's own files,
`/healthz`, `/api/status`, every `/api/auth/*` route, `/api/apply/config`, `/api/chat/config`, `/api/billing/status`, the legal pages,
`/help/articles.json`, the support page, the service worker, the manifest and the offline page. `/sitemap.xml` lists only the home page
and the legal pages, and the home page's JSON-LD only names the site. The owner pages (`/outbox`, `/api/outbox`, `/feedback`, `/setup`,
`/api/feed-health`) keep their own owner check (this computer, or the owner password) instead of the session gate: on a test server the
test inbox is how a code is read before anyone is signed in.

**Test mode.** `UAPLY_SIGNUP_TEST=1` on a server that is not public (this computer): `POST /api/auth/signup` makes the account already
verified, signs it in at once and emails nothing (`delivery: "none", testMode: true`), and providers says `signupTest: true`. On a public
server the setting is ignored, always. `UAPLY_CODE_SIGNIN=0` switches the code routes off (a test server that checks the password routes
alone); nothing else does. `tools/test-signin-contract.py` tests all of this.

## The promise
Every address has at most one UAply account, and nothing done with one account ever reaches another. Sign-up, log-in, Forgot password,
the 6-digit code, Continue with Google, the sign-up limits and the lock-out all find an account through one key: the canonical address.

## The canonical address
`auth_api.canonical_email(text)` is the only way an address becomes a key:
1. **NFKC** first, so look-alike forms of the same letters (full-width `ａｌｉｃｅ`, the Kelvin sign) become the plain letters they stand
   for. Without it, `ａlice@example.com` was refused at log-in while `alice@example.com` worked, and a future change that accepted
   Unicode could have made it a second account.
2. **Trimmed** (spaces, tabs, line breaks around it).
3. Anything left that is a **space or a control/format character** (NUL, DEL, zero-width space, soft hyphen, a line break inside) is
   refused, never silently removed.
4. **Lower-cased**, local part and domain. RFC 5321 lets a server treat the local part as case-sensitive, but no mail provider people
   use does, and two accounts that differ only in case is the classic way people get confused or impersonated.
5. Must then be **plain ASCII** and match the address pattern. Internationalised addresses (a non-ASCII local part or domain) are
   refused on purpose: UAply's mail sending does not support SMTPUTF8, and two different Unicode spellings can look identical
   (`аlice` with a Cyrillic а). Someone with such an address can use its ASCII (punycode) form or another address.

Stored addresses were already trimmed, lower-case ASCII under the old rule, and NFKC changes nothing in ASCII, so no stored address
changes and no migration is needed. `tools/audit-accounts.py` confirms that on any disk.

## Dots and +tags: separate accounts (the rule, and why)
What the providers do: Gmail ignores dots in `@gmail.com` (and `@googlemail.com`) addresses and delivers `name+anything@gmail.com` to
`name@gmail.com`. Google Workspace addresses (a company's or school's own domain on Google) are different: Google says dots do matter
there. Outlook, iCloud, Fastmail, Proton and Yahoo each have their own plus or alias rules, some domains treat `+` as an ordinary
character, and some servers use `-` instead.

**UAply keeps every address exactly as typed (after the canonical steps above): `owner@gmail.com`, `owner+live1@gmail.com` and
`o.w.n.e.r@gmail.com` are three accounts.** Reasons:
- **No accidental merges, no takeover.** Folding is provider-specific and providers change their rules. Folding a domain where dots
  or `+` are significant would put two different people into one account. Even Gmail-only folding would merge accounts that the
  person deliberately keeps apart (the owner's own test accounts are `owner+live1@gmail.com` style).
- **Separate accounts cannot interfere.** Every account still needs its 6-digit code (or Google) to prove the address, and all
  spellings that reach one Gmail inbox reach the same person, so nobody else can verify or reset any of them.
- **Google sign-in links only the exact address.** Google returns the address as the person registered it. A Google sign-in as
  `john.smith@gmail.com` does not join a password account made as `johnsmith@gmail.com`; that person gets a separate account. This
  is the price of "never merge", and it is the person's own two accounts, never someone else's.
- **Abuse** (several free accounts from one inbox) is handled by the sign-up limit below and the plan limits, not by guessing at
  mailboxes; anyone can make several Gmail accounts anyway.

The sign-up screen says so when the typed address has a `+tag` ("Each address is its own UAply account: one with a +tag is a separate
account from the plain address..."). It is worked out from the typed text alone. The server never says "the plain address already has
an account", because that would tell any visitor who has an account.

## Races
Sign-ups and Google sign-ins for a new address are serialised by a lock in the server and, underneath, by the database: `users.email`
is UNIQUE, and a second unique index `users_email_nocase` refuses two rows that differ only in letter case (a safety net for any
future code path that forgets to clean an address). A database that already holds such a pair cannot get the index; the server still
starts and its log says to run the audit. Tested: 20 sign-ups for one address at the same instant from 20 threads, from 20 separate
processes on one file, and over HTTP (three spellings), and ten password sign-ups racing ten Google sign-ins: always exactly one account.

## Google
- An account is found by Google's permanent account number (`sub`) first. A Google account whose email later changes keeps opening the
  same UAply account; it never makes a second one, even if someone has since made an account with the new address (that one is not
  touched).
- A new `sub` with an address Google is the authority on (Gmail, or a Workspace account) joins the one account with that exact address.
  If that account's password was never proven (no code, no reset link), the password is removed and its sessions end, because whoever
  chose it never showed they own the address. A proven password is kept.
- An address Google is not the authority on (a personal Google account registered with some other provider's address) cannot join an
  existing account ("That email already has a UAply account"); a new account made with it starts unverified.
- An email Google has not verified is refused.
- Known and accepted: a Workspace administrator who gives a departed employee's address to someone new hands over that address's UAply
  account too, exactly as Forgot password would. Gmail addresses are never reissued.

## Deleting and signing up again
Deleting removes the account, its sessions, codes, reset links, Google links (database cascade) and its application records. Account
numbers are never reused (SQLite AUTOINCREMENT), so signing up again with the same address makes a fresh, unverified, free account with
a new number. Stripe objects now carry the account's address next to its number (`uaply_email`), and the webhook accepts the number only
when the address matches: if an accounts file were ever lost (a host without a disk), a restarted numbering can never hand one
person's subscription to another. Older objects that carry only the number still work.

## A mailbox the person keeps
1. **Proof of possession:** the 6-digit code (or Google, for addresses Google is the authority on). Unchanged.
2. **Privacy relays always pass** (`tools/data/relay-domains.txt`: Apple Hide My Email `privaterelay.appleid.com`, DuckDuckGo `duck.com`,
   Firefox Relay `mozmail.com`, SimpleLogin, addy.io, Proton Pass). They forward to a real inbox, and Sign in with Apple produces them.
   This list is consulted first. Role addresses (`info@`, `support@`) are real mailboxes and pass.
3. **Throwaway domains are refused** (`tools/data/disposable-domains.txt`, and any domain under one): "Please use an email address you'll
   keep — temporary addresses can't be used for job applications." Every entry was checked to be in the community-maintained list at
   https://github.com/disposable-email-domains/disposable-email-domains (CC0, the list PyPI uses, evidence required per entry), never the
   large auto-generated lists, which flag relays and obscure real domains. The owner edits the file by hand; edits apply without a restart.
4. **A domain that cannot receive mail is refused before any code is sent**, on a public server that really sends email (or with
   `UAPLY_DNS_CHECK=on`). UAply asks DNS over HTTPS (`https://dns.google/resolve`, then `https://cloudflare-dns.com/dns-query`; 3 seconds
   each) for an MX record, then an A or AAAA record (RFC 5321 lets mail go to the domain's own address). A null MX (`0 .`) counts as no
   MX. "No such domain", or neither record: refused, with a sentence that suggests checking the spelling. Any timeout or resolver error:
   **let through** and one line in the log. Verdicts are remembered for a day. No mail server is ever contacted (port 25 is blocked on
   Render, and probing gets a server blocklisted). Only the domain goes to Google and Cloudflare, never the address.
5. **At most 40 sign-up tries an hour per visitor address** on a public server (a campus or office shares one address), and at most 5 for
   one email from one address; 10 on the owner's own computer, where every request comes from 127.0.0.1. Verification codes: 3 an hour per
   account, 80 per address, 5 per address and email. The visitor address is the last hop the host's proxy added to X-Forwarded-For (an
   internal 10.x/172.16-31.x/192.168.x/100.64.x hop after it is skipped), or CF-Connecting-IP when that hop is one of Cloudflare's published
   ranges (read at start and every 24 hours; a built-in copy otherwise). Entries the sender wrote are never used (`serve.client_ip`).
   Each address counts on its own for these limits, IPv6 ones too (only the site's share in item 6 groups an IPv6 /64).
6. **At most 500 code emails an hour for the whole site** (`UAPLY_CODE_SENDS_PER_HOUR`), every route and visitor together: past it, a
   code request gets "UAply is sending a lot of sign-in codes right now. Try again in a few minutes, or use Continue with Google."
   **One visitor may use at most its share of that hour**: 5% of it (`SITE_SHARE_PERCENT`), but never less than the 80 one connection
   may send anyway (item 5), so a campus behind one address keeps its 80; at the default 500 the share is 80. For the share an IPv6
   visitor counts by its /64 (`auth_api.share_key`: one home, carrier or server is given a whole /64), so fresh addresses of one /64
   cannot use the hour up; past its share it gets the plain code limit answer. The site-wide cap stays the backstop. **The owner
   of an account is never held back by the site's hour or the share**: a device with the known-device cookie for that address, or one
   signed in to that address's verified account, still gets its code. A session of an account nobody proved yet is no pass (anyone
   can open one). The password sign-up's first code counts toward the hour but is never refused by it, as before.
7. **Google joining an account whose address was never proven** (opened with a password, or with no password, and no code typed) asks
   the person for their own 18+ / Terms tick first, and records that tick (`terms_at`); `oauth_login` says `created` only when it made
   the account, so a page never calls an older account new.

## Checking a live disk
On Render: Shell, then `python tools/audit-accounts.py /var/data` (add `--full` to see whole addresses; they are masked by default).
It opens every `<instance>/uaply.db` read-only and reports DUPLICATE (same canonical address), NOT CANONICAL, GOOGLE LINK (one Google
account on two UAply accounts) and ORPHAN rows, plus a note for inboxes with several accounts (allowed, listed for information). Exit
code 0 means every address is one account; 1 means something needs a look; nothing is ever changed.

## Not done
- The full community throwaway list (about 4,000 domains) is not pasted in; the file has the best-known 123, each confirmed in it.
- The Privacy Policy should mention that the domain of a new address is looked up through Google Public DNS and Cloudflare (attorney
  review).
- A note in the code email ("this inbox already has a UAply account as ...") would warn the inbox owner, and only them, about +tag
  accounts; not built.
