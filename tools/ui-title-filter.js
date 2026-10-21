// "Hide roles that do not match my target titles" (on by default) never leaves a new student with an empty deck, in a real browser.
// The October 21 walk as a Drexel junior: two marketing titles hid 109 of 115 internships and the Jobs menu read "Internships 0".
//   W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-title-filter.js       (a server with the job feeds on; also W=1280 H=800)
// Checks: Internships and Co-op are never filtered by title; a section where no listing matches the titles shows its roles anyway, with
// "Showing all roles: none matched your target titles" and a way to Filters; a section where some listings match is still filtered.
const PORT = process.env.PORT || "8766";
const TAG = "[" + (process.env.W || 1100) + "x" + (process.env.H || 900) + "] ";
module.exports = async ({ ev, sleep, nav, logs }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const W = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (n, ok, x) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + TAG + n + (x ? "  " + x : "")); };
  const J = async (expr) => JSON.parse(await ev("JSON.stringify((()=>{" + expr + "})())") || "null");
  await nav("http://127.0.0.1:" + PORT + "/");
  for (let i = 0; i < 60 && !(await ev("!!(" + W + ".__uaply&&" + W + ".__uaply.JOBS.some(j=>j.live&&j.type==='internship'))")); i++) await sleep(1000);
  await ev("(()=>{const b=" + F + ".getElementById('kcYes');if(b)b.click()})()"); await sleep(300);
  // the student's profile, as Profile setup saves it: two marketing titles, internship and part-time, on-site or hybrid in Philadelphia
  const setTitles = (t) => ev("(()=>{const w=" + W + ",A=w.__uaply;Object.assign(A.S.profile,{name:'Jordan Alvarez',email:'jordan.alvarez@example.edu',custom:true,title:" + JSON.stringify(t[0]) +
    ",loc:'Philadelphia',edu:'Bachelor',years:0,skills:['Excel','SQL','Tableau'],modes:{remote:false,hybrid:true,onsite:true}});A.S.profile.ext=Object.assign(A.S.profile.ext||{},{titles:" + JSON.stringify(t.slice(1)) +
    ",types:['internship','parttime']});A.save();A.renderAll();return true})()");
  await setTitles(["Marketing Intern", "Marketing Assistant"]); await sleep(600);
  const acct = await J("const w=" + W + ";return JSON.parse(w.localStorage.getItem(w.__uaplyKey+'.acct')||'{}').fTitleOnly");
  check("the target-title filter is on, as for every new profile", acct === true, String(acct));
  // how many listings of a kind show, and how many would with the title filter off (the same count = titles do not narrow it)
  const counts = (type) => J("const w=" + W + ",A=w.__uaply,AK=w.__uaplyKey+'.acct';const all=A.JOBS.filter(j=>j.live&&(j.type||'job')===" + JSON.stringify(type) + ");" +
    "const on=all.filter(j=>!w.__uaplyHide(j)).length;return {all:all.length,shown:on}");
  const pick = async (type) => { await ev("(()=>{const d=" + F + ";d.getElementById('nb-svc').click()})()"); await sleep(300);
    await ev("(()=>{const d=" + F + ";const b=[...d.querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')===" + JSON.stringify(type) + ");if(b)b.click()})()"); await sleep(900); };
  const note = () => ev("(()=>{const n=" + F + ".getElementById('titleNote');return n&&!n.hidden?n.innerText.replace(/\\s+/g,' ').trim():''})()");
  const cards = () => ev(F + ".querySelectorAll('#deck .card').length");

  // 1. Internships: titles never hide one
  await pick("internship");
  const ci = await counts("internship");
  // the same internships show whatever the titles say (marketing titles hid 109 of 115 before)
  await setTitles(["Zookeeper of rare lemurs"]); await sleep(300);
  const ci2 = await counts("internship");
  await setTitles(["Marketing Intern", "Marketing Assistant"]); await sleep(300);
  check("Internships: target titles hide none of them (the same listings show with any titles)", ci.all > 0 && ci.shown > 0 && ci.shown === ci2.shown, JSON.stringify({ marketing: ci, other: ci2 }));
  check("Internships: the deck has cards on first open (it was empty)", (await cards()) > 0, String(await cards()));
  check("Internships: no 'Showing all roles' note (nothing was set aside)", (await note()) === "", await note());
  const menuInt = await ev("(()=>{const e=[..." + F + ".querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='internship');return e?e.innerText.replace(/\\s+/g,' ').trim():''})()");
  check("the Jobs menu no longer reads 'Internships 0'", !/Internships\s*0\b/.test(menuInt), menuInt);
  await pick("coop");
  const cc = await counts("coop");
  await setTitles(["Zookeeper of rare lemurs"]); await sleep(300);
  const cc2 = await counts("coop");
  check("Co-op: target titles hide none of them either, and no note", cc.shown === cc2.shown && (await note()) === "", JSON.stringify({ marketing: cc, other: cc2 }));

  // 2. a section where no listing matches the titles: the roles show, with the one-line note and the way to Filters
  await setTitles(["Zookeeper of rare lemurs", "Lighthouse keeper"]); await sleep(400);
  await pick("job");
  const cj = await counts("job");
  check("Full-time with titles nothing matches: the roles show anyway", cj.shown > 0 && (await cards()) > 0, JSON.stringify(cj));
  const n1 = await note();
  check("...with 'Showing all roles: none matched your target titles' and Filters", /^Showing all roles: none matched your target titles\. Filters$/.test(n1), n1);
  await ev("(()=>{const b=" + F + ".getElementById('titleFilters');if(b)b.click()})()"); await sleep(700);
  const onFilters = await ev("(()=>{const d=" + F + ";const f=d.getElementById('fTitleOnly');return !!(f&&f.offsetParent)})()");
  check("...and Filters opens, with the target-title switch on it", onFilters === true);

  // 3. a section where some listings match: still filtered, no note
  const role = await ev("(()=>{const A=" + W + ".__uaply;const j=A.JOBS.find(j=>j.live&&(j.type||'job')==='job'&&/engineer/i.test(j.role));return j?j.role:''})()");
  await setTitles([role || "Software Engineer"]); await sleep(400);
  await pick("job");
  const cm = await counts("job");
  check("Full-time with a title that matches some: the others are still hidden", cm.shown > 0 && cm.shown < cj.shown, JSON.stringify({ title: role, shown: cm.shown, before: cj.shown }));
  check("...and there is no 'Showing all roles' note", (await note()) === "", await note());
  const wide = await J("const d=" + F + ";return d.documentElement.scrollWidth<=d.documentElement.clientWidth+1");
  check("nothing is wider than the screen", wide === true);
  check("no script errors", logs.length === 0, logs.join(" / ").slice(0, 300));
  console.log(bad ? bad + " problem(s)" : "All good");
};
