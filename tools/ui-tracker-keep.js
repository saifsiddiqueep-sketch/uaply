// Job Tracker keeps its rows (October 22, 2026): a reload 31 days after the saved copies were made, and 500 swipes, lose no row.
//   PORT=<sandbox port, any job feed> W=390 H=844 node tools/cdp.js tools/ui-tracker-keep.js
// Seeds this browser with swipes on jobs that are not in the server's list:
//   A  60 applications saved the old way (no row copy) whose saved job copies are 31 days old (the old rule dropped them after 30 days)
//   B  40 applications whose jobs left the list and the saved copy (only the swipe's own row copy is left)
//   C 400 passes
// then reloads and checks every application still has its Job Tracker row, the passes are kept, no stand-in job reaches the deck, and the
// old swipes got their row copy. Then 1,000 passes plus one more swipe: the oldest pass goes, the newest stays, no application goes.
const PORT = process.env.PORT;
module.exports = async ({ ev, sleep, nav }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + "[tracker] " + name + (ok || extra === undefined ? "" : "  | " + String(extra).slice(0, 300))); };
  const base = "http://127.0.0.1:" + PORT + "/";
  const ready = async () => { for (let i = 0; i < 60; i++) { if (await ev("!!(" + FW + "&&" + FW + ".__uaply&&" + F + ".getElementById('bnav'))").catch(() => false)) return true; await sleep(250); } return false; };
  const agree = () => ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m){m.click();return true}return false})()");

  // the test person signs up first (October 22, Saif: nobody reaches anything on the site without an account)
  await nav(base + "healthz"); await sleep(300);
  const su = await ev("fetch('/api/auth/signup',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'tracker.'+Date.now()+'@example.com',password:'Signup-first-99',first:'Test',last:'Person',agree:true,passwordless:false})}).then(r=>r.status)");
  check("the test person signs up first (POST /api/auth/signup), so the app opens behind the sign-in gate", su === 200, su);
  await nav(base); await ready(); await sleep(800); await agree(); await sleep(500);
  const KEY = await ev("window.__uaplyBuildKey");
  const DAY = 864e5, now = Date.now();
  const job = (id, i, tag) => ({ id, co: tag + " Co " + i, role: tag + " Role " + i, loc: "Austin, TX", mode: "onsite", type: "job", sal: [0, 0], yrs: 0, edu: "High school",
    skills: ["Excel"], blurb: "A test posting.", url: "https://example.com/" + tag + "/" + i, live: true, source: "Test" });
  const seed = (extraPasses) => ev("(()=>{const K=" + JSON.stringify(KEY) + ",now=" + now + ",DAY=" + DAY + ";const s=JSON.parse(localStorage.getItem(K)||'{}');" +
    "s.profile=s.profile||{name:'Sam Rivera',email:'sam@example.com',custom:true};s.decisions={};s.history=[];const cache=[];" +
    "const job=" + job.toString().replace(/\n/g, " ") + ";" +
    "for(let i=0;i<60;i++){const id=9000001+i;s.decisions[id]={s:'applied',at:now-40*DAY+i,pct:80,as:'Sam',title:''};s.history.push(id);const j=job(id,i,'Old');j.seen=now-31*DAY;cache.push(j)}" +
    "for(let i=0;i<40;i++){const id=9100001+i;const j=job(id,i,'Gone');s.decisions[id]={s:'applied',at:now-35*DAY+i,pct:70,as:'Sam',title:'',row:{t:j.role,c:j.co,l:j.loc,u:j.url,ty:'job',m:'onsite'}};s.history.push(id)}" +
    "for(let i=0;i<" + (400 + extraPasses) + ";i++){const id=9200001+i;const j=job(id,i,'Pass');s.decisions[id]={s:'passed',at:now-20*DAY+i*1000,pct:40,as:'Sam',title:'',row:{t:j.role,c:j.co,l:j.loc,u:j.url,ty:'job',m:'onsite'}};s.history.push(id)}" +
    "localStorage.setItem(K,JSON.stringify(s));localStorage.setItem(K+'.live',JSON.stringify({jobs:cache}));return Object.keys(s.decisions).length})()");

  // ---- 500 swipes, saved copies 31 days old, then a reload ----
  const n = await seed(0);
  check("seeded 500 swipes (100 applications, 400 passes)", n === 500, n);
  await nav(base); await ready(); await sleep(2500);
  const st = JSON.parse(await ev("(()=>{const U=" + FW + ".__uaply,S=U.S,by={};U.JOBS.forEach(j=>by[j.id]=j);const ks=Object.keys(S.decisions);" +
    "const app=ks.filter(k=>S.decisions[k].s==='applied'),pas=ks.filter(k=>S.decisions[k].s==='passed');" +
    "return JSON.stringify({app:app.length,pas:pas.length,appJobs:app.filter(k=>by[k]).length,oldRows:app.filter(k=>+k<9100000&&S.decisions[k].row&&S.decisions[k].row.c).length," +
    "stubs:U.JOBS.filter(j=>j.stub).length,deckStub:[...(" + F + ").querySelectorAll('.card')].filter(c=>+c.getAttribute('data-id')>=9000000).length," +
    "cacheOld:JSON.parse(localStorage.getItem(" + JSON.stringify(KEY + ".live") + ")||'{\"jobs\":[]}').jobs.filter(j=>j.id<9100000&&j.id>=9000000).length})})()"));
  check("after the reload all 100 applications and 400 passes are kept", st.app === 100 && st.pas === 400, JSON.stringify(st));
  check("every application has its job for the Job Tracker row (saved copies 31 days old kept, the rest from the swipe's row copy)", st.appJobs === 100, JSON.stringify(st));
  check("the 60 saved copies made 31 days ago are still in the saved list (a swiped job never ages out)", st.cacheOld === 60, JSON.stringify(st));
  check("the old swipes got their row copy from the saved list", st.oldRows === 60, JSON.stringify(st));
  check("no stand-in job reaches the deck", st.deckStub === 0, JSON.stringify(st));

  // the rows on screen: Job Tracker, Applied
  await ev(F + ".getElementById('nb-dash').click()"); await sleep(400);
  await ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='applied'&&b.offsetParent);if(e)e.click()})()"); await sleep(900);
  const shown = JSON.parse(await ev("(()=>{const t=(" + F + ".getElementById('pane-track')||" + F + ".body).innerText;return JSON.stringify({old:(t.match(/Old Role/g)||[]).length,gone:(t.match(/Gone Role/g)||[]).length})})()"));
  check("Job Tracker, Applied shows all 100 rows: 60 from 40 days ago and 40 whose job left everything", shown.old === 60 && shown.gone === 40, JSON.stringify(shown));

  // ---- 1,000 passes and one more swipe: the oldest pass goes, nothing else ----
  await seed(600);
  await nav(base); await ready(); await sleep(2500);
  const before = JSON.parse(await ev("JSON.stringify((()=>{const S=" + FW + ".__uaply.S;const v=Object.values(S.decisions);return {app:v.filter(x=>x.s==='applied').length,pas:v.filter(x=>x.s==='passed').length}})())"));
  check("1,000 passes and 100 applications loaded", before.pas === 1000 && before.app === 100, JSON.stringify(before));
  await ev("(()=>{const b=[...(" + F + ").querySelectorAll('.nb')].find(x=>x.id==='nb-svc'||x.id==='nb-jobs');if(b)b.click()})()"); await sleep(300);
  const top = await ev("(()=>{const c=" + F + ".querySelector('.card.top');return c?+c.getAttribute('data-id'):0})()");
  await ev(F + ".dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}))"); await sleep(1500);
  const after = JSON.parse(await ev("JSON.stringify((()=>{const S=" + FW + ".__uaply.S;const v=Object.values(S.decisions);return {app:v.filter(x=>x.s==='applied').length,pas:v.filter(x=>x.s==='passed').length," +
    "oldest:!!S.decisions[9200001],newest:!!S.decisions[" + top + "],row:S.decisions[" + top + "]&&S.decisions[" + top + "].row||null,hist:S.history.length}})())"));
  check("a swipe on the deck (" + top + ") was made", !!top && after.newest, JSON.stringify(after));
  check("...it carries its row copy (title and company)", !!(after.row && after.row.t && after.row.c), JSON.stringify(after.row));
  check("...the passes stay at 1,000: the oldest pass went, the new one stayed", after.pas === 1000 && !after.oldest, JSON.stringify(after));
  check("...no application went, and the undo history has no dropped swipe", after.app === 100 && after.hist === 1100, JSON.stringify(after));
  const saved = JSON.parse(await ev("JSON.stringify((()=>{const s=JSON.parse(localStorage.getItem(" + JSON.stringify(KEY) + "));return {pas:Object.values(s.decisions).filter(x=>x.s==='passed').length,row:!!(s.decisions[" + top + "]||{}).row}})())"));
  check("...and that is what was saved", saved.pas === 1000 && saved.row, JSON.stringify(saved));
  // ---- answers: what a swipe to Plaid sends never holds an answer written for Stripe (October 22) ----
  const sent = JSON.parse(await ev("(()=>{const w=" + FW + ",k=w.__uaplyKey;localStorage.setItem(k+'.answers',JSON.stringify({" +
    "'{at stripe} why do you want to work at {co}':'STRIPE-ONLY','why do you want to work at {co}':'OLD-CO','why do you want to work here':'OLD-WHY'," +
    "'{at plaid} why do you want to work at {co}':'PLAID','are you legally authorized to work in the us':'Yes','what is your notice period':'Two weeks at Stripe'}));" +
    "localStorage.setItem(k+'.answersAsked',JSON.stringify({'what is your notice period':{co:'Stripe'}}));" +
    "return JSON.stringify([w.__uaplyAnswersFor('Plaid'),w.__uaplyAnswersFor('Stripe')])})()"));
  check("a swipe to Plaid sends Plaid's own answer and the general ones, never Stripe's, an older {co} or 'why' answer, or one naming Stripe that Stripe asked",
    JSON.stringify(sent[0]) === JSON.stringify({ "{at plaid} why do you want to work at {co}": "PLAID", "are you legally authorized to work in the us": "Yes" }), JSON.stringify(sent[0]));
  check("...and a swipe to Stripe sends Stripe's own one", sent[1]["{at stripe} why do you want to work at {co}"] === "STRIPE-ONLY" && !sent[1]["{at plaid} why do you want to work at {co}"], JSON.stringify(sent[1]));
  console.log("RESULT " + pass + "/" + (pass + fail));
  if (fail) throw new Error(fail + " tracker check(s) failed");
};
