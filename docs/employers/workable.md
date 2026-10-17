# Workable

[Back to the employer kit](README.md)

## What UAply sends
For each person who applies to one of your Workable jobs through UAply, UAply reads that job's questions with your token, then creates one
candidate on that job through Workable's API (`POST /spi/v3/jobs/{shortcode}/candidates`), marked as **applied**, not as sourced by a
recruiter:
- name, email, phone, the place they live, a headline and short summary
- the resume as a file (PDF, DOC, DOCX or RTF; any other type is sent as a link instead)
- school, degree and field of study; the most recent job with its title, company and start date
- their LinkedIn profile
- answers to your job's questions where the person's profile has them (yes/no, dropdown and multiple choice, text, numbers)
- the person's message as the cover letter, ending "Applied through UAply."
- the source, set to `UAply`

Never sent: gender, race or ethnicity, veteran status or disability status, even when a job question asks. A required file question
(other than the resume) is left to the person, and nothing is sent until it is answered on your page.

Because the candidate is marked as applied, Workable sends the person its usual "thank you for applying" email.

## Where you create the key
You must be an **Admin** in Workable. Click your profile icon (top right), then **Settings**, **Integrations**, **Apps**. In **API Access
Tokens**, click **Generate API token**, name it "UAply", pick an expiry, and tick only these two scopes:
- **r_jobs** (read your jobs and their questions)
- **w_candidates** (create candidates)

Copy the token right away: Workable shows it only once. Also tell us your subdomain, the first part of `yourcompany.workable.com` (it is also
the name in your careers page address, `apply.workable.com/yourcompany`).

Source: Workable's help article "Generating/revoking access tokens for Workable's API" and its API reference (job questions, create
candidate), read October 17, 2026.

## What the key can do
With those two scopes: read your jobs, their details, stages and questions, and create or change candidates (Workable's w_candidates scope
also allows comments, tags, moving and disqualifying). UAply only reads a job's questions when someone applies and creates that one candidate.
It never moves, rates, disqualifies or comments on anyone. If you would rather not give change rights over existing candidates, tell us:
Workable has no narrower scope for creating candidates, so the alternative is the [email or webhook route](email-and-webhook.md).

Workable's OAuth connection is reserved for its official partners. UAply is not one and does not use it; your own token is the only way
UAply connects.

## How to revoke it
Same page (**Settings**, **Integrations**, **Apps**, **API Access Tokens**): click the three dots next to the token, **Revoke token**,
then **Revoke**. Applications from UAply stop at once. Then tell us, so we delete our copy. A token also stops on its own when it expires.

## What you see per application
A new candidate in the **Applied** stage of that job, with the resume, the answers, education and experience filled in, and UAply as the
source. If the same email has already applied to that job, Workable refuses the duplicate and UAply tells the person.
