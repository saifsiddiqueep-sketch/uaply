// The sign-up and email-code screens in a real browser, and Google's button area, on the sign-in gate's card (October 22, Saif: nobody
// reaches anything on the site without an account, so the card is the first screen). Needs a server with the stand-in Google configured
// (see tools/run-all-tests.sh) so the Google area is switched on, and NOT in sign-up test mode: this walks the emailed code.
//   W=390 H=844 PORT=18768 node tools/cdp.js tools/ui-verify.js
const PORT = process.env.PORT || "18768";
module.exports = async ({ ev, sleep, nav, logs }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const BASE = "http://127.0.0.1:" + PORT;
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const q = (sel) => F + ".querySelector(" + JSON.stringify(sel) + ")";
  const card = () => ev("((" + F + ").getElementById('acctSec')||{innerText:''}).innerText.split(/\\s+/).join(' ')");
  const cmsg = () => ev("((" + F + ").querySelector('.sg-cmsg')||{}).textContent||''");
  const setv = (sel, v) => ev("(()=>{const e=" + q(sel) + ";if(!e)return false;e.focus();e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return true})()");
  const typeCode = (c) => ev("(()=>{const b=[...(" + F + ").querySelectorAll('.sg-code input')];if(b.length!==6)return false;b[0].focus();b[0].value=" + JSON.stringify(c) + ";b[0].dispatchEvent(new Event('input',{bubbles:true}));return true})()");
  const me = () => ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>JSON.stringify(j.user||null))").then(JSON.parse);
  const codeFromInbox = (addr) => ev("fetch('/outbox').then(r=>r.text()).then(t=>{const all=[...t.replace(/<[^>]+>/g,' ').replace(/\\s+/g,' ').matchAll(new RegExp('([0-9]{6}) is your UAply verification code to '+" + JSON.stringify(addr.replace(/\./g, "\\.")) + ",'g'))];return all.length?all[0][1]:''})");
  const email = "ui.verify." + Date.now() + "@example.com";
  const prov = JSON.parse(await (async () => { try { return JSON.stringify(await (await fetch(BASE + "/api/auth/providers")).json()); } catch (e) { return "{}"; } })());
  if (prov.signupTest) console.log("  (this server is in sign-up test mode: there is no code to walk; run it on a server without UAPLY_SIGNUP_TEST)");

  await nav(BASE + "/");
  for (let i = 0; i < 40 && !(await ev("!!" + q(".sg-su")).catch(() => false)); i++) await sleep(250);
  await sleep(800);
  check("signed out, the sign-up form is the screen (the sign-in gate's card)", !!(await ev("!!" + q(".sg-su"))) && (await ev(F + ".body.classList.contains('sgGated')")));
  check("Google's button area is there (the page was told Google is switched on)", !!(await ev("!!" + q(".sg-card .sg-btn.g"))));
  check("the Google area asks for consent through the card's own 18+ / Terms tick (needed the first time)", !!(await ev("!!" + q(".sg-su .sg-ag"))));
  const gtxt = await ev("((" + q(".sg-card .sg-btn.g") + ")||{}).innerText||''");
  check("Google's button drew: the G logo and the words Continue with Google", /Continue with Google/.test(gtxt) && !!(await ev("!!" + q(".sg-card .sg-btn.g svg"))), gtxt.slice(0, 80));

  // sign up with a password
  await setv(".sg-su [data-email] input", email); await setv(".sg-su .sg-fn input", "Vera"); await setv(".sg-su .sg-ln input", "Fy"); await setv(".sg-su .sg-pw input", "correct horse 99");
  await ev("(()=>{const a=" + q(".sg-su .sg-ag") + ";if(a&&!a.checked)a.click();" + q(".sg-su [type=submit]") + ".click()})()");
  for (let i = 0; i < 30 && !/Check your email/.test(await card()); i++) await sleep(250);
  const t1 = await card();
  check("after sign-up, the page asks for the 6-digit code", /Check your email/.test(t1) && (await ev(F + ".querySelectorAll('.sg-code input').length")) === 6, t1.slice(0, 160));
  const u1 = await me();
  check("the account is made and signed in, its email not verified yet", !!u1 && u1.email === email && u1.emailVerified === false, JSON.stringify(u1));
  check("the card says where the code went (this address) and for how long", t1.includes(email) && /10 minutes/.test(t1), t1.slice(0, 200));

  // wrong code, then the right one
  await typeCode("000000"); await sleep(1500);
  const wrong = await cmsg();
  check("a wrong code is refused and says how many tries are left", /tries? left|not right|did not work/i.test(wrong), wrong);
  check("...and the boxes clear for the next try", (await ev("[...(" + F + ").querySelectorAll('.sg-code input')].map(x=>x.value).join('')")) === "");
  await ev("(()=>{const m=" + q(".sg-cmsg") + ";if(m)m.textContent=''})()");
  await typeCode("12"); await sleep(800);
  check("a code that is too short is not sent (nothing is checked until all six digits are in)", (await cmsg()) === "" &&
    (await ev("[...(" + F + ").querySelectorAll('.sg-code input')].map(x=>x.value).join('')")) === "12", await cmsg());
  await ev("[...(" + F + ").querySelectorAll('.sg-code input')].forEach(x=>{x.value='';x.dispatchEvent(new Event('input',{bubbles:true}))})");
  for (let i = 0; i < 40 && (await ev("!!(" + q(".sg-resend") + "||{}).disabled")); i++) await sleep(1000);   // Resend opens 30 s after the code was sent
  check("Send a new code works (Resend code, once its 30 seconds are up)", await ev("(()=>{const r=" + q(".sg-resend") + ";if(!r||r.disabled)return false;r.click();return true})()"));
  await sleep(2000);
  check("it says a new code is on its way", /new code is on its way/i.test(await cmsg()), await cmsg());
  const code = await codeFromInbox(email);
  check("the code can be found in the test inbox", /^[0-9]{6}$/.test(code), code);
  await typeCode(code); await sleep(2500);
  const u2 = await me(), t2 = await card();
  check("the right code verifies the email", !!u2 && u2.emailVerified === true, JSON.stringify(u2));
  check("the code step is gone: the two questions come next (Account created)", !/Check your email/.test(t2) && /1 of 2|What kind of work|Account created/i.test(t2), t2.slice(0, 200));

  // it stays verified after a reload
  await nav(BASE + "/"); await sleep(3500);
  const u3 = await me();
  check("still verified after a reload, and the code step does not come back", !!u3 && u3.emailVerified === true && !/Check your email/.test(await card()), JSON.stringify(u3));
  const errs = logs.filter((l) => !/401|403|favicon/.test(l));
  check("no script errors", errs.length === 0, errs.join(" / ").slice(0, 160));
  console.log(bad ? "\n" + bad + " check(s) failed" : "\nAll sign-up and verification screen checks passed");
};
