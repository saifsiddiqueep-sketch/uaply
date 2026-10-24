// For each service tab: what the top card is, how many listings match, and what swiping does on a real (link-out) posting.
//   W=390 H=844 PORT=8769 node tools/cdp.js tools/ui-jobs.js
const PORT = process.env.PORT || "8766";
module.exports = async ({ ev, sleep, nav, shot, logs }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const T = require("path");
  const O = require("os").tmpdir();
  const clickSub = (sub) => ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a,[role=tab]')].find(b=>b.offsetParent&&b.innerText.split(/\\s+/).join(' ').trim().startsWith(" + JSON.stringify(sub) + "));if(!e)return false;e.click();return true})()");
  const setVal = (id, v) => ev("(()=>{const e=" + F + ".getElementById('" + id + "');if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(3000);
  // a profile, the way a user would fill it
  await ev(F + ".getElementById('nb-prof').click()"); await sleep(300);
  await clickSub("Profile setup"); await sleep(400);
  await setVal("pName", "Audit Tester"); await setVal("pEmail", "audit.tester@example.com");
  await ev(F + ".getElementById('wzNext').click()"); await sleep(800);
  await ev(F + ".getElementById('nb-svc').click()"); await sleep(500);
  for (const tab of ["Full-time", "Part-time", "Internships", "Coop"]) {
    await clickSub(tab); await sleep(700);
    const info = JSON.parse(await ev("JSON.stringify({count:(" + F + ".getElementById('fCount')||{}).innerText||'',cards:(" + F + ").querySelectorAll('.card').length,top:((" + F + ").querySelector('.card')||{}).innerText?(" + F + ").querySelector('.card').innerText.split(String.fromCharCode(10)).slice(0,4).join(' / '):'(no card)'})"));
    console.log("[" + tab + "] " + info.count);
    console.log("      top card: " + info.top.slice(0, 150));
    await shot(T.join(O, "jobs-" + tab.toLowerCase().replace(/[^a-z]/g, "") + ".png"));
  }
  // swipe right on a real posting (Internships)
  await clickSub("Internships"); await sleep(600);
  const before = logs.length;
  await ev(F + ".getElementById('btnYes').click()"); await sleep(1500);
  console.log("swipe right -> consent dialog:", await ev("!!" + F + ".getElementById('kcYes')"));
  await ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m){m.ownerDocument.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});m.disabled=false;m.click()}})()"); await sleep(2500);
  console.log("after agreeing, what the person sees:");
  console.log("   ", await ev("[...(" + F + ").querySelectorAll('[role=dialog],[role=status],[role=alert],.toast,.sheet,#kitSheet,.kit')].map(e=>e.innerText.split(String.fromCharCode(10)).join(' ').slice(0,260)).filter(Boolean).join(' || ')"));
  await shot(T.join(O, "jobs-after-swipe.png"));
  console.log("script errors during the swipe:", logs.length - before);
};
