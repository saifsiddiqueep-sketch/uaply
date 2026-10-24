// One complete application on the sandbox, signed in as a real address, to an employer that receives applications by email
// (the owner's own "UAply Test Employer"). Signs up, verifies with the emailed code, fills the profile, swipes right, then shows
// what the employer received and the confirmation the applicant received (test inbox, or real email once email sending is connected).
//   OUT=<folder> EMAIL=<applicant address> NAME="<full name>" W=390 H=844 PORT=8766 node tools/cdp.js tools/shot-real-apply.js
// The account password is generated here and written only to data/<instance>/test-account.txt (git-ignored); it is never printed.
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const PORT = process.env.PORT || "8766";
module.exports = async ({ ev, sleep, nav, shot, logs }) => {
  const OUT = process.env.OUT, EMAIL = process.env.EMAIL, NAME = process.env.NAME || "UAply Tester";
  fs.mkdirSync(OUT, { recursive: true });
  const F = "document.querySelector('iframe').contentDocument";
  const FW = "document.querySelector('iframe').contentWindow";
  const setVal = (id, v) => ev("(()=>{const e=" + F + ".getElementById('" + id + "');if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  const pick = async (nb, label) => { await ev(F + ".getElementById('" + nb + "').click()"); await sleep(450); return ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith(" + JSON.stringify(label) + "));if(!e)return false;e.click();return true})()"); };
  const text = () => ev("(" + F + ").body.innerText");
  const snap = async (name) => { await shot(path.join(OUT, name + ".png")); console.log("shot", name); };
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };

  await nav("http://127.0.0.1:" + PORT + "/"); await sleep(4500);
  await ev("(()=>{const b=document.getElementById('fold');if(b&&b.getAttribute('aria-expanded')==='true')b.click()})()");

  // 1. an account with the real address, verified with the 6-digit code
  const store = path.join(__dirname, "..", "data", "sandbox"), saved = path.join(store, "test-account.txt");
  fs.mkdirSync(store, { recursive: true });
  let pw = "";
  try { const t = fs.readFileSync(saved, "utf8"); if (t.includes("email: " + EMAIL + "\n")) pw = (t.match(/password: (\S+)/) || [])[1] || ""; } catch (e) {}
  const existing = !!pw;
  if (existing) {                                       // made by an earlier run: sign in with the saved test password
    const st = await ev("fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:" + JSON.stringify(EMAIL) + ",password:" + JSON.stringify(pw) + "})}).then(r=>r.status)");
    console.log("   signed in to the existing test account:", st === 200 ? "yes" : "no (" + st + ")");
    await nav("http://127.0.0.1:" + PORT + "/"); await sleep(4500);
    await ev("(()=>{const b=document.getElementById('fold');if(b&&b.getAttribute('aria-expanded')==='true')b.click()})()");
  } else {
    pw = "uaply-test-" + crypto.randomBytes(9).toString("base64url");
    fs.writeFileSync(saved, "Sandbox test account (this computer only)\nemail: " + EMAIL + "\npassword: " + pw + "\n");
    await pick("nb-prof", "Account"); await sleep(700);
    await setVal("sEmail", EMAIL); await setVal("sPw", pw); await setVal("sPw2", pw);
    await ev("(()=>{const c=" + F + ".getElementById('sAgree');if(c)c.checked=true})()");
    await ev(F + ".querySelector('[data-auth=ssubmit]').click()"); await sleep(3000);
    const signed = await text();
    const code = await ev("fetch('/outbox').then(r=>r.text()).then(t=>{const m=t.match(/([0-9]{6}) is your UAply (?:verification|sign-in) code/);return m?m[1]:''})");
    check("the verification code was delivered (test inbox, or the real inbox when email is connected)", /^[0-9]{6}$/.test(code) || /sent/i.test(signed), code ? "code found in the test inbox" : "");
    if (code) { await setVal("sCode", code); await ev(F + ".querySelector('[data-auth=sverify]').click()"); await sleep(2000); }
  }
  const me = await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>JSON.stringify(j.user&&{email:j.user.email,verified:j.user.emailVerified}))");
  check("signed in and verified as " + EMAIL, me.includes('"verified":true') && me.toLowerCase().includes(EMAIL.toLowerCase()), me);
  await snap("real-1-signed-in-verified");

  // 2. the profile an employer sees
  await pick("nb-prof", "Settings"); await sleep(600);
  await setVal("pName", NAME); await setVal("pEmail", EMAIL); await setVal("pLoc", "Philadelphia, PA");
  for (const [k, v] of [["school", "Drexel University"], ["major", "Computer Science"], ["grad", "2027-06"],
                        ["summary", "Test applicant created by UAply to check that a swipe right reaches the employer and the applicant gets a confirmation."]]) await setVal("px-" + k, v);
  await ev(F + ".getElementById('saveBtn').click()"); await sleep(900);
  await pick("nb-prof", "Preferences"); await sleep(700);
  await ev("(()=>{const w=" + FW + ";const i=" + F + ".getElementById('pResFile');const dt=new w.DataTransfer();const bytes=new w.Uint8Array([37,80,68,70,45,49,46,52,10,37,226,227,207,211,10,85,65,112,108,121,10,37,37,69,79,70,10]);dt.items.add(new w.File([bytes],'UAply-Test-Resume.pdf',{type:'application/pdf'}));i.files=dt.files;i.dispatchEvent(new w.Event('change',{bubbles:true}))})()");
  await sleep(1000);
  for (const [k, v] of [["auth", "citizen"], ["sponsor", "no"], ["start", "grad"]]) await setVal("px-" + k, v);
  await ev(F + ".getElementById('saveBtn').click()"); await sleep(900);

  // 3. only the jobs that really send: the test employer receives applications by email
  await pick("nb-prof", "Filters"); await sleep(700);
  await ev("(()=>{const c=" + F + ".getElementById('fInstant');if(c&&!c.checked)c.click()})()"); await sleep(600);
  await ev("(()=>{const b=[...(" + F + ").querySelectorAll('button')].find(x=>x.offsetParent&&/^save/i.test(x.innerText.trim()));if(b)b.click()})()"); await sleep(800);
  await pick("nb-svc", "Internships"); await sleep(1200);                                  // the test posting is an internship
  const top = await ev("(()=>{const c=" + F + ".querySelector('.card.top');return c?c.innerText.split(String.fromCharCode(10)).filter(x=>x.trim()).join(' | '):'(none)'})()");
  check("the deck shows the test employer's posting with Apply instantly", /UAply Test Employer/.test(top) && /Apply instantly/i.test(top), top.slice(0, 140));
  if (process.env.ROLE) {                               // a particular posting: pass the ones before it
    for (let i = 0; i < 6; i++) {
      const t = await ev("(()=>{const c=" + F + ".querySelector('.card.top');return c?c.innerText:''})()");
      if (t.includes(process.env.ROLE) || !t) break;
      await ev(F + ".getElementById('btnNo').click()"); await sleep(900);
    }
  }
  await snap("real-2-the-job");

  // 4. swipe right
  const before = await ev("fetch('/api/outbox').then(r=>r.json()).then(j=>j.applications.length)");
  await ev(F + ".getElementById('btnYes').click()"); await sleep(900);
  await ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m){m.ownerDocument.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});m.disabled=false;m.click()}})()");
  for (let i = 0; i < 20; i++) { await sleep(500); if (await ev("!!" + F + ".getElementById('kitToast')")) break; }
  await sleep(800);
  const toastText = await ev("((" + F + ".getElementById('kitToast')||{}).innerText||'')");
  check("swipe right says it applied, and where the confirmation is", /Applied to UAply Test Employer/.test(toastText), toastText);
  await snap("real-3-applied");

  // 5. what the employer received, and the applicant's confirmation
  const ob = await ev("fetch('/api/outbox').then(r=>r.json()).then(j=>JSON.stringify(j.applications[0]))").then(JSON.parse);
  check("one new application, delivered to the employer's address", (await ev("fetch('/api/outbox').then(r=>r.json()).then(j=>j.applications.length)")) === before + 1 && ob.to === "uaplytechnologies@uaply.net",
        ob.status + " to " + ob.to + " from " + ob.candidate.name + " <" + ob.candidate.email + ">");
  await nav("http://127.0.0.1:" + PORT + "/outbox"); await sleep(1500);
  const page = await ev("document.body.innerText");
  check("the applicant's confirmation of this application is addressed to " + EMAIL, new RegExp("Applied: [^\n]*UAply Test Employer[^\n]*to " + EMAIL.replace(/[.]/g, "[.]")).test(page) || page.includes("UAply Test Employer") && page.includes("to " + EMAIL), "");
  await snap("real-4-test-inbox-employer-copy");
  await ev("(()=>{const h=[...document.querySelectorAll('h2')].find(x=>/Receipts/.test(x.innerText));if(h)h.scrollIntoView({block:'start'})})()"); await sleep(400);
  await snap("real-5-applicant-confirmation");
  check("no script errors", logs.length === 0, logs.join(" / ").slice(0, 200));
  console.log(bad ? bad + " check(s) failed" : "The complete application worked");
};
