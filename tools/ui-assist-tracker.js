// Assisted apply from the Job Tracker, as the phone app runs it (docs/assisted-apply.md). Needs a running server:
//   python serve.py 20572 dev --api   then   PORT=20572 W=390 H=844 node tools/cdp.js tools/ui-assist-tracker.js
// The phone app's native part (Capacitor.Plugins.UAplyAssist, mobile/android AssistActivity) is stood in for by a fake plugin that records
// what the web app hands it and answers as the native screen would: a scan call returns the form's questions the profile cannot answer
// (minus the ones already answered), a fill call returns what __assistNext says. Checks: "Finish applying on their site" first reads the
// form, asks those questions in UAply's own question box (required ones must be answered, optional ones may be left), and only then opens
// the form with the answers, in "assisted" mode, with the profile and never a voluntary answer; "Not now" opens nothing; a closed form
// without the employer's confirmation leaves the row "Finish on their site"; only a confirmation page makes it "Sent".
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
    "w.localStorage.removeItem((w.__uaplyKey||'uaply')+'.answers');" +
    "const A=w.__uaply;Object.assign(A.S.profile,{name:'Sam Rivera',email:'sam.rivera.test@example.com',custom:true,title:'Data Analyst',years:1,skills:['Python','SQL','Excel'],loc:'Philadelphia, PA',edu:'Bachelor',ext:{phone:'215-555-0142',auth:'citizen',sponsor:'no',school:'Temple University',start:'now',pronouns:'they/them'}});A.save()})()");
  await nav(base); await sleep(4500);
  await ev("(()=>{const w=" + FW + ";w.__uaplyResume=function(){return {name:'Sam Rivera Resume.pdf',size:40,data:'data:application/pdf;base64,'+btoa('%PDF-1.4 Sam Rivera resume for tests %%EOF')}}})()");
  // the phone app's native plugin, stood in for
  await ev("(()=>{window.__assistCalls=[];window.__assistNext={confirmed:false,url:''};" +
    "window.__assistQs=[{q:'Describe a project you led',key:'Describe a project you led',kind:'textarea',required:true},{q:'Cover letter',key:'Cover letter',kind:'textarea',required:false}];" +
    "window.Capacitor={isNativePlatform:()=>true,getPlatform:()=>'android',Plugins:{UAplyAssist:{open:(o)=>{window.__assistCalls.push(o);" +
    "if(o.scan){const a=(o.profile&&o.profile.answers)||{};return Promise.resolve({confirmed:false,questions:window.__assistQs.filter(q=>!a[q.key]),seen:20,filled:15})}" +
    "return Promise.resolve(window.__assistNext)}}}}})()");
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
  const calls = async () => JSON.parse(await ev("JSON.stringify(window.__assistCalls)"));
  const sheet = () => ev("(()=>{const o=" + F + ".getElementById('kitAsk');return o?o.innerText.replace(/\\s+/g,' '):''})()");
  const toast = () => ev("((" + F + ").getElementById('kitToast')||{}).innerText||''");
  await openApplied();
  check("the hand-off row says Finish on their site", /Finish on their site/.test(await row()), (await row()).slice(0, 160));

  // 1. Finish: the form is read first; its unanswerable questions come up in UAply's question box before the form opens
  check("Finish applying on their site is there", await finish());
  await sleep(1500);
  let c = await calls();
  check("the app is first asked to read the form (scan), with the employer's page", c.length === 1 && c[0].scan === true && /^https:\/\/job-boards\.greenhouse\.io\/exampleco\/jobs\/4001\?gh_src=uaply$/.test(c[0].url || ""), JSON.stringify(c.map((x) => [x.scan, x.url])));
  const s1 = await sheet();
  check("UAply's question box asks the form's questions before the form opens", /2 questions from Example Co/.test(s1) && /Describe a project you led/.test(s1) && /Cover letter \(optional\)/.test(s1) && /Continue to Example Co's form/.test(s1), s1.slice(0, 300));
  // the required one cannot be skipped
  await ev("(" + F + ").getElementById('kaYes').click()"); await sleep(300);
  check("a required question cannot be left blank", /Answer every question/.test(await ev("((" + F + ").getElementById('kaMsg')||{}).textContent||''")) && (await calls()).length === 1);
  await ev("(()=>{const t=(" + F + ").getElementById('kaQ0');t.value='A help center I rebuilt';t.dispatchEvent(new Event('input',{bubbles:true}));(" + F + ").getElementById('kaYes').click()})()");
  await sleep(1500);
  c = await calls();
  const p = (c[1] || {}).profile || {};
  check("then the form opens, filled with the answer (the optional one left blank)", c.length === 2 && !c[1].scan && p.answers && p.answers["Describe a project you led"] === "A help center I rebuilt" && !p.answers["Cover letter"], JSON.stringify(p.answers));
  check("the assist script itself is handed over", /window\.UAplyAssist/.test(c[1].engine || "") && /scan/.test(c[1].engine || ""));
  check("mode is assisted (the shipped switch)", c[1].mode === "assisted" && c[1].system === "greenhouse", c[1].mode + " " + c[1].system);
  check("the profile carries the person's details", p.name === "Sam Rivera" && p.first === "Sam" && p.email === "sam.rivera.test@example.com" && p.phone === "215-555-0142" && p.city === "Philadelphia" && p.auth === "yes" && p.sponsor === "no" && p.school === "Temple University" && p.heard === "UAply" && p.adult === "yes",
    JSON.stringify(Object.assign({}, p, { resume: undefined, answers: undefined })).slice(0, 300));
  check("the resume file goes with it", !!(p.resume && p.resume.b64 && /pdf/.test(p.resume.type)));
  const flat = JSON.stringify(Object.assign({}, p, { resume: null }));
  check("no voluntary answer and no pronouns in what the app gets", !/gender|race|ethnic|hispanic|veteran|disab|pronoun|they\/them/i.test(flat), flat.slice(0, 200));
  await sleep(300);
  let d = await dec();
  check("closed without a confirmation page: still not sent", d && d.sent && d.sent.status === "handoff", JSON.stringify(d && d.sent));
  check("the row still says Finish on their site", /Finish on their site/.test(await row()) && !/\bSent\b/.test(await row()), (await row()).slice(0, 200));
  check("the person is told it is not sent yet", /Not sent yet/.test(await toast()));

  // 2. "Not now" in the question box: nothing opens
  check("Finish applying again", await finish());
  await sleep(1200);
  const s2 = await sheet();
  check("an answered question is not asked again; the optional one still is", /One question from Example Co/.test(s2) && /Cover letter \(optional\)/.test(s2) && !/Describe a project/.test(s2), s2.slice(0, 200));
  await ev("(" + F + ").getElementById('kaNo').click()"); await sleep(800);
  check("Not now: the form does not open", (await calls()).length === 3 && (await dec()).sent.status === "handoff", (await calls()).length + " calls");

  // 3. again, and this time the employer's confirmation page appears after the person taps Submit
  await ev("window.__assistNext={confirmed:true,url:'https://job-boards.greenhouse.io/exampleco/jobs/4001/confirmation'}");
  check("Finish applying a third time", await finish());
  await sleep(1200);
  await ev("(" + F + ").getElementById('kaYes').click()");   // the optional question may be left blank
  await sleep(1500);
  d = await dec();
  check("the confirmation page makes it Sent", d && d.sent && d.sent.status === "sent" && d.sent.via === "assist", JSON.stringify(d && d.sent));
  const r2 = await row();
  check("the row says Sent, on the employer's own page", /\bSent\b/.test(r2) && /Sent on Example Co's own page/.test(r2), r2.slice(0, 220));
  check("Finish applying is gone from a sent row", !(await ev("!!" + F + ".querySelector('[data-finish=\"" + ID + "\"]')")));
  check("five calls in all (scan, form, scan, scan, form)", (await calls()).map((x) => x.scan ? "scan" : "form").join(",") === "scan,form,scan,scan,form", (await calls()).map((x) => x.scan ? "scan" : "form").join(","));

  // an answer written for one employer stays with it: a cover letter for Example Co is not put into Other Co's form; a plain answer is
  await ev("(()=>{const w=" + FW + ",k=(w.__uaplyKey||'uaply');const a=JSON.parse(w.localStorage.getItem(k+'.answers')||'{}'),m=JSON.parse(w.localStorage.getItem(k+'.answersAsked')||'{}');" +
    "a['Cover letter']='Dear Example Co team, I would love to join you.';m['Cover letter']={q:'Cover letter',kind:'textarea',co:'Example Co',at:Date.now()};" +
    "w.localStorage.setItem(k+'.answers',JSON.stringify(a));w.localStorage.setItem(k+'.answersAsked',JSON.stringify(m))})()");
  const own = JSON.parse(await ev("JSON.stringify(" + FW + ".__uaplyAssistProfile({co:'Example Co'}).answers)"));
  const other = JSON.parse(await ev("JSON.stringify(" + FW + ".__uaplyAssistProfile({co:'Other Co'}).answers)"));
  check("a cover letter written for one employer is not put into another's form", own["Cover letter"] && !other["Cover letter"], JSON.stringify(Object.keys(other)));
  check("a plain answer is used for every employer", own["Describe a project you led"] === "A help center I rebuilt" && other["Describe a project you led"] === "A help center I rebuilt");

  // 4. on the website (no app), the button still opens the employer's page as before
  await ev("(()=>{delete window.Capacitor;const w=" + FW + ",A=w.__uaply;A.S.decisions[" + ID + "].sent={at:Date.now(),to:'',status:'handoff'};A.save();A.renderAll();w.__opened=[];w.__uaplyOpen=function(u){w.__opened.push(u)}})()");
  await openApplied();
  await finish(); await sleep(600);
  const opened = JSON.parse(await ev("JSON.stringify(" + FW + ".__opened)"));
  check("on the website the button opens the employer's page", opened.length === 1 && /gh_src=uaply/.test(opened[0]), JSON.stringify(opened));
  console.log("\n" + (n - bad) + "/" + n + " passed");
  if (bad) process.exitCode = 1;
};
module.exports.limitMs = 180000;
