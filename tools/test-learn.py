"""Swipe learning (the sandbox "learn" feature, shared/uaply-learn.js): the math, the worked example from the design, and a replay
test on four made-up swipe histories with a clear taste. No server and no network: the real JavaScript runs in Node.
  python tools/test-learn.py"""
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
R = []


def t(name, good, detail=""):
    R.append(bool(good))
    print(("PASS " if good else "FAIL ") + name + ("" if good or not detail else "  -> " + str(detail)))


# The harness loads the real shared/uaply-learn.js (and, for the assembly check, every shared file the sandbox loads) and answers
# a list of questions. Python builds the fixtures and checks the answers.
HARNESS = r"""
const fs = require("fs"), path = require("path");
const ROOT = process.argv[2];
const read = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const win = {};
new Function("window", read("shared/uaply-learn.js"))(win);
const L = win.UAplyLearn.core;
const DAY = 864e5;
/* hand-made evidence has no Undo: every stored swipe is a decision (dec = n), and a no (D) means at least one real pass (P) */
function E(o) { return { like: o.like || {}, dis: o.dis || {}, cnt: o.cnt || {}, n: o.n || 0, dec: o.dec == null ? o.n || 0 : o.dec, P: o.P == null ? (o.D ? 1 : 0) : o.P, L: o.L || 0, D: o.D || 0 }; }
function state(evs, n, seed, ver) { return { v: 1, seed: seed || 7, n: n == null ? evs.length : n, ver: ver || 1, ev: evs }; }
/* replay: train on every swipe but the last `hold`, then score the held-out jobs */
function replay(f, hold) {
  const byId = {}; f.jobs.forEach((j) => { byId[j.id] = j; });
  const st = L.fresh(); st.seed = 11;
  const train = f.history.slice(0, f.history.length - hold), test = f.history.slice(f.history.length - hold);
  train.forEach((h) => L.swipe(st, byId[h.id], h.dir, h.dwell, false, h.at));
  const now = f.history[f.history.length - 1].at;
  const ev = L.evidence(st.ev, now);
  return test.map((h) => { const j = byId[h.id], s = L.score(j, j.fit, ev), x = L.explain(j, s, ev);
    return { id: h.id, dir: h.dir, fit: j.fit, z: s.z, shown: s.shown, delta: s.delta, why: x.why, key: x.key, yes: x.yes, no: x.no, attrs: L.attrs(j) }; });
}
/* the sandbox page as envs.js builds it: every feature that is on, patched in ORDER, must still parse */
function assemble() {
  const w = {}, ls = { getItem() { return null; }, setItem() {} };
  const doc = { getElementById() { return null; }, querySelector() { return null; }, createElement() { return {}; } };
  const sb = read("sandbox/index.html");
  ["uaply-nav.js", "uaply-live.js", "uaply-profile.js", "uaply-chat.js", "uaply-learn.js", "uaply-envs.js", "uaply-employers.js"].forEach((f) =>
    new Function("window", "localStorage", "document", read("shared/" + f))(w, ls, doc));
  const on = {}; (sb.match(/var on=\{([^}]*)\}/)[1]).split(",").forEach((kv) => { const k = kv.split(":")[0].trim(); if (k) on[k] = true; });
  const order = w.UAplyEnv.ORDER.filter((k) => k !== "confirm");
  let src = read("prod/index.html").replace('var KEY="hireswipe.v1";', 'var KEY="hireswipe.sandbox.v1";'), err = "";
  order.forEach((k) => { if (on[k] && w.UAplyEnv.FEATURES[k].patch) { try { src = w.UAplyEnv.FEATURES[k].patch(src); } catch (e) { err += k + ": " + e.message + ". "; } } });
  let parses = true; try { new Function(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/.exec(src)[1]); } catch (e) { parses = false; err += "parse: " + e.message; }
  const dev = read("dev/index.html");
  return { err, parses, learnOn: !!on.learn, learnLast: w.UAplyEnv.ORDER.indexOf("learn") === w.UAplyEnv.ORDER.indexOf("chat") + 1,
    hooks: ["__uaplyLearnOrder", "__uaplyLearnSwipe", "__uaplyLearnUndo", "__uaplyLearnLine"].every((h) => src.indexOf(h) > -1),
    devPromoted: /var PROMOTED=\[[^\]]*"learn"/.test(dev), devLoads: dev.indexOf("uaply-learn.js") > -1, sandboxLoads: sb.indexOf('<script src="uaply-learn.js"></script>') > -1 };
}
const out = JSON.parse(fs.readFileSync(0, "utf8")).map((q) => {
  const a = q.args || [];
  switch (q.fn) {
    case "K": return L.K;
    case "family": return a[0].map(L.family);
    case "attrs": return a[0].map(L.attrs);
    case "label": return L.label(a[0], a[1]);
    case "weight": return a[0].map(L.weight);
    case "evidence": return L.evidence(a[0], a[1]);
    case "score": { const ev = E(a[2]); const s = L.score(a[0], a[1], ev); return Object.assign(s, { explain: L.explain(a[0], s, ev) }); }
    case "literal": { /* the design's formula word for word (no yes/no balance, no "enough to learn from" gate), for comparison */
      L.K.center = false; L.K.gate = false; try { const ev = L.evidence(a[2], a[3]); return L.score(a[0], a[1], ev); } finally { L.K.center = true; L.K.gate = true; } }
    case "ready": return L.ready(L.evidence(a[0], a[1]));
    case "scoreEv": { const ev = L.evidence(a[2], a[3]); const s = L.score(a[0], a[1], ev); return Object.assign(s, { explain: L.explain(a[0], s, ev), n: ev.n }); }
    case "order": { const items = a[0]; const r = L.order(items, a[1], a[2], a[3]);
      return { same: r === items, ids: r.map((x) => x.j.id), explore: r.map((x) => !!(x.m.learn && x.m.learn.explore)), pct: r.map((x) => x.m.pct),
        fit: r.map((x) => (x.m.fit == null ? x.m.pct : x.m.fit)), why: r.map((x) => (x.m.learn ? x.m.learn.why : "")), line: r.map((x) => L.lineHTML(x.m)), learnN: r.map((x) => (x.m.learn ? x.m.learn.n : null)) }; }
    case "orderMany": { /* the same deck under many seeds: how often is the first non-explore card remote */
      let hits = 0; for (let s = 1; s <= a[2]; s++) { const st = Object.assign({}, a[1], { seed: s }); const r = L.order(a[0], st, a[3]);
        const first = r.find((x) => !x.m.learn.explore); if (first && first.j.mode === "remote") hits++; } return hits; }
    case "ops": { /* swipe / undo / finish / reset on a state, then return it */
      const st = L.fresh(); st.seed = 3; a[0].forEach((o) => { if (o.op === "swipe") L.swipe(st, o.job, o.dir, o.dwell, !!o.read, o.at); else if (o.op === "undo") L.undo(st, o.id);
        else if (o.op === "finish") o.res = L.finish(st, o.id); else if (o.op === "reset") L.reset(st); }); return st; }
    case "clean": return L.clean(a[0]);
    case "line": return L.lineHTML(a[0]);
    case "replay": return replay(a[0], a[1]);
    case "assemble": return assemble();
    case "coldStart": { /* a new person's first right swipes on jobs unlike the best match: where does the best match land, seed by seed */
      const jobs = a[0], swiped = a[1], strong = a[2], seeds = a[3], now = a[4], ranks = [];
      for (let sd = 1; sd <= seeds; sd++) {
        const st = L.fresh(); st.seed = sd;
        swiped.forEach((id, i) => L.swipe(st, jobs.find((j) => j.id === id), "applied", 0, false, now - (swiped.length - i) * 60000));
        const items = jobs.filter((j) => swiped.indexOf(j.id) < 0).sort((x, y) => y.fit - x.fit).map((j) => ({ j: j, m: { pct: j.fit } }));
        const r = L.order(items, st, now);
        ranks.push(r.findIndex((x) => x.j.id === strong) + 1);
      }
      return ranks; }
    default: return "unknown " + q.fn;
  }
});
process.stdout.write(JSON.stringify(out));
"""

