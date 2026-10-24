"""Autofill: real employers' application forms answered from a UAply profile (autofill.py), and what a swipe right does with them.
  python tools/test-autofill.py
Uses public Greenhouse forms saved in tools/fixtures/greenhouse-forms.json (no internet needed) and the stand-in hiring system (mock-ats.py)."""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8797                # another port can be given, so two test runs never collide
os.environ["UAPLY_ATS_BASE_GREENHOUSE"] = "http://127.0.0.1:%d" % PORT
os.environ["UAPLY_ATS_BASE_LEVER"] = "http://127.0.0.1:%d" % PORT
os.environ["UAPLY_DATA_DIR"] = tempfile.mkdtemp()
os.environ["UAPLY_CONFIG_JSON"] = json.dumps({"delivery": "test", "smtp": {}, "owner_copy": "", "feeds": []})
sys.path.insert(0, ROOT)
import autofill        # noqa: E402
import ats_api         # noqa: E402
import jobs_api        # noqa: E402
import uaply_api       # noqa: E402

FORMS = json.load(open(os.path.join(HERE, "fixtures", "greenhouse-forms.json"), encoding="utf-8"))["forms"]
ok = bad = 0


def t(name, got, want):
    global ok, bad
    if got == want:
        ok += 1
        print("PASS", name)
    else:
        bad += 1
        print("FAIL", name, "\n   got: ", repr(got)[:300], "\n   want:", repr(want)[:300])


CAND = {"name": "Sam Rivera", "email": "sam@example.com", "title": "Software Engineer Intern", "loc": "Philadelphia, PA", "edu": "Bachelor", "years": 1,
        "ext": {"phone": "+1 215 555 0100", "linkedin": "https://www.linkedin.com/in/sam-rivera", "portfolio": "https://github.com/samrivera",
                "school": "Drexel University", "major": "Computer Science", "grad": "2027-06", "gpa": 3.6, "auth": "citizen", "sponsor": "no",
                "start": "grad", "zip": "19104", "state": "PA", "relocate": "yes", "office": "yes", "former": "no", "govt": "no", "phd": "no", "ack": True,
                "summary": "Computer science student who builds web apps.", "why": "I want to work at {company} because the {role} role fits what I build."}}
RESUME = ({"name": "resume.pdf", "type": "application/pdf", "size": 40}, b"%PDF-1.4 a small test resume for the autofill tests")


def plan(board, cand=CAND, answers=None, resume=RESUME):
    f = FORMS[board]
    return autofill.plan_greenhouse(f, cand, {"co": f["company_name"], "role": f["title"]}, "", resume[0], resume[1], answers)


def item(p, pattern):
    for i in p["items"]:
        if re.search(pattern, i["q"], re.I):
            return i
    return None


def field_for(board, pattern):
    """The Greenhouse field name of the question whose label matches."""
    for q in FORMS[board]["questions"]:
        if re.search(pattern, q["label"], re.I):
            return q["fields"][0]["name"]
    return None


def cand_with(**ext):
    c = json.loads(json.dumps(CAND))
    c["ext"].update(ext)
    return c


# ---- the standard part of every form -----------------------------------------------------------------------------------------------------
p = plan("waymo")
got = dict(p["fields"])
t("first and last name, email and phone are filled in", (got.get("first_name"), got.get("last_name"), got.get("email"), got.get("phone")),
  ("Sam", "Rivera", "sam@example.com", "+1 215 555 0100"))
t("the resume file goes in as a file", [f[0] for f in p["files"]], ["resume"])
t("the location's hidden map position is worked out from the ZIP code (Philadelphia area)", (round(float(got["latitude"])), round(float(got["longitude"]))), (40, -75))
t("hidden fields are never shown to the person as questions", any(i["q"] in ("Latitude", "Longitude") and not i.get("skip") for i in p["items"]), False)

# ---- questions whose options are whole sentences --------------------------------------------------------------------------------------------
# a question exactly as one Waymo posting asks it (its options are sentences)
WA = {"company_name": "Waymo", "title": "Intern", "location_questions": [], "questions": [{"required": True, "label": "Work Authorization", "fields": [
    {"name": "question_1", "type": "multi_value_single_select", "values": [
        {"label": "I am authorized to work for any employer in the country in which this position is based.", "value": 1},
        {"label": "I require, or in the future will require, Waymo's sponsorship to obtain work authorization in the country in which this position is based (e.g. H-1B, TN, etc.)", "value": 2},
        {"label": "My status to work in the country in which this position is based is unknown.", "value": 3}]}]}]}
wa = autofill.plan_greenhouse(WA, CAND, {"co": "Waymo"})["items"][0]
t("Work authorization (options are sentences): picks 'authorized to work for any employer'", wa["a"].startswith("I am authorized to work for any employer"), True)
wa2 = autofill.plan_greenhouse(WA, cand_with(sponsor="yes"), {"co": "Waymo"})["items"][0]
t("...and someone who needs sponsorship gets the sponsorship sentence instead", wa2["a"].startswith("I require"), True)
# ---- the start date from Profile, Account's "When can you start?" (apply journey, October 22) ----------------------------------------------
# the readiness checklist accepts that notice as the start date; the filler used to read only Profile setup's coded one and asked again
SD = {"company_name": "Acme", "title": "Analyst", "location_questions": [], "questions": [{"required": True, "label": "When can you start?",
      "fields": [{"name": "question_9", "type": "input_text", "values": []}]}]}
