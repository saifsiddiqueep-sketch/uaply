# Email or webhook (any hiring system, or none)

[Back to the employer kit](README.md)

Use this when your hiring system is not on the list, or you do not want to give UAply a key. You can choose email, a webhook, or both. With
both, the application counts as sent when at least one of them accepts it.

## What UAply sends
The applicant's name, email, phone, job title, location, years of experience, skills, headline and summary, education, links (resume,
LinkedIn, portfolio), work authorization, sponsorship, earliest start, country, willingness to relocate, most recent job, their message, the
match percentage, and the resume as a file. Expected pay only when your own form requires it. Any field can be empty: the person chooses what
to fill in.

Never sent: gender, race or ethnicity, veteran status or disability status.

## Email
Give UAply one recruiting address. Each application arrives as one email to that address, with the details in the message, the resume
attached, and Reply-To set to the applicant, so replying writes to them.

## Webhook
Give UAply an HTTPS address and a secret. Each application is POSTed there as JSON with these headers:
- `X-UAply-Delivery`: a unique id per application (use it to ignore a repeat)
- `X-UAply-Timestamp`: when it was sent, in seconds since 1970 (reject anything older than a few minutes)
- `X-UAply-Signature`: `sha256=` and a hex HMAC-SHA256 of `timestamp + "." + body`, keyed with your secret

Answer with any 2xx status. If your system fails, UAply tries again up to three times (after 1 and 3 seconds); a 4xx answer other than 408
or 429 is final. Redirects are not followed. The full body is in [EMPLOYERS.md](../../EMPLOYERS.md#the-webhook-in-detail).

## Where you "create the key"
There is no key on your side for email. For the webhook, you choose the secret (a long random string) and give it to UAply with the address.

## What it can do
UAply can only send to the address you gave. It cannot read anything from your systems.

## How to revoke it
Email: tell us, or simply stop reading that address or filter it. Webhook: answer 410 or turn off the address (UAply treats a 4xx as final),
and tell us. We remove you from the employer list, and nothing more is sent.

## What you see per application
Email: one message per applicant, resume attached. Webhook: one signed POST per applicant, in the shape above.
