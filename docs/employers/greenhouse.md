# Greenhouse

[Back to the employer kit](README.md)

## What UAply sends
For each person who applies to one of your Greenhouse postings through UAply, one application to that posting through Greenhouse's Job
Board API, the same route your own careers page uses:
- first name, last name, email, phone
- the resume as a file
- answers to your posting's own questions where the person's profile has them: LinkedIn, website, current employer and job title, work
  authorization, sponsorship, country, willingness to relocate, how they heard of the job, and expected pay only when your form requires it
- the fields your careers page fills in on its own: the two-letter country code, the location with its map position (from the person's
  ZIP code), and the most recent job

Never sent: answers to Greenhouse's voluntary demographic (EEOC) questions, or any gender, race, veteran or disability question.

## Where you create the key
Greenhouse Recruiting: **Configure** (the gear), **Dev Center**, **API Credential Management**, create a new credential of type
**Job Board API**. Copy it once and send it to UAply as the consent letter describes. Also tell us your board name, the part after
`boards.greenhouse.io/` in your job board address.

## What the key can do
A Job Board API key submits applications to your public job board's postings. It cannot read your candidates, change your jobs or see
anything in Greenhouse Recruiting beyond what the public board shows. UAply uses it only to submit applications.

## How to revoke it
Same page (**Configure**, **Dev Center**, **API Credential Management**): find the key and remove or deactivate it. Applications from
UAply stop at once. Then tell us, so we delete our copy.

## What you see per application
A new applicant on that job, with the resume attached and the answers filled in, as if the person had used your careers page. The person
also gets an email from UAply listing exactly what was sent.
