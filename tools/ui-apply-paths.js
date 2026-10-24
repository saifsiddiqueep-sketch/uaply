// What the person is told after each swipe right: the toast and the Applied row, on every delivery path. Run it through
// tools/ui-apply-paths.py, which starts the servers, the stand-in hiring system and mail server, and makes the account.
const fs = require("fs");
const SRV = process.env.SRV, PORT = process.env.PORT, ID = JSON.parse(fs.readFileSync(process.env.IDS, "utf8"));
module.exports = async ({ ev, sleep, nav, send, on }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + "[" + SRV + "] " + name + (extra ? "  | " + extra : "")); };
  // a page answer that is not JSON (cdp.js answers "JSERR <message>" when the page's own code threw) is reported as a failure with the
  // page's message, never a crash of this script that hides every check after it
  const J = (s) => { try { return JSON.parse(s); } catch (e) { check("a page answer could be read (the page said: " + String(s).slice(0, 200) + ")", false); return {}; } };
  const say = (k, v) => console.log("   " + k + ": " + v);
  let net = "ok";                                         // "down": UAply's server does not answer (the device itself stays online)
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/apply" }] });
  on("Fetch.requestPaused", (p) => net === "down" && p.request.method === "POST"
    ? send("Fetch.failRequest", { requestId: p.requestId, errorReason: "ConnectionRefused" }) : send("Fetch.continueRequest", { requestId: p.requestId }));
  const base = "http://127.0.0.1:" + PORT + "/";
  const toast = () => ev("(()=>{const t=" + F + ".getElementById('kitToast');return t?t.innerText.replace(/\\s+/g,' ').trim():''})()");
  const decision = (id) => ev("JSON.stringify((" + FW + ".__uaply.S.decisions||{})[" + id + "]||null)").then(J);
  const outbox = async () => (J(await ev("fetch('/api/outbox').then(r=>r.text())")).applications || []).length;
  async function boot(signedIn, addr) {
    await nav(base); await sleep(3000);
    if (signedIn) {
      const r = await ev("fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'ui@example.com',password:'test pass 12345'})}).then(r=>r.status)");
      check("signed in as ui@example.com", r === 200, "HTTP " + r);
    } else await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.status)");
    // the profile a person fills in, and the first-application agreement already given
    await ev("(()=>{const w=" + FW + ";w.localStorage.setItem((w.__uaplyKey||'uaply')+'.consent',JSON.stringify({v:5,at:Date.now(),agent:true,auto:false}));const A=w.__uaply;Object.assign(A.S.profile,{name:'Sam Rivera',email:'" + (addr || "ui@example.com") + "',custom:true,title:'Data Analyst',years:1,skills:['Python','SQL']});A.save()})()");
    await nav(base); await sleep(4500);
    // the resume file uploaded in Profile setup (a tiny real PDF)
    await ev("(()=>{const w=" + FW + ";w.__uaplyResume=function(){return {name:'Sam Rivera Resume.pdf',size:40,data:'data:application/pdf;base64,'+btoa('%PDF-1.4 Sam Rivera resume for tests %%EOF')}}})()");
    check("app loaded", await ev("!!(" + FW + ".__uaply&&" + FW + ".__uaplyOnDecision)"));
  }
  // Profile, Account and its Send applications for me switch
  const openAcct = async () => { await ev("(()=>{const d=" + F + ";d.getElementById('nb-prof').click();const it=d.querySelector('.nwrap[data-k=prof] .nitem[data-v=account]');if(it)it.click()})()"); await sleep(900); };
  const sw = () => ev("(()=>{const b=" + F + ".getElementById('aSendForMe');return b?(b.checked?'on':'off'):'none'})()");
  const note = () => ev("((" + F + ").getElementById('aSendNote')||{}).innerText||''");
  // signed out (the sign-in gate, October 22, Saif: nobody reaches the jobs without an account): no deck to swipe, and an application sent
  // anyway (a page left open from before the gate, or a direct call) is refused by the server with nothing sent
  async function signedOut(label, id) {
    await boot(false, "anon.ui@example.com");
    check(label + ": signed out, the sign-in gate is up (no deck, no job to swipe)", await ev("(()=>{try{const d=" + F + ";return d.body.classList.contains('sgGated')&&!d.querySelector('#deck .card.top')}catch(e){return false}})()"));
    const n0 = await outbox();
    const st = await ev("fetch('/api/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({consent:true,job:{id:" + id + ",co:'Mail Co',role:'Marketing Intern',url:'https://example.com/jobs/mail'},profile:{name:'Sam Rivera',email:'anon.ui@example.com',ext:{phone:'2155550100'}}})}).then(r=>r.json().then(j=>r.status+' '+(j.code||'')))");
    say(label + " | signed-out application", st);
    check(label + ": an application sent anyway is refused (401, sign in first) and nothing reaches the employer", st === "401 signin" && (await outbox()) === n0, st);
  }
  // a swipe right exactly as the deck does it (prod's decide()), on a chosen job
  const swipe = (id) => ev("(()=>{const w=" + FW + ",A=w.__uaply,job=A.JOBS.find(j=>j.id===" + id + ");if(!job)return 'no job';const m=A.evaluate(job,A.S.profile);" +
    "A.S.decisions[job.id]={s:'applied',at:Date.now(),pct:m.pct,as:A.S.profile.name,title:A.S.profile.title};A.S.history.push(job.id);A.save();A.renderAll();" +
    "w.__uaplyOnDecision('applied',job,m,A.S.profile,function(){},A.S,A.save);return 'ok'})()");
  const undoBtn = () => ev("(()=>{const b=" + F + ".getElementById('btnUndo');if(!b)return false;b.click();return true})()");
  const openApplied = async () => {
    await ev("(()=>{const b=" + F + ".getElementById('nb-dash');b.click()})()"); await sleep(400);
    await ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Applied'));if(e)e.click()})()"); await sleep(700);
  };
  async function row(id) {
    await openApplied();
    return ev("(()=>{const b=" + F + ".querySelector('#pane-track [data-id=\"" + id + "\"]');const r=b&&b.closest('.row');return r?r.innerText.replace(/\\s+/g,' ').trim():'(no row)'})()");
  }
  async function walk(label, id, wait, expectToast, expectRow) {
    check(label + ": the job is in the app", (await swipe(id)) === "ok");
    await sleep(wait || 2500);
    const t = await toast(), rw = await row(id);
    say(label + " | toast", t); say(label + " | Applied row", rw);
    if (expectToast) check(label + ": toast", expectToast.test(t), t);
    if (expectRow) check(label + ": Applied row", expectRow.test(rw), rw);
  }

  if (SRV === "devtest") {
    await signedOut("signed out, email employer", ID["Mail Co|Marketing Intern"]);
    await boot(true);
    // the first-swipe agreement (October 23, Reviewer 3): the Automatic submit tick sits right after the four ways, above "By continuing you
    // agree", it is on screen without scrolling at this size, it is off, and its words say no hiring system is switched on yet
    await ev("(()=>{" + FW + ".__uaplyConsentAgain(function(){});return 1})()"); await sleep(1500);
    const box = J(await ev("(()=>{const d=" + F + ",l=d.querySelector('label[for=kcAuto]'),dlg=d.querySelector('#kitConsent [role=dialog]'),ps=[...d.querySelectorAll('#kitConsent p')];" +
      "const by=ps.find(p=>/^By continuing you agree/.test(p.textContent)),ul=d.querySelector('#kitConsent ul');if(!l||!by||!dlg||!ul)return JSON.stringify({missing:true});const r=l.getBoundingClientRect(),dr=dlg.getBoundingClientRect();" +
      "return JSON.stringify({afterList:!!(ul.compareDocumentPosition(l)&Node.DOCUMENT_POSITION_FOLLOWING),aboveBy:!!(l.compareDocumentPosition(by)&Node.DOCUMENT_POSITION_FOLLOWING)," +
      "onScreen:r.top>=0&&r.bottom<=innerHeight,top:dr.top>=0,off:!d.getElementById('kcAuto').checked,words:(d.getElementById('kcAutoT')||{}).textContent||'',bottom:Math.round(r.bottom),h:innerHeight})})()"));
    check("the agreement: the Automatic submit tick sits after the four ways and above 'By continuing you agree'", box.afterList && box.aboveBy, JSON.stringify(box));
    check("...on screen without scrolling (" + box.bottom + " of " + box.h + " px), the box's top in view, and off", box.onScreen && box.top && box.off, JSON.stringify(box));
    check("...and it says where: 'where a hiring system allows it; none is switched on yet' (from assist-systems.json)", /^Automatic submit: where a hiring system allows it; none is switched on yet\./.test(box.words), box.words);
    await ev("(()=>{" + F + ".getElementById('kcYes').click();return 1})()"); await sleep(800);
    await walk("Greenhouse partner", ID["GH Partner|Robotics Intern"], 3000, /Applied to GH Partner \(test\)\. UAply filled in \d+ of \d+ answers\. Confirmation is in the test inbox/, /Sent to GH Partner hiring system \(test, nothing reached GH Partner\)/);
    await walk("public Greenhouse posting in dev (hand-off)", ID["Discord|Data Intern"], 3000, /^Saved [^.]+ to Job Tracker\. ?Undo$/, /Finish on their site Not sent yet: Discord takes applications on its own site\. See the job posting ↗ Finish applying on their site ↗/);   // quiet swipe (Oct 20): no "finish on their site" message
    // a job saved on this device that the server no longer lists
    await ev(FW + ".__uaplyJobs.add([{id:4242425,live:true,co:'Vanished Co',role:'Gone Intern',loc:'Philadelphia, PA',mode:'onsite',type:'internship',sal:[0,0],yrs:0,edu:'High school',skills:['Python'],blurb:'Gone.',url:'https://boards.greenhouse.io/vanished/jobs/9',source:\"Vanished Co's careers page\"}])");
    await walk("a job no longer in the feed", 4242425, 2500, /^Saved [^.]+ to Job Tracker\. ?Undo$/, /Finish on their site Not sent yet: Vanished Co takes applications on its own site\. See the job posting ↗ Finish applying on their site ↗/);
    // a question only the person can answer is asked once, then it goes
    await swipe(ID["GH Partner|Odd Question Role"]); await sleep(2500);
    const ask = await ev("(()=>{const o=" + F + ".getElementById('kitAsk');return o?o.innerText.replace(/\\s+/g,' ').slice(0,200):''})()");
    say("odd question | ask sheet", ask);
    check("a question only the person can answer is asked", /One question from GH Partner/.test(ask), ask);
    await ev("(()=>{const d=" + F + ";const t=d.querySelector('#kitAsk [data-k]');t.value='Blue, it is calm.';d.querySelector('#kitAsk form').dispatchEvent(new Event('submit',{cancelable:true}))})()");
    await sleep(2500);
    const t2 = await toast(), r2 = await row(ID["GH Partner|Odd Question Role"]);
    say("odd question answered | toast", t2); say("odd question answered | row", r2);
    check("after answering, it is sent", /Applied to GH Partner \(test\)/.test(t2) && /Sent to GH Partner hiring system/.test(r2), t2 + " / " + r2);
    // undo after it went, then the same swipe again
    const n0 = await outbox();
    await walk("employer that takes email", ID["Mail Co|Marketing Intern"], 2500, /Applied to Mail Co \(test\)/, /Sent to hr@mailco/);
    check("undo button works", await undoBtn()); await sleep(800);
    const tu = await toast(); say("undo after it went | toast", tu);
    check("undo after the application went says it stays sent", /Removed from your list\. The test application to Mail Co stays in the test inbox/.test(tu), tu);
    check("undo removed it from Applied", (await decision(ID["Mail Co|Marketing Intern"])) === null);
    await walk("same job again after undo (duplicate)", ID["Mail Co|Marketing Intern"], 2500, /Already applied to Mail Co/, /Sent to hr@mailco\.example \(test/);
    check("the second swipe sent nothing new", (await outbox()) === n0 + 1, "outbox grew by " + ((await outbox()) - n0));
    // UAply's server does not answer, then answers again (the device stays online: no "online" event comes)
    net = "down";
    await walk("server down", ID["Link Co|Barista"], 2500, /UAply could not reach its server\. It will send your application to Link Co as soon as it can/, /Waiting to send/);
    net = "ok";
    await sleep(31000);
    const t3 = await toast(), r3 = await row(ID["Link Co|Barista"]);
    say("server back | toast", t3); say("server back | row", r3);
    check("when the server answers again it is sent by itself, without a reload (quietly: the row changes, no new message)", !/Link Co/.test(t3) && /Finish on their site Not sent yet: Link Co takes applications/.test(r3), t3 + " / " + r3);
    // the device goes offline, then online
    await send("Network.enable");
    await send("Network.emulateNetworkConditions", { offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    await walk("device offline", ID["Lever Partner|Support Engineer"], 2500, /You're offline\. UAply will send your application to Lever Partner when you're back online/, /Waiting to send/);
    await send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    await sleep(3000);
    const t4 = await toast(), r4 = await row(ID["Lever Partner|Support Engineer"]);
    say("back online | toast", t4); say("back online | row", r4);
    check("back online: sent at once", /Applied to Lever Partner \(test\)/.test(t4) && /Sent to Lever Partner hiring system/.test(r4), t4 + " / " + r4);
  }
  if (SRV === "devtest") {
    // ---------- one tap, in the phone app (Saif, October 23): a hand-off opens the employer's own form right after the swipe, filled ----------
    // A stand-in for the app's assist plugin (Capacitor.Plugins.UAplyAssist) records each open and answers at once, so this times UAply's
    // own half: from the swipe to the form being asked for, filled (the form's own half is timed in tools/test-assist.js on the mock forms).
    const install = (fillAnswer) => ev("(()=>{window.__calls=[];window.Capacitor={isNativePlatform:()=>true,getPlatform:()=>'android',Plugins:{UAplyAssist:{open:function(o){" +
      "window.__calls.push({at:Date.now(),scan:!!o.scan,url:o.url,mode:o.mode,allow:o.allow,profile:Object.keys(o.profile||{}),engine:/UAplyAssist/.test(o.engine||'')});" +
      "return Promise.resolve(o.scan?{questions:[],seen:10,filled:8,keys:['name','email','phone'],answerKeys:[],resume:true}:" + JSON.stringify(fillAnswer) + ")}}}};return 1})()");
    const oneId = ID["Discord|Data Intern Two"];
    await install({ confirmed: false, url: "" });
    // every message the app shows, in order (the form opening answers at once here, so its own message follows the swipe's right away)
    await ev("(()=>{const d=" + F + ";window.__toasts=[];new MutationObserver(()=>{const t=d.getElementById('kitToast');const x=t?t.innerText.replace(/\\s+/g,' ').trim():'';if(x&&window.__toasts[window.__toasts.length-1]!==x)window.__toasts.push(x)}).observe(d.body,{childList:true,subtree:true,characterData:true});return 1})()");
    await ev("window.__t0=Date.now();1");
    check("one tap: the hand-off is in the app", (await swipe(oneId)) === "ok");
    for (let i = 0; i < 40 && (await ev("window.__calls.length")) < 2; i++) await sleep(100);
    const calls = J(await ev("JSON.stringify(window.__calls)")), t0 = await ev("window.__t0");
    const ms = calls.length >= 2 ? calls[1].at - t0 : -1;
    console.log("ONE-TAP-CLIENT " + JSON.stringify({ ms: ms, scanAsked: calls[0] ? calls[0].at - t0 : -1 }));
    check("one tap: right after the swipe the app reads the employer's form, then opens it filled (two opens: the scan, then the form)",
      calls.length === 2 && calls[0].scan === true && calls[1].scan === false && calls.every((c) => c.engine), JSON.stringify(calls).slice(0, 300));
    check("...the employer's own form address, with UAply's source tag, and only the hiring systems' hosts allowed",
      calls[1] && /^https:\/\/boards\.greenhouse\.io\/discord\/jobs\/1002\?gh_src=uaply$/.test(calls[1].url) && calls[1].allow.includes("boards.greenhouse.io") && calls[1].allow.every((h) => /greenhouse|lever|ashby|smartrecruiters|workable/.test(h)),
      calls[1] && calls[1].url + " " + calls[1].allow);
    check("...in assisted mode: the person taps Submit (no system is approved for automatic submit)", calls[1] && calls[1].mode === "assisted", calls[1] && calls[1].mode);
    const shown = J(await ev("JSON.stringify(window.__toasts||[])"));
    check("...and the swipe's message promises one tap only because the form did open: 'Saved to Job Tracker. One tap to finish on their site.'",
      Array.isArray(shown) && shown.some((x) => /^Saved to Job Tracker\. One tap to finish on their site\. ?Undo$/.test(x)), JSON.stringify(shown));
    check("...and UAply's half takes " + ms + " ms from the swipe (target well under the 3 s for the whole)", ms >= 0 && ms < 1500, ms + " ms");
    await sleep(800);
    const tb = await toast(), rb = await row(oneId);
    say("one tap, backed out | toast", tb); say("one tap, backed out | row", rb);
    check("one tap: backing out keeps Finish on their site", /Not sent yet\. Tap Finish applying when you are ready/.test(tb) && /Finish on their site/.test(rb), tb + " / " + rb);
    // the person finishes from Job Tracker: Sent only on the employer's confirmation page
    await install({ confirmed: true, url: "https://boards.greenhouse.io/discord/jobs/1002/confirmation" });
    check("one tap: Finish applying opens it again", await ev("(()=>{const b=" + F + ".querySelector('[data-finish=\"" + oneId + "\"]');if(!b)return false;b.click();return true})()"));
    await sleep(1500);
    const rs = await row(oneId);
    say("one tap, confirmed | row", rs);
    check("...and the employer's confirmation page makes it Sent", /Sent/.test(rs) && !/Finish on their site/.test(rs), rs);
    // Automatic submit needs the person's own tick on record, even on a hiring system the owner switched to automatic with counsel's
    // approval (Reviewer 3, October 23: dropping autoConsent() from the rule went unnoticed). The system list is answered here as
    // if Greenhouse were approved; without the tick the form opens assisted, with it automatic.
    await ev("(()=>{const w=" + F + ".defaultView,of=w.fetch.bind(w);w.__r3fetch=of;w.fetch=function(u,o){if(String(u).indexOf('/assist-systems.json')>=0)return Promise.resolve(new Response(JSON.stringify({systems:{greenhouse:{mode:'automatic',counsel_approved:true,human_check_share:0,hosts:['boards.greenhouse.io','job-boards.greenhouse.io']}}}),{headers:{'Content-Type':'application/json'}}));return of(u,o)};return 1})()");
    const modeWith = async (tick) => {
      await install({ confirmed: false, url: "" });
      await ev("(()=>{const w=" + F + ".defaultView;w.__uaplyConsentRec={v:w.__uaplyConsentV,auto:" + tick + "};const j=w.__uaply.JOBS.find(x=>x.id===" + oneId + ");return w.__uaplyOneTap(j)})()");
      for (let i = 0; i < 40 && (await ev("window.__calls.length")) < 2; i++) await sleep(100);
      const c = J(await ev("JSON.stringify(window.__calls)"));
      return c[1] ? c[1].mode : "(no form opened)";
    };
    const mNo = await modeWith(false);
    check("an approved system without the person's Automatic submit tick: the form opens assisted", mNo === "assisted", mNo);
    await sleep(800);
    const mYes = await modeWith(true);
    check("...and with the tick on record: automatic", mYes === "automatic", mYes);
    await ev("(()=>{const w=" + F + ".defaultView;if(w.__r3fetch)w.fetch=w.__r3fetch;delete w.__uaplyConsentRec;return 1})()");
    await sleep(800);
    // Send applications for me off (Profile, Account): a swipe right only saves the job; no employer's form opens by itself
    await openAcct();
    await ev("(()=>{" + F + ".getElementById('aSendForMe').click()})()"); await sleep(1500);
    check("one tap: Send applications for me turned off in Profile, Account", (await sw()) === "off", await note());
    await install({ confirmed: false, url: "" });
    const offId = ID["Discord|Data Intern Three"];
    check("one tap, switch off: the hand-off is in the app", (await swipe(offId)) === "ok");
    await sleep(2500);
    const offCalls = J(await ev("JSON.stringify(window.__calls)")), offToast = await toast();
    say("one tap, switch off | toast", offToast);
    check("...no employer's form opens, and the message says it was only saved", offCalls.length === 0 && /^Saved Discord to Job Tracker\. Send applications for me is off \(Profile, Account\), so nothing was sent\. ?Undo$/.test(offToast),
      offCalls.length + " opens | " + offToast);
    await openAcct();
    await ev("(()=>{" + F + ".getElementById('aSendForMe').click()})()"); await sleep(1500);
    check("...and turned on again", (await sw()) === "on", await note());
    await ev("(()=>{delete window.Capacitor;return 1})()");
  }
  if (SRV === "devlive") {
    const id = ID["Mail Co|Marketing Intern"];
    await signedOut("live, signed out, employer that takes email", id);
    await boot(true);
    const n0 = await outbox();
    await swipe(id); await sleep(1500);
    say("countdown | toast", await toast());
    await undoBtn(); await sleep(2500);
    const tc = await toast(); say("Undo button during the countdown | toast", tc);
    check("the Undo button during the countdown cancels and says so (no toast left counting)", /Cancelled\. Nothing was sent to Mail Co/.test(tc), tc);
    await sleep(5000);
    check("nothing was sent", (await outbox()) === n0, "outbox " + n0 + " -> " + (await outbox()));
    await walk("live, verified, employer that takes email", id, 8500, /Applied to Mail Co\. Confirmation emailed to ui@example\.com/, /Application sent to hr@mailco\.example/);
    await undoBtn(); await sleep(800);
    const tu = await toast(); say("undo after it was sent | toast", tu);
    check("undo after it was sent says the employer still has it", /Your application to Mail Co was already sent, so Mail Co still has it/.test(tu), tu);
    await walk("live, same job again after undo", id, 8500, /Already applied to Mail Co/, /Application sent to hr@mailco\.example/);
    const broken = ID["Dropbox|Broken System Intern"];
    await walk("live, the employer's hiring system fails", broken, 9000, /could not be sent/, /Not sent: UAply could not deliver it to Dropbox\. Try again/);
    await openApplied();
    check("Try again in the Applied row starts a new send", await ev("(()=>{const b=" + F + ".querySelector('#pane-track [data-act=resend][data-id=\"" + broken + "\"]');if(!b)return false;b.click();return true})()"));
    await sleep(1500);
    const tr = await toast(); say("Try again | toast", tr);
    check("...with the usual countdown", /Applying to Dropbox in/.test(tr), tr);
    await sleep(8000);
    check("...and when it fails again, the row still says not sent", /Not sent: UAply could not deliver it to Dropbox/.test(await row(broken)));
    await walk("live, Greenhouse partner", ID["GH Partner|Robotics Intern"], 9000, /Applied to GH Partner\. UAply filled in/, /Application sent to GH Partner/);
    await walk("live, public Greenhouse posting (hand-off)", ID["Discord|Data Intern"], 4000, /^Saved [^.]+ to Job Tracker\. ?Undo$/, /Finish on their site Not sent yet: Discord takes applications on its own site\. See the job posting ↗ Finish applying on their site ↗/);
  }
  if (SRV === "devlive") {
    // ---------- Send applications for me (Profile, Account; Terms section 3): off, a swipe right only saves the job ----------
    await openAcct();
    check("Profile, Account has the Send applications for me switch, and it is on", (await sw()) === "on", await sw());
    await ev("(()=>{" + F + ".getElementById('aSendForMe').click()})()"); await sleep(1500);
    check("...turned off, it says swipes right only save the job", (await sw()) === "off" && /^Off: swipes right only save the job to Job Tracker/.test(await note()), await note());
    const me = J(await ev("fetch('/api/auth/me').then(r=>r.text())"));
    check("...and the account keeps it (the server will honor it on every device)", me.user && me.user.sendForMe === false, JSON.stringify(me.user && me.user.sendForMe));
    const lv = ID["Lever Partner|Support Engineer"];
    await walk("live, Send applications for me off, an employer connected through Lever", lv, 4000, /^Saved Lever Partner to Job Tracker\. Send applications for me is off \(Profile, Account\), so nothing was sent\. ?Undo$/, /Finish on their site/);
    const last = (J(await ev("fetch('/api/outbox').then(r=>r.text())")).applications || [])[0] || {};
    check("...the server only saved it: a hand-off, nothing sent to Lever Partner", last.status === "handoff" && last.job && last.job.id === lv, JSON.stringify({ status: last.status, to: last.to }));
    const mc = ID["Mail Co|Sales Intern"];
    await walk("live, Send applications for me off, the employer that takes email", mc, 4000, /^Saved Mail Co to Job Tracker\. Send applications for me is off \(Profile, Account\), so nothing was sent\. ?Undo$/, /Finish on their site/);
    const last2 = (J(await ev("fetch('/api/outbox').then(r=>r.text())")).applications || [])[0] || {};
    check("...nothing emailed to Mail Co: only saved", last2.status === "handoff" && last2.job && last2.job.id === mc && !last2.to, JSON.stringify({ status: last2.status, to: last2.to }));
    await openAcct();
    await ev("(()=>{" + F + ".getElementById('aSendForMe').click()})()"); await sleep(1500);
    check("turned on again, it says a swipe right sends the application", (await sw()) === "on" && /^On: a swipe right sends your application wherever UAply can/.test(await note()), await note());
  }
  if (SRV === "sbtest") {
    await boot(true);
    // a public posting the sandbox fills in to show what UAply would send (October 23): nothing is sent, so it is a hand-off, said as one,
    // and Job Tracker says Saved, never Applied or Sent
    await walk("sandbox, public Greenhouse posting (form filled in for the test inbox, nothing sent)", ID["Discord|Data Intern"], 3000,
      /^Saved [^.]+ to Job Tracker\. ?Undo$/, /Saved [A-Z][a-z]{2} \d{1,2} Finish on their site Not sent yet: Discord takes applications on its own site/);
    const pv = (J(await ev("fetch('/api/outbox').then(r=>r.text())")).applications || [])[0] || {};
    check("...the test inbox has the filled-in form, marked as a preview (what UAply would send once Discord connects)", pv.preview === true && pv.status === "delivered_test", JSON.stringify({ status: pv.status, preview: pv.preview }));
    await openAcct();
    await ev("(()=>{" + F + ".getElementById('aSendForMe').click()})()"); await sleep(1500);
    check("sandbox: Send applications for me turned off", (await sw()) === "off", await note());
    await walk("sandbox, switch off, a public posting", ID["Discord|Data Intern Two"], 3000, /^Saved Discord to Job Tracker\. Send applications for me is off \(Profile, Account\), so nothing was sent\. ?Undo$/, /Finish on their site/);
    const pv2 = (J(await ev("fetch('/api/outbox').then(r=>r.text())")).applications || [])[0] || {};
    check("...not even the test inbox's filled-in form: only saved", pv2.status === "handoff" && !pv2.preview, JSON.stringify({ status: pv2.status, preview: pv2.preview }));
    await openAcct();
    await ev("(()=>{" + F + ".getElementById('aSendForMe').click()})()"); await sleep(1500);
  }
  console.log(bad ? bad + " problem(s)" : "All good");
};