node = shutil.which("node")
if not node:
    print("FAIL Node is not installed (it runs the real JavaScript)")
    sys.exit(1)
TMP = tempfile.mkdtemp(prefix="uaply-learn-")
HFILE = os.path.join(TMP, "harness.js")
with open(HFILE, "w", encoding="utf-8", newline="\n") as f:
    f.write(HARNESS)


def ask(*qs):
    """qs: (fn, args) pairs; returns the answers in order"""
    p = subprocess.run([node, HFILE, ROOT], input=json.dumps([{"fn": q[0], "args": list(q[1:])} for q in qs]), capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise SystemExit("harness failed: " + p.stderr[-1500:])
    return json.loads(p.stdout)


DAY = 86400000
NOW = 1792000000000          # a fixed "now" (October 2026), so fades are exact
K = ask(("K",))[0]

# ---------- the design's numbers ----------
t("signal weights are the design's: +1.5 finish, +1.2 read then right, +1.0 right, -0.6 slow left, -0.25 fast left, -0.3 undo after right",
  (K["finish"], K["read"], K["right"], K["slow"], K["fast"], K["undoRight"]) == (1.5, 1.2, 1.0, -0.6, -0.25, -0.3), K)
t("last 300 swipes, 0.98 a day, cap 1.5 per attribute, 25 / 40 points before / from 30 swipes, 1 in 5 explore",
  (K["keep"], K["fade"], K["cap"], K["capEarly"], K["capLate"], K["early"], K["every"]) == (300, 0.98, 1.5, 25, 40, 30, 5), K)

W = ask(("weight", [{"k": "R"}, {"k": "D"}, {"k": "F"}, {"k": "U"}, {"k": "L", "d": 300}, {"k": "L", "d": 700}, {"k": "L", "d": 1350},
                    {"k": "L", "d": 2000}, {"k": "L", "d": 9000}, {"k": "X"}]))[0]
t("each kind of swipe weighs what the design says (left: 0.7 s or less -0.25, 2 s or more -0.6, in between a straight line)",
  [round(x, 4) for x in W] == [1.0, 1.2, 1.5, -0.3, -0.25, -0.25, -0.425, -0.6, -0.6, 0], W)

# ---------- worked example (design page): 40 swipes; remote 9/2, product design 8/1, pay $60k-$80k 7/3; Product Designer at Figma, remote, $70k, 72 ----------
figma = {"id": 1, "co": "Figma", "role": "Product Designer", "mode": "remote", "type": "job", "sal": [70000, 70000], "yrs": 0, "skills": [],
         "live": True, "source": "Figma's careers page"}
# The example does not say how often the student says yes overall; with an even balance (here 20 yes, 20 no) the learner's
# naive-Bayes correction (K.center in the code) is zero and the formula is exactly the design's.
ev40 = {"like": {"m:remote": 9, "r:product design": 8, "p:60": 7}, "dis": {"m:remote": 2, "r:product design": 1, "p:60": 3},
        "cnt": {"m:remote": {"yes": 9, "no": 2}, "r:product design": {"yes": 8, "no": 1}, "p:60": {"yes": 7, "no": 3}}, "n": 40, "L": 20, "D": 20}
fa, s40, s29 = ask(("attrs", [figma]), ("score", figma, 72, ev40), ("score", figma, 72, dict(ev40, n=29)))
fa = fa[0]
parts = {p["a"]: p for p in s40["parts"]}
t("the Figma card carries remote, role family 'product design' and pay band $60k-$80k", {"m:remote", "r:product design", "p:60"} <= set(fa), fa)
t("worked example: logit(0.72) = +0.94", round(math.log(0.72 / 0.28), 2) == 0.94 and abs(s40["z"] - sum(p["c"] for p in s40["parts"]) - 0.944) < 0.001)
t("worked example: remote = log(10/3) = +1.20", round(parts["m:remote"]["c"], 2) == 1.20, parts.get("m:remote"))
t("worked example: product design = log(9/2) = 1.504, capped at +1.50", round(parts["r:product design"]["raw"], 3) == 1.504 and parts["r:product design"]["c"] == 1.5)
t("worked example: pay $60k to $80k = log(8/4) = +0.69", round(parts["p:60"]["c"], 2) == 0.69)
t("worked example: sum = +4.33 (4.341 before rounding each term)", abs(s40["z"] - 4.33) < 0.015, s40["z"])
t("worked example: p = 0.987", round(s40["p"], 3) == 0.987, s40["p"])
# The design page then says "shown as 94%, +22 from your swipes". Its own formula and caps give 98.7%: +26.7 points, inside the
# 40-point limit that applies at 40 swipes, so the card shows 99% and +27. Reported to the manager; the code follows the formula.
t("worked example on the card: 99% and +27 (formula and the 40-point limit at 40 swipes; the design page's '94%, +22' does not follow from its own formula)",
  s40["shown"] == 99 and s40["delta"] == 27, (s40["shown"], s40["delta"]))
t("the same card with 29 swipes: the learned part stops at +25 (97%)", s29["shown"] == 97 and s29["delta"] == 25, (s29["shown"], s29["delta"]))
t("worked example line: the attribute that added most (product design, +1.50) with its counts: 'You've liked 8 of 9 product design roles.'",
  s40["explain"]["why"] == "You've liked 8 of 9 product design roles.", s40["explain"])
t("the line names an attribute the card has, with counts from the history", s40["explain"]["key"] in fa and
  s40["explain"]["yes"] == ev40["cnt"][s40["explain"]["key"]]["yes"], s40["explain"])
# second half of the example: an on-site New York product design role at 72, after 0 likes and 6 dislikes for on-site New York
nyc = dict(figma, id=2, co="Ashgrove", mode="onsite", loc="New York, NY", sal=[0, 0])
evny = {"L": 20, "D": 20, "like": {"r:product design": 8}, "dis": {"r:product design": 1, "m:onsite": 6, "l:new york": 6},
        "cnt": {"r:product design": {"yes": 8, "no": 1}, "m:onsite": {"yes": 0, "no": 6}, "l:new york": {"yes": 0, "no": 6}}, "n": 40}
sny = ask(("score", nyc, 72, evny))[0]
pn = {p["a"]: p for p in sny["parts"]}
t("worked example, on-site New York: 0 likes and 6 dislikes is log(1/7) = -1.95, held at -1.50 (the minus side is capped like the plus side)",
  round(pn["m:onsite"]["raw"], 2) == -1.95 and pn["m:onsite"]["c"] == -1.5 and pn["l:new york"]["c"] == -1.5, pn)
t("worked example, on-site New York: remote is absent and the card drops (72%% -> %d%%)" % sny["shown"], "m:remote" not in pn and sny["shown"] < 72, sny["shown"])
t("worked example, on-site New York line: 'You've passed on 6 of 6 on-site jobs.' (or New York)",
  sny["explain"]["why"] in ("You've passed on 6 of 6 on-site jobs.", "You've passed on 6 of 6 jobs in New York."), sny["explain"])

# ---------- attributes ----------
fam = ask(("family", ["Senior Product Designer", "Software Engineer II", "Software Engineer, Backend", "Data Science Intern", "Product Design Lead",
                      "Sr. Data Analyst (Remote)", "UX/UI Designer"]))[0]
t("role family = first two words of the normalized title", fam == ["product design", "software engineer", "software engineer", "data science",
                                                                   "product design", "data analyst", "ux ui"], fam)
base = {"id": 5, "co": "Comcast", "role": "Data Analyst", "mode": "hybrid", "type": "internship", "sal": [50000, 70000], "yrs": 2, "loc": "Philadelphia, PA",
        "skills": ["SQL", "Python", "Excel"], "live": True, "source": "Comcast's careers page"}
private = dict(base, gpa="3.9", auth="US citizen or national", sponsor="No", eeo={"race": ["Asian"], "gender": "Female", "veteran": "No"},
               race="Asian", gender="Female", veteran="No", disability="No", majors=["Statistics"], desc="GPA 3.5 or higher", blurb="Visa sponsorship")
a1, a2 = ask(("attrs", [base, private]))[0]
t("a job's attributes: work style, type, role family, company, pay band, years band, city, skills, source",
  a1 == ["m:hybrid", "t:internship", "r:data analyst", "c:comcast", "p:60", "y:1-2", "l:philadelphia", "s:sql", "s:python", "s:excel", "o:board"], a1)
t("GPA, work authorization, sponsorship and voluntary answers never become attributes (same attributes with or without them)", a1 == a2, a2)
remote_job = dict(base, mode="remote", loc="Remote (US)", sal=[0, 0], yrs=7, type="weird", source="Remotive")
t("remote jobs have no city, unknown pay has no band, 6+ years is '5+', an unknown type counts as full-time, a feed is its own source",
  ask(("attrs", [remote_job]))[0][0] == ["m:remote", "t:job", "r:data analyst", "c:comcast", "y:5+", "s:sql", "s:python", "s:excel", "o:remotive"], ask(("attrs", [remote_job]))[0])
cl = ask(("clean", {"seed": 5, "n": 3, "ver": 2, "ev": [{"id": 1, "at": NOW, "k": "R", "a": ["m:remote", "e:asian", "g:3.9", "gpa:4", "x"]},
                                                       {"id": 2, "at": NOW, "k": "Z", "a": []}, "junk"]}))[0]
t("a saved state can only hold job attributes: anything else (a voluntary answer, a GPA) is dropped when it is read back",
  cl["ev"] == [{"id": 1, "at": NOW, "k": "R", "d": 0, "a": ["m:remote"]}], cl)
t("a broken saved state starts fresh", ask(("clean", "nonsense"))[0]["ev"] == [])

# ---------- evidence: window, fade, undo, finish ----------
old = [{"id": i, "at": NOW - 10 * DAY, "k": "R", "a": ["c:old%d" % i]} for i in range(50)]
new = [{"id": 100 + i, "at": NOW, "k": "L", "d": 3000, "a": ["m:onsite"]} for i in range(300)]
ev = ask(("evidence", old + new, NOW))[0]
t("only the last 300 swipes count (350 given, the 50 oldest are ignored)", ev["n"] == 300 and not any(k.startswith("c:old") for k in ev["like"]), ev["n"])
ev = ask(("evidence", [{"id": 1, "at": NOW - 10 * DAY, "k": "R", "a": ["m:remote"]}, {"id": 2, "at": NOW - 10 * DAY - 3600000, "k": "F", "a": ["m:remote"]}], NOW))[0]
t("a 10-day-old swipe weighs 0.98^10 = 0.817 of a new one", abs(ev["like"]["m:remote"] - 2.5 * 0.98 ** 10) < 1e-9 and abs(0.98 ** 10 - 0.8171) < 1e-4, ev["like"])
J = {"id": 9, "co": "Acme", "role": "Analyst", "mode": "remote", "type": "job", "sal": [0, 0], "yrs": 0, "skills": [], "live": True, "source": "x careers page"}
st = ask(("ops", [{"op": "swipe", "job": J, "dir": "passed", "dwell": 400, "at": NOW}, {"op": "undo", "id": 9}]))[0]
t("Undo after a swipe left removes it entirely (as if never swiped)", st["ev"] == [] and st["n"] == 0, st)
st = ask(("ops", [{"op": "swipe", "job": J, "dir": "applied", "dwell": 0, "at": NOW}, {"op": "undo", "id": 9}]))[0]
t("Undo after a swipe right turns it into a small no (-0.3)", [e["k"] for e in st["ev"]] == ["U"] and ask(("weight", st["ev"]))[0] == [-0.3], st["ev"])
st = ask(("ops", [{"op": "swipe", "job": J, "dir": "applied", "dwell": 0, "at": NOW}, {"op": "finish", "id": 9}]))[0]
t("finishing on the employer's site after a swipe right upgrades it to +1.5", [e["k"] for e in st["ev"]] == ["F"])
st = ask(("ops", [{"op": "finish", "id": 9}, {"op": "swipe", "job": J, "dir": "passed", "dwell": 100, "at": NOW}, {"op": "finish", "id": 9}]))[0]
t("opening the employer's site never turns a swipe left (or no swipe) into a yes", [e["k"] for e in st["ev"]] == ["L"])
st = ask(("ops", [{"op": "swipe", "job": J, "dir": "applied", "read": True, "dwell": 0, "at": NOW}]))[0]
t("a swipe right after opening the details is stored as a considered yes (+1.2)", [e["k"] for e in st["ev"]] == ["D"])
st = ask(("ops", [{"op": "swipe", "job": J, "dir": "passed", "dwell": 100, "at": NOW}, {"op": "swipe", "job": J, "dir": "applied", "dwell": 0, "at": NOW + 1}]))[0]
t("swiping the same job again replaces the old swipe (one entry per job)", [e["k"] for e in st["ev"]] == ["R"])
st = ask(("ops", [{"op": "swipe", "job": dict(J, id=i), "dir": "applied", "dwell": 0, "at": NOW + i} for i in range(310)] + [{"op": "reset"}]))[0]
t("Reset forgets everything", st["ev"] == [] and st["n"] == 0)
st = ask(("ops", [{"op": "swipe", "job": dict(J, id=i), "dir": "applied", "dwell": 0, "at": NOW + i} for i in range(310)]))[0]
t("never more than 300 swipes are kept on the device", len(st["ev"]) == 300 and st["ev"][0]["id"] == 10)

# ---------- caps ----------
# (L 1 and D 1: this person has both a yes and a no, so the learner may move scores, and the even balance makes centring zero)
huge = {"like": {"m:remote": 1000, "t:job": 1000, "o:board": 1000, "r:analyst": 1000}, "dis": {}, "cnt": {}, "n": 10, "L": 1, "D": 1}
s10, s50 = ask(("score", J, 50, huge), ("score", J, 50, dict(huge, n=50)))
t("no attribute adds more than +1.5, however strong the evidence", all(p["c"] <= 1.5 for p in s10["parts"]) and max(p["raw"] for p in s10["parts"]) > 6)
sneg = ask(("score", J, 60, {"like": {}, "dis": {"m:remote": 1000, "t:job": 1000}, "cnt": {}, "n": 50, "L": 1, "D": 1}))[0]
t("and no attribute takes away more than 1.5, however many passes", all(p["c"] >= -1.5 for p in sneg["parts"]) and min(p["raw"] for p in sneg["parts"]) < -6, sneg["parts"])
t("before 30 swipes the learned part is at most +25 points (50% -> 75%)", s10["shown"] == 75, s10["shown"])
t("from 30 swipes on it is at most +40 points (50% -> 90%)", s50["shown"] == 90, s50["shown"])
neg = {"like": {}, "dis": {"m:remote": 1000, "t:job": 1000}, "cnt": {}, "n": 50, "L": 1, "D": 1}
t("and at most -40 the other way (60% -> 20%)", ask(("score", J, 60, neg))[0]["shown"] == 20)
t("no evidence for any of the job's attributes: the score is the match score", ask(("score", J, 63, {"n": 50}))[0]["shown"] == 63)

# ---------- a person who passes far more than they apply (most people) ----------
# 29 on-site New York jobs passed, after about a second each, and nothing else yet. The design's formula word for word pushes every
# attribute down, even "full-time" and the source that every job shares, so every card loses the full 40 points and the order never
# changes. Measured against this person's overall yes/no balance (naive Bayes, K.center), nothing counts against anything yet.
onsite_ev = [{"id": 2000 + i, "at": NOW - i * 60000, "k": "L", "d": 1100, "a": ["m:onsite", "t:job", "o:board", "l:new york", "r:software engineer"]} for i in range(29)]
rjob = {"id": 7, "co": "Remote Co", "role": "Software Engineer", "mode": "remote", "type": "job", "sal": [0, 0], "yrs": 0, "skills": [], "live": True, "source": "R careers page"}
ojob = dict(rjob, id=8, co="Office Co", mode="onsite", loc="New York, NY")
lit_r, lit_o, cen_r, cen_o = ask(("literal", rjob, 85, onsite_ev, NOW), ("literal", ojob, 100, onsite_ev, NOW), ("scoreEv", rjob, 85, onsite_ev, NOW), ("scoreEv", ojob, 100, onsite_ev, NOW))
t("pass-heavy person, the design's formula word for word: a remote job never seen also drops (85%% -> %d%%) and on-site stays above it (%d%%)" % (lit_r["shown"], lit_o["shown"]),
  lit_r["delta"] < -20 and lit_o["shown"] > lit_r["shown"], (lit_r["shown"], lit_o["shown"]))
t("pass-heavy person, measured against their own yes/no balance: nothing counts against a job yet (85%% stays %d%%, 100%% stays %d%%)" % (cen_r["shown"], cen_o["shown"]),
  cen_r["delta"] == 0 and cen_o["delta"] == 0, (cen_r["shown"], cen_o["shown"]))
two = onsite_ev + [{"id": 3000 + i, "at": NOW, "k": "R", "a": ["m:remote", "t:job", "o:board", "r:software engineer"]} for i in range(2)]
c2r, c2o = ask(("scoreEv", rjob, 85, two, NOW), ("scoreEv", ojob, 100, two, NOW))
t("then two remote jobs liked: remote moves up (85%% -> %d%%) and on-site down (100%% -> %d%%), so remote is now first" % (c2r["shown"], c2o["shown"]),
  c2r["shown"] > c2o["shown"] and c2r["explain"]["why"] == "You've liked 2 of 2 remote jobs." and c2o["explain"]["why"] == "You've passed on 29 of 29 on-site jobs.",
  (c2r["explain"], c2o["explain"]))
shared = [p for p in c2r["parts"] if p["a"] in ("t:job", "o:board")]
t("attributes every swiped job had (full-time, the source) carry almost no weight: %s" % ", ".join("%s %+.2f" % (p["a"], p["c"]) for p in shared),
  len(shared) == 2 and all(abs(p["c"]) < 0.01 for p in shared), shared)
pdeck = [{"j": dict(ojob, id=10 + i, co="Office %d" % i), "m": {"pct": 100 - i}} for i in range(10)] + [{"j": dict(rjob, id=40 + i, co="Remote %d" % i), "m": {"pct": 85 - i}} for i in range(10)]
po = ask(("order", pdeck, {"v": 1, "seed": 7, "n": 29, "ver": 3, "ev": onsite_ev}, NOW, None))[0]
exp = [i for i, e in zip(po["ids"], po["explore"]) if e]
t("pass-heavy person: the explore card (1 in 5) is a remote job, the kind UAply knows least about", exp and all(i >= 40 for i in exp), (exp, po["ids"][:6]))

# ---------- the deck order ----------
def job(i, mode, fit):
    return {"j": {"id": i, "co": "Co%d" % i, "role": ["Data Analyst", "Software Engineer", "Product Designer"][i % 3], "mode": mode, "type": "job",
                  "sal": [60000 + 2000 * (i % 7), 80000 + 2000 * (i % 7)], "yrs": i % 4, "loc": "Philadelphia, PA", "skills": ["SQL", "Go", "Figma"][i % 3:i % 3 + 1],
                  "live": True, "source": "Co careers page"}, "m": {"pct": fit}}


deck = [job(i, "onsite", 95 - i) for i in range(20)] + [job(100 + i, "remote", 70 - i) for i in range(20)]
hist = [{"id": 1000 + i, "at": NOW - i * 3600000, "k": "R" if i % 2 == 0 else "L", "d": 1500, "a": ["m:remote" if i % 2 == 0 else "m:onsite", "t:job"]} for i in range(30)]
st30 = {"v": 1, "seed": 7, "n": 30, "ver": 4, "ev": hist}
o0, o1, o1b, o2 = ask(("order", deck, {"v": 1, "seed": 7, "n": 0, "ver": 0, "ev": []}, NOW, None), ("order", deck, st30, NOW, None),
                      ("order", deck, st30, NOW, None), ("order", deck, dict(st30, n=32), NOW, None))
t("no swipes: the deck is exactly today's deck (same list, same order)", o0["same"] and o0["ids"] == [x["j"]["id"] for x in deck])
t("the learner only reorders: the same cards, none added or dropped (filters stay hard rules)", sorted(o1["ids"]) == sorted(x["j"]["id"] for x in deck))
t("the same state gives the same order (the deck does not reshuffle between two looks)", o1["ids"] == o1b["ids"])
mode = {x["j"]["id"]: x["j"]["mode"] for x in deck}
first = [mode[i] for i, e in zip(o1["ids"], o1["explore"]) if not e][:10]
t("15 remote yes and 15 on-site no: the remote cards come first, although on-site ones match better (95% vs 70%)", first == ["remote"] * 10, first)
ex_pos = [i for i, e in enumerate(o1["explore"]) if e]
t("1 in 5 cards is from outside the learned top: positions 5, 10, 15... after 30 swipes", ex_pos[:4] == [4, 9, 14, 19], ex_pos[:6])
t("the explore cards come from the bottom half of the learned ranking (here: on-site)", all(mode[o1["ids"][i]] == "onsite" for i in ex_pos[:4]))
t("the explore slot moves with the number of swipes (32 swipes: positions 3, 8, ...)", [i for i, e in enumerate(o2["explore"]) if e][:2] == [2, 7])
t("explore cards say so on the card", all('data-explore="1"' in o1["line"][i] and "Something different" in o1["line"][i] for i in ex_pos[:3]))
pin = ask(("order", deck, st30, NOW, 7))[0]
t("the card Undo brought back stays on top", pin["ids"][0] == 7)
hits = ask(("orderMany", deck, st30, 200, NOW))[0]
t("Thompson sampling: across 200 different seeds the first regular card is remote every time (%d / 200)" % hits, hits == 200, hits)
early = [{"id": 1, "at": NOW, "k": "R", "a": ["m:remote", "t:job"]}]
o3 = ask(("order", deck, {"v": 1, "seed": 7, "n": 1, "ver": 1, "ev": early}, NOW, None))[0]
moved = sum(1 for a, b in zip(o3["ids"][:10], [x["j"]["id"] for x in deck][:10]) if a != b)
t("after a single swipe the draws are wide but the match score still counts: top 10 has some of today's best on-site jobs",
  sum(1 for i in o3["ids"][:10] if mode[i] == "onsite") >= 3, (moved, [mode[i] for i in o3["ids"][:10]]))
line = ask(("line", {"pct": 80, "fit": 60, "learn": {"delta": 20, "why": "You've liked 2 of 2 jobs at <b>Evil</b>.", "explore": False}}))[0]
t("the card line reads 'Learned from your swipes: +20.' and escapes job text", line.startswith('<p class="learned"><b>Learned from your swipes: +20.</b>') and "&lt;b&gt;Evil" in line, line)
t("a card with nothing learned gets no line", ask(("line", {"pct": 60, "fit": 60, "learn": {"delta": 0, "why": "", "explore": False}}))[0] == "")

# ---------- replay test: hide the last 10 swipes of each history, train on the rest, rank liked above passed ----------
TITLES = ["Product Designer", "UX Designer", "Software Engineer", "Data Analyst", "Marketing Coordinator", "Sales Associate", "Financial Analyst", "Research Assistant"]
CITIES = ["Philadelphia, PA", "New York, NY", "Pittsburgh, PA", "Boston, MA", "Newark, NJ"]
SKILLS = ["SQL", "Python", "Excel", "Figma", "React", "Java", "Tableau", "Salesforce", "SEO", "Go", "Prototyping", "Statistics", "Copywriting", "AWS", "R"]


def pool(rnd, n=160):
    out = []
    for i in range(n):
        mode = rnd.choice(["remote", "hybrid", "onsite"])
        lo = rnd.randrange(30, 140) * 1000
        out.append({"id": 5000 + i, "co": "Company %d" % rnd.randrange(30), "role": rnd.choice(TITLES), "mode": mode,
                    "type": rnd.choice(["job", "job", "internship", "coop"]), "sal": [lo, lo + rnd.randrange(5, 30) * 1000], "yrs": rnd.randrange(0, 7),
                    "loc": "Remote (US)" if mode == "remote" else rnd.choice(CITIES), "skills": rnd.sample(SKILLS, rnd.randrange(2, 5)),
                    "live": True, "source": rnd.choice(["Acme's careers page", "Remotive"]), "fit": rnd.randrange(35, 96)})
    return out


TASTES = [
    ("likes remote jobs", lambda j: j["mode"] == "remote"),
    ("likes design roles", lambda j: "Designer" in j["role"]),
    ("likes pay of $100k and more", lambda j: (j["sal"][0] + j["sal"][1]) / 2 >= 100000),
    ("likes internships and co-ops", lambda j: j["type"] in ("internship", "coop")),
]


def history(seed, likes, n=40):
    """a person who sees jobs in a random order and swipes right 85% of the time on what they like, 10% otherwise"""
    while True:
        rnd = random.Random(seed)
        jobs = pool(rnd)
        shown = rnd.sample(jobs, n)
        h = []
        for i, j in enumerate(shown):
            yes = rnd.random() < (0.85 if likes(j) else 0.10)
            h.append({"id": j["id"], "dir": "applied" if yes else "passed", "dwell": 0 if yes else rnd.choice([400, 900, 1600, 2600, 4000]),
                      "at": NOW - (n - i) * 3 * 3600000})
        held = [x["dir"] for x in h[-10:]]
        if "applied" in held and "passed" in held:   # both kinds among the hidden 10, or AUC means nothing
            return {"jobs": jobs, "history": h}
        seed += 1000


def auc(rows, key):
    pos = [r[key] for r in rows if r["dir"] == "applied"]
    neg = [r[key] for r in rows if r["dir"] == "passed"]
    return sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


wins = 0
for k, (name, likes) in enumerate(TASTES):
    fx = history(41 + k, likes)
    rows = ask(("replay", fx, 10))[0]
    a_learn, a_fixed = auc(rows, "z"), auc(rows, "fit")
    wins += a_learn > a_fixed
    t("replay, person %d (%s): AUC %.2f with learning vs %.2f with the match score alone" % (k + 1, name, a_learn, a_fixed), a_learn >= 0.5, (a_learn, a_fixed))
    # explanation check: every learned line names an attribute this job has, with the right counts from the 30 training swipes
    by = {j["id"]: j for j in fx["jobs"]}
    trained = fx["history"][:-10]
    bad = []
    for r in rows:
        if not r["delta"]:
            continue
        a = r["key"]
        if a not in r["attrs"]:
            bad.append((r["id"], a))
    t("replay, person %d: every learned line names an attribute the job really has" % (k + 1), not bad, bad)
    # recount from the history in Python (the same attribute rules, via the harness) and compare with the line
    ats = dict(zip([h["id"] for h in trained], ask(("attrs", [by[h["id"]] for h in trained]))[0]))
    wrong = []
    for r in rows:
        if not r["delta"]:
            continue
        yes = sum(1 for h in trained if r["key"] in ats[h["id"]] and h["dir"] == "applied")
        no = sum(1 for h in trained if r["key"] in ats[h["id"]] and h["dir"] == "passed")
        if (r["yes"], r["no"]) != (yes, no) or not re.search(r"(liked %d|passed on %d) of %d " % (yes, no, yes + no), r["why"]):
            wrong.append((r["id"], r["why"], yes, no))
    t("replay, person %d: the counts in every line match the swipe history" % (k + 1), not wrong, wrong[:3])
t("replay: learning ranks liked jobs above passed ones better than the match score alone on at least 3 of 4 people (%d of 4)" % wins, wins >= 3)

# ---------- a new person's first swipes never push the best match down (October 22) ----------
# Five right swipes on jobs unlike the best match used to bury it: with only yeses, every attribute that some (not all) liked jobs shared
# scored below this person's overall yes rate, and the card draw was wide, so a 95% match fell out of the top 10 on many draws.
COLD = [dict(id=1, co="Strong Analytics", role="Data Analyst", mode="onsite", type="job", sal=[80000, 100000], yrs=2, loc="Philadelphia, PA",
             skills=["SQL", "Python", "Tableau"], live=True, source="Strong Analytics careers page", fit=95)]
ROLES = ["Software Engineer", "Product Designer", "Account Executive", "Nurse", "Mechanic", "Teacher", "Chef", "Marketing Manager"]
for i in range(2, 41):
    COLD.append(dict(id=i, co="Company %d" % i, role=ROLES[i % len(ROLES)] + " %d" % i, mode=["onsite", "hybrid", "remote"][i % 3],
                     type="job", sal=[40000 + 2000 * i, 60000 + 2000 * i], yrs=i % 6, loc=["Philadelphia, PA", "Newark, NJ", "Remote (US)"][i % 3],
                     skills=["Skill%d" % (i % 7), "Skill%d" % (i % 5)], live=True, source="Company %d careers page" % i, fit=90 - i))
# five jobs unlike it (part-time, remote, other fields), each swiped right
for i, jid in enumerate((41, 42, 43, 44, 45)):
    COLD.append(dict(id=jid, co="Unrelated %d" % i, role=["Barista", "Dog Walker", "Delivery Driver", "Cashier", "Tutor"][i], mode="remote",
                     type="job", sal=[25000, 30000], yrs=0, loc="Remote (US)", skills=["Coffee", "Driving", "Customer Service"][:1 + i % 3],
                     live=True, source="Unrelated %d careers page" % i, fit=40))
ranks = ask(("coldStart", COLD, [41, 42, 43, 44, 45], 1, 40, 1792600000000))[0]
t("a 95%% match stays in the top 10 after a new person's first 5 right swipes on unrelated jobs (40 draws; worst rank %d)" % max(ranks),
  max(ranks) <= 10, ranks)
t("...and with so little to learn from, the deck stays in match order (the best match first on every draw)", all(r == 1 for r in ranks), ranks)

# ---------- an eager new person: right swipes first, then one quick pass (card Vgip6Itd, October 22) ----------
# Measured on the dev build before the fix (tools/ui-learn.js, made-up jobs): after 2 right swipes Filters said "You passed on 0 of 1
# software engineer roles"; after 7 right and 1 quick pass the best card lost a point "because" "You've passed on 0 of 2 software engineer
# roles", and a remote 85% job never seen dropped to 60%. A yes-heavy person's overall yes rate pushed every kind of job liked only
# once or twice below the centre, and the line then named a pass that never happened.
EG = [dict(id=700 + i, co="Eager Co %d" % i, role=["Software Engineer", "Data Analyst"][i % 2] + " %d" % i, mode="onsite", type="job",
           sal=[120000, 140000], yrs=i % 3, loc="New York, NY", skills=["SQL", "React"][: 1 + i % 2], live=True, source="Eager Co careers page") for i in range(8)]
eh = [{"id": j["id"], "at": NOW - (8 - i) * 60000, "k": "R", "a": a} for i, (j, a) in enumerate(zip(EG, ask(("attrs", EG))[0]))]
NEXT = dict(EG[0], id=799, co="Next Co", role="Software Engineer", yrs=0)
two = eh[:2]
r2, s2 = ask(("ready", two, NOW), ("scoreEv", NEXT, 95, two, NOW))
t("eager new person, 2 right swipes: not ready to learn, the next card keeps its 95%% and has no reason line (%d%%, '%s')" % (s2["shown"], s2["explain"]["why"]),
  r2 is False and s2["shown"] == 95 and s2["delta"] == 0 and s2["explain"]["why"] == "", s2)
for n in range(1, 8):
    rn, sn = ask(("ready", eh[:n], NOW), ("scoreEv", NEXT, 95, eh[:n], NOW))
    if rn or sn["delta"]:
        t("eager new person: no score moves before %d swipes (moved at %d)" % (K["minN"], n), False, sn)
        break
else:
    t("eager new person: no score moves before %d swipes (1 to 7 right swipes, the card stays 95%%)" % K["minN"], True)
all8 = eh
r8, s8 = ask(("ready", all8, NOW), ("scoreEv", NEXT, 95, all8, NOW))
t("8 right swipes and no pass: still nothing to compare with, nothing moves", r8 is False and s8["delta"] == 0, s8)
# 7 right, then one quick pass: now the learner may move scores, but only with reasons that happened
mixed = eh[:7] + [dict(eh[7], k="L", d=300)]
probe = [NEXT, dict(NEXT, id=798, role="Data Analyst", skills=["SQL"]), dict(NEXT, id=797, mode="remote", loc="Remote (US)", skills=["SQL", "Go"]),
         dict(NEXT, id=796, yrs=2, skills=["React"])]
r8m = ask(("ready", mixed, NOW))[0]
sc = ask(*[("scoreEv", j, 95 - 5 * k, mixed, NOW) for k, j in enumerate(probe)])
lies = [(x["explain"]["why"], x["explain"].get("yes"), x["explain"].get("no")) for x in sc if x["delta"] and (
        (x["delta"] < 0 and not x["explain"].get("no")) or (x["delta"] > 0 and not x["explain"].get("yes")) or re.search(r"(passed on|liked) 0 of", x["explain"]["why"]))]
t("7 right and 1 quick pass: ready to learn, and no card's reason claims a pass (or a like) that did not happen",
  r8m is True and not lies, (r8m, lies, [(x["shown"], x["explain"]["why"]) for x in sc]))
down_parts = [(p["a"], round(p["c"], 3)) for x in sc for p in x["parts"] if p["c"] < 0 and not any(h["k"] == "L" and p["a"] in h["a"] for h in mixed)]
t("a kind of job this person never passed on cannot pull a card down (centring only measures, never invents a no)", not down_parts, down_parts)
up_parts = [(p["a"], round(p["c"], 3)) for x in sc for p in x["parts"] if p["c"] > 0 and not any(h["k"] != "L" and p["a"] in h["a"] for h in mixed)]
t("and a kind of job this person never liked cannot push a card up", not up_parts, up_parts)
lines = ask(*[("line", {"pct": x["shown"], "fit": x["fit"], "learn": {"delta": x["delta"], "why": x["explain"]["why"], "explore": False}}) for x in sc])
t("no card line says 'passed on 0' or 'liked 0'", not any(re.search(r"(passed on|liked) 0 of", l) for l in lines),
  [l.encode("ascii", "replace").decode() for l in lines])

# ---------- an eager new person taps Undo: an Undo is never a pass (card Vgip6Itd, review round 1, October 22) ----------
# Measured on dev and sandbox before this: 8 right swipes, then Undo of the 8th (kinds RRRRRRRU, no swipe left at all). The learner
# counted the Undo as a pass, became "ready", and the card just undone read "Learned from your swipes: -10. You've passed on 1 of 2
# product design roles."; 7 of the next 12 cards claimed a pass, and Filters said "You passed on 1 of 2 product design roles."
def undo_ops(rights, undo_at, after):
    ops, k = [], 0
    for j in EG[:rights]:
        k += 1; ops.append({"op": "swipe", "job": j, "dir": "applied", "dwell": 0, "at": NOW - (20 - k) * 60000})
        if j is EG[undo_at - 1]:
            ops.append({"op": "undo", "id": j["id"]})
    for j in after:
        k += 1; ops.append({"op": "swipe", "job": j, "dir": "applied", "dwell": 0, "at": NOW - (20 - k) * 60000})
    return ask(("ops", ops))[0]["ev"]
ua = undo_ops(8, 8, [])                                                   # 8 right, Undo of the 8th
ub = undo_ops(6, 6, [dict(EG[6], id=760), dict(EG[7], id=761)])          # 6 right, Undo of the 6th, 2 more right
UPROBE = [EG[7], EG[5]] + probe
for name, uev in (("8 right then Undo of the 8th", ua), ("6 right, Undo, 2 right", ub)):
    kinds = "".join(e["k"] for e in uev)
    ru, ev_u = ask(("ready", uev, NOW), ("evidence", uev, NOW))
    su = ask(*[("scoreEv", j, 95 - 3 * k, uev, NOW) for k, j in enumerate(UPROBE)])
    claims = [(x["shown"], x["explain"]["why"]) for x in su if x["delta"] or x["explain"]["why"]]
    t("%s (%s): not ready, an Undo is not one of the %d swipes nor a pass (%d swipes, %d passes)" % (name, kinds, K["minN"], ev_u["dec"], ev_u["P"]),
      kinds.count("U") == 1 and "L" not in kinds and ru is False and ev_u["dec"] == 7 and ev_u["P"] == 0, (kinds, ru, ev_u["dec"], ev_u["P"]))
    t("%s: every card keeps its match score, the one just undone included, and no reason names a pass" % name, not claims, claims)
    t("%s: no attribute counts a pass" % name, all(c["no"] == 0 for c in ev_u["cnt"].values()), {a: c for a, c in ev_u["cnt"].items() if c["no"]})
    udeck = [{"j": j, "m": {"pct": 95 - 3 * k}} for k, j in enumerate(UPROBE)]
    uo = ask(("order", udeck, {"v": 1, "seed": 7, "n": 7, "ver": 9, "ev": uev}, NOW, None))[0]
    t("%s: the deck stays in match order, with no learned line and no 'Something different' card" % name,
      uo["same"] and not any(uo["line"]), (uo["same"], uo["line"]))
# Once there is a real pass, an Undo may still take some of the lean up away, but it never becomes a reason, and the pass counts are real.
uc = ua + [{"id": 790, "at": NOW - 30000, "k": "L", "d": 300, "a": ask(("attrs", [dict(NEXT, id=790, co="Pass Co", role="Data Analyst", mode="remote", loc="Remote (US)", skills=["Go"])]))[0][0]}]
ruc, ev_c = ask(("ready", uc, NOW), ("evidence", uc, NOW))
sc_u = ask(*[("scoreEv", j, 95 - 3 * k, uc, NOW) for k, j in enumerate(UPROBE)])
passes = lambda a: sum(1 for h in uc if h["k"] == "L" and a in h["a"])
bad_down = [(p["a"], round(p["c"], 3)) for x in sc_u for p in x["parts"] if p["c"] < 0 and not passes(p["a"])]
bad_why = [x["explain"]["why"] for x in sc_u if x["delta"] < 0 and (not x["explain"].get("no") or x["explain"]["no"] != passes(x["explain"]["key"]))]
t("8 right, Undo, then 1 real pass: ready, and only kinds of job really passed on can pull a card down (an Undo alone never does)",
  ruc is True and ev_c["P"] == 1 and not bad_down, (ruc, bad_down))
t("...and every 'passed on N' counts real swipes left only, never the Undo", not bad_why, (bad_why, [(x["shown"], x["explain"]["why"]) for x in sc_u]))

# ---------- an Undo is not one of the 30 swipes either (card Vgip6Itd, review round 2, October 22) ----------
# Measured before this: 29 real swipes, then a right swipe and its Undo, stored 30 entries. The early limit (25) and the strong-match
# floor (a 90%+ match loses at most 10 points before 30 swipes) counted entries, not swipes, so one Undo let a 95% card fall to 55.
MJ = [dict(id=600 + i, co="Co %d" % (i % 7), role=["Software Engineer", "Data Analyst", "Product Designer"][i % 3], mode=["onsite", "remote", "hybrid"][i % 3],
           type="job", sal=[100000, 130000], yrs=i % 3, loc="New York, NY", skills=[["SQL", "Go"], ["React", "CSS"], ["Figma"]][i % 3], live=True,
           source="Co careers page") for i in range(36)]
def swipes29(extra):
    ops = [{"op": "swipe", "job": MJ[i], "dir": "applied" if i % 3 == 1 else "passed", "dwell": 300, "at": NOW - (100 - i) * 60000} for i in range(29)]
    return ask(("ops", ops + extra))[0]["ev"]
STRONG = dict(MJ[0], id=690, co="Co 0", yrs=0)
plain29 = swipes29([])
undo29 = swipes29([{"op": "swipe", "job": MJ[30], "dir": "applied", "dwell": 0, "at": NOW - 60000}, {"op": "undo", "id": MJ[30]["id"]}])
undo25 = ask(("ops", [{"op": "swipe", "job": MJ[i], "dir": "applied" if i % 3 == 1 else "passed", "dwell": 300, "at": NOW - (100 - i) * 60000} for i in range(25)]
              + [o for k in range(5) for o in ({"op": "swipe", "job": MJ[30 + k], "dir": "applied", "dwell": 0, "at": NOW - (10 - k) * 60000}, {"op": "undo", "id": MJ[30 + k]["id"]})]))[0]["ev"]
s29, su29, su25 = ask(("scoreEv", STRONG, 95, plain29, NOW), ("scoreEv", STRONG, 95, undo29, NOW), ("scoreEv", STRONG, 95, undo25, NOW))
ev29u = ask(("evidence", undo29, NOW))[0]
t("29 swipes then a right swipe and Undo: still 29 swipes (30 stored), the early limit stays %d" % K["capEarly"],
  ev29u["n"] == 30 and ev29u["dec"] == 29 and su29["lim"] == K["capEarly"] == s29["lim"], (ev29u["n"], ev29u["dec"], s29["lim"], su29["lim"]))
t("...and the 95%% match the 29 swipes pull down is held at %d or above, Undo or not (shown %s, %s without the Undo)" % (95 - K["strongDrop"], su29["shown"], s29["shown"]),
  s29["delta"] < 0 and su29["shown"] >= 95 - K["strongDrop"] and su29["shown"] == s29["shown"], (s29["shown"], su29["shown"]))
t("25 swipes and 5 Undos: still before the 30 swipes, limit %d and the 95%% match held at %d or above (shown %s)" % (K["capEarly"], 95 - K["strongDrop"], su25["shown"]),
  su25["lim"] == K["capEarly"] and su25["shown"] >= 95 - K["strongDrop"], (su25["lim"], su25["shown"]))
udk = [{"j": STRONG, "m": {"pct": 95}}] + [{"j": dict(MJ[k], id=650 + k), "m": {"pct": 99 - k}} for k in range(1, 12)]
uo29 = ask(("order", udk, {"v": 1, "seed": 7, "n": 29, "ver": 31, "ev": undo29}, NOW, None))[0]
spct = uo29["pct"][uo29["ids"].index(STRONG["id"])]
t("...in the deck too: the 95%% card shows %s (at least %d), and each card's learn count is the 29 swipes, not the 30 stored entries" % (spct, 95 - K["strongDrop"]),
  not uo29["same"] and spct >= 95 - K["strongDrop"] and set(uo29["learnN"]) == {29}, (spct, set(uo29["learnN"])))

# ---------- the sandbox page still assembles; dev does not get it ----------
asm = ask(("assemble",))[0]
t("sandbox: every feature that is on (learn included) patches the production page and the result parses", asm["parses"] and not asm["err"], asm["err"])
t("sandbox: learn is on, its hooks are in the page, and it runs last in ORDER (right after chat)", asm["learnOn"] and asm["hooks"] and asm["learnLast"], asm)
t("sandbox and dev both load shared/uaply-learn.js, and dev lists learn in PROMOTED (promoted October 17)", asm["sandboxLoads"] and asm["devLoads"] and asm["devPromoted"], asm)

shutil.rmtree(TMP, ignore_errors=True)
ok = sum(R)
print("\n%d / %d" % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)