x_notice = uaply_api._ext({"notice": "2 weeks"})
sd = autofill.plan_greenhouse(SD, dict(CAND, ext=dict(CAND["ext"], start="", notice=x_notice.get("notice", ""))), {"co": "Acme"})
t("start date: with only the notice from Profile, Account ('2 weeks'), the form gets 'Within 2 weeks' and nothing is asked",
  ([i["a"] for i in sd["items"] if i["q"] == "When can you start?"], len(sd["missing"])), (["Within 2 weeks"], 0))
sd2 = autofill.plan_greenhouse(SD, dict(CAND, ext=dict(CAND["ext"], start="now", notice="2 months or more")), {"co": "Acme"})
t("...and Profile setup's own start date still comes first when both are set", [i["a"] for i in sd2["items"] if i["q"] == "When can you start?"], ["Immediately"])
t("...and a notice that is not one of the four choices is dropped", uaply_api._ext({"notice": "<b>tomorrow</b>"}).get("notice"), "")
reg = item(p, r"state/region in which you currently reside")
t("a state list without the person's state: 'Another State in the US' (never a wrong state)", reg and reg["a"], "Another State in the US")
st = item(plan("affirm"), r"state or canadian province")
t("a US state asked as a list of full names: PA becomes Pennsylvania", st and st["a"], "Pennsylvania")
fe = item(plan("affirm"), r"previously been employed at affirm")
t("'Have you worked here before' with sentence options: 'I have not previously been employed'", fe and fe["a"], "I have not previously been employed at Affirm")
gv = item(plan("coinbase"), r"current government official")
t("government official: answered No from the profile", gv and gv["a"].lower().startswith("no"), True)

# ---- careful cases ---------------------------------------------------------------------------------------------------------------------------
sp = item(plan("imc"), r"immigration sponsorship to begin")
t("a sponsorship question that mentions OPT is still answered as sponsorship", sp and sp["a"], "No")
opt = item(plan("duolingo"), r"optional practical training")
t("an OPT question for a US citizen is answered No (it only applies to student visas)", opt and opt["a"], "No")
opt2 = item(plan("duolingo", cand_with(auth="authorized")), r"optional practical training")
t("...but for someone on a visa it is left for the person", (opt2["a"], opt2["need"]), ("", True))
eeo = [i for i in plan("dropbox")["items"] if re.search(r"gender|race|veteran|disabilit|hispanic", i["q"], re.I)]
t("voluntary self-identification is never answered", all(not i["a"] for i in eeo), True)
ack_on = item(plan("waymo"), r"candidate privacy policy")
ack_off = item(plan("waymo", cand_with(ack=False)), r"candidate privacy policy")
t("a privacy-notice acknowledgment is ticked only when the person chose that", (bool(ack_on["a"]), ack_off["a"], ack_off["need"]), (True, "", True))
ai = item(plan("coinbase"), r"best describes how you use ai tools")
t("a real question that mentions AI is not mistaken for an acknowledgment", (ai["a"], ai["need"]), ("", True))
essay = item(plan("duolingo", cand_with(why="")), r"why are you interested in duolingo")
t("an essay question is never invented", (essay["a"], essay["need"]), ("", True))
essay2 = item(plan("duolingo"), r"why are you interested in duolingo")
t("...but the person's own 'why' template is used, with the company filled in", "Duolingo" in essay2["a"], True)
nozip = plan("waymo", cand_with(zip=""))
t("with no ZIP code, the ZIP code is asked once (not latitude and longitude)", [m["q"] for m in nozip["missing"] if "ZIP" in m["q"]],
  ["Your ZIP code (the employer's form uses it for your location)"])
t("...and the answer the person gives fills the map position", "latitude" in dict(plan("waymo", cand_with(zip=""), {"zip": "94103"})["fields"]), True)
no_resume = plan("waymo", cand_with(summary="", headline=""), resume=(None, None))
t("no resume file and none pasted: the resume question is asked", any(m["q"].startswith("Resume") for m in no_resume["missing"]), True)

# ---- the answers that most often stop an application: relocation, expected pay, country, location, current job ----------------------------
YN = [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}]
LOCQ = [{"required": True, "label": "Location", "fields": [{"name": "location", "type": "input_text", "values": []}]},
        {"required": True, "label": "Latitude", "fields": [{"name": "latitude", "type": "input_hidden", "values": []}]},
        {"required": True, "label": "Longitude", "fields": [{"name": "longitude", "type": "input_hidden", "values": []}]}]
READY = {"company_name": "Acme", "title": "Analyst", "location_questions": LOCQ, "questions": [
    {"required": True, "label": "Are you willing to relocate?", "fields": [{"name": "question_1", "type": "multi_value_single_select", "values": YN}]},
    {"required": True, "label": "What are your salary expectations?", "fields": [{"name": "question_2", "type": "input_text", "values": []}]},
    {"required": True, "label": "Which country do you currently live in?", "fields": [{"name": "question_3", "type": "multi_value_single_select", "values": [
        {"label": "United States of America", "value": 11}, {"label": "Canada", "value": 12}, {"label": "Other", "value": 13}]}]},
    {"required": True, "label": "What is your current job title?", "fields": [{"name": "question_4", "type": "input_text", "values": []}]},
    {"required": False, "label": "Dates of employment at your most recent employer", "fields": [{"name": "question_5", "type": "input_text", "values": []}]},
    {"required": True, "label": "Are you currently employed?", "fields": [{"name": "question_6", "type": "multi_value_single_select", "values": YN}]},
    {"required": False, "label": "Are you comfortable with the salary range for this role?", "fields": [{"name": "question_7", "type": "multi_value_single_select", "values": YN}]}]}
