// Resume-first onboarding (card 181), in a real browser at phone size, on the sandbox (the sign-in gate, the resume experiment):
//   1. the first question after sign-up is the resume (its order lives in Q_ORDER, shared/uaply-signup.js)
//   2. "I don't have one right now": the questions, then one Phone question (skippable, checked as a US or international number)
//   3. a reload in the middle of the questions comes back to the same step with the answers given so far
//   4. a swipe right below the minimum opens the sheet: Not now keeps "Needs profile"; a phone number added there sends THAT application
//   5. a second person starts with a resume: a wrong file gets a plain sentence and a way on; the "Check these" card lists only what was
//      found, never the name typed on the card; a box cleared is left out; the questions the resume answered are not asked
//   W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-onboard.js        (a sandbox server: UAPLY_SIGNUP_TEST=1 python serve.py 18766 sandbox --api)
const fs = require("fs");
const path = require("path");
const PORT = process.env.PORT || "8766";
const BASE = "http://127.0.0.1:" + PORT;
const STUDENT = fs.readFileSync(path.join(__dirname, "fixtures", "resumes", "student.txt"), "utf8");
module.exports = async ({ ev, sleep, nav }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const W = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (n, ok, x) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + n + (ok || x === undefined ? "" : "  " + String(x).slice(0, 300))); };
  const q = (js) => ev("(()=>{try{const d=" + F + ",w=d.defaultView;" + js + "}catch(e){return 'ERR '+e.message}})()");
  const waitFor = async (js, ms) => { const end = Date.now() + (ms || 10000); let v; while (Date.now() < end) { v = await q(js); if (v && !String(v).startsWith("ERR")) return v; await sleep(200); } return v; };
  const h2 = () => q("const h=d.querySelector('#acctSec .sg-qs h2');return h?h.textContent:''");
  const next = () => q("d.querySelector('.sg-next').click();return 1");
  const gated = () => q("return d.body.classList.contains('sgGated')");
  const email = (t) => "first.onboard" + t + "." + Date.now().toString(36) + Math.random().toString(36).slice(2, 6) + "@example.com";
  const PW = "Onb-" + Math.random().toString(36).slice(2, 10) + "-pw9";
  const signUp = async (em) => {
    await waitFor("return d.body.classList.contains('sgGated')&&d.querySelector('.sg-su')?1:0", 20000);
    const setv = (sel, v) => q("const e=d.querySelector(" + JSON.stringify(sel) + ");if(!e)return 0;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return 1");
    await setv(".sg-su [data-email] input", em); await setv(".sg-su .sg-fn input", "Test"); await setv(".sg-su .sg-ln input", "Person"); await setv(".sg-su .sg-pw input", PW);
    await q("const a=d.querySelector('.sg-su .sg-ag');if(a&&!a.checked)a.click();d.querySelector('.sg-su [type=submit]').click();return 1");
    return waitFor("const h=d.querySelector('#acctSec .sg-qs h2');return h&&/resume/.test(h.textContent)?h.textContent:''", 15000);
  };
  // the resume experiment (FEATURES.resume) on at the start: its switch in the sandbox controls, pressed if it is off (a press reloads the app)
  const resumeOn = async () => {
    await sleep(300);
    const was = await ev("(()=>{const b=document.querySelector('#feats button[data-k=resume]');if(!b)return 'none';const p=b.getAttribute('aria-pressed');if(p!=='true')b.click();return p})()");
    if (was !== "true") await sleep(500);
    return ev("(()=>{const b=document.querySelector('#feats button[data-k=resume]');return b?b.getAttribute('aria-pressed'):'none'})()");
  };
  const consent = () => q("const y=d.getElementById('kcYes');if(y){d.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});y.disabled=false;y.click()}const t=d.getElementById('tipsClose');if(t)t.click();return 1");

  // ---------- person B: no resume ----------
  await nav(BASE + "/legal/privacy.html"); await ev("(()=>{localStorage.clear();sessionStorage.clear();return 1})()");
  await nav(BASE + "/");
  check("the resume experiment is on (FEATURES.resume)", (await resumeOn()) === "true");
  const first = await signUp(email("b"));
  check("the first question after sign-up is the resume", first === "Start with your resume — we’ll fill in the rest", first);
  const r1 = JSON.parse(await q("const s=d.querySelector('#acctSec .sg-qs');return JSON.stringify({eb:(s.querySelector('.sg-eyebrow')||{}).textContent,sub:(s.querySelector('.sg-sub')||{}).textContent," +
    "acc:(s.querySelector('.sg-rk input[type=file]')||{}).accept||'',pick:(s.querySelector('[data-rk=pick]')||{}).offsetHeight,next:d.querySelector('.sg-next').textContent,focus:d.activeElement&&d.activeElement.tagName,pv:(d.querySelector('.sg-pvmini')||{}).textContent})"));
  check("...it says a resume is needed to apply, what is read and who sees it, and counts its steps (1 of 4: resume, work, where, phone)", r1.sub === "Most jobs need a resume to apply. PDF, Word or text, up to 1 MB. Read once to fill your profile; employers only see it when you apply." && r1.eb === "1 of 4", JSON.stringify(r1));
  check("...takes PDF, Word and text, with a 44px pick button; focus is on the heading", /\.pdf/.test(r1.acc) && /\.docx/.test(r1.acc) && /\.txt/.test(r1.acc) && r1.pick >= 44 && r1.focus === "H2", JSON.stringify(r1));
  check("...the main button is the way past it: I don't have one right now; the preview says 2 of 3 needed", r1.next === "I don’t have one right now" && /2 of 3 needed/.test(r1.pv), JSON.stringify(r1));
  await next(); await sleep(400);
  check("skip: the questions follow (What kind of work)", /What kind of work/.test(await h2()), await h2());
  await q("[...d.querySelectorAll('.sg-chip')].find(b=>b.textContent==='Retail').click();return 1"); await sleep(200);
  // a reload in the middle: the same step, the answer kept, the gate still up
  await nav(BASE + "/"); await resumeOn();
  const back = await waitFor("const h=d.querySelector('#acctSec .sg-qs h2');return h?h.textContent:''", 15000);
  const kept = await q("const c=[...d.querySelectorAll('.sg-chip')].find(b=>b.textContent==='Retail');return c?c.getAttribute('aria-pressed'):''");
  check("a reload comes back to the same step with the answer kept (What kind of work, Retail picked), behind the gate", /What kind of work/.test(back) && kept === "true" && (await gated()) === true, back + " / " + kept);
  await next(); await sleep(400);
  check("...then Where do you live", /Where do you live/.test(await h2()), await h2());
  await next(); await sleep(400);
  const ph = JSON.parse(await q("return JSON.stringify({h:(d.querySelector('#acctSec .sg-qs h2')||{}).textContent,eb:(d.querySelector('.sg-eyebrow')||{}).textContent,type:(d.querySelector('.sg-ph input')||{}).type,next:d.querySelector('.sg-next').textContent})"));
  check("skip path: one Phone question, last (4 of 4), a phone box, skippable", ph.h === "What number can employers call?" && ph.eb === "4 of 4" && ph.type === "tel" && ph.next === "Skip", JSON.stringify(ph));
  await q("const i=d.querySelector('.sg-ph input');i.value='12';i.dispatchEvent(new Event('input',{bubbles:true}));return 1");
  await next(); await sleep(300);
  const perr = await q("return (d.querySelector('.sg-pherr')||{}).textContent");
  check("...a number that is not one is refused with a plain sentence", /US number/.test(perr) && /What number/.test(await h2()), perr);
  await q("const i=d.querySelector('.sg-ph input');i.value='';i.dispatchEvent(new Event('input',{bubbles:true}));return 1");
  await next(); await sleep(400);
  const done1 = await q("return d.querySelector('#acctSec .sg-qs').innerText");
  check("...skipped: Almost ready, add a phone number or a resume", /Almost ready/.test(done1) && /a phone number or a resume/.test(done1), done1.slice(0, 200));
  await next(); await sleep(1500);
  check("Show me jobs: the gate comes down", (await gated()) === false);
  await consent(); await sleep(900); await consent();
  await waitFor("return w.__uaply&&w.__uaply.JOBS&&w.__uaply.JOBS.length>1?1:0", 20000);
  // a swipe right exactly as the deck does it after the gate (prod's decide())
  const swipe = (i) => q("const A=w.__uaply,job=A.JOBS.filter(j=>!A.S.decisions[j.id])[" + i + "];if(!job)return 0;const m=A.evaluate(job,A.S.profile);" +
    "A.S.decisions[job.id]={s:'applied',at:Date.now(),pct:m.pct,as:A.S.profile.name,title:A.S.profile.title};A.S.history.push(job.id);A.save();A.renderAll();" +
    "w.__uaplyOnDecision('applied',job,m,A.S.profile,function(){},A.S,A.save);return job.id");
  const status = (id) => q("const x=w.__uaply.S.decisions[" + JSON.stringify(id) + "];return x&&x.sent?x.sent.status:''");
  const j1 = await swipe(0); await sleep(300); await consent();
  const sh = await waitFor("const s=d.querySelector('.rkSheet');return s?s.querySelector('h2').textContent:''", 5000);
  check("a swipe right below the minimum opens the sheet: Add your resume to send this", sh === "Add your resume to send this", sh);
  const shOpts = await q("const s=d.querySelector('.rkSheet');return JSON.stringify({pick:!!s.querySelector('[data-rk=pick]'),phone:!!s.querySelector('[data-sh=phone]'),st:" + JSON.stringify("") + "})");
  check("...with the resume upload and Add a phone number instead; nothing marked yet", /"pick":true/.test(shOpts) && /"phone":true/.test(shOpts) && (await status(j1)) === "", shOpts);
  // the arrow keys belong to the sheet: ArrowRight must not apply to the next job (and open a second sheet), ArrowLeft must not pass one unseen
  const nDec = () => q("return Object.keys(w.__uaply.S.decisions).length");
  const before = await nDec();
  for (const k of ["ArrowRight", "ArrowLeft", "ArrowRight"]) { await q("(d.activeElement||d.body).dispatchEvent(new KeyboardEvent('keydown',{key:" + JSON.stringify(k) + ",bubbles:true,cancelable:true}));return 1"); await sleep(250); }
  const keys = JSON.parse(await q("return JSON.stringify({sheets:d.querySelectorAll('.rkSheetBg').length,ph:d.querySelectorAll('#rkShPh').length})"));
  const after = await nDec();
  check("...with the sheet open, ArrowRight and ArrowLeft do nothing behind it: still one sheet, no job swiped", keys.sheets === 1 && keys.ph <= 1 && after === before, JSON.stringify(keys) + " decisions " + before + " -> " + after);
  await q("[...d.querySelectorAll('.rkSheet [data-sh=no]')][0].click();return 1"); await sleep(600);
  check("Not now: the sheet closes and the job is kept as Needs profile (as before)", !(await q("return !!d.querySelector('.rkSheet')")) && (await status(j1)) === "needs_profile", await status(j1));
  const j2 = await swipe(0); await sleep(300); await consent();
  await waitFor("return d.querySelector('.rkSheet')?1:0", 5000);
  await q("d.querySelector('.rkSheet [data-sh=phone]').click();return 1"); await sleep(200);
  await q("const i=d.getElementById('rkShPh');i.value='555';d.querySelector('.rkPh').requestSubmit();return 1"); await sleep(200);
  check("...a phone number that is not one is refused", /US number/.test(await q("return d.querySelector('.rkPh .err').textContent")));
  await q("const i=d.getElementById('rkShPh');i.value='+44 20 7946 0000';d.querySelector('.rkPh').requestSubmit();return 1");
  const st2 = await waitFor("const x=w.__uaply.S.decisions[" + JSON.stringify(j2) + "];const s=x&&x.sent&&x.sent.status;return s&&s!=='pending'?s:''", 20000);
  const rd = await q("return JSON.stringify({min:w.__uaplyReadiness().min,phone:w.__uaplyApplyExt().phone,sheet:!!d.querySelector('.rkSheet')})");
  check("a phone number added in the sheet: it closes, the minimum is met, and THAT application goes the normal way (not Needs profile)", /"min":true/.test(rd) && /\+44 20 7946 0000/.test(rd) && /"sheet":false/.test(rd) && st2 && st2 !== "needs_profile", st2 + " " + rd);

  // ---------- person A: starts with a resume ----------
  // sign out on the server and start the device fresh (the same way ui-apply-paths.js does)
  await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.status)");
  await nav(BASE + "/legal/privacy.html"); await ev("(()=>{localStorage.clear();sessionStorage.clear();return 1})()");
  await nav(BASE + "/"); await resumeOn();
  const h0 = await signUp(email("a"));
  check("a second person: the resume question first again", /Start with your resume/.test(h0), h0);
  const choose = (name, text, type) => q("const i=d.querySelector('.sg-rk input[type=file]');const dt=new w.DataTransfer();dt.items.add(new w.File([" + JSON.stringify(text) + "]," + JSON.stringify(name) + ",{type:" + JSON.stringify(type) + "}));i.files=dt.files;i.dispatchEvent(new w.Event('change',{bubbles:true}));return 1");
  await choose("photo.png", "not a resume", "image/png"); await sleep(300);
  const e1 = await q("return JSON.stringify({m:d.querySelector('.sg-rk .rkMsg').textContent,b:[...d.querySelectorAll('.sg-rk [data-rk=after] button')].map(b=>b.textContent)})");
  check("a picture: a plain sentence, Try another file and Continue without (never stuck)", /That is a picture/.test(e1) && /Try another file/.test(e1) && /Continue without/.test(e1), e1);
  // what the server finds in the made-up resume, to hold the card to it
  const found = JSON.parse(await ev("fetch('/api/profile/resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({resume:{name:'student.txt',data:'data:text/plain;base64,'+btoa(unescape(encodeURIComponent(" + JSON.stringify(STUDENT) + ")))}})}).then(r=>r.json()).then(j=>JSON.stringify(Object.keys(j.fields||{})))"));
  await choose("student.txt", STUDENT, "text/plain");
  const ck = await waitFor("const h=d.querySelector('.sg-rk .rkCheck h3');return h?h.textContent:''", 15000);
  const card = JSON.parse(await q("return JSON.stringify({focus:d.activeElement&&d.activeElement.textContent,rows:[...d.querySelectorAll('.sg-rk .rkF')].map(f=>({l:f.querySelector('label').childNodes[0].textContent.trim(),v:f.querySelector('input').value,src:/From your resume/.test(f.textContent)}))})"));
  const labels = card.rows.map((r) => r.l);
  check("Check these: the card lists what was found, focus on its heading", ck === "Check these" && card.focus === "Check these" && card.rows.length > 0, JSON.stringify(card).slice(0, 300));
  check("...the name typed on the card is not offered (never overwrite a typed value)", labels.indexOf("Full name") < 0, labels.join(","));
  check("...phone, city, state and ZIP from the resume, each with its source line", ["Phone", "City", "State", "ZIP code"].every((l) => labels.indexOf(l) > -1) && card.rows.every((r) => r.src), labels.join(","));
  const KEY = { "Phone": "phone", "City": "location", "State": "location", "ZIP code": "location", "Email": "email", "Job title": "job_title", "School": "school", "Major": "major", "GPA": "gpa", "Graduation": "grad", "Skills": "skills", "LinkedIn": "linkedin", "Portfolio or GitHub": "portfolio", "Summary": "summary", "Headline": "headline", "Most recent employer": "employer", "Started": "job_start", "Ended": "job_end" };
  check("...and nothing the resume did not have", labels.every((l) => KEY[l] && found.indexOf(KEY[l]) > -1), labels.join(",") + " / " + found.join(","));
  await q("const f=[...d.querySelectorAll('.sg-rk .rkF')].find(f=>/ZIP/.test(f.querySelector('label').textContent));f.querySelector('input').value='';return 1");
  await q("d.querySelector('.sg-rk .rkCheck [type=submit]').click();return 1");
  const done2 = await waitFor("const s=d.querySelector('#acctSec .sg-done h2');return s?s.textContent:''", 10000);
  check("saved: the questions the resume answered (work, where) and the phone question are not asked: ready to swipe", done2 === "You’re ready to swipe.", done2 + " / " + (await h2()));
  const pv = await q("return (d.querySelector('.sg-pv')||{}).textContent||''");
  check("...the preview says 3 of 3 needed, Resume added", /3 of 3 needed/.test(pv) && /Resume added/.test(pv), pv.slice(0, 600));
  const st = JSON.parse(await q("const p=w.__uaply.S.profile,x=w.__uaplyApplyExt(),r=w.__uaplyResume&&w.__uaplyResume();return JSON.stringify({name:p.name,loc:p.loc,title:p.title,phone:x.phone,state:x.state,zip:x.zip||'',res:r&&r.name,headline:(p.ext||{}).headline||'',summary:x.summary||'',linkedin:x.linkedin||''})"));
  check("...kept where Profile setup keeps them: city, state, phone, title; the typed name; the ZIP left out; the file is the application resume",
    st.name === "Test Person" && st.loc === "Philadelphia" && st.state === "PA" && st.phone === "(215) 555-0134" && st.title === "Software Engineering Intern" && st.zip === "" && st.res === "student.txt", JSON.stringify(st));
  check("...nothing filled that the resume did not say", ["headline", "summary", "linkedin"].every((k) => found.indexOf(k) > -1 || !st[k]), JSON.stringify(st));
  console.log(bad ? "FAILED: " + bad : "ALL ONBOARDING CHECKS PASSED");
  if (bad) process.exitCode = 1;
};
