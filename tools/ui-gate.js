// The sign-in gate (October 22, 2026, Saif): nobody reaches anything on the site without an account.
//   W=390 H=844 PORT=<sandbox port> node tools/cdp.js tools/ui-gate.js        (and W=1280 H=800)
// Signed out, the sign-up card is the whole screen: the header, the deck, Job Tracker, Profile, Hiring mode and Help are not drawn at all,
// and no job is reachable by scrolling, by the keyboard (Tab, the arrow keys that swipe), by the address (#hash), by the app's own buttons
// or by its menus. The links on the card (Terms, Privacy, Delete an account, Help and support) open. A sign-up in test mode (the
// server's providers.signupTest; otherwise the code from the sandbox's test inbox) lands on the two questions, then the cards; Sign out
// brings the gate back. The sandbox server must run with smtp {} (codes land in the test inbox).
module.exports = async ({ ev, sleep, nav, send, logs }) => {
  const PORT = process.env.PORT, W = Number(process.env.W || 1280), H = Number(process.env.H || 800), phone = W < 700;
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + "[gate " + W + "] " + name + (extra !== undefined && !ok ? "  | " + String(extra).slice(0, 400) : "")); };
  const q = (sel) => F + ".querySelector(" + JSON.stringify(sel) + ")";
  const typeIn = (sel, v) => ev("(()=>{const e=" + q(sel) + ";if(!e)return false;e.focus();e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return true})()");
  const click = (sel) => ev("(()=>{const e=" + q(sel) + ";if(!e)return false;e.click();return true})()");
  const gated = () => ev(F + ".body.classList.contains('sgGated')");
  const me = () => ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user?j.user.email:null)");
  const base = "http://127.0.0.1:" + PORT;
  const load = async (u) => { await nav(base + (u || "/?app=1")); for (let i = 0; i < 40; i++) { if (await ev("!!(" + FW + "&&" + FW + ".__uaply&&" + q(".sg-card") + ")").catch(() => false)) break; await sleep(250); } await sleep(800); };
  // what a person can see: the app's elements that are drawn, and the visible text, outside the card
  const seen = () => ev("(()=>{const d=" + F + ",w=d.defaultView,acct=d.getElementById('acctSec');" +
    "const drawn=(s)=>[...d.querySelectorAll(s)].filter(e=>e.getClientRects().length&&w.getComputedStyle(e).visibility!=='hidden').length;" +
    "const outside=[...d.body.querySelectorAll('*')].filter(e=>!acct.contains(e)&&!e.contains(acct)&&e.getClientRects().length&&w.getComputedStyle(e).visibility!=='hidden'&&!/^(SCRIPT|STYLE|LINK|META)$/.test(e.tagName));" +
    "const jobs=(w.__uaply&&w.__uaply.JOBS||[]).map(j=>j.role).filter(r=>r&&r.length>6);const txt=d.body.innerText;" +
    "return JSON.stringify({header:drawn('header.bar'),nav:drawn('#bnav'),deck:drawn('#pane-swipe'),cards:drawn('.card'),track:drawn('#pane-track'),apps:drawn('#pane-apps'),help:drawn('#uaChatBtn'),hire:drawn('[data-hire],#hireSec,.hire'),setup:drawn('#form'),outside:outside.map(e=>e.tagName+(e.id?'#'+e.id:'')).slice(0,8),jobText:jobs.filter(r=>txt.indexOf(r)>-1).slice(0,3),nJobs:jobs.length})})()").then(JSON.parse);
  const nothingBehind = (s) => !s.header && !s.nav && !s.deck && !s.cards && !s.track && !s.apps && !s.help && !s.hire && !s.setup && s.outside.length === 0 && s.jobText.length === 0;
  if (!phone) await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  await send("Storage.clearDataForOrigin", { origin: base, storageTypes: "all" });

  // ---- 1. a first visit, signed out: only the card ----
  await load();
  check("signed out, the gate is up", (await gated()) && (await me()) === null);
  let s = await seen();
  check("only the card is drawn: no header, bottom bar, deck, job card, Job Tracker, Help, Hiring mode or Profile setup, and no job's title in the page's text", nothingBehind(s), JSON.stringify(s));
  check("(the app does hold jobs behind it, so the check above means something)", s.nJobs > 0, JSON.stringify(s));
  const order = await ev("(" + q("#acctSec") + ").innerText");
  check("the card: Create your UAply account, Continue with Google, or, Email, First name, Last name, Password, the 18+ tick, Create my account, Have an account? Sign in",
    /Create your UAply account[\s\S]*Continue with Google[\s\S]*\bor\b[\s\S]*Email[\s\S]*First name[\s\S]*Last name[\s\S]*Password[\s\S]*18 or older[\s\S]*Create my account[\s\S]*Have an account\?[\s\S]*Sign in/.test(order), order.slice(0, 400));
  check("no way to put the card away: no Not now, Close, Skip or Show me jobs on it", !/Not now|Show me jobs|Close|Skip|Maybe later/.test(order), order.slice(0, 400));
  const Lw = JSON.parse(await ev("(()=>{const d=" + F + ",w=d.defaultView,c=d.querySelector('.sg-card').getBoundingClientRect();const m=d.getElementById('main');return JSON.stringify({l:c.left,r:c.right,w:c.width,vw:w.innerWidth,cw:m.clientWidth,hs:d.documentElement.scrollWidth>w.innerWidth})})()"));
  check(phone ? "phone: the card fills the width with 16 px gutters, no sideways scroll" : "laptop: the card is centered (in the screen less its scroll bar), at most 440 px wide, no sideways scroll",
    !Lw.hs && (phone ? Math.abs(Lw.l - 16) <= 1 && Math.abs(Lw.vw - Lw.r - 16) <= 1 : Lw.w <= 440.5 && Math.abs(Lw.l - (Lw.cw - Lw.r)) <= 2), JSON.stringify(Lw));

  // ---- 2. scrolling: to the bottom of the screen and past it, nothing but the card ----
  await ev("(()=>{const d=" + F + ";d.getElementById('main').scrollTop=1e6;d.scrollingElement.scrollTop=1e6;d.defaultView.scrollTo(0,1e6)})()"); await sleep(300);
  const pts = JSON.parse(await ev("(()=>{const d=" + F + ",w=d.defaultView,acct=d.getElementById('acctSec'),out=[];for(let y=5;y<w.innerHeight;y+=40)for(let x=5;x<w.innerWidth;x+=60){const e=d.elementFromPoint(x,y);if(e&&!acct.contains(e)&&e.id!=='main'&&e.id!=='pane-profile'&&e!==d.body&&e!==d.documentElement)out.push(e.tagName+(e.id?'#'+e.id:'')+'.'+e.className)}return JSON.stringify(out.slice(0,5))})()"));
  check("scrolled to the end: every point of the screen is the card or the empty page around it", pts.length === 0, JSON.stringify(pts));
  s = await seen(); check("...and still nothing behind it is drawn", nothingBehind(s), JSON.stringify(s));

  // ---- 3. the keyboard: Tab reaches only the card and its links; the arrow keys that swipe do nothing ----
  await send("Emulation.setFocusEmulationEnabled", { enabled: true });
  await ev("(()=>{const a=" + F + ".activeElement;if(a&&a.blur)a.blur()})()");
  const outsideFocus = [];
  for (let i = 0; i < 40; i++) {
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    const f = await ev("(()=>{const d=" + F + ",a=d.activeElement;if(!a||a===d.body)return 'body';return d.getElementById('acctSec').contains(a)?'':(a.tagName+'#'+a.id+'.'+a.className).slice(0,60)})()");
    if (f && f !== "body") outsideFocus.push(f);
  }
  check("40 presses of Tab never leave the card", outsideFocus.length === 0, JSON.stringify(outsideFocus.slice(0, 5)));
  const dec0 = await ev("Object.keys(" + FW + ".__uaply.S.decisions||{}).length");
  await ev("(()=>{const a=" + F + ".activeElement;if(a&&a.blur)a.blur()})()");
  for (const k of ["ArrowRight", "ArrowLeft", "ArrowRight"]) { await send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code: k, windowsVirtualKeyCode: k === "ArrowRight" ? 39 : 37 }); await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code: k, windowsVirtualKeyCode: k === "ArrowRight" ? 39 : 37 }); await sleep(400); }
  check("the arrow keys that swipe a card do nothing: no job is applied to or passed", (await ev("Object.keys(" + FW + ".__uaply.S.decisions||{}).length")) === dec0 && (await gated()));
  await send("Emulation.setFocusEmulationEnabled", { enabled: false });

  // ---- 4. the address and the app's own ways in: #hash, the tabs and menus, the app's show() ----
  for (const h of ["#swipe", "#dash", "#apps", "#profile", "#hire"]) { await ev(FW + ".location.hash=" + JSON.stringify(h) + ";top.location.hash=" + JSON.stringify(h)); await sleep(250); }
  s = await seen(); check("an address ending in #swipe, #dash, #apps, #profile or #hire shows only the card", nothingBehind(s) && (await gated()), JSON.stringify(s));
  await ev("(()=>{const d=" + F + ";['nb-svc','nb-dash','nb-prof'].forEach(id=>{const b=d.getElementById(id);if(b)b.click()});[...d.querySelectorAll('.nitem')].forEach(b=>{try{b.click()}catch(e){}})})()"); await sleep(600);
  s = await seen(); check("every tab and menu item pressed by script: still only the card", nothingBehind(s) && (await gated()), JSON.stringify(s));
  await ev("(()=>{const A=" + FW + ".__uaply;['swipe','apps','dash','profile'].forEach(t=>{try{A.show(t)}catch(e){}})})()"); await sleep(600);
  s = await seen(); check("the app's own show('swipe'), show('apps'): still only the card", nothingBehind(s) && (await gated()) && !!(await ev("!!" + q(".sg-su"))), JSON.stringify(s));
  await ev("(()=>{const b=" + F + ".getElementById('hdrAcct')||" + F + ".querySelector('.hirebtn,[data-hire]');if(b)b.click()})()"); await sleep(400);
  s = await seen(); check("the header's buttons (Sign in, Switch to hiring) pressed by script: still only the card", nothingBehind(s), JSON.stringify(s));

  // ---- 5. the links on the card open: Terms, Privacy, Delete an account, Help and support ----
  const links = JSON.parse(await ev("JSON.stringify([...(" + F + ").querySelectorAll('.sg-legal a')].map(a=>({t:a.textContent,h:a.href,n:a.target})))"));
  check("the card links Terms, Privacy, Delete an account and Help and support, each in a new tab", links.length === 4 && links.every((l) => l.n === "_blank") &&
    /Terms/.test(links.map((l) => l.t).join()) && /Privacy/.test(links.map((l) => l.t).join()) && /Delete/.test(links.map((l) => l.t).join()) && /Help/.test(links.map((l) => l.t).join()), JSON.stringify(links));
  const codes = JSON.parse(await ev("Promise.all(" + JSON.stringify(links.map((l) => l.h)) + ".map(u=>fetch(u).then(r=>r.status+' '+(r.headers.get('content-type')||'')))).then(x=>JSON.stringify(x))"));
  check("...and every one of them answers (an HTML page, no account needed)", codes.length === 4 && codes.every((c) => /^200 text\/html/.test(c)), JSON.stringify(codes));
  const tl = JSON.parse(await ev("JSON.stringify([...(" + F + ").querySelectorAll('.sg-agree a')].map(a=>a.href))"));
  check("the Terms and Privacy links in the 18+ line answer too", tl.length === 2 && (await ev("Promise.all(" + JSON.stringify(tl) + ".map(u=>fetch(u).then(r=>r.status))).then(x=>x.every(c=>c===200))")), JSON.stringify(tl));
  const tg = JSON.parse(await ev("JSON.stringify([...(" + F + ").querySelectorAll('.sg-legal a')].map(a=>{const r=a.getBoundingClientRect();return Math.round(r.height)}))"));
  check("the links are 44 px tall targets", tg.every((h) => h >= 44), JSON.stringify(tg));

  // ---- 6. sign up (test mode: the server signs the person in at once, or the code from the test inbox), then the two questions ----
  const stamp = Date.now().toString(36), email = "gate." + stamp + "@example.com";
  const prov = JSON.parse(await ev("fetch('/api/auth/providers').then(r=>r.json()).then(j=>JSON.stringify(j))"));
  await typeIn("[data-email] input", email); await typeIn(".sg-fn input", "Gale"); await typeIn(".sg-ln input", "Tester"); await typeIn(".sg-pw input", "Gate-" + stamp + "-pw");
  await click(".sg-su .sg-ag"); await click(".sg-su [type=submit]"); await sleep(1800);
  let t = await ev("(" + q("#acctSec") + ").innerText");
  if (!prov.signupTest) {
    console.log("  (this server is not in sign-up test mode: providers.signupTest is " + prov.signupTest + "; the code comes from the test inbox)");
    check("not test mode: the code step, still behind the gate", /Check your email/.test(t) && (await gated()), t.slice(0, 200));
    const code = await ev("fetch('/outbox').then(r=>r.text()).then(t=>{const m=t.match(/([0-9]{6}) is your UAply verification code/);return m?m[1]:''})");
    await typeIn(".sg-code input", code); await sleep(2000);
    t = await ev("(" + q("#acctSec") + ").innerText");
  }
  check("the sign-up lands on the two questions (Account created, Gale. 1 of 2), still behind the gate", /Account created, Gale/.test(t) && /1 of 2/i.test(t) && (await gated()), t.slice(0, 300));
  check("signed in as the new account", (await me()) === email);
  s = await seen(); check("during the questions nothing behind the card is drawn either", nothingBehind(s), JSON.stringify(s));
  await click(".sg-next"); await sleep(400); await click(".sg-next"); await sleep(500); await click(".sg-next"); await sleep(1200);
  check("after the questions the gate is gone and the cards are on screen", !(await gated()) && (await ev("!" + F + ".getElementById('pane-swipe').hidden")) && (await ev("!!" + q("#bnav") + "&&" + q("#bnav") + ".getClientRects().length>0")));
  await load();
  check("a reload, signed in: the app as before, no gate", !(await gated()) && (await me()) === email);

  // ---- 7. Sign out brings the gate back ----
  await ev("(()=>{const d=" + F + ";d.getElementById('nb-prof').click();const it=[...d.querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')==='account');if(it)it.click()})()"); await sleep(1200);
  await click("[data-auth=sout]"); await sleep(1800);
  s = await seen();
  check("Sign out: the gate is back, the card is empty, nothing behind it is drawn", (await gated()) && (await me()) === null && nothingBehind(s) &&
    (await ev(q("[data-email] input") + ".value")) === "", JSON.stringify(s));
  await load();
  check("and after a reload, signed out: the gate", (await gated()) && nothingBehind(await seen()));

  const errs = logs.filter((l) => !/favicon|ERR_FILE_NOT_FOUND|401/.test(l));
  check("no script errors", errs.length === 0, errs.join(" | "));
  console.log("\n" + (n - bad) + " / " + n);
  if (bad) throw new Error(bad + " gate check(s) failed");
};