JOB = {"employer": "Acme Robotics", "job_title": "Support Engineer", "job_start": "2024-06", "country": "US", "salary": "85000"}


def ready(**ext):
    c = cand_with(**dict(JOB, **ext))
    return autofill.plan_greenhouse(READY, c, {"co": "Acme", "role": "Analyst"})


full = ready()
fd = dict(full["fields"])
t("relocation, expected pay, country, job title and 'currently employed' all come from the profile: nothing is asked", full["missing"], [])
t("...with the right answers", [fd.get("question_%d" % i) for i in (1, 2, 3, 4, 5, 6)],
  ["1", "85000", "11", "Support Engineer", "June 2024 to present", "1"])
t("a yes/no question that only mentions pay is never given a number", "question_7" in fd, False)
t("the plan says expected pay went to this employer (for the receipt)", full["salary_sent"], True)
bare = ready(relocate="", salary="", country="", zip="", state="", job_title="", job_start="", employer="")
asked = sorted(m["q"] for m in bare["missing"])
t("without those profile answers, each one is asked instead (and the ZIP code for the location)",
  [q for q in asked if not q.startswith("What is your current job title")],
  ["Are you currently employed?", "Are you willing to relocate?", "What are your salary expectations?", "Which country do you currently live in?",
   "Your ZIP code (the employer's form uses it for your location)"])
t("'current job title' falls back to the title the person is looking for", dict(ready(job_title="")["fields"]).get("question_4"), "Software Engineer Intern")
opt_pay = json.loads(json.dumps(READY))
opt_pay["questions"][1]["required"] = False
op = autofill.plan_greenhouse(opt_pay, cand_with(**JOB), {"co": "Acme"})
t("an optional pay question is left blank even when the profile has an amount", ("question_2" in dict(op["fields"]), op["salary_sent"]), (False, False))
t("a profile that left expected pay blank never sends an amount", ("question_2" in dict(ready(salary="")["fields"]), ready(salary="")["salary_sent"]), (False, False))
t("a country question for someone in Canada picks Canada", dict(ready(country="CA")["fields"]).get("question_3"), "12")


def geo_fields(p):
    d = dict(p["fields"])
    return {k: d[k] for k in ("country_short_name", "location", "latitude", "longitude") if k in d}


g = geo_fields(full)
t("hidden fields: country, location and its map position are all sent", (g.get("country_short_name"), g.get("location"), round(float(g["latitude"])), round(float(g["longitude"]))),
  ("US", "Philadelphia, Pennsylvania, United States", 40, -75))
t("...even on a form with no location box (Dropbox): all three location fields together", sorted(geo_fields(plan("dropbox", cand_with(**JOB)))),
  ["country_short_name", "latitude", "location", "longitude"])
t("no ZIP code: no location at all (Greenhouse ignores one without coordinates), the country still goes", sorted(geo_fields(ready(zip=""))), ["country_short_name"])
t("...and the ZIP code the person types when asked brings all three back",
  sorted(geo_fields(autofill.plan_greenhouse(READY, cand_with(**dict(JOB, zip="")), {"co": "Acme"}, answers={"zip": "94103"}))),
  ["country_short_name", "latitude", "location", "longitude"])
t("someone in Canada: the country is CA and a US ZIP code is not turned into a location", geo_fields(ready(country="CA")), {"country_short_name": "CA"})
t("country 'Other': no country code is guessed and no US location is made from the ZIP code", geo_fields(ready(country="other")), {})
t("an older profile with a US state but no country counts as the United States", geo_fields(ready(country="")).get("country_short_name"), "US")
for b in FORMS:                                                      # on every saved real form, the location fields go together or not at all
    for c in (CAND, cand_with(zip=""), cand_with(zip="", country="other")):
        n = len({"location", "latitude", "longitude"} & set(dict(plan(b, c)["fields"])))
        if n not in (0, 3):
            t("location fields together on %s" % b, n, 3)
t("on every saved form, location, latitude and longitude are sent together or not at all", True, True)

emp = {k: v for k, v in full["fields"] if k.startswith("employments")}
t("the most recent job goes in Greenhouse's employments list: company, title, start and 'current'", emp,
  {"employments[0][company_name]": "Acme Robotics", "employments[0][title]": "Support Engineer", "employments[0][start_date][month]": "6",
   "employments[0][start_date][year]": "2024", "employments[0][current]": "true"})
ended = {k: v for k, v in ready(job_end="2025-03")["fields"] if k.startswith("employments")}
t("...a job that ended has its end month instead of 'current'", (ended.get("employments[0][end_date][month]"), ended.get("employments[0][end_date][year]"),
                                                                  "employments[0][current]" in ended), ("3", "2025", False))
t("...and nothing is sent without a title or a start month", [any(k.startswith("employments") for k, _ in ready(**x)["fields"]) for x in ({"job_title": ""}, {"job_start": ""})],
  [False, False])
t("'currently employed' is No once the job has an end month", dict(ready(job_end="2025-03")["fields"]).get("question_6"), "0")
t("voluntary questions stay unanswered with the new profile answers too", all(not i["a"] for i in plan("dropbox", cand_with(**JOB))["items"] if i.get("skip") == "voluntary"), True)

