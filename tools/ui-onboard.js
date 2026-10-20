// First-run and swipe lock (sandbox, Trello card 9), in a real browser at iPhone size: the welcome, the sign-in screen (Apple shown as not
// yet available), Profile setup with Skip for now (what was typed is kept), every way to swipe blocked while the profile is incomplete
// (arrow keys, the Pass and Apply buttons, a mouse drag, a direct call) with the card back in place, nothing saved and one sheet,
// Maybe Later, reduced motion, the ready check, swiping unlocked once the profile is complete, and a returning visitor skipping it all.
//   W=390 H=844 PORT=8766 node tools/cdp.js tools/ui-onboard.js        (a sandbox server: python serve.py 8766 sandbox --api)
// Set SHOT=folder to save the screenshots shot-onb-*.png there.
const fs = require("fs");
const path = require("path");
const PORT = process.env.PORT || "8766";
module.exports = async ({ ev, sleep, nav, shot, send }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const W = "document.querySelector('iframe').contentWindow";
  const check = (n, ok, x) => console.log((ok ? "PASS " : "FAIL ") + n + (x ? "  " + x : ""));
  const snap = async (n) => { if (process.env.SHOT) { fs.mkdirSync(process.env.SHOT, { recursive: true }); await shot(path.join(process.env.SHOT, "shot-onb-" + n + ".png")); } };
  const txt = (sel) => ev("((" + F + ".querySelector(" + JSON.stringify(sel) + ")||{}).textContent||'')");
  const click = (sel) => ev("(()=>{const b=" + F + ".querySelector(" + JSON.stringify(sel) + ");if(!b)return false;b.click();return true})()");
  const decisions = () => ev("Object.keys(" + W + ".__uaply.S.decisions).length");
  const sheets = () => ev(F + ".querySelectorAll('#onbSheet').length");
  const key = (k) => ev("(()=>{const w=" + W + ";w.document.dispatchEvent(new w.KeyboardEvent('keydown',{key:'" + k + "',bubbles:true}));return true})()");
  const closeSheet = async () => { await click("#onbLater"); await sleep(350); };
  const set = (id, v) => ev("(()=>{const w=" + W + ",e=w.document.getElementById(" + JSON.stringify(id) + ");if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new w.Event('input',{bubbles:true}));e.dispatchEvent(new w.Event('change',{bubbles:true}));return true})()");

  await nav("http://127.0.0.1:" + PORT + "/?app=1");
  await sleep(3500);

  // ---- welcome ----
  check("a first visit opens the welcome", (await txt("#onb h1")) === "Your next opportunity starts here.", await txt("#onb h1"));
  check("with the second line", /Discover jobs that fit you\. Swipe\. Apply\. Move forward\./.test(await txt("#onb p")));
  await sleep(500); await snap("welcome");
  await click("#onbStart"); await sleep(450);
  check("Get started goes to sign-in", (await txt("#onb h2")) === "Create your account", await txt("#onb h2"));
  check("email and Google are offered", !!(await ev("!!(" + F + ".getElementById('onbEmail')&&" + F + ".getElementById('onbGoogle'))")));
  check("Apple is shown as not available yet (no Apple sign-in exists)", /Continue with Apple\s*Not available yet/.test(await txt("#onb .soon")) && !(await ev("!!" + F + ".querySelector('#onb .soon button')")));
  await snap("signin");
  await click("#onbNoAcct"); await sleep(900);
  check("Set up my profile first opens Profile setup", !(await ev("!!" + F + ".getElementById('onb')")) && !(await ev(F + ".getElementById('pane-profile').hidden")));
  check("Skip for now is on the step", (await txt("#onbSkip")) === "Skip for now");
  const step0 = await ev("(" + F + ".querySelector('.wzDots button[aria-current=step]')||{}).getAttribute?.('data-step')");
  check("it opens on the first step (About you)", step0 === "0", step0);

  // ---- skip keeps what was typed ----
  await set("pName", "Ada Lovelace");
  await snap("setup");
  await click("#onbSkip"); await sleep(600);
  const step1 = await ev("(" + F + ".querySelector('.wzDots button[aria-current=step]')||{}).getAttribute?.('data-step')");
  check("Skip for now moves to the next step", step1 === "1", step1);
  check("...and keeps the name that was typed (saved)", (await ev(W + ".__uaply.S.profile.name")) === "Ada Lovelace", await ev(W + ".__uaply.S.profile.name"));
  check("...and marks the step as skipped", /about/.test(await ev("JSON.stringify(Object.keys(" + W + ".localStorage).filter(k=>/onboard/.test(k)).map(k=>" + W + ".localStorage.getItem(k)))")));

  // ---- the lock ----
  await ev(W + ".__uaply.show('swipe')"); await sleep(600);
  await click("#kcYes"); await sleep(400);                       // the one-time agreement (consentFirst)
  const bar = await txt("#onbBar");
  check("the cards show Profile N% complete", /^Profile \d+% complete/.test(bar), bar);
  const before = await decisions(), topId = await ev("(" + F + ".querySelector('#deck .card.top')||{}).getAttribute?.('data-id')");
  await key("ArrowRight"); await sleep(400);
  check("arrow right is blocked and opens the sheet", (await sheets()) === 1 && (await decisions()) === before);
  check("the sheet says so", (await txt("#onbSheet h2")) === "You're almost there." && /Complete your profile to unlock job swiping and start applying\./.test(await txt("#onbSheet")));
  check("its buttons", (await txt("#onbGo")) === "Complete My Profile" && (await txt("#onbLater")) === "Maybe Later");
  await sleep(300); await snap("locked");
  await key("ArrowLeft"); await click("#btnYes"); await click("#btnNo"); await sleep(300);
  check("more swipes while it is open do not open a second sheet", (await sheets()) === 1);
  await closeSheet();
  check("Maybe Later closes it", (await sheets()) === 0);
  await click("#btnNo"); await sleep(400);
  check("the Pass button is blocked too (left)", (await sheets()) === 1 && (await decisions()) === before);
  await closeSheet();
  await click("#btnYes"); await sleep(400);
  check("the Apply button is blocked (right)", (await sheets()) === 1 && (await decisions()) === before);
  await closeSheet();
  // a mouse drag far past the swipe distance
  const drag = await ev("(async()=>{const w=" + W + ",c=w.document.querySelector('#deck .card.top'),r=c.getBoundingClientRect(),y=r.top+r.height/2,x=r.left+r.width/2;" +
    "const P=(t,cx)=>c.dispatchEvent(new w.PointerEvent(t,{bubbles:true,pointerId:7,pointerType:'mouse',button:0,buttons:1,clientX:cx,clientY:y}));" +
    "P('pointerdown',x);for(let i=1;i<=10;i++){P('pointermove',x+i*25);await new Promise(r=>setTimeout(r,16))}P('pointerup',x+250);await new Promise(r=>setTimeout(r,500));" +
    "return {tf:c.style.transform||'',top:(w.document.querySelector('#deck .card.top')||{}).getAttribute?.('data-id')}})()");
  check("a drag right is blocked, with one sheet", (await sheets()) === 1 && (await decisions()) === before);
  check("...and the card springs back to its place", drag.tf === "" && drag.top === topId, JSON.stringify(drag));
  await closeSheet();
  await ev("(()=>{" + W + ".__uaplyLocked&&0})()");
  const direct = await ev("(()=>{const d=" + F + ";const b=d.getElementById('btnNo');b.disabled=false;b.click();return true})()");
  await sleep(400);
  check("any other way in (a script pressing Pass) is blocked", direct && (await decisions()) === before);
  await closeSheet();
  const store = await ev("JSON.stringify(Object.keys(JSON.parse(" + W + ".localStorage.getItem(" + W + ".__uaplyKey)).decisions||{}))");
  check("nothing was applied, passed or saved", store === "[]", store);

  // ---- reduced motion ----
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  await key("ArrowRight"); await sleep(150);
  const anim = await ev("getComputedStyle(" + F + ".getElementById('onbSheet')).animationName");
  check("with reduced motion the sheet appears without sliding", anim === "none", anim);
  await click("#onbLater"); await sleep(50);
  check("...and closes at once", (await sheets()) === 0);
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "no-preference" }] });

  // ---- Complete My Profile goes to the earliest missing step ----
  await sleep(400); await key("ArrowRight"); await sleep(400);
  await click("#onbGo"); await sleep(700);
  const goStep = await ev("(" + F + ".querySelector('.wzDots button[aria-current=step]')||{}).getAttribute?.('data-step')");
  check("Complete My Profile opens Profile setup at the earliest incomplete step (About you: email and phone)", goStep === "0", goStep + " " + await ev("JSON.stringify(" + W + ".__uaplyOnboard.ready())"));

  // ---- fill the required fields, finish: the ready check ----
  await set("pEmail", "ada@example.com");
  const phoneId = (await ev("!!(" + F + ".getElementById('px-phone')&&" + F + ".getElementById('px-phone').offsetParent)")) ? "px-phone" : "pPhone";
  await set(phoneId, "215 555 0100");
  await set("pLoc", "Philadelphia");
  const resId = (await ev("!!" + F + ".getElementById('px-resume')")) ? "px-resume" : "resLink";
  await set(resId, "https://ada.example/cv.pdf");
  await set("pTitle", "Analyst"); await set("pSkills", "Excel, SQL, Python");
  for (let i = 0; i < 5; i++) { await click("#wzNext"); await sleep(500); if (await ev("!!" + F + ".getElementById('onb')")) break; }
  const r = JSON.parse(await ev("JSON.stringify(" + W + ".__uaplyOnboard.ready())"));
  check("the required fields now read as ready", r.state === "ready", JSON.stringify(r.missing));
  if (!(await ev("!!" + F + ".getElementById('onb')"))) await ev(W + ".__uaplyOnboard.finish()");
  await sleep(500);
  check("the ready screen", (await txt("#onb h2")) === "You're ready to make moves.", await txt("#onb h2"));
  check("lists the five required items, all done", (await ev(F + ".querySelectorAll('#onb ul.chk li.ok').length")) === 5);
  await snap("ready");
  await click("#onbExplore"); await sleep(800);
  check("Start Exploring Jobs goes to the cards", !(await ev("!!" + F + ".getElementById('onb')")) && !(await ev(F + ".getElementById('pane-swipe').hidden")));
  check("the % pill is gone once complete", await ev(F + ".getElementById('onbBar').hidden"));

  // ---- unlocked ----
  await key("ArrowLeft"); await sleep(900);
  check("with a complete profile a swipe goes through (left: passed)", (await decisions()) === before + 1 && (await sheets()) === 0);

  // ---- a returning visitor ----
  await nav("http://127.0.0.1:" + PORT + "/?app=1"); await sleep(3500);
  check("a returning visitor with a complete profile skips onboarding", !(await ev("!!" + F + ".getElementById('onb')")));
  const wide = await ev("(()=>{const d=" + F + ";return d.documentElement.scrollWidth<=d.documentElement.clientWidth+1})()");
  check("nothing is wider than the phone", wide);
};
