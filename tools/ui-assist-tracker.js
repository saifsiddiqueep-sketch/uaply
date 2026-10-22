// Assisted apply from the Job Tracker, as the phone app runs it (docs/assisted-apply.md). Needs a running server:
//   python serve.py 20572 dev --api   then   PORT=20572 W=390 H=844 node tools/cdp.js tools/ui-assist-tracker.js
// The phone app's native part (Capacitor.Plugins.UAplyAssist, mobile/android AssistActivity) is stood in for by a fake plugin that records
// what the web app hands it and answers as the native page would. Checks: "Finish applying on their site" hands the employer's page, the
// assist script and the profile (never a voluntary answer) to the app in "assisted" mode; a closed page without the employer's
// confirmation leaves the row "Finish on their site"; only a confirmation page makes it "Sent".
const PORT = process.env.PORT || "20572";
module.exports = async ({ ev, sleep, nav }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  | " + extra : "")); };
  const base = "http://127.0.0.1:" + PORT + "/";
  await nav(base); await sleep(3500);
  check("the server hands out the assist script and the per-system switch",
    (await ev("Promise.all([fetch('/uaply-assist.js').then(r=>r.status+':'+r.headers.get('content-type')),fetch('/assist-systems.json').then(r=>r.json()).then(j=>Object.keys(j.systems).length)]).then(a=>a.join(' '))")).startsWith("200:"));
  // a person with a profile, the agreement given, and a resume file; and voluntary answers saved on the device, which must never leave it
  await ev("(()=>{const w=" + FW + ";w.localStorage.setItem((w.__uaplyKey||'uaply')+'.consent',JSON.stringify({v:3,at:Date.now(),agent:true}));" +
    "const A=w.__uaply;Object.assign(A.S.profile,{name:'Sam Rivera',email:'sam.rivera.test@example.com',custom:true,title:'Data Analyst',years:1,skills:['Python','SQL','Excel'],loc:'Philadelphia, PA',edu:'Bachelor',ext:{phone:'215-555-0142',auth:'citizen',sponsor:'no',school:'Temple University',start:'now',pronouns:'they/them'}});A.save()})()");
  await nav(base); await sleep(4500);
  await ev("(()=>{const w=" + FW + ";w.__uaplyResume=function(){return {name:'Sam Rivera Resume.pdf',size:40,data:'data:application/pdf;base64,'+btoa('%PDF-1.4 Sam Rivera resume for tests %%EOF')}}})()");
  // the phone app's native plugin, stood in for: records each call and answers with __assistNext
  await ev("(()=>{window.__assistCalls=[];window.__assistNext={confirmed:false,url:''};window.Capacitor={isNativePlatform:()=>true,getPlatform:()=>'android',Plugins:{UAplyAssist:{open:(o)=>{window.__assistCalls.push(o);return Promise.resolve(window.__assistNext)}}}}})()");
  // a hand-off job in Applied (an employer on Greenhouse that is not connected to UAply)
  const ID = 990001;
  await ev("(()=>{const w=" + FW + ",A=w.__uaply;A.JOBS.push({id:" + ID + ",co:'Example Co',role:'Support Analyst',loc:'Philadelphia, PA',type:'job',mode:'onsite',url:'https://job-boards.greenhouse.io/exampleco/jobs/4001',source:'greenhouse',skills:['Excel'],sal:'',blurb:''});" +
    "A.S.decisions[" + ID + "]={s:'applied',at:Date.now(),pct:80,as:'Sam Rivera',title:'Data Analyst',sent:{at:Date.now(),to:'',status:'handoff'}};A.S.history.push(" + ID + ");A.save();A.renderAll()})()");
  const openApplied = async () => {
    await ev("(()=>{const b=" + F + ".getElementById('nb-dash');b.click()})()"); await sleep(400);
    await ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Applied'));if(e)e.click()})()"); await sleep(700);
  };
  const row = () => ev("(()=>{const b=" + F + ".querySelector('[data-id=\"" + ID + "\"]');const r=b&&b.closest('.row');return r?r.innerText.replace(/\\s+/g,' '):''})()");
  const finish = () => ev("(()=>{const b=" + F + ".querySelector('[data-finish=\"" + ID + "\"]');if(!b)return false;b.click();return true})()");
  const dec = async () => JSON.parse(await ev("JSON.stringify(" + FW + ".__uaply.S.decisions[" + ID + "]||null)"));
  await openApplied();
  check("the hand-off row says Finish on their site", /Finish on their site/.test(await row()), (await row()).slice(0, 160));

  // 1. the person opens it in the app, then closes the page without the employer's confirmation
  check("Finish applying on their site is there", await finish());
  await sleep(1500);
  const calls = JSON.parse(await ev("JSON.stringify(window.__assistCalls)"));
  check("the app was asked to open the employer's page once", calls.length === 1, calls.length + " calls");
  const c = calls[0] || {}, p = c.profile || {};
  check("the employer's own page, with UAply's source tag", /^https:\/\/job-boards\.greenhouse\.io\/exampleco\/jobs\/4001\?gh_src=uaply$/.test(c.url || ""), c.url);
  check("the assist script itself is handed over", /window\.UAplyAssist/.test(c.engine || "") && (c.engine || "").length > 5000);
  check("mode is assisted (the shipped switch)", c.mode === "assisted" && c.system === "greenhouse", c.mode + " " + c.system);
  check("the profile carries the person's details", p.name === "Sam Rivera" && p.first === "Sam" && p.email === "sam.rivera.test@example.com" && p.phone === "215-555-0142" && p.city === "Philadelphia" && p.auth === "yes" && p.sponsor === "no" && p.school === "Temple University",
    JSON.stringify(Object.assign({}, p, { resume: undefined, answers: undefined })).slice(0, 300));
  check("the resume file goes with it", !!(p.resume && p.resume.b64 && /pdf/.test(p.resume.type)));
  const flat = JSON.stringify(Object.assign({}, p, { resume: null }));
  check("no voluntary answer and no pronouns in what the app gets", !/gender|race|ethnic|hispanic|veteran|disab|pronoun|they\/them/i.test(flat), flat.slice(0, 200));
  await sleep(500);
  let d = await dec();
  check("closed without a confirmation page: still not sent", d && d.sent && d.sent.status === "handoff", JSON.stringify(d && d.sent));
  check("the row still says Finish on their site", /Finish on their site/.test(await row()) && !/\bSent\b/.test(await row()), (await row()).slice(0, 200));
  check("the person is told it is not sent yet", /Not sent yet/.test(await ev("((" + F + ").getElementById('kitToast')||{}).innerText||''")));

  // 2. again, and this time the employer's confirmation page appears after the person taps Submit
  await ev("window.__assistNext={confirmed:true,url:'https://job-boards.greenhouse.io/exampleco/jobs/4001/confirmation'}");
  check("Finish applying again", await finish());
  await sleep(1500);
  d = await dec();
  check("the confirmation page makes it Sent", d && d.sent && d.sent.status === "sent" && d.sent.via === "assist", JSON.stringify(d && d.sent));
  const r2 = await row();
  check("the row says Sent, on the employer's own page", /\bSent\b/.test(r2) && /Sent on Example Co's own page/.test(r2), r2.slice(0, 220));
  check("Finish applying is gone from a sent row", !(await ev("!!" + F + ".querySelector('[data-finish=\"" + ID + "\"]')")));
  check("two calls in all", JSON.parse(await ev("JSON.stringify(window.__assistCalls.length)")) === 2);

  // 3. on the website (no app), the button still opens the employer's page as before
  await ev("(()=>{delete window.Capacitor;const w=" + FW + ",A=w.__uaply;A.S.decisions[" + ID + "].sent={at:Date.now(),to:'',status:'handoff'};A.save();A.renderAll();w.__opened=[];w.__uaplyOpen=function(u){w.__opened.push(u)}})()");
  await openApplied();
  await finish(); await sleep(600);
  const opened = JSON.parse(await ev("JSON.stringify(" + FW + ".__opened)"));
  check("on the website the button opens the employer's page", opened.length === 1 && /gh_src=uaply/.test(opened[0]), JSON.stringify(opened));
  console.log("\n" + (n - bad) + "/" + n + " passed");
  if (bad) process.exitCode = 1;
};
module.exports.limitMs = 180000;
