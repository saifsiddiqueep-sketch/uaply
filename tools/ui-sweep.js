// Walks every screen of the sandbox (or dev: PORT=8767) in a headless browser and reports what is missing or throws.
// node tools/cdp.js tools/ui-sweep.js
const PORT = process.env.PORT || "8766";
const REL = process.env.REL === "1";      // the release build (dev): no Plan screen, real jobs only (covered by tools/ui-release.js)
const gateSignup = require("./gate-signup.js");   // the test person signs up first (Saif, October 22: no account, no data)
module.exports = async ({ ev, sleep, nav, logs }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const W = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok || (typeof ok === "string" && ok.startsWith("JSERR"))) { ok = false; bad++; } console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const clickText = (txt, scope = "button,a,[role=tab]") => ev("(()=>{const e=[...(" + F + ").querySelectorAll('" + scope + "')].find(b=>b.innerText.split(/\\s+/).join(' ').trim().startsWith(" + JSON.stringify(txt) + "));if(!e)return false;e.click();return true})()");
  const visibleText = () => ev("(" + F + ").body.innerText.split(/\\s+/).join(' ')");

  await gateSignup({ ev, sleep, nav }, "http://127.0.0.1:" + PORT, "sweep");
  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(1500);
  check("page loads with job cards", (await ev(F + ".querySelectorAll('.card').length")) >= 1);

  // services
  await ev(F + ".getElementById('nb-svc').click()");
  await sleep(500);
  for (const tab of ["Full-time", "Part-time", "Internships", "Coop"]) {
    const ok = await clickText(tab);
    await sleep(400);
    check("Services: " + tab + " (cards or an empty message shows)", ok && ((await ev(F + ".querySelectorAll('.card').length")) > 0 || (await visibleText()).length > 200));
  }
  await clickText("Full-time");
  await sleep(400);
  for (const f of ["All", "Remote", "Hybrid", "On-site"]) {
    check("filter chip " + f, await clickText(f, "button"));
    await sleep(150);
  }
  await clickText("All", "button");
  await sleep(500);
  // swipe right on a job: the application must reach the simulated recruiter inbox
  const before = JSON.parse(await ev("fetch('/api/outbox').then(r=>r.json()).then(j=>JSON.stringify({n:j.applications.length}))")).n;
  // fill in the profile the way a person would (Profile, Profile setup), then save
  await ev(F + ".getElementById('nb-prof').click()");
  await sleep(400);
  await clickText("Profile setup");
  await sleep(400);
  const setVal = (id, v) => ev("(()=>{const e=" + F + ".getElementById('" + id + "');if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  check("profile name field", await setVal("pName", "Test User"));
  check("profile email field", await setVal("pEmail", "sweep.tester@example.com"));
  // a phone number too: a swipe right needs a name, an email and a phone number or a resume before it can apply (October 21)
  check("profile phone field", await setVal((await ev("!!" + F + ".getElementById('px-phone')")) ? "px-phone" : "pPhone", "+1 215 555 0100"));
  await setVal("pSkills", "Python, SQL, Git");
  await ev("(()=>{const f=" + F + ".getElementById('wzNext');f.click();return true})()");
  await sleep(800);
  await ev(F + ".getElementById('nb-svc').click()");
  await sleep(600);
  check("Apply button exists", !!(await ev("!!" + F + ".getElementById('btnYes')")));
  await ev(F + ".getElementById('btnYes').click()");
  await sleep(1500);
  console.log("  consent dialog:", await ev("(()=>{const m=" + F + ".getElementById('kcYes');if(!m)return 'none (already agreed)';m.click();return 'agreed'})()"));
  await sleep(2500);
  // the sandbox fills in the employer's real form; if it has questions only the person can answer, it asks them once: answer and send
  const asked = await ev("(()=>{const o=" + F + ".getElementById('kitAsk');if(!o)return 0;let n=0;o.querySelectorAll('[data-k]').forEach(el=>{n++;if(el.tagName==='SELECT')el.value=el.options[1]?el.options[1].text:'';else el.value=el.tagName==='TEXTAREA'?'Because I build things.':'Sam'});const b=" + F + ".getElementById('kaYes');if(b&&!/Profile/.test(b.innerText))b.click();return n})()");
  const needsFile = await ev("/needs a resume file/.test((" + F + ".getElementById('kitAsk')||{}).innerText||'')");
  if (asked) { console.log("  the employer's form asked", asked, "question(s); answered once" + (needsFile ? " (it also needs a resume file, which this profile has not got)" : "")); await sleep(3000); }
  // the server answers a swipe right in a second or two, longer on a busy machine: wait up to 15 s for the inbox to grow, not a fixed 2.5 s
  let after = 0;
  for (let i = 0; i < 30; i++) { after = JSON.parse(await ev("fetch('/api/outbox').then(r=>r.json()).then(j=>JSON.stringify({n:j.applications.length}))")).n; if (after > before) break; await sleep(500); }
  console.log("  applications in inbox before/after:", before, after);
  const newest = await ev("fetch('/api/outbox').then(r=>r.json()).then(j=>(j.applications[0]||{}).status||'')");
  check(REL ? "swipe right on a real job is recorded as a hand-off to the employer's own page" : "swipe right created an application in the test inbox",
        REL ? after > before && newest === "handoff" : (after > before || needsFile), "(newest status: " + newest + (needsFile ? "; the employer needs a resume file first" : "") + ")");
  // Job Tracker (the nb-dash menu)
  await ev(F + ".getElementById('nb-dash').click()");
  await sleep(500);
  for (const t of ["Overview", "Applied", "Accepted", "Rejected", "Interviews"]) {
    check("Job Tracker: " + t, await clickText(t));
    await sleep(250);
  }
  // profile sections
  await ev(F + ".getElementById('nb-prof').click()");
  await sleep(500);
  for (const t of ["Account", "Profile setup", "Filters", "Plan", "Data"]) {
    const ok = await clickText(t);
    await sleep(350);
    const txt = await visibleText();
    check("Profile: " + t, ok && txt.length > 100, "(clicked=" + ok + ", text length=" + txt.length + ")");
  }
  // data & privacy has the legal block
  check("Data & privacy shows Legal links", (await ev(F + ".querySelectorAll('[data-legal]').length")) === 5);
  // settings controls
  await clickText("Profile setup");
  await sleep(400);
  check("Profile setup has a Save and continue button", !!(await ev("!!" + F + ".getElementById('wzNext')")));
  // help assistant
  check("Help button opens the assistant", await ev("(()=>{const b=" + F + ".getElementById('uaChatBtn');if(!b)return false;b.click();return true})()"));
  await sleep(500);
  check("assistant panel appears", await ev("!!" + F + ".querySelector('#uaChat, .uaChat, [id^=uaChat]:not(#uaChatBtn)')"));
  // legal bar
  check("legal bar links (Terms, Privacy, AI and matching, Copyright, Support)", (await ev(F + ".querySelectorAll('#legalbar a').length")) === 5);
  console.log(bad ? "\n" + bad + " check(s) failed" : "\nAll sweep checks passed");
};
