// A stranger's first visit to a running UAply site, in a real browser, at phone size (390x844) and computer size (1280x800). Run it after
// every deploy, next to tools/live-check.py:
//   node tools/cdp.js tools/ui-live.js --base https://uaply.onrender.com
//   node tools/cdp.js tools/ui-live.js --base https://uaply.onrender.com --email you+uaply1@gmail.com --code-file code.txt
//   node tools/cdp.js tools/ui-live.js --base https://<a server with Stripe TEST keys> --email you+uaply1@gmail.com --code-file code.txt --stripe-test
// Each size starts as a clean browser and checks: the agreement box at first open, Got it on the tips, a swipe, the Account screen's wording
// (with email off it must say email is not switched on yet, never "Cannot reach UAply"), the Continue with Google button only when Google is
// configured (and that it leads to Google's sign-in page; it never signs in to a Google account), Plan & billing ("free during early access"
// without Stripe keys, real buttons with keys) and the help assistant.
// --email ADDRESS     signs that address up once (one sign-up per run per address), then waits for the 6-digit code: --code 123456, or
//                     --code-file PATH, which is read every 2 seconds for 3 minutes (type the code from the email into that file). Verifies
//                     it, swipes right on one card (only when the server is in test delivery mode, so nothing reaches an employer) and checks
//                     the Applied list.
// --stripe-test       with Stripe TEST keys on the server: Choose Plus, Stripe Checkout with the test card 4242 4242 4242 4242 (12/34, CVC 123,
//                     ZIP 19104), the plan must read Plus; then a second account (--email2, default: the first address with "2" added to its
//                     +tag; --code2 or the same --code-file) tries the declined test card 4000 0000 0000 0002 and must stay on Free. Refused on
//                     a server with live keys: this tool never uses a real card. If Stripe shows a captcha the tool stops: it never solves one.
//                     The card fields are found in Stripe's page or inside its iframes and typed as keystrokes (tools/stripe-checkout.js, tried
//                     against a stand-in by tools/ui-stripe-form.js); after the 4242 card the plan must read Plus within 60 s (the webhook).
// --shields          runs as Brave Shields would: third-party cookies blocked (cdp.js starts Chrome with --test-third-party-cookie-phaseout)
//                     and every request checked against the ad-block filter lists in --lists DIR (EasyList, EasyPrivacy, uBlock filters,
//                     brave/adblock-lists: plain .txt files you download), first-party requests too (Brave's "aggressive" setting). A blocked
//                     UAply request, an app frame that is not same-origin, or storage that throws fails the run. Run it with and without.
// --read-only        never changes anything on the site (tools/launch-smoke.sh uses it on the live site): every request the app would
//                     send to it that is not a GET is answered here in the browser and never leaves it (the Pass swipe's record, the
//                     read-ahead of an employer's form, feedback), except the help assistant's question, which the site answers from its
//                     articles and does not store (chat_api.py). The run lists what it held back. Not with --email or --stripe-test.
// --out DIR           also saves a screenshot of each step there.   --google-host HOST   where Google's page must be (default accounts.google.com).
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const stripe = require("./stripe-checkout.js");          // fills Stripe Checkout, card fields in Stripe's iframes included (tested by ui-stripe-form.js)

function arg(name, dflt) { const i = process.argv.indexOf("--" + name); return i > 2 && i + 1 < process.argv.length ? process.argv[i + 1] : dflt; }
const flag = (name) => process.argv.includes("--" + name);
const BASE = String(arg("base", process.env.BASE || "")).replace(/\/+$/, "");
const EMAIL = (arg("email", "") || "").trim().toLowerCase();
const STRIPE = flag("stripe-test");
const OUT = arg("out", "");
const GHOST = arg("google-host", "accounts.google.com");
const SHIELDS = flag("shields"), LISTS = arg("lists", "");
const READONLY = flag("read-only");
function secondAddress(a) {                         // you+tag@gmail.com -> you+tag2@gmail.com; you@gmail.com -> you+uaply2@gmail.com
  const [user, dom] = a.split("@");
  return (user.includes("+") ? user + "2" : user + "+uaply2") + "@" + dom;
}
const EMAIL2 = (arg("email2", "") || (EMAIL ? secondAddress(EMAIL) : "")).trim().toLowerCase();
// waiting on a person for one or two codes: ask cdp.js for more time than its usual 9 minutes
module.exports = async (api) => main(api);
module.exports.limitMs = (9 + (EMAIL ? 4 : 0) + (STRIPE ? 9 : 0)) * 60000;

