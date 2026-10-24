// The app starts without waiting on anything outside it, and a reload never loses a swipe. In a real browser, on dev or the sandbox:
//   W=390 H=844 PORT=18767 node tools/cdp.js tools/ui-boot.js        (a server with the job feeds on)
// 1. fonts.googleapis.com never answers (a slow phone network, a blocked font site): the agreement box, the navigation and the swipe
//    learner are still there within a few seconds. They used to wait for the page's load event, which waits for every font: 20 s here.
// 2. swipes on real postings survive a reload even while /api/jobs has not answered yet (or the job left the feed): the start-up read
//    used to drop every decision whose job was not in the list yet, and the next save made the loss permanent.
const PORT = process.env.PORT || "8767";
const gateSignup = require("./gate-signup.js");   // the test person signs up first (Saif, October 22: no account, no data)
module.exports = async ({ ev, sleep, send, on, logs }) => {
  const F = "document.querySelector('iframe')&&document.querySelector('iframe').contentDocument";
  const FW = "(document.querySelector('iframe')||{}).contentWindow";
  let bad = 0;
  const check = (n, ok, x) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? "  " + x : "")); };
  const base = "http://127.0.0.1:" + PORT + "/";
  let holdJobs = false;
  // fonts.googleapis.com and fonts.gstatic.com never answer; /api/jobs is held back when asked
  await send("Fetch.enable", { patterns: [{ urlPattern: "*fonts.googleapis.com*" }, { urlPattern: "*fonts.gstatic.com*" }, { urlPattern: "*/api/jobs*" }] });
  on("Fetch.requestPaused", (p) => {
    if (/fonts\.(googleapis|gstatic)\.com/.test(p.request.url)) return;                 // left hanging, like a font site that never answers
    if (holdJobs) return;                                                                 // the job list has not arrived yet
    send("Fetch.continueRequest", { requestId: p.requestId });
  });
  const ready = async (ms) => {
    const t0 = Date.now(), seen = {};
    while (Date.now() - t0 < ms) {
      for (const [k, x] of Object.entries({ agree: "!!(" + F + "&&" + F + ".getElementById('kcYes'))", nav: "!!(" + F + "&&" + F + ".getElementById('nb-svc'))", learn: "!!(" + FW + "&&" + FW + ".__uaplyLearn)" }))
        if (!seen[k]) { let v = false; try { v = await ev(x); } catch (e) {} if (v === true) seen[k] = Date.now() - t0; }
      if (Object.keys(seen).length === 3) break;
      await sleep(100);
    }
    return seen;
  };

  await gateSignup({ ev, sleep, nav: (u) => send("Page.navigate", { url: u }).then(() => sleep(300)) }, "http://127.0.0.1:" + PORT, "boot");
  // 1. a font site that never answers
  await send("Page.navigate", { url: base });
  const t = await ready(6000);
  check("with the font site never answering, the agreement box, the navigation and the learner are there within 6 s",
    t.agree !== undefined && t.nav !== undefined && t.learn !== undefined, JSON.stringify(t) + " ms");

  // 2. swipe on real postings, then reload while the job list is held back
  await ev("(()=>{const b=" + F + ".getElementById('kcYes');if(b){b.ownerDocument.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});b.disabled=false;b.click()}})()");
  await ev(require("./fixtures/ready-profile.js").readyProfile());   // the least a swipe right needs (name, email, phone): else the card does not move
  for (let i = 0; i < 60 && !(await ev("!!(" + FW + ".__uaply&&" + FW + ".__uaply.JOBS.filter(j=>j.live).length>5)")); i++) await sleep(500);
  for (const id of ["btnNo", "btnYes", "btnYes"]) { await ev(F + ".getElementById('" + id + "').click()"); await sleep(1500); await ev("(()=>{const b=" + F + ".getElementById('kcYes');if(b){b.ownerDocument.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});b.disabled=false;b.click()}})()"); }
  const before = await ev("JSON.stringify(Object.keys(" + FW + ".__uaply.S.decisions).sort())");
  check("three swipes on real postings are recorded", JSON.parse(before).length === 3 && JSON.parse(before).every((k) => +k >= 100000), before);
  holdJobs = true;
  await send("Page.reload");
  await sleep(3000);
  const after = await ev("JSON.stringify(Object.keys((" + FW + ".__uaply||{S:{decisions:{}}}).S.decisions).sort())");
  check("after a reload, before the job list has arrived, the swipes are still there", after === before, after + " vs " + before);
  const saved = await ev("(()=>{const w=" + FW + ";try{return JSON.stringify(Object.keys(JSON.parse(w.localStorage.getItem(w.__uaplyBuildKey||w.__uaplyKey)).decisions).sort())}catch(e){return 'none'}})()");
  check("...and in what this browser saved", saved === before, saved);
  holdJobs = false;
  check("no script errors", logs.length === 0, logs.join(" / ").slice(0, 300));
  console.log(bad ? bad + " problem(s)" : "All good");
};