# what the server keeps from the browser, and what the employer and the receipt see
x = uaply_api._ext(dict(CAND["ext"], **dict(JOB, job_end="2023-01")))
t("dates that cannot be right (an end before the start) are dropped, so a job never reads as current by mistake", (x["job_start"], x["job_end"]), ("", ""))
x = uaply_api._ext(dict(CAND["ext"], **dict(JOB, salary="lots", country="FR")))
t("expected pay must be a number and the country one of the listed ones", (x["salary"], x["country"]), ("", ""))
x = uaply_api._ext(dict(CAND["ext"], **JOB))
rows = dict(uaply_api._detail_rows({"name": "Sam", "email": "s@example.com", "ext": x}))
t("the receipt lists the country, the job title and dates there, relocation and (when sent) expected pay",
  [rows.get(k) for k in ("Country", "Most recent employer", "Job title there", "Dates there", "Willing to relocate", "Expected yearly pay")],
  ["United States", "Acme Robotics", "Support Engineer", "June 2024 to present", "Yes", "$85,000"])
hook = uaply_api._webhook_payload({"id": "a1", "at": 0, "job": {"id": 1, "role": "R", "co": "C", "loc": "", "url": "https://x"}, "candidate":
                                   {"name": "Sam", "email": "s@example.com", "ext": dict(x, salary="")}}, None)["applicant"]
t("the webhook carries the country, relocation and the most recent job, and no expected pay unless a form asked",
  (hook["country"], hook["willing_to_relocate"], hook["most_recent_job"], "expected_yearly_pay_usd" in hook),
  ("US", "yes", {"employer": "Acme Robotics", "title": "Support Engineer", "start": "2024-06", "end": "", "current": True}, False))

# ---- saved answers ---------------------------------------------------------------------------------------------------------------------------
first = plan("coinbase")
asked = {m["key"]: (m.get("opts") or ["yes"])[0] for m in first["missing"]}
again = plan("coinbase", answers=asked)
t("after the person answers the missing questions once, the same form is complete", again["missing"], [])
k_dbx = autofill.norm("Have you previously worked for Dropbox?", "Dropbox")
k_other = autofill.norm("Have you previously worked for Discord?", "Discord")
t("an answer about one employer (\"worked for Dropbox?\") is kept for that employer, not carried to another (October 22)", (k_dbx != k_other, k_dbx), (True, "{at dropbox} have you previously worked for {co}"))
# a long question whose 160-character cut lands right after a word (Block's "I certify ..." does): the key the browser saves the
# answer under must be the key the server looks it up by, or the same question comes back after every answer
long_q = "I certify that all of the information I have provided is correct and complete and realize that falsification or misrepresentation, including omission, on this or any other personnel record"
k_long = autofill.norm(long_q, "Block")
t("a long question's key never ends in a space (it is cut at 160, then trimmed)", (len(k_long) <= 160, k_long == k_long.strip()), (True, True))
t("an answer saved under a long question's key is found again", autofill.clean_answers({k_long: "Yes"}).get(k_long), "Yes")
t("saved answers from the browser are capped and cleaned", (len(autofill.clean_answers({"q%d" % i: "a" for i in range(200)})), autofill.clean_answers({"x": 5, "": "y", "ok": "  v "})),
  (80, {"ok": "v"}))

# ---- every kind of question the app can ask on screen ------------------------------------------------------------------------------------------
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("mock_ats", os.path.join(HERE, "mock-ats.py"))
MOCK = importlib.util.module_from_spec(_spec)
_argv, sys.argv = sys.argv, [sys.argv[0]]
_spec.loader.exec_module(MOCK)                          # only its forms are used here; it serves nothing until its main block runs
sys.argv = _argv
EK = {"questions": MOCK.questions_for("1007"), "location_questions": [], "company_name": "Every Kind Co", "title": "Data Analyst"}
BARE = {"name": "Sam Rivera", "email": "sam@example.com", "loc": "Philadelphia, PA", "ext": {"phone": "+1 215 555 0100", "auth": "citizen", "sponsor": "no"}}
ek = autofill.plan_greenhouse(EK, BARE, {"co": "Every Kind Co", "role": "Data Analyst"}, "", RESUME[0], RESUME[1], {})
mk = {m["q"][:40]: m for m in ek["missing"]}
t("each kind of required question is asked with its own control",
  [(m["kind"], len(m.get("opts") or []), m.get("unit"), m.get("consent")) for m in ek["missing"]],
  [("textarea", 0, None, None), ("select", 20, None, None), ("multi", 10, None, None), ("month", 0, None, None), ("date", 0, None, None),
   ("number", 0, "hours", None), ("select", 2, None, None), ("select", 1, None, True)])
t("a long list sends every option (the app makes it searchable), not the first 60", len(autofill.public_plan(dict(ek, missing=[dict(ek["missing"][1], opts=["x"] * 400)]))["missing"][0]["opts"]), 400)
t("...and the plan caps what it sends at MAX_OPTS", len(autofill.ask_item({"kind": "select", "req": True}, "select", "Pick", [{"label": str(i), "value": i} for i in range(900)])["opts"]),
  autofill.MAX_OPTS)
notice = [m for m in ek["missing"] if m.get("consent")][0]
t("a notice the person must accept names the option that accepts it, and the public plan carries it", (notice["agree"], autofill.public_plan(ek)["missing"][-1]["agree"]),
  ("I acknowledge", "I acknowledge"))
