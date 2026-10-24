// Always jobs (Saif, October 24, 2026): a person always has jobs to swipe, at any match. On the sandbox or dev (PORT), as a new sign-up:
//   - narrow filters (Internships, on-site, minimum match 90) with no job inside them: the deck still has 20 or more cards, every one
//     marked "Outside your filters: ..." on the card, nearest first;
//   - minimum match 90 still works as a filter: every card inside the filters is at 90% or more, every card below it says so;
//   - the learner moves a liked match band up after 15 swipes;
//   - the deck is empty only when everything has been swiped, and then it says so.
//   W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-always-jobs.js
const PORT = process.env.PORT || "18766";
const gateSignup = require("./gate-signup.js");
module.exports = async ({ ev, sleep, nav, logs }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra && !ok ? "  | " + String(extra).slice(0, 300) : "")); };
  const J = async (x) => { const s = await ev("JSON.stringify(" + x + ")"); try { return JSON.parse(s); } catch (e) { return s; } };
  await gateSignup({ ev, sleep, nav }, "http://127.0.0.1:" + PORT, "always");
  await nav("http://127.0.0.1:" + PORT + "/?app=1");
  await sleep(3500);
  if (await ev("!!" + F + ".getElementById('kcYes')")) { await ev(F + ".getElementById('kcYes').click()"); await sleep(400); }
  for (let i = 0; i < 60; i++) { if (await ev("!" + FW + ".__uaplyLoadingJobs")) break; await sleep(500); }
  // only this test's own 40 jobs: full-time and remote, so none is an on-site internship
  await ev("(()=>{const w=" + FW + ",A=w.__uaply;w.__uaplyOnDecision=null;w.__uaplyHideSamples=true;const h0=w.__uaplyHide;" +
    "w.__uaplyHide=function(j){return !j.ajTest||(h0?h0(j):false)};const list=[];" +
    "for(let i=1;i<=40;i++)list.push({id:910000+i,co:'Always Co '+i,role:(i%2?'Data Analyst':'Software Engineer'),mode:'remote',loc:'Remote (US)',type:'job',sal:[60000,80000],yrs:i%4,edu:'Bachelor'," +
    "skills:i%3?['SQL','Excel']:['Go','Rust'],blurb:'A made-up job for the always-jobs test.',live:true,ajTest:true,source:'Always Co careers page'});" +
    "w.__uaplyJobs.add(list);A.setType('internship');A.setFilter('onsite');A.setMin(90);A.renderAll();return 1})()");
  await sleep(800);
  const q = await J("(" + FW + ".__uaplyQueue?" + FW + ".__uaplyQueue():[]).map(x=>({id:x.j.id,out:x.out||'',pct:x.m.pct}))");
  check("narrow filters with no job inside them: the deck still has 20 or more cards", Array.isArray(q) && q.length >= 20, Array.isArray(q) ? q.length : q);
  check("...every one marked outside the filters (full-time, remote)", Array.isArray(q) && q.every((x) => /full-time/.test(x.out) && /remote/.test(x.out)), JSON.stringify((q || []).slice(0, 3)));
  const line = await ev("(()=>{const p=" + F + ".querySelector('#deck .card.top .outside');return p?p.textContent:''})()");
  check("the top card says it on one line: 'Outside your filters: full-time, remote, ...'", /^Outside your filters: full-time, remote/.test(line), line);
  // minimum match 90 still filters: on the test's own jobs in their own stack, inside the filters only 90% and up
  await ev("(()=>{const A=" + FW + ".__uaply;A.setType('job');A.setFilter('all');A.setMin(90);A.renderAll();return 1})()");
  await sleep(500);
  const q2 = await J("(" + FW + ".__uaplyQueue()).map(x=>({out:x.out||'',pct:x.m.fit==null?x.m.pct:x.m.fit}))");
  const inn = q2.filter((x) => !x.out), outs = q2.filter((x) => x.out);
  check("minimum match 90 still works as a filter: every card inside it is at 90% or more", inn.every((x) => x.pct >= 90), JSON.stringify(inn.slice(0, 3)));
  check("...and every card below it is marked 'below 90% match', after the ones inside", outs.every((x) => /below 90% match/.test(x.out)) && q2.slice(0, inn.length).every((x) => !x.out), JSON.stringify(outs.slice(0, 3)));
  // no hard gate by default: minimum match back to 0 (Filters "Show everything"), the whole stack is inside
  await ev("(()=>{const A=" + FW + ".__uaply;A.setMin(0);A.renderAll();return 1})()");
  await sleep(300);
  check("with no minimum match (the default) every job of the stack is inside the filters, ordered by match", await ev("(()=>{const q=" + FW + ".__uaplyQueue();return q.length===40&&q.every(x=>!x.out)})()"), "");
  check("...and the card shows its percentage", /^[0-9]+%$/.test(await ev("(()=>{const b=" + F + ".querySelector('#deck .card.top .ring b');return b?b.textContent:''})()")), "");
  // the learner (shared/uaply-learn.js): 15 swipes right on 60-69% jobs and left on 80-89% ones move the liked band up
  const band = await J("(()=>{const C=(window.UAplyLearn||" + FW + ".UAplyLearn).core,st=C.fresh(),now=Date.now();for(let i=0;i<15;i++){const like=i%2===0;" +
    "C.swipe(st,{id:920000+i,co:'Band Co '+i,role:'Role '+i,mode:'remote',type:'job'},like?'applied':'passed',2500,false,now,like?65:85)}" +
    "const E=C.evidence(st.ev,now),a=C.score({id:1,co:'New A',role:'Other A',mode:'remote',type:'job'},65,E),b=C.score({id:2,co:'New B',role:'Other B',mode:'remote',type:'job'},85,E);" +
    "return {n:E.n,a:a.shown,b:b.shown,da:a.delta,db:b.delta}})()");
  check("the learner moves a liked match band up after 15 swipes (a new 65% job now ranks above a new 85% one)", band && band.n === 15 && band.da > 0 && band.db < 0 && band.a > band.b, JSON.stringify(band));
  // the empty deck only when everything was swiped
  await ev("(()=>{const A=" + FW + ".__uaply;A.JOBS.forEach(j=>{if(j.ajTest)A.S.decisions[j.id]={s:'passed',at:Date.now(),pct:50}});A.renderAll();return 1})()");
  await sleep(400);
  const empty = await ev("(()=>{const h=" + F + ".querySelector('#deck .empty h2');return h?h.textContent:''})()");
  check("the deck is empty only when everything was swiped, and it says so", empty === "You have seen every one of these", empty);
  check("no script errors", logs.filter((l) => l.startsWith("EXC")).length === 0, logs.join(" | "));
  console.log(bad ? bad + " problem(s)" : "All good");
  if (bad) process.exitCode = 1;
};
module.exports.limitMs = 180000;
