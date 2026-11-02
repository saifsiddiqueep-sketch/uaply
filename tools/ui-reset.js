// Walks forgot password -> email link -> new password -> sign in -> change password through the real screens, from the sign-in gate's card
// (October 22, Saif: signed out, the card is the whole screen; its Welcome back view has Forgot password?).
// PORT=<dev or sandbox port> node tools/cdp.js tools/ui-reset.js     (ideally with a clean data folder)
const PORT = process.env.PORT || "8766";
module.exports = async ({ ev, sleep, nav, send, shot }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const BASE = "http://127.0.0.1:" + PORT;
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const q = (sel) => F + ".querySelector(" + JSON.stringify(sel) + ")";
  const clickSel = (sel) => ev("(()=>{const e=" + q(sel) + ";if(!e)return false;e.click();return true})()");
  const byAuth = (a) => F + ".querySelector('[data-auth=\"" + a + "\"]')";
  const click = (a) => ev("(()=>{const e=" + byAuth(a) + ";if(!e)return false;e.click();return true})()");
  const setVal = (id, v) => ev("(()=>{const e=" + F + ".getElementById('" + id + "');if(!e)return false;e.value=" + JSON.stringify(v) + ";return true})()");
  const setSel = (sel, v) => ev("(()=>{const e=" + q(sel) + ";if(!e)return false;e.focus();e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return true})()");
  const note = () => ev(F + ".getElementById('aMsg')?" + F + ".getElementById('aMsg').innerText:''");
  const accountText = () => ev("(" + F + ").body.innerText.split(String.fromCharCode(10)).join(' ')");
  const me = () => ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>JSON.stringify(j.user||null))").then(JSON.parse);
  const ready = async (sel) => { for (let i = 0; i < 40 && !(await ev("!!" + q(sel)).catch(() => false)); i++) await sleep(250); await sleep(500); };
  const openAccount = async () => {
    await ev(F + ".getElementById('nb-prof').click()"); await sleep(400);
    await ev("(()=>{const b=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')==='account');if(b)b.click()})()"); await sleep(700);
  };
  const email = "ui.reset." + Date.now() + "@example.com";

  await send("Storage.clearDataForOrigin", { origin: BASE, storageTypes: "all" });
  await nav(BASE + "/");
  await sleep(1200);
  // make an account through the API, then sign out, so the screen is the gate's card
  console.log("signup via API:", await ev("fetch('/api/auth/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'" + email + "',password:'old password 11',first:'Rhea',last:'Set',agree:true})}).then(r=>r.status)"));
  console.log("logout via API:", await ev("fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.status)"));
  await nav(BASE + "/");
  await ready(".sg-card");
  check("create-account form shows first (the sign-in gate's card)", !!(await ev("!!" + q(".sg-su"))));
  check("switch to sign in (Have an account? Sign in)", await clickSel(".sg-to-in")); await sleep(400);
  check("Forgot password? button is on the sign-in screen (Welcome back)", !!(await ev("!!" + q(".sg-forgot"))) && /Welcome back/.test(await accountText()));
  check("open Forgot password", await clickSel(".sg-forgot")); await sleep(400);
  const em0 = await ev("((" + q(".sg-si [data-email] .sg-fmsg") + ")||{}).textContent||''");
  check("an empty email is refused with a message (the link needs the address)", /email/i.test(em0) && !(await ev("!!" + q(".sg-fgmsg"))), em0);
  await setSel(".sg-si [data-email] input", email);
  await clickSel(".sg-forgot"); await sleep(1500);
  const fg = await ev("((" + q(".sg-fgmsg") + ")||{}).textContent||''");
  check("it says a link is on its way to that address (the same answer whether or not it has an account)", fg.includes(email) && /link to choose a new password/.test(fg), fg);
  const tok = await ev("fetch('/outbox').then(r=>r.text()).then(t=>{const d=document.createElement('textarea');d.innerHTML=t;const m=d.value.match(/[?]reset=([A-Za-z0-9_-]{20,100})/);return m?m[1]:''})");
  check("test mode: the reset link is in the test inbox", tok.length > 20);

  // follow the link from the email
  await nav(BASE + "/?reset=" + tok);
  await sleep(1800);
  check("link opens the new-password form, on screen behind the gate", !!(await ev("(()=>{const e=" + F + ".getElementById('sRPw');return !!e&&e.getClientRects().length>0})()")));
  await setVal("sRPw", "short"); await setVal("sRPw2", "short");
  await click("sresetgo"); await sleep(300);
  check("a short password is refused", (await note()).includes("8 characters"), await note());
  await setVal("sRPw", "brand new pass 22"); await setVal("sRPw2", "different pass 33");
  await click("sresetgo"); await sleep(300);
  check("mismatched passwords are refused", (await note()).includes("do not match"), await note());
  await setVal("sRPw2", "brand new pass 22");
  await click("sresetgo"); await sleep(1500);
  check("success message, and the new-password form is gone", /Password changed/.test((await note()) + " " + (await accountText())) && !(await ev("!!" + F + ".getElementById('sRPw')")), (await note()) || (await accountText()).slice(0, 200));
  check("the address bar no longer holds the token", !(await ev("location.href")).includes("reset="));

  // sign in with the new password, on the card
  await nav(BASE + "/"); await ready(".sg-card");
  if (await ev("!!" + q(".sg-to-in"))) { await clickSel(".sg-to-in"); await sleep(400); }
  await setSel(".sg-si [data-email] input", email); await setSel(".sg-si .sg-pw input", "old password 11");
  await clickSel(".sg-si [type=submit]"); await sleep(1500);
  check("the old password no longer signs in", (await me()) === null);
  await setSel(".sg-si .sg-pw input", "brand new pass 22");
  await clickSel(".sg-si [type=submit]"); await sleep(2000);
  const u = await me();
  check("sign in with the new password", !!u && u.email === email, JSON.stringify(u));
  for (let i = 0; i < 6 && (await ev(F + ".body.classList.contains('sgGated')")); i++) { await clickSel(".sg-next"); await sleep(700); }   // any questions left (resume skipped, work, where, phone, the last screen)
  await shot(require("path").join(require("os").tmpdir(), "ui-signed-in.png"));

  // change password, on the Account screen
  await nav(BASE + "/"); await sleep(2500);
  await openAccount();
  check("Change password button shows", !!(await ev("!!" + byAuth("schg"))), (await accountText()).slice(0, 200));
  await click("schg"); await sleep(300);
  await setVal("sCur", "wrong password 9"); await setVal("sNew", "changed again 44"); await setVal("sNew2", "changed again 44");
  await click("schgo"); await sleep(1200);
  check("wrong current password is refused", (await note()).includes("current password"), await note());
  await setVal("sCur", "brand new pass 22"); await setVal("sNew", "changed again 44"); await setVal("sNew2", "changed again 44");
  await click("schgo"); await sleep(3500);
  check("password changed", (await note()).includes("Password changed"), await note());
  const u2 = await me();
  check("still signed in", !!u2 && u2.email === email);
  console.log(bad ? "\n" + bad + " check(s) failed" : "\nAll reset-flow checks passed");
};