t("the voluntary question in the same form is never asked or answered", [i.get("skip") for i in ek["items"] if "gender" in i["q"].lower()], ["voluntary"])
t("units from the label", [autofill.unit(x) for x in ("How many years of SQL?", "How many hours per week?", "Expected hourly rate (USD)", "What percent travel?", "How many?")],
  ["years", "hours", "USD", "%", ""])
t("text boxes that ask for a date, a month or a number get those controls; anything else stays text",
  [autofill.sheet_kind("text", x) for x in ("Start date (MM/DD/YYYY)", "Graduation date", "How many languages do you speak?", "Your nickname")],
  ["date", "month", "number", "text"])
t("a file other than the resume, or a type UAply does not know, cannot be asked on screen", [autofill.sheet_kind(k, "x") for k in ("file", "other")], ["other", "other"])
t("a yes/no question that is not a notice is never shown as a box to tick",
  autofill.ask_item({"kind": "select", "req": True}, "boolean", "Will you require sponsorship?", []).get("consent"), None)
t("an optional notice is not turned into a box the person must tick", autofill.ask_item({"kind": "select", "req": False}, "select", "I acknowledge the notice",
                                                                                        [{"label": "I acknowledge", "value": 1}]).get("consent"), None)
t("a link to read is kept only when it is a plain https address", [autofill.ask_item({"kind": "select", "req": True}, "select", "I consent to the policy",
                                                                                    [{"label": "I consent"}], u).get("link") for u in ("https://example.org/privacy", "javascript:alert(1)")],
  ["https://example.org/privacy", None])

# the answers typed in the sheet, as the form gets them
keys = {m["q"][:12]: m["key"] for m in ek["missing"]}
ans = {keys["Tell us abou"]: "I built a bus-times app used by 300 students.", keys["Which office"]: "Philadelphia", keys["Which of the"]: "Python\nSQL\nTableau",
       keys["Expected gra"]: "2027-06", keys["Earliest dat"]: "2027-07-01", keys["How many hou"]: "20", keys["Do you have "]: "Yes",
       keys["Please read "]: "I acknowledge"}
full = autofill.plan_greenhouse(EK, BARE, {"co": "Every Kind Co", "role": "Data Analyst"}, "", RESUME[0], RESUME[1], ans)
F = {}
for k, v in full["fields"]:
    F.setdefault(k, []).append(v)
t("with those answers nothing is missing", full["missing"], [])
t("...a month and a date go into text boxes the way their labels ask (MM/YYYY, MM/DD/YYYY)", (F.get("question_403"), F.get("question_404")), (["06/2027"], ["07/01/2027"]))
t("...several choices go in as one field per choice", F.get("question_402[]"), ["600", "601", "603"])
t("...the long list sends the chosen option's value, the notice its one option, the number as typed", (F.get("question_401"), F.get("question_407"), F.get("question_405")),
  (["512"], ["1"], ["20"]))
t("...the person sees the choices in words", [i["a"] for i in full["items"] if i["q"].startswith("Which of these")], ["Python, SQL, Tableau  (your saved answer)"])
wrong = dict(ans, **{keys["Which of the"]: "Python\nCobol"})
t("a multi-select answer with one choice that is not on this form is not guessed: the question is asked again",
  [m["q"][:30] for m in autofill.plan_greenhouse(EK, BARE, {"co": "X"}, "", RESUME[0], RESUME[1], wrong)["missing"]], ["Which of these tools have you "])
t("a month answer is never sent to a box that wants a whole date", autofill._answer("Start", "k", "date", [], {"k": "2027-06"}, [], {}), None)
t("a number written with a comma or a dollar sign is still a number", [autofill._answer("Pay", "k", "number", [], {"k": v}, [], {})[0] for v in ("85,000", "$ 40", "12.5")],
  [85000, 40, 12.5])
t("words in a number question are never sent", autofill._answer("Hours", "k", "number", [], {"k": "about 20"}, [], {}), None)
t("the same month written for a label that wants words", autofill._as_text("2027-06", "Graduation date"), "June 2027")
t("saved answers keep the line breaks of a multi-select and a long answer", autofill.clean_answers({"k": "Python\nSQL"}), {"k": "Python\nSQL"})

# ---- how often a form is complete from the profile alone ------------------------------------------------------------------------------------
complete = sum(1 for b in FORMS if not plan(b)["missing"])
t("every saved form gets its name, email, phone and resume filled in", all({"first_name", "last_name", "email", "phone"} <= set(dict(plan(b)["fields"])) and plan(b)["files"] for b in FORMS), True)
print("   (%d of %d saved forms are complete from the profile alone)" % (complete, len(FORMS)))

