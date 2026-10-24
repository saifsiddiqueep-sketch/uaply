// Profile setup asks each thing once (Saif, October 24, from Reviewer 3's audit): step 5 no longer asks "Willing to relocate" or
// "Willing to work from the job's office" (both come from step 3's Work style ticks), step 4's "About you" field is "Summary" (step 1
// is About you), step 3 is "Location and pay", one resume picker with one limit (1 MB, what an application can carry), Data & privacy
// says the person agreed when they created the account, and the message to the employer goes into a cover letter box on one-tap forms.
//   W=390 H=844 PORT=<sandbox or dev, sign-up test mode> node tools/cdp.js tools/ui-profile-polish.js      (and W=1280 H=800)
module.exports = async ({ ev, sleep, send, nav, logs }) => {
  const PORT = process.env.PORT, W = Number(process.env.W || 390), H = Number(process.env.H || 844), base = "http://127.0.0.1:" + PORT;
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + "[profile " + W + "] " + name + (extra !== undefined && !ok ? "  | " + String(extra).slice(0, 300) : "")); };
  const J = (x) => ev("JSON.stringify((()=>{const d=" + F + ",w=" + FW + ";" + x + "})())").then((t) => JSON.parse(t || "null"));
  if (W >= 700) await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  const who = await require("./gate-signup.js")({ ev, sleep, nav }, base, "polish", { api: true });
  check("the test person signs up first", !!who.ok);
  await send("Page.navigate", { url: base + "/" });
  for (let i = 0; i < 80 && !(await ev("!!(" + F + "&&" + FW + ".__uaply&&" + FW + ".__uaplyOpenProf&&" + F + ".getElementById('bnav'))").catch(() => false)); i++) await sleep(250);
  await sleep(1200);

  // ---- Data & privacy before this device's agreement: the account's own agreement is told, not "you have not agreed" ----
  await ev("(()=>{const b=" + F + ".getElementById('kcNo');if(b)b.click()})()"); await sleep(300);
  await ev("(()=>{const d=" + F + ";d.getElementById('nb-prof').click()})()"); await sleep(400);
  await ev("(()=>{const d=" + F + ";const b=[...d.querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')==='data');if(b)b.click()})()"); await sleep(900);
  const line = await J("return (d.getElementById('aAgreed')||{}).textContent||''");
  check("Data & privacy says the person agreed when they created the account (not 'You have not agreed')", /^You agreed to the Terms and Privacy Policy on .+, when you created your account[.]/.test(line) && !/have not agreed/.test(line), line);
  await ev("(()=>{const w=" + FW + ";if(w.__uaplyConsentAgain)w.__uaplyConsentAgain(function(){})})()"); await sleep(500);
  const box = await J("const b=d.getElementById('kitConsent');return b?b.innerText:''");
  check("the agreement box no longer says You only see this once", !/You only see this once/.test(box || ""), String(box).slice(-160));
  await ev("(()=>{const b=" + F + ".getElementById('kcYes');if(b){b.ownerDocument.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});b.disabled=false;b.click()}})()"); await sleep(400);

  // ---- step 3 is Location and pay; step 5 asks no relocation or office question ----
  await ev(FW + ".__uaplyOpenProf('where')"); await sleep(900);
  const s3 = await J("const c=d.querySelector('.wzDots button[aria-current=step]');return {step:c?c.getAttribute('aria-label'):'',text:d.getElementById('form').innerText.slice(0,400)}");
  check("step 3 is called Location and pay", /Location and pay/.test(s3.step) && !/Where and pay/.test(s3.text), JSON.stringify(s3));
  await ev(FW + ".__uaplyOpenProf('final')"); await sleep(900);
  const s5 = await J("const t=d.getElementById('form').innerText;return {office:!!d.getElementById('px-office'),reloc:!!d.getElementById('px-relocate'),t1:/Willing to relocate for the right job/.test(t),t2:/work from the job.s office/.test(t)}");
  check("step 5 no longer asks Willing to relocate or Willing to work from the job's office", !s5.office && !s5.reloc && !s5.t1 && !s5.t2, JSON.stringify(s5));

  // ---- both answers come from step 3's Work style ticks ----
  const setWs = async (ticks) => {
    await ev(FW + ".__uaplyOpenProf('where')"); await sleep(700);
    await ev("(()=>{const d=" + F + ",w=" + FW + ";for(const [id,on] of " + JSON.stringify(Object.entries(ticks)) + "){const c=d.getElementById(id);if(c&&c.checked!==on){c.checked=on;c.dispatchEvent(new w.Event('change',{bubbles:true}))}}})()"); await sleep(200);
    await ev("(()=>{const b=" + F + ".getElementById('wzNext');if(b)b.click()})()"); await sleep(900);
    return J("const p=w.__uaply.S.profile,x=p.ext||{},a=w.__uaplyApplyExt?w.__uaplyApplyExt():{};return {relocate:x.relocate,office:x.office,sent:{relocate:a.relocate,office:a.office}}");
  };
  let e = await setWs({ "pm-remote": false, "pm-hybrid": false, "pm-onsite": true, pReloc: true });
  check("On-site and Willing to relocate ticked: forms get relocate Yes and office Yes", e.relocate === "yes" && e.office === "yes" && e.sent.relocate === "yes" && e.sent.office === "yes", JSON.stringify(e));
  e = await setWs({ "pm-remote": true, "pm-hybrid": false, "pm-onsite": false, pReloc: false });
  check("only Remote ticked, relocate not ticked: office No, and relocate left unanswered (a form that asks it asks the person each time)", e.relocate === undefined && e.office === "no" && e.sent.relocate === undefined && e.sent.office === "no", JSON.stringify(e));
  const ap = await J("const p=w.__uaplyAssistProfile({co:'Polish Test Co'});return p?p.relocate:null");
  check("...and the one-tap form fill has no relocate answer either", ap === "", JSON.stringify(ap));
  e = await setWs({ "pm-remote": true, "pm-hybrid": true, "pm-onsite": false, pReloc: false });
  check("Remote and Hybrid ticked: office Yes", e.office === "yes", JSON.stringify(e));

  // ---- step 4: the field is Summary, and one resume picker with one limit ----
  await ev(FW + ".__uaplyOpenProf('back')"); await sleep(900);
  const s4 = await J("const l=d.querySelector('label[for=px-summary]')||d.querySelector('label[for=aSummary]'),s=d.getElementById('aResF'),rs=d.getElementById('rsBox');" +
    "const vis=(e)=>!!(e&&e.getClientRects().length);const pickers=[...d.querySelectorAll('#form input[type=file]')].filter(i=>i.id!=='aImp'&&(vis(i)||(i.id==='rsFile'&&vis(d.getElementById('rsChoose'))))).map(i=>i.id);" +
    "const txt=(s?s.innerText:'')+(rs&&!(s&&s.contains(rs))?rs.innerText:'');return {label:l?l.textContent.trim():'',sandbox:!!rs,pickers,mb:txt.match(/up to [0-9]+ MB/g)||[]}");
  check("step 4's field is called Summary (About you is step 1)", s4.label === "Summary", JSON.stringify(s4));
  check("one resume picker on step 4 (" + (s4.sandbox ? "Choose your resume" : "Upload your resume file") + ") and one limit, up to 1 MB",
    s4.pickers.length === 1 && s4.pickers[0] === (s4.sandbox ? "rsFile" : "pResFile") && s4.mb.length >= 1 && s4.mb.every((x) => x === "up to 1 MB"), JSON.stringify(s4));

  // ---- the message to the employer goes into a cover letter box on one-tap forms (when the person turned it on) ----
  const job = { id: 4261001, co: "Polish Test Co", role: "Analyst", sal: [60000, 70000], live: true, loc: "Philadelphia, PA", mode: "onsite", type: "job", yrs: 0, edu: "Bachelor",
    skills: ["Excel"], blurb: "A test posting.", url: "https://example.com/jobs/4261001", source: "careers page", apply: "link", contact: "", posted: Date.now() };
  await ev(FW + ".__uaplyOpenProf('final')"); await sleep(800);
  const sw = await J("const c=d.getElementById('aAutoMsg');return c?{dis:c.disabled,on:c.checked}:null");
  if (!sw || sw.dis) console.log("SKIP [profile " + W + "] the message to the employer is not available on this plan here (" + JSON.stringify(sw) + ")");
  else {
    if (!sw.on) { await ev("(()=>{const c=" + F + ".getElementById('aAutoMsg');c.click()})()"); await sleep(300); }
    const on = await J("const p=w.__uaplyAssistProfile(" + JSON.stringify(job) + ");return p?p.note:null");
    check("message on: the one-tap profile carries it as note (for the cover letter box)", /^Hi Polish Test Co hiring team/.test(on || ""), on);
    await ev("(()=>{const c=" + F + ".getElementById('aAutoMsg');if(c.checked)c.click()})()"); await sleep(300);
    const off = await J("const p=w.__uaplyAssistProfile(" + JSON.stringify(job) + ");return p?p.note:null");
    check("message off: no note", off === "", off);
  }

  const errs = logs.filter((l) => !/favicon|ERR_FILE_NOT_FOUND|401|403/.test(l));
  check("no script errors", errs.length === 0, errs.join(" | "));
  console.log("\n" + (n - bad) + " / " + n);
  if (bad) throw new Error(bad + " profile check(s) failed");
};
