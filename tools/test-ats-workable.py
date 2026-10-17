"""Tests delivery straight into an employer's Workable against a stand-in that follows Workable's API reference (tools/mock-ats.py): the job's questions
are read with the employer's token (Bearer, scope r_jobs), answered from the profile, and the candidate goes in as JSON with "sourced": false and the
resume in base64 (scope w_candidates). Also: the public jobs feed and the shortcode it records, a question nobody can answer, a file question, a
self-identification question never answered, a token without w_candidates, a rate limit, a duplicate, a network failure, a hostile reply, and that a
token never leaks.
  python tools/test-ats-workable.py [PORT]"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20441
os.environ["UAPLY_ATS_BASE_WORKABLE"] = "http://127.0.0.1:%d" % PORT
os.environ["UAPLY_CONFIG_FILE"] = "none"
import ats_api  # noqa: E402
import autofill  # noqa: E402
import jobs_api  # noqa: E402

R = []
KEY, SUB = "wk-token-345", "acmeworks"
PLAIN, QUESTIONS, ODD, SLOW, HOSTILE, DUP, FILEQ = ("WK0000000%d" % i for i in range(1, 8))


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


proc = subprocess.Popen([sys.executable, os.path.join(HERE, "mock-ats.py"), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)


def received():
    return json.loads(urllib.request.urlopen("http://127.0.0.1:%d/__received" % PORT).read())


CAND = {"name": "Pat Doe", "email": "pat@example.com", "loc": "Philadelphia, PA", "edu": "Bachelor", "years": 2, "title": "Software developer",
        "ext": {"phone": "+1 215 555 0100", "linkedin": "https://www.linkedin.com/in/patdoe", "auth": "citizen", "sponsor": "no",
                "school": "Drexel University", "major": "Computer Science", "summary": "Computer science student who likes building things.",
                "employer": "Corner Cafe", "job_title": "Barista", "job_start": "2024-06", "job_end": "", "gender": "woman"},
        "job": {"co": "Acme Works", "role": "Junior Developer"}}
RESUME = ({"name": "resume.pdf", "type": "application/pdf", "size": 40}, b"%PDF-1.4 a small test resume for the stand-in server")


def copy(**ext):
    c = json.loads(json.dumps(CAND))
    c["ext"].update(ext)
    return c


try:
    # ---- the connection itself --------------------------------------------------------------------------------------------------------------
    t("Workable is one of the systems an employer can connect", ("workable" in ats_api.KINDS, ats_api.NAMES["workable"]), (True, "Workable"))
    t("a connection needs the account's subdomain and a token", (ats_api.valid_connection("workable", SUB, KEY), ats_api.valid_connection("workable", "a/b", KEY),
                                                                 ats_api.valid_connection("workable", SUB, "")), (True, False, False))
    os.environ["UAPLY_ATS_BASE_WORKABLE"] = "https://evil.example"
    t("the address is the employer's own account, https://{subdomain}.workable.com/spi/v3; a base from the environment counts only for this computer",
      ats_api._wk_base(SUB), "https://acmeworks.workable.com/spi/v3")
    os.environ["UAPLY_ATS_BASE_WORKABLE"] = "http://127.0.0.1:%d" % PORT

    # ---- the questions ------------------------------------------------------------------------------------------------------------------------
    form = json.load(open(os.path.join(HERE, "fixtures", "workable-questions.json"), encoding="utf-8"))["jobs"][QUESTIONS]
    qs = ats_api._wk_questions(form)
    t("each Workable question becomes a plain question with its kind", [(q["id"], q["kind"]) for q in qs],
      [("q_auth", "boolean"), ("q_spon", "select"), ("q_heard", "select"), ("q_li", "text"), ("q_years", "number"), ("q_gender", "select")])
    t("...choices keep Workable's own ids as the values sent back", [o["value"] for o in qs[1]["options"]], ["c_spon_yes", "c_spon_no"])
    t("a multiple-choice question that allows several answers is a multi", ats_api._wk_questions({"questions": [
        {"id": "m", "body": "Which languages?", "type": "multiple_choice", "single_answer": False, "choices": [{"id": "a", "body": "Python"}]}]})[0]["kind"], "multi")
    t("an unknown question type is left to the person", ats_api._wk_questions({"questions": [{"id": "x", "body": "Video", "type": "video", "required": True}]})[0]["kind"], "other")

    # ---- sending ------------------------------------------------------------------------------------------------------------------------------
    st, why = ats_api.submit("workable", SUB, PLAIN, KEY, CAND, "I would love to join.", *RESUME)
    t("a job with no questions is sent", (st, why), ("sent", ""))
    got = received()[-1]
    b, c = got["body"], got["body"]["candidate"]
    t("...as a person who applied (sourced false), never as a recruiter's upload", (got["system"], got["job"], b["sourced"]), ("workable", PLAIN, False))
    t("...with the name, email, phone and address", (c["name"], c["firstname"], c["lastname"], c["email"], c["phone"], c["address"]),
      ("Pat Doe", "Pat", "Doe", "pat@example.com", "+1 215 555 0100", "Philadelphia, PA"))
    t("...the resume as a file (name and base64 data)", (c["resume"]["name"], c["resume"]["data"]), ("resume.pdf", "(%d bytes)" % len(RESUME[1])))
    t("...the note as the cover letter, and the summary", ("I would love to join." in c["cover_letter"], c["summary"].startswith("Computer science")), (True, True))
    t("...education with the school Workable requires", c["education_entries"], [{"school": "Drexel University", "degree": "Bachelor's Degree", "field_of_study": "Computer Science"}])
    t("...the current job with title, company, start date and current", c["experience_entries"],
      [{"title": "Barista", "company": "Corner Cafe", "start_date": "2024-06-01", "current": True}])
    t("...LinkedIn as a social profile, and UAply named as the source", (c["social_profiles"], c["domain"]), ([{"type": "linkedin", "url": "https://www.linkedin.com/in/patdoe"}], "UAply"))
    t("...and nothing voluntary or disqualifying", ("disqualified" in c, "gender" in json.dumps(c).lower()), (False, False))

    st, why = ats_api.submit("workable", SUB, QUESTIONS, KEY, CAND, "", *RESUME)
    got = received()[-1]
    t("the job's questions are answered from the profile with Workable's choice ids", (st, got["answered"]),
      ("sent", {"q_auth": True, "q_spon": ["c_spon_no"], "q_heard": ["c_board"], "q_li": "https://www.linkedin.com/in/patdoe", "q_years": 2}))
    t("...in Workable's shape: question_key with checked, choices or body", got["body"]["candidate"]["answers"][:2],
      [{"question_key": "q_auth", "checked": True}, {"question_key": "q_spon", "choices": ["c_spon_no"]}])
    t("...the gender question is never answered, even though the profile could", any(a["question_key"] == "q_gender" for a in got["body"]["candidate"]["answers"]), False)

    before = len(received())
    st, why = ats_api.submit("workable", SUB, QUESTIONS, KEY, copy(sponsor=""), "", *RESUME)
    t("a required question the profile cannot answer sends NOTHING and names it", (st, "sponsorship" in why, len(received())), ("needs_manual", True, before))
    c2 = copy(sponsor="")
    c2["answers"] = {autofill.norm("Will you now or in the future require sponsorship for employment visa status?", "Acme Works"): "No"}
    st, why = ats_api.submit("workable", SUB, QUESTIONS, KEY, c2, "", *RESUME)
    t("...once the person answers it, it goes in with that answer", (st, received()[-1]["answered"].get("q_spon")), ("sent", ["c_spon_no"]))
    before = len(received())
    st, why = ats_api.submit("workable", SUB, ODD, KEY, CAND, "", *RESUME)
    t("a required free-text question nobody can answer is never guessed", (st, "favorite color" in why, len(received())), ("needs_manual", True, before))
    st, why = ats_api.submit("workable", SUB, FILEQ, KEY, CAND, "", *RESUME)
    t("a required file other than the resume is left to the person", (st, "writing sample" in why, len(received())), ("needs_manual", True, before))
    long_li = "https://www.linkedin.com/in/" + "p" * 140
    p = ats_api.plan("workable", QUESTIONS, KEY, copy(linkedin=long_li), CAND["job"], "", RESUME[0], {}, SUB)
    t("a short-text answer longer than Workable's 128 characters is not sent (it is optional here, so it is just left out)",
      ("q_li" in dict(p["values"]), [m["q"] for m in p["missing"]]), (False, []))
    st, why = ats_api.submit("workable", SUB, PLAIN, KEY, copy(resume="https://pat.example/resume.pdf"), "", None, None)
    c = received()[-1]["body"]["candidate"]
    t("with no resume file, nothing pretends to be one and the link goes in the cover letter", (st, "resume" in c, "https://pat.example/resume.pdf" in c["cover_letter"]), ("sent", False, True))
    st, why = ats_api.submit("workable", SUB, PLAIN, KEY, CAND, "", {"name": "resume.png", "type": "image/png", "size": 5}, b"\x89PNG....")
    t("a resume in a type Workable does not take (only pdf, doc, docx, rtf) is not sent as a file", (st, "resume" in received()[-1]["body"]["candidate"]), ("sent", False))

    # ---- refusals and failures ------------------------------------------------------------------------------------------------------------------
    before = len(received())
    st, why = ats_api.submit("workable", SUB, PLAIN, "wrong-wk-token-000", CAND, "", *RESUME)
    t("a wrong token is refused (HTTP 401) and the reason never repeats it", (st, "refused the key" in why, "401" in why, "wrong-wk" in why, len(received())),
      ("failed", True, True, False, before))
    st, why = ats_api.submit("workable", SUB, PLAIN, KEY, CAND, "", *RESUME)
    t("...the right token works at once afterwards", st, "sent")
    st, why = ats_api.submit("workable", SUB, PLAIN, "wk-readonly-token", CAND, "", *RESUME)
    t("a token without the w_candidates scope can read questions but is refused on the send (HTTP 403)", (st, "403" in why), ("failed", True))
    st, why = ats_api.submit("workable", SUB, SLOW, KEY, CAND, "", *RESUME)
    t("a rate limit is reported as a pause", (st, "429" in why), ("failed", True))
    st, why = ats_api.submit("workable", SUB, DUP, KEY, CAND, "", *RESUME)
    t("a person Workable already has for this job is reported plainly", (st, why), ("failed", "Workable already has an application from this email for this job"))
    st, why = ats_api.submit("workable", SUB, HOSTILE, KEY, CAND, "", *RESUME)
    t("a hostile reply is cut short, loses its markup and control characters, and never carries the token back",
      (st, "HTTP 500" in why, "<" in why, "\x00" in why, KEY in why, len(why) < 220), ("failed", True, False, False, False, True))
    st, why = ats_api.submit("workable", SUB, "WK99999999", KEY, CAND, "", *RESUME)
    t("a job Workable does not know is reported, not sent", (st, "HTTP 404" in why), ("failed", True))
    os.environ["UAPLY_ATS_BASE_WORKABLE"] = "http://127.0.0.1:1"
    st, why = ats_api.submit("workable", "netfail", PLAIN, KEY, CAND, "", *RESUME)
    t("a network failure (nothing listening) is a failure with HTTP 0, never a crash", (st, "HTTP 0" in why), ("failed", True))
    os.environ["UAPLY_ATS_BASE_WORKABLE"] = "http://127.0.0.1:%d" % PORT

    # ---- the check before a swipe is sent ------------------------------------------------------------------------------------------------------
    p = ats_api.plan("workable", QUESTIONS, KEY, copy(sponsor=""), CAND["job"], "", RESUME[0], {}, SUB)
    t("the plan asks the missing question in the shape the app shows", [(m["kind"], m.get("opts")) for m in p["missing"]], [("select", ["Yes", "No"])])
    t("the plan never contains the token", KEY in json.dumps(p), False)
    t("without the subdomain there is no plan (Workable's address needs it)", ats_api.plan("workable", QUESTIONS, KEY, CAND, CAND["job"], "", RESUME[0], {}), None)

    # ---- the public jobs feed ------------------------------------------------------------------------------------------------------------------
    seen = []
    feed = {"name": "Acme Works", "jobs": [
        {"title": "Software Engineering Intern", "shortcode": "AB12CD34EF", "employment_type": "Internship", "telecommuting": False, "url": "https://apply.workable.com/j/AB12CD34EF",
         "shortlink": "https://apply.workable.com/j/AB12CD34EF", "application_url": "https://apply.workable.com/j/AB12CD34EF/apply", "published_on": "2026-10-01",
         "country": "United States", "city": "Philadelphia", "state": "Pennsylvania", "description": "<p>Python and SQL. Build things.</p>",
         "locations": [{"country": "United States", "countryCode": "US", "city": "Philadelphia", "region": "Pennsylvania", "hidden": False}]},
        {"title": "Account Executive", "shortcode": "ZZ99", "employment_type": "Full-time", "url": "https://apply.workable.com/j/ZZ99", "country": "France", "city": "Paris",
         "description": "<p>Excel and analytics.</p>", "locations": [{"country": "France", "city": "Paris", "hidden": False}]},
        {"title": "No code", "url": "https://apply.workable.com/j/x"}]}
    real_get = jobs_api._get
    jobs_api._get = lambda url, headers=None: (seen.append(url), feed)[1]
    try:
        raw = jobs_api._fetch_raw("workable", "acmeworks", "Acme Works")
    finally:
        jobs_api._get = real_get
    t("the feed reads Workable's public, keyless jobs list for the account", seen, ["https://www.workable.com/api/accounts/acmeworks?details=true"])
    t("...keeps postings that have a shortcode and title, with the location", [(r["id"], r["loc"]) for r in raw],
      [("AB12CD34EF", "Philadelphia, Pennsylvania, United States"), ("ZZ99", "Paris, France")])
    j = jobs_api._normalize(raw[0], "workable", "Acme Works", "acmeworks")
    t("a Workable posting records its subdomain and shortcode, links to the posting, and is a hand-off until the employer connects",
      (j["ats"], j["url"], j["apply"], j["type"], j["via"]),
      ({"kind": "workable", "board": "acmeworks", "id": "AB12CD34EF"}, "https://apply.workable.com/j/AB12CD34EF", "link", "internship", "Acme Works on Workable"))
    t("a posting outside the US is dropped", jobs_api._normalize(raw[1], "workable", "Acme Works", "acmeworks"), None)
finally:
    proc.terminate()

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
