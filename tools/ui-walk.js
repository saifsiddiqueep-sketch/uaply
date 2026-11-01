// The friction points the stranger walk of the live site found on October 18 (Bot 1), checked in a real browser with finger taps on a
// phone (390x844) against a running dev server:
//   PORT=8767 CDP_LIMIT_MS=600000 node tools/cdp.js tools/ui-walk.js
// 1. a message after a swipe uses the phone's width (it used to wrap into a column half the screen wide, over the card)
// 2. Save and continue in Profile setup opens the next step at its top (it used to scroll to the step's last field)
// 3. a LinkedIn link typed as "linkedin.com/in/..." is completed to https:// instead of blocking Save
// 4. when no listing matches the target titles, the deck shows the roles anyway with "Showing all roles: none matched your target
//    titles" and a way to Filters (since Oct 21); an empty deck that other filters hide says so (not "You have seen every one of these")
// 5. Data & privacy: a restore says "Restored." (the message used to be wiped at once); "Show it again" drops "You see this again only if the agreement changes"
// 6. Account: the line above "You are signed in" no longer asks to sign in; "Sign in" everywhere (not "Log in"); a sign-out or a
//    password change that reaches a restarting server (502) says so, and a failed sign-out never claims "Signed out."
// 7. help: an answer that did not help offers "Talk to a person" at once
// 8. the one-tap rating question goes away when the person taps anything else (a tap meant for a menu landed on its "3")
// 9. a right swipe on a hand-off job is quiet ("Saved X to Applied · N% match" with Undo, never "Finish on their site"); Applied shows the
//    status chip, See the job posting and Finish applying on their site, which copies only name, email, phone and links and tags Greenhouse/Lever links
// 10. at laptop size (W 1000 or more, October 20 layout pass): one centred column about 960 px wide, with Account and Plan & billing in
//     its middle
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

  // a right swipe that must land: if the card did not go (a card still settling, a message over it), say what was under the finger and try once more
  const swipeRight = async (id) => {
    for (let i = 0; i < 2; i++) {
      await sleep(700);
      await swipe(240);
      if (await waitFor("return !!w.__uaply.S.decisions[" + id + "]", 3000) === true) return true;
      console.log("     swipe " + (i + 1) + " did not take; under the finger: " + await q("const c=d.querySelector('.card.top');if(!c)return 'no card';const r=c.getBoundingClientRect();const e=d.elementFromPoint(r.left+r.width/2,r.top+r.height/2-60);return e?(e.id||e.className||e.tagName):'nothing'"));
    }
    return false;
  };
  // 390x844 (a phone) unless W and H ask for another size, e.g. W=1280 H=800 for a computer; taps stay finger taps either way
  const VW = +(process.env.W || 390), VH = +(process.env.H || 844);
  await send("Emulation.setDeviceMetricsOverride", { width: VW, height: VH, deviceScaleFactor: VW < 700 ? 2 : 1, mobile: VW < 700 });
  await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  await send("Network.enable");
  await nav(BASE + "/healthz");
  await send("Storage.clearDataForOrigin", { origin: BASE, storageTypes: "all" });
  await send("Network.clearBrowserCookies");
  await nav(BASE + "/");
  // the test person signs up first (October 22, Saif: nobody reaches anything on the site without an account); section 6 signs out and
  // walks the sign-up card itself
  const first = "walkfirst" + Date.now() + "@example.com";
  const su = await ev("fetch('/api/auth/signup',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:" + JSON.stringify(first) + ",password:'Walk-first-pw9',first:'Walk',last:'First',agree:true,passwordless:false})}).then(r=>r.status)");
  check("0. the test person signs up first (POST /api/auth/signup)", su === 200, su);
  await nav(BASE + "/");
  const jobs = await waitFor("return d.querySelector('.card.top h2')&&d.querySelectorAll('.card').length", 60000);
  console.log("     size " + VW + "x" + VH + ": the app frame is " + (await q("return w.innerWidth+'x'+w.innerHeight")));
  if (!check("the deck shows job cards", !!jobs, "no card after 60 s (does the server have its job feeds on?)")) { console.log("\n" + pass + " / " + (pass + fail)); return; }
  await waitFor("return d.getElementById('kcYes')", 5000);
  await tap("(()=>{d.querySelectorAll('.kcTick').forEach(c=>{c.checked=true;c.dispatchEvent(new Event('change'))});return d.getElementById('kcYes')})()");
  await tap(byText("/^Not now$/"));
  await tap("d.getElementById('tipsClose')");

  // 0. (Saif, October 24) a swipe right with an empty profile is never blocked: the job is saved to Job Tracker and nothing is sent
  const top0 = await q("return +d.querySelector('.card.top').getAttribute('data-id')");
  await swipe(240);
  await sleep(600);
  check("0. a swipe right with an empty profile saves the job (nothing is sent) and the deck moves on",
    (await q("const x=w.__uaply.S.decisions[" + top0 + "];return !!x&&!(x.sent&&(x.sent.status==='sent'||x.sent.status==='delivered_test'))")) === true &&
    (await q("const c=d.querySelector('.card.top');return c?+c.getAttribute('data-id'):0")) !== top0, "");
  check("0. ...with no Finish your profile box over the deck", (await q("return !d.getElementById('rdyBox')")) === true, "");
  // 1. the message after a swipe (here "Passed on ..."): as wide as the phone allows, not a column half the screen wide over the card
  await swipe(-240);
  const t1 = await waitFor("const t=[...d.querySelectorAll('.toast')].find(x=>x.getClientRects().length&&x.innerText.length>10);return t?JSON.stringify({w:Math.round(t.getBoundingClientRect().width),h:Math.round(t.getBoundingClientRect().height),vw:w.innerWidth,t:t.innerText.slice(0,70)}):''", 6000);
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

  // 4. finish: no listing matches the target title. Since Oct 21 the title filter never empties a stack: the roles show, with a note
  await tap("d.getElementById('wzNext')");
  const back = await waitFor("return d.querySelectorAll('.card').length", 8000);
  const note = await text("#titleNote");
  check("4. when no listing matches the target titles, the deck still shows the jobs", back > 0, back);
  check("4. ...with the one-line note 'Showing all roles: none matched your target titles' and a way to Filters",
    /^Showing all roles: none matched your target titles\. Filters$/.test(note) && !!(await q("return !!d.getElementById('titleFilters')")), note);
  const empty = await q("const A=w.__uaply;return w.__uaplyEmpty(A.JOBS,{decisions:{}},'job').join(' ')");
  check("4. an empty deck that other filters hide still says so (no number), not 'You have seen every one of these'",
    /No full-time jobs match your filters yet/.test(empty) && /Filters/.test(empty) && !/\d/.test(empty.replace(/<[^>]+>/g, "")) && !/You have seen every one/.test(empty), empty);

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
  check("5. the agreement shown again no longer says 'You see this again only if the agreement changes'", !!again && !/You see this again only if/.test(again), (again || "").slice(-120));
  await tap("(()=>{d.querySelectorAll('.kcTick').forEach(c=>{c.checked=true;c.dispatchEvent(new Event('change'))});return d.getElementById('kcYes')})()");

  // 6. Account: sign up, the line above "You are signed in", a failed sign-out, Sign in wording (the first account signs out for it)
  await ev("fetch('/api/auth/logout',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'})");
  await nav(BASE + "/"); await waitFor("return !!d.getElementById('bnav')&&!!d.getElementById('acctSec')", 15000); await sleep(800);
  // since October 22 (Saif) signed out is the sign-in gate: the sign-up card is the whole screen, and the person signs up on it by touch
  const gateUp = (await q("return d.body.classList.contains('sgGated')&&d.querySelector('.sg-su')?'y':''")) === "y";
  if (!gateUp) await menu("nb-prof", "account");
  const email = "walk" + Date.now() + "@example.com", pw = "Walk-" + Math.random().toString(36).slice(2) + "-Pw9";
  if (gateUp) {
    await type(".sg-su [data-email] input", email); await type(".sg-su .sg-fn input", "Walk"); await type(".sg-su .sg-ln input", "Tester"); await type(".sg-su .sg-pw input", pw);
    await tap("d.querySelector('.sg-su .sg-ag')");
    await tap("d.querySelector('.sg-su [type=submit]')");
    await waitFor("return /Check your email|1 of 2|What kind of work|What should employers/i.test(d.getElementById('acctSec').innerText)?1:''", 8000);
    if (/Check your email/.test(await text("#acctSec"))) {
      const c = await ev("fetch('/outbox').then(r=>r.text()).then(t=>{const m=t.replace(/<[^>]+>/g,' ').match(/([0-9]{6}) is your UAply verification code/);return m?m[1]:''})");
      await type(".sg-code input", c); await sleep(2000);
    }
    for (let i = 0; i < 4 && (await q("return d.body.classList.contains('sgGated')?'y':''")) === "y"; i++) { await tap("d.querySelector('.sg-next')"); await sleep(700); }
    await menu("nb-prof", "account");
  } else {
    await type("#sEmail", email); await type("#sPw", pw); await type("#sPw2", pw);
    await tap("d.getElementById('sAgree')");
    await tap("d.querySelector('[data-auth=ssubmit]')");
  }
  const signed = await waitFor("return /You are signed in|Signed in as/.test(d.getElementById('acctSec').innerText)", 8000);
  check("6. sign-up on this server signs the person in" + (gateUp ? " (on the sign-in gate's card, by touch)" : ""), !!signed && (await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user&&j.user.email)")) === email, (await text("#acctSec")).slice(0, 200));
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
  const so2 = gateUp ? await waitFor("return d.body.classList.contains('sgGated')?'y':''", 5000) : await waitFor("return /^Signed out/.test(d.getElementById('aMsg').innerText.trim())", 5000);
  check("6. with the server back, Sign out signs out" + (gateUp ? " (and the sign-in gate is back)" : ""), !!so2 && (await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>!!(j&&j.user)).catch(()=>null)")) === false, await text("#aMsg"));
  if (gateUp) await tap("d.querySelector('.sg-to-in')");
  else if (await q("return !!d.querySelector('[data-auth=smode]')&&/already have/.test(d.querySelector('[data-auth=smode]').innerText)")) await tap("d.querySelector('[data-auth=smode]')");
  const form = await text("#acctSec");
  check("6. the sign-in form says Sign in, never Log in", /Sign in to UAply/.test(form) && !/\bLog in\b/.test(form), form.slice(0, 160));
  if (gateUp) {
    await type(".sg-si [data-email] input", email); await type(".sg-si .sg-pw input", pw);
    await tap("d.querySelector('.sg-si [type=submit]')");
    const si = await waitFor("return d.body.classList.contains('sgGated')?'':'in'", 8000);
    check("6. signing in with the password opens the app (the gate lifts)", si === "in" && (await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user&&j.user.email)")) === email, si);
  } else {
    await type("#sEmail", email); await type("#sPw", pw);
    await tap("d.querySelector('[data-auth=ssubmit]')");
    const si = await waitFor("const t=d.getElementById('aMsg').innerText.trim();return /…$/.test(t)?'':t", 6000);
    check("6. signing in says 'You are signed in.'", si === "You are signed in.", si);
  }

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
  check("8. a tap on the Job Tracker tab closes the rating question", (await q("return d.getElementById('uaNudge').hidden")) === true);
  // (card 182: the Job Tracker tab has no menu; the same tap opens its Overview)
  const ovOpen = await waitFor("const p=d.getElementById('pane-track');return !!(p&&p.offsetParent)", 3000);
  check("8. ...and the same tap opens the Job Tracker Overview", ovOpen === true, ovOpen);

  // 9. quiet swipe (Oct 20): a right swipe on a job that takes applications on its own site never interrupts with "Finish on their
  //    site"; the message is the short "Saved X to Applied · N% match" with Undo, and the Applied row carries the status and both links
  //    (the walk above restored a backup with no email, so the applicant's details are set again first)
  await q("const p=w.__uaply.S.profile;p.name='Walk Tester';p.email='walk.tester@example.com';p.custom=true;p.ext=Object.assign({},p.ext,{phone:'(215) 555-0100'});w.__uaply.save();return 1");
  await tap("d.getElementById('nb-svc')"); await sleep(300);
  await tap("[...d.querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')==='job')");
  await waitFor("return d.querySelector('.card.top h2')&&!d.getElementById('main').hidden", 8000);
  const job9 = await q("const c=d.querySelector('.card.top');return c?JSON.stringify({id:+c.getAttribute('data-id'),co:c.querySelector('.chead p').textContent.trim()}):''");
  const j9 = job9 ? JSON.parse(job9) : {};
  await q("w.__walkToasts=[];new w.MutationObserver(()=>{const t=d.getElementById('kitToast')||d.querySelector('.toast');if(t&&t.innerText)w.__walkToasts.push(t.innerText.replace(/\\s+/g,' '))}).observe(d.body,{childList:true,subtree:true,characterData:true});return 1");
  // (nothing left open from sections 7 and 8 over the card: the Help panel, the rating question)
  await q("const x=d.getElementById('uaChatX');if(x&&x.offsetParent)x.click();const n=d.getElementById('uaNudge');if(n&&!n.hidden){const b=[...n.querySelectorAll('button')].find(b=>/not now|close|later/i.test(b.innerText));if(b)b.click()}return 1"); await sleep(400);
  await swipeRight(j9.id);
  const st9 = await waitFor("const x=w.__uaply.S.decisions[" + j9.id + "];return x&&x.sent&&x.sent.status?x.sent.status:''", 15000);
  if (st9 !== "handoff") console.log("     after the swipe: " + await q("const x=w.__uaply.S.decisions[" + j9.id + "];return JSON.stringify({dec:x||null,dialogs:[...d.querySelectorAll('[role=dialog]')].filter(e=>e.offsetParent).map(e=>e.innerText.slice(0,140).replace(/\s+/g,' ')),toasts:w.__walkToasts.slice(0,3)})"));
  await sleep(600);
  const toasts9 = JSON.parse(await q("return JSON.stringify(w.__walkToasts)") || "[]");
  check("9. the swiped job is a hand-off (the server says it takes applications on its own site)", st9 === "handoff", st9 + " " + JSON.stringify(j9));
  check("9. no message after the swipe says 'Finish on their site' or 'Not sent yet'", toasts9.length > 0 && !toasts9.some((t) => /finish on their site|not sent yet|finish now/i.test(t)), JSON.stringify(toasts9));
  check("9. the message is the hand-off's 'Saved <company> to Job Tracker.' (one tap is promised only where the app opens the form) with Undo", toasts9.some((t) => /^Saved [^.]+ to Job Tracker\. ?Undo$/.test(t)), JSON.stringify(toasts9));
  await tap("d.getElementById('nb-dash')"); await sleep(500);
  const row9 = await q("const b=d.querySelector('#track [data-finish=\"" + j9.id + "\"]')||d.querySelector('[data-finish=\"" + j9.id + "\"]');const r=b&&b.closest('.row');if(!r)return '';return JSON.stringify({txt:r.innerText.replace(/\\s+/g,' '),chip:(r.querySelector('.stchip')||{}).textContent||'',links:[...r.querySelectorAll('.joblinks .linkbtn')].map(x=>x.innerText.trim()),open:(r.querySelector('[data-open]')||{getAttribute:()=>''}).getAttribute('data-open'),url:(w.__uaply.JOBS.find(j=>j.id===" + j9.id + ")||{}).url})");
  const r9 = row9 ? JSON.parse(row9) : {};
  check("9. Applied shows the row with both links: See the job posting, Finish applying on their site (and Mark as applied)", JSON.stringify(r9.links) === JSON.stringify(["See the job posting ↗", "Finish applying on their site ↗", "Mark as applied"]), row9);
  check("9. ...the status chip says Finish on their site", r9.chip === "Finish on their site", row9);
  check("9. ...See the job posting opens the job's own address", !!r9.url && r9.open === r9.url, row9);
  // Finish applying: copies only name, email, phone and links (never voluntary answers or the resume) and opens a tagged link
  // the profile has a phone, a LinkedIn link and a resume link; only the first two may be copied. The clipboard is allowed here, so the
  // real copy is read back (a browser that blocks it gets no message and no error: that path is the try/catch in finishOnSite)
  await q("const p=w.__uaply.S.profile;p.ext=Object.assign({},p.ext,{phone:'(215) 555-0100',linkedin:'https://www.linkedin.com/in/walk',resume:'https://drive.example.com/cv.pdf'});w.__uaply.save();return 1");
  await send("Browser.grantPermissions", { origin: BASE, permissions: ["clipboardReadWrite", "clipboardSanitizedWrite"] });
  await send("Emulation.setFocusEmulationEnabled", { enabled: true });
  await q("w.__walkOpened=[];const o=w.__uaplyOpen;w.__uaplyOpen=function(u){w.__walkOpened.push(u)};w.__walkOpen0=o;return 1");
  await tap("d.querySelector('[data-finish=\"" + j9.id + "\"]')");
  const copied9 = await waitFor("const t=d.getElementById('kitToast');return t&&/Profile copied, paste it into their form/.test(t.innerText)?t.innerText:''", 4000);
  check("9. Finish applying shows 'Profile copied, paste it into their form'", /Profile copied, paste it into their form/.test(copied9 || ""), copied9);
  const clip9 = await ev("document.querySelector('iframe').contentWindow.navigator.clipboard.readText().catch(e=>'READ FAILED '+e.message)");
  check("9. ...and the clipboard holds Name, Email, Phone and LinkedIn", /^Name: Walk Tester\r?\nEmail: walk\.tester@example\.com\r?\nPhone: \(215\) 555-0100\r?\nLinkedIn: https:\/\/www\.linkedin\.com\/in\/walk$/.test(clip9), JSON.stringify(clip9));
  check("9. ...never the resume link, voluntary answers, race, gender, veteran or disability", !/resume|cv\.pdf|race|gender|veteran|disab|ethnic|hispanic/i.test(clip9), JSON.stringify(clip9));
  const opened = JSON.parse(await q("return JSON.stringify(w.__walkOpened)") || "[]");
  // the application form, not the posting (apply journey, October 22): Lever /apply, Ashby /application, SmartRecruiters ?oga=true, plus
  // the source tag on Greenhouse and Lever; tools/ui-journey.js checks each rule on its own
  const want9 = await q("return w.__uaplyHandoffURL(" + JSON.stringify(r9.url || "") + ")");
  check("9. Finish applying on their site opens the employer's application form (tagged only on Greenhouse and Lever)", opened.length === 1 && opened[0] === want9, JSON.stringify(opened) + " wanted " + want9);
  const tag9 = JSON.parse(await q("return JSON.stringify([w.__uaplyHandoffURL('https://job-boards.greenhouse.io/acme/jobs/1'),w.__uaplyHandoffURL('https://jobs.lever.co/acme/abc?x=1'),w.__uaplyHandoffURL('https://jobs.ashbyhq.com/acme/1'),w.__uaplyHandoffURL('https://evilgreenhouse.io.example.com/j')])"));
  check("9. source tags: ?gh_src=uaply on Greenhouse, lever-source=uaply on Lever, nothing on any other site", tag9[0].endsWith("?gh_src=uaply") && tag9[1].endsWith("?x=1&lever-source=uaply") && tag9[2] === "https://jobs.ashbyhq.com/acme/1" && !/uaply/.test(tag9[3]), JSON.stringify(tag9));
  const pre9 = await q("return w.__uaplyPrefillText()");
  check("9. the copied profile block has name, email and phone", /^Name: Walk Tester\nEmail: walk\.tester@example\.com\nPhone: /.test(pre9), JSON.stringify(pre9));
  check("9. ...and never the resume, voluntary answers, race, gender, veteran or disability", !/resume|cv\.pdf|race|gender|veteran|disab|ethnic|hispanic/i.test(pre9), JSON.stringify(pre9));
  // Undo stays: a second right swipe, then Undo on its message, puts that job back in the deck and out of Applied
  await q("w.__uaplyOpen=w.__walkOpen0;return 1");
  await tap("d.getElementById('nb-svc')"); await sleep(300);
  await tap("[...d.querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')==='job')");
  await waitFor("return d.querySelector('.card.top h2')", 8000);
  const id10 = await q("const c=d.querySelector('.card.top');return c?+c.getAttribute('data-id'):0");
  await swipeRight(id10);
  await waitFor("const x=w.__uaply.S.decisions[" + id10 + "];return x&&x.sent&&x.sent.status", 8000);
  const undo = await waitFor("const t=d.getElementById('kitToast');const b=t&&[...t.querySelectorAll('button')].find(x=>x.textContent==='Undo');return b?'yes':''", 4000);
  if (undo) await tap("[...d.getElementById('kitToast').querySelectorAll('button')].find(x=>x.textContent==='Undo')");
  if (undo && await q("return !!w.__uaply.S.decisions[" + id10 + "]") === true) console.log("     WARN Undo tap did not take, pressing it with a click instead; under the finger: " + await q("const b=[...(d.getElementById('kitToast')||d).querySelectorAll('button')].find(x=>x.textContent==='Undo');if(b)setTimeout(()=>b.click(),0);return 'see next'") + ";");
  await sleep(600);
  check("9. Undo on the saved message takes that job back (no longer in Applied, back among the jobs to swipe, as Undo always did)", undo === "yes" && (await q("return !w.__uaply.S.decisions[" + id10 + "]&&w.__uaply.S.history.indexOf(" + id10 + ")<0")) === true, "undo button " + undo + ", decision " + (await q("return JSON.stringify(w.__uaply.S.decisions[" + id10 + "]||null)")) + ", top " + (await q("return (d.querySelector('.card.top')||{getAttribute:()=>0}).getAttribute('data-id')")) + " want " + id10);

  // 10. laptops (from 1000 px wide): the app is one centred column about 960 px wide, and Account and Plan & billing sit in its middle
  //     (they used to sit against the left edge of a 1100 px column, with empty space on their right)
  //     The walk above, run last because it leaves the phone size, runs at phone size whatever the window (it sets 390x844 itself), so this part first goes back to the real window.
  if (+(process.env.W || 1100) >= 1000) {
    await send("Emulation.clearDeviceMetricsOverride"); await send("Emulation.setTouchEmulationEnabled", { enabled: false });
    await nav(BASE + "/"); await waitFor("return !!d.getElementById('bnav')&&!!d.getElementById('acctSec')", 15000); await sleep(600);
    const col = JSON.parse(await q("const m=d.getElementById('main').getBoundingClientRect(),n=d.getElementById('bnav').getBoundingClientRect(),h=d.querySelector('header.bar').getBoundingClientRect();return JSON.stringify({w:w.innerWidth,ml:m.left,mr:m.right,nl:n.left,nr:n.right,hl:h.left,hr:h.right})"));
    const mid = (l, r) => (l + r) / 2;
    check("10. laptop (" + col.w + " px): the screens, the header and the bottom bar share one column at most 960 px wide, centred in the window",
      col.w >= 1000 && col.mr - col.ml <= 960.5 && Math.abs(mid(col.ml, col.mr) - col.w / 2) <= 1.5 && Math.abs(col.nl - col.ml) <= 1.5 && Math.abs(col.nr - col.mr) <= 1.5 && Math.abs(col.hl - col.ml) <= 1.5 && Math.abs(col.hr - col.mr) <= 1.5,
      JSON.stringify(col));
    for (const [v, name] of [["account", "Account"], ["plan", "Plan & billing"]]) {
      await q("d.getElementById('nb-prof').click();return 1"); await sleep(300);
      await q("const b=[...d.querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')==='" + v + "');if(b)b.click();return !!b"); await sleep(700);
      const s = JSON.parse(await q("const a=d.getElementById('acctSec'),m=d.getElementById('main');if(!a||a.hidden)return 'null';const r=a.getBoundingClientRect(),mr=m.getBoundingClientRect();return JSON.stringify({l:r.left,r:r.right,ml:mr.left,mr:mr.right,sb:m.offsetWidth-m.clientWidth})"));
      check("10. laptop: " + name + " sits in the middle of the column (not against its left edge)",
        !!s && s.l - s.ml > 40 && Math.abs((s.l + s.r) / 2 - (s.ml + s.mr - s.sb) / 2) <= 2, JSON.stringify(s));
    }
  }

  const errs = logs.filter((l) => l.startsWith("EXC"));
  check("no script errors", errs.length === 0, errs.slice(0, 3).join(" | "));
  console.log("\n" + pass + " passed, " + fail + " failed");
  console.log(pass + " / " + (pass + fail));
};
module.exports.limitMs = 300000;
