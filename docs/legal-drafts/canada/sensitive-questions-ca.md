**DRAFT — not reviewed by counsel**

# Sensitive questions: never auto-filled (Canada)

Note: a search of this worktree for "Needs you" found no existing code. This is a new spec. The US rule today is "UAply never answers voluntary self-identification questions" (legal/terms.html:25).

## The rule

UAply never fills these in. Each one is marked **Needs you**. The application is not sent until the user answers or skips it. UAply never guesses.

1. **Social Insurance Number (SIN).** We never ask for, collect or store a SIN.
2. **Work eligibility in Canada.**
3. **Date of birth or age.**
4. **Self-identification and employment-equity questions:** women, Indigenous peoples, persons with disabilities, members of visible minorities.
5. **Disability or accommodation.**
6. **Criminal record or background check.**

## User-facing text

**Needs you (general):** "This question is sensitive. We did not answer it. Answer it yourself, or leave it blank if the employer allows."

**SIN:** "This form asks for a Social Insurance Number. UAply never asks for, collects or stores a SIN. We stopped. Give your SIN only directly to the employer, and only after you get a job offer."

**Self-identification:** "These questions are voluntary. We did not answer them. You choose whether to answer."

## Behaviour

- Detector runs on every employer question before auto-fill.
- On a match: leave the field empty, add it to Needs you, and block sending until the user acts.
- SIN match: also stop the whole application, show the SIN text, and log the event (no SIN value stored, ever).
- If the user types a value in a Needs-you field, it goes to the employer only. Do not save it to the profile or logs. [TO FILL: confirm.]
- Be cautious: if unsure whether a question is sensitive, treat it as sensitive.
- Never log the answer text of these fields.

## Detector patterns (case-insensitive, ignore accents)

| Category | English | French |
|---|---|---|
| SIN | social insurance number, SIN, SIN number, social insurance no, \b\d{3}[- ]?\d{3}[- ]?\d{3}\b (nine digits) | NAS, numéro d'assurance sociale, no d'assurance sociale, n° d'assurance sociale |
| Work eligibility | legally authorized to work in Canada, eligible to work in Canada, work permit, work authorization, study permit, PGWP, permanent resident, citizen of Canada, require sponsorship | autorisé à travailler au Canada, admissible à travailler, permis de travail, permis d'études, résident permanent, citoyen canadien, parrainage |
| Date of birth / age | date of birth, DOB, birth date, birthday, how old are you, are you over 18, age | date de naissance, âge, quel âge, avez-vous 18 ans, majeur |
| Self-identification | self-identify, self-identification, employment equity, equity-seeking, visible minority, racialized, Indigenous, First Nations, Métis, Inuit, Aboriginal, woman, gender, race, ethnicity, LGBTQ, 2SLGBTQ+, veteran | auto-identification, équité en matière d'emploi, minorité visible, personne racisée, Autochtone, Premières Nations, Inuit, Métis, femme, genre, sexe, origine ethnique |
| Disability / accommodation | disability, disabled, accommodation, accessibility needs, medical condition | handicap, situation de handicap, invalidité, mesure d'adaptation, mesures d'accommodement, besoins d'accessibilité, état de santé |
| Criminal record | criminal record, criminal history, convicted, conviction, pardon, record suspension, background check, police check, vulnerable sector | casier judiciaire, antécédents judiciaires, condamné, condamnation, pardon, suspension du casier, vérification des antécédents, vérification policière |

Notes for the engineer:
- Match the question label, helper text, and option labels.
- Prefer false alarms to misses.
- "age" and "SIN" and "woman" are short and can match inside other words. Use word boundaries.
- Test with French labels and with accents removed ("numero d'assurance sociale").
- Add a test list of real employer forms. [TO FILL]
