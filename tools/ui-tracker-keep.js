// Job Tracker keeps its rows (October 22, 2026): a reload 31 days after the saved copies were made, and 500 swipes, lose no row.
//   PORT=<sandbox port, any job feed> W=390 H=844 node tools/cdp.js tools/ui-tracker-keep.js
// Seeds this browser with swipes on jobs that are not in the server's list:
//   A  60 applications saved the old way (no row copy) whose saved job copies are 31 days old (the old rule dropped them after 30 days)
//   B  40 applications whose jobs left the list and the saved copy (only the swipe's own row copy is left)
//   C 400 passes
// then reloads and checks every application still has its Job Tracker row, the passes are kept, no stand-in job reaches the deck, and the
// old swipes got their row copy. Then 1,000 passes plus one more swipe: the oldest pass goes, the newest stays, no application goes.
// Then (Trello EJDLrliG) a backup restored when its jobs are no longer listed keeps every swipe that carries its row copy, with what
// happened to it (Sent, Sent (by you), the Interview stage) and its details, and says how many it could not bring back; a hand-off row
// with no link still has Mark as applied; and Mark as applied counts for what UAply learns (the strongest yes), which Undo takes back.
// A restored application that was waiting to send comes back as Not sent with Try again: after a reload nothing goes to /api/apply with
// nobody tapping anything (it used to be sent on its own). A hand-edited id such as "1e6" is skipped and the restore still finishes.
// Sandbox only (run-all-tests.sh runs it on the sandbox server): on a dev server the "swipe on the deck" checks fail on unchanged code too.
const PORT = process.env.PORT;
const gateSignup = require("./gate-signup.js");   // the test person signs up first (Saif, October 22: no account, no data)
const fs = require("fs"), os = require("os"), path = require("path");
module.exports = async ({ ev, sleep, nav, send, on }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + "[tracker] " + name + (ok || extra === undefined ? "" : "  | " + String(extra).slice(0, 300))); };
  const base = "http://127.0.0.1:" + PORT + "/";
  const ready = async () => { for (let i = 0; i < 60; i++) { if (await ev("!!(" + FW + "&&" + FW + ".__uaply&&" + F + ".getElementById('bnav'))").catch(() => false)) return true; await sleep(250); } return false; };
  const agree = () => ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m){m.ownerDocument.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});m.disabled=false;m.click();return true}return false})()");

  // the test person signs up first (October 22, Saif: nobody reaches anything on the site without an account)
  const who = await gateSignup({ ev, sleep, nav }, base, "tracker");
  const su = who.ok ? 200 : 0 || await ev("fetch('/api/auth/signup',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'tracker.'+Date.now()+'@example.com',password:'Signup-first-99',first:'Test',last:'Person',agree:true,passwordless:false})}).then(r=>r.status)");
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
  // written from inside the app's own frame: a write from this page fires the frame's "storage" event, which repaints the kept answers
  const sent = JSON.parse(await ev("(()=>{const w=" + FW + ",k=w.__uaplyKey,localStorage=w.localStorage;localStorage.setItem(k+'.answers',JSON.stringify({" +
    "'{at stripe} why do you want to work at {co}':'STRIPE-ONLY','why do you want to work at {co}':'OLD-CO','why do you want to work here':'OLD-WHY'," +
    "'{at plaid} why do you want to work at {co}':'PLAID','are you legally authorized to work in the us':'Yes','what is your notice period':'Two weeks at Stripe'}));" +
    "localStorage.setItem(k+'.answersAsked',JSON.stringify({'what is your notice period':{co:'Stripe'}}));" +
    "return JSON.stringify([w.__uaplyAnswersFor('Plaid'),w.__uaplyAnswersFor('Stripe')])})()"));
  check("a swipe to Plaid sends Plaid's own answer and the general ones, never Stripe's, an older {co} or 'why' answer, or one naming Stripe that Stripe asked",
    JSON.stringify(sent[0]) === JSON.stringify({ "{at plaid} why do you want to work at {co}": "PLAID", "are you legally authorized to work in the us": "Yes" }), JSON.stringify(sent[0]));
  check("...and a swipe to Stripe sends Stripe's own one", sent[1]["{at stripe} why do you want to work at {co}"] === "STRIPE-ONLY" && !sent[1]["{at plaid} why do you want to work at {co}"], JSON.stringify(sent[1]));

  // ---- a backup restored on a new device after its jobs left the list (Trello EJDLrliG) ----
  const row = (i, u) => ({ t: "Restore Role " + i, c: "Restore Co " + i, l: "Denver, CO", u: u === undefined ? "https://example.com/restore/" + i : u, ty: "job", m: "onsite" });
  const bk = { app: "uaply", v: 1, exported: new Date().toISOString(), profile: { name: "Sam Rivera", email: "sam@example.com", title: "Analyst", years: 2, edu: "Bachelor", skills: ["Excel"], salary: 0, loc: "Denver", modes: {} },
    decisions: {
      9300001: { s: "applied", at: now - 50 * DAY, pct: 81, as: "Sam", title: "", row: row(1), sent: { at: now - 49 * DAY, to: "", status: "self", prev: "handoff", once: false } },
      9300002: { s: "applied", at: now - 48 * DAY, pct: 77, as: "Sam", title: "", st: "interview", row: row(2), sent: { at: now - 48 * DAY, to: "Restore Co 2", status: "sent" } },
      9300003: { s: "applied", at: now - 47 * DAY, pct: 70, as: "Sam", title: "" },
      9300004: { s: "applied", at: now - 46 * DAY, pct: 66, as: "Sam", title: "", row: row(4, ""), sent: { at: now - 46 * DAY, to: "", status: "handoff" } },
      9300005: { s: "passed", at: now - 45 * DAY, pct: 30, as: "Sam", title: "", row: row(5) },
      9300006: { s: "applied", at: now - 44 * DAY, pct: 72, as: "Sam", title: "", row: row(6), sent: { at: now - 44 * DAY, to: "", status: "pending", prev: "pending" } },
      9300007: { s: "applied", at: now - 43 * DAY, pct: 71, as: "Sam", title: "", row: row(7), sent: { at: now - 43 * DAY, to: "", status: "self", prev: "pending", once: false } },
      "1e6": { s: "applied", at: now - 42 * DAY, pct: 60, as: "Sam", title: "", row: row(8) } },
    acct: { apps: { 9300002: { when: "2026-11-02", note: "Second round with the team lead" } } } };
  const file = path.join(os.tmpdir(), "uaply-tracker-restore-" + process.pid + ".json");
  fs.writeFileSync(file, JSON.stringify(bk));
  // a new device: nothing saved (no swipes, no saved job list; the answers seeded above go too, their asked record is test-only with no
  // question text). Written from inside the app's frame, so no "storage" event repaints anything first
  await ev("(()=>{const k=" + FW + ".__uaplyKey,L=" + FW + ".localStorage;[k,k+'.live',k+'.answers',k+'.answersAsked'].forEach(x=>L.removeItem(x));return 1})()");
  await nav(base); await ready(); await sleep(2000); await agree(); await sleep(500);
  // every request the app makes from here on: a restore must never send an application by itself
  const posts = []; let seen = 0;
  on("Network.requestWillBeSent", (p) => { seen++; if (p.request.method === "POST" && /\/api\/apply(\?|$)/.test(p.request.url.split("#")[0])) posts.push(p.request.url); });
  await send("Network.enable");
  check("a new device: nothing saved before the restore", (await ev("(()=>{const S=" + FW + ".__uaply.S;return Object.keys(S.decisions).length})()")) === 0);
  await ev(F + ".getElementById('nb-prof').click()"); await sleep(300);
  await ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='data'&&b.offsetParent);if(e)e.click()})()"); await sleep(600);
  const inp = await send("Runtime.evaluate", { expression: F + ".getElementById('aImp')" });
  await send("DOM.enable");
  await send("DOM.setFileInputFiles", { files: [file], objectId: inp.result.result.objectId });
  let said = "";
  for (let i = 0; i < 24 && !said; i++) { await sleep(250); said = await ev("(()=>{const m=" + F + ".getElementById('aMsg');return m?m.innerText.trim():''})()"); }
  try { fs.unlinkSync(file); } catch (e) {}
  const rs = JSON.parse(await ev("JSON.stringify((()=>{const U=" + FW + ".__uaply,S=U.S,by={};U.JOBS.forEach(j=>by[j.id]=j);const g=k=>S.decisions[k]||null;" +
    "return {d:[9300001,9300002,9300003,9300004,9300005].map(k=>!!g(k)),jobs:[9300001,9300002,9300004,9300005].map(k=>!!(by[k]&&by[k].stub)),deck:[...(" + F + ").querySelectorAll('.card')].filter(c=>+c.getAttribute('data-id')>=9300000).length," +
    "s1:g(9300001)&&g(9300001).sent&&g(9300001).sent.status,s2:g(9300002)&&g(9300002).sent&&g(9300002).sent.status,st2:g(9300002)&&g(9300002).st,row4:g(9300004)&&g(9300004).row}})())"));
  check("a restore whose jobs are no longer listed keeps the 4 swipes that carry their row copy, and only those", JSON.stringify(rs.d) === "[true,true,false,true,true]", JSON.stringify(rs));
  check("...each comes back as a stand-in for its Job Tracker row, never a card on the deck", rs.jobs.every(Boolean) && rs.deck === 0, JSON.stringify(rs));
  check("...with what happened to it: Sent (by you), Sent, the Interview stage", rs.s1 === "self" && rs.s2 === "sent" && rs.st2 === "interview", JSON.stringify(rs));
  check("...and the message starts with the one application that could not come back, and why", /^Restored, except for 1 application: its job is no longer listed, and the file has no copy of it\. Your profile, your other applications/.test(said), said);
  const rp = JSON.parse(await ev("JSON.stringify((()=>{const S=" + FW + ".__uaply.S,g=k=>S.decisions[k]||{};return {s6:g(9300006).sent||null,p7:(g(9300007).sent||{}).prev,odd:Object.keys(S.decisions).filter(k=>!/^[0-9]+$/.test(k)),n:Object.keys(S.decisions).length}})())"));
  check("a restored application that was waiting to send comes back as Not sent (Try again), never as waiting to send", !!rp.s6 && rp.s6.status === "failed", JSON.stringify(rp));
  check("...and Undo of a restored Mark as applied can never put one back to waiting to send", rp.p7 === "failed", JSON.stringify(rp));
  check("a hand-edited id such as 1e6 is skipped and the restore still finishes", rp.odd.length === 0 && rp.n === 6 && !!said, JSON.stringify(rp));
  const acctTxt = await ev("Object.keys(localStorage).map(k=>localStorage.getItem(k)).join(' ')");
  check("...and the details of a restored application are kept (its interview note)", /Second round with the team lead/.test(acctTxt), "note not in this browser's storage");
  await ev(F + ".getElementById('nb-dash').click()"); await sleep(400);
  await ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='applied'&&b.offsetParent);if(e)e.click()})()"); await sleep(900);
  const chips = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ",o={};[9300001,9300004,9300005].forEach(k=>{const b=d.querySelector('#pane-track [data-id=\"'+k+'\"]');const r=b&&b.closest('.row');" +
    "o[k]=r?{chip:(r.querySelector('.stchip')||{}).textContent||'',mark:!!r.querySelector('[data-act=markapplied]'),text:r.innerText}:null});return o})())"));
  check("Job Tracker, Applied: the restored hand-off the person had marked says Sent (by you)", !!chips[9300001] && chips[9300001].chip === "Sent (by you)", JSON.stringify(chips[9300001]));
  check("a hand-off row with no link to the posting still offers Mark as applied", !!chips[9300004] && chips[9300004].chip === "Finish on their site" && chips[9300004].mark, JSON.stringify(chips[9300004]));
  // card 182: passed jobs sit behind the Overview's "Jobs you passed on" link
  await ev("(()=>{const b=" + F + ".querySelector('#pane-track [data-filt=passed]');if(b)b.click();return 1})()"); await sleep(400);
  chips[9300005] = JSON.parse(await ev("JSON.stringify((()=>{const b=" + F + ".querySelector('#pane-track [data-id=\"9300005\"]');const r=b&&b.closest('.row');return r?{text:r.innerText}:null})())"));
  await ev("(()=>{const b=" + F + ".querySelector('#pane-track [data-filt=all]');if(b)b.click();return 1})()"); await sleep(400);
  check("...and the restored pass is listed under Passed", !!chips[9300005] && /Restore Role 5/.test(chips[9300005].text), JSON.stringify(chips[9300005]));
  // Mark as applied is the strongest yes for what UAply learns (the same as going on to the employer's site); Undo takes it back
  await ev("(()=>{const L=" + FW + ".__uaplyLearn.state();L.ev.push({id:9300004,at:Date.now(),k:'R',d:0,a:['t:job','m:onsite']});return 1})()");
  const kind = () => ev("(()=>{const L=" + FW + ".__uaplyLearn.state();for(let i=L.ev.length-1;i>=0;i--)if(L.ev[i].id===9300004)return L.ev[i].k;return ''})()");
  const chip4 = () => ev("(()=>{const b=" + F + ".querySelector('#pane-track [data-id=\"9300004\"]');const r=b&&b.closest('.row');return r?(r.querySelector('.stchip')||{}).textContent:''})()");
  await ev("(()=>{const b=" + F + ".querySelector('[data-act=markapplied][data-id=\"9300004\"]');if(b)b.click();return 1})()"); await sleep(400);
  const k1 = await kind(), c1 = await chip4();
  check("Mark as applied on it: the row says Sent (by you), and the swipe counts as finished on the employer's site for what UAply learns", c1 === "Sent (by you)" && k1 === "F", c1 + " | " + k1);
  await ev("(()=>{const b=" + F + ".querySelector('[data-act=unmark][data-id=\"9300004\"]');if(b)b.click();return 1})()"); await sleep(400);
  const k2 = await kind(), c2 = await chip4();
  check("...Undo puts the row and what UAply learned back as they were", k2 === "R" && c2 === "Finish on their site", c2 + " | " + k2);
  // the restored application that was waiting to send: its row says Not sent with Try again, and the next visit sends nothing by itself
  const r6 = JSON.parse(await ev("JSON.stringify((()=>{const b=" + F + ".querySelector('#pane-track [data-id=\"9300006\"]');const r=b&&b.closest('.row');return r?{chip:(r.querySelector('.stchip')||{}).textContent,again:!!r.querySelector('[data-act=resend]')}:null})())"));
  check("Job Tracker: that row says Not sent, with Try again (only a tap sends it)", !!r6 && r6.chip === "Not sent" && r6.again, JSON.stringify(r6));
  const at6 = await ev("(()=>{const x=" + FW + ".__uaply.S.decisions[9300006];return x&&x.sent?x.sent.at:0})()");
  await nav(base); await ready(); await sleep(9000);
  const s6 = JSON.parse(await ev("JSON.stringify((()=>{const x=" + FW + ".__uaply.S.decisions[9300006];return x&&x.sent||null})())"));
  check("a reload and 9 seconds with no tap: no application went to /api/apply, and that one is unchanged", seen > 0 && posts.length === 0 && !!s6 && s6.status === "failed" && s6.at === at6,
    "requests seen " + seen + " | /api/apply posts " + JSON.stringify(posts) + " | " + JSON.stringify(s6) + " | at before " + at6);
  console.log("RESULT " + pass + "/" + (pass + fail));
  if (fail) throw new Error(fail + " tracker check(s) failed");
};
