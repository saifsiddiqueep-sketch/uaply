"""Job ids never collide (October 22, 2026): 20,000 synthetic postings, among them postings whose first 6 hex digits are the same, all
reach the list with an id of their own; an id that never collided is exactly what it was before; the ids survive a restart (also when the
postings come back in another order); the partner employers' ids follow the same rule.
  python tools/test-job-ids.py
Before the fix the merge kept only the first posting of each shared id, so the forced pairs below were lost (the check on the old rule
counts them)."""
import hashlib
import os
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="uaply-ids-")
os.environ["UAPLY_DATA_DIR"] = TMP
os.environ["UAPLY_CONFIG_FILE"] = "none"
os.environ["UAPLY_CONFIG_JSON"] = '{"feeds":["greenhouse"],"smtp":{},"owner_copy":""}'
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import jobs_api as J  # noqa: E402

R = []


def t(name, ok, extra=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> " + str(extra)[:300]))


def h6(key):
    return int(hashlib.sha1(key.encode()).hexdigest()[:6], 16)


def restart():
    J._idreg.update(loaded=False, dirty=False, ids={})


# ---- postings that collide on purpose: keys whose first 6 hex digits are the same ----
buckets, pairs = {}, []
n = 0
while len(pairs) < 60:
    k = "greenhouse:%d" % n
    n += 1
    v = h6(k)
    if v in buckets:
        pairs.append((buckets[v], k))
    else:
        buckets[v] = k
keys = []
for p in pairs:                                           # the first of every pair before any second one: the first keeps its old id
    if p[0] not in keys:
        keys.append(p[0])
for p in pairs:
    if p[1] not in keys:
        keys.append(p[1])
forced = set(keys)
i = 0
while len(keys) < 20000:                                  # the rest: ordinary postings (a few of them collide by chance too)
    k = "lever:posting-%d" % i
    i += 1
    if k not in forced:
        keys.append(k)
old_ids = [100000 + h6(k) for k in keys]
lost_before = len(old_ids) - len(set(old_ids))
t("the old rule (6 hex digits): the forced pairs share ids, so the old list lost at least 60 postings (%d)" % lost_before, lost_before >= 60, lost_before)

# ---- every posting its own id ----
t0 = time.time()
ids = {k: J._claim_id(k, 100000) for k in keys}
t("20,000 postings: 20,000 different ids", len(set(ids.values())) == 20000, len(set(ids.values())))
t("claiming 20,000 ids takes under 2 s (%.2f s)" % (time.time() - t0), time.time() - t0 < 2)
t("the same posting asked again gets the same id", all(J._claim_id(k, 100000) == ids[k] for k in keys[:500]))
first_of_pair = [a for a, b in pairs]
t("an id that was free is exactly the old one (the first of each forced pair, and every ordinary posting that did not collide)",
  all(ids[a] == 100000 + h6(a) for a in first_of_pair) and
  sum(1 for k in keys if ids[k] == 100000 + h6(k)) == 20000 - lost_before, sum(1 for k in keys if ids[k] == 100000 + h6(k)))
second = [b for a, b in pairs]
t("the second of each forced pair gets a longer id (7 or more hex digits), not 0 and not past 2**53",
  all(ids[b] != 100000 + h6(b) and 0 < ids[b] < 2 ** 53 for b in second), [ids[b] for b in second[:3]])
t("_jid uses the same rule", J._jid("greenhouse", pairs[0][1].split(":", 1)[1]) == ids[pairs[0][1]])

# ---- a restart: the ids are read back, and the postings may come back in the opposite order ----
J._save_ids()
t("the ids are saved beside the job list", os.path.isfile(os.path.join(TMP, J.ID_FILE)))
restart()
again = {k: J._claim_id(k, 100000) for k in reversed(keys)}
t("after a restart, in the opposite order, every posting gets the same id as before", again == ids,
  [k for k in keys if again[k] != ids[k]][:3])
restart()
os.remove(os.path.join(TMP, J.ID_FILE))
fresh = {k: J._claim_id(k, 100000) for k in reversed(keys)}
t("(without the saved file the later one of a pair would take the short id: why the file is kept)",
  any(fresh[b] == 100000 + h6(b) for b in second))
restart()
J._save_ids()

# ---- the list itself: every one of the 20,000 is shown, none twice ----
restart()
src_a, src_b = ("greenhouse", "boarda", "Board A"), ("greenhouse", "boardb", "Board B")
jobs_a, jobs_b = [], []
for idx, k in enumerate(keys):
    j = {"id": J._jid(*k.split(":", 1)), "co": "Company %d" % idx, "role": "Role %d" % idx, "loc": "Austin, TX", "mode": "onsite",
         "url": "https://example.com/%d" % idx, "posted": int(time.time() * 1000)}
    (jobs_a if idx % 2 else jobs_b).append(j)
J.SOURCES[:] = [src_a, src_b]
J.feeds_allowed = lambda: {"greenhouse"}
J.partner_jobs = lambda: []
J._load_source = lambda src: ((jobs_a if src == src_a else jobs_b), "ok")
J._save_disk = lambda: None
meta = {}
shown = [j for j, feed in J._collect(meta, time.time() * 1000)]
t("the merged list shows all 20,000 postings", len(shown) == 20000, len(shown))
t("...each id once", len(set(j["id"] for j in shown)) == 20000)
t("...and nothing was counted as the same job from two feeds", meta.get("merged") == 0, meta.get("merged"))

# ---- the same posting through two feeds still counts once ----
J._load_source = lambda src: (jobs_a[:5], "ok")
shown = [j for j, feed in J._collect({}, time.time() * 1000)]
t("the same posting in two feeds is shown once", len(shown) == 5, len(shown))

# ---- partner employers: the old id unless taken ----
restart()
pk = "partner:Acme Bakery:Barista"
t("a partner job's id is the old one (200000 + 6 hex digits)", J._claim_id(pk, 200000) == 200000 + h6(pk))

print("%d / %d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
