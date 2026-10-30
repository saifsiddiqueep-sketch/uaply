// The resume sentence the person reads against what a swipe right really sends, in a real browser: the upload box under Profile setup,
// Background and links, and the desktop preview ("What employers see") name the file that the application then carries, byte for byte;
// the message after the swipe repeats where the server says it went; a hand-off says the file was not sent; with no file or only a link
// the words and the request agree again; and at phone size (where the preview is hidden) the upload box says the same thing.
// Every step waits for what it needs (the app ready to send, the request and its answer, the message) up to a time limit, never a fixed
// pause, so a cold server or a slow computer gives the same result; a wait that runs out fails with "timed out waiting for ...".
//   PORT=19402 node tools/cdp.js tools/ui-resume-disclosure.js        (a sandbox server in test mode: py -3 serve.py 19402 sandbox --api)
const PORT = process.env.PORT || "19402";
module.exports = async ({ ev, sleep, nav, send }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0, all = 0;
  const check = (n, ok, x) => { all++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? "  | " + x : "")); };
  // poll `expr` (run inside the app's frame as w, d) until it is true; on time out, one counted FAIL that names what never came
  const until = async (what, expr, ms = 20000) => {
    const js = "(()=>{try{const w=" + FW + ",d=w.document;return !!(" + expr + ")}catch(e){return false}})()";
    const t0 = Date.now();
    while (Date.now() - t0 < ms) { if ((await ev(js)) === true) return true; await sleep(150); }
    check("timed out waiting for " + what + " (" + Math.round(ms / 1000) + " s)", false);
    return false;
  };
  const text = (id) => ev("(()=>{const e=" + F + ".getElementById(" + JSON.stringify(id) + ");return e?e.textContent.replace(/\\s+/g,' ').trim():''})()");
  const toast = () => ev("(()=>{const t=" + F + ".getElementById('kitToast');return t?t.innerText.replace(/\\s+/g,' ').trim():''})()");
  const NEVER = /(never|not) (sent|shared)[^.]*resume file|resume file[^.]*(never|not) (sent|shared)|resume file \(it stays on this device/i;
  const base = "http://127.0.0.1:" + PORT + "/";
  // the app is up and a swipe right will apply: the deck, the decision hook, and the server's answer to /api/apply/config (the mode)
  const READY = "w.__uaply&&w.__uaply.S&&w.__uaply.JOBS&&w.__uaply.JOBS.length&&w.__uaplyOnDecision&&w.__uaplySubmitOn&&w.__uaplyMode&&w.__uaplyOpenProf&&d.getElementById('pResFile')";

  await nav(base); await until("the app to load", READY, 30000);
  // a filled-in profile (a new email each run, so a server kept running between runs never answers "duplicate") and the first-application
  // agreement already given (as tools/ui-apply-paths.js does)
  await ev("(()=>{const w=" + FW + ";w.localStorage.setItem((w.__uaplyKey||'uaply')+'.consent',JSON.stringify({v:2,at:Date.now()}));const A=w.__uaply;Object.assign(A.S.profile,{name:'Sam Rivera',email:'sam.ui.'+Date.now()+'@example.com',custom:true,title:'Data Analyst',years:1,skills:['Python','SQL']});A.save()})()");
  await nav(base); await until("the app to load again, ready to send", READY + "&&w.__uaply.S.profile.name==='Sam Rivera'", 30000);
  // every /api/apply request and answer, exactly as the app sends and receives them
  await ev("(()=>{const w=" + FW + ";w.__sent=[];w.__got=[];const of=w.fetch;w.fetch=function(u,o){const cap=String(u).indexOf('/api/apply')>-1&&o&&o.method==='POST'&&String(u).indexOf('/config')<0;" +
    "if(cap)w.__sent.push(JSON.parse(o.body));return of.apply(this,arguments).then(function(r){if(cap)r.clone().json().then(function(j){w.__got.push(j)},function(){w.__got.push(null)});return r})};return true})()");
  check("app loaded in test mode", await ev("!!(" + FW + ".__uaply&&" + FW + ".__uaplyOnDecision)&&" + FW + ".__uaplyMode==='test'"), await ev(FW + ".__uaplyMode"));

  // choose a PDF in the resume box the way a person does
  await ev("(()=>{" + FW + ".__uaplyOpenProf('back')})()");
  await until("Profile setup to open on Background and links", "d.getElementById('pResFile').offsetParent!==null");
  const PDF = "%PDF-1.4 Sam Rivera resume for the disclosure test %%EOF";
  const choose = () => ev("(()=>{const w=" + FW + ",i=w.document.getElementById('pResFile');const dt=new w.DataTransfer();dt.items.add(new w.File([" + JSON.stringify(PDF) + "],'Sam Rivera Resume.pdf',{type:'application/pdf'}));i.files=dt.files;i.dispatchEvent(new w.Event('change',{bubbles:true}));return true})()");
  await choose();
  await until("the upload box and the preview to name the file", "/Sam Rivera Resume\\.pdf/.test(d.getElementById('resShare').textContent)&&/Sam Rivera Resume\\.pdf/.test((d.getElementById('wzPrevNote')||{}).textContent||'')");
  const box = await text("resShare"), note = await text("wzPrevNote");
  const prevShown = await ev("(()=>{const p=" + F + ".getElementById('wzPrev');return !!p&&p.offsetParent!==null})()");
  const rowFile = await ev("(()=>{const li=[...(" + F + ").querySelectorAll('#wzPrev li')].find(l=>l.firstChild.textContent==='Resume file');return li?li.lastChild.textContent:''})()");
  console.log("   upload box: " + box); console.log("   preview: " + note);
  check("the preview is shown at desktop width", prevShown === true);
  check("the upload box names the file and says it goes with each application UAply sends", /Sam Rivera Resume\.pdf/.test(box) && /goes with each application UAply sends/.test(box), box);
  check("the preview says the same, in the same words", note.indexOf(box) > -1, note);
  check("the preview lists the file as attached, as the server's email does", rowFile === "Sam Rivera Resume.pdf (attached)", rowFile);
  check("both say a hand-off sends the employer nothing", /only on its own site, UAply sends it nothing/.test(box) && /only on its own site, UAply sends it nothing/.test(note));
  check("neither says the resume file is never sent", !NEVER.test(box) && !NEVER.test(note), (box + " " + note).match(NEVER) || "");
  check("street address and voluntary answers are still never sent", /Never sent: your street address and your voluntary answers\./.test(note), note);

  // swipe right on an example listing (test mode: the simulated recruiter inbox), then wait for the request, its answer and the message
  const swipe = (expr) => ev("(()=>{const w=" + FW + ",A=w.__uaply,job=" + expr + ";if(!job)return 'no job';const m=A.evaluate(job,A.S.profile);" +
    "A.S.decisions[job.id]={s:'applied',at:Date.now(),pct:m.pct,as:A.S.profile.name,title:A.S.profile.title};A.S.history.push(job.id);A.save();A.renderAll();" +
    "const t=w.document.getElementById('kitToast');if(t)t.remove();" +           // the last message goes, so the wait below sees this swipe's
    "w.__uaplyOnDecision('applied',job,m,A.S.profile,function(){},A.S,A.save);return job.co})()");
  const swipeAndWait = async (expr, what) => {
    const n = await ev(FW + ".__got.length");
    const co = await swipe(expr);
    const ok = await until("the answer to the swipe on " + what, "w.__got.length>" + n) &&
      await until("the message after the swipe on " + what, "(d.getElementById('kitToast')||{}).textContent&&d.getElementById('kitToast').textContent.indexOf(" + JSON.stringify(co) + ")>-1");
    return { co, ok };
  };
  const last = async (k) => JSON.parse(await ev("JSON.stringify(" + FW + "." + k + ".slice(-1)[0]||null)"));
  const pick = (k) => "A.JOBS.filter(j=>!j.live&&j.id<1000&&!A.S.decisions[j.id])[" + k + "]";
  const s1 = await swipeAndWait(pick(0), "an example listing");
  const sent1 = await last("__sent"), got1 = await last("__got");
  const bytes1 = sent1 && sent1.resume ? await ev("atob(" + JSON.stringify(sent1.resume.data.split(",")[1]) + ")") : "";
  check("the request carries the very file the preview named, byte for byte", !!sent1 && sent1.resume && sent1.resume.name === "Sam Rivera Resume.pdf" && bytes1 === PDF, sent1 && sent1.resume && sent1.resume.name);
  check("the server says the file went with the (simulated) email", got1 && got1.status === "delivered_test" && got1.resume && JSON.stringify(got1.resume.sent_with) === '["email (simulated)"]', JSON.stringify(got1 && got1.resume));
  const t1 = await toast();
  check("the message after the swipe repeats where the file went", /Applied to .* \(test\)\./.test(t1) && /Your resume file \(Sam Rivera Resume\.pdf\) is in the test application\./.test(t1), s1.co + " | " + t1);
  const ob = JSON.parse(await ev("fetch('/api/outbox').then(r=>r.text())"));
  const lastApp = (ob.applications || [])[0] || {};          // newest first
  check("the test inbox record names the same file", lastApp.resume && lastApp.resume.name === "Sam Rivera Resume.pdf", JSON.stringify(lastApp.resume || null));

  // a posting whose employer takes applications only on its own site: a hand-off, and the message says the file was not sent
  await ev(FW + ".__uaplyJobs.add([{id:4242426,live:true,co:'Own Site Co',role:'Data Intern',loc:'Philadelphia, PA',mode:'onsite',type:'internship',sal:[0,0],yrs:0,edu:'High school',skills:['Python'],blurb:'Apply on our site.',url:'https://boards.greenhouse.io/ownsite/jobs/9',source:\"Own Site Co's careers page\"}])");
  await until("the added posting to be in the deck", "w.__uaply.JOBS.some(j=>j.id===4242426)");
  await swipeAndWait("A.JOBS.find(j=>j.id===4242426)", "Own Site Co");
  const got2 = await last("__got"), t2 = await toast();
  check("hand-off: the server says nothing carried the file", got2 && got2.status === "handoff" && got2.resume && got2.resume.handoff === true, JSON.stringify(got2 && got2.resume));
  check("hand-off: the message says UAply did not send the file and where to upload it", /UAply did not send your resume file \(Sam Rivera Resume\.pdf\): upload it on Own Site Co's form\./.test(t2), t2);

  // remove the file, add only a link: the words and the next request agree again
  await ev("(()=>{" + FW + ".__uaplyOpenProf('back')})()");
  await until("the Remove button for the resume file", "d.getElementById('resRm')");
  await ev("(()=>{const b=" + F + ".getElementById('resRm');if(b)b.click();return !!b})()");
  await until("the upload box to say no file is added", "/^\\s*No resume file or link is added yet\\./.test(d.getElementById('resShare').textContent)");
  const none = await text("resShare");
  check("no file and no link: the upload box says nothing is added", /^No resume file or link is added yet\./.test(none), none);
  // a link the box refuses (not https) is not saved, so the swipe sends none: the preview and the box must not show or mention it
  await ev("(()=>{const w=" + FW + ",u=w.document.getElementById('pResUrl');u.value='http://insecure.example/sam-resume';u.dispatchEvent(new w.Event('change',{bubbles:true}));return true})()");
  await until("the box to refuse the http link", "/full https:\\/\\/ link/.test(d.getElementById('resMsg').textContent)");
  const badMsg = await text("resMsg"), badBox = await text("resShare"), badNote = await text("wzPrevNote");
  const rowLink = await ev("(()=>{const li=[...(" + F + ").querySelectorAll('#wzPrev li')].find(l=>l.firstChild.textContent==='Resume link');return li?li.lastChild.textContent:''})()");
  check("a refused http link: the box says why, and neither the box nor the preview says employers get a link", /full https:\/\/ link/.test(badMsg) && /^No resume file or link is added yet\./.test(badBox) && !/resume link instead/.test(badNote), badMsg + " | " + badBox);
  check("a refused http link: the preview shows no resume link", rowLink === "Not added yet", rowLink);
  await ev("(()=>{const w=" + FW + ",u=w.document.getElementById('pResUrl');u.value='https://drive.example.com/sam-resume';u.dispatchEvent(new w.Event('change',{bubbles:true}));return true})()");
  await until("the upload box and the preview to take the link", "/resume link instead/.test(d.getElementById('resShare').textContent)&&/resume link instead/.test((d.getElementById('wzPrevNote')||{}).textContent||'')");
  const linkBox = await text("resShare"), linkNote = await text("wzPrevNote");
  const rowFile2 = await ev("(()=>{const li=[...(" + F + ").querySelectorAll('#wzPrev li')].find(l=>l.firstChild.textContent==='Resume file');return li?li.lastChild.textContent:''})()");
  // the link goes with an email, and into a hiring system only where its form has a place for it (Greenhouse and Ashby forms may have none)
  check("only a link: the upload box and the preview say where the link goes, and promise it to no form that has no place for it",
    /UAply sends your resume link instead with an emailed application, and to an employer's hiring system when its form has a place for it/.test(linkBox) &&
    !/employers get your resume link/.test(linkBox) && linkNote.indexOf(linkBox) > -1, linkBox);
  check("only a link: the preview shows no file attached", rowFile2 === "Not added yet", rowFile2);
  await swipeAndWait(pick(0), "a second example listing");
  const sent3 = await last("__sent"), got3 = await last("__got");
  check("only a link: the request carries no file and the link", !!sent3 && sent3.resume === null && sent3.profile.ext.resume === "https://drive.example.com/sam-resume", JSON.stringify(sent3 && [sent3.resume, sent3.profile.ext.resume]));
  check("only a link: the answer has no file summary, says the link went with the (simulated) email, and the message names no file",
    got3 && !got3.resume && got3.resume_link && JSON.stringify(got3.resume_link.link_with) === '["email (simulated)"]' && !/resume (file|link)/i.test(await toast()),
    JSON.stringify(got3 && [got3.status, got3.resume_link]));

  // at phone size the preview is hidden, so the upload box alone must say it
  await choose();
  await until("the upload box to name the file again", "/Sam Rivera Resume\\.pdf/.test(d.getElementById('resShare').textContent)");
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 3, mobile: true });
  await until("the phone layout (the preview hidden)", "(()=>{const p=d.getElementById('wzPrev');return !p||p.offsetParent===null})()");
  const phone = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ",s=d.getElementById('resShare'),p=d.getElementById('wzPrev'),r=s.getBoundingClientRect();return {shown:s.offsetParent!==null,prev:!!p&&p.offsetParent!==null,right:r.right,vw:d.documentElement.clientWidth,t:s.textContent}})())"));
  check("phone: the preview is hidden and the upload box shows the sentence, inside the screen", phone.shown && !phone.prev && phone.right <= phone.vw + 1, JSON.stringify({ shown: phone.shown, prev: phone.prev, right: phone.right, vw: phone.vw }));
  check("phone: the upload box says the same as on a computer", phone.t === box, phone.t);
  await send("Emulation.clearDeviceMetricsOverride");
  console.log((all - bad) + " / " + all);
};
