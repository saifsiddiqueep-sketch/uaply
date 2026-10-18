// The friction points the stranger walk of the live site found on October 18 (Bot 1), checked in a real browser with finger taps on a
// phone (390x844) against a running dev server:
//   PORT=8767 CDP_LIMIT_MS=600000 node tools/cdp.js tools/ui-walk.js
// 1. a message after a swipe uses the phone's width (it used to wrap into a column half the screen wide, over the card)
// 2. Save and continue in Profile setup opens the next step at its top (it used to scroll to the step's last field)
// 3. a LinkedIn link typed as "linkedin.com/in/..." is completed to https:// instead of blocking Save
// 4. an empty deck where every listing is hidden by the target titles says so (not "You have seen every one of these") and
//    "Show all roles" brings the jobs back in one tap
// 5. Data & privacy: a restore says "Restored." (the message used to be wiped at once); "Show it again" drops "You only see this once"
// 6. Account: the line above "You are signed in" no longer asks to sign in; "Sign in" everywhere (not "Log in"); a sign-out or a
//    password change that reaches a restarting server (502) says so, and a failed sign-out never claims "Signed out."
// 7. help: an answer that did not help offers "Talk to a person" at once
// 8. the one-tap rating question goes away when the person taps anything else (a tap meant for a menu landed on its "3")
const fs = require("fs");
const os = require("os");
const path = require("path");
const PORT = process.env.PORT || "8767";
const BASE = "http://127.0.0.1:" + PORT;
module.exports = async ({ ev, sleep, nav, send, logs, on }) => {
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + name + (ok || !extra ? "" : "  -> " + extra)); return ok; };
  const F = "document.querySelector('iframe').contentDocument";
  const q = (js) => ev("(()=>{try{const d=" + F + ",w=d.defaultView;" + js + "}catch(e){return 'ERR '+e.message}})()");
  const text = (sel) => q("const e=d.querySelector(" + JSON.stringify(sel) + ");return e?e.innerText.replace(/\\s+/g,' ').trim():''");
  const waitFor = async (js, ms) => { const end = Date.now() + (ms || 8000); let v; while (Date.now() < end) { v = await q(js); if (v && !String(v).startsWith("ERR")) return v; await sleep(250); } return v; };
  // a finger tap at the middle of an element (scrolled into view first), the way a phone sends it
  const tapAt = async (x, y) => { await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] }); await sleep(50); await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] }); await sleep(350); };
  const where = (finder) => q("const e=(" + finder + ");if(!e)return null;e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect(),o=document.querySelector('iframe').getBoundingClientRect();return {x:Math.round(o.left+r.left+r.width/2),y:Math.round(o.top+r.top+r.height/2)}");
  const tap = async (finder) => { const p = await where(finder); if (!p || typeof p !== "object") return false; await sleep(150); const p2 = await where(finder); await tapAt(p2.x, p2.y); return true; };
  const byText = (re) => "[...d.querySelectorAll('button,a,[role=button],.nitem')].find(b=>b.offsetParent&&" + re + ".test(b.innerText.trim()))";
  const type = async (sel, s) => { await tap("d.querySelector(" + JSON.stringify(sel) + ")"); await q("const e=d.querySelector(" + JSON.stringify(sel) + ");e.focus();e.select&&e.select();return 1"); await send("Input.insertText", { text: s }); await sleep(150); };
  const menu = async (tab, item) => { await tap("d.getElementById('" + tab + "')"); await sleep(300); return tap("[...d.querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')==='" + item + "')"); };
  const swipe = async (dx) => {
    const c = await where("d.querySelector('.card.top')"); if (!c) return false;
    await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: c.x, y: c.y - 60 }] });
    for (let i = 1; i <= 12; i++) { await sleep(16); await send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: c.x + (dx * i) / 12, y: c.y - 60 }] }); }
    await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] }); await sleep(900); return true;
  };

  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  await send("Network.enable");
  await nav(BASE + "/healthz");
  await send("Storage.clearDataForOrigin", { origin: BASE, storageTypes: "all" });
  await send("Network.clearBrowserCookies");
  await nav(BASE + "/");
  const jobs = await waitFor("return d.querySelector('.card.top h2')&&d.querySelectorAll('.card').length", 60000);
  if (!check("the deck shows job cards", !!jobs, "no card after 60 s (does the server have its job feeds on?)")) { console.log("\n" + pass + " / " + (pass + fail)); return; }
  await waitFor("return d.getElementById('kcYes')", 5000);
  await tap("d.getElementById('kcYes')");
  await tap(byText("/^Not now$/"));
  await tap("d.getElementById('tipsClose')");

  // 1. the message after a swipe right (on the live site "Add your name and email in Profile setup...", here the saved-to-Applied
  //    one): as wide as the phone allows, not a column half the screen wide over the card
  await swipe(240);
  const t1 = await waitFor("const t=[...d.querySelectorAll('.toast')].find(x=>x.getClientRects().length&&x.innerText.length>40);return t?JSON.stringify({w:Math.round(t.getBoundingClientRect().width),h:Math.round(t.getBoundingClientRect().height),vw:w.innerWidth,t:t.innerText.slice(0,70)}):''", 6000);
  const r1 = t1 ? JSON.parse(t1) : {};
  check("1. the message after a swipe uses the phone's width (at least 300 of 390 px; it was 195)", r1.w >= 300 && r1.w <= r1.vw - 16, JSON.stringify(r1));
  check("1. ...and stays short (at most 4 lines' height; the live one was 9)", r1.h > 0 && r1.h <= 110, JSON.stringify(r1));
  // the same rule on the longest message the live site showed, put up the way the app puts up every message
  const t1b = await q("const t=d.createElement('div');t.className='toast';t.innerHTML='<span>Add your name and email in Profile setup, under About you, so employers can reply. Coinbase is back in your deck.</span><button type=button>Open Profile</button>';d.body.appendChild(t);const r=t.getBoundingClientRect();t.remove();return JSON.stringify({w:Math.round(r.width),h:Math.round(r.height)})");
  const r1b = JSON.parse(t1b);
  check("1. the 'Add your name and email' message is at least 300 px wide and at most 4 lines high (it was 195 x 9 lines)", r1b.w >= 300 && r1b.h <= 110, t1b);

  // 2. Profile setup: Save and continue opens the next step at its top
  await menu("nb-prof", "settings");
  await waitFor("return /Step 1 of 5/.test(d.getElementById('wzCount').innerText)", 5000);
  await type("#pName", "Walk Tester");
  await type("#pEmail", "walk.tester@example.com");
  await tap("d.getElementById('wzNext')");
  await waitFor("return /Step 2 of 5/.test(d.getElementById('wzCount').innerText)", 5000);
  await sleep(1200);                                            // the old smooth scroll to "Saved." took about a second
  const top2 = await q("return d.getElementById('main').scrollTop");
  check("2. Save and continue opens step 2 at its top (scrolled " + top2 + " px; it used to land at the last field)", top2 < 60, top2);
  check("2. ...and still says Saved.", /Saved\./.test(await text("#wzMsg")), await text("#wzMsg"));
  // 4 (set up): a target title the feed has no jobs for
  await type("#pTitle", "Underwater Basket Weaving Lead");
  await tap("d.getElementById('wzNext')");
  await waitFor("return /Step 3 of 5/.test(d.getElementById('wzCount').innerText)", 5000);
  await tap("d.getElementById('wzNext')");
  await waitFor("return /Step 4 of 5/.test(d.getElementById('wzCount').innerText)", 5000);

  // 3. LinkedIn without https://
  await type("#px-linkedin", "linkedin.com/in/walk-tester");
  const err3 = await text("#px-linkedin-err");
  check("3. typing linkedin.com/in/... shows no 'Use a full link' error", !/full link/.test(err3), err3);
  await tap("d.getElementById('wzNext')");
  const on5 = await waitFor("return /Step 5 of 5/.test(d.getElementById('wzCount').innerText)", 5000);
  check("3. Save and continue is not blocked by that link (step 5 opens)", !!on5, await text("#wzMsg"));
  check("3. ...and the link is saved as https://linkedin.com/in/walk-tester", (await q("return d.getElementById('px-linkedin').value")) === "https://linkedin.com/in/walk-tester", await q("return d.getElementById('px-linkedin').value"));
  check("3. a bare www address is completed too, and a plain word is left for the check to refuse",
    (await q("return w.__uaplyFullLink('www.example.com/me')+' | '+w.__uaplyFullLink('http://site.org')+' | '+w.__uaplyFullLink('my site')")) === "https://www.example.com/me | https://site.org | my site",
    await q("return w.__uaplyFullLink('www.example.com/me')+' | '+w.__uaplyFullLink('http://site.org')+' | '+w.__uaplyFullLink('my site')"));

  // 4. finish: every listing is hidden by the target title
  await tap("d.getElementById('wzNext')");
  const empty = await waitFor("return !d.querySelector('.card.top')&&d.querySelector('#deck .empty h2')?d.querySelector('#deck .empty').innerText.replace(/\\s+/g,' '):''", 8000);
  check("4. an empty deck hidden by filters says '(No|No more) jobs here match your profile and filters'", /No (more )?jobs here match your profile and filters/.test(empty || ""), empty);
  check("4. ...with how many are hidden, not 'You have seen every one of these'", !/You have seen every one/.test(empty || "") && /\d+ listings? (is|are) hidden by your filters or target titles/.test(empty || ""), empty);
  const note = await text("#titleNote");
  check("4. the target-title note offers Show all roles", /hidden because/.test(note) && !!(await q("return !!d.getElementById('titleShowAll')")), note);
  await tap("d.getElementById('titleShowAll')");
  const back = await waitFor("return d.querySelectorAll('.card').length", 5000);
  check("4. one tap on Show all roles brings the jobs back and turns the filter off", back > 0 && (await q("return d.getElementById('titleNote').hidden")) === true, back);

  // 5. Data & privacy: restore, then Show it again
  await menu("nb-prof", "data");
  const file = path.join(os.tmpdir(), "uaply-walk-backup-" + process.pid + ".json");
  fs.writeFileSync(file, JSON.stringify({ app: "uaply", v: 1, exported: new Date().toISOString(), profile: { name: "Restored Person", title: "Analyst", years: 2, edu: "Bachelor", skills: ["SQL"], salary: 0, loc: "Philadelphia", modes: {} }, decisions: {}, acct: {} }));
  const inp = await send("Runtime.evaluate", { expression: F + ".getElementById('aImp')" });
  await send("DOM.enable");
  await send("DOM.setFileInputFiles", { files: [file], objectId: inp.result.result.objectId });
  const said = await waitFor("const m=d.getElementById('aMsg');return m&&m.innerText.trim()", 5000);
  check("5. a restore says Restored. (it used to say nothing)", /^Restored\./.test(said || ""), said);
  try { fs.unlinkSync(file); } catch (e) {}
  await tap(byText("/^Show it again$/"));
  const again = await waitFor("const b=d.getElementById('kitConsent');return b?b.innerText:''", 4000);
  check("5. the agreement shown again no longer says 'You only see this once'", !!again && !/You only see this once/.test(again), (again || "").slice(-120));
  await tap("d.getElementById('kcYes')");

  // 6. Account: sign up, the line above "You are signed in", a failed sign-out, Sign in wording
  await menu("nb-prof", "account");
  const email = "walk" + Date.now() + "@example.com", pw = "Walk-" + Math.random().toString(36).slice(2) + "-Pw9";
  await type("#sEmail", email); await type("#sPw", pw); await type("#sPw2", pw);
  await tap("d.getElementById('sAgree')");
  await tap("d.querySelector('[data-auth=ssubmit]')");
  const signed = await waitFor("return /You are signed in/.test(d.getElementById('acctSec').innerText)", 8000);
  check("6. sign-up on this server signs the person in", !!signed, (await text("#aMsg")));
  const lead = await text("#acctSec .lead");
  check("6. signed in, the Account line no longer says 'Sign in to get an email receipt'", !/^Sign in/.test(lead) && /Your sign-in/.test(lead), lead);
  // a server that is restarting (Render answers 502 during a deploy)
  on("Fetch.requestPaused", (p) => send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: 502, responseHeaders: [{ name: "Content-Type", value: "text/html" }], body: Buffer.from("<html><body>Bad Gateway</body></html>").toString("base64") }));
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/auth/logout*" }, { urlPattern: "*/api/auth/change-password*" }] });
  await tap(byText("/^Change password$/"));
  await type("#sCur", pw); await type("#sNew", pw + "x"); await type("#sNew2", pw + "x");
  await tap(byText("/^Save new password$/"));
  const cp = await waitFor("return d.getElementById('aMsg').innerText.trim()", 5000);
  check("6. a password change that meets a restarting server says so (not 'The server sent an unexpected reply')", /restarting/.test(cp || "") && !/unexpected reply/.test(cp || ""), cp);
  await tap(byText("/^Cancel$/"));
  await tap(byText("/^Sign out$/"));
  const so = await waitFor("return d.getElementById('aMsg').innerText.trim()", 5000);
  check("6. a sign-out that did not reach the server says 'You are still signed in' (never 'Signed out.')", /You are still signed in/.test(so || "") && !/^Signed out/.test(so || ""), so);
  const me = await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>!!(j&&j.user)).catch(()=>null)");
  check("6. ...which is true: the server still has the session", me === true, me);
  await send("Fetch.disable");
  await tap(byText("/^Sign out$/"));
  const so2 = await waitFor("return /^Signed out/.test(d.getElementById('aMsg').innerText.trim())", 5000);
  check("6. with the server back, Sign out signs out", !!so2 && (await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>!!(j&&j.user)).catch(()=>null)")) === false, await text("#aMsg"));
  if (await q("return !!d.querySelector('[data-auth=smode]')&&/already have/.test(d.querySelector('[data-auth=smode]').innerText)")) await tap("d.querySelector('[data-auth=smode]')");
  const form = await text("#acctSec");
  check("6. the sign-in form says Sign in, never Log in", /Sign in to UAply/.test(form) && !/\bLog in\b/.test(form), form.slice(0, 160));
  await type("#sEmail", email); await type("#sPw", pw);
  await tap("d.querySelector('[data-auth=ssubmit]')");
  const si = await waitFor("const t=d.getElementById('aMsg').innerText.trim();return /…$/.test(t)?'':t", 6000);
  check("6. signing in says 'You are signed in.'", si === "You are signed in.", si);

  // 7. help: No offers a person
  await tap("d.getElementById('uaChatBtn')");
  await type("#uaChatIn", "how do I apply");
  await tap(byText("/^Send$/"));
  await waitFor("return [...d.querySelectorAll('#uaChat button')].some(b=>b.offsetParent&&/^No$/.test(b.innerText.trim()))", 8000);
  await tap("[...d.querySelectorAll('#uaChat button')].find(b=>b.offsetParent&&/^No$/.test(b.innerText.trim()))");
  const chips = await q("return [...d.querySelectorAll('#uaChat button')].filter(b=>b.offsetParent).map(b=>b.innerText.trim()).join(' / ')");
  check("7. after 'No', the assistant offers Talk to a person", /Talk to a person/.test(chips), chips);
  await tap("[...d.querySelectorAll('#uaChat button')].find(b=>b.offsetParent&&/^Talk to a person$/.test(b.innerText.trim()))");
  const human = await text("#uaChatLog");
  check("7. ...and that goes straight to how to reach the team", /leave a message here|reply within|reply by email/i.test(human.slice(-300)), human.slice(-200));
  await tap("d.getElementById('uaChatX')");

  // 8. the rating question goes away on any other tap, so a menu opened under it gets the tap
  await q("const n=d.getElementById('uaNudge');n.hidden=false;return 1");
  await tap("d.getElementById('nb-dash')");
  check("8. a tap on the Dashboard tab closes the rating question", (await q("return d.getElementById('uaNudge').hidden")) === true);
  const menuOpen = await q("return [...d.querySelectorAll('.nitem')].some(b=>b.offsetParent&&b.getAttribute('data-v')==='applied')");
  check("8. ...and the Dashboard menu opens for the next tap", menuOpen === true, menuOpen);

  const errs = logs.filter((l) => l.startsWith("EXC"));
  check("no script errors", errs.length === 0, errs.slice(0, 3).join(" | "));
  console.log("\n" + pass + " passed, " + fail + " failed");
  console.log(pass + " / " + (pass + fail));
};
module.exports.limitMs = 300000;
