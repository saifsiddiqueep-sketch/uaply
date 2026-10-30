"""Checks Recruitee careers sites for UAply (October 23, 2026): for each company name, reads https://{c}.recruitee.com/robots.txt and,
if it allows /api/, the site's public offers list (GET https://{c}.recruitee.com/api/offers/, no key), one site a second. Prints and saves
each site's number of offers, how many are in the US and how many in PA, NJ or DE. Candidates came from a web search limited to
recruitee.com (health care, dental, legal, hospitality and the Philadelphia region first). Verified boards go in job-boards.json as
{"kind": "recruitee", "token": c, "name": ..., "total", "us", "tri", "checked"}, and only with "us" of 5 or more (every board's rule,
checked by tools/test-sources-health.py; find-boards.py --min-us).
  python tools/find-recruitee.py names.txt out.json      (names.txt: company subdomains, separated by spaces or lines)"""
import json, sys, time, urllib.request, urllib.error, urllib.robotparser
UA = "UAply-jobs/1.0 (+https://uaply.net)"
names = [x.strip() for x in open(sys.argv[1]).read().split() if x.strip()]
out = {}
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.geturl(), r.read()
for c in dict.fromkeys(names):
    base = "https://%s.recruitee.com" % c
    try:
        s, final, body = get(base + "/robots.txt")
        rp = urllib.robotparser.RobotFileParser(); rp.parse(body.decode("utf-8", "replace").splitlines())
        if "careers_not_hosted" in final or not rp.can_fetch(UA, base + "/api/offers/"):
            out[c] = {"error": "not hosted" if "careers_not_hosted" in final else "robots"}; print(c, out[c]); time.sleep(1); continue
        time.sleep(1)
        s, final, body = get(base + "/api/offers/")
        offers = json.loads(body).get("offers") or []
        us = [o for o in offers if (o.get("country_code") or "").upper() == "US" or any((l.get("country_code") or l.get("country") or "") in ("US", "United States") for l in o.get("locations") or [])]
        tri = [o for o in us if (o.get("state_code") or "").upper() in ("PA", "NJ", "DE")]
        cats = sorted({o.get("category_code") or "" for o in offers})
        out[c] = {"total": len(offers), "us": len(us), "tri": len(tri), "company": (offers[0].get("company_name") if offers else ""), "cats": cats[:6]}
    except urllib.error.HTTPError as e:
        out[c] = {"error": "HTTP %d" % e.code}
    except Exception as e:
        out[c] = {"error": type(e).__name__}
    print(c, out[c])
    time.sleep(1)
json.dump(out, open(sys.argv[2], "w"), indent=1)