# ---- a swipe right, end to end: the questions are asked, then it goes in -----------------------------------------------------------------------
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "mock-ats.py"), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(50):
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:%d/__received" % PORT, timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    st_, why = ats_api.submit("greenhouse", "acme", "1003", "gh-secret-key-123", dict(CAND), "", *RESUME)
    t("a connected employer's form with a question only the person can answer: nothing is sent", st_, "needs_manual")
    key = autofill.norm("What is your favorite color and why?", "")
    st_, why = ats_api.submit("greenhouse", "acme", "1003", "gh-secret-key-123", dict(CAND, answers={key: "Blue, it is calm."}), "", *RESUME)
    t("...and once the person answers it, the application goes in with that answer", st_, "sent")
    st_, why = ats_api.submit("greenhouse", "acme", "1006", "gh-secret-key-123", cand_with(**JOB), "", *RESUME)
    t("relocation, expected pay, country and the location box: answered from the profile, sent without asking", (st_, why), ("sent", ""))
    got = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/__received" % PORT, timeout=5).read())[-1]
    f = got["fields"]
    t("...the employer's system received those answers, the country, the location with its map position and the job",
      ([f.get(k) for k in ("question_300", "question_301", "question_302", "country_short_name", "location")], "latitude" in f and "longitude" in f, got["employments"]),
      (["1", "85000", "11", "US", "Philadelphia, Pennsylvania, United States"], True,
       [{"[company_name]": "Acme Robotics", "[title]": "Support Engineer", "[start_date][month]": "6", "[start_date][year]": "2024", "[current]": "true"}]))
    st_, why = ats_api.submit("greenhouse", "acme", "1006", "gh-secret-key-123", cand_with(**dict(JOB, salary="", relocate="")), "", *RESUME)
    t("...without expected pay and relocation in the profile, nothing is sent and those two are asked", (st_, "salary expectations" in why, "relocate" in why), ("needs_manual", True, True))

    # every kind of question, asked once, then sent into the employer's Greenhouse; the same answers then fill a second employer's form
    c = dict(BARE)
    st_, why = ats_api.submit("greenhouse", "acme", "1007", "gh-secret-key-123", c, "", *RESUME)
    t("a connected employer's form with every kind of question the profile cannot answer: nothing is sent", (st_, "proud" in why), ("needs_manual", True))
    st_, why = ats_api.submit("greenhouse", "acme", "1007", "gh-secret-key-123", dict(c, answers=ans), "", *RESUME)
    got = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/__received" % PORT, timeout=5).read())[-1]["fields"]
    t("...with the person's answers it is accepted by the stand-in, which checks every required answer and option", (st_, why), ("sent", ""))
    t("...the employer received each kind as its form expects", [got.get(k) for k in ("question_401", "question_402[]", "question_403", "question_404", "question_405", "question_407")],
      ["512", ["600", "601", "603"], "06/2027", "07/01/2027", "20", "1"])
    t("...and never the voluntary question", "question_408" in got, False)
    st_, why = ats_api.submit("greenhouse", "acme", "1008", "gh-secret-key-123", dict(c, answers=ans), "", *RESUME)
    t("the same questions at another posting are answered from the saved answers, nothing asked", (st_, why), ("sent", ""))
    st_, why = ats_api.submit("greenhouse", "acme", "1009", "gh-secret-key-123", dict(CAND), "", *RESUME)
    t("a required file other than the resume is left to the person: nothing is sent", (st_, "Writing sample" in why), ("needs_manual", True))

    # the sandbox's preview: a real (public) posting whose employer has not connected, in test mode
    jid = 4242001
    with jobs_api._lock:
        jobs_api._cache["autofill-test"] = {"at": time.time(), "jobs": [{"id": jid, "co": "Acme", "role": "Intern", "url": "https://acme.example/j/1003", "loc": "Remote",
                                                                          "mode": "remote", "type": "internship", "sal": [0, 0], "apply": "link", "live": True, "contact": "",
                                                                          "ats": {"kind": "greenhouse", "board": "openboard", "id": "1003"}}]}
    body = {"consent": True, "job": {"id": jid, "co": "Acme", "role": "Intern", "url": "https://acme.example/j/1003"},
            "profile": {"name": "Sam Rivera", "email": "sam@example.com", "loc": "Philadelphia, PA", "ext": dict(CAND["ext"], **JOB)},
            "resume": {"name": "resume.pdf", "data": "data:application/pdf;base64,JVBERi0xLjQgYSBzbWFsbCB0ZXN0IHJlc3VtZSBmb3IgdGhlIGF1dG9maWxsIHRlc3Rz"}}
    uaply_api.init("sandbox")
    code, out = uaply_api.submit(dict(body))
    t("sandbox: swipe right asks the one question the profile cannot answer", (code, out.get("status"), [q["q"] for q in out.get("questions", [])]),
      (200, "needs_answers", ["What is your favorite color and why?"]))
    t("...and nothing was recorded or sent yet", len(uaply_api.APPS), 0)
    code, out = uaply_api.submit(dict(body, answers={key: "Blue"}))
    t("sandbox: with the answer, it is applied (to the test inbox, never the employer)", (code, out.get("status"), out.get("simulated")), (200, "delivered_test", True))
    t("...and the reply says how much was filled in for the person", (out.get("plan") or {}).get("filled", 0) >= 5, True)
    rec = uaply_api.APPS[-1]
    t("a form that never asked for pay: expected pay is not kept or listed, the rest of the new answers are",
      (rec["candidate"]["ext"]["salary"], "Expected yearly pay" in dict(uaply_api._detail_rows(rec["candidate"])),
       dict(uaply_api._detail_rows(rec["candidate"])).get("Job title there")), ("", False, "Support Engineer"))
    page = uaply_api.outbox_html().decode("utf-8")
    t("the test inbox page shows the employer's form as UAply filled it in", ("filled in by UAply" in page, "Blue" in page), (True, True))
    code, out = uaply_api.submit(dict(body, answers={key: "Blue"}))
    t("sandbox: a second swipe on the same job is a duplicate, not a second application", out.get("status"), "duplicate")
    with jobs_api._lock:
        jobs_api._cache["autofill-test"]["jobs"].append(dict(jobs_api._cache["autofill-test"]["jobs"][0], id=jid + 1, url="https://acme.example/j/1006",
                                                             ats={"kind": "greenhouse", "board": "openboard", "id": "1006"}))
    body6 = dict(body, job=dict(body["job"], id=jid + 1, url="https://acme.example/j/1006"))
    code, out = uaply_api.submit(body6)
    rec = uaply_api.APPS[-1]
    t("sandbox: a form that requires expected pay gets it from the profile, and the record and receipt list it",
      (out.get("status"), rec["candidate"]["ext"]["salary"], dict(uaply_api._detail_rows(rec["candidate"])).get("Expected yearly pay")), ("delivered_test", 85000, "$85,000"))
    # the server path: an answer written for one employer never reaches another employer's form, whatever the browser sends
    with jobs_api._lock:
        jobs_api._cache["autofill-test"]["jobs"].append(dict(jobs_api._cache["autofill-test"]["jobs"][0], id=jid + 2, co="Plaid", url="https://plaid.example/j/1011",
                                                             ats={"kind": "greenhouse", "board": "openboard", "id": "1011"}))
    body11 = dict(body, job=dict(body["job"], id=jid + 2, co="Plaid", url="https://plaid.example/j/1011"),      # (no "why" text in the profile: only an answer can fill it)
                  profile=dict(body["profile"], ext={k: v for k, v in body["profile"]["ext"].items() if k != "why"}))
    other = {"{at stripe} why do you want to work at {co}": "STRIPE-ONLY: I love Stripe's payments API.",
             "why do you want to work at {co}": "OLD-CO: kept the old way for whichever employer asked.",
             "why do you want to work here": "OLD-WHY: kept the old way too."}
    t("the server drops answers kept for another employer, and older answers about an employer (clean_answers)",
      autofill.clean_answers(dict(other, **{"are you legally authorized to work in the us": "Yes"}), "Plaid"), {"are you legally authorized to work in the us": "Yes"})
    code, out = uaply_api.submit(dict(body11, answers=other))
    t("sandbox: Plaid's 'why us' sent with only Stripe's and older answers is asked, nothing sent", (code, out.get("status"), [q["q"] for q in out.get("questions", [])]),
      (200, "needs_answers", ["Why do you want to work at Plaid?"]))
    n_apps = len(uaply_api.APPS)
    code, out = uaply_api.submit(dict(body11, answers=dict(other, **{"{at plaid} why do you want to work at {co}": "PLAID: its own answer."})))
    rec = uaply_api.APPS[-1] if len(uaply_api.APPS) > n_apps else {}
    sent_text = json.dumps(rec, ensure_ascii=False)
    t("...with Plaid's own answer it is applied, and Stripe's and the older answers are nowhere in what was kept or filled",
      (out.get("status"), "PLAID: its own answer." in sent_text, "STRIPE-ONLY" in sent_text, "OLD-CO" in sent_text, "OLD-WHY" in sent_text),
      ("delivered_test", True, False, False, False))
    uaply_api.init("dev")
    code, out = uaply_api.submit(dict(body))
    t("dev (no preview): the same posting is a hand-off, with the filled answers ready for the employer's page", (out.get("status"), bool(out.get("plan"))), ("handoff", True))
