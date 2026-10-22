// Measures UAply's assisted apply (shared/uaply-assist.js) on real employer application forms, WITHOUT submitting anything:
//   URLS=apply-urls.json [OUT=report.json] [SHOTS=folder] [ONLY=greenhouse] W=390 H=844 node tools/cdp.js tools/assist-measure.js
// apply-urls.json is {"greenhouse": [hosted form urls], "lever": [...], ...}. For each page: open it, inject the assist script, fill it with
// a made-up test person (and a small test resume), and record fields seen / filled / left, voluntary questions skipped, the resume
// attached or not, any human check (reCAPTCHA, hCaptcha, Turnstile), the Submit button found, and the time to "ready to review".
// Safety: every request that is not a GET (or a HEAD/OPTIONS) is refused by the browser before it leaves, so no application, no file
// and no tracking form post can be sent, whatever the page does. Nothing is clicked except the employer's own "Apply" link on a
// posting page that shows the form only after it (SmartRecruiters).
const fs = require("fs");
const path = require("path");
const URLS = JSON.parse(fs.readFileSync(process.env.URLS, "utf8"));
const ENGINE = fs.readFileSync(path.join(__dirname, "..", "shared", "uaply-assist.js"), "utf8");
const RESUME = fs.readFileSync(path.join(__dirname, "fixtures", "resumes", "twocolumn.pdf")).toString("base64");
const PERSON = {
  first: "Sam", last: "Rivera", name: "Sam Rivera", email: "sam.rivera.test@example.com", phone: "215-555-0142",
  linkedin: "https://www.linkedin.com/in/samrivera-test", website: "https://samrivera.example.com", city: "Philadelphia", state: "PA", country: "United States",
  school: "Temple University", degree: "Bachelor", major: "Communications", grad: "2026-05", auth: "yes", sponsor: "no", start: "now", heard: "UAply", adult: "yes", jobStart: "2023-06",
  state: "PA", zip: "19122", street: "1801 N Broad St", country: "US", company: "Philly Coffee Co", title: "Shift lead", relocate: "yes", office: "yes", former: "no", govt: "no", phd: "no",
  why: "I want to bring my customer and writing experience to {company} as a {role}.", summary: "Communications graduate with three years of customer-facing work and a writing portfolio.",
  answers: {}, resume: { name: "Sam Rivera resume.pdf", type: "application/pdf", b64: RESUME }
};
// NORESUME=1: no resume file (a screenshot of a form whose page fails once its resume upload is refused: Workable's does)
if (process.env.NORESUME) delete PERSON.resume;
// The "required left" bridge, as the app runs it: UAplyAssist.scan reads the form first and lists what the profile cannot answer; the
// app asks those in UAply's question box before the form opens, and the answers go into the fill. Here the test person answers them,
// the same plain way every time (BRIDGE=required: only the required ones, the app's default; BRIDGE=all: the optional ones too;
// BRIDGE=off: no bridge, the profile alone). The answers are deliberately dull: what is measured is that each one lands in its field.
const BRIDGE = process.env.BRIDGE || "required";
function personAnswer(q) {
  const t = String(q.q || "").toLowerCase();
  const opts = (q.opts || []).filter((o) => o && !/^(select|choose|please select|--)/i.test(o));
  const pick = (re) => opts.find((o) => re.test(o));
  if ((q.kind === "select" || q.kind === "multi") && opts.length) {
    if (/relative|related|referr|family|friend|conflict|currently employ|government|sanction|convicted|criminal|non-?compete|previously applied|already applied/i.test(t)) return pick(/^no\b/i) || opts[opts.length - 1];
    return pick(/^yes\b/i) || pick(/^other\b/i) || opts[0];
  }
  if (q.kind === "number" || /how many|number of|years of/i.test(t)) return "3";
  if (q.kind === "date") return "2026-06-01";
  if (q.kind === "month") return "2026-06";
  if (/salary|compensation|pay\b|rate/i.test(t)) return "60000";
  if (/^(if|please (list|specify|explain|provide|state))\b/i.test(t) || q.kind === "text") return "N/A";
  return "I would welcome the chance to talk about this in an interview.";
}
const CHECK_NET =/hcaptcha\.com|\/recaptcha\/|recaptcha\.net|challenges\.cloudflare\.com|turnstile/i;
module.exports = async ({ ev, sleep, nav, send, on, shot }) => {
  const blocked = [];
  let netChecks = new Set();
  await send("Fetch.enable", { patterns: [{ urlPattern: "*", requestStage: "Request" }] });
  // the pages load their own data with POSTs too (Ashby's GraphQL, SmartRecruiters' app), so those go through; what is refused is anything
  // that could carry an application: a POST/PUT/PATCH whose address or body mentions submitting or applying, any file upload (multipart),
  // and anything carrying the test person's details (a draft some forms save as you type)
  const SENDS = /submit|upload|draft|attachment|job_app|\/apply\/?(\?|$)|\/applications?\/?(\?|$)|\/candidates?\/?(\?|$)/i, PERSON_RE = /sam\.rivera|Rivera|215-555-0142|samrivera/;
  on("Fetch.requestPaused", (p) => {
    const m = p.request.method, body = p.request.postData || "", ct = (p.request.headers["Content-Type"] || p.request.headers["content-type"] || "");
    const cm = CHECK_NET.exec(p.request.url); if (cm) netChecks.add(/hcaptcha/i.test(cm[0]) ? "hCaptcha" : /recaptcha/i.test(cm[0]) ? "reCAPTCHA" : "Turnstile");
    const risky = m !== "GET" && m !== "HEAD" && m !== "OPTIONS" && (SENDS.test(p.request.url) || /submit|upload/i.test(body.slice(0, 2000)) || /multipart/i.test(ct) || PERSON_RE.test(body) || p.request.hasPostData && !body);
    if (risky) { blocked.push(m + " " + p.request.url.slice(0, 90)); send("Fetch.failRequest", { requestId: p.requestId, errorReason: "BlockedByClient" }); }
    else send("Fetch.continueRequest", { requestId: p.requestId });
  });
  const out = {};
  for (const [system, urls] of Object.entries(URLS)) {
    if (process.env.ONLY && process.env.ONLY !== system) continue;
    out[system] = [];
    for (const url of urls) {
      const t0 = Date.now();
      netChecks = new Set();
      await send("Page.navigate", { url });
      let n = 0;
      for (let i = 0; i < 40; i++) { await sleep(500); n = await ev("document.querySelectorAll('input:not([type=hidden]),textarea,select').length"); if (n > 3) break; }
      if (n <= 3) {   // a posting page that shows the form after its own Apply / I'm interested link
        await ev("(()=>{const a=[...document.querySelectorAll('a,button')].find(b=>/^(apply( now| for this job)?|i'?m interested)$/i.test((b.innerText||'').trim()));if(a)a.click();return !!a})()");
        for (let i = 0; i < 30; i++) { await sleep(500); n = await ev("document.querySelectorAll('input:not([type=hidden]),textarea,select').length"); if (n > 3) break; }
      }
      const loadMs = Date.now() - t0;
      if (n <= 3) {   // no form: a bot wall, an error page, a closed posting. Recorded as it is; nothing is tried to get past it.
        const pg = await ev("JSON.stringify({title:document.title,text:(document.body&&document.body.innerText||'').replace(/\\s+/g,' ').slice(0,160)})");
        let pj = {}; try { pj = JSON.parse(pg); } catch (e) {}
        const r = { url, noForm: true, title: pj.title, text: pj.text, loadMs, netChecks: [...netChecks] };
        out[system].push(r);
        console.log(system.padEnd(16) + " NO FORM  " + url.slice(0, 80) + "  [" + (pj.title || "") + "] " + (pj.text || "").slice(0, 100));
        if (process.env.SHOTS) { fs.mkdirSync(process.env.SHOTS, { recursive: true }); await shot(path.join(process.env.SHOTS, system + "-" + out[system].length + "-noform.png")); }
        continue;
      }
      await ev(ENGINE);
      const job = { co: "the company", role: "this role" };
      let asked = [], who = PERSON;
      if (BRIDGE !== "off") {
        const sc = await ev("UAplyAssist.scan(" + JSON.stringify(PERSON) + ",{job:" + JSON.stringify(job) + "}).then(r=>JSON.stringify(r.questions||[])).catch(e=>'[]')");
        try { asked = JSON.parse(sc).filter((q) => BRIDGE === "all" || q.required); } catch (e) { asked = []; }
        const answers = {};
        asked.forEach((q) => { answers[q.key] = personAnswer(q); });
        who = Object.assign({}, PERSON, { answers });
      }
      const rep = await ev("UAplyAssist.fill(" + JSON.stringify(who) + ",{banner:true,debug:" + (process.env.DEBUG ? "true" : "false") + ",job:" + JSON.stringify(job) + "}).then(r=>JSON.stringify(r)).catch(e=>JSON.stringify({error:String(e)}))");
      let r = {};
      try { r = JSON.parse(rep); } catch (e) { r = { error: String(rep).slice(0, 120) }; }
      await sleep(1500);   /* a check that loads late (Workable's) */
      const late = await ev("JSON.stringify(window.UAplyAssist?UAplyAssist.humanCheck():{})");
      try { const hc = JSON.parse(late); if (hc.present) { r.humanCheck = true; r.checkKind = r.checkKind || hc.kind; r.checkShown = r.checkShown || hc.shown; } } catch (e) {}
      r.netChecks = [...netChecks];
      r.url = url; r.loadMs = loadMs; r.readyMs = loadMs + (r.ms || 0); r.inputs = n;
      r.bridge = BRIDGE; r.asked = asked.length; r.askedReq = asked.filter((q) => q.required).length; r.askedQ = asked.map((q) => q.kind + ": " + q.q.slice(0, 70));
      out[system].push(r);
      console.log(system.padEnd(16) + " seen " + String(r.seen).padStart(2) + " filled " + String(r.filled).padStart(2) + " (answers " + (r.fromAnswers || 0) + ", asked " + r.asked + ") leftReq " + String(r.leftReq).padStart(2) + " consent " + (r.consentLeft || 0) + " eeo " + (r.eeoSkipped || 0) + " resume " + (r.resumeAttached ? "yes" : r.resumeInput ? "NO" : "-") + " check " + (r.humanCheck ? (r.checkKind || "yes") + (r.checkShown ? "(shown)" : "(invisible)") : "no") + " net " + (r.netChecks.join("+") || "-") + " submit " + (r.submit ? "found" : "-") + " " + Math.round(r.readyMs / 100) / 10 + "s  " + url.slice(0, 80) + (r.error ? " ERR " + r.error : ""));
      if (process.env.DEBUG && r.fields) r.fields.forEach((f) => console.log("    " + (f.req ? "*" : " ") + " " + f.how.padEnd(18) + " " + (f.key || "-").padEnd(9) + " " + f.q));
      if (process.env.SHOTS) {
        fs.mkdirSync(process.env.SHOTS, { recursive: true });
        if (out[system].length <= 2) { await ev("window.scrollTo(0,0)"); await sleep(400); await shot(path.join(process.env.SHOTS, system + "-" + out[system].length + "-top.png")); await ev("(()=>{const b=document.querySelector('#uaplyAssistBar');const s=[...document.querySelectorAll('button,input[type=submit]')].find(x=>x.style.outlineOffset==='3px');if(s)s.scrollIntoView({block:'center'});return !!b})()"); await sleep(400); }
        await shot(path.join(process.env.SHOTS, system + "-" + out[system].length + ".png"));
      }
      // the test person's details never stay in this browser: drop any draft the page kept (only items holding them)
      await ev("(()=>{for(const st of [localStorage,sessionStorage]){try{for(const k of Object.keys(st)){if(/sam\\.rivera|Rivera|215-555-0142|samrivera/.test(st.getItem(k)||''))st.removeItem(k)}}catch(e){}}})()");
    }
  }
  await send("Page.navigate", { url: "about:blank#uaply-assist-done" });
  console.log("BLOCKED (never sent): " + blocked.length + " non-GET requests" + (blocked.length ? ": " + blocked.slice(0, 5).join(" | ") : ""));
  if (process.env.OUT) fs.writeFileSync(process.env.OUT, JSON.stringify({ at: new Date().toISOString(), blocked: blocked.length, results: out }, null, 1));
};
module.exports.limitMs = 3600000;
