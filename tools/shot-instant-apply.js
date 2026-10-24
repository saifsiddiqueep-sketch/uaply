// Signs up and verifies an account, fills the profile, swipes right on a job that says "Apply instantly" and saves screenshots of each step.
//   OUT=<folder> MAIL=<mail.jsonl of tools/fake-smtp.py> W=390 H=844 PORT=18795 node tools/cdp.js tools/shot-instant-apply.js
const path = require("path");
const fs = require("fs");
const { execFileSync } = require("child_process");
const PORT = process.env.PORT || "18795";
module.exports = async ({ ev, sleep, nav, shot }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const OUT = process.env.OUT;
  fs.mkdirSync(OUT, { recursive: true });
  const set = (id, v) => ev("(()=>{const e=" + F + ".getElementById('" + id + "');if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  const click = (txt) => ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a,[role=tab]')].find(b=>b.offsetParent&&b.innerText.split(/\\s+/).join(' ').trim().startsWith(" + JSON.stringify(txt) + "));if(!e)return false;e.click();return true})()");
  const go = async (nb, label) => { await ev(F + ".getElementById('" + nb + "').click()"); await sleep(350); let ok = await click(label); if (!ok) { await ev(F + ".getElementById('" + nb + "').click()"); await sleep(350); ok = await click(label); } await sleep(700); return ok; };
  const EMAIL = "new.user@gmail.com";

  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(3500);
  await go("nb-prof", "Account"); await sleep(1000);
  await set("sEmail", EMAIL); await set("sPw", "correct horse 99"); await set("sPw2", "correct horse 99");
  await ev("(()=>{" + F + ".getElementById('sAgree').checked=true})()");
  await ev(F + ".querySelector('[data-auth=ssubmit]').click()"); await sleep(3000);
  const info = execFileSync("python", ["tools/mail-extract.py", process.env.MAIL, OUT, EMAIL], { encoding: "utf-8" });
  const code = (info.match(/code=(\d{6})/) || [])[1];
  await set("sCode", code);
  await ev(F + ".querySelector('[data-auth=sverify]').click()"); await sleep(1800);
  // the profile an applicant fills in once
  await go("nb-prof", "Settings");
  await set("pName", "Sam Rivera"); await set("pEmail", EMAIL); await set("pTitle", "Robotics"); await set("pSkills", "Python, SQL"); await set("pYears", "1");
  await ev(F + ".getElementById('saveBtn').click()"); await sleep(700);
  await go("nb-prof", "Resume");
  await set("aPhone", "+1 555 123 4567"); await set("aSummary", "Computer science student who builds small robots and likes testing them.");
  await ev("(()=>{const b=" + F + ".querySelector('[data-a=saveres]');if(b)b.click()})()"); await sleep(700);
  // the job, with its badge
  await go("nb-svc", "Internships"); await sleep(1200);
  await shot(path.join(OUT, "apply-1-card.png"));
  console.log("card shows Apply instantly:", await ev("(" + F + ").body.innerText.indexOf('Apply instantly')>=0"));
  // swipe right: the undo window, then the result
  await ev(F + ".getElementById('btnYes').click()"); await sleep(1300);
  await ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m){m.ownerDocument.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});m.disabled=false;m.click()}})()"); await sleep(1800);
  await shot(path.join(OUT, "apply-2-undo-window.png"));
  await sleep(6500);
  await shot(path.join(OUT, "apply-3-applied.png"));
  console.log("result:", (await ev("(" + F + ").body.innerText.split(/\\s+/).join(' ')")).match(/(Applying to|Applied to|Saved\.|Could not)[^.]{0,120}/g));
};