const WRONG = /Cannot reach UAply|check your (internet|connection)|Something went wrong|undefined|\[object Object\]|\bNaN\b/i;
const SIZES = [[390, 844, true], [1280, 800, false]];

async function main(api) {
  const { ev, sleep, nav, shot, logs, send, on } = api;
  const count = { PASS: 0, FAIL: 0, SKIP: 0 };
  const out = (kind, name, extra) => { count[kind]++; console.log(kind + " " + name + (extra ? "  -> " + extra : "")); };
  const check = (name, ok, extra) => { out(ok ? "PASS" : "FAIL", name, ok ? "" : extra); return ok; };
  const skip = (name, needs) => out("SKIP", name + " (needs " + needs + ")");
  const info = (t) => console.log("     " + t);
  if (!/^https?:\/\/[^/]+$/.test(BASE)) { console.log("TEST SCRIPT FAILED: give the site with --base https://uaply.onrender.com"); return; }
  if (EMAIL && !/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/.test(EMAIL)) { console.log("TEST SCRIPT FAILED: --email does not look like an email address"); return; }
  const F = "document.querySelector('iframe').contentDocument";
  const NL = "String.fromCharCode(10)";
  const appText = () => ev("(()=>{try{return (" + F + ").body.innerText.split(" + NL + ").join(' ')}catch(e){return ''}})()");
  const secText = (sel) => ev("(()=>{try{const e=" + F + ".querySelector(" + JSON.stringify(sel) + ");return e?e.innerText.split(/\\s+/).join(' '):''}catch(x){return ''}})()");
  const has = (sel) => ev("(()=>{try{return !!" + F + ".querySelector(" + JSON.stringify(sel) + ")}catch(e){return false}})()");
  const click = (sel) => ev("(()=>{try{const e=" + F + ".querySelector(" + JSON.stringify(sel) + ");if(!e)return false;e.click();return true}catch(x){return false}})()");
  const setVal = (id, v) => ev("(()=>{const e=" + F + ".getElementById('" + id + "');if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return true})()");
  const tick = (id) => ev("(()=>{const c=" + F + ".getElementById('" + id + "');if(!c)return false;c.checked=true;c.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  const json = (p, opts) => ev("fetch(" + JSON.stringify(p) + (opts ? "," + JSON.stringify(opts) : "") + ").then(async r=>({s:r.status,j:await r.json().catch(()=>null)})).catch(e=>({s:0,j:null}))");
  const snap = async (name) => { if (OUT) { fs.mkdirSync(OUT, { recursive: true }); await shot(path.join(OUT, name + ".png")); } };
  const waitFor = async (fn, ms) => { const end = Date.now() + ms; let v; while (Date.now() < end) { v = await fn(); if (v) return v; await sleep(500); } return v; };
  const menu = async (tab, item) => {                 // open a bottom-bar menu and pick an item, the way a tap does
    await click("#" + tab); await sleep(450);
    let ok = await click(".nwrap[data-k=" + tab.replace("nb-", "") + "] .nitem[data-v=" + item + "]");
    if (!ok) ok = await ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')===" + JSON.stringify(item) + ");if(!e)return false;e.click();return true})()");
    await sleep(900);
    return ok;
  };
  const fresh = async () => {                         // a clean browser: no cookies, no saved agreement, no profile
    await send("Network.clearBrowserCookies");
    await send("Storage.clearDataForOrigin", { origin: BASE, storageTypes: "all" });
    await nav(BASE + "/");
    await waitFor(() => has("#nb-prof"), 60000);         // patient: a cold server can take a while to answer the first page
    await sleep(1500);
  };
  const agree = async () => {
    await waitFor(() => has("#kcYes"), 8000);
    await click("#kcYes"); await sleep(600);
    await ev("(()=>{try{const b=[...(" + F + ").querySelectorAll('#locAsk button')].find(x=>/Not now/.test(x.innerText));if(b)b.click()}catch(e){}})()");
    await click("#tipsClose"); await sleep(300);
  };

  const blocked = [], held = [];
  if (READONLY && (EMAIL || STRIPE)) { console.log("TEST SCRIPT FAILED: --read-only cannot sign up or buy: leave out --email and --stripe-test"); return; }
  // --read-only: a request to the site that could change something is answered here and never sent (see the top of this file)
  const hold = (p) => {
    if (!READONLY || /^(GET|HEAD|OPTIONS)$/.test(p.request.method)) return false;
    let u; try { u = new URL(p.request.url); } catch (e) { return false; }
    if (u.origin !== new URL(BASE).origin || u.pathname === "/api/chat") return false;
    held.push(p.request.method + " " + u.pathname);
    const ok = u.pathname === "/api/decision" || u.pathname === "/api/feedback";
    const body = ok ? '{"ok":true}' : '{"error":"Held back by ui-live --read-only: nothing was sent to the site.","code":"read_only"}';
    send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: ok ? 200 : 503, responseHeaders: [{ name: "Content-Type", value: "application/json" }],
      body: Buffer.from(body).toString("base64") });
    return true;
  };
  let eng = null, sh = null;
  if (SHIELDS) {
    if (!LISTS || !fs.existsSync(LISTS)) { console.log("TEST SCRIPT FAILED: --shields needs --lists DIR with the filter lists (.txt)"); return; }
    sh = require("./shields.js"); eng = sh.create(LISTS);
    info("shields mode: third-party cookies blocked, " + eng.size + " filter rules from " + LISTS + ", applied to first-party requests too");
  }
  if (READONLY) info("read-only: requests that could change the site are answered in the browser and never sent (the help question is sent: it is not stored)");
  if (SHIELDS || READONLY) {
    await send("Fetch.enable", { patterns: [{ urlPattern: "*", requestStage: "Request" }] });
    on("Fetch.requestPaused", (p) => {
      if (hold(p)) return;
      if (!SHIELDS) { send("Fetch.continueRequest", { requestId: p.requestId }); return; }
      let rule = null;
      try { if (/^https?:/.test(p.request.url)) rule = eng.match(p.request.url, sh.CDP_TYPES[p.resourceType] || "other", BASE + "/", true); } catch (e) {}
      if (rule) { blocked.push(p.request.url + "  by " + rule); send("Fetch.failRequest", { requestId: p.requestId, errorReason: "BlockedByClient" }); }
      else send("Fetch.continueRequest", { requestId: p.requestId });
    });
  }
  console.log("UAply browser check of " + BASE + (SHIELDS ? " (shields mode)" : "") + " at " + new Date().toISOString().slice(0, 19).replace("T", " ") + " UTC");
  await send("Network.enable");
  // one timed health probe first, so a slow (cold) server is named here instead of looking like a fault of the site further down
  {
    const t0 = Date.now();
    let hs = "no answer";
    try { const r = await fetch(BASE + "/healthz", { signal: AbortSignal.timeout(60000) }); hs = "HTTP " + r.status; } catch (e) { hs = "no answer (" + (e.name || "error") + ")"; }
    const secs = (Date.now() - t0) / 1000;
    info("healthz: " + hs + " in " + secs.toFixed(2) + " s" + (secs > 2 ? " (a slow server: the waits below are patient, up to 60 s for the first job card)" : ""));
  }
  await nav(BASE + "/healthz");
  // what the server says is on (/api/status, or the older endpoints the app itself reads)
  let st = await json("/api/status");
  if (!(st.s === 200 && st.j && st.j.ok)) {
    const p = (await json("/api/auth/providers")).j || {}, b = (await json("/api/billing/status")).j || {};
    st = { s: 200, j: { email: !!p.canEmail, google: !!p.googleRedirect, googleButton: !!p.google, payments: !!b.enabled, paymentsTest: !!(b.enabled && b.test), old: true } };
  }
  const S = st.j;
  const cfg = (await json("/api/apply/config")).j || {};
  info("server says" + (S.old ? " (no /api/status on this deploy yet)" : "") + ": email " + (S.email ? "on" : "off") + ", Google " + (S.google ? "on" : S.googleButton ? "button only" : "off") +
    ", payments " + (S.payments ? "on (" + (S.paymentsTest ? "test" : "LIVE") + " mode)" : "off") + ", delivery " + (cfg.mode || "?"));

  for (const [W, H, phone] of SIZES) {
    const tag = "[" + W + "x" + H + "] ";
    await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: phone ? 3 : 1, mobile: phone });
    await send("Emulation.setTouchEmulationEnabled", { enabled: phone });
    const before = logs.length;
    await fresh();
    if (SHIELDS) {
      const fr = await ev("(()=>{const w=document.querySelector('iframe').contentWindow;let ls='ok';try{w.localStorage.setItem('uaply.t','1');w.localStorage.removeItem('uaply.t')}catch(e){ls=e.name}return JSON.stringify({origin:w.origin,ls})})()");
      const o = JSON.parse(fr || "{}");
      check(tag + "shields: the app frame is same-origin with the site (its cookies and storage are first-party)", o.origin === new URL(BASE).origin, fr);
      check(tag + "shields: the app's storage works", o.ls === "ok", fr);
    }
    // 1. the agreement, at first open
    const box = await waitFor(() => secText("#kitConsent"), 8000);
    check(tag + "a clean browser is asked for the agreement at first open", /Before you start swiping/.test(box || ""), (box || "no box").slice(0, 80));
    check(tag + "the agreement links the Terms, Privacy Policy and AI pages", (await ev("(" + F + ").querySelectorAll('#kitConsent a[href*=legal]').length")) >= 3, "");
    await snap(W + "-1-agreement");
    await click("#kcYes"); await sleep(700);
    check(tag + "Agree closes the box", !(await has("#kcYes")), "");
    await ev("(()=>{try{const b=[...(" + F + ").querySelectorAll('#locAsk button')].find(x=>/Not now/.test(x.innerText));if(b)b.click()}catch(e){}})()"); await sleep(300);
    // 2. Got it
    const tipsShown = await ev("(()=>{const t=" + F + ".getElementById('tips');return !!(t&&t.offsetParent)})()");
    await click("#tipsClose"); await sleep(400);
    check(tag + "the tips line shows and Got it closes it", tipsShown && !(await ev("(()=>{const t=" + F + ".getElementById('tips');return !!(t&&t.offsetParent)})()")), "shown " + tipsShown);
    // 3. a swipe (left: Pass, which sends nothing to anyone). The first job card is waited for patiently: a cold server can take many
    // seconds to send the job list (the October 22 dry run: healthz 6 s, no card yet after the old short wait, 6 of 31 checks failed)
    const cardAt = Date.now();
    const top1 = await waitFor(() => ev("(()=>{const c=" + F + ".querySelector('.card.top h2');return c?c.textContent.trim():''})()"), 60000);
    info(tag + "the first job card was there after " + ((Date.now() - cardAt) / 1000).toFixed(1) + " s" + (top1 ? "" : " (none within 60 s)"));
    check(tag + "the deck shows a real job card", !!top1, "no card");
    await click("#btnNo"); await sleep(1200);
    const top2 = await ev("(()=>{const c=" + F + ".querySelector('.card.top h2');return c?c.textContent.trim():''})()");
    check(tag + "Pass moves to the next card", !!top2 && top2 !== top1, JSON.stringify([top1, top2]));
    info(tag + "cards: " + JSON.stringify(top1).slice(0, 60) + " then " + JSON.stringify(top2).slice(0, 60));
    // 4. the Account screen
    let opened = await menu("nb-prof", "account");
    if (!(await has("#sEmail"))) { await click("#hdrAcct"); await sleep(900); opened = true; }
    const acct = await secText("#acctSec");
    check(tag + "Account shows the real sign-up form", opened && (await has("#sEmail")) && (await has("#sAgree")), acct.slice(0, 100));
    check(tag + "Account never says 'Cannot reach UAply' or 'check your internet'", !WRONG.test(acct), (acct.match(WRONG) || [""])[0]);
    if (S.email) check(tag + "email is on: Account promises a receipt for each swipe right", /each swipe right emails you a receipt/.test(acct) && !/Email is not switched on/.test(acct), acct.slice(0, 160));
    else check(tag + "email is off: Account says email is not switched on yet (and promises no receipt)", /Email is not switched on for this site yet/.test(acct),
      (acct.match(/[^.]*each swipe right emails you a receipt[^.]*\./) || [""])[0].trim() ? "it promises instead: \"" + acct.match(/[^.]*each swipe right emails you a receipt[^.]*\./)[0].trim() + "\"" : acct.slice(0, 160));
    // 5. Continue with Google: present only when the server has the client ID and secret
    const gArea = await has("#gBtn"), gButton = await has("[data-auth=gsign]");
    if (S.google) {
      check(tag + "Google is configured: Continue with Google and its 18+ box are there", gArea && gButton && (await has("#gAgree")), "area " + gArea + ", button " + gButton);
    } else {
      check(tag + "Google is not configured: no Continue with Google anywhere", !gArea && !/Continue with Google/.test(acct), acct.match(/.{0,40}Google.{0,40}/) ? acct.match(/.{0,40}Google.{0,40}/)[0] : "");
    }
    await snap(W + "-2-account");
    // 6. Plan & billing
    await menu("nb-prof", "plan");
    const plan = await secText("#acctSec");
    const buy = await ev("(" + F + ").querySelectorAll('[data-bill=plus],[data-bill=pro],[data-bill=signin]').length");
    if (S.payments) check(tag + "payments are on: Plan & billing offers Plus and Pro (Sign in to choose)", buy === 2 && !/free during early access/.test(plan) && (!S.paymentsTest || /Test mode: no real charges/.test(plan)), buy + " buttons; " + plan.slice(0, 120));
    else check(tag + "payments are off: Plan & billing says free during early access, no buttons", buy === 0 && /Paid plans are coming\. UAply is free during early access\./.test(plan) && /Current plan: Free \(early access\)/.test(plan), buy + " buttons; " + plan.slice(0, 120));
    check(tag + "Plan & billing has no 'Cannot reach' or broken text", !WRONG.test(plan), (plan.match(WRONG) || [""])[0]);
    await snap(W + "-3-plan");
    // 7. the help assistant
    await click("#uaChatBtn"); await sleep(700);
    const n0 = (await secText("#uaChatLog")).length;
    await ev("(()=>{const d=" + F + ",i=d.getElementById('uaChatIn');if(!i)return;i.value='How do I apply?';d.getElementById('uaChatF').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))})()");
    const ans = await waitFor(async () => { const t = await secText("#uaChatLog"); return t.length > n0 + 60 && /swipe/i.test(t.slice(n0)) ? t : ""; }, 15000);
    check(tag + "the help assistant answers 'How do I apply?'", !!ans && !WRONG.test(ans.slice(n0)), (ans || await secText("#uaChatLog")).slice(-140));
    await snap(W + "-4-help");
    await click("#uaChatX"); await sleep(300);
    // 8. Continue with Google leads to Google's own page (checked once, at phone size; it never signs in)
    if (S.google && phone) {
      await menu("nb-prof", "account");
      await tick("gAgree");
      const seen = [];
      on("Network.requestWillBeSent", (p) => { if (p.type === "Document") seen.push(p.request.url); });
      await click("[data-auth=gsign]");
      const hit = await waitFor(() => seen.find((u) => { try { return new URL(u).host === GHOST; } catch (e) { return false; } }), 15000);
      on("Network.requestWillBeSent", () => {});
      await send("Page.stopLoading");
      const ru = hit ? new URL(hit).searchParams.get("redirect_uri") : "";
      check(tag + "Continue with Google opens Google's sign-in page (" + GHOST + ")", !!hit, seen.slice(0, 3).join(" | ").slice(0, 200));
      check(tag + "...and asks Google to come back to this site", ru === BASE + "/api/auth/google/callback", ru);
      if (hit && GHOST === "accounts.google.com") {
        await sleep(2500);
        const g = await ev("document.body?document.body.innerText.slice(0,400):''");
        const err = String(g).match(/redirect_uri_mismatch|invalid_client|deleted_client|org_internal|Access blocked|Error 4\d\d/);
        check(tag + "Google's page opened without an error (no redirect_uri_mismatch, invalid_client, Access blocked)", !err, err ? err[0] : "");
        await snap(W + "-5-google");
      }
      info(tag + "stopped at Google's page: this tool never signs in to a Google account");
      await send("Network.clearBrowserCookies");     // the stand-in Google of the test suite signs straight back in; forget that session
    } else if (!S.google && phone) skip(tag + "Continue with Google leads to Google's sign-in page", "the Google client ID and secret on the server");
    const errs = logs.slice(before).filter((l) => l.startsWith("EXC"));
    check(tag + "no script errors", errs.length === 0, errs.slice(0, 3).join(" | "));
  }

  // ---------- sign-up by email code, with a person's real inbox ----------
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 3, mobile: true });
  await send("Emulation.setTouchEmulationEnabled", { enabled: true });
  const used = new Set();
  async function getCode(addr, given, startedAt) {
    if (given) return given;
    const file = arg("code-file", "");
    if (!file) return "";
    console.log("     waiting up to 3 minutes for the code sent to " + addr + ": type the 6 digits into " + path.resolve(file));
    const end = Date.now() + 180000;
    while (Date.now() < end) {
      try {
        const stt = fs.statSync(file);
        if (stt.mtimeMs >= startedAt - 1000) {
          const t = fs.readFileSync(file, "utf8");
          // the 6 digits typed by a person, or (the test suite) a stand-in mail server's file: "123456 is your UAply verification code"
          const found = [...t.matchAll(/([0-9]{6}) is your UAply verification code/g)].map((m) => m[1]);
          if (!found.length) found.push(...[...t.matchAll(/(?:^|[^0-9])([0-9]{3}[ -]?[0-9]{3})(?![0-9])/g)].map((m) => m[1].replace(/[ -]/g, "")));
          const c = found.find((x) => !used.has(x));
          if (c) { used.add(c); return c; }
        }
      } catch (e) {}
      await sleep(2000);
    }
    return "";
  }
  async function signUp(addr, given, label) {
    await fresh(); await agree();
    await menu("nb-prof", "account");
    if (!(await has("#sEmail"))) { await click("#hdrAcct"); await sleep(900); }
    const pw = "Live-" + crypto.randomBytes(12).toString("base64url");       // kept in memory only, never printed or saved
    await setVal("sEmail", addr); await setVal("sPw", pw); await setVal("sPw2", pw); await tick("sAgree");
    const startedAt = Date.now();
    await click("[data-auth=ssubmit]");
    const t1 = await waitFor(async () => { const t = await secText("#acctSec"); return /Verify your email|already has an account|Too many/.test(t) ? t : ""; }, 15000);
    if (!check(label + "sign-up of " + addr + " creates the account and asks for the 6-digit code", /Verify your email/.test(t1 || "") && (await has("#sCode")), (t1 || await secText("#acctSec")).slice(0, 160))) return false;
    check(label + "it says the code was emailed", /We emailed (you )?a 6-digit code/.test(t1 + " " + await secText("#aMsg")), (await secText("#aMsg")).slice(0, 120));
    await snap("signup-" + label.replace(/\W+/g, "") + "-1-code");
    const code = await getCode(addr, given, startedAt);
    if (!check(label + "a 6-digit code was given (--code, or typed into the --code-file within 3 minutes)", /^[0-9]{6}$/.test(code), code ? "not 6 digits" : "no code arrived")) return false;
    await setVal("sCode", code); await click("[data-auth=sverify]");
    const t2 = await waitFor(async () => { const t = await secText("#acctSec"); return /email verified/.test(t) && !(await has("#sCode")) ? t : ""; }, 15000);
    return check(label + "the code verifies the email", !!t2, (await secText("#aMsg")).slice(0, 120));
  }

  if (!EMAIL) skip("sign-up by email code", "--email you+tag@gmail.com and --code-file or --code (a real inbox)");
  else if (!S.email) skip("sign-up of " + EMAIL + " by email code", "email on the server (the Brevo SMTP key): with email off no code is sent, so the address is not used");
  else if (await signUp(EMAIL, arg("code", ""), "[account 1] ")) {
    // a swipe right, then the Applied list
    if (cfg.mode !== "test") skip("[account 1] a swipe right appears under Applied", "delivery mode 'test' on the server (it is " + cfg.mode + "): this tool never sends an application to an employer");
    else {
      await menu("nb-svc", "job");
      const role = await ev("(()=>{const c=" + F + ".querySelector('.card.top h2');return c?c.textContent.trim():''})()");
      await click("#btnYes"); await sleep(1500);
      if (await has("#kcYes")) await click("#kcYes");
      await sleep(8000);                                // the 5-second undo window, then the send
      const toast = await ev("[...(" + F + ").querySelectorAll('.toast')].map(x=>x.innerText).join(' | ')");
      info("[account 1] after a swipe right on " + JSON.stringify(role).slice(0, 60) + ": " + String(toast).split(/\s+/).join(" ").slice(0, 160));
      await menu("nb-dash", "applied");
      if (!(await secText("body")).includes(role)) await ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a,[role=tab]')].find(b=>b.offsetParent&&b.innerText.trim().startsWith('Applied'));if(e)e.click()})()");
      await sleep(800);
      const page = await appText();
      check("[account 1] the job swiped right appears under Job Tracker > Applied", !!role && page.includes(role), role);
      await snap("signup-account1-2-applied");
    }
    // ---------- Stripe test cards ----------
    if (!STRIPE) skip("a Stripe test-card purchase", "--stripe-test and Stripe TEST keys on the server");
    else if (!S.payments) skip("a Stripe test-card purchase", "Stripe keys on the server (STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_PLUS, STRIPE_PRICE_PRO)");
    else if (!S.paymentsTest) skip("a Stripe test-card purchase", "TEST-mode keys: this server has LIVE keys, where test cards cannot unlock a plan and this tool never uses a real card");
    else {
      const bought = await pay("plus", "4242424242424242", "[account 1] ", true);
      if (bought) {
        // the plan changes only when Stripe's signed webhook reaches the server: give it up to 60 seconds
        const t0 = Date.now();
        const plan = await waitFor(async () => { const b = (await json("/api/billing/status")).j || {}; return b.plan === "plus" ? b : null; }, 60000);
        check("[account 1] after the 4242 test card the server says the plan is Plus (the signed webhook arrived" + (plan ? ", after " + Math.round((Date.now() - t0) / 1000) + " s" : "") + ")",
          !!plan, "still " + (((await json("/api/billing/status")).j || {}).plan) + " after 60 s: check Stripe, Developers > Webhooks for a failed delivery");
        const me = ((await json("/api/auth/me")).j || {}).user || {};
        check("[account 1] /api/auth/me says plan Plus too", me.plan === "plus", JSON.stringify({ plan: me.plan }));
        await menu("nb-prof", "plan"); await sleep(1500);
        check("[account 1] Plan & billing reads Current plan: Plus", /Current plan: Plus/.test(await secText("#acctSec")), (await secText("#acctSec")).slice(0, 120));
        await snap("stripe-1-plus");
      }
      // a second account and a declined card: nothing may change
      if (await signUp(EMAIL2, arg("code2", ""), "[account 2] ")) {
        await pay("plus", "4000000000000002", "[account 2] ", false);
        await nav(BASE + "/"); await sleep(3000);
        const b2 = (await json("/api/billing/status")).j || {};
        check("[account 2] after the declined card 4000 0000 0000 0002 the plan is still Free", b2.signedIn === true && b2.plan === "free", JSON.stringify({ signedIn: b2.signedIn, plan: b2.plan }));
        await menu("nb-prof", "plan"); await sleep(800);
        check("[account 2] Plan & billing still reads Current plan: Free", /Current plan: Free/.test(await secText("#acctSec")), (await secText("#acctSec")).slice(0, 120));
      }
    }
  }

  // Stripe Checkout, the hosted page (checkout.stripe.com): only Stripe's published test cards (stripe-checkout.js refuses any other number),
  // typed into the card fields wherever Stripe draws them (its own iframes included)
  async function pay(k, card, label, shouldWork) {
    await menu("nb-prof", "plan");
    if (!check(label + "Choose " + k + " is offered to a verified account", await click("[data-bill=" + k + "]"), (await secText("#acctSec")).slice(0, 120))) return false;
    const onStripe = await waitFor(async () => /(^|\.)stripe\.com$/.test(await ev("location.host")) && (await ev("document.readyState")) === "complete", 30000);
    if (!check(label + "Choose " + k + " opens Stripe's own Checkout page", !!onStripe, await ev("location.href"))) return false;
    const sess = (String(await ev("location.pathname")).match(/cs_(?:test|live)_[A-Za-z0-9]+/) || [""])[0];
    info(label + "Stripe Checkout session " + (sess || "(id not in the address)") + ": match it in Stripe, Developers > Events");
    if (/^cs_live_/.test(sess)) { check(label + "Stripe Checkout is in TEST mode", false, "a LIVE session: this tool never types a card there"); return false; }
    const r = await stripe.fill(api, { card, email: label.includes("2") ? EMAIL2 : EMAIL });
    info(label + "Stripe's form: " + r.notes.join(", "));
    await snap("stripe-" + card.slice(-4) + "-filled");
    if (!check(label + "the card fields are found and filled (in the page or Stripe's iframes)", r.ok, r.notes.join(", "))) return false;
    const F = r.F;
    if (!check(label + "Pay is pressed", await stripe.submit(api, F), "the Pay button stayed disabled: " + (await F.text()).slice(0, 160))) return false;
    // Stripe Link may ask an address it knows for a code by text message: this tool cannot answer that
    const linkCode = async () => /Enter the code|Verify it.s you|sent a code to/i.test(await F.text());
    if (shouldWork) {
      // back to the site's public_url (which may be another address than --base, e.g. https://uaply.net) with ?billing=success
      const back = await waitFor(async () => (await stripe.captcha(F)) ? "captcha" : (await linkCode()) ? "link" :
        /[?&]billing=success/.test(await ev("location.href")) || String(await ev("location.href")).startsWith(BASE + "/") ? "back" : "", 90000);
      if (back === "back") { await nav(BASE + "/?billing=success"); await sleep(1500); }          // the session cookie belongs to --base
      if (back === "captcha") { check(label + "Stripe Checkout finished", false, "Stripe asked for a captcha (a bot check). This tool never solves one: finish this payment by hand"); return false; }
      if (back === "link") { check(label + "Stripe Checkout finished", false, "Stripe Link asked for a code for this address: use an address with no Link account"); return false; }
      return check(label + "the test card " + card.replace(/(\d{4})(?=\d)/g, "$1 ") + " is accepted and Stripe sends the browser back to UAply", back === "back",
        String(await ev("location.href")).slice(0, 100) + " | " + (await F.text()).slice(0, 200));
    }
    const said = await waitFor(async () => { if (await stripe.captcha(F)) return "captcha"; const t = await F.text(); return /declined/i.test(t) ? t : ""; }, 45000);
    if (said === "captcha") { check(label + "Stripe Checkout answered", false, "Stripe asked for a captcha (a bot check). This tool never solves one"); return false; }
    await snap("stripe-" + card.slice(-4) + "-declined");
    if (said) info(label + "Stripe said: " + (said.match(/[^.]*declined[^.]*\./i) || [said.slice(0, 120)])[0].trim());
    return check(label + "the declined test card " + card.replace(/(\d{4})(?=\d)/g, "$1 ") + " is refused on Stripe's page (the error shows inline)",
      !!said && /stripe\.com$/.test(await ev("location.host")), String(await ev("location.href")).slice(0, 100) + " | " + (await F.text()).slice(0, 160));
  }

  if (SHIELDS) {
    const own = blocked.filter((u) => u.startsWith(BASE));
    check("shields: no UAply request was blocked by the filter lists", !own.length, own.slice(0, 5).join(" | "));
    info("shields: requests blocked in all: " + blocked.length + (blocked.length ? " (" + blocked.slice(0, 6).join(" | ") + ")" : ""));
  }
  if (READONLY) info("read-only: held back " + held.length + " request(s) that could have changed the site" + (held.length ? ": " + [...new Set(held)].join(", ") : ""));
  console.log("\n" + count.PASS + " passed, " + count.FAIL + " failed, " + count.SKIP + " skipped");
  console.log(count.PASS + " / " + (count.PASS + count.FAIL));
}
