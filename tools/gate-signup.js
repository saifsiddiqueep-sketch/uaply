// A fresh test person signs up before a browser test that swipes or reads job data (Saif, October 22, 2026: nobody reaches anything on the
// site without an account; data routes answer 401 "signin" to a visitor with none). Used by tools/ui-swipes.js, ui-sweep.js, ui-boot.js,
// ui-inject.js, ui-learn.js, ui-questions.js, ui-phone.js, ui-tracker-keep.js, ui-walk.js and ui-journey.js:
//   const gateSignup = require("./gate-signup.js");  ...  const who = await gateSignup({ ev, sleep, nav }, "http://127.0.0.1:" + PORT, "swipes");
// On a page that shows the sign-in gate (the sandbox's card) it signs up through the card itself: its own boxes, the 18+ tick, Create my
// account, then the two questions. Elsewhere (a page without the card) it posts /api/auth/signup. On a test server (UAPLY_SIGNUP_TEST=1:
// providers.signupTest) the account is confirmed at once; otherwise the code is read from the server's test inbox (/outbox) and typed.
// Call it after the test clears cookies and storage. Returns {email, how, ok}; the browser is signed in when ok is true.
module.exports = async function gateSignup({ ev, sleep, nav }, base, tag) {
  base = String(base).replace(/\/+$/, "");
  const F = "document.querySelector('iframe').contentDocument";
  const email = "first." + (tag || "test") + "." + Date.now().toString(36) + Math.random().toString(36).slice(2, 6) + "@example.com";
  const PW = "First-" + Math.random().toString(36).slice(2, 10) + "-pw9";
  const me = () => ev("fetch('/api/auth/me',{credentials:'same-origin'}).then(r=>r.json()).then(j=>j.user?JSON.stringify(j.user):'')").then((t) => (t ? JSON.parse(t) : null));
  const code = () => ev("fetch('/outbox').then(r=>r.text()).then(t=>{const m=t.replace(/<[^>]+>/g,' ').match(new RegExp('([0-9]{6}) is your UAply (?:verification|sign-in) code to '+" + JSON.stringify(email.replace(/\./g, "\\.")) + "));return m?m[1]:''})");
  await nav(base + "/");
  let gated = false;
  for (let i = 0; i < 60; i++) {
    const s = await ev("(()=>{try{const d=" + F + ";if(!d||!d.body)return '';if(d.body.classList.contains('sgGated')&&d.querySelector('.sg-su'))return 'gate';return d.getElementById('bnav')?'app':''}catch(e){return ''}})()").catch(() => "");
    if (s === "gate") { gated = true; break; }
    if (s === "app" && i > 12) break;            // a page without the gate (dev, the live build): its bottom bar, and no card after 3 s
    await sleep(250);
  }
  if (gated) {
    const setv = (sel, v) => ev("(()=>{const e=" + F + ".querySelector(" + JSON.stringify(sel) + ");if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return true})()");
    await setv(".sg-su [data-email] input", email); await setv(".sg-su .sg-fn input", "Test"); await setv(".sg-su .sg-ln input", "Person"); await setv(".sg-su .sg-pw input", PW);
    await ev("(()=>{const d=" + F + ",a=d.querySelector('.sg-su .sg-ag');if(a&&!a.checked)a.click();d.querySelector('.sg-su [type=submit]').click()})()");
    for (let i = 0; i < 40; i++) { await sleep(250); if (/Check your email|1 of 2|What kind of work|What should employers/i.test(await ev("(" + F + ".getElementById('acctSec')||{innerText:''}).innerText"))) break; }
    if (/Check your email/.test(await ev("(" + F + ".getElementById('acctSec')||{innerText:''}).innerText"))) {
      let c = ""; for (let i = 0; i < 20 && !c; i++) { c = await code(); if (!c) await sleep(500); }
      if (c) { await setv(".sg-code input", c); await sleep(2000); }
    }
    for (let i = 0; i < 4; i++) {
      if (!(await ev(F + ".body.classList.contains('sgGated')"))) break;
      await ev("(()=>{const b=" + F + ".querySelector('.sg-next');if(b)b.click()})()"); await sleep(700);
    }
    // the card wrote a profile for the new person (name, work, place): the device goes back to how the test found it, as after the
    // API sign-up below, so a test built on the example profile still has it. The session cookie stays: that is the account.
    await ev("(()=>{try{localStorage.clear();sessionStorage.clear()}catch(e){}return 1})()");
  } else {
    const st = await ev("fetch('/api/auth/signup',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:" + JSON.stringify(email) + ",password:" + JSON.stringify(PW) + ",first:'Test',last:'Person',agree:true,passwordless:false})}).then(r=>r.status)");
    let u = await me();
    if (st === 200 && u && u.emailVerified === false) {      // not a test server: the code from the test inbox confirms the address
      let c = ""; for (let i = 0; i < 20 && !c; i++) { c = await code(); if (!c) await sleep(500); }
      if (c) await ev("fetch('/api/auth/verify',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:" + JSON.stringify(c) + "})}).then(r=>r.status)");
    }
  }
  const u = await me();
  const ok = !!u && u.email === email;
  console.log((ok ? "     " : "FAIL ") + "the test person signed up first (" + (gated ? "through the sign-in gate's card" : "POST /api/auth/signup") + "): " + (ok ? email + (u.emailVerified ? ", confirmed" : ", not yet confirmed") : "not signed in"));
  return { email, how: gated ? "card" : "api", ok };
};
