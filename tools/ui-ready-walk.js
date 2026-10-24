// A student with a half-finished profile tries to apply, with a finger, at phone size (390x844) or laptop size (1280x800). Run by
// tools/test-swipe-e2e.py (it starts the server, the stand-in hiring systems and mail, and checks what Greenhouse received):
//   1. the top card has no profile badge; a swipe right saves it to Job Tracker as Needs profile, with one Complete profile line
//   2. one tap on Add next to Phone number opens Profile setup with the phone field ready; the number is typed and saved
//   3. back on the job, the card says "2 answers needed" (the employer's form wants a resume and asks about work authorization)
//   4. Send now opens the question box with just those two; the answer is kept and Open Profile goes to the resume step
//   5. the resume file is added; the job waits in Job Tracker as "Not sent yet" with Answer now
//   6. Answer now sends it without asking again, and Job Tracker says Sent
// SHOTS=folder saves a picture of each step. The last line is a JSON summary.
const fs = require("fs");
const path = require("path");
const PORT = process.env.PORT, BASE = "http://127.0.0.1:" + PORT, SMTP = process.env.SMTP_FILE;
const JOB = +process.env.WALK_JOB, EMAIL = process.env.WALK_EMAIL, W = +(process.env.W || 390), H = +(process.env.H || 844);
const PASSWORD = "Walk-" + Math.random().toString(36).slice(2, 10) + "7";
module.exports = async ({ ev, sleep, nav, send, shot, logs }) => {
  const tag = "walk-" + W;
  const count = {};
  const check = (name, ok, extra) => {
    count[tag] = count[tag] || { pass: 0, fail: 0 }; count[tag][ok ? "pass" : "fail"]++;
    console.log((ok ? "PASS " : "FAIL ") + "[" + tag + "] " + name + (ok || !extra ? "" : "  -> " + String(extra).slice(0, 300)));
    return ok;
  };
  const snap = async (n) => { if (process.env.SHOTS) { fs.mkdirSync(process.env.SHOTS, { recursive: true }); await shot(path.join(process.env.SHOTS, "walk-" + W + "-" + n + ".png")); } };
  const F = "document.querySelector('iframe').contentDocument";
  const q = (js) => ev("(async()=>{try{const d=" + F + ",w=d.defaultView;" + js + "}catch(e){return 'ERR '+e.message}})()");
  const waitFor = async (js, ms) => { const end = Date.now() + (ms || 10000); let v; while (Date.now() < end) { v = await q(js); if (v && !String(v).startsWith("ERR")) return v; await sleep(250); } return v; };
  const tapAt = async (x, y) => { await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] }); await sleep(60); await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] }); await sleep(400); };
  const where = (finder) => q("const e=(" + finder + ");if(!e)return null;e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect(),o=document.querySelector('iframe').getBoundingClientRect();return {x:Math.round(o.left+r.left+r.width/2),y:Math.round(o.top+r.top+r.height/2)}");
  const tap = async (finder) => { const p = await where(finder); if (!p || typeof p !== "object") return false; await sleep(150); const p2 = await where(finder); await tapAt(p2.x, p2.y); return true; };
  const swipeRight = async () => {
    const c = await q("const e=d.querySelector('.card.top');if(!e)return null;const r=e.getBoundingClientRect(),o=document.querySelector('iframe').getBoundingClientRect();return {x:Math.round(o.left+r.left+r.width/2),y:Math.round(o.top+r.top+Math.min(r.height/2,160))}");
    if (!c || typeof c !== "object") return false;
    await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: c.x, y: c.y }] });
    for (let i = 1; i <= 12; i++) { await sleep(16); await send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: c.x + 20 * i, y: c.y }] }); }
    await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] }); await sleep(1100); return true;
  };
  const post = (p, body) => q("const r=await w.fetch(" + JSON.stringify(p) + ",{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(" + JSON.stringify(body) + ")});return JSON.stringify({s:r.status,j:await r.json().catch(()=>null)})").then((x) => { try { return JSON.parse(x); } catch (e) { return { s: 0, j: x }; } });
  const boot = async () => {
    await nav(BASE + "/?app=1");
    await waitFor("return w.__uaplyReadiness&&w.__uaplyReadyOf&&w.__uaplySubmitOn&&w.__uaplyMode&&d.getElementById('nb-prof')?1:0", 30000);
    await sleep(900);
    await q("const y=d.getElementById('kcYes');if(y)y.click();const n=[...d.querySelectorAll('#locAsk button')].find(x=>/Not now/.test(x.innerText));if(n)n.click();const t=d.getElementById('tipsClose');if(t)t.click();return 1");
    await sleep(500);
  };

  await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: W < 700 ? 2 : 1, mobile: W < 700 });
  await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  await nav(BASE + "/healthz");
  await send("Storage.clearDataForOrigin", { origin: BASE, storageTypes: "all" });
  await send("Network.clearBrowserCookies");
  await boot();
  // an account with a verified email (a live server sends straight to an employer only from one)
  const su = await post("/api/auth/signup", { email: EMAIL, password: PASSWORD, agree: true });
  let code = "";
  for (let i = 0; i < 40 && !code; i++) {
    const lines = fs.existsSync(SMTP) ? fs.readFileSync(SMTP, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];
    const m = lines.reverse().find((x) => (x.to || []).join(",").toLowerCase().includes(EMAIL));
    const hit = m && (m.raw.match(/Subject:[^\n]*\b(\d{6})\b/) || m.raw.match(/\b(\d{6})\b/));
    if (hit) code = hit[1]; else await sleep(250);
  }
  const vf = await post("/api/auth/verify", { code });
  check("a new account with a verified email", su.s === 200 && vf.s === 200, JSON.stringify([su.s, vf.s]));
  await boot();      // signed in now: the job list loads only for an account (Saif, October 22: nobody reaches site data without one)
  // the half-finished student: name, email, school and major, a city, no phone, no resume, no work authorization; every other job
  // already passed, so this employer's job is the one on top
  await q(`const K=w.__uaplyKey,S=JSON.parse(w.localStorage.getItem(K)||'{}');S.profile=Object.assign({},S.profile||{},{custom:true,name:'Sam Rivera',email:${JSON.stringify(EMAIL)},
      title:'Campus Ambassador',years:0,skills:['Canva','HubSpot','Excel'],loc:'Philadelphia, PA',edu:'High school',salary:0,
      ext:{school:'Temple University',major:'Communications',sponsor:'no'}});
    S.decisions=S.decisions||{};S.history=S.history||[];w.__uaply.JOBS.forEach(j=>{if(j.id!==${JOB}&&!S.decisions[j.id])S.decisions[j.id]={s:'passed',at:Date.now(),pct:50}});
    w.localStorage.setItem(K,JSON.stringify(S));return 1`);
  await boot();
  const top = await waitFor("const c=d.querySelector('#deck .card.top');return c?+c.getAttribute('data-id'):0", 8000);
  check("the employer's job is on top of the deck", top === JOB, top + " vs " + JOB);
  await sleep(1500);
  const b1 = await q("const s=d.querySelector('#deck .card.top .facts .rdy');return s?s.textContent:''");
  check("1. the card has no profile badge (no per-card nagging)", b1 === "", b1);
  await snap("1-card");
  // 1. a finger swipe right (Saif, October 24: an incomplete profile never blocks it): saved to Job Tracker, and one line says so
  await q("try{w.sessionStorage.removeItem('uaply.np')}catch(e){}w.__uaplyNPTold=false;return 1");
  await swipeRight();
  const line = await waitFor("const t=d.getElementById('kitToast');return t?t.innerText:''", 6000);
  check("1. a swipe right saves it: 'Saved to your Job Tracker. Complete your profile to send applications automatically.' with Complete profile",
    String(line).startsWith("Saved to your Job Tracker. Complete your profile to send applications automatically.") && String(line).indexOf("Complete profile") > -1, line);
  check("1. ...Job Tracker has it as Needs profile, and the deck moved on", (await q("const x=w.__uaply.S.decisions[" + JOB + "];return x&&x.sent?x.sent.status:''")) === "needs_profile" &&
    (await q("const c=d.querySelector('#deck .card.top');return c?+c.getAttribute('data-id'):0")) !== JOB, "");
  await snap("2-saved-needs-profile");
  // 2. one tap on Complete profile: Profile setup at the first missing step (the phone number)
  await tap("[...d.querySelectorAll('#kitToast button')].find(b=>b.textContent.trim()==='Complete profile')");
  const focus = await waitFor("const a=d.activeElement;return a&&/phone/i.test(a.id)?a.id:''", 4000);
  check("2. Complete profile opens Profile setup with the phone field focused", !!focus, focus);
  await send("Input.insertText", { text: "215-555-0142" });
  await q("const e=d.activeElement;if(e)e.dispatchEvent(new Event('input',{bubbles:true}));return 1");
  await snap("3-phone");
  await tap("d.getElementById('wzNext')");
  await sleep(900);
  const rd = JSON.parse(await q("return JSON.stringify(w.__uaplyReadiness())") || "{}");
  check("2. saved: the profile now has the minimum", rd.min === true, JSON.stringify(rd).slice(0, 200));
  // 3. Job Tracker: the saved job now offers Send now; one tap sends it, and the employer's form asks two things first
  await tap("d.getElementById('nb-dash')"); await sleep(300);
  await tap("[...d.querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')==='applied')"); await sleep(900);
  const row0 = await q(`const b=d.querySelector('#pane-track [data-id="${JOB}"]');const r=b&&b.closest('.row');return r?r.innerText:''`);
  check("3. Job Tracker: the saved job offers Send now", row0.indexOf("Send now") > -1, row0);
  await snap("4-send-now");
  await tap("[...d.querySelectorAll('#pane-track [data-act=resend]')].find(b=>+b.getAttribute('data-id')===" + JOB + ")");
  const ask = await waitFor("const o=d.getElementById('kitAsk');return o?o.innerText.replace(/\\s+/g,' '):''", 8000);
  check("4. Send now opens the question box: work authorization, and a resume file", /^2 questions from Acme Robotics/.test(ask || "") && /authorized to work/i.test(ask || "") && /needs a resume file/i.test(ask || ""), ask);
  check("4. ...nothing was sent yet", (await q("return d.getElementById('kaYes').textContent")) === "Open Profile", await q("return d.getElementById('kaYes').textContent"));
  await snap("5-question");
  await q("const o=d.getElementById('kitAsk');o.querySelectorAll('select').forEach(s=>{const y=[...s.options].find(x=>/^yes/i.test(x.text));if(y){s.value=y.value;s.dispatchEvent(new Event('change',{bubbles:true}))}});o.querySelectorAll('input[type=radio]').forEach(r=>{if(/^yes/i.test((r.closest('label')||r.parentElement).innerText))r.click()});return 1");
  await tap("d.getElementById('kaYes')");                       // Open Profile: the answer is kept, the resume step opens
  const st1 = await waitFor("const x=w.__uaply.S.decisions[" + JOB + "];return x&&x.sent?x.sent.status:''", 5000);
  check("5. the answer is kept and the job waits in Job Tracker as Not sent yet", st1 === "needs_answers", st1);
  const onStep = await waitFor("const e=d.getElementById('aResF');return e&&e.offsetParent?'yes':''", 5000);   // the resume box (its own picker is hidden where Fill from your resume is the one picker)
  check("5. Profile setup opens on the step with the resume file", onStep === "yes", onStep);
  // the student adds a resume file (a file picker cannot be driven, so the file goes into the same input a picker fills)
  const b64 = fs.readFileSync(path.join(__dirname, "fixtures", "resumes", "newgrad.docx")).toString("base64");
  await q("const i=d.getElementById('pResFile');const bin=atob(" + JSON.stringify(b64) + ");const u=new Uint8Array(bin.length);for(let k=0;k<bin.length;k++)u[k]=bin.charCodeAt(k);" +
    "const dt=new w.DataTransfer();dt.items.add(new w.File([u],'sam-rivera-resume.docx',{type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}));i.files=dt.files;i.dispatchEvent(new w.Event('change',{bubbles:true}));return 1");
  const kept = await waitFor("const r=w.__uaplyResume&&w.__uaplyResume();return r&&r.name?r.name:''", 6000);
  check("5. the resume file is kept for applications", kept === "sam-rivera-resume.docx", kept);
  await tap("d.getElementById('wzNext')"); await sleep(800);
  await snap("6-resume");
  // 6. Job Tracker: Not sent yet, with Answer now; one tap sends it, nothing is asked again
  await tap("d.getElementById('nb-dash')"); await sleep(300);
  await tap("[...d.querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')==='applied')"); await sleep(900);
  const row = await q("const b=d.querySelector('#pane-track [data-id=\"" + JOB + "\"]');const r=b&&b.closest('.row');return r?r.innerText.replace(/\\s+/g,' '):''");
  check("6. Job Tracker: Not sent yet, with Answer now", /Not sent yet/.test(row) && /Answer now/.test(row), row);
  await snap("7-not-sent-yet");
  await tap("[...d.querySelectorAll('#pane-track [data-act=resend]')].find(b=>+b.getAttribute('data-id')===" + JOB + ")");
  const again = await waitFor("if(d.getElementById('kitAsk'))return 'asked again';const x=w.__uaply.S.decisions[" + JOB + "];return x&&x.sent&&['sent','failed','handoff'].includes(x.sent.status)?x.sent.status:''", 15000);
  check("6. Answer now sends it: nothing asked again (the answer and the resume are there now)", again === "sent", again);
  const st = again;
  await sleep(600);
  const chip = await q("const b=d.querySelector('#pane-track [data-id=\"" + JOB + "\"]');const r=b&&b.closest('.row');return r?(r.querySelector('.stchip')||{}).textContent||'':''");
  check("6. Job Tracker says Sent", chip === "Sent", chip);
  await snap("8-sent");
  // the checklist on Account and on the last setup step: ready to apply, with one tap for what the profile still leaves to a question
  await tap("d.getElementById('nb-prof')"); await sleep(300);
  await tap("[...d.querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')==='account')"); await sleep(900);
  const acc = await q("const b=d.querySelector('#acctSec .rdyList');return b?b.innerText.replace(/\\s+/g,' '):''");
  check("7. Account shows the checklist: ready to apply, work authorization still one tap away", /^Ready to apply · \d of 8 filled in/.test(acc) && /Work authorization Add/.test(acc) && /Phone number Done/.test(acc), acc.slice(0, 200));
  await snap("9-account");
  await tap("d.querySelector('#acctSec [data-ready=auth]')"); await sleep(900);
  const authF = await waitFor("const a=d.activeElement;return a&&/auth/.test(a.id)?a.id:''", 4000);
  check("7. Add next to Work authorization opens the setup step with that question focused", !!authF, authF);
  const last = await q("const b=d.getElementById('wzReady');return b&&b.offsetParent?b.innerText.replace(/\\s+/g,' ').slice(0,80):''");
  check("7. the last setup step shows the same checklist above Finish", /^Ready to apply/.test(last), last);
  check("no script errors", logs.filter((l) => l.startsWith("EXC")).length === 0, logs.join(" | "));
  console.log("E2E-WALK " + JSON.stringify({ count, top, line: String(line || "").slice(0, 120), ask: (ask || "").slice(0, 120), status: st }));
};
module.exports.limitMs = 420000;
