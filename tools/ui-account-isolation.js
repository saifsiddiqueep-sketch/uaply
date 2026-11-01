// Two accounts never see each other's data (Trello 023, November 1, 2026): local evidence with two made-up people, the stand-in Google
// and the test inbox, in two separate browsers, with Sign out and sign-in in between. Nothing here reaches a real Google, a real inbox or
// the live site.
//   Browser 1 (PHASE=1): A signs up (email + password), gets a profile ("Avery Alpha") and three Job Tracker rows (AlphaCorp), Sign out in
//     the app, then B signs in on the same browser with Continue with Google (the stand-in). Checks: who the server says is signed in, the
//     profile kept on each account, the old session after Sign out, and what B sees on the device (profile, Job Tracker, saved copy).
//   Browser 2 (PHASE=2, a fresh Chrome): A signs in by password, then B with Google: each gets back only their own profile and rows.
// The server must run with smtp {} and google.* pointing at tools/mock-google.py, as the sign-up test's server does:
//   UAPLY_DATA_DIR=<empty dir> UAPLY_CONFIG_JSON='{"delivery":"test","smtp":{},"feeds":[],"owner_copy":"","google":{"client_id":
//     "test.apps.googleusercontent.com","client_secret":"test-secret","auth_url":"http://127.0.0.1:<MG>/auth","token_url":
//     "http://127.0.0.1:<MG>/token","certs_url":"http://127.0.0.1:<MG>/certs"}}' python serve.py <PORT> sandbox --api
//   PHASE=1 STATE=<file> W=390 H=844 PORT=<PORT> MOCK_GOOGLE_PORT=<MG> node tools/cdp.js tools/ui-account-isolation.js   (then PHASE=2)
// A line starting FAIL is data that crossed from one person to the other (or a step that did not happen).
const fs = require("fs");
const gateSignup = require("./gate-signup.js");
module.exports = async ({ ev, sleep, nav, send }) => {
  const PORT = process.env.PORT, MG = process.env.MOCK_GOOGLE_PORT, PHASE = process.env.PHASE || "1", STATE = process.env.STATE;
  const W = Number(process.env.W || 1280), H = Number(process.env.H || 720), base = "http://127.0.0.1:" + PORT;
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + "[isolation " + PHASE + "] " + name + (ok || extra === undefined ? "" : "  | " + String(extra).slice(0, 300))); };
  const q = (sel) => F + ".querySelector(" + JSON.stringify(sel) + ")";
  const click = (sel) => ev("(()=>{const e=" + q(sel) + ";if(!e)return false;e.click();return true})()");
  const ready = async () => { for (let i = 0; i < 60; i++) { if (await ev("!!(" + FW + "&&" + FW + ".__uaply&&" + F + ".getElementById('bnav'))").catch(() => false)) return true; await sleep(250); } return false; };
  const load = async () => { await nav(base + "/?app=1"); await ready(); await sleep(2500); };
  const openAccount = async () => {
    await ev("(()=>{const b=[...(" + F + ").querySelectorAll('button')].find(x=>x.offsetParent&&x.innerText.trim()==='Not now');if(b)b.click()})()"); await sleep(400);
    await ev("(()=>{const b=" + F + ".getElementById('nb-prof');if(b)b.click()})()"); await sleep(400);
    await ev("(()=>{const b=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Account'));if(b)b.click()})()"); await sleep(1800);
  };
  const me = () => ev("fetch('/api/auth/me',{credentials:'same-origin'}).then(r=>r.json()).then(j=>JSON.stringify(j.user||null))").then(JSON.parse);
  const acctProfile = () => ev("fetch('/api/profile/data',{credentials:'same-origin'}).then(r=>r.status===200?r.json().then(j=>JSON.stringify(j.fields)):String(r.status))");
  const KEY = () => ev("window.__uaplyBuildKey||" + FW + ".__uaplyKey");
  const device = async () => { const k = await KEY(); return JSON.parse(await ev("localStorage.getItem(" + JSON.stringify(k) + ")||'{}'")); };
  const tracker = async () => {
    await ev("(()=>{const b=" + F + ".getElementById('nb-dash');if(b)b.click()})()"); await sleep(400);
    await ev("(()=>{const b=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Applied'));if(b)b.click()})()"); await sleep(1500);
    return ev(F + ".body.innerText");
  };
  const sessionCookie = async () => { const r = await send("Network.getCookies", { urls: [base + "/"] }); if (process.env.DEBUG) console.log("NOTE cookies " + JSON.stringify(((r.result || r).cookies || []).map((x) => x.name + (x.httpOnly ? " HttpOnly" : "") + " " + x.sameSite))); const c = ((r.result || r).cookies || []).find((x) => /^uaply_.*_session$/.test(x.name)); return c ? c.name + "=" + c.value : ""; };
  const withCookie = (path, cookie) => fetch(base + path, { headers: { Cookie: cookie } }).then(async (r) => ({ status: r.status, body: await r.text() }));
  const signOut = async () => { await openAccount(); const ok = await click("[data-auth=sout]"); await sleep(2000); return ok; };
  const google = async (email, sub) => {
    await fetch("http://127.0.0.1:" + MG + "/mock/next?email=" + encodeURIComponent(email) + "&sub=" + sub + "&verified=1");
    await load(); await openAccount();
    await ev("(()=>{const a=" + q(".sg-ag") + ";if(a&&!a.checked)a.click()})()");
    await click("[data-sg=google]"); await sleep(6000); await ready(); await sleep(1500);
  };
  const until = async (fn, ms) => { for (let t = 0; t < ms; t += 250) { if (await fn().catch(() => false)) return true; await sleep(250); } return false; };
  const gateUp = () => ev("!!" + FW + ".__uaplyGateUp");
  const typeIn = (sel, v) => ev("(()=>{const e=" + q(sel) + ";if(!e)return false;e.focus();e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return true})()");
  // a new Google account is asked its name, then the work questions: finish them so the real Job Tracker shows (not the gate)
  const finishGate = async (first, last) => {
    if (await ev("!!" + q(".sg-fn input"))) { await typeIn(".sg-fn input", first); await typeIn(".sg-ln input", last); }
    for (let i = 0; i < 6 && (await gateUp()); i++) { await click(".sg-next"); await sleep(600); }
    return !(await gateUp());
  };
  const trackerShown = () => ev("(()=>{const p=" + F + ".getElementById('pane-track');return !!p&&!p.hidden&&p.querySelectorAll('*').length>0})()");
  const ALPHA = /Avery|Alpha|AlphaCorp/;
  const pwLogin = async (email, pw) => {
    const st = await ev("fetch('/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:" + JSON.stringify(email) + ",password:" + JSON.stringify(pw) + "})}).then(r=>r.status)");
    await load(); return st;
  };
  const addRows = async () => { const k = await KEY(), now = Date.now(); await ev("(()=>{const s=JSON.parse(localStorage.getItem(" + JSON.stringify(k) + ")||'{}');s.decisions=s.decisions||{};s.history=s.history||[];" +
    "for(let i=0;i<3;i++){const id=9700001+i;s.decisions[id]={s:'applied',at:" + now + "-i*1000,pct:80,as:'Avery Alpha',title:'',row:{t:'Alpha Role '+i,c:'AlphaCorp',l:'Austin, TX',u:'https://example.com/alpha/'+i,ty:'job',m:'remote'}};if(s.history.indexOf(id)<0)s.history.push(id)}" +
    "localStorage.setItem(" + JSON.stringify(k) + ",JSON.stringify(s));return 1})()"); await load(); };
  const aBack = async (label, email, pw) => {
    check(label + ": A signs in again by password", (await pwLogin(email, pw)) === 200);
    await until(async () => ((await tracker()).match(/AlphaCorp/g) || []).length >= 3, 8000);
    const ua = await me(), da = await device(), ta = await tracker();
    check(label + ": A is the one signed in", ua && ua.email === email, JSON.stringify(ua));
    check(label + ": A's own profile is back (Avery Alpha)", /Avery Alpha/.test(JSON.stringify(da.profile || {})) || /Avery Alpha/.test(await acctProfile()), JSON.stringify(da.profile || {}).slice(0, 160));
    if ((ta.match(/AlphaCorp/g) || []).length < 3) console.log("NOTE [isolation " + PHASE + "] " + label + ": device rows " + Object.keys(da.decisions || {}).length + ", tracker text " + JSON.stringify(ta.slice(0, 300)) + ", row owner record " + await ev("(()=>{const o={};for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i);if(/\.rows$/.test(k))o[k]=localStorage.getItem(k).slice(0,400)}return JSON.stringify(o)})()"));
    check(label + ": A's own three Job Tracker rows are back", (ta.match(/AlphaCorp/g) || []).length >= 3, (ta.match(/AlphaCorp/g) || []).length + " AlphaCorp mentions");
    check(label + ": A sees none of B's profile", !/Blake|Beta/.test(JSON.stringify(da.profile || {})), JSON.stringify(da.profile || {}).slice(0, 160));
  };
  if (W < 700) await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 2, mobile: true });
  else await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });

  if (PHASE === "1") {
    // ---- A: sign up, a profile and three Job Tracker rows on this device, kept on A's account ----
    const A = await gateSignup({ ev, sleep, nav }, base, "alpha", { api: true });
    check("A signed up (email + password, code from the test inbox)", A.ok, A.email);
    await load();
    const k = await KEY(), now = Date.now();
    await ev("(()=>{const K=" + JSON.stringify(k) + ",now=" + now + ";const s=JSON.parse(localStorage.getItem(K)||'{}');" +
      "s.profile={name:'Avery Alpha',title:'Alpha Analyst',years:3,edu:'Bachelor',skills:['AlphaSkill'],salary:70000,payUnit:'year',loc:'Austin, TX'," +
      "modes:{remote:true,hybrid:false,onsite:false},reloc:false,email:" + JSON.stringify(A.email) + ",custom:true};s.decisions={};s.history=[];" +
      "for(let i=0;i<3;i++){const id=9700001+i;s.decisions[id]={s:'applied',at:now-i*1000,pct:80,as:'Avery Alpha',title:'',row:{t:'Alpha Role '+i,c:'AlphaCorp',l:'Austin, TX',u:'https://example.com/alpha/'+i,ty:'job',m:'remote'}};s.history.push(id)}" +
      "localStorage.setItem(K,JSON.stringify(s));return 1})()");
    await load();
    await until(async () => /Avery Alpha/.test(await acctProfile()), 8000);
    const ua = await me();
    const pa = await acctProfile();
    check("A is the one signed in (/api/auth/me)", ua && ua.email === A.email, JSON.stringify(ua));
    check("A's profile is kept on A's account (/api/profile/data has Avery Alpha)", /Avery Alpha/.test(pa), pa);
    check("A's Job Tracker shows A's three AlphaCorp rows", ((await tracker()).match(/AlphaCorp/g) || []).length >= 3);
    const cookieA = await sessionCookie();
    check("A's session cookie is HttpOnly (read here through the browser's own tools, not the page)", !(await ev("document.cookie")).includes("_session="));
    check("a forged ?user= on the profile route still answers only A's own profile", (await ev("fetch('/api/profile/data?user=1&id=1',{credentials:'same-origin'}).then(r=>r.text())")).includes("Avery"));

    // ---- Sign out in the app ----
    check("Sign out is on the Account page and was tapped", await signOut());
    check("after Sign out nobody is signed in (/api/auth/me)", (await me()) === null);
    check("after Sign out the profile route answers 401", (await acctProfile()) === "401");
    const replay = await withCookie("/api/profile/data", cookieA), replayMe = await withCookie("/api/auth/me", cookieA);
    check("A's old session cookie, sent again after Sign out, is refused (401, no profile)", replay.status === 401 && !/Avery/.test(replay.body), replay.status + " " + replay.body);
    check("A's old session cookie no longer names anyone (/api/auth/me)", !/@/.test(replayMe.body), replayMe.body);
    const d0 = await device();
    // by design Sign out only ends the session; the device copy stays until someone else signs in (then claimDevice runs)
    console.log("NOTE [isolation 1] after Sign out the device copy still holds A's profile=" + ALPHA.test(JSON.stringify(d0.profile || {})) + ", rows=" + Object.keys(d0.decisions || {}).length + " (by design)");
    const t0 = await tracker();
    check("after Sign out the Job Tracker shows none of A's rows (the sign-in gate hides them)", !/AlphaCorp/.test(t0) && !(await trackerShown()), (t0.match(/AlphaCorp/g) || []).length + " AlphaCorp mentions");

    // ---- B: Continue with Google (the stand-in) on the same browser ----
    const stamp = Date.now().toString(36), B = { email: "beta." + stamp + "@gmail.com", sub: "iso" + stamp };
    await google(B.email, B.sub);
    const ub = await me();
    check("B is the one signed in after Google (/api/auth/me), not A", ub && ub.email === B.email && ub.email !== A.email, JSON.stringify(ub));
    check("B finishes the new-account questions (name Blake Beta) and the gate goes away", await finishGate("Blake", "Beta"));
    await until(async () => /Blake/.test(await acctProfile()), 8000);   // the profile sync has written B's account
    const pb = await acctProfile(), d1 = await device(), tb = await tracker();
    check("B's Job Tracker pane is really on screen (not hidden behind the gate)", await trackerShown());
    check("B's account did not receive A's profile (/api/profile/data)", !ALPHA.test(pb), pb);
    check("B's app shows no part of A's profile", !ALPHA.test(JSON.stringify(d1.profile || {})), JSON.stringify(d1.profile || {}));
    check("B's saved copy on this device holds none of A's Job Tracker rows", !/AlphaCorp/.test(JSON.stringify(d1.decisions || {})), Object.keys(d1.decisions || {}).length + " rows: " + JSON.stringify(d1.decisions || {}).slice(0, 160));
    check("B's Job Tracker shows none of A's rows", !/AlphaCorp/.test(tb), (tb.match(/AlphaCorp/g) || []).length + " AlphaCorp mentions");
    const cookieB = await sessionCookie();
    check("B's session is a different cookie from A's", cookieB && cookieB !== cookieA, "A " + cookieA.length + " chars, B " + cookieB.length + " chars, same=" + (cookieA === cookieB));
    console.log("NOTE [isolation 1] B's device profile: " + JSON.stringify(d1.profile || {}).slice(0, 200) + " | rows " + Object.keys(d1.decisions || {}).length + " | key " + (await KEY()));
    check("A's old cookie still cannot read anything while B is signed in", (await withCookie("/api/profile/data", cookieA)).status === 401);
    await signOut();
    await aBack("back on browser 1", A.email, A.pw);
    await signOut();
    if (STATE) fs.writeFileSync(STATE, JSON.stringify({ A: { email: A.email, pw: A.pw }, B }));
  } else {
    // ---- a second browser (fresh profile): A by password, then B by Google ----
    const S = JSON.parse(fs.readFileSync(STATE, "utf8"));
    await nav(base + "/legal/privacy.html"); await sleep(500);
    const st = await pwLogin(S.A.email, S.A.pw);
    check("A signs in by password in a second browser", st === 200, st);
    await until(async () => /Avery Alpha/.test(JSON.stringify((await device()).profile || {})), 8000);
    const ua = await me(), da = await device();
    check("A is the one signed in", ua && ua.email === S.A.email, JSON.stringify(ua));
    check("A's profile comes back from A's account in the new browser (Avery Alpha)", /Avery Alpha/.test(JSON.stringify(da.profile || {})), JSON.stringify(da.profile || {}));
    check("nothing of B's is on A's account", !(await acctProfile()).includes(S.B.email));
    await addRows();                                    // A applies to three jobs on this browser too (rows live on the device only)
    check("A's Job Tracker on browser 2 shows A's three AlphaCorp rows", ((await tracker()).match(/AlphaCorp/g) || []).length >= 3);
    await signOut();
    check("after Sign out nobody is signed in", (await me()) === null);
    await google(S.B.email, S.B.sub);
    const ub = await me();
    check("B signs in again with Google in the second browser", ub && ub.email === S.B.email, JSON.stringify(ub));
    await until(async () => /Blake/.test(JSON.stringify((await device()).profile || {})), 8000);
    await sleep(2500);                                  // two more profile-sync ticks: any push of A's fields to B would have happened
    const pb = await acctProfile(), db = await device(), tb = await tracker();
    // the existing-account case: B already has an account; A was the last one on this browser
    check("existing account B on A's browser: B's account received no part of A's profile", !ALPHA.test(pb), pb);
    check("existing account B on A's browser: B's app shows no part of A's profile", !ALPHA.test(JSON.stringify(db.profile || {})), JSON.stringify(db.profile || {}));
    check("existing account B on A's browser: B's saved copy holds none of A's Job Tracker rows", !/AlphaCorp/.test(JSON.stringify(db.decisions || {})), Object.keys(db.decisions || {}).length + " rows");
    check("existing account B on A's browser: B's Job Tracker shows none of A's rows", !/AlphaCorp/.test(tb), (tb.match(/AlphaCorp/g) || []).length + " AlphaCorp mentions");
    await signOut();
    await aBack("back on browser 2", S.A.email, S.A.pw);
    await signOut();
  }
  console.log((bad ? "FAIL " : "") + "[isolation " + PHASE + "] " + (bad ? bad + " check(s) failed" : "all checks passed") + " at " + W + "x" + H);
};
