// What the person is told after each swipe right: the toast and the Applied row, on every delivery path. Run it through
// tools/ui-apply-paths.py, which starts the servers, the stand-in hiring system and mail server, and makes the account.
const fs = require("fs");
const SRV = process.env.SRV, PORT = process.env.PORT, ID = JSON.parse(fs.readFileSync(process.env.IDS, "utf8"));
module.exports = async ({ ev, sleep, nav, send, on }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + "[" + SRV + "] " + name + (extra ? "  | " + extra : "")); };
  const say = (k, v) => console.log("   " + k + ": " + v);
  let net = "ok";                                         // "down": UAply's server does not answer (the device itself stays online)
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/apply" }] });
  on("Fetch.requestPaused", (p) => net === "down" && p.request.method === "POST"
    ? send("Fetch.failRequest", { requestId: p.requestId, errorReason: "ConnectionRefused" }) : send("Fetch.continueRequest", { requestId: p.requestId }));
  const base = "http://127.0.0.1:" + PORT + "/";
  const toast = () => ev("(()=>{const t=" + F + ".getElementById('kitToast');return t?t.innerText.replace(/\\s+/g,' ').trim():''})()");
  const decision = (id) => ev("JSON.stringify((" + FW + ".__uaply.S.decisions||{})[" + id + "]||null)").then(JSON.parse);
  const outbox = async () => JSON.parse(await ev("fetch('/api/outbox').then(r=>r.text())")).applications.length;
  async function boot(signedIn, addr) {
    await nav(base); await sleep(3000);
    if (signedIn) {
      const r = await ev("fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'ui@example.com',password:'test pass 12345'})}).then(r=>r.status)");
      check("signed in as ui@example.com", r === 200, "HTTP " + r);
    } else await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.status)");
    // the profile a person fills in, and the first-application agreement already given
    await ev("(()=>{const w=" + FW + ";w.localStorage.setItem((w.__uaplyKey||'uaply')+'.consent',JSON.stringify({v:2,at:Date.now()}));const A=w.__uaply;Object.assign(A.S.profile,{name:'Sam Rivera',email:'" + (addr || "ui@example.com") + "',custom:true,title:'Data Analyst',years:1,skills:['Python','SQL']});A.save()})()");
    await nav(base); await sleep(4500);
    // the resume file uploaded in Profile setup (a tiny real PDF)
    await ev("(()=>{const w=" + FW + ";w.__uaplyResume=function(){return {name:'Sam Rivera Resume.pdf',size:40,data:'data:application/pdf;base64,'+btoa('%PDF-1.4 Sam Rivera resume for tests %%EOF')}}})()");
    check("app loaded", await ev("!!(" + FW + ".__uaply&&" + FW + ".__uaplyOnDecision)"));
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
    await boot(false, "anon.ui@example.com");
    await walk("signed out, email employer", ID["Mail Co|Marketing Intern"], 2500, /Applied to Mail Co \(test\)\. Sign in to get a confirmation email/, /Sent to hr@mailco\.example \(test, nothing reached Mail Co\)/);
    await boot(true);
    await walk("Greenhouse partner", ID["GH Partner|Robotics Intern"], 3000, /Applied to GH Partner \(test\)\. UAply filled in \d+ of \d+ answers\. Confirmation is in the test inbox/, /Sent to GH Partner hiring system \(test, nothing reached GH Partner\)/);
    await walk("public Greenhouse posting in dev (hand-off)", ID["Discord|Data Intern"], 3000, /^Saved Discord to Applied · \d+% match ?Undo$/, /Finish on their site Not sent yet: Discord takes applications on its own site\. See the job posting ↗ Finish applying on their site ↗/);   // quiet swipe (Oct 20): no "finish on their site" message
    // a job saved on this device that the server no longer lists
    await ev(FW + ".__uaplyJobs.add([{id:4242425,live:true,co:'Vanished Co',role:'Gone Intern',loc:'Philadelphia, PA',mode:'onsite',type:'internship',sal:[0,0],yrs:0,edu:'High school',skills:['Python'],blurb:'Gone.',url:'https://boards.greenhouse.io/vanished/jobs/9',source:\"Vanished Co's careers page\"}])");
    await walk("a job no longer in the feed", 4242425, 2500, /^Saved Vanished Co to Applied · \d+% match ?Undo$/, /Finish on their site Not sent yet: Vanished Co takes applications on its own site\. See the job posting ↗ Finish applying on their site ↗/);
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
  if (SRV === "devlive") {
    await boot(false, "anon.ui@example.com");
    const id = ID["Mail Co|Marketing Intern"];
    await walk("live, signed out, employer that takes email", id, 8000, /Sign in first \(Profile, Account\) and verify your email, so Mail Co can trust your address\. Mail Co is back in your deck\.\s*Open Account/, /\(no row\)/);
    check("the job went back to the deck", (await decision(id)) === null);
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
    await walk("live, public Greenhouse posting (hand-off)", ID["Discord|Data Intern"], 4000, /^Saved Discord to Applied · \d+% match ?Undo$/, /Finish on their site Not sent yet: Discord takes applications on its own site\. See the job posting ↗ Finish applying on their site ↗/);
  }
  if (SRV === "sbtest") {
    await boot(true);
    await walk("sandbox, public Greenhouse posting (form filled in, nothing sent)", ID["Discord|Data Intern"], 3000, /Applied to Discord \(test\)\. UAply filled in \d+ of \d+ answers/, /Sent to Discord hiring system \(test, nothing reached Discord\)/);
  }
  console.log(bad ? bad + " problem(s)" : "All good");
};
