// The deck reads the job list a page at a time (October 23: 16,000 postings were a 14.8 MB answer and about 3 s before the first card).
//   W=390 H=844 PORT=<a sandbox with more than 400 jobs, sign-up test mode> node tools/cdp.js tools/ui-deck-pages.js     (and W=1280 H=800)
// At sign-in the app asks for the first page (?size=200&page=1) only; when the stack on screen is within 20 cards of its end, the next
// page comes through its "next" cursor in the background; a stack of its own (Internships) gets its own pages (?type=internship); no job
// is ever in the app twice; Job Tracker lists the swiped jobs; and a shared job that is on no early page still opens in front (?job=<id>).
module.exports = async ({ ev, sleep, nav, send, logs }) => {
  const PORT = process.env.PORT, W = Number(process.env.W || 390), base = "http://127.0.0.1:" + PORT;
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + "[pages " + W + "] " + name + (extra !== undefined && !ok ? "  | " + String(extra).slice(0, 300) : "")); };
  if (W >= 700) await send("Emulation.setDeviceMetricsOverride", { width: W, height: Number(process.env.H || 800), deviceScaleFactor: 1, mobile: false });
  const who = await require("./gate-signup.js")({ ev, sleep, nav }, base, "pages", { api: true });
  check("the test person signs up first", !!who.ok);
  const total = JSON.parse(await ev("fetch('/api/jobs?size=1&page=1').then(r=>r.json()).then(j=>JSON.stringify({total:j.total,next:j.next}))"));
  check("this server has more than 400 jobs (so paging means something)", total.total > 400, JSON.stringify(total));
  // the requests the app makes, read from the frame's resource timing
  const asked = () => ev("JSON.stringify([...document.querySelector('iframe').contentWindow.performance.getEntriesByType('resource'),...performance.getEntriesByType('resource')].map(e=>e.name).filter(u=>/\\/api\\/jobs/.test(u)).map(u=>u.replace(/^https?:\\/\\/[^/]+/,'')))").then(JSON.parse);
  const live = () => ev("(()=>{const A=" + FW + ".__uaply;const ids=A.JOBS.filter(j=>j.live&&!j.stub).map(j=>j.id);return JSON.stringify({n:ids.length,dup:ids.length-new Set(ids).size})})()").then(JSON.parse);
  await send("Page.navigate", { url: base + "/" });
  for (let i = 0; i < 80 && !(await ev("!!(" + F + "&&" + F + ".querySelector('#deck .card.top'))").catch(() => false)); i++) await sleep(250);
  await sleep(1200);
  await ev("(()=>{const b=" + F + ".getElementById('kcYes');if(b)b.click()})()");
  let a = await asked(), L = await live();
  check("at sign-in the app asks for the first page only (?size=200&page=1), never the whole list", a.some((u) => /[?&]size=200&page=1$/.test(u)) && !a.some((u) => u === "/api/jobs"), JSON.stringify(a));
  check("...and holds about one page of jobs (" + L.n + "), none twice", L.n > 0 && L.n <= 260 && L.dup === 0, JSON.stringify(L));
  // within 20 cards of the end: every job of the stack on screen but 15 is passed (as swipes would), then the deck is drawn again
  const left = (k) => ev("(()=>{const w=" + FW + ",A=w.__uaply,t=A.getType();const mine=A.JOBS.filter(j=>j.live&&!j.stub&&(j.type||'job')===t&&!A.S.decisions[j.id]);" +
    "mine.slice(" + k + ").forEach(j=>{A.S.decisions[j.id]={s:'passed',at:Date.now(),pct:50}});A.save();A.renderAll();return mine.length})()");
  const before = L.n;
  await left(15);
  let grew = false;
  for (let i = 0; i < 40 && !grew; i++) { await sleep(250); L = await live(); grew = L.n > before; }
  a = await asked();
  check("15 cards from the end, more of the stack comes in the background (" + before + " -> " + L.n + " jobs; its own page, ?type=)", grew && a.length > 1 && a.slice(1).every((u) => /[?&]size=200&type=\w+&(page=1|cursor=)/.test(u)), JSON.stringify(a.slice(-4)));
  // and near the end again: that stack's next page through its "next" cursor
  const before2 = L.n; await left(15); grew = false;
  for (let i = 0; i < 40 && !grew; i++) { await sleep(250); L = await live(); grew = L.n > before2; }
  a = await asked();
  check("near the end again, the next page through its cursor (" + before2 + " -> " + L.n + " jobs)", grew && a.some((u) => /cursor=/.test(u)), JSON.stringify(a.slice(-3)));
  check("...and still no job twice", L.dup === 0, JSON.stringify(L));
  check("the deck never ran dry meanwhile (a card on top)", !!(await ev("!!" + F + ".querySelector('#deck .card.top')")));
  // a stack of its own: Internships asks for its own first page
  await ev("(()=>{const A=" + FW + ".__uaply;if(A.setType)A.setType('internship')})()"); await sleep(500);
  await left(5); await sleep(2500);
  a = await asked();
  check("switching to the Internships stack asks for its own pages (?type=internship)", a.some((u) => /type=internship/.test(u)), JSON.stringify(a.slice(-4)));
  L = await live();
  check("...still no job twice", L.dup === 0, JSON.stringify(L));
  await ev("(()=>{const A=" + FW + ".__uaply;if(A.setType)A.setType('job')})()"); await sleep(500);
  // Job Tracker lists the passed jobs (their rows come from the jobs the pages brought)
  await ev("(()=>{const b=" + F + ".getElementById('nb-dash');if(b)b.click()})()"); await sleep(400);
  await ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Applied'));if(e)e.click()})()"); await sleep(900);
  const rows = await ev("(" + F + ").querySelectorAll('#pane-track .row').length");
  check("Job Tracker lists the passed jobs (" + rows + " rows)", rows >= 10, rows);
  // a shared job that is on no early page: the friend's link still puts it in front
  const far = JSON.parse(await ev("fetch('/api/jobs?size=1&page=" + Math.max(2, total.total - 3) + "').then(r=>r.json()).then(j=>JSON.stringify(j.jobs[0]||null))"));
  if (far && (await ev("!!" + FW + ".__uaplySharePin"))) {
    await send("Page.navigate", { url: base + "/?job=" + far.id + "&t=" + encodeURIComponent(far.role) + "&c=" + encodeURIComponent(far.co) });
    let top = "";
    for (let i = 0; i < 60; i++) { await sleep(250); top = await ev("(()=>{try{const c=" + F + ".querySelector('#deck .card.top');return c?c.getAttribute('data-id'):''}catch(e){return ''}})()"); if (top === String(far.id)) break; }
    check("a shared job near the end of the list (not on the first page) opens in front from its link (GET /api/jobs/<id>)", top === String(far.id), top + " vs " + far.id);
  } else console.log("  (Share this job is not on this build, or no far job: the shared-job check is for the sandbox)");
  const errs = logs.filter((l) => !/favicon|ERR_FILE_NOT_FOUND|401|403/.test(l));
  check("no script errors", errs.length === 0, errs.join(" | "));
  console.log("\n" + (n - bad) + " / " + n);
  if (bad) throw new Error(bad + " paging check(s) failed");
};
