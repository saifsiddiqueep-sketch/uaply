// The deck and the job list (October 23): the first page for the first card, then the whole list ranked in the background.
//   W=390 H=844 PORT=<a server with more than 400 jobs, sign-up test mode> node tools/cdp.js tools/ui-deck-pages.js     (and W=1280 H=800)
// At sign-in the app asks for the first page (?size=200&page=1) and draws the first card from it; then the whole list comes and the deck
// is ranked over all of it, the card on top held where it was; a nurse or barista sees a matching card within the first 10 once it is
// ranked (the server's first page can hold none: its order is its sources' order), and no "none matched your target titles" note
// meanwhile. The start-up questions (/api/auth/me, /api/auth/providers, /api/apply/config) are asked once each. If the whole list cannot
// come, the deck carries on a page at a time: near the end of a stack its next page (?type=, its cursor), each stack its own, no job twice.
// Job Tracker lists the swiped jobs, and a shared job that is on no early page still opens in front (?job=<id>, the sandbox).
module.exports = async ({ ev, sleep, nav, send, on, logs }) => {
  const PORT = process.env.PORT, W = Number(process.env.W || 390), base = "http://127.0.0.1:" + PORT;
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + "[pages " + W + "] " + name + (extra !== undefined && !ok ? "  | " + String(extra).slice(0, 300) : "")); };
  if (W >= 700) await send("Emulation.setDeviceMetricsOverride", { width: W, height: Number(process.env.H || 800), deviceScaleFactor: 1, mobile: false });
  const who = await require("./gate-signup.js")({ ev, sleep, nav }, base, "pages", { api: true });
  check("the test person signs up first", !!who.ok);
  const total = JSON.parse(await ev("fetch('/api/jobs?size=1&page=1').then(r=>r.json()).then(j=>JSON.stringify({total:j.total,next:j.next}))"));
  check("this server has more than 400 jobs (so paging means something)", total.total > 400, JSON.stringify(total));
  // the requests the app makes, read from the frame's and the page's resource timing (each with its start time)
  const asked = () => ev("JSON.stringify([...document.querySelector('iframe').contentWindow.performance.getEntriesByType('resource'),...performance.getEntriesByType('resource')].filter(e=>/\\/api\\//.test(e.name)).map(e=>[e.name.replace(/^https?:\\/\\/[^/]+/,''),Math.round(e.startTime)]))").then(JSON.parse);
  const live = () => ev("(()=>{const A=" + FW + ".__uaply;const ids=A.JOBS.filter(j=>j.live&&!j.stub).map(j=>j.id);return JSON.stringify({n:ids.length,dup:ids.length-new Set(ids).size})})()").then(JSON.parse);
  const top = () => ev("(()=>{try{const c=" + F + ".querySelector('#deck .card.top');return c?JSON.stringify({id:+c.getAttribute('data-id'),role:(c.querySelector('h2')||{}).textContent||''}):'null'}catch(e){return 'null'}})()").then(JSON.parse);
  const firstCard = async () => { for (let i = 0; i < 120; i++) { const t = await top().catch(() => null); if (t && t.id >= 100000) return t; await sleep(50); } return null; };
  const passTop = () => ev("(()=>{const b=" + F + ".getElementById('btnNo');if(b)b.click()})()");
  const note = () => ev("(()=>{const n=" + F + ".getElementById('titleNote');return !!n&&n.getClientRects().length>0})()");

  // the target titles to look for: a nurse and a barista when this server lists them (the seeded 16,000-job server puts 1,000 tech
  // postings first), else the title of a job far down the list that the first page has none of (a real feed's own mix)
  const T = JSON.parse(await ev("Promise.all([fetch('/api/jobs?size=200&page=1').then(r=>r.json()),fetch('/api/jobs').then(r=>r.json())]).then(([p,a])=>{" +
    "const first=p.jobs.map(j=>j.role.toLowerCase()).join(' | '),all=a.jobs;const out=[];" +
    "for(const [t,w] of [['Registered Nurse','nurse'],['Barista','barista']])if(all.some(j=>j.role.toLowerCase().includes(w)))out.push({title:t,word:w,inFirst:first.includes(w)});" +
    "if(!out.length){const far=all.slice(400).find(j=>{const w=(j.role.toLowerCase().match(/[a-z]{5,}/g)||[]).find(x=>!first.includes(x));return !!w});" +
    "if(far){const w=(far.role.toLowerCase().match(/[a-z]{5,}/g)||[]).find(x=>!first.includes(x));out.push({title:far.role,word:w,inFirst:false})}}return JSON.stringify(out)})"));
  console.log("  target titles to look for: " + JSON.stringify(T));
  check("(there is a target title to look for: a nurse, a barista, or a far job's title)", T.length > 0, JSON.stringify(T));
  const T1 = T[0] || { title: "Registered Nurse", word: "nurse" }, rx1 = new RegExp(T1.word, "i");
  // ---- 1. a person with that target title: the first card from page 1, then the whole list ranked, the top card held ----
  await send("Page.navigate", { url: base + "/" });
  for (let i = 0; i < 80 && !(await ev("!!(" + F + "&&" + FW + ".__uaply&&" + F + ".getElementById('bnav'))").catch(() => false)); i++) await sleep(250);
  await ev("(()=>{const b=" + F + ".getElementById('kcYes');if(b)b.click()})()"); await sleep(300);
  await ev("(()=>{const A=" + FW + ".__uaply;Object.assign(A.S.profile,{name:'Nia Nurse',title:" + JSON.stringify(T1.title) + ",custom:true,skills:['Patient care','Customer service'],years:2,salary:0,modes:{remote:true,hybrid:true,onsite:true}});A.save();" +
    "Object.keys(localStorage).filter(k=>/.live$|jobs|cache/i.test(k)).forEach(k=>localStorage.removeItem(k));return 1})()");
  await send("Page.navigate", { url: base + "/" });
  const t1 = await firstCard(), L1 = await live(), note1 = await note();
  for (let i = 0; i < 120 && (await live()).n < Math.min(total.total, 1000); i++) await sleep(250);
  await sleep(600);
  const t2 = await top(), L2 = await live(), A2 = await asked(), note2 = await note();
  const list = A2.filter((x) => /^\/api\/jobs($|\?)/.test(x[0]));
  check("the first card comes from the first page alone (" + (L1 && L1.n) + " jobs in the app when it was drawn)", !!t1 && L1.n <= 260, JSON.stringify({ t1, L1 }));
  check("the first request for the list is ?size=200&page=1, and the whole list comes after it, in the background", list.length >= 2 && /[?&]size=200&page=1$/.test(list[0][0]) && list.some((x) => x[0] === "/api/jobs" && x[1] >= list[0][1]), JSON.stringify(list));
  check("...then the deck holds the whole list (" + L2.n + " jobs), none twice", L2.n >= Math.min(total.total, 1000) && L2.dup === 0, JSON.stringify(L2));
  check("the card on top stays where it was while the whole list is ranked (nothing moves under the thumb)", !!t1 && !!t2 && t1.id === t2.id, JSON.stringify({ t1, t2 }));
  check("no \"none matched your target titles\" note before the whole list is ranked, nor after it (it has " + T1.word + " jobs)", !note1 && !note2, JSON.stringify({ note1, note2 }));
  const roles = [];
  await passTop(); await sleep(700);
  for (let i = 0; i < 10; i++) { const t = await top(); if (!t) break; roles.push(t.role); if (rx1.test(t.role)) break; await passTop(); await sleep(500); }
  check("once ranked, a person after " + JSON.stringify(T1.title) + " sees a matching card within the first 10 (" + roles.length + " looked at; the first page had " + (T1.inFirst ? "some" : "none") + ")", roles.some((r) => rx1.test(r)), JSON.stringify(roles));
  const once = (p) => A2.filter((x) => x[0] === p).length;
  check("the start-up questions are asked once each: /api/auth/me, /api/auth/providers, /api/apply/config", once("/api/auth/me") === 1 && once("/api/auth/providers") <= 1 && once("/api/apply/config") <= 1,
    JSON.stringify({ me: once("/api/auth/me"), providers: once("/api/auth/providers"), config: once("/api/apply/config") }));

  // ---- 2. a second target title (a barista), the same ----
  if (T[1]) {
    const rx2 = new RegExp(T[1].word, "i");
    await ev("(()=>{const A=" + FW + ".__uaply;A.S.profile.title=" + JSON.stringify(T[1].title) + ";A.S.decisions={};A.save();A.renderAll();return 1})()"); await sleep(800);
    const r2 = [];
    for (let i = 0; i < 10; i++) { const t = await top(); if (!t) break; r2.push(t.role); if (rx2.test(t.role)) break; await passTop(); await sleep(500); }
    check("a person after " + JSON.stringify(T[1].title) + " sees a matching card within the first 10 of the ranked deck", r2.some((r) => rx2.test(r)), JSON.stringify(r2));
  } else console.log("  (one target title on this server: the second-title check needs both a nurse and a barista posting)");

  // ---- 3. the whole list refused (a slow link, an error): the deck carries on a page at a time ----
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/jobs", requestStage: "Request" }] });
  const stop = on("Fetch.requestPaused", (p) => /\/api\/jobs$/.test(p.request.url) ? send("Fetch.failRequest", { requestId: p.requestId, errorReason: "Failed" }) : send("Fetch.continueRequest", { requestId: p.requestId }));
  await ev("(()=>{const A=" + FW + ".__uaply;A.S.profile.title='';A.S.profile.custom=false;A.S.decisions={};A.save();Object.keys(localStorage).filter(k=>/.live$|jobs|cache/i.test(k)).forEach(k=>localStorage.removeItem(k));return 1})()");
  await send("Page.navigate", { url: base + "/" });
  await firstCard(); await sleep(1500);
  let L = await live();
  check("the whole list refused: the deck still has its first page (" + L.n + " jobs), none twice", L.n > 0 && L.n <= 260 && L.dup === 0, JSON.stringify(L));
  const left = (k) => ev("(()=>{const w=" + FW + ",A=w.__uaply,t=A.getType();const mine=A.JOBS.filter(j=>j.live&&!j.stub&&(j.type||'job')===t&&!A.S.decisions[j.id]);" +
    "mine.slice(" + k + ").forEach(j=>{A.S.decisions[j.id]={s:'passed',at:Date.now(),pct:50}});A.save();A.renderAll();return mine.length})()");
  const before = L.n;
  await left(15);
  let grew = false;
  for (let i = 0; i < 40 && !grew; i++) { await sleep(250); L = await live(); grew = L.n > before; }
  let a = (await asked()).map((x) => x[0]).filter((u) => /^\/api\/jobs\?/.test(u));
  check("15 cards from the end, more of the stack comes in the background (" + before + " -> " + L.n + " jobs; its own page, ?type=)", grew && a.slice(1).some((u) => /[?&]size=200&type=\w+&(page=1|cursor=)/.test(u)), JSON.stringify(a.slice(-4)));
  const before2 = L.n; await left(15); grew = false;
  for (let i = 0; i < 40 && !grew; i++) { await sleep(250); L = await live(); grew = L.n > before2; }
  a = (await asked()).map((x) => x[0]).filter((u) => /^\/api\/jobs\?/.test(u));
  check("near the end again, the next page through its cursor (" + before2 + " -> " + L.n + " jobs)", grew && a.some((u) => /cursor=/.test(u)), JSON.stringify(a.slice(-3)));
  check("...and still no job twice", L.dup === 0, JSON.stringify(L));
  check("the deck never ran dry meanwhile (a card on top)", !!(await ev("!!" + F + ".querySelector('#deck .card.top')")));
  await ev("(()=>{const A=" + FW + ".__uaply;if(A.setType)A.setType('internship')})()"); await sleep(500);
  await left(5); await sleep(2500);
  a = (await asked()).map((x) => x[0]);
  check("switching to the Internships stack asks for its own pages (?type=internship)", a.some((u) => /type=internship/.test(u)), JSON.stringify(a.slice(-4)));
  L = await live();
  check("...still no job twice", L.dup === 0, JSON.stringify(L));
  await ev("(()=>{const A=" + FW + ".__uaply;if(A.setType)A.setType('job')})()"); await sleep(500);
  if (typeof stop === "function") stop();
  await send("Fetch.disable");

  // ---- 4. Job Tracker lists the passed jobs ----
  await ev("(()=>{const b=" + F + ".getElementById('nb-dash');if(b)b.click()})()"); await sleep(400);
  await ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Applied'));if(e)e.click()})()"); await sleep(900);
  const rows = await ev("(" + F + ").querySelectorAll('#pane-track .row').length");
  check("Job Tracker lists the passed jobs (" + rows + " rows)", rows >= 10, rows);

  // ---- 5. a shared job that is on no early page: the friend's link still puts it in front (the sandbox, where Share this job is) ----
  const far = JSON.parse(await ev("fetch('/api/jobs?size=1&page=" + Math.max(2, total.total - 3) + "').then(r=>r.json()).then(j=>JSON.stringify(j.jobs[0]||null))"));
  if (far && (await ev("!!" + FW + ".__uaplySharePin"))) {
    await send("Page.navigate", { url: base + "/?job=" + far.id + "&t=" + encodeURIComponent(far.role) + "&c=" + encodeURIComponent(far.co) });
    let tp = "";
    for (let i = 0; i < 60; i++) { await sleep(250); tp = await ev("(()=>{try{const c=" + F + ".querySelector('#deck .card.top');return c?c.getAttribute('data-id'):''}catch(e){return ''}})()"); if (tp === String(far.id)) break; }
    check("a shared job near the end of the list (not on the first page) opens in front from its link (GET /api/jobs/<id>, with the first page)", tp === String(far.id), tp + " vs " + far.id);
  } else console.log("  (Share this job is not on this build: the shared-job check is for the sandbox)");
  const errs = logs.filter((l) => !/favicon|ERR_FILE_NOT_FOUND|401|403|net::ERR_FAILED|Failed to fetch/.test(l));
  check("no script errors", errs.length === 0, errs.join(" | "));
  console.log("\n" + (n - bad) + " / " + n);
  if (bad) throw new Error(bad + " paging check(s) failed");
};