finally:
    proc.terminate()

# ---- answers about one employer stay with that employer (October 22, 2026), and the phone app keys a question as the server does ----
print("\nAnswers per employer")
t("a question naming the employer is kept for that employer", autofill.norm("Why do you want to work at Stripe?", "Stripe"),
  "{at stripe} why do you want to work at {co}")
t("...and so is 'why here' without the name", autofill.norm("Why do you want to work here?", "Plaid Inc.").startswith("{at plaid inc} "), True)
t("a question about the person is kept for every employer", autofill.norm("Are you legally authorized to work in the US?", "Stripe"),
  "are you legally authorized to work in the us")
t("a kept answer's key survives the browser's round trip (clean_answers)",
  list(autofill.clean_answers({"{at stripe} why do you want to work at {co}": "x"}).keys()), ["{at stripe} why do you want to work at {co}"])
QS = [{"id": "q1", "label": "Why do you want to work at Plaid?", "req": True, "kind": "textarea"},
      {"id": "q2", "label": "Are you legally authorized to work in the US?", "req": True, "kind": "text"}]
CAND = {"name": "Sam Rivera", "email": "sam@example.com", "ext": {}}
JOB = {"co": "Plaid", "role": "Analyst", "url": "https://example.com/1"}
saved = {"{at stripe} why do you want to work at {co}": "Stripe's payments API is why.",
         "why do you want to work at {co}": "An answer kept the old way, for whichever employer asked.",
         "are you legally authorized to work in the us": "Yes"}
plan = autofill.plan_questions(QS, CAND, JOB, answers=saved, company="Plaid")
vals = dict(plan["values"])
t("Plaid's 'why us' is never filled with Stripe's answer, nor with an answer kept the old way ({co})",
  vals.get("q1") not in ("Stripe's payments API is why.", "An answer kept the old way, for whichever employer asked."), True)
t("...it is asked instead", [m.get("key") for m in plan["missing"]], ["{at plaid} why do you want to work at {co}"])
t("the work authorization answer is used at Plaid too", vals.get("q2"), "Yes")
saved["{at plaid} why do you want to work at {co}"] = "Plaid's own answer."
t("Plaid's own answer fills Plaid's question", dict(autofill.plan_questions(QS, CAND, JOB, answers=saved, company="Plaid")["values"]).get("q1"),
  "Plaid's own answer.")
