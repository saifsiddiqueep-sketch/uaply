// The sign-in gate on a running site, read only (October 22, 2026: nobody reaches anything on the site without an account).
//   node tools/cdp.js tools/ui-gate-live.js --base https://uaply.net                (both sizes: 390x844 and 1280x800)
//   node tools/cdp.js tools/ui-gate-live.js --base http://127.0.0.1:21950 --server-gated
// It never signs up, signs in, sends email or changes anything: every request the app itself would send that is not a GET is answered
// in the browser instead (and listed), and the address checks below send only GETs and POSTs whose body is not an object, which the
// server refuses before any handler reads it. What it proves, at each size, in a clean browser with no session:
// 1. the first paint and every frame of the first 3 s show the sign-up card and nothing else (no header, bottom bar, deck, job card,
//    Job Tracker, Help or Hiring mode drawn), and no job's title is anywhere in the page's DOM text (scripts aside);
// 2. the card's order: First name and Last name, then the Password row under both;
// 3. Terms, Privacy, Delete an account and Help and support on the card answer (an HTML page, no account needed);
// 4. the data addresses answer 401 to a signed-out request (/api/jobs, /api/apply, /api/apply/plan, /api/apply/mark, /api/chat,
//    /api/profile/resume, /api/outbox, /api/feedback, /api/employer/me) while /healthz, /api/auth/providers, /api/apply/config,
//    /api/chat/config and /api/billing/status answer 200. Until the server half of the gate is in, the 401 lines print as
//    "WAIT server not yet gated" and do not fail; --server-gated (or GATE_SERVER=1) makes them FAIL. The owner's pages (/outbox,
//    /api/outbox, /feedback, /setup, /api/feed-health) must answer 401 or 403 on a public server and are open on this computer;
// 5. the service worker keeps nothing that could show a job to a signed-out visitor: its cache holds only the offline screen and its
//    icon, no /api/ answer and no page, and its code saves nothing else (no cache.put) and answers page loads from the network first.
const fs = require("fs");
const path = require("path");
const http = require("http"), https = require("https");
// the requests from here go through Node's own http module, one connection each: Node 24's built-in fetch, next to cdp.js's socket to
// Chrome, crashed with an internal assertion (undici "assert(!this.paused)") on Windows. Same shape as fetch for what this file uses.
function fetch(url, o) {
  o = o || {};
  return new Promise((resolve, reject) => {
    const u = new URL(url), lib = u.protocol === "https:" ? https : http, body = o.body === undefined ? null : Buffer.from(String(o.body));
    const req = lib.request(u, { method: o.method || "GET", headers: Object.assign({ Connection: "close" }, o.headers || {}, body ? { "Content-Length": body.length } : {}),
      agent: false, timeout: 30000 }, (res) => {
      const chunks = []; res.on("data", (c) => chunks.push(c));
      res.on("end", () => { const t = Buffer.concat(chunks).toString("utf8");
        resolve({ status: res.statusCode, ok: res.statusCode >= 200 && res.statusCode < 300, headers: { get: (k) => res.headers[String(k).toLowerCase()] || null }, text: async () => t }); });
    });
    req.on("timeout", () => req.destroy(Object.assign(new Error("timed out"), { name: "TimeoutError" })));
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}
function arg(name, dflt) { const i = process.argv.indexOf("--" + name); return i > 2 && i + 1 < process.argv.length ? process.argv[i + 1] : dflt; }
const BASE = String(arg("base", process.env.BASE || "")).replace(/\/+$/, "");
const SERVER_GATED = process.argv.includes("--server-gated") || process.env.GATE_SERVER === "1";
const OUT = arg("out", "");
const SIZES = [[390, 844, true], [1280, 800, false]];
const DATA_GET = ["/api/jobs", "/api/employer/me"];
// the owner's pages (serve.py OWNER_PAGES): behind the owner check, not the sign-in gate. On a public server a visitor gets 401 (an
// owner password is set) or 403 (none is); on this computer (not public) they are open by design: the test inbox is how a code is read
// before anyone is signed in. Which one this server is comes from /api/status "public".
const OWNER = ["/outbox", "/api/outbox", "/feedback", "/setup", "/api/feed-health"];
const DATA_POST = ["/api/apply", "/api/apply/plan", "/api/apply/mark", "/api/chat", "/api/profile/resume", "/api/feedback"];
const OPEN = ["/healthz", "/api/auth/providers", "/api/apply/config", "/api/chat/config", "/api/billing/status"];

module.exports = async ({ ev, sleep, send, on, logs, shot }) => {
  const count = { PASS: 0, FAIL: 0, WAIT: 0 };
  const out = (k, name, extra) => { count[k]++; console.log(k + " " + name + (extra ? "  -> " + String(extra).slice(0, 400) : "")); };
  const check = (name, ok, extra) => out(ok ? "PASS" : "FAIL", name, ok ? "" : extra);
  const info = (t) => console.log("     " + t);
  if (!/^https?:\/\/[^/]+$/.test(BASE)) { console.log("TEST SCRIPT FAILED: give the site with --base https://uaply.net"); return; }
  const F = "document.querySelector('iframe').contentDocument", FW = "(document.querySelector('iframe')||{}).contentWindow";
  const q = (sel) => F + ".querySelector(" + JSON.stringify(sel) + ")";
  const snap = async (n) => { if (OUT) { fs.mkdirSync(OUT, { recursive: true }); await shot(path.join(OUT, n + ".png")); } };

  // the app's own writes never leave the browser (the probes below are fetched from Node, not by the page)
  const held = [];
  await send("Fetch.enable", { patterns: [{ urlPattern: "*", requestStage: "Request" }] });
  on("Fetch.requestPaused", (p) => {
    let u = null; try { u = new URL(p.request.url); } catch (e) {}
    if (u && u.origin === BASE && !/^(GET|HEAD|OPTIONS)$/.test(p.request.method)) {
      held.push(p.request.method + " " + u.pathname);
      send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: 503, responseHeaders: [{ name: "Content-Type", value: "application/json" }],
        body: Buffer.from('{"error":"held back by ui-gate-live (read only)"}').toString("base64") });
    } else send("Fetch.continueRequest", { requestId: p.requestId });
  });

  console.log("UAply gate check of " + BASE + " at " + new Date().toISOString().slice(0, 19).replace("T", " ") + " UTC" + (SERVER_GATED ? " (server gate expected)" : ""));
  const t0 = Date.now();
  let hz = "no answer"; try { const r = await fetch(BASE + "/healthz", {}); await r.text(); hz = "HTTP " + r.status; } catch (e) { hz = "no answer (" + e.name + ")"; }
  info("healthz: " + hz + " in " + ((Date.now() - t0) / 1000).toFixed(2) + " s");

  // ---- 4. the addresses, signed out (no cookie: fetched from here, not from a browser) ----
  const hdr = { Origin: BASE, "Content-Type": "application/json" };
  for (const p of OPEN) {
    let s = 0; try { const r = await fetch(BASE + p, {}); await r.text(); s = r.status; } catch (e) {}
    check("signed out, " + p + " answers 200 (it must work before an account exists)", s === 200, "HTTP " + s);
  }
  let pub = null;
  try { const r = await fetch(BASE + "/api/status", {}); const j = JSON.parse(await r.text()); if (typeof j.public === "boolean") pub = j.public; } catch (e) {}
  if (pub === null) pub = !/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(BASE);      // an older server without "public": judge by the address
  info("this server is " + (pub ? "public: the owner's pages must be closed to a visitor" : "on this computer only: the owner's pages are open by design"));
  for (const p of OWNER) {
    let s = 0; try { const r = await fetch(BASE + p, {}); await r.text(); s = r.status; } catch (e) {}
    if (pub) check("signed out, the owner's page " + p + " is closed to a visitor (401 with an owner password, 403 without)", s === 401 || s === 403, "HTTP " + s);
    else check("this computer: the owner's page " + p + " answers (open to the owner here by design)", s === 200, "HTTP " + s);
  }
  for (const [m, p] of DATA_GET.map((x) => ["GET", x]).concat(DATA_POST.map((x) => ["POST", x]))) {
    let s = 0;
    try { const r = await fetch(BASE + p, { method: m, headers: hdr, body: m === "POST" ? '"read-only probe: not an object"' : undefined }); await r.text(); s = r.status; } catch (e) {}
    const name = "signed out, " + m + " " + p + " answers 401";
    if (s === 401) check(name, true);
    else if (SERVER_GATED) check(name, false, "HTTP " + s);
    else out("WAIT", name + " (server not yet gated)", "HTTP " + s);
  }

  for (const [W, H, phone] of SIZES) {
    const tag = "[" + W + "x" + H + "] ";
    await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: phone ? 3 : 1, mobile: phone });
    await send("Emulation.setTouchEmulationEnabled", { enabled: phone });
    await send("Network.clearBrowserCookies");
    await send("Storage.clearDataForOrigin", { origin: BASE, storageTypes: "all" });
    const before = logs.length;

    // ---- 1. the first paint and the first 3 s: only the card ----
    const seen = () => ev("(()=>{try{const d=" + F + ";if(!d||!d.body)return null;const w=d.defaultView,acct=d.getElementById('acctSec');" +
      "const drawn=(s)=>[...d.querySelectorAll(s)].filter(e=>e.getClientRects().length&&w.getComputedStyle(e).visibility!=='hidden').length;" +
      "const outside=acct?[...d.body.querySelectorAll('*')].filter(e=>!acct.contains(e)&&!e.contains(acct)&&e.getClientRects().length&&w.getComputedStyle(e).visibility!=='hidden'&&!/^(SCRIPT|STYLE|LINK|META|NOSCRIPT)$/.test(e.tagName)).map(e=>(e.tagName+'#'+e.id+'.'+e.className).slice(0,50)):['(no Account card yet)'];" +
      "const roles=(w.__uaply&&w.__uaply.JOBS||[]).map(j=>String(j.role||'')).filter(r=>r.length>6);" +
      "const walk=d.createTreeWalker(d.body,NodeFilter.SHOW_TEXT,{acceptNode:n=>/^(SCRIPT|STYLE|NOSCRIPT)$/.test(n.parentNode.tagName)?2:1});let txt='';while(walk.nextNode())txt+=walk.currentNode.nodeValue+' ';" +
      "return {card:!!d.querySelector('.sg-card'),header:drawn('header.bar'),nav:drawn('#bnav'),deck:drawn('#pane-swipe'),cards:drawn('.card'),track:drawn('#pane-track'),help:drawn('#uaChatBtn'),hire:drawn('#hireSec,[data-hire]'),outside:outside.slice(0,6),nJobs:roles.length,jobInDom:roles.filter(r=>txt.indexOf(r)>-1).slice(0,3)}}catch(e){return null}})()");
    const behind = (s) => !s || s.header || s.nav || s.deck || s.cards || s.track || s.help || s.hire || s.outside.length;
    await send("Page.navigate", { url: BASE + "/" });
    const frames = [], end = Date.now() + 3000;
    while (Date.now() < end) { const s = await seen(); if (s && s.card) frames.push(s); await sleep(100); }
    for (let i = 0; i < 40 && !(await ev("!!(" + FW + "&&" + FW + ".__uaply&&" + q(".sg-card") + ")").catch(() => false)); i++) await sleep(250);
    await sleep(800);
    const last = await seen();
    const shown = frames.filter((s) => behind(s));
    check(tag + "the first paint is the sign-up card: in every frame of the first 3 s nothing else is drawn (no header, bottom bar, deck, job card, Job Tracker, Help, Hiring mode)",
      frames.length > 0 && shown.length === 0, frames.length ? JSON.stringify(shown[0]) : "the card never appeared in the first 3 s");
    check(tag + "...and once loaded, still only the card", !!last && last.card && !behind(last), JSON.stringify(last));
    check(tag + "no job's title is anywhere in the page's text, drawn or hidden", !!last && last.jobInDom.length === 0, JSON.stringify(last && last.jobInDom));
    info(tag + "jobs held by the app behind the gate: " + (last ? last.nJobs : "?") + (last && !last.nJobs ? " (none: the server sent no jobs to a signed-out visitor)" : ""));
    await snap(W + "-gate");

    // ---- 2. the card's order: First name, Last name, then the Password row under both ----
    const geo = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ",r=(s)=>{const e=d.querySelector(s);if(!e||!e.getClientRects().length)return null;const b=e.getBoundingClientRect();return {t:Math.round(b.top),b:Math.round(b.bottom),l:Math.round(b.left)}};" +
      "return {fn:r('.sg-fn'),ln:r('.sg-ln'),pw:r('.sg-pw'),email:r('[data-email]')}})())"));
    check(tag + "the Password row sits under First name and Last name", !!(geo.fn && geo.ln && geo.pw) && geo.pw.t >= Math.max(geo.fn.b, geo.ln.b) - 1, JSON.stringify(geo));

    // ---- 3. the card's links answer without an account ----
    const links = JSON.parse(await ev("JSON.stringify([...(" + F + ").querySelectorAll('.sg-legal a, .sg-agree a')].map(a=>({t:a.textContent.trim(),h:a.href})))"));
    const want = { Terms: /Terms/, Privacy: /Privacy/, deletion: /Delete/, "help and support": /Help|Support/ };
    for (const [k, rx] of Object.entries(want)) {
      const l = links.find((x) => rx.test(x.t));
      let s = "no link";
      if (l) { try { const r = await fetch(l.h, {}); await r.text(); s = r.status + " " + (r.headers.get("content-type") || ""); } catch (e) { s = "no answer"; } }
      check(tag + k + " opens from the card without an account (" + (l ? new URL(l.h).pathname : "?") + ")", /^200 text\/html/.test(s), s);
    }

    // ---- 5. the service worker keeps no job page ----
    const sw = JSON.parse(await ev("(async()=>{try{if(!('serviceWorker' in navigator))return JSON.stringify({sw:'none'});const r=await Promise.race([navigator.serviceWorker.ready,new Promise(x=>setTimeout(()=>x(null),8000))]);" +
      "const ks=await caches.keys();const all=[];for(const k of ks){const c=await caches.open(k);for(const q of await c.keys())all.push(k+' '+new URL(q.url).pathname)}" +
      "return JSON.stringify({sw:r&&r.active?r.active.scriptURL:'not registered',cached:all})}catch(e){return JSON.stringify({sw:'error '+e.message})}})()"));
    const bad = (sw.cached || []).filter((c) => !/ \/(uaply-offline\.html|uaply-icon-192\.png)$/.test(c));
    check(tag + "the service worker's cache holds only the offline screen and its icon: no page, no /api/ answer, no job", bad.length === 0, JSON.stringify(sw));
    // and what the worker would do with a page load: it may answer one only with the saved offline screen (network first, nothing
    // else saved); a worker that put pages or /api/ answers into its cache could later show a job to someone signed out
    let src = "";
    try { const r = await fetch(BASE + "/uaply-sw.js", {}); src = r.ok ? await r.text() : ""; } catch (e) {}
    if (!src) info(tag + "no service worker at " + BASE + "/uaply-sw.js");
    else check(tag + "the service worker never saves a page or an /api/ answer (no cache.put; it keeps only its shell) and answers a page load from the network first",
      !/\.put\(/.test(src) && /SHELL\s*=\s*\[PAGE,\s*ICON\]/.test(src) && /respondWith\(fetch\(req\)/.test(src), "worker " + src.length + " bytes; " + (/\.put\(/.test(src) ? "it calls put()" : "no put()"));
    const errs = logs.slice(before).filter((l) => !/favicon|ERR_FILE_NOT_FOUND|401|held back/.test(l));
    check(tag + "no script errors", errs.length === 0, errs.join(" | "));
  }
  info("read only: held back " + held.length + " request(s) the app would have sent" + (held.length ? ": " + [...new Set(held)].join(", ") : ""));
  console.log("\n" + count.PASS + " passed, " + count.FAIL + " failed, " + count.WAIT + " waiting (server not yet gated)");
  console.log(count.PASS + " / " + (count.PASS + count.FAIL));
};
