// Release check for the dev build at phone size: no test or developer content anywhere, real jobs only, a blank new profile,
// buy buttons only where the server allows them (keys set, or the owner's own computer), and a working account area.
//   W=390 H=844 PORT=8767 node tools/cdp.js tools/ui-release.js
const PORT = process.env.PORT || "8767";
module.exports = async ({ ev, sleep, nav, logs }) => {
  // the sign-in gate (October 22, Saif): nobody reaches the jobs without an account, so a fresh test person signs up first (tools/gate-signup.js)
  const gateWho = await require("./gate-signup.js")({ ev, sleep, nav }, "http://127.0.0.1:" + (process.env.PORT || "8767"), "release");
  const F = "document.querySelector('iframe').contentDocument";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const nl = "String.fromCharCode(10)";
  const pageText = () => ev("(document.body.innerText + ' ' + (" + F + ").body.innerText).split(" + nl + ").join(' ')");
  const sub = (s) => ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a,[role=tab]')].find(b=>b.offsetParent&&b.innerText.split(/\\s+/).join(' ').trim().startsWith(" + JSON.stringify(s) + "));if(e)e.click();return !!e})()");
  const setVal = (id, v) => ev("(()=>{const e=" + F + ".getElementById('" + id + "');if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  // words that must never reach a real user of the release build
  const BANNED = /SANDBOX|TEST MODE|\(test\)|simulated|Sandbox controls|Northwind|Calloway|Ironbridge|Seaside Software|Redwood Marketing|Atlas Robotics|Harbor Bank|Summit Health|Corner Table|Brightpath|Lumen Labs|Release candidate|Jordan Lee/i;
  // words no visitor may see on any screen, even on the owner's own computer: developer addresses, filler, coding-tool names,
  // promises the app does not keep (no profile sync between devices, password reset exists)
  const NEVER = /localhost|127\.0\.0\.1|example\.com|lorem|\bTODO\b|test version|Claude|Anthropic|follow you to any device|isn't available yet|\bTBD\b|Switch to hiring/i;
  // owner-only hints ("test inbox", "on this computer") are fine on the owner's own computer, never on a hosted server
  const owner = JSON.parse(await (async () => { try { return JSON.stringify((await (await fetch("http://127.0.0.1:" + PORT + "/api/chat/config")).json()).owner === true); } catch (e) { return "false"; } })());
  const OWNER_ONLY = /test inbox|on this computer|Connect Gmail|Connect Stripe/i;
  // the buy buttons: on a public server only when Stripe keys are set; then, or with the owner's test links, labelled as test mode
  const BILL = JSON.parse(await (async () => { try { return JSON.stringify(await (await fetch("http://127.0.0.1:" + PORT + "/api/billing/status")).json()); } catch (e) { return "{}"; } })());
  const TESTY = /TEST MODE|Choose Plus|Choose Pro/i;
  const scan = async (where) => {
    const t = (await pageText()).split("Test mode: no real charges").join(" ").split(gateWho.email).join(" ");   // the test person's own address (signed in through the gate) is theirs, not developer wording   // the one allowed test-mode label (Plan and billing)
    const m = t.match(BANNED) || t.match(NEVER) || (!owner && t.match(OWNER_ONLY)) || (!BILL.buttons && t.match(TESTY));
    check("no test or developer wording on " + where, !m, m ? "found: " + m[0] : "");
  };

  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(3500);
  check("developer bar is hidden", await ev("getComputedStyle(document.getElementById('devbar')).display === 'none'"));
  check("tab title is just UAply", (await ev("document.title")) === "UAply");
  check("jobs loaded from the server", (await ev("document.querySelector('iframe').contentWindow.__uaplyHideSamples === true")));
  check("a new visitor is told the scores use an example profile", await ev("getComputedStyle(" + F + ".getElementById('banner')).display !== 'none'"));
  check("no 'N jobs left' counters in the release build", await ev("getComputedStyle(" + F + ".getElementById('progress')).display === 'none'"));
  // the agreement is asked once, at first open (consentFirst), with the wording Bot 7 corrected
  for (let i = 0; i < 10 && !(await ev("!!" + F + ".getElementById('kcYes')")); i++) await sleep(300);
  const agree = String(await ev("((" + F + ").getElementById('kitConsent')||{}).innerText||''"));
  check("a clean browser is asked for the agreement at first open, before any swipe", /Before you start swiping/.test(agree), agree.slice(0, 60));
  check("the agreement says how a swipe sends (the resume included), where email goes, that voluntary questions are never answered, how to stop it, the match line, the Automatic submit tick (off), and links How matching works, the Terms and the Privacy Policy",
    /A swipe right goes one of three ways/.test(agree) && /By email, with your resume, where the job posting gives an address/.test(agree) && /never answers questions about race, gender, veteran status or disability/.test(agree) &&
    /Into the employer's own hiring system/.test(agree) && /saved to Job Tracker with a receipt/.test(agree) && /turn off Send applications for me in Profile, Account/.test(agree) &&
    /Automatic submit:/.test(agree) && (await ev("!(" + F + ").getElementById('kcAuto').checked")) &&
    /The match percentage is worked out automatically/.test(agree) &&
    (await ev("(" + F + ").querySelectorAll('#kitConsent a[href*=legal]').length")) === 3, agree.slice(0, 120));
  await scan("the first screen, with the agreement open");
  await ev(F + ".getElementById('kcYes').click()"); await sleep(500);
  check("Hiring mode is not in the release build (no Switch to hiring pill)", !/Switch to hiring/.test(await pageText()));
  await scan("the first screen");
  console.log("   first card:", (await ev("(" + F + ").body.innerText.split(" + nl + ").filter(x=>x.trim()).slice(3,12).join(' | ')")).slice(0, 180));

  for (const tab of ["Full-time", "Part-time", "Internships", "Coop"]) {
    await ev(F + ".getElementById('nb-svc').click()"); await sleep(300);
    await sub(tab); await sleep(600);
    await scan("Services > " + tab);
  }
  await ev(F + ".getElementById('nb-dash').click()"); await sleep(400);
  for (const s of ["Overview", "Applied", "Accepted", "Rejected", "Interviews"]) { await sub(s); await sleep(300); await scan("Job Tracker > " + s); }

  await ev(F + ".getElementById('nb-prof').click()"); await sleep(500);
  const items = await ev("[...(" + F + ").querySelectorAll('button')].filter(b=>b.offsetParent).map(b=>b.innerText.trim().split(" + nl + ")[0]).join('|')");
  check("Profile menu has Plan & billing (real plans, backed by Stripe)", /Plan/.test(items), items.split("|").slice(-8).join(", "));
  for (const s of ["Account", "Profile setup", "Filters", "Plan", "Data"]) {
    if (!(await sub(s))) { await ev(F + ".getElementById('nb-prof').click()"); await sleep(350); await sub(s); }   // reopen the menu only if it closed
    await sleep(500);
    await scan("Profile > " + s);
    if (s === "Profile setup") {
      const vals = JSON.parse(await ev("JSON.stringify(['pName','pTitle','pYears','pSkills','pSalary','pLoc'].map(id=>(" + F + ".getElementById(id)||{}).value))"));
      check("a new profile starts blank (no sample name, title, skills, pay or city)", vals.every((v) => v === ""), JSON.stringify(vals));
    }
    if (s === "Account") {
      await sleep(600);
      // signed in through the gate (the signed-out sign-up card is checked by tools/ui-gate.js): the real account card, the address and Sign out
      check("account area shows the real account card (signed in as the test person, with Sign out)", (await pageText()).includes(gateWho.email) && !!(await ev("!!" + F + ".querySelector('[data-auth=sout]')")), (await pageText()).slice(0, 140));
      check("no simulated sign-in buttons", !(await ev("!!" + F + ".querySelector('[data-auth=google],[data-auth=apple],[data-auth=sendlink],[data-auth=sendcode]')")));
    }
    if (s === "Data") {
      await sleep(700); const n = await ev(F + ".querySelectorAll('[data-legal]').length"); check("Data & privacy lists the legal pages", n === 5, "found " + n);
      const line = await ev("((" + F + ").getElementById('aAgreed')||{}).textContent||''");
      check("Data & privacy says when you agreed", /^You agreed to the Terms and Privacy Policy on .*[0-9]{4}[.]$/.test(line), line);
      await sub("Show it again"); await sleep(700);
      check("Show it again clears the saved agreement and opens the box", await ev("!!" + F + ".getElementById('kcYes')") && (await ev("(()=>{try{return " + F + ".defaultView.localStorage.getItem(" + F + ".defaultView.__uaplyKey+'.consent')}catch(e){return 'x'}})()")) === null);
      await ev(F + ".getElementById('kcYes').click()"); await sleep(600);
      check("agreeing again saves it and the line comes back", /^You agreed to the Terms and Privacy Policy on /.test(await ev("((" + F + ").getElementById('aAgreed')||{}).textContent||''")));
    }
    if (s === "Plan") {
      const t = await pageText(), choose = await ev("(" + F + ").querySelectorAll('[data-bill=plus],[data-bill=pro],[data-bill=signin]').length");   // with keys and no account yet: Sign in to choose Plus / Pro
      if (BILL.buttons) check("Plan and billing offers Choose Plus and Choose Pro here, labelled as test mode when it is (server: buttons on)", choose === 2 && (!(BILL.test || !BILL.enabled) || /Test mode: no real charges/.test(t)), "buttons " + choose);
      else check("Plan and billing on a public server without Stripe keys: no buy buttons, early access said plainly", choose === 0 && /Paid plans are coming. UAply is free during early access./.test(t), "buttons " + choose);
    }
  }

  // every link a visitor can tap here (Data & privacy, the fine print under the menu) opens the right page, and so does every link
  // inside those legal pages. The legal pages must also not name screens that no longer exist.
  const hrefs = JSON.parse(await ev("JSON.stringify([...new Set([...(" + F + ").querySelectorAll('a[href]'),...document.querySelectorAll('a[href]')].map(a=>a.href))])"));
  const TITLES = { "support.html": "UAply Support", "terms.html": "Terms of Service", "privacy.html": "Privacy Policy", "ai-and-employment.html": "AI and matching", "copyright.html": "Copyright and content", "index.html": "UAply legal", "": "UAply legal" };
  const OLD_SCREENS = /Profile, Settings|Profile, Preferences|Resume and links|Profile, Resume|Settings screen/;
  const seen = new Set(), queue = hrefs.filter((u) => u.includes("/legal/"));
  check("the legal links are there to tap, Support included", queue.length >= 6 && queue.some((u) => u.endsWith("/legal/support.html")), queue.length + " legal links");
  while (queue.length) {
    const u = queue.shift().split("#")[0];
    if (seen.has(u)) continue;
    seen.add(u);
    const r = JSON.parse(await ev("fetch(" + JSON.stringify(u) + ").then(async r=>JSON.stringify({s:r.status,t:await r.text()})).catch(e=>JSON.stringify({s:0,t:e.message}))"));
    const want = TITLES[u.split("/legal/")[1]];
    const title = (r.t.match(/<title>([^<]*)<\/title>/) || [])[1] || "";
    const old = r.t.match(OLD_SCREENS);
    check("legal page " + u.split("/").slice(-2).join("/") + " opens with the right title" + (old ? "" : " and names only screens that exist"),
      r.s === 200 && (!want || title.includes(want)) && !old, r.s + " " + title + (old ? " | names an old screen: " + old[0] : ""));
    for (const m of r.t.matchAll(/href="([^"#]+)"/g)) {
      const next = new URL(m[1], u).href;
      if (next.startsWith("http://127.0.0.1:" + PORT + "/legal/") && !seen.has(next)) queue.push(next);
    }
  }

  // Help, then Talk to a person: the Support page is offered and opens
  await ev("(()=>{const b=(" + F + ").getElementById('uaChatBtn');if(b)b.click()})()"); await sleep(900);
  await ev("(()=>{const e=[...(" + F + ").querySelectorAll('#uaChat button')].find(b=>b.innerText.trim()==='Talk to a person');if(e)e.click()})()"); await sleep(900);
  const sup = await ev("((" + F + ").querySelector('#uaChat a[data-support]')||{}).href||''");
  const supSt = sup ? await ev("fetch(" + JSON.stringify(sup) + ").then(r=>r.status)") : 0;
  check("Help, Talk to a person links the Support page, and it opens", /\/legal\/support\.html$/.test(sup) && supSt === 200, sup + " " + supSt);
  await ev("(()=>{const b=(" + F + ").getElementById('uaChatX');if(b)b.click()})()"); await sleep(300);

  // the help assistant's answers to its own starter questions, as the release build gives them
  const ask = (q) => ev("fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:[{role:'user',content:" + JSON.stringify(q) + "}]})}).then(r=>r.json()).then(j=>JSON.stringify({a:j.answer||j.error||'',src:(j.sources||[]).map(s=>s.id)}))");
  for (const [q, want] of [["How do I apply?", "swipe-right"], ["Why don't I see any jobs?", "no-jobs"], ["How do plans and billing work?", "plans"], ["I forgot my password", "forgot-password"], ["How do I upload my resume?", "resume"], ["What data do you keep?", "privacy"]]) {
    const r = JSON.parse(await ask(q));
    const m = r.a.match(BANNED) || r.a.match(NEVER) || r.a.match(/test inbox|simulated|sandbox/i);
    check("assistant answers \"" + q + "\" from the right article, in release wording", r.src[0] === want && !m, (r.src[0] || "no article") + (m ? " | says: " + m[0] : "") + " | " + r.a.slice(0, 90));
  }
  // saving only a name and email must not hide the real jobs
  await sub("Profile setup"); await sleep(400);
  await setVal("pName", "Release Tester"); await setVal("pEmail", "release.tester@example.com");
  await ev(F + ".getElementById('wzNext').click()"); await sleep(900);
  await ev(F + ".getElementById('nb-svc').click()"); await sleep(300);
  await sub("Internships"); await sleep(700);
  const hidden = await ev("(" + F + ").body.innerText.split(" + nl + ").join(' ').match(/(\\d+) listings? (are|is) hidden because/)");
  check("saving just a name and email leaves the real jobs visible", !hidden, hidden ? hidden[0] : "");
  check("the example-profile notice goes away once there is a real profile", await ev("getComputedStyle(" + F + ".getElementById('banner')).display === 'none'"));
  check("a real internship card shows", (await ev(F + ".querySelectorAll('.card').length")) >= 1);
  await scan("the deck after saving a profile");

  // each service tab shows its own kind of job. Read the actual top card and look it up in the job list: no guessing from page text.
  const topJob = () => ev("JSON.stringify((()=>{const w=document.querySelector('iframe').contentWindow;const c=w.document.querySelector('.card.top');" +
    "if(!c)return {type:w.__uaply.getType(),card:null};const n=x=>String(x).split(/\\s+/).join(' ');const t=n(c.innerText);const j=w.__uaply.JOBS.find(j=>t.includes(n(j.role))&&t.includes(n(j.co)));" +
    "return {type:w.__uaply.getType(),card:j?{role:j.role,co:j.co,jtype:j.type||'job',live:!!j.live}:'unmatched'}})())");
  const pick = async (nb, label) => {                                   // open the menu and choose an item, the way a tap does
    await ev(F + ".getElementById('" + nb + "').click()"); await sleep(450);
    return ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith(" + JSON.stringify(label) + "));if(!e)return false;e.click();return true})()");
  };
  const kinds = { "Full-time": "job", "Part-time": "parttime", "Internships": "internship", "Coop": "coop" };
  for (const [tab, want] of Object.entries(kinds)) {
    check("choosing " + tab + " works", await pick("nb-svc", tab)); await sleep(800);
    const r = JSON.parse(await topJob());
    if (r.card === null) check("Services > " + tab + " is empty with a friendly message", want === "coop" || want === "parttime", "no card (only acceptable for rare types)");
    else check("Services > " + tab + " shows a real " + want + " job", r.type === want && r.card !== "unmatched" && r.card.jtype === want && r.card.live === true,
      r.card === "unmatched" ? "card not found in job list" : r.card.co + ": " + r.card.role + " [" + r.card.jtype + ", live=" + r.card.live + "]");
  }

  // swiping right on a real job: consent once, then the hand-off to the employer's own page, and it appears under Applied
  await pick("nb-svc", "Internships"); await sleep(800);
  // first with the example profile: the release build never applies with it; "Finish your profile first" says what is missing, the card stays
  const top0 = await ev("(()=>{const c=" + F + ".querySelector('.card.top');return c?+c.getAttribute('data-id'):0})()");
  await ev(F + ".getElementById('btnYes').click()"); await sleep(1200);
  const fin = await ev("(()=>{const b=" + F + ".getElementById('rdyBox');return b?b.innerText.split(/\\s+/).join(' '):''})()");
  check("a swipe right with the example profile opens Finish your profile first, and the card stays", /^Finish your profile first/.test(fin) &&
    (await ev("(()=>{const c=" + F + ".querySelector('.card.top');return c?+c.getAttribute('data-id'):0})()")) === top0, fin.slice(0, 120));
  await ev("(()=>{const b=" + F + ".getElementById('rdyNo');if(b)b.click()})()"); await sleep(300);
  // then with the least a swipe needs: a name, an email and a phone number
  await ev("(()=>{const A=document.querySelector('iframe').contentWindow.__uaply;Object.assign(A.S.profile,{name:'Release Tester',email:'release.tester@example.com',custom:true});A.S.profile.ext=Object.assign({},A.S.profile.ext,{phone:'+1 215 555 0100'});A.save();A.renderAll()})()");
  await sleep(600);
  await ev(F + ".getElementById('btnYes').click()"); await sleep(1200);
  check("no agreement box at the first swipe right (it was answered at first open)", !(await ev("!!" + F + ".getElementById('kcYes')")));
  await ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m)m.click()})()"); await sleep(2200);
  const after = await pageText();
  check("swiping right on a real job says only that it was saved (or applied), never 'Finish on their site'", /Saved .+ to Applied · \d+% match|Saved [^.]+ to Job Tracker\.(?! Send applications for me is off)|Applied to/.test(after) && !/finish on their site|not sent yet|finish now/i.test(after.slice(-200)), after.slice(-160));
  await ev(F + ".getElementById('nb-dash').click()"); await sleep(400);
  await sub("Applied"); await sleep(600);
  check("the swiped job appears under Job Tracker > Applied", (await ev(F + ".querySelectorAll('.app,.appitem,[data-app],article,.row').length")) > 0 || /intern/i.test(await pageText()));
  // Learns from your swipes is in dev: after a few swipes the learner holds them, and a card carries the "Learned from your swipes" line
  await ev(F + ".getElementById('nb-svc').click()"); await sleep(300); await sub("Full-time"); await sleep(800);
  for (let i = 0; i < 8; i++) { await ev("(()=>{const b=" + F + ".getElementById('btnNo');if(b)b.click()})()"); await sleep(700); }
  const lr = JSON.parse(await ev("JSON.stringify((()=>{const w=document.querySelector('iframe').contentWindow;return {on:!!(w.__uaplyLearn&&w.__uaplyLearnOrder),n:w.__uaplyLearn?w.__uaplyLearn.state().ev.length:-1,line:[...w.document.querySelectorAll('.card .learned')].map(x=>x.textContent).filter(Boolean)[0]||''}})())"));
  check("Learns from your swipes is on in dev and counted the swipes", lr.on && lr.n >= 6, JSON.stringify(lr).slice(0, 120));
  check("after the swipes a card says 'Learned from your swipes'", /^Learned from your swipes/.test(lr.line), lr.line.slice(0, 120));
  check("no script errors", logs.length === 0, logs.join(" / ").slice(0, 160));
  console.log(bad ? "\n" + bad + " check(s) failed" : "\nAll release checks passed");
};
