**DRAFT — not reviewed by counsel**

# Consent screen: first apply to each employer (Canada)

Shown before the first apply to a given employer, every time that employer is new to the user. This is in addition to the one-time first-swipe agreement (US text: consent_api.py:26-42, VERSION 6). [TO FILL: counsel to say whether this replaces or adds to it for Canada.]

## Screen copy

**Heading:** Apply to {Employer name}?

**Body:**

You swiped right on **{Job title}** at **{Employer name}**. If you continue, UAply will apply for you.

What we send:
- Your profile details: {list of fields for this job, for example name, email, phone, work history, education, skills}
- Your resume: {file name}
- Your answers to this employer's screening questions: {count} answers. You can review them first.

{Employer name} is a separate company. It has its own privacy policy: [Read {Employer name}'s privacy policy]. Once it has your details, its policy applies, not ours.

{Employer name} is in {country}. This may be outside Canada, and your information may be stored there.

To stop: turn off "Send applications for me" in Profile, Account. To stop for this employer only, tap "Never send to {Employer name}" in Profile, Account, Employers. Applications already sent cannot be recalled.

See everything we sent: [What we sent]

**Checkbox (unchecked by default):**
[ ] I agree that UAply may send the information above to {Employer name}.

**Buttons:**
- Primary: **Send application** (disabled until the box is checked)
- Secondary: **Save to Job Tracker only**
- Link: **Cancel**

## How it behaves

- Shown before the first apply to each employer, not before later ones to the same employer.
- Checkbox starts unchecked. The send button stays off until it is checked.
- If the user picks "Save to Job Tracker only" or Cancel, nothing is sent.
- Employer name, country, privacy-policy link and field list are filled from the job. If the privacy-policy link or country is unknown, show "Not available" and do not send until the user confirms. [TO FILL: counsel to confirm this rule.]
- Questions on the Needs-you list (sensitive-questions-ca.md) are left for the user and are not in the "what we send" list.
- The choice is saved: user, employer, time, wording version, what was listed.
- Per-employer "Never send" turns this employer off. "Send applications for me" off turns all off.
- Every send appears in "What we sent" history.
- Undo countdown stays as in the US app.
