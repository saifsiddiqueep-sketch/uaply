// Sign-up v2 in a real browser (the sandbox's "Sign-up, nothing hidden" card): layout, the typo fix, the tick box, sign-up with an emailed code,
// the two questions (Enter, Esc, Skip/Continue), what is kept on the device, sign-in by code, and Continue with Google against the stand-in.
// Also: a redraw of the Account screen while someone types (a late start-up answer) keeps them in the box with the caret where it was, and
// after Sign out in the app the next person gets an empty card with the box unticked.
// A shared device (Saif's note on PR #49/#50, Oct 22): Sign out asks whether to remove this person's details (default keeps them); a sign-in
// by code to an existing account B on a device holding A's profile and phone asks Keep / Start fresh in the card's own sheet, and Start
// fresh gives B an empty phone; a new account on a device holding someone's profile and swipes asks too, and Start fresh empties Applied;
// a name typed with a@gmail.com never goes to the Google account b@gmail.com that comes back (empty name boxes, the name question).
// Fix round 1: the question never shows the other person's name; while it is open (also after a reload, over the swipe deck) no key
// reaches the deck and a waiting application is held, then dropped by Start fresh; Start fresh also clears what UAply learned, the saved
// location and the plan; a profile email typed before any account never counts as another person's; Keep on a new account keeps the
// saved profile's name as it is; and the account the kept profile came from signs in again without the question.
// Fix round 2: after Keep the profile carries the new account's own email (the live server sends straight to an employer only from the
// account's email), and the first account gets its own back when it signs in again; Start fresh and Remove also clear the help chat's
// record (its agreement to the AI notice); a held application that is dropped is answered "not sent" (409), never a failed request; and a
// sign-in that does not come through the card (the app's own sign-in hook) gets the same question, holding an application asked for first.
//   W=1280 H=720 PORT=<sandbox port> MOCK_GOOGLE_PORT=8790 node tools/cdp.js tools/ui-signup.js      (W=390 H=844 for a phone)
// The sandbox server must run with smtp {} (codes land in the test inbox) and, for the Google part, google.* pointing at tools/mock-google.py.
// Each run emails 13 codes from 127.0.0.1 and makes 4 accounts by code (the server allows 80 codes an hour per connection, and 10 sign-ups
// an hour from this computer): give each run its own fresh server data folder.
module.exports = async ({ ev: ev0, sleep, nav, send, logs }) => {
  const ev = async (x) => { try { return await ev0(x); } catch (e) { await sleep(700); try { return await ev0(x); } catch (e2) { return "CDPERR " + e2.message + " in " + String(x).slice(0, 80); } } };
  const PORT = process.env.PORT, MG = process.env.MOCK_GOOGLE_PORT || "";
  const W = Number(process.env.W || 1280), H = Number(process.env.H || 720), phone = W < 700;
  const F = "document.querySelector('iframe').contentDocument";
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra && !ok ? "  " + extra : "")); };
  const q = (sel) => F + ".querySelector(" + JSON.stringify(sel) + ")";
  const text = () => ev("(" + F + ".getElementById('acctSec')||{innerText:''}).innerText");
  const typeIn = (sel, v) => ev("(()=>{const e=" + q(sel) + ";if(!e)return false;e.focus();e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return true})()");
  const click = (sel) => ev("(()=>{const e=" + q(sel) + ";if(!e)return false;e.click();return true})()");
  const key = (sel, k) => ev("(()=>{const e=" + q(sel) + "||" + F + ".activeElement;e.dispatchEvent(new KeyboardEvent('keydown',{key:" + JSON.stringify(k) + ",bubbles:true,cancelable:true}));return true})()");
  // the codes in the test inbox for one address, newest first (the outbox lists mail newest first: "<b>123456 is your ...</b> to addr<time>")
  const codesTo = (addr) => ev("fetch('/outbox').then(r=>r.text()).then(t=>{const re=/([0-9]{6}) is your UAply verification code<\\/b> to ([^<]+?)<time>/g,o=[];let m;while((m=re.exec(t)))if(m[2].trim().toLowerCase()===" + JSON.stringify(addr.toLowerCase()) + ")o.push(m[1]);return JSON.stringify(o)})").then(JSON.parse);
  const usedCodes = new Set();
  const markSeen = async (addr) => { for (const c of await codesTo(addr)) usedCodes.add(addr + c); };
  // waits (up to 6 s) for a code to that address that no step has used yet
  const codeFor = async (addr) => {
    for (let i = 0; i < 24; i++) { const l = await codesTo(addr); if (l.length && !usedCodes.has(addr + l[0])) { l.forEach((c) => usedCodes.add(addr + c)); return l[0]; } await sleep(250); }
    return "";
  };
  const typeCode = (c) => typeIn(".sg-code input", c);
  const openAccount = async () => {
    await ev("(()=>{const b=[...(" + F + ").querySelectorAll('button')].find(x=>x.offsetParent&&x.innerText.trim()==='Not now');if(b)b.click()})()"); await sleep(400);
    await ev(F + ".getElementById('nb-prof').click()"); await sleep(400);
    await ev("[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Account')).click()"); await sleep(1800);
  };
  const load = async (u) => { await nav("http://127.0.0.1:" + PORT + (u || "/?app=1")); await sleep(3500); };
  const FW = "document.querySelector('iframe').contentWindow";
  const logout = () => ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})");
  const post = (path, body) => ev("fetch(" + JSON.stringify(path) + ",{method:'POST',headers:{'Content-Type':'application/json'},body:" + JSON.stringify(JSON.stringify(body)) + "}).then(r=>r.status)");
  // the sheet that asks before anything on the device is kept or removed (shared/uaply-signup.js sheet())
  const sheetText = () => ev("(()=>{const s=" + F + ".querySelector('.sg-sheet');return s?s.innerText:''})()");
  const choose = async (label) => {
    const ok = await ev("(()=>{const b=[...(" + F + ").querySelectorAll('.sg-sheet button')].find(x=>x.textContent.trim()===" + JSON.stringify(label) + ");if(!b)return false;b.click();return true})()");
    for (let i = 0; ok && i < 30 && (await ev("!!" + F + ".querySelector('.sg-sheet')")) === true; i++) await sleep(100);
    await sleep(1200); return ok;
  };
  const chatRec = () => ev(FW + ".localStorage.getItem(" + FW + ".__uaplyKey+'.chat')");
  // the browser's own confirm box must never be the question: count any call to it
  const spyConfirm = () => ev("(()=>{const fw=" + FW + ";fw.__conf=0;fw.confirm=function(){fw.__conf++;return true};return true})()");
  const confirms = () => ev(FW + ".__conf||0");
  // what this device holds: the profile, the phone, the swipe list, the record of whose it is
  const device = () => ev("(()=>{const w=" + FW + ",k=w.__uaplyKey,j=(x)=>{try{return JSON.parse(w.localStorage.getItem(x))}catch(e){return null}};const s=j(k)||{},a=j(k+'.acct')||{},p=s.profile||{};" +
    "return JSON.stringify({name:p.name||'',email:p.email||'',phone:a.phone||'',swipes:Object.keys(s.decisions||{}).length,apps:Object.keys(a.apps||{}).length,owner:j(k+'.signup.owner')})})()").then(JSON.parse);
  const sheetBox = () => ev("(()=>{const c=" + F + ".querySelector('.sg-sheet .sg-card'),fw=" + FW + ";if(!c)return null;const r=c.getBoundingClientRect();return JSON.stringify({l:r.left,r:r.right,t:r.top,b:r.bottom,vw:fw.innerWidth,vh:fw.innerHeight})})()").then((x) => x && JSON.parse(x));
  const fits = (b) => !!b && b.l >= 0 && b.t >= 0 && b.r <= b.vw + 0.5 && b.b <= b.vh + 0.5 && (!phone || (Math.abs(b.l - 16) <= 1 && Math.abs(b.vw - b.r - 16) <= 1));
  const appliedRows = async () => {
    await ev(F + ".getElementById('nb-dash').click()"); await sleep(400);
    await ev("[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Applied')).click()"); await sleep(900);
    return ev("[...(" + F + ").querySelectorAll('#pane-track .row')].filter(r=>r.offsetParent).length");
  };
  const stamp = Date.now().toString(36);

  if (!phone) await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });   // no animation timing in the checks
  await load();
  // account B for the shared-device checks below, made by code from the top page (nothing on this device changes), then signed out
  const bm = "b." + stamp + "@example.com";
  await post("/api/auth/signup", { email: bm, agree: true, passwordless: true }); await sleep(900);
  const bCode = await codeFor(bm);
  check("account B exists (made by code, then signed out)", (await post("/api/auth/code/verify", { email: bm, code: bCode, agree: true })) === 200);
  await logout();
  await openAccount();

  // ---- layout (Mohammed's Oct 21 call) ----
  const L = JSON.parse(await ev("(()=>{const d=" + F + ",fw=d.defaultView,r=(s)=>{const e=d.querySelector(s);return e&&e.getBoundingClientRect()};" +
    "const c=r('.sg-card'),g=r('[data-sg=google]'),b=r('.sg-bb'),m=d.getElementById('main'),mr=m.getBoundingClientRect(),inner=mr.left+m.clientLeft,innerW=m.clientWidth;" +
    "return JSON.stringify({c:c&&{l:c.left,r:c.right,t:c.top,w:c.width},g:g&&{b:g.bottom},b:b&&{b:b.bottom,cx:(b.left+b.right)/2},vw:fw.innerWidth,vh:fw.innerHeight,mainL:inner,mainW:innerW,hs:d.documentElement.scrollWidth>fw.innerWidth,old:!!d.getElementById('signBox')})})()"));
  check("the new card replaces the old one (no #signBox)", !!L.c && !L.old, JSON.stringify(L));
  check("Continue with Google is above the fold", !!L.g && L.g.b < L.vh, JSON.stringify(L.g) + " vh " + L.vh);
  check("the brand mark sits directly above the card (gap under 16 px) and is centered on it", !!L.b && L.c.t - L.b.b >= 0 && L.c.t - L.b.b <= 16 && Math.abs(L.b.cx - (L.c.l + L.c.w / 2)) <= 2, JSON.stringify(L));
  check("the card is centered in the screen's column", Math.abs((L.c.l - L.mainL) - (L.mainL + L.mainW - L.c.r)) <= 2, JSON.stringify(L));
  if (phone) check("phone: the card fills the width with 16 px gutters", Math.abs(L.c.l - 16) <= 1 && Math.abs(L.vw - L.c.r - 16) <= 1, JSON.stringify(L));
  else check("laptop: the card is at most 440 px wide", L.c.w <= 440.5, JSON.stringify(L.c));
  check("no sideways scrolling", !L.hs);
  let t = await text();
  check("the card reads in Mohammed's order: Google, or, Email, First name, Last name, the 18+ tick, Create my account, Sign in",
    /Create your UAply account[\s\S]*Continue with Google[\s\S]*\bor\b[\s\S]*Email[\s\S]*First name[\s\S]*Last name[\s\S]*Kept on this device[\s\S]*18 or older[\s\S]*Create my account[\s\S]*Have an account\?[\s\S]*Sign in/.test(t) && !/18 or older[\s\S]*Continue with Google/.test(t), t.slice(0, 400));
  const G = JSON.parse(await ev("(()=>{const d=" + F + ",y=(s)=>{const e=d.querySelector(s);return e?Math.round(e.getBoundingClientRect().bottom):-1};return JSON.stringify({g:y('[data-sg=google]'),tick:y('.sg-agree'),create:y('.sg-su [type=submit]')})})()"));
  console.log("  measured: Google bottom " + G.g + " px, tick bottom " + G.tick + " px, Create bottom " + G.create + " px, window " + L.vh + " px");
  check("no password box anywhere on the card", !(await ev("!!" + F + ".querySelector('#acctSec input[type=password]')")));
  check("no 'where your details go' map or live summary", !/Where your details go/i.test(t));
  check("every field has a label", await ev("[..." + F + ".querySelectorAll('.sg-card input:not([type=checkbox])')].every(i=>i.labels&&i.labels.length)"));

  // ---- validation ----
  await click(".sg-su [type=submit]"); await sleep(400);
  t = await text();
  check("Create my account with nothing filled shows every problem at once", /Tick the box/.test(t) && /Enter your email/.test(t) && /Add your first name/.test(t) && /Add your last name/.test(t), t.slice(0, 600));
  check("focus goes to the first problem in page order (the email box)", await ev(F + ".activeElement&&!!" + F + ".activeElement.closest('[data-email]')"));
  await typeIn("[data-email] input", "sam@gmial.com"); await sleep(800);
  check("a typo in the domain offers the fix", (await ev("(" + q(".sg-fix") + "||{}).textContent")) === "sam@gmail.com");
  await click(".sg-fix"); await sleep(200);
  check("one tap fixes it", (await ev(q("[data-email] input") + ".value")) === "sam@gmail.com");

  // ---- the Account screen redrawn while someone types (a late start-up answer on a slow connection): they stay in the box ----
  await send("Emulation.setFocusEmulationEnabled", { enabled: true });   // a window in front, as for a person typing: focus events fire
  const active = () => ev("(()=>{const a=" + F + ".activeElement;let s=null;try{s=a.selectionStart}catch(e){}return JSON.stringify({f:a&&a.getAttribute&&a.getAttribute('data-f'),v:a&&a.value,s:s,same:a&&a.isConnected})})()").then(JSON.parse);
  await ev("(()=>{const e=" + q("[data-email] input") + ";e.focus()})()");
  await ev(F + ".defaultView.__uaplyAuthApi.redraw()"); await sleep(150);
  let A1 = await active();
  await send("Input.insertText", { text: "x" }); await sleep(100);
  const afterType = await ev(q("[data-email] input") + ".value");
  check("a redraw while typing the email keeps focus in the email box, and the next letter lands at the end", A1.f === "email" && A1.v === "sam@gmail.com" && afterType === "sam@gmail.comx", JSON.stringify(A1) + " then " + afterType);
  await typeIn("[data-email] input", "sam@gmail.com");
  await typeIn(".sg-fn input", "Sa");
  await ev("(()=>{const e=" + q(".sg-fn input") + ";e.focus();e.setSelectionRange(1,1);e.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true}))})()");
  await ev(F + ".defaultView.__uaplyAuthApi.redraw()"); await sleep(150);
  A1 = await active();
  check("...and in the first-name box the caret stays where it was", A1.f === "First name" && A1.v === "Sa" && A1.s === 1, JSON.stringify(A1));
  await typeIn(".sg-fn input", "");
  await ev("(()=>{const a=" + F + ".activeElement;if(a&&a.blur)a.blur()})()"); await sleep(50);
  await ev(F + ".defaultView.__uaplyAuthApi.redraw()"); await sleep(150);
  A1 = await active();
  check("...but a person who left the box on purpose is not pulled back into it", A1.f === null || A1.f === undefined || A1.f === "", JSON.stringify(A1));
  await send("Emulation.setFocusEmulationEnabled", { enabled: false });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "no-preference" }] });   // the shake is motion
  await click("[data-sg=google]"); await sleep(120);
  const shook = await ev(q(".sg-agree") + ".classList.contains('sg-shake')");
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  await sleep(400);
  t = await text();
  check("an unticked Google tap stays on the card, shakes the box, says why and moves focus to the box",
    /Tick the box first, then Continue with Google/.test(t) && (await ev("location.pathname")) === "/" && shook === true && (await ev(F + ".activeElement&&" + F + ".activeElement.classList.contains('sg-ag')")), "shook " + shook);
  await click("[data-sg=google]"); await sleep(300);
  check("with reduced motion the box does not shake (the message still shows)", (await ev(q(".sg-agree") + ".classList.contains('sg-shake')")) === false && /Tick the box first/.test(await text()));

  // ---- sign up with an emailed code ----
  const email = "sg." + stamp + "@example.com";
  await ev("(()=>{const a=" + q(".sg-ag") + ";a.click()})()");
  await typeIn("[data-email] input", email); await typeIn(".sg-fn input", "Sam"); await typeIn(".sg-ln input", "Rivera");
  await key(".sg-ln input", "Enter");     // a real Enter submits the form; dispatching keydown does not, so press the button like Enter would
  await click(".sg-su [type=submit]"); await sleep(1500);
  t = await text();
  check("Create my account goes to the code step, no password asked", /Check your email/.test(t) && t.includes(email), t.slice(0, 300));
  check("the sandbox says where the code is (test inbox)", /test inbox/.test(t));
  check("nobody is signed in before the code is typed", (await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user)")) === null);
  check("six code boxes", (await ev(F + ".querySelectorAll('.sg-code input').length")) === 6);
  await typeCode("000000"); await sleep(1200);
  t = await text();
  check("a wrong code says so and the boxes clear", /not right/.test(t) && (await ev(q(".sg-code input") + ".value")) === "", t.slice(0, 300));
  const code1 = await codeFor(email);
  check("the code is in the test inbox", /^[0-9]{6}$/.test(code1));
  await typeCode(code1); await sleep(1800);
  t = await text();
  check("the right code: 'Account created, Sam.' and question 1 of 2", /Account created, Sam\./.test(t) && /1 of 2/i.test(t) && /What kind of work are you after\?/.test(t), t.slice(0, 300));
  const me = JSON.parse(await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>JSON.stringify(j.user))"));
  check("the session is real and the email is verified", me && me.email === email && me.emailVerified === true && me.hasPassword === false, JSON.stringify(me));
  const pv = await ev(q(".sg-pv") + ".textContent");      // on a phone the preview is folded into one line that opens
  check("the preview already shows the name and the verified email", /Sam Rivera/.test(pv) && pv.includes(email) && /Your email is confirmed/.test(pv), pv.slice(0, 300));
  check("the preview counts the app's minimum to apply (2 of 3: a phone number or a resume still needed), nothing promised for later",
    /2 of 3 needed/.test(pv) && /Phone or resume\s*Needed before UAply can apply/.test(pv) && !/only when a job needs/i.test(pv), pv.slice(0, 400));
  check("the main button reads Skip while nothing is picked", (await ev(q(".sg-next") + ".textContent")) === "Skip");
  await ev("[..." + F + ".querySelectorAll('.sg-chip')].find(b=>b.textContent==='Barista').click()"); await sleep(150);
  check("and Continue once something is picked", (await ev(q(".sg-next") + ".textContent")) === "Continue");
  await key(".sg-qs input", "Enter"); await sleep(400);
  t = await text();
  check("Enter advances to question 2 of 2", /2 of 2/i.test(t) && /Where do you want to work\?/.test(t), t.slice(0, 200));
  await key(".sg-qs input", "Escape"); await sleep(400);
  t = await text();
  check("Esc goes back to question 1, with the pick kept", /1 of 2/i.test(t) && (await ev("[..." + F + ".querySelectorAll('.sg-chip')].find(b=>b.textContent==='Barista').getAttribute('aria-pressed')")) === "true");
  await click(".sg-next"); await sleep(400);
  await typeIn(".sg-qs input", "Austin, TX"); await click(".sg-rem"); await sleep(100);
  await click(".sg-next"); await sleep(400);
  t = await text();
  check("then 'Almost ready': a phone number or a resume before UAply can apply, one tap from each, and the line about employers' own sites",
    /Almost ready/.test(t) && /Before UAply can apply, add a phone number or a resume/.test(t) && /open their own site/.test(t) && !/only when a job needs/i.test(t) &&
    (await ev("!!" + q("[data-ready=phone]") + "&&!!" + q("[data-ready=resume]"))), t.slice(0, 300));
  await click(".sg-next"); await sleep(1200);
  check("Start swiping goes to the cards", await ev("!" + F + ".getElementById('pane-swipe').hidden"));
  const P = JSON.parse(await ev("(()=>{const w=document.querySelector('iframe').contentWindow,k=w.__uaplyKey;const s=JSON.parse(w.localStorage.getItem(k)||'{}'),a=JSON.parse(w.localStorage.getItem(k+'.acct')||'{}');return JSON.stringify({p:s.profile||{},titleOnly:a.fTitleOnly})})()"));
  check("kept on this device: name, first pick as the target title, city, remote (and nothing hides the other roles)",
    P.p.name === "Sam Rivera" && P.p.title === "Barista" && P.p.loc === "Austin, TX" && P.p.custom === true && P.p.modes && P.p.modes.remote && P.p.modes.onsite && P.titleOnly === false, JSON.stringify(P));
  check("the example profile's skills were not copied into the new profile", Array.isArray(P.p.skills) && P.p.skills.length === 0);
  await openAccount();
  t = await text();
  check("the app's signed-in card says how a code account signs in (no 'You sign in with Google', no 'Forgot password')",
    /You sign in with an emailed code/.test(t) && !/You sign in with Google/.test(t) && !/Forgot password/.test(t), t.slice(0, 600));
  check("...and keeps the readiness checklist", /Not ready to apply yet|Ready to apply/.test(t));

  // ---- Sign out in the app (no reload): it asks first; the next person on this device starts from an empty card ----
  await ev(FW + ".__uaplyAuthApi.acct(a=>{a.phone='215-555-0100'})");   // A (Sam) has a phone saved on this device
  await spyConfirm();
  await click("[data-auth=sout]"); await sleep(500);
  let st = await sheetText();
  check("Sign out asks first, in the card's own sheet: 'Remove my details from this device', unticked, and nobody is signed out yet",
    /Sign out of UAply\?/.test(st) && /Remove my details from this device/.test(st) && (await ev("!" + q(".sg-sheet .sg-rm") + ".checked")) &&
    !!(await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user)")) && (await confirms()) === 0, st.slice(0, 300));
  check("...the sheet fits the screen" + (phone ? " with 16 px gutters" : ""), fits(await sheetBox()), JSON.stringify(await sheetBox()));
  await choose("Sign out");
  const E = JSON.parse(await ev("(()=>{const d=" + F + ",v=(s)=>{const e=d.querySelector(s);return e?(e.type==='checkbox'?e.checked:e.value):null};return JSON.stringify({card:!!d.querySelector('.sg-su'),email:v('[data-email] input'),first:v('.sg-fn input'),last:v('.sg-ln input'),ticked:v('.sg-ag'),me:null})})()"));
  E.me = await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user)");
  check("Sign out in the app, then the card: no email, no name, the box unticked (the next person's tick is their own)",
    E.card && E.email === "" && E.first === "" && E.last === "" && E.ticked === false && E.me === null, JSON.stringify(E));
  let D = await device();
  check("...left unticked, Sign out keeps A's details on this device (name, phone) and whose they are", D.name === "Sam Rivera" && D.phone === "215-555-0100" && D.owner && D.owner.email === email, JSON.stringify(D));

  // ---- sign in again with a code ----
  await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})");
  await load(); await openAccount();
  await click(".sg-to-in"); await sleep(300);
  t = await text();
  check("Have an account? Sign in opens 'Welcome back' with Google, or, Email, Email me a code", /Welcome back[\s\S]*Continue with Google[\s\S]*Email[\s\S]*Email me a code[\s\S]*New here\?/.test(t), t.slice(0, 300));
  await key("[data-email] input", "Escape"); await sleep(300);
  check("Esc on sign-in goes back to Create your account", /Create your UAply account/.test(await text()));
  await click(".sg-to-in"); await sleep(300);
  await typeIn("[data-email] input", email); await click(".sg-si [type=submit]"); await sleep(1500);
  t = await text();
  check("Email me a code never says whether the address has an account", /If .* has a UAply account, we sent it a 6-digit code/.test(t), t.slice(0, 200));
  await typeCode(await codeFor(email)); await sleep(1800);
  t = await text();
  check("the code signs in: 'You're signed in, Sam.' (the name kept on this device)", /You’re signed in, Sam\./.test(t), t.slice(0, 200));
  check("...the same person on the same device: no question about the profile", !(await sheetText()), await sheetText());
  await click(".sg-start"); await sleep(800);

  // ---- PR #49 finding 5: B signs in by code to an EXISTING account on a device that holds A's profile and phone ----
  await logout(); await load(); await spyConfirm(); await openAccount();
  await click(".sg-to-in"); await sleep(300);
  await typeIn("[data-email] input", bm); await click(".sg-si [type=submit]"); await sleep(1500);
  await typeCode(await codeFor(bm)); await sleep(1800);
  st = await sheetText(); D = await device();
  check("B signs in by code on a device holding A's profile: 'This device holds another person’s profile. Start fresh for " + bm + "?' with Keep and Start fresh, and nothing of A's shown (no name)",
    /This device holds another person’s profile\./.test(st) && st.includes("Start fresh for " + bm + "?") && !/Sam|Rivera/.test(st) && !!(await ev("!!" + q(".sg-sheet [data-sh=no]") + "&&" + q(".sg-sheet [data-sh=no]") + ".textContent==='Keep'&&" + q(".sg-sheet [data-sh=yes]") + ".textContent==='Start fresh'")), st.slice(0, 400));
  check("...in the card's own style (a sheet, not the browser's confirm box), and nothing is removed before B answers",
    (await confirms()) === 0 && (await ev("!!" + q(".sg-sheet .sg-card.sg-pop") + "&&" + q(".sg-sheet [role=alertdialog]") + ".getAttribute('aria-modal')==='true'")) && D.phone === "215-555-0100" && D.name === "Sam Rivera", JSON.stringify(D));
  check("...the sheet fits the screen" + (phone ? " with 16 px gutters" : "") + " and focus is inside it", fits(await sheetBox()) && (await ev("!!" + q(".sg-sheet") + ".contains(" + F + ".activeElement)")), JSON.stringify(await sheetBox()));
  await choose("Start fresh");
  t = await text(); D = await device();
  check("Start fresh: B is signed in with B's own profile, the phone empty, nothing of A's name left",
    /You’re signed in\./.test(t) && t.includes(bm) && !/Sam/.test(t) && D.email === bm && D.phone === "" && D.name === "" && D.owner && D.owner.email === bm, JSON.stringify(D) + " " + t.slice(0, 300));
  check("...and the card says what was removed from this device", /You chose Start fresh: the other person’s profile, phone, resume, saved answers and swipe list were removed from this device/.test(t), t.slice(0, 400));
  await click(".sg-start"); await sleep(800);

  // ---- Sign out with "Remove my details from this device" (Saif, Oct 22): B's profile, phone, resume, answers and swipes leave the device ----
  await ev("(()=>{const w=" + FW + ",A=w.__uaply,j=A.JOBS[0];A.S.profile.name='Bea Brown';A.S.decisions[j.id]={s:'applied',at:Date.now(),pct:80,as:'Bea',title:''};A.S.history.push(j.id);A.save();" +
    "w.__uaplyAuthApi.acct(a=>{a.phone='267-555-0199';a.resumeName='bea.pdf';a.resumeData='data:application/pdf;base64,AAAA'});w.localStorage.setItem(w.__uaplyKey+'.answers',JSON.stringify({q1:'yes'}));" +
    "w.localStorage.setItem(w.__uaplyKey+'.loc',JSON.stringify({lat:39.95,lon:-75.17,at:Date.now(),asked:true}));" +
    "w.localStorage.setItem(w.__uaplyKey+'.chat',JSON.stringify({aiOk:Date.now(),given:Date.now()}));return true})()");
  await openAccount();
  await click("[data-auth=sout]"); await sleep(500);
  await ev("(()=>{const c=" + q(".sg-sheet .sg-rm") + ";c.click();return c.checked})()");
  await choose("Sign out"); await sleep(300);
  D = await device(); t = await text();
  const leftover = await ev("(()=>{const w=" + FW + ",k=w.__uaplyKey;return JSON.stringify([w.localStorage.getItem(k+'.answers'),w.localStorage.getItem(k+'.signup'),JSON.parse(w.localStorage.getItem(k+'.acct')||'{}').resumeName||''])})()");
  check("ticked: signed out, and B's profile, phone, resume, saved answers and swipe list are gone from this device (and the record of whose they were)",
    (await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user)")) === null && D.name === "" && D.email === "" && D.phone === "" && D.swipes === 0 && D.apps === 0 && D.owner === null && leftover === '[null,null,""]',
    JSON.stringify(D) + " " + leftover);
  check("...and the screen says so", /Your details were removed from this device/.test(t), t.slice(0, 300));
  check("...and the saved device location is gone too", (await ev(FW + ".localStorage.getItem(" + FW + ".__uaplyKey+'.loc')")) === null);
  check("...and so is the help chat's record: B's agreement to the AI notice never carries over to the next person", (await chatRec()) === null, String(await chatRec()));

  // ---- fix round 1 (CISO): B's session at page load on a device holding A's profile, a waiting application, learned swipes, a location
  // and a plan. The question opens over the swipe deck: no key reaches the deck, the waiting application is held, Start fresh drops it ----
  const al = "al." + stamp + "@example.com";
  await post("/api/auth/code/send", { email: bm }); await sleep(900);
  check("B signs in (code, from the top page) for the reload check", (await post("/api/auth/code/verify", { email: bm, code: await codeFor(bm) })) === 200);
  await ev("(()=>{const w=" + FW + ",A=w.__uaply,k=w.__uaplyKey,j=A.JOBS[0];A.S.profile=Object.assign({},A.S.profile,{name:'Al Apple',email:'" + al + "',custom:true});" +
    "A.S.decisions={};A.S.decisions[j.id]={s:'applied',at:Date.now(),pct:80,as:'Al',title:'',sent:{at:Date.now(),to:'',status:'pending'}};A.S.history=[j.id];" +
    "if(A.S.learn&&Array.isArray(A.S.learn.ev)){A.S.learn.ev.push({id:j.id,at:Date.now(),k:'R',d:4000,a:['c:acme']});A.S.learn.n=(A.S.learn.n||0)+1}A.save();" +
    "w.__uaplyAuthApi.acct(a=>{a.phone='215-555-0111';a.plan='pro';a.pay=[{at:Date.now(),plan:'pro',amt:9}];a.fCo='Acme'});" +
    "w.localStorage.setItem(k+'.signup.owner',JSON.stringify({email:'" + al + "',kept:false}));w.localStorage.setItem(k+'.consent',JSON.stringify({v:3,at:Date.now(),agent:true}));" +
    "w.localStorage.setItem(k+'.loc',JSON.stringify({lat:39.95,lon:-75.17,at:Date.now(),asked:true}));w.localStorage.setItem(k+'.chat',JSON.stringify({aiOk:Date.now()}));return true})()");
  const alApps = () => ev("fetch('/api/outbox').then(r=>r.json()).then(j=>(j.applications||[]).filter(a=>a.candidate&&a.candidate.email===" + JSON.stringify(al) + ").length)");
  await load(); await sleep(3000);   // the jobs load, and 1.5 s later the app sends waiting applications again
  st = await sheetText();
  const R = () => ev("(()=>{const d=" + F + ",w=" + FW + ",s=d.querySelector('.sg-sheet'),x=w.__uaply.S.decisions,ids=Object.keys(x);return JSON.stringify({sheet:!!s,inSheet:!!(s&&s.contains(d.activeElement)),n:ids.length,st:ids.map(i=>x[i].s+':'+((x[i].sent||{}).status||'')).join(','),deck:!!(d.getElementById('pane-swipe')&&!d.getElementById('pane-swipe').hidden&&d.querySelector('#deck .card'))})})()").then(JSON.parse);
  let K = await R();
  check("a page that opens with B signed in on A's device: the question, over the swipe deck, without A's name", /Start fresh for /.test(st) && st.includes(bm) && !/Al Apple/.test(st) && K.deck && K.inSheet, JSON.stringify(K) + " " + st.slice(0, 200));
  await ev("(()=>{const w=" + FW + ";if(w.__uaplyRetryPending)w.__uaplyRetryPending();return 1})()"); await sleep(1500);   // and once more now, on purpose
  K = await R();
  check("...the application A left waiting is held while the question is open (nothing sent under B's account)", (await alApps()) === 0 && K.n === 1 && /pending/.test(K.st), JSON.stringify(K));
  await ev("(()=>{const d=" + F + ";d.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}));d.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true,cancelable:true}));return 1})()"); await sleep(1500);
  K = await R();
  check("...ArrowRight and ArrowLeft on the sheet never swipe the deck behind it", K.sheet && K.n === 1 && /^applied:pending$/.test(K.st) && (await alApps()) === 0, JSON.stringify(K));
  await ev("(()=>{const d=" + F + ",s=d.querySelector('.sg-sheet'),o={bubbles:true,cancelable:true,clientX:3,clientY:3};s.dispatchEvent(new MouseEvent('mousedown',o));s.dispatchEvent(new MouseEvent('mouseup',o));s.dispatchEvent(new MouseEvent('click',o));return 1})()");
  await ev("(()=>{const d=" + F + ";d.body.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}));d.body.dispatchEvent(new KeyboardEvent('keydown',{key:'z',bubbles:true,cancelable:true}));return 1})()"); await sleep(1500);
  K = await R();
  check("...a press on the dark background keeps focus in the sheet, and keys aimed at the page behind do nothing", K.sheet && K.inSheet && K.n === 1 && (await alApps()) === 0, JSON.stringify(K));
  await ev("(()=>{const d=" + F + ";d.body.focus&&d.body.focus();d.body.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true}));return 1})()"); await sleep(200);
  check("...Tab from outside the sheet goes back into it", (await R()).inSheet);
  // an application asked for now (as a swipe by hand would) is held too; Start fresh must answer it "not sent", never fail it (a failed
  // request reads as "could not reach the server" in uaply-live.js, which then promises to send it later)
  const held = (name) => "(()=>{const w=" + FW + ";w." + name + "=undefined;w.fetch('/api/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.json().then(j=>{w." + name + "=r.status+':'+(j.code||'')+':'+(j.error||'')}),e=>{w." + name + "='rejected:'+e.message});return 1})()";
  await ev(held("__byHand")); await sleep(600);
  check("...an application asked for while the question is open waits too", (await ev("String(" + FW + ".__byHand)")) === "undefined");
  await choose("Start fresh"); await sleep(1500);
  const bh = String(await ev("String(" + FW + ".__byHand)"));
  check("Start fresh answers the held application 'not sent' (409), never a failure that promises a later send", /^409:preview:Not sent: you chose Start fresh\.$/.test(bh) && !/could not reach its server/.test(await ev(F + ".body.innerText")), bh);
  check("...and the help chat's agreement to the AI notice (A's) is gone with the rest", (await chatRec()) === null, String(await chatRec()));
  const W2 = JSON.parse(await ev("(()=>{const w=" + FW + ",k=w.__uaplyKey,j=(x)=>{try{return JSON.parse(w.localStorage.getItem(x))}catch(e){return null}};const s=j(k)||{},a=j(k+'.acct')||{};" +
    "return JSON.stringify({learn:s.learn&&s.learn.ev?s.learn.ev.length:0,loc:w.localStorage.getItem(k+'.loc'),plan:a.plan,pay:(a.pay||[]).length,fCo:a.fCo||''})})()"));
  D = await device();
  check("Start fresh: A's waiting application is dropped, never sent under B's account", (await alApps()) === 0 && D.swipes === 0, JSON.stringify(D));
  check("...and A's learned swipes, saved location, plan and company filter are gone with the profile and phone",
    D.phone === "" && D.name === "" && D.email === bm && D.owner && D.owner.email === bm && W2.learn === 0 && W2.loc === null && W2.plan === "trial" && W2.pay === 0 && W2.fCo === "",
    JSON.stringify(D) + " " + JSON.stringify(W2));

  // ---- fix round 2: a sign-in that does not come through the card (the app's own password sign-in, used when the server has code sign-in
  // off, ends in __uaplyAuthApi.signedIn): on a device holding Al's profile the same question opens, and an application asked for before
  // the page has looked is held ----
  await logout(); await load();
  await ev("(()=>{const w=" + FW + ",A=w.__uaply,k=w.__uaplyKey;A.S.profile=Object.assign({},A.S.profile,{name:'Al Apple',email:'" + al + "',custom:true});A.S.decisions={};A.S.history=[];A.save();" +
    "w.__uaplyAuthApi.acct(a=>{a.phone='215-555-0111'});w.localStorage.setItem(k+'.signup.owner',JSON.stringify({email:'" + al + "',kept:false}));return true})()");
  await post("/api/auth/code/send", { email: bm }); await sleep(900);
  check("B gets a session outside the card (code, from the top page)", (await post("/api/auth/code/verify", { email: bm, code: await codeFor(bm) })) === 200);
  const meB = await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>JSON.stringify(j.user))");
  await ev("(()=>{const w=" + FW + ";w.__uaplyAuthApi.signedIn(JSON.parse(" + JSON.stringify(meB) + "));return 1})()");
  await ev(held("__pw")); await sleep(1200);
  st = await sheetText();
  check("a sign-in outside the card on a device holding Al's profile: the same question, without Al's name", st.includes("Start fresh for " + bm + "?") && !/Al Apple/.test(st), st.slice(0, 300));
  check("...the application asked for at once after that sign-in is held, not sent under B's account with Al's details", (await ev("String(" + FW + ".__pw)")) === "undefined" && (await alApps()) === 0);
  await choose("Start fresh");
  D = await device();
  check("...Start fresh: answered 'not sent', and B's device holds only B's account email", /^409:preview:/.test(String(await ev("String(" + FW + ".__pw)"))) && (await alApps()) === 0 && D.phone === "" && D.name === "" && D.email === bm && D.owner && D.owner.email === bm,
    String(await ev("String(" + FW + ".__pw)")) + " " + JSON.stringify(D));
  // the same, but the session ends (in another tab) while the question is open: what it held is answered "not sent", and nothing later
  // is held for a question that is gone
  await logout(); await load();
  await ev("(()=>{const w=" + FW + ",A=w.__uaply,k=w.__uaplyKey;A.S.profile=Object.assign({},A.S.profile,{name:'Al Apple',email:'" + al + "',custom:true});A.save();" +
    "w.localStorage.setItem(k+'.signup.owner',JSON.stringify({email:'" + al + "',kept:false}));return true})()");
  await post("/api/auth/code/send", { email: bm }); await sleep(900);
  await post("/api/auth/code/verify", { email: bm, code: await codeFor(bm) });
  await ev("(()=>{const w=" + FW + ";w.__uaplyAuthApi.signedIn(JSON.parse(" + JSON.stringify(meB) + "));return 1})()");
  await ev(held("__so")); await sleep(1200);
  const soQ = (await sheetText()).includes("Start fresh for " + bm + "?");
  await logout();
  await ev("(()=>{const w=" + FW + ",el=w.document.createElement('div');w.__uaplySignCard(el,JSON.parse(" + JSON.stringify(meB) + "));w.__uaplySignCard(el,null);return 1})()"); await sleep(600);
  const so = String(await ev("String(" + FW + ".__so)"));
  await ev(held("__so2")); await sleep(1500);
  const so2 = String(await ev("String(" + FW + ".__so2)"));
  check("signed out while the question is open: the question closes, the held application is answered 'not sent', and later ones are not held",
    soQ && !(await sheetText()) && so === "409:preview:Not sent: you signed out before choosing Keep or Start fresh." && so2 !== "undefined" && !/^409:preview/.test(so2) && (await alApps()) === 0, [soQ, so, so2].join(" | "));
  await logout();

  // an address with no account gets the same answer, and its code cannot sign anyone in
  await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})");
  const ghost = JSON.parse(await ev("fetch('/api/auth/code/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'nobody." + stamp + "@example.com'})}).then(r=>r.json()).then(j=>JSON.stringify(j))"));
  check("an address with no account gets the same answer", ghost.ok === true && Object.keys(ghost).length === 1, JSON.stringify(ghost));

  // ---- a refresh before the code, then "Email me a code": the tick is asked again and so is the name; hostile text never runs ----
  const HOST = "<img src=x onerror=\"top.__sgx=1\">", rm = "r." + stamp + "@example.com";
  // the device holds a profile someone typed before making any account (a work email, a phone), and no account on record
  await ev("(()=>{const w=" + FW + ",A=w.__uaply,k=w.__uaplyKey;w.localStorage.removeItem(k+'.signup.owner');w.localStorage.removeItem(k+'.signup');" +
    "A.S.profile=Object.assign({},A.S.profile,{name:'Sam Rivera',email:'sam.work." + stamp + "@example.com',custom:true});A.save();w.__uaplyAuthApi.acct(a=>{a.phone='215-555-0100'});return true})()");
  await load(); await openAccount();
  await typeIn("[data-email] input", rm); await typeIn(".sg-fn input", HOST); await typeIn(".sg-ln input", "<script>top.__sgx=2</script>");
  await ev("(()=>{const a=" + q(".sg-ag") + ";a.click()})()");
  await click(".sg-su [type=submit]"); await sleep(1500);
  check("hostile text typed on the card: the code step, nothing ran", /Check your email/.test(await text()) && !(await ev("!!(window.__sgx||" + F + ".defaultView.__sgx)")));
  await load(); await openAccount();
  await click(".sg-to-in"); await sleep(300);
  await markSeen(rm);   // the code from Create my account was never typed: the next one is the one to use
  await typeIn("[data-email] input", rm); await click(".sg-si [type=submit]"); await sleep(1500);
  await typeCode(await codeFor(rm)); await sleep(1500);
  t = await text();
  check("after a refresh, Email me a code on the brand-new account asks for the tick first (no session yet)",
    /Tick the box/.test(t) && (await ev("!!" + q(".sg-cag .sg-ag"))) && (await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user)")) === null, t.slice(0, 300));
  await ev("(()=>{const a=" + q(".sg-cag .sg-ag") + ";a.click()})()"); await sleep(1800);
  t = await text();
  check("ticked: 'Account created.' (no stray comma) and the name is asked, since it was lost with the refresh",
    /Account created\./.test(t) && !/Account created, \./.test(t) && /What should employers call you\?/.test(t) && (await ev(q(".sg-fn input") + ".value")) === "", t.slice(0, 300));
  await typeIn(".sg-fn input", HOST); await typeIn(".sg-ln input", "Rowe"); await sleep(200);
  await click(".sg-next"); await sleep(500);
  const pv2 = await ev(q(".sg-pv") + ".textContent");
  check("a hostile name shows as text in the preview and never runs", pv2.includes("<img src=x") && !(await ev("!!(window.__sgx||" + F + ".defaultView.__sgx)")) && !(await ev("!!" + F + ".querySelector('#acctSec img[src=x]')")), pv2.slice(0, 200));
  D = await device();
  check("a profile email typed before any account, then a new account with another address: no question (it is that person's own), and the account takes the device as it is",
    (await confirms()) === 0 && !(await sheetText()) && D.owner && D.owner.email === rm && D.phone === "215-555-0100", JSON.stringify(D));
  await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})");

  // ---- PR #50, asked first: a NEW account on a device that holds another person's profile and swipes ----
  await load(); await spyConfirm();
  await ev("(()=>{const A=" + FW + ".__uaply,j=A.JOBS[0];A.S.decisions[j.id]={s:'applied',at:Date.now(),pct:80,as:'R',title:''};A.S.history.push(j.id);A.save();A.renderAll();return true})()");
  check("seeded: the Applied list on this device shows the other person's application", (await appliedRows()) >= 1);
  await openAccount();
  const cm = "c." + stamp + "@example.com";
  await ev("(()=>{const a=" + q(".sg-ag") + ";a.click()})()");
  await typeIn("[data-email] input", cm); await typeIn(".sg-fn input", "Cy"); await typeIn(".sg-ln input", "Chen");
  await click(".sg-su [type=submit]"); await sleep(1500);
  await typeCode(await codeFor(cm)); await sleep(1800);
  st = await sheetText(); D = await device();
  check("a new account (code) on a device holding someone's profile and swipes: the same question, nothing removed yet",
    /This device holds another person’s profile\./.test(st) && st.includes("Start fresh for " + cm + "?") && D.swipes === 1 && /Rowe/.test(D.name) && (await confirms()) === 0, JSON.stringify(D) + " " + st.slice(0, 300));
  await choose("Start fresh");
  t = await text(); D = await device();
  check("Start fresh: 'Account created, Cy.', the note, and only Cy's own details on this device (empty swipe list)",
    /Account created, Cy\./.test(t) && /You chose Start fresh/.test(t) && D.name === "Cy Chen" && D.email === cm && D.swipes === 0 && D.apps === 0, JSON.stringify(D) + " " + t.slice(0, 300));
  check("...and the Applied list is empty for the second person", (await appliedRows()) === 0);
  await logout();

  // ---- Continue with Google (the stand-in) ----
  if (MG) {
    const gm = "gabi." + stamp + "@gmail.com";
    await ev("fetch('http://127.0.0.1:" + MG + "/mock/next?email=" + gm + "&sub=sg" + stamp + "&verified=1',{mode:'no-cors'})"); await sleep(300);
    await load(); await openAccount();
    await ev("(()=>{const a=" + q(".sg-ag") + ";a.click()})()");
    await click("[data-sg=google]"); await sleep(6000);
    await openAccount(); await sleep(800);
    check("Google, new account on a device holding Cy's profile: the question comes first", (await sheetText()).includes("Start fresh for " + gm + "?"), await sheetText());
    await choose("Start fresh");
    t = await text();
    check("Google, new Gmail account: 'Account created with Google.' and the name asked (Google is not asked for it)",
      /Account created with Google\./.test(t) && /What should employers call you\?/.test(t) && (await ev(q(".sg-fn input") + ".value")) === "", t.slice(0, 400));
    check("the note says what UAply keeps from Google: the email and the account number only", /UAply keeps only your email \(.*\) and your Google account number from Google/.test(t) && !/your name and your Google/.test(t), t.slice(0, 400));
    check("Google skipped the code (Gmail is vouched for by Google)", !/Check your email/.test(t));
    await typeIn(".sg-fn input", "Gabi"); await typeIn(".sg-ln input", "Lopez");
    await key(".sg-qs input", "Enter"); await sleep(300);
    await click(".sg-next"); await sleep(300); await click(".sg-next"); await sleep(300); await click(".sg-next"); await sleep(800);
    await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})");

    // a Google account whose address Google does not vouch for: the code first
    const xm = "lee." + stamp + "@example.org";
    await ev("fetch('http://127.0.0.1:" + MG + "/mock/next?email=" + xm + "&sub=sx" + stamp + "&verified=1',{mode:'no-cors'})"); await sleep(300);
    await load(); await openAccount();
    await typeIn(".sg-fn input", "Lee"); await typeIn(".sg-ln input", "Park");
    await ev("(()=>{const a=" + q(".sg-ag") + ";a.click()})()");
    await click("[data-sg=google]"); await sleep(6000);
    await openAccount(); await sleep(1200);
    await choose("Start fresh");   // the device holds Gabi's profile
    t = await text();
    check("Google with a non-Google address: the 6-digit code first", /Google signed you in, but it vouches only for Gmail/.test(t), t.slice(0, 300));
    await typeCode(await codeFor(xm)); await sleep(1800);
    t = await text();
    check("then 'Account created with Google.' and straight to the work question (the name was typed on the card)", /Account created with Google\./.test(t) && /What kind of work/.test(t), t.slice(0, 300));
    await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})");

    // ---- Keep on a NEW account (Google as bg@gmail.com, with 'Ana Diaz' and a@gmail.com typed): the profile saved here goes out as it is ----
    const am = "a." + stamp + "@gmail.com", bgm = "bg." + stamp + "@gmail.com";
    await ev("fetch('http://127.0.0.1:" + MG + "/mock/next?email=" + bgm + "&sub=sb" + stamp + "&verified=1',{mode:'no-cors'})"); await sleep(300);
    await load(); await openAccount();
    await typeIn("[data-email] input", am); await typeIn(".sg-fn input", "Ana"); await typeIn(".sg-ln input", "Diaz");
    await ev("(()=>{const a=" + q(".sg-ag") + ";a.click()})()");
    await click("[data-sg=google]"); await sleep(6000);
    await openAccount(); await sleep(800);
    st = await sheetText();
    check("Google as b@gmail.com on a device holding Lee's profile: the question first, without Lee's name", st.includes("Start fresh for " + bgm + "?") && !/Lee|Park/.test(st), st.slice(0, 300));
    check("...the sheet says what Keep does: that profile's name, phone and resume, with your account email", /Keep uses that profile for your applications: its name, phone and resume, with your account email\./.test(st), st.slice(0, 600));
    await choose("Keep");
    t = await text(); D = await device();
    check("Keep on a new account: the saved profile keeps its own name (Lee Park) and takes b@gmail.com's own email (the live server sends only from the account's email), no name question, Ana's name nowhere",
      D.name === "Lee Park" && D.email === bgm && !/What should employers call you\?/.test(t) && /What kind of work/.test(t) && !/Ana|Diaz/.test(t),
      JSON.stringify(D) + " " + t.slice(0, 300));
    const keptP = await ev("(()=>{const p=[..." + F + ".querySelectorAll('#acctSec p')].find(x=>/You kept the profile/.test(x.textContent));return p?p.textContent:''})()");
    check("...the screen says whose name the applications carry, and that line never shows Lee's email", /You kept the profile saved on this device, so your applications from here go out as Lee Park, with that profile’s phone and resume and your account email\./.test(keptP) && !keptP.includes(xm), keptP + " | " + t.slice(0, 400));
    check("...and the preview of what employers see shows that name", /Lee Park/.test(await ev(q(".sg-pv") + ".textContent")));
    await click(".sg-next"); await sleep(300); await click(".sg-next"); await sleep(300); await click(".sg-next"); await sleep(800);
    await openAccount();
    t = await text(); D = await device();
    check("...the Account screen keeps saying it after the questions, and the name is still Lee Park, with b@gmail.com's email", /You kept the profile saved on this device, so your applications from here go out as Lee Park/.test(t) && D.name === "Lee Park" && D.email === bgm, t.slice(0, 700));
    await logout();

    // the account the kept profile came from (Lee) signs in again: its own profile, so no question
    await ev("fetch('http://127.0.0.1:" + MG + "/mock/next?email=" + xm + "&sub=sx" + stamp + "&verified=1',{mode:'no-cors'})"); await sleep(300);
    await load(); await openAccount();
    await click(".sg-to-in"); await sleep(300);
    await click("[data-sg=google]"); await sleep(6000);
    await openAccount(); await sleep(800);
    t = await text(); D = await device();
    check("Lee signs in again on the device whose profile b@gmail.com kept: no question, Lee's own details and his own email back, signed in", !(await sheetText()) && /You’re signed in/.test(t) && D.name === "Lee Park" && D.email === xm && D.owner && D.owner.email === xm, JSON.stringify(D) + " " + t.slice(0, 300));
    if (await ev("!!" + q(".sg-start"))) { await click(".sg-start"); await sleep(800); }
    await logout();

    // ---- PR #49 finding 6: a name and a2@gmail.com typed on the card, then Google signs in bg2@gmail.com: the name stays with a2@gmail.com ----
    const am2 = "a2." + stamp + "@gmail.com", bgm2 = "bg2." + stamp + "@gmail.com";
    await ev("fetch('http://127.0.0.1:" + MG + "/mock/next?email=" + bgm2 + "&sub=sc" + stamp + "&verified=1',{mode:'no-cors'})"); await sleep(300);
    await load(); await openAccount();
    await typeIn("[data-email] input", am2); await typeIn(".sg-fn input", "Ana"); await typeIn(".sg-ln input", "Diaz");
    await ev("(()=>{const a=" + q(".sg-ag") + ";a.click()})()");
    await click("[data-sg=google]"); await sleep(6000);
    await openAccount(); await sleep(800);
    check("Google as bg2@gmail.com on a device holding Lee's profile: the question first", (await sheetText()).includes("Start fresh for " + bgm2 + "?"), await sheetText());
    await choose("Start fresh");
    t = await text(); D = await device();
    check("typed 'Ana Diaz' with a2@gmail.com, Google came back as bg2@gmail.com: the name question with empty boxes, Ana's name nowhere",
      /What should employers call you\?/.test(t) && (await ev(q(".sg-fn input") + ".value")) === "" && (await ev(q(".sg-ln input") + ".value")) === "" && !/Ana|Diaz/.test(t) && !/Ana|Diaz/.test(D.name),
      JSON.stringify(D) + " " + t.slice(0, 300));
    await typeIn(".sg-fn input", "Bo"); await typeIn(".sg-ln input", "Grant");
    await click(".sg-next"); await sleep(300); await click(".sg-next"); await sleep(300); await click(".sg-next"); await sleep(300); await click(".sg-next"); await sleep(800);
    check("...and the name B typed is the one on the profile", (await device()).name === "Bo Grant");
    await logout();

    // a new person pressing Google on "Welcome back" (no tick): the server refuses, the card sends them to Create your account
    await ev("fetch('http://127.0.0.1:" + MG + "/mock/next?email=new." + stamp + "@gmail.com&sub=sn" + stamp + "&verified=1',{mode:'no-cors'})"); await sleep(300);
    await load(); await openAccount();
    await click(".sg-to-in"); await sleep(300);
    await click("[data-sg=google]"); await sleep(6000);
    await openAccount(); await sleep(800);
    t = await text();
    check("a new person on Welcome back + Google lands on Create your account with one clear note", /Create your UAply account/.test(t) && /no UAply account yet\. Tick the box/.test(t), t.slice(0, 900));
    check("...the note sits at the box (below the names), marked", await ev("!!" + q(".sg-agree.bad") + "&&/no UAply account yet/.test(" + q(".sg-amsg") + ".textContent)"));

    // a password account on a Gmail address whose password was never confirmed: Google proves the inbox, but whoever opened the account
    // ticked the box for themselves, so the inbox's owner ticks it first (since October 22, PR #50 and a660b4a); then Google signs them in,
    // the password goes, and the card says so
    const pm = "pw." + stamp + "@gmail.com";
    await ev("fetch('/api/auth/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'" + pm + "',password:'correct horse 99',agree:true})})");
    await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})");
    await ev("fetch('http://127.0.0.1:" + MG + "/mock/next?email=" + pm + "&sub=sp" + stamp + "&verified=1',{mode:'no-cors'})"); await sleep(300);
    await load(); await openAccount();
    await click(".sg-to-in"); await sleep(300);
    await click("[data-sg=google]"); await sleep(6000);
    await openAccount(); await sleep(800);
    t = await text();
    check("Google (no tick) on an account someone opened with an unconfirmed password: the owner is asked for their own tick, no session",
      /Create your UAply account/.test(t) && /never finished\. Tick the box/.test(t) &&
      (await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user)")) === null, t.slice(0, 900));
    await ev("(()=>{const a=" + q(".sg-ag") + ";if(!a.checked)a.click()})()");
    await ev("fetch('http://127.0.0.1:" + MG + "/mock/next?email=" + pm + "&sub=sp" + stamp + "&verified=1',{mode:'no-cors'})"); await sleep(300);
    await click("[data-sg=google]"); await sleep(6000);
    await openAccount(); await sleep(800);
    check("Google to an existing account on a device holding another account's profile: the question", /This device holds another person’s profile/.test(await sheetText()), await sheetText());
    await choose("Start fresh");
    t = await text();
    const me2 = JSON.parse(await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>JSON.stringify(j.user))"));
    check("...ticked, Continue with Google: signed in, and the card says the unconfirmed password was removed",
      me2 && me2.email === pm && me2.hasPassword === false && /was removed to keep the account yours/.test(t), JSON.stringify(me2) + " " + t.slice(0, 600));
    await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})");
  }
  const errs = logs.filter((l) => !/favicon|ERR_FILE_NOT_FOUND/.test(l));
  check("no script errors", errs.length === 0, errs.join(" | "));
  console.log("\n" + (n - bad) + " / " + n);
};
