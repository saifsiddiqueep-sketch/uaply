// Fill from your resume, in a real browser at iPhone size: the box on Profile setup's Background and links step, a resume read by the
// server, empty fields filled, a field the person typed left alone with Replace offered, the line each answer came from, the file kept
// for applications, the plain error sentences, and nothing wider than the phone.
//   W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-resume.js        (a sandbox server: python serve.py 18766 sandbox --api)
// Set SHOT=some/folder to also save screenshots.
const fs = require("fs");
const path = require("path");
const PORT = process.env.PORT || "8766";
const STUDENT = fs.readFileSync(path.join(__dirname, "fixtures", "resumes", "student.txt"), "utf8");
module.exports = async ({ ev, sleep, nav, shot, logs }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const W = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (n, ok, x) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? "  " + x : "")); };
  const val = (id) => ev("(" + F + ".getElementById(" + JSON.stringify(id) + ")||{}).value");
  const snap = async (n) => { if (process.env.SHOT) { fs.mkdirSync(process.env.SHOT, { recursive: true }); await shot(path.join(process.env.SHOT, n + ".png")); } };
  // choose a file in the box the way a person does: the file goes into the input and its change event runs
  const choose = (name, text, type, size) => ev("(()=>{const w=" + W + ",d=w.document,i=d.getElementById('rsFile');const dt=new w.DataTransfer();" +
    "dt.items.add(new w.File([" + (size ? "new Uint8Array(" + size + ")" : JSON.stringify(text)) + "]," + JSON.stringify(name) + ",{type:" + JSON.stringify(type) + "}));i.files=dt.files;i.dispatchEvent(new w.Event('change',{bubbles:true}));return true})()");
  const waitMsg = async () => { for (let i = 0; i < 60; i++) { const busy = await ev("(" + F + ".getElementById('rsBox')||{}).getAttribute?.('aria-busy')"); if (busy !== "true") break; await sleep(200); } await sleep(200); };

  await nav("http://127.0.0.1:" + PORT + "/?app=1");
  await sleep(3500);
  await ev("(()=>{const b=" + F + ".getElementById('kcYes');if(b)b.click()})()"); await sleep(300);
  await ev("(()=>{" + W + ".__uaplyOpenProf('back')})()"); await sleep(800);
  const step = await ev("(()=>{const c=" + F + ".querySelector('.wzDots button[aria-current=step]');return c?c.getAttribute('aria-label'):''})()");
  check("Profile setup opens on Background and links", /Background and links/.test(step), step);
  const boxOn = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ",b=d.getElementById('rsBox');if(!b)return null;const r=b.getBoundingClientRect();return {shown:b.offsetParent!==null,w:r.width,right:r.right,vw:d.documentElement.clientWidth,title:b.querySelector('h4').textContent}})())"));
  check("the Fill from your resume box is on that step", boxOn && boxOn.shown && boxOn.title === "Fill from your resume", JSON.stringify(boxOn));
  check("the box fits the phone's width", boxOn && boxOn.right <= boxOn.vw + 1, JSON.stringify(boxOn));
  const tap = JSON.parse(await ev("JSON.stringify((()=>{const r=" + F + ".getElementById('rsChoose').getBoundingClientRect();return {h:r.height,w:r.width}})())"));
  check("Choose your resume is a full-size tap target (44px)", tap.h >= 44, JSON.stringify(tap));

  // the person already typed a school; the resume says another one
  await ev("(()=>{const w=" + W + ",e=w.document.getElementById('px-school');e.value='Drexel University';e.dispatchEvent(new w.Event('input',{bubbles:true}))})()");
  await choose("student.txt", STUDENT, "text/plain");
  await waitMsg();
  await snap("resume-filled");
  const head = await ev("(" + F + ".querySelector('#rsOut b')||{}).textContent||''");
  check("it says how many fields it filled and to check them", /^We filled \d+ fields from your resume\. Check them before you apply\.$/.test(head), head);
  const got = {};
  for (const id of ["pName", "pEmail", "px-phone", "px-linkedin", "px-portfolio", "px-major", "px-grad", "px-gpa", "px-employer", "pTitle", "pSkills", "pLoc", "adState", "adZip", "px-school"]) got[id] = await val(id);
  check("the example name is replaced (it was never typed)", got.pName === "Maya Patel", got.pName);
  check("empty fields are filled from the resume", got.pEmail === "maya.patel@example.edu" && got["px-phone"] === "(215) 555-0134" && got["px-linkedin"] === "https://www.linkedin.com/in/maya-patel-example" &&
    got["px-portfolio"] === "https://github.com/mayapatel-example" && got["px-major"] === "Computer Science" && got["px-grad"] === "2027-05" && got["px-gpa"] === "3.72" &&
    got["px-employer"] === "Brightline Labs" && got.pTitle === "Software Engineering Intern", JSON.stringify(got));
  check("skills, city, state and ZIP are filled", /Python/.test(got.pSkills) && /React/.test(got.pSkills) && got.pLoc === "Philadelphia" && got.adState === "PA" && got.adZip === "19104", JSON.stringify([got.pSkills, got.pLoc, got.adState, got.adZip]));
  check("the school the person typed is NOT changed", got["px-school"] === "Drexel University", got["px-school"]);
  const rows = JSON.parse(await ev("JSON.stringify([..." + F + ".querySelectorAll('#rsOut .rsList li')].map(li=>({k:li.querySelector('.k').textContent,src:!!li.querySelector('.src q'),btn:(li.querySelector('button')||{}).textContent||''})))"));
  check("every answer shows the line of the resume it came from", rows.length >= 12 && rows.every((r) => r.src), rows.length + " rows");
  const school = rows.find((r) => r.k === "School");
  check("the school row offers Replace", school && school.btn === "Replace", JSON.stringify(school));
  const outlined = await ev(F + ".querySelectorAll('.rsFilled').length");
  check("the filled fields are outlined so the person can find them", outlined >= 10, String(outlined));
  await ev("(()=>{const d=" + F + ";[...d.querySelectorAll('#rsOut .rsList li')].find(li=>li.querySelector('.k').textContent==='School').querySelector('button').click()})()"); await sleep(200);
  check("Replace puts the resume's school in", (await val("px-school")) === "Temple University", await val("px-school"));
  const kept = await ev("JSON.stringify((" + W + ".__uaplyResume&&" + W + ".__uaplyResume())||null)");
  check("the same file is kept as the resume sent with applications (the existing resume box)", /"name":"student.txt"/.test(kept), String(kept).slice(0, 80));
  const keepMsg = await ev(F + ".getElementById('rsKeep').textContent");
  check("...and it says so", /resume file sent with your applications/.test(keepMsg), keepMsg);
  const wide = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ",vw=d.documentElement.clientWidth;const over=[...d.querySelectorAll('#rsBox *')].filter(e=>e.offsetParent&&e.getBoundingClientRect().right>vw+1).map(e=>e.tagName+'.'+e.className);return {vw,sw:d.documentElement.scrollWidth,over:over.slice(0,5)}})())"));
  check("nothing in the list is wider than the phone (390px)", wide.sw <= wide.vw + 1 && wide.over.length === 0, JSON.stringify(wide));

  // saving the step keeps the answers
  await ev(F + ".getElementById('wzNext').click()"); await sleep(800);
  const saved = await ev("JSON.stringify((()=>{const w=" + W + ";const s=JSON.parse(w.localStorage.getItem(w.__uaplyKey));return {name:s.profile.name,school:(s.profile.ext||{}).school,grad:(s.profile.ext||{}).grad}})())");
  check("Save and continue saves what came from the resume", /"name":"Maya Patel"/.test(saved) && /Temple University/.test(saved) && /2027-05/.test(saved), saved);

  // a second read changes nothing the person now has, and says so
  await ev("(()=>{" + W + ".__uaplyOpenProf('back')})()"); await sleep(500);
  await choose("student.txt", STUDENT, "text/plain"); await waitMsg();
  const again = await ev("(" + F + ".querySelector('#rsOut b')||{}).textContent||''");
  check("reading the same resume again fills nothing new", /already (has answers|matches)/.test(again), again);

  // plain error sentences
  await choose("photo.png", "x", "image/png"); await sleep(200);
  check("a picture gets a plain sentence", /picture, not a document/.test(await ev(F + ".getElementById('rsMsg').textContent")));
  await choose("big.pdf", "", "application/pdf", 5 * 1024 * 1024 + 1); await sleep(300);
  check("a file over 5 MB gets a plain sentence", /over 5 MB/.test(await ev(F + ".getElementById('rsMsg').textContent")));
  await choose("broken.pdf", "this is not really a pdf, only text pretending", "application/pdf"); await waitMsg();
  const broken = await ev(F + ".getElementById('rsMsg').textContent");
  check("a file that is not really a PDF gets a plain sentence from the server", /could not read|not switched on|scanned/i.test(broken), broken);
  await snap("resume-error");
  check("no script errors", logs.length === 0, logs.join(" / ").slice(0, 300));
  console.log(bad ? bad + " problem(s)" : "All good");
};
