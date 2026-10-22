// Every way of swiping on the release build at iPhone size, and what each one sends. Run against a clean dev server:
//   W=390 H=844 PORT=8767 node tools/cdp.js tools/ui-swipes.js
const PORT = process.env.PORT || "8767";
module.exports = async ({ ev, sleep, nav, send, logs }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const FW = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const NL = "String.fromCharCode(10)";
  const topKey = () => ev("(()=>{const c=" + F + ".querySelector('.card.top');if(!c)return '(none)';return c.innerText.split(" + NL + ").filter(x=>x.trim()&&x!=='APPLY'&&x!=='PASS').slice(0,3).join(' | ')})()");
  const decisions = () => ev("JSON.stringify(Object.values(" + FW + ".__uaply.S.decisions||{}).reduce((a,d)=>{a[d.s]=(a[d.s]||0)+1;return a},{}))").then(JSON.parse);
  const click = (id) => ev("(()=>{const b=" + F + ".getElementById('" + id + "');if(!b||b.disabled)return false;b.click();return true})()");
  const key = (k) => ev(F + ".dispatchEvent(new KeyboardEvent('keydown',{key:'" + k + "',bubbles:true}))");
  const agree = async () => { await sleep(900); return ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m){m.click();return true}return false})()"); };
  const setVal = (id, v) => ev("(()=>{const e=" + F + ".getElementById('" + id + "');if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  const pick = async (nb, label) => { await ev(F + ".getElementById('" + nb + "').click()"); await sleep(450); return ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith(" + JSON.stringify(label) + "));if(!e)return false;e.click();return true})()"); };
  const reqs = () => ev("JSON.stringify((window.__reqs||[]).concat(" + FW + ".__reqs||[]))").then(JSON.parse);

  // a finger drag across the top card
  const drag = async (dx) => {
    const r = JSON.parse(await ev("JSON.stringify((()=>{const c=" + F + ".querySelector('.card.top');const f=document.querySelector('iframe').getBoundingClientRect();const b=c.getBoundingClientRect();return {x:f.left+b.left+b.width/2,y:f.top+b.top+b.height/3}})())"));
    const pt = (x) => [{ x: Math.round(x), y: Math.round(r.y), id: 1 }];
    await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pt(r.x) });
    for (let i = 1; i <= 8; i++) { await send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: pt(r.x + (dx * i) / 8) }); await sleep(30); }
    await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await sleep(900);
  };

  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(3500);
  await ev("(()=>{window.__reqs=[];const f=window.fetch;window.fetch=function(u,o){try{if(/api[/](apply|decision)/.test(String(u)))window.__reqs.push({u:String(u),b:o&&o.body?String(o.body):''})}catch(e){}return f.apply(this,arguments)}})()");
  await ev("(()=>{window.__reqs=window.__reqs||[]; const w=" + FW + "; w.__reqs=[]; const f=w.fetch; w.fetch=function(u,o){try{if(/api[/](apply|decision)/.test(String(u)))w.__reqs.push({u:String(u),b:o&&o.body?String(o.body):''})}catch(e){}return f.apply(this,arguments)}})()");

  // the profile a person would fill in, in Profile setup: name, email and phone (step 1, About you), then LinkedIn, portfolio and a
  // resume file (step 4, Background and links). When the Application profile asks the same question, its box is the one shown.
  const shown = (a, b) => ev("(()=>{const e=" + F + ".getElementById('" + a + "');return e&&!e.closest('.px-dup')?'" + a + "':'" + b + "'})()");
  const step = async (i) => { await ev("(()=>{const b=" + F + ".querySelector('.wzDots button[data-step=\"" + i + "\"]');if(b)b.click()})()"); await sleep(600); };
  const saveStep = async () => { await ev("(()=>{const b=" + F + ".getElementById('wzNext');if(b)b.click()})()"); await sleep(900); };
  check("Profile setup opens", await pick("nb-prof", "Profile setup")); await sleep(600);
  await setVal("pName", "Sam Rivera"); await setVal("pEmail", "sam.swipes@example.com");
  await setVal(await shown("px-phone", "pPhone"), "+1 215 555 0100");
  await saveStep();
  await step(3);
  check("Background and links opens", /Background and links/.test(await ev("(" + F + ").body.innerText")));
  const li = await shown("px-linkedin", "aLinked"), site = await shown("px-portfolio", "aSite");
  check("LinkedIn field is there", !!(await ev("!!" + F + ".getElementById('" + li + "')")), li);
  // the Application profile's boxes ask for full links (they say "Use a full link that starts with https://" otherwise)
  await setVal(li, li === "aLinked" ? "linkedin.com/in/sam-rivera" : "https://www.linkedin.com/in/sam-rivera");
  await setVal(site, site === "aSite" ? "samrivera.dev" : "https://samrivera.dev");
  check("the step says these details are sent with applications", /Sent with your applications/.test(await ev("(" + F + ").body.innerText")));
  check("the resume file upload is on this step", !!(await ev("(()=>{const i=" + F + ".getElementById('pResFile');return !!(i&&i.closest('.field')&&getComputedStyle(i.closest('.field')).display!=='none')})()")));
  await ev("(()=>{const w=" + FW + ";const i=" + F + ".getElementById('pResFile');const dt=new w.DataTransfer();const bytes=new w.Uint8Array([37,80,68,70,45,49,46,52,10,37,226,227,207,211,10,115,97,109,10,37,37,69,79,70,10]);dt.items.add(new w.File([bytes],'Sam-Rivera-Resume.pdf',{type:'application/pdf'}));i.files=dt.files;i.dispatchEvent(new w.Event('change',{bubbles:true}))})()");
  await sleep(1500);
  await saveStep();
  check("the resume file is held by the app", !!(await ev("!!(" + FW + ".__uaplyResume&&" + FW + ".__uaplyResume())")));
  await pick("nb-svc", "Full-time"); await sleep(900);

  // 1. Pass with the button
  const k0 = await topKey();
  check("there is a card to swipe", k0 !== "(none)", k0.slice(0, 60));
  await click("btnNo"); await sleep(900);
  const k1 = await topKey();
  check("Pass (button) moves to the next job", k1 !== k0 && k1 !== "(none)");
  check("the pass is recorded", (await decisions()).passed === 1, JSON.stringify(await decisions()));

  // 2. Undo
  await click("btnUndo"); await sleep(900);
  check("Undo brings the same job back", (await topKey()) === k0);
  check("Undo removes the record", !(await decisions()).passed, JSON.stringify(await decisions()));

  // 3. Apply with the button: consent once, then the request carries the profile, LinkedIn and the resume file
  await click("btnYes");
  check("the first Apply asks for consent once", await agree());
  await sleep(2500);
  const k2 = await topKey();
  check("Apply (button) moves to the next job", k2 !== k0 && k2 !== "(none)");
  const applyReq = (await reqs()).filter((r) => /api[/]apply/.test(r.u)).pop();
  const body = applyReq ? JSON.parse(applyReq.b) : { profile: { ext: {} }, job: {} };
  check("the application request was sent", !!applyReq);
  check("it carries the name and email", body.profile.name === "Sam Rivera" && body.profile.email === "sam.swipes@example.com");
  check("it carries LinkedIn (cleaned to a full https link)", body.profile.ext.linkedin === "https://linkedin.com/in/sam-rivera" || body.profile.ext.linkedin === "https://www.linkedin.com/in/sam-rivera", String(body.profile.ext.linkedin));
  check("it carries the portfolio and phone", String(body.profile.ext.portfolio).startsWith("https://samrivera.dev") && body.profile.ext.phone === "+1 215 555 0100", String(body.profile.ext.portfolio) + " / " + body.profile.ext.phone);
  check("it carries the resume file", !!(body.resume && body.resume.name === "Sam-Rivera-Resume.pdf" && /^data:application[/]pdf;base64,/.test(body.resume.data)));
  check("it carries the job details", !!(body.job.co && body.job.role && body.job.type && body.job.url));
  check("the apply is recorded", (await decisions()).applied === 1, JSON.stringify(await decisions()));

  // 4. keyboard
  const k3 = await topKey();
  await key("ArrowLeft"); await sleep(900);
  check("ArrowLeft passes", (await topKey()) !== k3 && (await decisions()).passed === 1, JSON.stringify(await decisions()));
  await key("z"); await sleep(900);
  check("Z undoes", (await topKey()) === k3 && !(await decisions()).passed, JSON.stringify(await decisions()));
  await key("ArrowRight"); await sleep(2500);
  check("ArrowRight applies", (await decisions()).applied === 2, JSON.stringify(await decisions()));

  // 5. finger drag, both directions
  const k4 = await topKey();
  await drag(-220);
  check("dragging the card left passes it", (await topKey()) !== k4 && (await decisions()).passed === 1, JSON.stringify(await decisions()));
  const k5 = await topKey();
  await drag(220); await sleep(2500);
  check("dragging the card right applies", (await topKey()) !== k5 && (await decisions()).applied === 3, JSON.stringify(await decisions()));
  const k6 = await topKey();
  await drag(40); await sleep(500);
  check("a short drag does nothing (the card springs back)", (await topKey()) === k6);

  // 6. two quick taps on Apply apply once
  const before = (await decisions()).applied;
  await ev("(()=>{const b=" + F + ".getElementById('btnYes');b.click();b.click()})()"); await sleep(3000);
  check("a double tap on Apply counts once", (await decisions()).applied === before + 1, JSON.stringify(await decisions()));

  // 7. the server saw one application per applied job, and passes were never sent as applications
  const all = (await reqs()).filter((r) => /api[/]apply/.test(r.u));
  const ids = all.map((r) => JSON.parse(r.b).job.id);
  check("no job was sent twice", new Set(ids).size === ids.length, ids.length + " requests");

  // 8. Job Tracker and a reload keep everything
  await pick("nb-dash", "Applied"); await sleep(700);
  const appliedShown = await ev("(" + F + ").querySelectorAll('#pane-track .app, #pane-track article, #pane-track li, #pane-track .row').length");
  check("the Applied list shows the jobs applied to", appliedShown >= 4, appliedShown + " rows");
  const dec = await decisions();
  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(3500);
  check("choices survive a reload", JSON.stringify(await decisions()) === JSON.stringify(dec), JSON.stringify(await decisions()));
  check("a passed or applied job does not come back after a reload", (await topKey()) !== k0);
  // 9. a signed-in account gets a confirmation for each swipe right, kept in the test inbox here (no real email is connected). Since the
  //    quiet swipe (Oct 21) a swipe right on a job that takes applications on its own site says only "Saved <company> to Applied · N%
  //    match" (tools/ui-apply-paths.js and ui-walk.js check that wording), so the confirmation is checked where it lands: the test inbox.
  //    The address is new on every run, so a second run on the same server is not an "already has an account" sign-up.
  const who = "sam.swipes." + Date.now() + "@example.com";
  await ev("fetch('/api/auth/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'" + who + "',password:'correct horse 99',agree:true})}).then(r=>r.status)");
  const inboxFor = (co) => ev("fetch('/outbox').then(r=>r.text()).then(t=>t.split(" + JSON.stringify(co) + ").length-1)");
  const swipeAndInbox = async () => {
    await nav("http://127.0.0.1:" + PORT + "/"); await sleep(3500);
    const co = await ev("(()=>{const w=" + FW + ",c=w.document.querySelector('.card.top'),id=c?+c.getAttribute('data-id'):0,j=w.__uaply.JOBS.find(x=>x.id===id);return j?j.co:''})()");   // the card Apply acts on
    const n0 = await inboxFor(co);
    await click("btnYes");
    // the swipe goes out after its few seconds of Undo time and its message comes with the server's answer: wait for both, up to 20 s
    let n1 = n0, text = "";
    for (let i = 0; i < 40; i++) {
      await sleep(500);
      if (n1 <= n0) n1 = await inboxFor(co);
      if (!/Saved .+ to Applied · \d+% match|Applied to /.test(text)) text = await ev("(" + F + ").body.innerText.split(" + NL + ").join(' ')");
      if (n1 > n0 && /Saved .+ to Applied · \d+% match|Applied to /.test(text)) break;
    }
    return { co, before: n0, after: n1, text };
  };
  const u = await swipeAndInbox();
  // with no real email connected (this test), nothing leaves the server, so even an unverified account's confirmation is kept in the test inbox;
  // with real email connected, an unverified account is told to verify first (covered by test-verify.py)
  check("signed in but not verified: the swipe right is saved, and its confirmation is kept in the test inbox",
    /Saved .+ to Applied · \d+% match|Applied to /.test(u.text) && u.after > u.before, JSON.stringify({ co: u.co, before: u.before, after: u.after }) + " " + u.text.slice(-120));
  // this account's own code (the test inbox lists every account's mail): the subject is "123456 is your UAply verification code to <address>"
  const code = await ev("fetch('/outbox').then(r=>r.text()).then(t=>{t=t.replace(/<[^>]+>/g,' ').replace(/\\s+/g,' ');const m=t.match(new RegExp('([0-9]{6}) is your UAply verification code to '+" + JSON.stringify(who.replace(/\./g, "\\.")) + "));return m?m[1]:''})");
  check("the verification code is in the test inbox", /^[0-9]{6}$/.test(code), code);
  check("the code verifies the account", (await ev("fetch('/api/auth/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:'" + code + "'})}).then(r=>r.status)")) === 200);
  const v = await swipeAndInbox();
  check("verified: the swipe right is saved, and its confirmation is in the test inbox", /Saved .+ to Applied · \d+% match|Applied to /.test(v.text) && v.after > v.before,
    JSON.stringify({ co: v.co, before: v.before, after: v.after }) + " " + v.text.slice(-120));
  check("the test inbox page opens and lists the confirmation", /Sam Rivera|sam.swipes@example.com/.test(await ev("fetch('/outbox').then(r=>r.text())")));
  check("no script errors during any of it", logs.length === 0, logs.join(" / ").slice(0, 160));
  console.log(bad ? "\n" + bad + " check(s) failed" : "\nAll swipe checks passed");
};
