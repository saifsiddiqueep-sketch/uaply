// Sign-up v2 in a real browser (the sandbox's "Sign-up, nothing hidden" card): layout, the typo fix, the tick box, sign-up with an emailed code,
// the two questions (Enter, Esc, Skip/Continue), what is kept on the device, sign-in by code, and Continue with Google against the stand-in.
// Also: a redraw of the Account screen while someone types (a late start-up answer) keeps them in the box with the caret where it was, and
// after Sign out in the app the next person gets an empty card with the box unticked.
//   W=1280 H=720 PORT=<sandbox port> MOCK_GOOGLE_PORT=8790 node tools/cdp.js tools/ui-signup.js      (W=390 H=844 for a phone)
// The sandbox server must run with smtp {} (codes land in the test inbox) and, for the Google part, google.* pointing at tools/mock-google.py.
// Each run emails 5 codes from 127.0.0.1 (the server allows 80 an hour per connection, and 10 sign-ups an hour from this computer).
module.exports = async ({ ev, sleep, nav, send, logs }) => {
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
  const codeFromInbox = () => ev("fetch('/outbox').then(r=>r.text()).then(t=>{const m=t.match(/([0-9]{6}) is your UAply verification code/);return m?m[1]:''})");
  const typeCode = (c) => typeIn(".sg-code input", c);
  const openAccount = async () => {
    await ev("(()=>{const b=[...(" + F + ").querySelectorAll('button')].find(x=>x.offsetParent&&x.innerText.trim()==='Not now');if(b)b.click()})()"); await sleep(400);
    await ev(F + ".getElementById('nb-prof').click()"); await sleep(400);
    await ev("[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Account')).click()"); await sleep(1800);
  };
  const load = async (u) => { await nav("http://127.0.0.1:" + PORT + (u || "/?app=1")); await sleep(3500); };
  const stamp = Date.now().toString(36);

  if (!phone) await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });   // no animation timing in the checks
  await load();
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
  const code1 = await codeFromInbox();
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
    /Almost ready/.test(t) && /Before UAply can apply, add a phone number or a resume/.test(t) && /For employers who don.t take UAply applications, the job waits in Job Tracker/.test(t) && !/applies for you/i.test(t) && !/only when a job needs/i.test(t) &&
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

  // ---- Sign out in the app (no reload): the next person on this device starts from an empty card ----
  await click("[data-auth=sout]"); await sleep(1500);
  const E = JSON.parse(await ev("(()=>{const d=" + F + ",v=(s)=>{const e=d.querySelector(s);return e?(e.type==='checkbox'?e.checked:e.value):null};return JSON.stringify({card:!!d.querySelector('.sg-su'),email:v('[data-email] input'),first:v('.sg-fn input'),last:v('.sg-ln input'),ticked:v('.sg-ag'),me:null})})()"));
  E.me = await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user)");
  check("Sign out in the app, then the card: no email, no name, the box unticked (the next person's tick is their own)",
    E.card && E.email === "" && E.first === "" && E.last === "" && E.ticked === false && E.me === null, JSON.stringify(E));

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
  await typeCode(await codeFromInbox()); await sleep(1800);
  t = await text();
  check("the code signs in: 'You're signed in, Sam.' (the name kept on this device)", /You’re signed in, Sam\./.test(t), t.slice(0, 200));
  await click(".sg-start"); await sleep(800);

  // an address with no account gets the same answer, and its code cannot sign anyone in
  await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})");
  const ghost = JSON.parse(await ev("fetch('/api/auth/code/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'nobody." + stamp + "@example.com'})}).then(r=>r.json()).then(j=>JSON.stringify(j))"));
  check("an address with no account gets the same answer", ghost.ok === true && Object.keys(ghost).length === 1, JSON.stringify(ghost));

  // ---- a refresh before the code, then "Email me a code": the tick is asked again and so is the name; hostile text never runs ----
  const HOST = "<img src=x onerror=\"top.__sgx=1\">", rm = "r." + stamp + "@example.com";
  await load(); await openAccount();
  await typeIn("[data-email] input", rm); await typeIn(".sg-fn input", HOST); await typeIn(".sg-ln input", "<script>top.__sgx=2</script>");
  await ev("(()=>{const a=" + q(".sg-ag") + ";a.click()})()");
  await click(".sg-su [type=submit]"); await sleep(1500);
  check("hostile text typed on the card: the code step, nothing ran", /Check your email/.test(await text()) && !(await ev("!!(window.__sgx||" + F + ".defaultView.__sgx)")));
  await load(); await openAccount();
  await click(".sg-to-in"); await sleep(300);
  await typeIn("[data-email] input", rm); await click(".sg-si [type=submit]"); await sleep(1500);
  await typeCode(await codeFromInbox()); await sleep(1500);
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
  await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})");

  // ---- Continue with Google (the stand-in) ----
  if (MG) {
    const gm = "gabi." + stamp + "@gmail.com";
    await ev("fetch('http://127.0.0.1:" + MG + "/mock/next?email=" + gm + "&sub=sg" + stamp + "&verified=1',{mode:'no-cors'})"); await sleep(300);
    await load(); await openAccount();
    await ev("(()=>{const a=" + q(".sg-ag") + ";a.click()})()");
    await click("[data-sg=google]"); await sleep(6000);
    await openAccount(); await sleep(800);
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
    t = await text();
    check("Google with a non-Google address: the 6-digit code first", /Google signed you in, but it vouches only for Gmail/.test(t), t.slice(0, 300));
    await typeCode(await codeFromInbox()); await sleep(1800);
    t = await text();
    check("then 'Account created with Google.' and straight to the work question (the name was typed on the card)", /Account created with Google\./.test(t) && /What kind of work/.test(t), t.slice(0, 300));
    await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})");

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
