# Ashby

[Back to the employer kit](README.md)

## What UAply sends
For each person who applies to one of your Ashby postings through UAply, UAply first reads that posting's application form with your
key (Ashby's public job board does not include the form), then submits it through `applicationForm.submit`:
- name, email, phone
- the resume as a file
- answers to your form's questions where the person's profile has them (the same list as for Greenhouse: links, current job, work
  authorization, sponsorship, country, relocation, how they heard, expected pay only when required)
- a tracking tag `utm_source=UAply`

Never sent: Ashby's voluntary EEOC survey (a separate form UAply never touches), or any gender, race, veteran or disability question in the
main form.

## Where you create the key
Ashby: **Admin**, **Integrations**, **API Keys**, create a key. Give it only the **Candidates write** and **Jobs read** permissions.
Also tell us your board name, the part after `jobs.ashbyhq.com/` in your job board address.

## What the key can do
With those two permissions: read your job postings (including their application forms) and create candidates and applications. Do not
give it more. UAply uses it only to read a posting's form at the moment someone applies, and to submit that application.

## How to revoke it
**Admin**, **Integrations**, **API Keys**: delete or disable the key. Applications from UAply stop at once. Then tell us, so we delete our
copy.

## What you see per application
A new application on that job with the resume attached, the form answered, and UAply in its source tracking. If you limit how many times one
person may apply, Ashby blocks extra ones as usual and UAply tells the person it was not sent.
