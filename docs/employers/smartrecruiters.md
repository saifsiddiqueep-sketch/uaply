# SmartRecruiters

[Back to the employer kit](README.md)

## What UAply sends
For each person who applies to one of your SmartRecruiters postings through UAply, UAply reads that posting's screening questions and
consent settings with your key, then sends one candidate through the Application API:
- first and last name, email, phone, city
- LinkedIn and website, school and degree
- the resume as a file
- answers to your screening questions where the person's profile has them
- the person's message to the hiring manager, ending "Applied through UAply."
- your required privacy consent, only when the person gave it (themselves, or by switching on "Acknowledge employers' notices for me")

Never sent: questions you marked as diversity questions, and optional consents (a talent pool, text messages). Work history is not sent,
because SmartRecruiters needs a start date for each job and UAply's profile does not hold one.

## Where you create the key
SmartRecruiters: **Settings**, **Admin**, **Credential Manager**, create an **Application API** key. Also tell us your company identifier,
the part after `jobs.smartrecruiters.com/` in your careers address.

## What the key can do
An Application API key reads a posting's application configuration and submits candidates to postings. UAply uses it for nothing else.

## How to revoke it
**Settings**, **Admin**, **Credential Manager**: delete or deactivate the key. Applications from UAply stop at once. Then tell us, so we
delete our copy.

## What you see per application
A new candidate on that posting with the resume, the screening answers, the consent recorded as given, and the person's message.
