"""Checks every Recruitee board in job-boards.json live for UAply (October 30, 2026): reads each board's public offers list
(GET https://{token}.recruitee.com/api/offers/, no key, the same URL jobs_api.py reads), one board a second, and prints per board
the slug, HTTP status, total offers, US offers and Canadian offers. Exits 1 if any board is dead (an error or a bad slug) or empty.
  python tools/check-recruitee-live.py"""
import json, os, sys, time, urllib.request, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import ats_api
UA = "UAply-jobs/1.0 (+https://uaply.net)"
US, CA = ("US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"), ("CA", "CAN", "CANADA")
def codes(o):
    got = [str(l.get("country_code") or l.get("country") or "").strip().upper() for l in o.get("locations") or [] if isinstance(l, dict)]
    return got or [str(o.get("country_code") or "").strip().upper()]
boards = [b["token"] for b in json.load(open(os.path.join(ROOT, "job-boards.json"), encoding="utf-8"))["boards"] if b.get("kind") == "recruitee"]
bad = 0
for t in boards:
    status, total, us, ca = "-", 0, 0, 0
    if not ats_api.ID_RE.match(t):
        status = "bad slug"
    else:
        try:
            req = urllib.request.Request("https://%s.recruitee.com/api/offers/" % t.lower(), headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                status = r.status
                offers = json.loads(r.read()).get("offers") or []
            total = len(offers)
            us = sum(1 for o in offers if any(c in US for c in codes(o)))
            ca = sum(1 for o in offers if any(c in CA for c in codes(o)))
        except urllib.error.HTTPError as e:
            status = e.code
        except Exception as e:
            status = type(e).__name__
    dead = status != 200 or total == 0
    bad += dead
    print("%-28s %-8s total %-4d us %-4d ca %-4d%s" % (t, status, total, us, ca, "  DEAD" if dead else ""))
    time.sleep(1)
print("%d boards, %d dead or empty" % (len(boards), bad))
sys.exit(1 if bad else 0)
