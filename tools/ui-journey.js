// The apply journey's fixes (October 22, 2026: 50 real swipes on the Galaxy A17 and a laptop), in a phone-sized Chrome with touch.
// Run through tools/ui-questions.py, which starts the stand-in Greenhouse and a UAply server (test mode, form previews on) with one ordinary
// feed posting on Greenhouse (FEED_ID). Each check failed on the code before the fix.
//   1. a card whose swipe will ask the form's questions says "N answers needed", not "Ready"
//   3. "When can you start?" from Profile, Account goes with the application when Profile setup's start date is empty
//   4. Finish applying opens the application form: Lever /apply, Ashby /application, SmartRecruiters ?oga=true (and the source tags)
//   5. a "Saved ... Undo" message whose time ran out while the tab was hidden goes when the tab is shown again
//   6. a job swiped right still has its Job Tracker row after the page is reloaded, even when the server's list does not have it
// (2, the question box on a phone's keyboard, is checked in tools/ui-questions.js at 390 px.)
const PORT = process.env.PORT, FEED = Number(process.env.FEED_ID);
module.exports = async ({ ev, sleep, nav, send }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  const base = "http://127.0.0.1:" + PORT + "/";
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + "[journey] " + name + (ok || extra === undefined ? "" : "  | " + extra)); };
  const inApp = (js) => ev("(()=>{try{const d=" + F + ",w=" + FW + ";" + js + "}catch(e){return 'ERR '+e.message}})()");
  const waitFor = async (js, ms) => { const end = Date.now() + (ms || 8000); let v; while (Date.now() < end) { v = await inApp(js); if (v && !String(v).startsWith("ERR")) return v; await sleep(250); } return v; };
  async function tapIn(sel) {
    const r = await inApp("const e=d.querySelector(" + JSON.stringify(sel) + ");if(!e)return null;e.scrollIntoView({block:'center'});const f=document.querySelector('iframe').getBoundingClientRect(),b=e.getBoundingClientRect();return JSON.stringify({x:f.left+b.left+b.width/2,y:f.top+b.top+b.height/2})");
    if (!r || String(r).startsWith("ERR")) return false;
    const p = JSON.parse(r);
    await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: p.x, y: p.y }] });
    await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await sleep(400);
    return true;
  }

  // ---- the person: ready to apply (name, email, phone), the agreement given, the notice "2 weeks" and no start date in Profile setup ----
  await nav(base); await sleep(3000);
  await inApp("w.localStorage.setItem((w.__uaplyKey||'uaply')+'.consent',JSON.stringify({v:3,at:Date.now(),agent:true}));" +
    "const ak=(w.__uaplyKey||'uaply')+'.acct',a=JSON.parse(w.localStorage.getItem(ak)||'{}');a.phone='(215) 555-0100';a.notice='2 weeks';w.localStorage.setItem(ak,JSON.stringify(a));" +
    "const A=w.__uaply;Object.assign(A.S.profile,{name:'Jo Tester',email:'jo.tester@example.com',custom:true,title:'Data Analyst',years:1,skills:['Python'],loc:'Philadelphia, PA'});A.S.tips=false;A.save();return 1");
  await nav(base); await sleep(4500);
  check("the app is ready to apply with this profile", (await waitFor("return w.__uaplyReadiness&&w.__uaplyReadiness().min?'yes':''", 8000)) === "yes");

  // ---- 1. readiness on the card: the same form plan the swipe uses ----
  await waitFor("return w.__uaplyFormPreview===true?'yes':''", 8000);
  const rd = await inApp("return w.__uaplyReadyOf(" + FEED + ").then(s=>JSON.stringify(s))");
  check("1. an ordinary Greenhouse posting whose form a swipe reads (form previews on): the card says 'N answers needed', not 'Ready'",
    /"k":"need"/.test(rd || "") && /answers? needed/.test(rd || ""), rd + " " + (await inApp("const A=w.__uaply,j=A.JOBS.find(j=>j.id===" + FEED + ");return JSON.stringify({inList:!!j,live:j&&j.live,instant:j&&j.instant,ats:j&&j.ats,submit:!!w.__uaplySubmitOn,mode:w.__uaplyMode,n:A.JOBS.length})")));
  const plan = await inApp("return fetch('/api/apply/config').then(r=>r.json()).then(c=>String(c.formPreview))");
  check("...and the server says form previews are on (GET /api/apply/config formPreview)", plan === "true", plan);

  // ---- 3. the notice as the start date ----
  const ext = JSON.parse(await inApp("return JSON.stringify(w.__uaplyApplyExt())") || "{}");
  check("3. 'When can you start?' (2 weeks) goes with the application when Profile setup's start date is empty", ext.notice === "2 weeks" && !ext.start, JSON.stringify({ notice: ext.notice, start: ext.start }));

  // ---- 4. Finish applying opens the form ----
  const U = "766dcff5-6f16-4b4e-a7e9-b757f2f4fba2";
  const urls = JSON.parse(await inApp("return JSON.stringify(" + JSON.stringify([
    "https://jobs.lever.co/acme/" + U, "https://jobs.lever.co/acme/" + U + "/?x=1#t", "https://jobs.lever.co/acme/" + U + "/apply",
    "https://jobs.ashbyhq.com/ibotta/" + U, "https://jobs.smartrecruiters.com/soprasteria1/744000145342400",
    "https://jobs.smartrecruiters.com/Equinox/744000156908409-personal-trainer?trid=a%20b", "https://job-boards.greenhouse.io/acme/jobs/1007",
    "https://jobs.ashbyhq.com/acme/1", "https://example.com/jobs/1"]) + ".map(w.__uaplyHandoffURL))"));
  const want = ["https://jobs.lever.co/acme/" + U + "/apply?lever-source=uaply", "https://jobs.lever.co/acme/" + U + "/apply?x=1&lever-source=uaply#t",
    "https://jobs.lever.co/acme/" + U + "/apply?lever-source=uaply", "https://jobs.ashbyhq.com/ibotta/" + U + "/application",
    "https://jobs.smartrecruiters.com/soprasteria1/744000145342400?oga=true", "https://jobs.smartrecruiters.com/Equinox/744000156908409-personal-trainer?trid=a%20b&oga=true",
    "https://job-boards.greenhouse.io/acme/jobs/1007?gh_src=uaply", "https://jobs.ashbyhq.com/acme/1", "https://example.com/jobs/1"];
  const wrong = want.map((x, i) => urls[i] === x ? "" : urls[i] + " (wanted " + x + ")").filter(Boolean);
  check("4. Finish applying opens the application form: Lever /apply, Ashby /application, SmartRecruiters ?oga=true; nothing else changed or re-encoded", !wrong.length, wrong.join(" | "));

  // ---- 5. an expired message goes when the tab is shown again ----
  const t5 = await inApp("const t=w.__uaplyKitToast('Saved Old Co to Applied','Undo',function(){},9000);t.el.setAttribute('data-until',String(Date.now()-1000));" +
    "d.dispatchEvent(new Event('visibilitychange'));return d.getElementById('kitToast')?'still there':'gone'");
  check("5. a 'Saved ... Undo' message whose time ran out while the tab was hidden goes as soon as the tab is shown", t5 === "gone", t5);
  const t5b = await inApp("w.__uaplyKitToast('Saved New Co to Applied','Undo',function(){},9000);d.dispatchEvent(new Event('visibilitychange'));const t=d.getElementById('kitToast');const ok=!!t;if(t)t.remove();return ok?'kept':'gone'");
  check("...while one still within its time stays", t5b === "kept", t5b);

  // ---- 6. the Job Tracker row after a reload, for a job the server does not list ----
  const JID = 970000202;
  await inApp("w.__uaplyJobs.add([{id:" + JID + ",co:'Reload Freight',role:'Data Analyst',loc:'Remote (US)',mode:'remote',sal:[0,0],yrs:0,edu:'High school',skills:['Python'],blurb:'A posting that left the feed.'," +
    "type:'job',jobType:'full-time',url:'https://jobs.lever.co/reloadfreight/" + U + "',source:'Reload Freight careers page',contact:'',apply:'link',live:true,seen:Date.now()}]);" +
    "w.__uaplyHideMore=function(j){return j.id!==" + JID + "};w.__uaply.renderAll();return 1");
  await sleep(600);
  const top = await waitFor("const c=d.querySelector('.card.top');return c&&+c.getAttribute('data-id')===" + JID + "?'yes':''", 6000);
  check("6. the job comes to the top of the deck", top === "yes", top + " " + (await inApp("const c=d.querySelector('.card.top');return JSON.stringify({top:c&&c.getAttribute('data-id'),cards:d.querySelectorAll('.card').length,inList:!!w.__uaply.JOBS.find(j=>j.id===" + JID + "),hide:(()=>{const j=w.__uaply.JOBS.find(j=>j.id===" + JID + ");return j?[w.__uaplyHide(j),w.__uaply.evaluate(j,w.__uaply.S.profile).pct,j.type,!!w.__uaply.S.decisions[j.id],w.__uaplyHide===undefined]:null})(),txt:(d.getElementById('deck')||{}).innerText})")));
  await tapIn("#btnYes");
  const dec = await waitFor("const x=w.__uaply.S.decisions[" + JID + "];return x&&x.s==='applied'?'yes':''", 10000);
  check("...a tap on Apply saves it to Applied", dec === "yes", dec);
  await sleep(1500);
  await nav(base); await sleep(4500);                        // the phone reloads the tab (it was put to sleep); the server never listed this job
  await inApp("d.getElementById('nb-dash').click();return 1"); await sleep(400);
  await inApp("const b=[...d.querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='applied');if(b)b.click();return 1"); await sleep(900);
  const row = await inApp("const r=d.querySelector('#pane-track [data-id=\"" + JID + "\"]')||d.querySelector('[data-finish=\"" + JID + "\"]');return r&&r.closest('.row')?'yes':'no'");
  check("...and after the page is reloaded its Job Tracker row is still there (the job was saved with the swipe)", row === "yes", row);

  console.log("\n" + pass + " / " + (pass + fail));
  if (fail) process.exitCode = 1;
};
