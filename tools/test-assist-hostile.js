// Assisted apply against pages that try to take what the phone app puts into them (October 22 review, finding 1):
//   W=390 H=844 node tools/cdp.js tools/test-assist-hostile.js
// It runs the phone app's own calls, the CALL text taken from AssistActivity.java and the engine wrapped the way AssistActivity wraps
// it, against pages served as if from their real https hosts (CDP Fetch answers every request; nothing goes to the network):
//   - a normal form on jobs.ashbyhq.com (the control: it is filled, with only what it asks for);
//   - a hostile page on an allowed host that defines its own window.UAplyAssist, traps the old window.__uaplyScan / __uaplyRep globals,
//     hunts for UAply's script to replace it, and wraps the browser's own value setters, JSON.stringify and Object.keys to watch;
//   - a posting that redirects to another site (evil.example), and a look-alike host (jobs.ashbyhq.com.evil.example).
// The hostile page and the other sites must receive nothing: no call, no profile, no typed value beyond the hostile form's own fields,
// and no question of theirs in UAply's question box.
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const ROOT = path.join(__dirname, "..");
const ENGINE = fs.readFileSync(path.join(ROOT, "shared", "uaply-assist.js"), "utf8");
const APP = path.join(ROOT, "mobile", "android", "app", "src", "main", "java", "com", "uaply", "app");
const JAVA = fs.readFileSync(path.join(APP, "AssistActivity.java"), "utf8");
const PLUGIN = fs.readFileSync(path.join(APP, "AssistPlugin.java"), "utf8");
const CFG = JSON.parse(fs.readFileSync(path.join(ROOT, "shared", "assist-systems.json"), "utf8"));
const m = /static final String CALL = "([^"]*)";/.exec(JAVA);
const CALL = m ? m[1] : "";
const WRAP_SRC = String.raw`"(function(__uaplyAssistKey){" + AssistPlugin.engine + "\n})('" + key + "')"`;
const wrap = (key) => "(function(__uaplyAssistKey){" + ENGINE + "\n})('" + key + "')";
function helpers() {   // uaply-nav.js's own assistShape / assistOnly / assistHosts, taken from the file as they are
  const nav = fs.readFileSync(path.join(ROOT, "shared", "uaply-nav.js"), "utf8");
  const code = nav.split("\n").filter((l) => /^\s*var ASSIST_[A-Z]+=|^\s*function assist(Shape|Only|Hosts)\(/.test(l)).join("\n");
  return new Function("w", code + "\nreturn {assistShape:assistShape,assistOnly:assistOnly,assistHosts:assistHosts};")({ URL: URL });
}
const RESUME = Buffer.from("%PDF-1.4 Sam Rivera resume RESUMEBYTES-7Q %%EOF").toString("base64");
const PERSON = {
  first: "Sam", last: "Rivera", name: "Sam Rivera", email: "sam.rivera.test@example.com", phone: "215-555-0142",
  linkedin: "https://www.linkedin.com/in/samrivera-test", website: "https://samrivera.example.com", street: "1500 Market St", city: "Philadelphia",
  state: "PA", zip: "19102", country: "US", company: "Philly Coffee Co", title: "Shift lead", school: "Temple University", degree: "Bachelor",
  major: "Communications", grad: "2026-05", gpa: "3.7", auth: "yes", sponsor: "no", adult: "yes", start: "now", salary: "65000", heard: "UAply",
  why: "I want to bring my customer and writing experience to {company}.", summary: "Barista turned analyst SUMMARY-9X",
  answers: { "Describe a project you led": "A help center I rebuilt", "Which shift do you prefer?": "Day",
    "Cover letter": "Dear hiring team, I have spent three years serving customers and writing COVER-4Z guides, and I would love to bring that to you." },
  resume: { name: "Sam Rivera resume.pdf", type: "application/pdf", b64: RESUME }
};
// what must never reach a page that does not ask for it
const SECRETS = { phone: "555-0142", phoneDigits: "2155550142", street: "1500 Market", zip: "19102", salary: "65000", linkedin: "samrivera-test",
  website: "samrivera.example", gpa: "3.7", why: "customer and writing", summary: "SUMMARY-9X", cover: "COVER-4Z", resume: "RESUMEBYTES-7Q", resumeB64: RESUME.slice(8, 30),
  resumeName: "Sam Rivera resume", company: "Philly Coffee" };
// the person as the first look at a form finds them: the project question not answered yet (the bridge asks it)
const BEFORE = Object.assign({}, PERSON, { answers: Object.assign({}, PERSON.answers) });
delete BEFORE.answers["Describe a project you led"];
const leaked = (text, except) => Object.keys(SECRETS).filter((k) => !(except || []).includes(k) && String(text).includes(SECRETS[k]));

const PROBE = `<script>
window.__seen = []; window.__got = []; window.__hijack = [];
(function () {
  var oj = JSON.stringify, ok = Object.keys;
  [HTMLInputElement, HTMLTextAreaElement, HTMLSelectElement].forEach(function (C) {
    var d = Object.getOwnPropertyDescriptor(C.prototype, "value");
    Object.defineProperty(C.prototype, "value", { configurable: true, get: d.get, set: function (v) { __seen.push("typed " + (this.id || this.name) + "=" + v); return d.set.call(this, v); } });
  });
  JSON.stringify = function () { var s = oj.apply(JSON, arguments); try { __seen.push("json " + String(s).slice(0, 4000)); } catch (e) {} return s; };
  Object.keys = function (o) { try { __seen.push("keys " + oj(o).slice(0, 4000)); } catch (e) {} return ok(o); };
})();
</script>`;
const FAKE = `<script>
window.UAplyAssist = {
  fill: function (p) { __got.push("fill " + JSON.stringify(p)); return Promise.resolve({}); },
  scan: function (p) { __got.push("scan " + JSON.stringify(p)); return Promise.resolve({ questions: [{ q: "Your bank password", key: "Your bank password", kind: "text", required: true }] }); },
  confirmed: function () { __got.push("confirmed"); return true; },
  submitIfAllowed: function () { __got.push("submit"); return true; },
  run: function (c) { __got.push("run " + JSON.stringify(c)); return JSON.stringify({ c: true }); }
};
["__uaplyScan", "__uaplyRep", "__uaplyAssistRan"].forEach(function (n) {
  Object.defineProperty(window, n, { configurable: true,
    get: function () { __got.push("read " + n); return n === "__uaplyScan" ? JSON.stringify({ questions: [{ q: "Your bank password", kind: "text", required: true }] }) : null; },
    set: function (v) { __got.push("set " + n + " " + v); } });
});
setInterval(function () {   /* find whatever UAply puts on the page, and try to replace it or wrap it */
  Object.getOwnPropertyNames(window).forEach(function (n) {
    if (!/^__uaplyAssist_/.test(n) || __hijack.indexOf(n) >= 0) return;
    __hijack.push(n);
    var trap = { run: function (c) { __got.push("hijacked " + JSON.stringify(c)); return "none"; } };
    try { window[n] = trap; } catch (e) {}
    try { Object.defineProperty(window, n, { value: trap }); } catch (e) {}
    try { window[n].run = trap.run; } catch (e) {}
    try { delete window[n]; } catch (e) {}
  });
}, 5);
</script>`;
const field = (id, label, extra) => `<div class="f"><label for="${id}">${label}</label><input id="${id}" name="${id}" type="text"${extra || ""}></div>`;
const page = (title, body, head) => `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title>${head || ""}</head><body><h1>${title}</h1><form onsubmit="return false">${body}<button type="submit">Submit application</button></form></body></html>`;
const PLAIN = page("Data Analyst at Example Co", field("first", "First name *", " required") + field("last", "Last name *", " required") + field("email", "Email *", " required") +
  field("phone", "Phone") + field("li", "LinkedIn profile") +
  `<div class="f"><label for="proj">Describe a project you led *</label><textarea id="proj" name="proj" required></textarea></div><div class="f"><label for="cv">Resume</label><input id="cv" type="file" name="resume"></div>`, PROBE);
const HOSTILE = page("Analyst at Example Co", field("first", "First name *", " required") + field("last", "Last name *", " required") + field("email", "Email *", " required") +
  `<div class="f"><label for="proj">Describe a project you led *</label><textarea id="proj" name="proj" required></textarea></div>`, PROBE + FAKE);
const EVIL = page("Apply now", field("first", "First name") + field("last", "Last name") + field("email", "Email") + field("phone", "Phone") + field("addr", "Street address") +
  field("zip", "ZIP code") + field("pay", "Desired salary", " required") + field("li", "LinkedIn") + `<div class="f"><label for="cv">Resume</label><input id="cv" type="file" name="resume"></div>`, PROBE + FAKE);
const PAGES = {
  "https://jobs.ashbyhq.com/exampleco/plain/application": { html: PLAIN },
  "https://jobs.ashbyhq.com/exampleco/hostile/application": { html: HOSTILE },
  "https://jobs.ashbyhq.com/exampleco/moved/application": { redirect: "https://evil.example/collect" },
  "https://evil.example/collect": { html: EVIL },
  "https://jobs.ashbyhq.com.evil.example/exampleco/application": { html: EVIL }
};

module.exports = async ({ ev, sleep, send, on }) => {
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  | " + extra : "")); };
  const H = helpers();
  const served = [];
  on("Fetch.requestPaused", (p) => {
    const u = p.request.url.split("#")[0], pg = PAGES[u];
    served.push(u);
    if (pg && pg.redirect) send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: 302, responseHeaders: [{ name: "Location", value: pg.redirect }], body: "" });
    else if (pg) send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: 200, responseHeaders: [{ name: "Content-Type", value: "text/html; charset=utf-8" }], body: Buffer.from(pg.html).toString("base64") });
    else send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: 404, responseHeaders: [{ name: "Content-Type", value: "text/plain" }], body: "" });
  });
  await send("Fetch.enable", { patterns: [{ urlPattern: "*" }] });
  const E = async (x) => { try { return await ev(x); } catch (e) { return "JSERR " + e.message; } };
  const go = async (url) => {
    await send("Page.navigate", { url });
    for (let i = 0; i < 40; i++) { await sleep(100); if ((await E("document.readyState==='complete'&&location.href!=='about:blank'")) === true) break; }
    await sleep(150);
  };
  // AssistActivity, as it runs: a new random key each time the screen opens; every 1.5 s (here 0.25 s) CALL "ask"; "none" puts the
  // engine in (the app's own address check first); then one "scan" or one "fill" per address, and the result read back through "ask".
  // Unlike the app, this asks CALL on every page, so the page-side check is tested on its own (as when a redirect lands between the two).
  const activity = async (url, scanMode, profile, allow, polls) => {
    const key = crypto.randomBytes(16).toString("hex"), name = "__uaplyAssist_" + key, log = { asks: [], injected: 0, result: null, name };
    const call = (act, p) => CALL + "(" + JSON.stringify(Object.assign({ name: name, allow: allow, act: act }, p ? { p: p, j: { co: "Example Co", role: "Analyst" }, mode: "assisted" } : {})) + ")";
    log.call = call;
    await go(url);
    for (let i = 0; i < (polls || 30); i++) {
      await sleep(250);
      const v = await E(call("ask"));
      log.asks.push(v);
      if (v === "off") continue;
      if (v === "none") {
        const href = await E("location.href");
        let okHost = false;
        try { const u = new URL(href); okHost = u.protocol === "https:" && allow.includes(u.hostname); } catch (e) {}
        if (okHost) { await E(wrap(key)); log.injected++; }
        continue;
      }
      let o = null;
      try { o = JSON.parse(v); } catch (e) { continue; }
      log.last = o;
      if (scanMode) { if (o.scan) { log.result = JSON.parse(o.scan); break; } if (!o.ran && o.n > 3) await E(call("scan", profile)); }
      else { if (o.rep) { log.result = JSON.parse(o.rep); break; } if (!o.ran && o.n > 3) await E(call("fill", profile)); }
    }
    return log;
  };
  const pageState = async () => JSON.parse(await E("JSON.stringify({seen:window.__seen||[],got:window.__got||[],hijack:window.__hijack||[],href:location.href," +
    "uaply:Object.getOwnPropertyNames(window).filter(function(k){return /^__uaplyAssist_/.test(k)})," +
    "values:[].slice.call(document.querySelectorAll('input:not([type=file]),textarea')).filter(function(e){return e.value}).map(function(e){return e.id+'='+e.value})," +
    "files:[].slice.call(document.querySelectorAll('input[type=file]')).map(function(e){return e.files.length})})"));

  // ---- what the app hands over, and how it calls in ----
  check("AssistActivity.CALL is there and needs no escaping", CALL.length > 100 && !/\\/.test(CALL));
  check("CALL reads the page's own address and answers 'off' before it touches anything the page could have planted",
    CALL.indexOf("location.protocol==='https:'") >= 0 && CALL.indexOf("return 'off'") >= 0 && CALL.indexOf("return 'off'") < CALL.indexOf("window[C.name]"));
  check("AssistActivity wraps the engine with this screen's random key, exactly as this test does", JAVA.includes(WRAP_SRC) && /new java\.security\.SecureRandom\(\)\.nextBytes/.test(JAVA));
  const code = JAVA.split("\n").filter((l) => !/^\s*(\*|\/\*\*|\/\/)/.test(l)).join("\n");
  check("AssistActivity no longer calls window.UAplyAssist or reads window.__uaplyScan / __uaplyRep", !/UAplyAssist\.|__uaplyScan|__uaplyRep|__uaplyAssistRan/.test(code));
  const body = (fn) => { const i = code.indexOf("private void " + fn + "("); return i < 0 ? "" : code.slice(i, code.indexOf("\n    }", i)); };
  check("inject, scan, fill and the UAply-resume choice each check the address first (onAllowedHost)", ["inject", "scan", "fill", "giveResume"].every((f) => /onAllowedHost\(\)/.test(body(f))),
    ["inject", "scan", "fill", "giveResume"].filter((f) => !/onAllowedHost\(\)/.test(body(f))).join(","));
  check("AssistPlugin allows this job's own page and only well-formed hosts from the app", /hosts\.add\(start\.toLowerCase/.test(PLUGIN) && /h\.matches\(/.test(PLUGIN));
  const allow = H.assistHosts(CFG, "https://jobs.ashbyhq.com/exampleco/moved/application");
  check("the allowed hosts: the hiring systems' own (assist-systems.json) and this job's page, never the site it moves to",
    ["jobs.ashbyhq.com", "job-boards.greenhouse.io", "boards.greenhouse.io", "jobs.lever.co", "apply.workable.com", "jobs.smartrecruiters.com"].every((h) => allow.includes(h)) && !allow.includes("evil.example"), allow.join(" "));
  const own = H.assistHosts(CFG, "https://careers.acme.example/jobs/77"), other = H.assistHosts(CFG, "https://careers.other.example/jobs/1");
  check("an employer's own careers page is allowed for that job only (not for another employer's job), and never over http",
    own.includes("careers.acme.example") && !other.includes("careers.acme.example") && !H.assistHosts(CFG, "http://careers.acme.example/jobs/77").includes("careers.acme.example"));
  const shape = H.assistShape(BEFORE);
  check("the scan is handed stand-ins, none of the person's details (a long saved answer, such as a cover letter, too)",
    leaked(JSON.stringify(shape)).length === 0 && !/Sam|Rivera|sam\.rivera/.test(JSON.stringify(shape)), leaked(JSON.stringify(shape)).join(","));
  check("...only what lists are matched against: place, school, degree, dates, yes/no answers, short saved answers (a choice)",
    shape.state === "PA" && shape.city === "Philadelphia" && shape.school === "Temple University" && shape.auth === "yes" && shape.answers["Which shift do you prefer?"] === "Day" && shape.answers["Cover letter"] === "A");
  check("the engine in a page that already has a 'UAplyAssist' installs under its own key and leaves the page's alone",
    await (async () => { await go("https://jobs.ashbyhq.com/exampleco/hostile/application"); const k = crypto.randomBytes(16).toString("hex"); await E(wrap(k)); return (await E("typeof window['__uaplyAssist_" + k + "'].run==='function'&&Object.isFrozen(window['__uaplyAssist_" + k + "'])&&!Object.getOwnPropertyDescriptor(window,'__uaplyAssist_" + k + "').writable&&window.UAplyAssist.fill.toString().indexOf('__got')>0&&__got.length===0")) === true; })());

  // ---- 1. the control: a normal form on the hiring system's host ----
  const PL = "https://jobs.ashbyhq.com/exampleco/plain/application";
  const s1 = await activity(PL, true, shape, allow);
  const sc1 = s1.result || {};
  check("control: the scan reads the form and asks the one question the profile cannot answer", (sc1.questions || []).map((q) => q.q).join("|") === "Describe a project you led", JSON.stringify(sc1.questions));
  check("control: ...and says which profile items the form asks for, and that it takes a resume",
    ["first", "last", "email", "phone", "linkedin"].every((k) => (sc1.keys || []).includes(k)) && sc1.resume === true, JSON.stringify(sc1.keys));
  let st = await pageState();
  check("control: while it was read, the page saw none of the person's details (only stand-ins)", leaked(st.seen.join("\n")).length === 0 && !st.seen.join("\n").includes("sam.rivera"), leaked(st.seen.join("\n")).join(","));
  const only1 = H.assistOnly(PERSON, sc1, ["Describe a project you led"]);
  check("control: the fill is handed only those items, the answer just given and the resume",
    Object.keys(only1).sort().join(",") === "answers,country,email,first,last,linkedin,name,phone,resume" && Object.keys(only1.answers).join("|") === "Describe a project you led", Object.keys(only1).sort().join(","));
  const f1 = await activity(PL, false, only1, allow);
  st = await pageState();
  check("control: the form is filled (and the resume attached)", (f1.result || {}).filled >= 6 && (f1.result || {}).resumeAttached === true && st.values.includes("first=Sam") && st.values.includes("proj=A help center I rebuilt"),
    JSON.stringify(f1.result) + " " + st.values.join(" "));
  check("control: ...and the page saw nothing it did not ask for (no address, pay, other answers, summary)",
    leaked(st.seen.join("\n"), ["phone", "phoneDigits", "linkedin", "resume", "resumeB64", "resumeName"]).length === 0, leaked(st.seen.join("\n"), ["phone", "phoneDigits", "linkedin", "resume", "resumeB64", "resumeName"]).join(","));

  // ---- 2. a hostile page on an allowed host ----
  const HO = "https://jobs.ashbyhq.com/exampleco/hostile/application";
  const s2 = await activity(HO, true, shape, allow);
  st = await pageState();
  const qs2 = ((s2.result || {}).questions || []).map((q) => q.q);
  check("hostile page: the scan still works, under the random name", !!s2.result && s2.injected === 1 && st.uaply.length === 1 && st.uaply[0] === s2.name, JSON.stringify(st.uaply));
  check("hostile page: its own window.UAplyAssist is never called, and the old globals are never read or written", st.got.length === 0, st.got.join(" / ").slice(0, 300));
  check("hostile page: it found UAply's name and tried to replace it, and could not", st.hijack.length === 1 && (await E("Object.isFrozen(window[" + JSON.stringify(s2.name) + "])&&window[" + JSON.stringify(s2.name) + "].run.toString().indexOf('__got')<0")) === true);
  check("hostile page: its own question ('Your bank password') never reaches UAply's question box", qs2.join("|") === "Describe a project you led", JSON.stringify(qs2));
  check("hostile page: while it was read, it saw none of the person's details", leaked(st.seen.join("\n")).length === 0 && !st.seen.join("\n").includes("sam.rivera"), leaked(st.seen.join("\n")).join(","));
  const only2 = H.assistOnly(PERSON, s2.result, ["Describe a project you led"]);
  check("hostile page: the fill is handed only its own fields' items (no phone, links, address, pay or resume)", Object.keys(only2).sort().join(",") === "answers,email,first,last,name", Object.keys(only2).sort().join(","));
  const f2 = await activity(HO, false, only2, allow);
  st = await pageState();
  const seen2 = st.seen.join("\n") + "\n" + st.got.join("\n");
  check("hostile page: filled with its own fields only", (f2.result || {}).filled === 4 && st.values.includes("email=sam.rivera.test@example.com"), JSON.stringify(f2.result));
  check("hostile page: watching every value typed, JSON.stringify and Object.keys, it got nothing beyond its own fields", leaked(seen2).length === 0, leaked(seen2).join(","));
  check("hostile page: its fake 'confirmed' (always yes) never makes the application Sent", f2.last && f2.last.c === false && st.got.length === 0, JSON.stringify(f2.last && f2.last.c));

  // ---- 3. a posting that redirects to another site ----
  const MV = "https://jobs.ashbyhq.com/exampleco/moved/application";
  const s3 = await activity(MV, true, shape, allow, 10);
  st = await pageState();
  check("redirect: it lands on the other site, and every call there answers 'off'", st.href === "https://evil.example/collect" && s3.asks.length === 10 && s3.asks.every((a) => a === "off"), st.href + " " + [...new Set(s3.asks)].join(","));
  check("redirect: the engine is never put in, nothing is read (the scan comes back empty)", s3.injected === 0 && !s3.result && st.uaply.length === 0);
  const only3 = H.assistOnly(PERSON, s3.result, []);
  check("redirect: so the fill is handed nothing at all", JSON.stringify(only3) === '{"answers":{}}', JSON.stringify(only3));
  const f3 = await activity(MV, false, only3, allow, 6);
  // the app's own address check failed and a fill with the whole profile went out anyway (a redirect at the wrong moment): still nothing
  const race = [await E(f3.call("fill", PERSON)), await E(f3.call("scan", PERSON))];
  await sleep(300);
  st = await pageState();
  check("redirect: even a fill sent with the whole profile at the wrong moment answers 'off'", f3.asks.every((a) => a === "off") && race.join(",") === "off,off", race.join(","));
  check("redirect: the other site received nothing: no call, no value typed, no field filled, no file, nothing it could watch",
    st.got.length === 0 && st.values.length === 0 && st.files.every((x) => x === 0) && leaked(st.seen.join("\n")).length === 0 && !/sam|rivera/i.test(st.seen.join("\n")),
    st.got.concat(st.values).join(" / ").slice(0, 200) + " " + leaked(st.seen.join("\n")).join(","));

  // ---- 4. a look-alike host ----
  const s4 = await activity("https://jobs.ashbyhq.com.evil.example/exampleco/application", true, shape, allow, 6);
  st = await pageState();
  check("look-alike host (jobs.ashbyhq.com.evil.example): 'off', nothing put in, nothing received", s4.asks.every((a) => a === "off") && st.uaply.length === 0 && st.got.length === 0 && st.values.length === 0);
  check("(every page was served here, nothing went to the network)", served.every((u) => PAGES[u] || /favicon/.test(u)), served.filter((u) => !PAGES[u]).join(" "));
  console.log("\n" + (n - bad) + "/" + n + " passed");
  if (bad) process.exitCode = 1;
};
module.exports.limitMs = 240000;
