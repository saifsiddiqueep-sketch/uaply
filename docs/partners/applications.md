# Partner applications: the answers pack

October 23, 2026. For Saif, to file each form in a few minutes. The fields were read from the live forms on October 23 (nothing was
typed into them or sent). Answers come from this repository. **[BLANK: ...]** marks what only you can fill in. File in this order:
SmartRecruiters, Ashby, Lever (the order and the reasons are on the swipe page: SmartRecruiters is 29.6% of our jobs and lets job boards
register; Ashby 4.8% and Lever 4.5%; Greenhouse 14.0% waits for one employer that uses Greenhouse to connect).

## Answers used in every form

| Item | Answer |
|---|---|
| Company name | UAply ([BLANK: company legal name], the name the Terms and Privacy Policy carry once filled in) |
| Address | [BLANK: street address], [BLANK: city, state, ZIP] (also a blank in legal/terms.html and legal/privacy.html) |
| Website | https://uaply.net |
| Privacy Policy | https://uaply.net/legal/privacy.html |
| Terms of Service | https://uaply.net/legal/terms.html |
| For employers | https://uaply.net/legal/employers.html |
| Technical and business contact | uaplytechnologies@uaply.net |
| Your name, phone, LinkedIn | [BLANK: Saif's first and last name], [BLANK: phone], [BLANK: LinkedIn profile URL] |
| Region | North America (United States) |
| Company size | [BLANK: number of people, for example 2] |
| Connect kit (what an employer does to connect) | docs/employers/connect-kit.pdf in the repository; the system pages are docs/employers/smartrecruiters.md, ashby.md and lever.md |

**About UAply (one paragraph).** UAply is a job app for students and early-career people in the United States. It shows one job at a time;
a swipe right starts an application. Listings come from employers' own public hiring systems and careers pages, and every card shows how
well the job fits the person's profile and how it would be sent. Accounts need a confirmed email address, and each person agrees before
their first application that UAply may submit applications on their behalf with the information they provide.

**The integration (one paragraph).** UAply is a job board that submits applications on behalf of candidates, with their recorded consent,
through your Application API, for employers who connect. For a connected employer, UAply reads the posting's application form (screening
questions, required consents), asks the candidate for anything their profile does not answer, and sends one application: name, email,
phone, location, links, education, the resume file and the screening answers. It never answers voluntary self-identification (diversity)
questions, never accepts an optional consent for the person, and never touches a human check. Employers switch it off by revoking the
credential.

**Expected volume.** A few hundred users in the first weeks, students on Philadelphia campuses (testers from October 25, 2026); tens of
applications a day across all employers at first, at most a few per minute.

**App description (Google Play short description).** "Swipe right to apply to real jobs that match your profile. Free in early access."
The full text is mobile/store/play/text/full-description.txt.

## 1. SmartRecruiters: partner registration

Form: https://partnerhub.smartrecruiters.com/aspx/SmartRecruitersRegistration (SmartRecruiters' marketplace page offers online
registration for job boards, assessment providers and recruitment agencies; the smartrecruiters.com partner link now sends to SAP's partner
program, which is not the one to use).

| Step and field | Answer |
|---|---|
| Page 1: email (the only field, then Next) | uaplytechnologies@uaply.net |
| Later pages: not visible without starting the sign-up | The page then asks whether you work for one of SmartRecruiters' listed organizations (answer: no) and continues with company details. Use the table above: company name, address, website, contact, region, size, partner type **Job board**, and the two paragraphs. |

What we ask for: Application API access (scope `candidate_applications_manage`) with customer-level credentials for employers who connect,
and a job-board listing in the Marketplace.

## 2. Ashby: integration partner

Form: https://share.hsforms.com/1AWsUTHXYSi6glbzTAI7J1A2yz21 (the "Reach out about integrating" button on
https://www.ashbyhq.com/integrations-directory). Not the general partner form on ashbyhq.com/partners: its program list has no
integration option.

| Field | Answer |
|---|---|
| First name*, Last name* | [BLANK: Saif's first name], [BLANK: last name] |
| Email* | uaplytechnologies@uaply.net |
| Company name* | UAply ([BLANK: company legal name]) |
| Website* | https://uaply.net |
| What integration are you looking to build? | The integration paragraph above, plus: "Using applicationForm.submit, with the employer's API key (candidatesWrite), for Ashby customers who choose to connect." |
| Integration Category | Job Boards |
| (Where you are) Just exploring / In planning / In development / Already built | In development (UAply's Ashby connector exists and is tested against a stand-in: ats_api.py, tools/test-ats-ashby.py) |
| How did you hear about us?* | "Ashby's API documentation and integrations directory; many of the employers our users apply to use Ashby." |
| How many customers do you have using Ashby today? | 1-50 is the lowest option. Honest answer: none connected yet; say so in the integration text ("first employers being contacted now"). |

## 3. Lever: partnership interest

Form: https://lever.co/partnershipinterest (every field is marked required).

| Field | Answer |
|---|---|
| First Name, Last Name | [BLANK: Saif's first name], [BLANK: last name] |
| Email Address | uaplytechnologies@uaply.net |
| Official Company Name | [BLANK: company legal name] (UAply) |
| Phone Number | [BLANK: phone] |
| Website | https://uaply.net |
| Company Description | The "About UAply" paragraph above |
| Primary Target Market (Region) | North America |
| Nature of your product | Job Board & Aggregators |
| Company Size | [BLANK: number of people] |
| Number of Mutual Customers | The lowest option is 1-10; we have none connected yet. Choose 1-10 only once one Lever employer has agreed to connect; until then, say "0 today" in the integration description. |
| Top Mutual Customers | "None connected yet; first Lever employers are being contacted" ([BLANK: names, once any agree]) |
| Describe how the product integration would work | The integration paragraph above, plus: "OAuth with each customer's authorization; we read the posting's application form and create the application with the resume; we never touch EEO questions." |
| Signup For Sandbox Account | Yes |
| Email Provider | [BLANK: the provider behind uaplytechnologies@uaply.net] |
| Email for Employ Sandbox Admin | uaplytechnologies@uaply.net |
| Receive latest HR news and insights | Leave unticked |

## After acceptance: what each program expects

- **SmartRecruiters:** partner-level (master) credentials from their partner team, used only to exchange customer-level credentials;
  each employer grants permission before UAply may act for it. The Application API asks for the employer's privacy-notice consent text and
  the diversity questions shown last, and allows 8 concurrent calls.
- **Ashby:** a review of fit by the integrations team, then (if accepted) publishing the integration to Ashby's customers; each employer
  still creates its own API key with candidatesWrite.
- **Lever:** an OAuth sandbox; then build, submit for production with a help-centre article, sandbox logins for Lever's team, an
  ecosystem listing and support details; a QA call; production credentials. A released integration is required to stay a partner.
- **Greenhouse (later):** at least one mutual customer and a privacy policy before applying; reviews on the first Monday of each month,
  answer within 7 business days; then the Greenhouse Partnership Agreement, the Partner Portal and a sandbox. Each employer's Job Board API
  key is still what submits an application.

Sources: the research of October 23 on the swipe page (SmartRecruiters developer docs on partner credentials and the Application API,
greenhouse.com/integration-partner, Lever's partner developer page, Ashby's custom careers page docs).
