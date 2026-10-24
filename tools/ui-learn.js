// Swipe learning on the sandbox or dev (PORT) at iPhone size: 30 real finger swipes with a clear pattern (right on remote, left on on-site), then
// the deck must put remote jobs first, the card must say what it learned with the right counts, 1 card in 5 must still be something
// else, Filters must have a Reset that clears it, and nothing may throw a script error.
//   W=390 H=844 PORT=19801 node tools/cdp.js tools/ui-learn.js        (SHOTS=<folder> also saves screenshots)
// The test shows only its own 80 made-up jobs (on-site ones match the profile better than remote ones), and turns off the apply step
// after a swipe right and the "Finish your profile first" gate before it (both are tested elsewhere): it checks what the learner does with
// the swipes, nothing else.
const PORT = process.env.PORT || "18766";
const path = require("path");
const gateSignup = require("./gate-signup.js");   // the test person signs up first (Saif, October 22: no account, no data)
module.exports = async (ctx) => {
  try { await learnTest(ctx); } catch (e) { console.log("FAIL the test stopped before its last check: " + (e && e.message)); throw e; }
};
async function learnTest({ ev, sleep, nav, send, logs, shot }) {
  const F = "document.querySelector('iframe').contentDocument";
  const FW = "document.querySelector('iframe').contentWindow";
  let bad = 0, n = 0;
  const failed = [];   // named again at the very end: the runner keeps only the last lines of a failed test
  const check = (name, ok, extra) => { n++; if (!ok) { bad++; failed.push(name + (extra ? "  " + String(extra).slice(0, 200) : "")); } console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const J = (x) => ev("JSON.stringify(" + x + ")").then((s) => (typeof s === "string" && !s.startsWith("JSERR") ? JSON.parse(s) : s));
  const snap = async (name) => { if (process.env.SHOTS) await shot(path.join(process.env.SHOTS, name)); };
  const pick = async (nb, label) => { await ev(F + ".getElementById('" + nb + "').click()"); await sleep(450); return ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith(" + JSON.stringify(label) + "));if(!e)return false;e.click();return true})()"); };
  // the top card: its job, the ring, and the learned line
  const top = () => J("(()=>{const w=" + FW + ",c=" + F + ".querySelector('.card.top');if(!c)return null;const id=+c.getAttribute('data-id'),j=w.__uaply.JOBS.find(x=>x.id===id),l=c.querySelector('.learned');" +
    "return {id:id,mode:j&&j.mode,ring:c.querySelector('.ring b').textContent,line:l?l.textContent:'',explore:!!(l&&l.getAttribute('data-explore'))}})()");
  // a finger drag across the top card (the same as tools/ui-swipes.js)
  const drag = async (dx) => {
    // where a finger would touch: the middle of the part of the card that is in sight, above Pass / Undo / Apply (notices above the deck,
    // such as the location box, can push most of the card below that row; the deck scrolls, the buttons stay)
    const r = await J("(()=>{const d=" + F + ",c=d.querySelector('.card.top');const f=document.querySelector('iframe').getBoundingClientRect();const b=c.getBoundingClientRect();" +
      "const bar=d.getElementById('btnNo'),lim=bar?bar.getBoundingClientRect().top-8:b.bottom,top=Math.max(b.top,0),bot=Math.min(b.bottom,lim);" +
      "return {x:f.left+b.left+b.width/2,y:f.top+(bot>top+40?Math.min(b.top+b.height/3,(top+bot)/2):b.top+b.height/3)}})()");
    const pt = (x) => [{ x: Math.round(x), y: Math.round(r.y), id: 1 }];
    await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pt(r.x) });
    for (let i = 1; i <= 8; i++) { await send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: pt(r.x + (dx * i) / 8) }); await sleep(30); }
    await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await sleep(900);
  };
  const decided = () => ev("Object.keys(" + FW + ".__uaply.S.decisions).length");

  await gateSignup({ ev, sleep, nav }, "http://127.0.0.1:" + PORT, "learn");
  await nav("http://127.0.0.1:" + PORT + "/?app=1");
  await sleep(3500);
  if (await ev("!!" + F + ".getElementById('kcYes')")) { await ev(F + ".querySelectorAll('.kcTick,#kcYes').forEach(c=>{if(c.id==='kcYes'){c.disabled=false;c.click()}else c.checked=true})"); await sleep(400); }
  check("this build (sandbox or dev) has the learner on", await ev("!!(" + FW + ".__uaplyLearn&&" + FW + ".__uaplyLearnOrder)"));
  check("a new visitor starts with nothing learned", (await J(FW + ".__uaplyLearn.state().ev.length")) === 0);
  // the same run every time: wait until the real feeds (if this server has them) have loaded, so no late redraw lands mid-swipe,
  // and fix the learner's random seed (a new visitor otherwise gets a random one)
  // (the sandbox says so in its controls bar; dev has no bar, so there it waits until the app stops loading jobs)
  for (let i = 0; i < 60; i++) { if (await ev("(()=>{const n=document.getElementById('note');return n?/^(Real postings|Could not load)/.test(n.textContent||''):!" + FW + ".__uaplyLoadingJobs})()")) break; await sleep(500); }
  // the deck reads the first page, then the whole list in the background (shared/uaply-live.js): wait for that too, and for the job count
  // to stay put for two seconds, so the whole list never lands in the middle of the swipes below
  for (let i = 0, last = -1, same = 0; i < 120 && same < 4; i++) {
    const st = JSON.parse(await ev("(()=>{const w=" + FW + ";return JSON.stringify({rk:w.document.documentElement.classList.contains('uaRank'),n:w.__uaply.JOBS.length})})()"));
    same = !st.rk && st.n === last ? same + 1 : 0; last = st.n; await sleep(500);
  }
  await ev(FW + ".__uaplyLearn.state().seed=20261016");

  // 80 made-up jobs: 40 on-site in New York asking for skills the example profile has (they match best), 40 remote asking for half of them
  await ev("(()=>{const w=" + FW + ",A=w.__uaply;w.__uaplyOnDecision=null;w.__uaplyReadyGate=function(){return false};w.__uaplyHideSamples=true;const h0=w.__uaplyHide;" +
    "w.__uaplyHide=function(j){return !j.lrnTest||(h0?h0(j):false)};" +   /* only the test's own jobs, marked: a real posting's id can be any number (900570 was one) */
    "A.S.profile.modes={remote:true,hybrid:true,onsite:true};A.S.profile.loc='New York';" +
    "const roles=['Software Engineer','Frontend Developer','Data Analyst','Product Designer'],mine=['JavaScript','React','TypeScript','CSS','HTML','SQL'],other=['Go','Rust','Kotlin','Elixir','Scala','Haskell'],list=[];" +
    "for(let i=1;i<=80;i++){const rem=i%2===0,k=i%4;list.push({id:900000+i,co:'Test Co '+i,role:roles[(i>>1)%4],mode:rem?'remote':'onsite',loc:rem?'Remote (US)':'New York, NY',type:'job'," +
    "sal:[95000+k*5000,120000+k*5000],yrs:k,edu:'Bachelor',skills:rem?[mine[i%6],mine[(i+1)%6],other[i%6],other[(i+3)%6]]:[mine[i%6],mine[(i+1)%6],mine[(i+2)%6],(i%3?mine[(i+3)%6]:other[i%6])]," +
    "blurb:'A made-up job for the swipe learning test.',live:true,lrnTest:true,source:'Test Co careers page'})}w.__uaplyJobs.add(list)})()");
  await sleep(800);
  const before = await J(FW + ".__uaplyLearn.peek(6)");
  check("before any swipe: the deck is in match order and on-site jobs come first (they fit the profile better)",
    Array.isArray(before) && before[0].mode === "onsite" && before.every((x, i) => i === 0 || before[i - 1].fit >= x.fit) && before.every((x) => !x.delta && !x.explore),
    JSON.stringify((before || []).map((x) => x.mode + " " + x.fit)));
  const fits = await J("(()=>{const q=" + FW + ".__uaplyQueue();const r={remote:[],onsite:[]};q.forEach(x=>r[x.j.mode].push(x.m.pct));return {r:Math.max(...r.remote),o:Math.min(...r.onsite)}})()");
  check("every on-site job matches the profile better than every remote one (" + fits.o + "% or more vs " + fits.r + "% or less)", fits.o > fits.r);
  if (process.env.DEBUG) console.log("DEBUG " + await ev("(()=>{const w=" + FW + ",A=w.__uaply,q=w.__uaplyQueue();const lo=q.filter(x=>x.j.mode==='onsite').sort((a,b)=>a.m.pct-b.m.pct)[0];return JSON.stringify({profile:A.S.profile,lo:lo&&{id:lo.j.id,pct:lo.m.pct,rows:lo.m.rows.map(r=>[r.k,r.s,r.ask,r.have])}})})()"));

  // 30 real swipes: right on remote, left on everything else
  const tally = { remoteRight: 0, otherLeft: 0 };
  let missed = 0;
  for (let i = 0; i < 30; i++) {
    const c = await top(), n0 = await decided();
    if (!c) { missed++; break; }
    // a pass counts more the longer the card was read (shared/uaply-learn.js: 0.7 s to 2 s): read each card past 2 s before passing it, so
    // every pass weighs the same in every run (at about 0.7 s, timing jitter changed the weights and with them the order of equal cards)
    await sleep(c.mode === "remote" ? 300 : 2300);
    await drag(c.mode === "remote" ? 170 : -170);
    if ((await decided()) !== n0 + 1) missed++;
    if (c.mode === "remote") tally.remoteRight++; else tally.otherLeft++;
  }
  check("30 finger swipes all landed", missed === 0, "missed " + missed);
  const st = await J("(()=>{const s=" + FW + ".__uaplyLearn.state();return {n:s.n,ev:s.ev.length,k:s.ev.map(e=>e.k).join('')}})()");
  check("the learner saw all 30 (" + tally.remoteRight + " right on remote, " + tally.otherLeft + " left on on-site)", st.n === 30 && st.ev === 30 && tally.remoteRight > 5 && tally.otherLeft > 5, JSON.stringify(st));
  check("the learner is saved with the swipes in this browser", await ev("(()=>{try{return JSON.parse(" + FW + ".localStorage.getItem(" + FW + ".__uaplyKey)).learn.ev.length===30}catch(e){return false}})()"));

  // the next cards: remote first
  const next = await J(FW + ".__uaplyLearn.peek(12)");
  const regular = next.filter((x) => !x.explore);
  const firstOther = regular.findIndex((x) => x.mode !== "remote"), lastRemote = regular.map((x) => x.mode).lastIndexOf("remote");
  check("after 30 swipes the next cards are remote first (" + regular.slice(0, 8).map((x) => x.mode).join(", ") + ")",
    regular.slice(0, 8).every((x) => x.mode === "remote") && (firstOther < 0 || firstOther > lastRemote));
  // What the design promises: what you liked pushes cards up and what you passed pushes them down, attribute by attribute. A remote
  // card can still end below its fit when its other attributes (role, pay band, years, skills) were mostly passed; then its line
  // must name one of those, never "remote".
  const rem = next.filter((x) => x.mode === "remote"), ons = next.filter((x) => x.mode !== "remote");
  const fell = rem.filter((x) => x.pct < x.fit);
  check("remote cards went up on average and every on-site card went down (" + JSON.stringify(next.map((x) => x.mode + " " + x.fit + "->" + x.pct)) + ")",
    rem.length && rem.reduce((s, x) => s + x.pct - x.fit, 0) > 0 && ons.every((x) => x.pct < x.fit));
  check("any remote card that ended below its fit says why with another attribute it has, never remote (" + fell.length + " such cards)",
    fell.every((x) => x.key && x.key !== "m:remote" && /^You've passed on /.test(x.why)), JSON.stringify(fell.map((x) => x.key + ": " + x.why)));

  // the line on the card
  const c1 = await top();
  const m = /^Learned from your swipes: \+(\d+)\. You've liked (\d+) of (\d+) remote jobs\. Profile fit alone: (\d+)%\./.exec(c1.line || "");
  check("the top card is a remote job and says 'Learned from your swipes: +N. You've liked R of T remote jobs.'", c1.mode === "remote" && !!m, c1.line);
  if (m) {
    check("its counts match the swipes: liked " + m[2] + " of " + m[3] + " remote jobs (" + tally.remoteRight + " swiped right, all remote ones)", +m[2] === tally.remoteRight && +m[3] === tally.remoteRight);
    check("the ring shows profile fit + the learned points (" + m[4] + "% + " + m[1] + " = " + c1.ring + ")", +c1.ring.replace("%", "") === +m[4] + +m[1]);
  }
  await snap("learn-1-after-30-swipes.png");

  // 1 in 5 is still something else: the next 5 cards shown
  const seen = [];
  for (let i = 0; i < 5; i++) {
    const c = await top();if (!c) { check("a card is on top for the next 5 swipes (" + i + " so far)", false); break; }seen.push(c);
    await sleep(300);
    if (c.explore) await snap("learn-2-explore-card.png");
    if (c.mode !== "remote") await sleep(2000);
    await drag(c.mode === "remote" ? 170 : -170);
  }
  const ex = seen.findIndex((c) => c.mode !== "remote");
  check("within the next 5 cards a non-remote card is shown (" + seen.map((c) => c.mode + (c.explore ? "*" : "")).join(", ") + "; * = explore slot)",
    ex > -1 && seen[ex].explore && /Something different/.test(seen[ex].line));
  check("the explore card still says what was learned about it ('passed on N of N on-site jobs')", ex > -1 && /You've passed on (\d+) of \1 on-site jobs\./.test(seen[ex].line), ex > -1 ? seen[ex].line : "");

  // Reset in Profile, Filters
  check("Profile, Filters opens", await pick("nb-prof", "Filters")); await sleep(600);
  const box = await J("(()=>{const b=" + F + ".getElementById('lrnBox');if(!b)return null;const r=b.getBoundingClientRect();return {vis:r.height>0&&getComputedStyle(b).display!=='none',sum:" + F + ".getElementById('lrnSum').textContent,btn:" + F + ".getElementById('lrnReset').textContent}})()");
  check("Filters shows what UAply learned, naming remote", box && box.vis && /Learned from your last 35 swipes/.test(box.sum) && /remote jobs/.test(box.sum) && /on-site jobs/.test(box.sum), box && box.sum);
  check("Filters has a 'Reset what UAply learned' button", box && box.btn === "Reset what UAply learned");
  await ev(F + ".getElementById('lrnBox').scrollIntoView()"); await sleep(300);
  await snap("learn-3-filters-before-reset.png");
  await ev(F + ".getElementById('lrnReset').click()"); await sleep(500);
  const after = await J("(()=>{const w=" + FW + ";let saved=-1;try{saved=JSON.parse(w.localStorage.getItem(w.__uaplyKey)).learn.ev.length}catch(e){}return {ev:w.__uaplyLearn.state().ev.length,n:w.__uaplyLearn.state().n,saved:saved,sum:" + F + ".getElementById('lrnSum').textContent}})()");
  check("Reset clears it, in memory and in the saved copy", after.ev === 0 && after.n === 0 && after.saved === 0, JSON.stringify(after));
  check("Reset says so", /^Done\. UAply forgot what it learned/.test(after.sum), after.sum);
  await snap("learn-4-filters-after-reset.png");
  await pick("nb-svc", "Full-time"); await sleep(800);
  const back = await J(FW + ".__uaplyLearn.peek(6)"), c2 = await top();
  check("after Reset the deck is back in match order with no learned numbers or lines",
    back.every((x, i) => (i === 0 || back[i - 1].fit >= x.fit) && !x.delta && !x.explore && x.pct === x.fit) && c2 && !c2.line && back[0].mode === "onsite",
    JSON.stringify(back.map((x) => x.mode + " " + x.fit + "/" + x.pct)) + " " + (c2 && c2.line));
  const swipesKept = await decided();
  check("Reset leaves the swipes themselves alone (35 decisions still in Applied / Passed)", swipesKept === 35, swipesKept);

  // no script errors at any point
  const errs = logs.filter((l) => l.startsWith("EXC") || l.startsWith("ERR"));
  check("no script errors", errs.length === 0, errs.join(" | ").slice(0, 300));
  console.log(bad ? bad + " problem(s)" : "All good");
  if (bad) { console.log("FAILED: " + failed.join(" | ")); process.exitCode = 1; }
  console.log((n - bad) + " / " + n);
}
