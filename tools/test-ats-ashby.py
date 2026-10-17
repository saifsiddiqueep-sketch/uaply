"""Tests delivery straight into an employer's Ashby against a stand-in that follows Ashby's documentation (tools/mock-ats.py): the form is read with the
employer's key, answered from the profile, and sent as multipart with the answers as a JSON string and the resume as a file part named by its field's value.
Also: a question nobody can answer, voluntary questions, a refused key, a rate limit, a network failure, a hostile reply, and that a key never leaks.
  python tools/test-ats-ashby.py"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8804          # a free port can be given: python tools/test-ats-ashby.py PORT
os.environ["UAPLY_ATS_BASE_ASHBY"] = "http://127.0.0.1:%d" % PORT
import ats_api  # noqa: E402
import autofill  # noqa: E402

R = []
KEY = "ashby-key-789"
PLAIN, QUESTIONS, ODD, UNKNOWN = ("11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222",
                                  "33333333-3333-4333-8333-333333333333", "77777777-7777-4777-8777-777777777777")


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


proc = subprocess.Popen([sys.executable, os.path.join(HERE, "mock-ats.py"), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)


def received():
    return json.loads(urllib.request.urlopen("http://127.0.0.1:%d/__received" % PORT).read())


CAND = {"name": "Pat Doe", "email": "pat@example.com", "loc": "Austin, TX", "edu": "Bachelor", "years": 2,
        "ext": {"phone": "+1 555 123 4567", "linkedin": "https://www.linkedin.com/in/patdoe", "portfolio": "https://pat.example", "auth": "citizen", "sponsor": "no",
                "relocate": "yes", "why": "I want to build {role} tools at {company}.", "summary": "Computer science student who likes building things."},
        "job": {"co": "Acme Robotics", "role": "Backend Engineer"}}
RESUME = ({"name": "resume.pdf", "type": "application/pdf", "size": 40}, b"%PDF-1.4 a small test resume for the stand-in server")


def copy(**ext):
    c = json.loads(json.dumps(CAND))
    c["ext"].update(ext)
    return c


try:
    # ---- the form and the plan ------------------------------------------------------------------------------------------------------------
    form = json.load(open(os.path.join(HERE, "fixtures", "ashby-forms.json"), encoding="utf-8"))["forms"][QUESTIONS]
    qs = ats_api._ashby_questions(form["applicationFormDefinition"])
    t("both ways Ashby lists a section's fields are read (fields and fieldEntries)", [q["id"] for q in qs][:4], ["_systemfield_name", "_systemfield_email", "_systemfield_resume", "q_work_auth"])
    t("the standard fields are recognised by their system path and type", [(q["id"], q["role"]) for q in qs if q["role"]],
      [("_systemfield_name", "name"), ("_systemfield_email", "email"), ("_systemfield_resume", "resume")])
    t("Ashby's types become the planner's kinds", {q["id"]: q["kind"] for q in qs if q["id"].startswith("q_")},
      {"q_work_auth": "select", "q_sponsor": "boolean", "q_heard": "select", "q_why": "textarea", "q_years": "number", "q_relocate": "multi", "q_gender": "select"})
    plan = autofill.plan_questions(qs, CAND, CAND["job"], "", RESUME[0], {}, "Acme Robotics")
    gender = [i for i in plan["items"] if i["q"] == "What is your gender?"][0]
    t("a gender question is skipped as voluntary and never given a value", (gender.get("skip"), "q_gender" in dict(plan["values"])), ("voluntary", False))

    # ---- sending ----------------------------------------------------------------------------------------------------------------------------
    st, why = ats_api.submit("ashby", "acme", PLAIN, KEY, CAND, "", *RESUME)
    t("a posting with only the standard fields is sent", (st, why), ("sent", ""))
    got = received()[-1]
    t("...with the name, email and phone under their paths, and the LinkedIn link", (got["values"]["_systemfield_name"], got["values"]["_systemfield_email"],
                                                                                    got["values"]["_systemfield_phone"], got["values"]["a1b2c3d4-linkedin"]),
      ("Pat Doe", "pat@example.com", "+1 555 123 4567", "https://www.linkedin.com/in/patdoe"))
    ref = got["values"]["_systemfield_resume"]
    t("...and the resume as a file part whose name is the resume field's value", (ref in got["files"], got["files"][ref]["filename"], got["files"][ref]["bytes"] > 20),
      (True, "resume.pdf", True))
    t("...to the right posting, credited to UAply", (got["system"], got["posting"], json.loads(got["utm"])), ("ashby", PLAIN, {"utm_source": "UAply"}))

    st, why = ats_api.submit("ashby", "acme", QUESTIONS, KEY, CAND, "", *RESUME)
    v = received()[-1]["values"]
    t("required questions are answered from the profile: work authorization, sponsorship (a yes/no box), how they heard, why this company",
      (st, v.get("q_work_auth"), v.get("q_sponsor"), v.get("q_heard"), v.get("q_why")),
      ("sent", "auth_yes", False, "board", "I want to build Backend Engineer tools at Acme Robotics."))
    t("a number question gets a number, a multiple-choice one a list of option values", (v.get("q_years"), v.get("q_relocate")), (2, ["reloc_yes"]))
    t("the voluntary gender question is not sent", "q_gender" in v, False)

    before = len(received())
    st, why = ats_api.submit("ashby", "acme", QUESTIONS, KEY, copy(sponsor=""), "", *RESUME)
    t("a required question the profile cannot answer sends NOTHING and names the question", (st, "sponsorship" in why, len(received())), ("needs_manual", True, before))
    st, why = ats_api.submit("ashby", "acme", ODD, KEY, CAND, "", *RESUME)
    t("a required free-text question nobody can answer is never guessed", (st, "favorite color" in why, len(received())), ("needs_manual", True, before))
    st, why = ats_api.submit("ashby", "acme", UNKNOWN, KEY, CAND, "", *RESUME)
    t("a required field of a type UAply cannot fill (a score) is left to the person", (st, "Rate your Python" in why, len(received())), ("needs_manual", True, before))
    st, why = ats_api.submit("ashby", "acme", PLAIN, KEY, CAND, "", None, None)
    t("a required resume with no resume file uploaded sends nothing", (st, "Resume" in why, len(received())), ("needs_manual", True, before))
    c = copy(sponsor="")
    c["answers"] = {autofill.norm("Will you now or in the future require visa sponsorship?"): "No"}
    st, why = ats_api.submit("ashby", "acme", QUESTIONS, KEY, c, "", *RESUME)
    t("...once the person answers it, their saved answer is used", (st, received()[-1]["values"].get("q_sponsor")), ("sent", False))

    # ---- refusals and failures ----------------------------------------------------------------------------------------------------------------
    before = len(received())
    st, why = ats_api.submit("ashby", "acme", PLAIN, "wrong-ashby-key-000", CAND, "", *RESUME)
    t("a wrong key is refused (HTTP 401) and the reason never repeats the key", (st, "refused the key" in why, "401" in why, "wrong-ashby" in why, len(received())),
      ("failed", True, True, False, before))
    st, why = ats_api.submit("ashby", "acme", PLAIN, KEY, CAND, "", *RESUME)
    t("...the right key works at once afterwards (a refused key is not remembered)", st, "sent")
    before = len(received())
    st, why = ats_api.submit("ashby", "acme", PLAIN, "ashby-readonly-key", CAND, "", *RESUME)
    t("a key without the permission to submit is refused (HTTP 403)", (st, "refused the key" in why, "403" in why, len(received())), ("failed", True, True, before))
    st, why = ats_api.submit("ashby", "acme", "88888888-8888-4888-8888-888888888888", KEY, CAND, "", *RESUME)
    t("Ashby's rate limit is reported as a pause", (st, "429" in why), ("failed", True))
    st, why = ats_api.submit("ashby", "acme", "44444444-4444-4444-8444-444444444444", KEY, CAND, "", *RESUME)
    t("a form Ashby refuses (success false) is reported with Ashby's own reason", (st, "refused this form" in why), ("failed", True))
    st, why = ats_api.submit("ashby", "acme", "66666666-6666-4666-8666-666666666666", KEY, CAND, "", *RESUME)
    t("an application blocked by the employer's limit is not reported as sent", (st, "blocked" in why), ("failed", True))
    st, why = ats_api.submit("ashby", "acme", "55555555-5555-4555-8555-555555555555", KEY, CAND, "", *RESUME)
    t("a hostile reply is cut short, loses its markup and control characters, and never carries the key back",
      (st, "HTTP 500" in why, "<" in why, "\x00" in why, KEY in why, len(why) < 220), ("failed", True, False, False, False, True))
    st, why = ats_api.submit("ashby", "acme", "99999999-9999-4999-8999-999999999999", KEY, CAND, "", *RESUME)
    t("a posting Ashby does not know is reported, not sent", (st, "could not read" in why, "job_posting_not_found" in why), ("failed", True, True))
    os.environ["UAPLY_ATS_BASE_ASHBY"] = "http://127.0.0.1:1"
    st, why = ats_api.submit("ashby", "acme", PLAIN, KEY, CAND, "", *RESUME)
    t("a network failure (nothing listening) is a failure with HTTP 0, never a crash", (st, "HTTP 0" in why), ("failed", True))
    os.environ["UAPLY_ATS_BASE_ASHBY"] = "https://evil.example"
    t("a base address from the environment is honored only for this computer", ats_api._base("ashby"), "https://api.ashbyhq.com")
    os.environ["UAPLY_ATS_BASE_ASHBY"] = "http://127.0.0.1:%d" % PORT

    # ---- the check before a swipe is sent (uaply_api uses it to ask a missing question once) -----------------------------------------------
    p = ats_api.plan("ashby", QUESTIONS, KEY, copy(sponsor=""), CAND["job"], "", RESUME[0], {})
    t("the plan names the missing question in the shape the app asks it", [(m["q"], m["kind"], m.get("opts")) for m in p["missing"]],
      [("Will you now or in the future require visa sponsorship?", "select", ["Yes", "No"])])
    t("the plan never contains the key", KEY in json.dumps(p), False)
    t("a plan with a bad key is simply not available", ats_api.plan("ashby", QUESTIONS, "wrong-ashby-key-000", CAND, CAND["job"], "", RESUME[0], {}), None)
finally:
    proc.terminate()

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
