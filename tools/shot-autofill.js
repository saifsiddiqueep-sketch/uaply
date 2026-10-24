// The sandbox, at iPhone size: a student fills in a profile once, swipes right on real postings, answers the few questions only they can
// answer, and UAply fills in and applies to the rest. Screenshots of each step go to OUT.
//   OUT=<folder> W=390 H=844 PORT=<sandbox server> node tools/cdp.js tools/shot-autofill.js
const path = require("path");
const fs = require("fs");
const PORT = process.env.PORT || "8766";
module.exports = async ({ ev, sleep, nav, shot, logs }) => {
  const OUT = process.env.OUT;
  fs.mkdirSync(OUT, { recursive: true });
  const F = "document.querySelector('iframe').contentDocument";
  const FW = "document.querySelector('iframe').contentWindow";
  const setVal = (id, v) => ev("(()=>{const e=" + F + ".getElementById('" + id + "');if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  const pick = async (nb, label) => { await ev(F + ".getElementById('" + nb + "').click()"); await sleep(450); return ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith(" + JSON.stringify(label) + "));if(!e)return false;e.click();return true})()"); };
  const text = () => ev("(" + F + ").body.innerText");
  const snap = async (name) => { await shot(path.join(OUT, name + ".png")); console.log("shot", name); };
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };

  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(5000);
  await ev("(()=>{const b=document.getElementById('fold');if(b&&b.getAttribute('aria-expanded')==='true')b.click()})()");   // hide the sandbox controls

  // ---- the profile, filled in once ----
  await pick("nb-prof", "Settings"); await sleep(600);
  await setVal("pName", "Sam Rivera"); await setVal("pEmail", "sam.rivera@example.com"); await setVal("pLoc", "Philadelphia, PA");
  for (const [k, v] of [["phone", "+1 215 555 0100"], ["linkedin", "https://www.linkedin.com/in/sam-rivera"], ["portfolio", "https://github.com/samrivera"],
                        ["summary", "Computer science student at Drexel who builds full-stack web apps and ships them to real users."],
                        ["school", "Drexel University"], ["major", "Computer Science"], ["grad", "2027-06"], ["gpa", "3.6"]]) await setVal("px-" + k, v);
  await setVal("adStreet", "3141 Chestnut St"); await setVal("adState", "PA"); await setVal("adZip", "19104");
  await ev(F + ".getElementById('saveBtn').click()"); await sleep(900);
  await pick("nb-prof", "Preferences"); await sleep(700);
  await ev("(()=>{const w=" + FW + ";const i=" + F + ".getElementById('pResFile');const dt=new w.DataTransfer();const bytes=new w.Uint8Array([37,80,68,70,45,49,46,52,10,37,226,227,207,211,10,115,97,109,10,37,37,69,79,70,10]);dt.items.add(new w.File([bytes],'Sam-Rivera-Resume.pdf',{type:'application/pdf'}));i.files=dt.files;i.dispatchEvent(new w.Event('change',{bubbles:true}))})()");
  await sleep(1200);
  for (const [k, v] of [["auth", "citizen"], ["sponsor", "no"], ["start", "grad"], ["office", "yes"], ["former", "no"], ["govt", "no"], ["phd", "no"], ["ack", "yes"],
                        ["why", "I'm excited about {company} because the {role} role matches the projects I build at Drexel, and I learn fastest on teams that ship."]]) await setVal("px-" + k, v);
  await ev("(()=>{const c=" + F + ".getElementById('pReloc');if(c&&!c.checked)c.click()})()");          // Work style: willing to relocate
  await ev(F + ".getElementById('saveBtn').click()"); await sleep(1500);
  await ev("(()=>{const t=" + F + ".getElementById('kitToast');if(t)t.remove();const h=" + F + ".querySelector('.toast');if(h)h.remove();const s=[...(" + F + ").querySelectorAll('h3')].find(h=>/questions employers ask/i.test(h.innerText));if(s)s.scrollIntoView({block:'start'})})()"); await sleep(500);
  await snap("auto-1-questions-employers-ask");
  const ext = await ev("JSON.stringify(" + FW + ".__uaplyApplyExt())");
  check("the profile keeps the new answers (phone, ZIP, relocation...)", ext.includes('"relocate":"yes"') && ext.includes('"phone":"+1 215 555 0100"') && ext.includes('"zip":"19104"'), ext.slice(0, 160));

  // ---- swipe right on real postings ----
  await pick("nb-svc", "Full-time"); await sleep(1200);
  const swipeRight = async (label) => {
    const before = await ev("(()=>{const c=" + F + ".querySelector('.card.top');return c?c.innerText.split(String.fromCharCode(10)).slice(0,3).join(' | '):''})()");
    await ev(F + ".getElementById('btnYes').click()"); await sleep(900);
    await ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m){m.ownerDocument.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});m.disabled=false;m.click()}})()");          // the one-time first-application agreement
    for (let i = 0; i < 20; i++) { await sleep(500); if (await ev("!!(" + F + ".getElementById('kitAsk')||" + F + ".getElementById('kitToast'))")) break; }
    console.log("   swiped right on:", before.slice(0, 90));
    return before;
  };
  const answerAll = () => ev("(()=>{const d=" + F + ";const o=d.getElementById('kitAsk');if(!o)return 0;let n=0;o.querySelectorAll('[data-k]').forEach(el=>{n++;if(el.tagName==='SELECT'){const opts=[...el.options].slice(1);const lab=(o.querySelector('label[for='+el.id+']')||{}).innerText||'';const pref=/hear|learn|find/i.test(lab)?/^other/i:/^no\\b/i;const hit=opts.find(x=>pref.test(x.text));el.value=(hit||opts[opts.length-1]).text}else if(el.tagName==='TEXTAREA'){el.value='I build full-stack projects at Drexel and want to learn from a team that ships to real users.'}else{el.value='Sam'}});return n})()");

  await swipeRight("first");
  const asked = await ev("!!" + F + ".getElementById('kitAsk')");
  if (asked) {
    await snap("auto-2-only-the-questions-you-must-answer");
    const n = await answerAll(); await sleep(300);
    console.log("   answered", n, "question(s) once");
    await ev(F + ".getElementById('kaYes').click()");
    for (let i = 0; i < 20; i++) { await sleep(500); if (await ev("!!" + F + ".getElementById('kitToast')")) break; }
  }
  await sleep(600);
  const t1 = await text();
  check("the first swipe right applied, and says how much UAply filled in", /Applied to .* \(test\)\. UAply filled in \d+ of \d+ answers/.test(t1), (t1.match(/Applied to[^\n]*/) || [""])[0].slice(0, 140));
  await snap("auto-3-applied-after-one-swipe");

  // more swipes: the saved answers carry over, so most go straight in
  let direct = 0, tries = 0;
  for (; tries < 6; tries++) {
    await sleep(700);
    await swipeRight("next");
    if (await ev("!!" + F + ".getElementById('kitAsk')")) { await answerAll(); await sleep(200); await ev(F + ".getElementById('kaYes').click()"); await sleep(2500); }
    else direct++;
    await sleep(900);
  }
  console.log("   " + direct + " of " + tries + " more swipes applied with no question at all");
  await snap("auto-4-next-swipe");

  // the Applied list says what really happened to each one
  await pick("nb-dash", "Applied"); await sleep(900);
  const applied = await text();
  check("the Applied list never says 'sent' for something that was not", !/Application sent to the company/.test(applied));
  check("the Applied list shows the test sends", /Sent to .* hiring system \(simulated\) \(test, nothing reached/.test(applied));
  await snap("auto-5-applied-list");

  // the test inbox shows the employer's own form, filled in
  await nav("http://127.0.0.1:" + PORT + "/outbox"); await sleep(1500);
  const ob = await ev("document.body.innerText");
  check("the test inbox shows the employer's form as UAply filled it in", /Employer's application form, filled in by UAply: \d+ of \d+ answers/.test(ob));
  await snap("auto-6-test-inbox-filled-form");
  check("no script errors", logs.length === 0, logs.join(" / ").slice(0, 200));
  console.log(bad ? bad + " check(s) failed" : "All autofill demo checks passed");
};
