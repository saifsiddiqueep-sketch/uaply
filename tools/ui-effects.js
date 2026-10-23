// Checks the buttons that ui-audit.js cannot "see" working: the + skill chips, the empty Add button, and the three file downloads.
//   W=390 H=844 PORT=18795 node tools/cdp.js tools/ui-effects.js
const PORT = process.env.PORT || "8766";
module.exports = async ({ ev, sleep, nav }) => {
  // the sign-in gate (October 22, Saif): nobody reaches the jobs without an account, so a fresh test person signs up first (tools/gate-signup.js)
  await require("./gate-signup.js")({ ev, sleep, nav }, "http://127.0.0.1:" + (process.env.PORT || "8767"), "effects");
  const F = "document.querySelector('iframe').contentDocument";
  const W = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const click = (txt) => ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a,[role=tab]')].find(b=>b.offsetParent&&b.innerText.split(/\\s+/).join(' ').trim().startsWith(" + JSON.stringify(txt) + "));if(!e)return false;e.click();return true})()");

  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(2500);

  // skill chips
  await ev(F + ".getElementById('nb-prof').click()"); await sleep(400);
  await click("Profile setup"); await sleep(500);
  await ev("(()=>{const b=" + F + ".querySelector('.wzDots button[data-step=\"1\"]');if(b)b.click()})()"); await sleep(500);   // step 2, Jobs you want: skills
  const before = await ev(F + ".getElementById('pSkills').value");
  const chips = JSON.parse(await ev("JSON.stringify([...(" + F + ").querySelectorAll('button')].filter(b=>b.offsetParent&&/^\\+ /.test(b.innerText.trim())).map(b=>b.innerText.trim()))"));
  console.log("  skills before:", JSON.stringify(before), "| chips shown:", chips.join(", "));
  check("suggestion chips are shown", chips.length > 0);
  if (chips.length) {
    const first = chips[0].slice(2);
    await click(chips[0]); await sleep(500);
    const after = await ev(F + ".getElementById('pSkills').value");
    const shown = await ev("(" + F + ").body.innerText.indexOf(" + JSON.stringify(first) + ")>=0");
    check("clicking " + chips[0] + " adds the skill to the field", after.toLowerCase().indexOf(first.toLowerCase()) >= 0, "(field now: " + JSON.stringify(after) + ")");
    const chipsAfter = JSON.parse(await ev("JSON.stringify([...(" + F + ").querySelectorAll('button')].filter(b=>b.offsetParent&&/^\\+ /.test(b.innerText.trim())).map(b=>b.innerText.trim()))"));
    check("the chip that was used is replaced or removed", chipsAfter.indexOf(chips[0]) < 0, "(chips now: " + chipsAfter.join(", ") + ")");
  }
  // empty Add must not break anything
  await ev("(()=>{const e=" + F + ".getElementById('pSkills');e.value='';e.dispatchEvent(new Event('input',{bubbles:true}))})()");
  const addOk = await click("Add"); await sleep(300);
  check("the Add button exists and an empty click does no harm", addOk && (await ev(F + ".getElementById('pSkills').value")) === "");

  // downloads: wrap Blob so we can see what each button builds
  await ev("(()=>{const w=" + W + ";w.__dl=[];const o=w.URL.createObjectURL.bind(w.URL);w.URL.createObjectURL=function(b){w.__dl.push({type:b.type,size:b.size});return o(b)};w.HTMLAnchorElement.prototype.click=function(){w.__dl.push({download:this.download||'',href:(this.href||'').slice(0,20)})}})()");
  await ev(F + ".getElementById('nb-prof').click()"); await sleep(400);
  await click("Data"); await sleep(500);
  for (const label of ["Download backup (JSON)", "Applications (CSV)"]) {
    await ev(W + ".__dl=[]");
    const ok = await click(label); await sleep(600);
    const got = JSON.parse(await ev("JSON.stringify(" + W + ".__dl)"));
    check(label + " builds a file", ok && got.length > 0 && got.some((g) => g.size > 0 || g.download), JSON.stringify(got));
  }
  await ev(F + ".getElementById('nb-dash').click()"); await sleep(500);
  await click("Overview"); await sleep(400);
  await ev(W + ".__dl=[]");
  const ok = await click("Export applications (CSV)"); await sleep(600);
  const got = JSON.parse(await ev("JSON.stringify(" + W + ".__dl)"));
  check("Export applications (CSV) builds a file", ok && got.length > 0 && got.some((g) => g.size > 0 || g.download), JSON.stringify(got));
  console.log(bad ? bad + " problem(s)" : "All good");
};
