"""Tests delivery straight into an employer's SmartRecruiters against a stand-in that follows the Application API reference (tools/mock-ats.py): the posting's
configuration is read with the employer's key (X-SmartToken), screening questions are answered from the profile, and the candidate goes in as JSON with
the resume in base64. Also: a question nobody can answer, diversity questions and optional consents never ticked, a refused key, a rate limit, a network
failure, a hostile reply, and that a key never leaks.
  python tools/test-ats-smartrecruiters.py"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8805          # a free port can be given: python tools/test-ats-smartrecruiters.py PORT
os.environ["UAPLY_ATS_BASE_SMARTRECRUITERS"] = "http://127.0.0.1:%d" % PORT
import ats_api  # noqa: E402
import autofill  # noqa: E402

R = []
KEY = "sr-smarttoken-012"
PLAIN, QUESTIONS, ODD, SLOW, HOSTILE = ("aaaaaaaa-0000-4000-8000-00000000000%d" % i for i in range(1, 6))


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


proc = subprocess.Popen([sys.executable, os.path.join(HERE, "mock-ats.py"), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)


def received():
    return json.loads(urllib.request.urlopen("http://127.0.0.1:%d/__received" % PORT).read())


CAND = {"name": "Pat Doe", "email": "pat@example.com", "loc": "Philadelphia, PA", "edu": "Bachelor", "years": 2,
        "ext": {"phone": "+1 215 555 0100", "linkedin": "https://www.linkedin.com/in/patdoe", "portfolio": "https://pat.example", "auth": "citizen", "sponsor": "no",
                "school": "Drexel University", "major": "Computer Science", "summary": "Computer science student who likes building things.", "ack": True},
        "job": {"co": "City of Philadelphia", "role": "Junior Cloud Engineer"}}
RESUME = ({"name": "resume.pdf", "type": "application/pdf", "size": 40}, b"%PDF-1.4 a small test resume for the stand-in server")


def copy(**ext):
    c = json.loads(json.dumps(CAND))
    c["ext"].update(ext)
    return c


try:
    # ---- the configuration and the plan ---------------------------------------------------------------------------------------------------
    cfg = json.load(open(os.path.join(HERE, "fixtures", "smartrecruiters-configurations.json"), encoding="utf-8"))["configurations"][QUESTIONS]
    qs = ats_api._sr_questions(cfg)
    t("each answerable field becomes a question; text to read (INFORMATION) does not", [q["id"] for q in qs],
      ["q-auth/f-auth", "q-spon/f-spon", "q-li/f-li", "q-eeo/f-eeo-g", "q-eeo/f-eeo-v", "consent"])
    t("diversity fields are marked voluntary", [q["id"] for q in qs if q.get("voluntary")], ["q-eeo/f-eeo-g", "q-eeo/f-eeo-v"])
    t("only the consent the employer requires is asked for", next(q["scopes"] for q in qs if q["id"] == "consent"), ["SINGLE"])

    # ---- sending ----------------------------------------------------------------------------------------------------------------------------
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", PLAIN, KEY, CAND, "I would love to join.", *RESUME)
    t("a posting with no screening questions is sent", (st, why), ("sent", ""))
    got = received()[-1]
    b = got["body"]
    t("...with the name split, the email, the phone, LinkedIn and website", (b["firstName"], b["lastName"], b["email"], b["phoneNumber"], b["web"]),
      ("Pat", "Doe", "pat@example.com", "+1 215 555 0100", {"linkedIn": "https://www.linkedin.com/in/patdoe", "website": "https://pat.example"}))
    t("...the location with the city and country code SmartRecruiters requires", b["location"],
      {"city": "Philadelphia", "region": "Pennsylvania", "regionCode": "PA", "country": "United States", "countryCode": "us"})
    t("...education with institution and degree", b["education"], [{"institution": "Drexel University", "degree": "Bachelor's Degree", "major": "Computer Science"}])
    t("...the resume as a base64 file, and the person's note and summary for the hiring manager",
      (b["resume"]["fileName"], b["resume"]["mimeType"], b["resume"]["fileContent"], "I would love to join." in b["messageToHiringManager"],
       "Computer science student" in b["messageToHiringManager"]), ("resume.pdf", "application/pdf", "(%d bytes)" % len(RESUME[1]), True, True))
    t("...to the right posting, with no consent when the employer asks for none", (got["system"], got["posting"], "consentDecisions" in b), ("smartrecruiters", PLAIN, False))

    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", QUESTIONS, KEY, CAND, "", *RESUME)
    got = received()[-1]
    t("screening questions are answered from the profile with the options' ids", (st, got["answered"]),
      ("sent", {"f-auth": ["v-yes"], "f-spon": ["s-no"], "f-li": ["https://www.linkedin.com/in/patdoe"]}))
    t("...in SmartRecruiters' shape: one record of field ids to lists of values", got["body"]["answers"][0], {"id": "q-auth", "records": [{"fields": {"f-auth": ["v-yes"]}}]})
    t("...the diversity questions are never answered", any(a["id"] == "q-eeo" for a in got["body"]["answers"]), False)
    t("...and only the required consent is given (with 'acknowledge for me' switched on), never the optional talent-pool one",
      got["body"]["consentDecisions"], {"SINGLE": True})

    before = len(received())
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", QUESTIONS, KEY, copy(ack=False), "", *RESUME)
    t("without 'acknowledge for me', a required consent is the person's to give: nothing is sent", (st, "consent" in why, len(received())), ("needs_manual", True, before))
    c = copy(ack=False)
    c["answers"] = {autofill.norm(ats_api._SR_CONSENT): "I consent"}
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", QUESTIONS, KEY, c, "", *RESUME)
    t("...once the person gives it, the application goes in with that consent", (st, received()[-1]["body"].get("consentDecisions")), ("sent", {"SINGLE": True}))
    before = len(received())
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", QUESTIONS, KEY, copy(sponsor=""), "", *RESUME)
    t("a required question the profile cannot answer sends NOTHING and names the question", (st, "sponsorship" in why, len(received())), ("needs_manual", True, before))
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", ODD, KEY, CAND, "", *RESUME)
    t("a required free-text question nobody can answer is never guessed", (st, "favorite color" in why, len(received())), ("needs_manual", True, before))
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", PLAIN, KEY, copy(resume="https://pat.example/resume.pdf"), "", None, None)
    b = received()[-1]["body"]
    t("with no resume file, nothing pretends to be one and the resume link goes to the hiring manager", (st, "resume" in b, "https://pat.example/resume.pdf" in b["messageToHiringManager"]),
      ("sent", False, True))
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", PLAIN, KEY, dict(CAND, loc="Remote (US)"), "", *RESUME)
    t("a location UAply cannot place as a city is left out rather than sent half-filled", (st, "location" in received()[-1]["body"]), ("sent", False))

    # ---- refusals and failures ----------------------------------------------------------------------------------------------------------------
    before = len(received())
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", PLAIN, "wrong-sr-token-000", CAND, "", *RESUME)
    t("a wrong key is refused (HTTP 401) and the reason never repeats the key", (st, "refused the key" in why, "401" in why, "wrong-sr" in why, len(received())),
      ("failed", True, True, False, before))
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", PLAIN, KEY, CAND, "", *RESUME)
    t("...the right key works at once afterwards", st, "sent")
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", SLOW, KEY, CAND, "", *RESUME)
    t("SmartRecruiters' rate limit is reported as a pause", (st, "429" in why), ("failed", True))
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", HOSTILE, KEY, CAND, "", *RESUME)
    t("a hostile reply is cut short, loses its markup and control characters, and never carries the key back",
      (st, "HTTP 500" in why, "<" in why, "\x00" in why, KEY in why, len(why) < 220), ("failed", True, False, False, False, True))
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", "aaaaaaaa-0000-4000-8000-000000000999", KEY, CAND, "", *RESUME)
    t("a posting SmartRecruiters does not know is reported, not sent", (st, "HTTP 404" in why), ("failed", True))
    before = len(received())
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", "744000146469759", KEY, CAND, "", *RESUME)
    t("a posting number instead of its uuid is refused before any request", (st, "uuid" in why, len(received())), ("failed", True, before))
    os.environ["UAPLY_ATS_BASE_SMARTRECRUITERS"] = "http://127.0.0.1:1"
    st, why = ats_api.submit("smartrecruiters", "CityofPhiladelphia", PLAIN, KEY, CAND, "", *RESUME)
    t("a network failure (nothing listening) is a failure with HTTP 0, never a crash", (st, "HTTP 0" in why), ("failed", True))
    os.environ["UAPLY_ATS_BASE_SMARTRECRUITERS"] = "https://evil.example"
    t("a base address from the environment is honored only for this computer", ats_api._base("smartrecruiters"), "https://api.smartrecruiters.com")
    os.environ["UAPLY_ATS_BASE_SMARTRECRUITERS"] = "http://127.0.0.1:%d" % PORT

    # ---- the check before a swipe is sent ---------------------------------------------------------------------------------------------------
    p = ats_api.plan("smartrecruiters", QUESTIONS, KEY, copy(ack=False), CAND["job"], "", RESUME[0], {})
    t("the plan asks for the consent in the shape the app shows", [(m["q"], m["kind"], m.get("opts")) for m in p["missing"]],
      [(ats_api._SR_CONSENT, "select", ["I consent", "No"])])
    t("the plan never contains the key", KEY in json.dumps(p), False)
finally:
    proc.terminate()

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
