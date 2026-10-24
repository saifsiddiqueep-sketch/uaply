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
// uaply-nav.js's own assistShape / assistOnly / assistHosts (what the phone app hands the page), taken from the file as they are
function assistHelpers() {
  const nav = fs.readFileSync(path.join(__dirname, "..", "shared", "uaply-nav.js"), "utf8");
  const code = nav.split("\n").filter((l) => /^\s*var ASSIST_[A-Z]+=|^\s*function assist(Shape|Only|Hosts)\(/.test(l)).join("\n");
  return new Function("w", code + "\nreturn {assistShape:assistShape,assistOnly:assistOnly,assistHosts:assistHosts};")({ URL: URL });
}
const RESUME = fs.readFileSync(path.join(__dirname, "fixtures", "resumes", "twocolumn.pdf")).toString("base64");
const PERSON = {
  first: "Sam", last: "Rivera", name: "Sam Rivera", email: "sam.rivera.test@example.com", phone: "215-555-0142",
  linkedin: "https://www.linkedin.com/in/samrivera-test", website: "https://samrivera.example.com", city: "Philadelphia", state: "PA", zip: "19122", country: "US",
  company: "Philly Coffee Co", title: "Shift lead", school: "Temple University", degree: "Bachelor", major: "Communications", grad: "2026-05",
  auth: "yes", sponsor: "no", adult: "yes", jobStart: "2023-06", start: "now", former: "no", heard: "UAply", why: "I want to bring my customer and writing experience to {company}.",
  answers: {}, resume: { name: "Sam Rivera resume.pdf", type: "application/pdf", b64: RESUME }
};
const DIR = "file:///" + path.join(__dirname, "fixtures", "assist").replace(/\\/g, "/") + "/";
// [system, check kind expected, fields that must hold these values, voluntary fields that must stay empty, boxes that must stay unticked]
const CASES = [
  ["greenhouse", "reCAPTCHA",
    [["#first_name", /^Sam$/], ["#last_name", /^Rivera$/], ["#email", /sam\.rivera/], ["#phone", /215-555-0142/], ["input[name=country]", /^United States$/],
     ["input[name=candidate-location]", /^Philadelphia, Pennsylvania/], ["#question_1", /linkedin\.com/], ["#question_2", /samrivera\.example/],
     ["input[name=question_4]", /^Yes$/], ["input[name=question_5]", /^No$/], ["#question_6", /Example Co|your company/], ["#question_7", /^$/],
     ["#preferred_name", /^Sam$/], ["#phone_cc", /^1$/], ["#question_3", /^UAply$/], ["#question_9", /^$/], ["#question_10", /^$/],
     ["#company-name-0", /^Philly Coffee Co$/], ["#title-0", /^Shift lead$/], ["#start-month-0", /^June$/], ["#start-year-0", /^2023$/], ["#current-role-0:checked", /^on$/], ["#end-month-0", /^$/], ["#question_11", /^$/]],
    ["input[name=gender]", "input[name=hispanic_ethnicity]", "input[name=veteran_status]", "input[name=disability_status]"], ["#gdpr"]],
  ["lever", "hCaptcha",
    [["[name=name]", /^Sam Rivera$/], ["[name=email]", /sam\.rivera/], ["[name=phone]", /215/], ["[name=location]", /^Philadelphia, Pennsylvania/],
     ["#selected-location", /Philadelphia/], ["[name=org]", /Philly Coffee/], ["[name='urls[LinkedIn]']", /linkedin/], ["[name='urls[GitHub]']", /^$/],
     ["[name='urls[Portfolio]']", /samrivera\.example/], ["[name='cards[1][field0]']:checked", /^Yes$/], ["[name='cards[1][field1]']:checked", /^No$/],
     ["[name='cards[1][field3]']", /^$/], ["[name='cards[1][field4]']:checked", /^b$/], ["[name='cards[1][field5]']", /^Other$/], ["[name='cards[1][field6]']", /^UAply$/],
     ["[name=pronouns]:checked", null], ["[name=useCustomPronoun]:checked", null], ["[name=customPronoun]", /^$/], ["[name='cards[1][field7]']:checked", null]],
    ["[name='eeo[gender]']", "[name='eeo[race]']", "[name='eeo[veteran]']"], ["[name='consent[marketing]']"]],
  ["ashby", "",
    [["#_systemfield_name", /^Sam Rivera$/], ["#_systemfield_email", /sam\.rivera/], ["#_systemfield_phone", /215/], ["#loc", /^Philadelphia, PA/], ["#li", /linkedin/],
     ["._fieldEntry:nth-of-type(7) [aria-pressed=true]", /^Yes$/], ["._fieldEntry:nth-of-type(8) [aria-pressed=true]", /^No$/], ["#why", /Example Co|your company/], ["#tell", /^$/], ["#gradDate", /^2026-05-01$/]],
    [], ["[name=gender_m]", "[name=gender_f]", "[name=gender_d]", "[name=ack]"]],
  ["workable", "Turnstile",
    [["#firstname", /^Sam$/], ["#lastname", /^Rivera$/], ["#email", /sam\.rivera/], ["#phone", /215/], ["#address", /^New Castle/], ["#postcode", /^$/],
     ["[name=CA_1]:checked", /^true$/], ["[name=CA_2]:checked", /^false$/], ["[name=CA_3]:checked", null], ["[name=CA_4]:checked", /^true$/], ["[name=CA_5]:checked", /^true$/], ["#QA_1", /^05\/2026$/]],
    [], ["[name=gdpr]"]],
  ["smartrecruiters", "",
    [["#firstName", /^Sam$/], ["#lastName", /^Rivera$/], ["#email", /sam\.rivera/], ["#confirmEmail", /sam\.rivera/], ["#phoneNumber", /215/], ["#city", /^Philadelphia$/],
     ["#linkedin", /linkedin/], ["[name=q-auth]:checked", /^v-yes$/], ["#q-spon", /^s-no$/], ["#msg", /^$/],
     ["#mobile", /^2155550142$/], ["#state", /^Pennsylvania$/], ["#country", /^United States$/], ["#degree", /^Bachelor's Degree$/], ["#gradm", /^May$/], ["#grady", /^2026$/], ["#shift", /^$/]],
    ["#eeo-gender"], ["[name=consent]"]]
];
module.exports = async ({ ev, sleep, send }) => {
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  | " + extra : "")); };
  const open = async (sys) => { await send("Page.navigate", { url: DIR + sys + ".html" }); for (let i = 0; i < 20; i++) { await sleep(150); if (await ev("!!window.__mock")) break; } };
  const fill = async (opts) => { opts = opts || {}; const who = opts.personAnswers ? Object.assign({}, PERSON, { answers: opts.personAnswers }) : PERSON; delete opts.personAnswers;
    return JSON.parse(await ev("UAplyAssist.fill(" + JSON.stringify(who) + "," + JSON.stringify(Object.assign({ job: { co: "Example Co", role: "Analyst" } }, opts)) + ").then(r=>JSON.stringify(r))")); };
  const EEOQ = /gender|race|ethnic|hispanic|veteran|disab|pronoun|age range/i;
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
    if (kind) check(sys + ": ...and never shows the automatic notice there", (await ev("UAplyAssist.autoSubmit('automatic',null,1)")) === "refused" && (await mock()).submits === 0 &&
      !(await ev("!!document.getElementById('uaplyAssistCancel')")));
    table.push([sys, r.seen, r.filled, r.leftReq, r.eeoSkipped, r.ms]);
    if (sys === "ashby") {
      check("ashby: automatic mode refuses while a required question is left", r.leftReq > 0 && (await ev("UAplyAssist.submitIfAllowed('automatic')")) === false && (await mock()).submits === 0, "leftReq " + r.leftReq);
      // the person answers the rest and ticks the acknowledgement; the page has no human check: only now may "automatic" submit
      await ev("(()=>{const t=document.getElementById('tell');const d=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value');d.set.call(t,'A help center I rebuilt');t.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('[name=ack]').click()})()");
      const r2 = await fill({ banner: false });
      check("ashby: nothing left after the person's answers", r2.leftReq === 0, "leftReq " + r2.leftReq + " " + r2.left.join(" / "));
      // automatic submit with its notice (October 23): "Submitting for you in N" and a Cancel; Cancel stops it, nothing is sent
      check("ashby: assisted mode never starts the automatic notice", (await ev("UAplyAssist.autoSubmit('assisted',null,1)")) === "refused" && (await mock()).submits === 0);
      await ev("window.__auto=UAplyAssist.autoSubmit('automatic',null,3);1");
      await sleep(400);
      const note = await ev("(document.getElementById('uaplyAssistBar')||{}).textContent||''");
      check("ashby: automatic mode first says 'Submitting for you in 3' with a Cancel button", /Submitting for you in [23]/.test(note) && (await ev("!!document.getElementById('uaplyAssistCancel')")), note);
      await ev("document.getElementById('uaplyAssistCancel').click();1");
      check("ashby: Cancel stops it: nothing submitted, the bar says to review it and tap Submit", (await ev("window.__auto")) === "cancelled" && (await mock()).submits === 0 &&
        /Not submitted\. Review it, then tap Submit/.test(await ev("(document.getElementById('uaplyAssistBar')||{}).textContent||''")));
      await sleep(1500);
      check("ashby: ...and stays stopped (no submit after the countdown would have ended)", (await mock()).submits === 0);
      // the same complete page with a human check added (Reviewer 3, October 23: the fixtures had no page where the check was the only
      // thing missing, so taking the check out of the rule went unnoticed): automatic refuses, and says nothing about submitting
      await ev("(()=>{const f=document.createElement('iframe');f.id='r3check';f.src='about:blank#recaptcha';f.title='reCAPTCHA';f.style.cssText='width:304px;height:78px';document.body.appendChild(f);return 1})()");
      check("ashby: a complete page that shows a human check: automatic refuses (no submit, no notice)", (await ev("UAplyAssist.submitIfAllowed('automatic')")) === false &&
        (await ev("UAplyAssist.autoSubmit('automatic',null,1)")) === "refused" && (await mock()).submits === 0);
      await ev("(()=>{const f=document.getElementById('r3check');if(f)f.remove();const b=document.getElementById('uaplyAssistBar');if(b)b.remove();return 1})()");
      check("ashby: automatic mode submits a complete page with no human check once the notice runs out", (await ev("UAplyAssist.autoSubmit('automatic',null,1)")) === "submitted" && (await mock()).submits === 1);
      await sleep(200);
      check("ashby: the thank-you page counts as confirmed (Job Tracker: Sent)", (await ev("UAplyAssist.confirmed()")) === true);
    } else {
      // the person finishes the form and taps the employer's Submit: the employer's thank-you page is the only thing that counts as Sent
      await ev("(()=>{const f=document.querySelector('form');f.dispatchEvent(new Event('submit',{cancelable:true}))})()");
      await sleep(200);
      check(sys + ": after the person's Submit, the thank-you page counts as confirmed", (await ev("typeof UAplyAssist!=='undefined'&&UAplyAssist.confirmed()")) === true);
    }
  }
  // the phone app never hands a page the whole profile (October 22 review): the scan gets stand-ins for the person's details
  // (uaply-nav.js assistShape), the fill only the items the scan saw the form ask for (assistOnly). It must fill exactly as well.
  const H = assistHelpers();
  const shape = H.assistShape(PERSON), shapeText = JSON.stringify(shape);
  check("the scan's profile holds none of the person's contact details, links, address, pay or resume file",
    !/Sam|Rivera|sam\.rivera|215-555|linkedin\.com\/in\/samrivera|samrivera\.example|19122|Philly Coffee|Shift lead|customer and writing/.test(shapeText) && !(shape.resume || {}).b64 && shapeText.length < 2000, shapeText.slice(0, 200));
  check("...but keeps what the form's lists are matched against (state, school, degree, dates, yes/no answers)",
    shape.state === "PA" && shape.school === "Temple University" && shape.degree === "Bachelor" && shape.grad === "2026-05" && shape.auth === "yes" && shape.sponsor === "no" && shape.email === "a@example.com" && shape.first === "A");
  for (const [sys, , want] of CASES) {
    await open(sys);
    await ev(ENGINE);
    const sc = JSON.parse(await ev("UAplyAssist.scan(" + JSON.stringify(shape) + ",{job:{co:'Example Co',role:'Analyst'}}).then(r=>JSON.stringify({keys:r.keys,answerKeys:r.answerKeys,resume:!!r.resumeInput}))"));
    const only = H.assistOnly(PERSON, sc, []);
    const full = table.find((x) => x[0] === sys);
    await open(sys);
    await ev(ENGINE);
    const r = JSON.parse(await ev("UAplyAssist.fill(" + JSON.stringify(only) + ",{job:{co:'Example Co',role:'Analyst'},banner:false}).then(r=>JSON.stringify(r))"));
    let same = true, diff = "";
    for (const [sel, re] of want) { const v = await val(sel); if (re === null ? v !== null : !(v !== null && re.test(v))) { same = false; diff += sel + "=" + JSON.stringify(v) + " "; } }
    check(sys + ": filled from only what the scan saw it ask for, every field lands the same as with the whole profile", same && r.filled === full[2] && r.leftReq === full[3] && r.resumeAttached,
      diff + "filled " + r.filled + "/" + full[2] + " leftReq " + r.leftReq + "/" + full[3] + " items " + Object.keys(only).join(","));
    const unused = Object.keys(PERSON).filter((k) => k !== "answers" && PERSON[k] && !(k in only));
    check(sys + ": ...and the page was not handed the rest of the profile", unused.length > 0 && !("answers" in only && Object.keys(only.answers).length), "not handed: " + unused.join(","));
  }
  // the "required left" bridge: scan reads the form and changes nothing; it asks the required questions the profile cannot answer (never a
  // voluntary or consent question); the person's answers, given in UAply's question box, then land in their fields, and nothing required is
  // left at the form but the consent boxes the person ticks there
  const BRIDGE = {
    greenhouse: [["Describe a project you led", "A help center I rebuilt", "#question_8", /^A help center I rebuilt$/]],
    lever: [["Do you have any relatives employed by Example Co?", "No", "[name='cards[1][field2]']:checked", /^No$/], ["Do you have a current Example Co membership?", "No", "[name='cards[1][field7]']:checked", /^No$/]],
    ashby: [["Tell us about a project you are proud of", "A help center I rebuilt", "#tell", /^A help center I rebuilt$/]],
    workable: [["Do you currently have any relatives or friends employed by Example Co?", "NO", "[name=CA_3]:checked", /^false$/]],
    smartrecruiters: [["Which shift do you prefer?", "Day", "#shift", /^Day$/]]
  };
  for (const [sys, items] of Object.entries(BRIDGE)) {
    await open(sys);
    await ev(ENGINE);
    const sc = JSON.parse(await ev("UAplyAssist.scan(" + JSON.stringify(PERSON) + ",{job:{co:'Example Co',role:'Analyst'}}).then(r=>JSON.stringify(r))"));
    const req = (sc.questions || []).filter((q) => q.required).map((q) => q.q);
    check(sys + " bridge: the scan asks the required questions the profile cannot answer", items.length === req.length && items.every((it) => req.includes(it[0])), JSON.stringify(req));
    check(sys + " bridge: no voluntary or consent question is asked", !(sc.questions || []).some((q) => EEOQ.test(q.q) || /consent|acknowledg|privacy notice|i have read/i.test(q.q)), JSON.stringify((sc.questions || []).map((q) => q.q)));
    check(sys + " bridge: each question comes with its kind (and its choices)", (sc.questions || []).every((q) => q.kind && (q.kind !== "select" || (q.opts && q.opts.length))));
    const m0 = await mock();
    const changed = await ev("[...document.querySelectorAll('input:not([type=hidden]):not([type=file]),textarea,select')].filter(e=>e.type==='radio'||e.type==='checkbox'?e.checked:(e.value&&e.defaultValue!==e.value&&!(e.tagName==='SELECT'&&e.selectedIndex===0))).length");
    check(sys + " bridge: the scan changed nothing on the page", changed === 0 && m0.submits === 0 && m0.submitClicks === 0 && m0.checkTouched === 0 && !(await ev("!!document.getElementById('uaplyAssistBar')")), "changed " + changed + " " + JSON.stringify(m0));
    // kept as the app keeps them: under the key the scan gave (the server's autofill.norm; a question naming the employer is that employer's)
    const answers = {}; items.forEach((it) => { const q = (sc.questions || []).find((x) => x.q === it[0]); answers[q ? q.key : it[0]] = it[1]; });
    if (sys === "lever") check("lever bridge: a question naming the employer is keyed to that employer, as the server keys it",
      ((sc.questions || []).find((x) => /relatives employed/.test(x.q)) || {}).key === "{at example co} do you have any relatives employed by {co}", JSON.stringify((sc.questions || []).map((x) => x.key)));
    const r = await fill({ banner: false, personAnswers: answers });
    for (const it of items) check(sys + " bridge: the person's answer lands: " + it[0], it[3].test(String(await val(it[2]))), "got " + (await val(it[2])));
    check(sys + " bridge: nothing required left at the form but the consent the person ticks there", r.leftReq - r.consentReq === 0, "leftReq " + r.leftReq + ", required consent " + r.consentReq + ": " + r.left.join(" / "));
    check(sys + " bridge: answers counted as the person's", r.fromAnswers === items.length, "fromAnswers " + r.fromAnswers);
  }
  // ---------- one tap (Saif, October 23): right after the swipe the form opens filled, scrolled to the check or Submit, with one line;
  // timed the way the phone app opens it: the scan pass (a load, the app's ask every 150 ms, the scan), then the form again (a load,
  // the ask, the fill). The person's own time (any question box, the check, Submit) is not in it. ----------
  const ASK = 150;              // AssistActivity.FAST: how often the app asks the page while the form loads
  const ONE = /One tap to finish: this employer asks you to confirm you are a person\./;
  const times = [];
  for (const [sys, kind] of CASES.map((c) => [c[0], c[1]])) {
    const t0 = Date.now();
    await open(sys); await sleep(ASK); await ev(ENGINE);
    const sc = JSON.parse(await ev("UAplyAssist.scan(" + JSON.stringify(H.assistShape(PERSON)) + ",{job:{co:'Example Co',role:'Analyst'}}).then(r=>JSON.stringify({ms:r.ms}))"));
    await open(sys); await sleep(ASK); await ev(ENGINE);
    const r = JSON.parse(await ev("UAplyAssist.fill(" + JSON.stringify(PERSON) + ",{job:{co:'Example Co',role:'Analyst'}}).then(r=>JSON.stringify(r))"));
    const ms = Date.now() - t0;
    times.push([sys, ms, sc.ms, r.ms]);
    const bar = await ev("(document.getElementById('uaplyAssistBar')||{}).textContent||''");
    if (kind) check(sys + " one tap: the form says it asks you to confirm you are a person, then tap Submit, and is scrolled to the check or Submit",
      ONE.test(bar) && /tap Submit/.test(bar) && (r.scrolledTo === "submit" || r.scrolledTo === "check"), bar + " | " + r.scrolledTo);
    else check(sys + ": no human check, so no 'confirm you are a person' line", !ONE.test(bar), bar);
    check(sys + " one tap: Submit is on screen", await ev("(()=>{const b=[...document.querySelectorAll('button,input[type=submit]')].filter(b=>/^(submit|apply|send)/i.test((b.innerText||b.value||'').trim())).pop();if(!b)return false;const q=b.getBoundingClientRect();return q.top>=0&&q.bottom<=innerHeight})()"));
    check(sys + " one tap: the check is never touched while the form opens and fills", (await mock()).checkTouched === 0 && (await mock()).submits === 0);
    check(sys + " one tap: the form is ready " + ms + " ms after the app opens it (target under 3 s)", ms < 3000, ms + " ms");
  }
  console.log("ONE-TAP-TIMES " + JSON.stringify(times));
  check("yes/no read from words: 'I will not require sponsorship' is a no", (await ev("UAplyAssist.ynOf('I will not require sponsorship')")) === "no");
  check("yes/no read from words: 'Yes, I am' is a yes; 'Decline to answer' is neither", (await ev("UAplyAssist.ynOf('Yes, I am')")) === "yes" && (await ev("UAplyAssist.ynOf('Decline to answer')")) === "");
  // labels that share a word with a profile answer but ask something else (all seen on real forms, October 21, 2026)
  const KEYS = [["Why do you want to work at Discord?", "why"], ["Name Pronunciation", null], ["What draws you to mobile design work?", null],
    ["Do you currently hold a right to work status with a limited duration?", null], ["Are you able to work in the United States now and in the future without sponsorship?", "nosponsor"],
    ["If yes, what is the email associated with your membership?", null], ["Do you currently have any relatives or friends employed by Thorlabs?", null],
    ["When did you graduate from High School?", null], ["Portfolio Password or Access Code(s)", null], ["Is there any other context you'd like to share about your U.S. work authorization?", null],
    ["Have you ever been previously employed by Spotify?", "former"], ["Which location are you applying for?", null], ["What is your current City, State, and Zip Code", "csz"],
    ["Will you now or in the future require visa sponsorship?", "sponsor"], ["Are you legally authorized to work in the United States?", "auth"], ["Current Street Address", "street"], ["Are you at least 18 years of age?", "adult"], ["Are you over the age of 21?", null],
    ["Phone country code", "phonecc"], ["Graduation month", "gradmonth"], ["Graduation year", "gradyear"], ["Preferred Name", "first"], ["Can you work without sponsorship?", "nosponsor"],
    ["Cover Letter", "cover"], ["Message to the hiring manager", "cover"]];
  await ev(ENGINE);
  for (const [q, k] of KEYS) { const got = await ev("UAplyAssist.keyOf(" + JSON.stringify(q) + ")"); check("label read as " + (k || "nothing to fill") + ": " + q, got === k, "got " + got); }
  // the message to the employer (Profile setup, the person's own switch) goes into a cover letter box; with it off the box is left alone
  for (const [note, want, name] of [["Hi Example Co hiring team, I just applied.", "Hi Example Co hiring team, I just applied.", "with the message on"], ["", "", "with the message off"]]) {
    await send("Page.navigate", { url: "data:text/html,<form><label for=c>Cover letter</label><textarea id=c></textarea></form>" }); await sleep(300); await ev(ENGINE);
    await ev("UAplyAssist.fill(" + JSON.stringify({ first: "A", note }) + ",{job:{co:'Example Co',role:'Analyst'},banner:false}).then(r=>JSON.stringify(r))");
    const got = await ev("document.getElementById('c').value");
    check("a cover letter box gets the message to the employer " + name, got === want, JSON.stringify(got));
  }
  // a page that is not a form and says nothing about an application is not a confirmation
  await send("Page.navigate", { url: "data:text/html,<h1>Careers at Example Co</h1><p>We are hiring.</p>" }); await sleep(300); await ev(ENGINE);
  check("a careers page is not a confirmation", (await ev("UAplyAssist.confirmed()")) === false);

  // the switch: shipped "assisted" everywhere, and the rule that turns "automatic" on
  const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "shared", "assist-systems.json"), "utf8"));
  check("assist-systems.json: every system ships assisted, approved by counsel (Saif, October 24; the owner's counsel_approved switch can turn it off)", Object.values(cfg.systems).every((s) => s.mode === "assisted" && s.counsel_approved === true));
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
