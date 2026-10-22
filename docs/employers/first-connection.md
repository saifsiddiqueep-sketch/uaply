# The first connected employer: Saif's own SmartRecruiters account

October 22, 2026. The goal for launch day: one real employer whose postings say **Apply instantly** in UAply, where a swipe right sends
the application into that employer's own hiring system. The quickest one we control is our own: UAply's company account on
SmartRecruiters, with one real posting. About 30 minutes. Nothing here costs money; stop and ask the owner if a step asks for a card.

## 1. The account and one posting (15 minutes)
1. Sign up at smartrecruiters.com for the free plan (SmartStart) as **UAply Technologies**, with the company address. You are its
   Administrator.
2. Publish one real job that UAply would really take applications for (for example a campus ambassador or a summer intern role), with
   a short screening question or two so the question box is exercised. A test-only posting would mislead people who apply.
3. Open your careers page: its address is `https://jobs.smartrecruiters.com/<identifier>`. Write down the identifier (the company
   identifier UAply needs). `https://careers.smartrecruiters.com/<identifier>` shows the same jobs.

## 2. The key (5 minutes), and the one thing to check first
1. As the Administrator: **Settings**, **Administration**, **Apps & Integrations**, **Credentials** (the Credential Manager), **New
   Credential**, **API Key**, name it "UAply", **Generate**.
2. SmartRecruiters shows the key **once**. Copy it straight into the connection (step 3); do not paste it into chat, email or a file
   in the repository.
3. **If there is no API Key option**: the free plan may not include API access (a pricing review says SmartStart has none; SmartRecruiters'
   own developer page does not say which plans have it). Then do not buy anything. Tell the owner, and for launch day use the email channel
   instead (`docs/employers/email-and-webhook.md`): our own recruiting address as the employer's `contact` in the employer list.
4. Know what the key can do: SmartRecruiters says an API key gives **full access** to the account's data (there is no narrower kind).
   UAply uses it only to read a posting's application form and to send candidates to it (`ats_api.py`), and never shows or logs it. That
   is one more reason to start with our own account.

## 3. Connect it and test it (5 minutes)
- **On this computer:** start the server, open `/setup`, box **Connect an employer's hiring system**: choose SmartRecruiters, type the
  identifier as the board name, paste the key, **Connect**. Then press **Test this connection** (or **Test** next to the saved
  connection). The answer should read: "<identifier> on SmartRecruiters: 1 open posting, and the key reads their application form."
  - "has no open postings right now": the posting is not published yet.
  - "Could not read ... open postings": the identifier is wrong.
  - "the key was refused": the key was copied wrong or deleted; make a new one.
- **On the hosted site** (Render, dashboard only, the owner's step): add the connection to the `UAPLY_ATS_JSON` setting, as
  `[{"kind": "smartrecruiters", "board": "<identifier>", "api_key": "<key>"}]`, save, and let the service restart. Then open
  `https://uaply.net/setup` with the owner password and press **Test** next to the saved connection (on the hosted site the test uses
  the saved key only; the key box stays empty).

## 4. Put the posting in the feed (one line, through a normal pull request)
UAply reads employers' boards from `job-boards.json`. Add our board so the posting appears in the deck:

    {"kind": "smartrecruiters", "token": "<identifier>", "name": "UAply Technologies", "total": 1, "us": 1, "tri": 1, "checked": "2026-10-22"}

After the next feed read (boards in that file are read every 2 hours), the job's card says **Apply instantly**.

## 5. Check it end to end, once
1. Record the consent the way the kit says (`docs/employers/consent-letter.md`): for our own account, a line in the owner's tracker with
   the date and who agreed is enough.
2. With a test person's account (not a real applicant), swipe right on our posting. The Job Tracker should say **Sent**, and the
   candidate should appear on the posting in SmartRecruiters with the resume and the screening answers.
3. Withdraw that test candidate in SmartRecruiters afterwards.

## 6. To stop
Delete the key in the Credential Manager (sending stops at once), remove the connection on `/setup` (or from `UAPLY_ATS_JSON`), and
remove the line from `job-boards.json`.
