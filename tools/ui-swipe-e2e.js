// The swipe guarantee, in a real browser: the browser half of tools/test-swipe-e2e.py, which starts the servers, the stand-in hiring systems
// and the stand-in mail server, and then checks what each employer really received. Run it through that script:
//   python tools/test-swipe-e2e.py
// A person signs up (the 6-digit code read from the stand-in mail server), reads a Word resume into the profile, and swipes right on one job
// for each way UAply applies: straight into a connected Greenhouse, Lever, Ashby, SmartRecruiters and Workable, by email to an employer who
// agreed, and the hand-off (finish on the employer's site). Also: a required question only the person can answer (asked once on screen,
// nothing sent until answered), and a required file UAply cannot ask for (an honest hand-off, never dropped). Every line is PASS or FAIL;
// the last line is a JSON summary the Python half reads.
const fs = require("fs");
const PORT = process.env.PORT, BASE = "http://127.0.0.1:" + PORT;
const SMTP = process.env.SMTP_FILE, JOBS = JSON.parse(process.env.E2E_JOBS || "{}"), RESUME = process.env.RESUME;
const EMAIL = "elena.rossi@example.com", PASSWORD = "Swipe-guarantee-" + Math.random().toString(36).slice(2, 10) + "7";
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
  const boot = async () => {
    await nav(BASE + "/?app=1");
    await waitFor("return d.defaultView.__uaply&&d.getElementById('nb-prof')?1:0", 20000);
    await q("const y=d.getElementById('kcYes');if(y)y.click();const n=[...d.querySelectorAll('#locAsk button')].find(x=>/Not now/.test(x.innerText));if(n)n.click();const t=d.getElementById('tipsClose');if(t)t.click();return 1");
    await sleep(500);
  };
  const post = (p, body) => q("const r=await w.fetch(" + JSON.stringify(p) + ",{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(" + JSON.stringify(body) + ")});return JSON.stringify({s:r.status,j:await r.json().catch(()=>null)})").then((x) => { try { return JSON.parse(x); } catch (e) { return { s: 0, j: x }; } });
  const val = (id) => q("return (d.getElementById(" + JSON.stringify(id) + ")||{}).value||''");

  await nav(BASE + "/healthz");
  await send("Storage.clearDataForOrigin", { origin: BASE, storageTypes: "all" });
  await send("Network.clearBrowserCookies");
  await boot();

  // ---------- 0. an account with a verified email (the code comes from the stand-in mail server) ----------
  const su = await post("/api/auth/signup", { email: EMAIL, password: PASSWORD, agree: true });
  check("account", "sign-up answers 200 with the new account", su.s === 200 && su.j && su.j.user, JSON.stringify(su));
  let code = "";
  for (let i = 0; i < 40 && !code; i++) {
    const lines = fs.existsSync(SMTP) ? fs.readFileSync(SMTP, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];
    const m = lines.reverse().find((x) => (x.to || []).join(",").toLowerCase().includes(EMAIL));
    const hit = m && (m.raw.match(/Subject:[^\n]*\b(\d{6})\b/) || m.raw.match(/\b(\d{6})\b/));
    if (hit) code = hit[1]; else await sleep(250);
  }
  check("account", "the 6-digit code was emailed to the person", /^\d{6}$/.test(code), code);
  const vf = await post("/api/auth/verify", { code });
  check("account", "the code verifies the email", vf.s === 200, JSON.stringify(vf));
  // voluntary answers the person gave on this device: they must never leave it (checked below in the clipboard, and by the Python half
  // in everything the hiring systems and the mail server received)
  await q("const k=w.__uaplyKey+'.acct';const a=JSON.parse(w.localStorage.getItem(k)||'{}');a.eeo={gender:'Non-binary',veteran:'I am a protected veteran',race:['Native Hawaiian or Other Pacific Islander'],hisp:'Yes',disability:'Yes, I have a disability (or have had one)'};w.localStorage.setItem(k,JSON.stringify(a));return 1");
  await boot();
  const me = await q("const r=await w.fetch('/api/auth/me',{credentials:'same-origin'});return JSON.stringify(await r.json())");
  check("account", "the app is signed in with the verified account", /"emailVerified": ?true/.test(me) && me.includes(EMAIL), me);

  // ---------- 1. the resume fills the profile, and the profile screen shows it ----------
  const b64 = fs.readFileSync(RESUME).toString("base64");
  await q("w.__uaplyOpenProf('back');return 1"); await sleep(900);
  const chose = await q("const i=d.getElementById('rsFile');if(!i)return 'no box';const bin=atob(" + JSON.stringify(b64) + ");const u=new Uint8Array(bin.length);for(let k=0;k<bin.length;k++)u[k]=bin.charCodeAt(k);" +
    "const dt=new w.DataTransfer();dt.items.add(new w.File([u],'newgrad.docx',{type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}));i.files=dt.files;i.dispatchEvent(new w.Event('change',{bubbles:true}));return 'ok'");
  check("resume", "Fill from your resume takes a Word file", chose === "ok", chose);
  await waitFor("const b=d.getElementById('rsBox');return b&&b.getAttribute('aria-busy')!=='true'&&/Filled|filled|found/i.test((d.getElementById('rsMsg')||{}).innerText||'')?1:0", 15000);
  const got = { name: await val("pName"), email: await val("pEmail"), phone: await val("px-phone"), school: await val("px-school"), major: await val("px-major") };
  check("resume", "the profile screen shows the name read from the resume", got.name === "Elena Rossi", JSON.stringify(got));
  check("resume", "...the email", got.email === EMAIL, JSON.stringify(got));
  check("resume", "...the phone", got.phone.replace(/\D/g, "") === "6175550110", JSON.stringify(got));
  check("resume", "...and the education (school and major)", got.school === "Northeastern University" && got.major === "Marketing", JSON.stringify(got));
  // the two answers hiring systems ask that a resume never says (typed by the person), then Save
  await q("const s=(i,v)=>{const e=d.getElementById(i);if(!e)return;e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))};s('px-auth','citizen');s('px-sponsor','no');s('pTitle','Marketing Coordinator');return 1");
  await q("const b=d.getElementById('wzNext');if(b)b.click();return 1"); await sleep(1200);
  const prof = JSON.parse(await q("const p=w.__uaply.S.profile;return JSON.stringify({name:p.name,email:p.email,custom:!!p.custom,auth:(p.ext||{}).auth,resume:!!(w.__uaplyResume&&w.__uaplyResume())})") || "{}");
  check("resume", "the profile is saved with the resume's details, and the resume file is kept for applications", prof.name === "Elena Rossi" && prof.email === EMAIL && prof.custom && prof.resume, JSON.stringify(prof));

  // ---------- swipe right, exactly as the deck does it (prod's decide()), on a chosen job ----------
  const swipe = (id) => q("const A=w.__uaply,job=A.JOBS.find(j=>j.id===" + id + ");if(!job)return 'no job';const m=A.evaluate(job,A.S.profile);" +
    "A.S.decisions[job.id]={s:'applied',at:Date.now(),pct:m.pct,as:A.S.profile.name,title:A.S.profile.title};A.S.history.push(job.id);A.save();A.renderAll();" +
    "w.__uaplyOnDecision('applied',job,m,A.S.profile,function(){},A.S,A.save);return 'ok'");
  // a final status: "needs_answers" is marked while the question box is open, so it is not the end of a send
  const status = (id) => waitFor("const x=w.__uaply.S.decisions[" + id + "];return x&&x.sent&&x.sent.status&&x.sent.status!=='pending'&&x.sent.status!=='needs_answers'?x.sent.status:''", 15000);
  const toastText = () => q("const t=d.getElementById('kitToast');return t?t.innerText.replace(/\\s+/g,' '):''");
  const openApplied = async () => { await q("d.getElementById('nb-dash').click();return 1"); await sleep(300); await q("[...d.querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='applied').click();return 1"); await sleep(800); };
  const rowOf = async (id) => { await openApplied(); return JSON.parse(await q("const r=[...d.querySelectorAll('#pane-track .row')].find(r=>r.querySelector('[data-id=\"" + id + "\"]'));if(!r)return 'null';return JSON.stringify({chip:(r.querySelector('.stchip')||{}).textContent||'',links:[...r.querySelectorAll('.joblinks .linkbtn')].map(x=>x.innerText.trim()),text:r.innerText.replace(/\\s+/g,' ')})") || "null"); };
  const summary = { statuses: {}, password: PASSWORD };   /* the Python half signs in again for the weekly-limit check */

  // ---------- 2. connected hiring systems and the email employer: Sent ----------
  for (const [label, key] of [["greenhouse", "gh"], ["lever", "lever"], ["ashby", "ashby"], ["smartrecruiters", "sr"], ["workable", "wk"], ["email", "mail"], ["email-posting", "postmail"]]) {
    const path = label.startsWith("email") ? label : "ats-" + label;
    const id = JOBS[key];
    check(path, "the job is in the deck (an employer who agreed)", (await swipe(id)) === "ok");
    const st = await status(id);
    summary.statuses[key] = st;
    const t = await toastText();
    check(path, "the swipe right is sent (the server says sent)", st === "sent", st + " | " + t);
    check(path, "...and the message says it was applied", /^Applied to /.test(t), t);
    const r = await rowOf(id);
    check(path, "Applied shows the row with the status Sent", r && r.chip === "Sent", JSON.stringify(r));
    check(path, "...and only See the job posting (nothing left to finish)", r && JSON.stringify(r.links) === JSON.stringify(["See the job posting ↗"]), JSON.stringify(r));
  }

  // ---------- 3. a hand-off: quiet swipe, Applied shows the status and both links, the copied block is right ----------
  {
    const id = JOBS.handoff;
    check("handoff", "the job is in the deck", (await swipe(id)) === "ok");
    const st = await status(id); summary.statuses.handoff = st;
    const t = await toastText();
    check("handoff", "nothing is sent: the server says hand-off", st === "handoff", st);
    check("handoff", "the message is the hand-off's: 'Saved to Job Tracker. One tap to finish on their site.' (never Applied or Sent)", /^Saved to Job Tracker\. One tap to finish on their site\. ?Undo$/.test(t), t);
    const r = await rowOf(id);
    check("handoff", "Applied shows the status Finish on their site", r && r.chip === "Finish on their site", JSON.stringify(r));
    check("handoff", "...with See the job posting, Finish applying on their site and Mark as applied", r && JSON.stringify(r.links) === JSON.stringify(["See the job posting ↗", "Finish applying on their site ↗", "Mark as applied"]), JSON.stringify(r));
    await send("Browser.grantPermissions", { origin: BASE, permissions: ["clipboardReadWrite", "clipboardSanitizedWrite"] });
    await send("Emulation.setFocusEmulationEnabled", { enabled: true });
    await q("w.__e2eOpened=[];w.__uaplyOpen=function(u){w.__e2eOpened.push(u)};d.querySelector('[data-finish=\"" + id + "\"]').click();return 1");
    const copied = await waitFor("const t=d.getElementById('kitToast');return t&&/Profile copied, paste it into their form/.test(t.innerText)?1:0", 4000);
    const clip = await ev("document.querySelector('iframe').contentWindow.navigator.clipboard.readText().catch(e=>'READ FAILED '+e.message)");
    const opened = JSON.parse(await q("return JSON.stringify(w.__e2eOpened)") || "[]");
    check("handoff", "Finish applying copies the profile and says 'Profile copied, paste it into their form'", copied === 1, copied);
    check("handoff", "...the block is Name, Email and Phone from the resume", /^Name: Elena Rossi\r?\nEmail: elena\.rossi@example\.com\r?\nPhone: 617-555-0110$/.test(clip), JSON.stringify(clip));
    check("handoff", "...never the resume or a voluntary answer", !/resume|docx|Non-binary|veteran|Hawaiian|disab|Hispanic/i.test(clip), JSON.stringify(clip));
    check("handoff", "...and opens the employer's posting, with ?gh_src=uaply because it is a Greenhouse link", opened.length === 1 && /^https:\/\/boards\.greenhouse\.io\/handoffco\/jobs\/77\?gh_src=uaply$/.test(opened[0]), JSON.stringify(opened));
  }

  // ---------- 4. a required question only the person can answer: asked once on screen, nothing sent until answered ----------
  {
    const id = JOBS.question;
    await q("const t=d.getElementById('kitToast');if(t)t.remove();return 1");
    check("question", "the job is in the deck", (await swipe(id)) === "ok");
    const box = await waitFor("const o=d.getElementById('kitAsk');return o?o.innerText.replace(/\\s+/g,' '):''", 8000);
    check("question", "the question box opens with the employer's question", /favorite color/i.test(box || ""), box);
    const sentBefore = (await (await fetch("http://127.0.0.1:" + process.env.MOCK_PORT + "/__received")).json()).filter((g) => g.job === "1003").length;
    check("question", "...and nothing reached the employer while the question is open", sentBefore === 0, sentBefore);
    await q("const o=d.getElementById('kitAsk');o.querySelectorAll('[data-k]').forEach(el=>{el.value='Blue, it is calm.';el.dispatchEvent(new Event('input',{bubbles:true}))});d.getElementById('kaYes').click();return 1");
    const st = await status(id); summary.statuses.question = st;
    check("question", "once answered it is sent", st === "sent", st + " | " + await toastText());
    const r = await rowOf(id);
    check("question", "Applied shows Sent", r && r.chip === "Sent", JSON.stringify(r));
  }

  // ---------- 5. a required file UAply cannot ask for: an honest hand-off, never silently dropped ----------
  {
    const id = JOBS.file;
    await q("const t=d.getElementById('kitToast');if(t)t.remove();return 1");
    check("cannot-ask", "the job is in the deck", (await swipe(id)) === "ok");
    const st = await status(id); summary.statuses.file = st;
    check("cannot-ask", "nothing is sent and the person is told to finish there (hand-off), not left waiting", st === "handoff", st);
    const r = await rowOf(id);
    check("cannot-ask", "Applied shows Finish on their site with both links (and Mark as applied)", r && r.chip === "Finish on their site" && r.links.length === 3, JSON.stringify(r));
  }

  check("browser", "no script errors", logs.filter((l) => l.startsWith("EXC")).length === 0, logs.join(" | "));
  console.log("E2E-SUMMARY " + JSON.stringify(Object.assign(summary, { count })));
};
module.exports.limitMs = 420000;