LABELS = ["Why do you want to work at Stripe?", "Why Stripe?", "Have you worked at Stripe before?", "What excites you about this role?",
          "Are you 18 years of age or older?", "First-name", "LinkedIn Profile URL*", "Do you now, or will you in the future, require sponsorship?",
          "Cover letter", "How did you hear about Stripe, Inc.?", "Current company", "  Résumé / CV  ", "Why are you leaving your current job?",
          "What is your expected start date (MM/DD/YYYY)?", "Tell us why you'd be a great fit"]
js = subprocess.run(["node", "-e", "global.window={};global.document={addEventListener(){}};global.location={href:''};"
                     "eval(require('fs').readFileSync(process.argv[1],'utf8'));const L=JSON.parse(process.argv[2]);"
                     "console.log(JSON.stringify(L.map(x=>[window.UAplyAssist.answerKey(x,'Stripe'),window.UAplyAssist.answerKey(x,'')])))",
                     os.path.join(ROOT, "shared", "uaply-assist.js"), json.dumps(LABELS)], capture_output=True, text=True, encoding="utf-8")
try:
    jsk = json.loads(js.stdout)
except ValueError:
    jsk = js.stderr[:300]
py = [[autofill.norm(x, "Stripe"), autofill.norm(x, "")] for x in LABELS]
t("the phone app's key for %d questions is the server's, letter for letter (with and without the employer)" % len(LABELS), jsk, py)
js2 = subprocess.run(["node", "-e", "global.window={};global.document={addEventListener(){}};global.location={href:''};"
                      "eval(require('fs').readFileSync(process.argv[1],'utf8'));const A=window.UAplyAssist;"
                      "const p={answers:{'{at stripe} why do you want to work at {co}':'S','why do you want to work at {co}':'old','Are you 18 years of age or older?':'Yes'}};"
                      "console.log(JSON.stringify([A.savedAnswer('Why do you want to work at Plaid?',p,'Plaid'),A.savedAnswer('Why do you want to work at Stripe?',p,'Stripe'),"
                      "A.savedAnswer('Are you 18 years of age or older?',p,'Plaid'),A.savedAnswer('Are you 18 years of age or older',p,'Plaid')]))",
                      os.path.join(ROOT, "shared", "uaply-assist.js")], capture_output=True, text=True, encoding="utf-8")
t("the phone app: Plaid's 'why us' is not Stripe's or an old {co} answer; Stripe's is; a question about the person is answered everywhere (also kept the old way, by its words)",
  js2.stdout.strip(), json.dumps(["", "S", "Yes", "Yes"], separators=(",", ":")))

# ---------- one pay question (October 24): per year or per hour in Profile setup step 3; a form gets it in the unit it asks for ----------
xh = uaply_api._ext({"salary": "37440", "salaryHour": "18", "payUnit": "hour"})
t("the server keeps the pay per year, per hour and its unit from the profile", (xh["salary"], xh["salaryHour"], xh["payUnit"]), (37440, 18.0, "hour"))
xy = uaply_api._ext({"salary": "60000"})
t("an older profile (yearly pay only, no unit): per year, and no hourly figure of its own", (xy["salary"], xy["salaryHour"], xy["payUnit"]), (60000, "", "year"))
cand_h = dict(CAND, ext=dict(CAND["ext"], salary=37440, salaryHour=18.0, payUnit="hour"))
rh = [(re.compile(p, re.I), f) for p, f in autofill._rules(cand_h, cand_h["ext"], {"co": "Acme", "role": "Barista"})]   # compiled, as plan_* does
ah = autofill._answer("What is your desired hourly rate?", "q1", "text", [], {}, rh, cand_h["ext"])
ay = autofill._answer("What are your salary expectations?", "q2", "text", [], {}, rh, cand_h["ext"])
t("a form that asks per hour gets 18, one that asks per year gets 37440", (ah and ah[0], ay and ay[0]), ("18", "37440"))
cand_y = dict(CAND, ext=dict(CAND["ext"], salary=62400, salaryHour="", payUnit="year"))
ry = [(re.compile(p, re.I), f) for p, f in autofill._rules(cand_y, cand_y["ext"], {"co": "Acme", "role": "Analyst"})]
t("a yearly figure, asked per hour: a year is 2080 hours (62400 -> 30)", (autofill._answer("Expected hourly pay?", "q3", "text", [], {}, ry, cand_y["ext"]) or [None])[0], "30")
cand_0 = dict(CAND, ext=dict(CAND["ext"], salary="", salaryHour=""))
r0 = [(re.compile(p, re.I), f) for p, f in autofill._rules(cand_0, cand_0["ext"], {"co": "Acme", "role": "Analyst"})]
t("no pay given: the hourly question is left for the person (asked each time)", autofill._answer("What is your desired hourly rate?", "q4", "text", [], {}, r0, cand_0["ext"]), None)
t("an optional hourly pay question is not answered (pay goes only where a form requires it), per hour as per year", (autofill._answer("What is your desired hourly rate?", "q5", "text", [], {}, rh, cand_h["ext"], req=False), autofill._answer("What are your salary expectations?", "q6", "text", [], {}, rh, cand_h["ext"], req=False)), (None, None))

print("\n%d / %d" % (ok, ok + bad))
sys.exit(1 if bad else 0)
