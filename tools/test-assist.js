// Assisted apply on a mock form of each hiring system (tools/fixtures/assist/*.html, built from the real forms measured October 21, 2026):
//   W=390 H=844 node tools/cdp.js tools/test-assist.js
// For each system it fills the form with shared/uaply-assist.js as the phone app does, then checks: the profile's answers landed in the
// right fields; no voluntary self-identification question was touched; no consent box was ticked; Submit was never clicked or sent; the
// human check was never touched and is reported; the resume is attached; the page is not taken for a confirmation page while the form is
// there, and is once the person's own Submit shows the employer's thank-you page. Then the per-system switch: "assisted" never submits;
// "automatic" refuses on every page with a human check or with a required question left, and submits on the one page with neither.
// Also checks shared/assist-systems.json: every system ships "assisted", and the mode rule in shared/uaply-nav.js.
const fs = require("fs");
const path = require("path");
const ENGINE = fs.readFileSync(path.join(__dirname, "..", "shared", "uaply-assist.js"), "utf8");
const RESUME = fs.readFileSync(path.join(__dirname, "fixtures", "resumes", "twocolumn.pdf")).toString("base64");
const PERSON = {
  first: "Sam", last: "Rivera", name: "Sam Rivera", email: "sam.rivera.test@example.com", phone: "215-555-0142",
  linkedin: "https://www.linkedin.com/in/samrivera-test", website: "https://samrivera.example.com", city: "Philadelphia", state: "PA", zip: "19122", country: "US",
  company: "Philly Coffee Co", title: "Shift lead", school: "Temple University", degree: "Bachelor", major: "Communications", grad: "2026-05",
  auth: "yes", sponsor: "no", start: "now", former: "no", heard: "Job board", why: "I want to bring my customer and writing experience to {company}.",
  answers: {}, resume: { name: "Sam Rivera resume.pdf", type: "application/pdf", b64: RESUME }
};
const DIR = "file:///" + path.join(__dirname, "fixtures", "assist").replace(/\\/g, "/") + "/";
// [system, check kind expected, fields that must hold these values, voluntary fields that must stay empty, boxes that must stay unticked]
const CASES = [
  ["greenhouse", "reCAPTCHA",
    [["#first_name", /^Sam$/], ["#last_name", /^Rivera$/], ["#email", /sam\.rivera/], ["#phone", /215-555-0142/], ["input[name=country]", /^United States$/],
     ["input[name=candidate-location]", /^Philadelphia, Pennsylvania/], ["#question_1", /linkedin\.com/], ["#question_2", /samrivera\.example/],
     ["input[name=question_4]", /^Yes$/], ["input[name=question_5]", /^No$/], ["#question_6", /Example Co|your company/], ["#question_7", /^$/]],
    ["input[name=gender]", "input[name=hispanic_ethnicity]", "input[name=veteran_status]", "input[name=disability_status]"], ["#gdpr"]],
  ["lever", "hCaptcha",
    [["[name=name]", /^Sam Rivera$/], ["[name=email]", /sam\.rivera/], ["[name=phone]", /215/], ["[name=location]", /^Philadelphia, Pennsylvania/],
     ["#selected-location", /Philadelphia/], ["[name=org]", /Philly Coffee/], ["[name='urls[LinkedIn]']", /linkedin/], ["[name='urls[GitHub]']", /^$/],
     ["[name='urls[Portfolio]']", /samrivera\.example/], ["[name='cards[1][field0]']:checked", /^Yes$/], ["[name='cards[1][field1]']:checked", /^No$/],
     ["[name='cards[1][field3]']", /^$/]],
    ["[name='eeo[gender]']", "[name='eeo[race]']", "[name='eeo[veteran]']"], ["[name='consent[marketing]']"]],
  ["ashby", "",
    [["#_systemfield_name", /^Sam Rivera$/], ["#_systemfield_email", /sam\.rivera/], ["#_systemfield_phone", /215/], ["#loc", /^Philadelphia, PA/], ["#li", /linkedin/],
     ["._fieldEntry:nth-of-type(7) [aria-pressed=true]", /^Yes$/], ["._fieldEntry:nth-of-type(8) [aria-pressed=true]", /^No$/], ["#why", /Example Co|your company/], ["#tell", /^$/]],
    [], ["[name=gender_m]", "[name=gender_f]", "[name=gender_d]", "[name=ack]"]],
  ["workable", "Turnstile",
    [["#firstname", /^Sam$/], ["#lastname", /^Rivera$/], ["#email", /sam\.rivera/], ["#phone", /215/], ["#address", /^New Castle/], ["#postcode", /^$/],
     ["[name=CA_1]:checked", /^true$/], ["[name=CA_2]:checked", /^false$/], ["[name=CA_3]:checked", null], ["[name=CA_4]:checked", /^true$/]],
    [], ["[name=gdpr]"]],
  ["smartrecruiters", "",
    [["#firstName", /^Sam$/], ["#lastName", /^Rivera$/], ["#email", /sam\.rivera/], ["#confirmEmail", /sam\.rivera/], ["#phoneNumber", /215/], ["#city", /^Philadelphia$/],
     ["#linkedin", /linkedin/], ["[name=q-auth]:checked", /^v-yes$/], ["#q-spon", /^s-no$/], ["#msg", /^$/]],
    ["#eeo-gender"], ["[name=consent]"]]
];
module.exports = async ({ ev, sleep, send }) => {
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  | " + extra : "")); };
  const open = async (sys) => { await send("Page.navigate", { url: DIR + sys + ".html" }); for (let i = 0; i < 20; i++) { await sleep(150); if (await ev("!!window.__mock")) break; } };
  const fill = async (opts) => JSON.parse(await ev("UAplyAssist.fill(" + JSON.stringify(PERSON) + "," + JSON.stringify(Object.assign({ job: { co: "Example Co", role: "Analyst" } }, opts || {})) + ").then(r=>JSON.stringify(r))"));
  const val = (sel) => ev("(()=>{const e=document.querySelector(" + JSON.stringify(sel) + ");if(!e)return null;return e.type==='file'?String(e.files.length):e.tagName==='BUTTON'?e.innerText.trim():(e.value!=null?e.value:e.innerText.trim())})()");
  const mock = async () => JSON.parse(await ev("JSON.stringify(window.__mock)"));
  const table = [];

  for (const [sys, kind, want, eeo, boxes] of CASES) {
    await open(sys);
    await ev(ENGINE);
    const r = await fill({ debug: true });
    for (const [sel, re] of want) {
      const v = await val(sel);
      if (re === null) check(sys + ": " + sel + " left for the person", v === null, "got " + v);
      else check(sys + ": " + sel + " = " + re, v !== null && re.test(v), "got " + JSON.stringify(v));
    }
    for (const sel of eeo) check(sys + ": voluntary " + sel + " untouched", (await val(sel)) === "", "got " + (await val(sel)));
    for (const sel of boxes) check(sys + ": " + sel + " not ticked", await ev("!document.querySelector(" + JSON.stringify(sel) + ").checked"));
    check(sys + ": voluntary questions counted as skipped, not filled", r.eeoSkipped >= (eeo.length || (sys === "ashby" ? 3 : 0)) && !r.filledKeys.some((k) => /gender|race|veteran|disab/i.test(k)), "skipped " + r.eeoSkipped);
    check(sys + ": resume attached to the resume box", r.resumeAttached && (await ev("[...document.querySelectorAll('input[type=file]')].some(i=>i.files.length===1&&i.files[0].name==='Sam Rivera resume.pdf')")));
    check(sys + ": human check " + (kind || "none") + " reported", kind ? r.humanCheck && r.checkKind === kind : !r.humanCheck, r.checkKind + " shown " + r.checkShown);
    const m = await mock();
    check(sys + ": Submit never clicked, nothing submitted, check never touched", m.submits === 0 && m.submitClicks === 0 && m.checkTouched === 0, JSON.stringify(m));
    check(sys + ": Submit found and the bar says Review and tap Submit", r.submit && /tap Submit/.test(await ev("(document.getElementById('uaplyAssistBar')||{}).textContent||''")));
    check(sys + ": the form is not taken for a confirmation page", (await ev("UAplyAssist.confirmed()")) === false);
    check(sys + ": assisted mode never submits", (await ev("UAplyAssist.submitIfAllowed('assisted')")) === false && (await mock()).submits === 0);
    if (kind) check(sys + ": automatic mode refuses a page with a human check", (await ev("UAplyAssist.submitIfAllowed('automatic')")) === false && (await mock()).submits === 0);
    table.push([sys, r.seen, r.filled, r.leftReq, r.eeoSkipped, r.ms]);
    if (sys === "ashby") {
      check("ashby: automatic mode refuses while a required question is left", r.leftReq > 0 && (await ev("UAplyAssist.submitIfAllowed('automatic')")) === false && (await mock()).submits === 0, "leftReq " + r.leftReq);
      // the person answers the rest and ticks the acknowledgement; the page has no human check: only now may "automatic" submit
      await ev("(()=>{const t=document.getElementById('tell');const d=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value');d.set.call(t,'A help center I rebuilt');t.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('[name=ack]').click()})()");
      const r2 = await fill({ banner: false });
      check("ashby: nothing left after the person's answers", r2.leftReq === 0, "leftReq " + r2.leftReq + " " + r2.left.join(" / "));
      check("ashby: automatic mode submits a complete page with no human check", (await ev("UAplyAssist.submitIfAllowed('automatic')")) === true && (await mock()).submits === 1);
      await sleep(200);
      check("ashby: the thank-you page counts as confirmed (Job Tracker: Sent)", (await ev("UAplyAssist.confirmed()")) === true);
    } else {
      // the person finishes the form and taps the employer's Submit: the employer's thank-you page is the only thing that counts as Sent
      await ev("(()=>{const f=document.querySelector('form');f.dispatchEvent(new Event('submit',{cancelable:true}))})()");
      await sleep(200);
      check(sys + ": after the person's Submit, the thank-you page counts as confirmed", (await ev("typeof UAplyAssist!=='undefined'&&UAplyAssist.confirmed()")) === true);
    }
  }
  // labels that share a word with a profile answer but ask something else (all seen on real forms, October 21, 2026)
  const KEYS = [["Why do you want to work at Discord?", "why"], ["Name Pronunciation", null], ["What draws you to mobile design work?", null],
    ["Do you currently hold a right to work status with a limited duration?", null], ["Are you able to work in the United States now and in the future without sponsorship?", "nosponsor"],
    ["If yes, what is the email associated with your membership?", null], ["Do you currently have any relatives or friends employed by Thorlabs?", null],
    ["When did you graduate from High School?", null], ["Portfolio Password or Access Code(s)", null], ["Is there any other context you'd like to share about your U.S. work authorization?", null],
    ["Have you ever been previously employed by Spotify?", "former"], ["Which location are you applying for?", null], ["What is your current City, State, and Zip Code", "csz"],
    ["Will you now or in the future require visa sponsorship?", "sponsor"], ["Are you legally authorized to work in the United States?", "auth"], ["Current Street Address", "street"]];
  await ev(ENGINE);
  for (const [q, k] of KEYS) { const got = await ev("UAplyAssist.keyOf(" + JSON.stringify(q) + ")"); check("label read as " + (k || "nothing to fill") + ": " + q, got === k, "got " + got); }
  // a page that is not a form and says nothing about an application is not a confirmation
  await send("Page.navigate", { url: "data:text/html,<h1>Careers at Example Co</h1><p>We are hiring.</p>" }); await sleep(300); await ev(ENGINE);
  check("a careers page is not a confirmation", (await ev("UAplyAssist.confirmed()")) === false);

  // the switch: shipped "assisted" everywhere, and the rule that turns "automatic" on
  const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "shared", "assist-systems.json"), "utf8"));
  check("assist-systems.json: every system ships assisted, none approved by counsel", Object.values(cfg.systems).every((s) => s.mode === "assisted" && s.counsel_approved === false));
  const nav = fs.readFileSync(path.join(__dirname, "..", "shared", "uaply-nav.js"), "utf8");
  const src = /function assistMode\(cfg,sys\)\{[^\n]*?\}(?=\n)/.exec(nav);
  check("uaply-nav.js has the mode rule", !!src);
  if (src) {
    const assistMode = new Function(src[0] + ";return assistMode")();
    const one = (s) => ({ systems: { ashby: s } });
    check("mode rule: the shipped file gives assisted", assistMode(cfg, "ashby") === "assisted" && assistMode(cfg, "greenhouse") === "assisted");
    check("mode rule: automatic without counsel's approval stays assisted", assistMode(one({ mode: "automatic", counsel_approved: false, human_check_share: 0 }), "ashby") === "assisted");
    check("mode rule: automatic on a system with human checks stays assisted", assistMode(one({ mode: "automatic", counsel_approved: true, human_check_share: 0.05 }), "ashby") === "assisted");
    check("mode rule: automatic with approval and no human check is automatic", assistMode(one({ mode: "automatic", counsel_approved: true, human_check_share: 0 }), "ashby") === "automatic");
    check("mode rule: an unknown system is assisted", assistMode(cfg, "workday") === "assisted" && assistMode(null, "ashby") === "assisted");
  }
  console.log("\nsystem            seen filled leftReq voluntary-skipped ms");
  for (const t of table) console.log(t[0].padEnd(17) + String(t[1]).padStart(5) + String(t[2]).padStart(7) + String(t[3]).padStart(8) + String(t[4]).padStart(18) + String(t[5]).padStart(6));
  console.log("\n" + (n - bad) + "/" + n + " passed");
  if (bad) process.exitCode = 1;
};
module.exports.limitMs = 240000;
