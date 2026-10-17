"""Tests swipe right end to end into an employer's hiring system: which jobs become "apply instantly", that the key never reaches a browser, the rules for a
live send (verified account, matching email), the hand-off when a posting asks something the profile cannot answer, and failures. Stand-in hiring system.
  python tools/test-ats-flow.py"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="uaply-atsflow-")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8796                # another port can be given, so two test runs never collide
os.environ.update(UAPLY_DATA_DIR=TMP, UAPLY_CONFIG_JSON="{}", UAPLY_ATS_BASE_GREENHOUSE="http://127.0.0.1:%d" % PORT, UAPLY_ATS_BASE_LEVER="http://127.0.0.1:%d" % PORT,
                  UAPLY_ATS_BASE_ASHBY="http://127.0.0.1:%d" % PORT, UAPLY_ATS_BASE_SMARTRECRUITERS="http://127.0.0.1:%d" % PORT)
os.environ["UAPLY_ATS_JSON"] = json.dumps([{"kind": "lever", "board": "acme", "api_key": "lever-key-456"}, {"kind": "workday", "board": "x", "api_key": "abcdefgh123"},
                                           {"kind": "ashby", "board": "acmeashby", "api_key": "ashby-key-789"},
                                           {"kind": "smartrecruiters", "board": "CityofPhiladelphia", "api_key": "sr-smarttoken-012"}])

import jobs_api  # noqa: E402
import autofill  # noqa: E402
import ats_api  # noqa: E402
import uaply_api  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


with open(os.path.join(TMP, "uaply-partners.json"), "w", encoding="utf-8") as f:
    json.dump({"employers": [{"name": "Acme Robotics", "consent": "The owner posted these jobs for the employer (test)", "url": "https://acme.example/careers",
                              "ats": {"kind": "greenhouse", "board": "acme", "api_key": "gh-secret-key-123"},
                              "jobs": [{"role": "Robotics Intern", "skills": ["Python"], "ats_job_id": "1001", "loc": "Austin, TX", "mode": "onsite", "type": "internship"},
                                       {"role": "Support Engineer", "skills": ["SQL"], "ats_job_id": "1002", "loc": "Remote (US)", "mode": "remote"},
                                       {"role": "Odd Question Role", "skills": ["Python"], "ats_job_id": "1003", "loc": "Remote (US)", "mode": "remote"},
                                       {"role": "No Id Role", "skills": ["Python"], "loc": "Remote (US)", "mode": "remote"}]}]}, f)
mock = subprocess.Popen([sys.executable, os.path.join(HERE, "mock-ats.py"), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
cfg = {"delivery": "live", "smtp": {}, "daily_limit": 50}
uaply_api.config = lambda: cfg
uaply_api.init("atsflow")


def received():
    return json.loads(urllib.request.urlopen("http://127.0.0.1:%d/__received" % PORT).read())


def job_by(role):
    return [j for j in jobs_api.partner_jobs() if j["role"] == role][0]


def apply_to(job, email="pat@example.com", verified=True, user_email=None):
    user = {"id": 1, "email": user_email or email, "emailVerified": verified}
    p = {"consent": True, "confirm_real": True, "match": 80, "note": "", "job": {"id": job["id"], "co": job["co"], "role": job["role"], "url": job.get("url") or "https://acme.example/careers", "loc": job["loc"]},
         "profile": {"name": "Pat Doe", "email": email, "title": "Dev", "years": 1, "skills": ["Python"], "loc": "Austin, TX", "edu": "Bachelor",
                     "ext": {"phone": "+1 555 123 4567", "auth": "citizen", "sponsor": "no", "linkedin": "https://www.linkedin.com/in/patdoe"}},
         "resume": {"name": "resume.pdf", "data": "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4 a small test resume file for the flow test").decode()}}
    apply_to.last, apply_to.user = p, user
    return uaply_api.submit(p, user)


try:
    # which jobs are "apply instantly", and what browsers can see
    jobs = jobs_api.partner_jobs()
    t("partner jobs that have a hiring-system job id are instant; the one without an id is not", [(j["role"], j["instant"], j["apply"]) for j in jobs],
      [("Robotics Intern", True, "direct"), ("Support Engineer", True, "direct"), ("Odd Question Role", True, "direct"), ("No Id Role", False, "link")])
    t("the key is never in what browsers get", "gh-secret-key" in json.dumps(jobs_api.get_jobs()) or "lever-key" in json.dumps(jobs_api.get_jobs()), False)
    t("only well-formed connections are accepted (an unknown system is ignored)", sorted(jobs_api.ats_connections()),
      [("ashby", "acmeashby"), ("lever", "acme"), ("smartrecruiters", "CityofPhiladelphia")])
    feed = jobs_api._normalize(dict(id="posting-uuid-9", title="Backend Engineer", company="Acme", loc="Remote - USA", remote=True,
                                    text="Python and SQL required. 2 years of experience.", url="https://jobs.lever.co/acme/posting-uuid-9", salary_text="", posted=0), "lever", "Acme", "acme")
    other = jobs_api._normalize(dict(id="777", title="Backend Engineer", company="Other", loc="Remote - USA", remote=True,
                                     text="Python and SQL required.", url="https://boards.greenhouse.io/other/jobs/777", salary_text="", posted=0), "greenhouse", "Other", "other")
    t("a feed posting records where it lives in the employer's system", feed["ats"], {"kind": "lever", "board": "acme", "id": "posting-uuid-9"})
    ash = jobs_api._normalize(dict(id="11111111-1111-4111-8111-111111111111", title="Software Engineer Intern", company="Acme Ashby", loc="Remote - USA", remote=True,
                                   text="Python and SQL required.", url="https://jobs.ashbyhq.com/acmeashby/11111111-1111-4111-8111-111111111111", salary_text="", posted=0),
                              "ashby", "Acme Ashby", "acmeashby")
    # a SmartRecruiters posting as jobs_api._smartrecruiters builds it: the number is the job's id, the uuid is where the Application API finds it
    srj = jobs_api._normalize(dict(id="744000146469759", ats_id="aaaaaaaa-0000-4000-8000-000000000002", title="Junior Cloud Engineer", company="City of Philadelphia",
                                   loc="Philadelphia, PA", remote=None, text="Python and AWS required.", url="https://jobs.smartrecruiters.com/CityofPhiladelphia/744000146469759",
                                   salary_text="", posted=0), "smartrecruiters", "City of Philadelphia", "CityofPhiladelphia")
    t("an Ashby posting records its board and posting id; a SmartRecruiters one its company and posting uuid", (ash["ats"], srj["ats"]),
      ({"kind": "ashby", "board": "acmeashby", "id": "11111111-1111-4111-8111-111111111111"},
       {"kind": "smartrecruiters", "board": "CityofPhiladelphia", "id": "aaaaaaaa-0000-4000-8000-000000000002"}))
    t("...while the job's own id stays the one made from the posting number, so saved swipes keep matching",
      srj["id"], jobs_api._normalize(dict(id="744000146469759", title="Junior Cloud Engineer", company="City of Philadelphia", loc="Philadelphia, PA", remote=None,
                                          text="Python and AWS required.", url="https://jobs.smartrecruiters.com/CityofPhiladelphia/744000146469759", salary_text="",
                                          posted=0), "smartrecruiters", "City of Philadelphia", "CityofPhiladelphia")["id"])
    jobs_api._cache[("lever", "acme", "Acme")] = {"at": time.time(), "jobs": [feed], "status": "1 jobs"}
    jobs_api._cache[("greenhouse", "other", "Other")] = {"at": time.time(), "jobs": [other], "status": "1 jobs"}
    jobs_api._cache[("ashby", "acmeashby", "Acme Ashby")] = {"at": time.time(), "jobs": [ash], "status": "1 jobs"}
    jobs_api._cache[("smartrecruiters", "CityofPhiladelphia", "City of Philadelphia")] = {"at": time.time(), "jobs": [srj], "status": "1 jobs"}
    jobs_api.SOURCES = [("lever", "acme", "Acme"), ("greenhouse", "other", "Other"), ("ashby", "acmeashby", "Acme Ashby"),
                        ("smartrecruiters", "CityofPhiladelphia", "City of Philadelphia")]
    jobs_api.feeds_allowed = lambda: {"lever", "greenhouse", "ashby", "smartrecruiters"}
    jobs_api._load_source = lambda src: (jobs_api._cache[src]["jobs"], "ok")
    listing = {j["id"]: j for j in jobs_api.get_jobs()["jobs"]}
    t("a feed posting whose employer connected is marked instant; any other stays a hand-off", (listing[feed["id"]]["instant"], listing[feed["id"]]["apply"], listing[other["id"]].get("instant"), listing[other["id"]]["apply"]),
      (True, "direct", None, "link"))
    t("the policy for each", (jobs_api.job_policy(feed["id"]), jobs_api.job_policy(other["id"])), ("direct", "link"))
    t("the key is held only by the server", (jobs_api.known_ats(feed["id"])["key"], jobs_api.known_ats(other["id"])), ("lever-key-456", None))
    t("connected Ashby and SmartRecruiters postings are instant too, with no key in what browsers get",
      (listing[ash["id"]]["instant"], listing[srj["id"]]["instant"], "ashby-key" in json.dumps(listing) or "sr-smarttoken" in json.dumps(listing)), (True, True, False))

    # test mode says where the live app would send it: into the hiring system, not to a made-up email address (Acme gave no address)
    cfg["delivery"] = "test"
    code, out = apply_to(job_by("Support Engineer"), email="testmode@example.com")
    cfg["delivery"] = "live"
    t("test mode: a connected hiring system is simulated as the hiring system, not as an email", (out["status"], out["to"], uaply_api.APPS[-1]["channels"]),
      ("delivered_test", "Acme Robotics hiring system (simulated)", ["hiring system (simulated)"]))

    # a partner job: swipe right sends into their Greenhouse
    before = len(received())
    code, out = apply_to(job_by("Robotics Intern"))
    t("swipe right on a connected partner job is sent", (code, out["status"]), (200, "sent"))
    got = received()[before:]
    t("...it arrived in their Greenhouse for the right job, with the person's details", [(g["system"], g["board"], g["job"], g["fields"]["email"], g["fields"]["first_name"]) for g in got],
      [("greenhouse", "acme", "1001", "pat@example.com", "Pat")])
    t("...and the record names the channel but holds no key", (uaply_api.APPS[-1]["channels"], "gh-secret" in json.dumps(uaply_api.APPS[-1])), (["hiring system (greenhouse)"], False))
    code, out = apply_to(job_by("Robotics Intern"))
    t("applying twice is recognised, not sent twice", (out["status"], len(received()) - before), ("duplicate", 1))

    before = len(received())
    code, out = apply_to(job_by("Support Engineer"), email="sam@example.com")
    t("questions in the posting (work authorization, sponsorship, how you heard) are answered from the profile", (out["status"], received()[-1]["fields"].get("question_101")), ("sent", "1"))

    # a posting with a question the profile cannot answer: nothing sent, the person finishes on the employer's page
    before = len(received())
    code, out = apply_to(job_by("Odd Question Role"), email="lee@example.com")
    t("a required question the profile cannot answer: nothing is sent, and the app is told to ask it", (out["status"], [q["q"] for q in out.get("questions", [])], len(received())),
      ("needs_answers", ["What is your favorite color and why?"], before))
    code, out = uaply_api.submit(dict(apply_to.last, answers={autofill.norm("What is your favorite color and why?"): "Blue, it is calm."}), apply_to.user)
    t("...once the person answers it, the application goes into the employer's system with that answer",
      (out["status"], len(received()), "Blue, it is calm." in json.dumps(received()[-1]["fields"])), ("sent", before + 1, True))

    # the rules for a live send
    code, out = apply_to(job_by("Support Engineer"), email="unver@example.com", verified=False)
    t("an unverified account cannot send directly", (code, out.get("code")), (403, "verify"))
    code, out = apply_to(job_by("Support Engineer"), email="other@example.com", user_email="mine@example.com")
    t("the application's email must be the account's verified email", code, 400)
    cfg["test_recipient"] = "tester@example.com"
    before = len(received())
    code, out = apply_to(job_by("Robotics Intern"), email="redir@example.com")
    cfg.pop("test_recipient")
    t("a test redirect never reaches a real employer's system", (code, len(received())), (200, before))

    # a feed posting of a connected employer (Lever)
    before = len(received())
    code, out = apply_to(feed, email="lev@example.com")
    t("swipe right on a connected employer's real posting goes into their Lever", (out["status"], [(g["system"], g["site"], g["posting"]) for g in received()[before:]]),
      ("sent", [("lever", "acme", "posting-uuid-9")]))
    code, out = apply_to(other, email="oth@example.com")
    t("an employer that did not connect only ever gets a hand-off, nothing is sent", (out["status"], len(received())), ("handoff", before + 1))

    # a connected employer's Ashby posting
    before = len(received())
    code, out = apply_to(ash, email="ash@example.com")
    t("swipe right on a connected employer's Ashby posting goes into their Ashby, with the resume file",
      (out["status"], [(g["system"], g["posting"], g["values"]["_systemfield_email"], len(g["files"])) for g in received()[before:]]),
      ("sent", [("ashby", "11111111-1111-4111-8111-111111111111", "ash@example.com", 1)]))
    t("...the record names the channel and holds no key", (uaply_api.APPS[-1]["channels"], "ashby-key" in json.dumps(uaply_api.APPS[-1])), (["hiring system (ashby)"], False))

    # a connected employer's SmartRecruiters posting that asks for a consent the person has not given yet
    before = len(received())
    code, out = apply_to(srj, email="srp@example.com")
    t("a SmartRecruiters posting that needs the person's consent: nothing is sent, and the app is told to ask it once",
      (out["status"], [q["q"] for q in out.get("questions", [])], len(received())), ("needs_answers", [ats_api._SR_CONSENT], before))
    code, out = uaply_api.submit(dict(apply_to.last, answers={autofill.norm(ats_api._SR_CONSENT): "I consent"}), apply_to.user)
    got = received()[-1]
    t("...once given, it goes into their SmartRecruiters at the posting's uuid, with the screening answers and that consent",
      (out["status"], got["system"], got["posting"], got["answered"].get("f-auth"), got["body"].get("consentDecisions")),
      ("sent", "smartrecruiters", "aaaaaaaa-0000-4000-8000-000000000002", ["v-yes"], {"SINGLE": True}))
    cfg["delivery"] = "test"
    before = len(received())
    code, out = apply_to(srj, email="srtest@example.com")
    cfg["delivery"] = "live"
    t("test mode never uses an employer's key: it is simulated without asking or sending anything", (out["status"], len(received())), ("delivered_test", before))

    # an employer system that fails
    uaply_api.hide_errors = True
    code, out = apply_to(job_by("Support Engineer"), email="x1@example.com") if False else (200, {})
    jobs_api._ats_jobs[job_by("Support Engineer")["id"]]["key"] = "wrong-key-0000"
    code, out = apply_to(job_by("Support Engineer"), email="fail@example.com")
    uaply_api.hide_errors = False
    t("a refused key is reported as failed, with a plain sentence and no key or employer detail", (out["status"], out.get("error"), "wrong-key" in json.dumps(out)),
      ("failed", "Your application to Acme Robotics could not be sent right now. Try again in a moment.", False))
finally:
    mock.terminate()

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
