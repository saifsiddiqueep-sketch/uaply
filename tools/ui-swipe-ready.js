// The swipe guarantee, part two: readiness (the owner's rule, October 21: a right swipe never sends an incomplete application, and never
// pretends). Run by tools/test-swipe-e2e.py after tools/ui-swipe-e2e.js, with the same account and server:
//   python tools/test-swipe-e2e.py
// For every apply path (Greenhouse, Greenhouse with a required phone, Greenhouse with work-authorization questions, Lever, Ashby,
// SmartRecruiters, Workable, an email employer, a hand-off) and four half-finished profiles (below the minimum, no phone, no resume, no
// work authorization), plus an employer's own question on Greenhouse, Ashby, SmartRecruiters and Workable, a swipe right must end one of
// these honest ways, and only the one the employer's form calls for:
//   profile   "Finish your profile first": nothing sent, the card stays, nothing in Job Tracker
//   ask       the question box with only what is missing; answered, the application is sent (and the employer side is checked by Python)
//   ask-file  the box needs a resume file: Not now leaves it in Job Tracker as "Not sent yet" with Answer now, nothing sent
//   sent      sent at once (the employer's form needs nothing more)       handoff   nothing sent, finish on their site
// Cards say so before the swipe ("Ready", "Ready to apply", "N answers needed"). The last line is a JSON summary.
const PORT = process.env.PORT, BASE = "http://127.0.0.1:" + PORT, MOCK = process.env.MOCK_PORT;
const R = JSON.parse(process.env.E2E_READY || "{}");            // {jobs: {"<state>|<path>": id}, ...}
module.exports = async ({ ev, sleep, nav, send, logs }) => {
  const count = {};
  const check = (path, name, ok, extra) => {
    count[path] = count[path] || { pass: 0, fail: 0 }; count[path][ok ? "pass" : "fail"]++;
    console.log((ok ? "PASS " : "FAIL ") + "[" + path + "] " + name + (ok || !extra ? "" : "  -> " + String(extra).slice(0, 300)));
    return ok;
  };
  const F = "document.querySelector('iframe').contentDocument";
  const q = (js) => ev("(async()=>{try{const d=" + F + ",w=d.defaultView;" + js + "}catch(e){return 'ERR '+e.message}})()");
  const waitFor = async (js, ms) => { const end = Date.now() + (ms || 10000); let v; while (Date.now() < end) { v = await q(js); if (v && !String(v).startsWith("ERR")) return v; await sleep(250); } return v; };
  const received = async () => (await (await fetch("http://127.0.0.1:" + MOCK + "/__received")).json()).length;
  const boot = async () => {
    await nav(BASE + "/?app=1");
    await waitFor("return w.__uaplyReadiness&&w.__uaplyReadyOf&&w.__uaplySubmitOn&&w.__uaplyMode&&d.getElementById('nb-prof')?1:0", 30000);
    await q("const y=d.getElementById('kcYes');if(y)y.click();const n=[...d.querySelectorAll('#locAsk button')].find(x=>/Not now/.test(x.innerText));if(n)n.click();const t=d.getElementById('tipsClose');if(t)t.click();return 1");
    await sleep(900);
    await q("const y=d.getElementById('kcYes');if(y)y.click();return 1");     // the agreement box opens 0.7 s after load
    await sleep(300);
  };
  let full = "";
  // a half-finished profile, set the way the app stores it, then the app is opened again so every screen reads it
  const setState = async (state) => {
    if (!full) full = await q("const K=w.__uaplyKey;return JSON.stringify([w.localStorage.getItem(K),w.localStorage.getItem(K+'.acct')])");   // the complete profile the first half made
    await q(`const K=w.__uaplyKey,F=${full};w.localStorage.setItem(K,F[0]);w.localStorage.setItem(K+'.acct',F[1]);
      const S=JSON.parse(w.localStorage.getItem(K)),A=JSON.parse(w.localStorage.getItem(K+'.acct')),p=S.profile,x=p.ext=p.ext||{};
      const st=${JSON.stringify(state)};
      if(st==='below-min'||st==='no-phone'){x.phone='';A.phone=''}
      if(st==='below-min'||st==='no-resume'){A.resumeName='';A.resumeData='';A.resumeSize=0;A.resumeUrl='';x.resume='';x.summary='';x.headline='';A.summary=''}
      if(st==='no-auth'){x.auth='';x.sponsor='no';if(A.eeo){A.eeo.auth=''}}
      w.localStorage.setItem(K,JSON.stringify(S));w.localStorage.setItem(K+'.acct',JSON.stringify(A));
      w.localStorage.removeItem(K+'.answers');w.localStorage.removeItem(K+'.asked');return 1`);
    await boot();
    console.log("     " + state + ": " + await q("const r=w.__uaplyReadiness();return 'minimum '+(r.min?'met':'NOT met')+'; '+r.items.map(i=>i.k+(i.done?'+':'-')).join(' ')"));
  };
  // a swipe right exactly as the deck does it after the gate (prod's decide()), on a chosen job: decision, then the apply flow
  const swipe = (id) => q("const A=w.__uaply,job=A.JOBS.find(j=>j.id===" + id + ");if(!job)return 'no job';if(w.__uaplyReadyGate&&w.__uaplyReadyGate(job))return 'gated';const m=A.evaluate(job,A.S.profile);" +
    "A.S.decisions[job.id]={s:'applied',at:Date.now(),pct:m.pct,as:A.S.profile.name,title:A.S.profile.title};A.S.history.push(job.id);A.save();A.renderAll();" +
    "w.__uaplyOnDecision('applied',job,m,A.S.profile,function(){},A.S,A.save);return 'ok'");
  // final: a send's own outcome ("needs_answers" is marked while the question box is open); not final: whatever the row says now
  const status = (id, ms, notFinal) => waitFor("const x=w.__uaply.S.decisions[" + id + "];const s=x&&x.sent&&x.sent.status;return s&&s!=='pending'&&(" + (notFinal ? "true" : "s!=='needs_answers'") + ")?s:''", ms || 20000);
  // answer every question in the box the way a person would: yes to work authorization, no to sponsorship, a job board, a phone number,
  // a sentence for anything written
  const answerBox = () => q(`const o=d.getElementById('kitAsk');if(!o)return 'no box';
    o.querySelectorAll('.kaF').forEach(b=>{const lab=(b.querySelector('.kaL')||b).innerText;
      b.querySelectorAll('select').forEach(s=>{const opts=[...s.options].filter(x=>x.value);const pick=/sponsor/i.test(lab)?opts.find(x=>/^no/i.test(x.text)):/authori[sz]ed|eligible/i.test(lab)?opts.find(x=>/^yes/i.test(x.text)):/hear/i.test(lab)?opts.find(x=>/board|other/i.test(x.text)):null;s.value=(pick||opts[0]||{}).value||'';s.dispatchEvent(new Event('change',{bubbles:true}))});
      b.querySelectorAll('input[type=radio]').forEach((r,i,all)=>{if(i===0)r.click()});
      b.querySelectorAll('input[type=checkbox]').forEach(c=>{if(!c.checked)c.click()});
      b.querySelectorAll('input[type=text],input[type=tel],input:not([type]),textarea,input[type=number],input[type=date],input[type=month]').forEach(t=>{if(t.disabled)return;t.value=/phone/i.test(lab)?'617-555-0199':t.type==='number'?'20':t.type==='date'?'2027-07-01':t.type==='month'?'2027-06':'Blue, it is calm.';t.dispatchEvent(new Event('input',{bubbles:true}))});
    });return 'ok'`);
  const summary = { outcomes: {} };
  let swipes = 0;
  const EXPECT = R.expect || {};

  await nav(BASE + "/healthz");
  await send("Storage.clearDataForOrigin", { origin: BASE, storageTypes: "all" });
  await send("Network.clearBrowserCookies");
  await boot();
  // this browser is new: sign in to the first half's verified account, and give it the complete profile the first half built from the
  // resume (name, email, phone, school and major, city, work authorization, the resume file itself, voluntary answers kept on the device)
  const login = await q("const r=await w.fetch('/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'elena.rossi@example.com',password:" + JSON.stringify(process.env.E2E_PASSWORD || "") + "})});return r.status");
  check("browser", "signed in to the verified account from the first half", login === 200, login);
  const b64 = require("fs").readFileSync(process.env.RESUME).toString("base64");
  await q(`const K=w.__uaplyKey,S=JSON.parse(w.localStorage.getItem(K)),A=JSON.parse(w.localStorage.getItem(K+'.acct')||'{}');
    S.profile=Object.assign({},S.profile,{custom:true,name:'Elena Rossi',email:'elena.rossi@example.com',title:'Readiness',years:1,
      skills:['HubSpot','Canva','Google Analytics','Copywriting','Mailchimp','Excel'],loc:'Boston, MA',edu:'Bachelor',
      ext:Object.assign({},S.profile.ext,{phone:'617-555-0110',auth:'citizen',sponsor:'no',school:'Northeastern University',major:'Marketing',
        summary:'Recent marketing graduate who has run social campaigns',start:'now'})});
    A.resumeName='newgrad.docx';A.resumeSize=${Buffer.from(b64, "base64").length};A.resumeData='data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,${b64}';
    A.eeo=Object.assign({},A.eeo,{gender:'Non-binary',veteran:'I am a protected veteran',race:['Native Hawaiian or Other Pacific Islander'],hisp:'Yes',disability:'Yes, I have a disability (or have had one)'});
    w.localStorage.setItem(K,JSON.stringify(S));w.localStorage.setItem(K+'.acct',JSON.stringify(A));return 1`);
  await boot();
  const r0 = JSON.parse(await q("return JSON.stringify(w.__uaplyReadiness())") || "{}");
  check("browser", "the complete profile has everything a swipe needs", r0.min === true && r0.done >= 7, JSON.stringify(r0).slice(0, 200));
  // ---------- 1. below the minimum: every card says so, and a swipe right (the real Apply button on the top card) changes nothing ----------
  await setState("below-min");
  // a real employer's job on top (the sandbox also lists made-up examples, which a swipe only saves on this device)
  const topJob = R.jobs["below-min|mail"];
  await q("const A=w.__uaply;A.JOBS.forEach(j=>{if(j.id!==" + topJob + "&&!A.S.decisions[j.id])A.S.decisions[j.id]={s:'passed',at:Date.now(),pct:50}});A.save();A.renderAll();return 1");
  await sleep(500);
  const rd = JSON.parse(await q("return JSON.stringify(w.__uaplyReadiness())") || "{}");
  check("below-min", "the profile is below the minimum (name, email, phone or resume)", rd.min === false && /a phone number or a resume/.test((rd.missing || []).join("|")), JSON.stringify(rd).slice(0, 200));
  await sleep(1500);
  const badge = await q("const s=d.querySelector('#deck .card.top .facts .rdy');return s?s.textContent:''");
  check("below-min", "the top card (" + topJob + ") has no profile badge (no per-card nagging)", badge === "" && (await q("return +d.querySelector('#deck .card.top').getAttribute('data-id')")) === topJob, badge);
  const before = await received(), top0 = await q("return +d.querySelector('#deck .card.top').getAttribute('data-id')");
  // Saif, October 24: an incomplete profile never blocks a swipe. A swipe right saves it to Job Tracker as "Needs profile", and one line says so
  await q("try{w.sessionStorage.removeItem('uaply.np')}catch(e){}w.__uaplyNPTold=false;d.getElementById('btnYes').click();return 1"); await sleep(1500);
  const msg = await q("const t=d.getElementById('kitToast');return t?t.innerText:''");
  check("below-min", "a swipe right saves it and says so: 'Saved to your Job Tracker. Complete your profile to send applications automatically.' with Complete profile",
    String(msg).startsWith("Saved to your Job Tracker. Complete your profile to send applications automatically.") && String(msg).indexOf("Complete profile") > -1, msg);
  const st0 = await q("const x=w.__uaply.S.decisions[" + top0 + "];return x&&x.sent?x.sent.status:''");
  check("below-min", "...it is in Job Tracker as needs_profile, the card left the deck, nothing reached an employer",
    st0 === "needs_profile" && (await received()) === before && (await q("const c=d.querySelector('#deck .card.top');return c?+c.getAttribute('data-id'):0")) !== top0, st0);
  const openApplied = async () => {
    await q("d.getElementById('nb-dash').click();return 1"); await sleep(300);
    await q("[...d.querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='applied').click();return 1"); await sleep(900);
    return q(`const b=d.querySelector('#pane-track [data-id="${top0}"]');const r=b&&b.closest('.row');return r?r.innerText:''`);
  };
  const row1 = await openApplied();
  check("below-min", "Job Tracker marks it Needs profile, with Complete profile, and the tracker has its small badge",
    row1.indexOf("Needs profile") > -1 && row1.indexOf("Complete profile") > -1 && (await q("return !!d.querySelector('#nb-dash .npDot')")) === true, row1);
  // the profile is completed: the same row sends it with one tap
  const keep = await q("return JSON.stringify(w.__uaply.S.decisions[" + top0 + "])");
  await setState("full");          // (setState puts back the saved profile from before the swipe: the saved job is put back with it)
  await q("const A=w.__uaply;A.S.decisions[" + top0 + "]=" + keep + ";if(A.S.history.indexOf(" + top0 + ")<0)A.S.history.push(" + top0 + ");A.save();A.renderAll();return 1");
  const row2 = await openApplied();
  check("below-min", "once the profile is complete, the row offers Send now", row2.indexOf("Send now") > -1, row2);
  await q(`const b=d.querySelector('#pane-track [data-act="resend"][data-id="${top0}"]');if(b)b.click();return 1`);
  const sent0 = await waitFor("const x=w.__uaply.S.decisions[" + top0 + "];const s=x&&x.sent&&x.sent.status;return s&&s!=='pending'&&s!=='needs_profile'?s:''", 25000);
  check("below-min", "...and Send now sends it", sent0 === "sent" || sent0 === "delivered_test", sent0);
  await q("d.getElementById('nb-svc').click();return 1"); await sleep(300);
  await q("[...d.querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='job').click();return 1"); await sleep(500);
  await q("const A=w.__uaply;Object.keys(A.S.decisions).forEach(k=>{if(A.S.decisions[k].s==='passed'||+k===" + top0 + ")delete A.S.decisions[k]});A.save();A.renderAll();return 1");
  await setState("below-min");

  // ---------- 2. every state on every apply path ----------
  for (const state of ["below-min", "no-phone", "no-resume", "no-auth", "question"]) {
    if (state !== "below-min") await setState(state === "question" ? "full" : state);
    const keys = Object.keys(R.jobs).filter((k) => k.startsWith(state + "|"));
    for (const key of keys) {
      const path = key.split("|")[1], id = R.jobs[key], want = EXPECT[key] || "sent";
      if (state === "question") await q("w.localStorage.removeItem(w.__uaplyKey+'.answers');return 1");   // each employer's own question is asked, not answered from the last one
      const card = await q("return JSON.stringify(await w.__uaplyReadyOf(" + id + "))");
      const cardObj = (() => { try { return JSON.parse(card); } catch (e) { return null; } })();
      const n0 = await received();
      await q("['kitAsk','kitToast','rdyBox'].forEach(i=>{const e=d.getElementById(i);if(e)e.remove()});return 1");
      // the server allows 40 swipes a minute from one address, and this test swipes faster than a person: pause a minute every 30 swipes
      swipes++; if (swipes % 30 === 0) { console.log("     (a minute's pause: the server's limit of 40 swipes a minute)"); await sleep(61000); }
      const r = await swipe(id);
      let got = "", asked = "";
      if (r === "gated") got = "profile";
      else {
        const seen = await waitFor("if(d.getElementById('kitAsk'))return 'ask';const x=w.__uaply.S.decisions[" + id + "];return x&&x.sent&&x.sent.status&&x.sent.status!=='pending'?x.sent.status:''", 25000);   // a busy computer: the employer's form is read first
        if (seen === "ask") {
          asked = await q("return d.getElementById('kitAsk').innerText.replace(/\\s+/g,' ').slice(0,400)");
          const file = await q("return d.getElementById('kaYes').textContent");
          if (file === "Open Profile") {
            await q("d.getElementById('kaNo').click();return 1");
            got = "ask-file:" + (await status(id, 4000, true));
            await q("d.getElementById('nb-dash').click();return 1"); await sleep(300);
            await q("[...d.querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='applied').click();return 1"); await sleep(900);
            const row = await q("const b=d.querySelector('#pane-track [data-id=\"" + id + "\"]');const r=b&&b.closest('.row');return r?r.innerText.replace(/\\s+/g,' '):''");
            check(state, path + " (" + state + "): the Job Tracker row reads Not sent yet, with Answer now", /Not sent yet/.test(row) && /Answer now/.test(row) && !/\bSent\b/.test(row), row);
            await q("d.getElementById('nb-svc').click();return 1"); await sleep(300);
            await q("[...d.querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='job').click();return 1"); await sleep(500);
          } else {
            await answerBox(); await q("d.getElementById('kaYes').click();return 1");
            got = "ask:" + (await status(id));
          }
        } else got = seen || "nothing";
      }
      summary.outcomes[key] = { got, asked: asked.slice(0, 200), card: cardObj };
      const n1 = await received();
      const label = path + " (" + state + ")";
      const ok = want === "profile" ? got === "needs_profile" : want === "ask" ? got === "ask:sent" : want === "ask-file" ? got === "ask-file:needs_answers" : want === "handoff" ? got === "handoff" : got === "sent";
      check(state, label + ": the swipe ends as the employer's form calls for (" + want + ")", ok, got + " | " + asked.slice(0, 160));
      if (want === "ask" && R.asks && R.asks[key]) check(state, label + ": the box asks exactly for " + R.asks[key], new RegExp(R.asks[key], "i").test(asked), asked);
      // nothing reaches an employer unless it was sent: a mock receipt only for a send into a hiring system
      const intoAts = ["gh", "ghphone", "ghauth", "ghq", "lever", "ashby", "ashbyq", "sr", "srq", "wk", "wkq"].includes(path);
      check(state, label + ": the employer received " + (/sent$/.test(got) && intoAts ? "exactly one application" : "nothing"), n1 - n0 === (/sent$/.test(got) && intoAts ? 1 : 0), (n1 - n0) + " new");
      // the row in Job Tracker says what really happened
      if (true) {
        const row = await q("const x=w.__uaply.S.decisions[" + id + "];return x&&x.sent?x.sent.status:'(no row)'");
        check(state, label + ": Job Tracker keeps it as " + (/sent$/.test(got) ? "Sent" : got.startsWith("ask-file") ? "Not sent yet, with Answer now" : got === "needs_profile" ? "Needs profile" : "Finish on their site"),
          /sent$/.test(got) ? row === "sent" : got.startsWith("ask-file") ? row === "needs_answers" : got === "needs_profile" ? row === "needs_profile" : row === "handoff", row);
      } else check(state, label + ": nothing in Job Tracker, the card stays in the deck", (await q("return !w.__uaply.S.decisions[" + id + "]")) === true, "");
      // the card said so before the swipe
      const cw = R.cards && R.cards[key];
      if (cw) check(state, label + ": the card said \"" + cw + "\" before the swipe", !!cardObj && new RegExp(cw).test(cardObj.t), card);
    }
  }
  check("browser", "no script errors", logs.filter((l) => l.startsWith("EXC")).length === 0, logs.join(" | "));
  console.log("E2E-READY " + JSON.stringify(Object.assign(summary, { count })));
};
module.exports.limitMs = 900000;
