// Types script and HTML payloads into every profile field, applies for a job, then walks the screens and the owner's test inbox:
// nothing may execute and no injected element may appear.
//   W=390 H=844 PORT=18795 node tools/cdp.js tools/ui-inject.js
const PORT = process.env.PORT || "18795";
module.exports = async ({ ev, sleep, nav }) => {
  const F = "document.querySelector('iframe').contentDocument";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const click = (txt) => ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a,[role=tab]')].find(b=>b.offsetParent&&b.innerText.split(/\\s+/).join(' ').trim().startsWith(" + JSON.stringify(txt) + "));if(!e)return false;e.click();return true})()");
  const set = (id, v) => ev("(()=>{const e=" + F + ".getElementById('" + id + "');if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  const XSS = "(window.top.__xss=(window.top.__xss||0)+1)";
  const P1 = '<img src=x onerror="' + XSS + '">';
  const P2 = '"><script>' + XSS + "</script>";
  const P3 = "javascript:" + XSS;
  const P4 = "'><svg onload=" + XSS + ">";
  const goto = async (nb, label) => {
    await ev(F + ".getElementById('" + nb + "').click()"); await sleep(350);
    let ok = await click(label);
    if (!ok) { await ev(F + ".getElementById('" + nb + "').click()"); await sleep(350); ok = await click(label); }
    await sleep(600);
    return ok;
  };
  const injected = () => ev("JSON.stringify({xss:window.top.__xss||0,imgs:" + F + ".querySelectorAll('img[src=x]').length,svgs:" + F + ".querySelectorAll('svg[onload]').length,scripts:[..." + F + ".querySelectorAll('script')].filter(s=>/__xss/.test(s.textContent)).length,handlers:[..." + F + ".querySelectorAll('*')].filter(e=>e.hasAttribute('onerror')||e.hasAttribute('onload')).length})");

  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(3500);

  // an account, so the application is sent as a signed-in person
  await goto("nb-prof", "Account");
  await sleep(1200);
  await set("sEmail", "inject.tester@example.com"); await set("sPw", "correct horse 99"); await set("sPw2", "correct horse 99");
  await ev("(()=>{" + F + ".getElementById('sAgree').checked=true})()");
  await ev(F + ".querySelector('[data-auth=ssubmit]').click()"); await sleep(2500);

  // hostile text in every free-text profile field
  await goto("nb-prof", "Profile setup");
  await set("pName", P1); await set("pEmail", "inject.tester@example.com"); await set("pSkills", P1 + ", " + P4 + ", Python"); await set("pLoc", P4);
  await set("px-phone", "+1 555 123 4567");                  // a phone box rightly refuses markup, so it gets a valid number; every free-text box gets the payload
  for (const id of ["px-school", "px-major", "px-employer", "px-job_title", "px-headline", "px-gpa"]) await set(id, P1);
  await ev(F + ".getElementById('saveBtn').click()"); await sleep(800);
  await goto("nb-prof", "Profile setup");   // Settings, Resume and Preferences are now steps of Profile setup: every field is on this one form
  await set("px-phone", "+1 555 123 4567");
  for (const id of ["px-school", "px-major", "px-employer", "px-job_title", "px-headline", "px-gpa"]) await set(id, P1);
  for (const id of ["px-linkedin", "px-portfolio", "px-resume"]) await set(id, P3);
  await set("px-summary", P1 + P2 + P4);
  for (const id of ["px-cover", "px-note"]) await set(id, P1 + P2);
  await ev(F + ".getElementById('saveBtn')&&" + F + ".getElementById('saveBtn').click()"); await sleep(800);
  let r = JSON.parse(await injected());
  check("nothing ran while the hostile text was typed and saved", r.xss === 0 && r.imgs === 0 && r.svgs === 0 && r.scripts === 0, JSON.stringify(r));

  // reload (everything is now read back from storage) and walk every screen
  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(3500);
  for (const [nb, label] of [["nb-prof", "Account"], ["nb-prof", "Profile setup"], ["nb-prof", "Filters"], ["nb-prof", "Data"],
                             ["nb-dash", "Overview"], ["nb-dash", "Applied"], ["nb-dash", "Interviews"], ["nb-svc", "Internships"], ["nb-svc", "Coop"], ["nb-svc", "Full-time"]]) {
    await goto(nb, label);
    r = JSON.parse(await injected());
    check("after reload, " + label + " runs and shows nothing injected", r.xss === 0 && r.imgs === 0 && r.svgs === 0 && r.scripts === 0 && r.handlers === 0, r.xss || r.imgs || r.handlers ? JSON.stringify(r) : "");
  }
  // the typed text is shown as plain text, not as markup
  await goto("nb-prof", "Profile setup");
  const nameShown = await ev(F + ".getElementById('pName').value");
  check("the name box still holds the exact text typed (shown, not run)", nameShown === P1, JSON.stringify(nameShown).slice(0, 60));

  // apply for a job with that profile, then look at Applied and at the owner's test inbox
  await goto("nb-svc", "Full-time");
  const appsBefore = await ev("fetch('/api/outbox').then(r=>r.json()).then(j=>j.applications.length)");
  await ev(F + ".getElementById('btnYes').click()"); await sleep(1500);
  await ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m)m.click()})()"); await sleep(3500);
  // the sandbox fills in the employer's real form and asks once for anything only the person can answer: answer (with hostile text too) and send
  if (await ev("(()=>{const o=" + F + ".getElementById('kitAsk');if(!o)return false;o.querySelectorAll('[data-k]').forEach(el=>{if(el.tagName==='SELECT')el.value=el.options[1]?el.options[1].text:'';else el.value=" + JSON.stringify("<img src=x onerror=\"window.top.__xss=1\">") + "});const b=" + F + ".getElementById('kaYes');if(b&&!/Profile/.test(b.innerText)){b.click();return true}return false})()")) await sleep(3500);
  const appsAfter = await ev("fetch('/api/outbox').then(r=>r.json()).then(j=>j.applications.length)");
  check("the swipe with the hostile profile was really sent (so the checks below are looking at something)", appsAfter > appsBefore, "(" + appsBefore + " -> " + appsAfter + ")");
  console.log("   screen after the swipe:", (await ev("(" + F + ").body.innerText.split(/" + String.fromCharCode(92) + "s+/).join(' ')")).slice(0, 420));
  r = JSON.parse(await injected());
  check("after applying with the hostile profile nothing ran", r.xss === 0 && r.imgs === 0 && r.handlers === 0, JSON.stringify(r));
  // the job title is typed last: a custom title rightly filters the deck, so it goes in after the swipe
  await goto("nb-prof", "Profile setup");
  await set("pTitle", P2);
  await ev(F + ".getElementById('saveBtn').click()"); await sleep(800);
  r = JSON.parse(await injected());
  check("a hostile job title typed and saved runs nothing", r.xss === 0 && r.imgs === 0 && r.scripts === 0 && r.handlers === 0, JSON.stringify(r));
  await goto("nb-dash", "Applied");
  r = JSON.parse(await injected());
  check("the Applied list shows nothing injected", r.xss === 0 && r.imgs === 0 && r.handlers === 0, JSON.stringify(r));
  await nav("http://127.0.0.1:" + PORT + "/outbox");
  await sleep(1500);
  const box = JSON.parse(await ev("JSON.stringify({xss:window.__xss||0,imgs:document.querySelectorAll('img[src=x]').length,svgs:document.querySelectorAll('svg[onload]').length,scripts:[...document.querySelectorAll('script')].filter(s=>/__xss/.test(s.textContent)).length,handlers:[...document.querySelectorAll('*')].filter(e=>e.hasAttribute('onerror')||e.hasAttribute('onload')).length,text:document.body.innerText.indexOf('onerror')>=0})"));
  check("the owner's test inbox page shows the hostile text only as text", box.xss === 0 && box.imgs === 0 && box.svgs === 0 && box.scripts === 0 && box.handlers === 0, JSON.stringify(box));
  check("and the hostile text is visible there as plain words (so it was stored and escaped, not dropped silently)", box.text === true);
  await nav("http://127.0.0.1:" + PORT + "/feedback");
  await sleep(800);
  const fb = JSON.parse(await ev("JSON.stringify({imgs:document.querySelectorAll('img[src=x]').length,handlers:[...document.querySelectorAll('*')].filter(e=>e.hasAttribute('onerror')||e.hasAttribute('onload')).length})"));
  check("the feedback page has nothing injected", fb.imgs === 0 && fb.handlers === 0, JSON.stringify(fb));
  console.log(bad ? bad + " problem(s)" : "All good");
};
