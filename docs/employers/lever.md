# Lever

[Back to the employer kit](README.md)

## What UAply sends
For each person who applies to one of your Lever postings through UAply, one application through Lever's Postings API:
- name, email, phone
- current company, LinkedIn and portfolio links, a resume link if the person gave one
- the resume as a file
- a comment with the person's message, their short summary and the line "Applied through UAply."
- the source, set to `UAply`

Lever's Postings API does not carry a posting's custom questions, so none are answered. Nothing about gender, race, veteran or
disability status is sent.

## Where you create the key
Lever: **Settings**, **Integrations and API**, the **API Credentials** tab, **Generate new key** under the Postings API. Only a
**Super Admin** can do this. Also tell us your site name, the part after `jobs.lever.co/` in your job site address.

## What the key can do
A Postings API key submits applications to your published postings. It does not open the rest of Lever's API (candidates,
opportunities, notes). UAply uses it only to submit applications.

## How to revoke it
Same tab (**Settings**, **Integrations and API**, **API Credentials**): delete the key. Applications from UAply stop at once. Then tell
us, so we delete our copy.

## What you see per application
A new opportunity on that posting with the resume attached, the source shown as UAply, and the person's message in the comments.
