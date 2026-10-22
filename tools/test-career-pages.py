"""Employers' own careers sites (kind "careerpage"): the sitemap, then each job page's schema.org JobPosting data, honoring robots.txt and
its crawl delay, never past a human check, only pages on the sitemap's own host, a page read again only when its lastmod changes.
Also the packed job cache (each source's jobs held compressed) and the saved list. No network: every answer is made up here.
  python tools/test-career-pages.py"""
import json
import os
import sys
import tempfile
import time
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["UAPLY_CONFIG_FILE"] = "none"
os.environ["UAPLY_CONFIG_JSON"] = "{}"
os.environ["UAPLY_DATA_DIR"] = tempfile.mkdtemp(prefix="uaply-cp-")
import jobs_api as J  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


NOW = time.strftime("%Y-%m-%dT%H:%M:%S-04:00", time.gmtime(time.time() - 2 * 86400))
OLD = time.strftime("%Y-%m-%dT%H:%M:%S-04:00", time.gmtime(time.time() - 90 * 86400))
SITE = "https://careers-acme.icims.com"


def page(title, region="PA", country="US", extra=""):
    ld = {"@context": "https://schema.org", "@type": "JobPosting", "title": title, "hiringOrganization": {"@type": "Organization", "name": "Acme Gas"},
          "jobLocation": [{"@type": "Place", "address": {"addressLocality": "Philadelphia", "addressRegion": region, "addressCountry": country}}],
          "datePosted": NOW, "employmentType": "PART_TIME" if "Part" in title else "FULL_TIME",
          "description": "<p>Customer service, Excel and scheduling.</p>",
          "baseSalary": {"currency": "USD", "value": {"minValue": 45000, "maxValue": 60000, "unitText": "YEAR"}}}
    return '<html><head><script type="application/ld+json">%s</script></head><body>%s</body></html>' % (json.dumps(ld), extra)


ANSWERS = {
    SITE + "/robots.txt": "User-agent: *\nCrawl-delay: 0\nDisallow: /jobs/secret\n",
    SITE + "/sitemap.xml": "<urlset>" + "".join("<url><loc>%s</loc><lastmod>%s</lastmod></url>" % (u, m) for u, m in [
        (SITE + "/jobs/1/clerk/job?in_iframe=1", NOW), (SITE + "/jobs/2/cashier-part-time/job", NOW), (SITE + "/jobs/3/old-role/job", OLD),
        (SITE + "/jobs/secret/9/job", NOW), ("https://evil.example/jobs/4/x/job", NOW), (SITE + "/jobs/5/captcha/job", NOW),
        (SITE + "/jobs/6/berlin/job", NOW), (SITE + "/about", NOW)]) + "</urlset>",
    SITE + "/jobs/1/clerk/job?in_iframe=1": page("Customer Service Clerk"),
    SITE + "/jobs/2/cashier-part-time/job": page("Cashier Part-Time"),
    SITE + "/jobs/3/old-role/job": page("Old Role"),
    SITE + "/jobs/5/captcha/job": page("Clerk Two", extra='<div class="g-recaptcha"></div>'),
    SITE + "/jobs/6/berlin/job": page("Berlin Clerk", region="BE", country="DE"),
    "https://evil.example/jobs/4/x/job": page("Should never be read"),
}
CALLS = []


def fake_get(url, headers=None, as_text=False):
    CALLS.append(url)
    if url in ANSWERS:
        return ANSWERS[url]
    raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)


def fake_parts(url, headers=None):
    body = fake_get(url, headers, True).encode("utf-8")            # a sitemap arrives in 7-byte parts: every tag gets cut somewhere
    return iter([body[i:i + 7] for i in range(0, len(body), 7)])


J._get = fake_get
J._get_parts = fake_parts
J.CP_MIN_DELAY = 0.0
J.CAREER_PAGES["acme"] = SITE + "/sitemap.xml"
src = ("careerpage", "acme", "Acme Gas")
jobs, status = J._fetch_source(src)
roles = sorted(j["role"] for j in jobs)
t("a careers site: the job pages its sitemap lists are read for their JobPosting data", roles, ["Cashier Part-Time", "Customer Service Clerk"])
t("robots.txt is read first, and a page it disallows (/jobs/secret) is never asked for", (CALLS[0], any("/jobs/secret" in u for u in CALLS)), (SITE + "/robots.txt", False))
t("a page on another host listed in the sitemap is never asked for", any("evil.example" in u for u in CALLS), False)
t("a page older than 60 days by its lastmod is not read", any("/jobs/3/" in u for u in CALLS), False)
t("a page with a human check is skipped (never answered)", "Clerk Two" in roles, False)
t("a posting outside the US (addressCountry DE) is not shown", "Berlin Clerk" in roles, False)
clerk = [j for j in jobs if j["role"] == "Customer Service Clerk"][0]
t("the job: the employer's own page (without in_iframe), place, pay, type, credit, link-out",
  (clerk["url"], clerk["loc"], clerk["sal"], clerk["jobType"], clerk["via"], clerk["apply"]),
  (SITE + "/jobs/1/clerk/job", "Philadelphia, PA", [45000, 60000], "full-time", "Acme Gas careers site", "link"))
