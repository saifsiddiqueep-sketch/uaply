// Signs up a fresh account (left unverified, like a new user), swipes right, and saves screenshots of the message and of the test inbox.
//   OUT=<folder> W=390 H=844 PORT=18796 node tools/cdp.js tools/shot-swipe-email.js
const path = require("path");
const fs = require("fs");
const PORT = process.env.PORT || "18796";
module.exports = async ({ ev, sleep, nav, shot }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const OUT = process.env.OUT;
  fs.mkdirSync(OUT, { recursive: true });
  const set = (id, v) => ev("(()=>{const e=" + F + ".getElementById('" + id + "');if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  const click = (txt) => ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a,[role=tab]')].find(b=>b.offsetParent&&b.innerText.split(/\\s+/).join(' ').trim().startsWith(" + JSON.stringify(txt) + "));if(!e)return false;e.click();return true})()");
  const text = () => ev("(" + F + ").body.innerText.split(/\\s+/).join(' ')");

  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(3000);
  // 1. an account, left unverified
  await ev(F + ".getElementById('nb-prof').click()"); await sleep(400);
  await click("Account"); await sleep(1500);
  await set("sEmail", "demo.person@example.com"); await set("sPw", "correct horse 99"); await set("sPw2", "correct horse 99");
  await ev("(()=>{" + F + ".getElementById('sAgree').checked=true})()");
  await ev(F + ".querySelector('[data-auth=ssubmit]').click()"); await sleep(2500);
  console.log("signed up; account says:", (await text()).slice(0, 150));
  // 2. a profile so the application can be sent
  await ev(F + ".getElementById('nb-prof').click()"); await sleep(400);
  await click("Settings"); await sleep(600);
  await set("pName", "Demo Person"); await set("pEmail", "demo.person@example.com"); await set("pSkills", "Python, SQL");
  await ev(F + ".getElementById('saveBtn').click()"); await sleep(800);
  // 3. swipe right
  await ev(F + ".getElementById('nb-svc').click()"); await sleep(500);
  await click("Full-time"); await sleep(900);                         // choose from the menu, the way a person does, so the menu closes
  await ev(F + ".getElementById('btnYes').click()"); await sleep(1500);
  await ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m){m.ownerDocument.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});m.disabled=false;m.click()}})()");
  await sleep(2200);
  const msg = await ev("(()=>{const d=" + F + ";const s=d.getElementById('toast')||d.querySelector('.toast,[role=status]');return s?s.innerText:''})()");
  console.log("message after the swipe:", JSON.stringify(msg));
  await shot(path.join(OUT, "swipe-1-message.png"));
  // 4. the test inbox
  await nav("http://127.0.0.1:" + PORT + "/outbox");
  await sleep(1500);
  const box = await ev("document.body.innerText.split(/\\s+/).join(' ')");
  console.log("test inbox shows a [TEST] confirmation to demo.person@example.com:", /\[TEST\][^|]{0,120}/.test(box) && box.indexOf("demo.person@example.com") >= 0);
  await ev("(()=>{const a=[...document.querySelectorAll('summary,h2,h3,b')].find(e=>/Confirmation|Receipts|receipt/i.test(e.innerText));if(a)a.scrollIntoView({block:'start'})})()");
  await sleep(400);
  await shot(path.join(OUT, "swipe-2-test-inbox.png"));
};