t("employmentType PART_TIME -> part-time", [j["jobType"] for j in jobs if j["role"] == "Cashier Part-Time"], ["part-time"])
CALLS.clear()
again, _ = J._fetch_source(src)
t("the next refresh reads the sitemap only: pages whose lastmod did not change are not read again (a human-check page, or one outside the US, neither)",
  [u for u in CALLS if "/jobs/" in u], [])
t("...and makes the same jobs from the last read's own copies (no description held in between)",
  sorted((j["id"], j["role"], j["loc"], j["jobType"], j["sal"]) for j in again) == sorted((j["id"], j["role"], j["loc"], j["jobType"], j["sal"]) for j in jobs), True)
J._robots.clear()
ANSWERS[SITE + "/robots.txt"] = "User-agent: *\nDisallow: /\n"
CALLS.clear()
J._cache.pop(src, None)
jobs, status = J._fetch_source(src)
t("a site whose robots.txt disallows everything is not read at all (only robots.txt)", (jobs, CALLS, status.startswith("error")), ([], [SITE + "/robots.txt"], True))
for bad in ("http://careers-acme.icims.com/sitemap.xml", "https://127.0.0.1/sitemap.xml", "https://localhost/sitemap.xml", "https://user:pw@acme.example/s.xml",
            "https://acme.example:8443/s.xml", "https://intranet.local/s.xml"):
    t("a sitemap address %r is never fetched" % bad, J._public_https(bad), False)
t("an ordinary public https sitemap is", J._public_https("https://careers-acme.icims.com/sitemap.xml"), True)

# ---------------- the packed cache ----------------
J._robots.clear()
J._cache.clear()
ANSWERS[SITE + "/robots.txt"] = "User-agent: *\n"
J._fetch_source(src)
e = J._cache[src]
t("a source's jobs are held packed (compressed), with their ids", ("packed" in e, isinstance(e["packed"].z, bytes), e["packed"].n, len(e["packed"].ids)), (True, True, 2, 2))
t("reading entry['jobs'] or .get('jobs') unpacks them", (len(e["jobs"]), len(e.get("jobs"))), (2, 2))
some = e["jobs"][0]
t("job_info finds a job by id from the packed cache", (J.job_info(some["id"]) or {}).get("role"), some["role"])
t("...and an unknown id is None", J.job_info(123), None)
J._disk["dirty"] = True
J._save_disk()
with open(J._cache_file(), encoding="utf-8") as f:
    saved = json.load(f)
t("the saved list keeps each source packed (base64 of the compressed list), not every job spelled out", ("z" in saved["careerpage|acme|Acme Gas"], "jobs" in saved["careerpage|acme|Acme Gas"]), (True, False))
J._cache.clear()
J._disk["loaded"] = False
J._load_disk()
t("...and a restart reads it back packed, the same jobs", (sorted(j["role"] for j in J._cache[src]["jobs"]), "packed" in J._cache[src]), (roles, True))

# an iCIMS site whose pages moved to another host of the same domain (careers-x -> externalcareers-x): read, with that host's robots.txt
J._cache.pop(src, None)
J._cp_pages.clear()
J._robots.clear()
ANSWERS[SITE + "/robots.txt"] = "User-agent: *\n"
ANSWERS["https://externalcareers-acme.icims.com/robots.txt"] = "User-agent: *\n"
ANSWERS["https://externalcareers-acme.icims.com/jobs/7/nurse/job"] = page("Registered Nurse")
ANSWERS[SITE + "/sitemap.xml"] = "<urlset><url><loc>https://externalcareers-acme.icims.com/jobs/7/nurse/job</loc><lastmod>%s</lastmod></url></urlset>" % NOW
CALLS.clear()
jobs7, _ = J._fetch_source(src)
t("pages on another host of the sitemap's domain are read, after that host's own robots.txt",
  ([j["role"] for j in jobs7], "https://externalcareers-acme.icims.com/robots.txt" in CALLS), (["Registered Nurse"], True))

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
