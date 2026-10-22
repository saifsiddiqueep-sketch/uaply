// Share this job (shared/uaply-share.js, sandbox): Mohammed's version A, October 22.
//   W=390 H=844 PORT=8751 node tools/cdp.js tools/ui-share.js
//   W=1280 H=720 PORT=8751 node tools/cdp.js tools/ui-share.js
// Against a sandbox server (serve.py <port> sandbox --api). This test answers /api/jobs itself with fixed postings, so it runs the same
// with the job feeds on or off. SHOTS=<folder> saves the three screens (and the Applied row) there.
//  1. the swipe page: a 36 px "Share this job" icon in the card's top-right corner, and nothing else changed (the same page with the
//     experiment switched off in the sandbox's controls is compared element by element, the card's HTML too)
//  2. the link: ?job=<id>&t=<title>&c=<company>, URL-encoded; "<Role> at <Company> on UAply"; the employer's link on a hand-off; an
//     example job never carries ?job=; the share sheet first, else the clipboard with a visible note; a tap never swipes the card
//  3. the friend's landing: the shared job in front, "Shared with you" above the card, ?job= gone from the address, Pass / Undo / Apply
//  3b. a long id (a posting whose first id collided: 9 to 16 digits, below 2**53) lands the same; an unsafe or too-long id is ignored
//  3c. a friend whose saved work-style filter (Remote) excludes the shared job still gets it first, with the line
//  3d. a friend who already swiped the job: no second card, a note on the line instead
//  4. the job no longer listed: "No longer listed" with the title and company from the link, open jobs like it (title words or company
//     first, then the same kind of job) with age and route, every row tall enough to show all its lines, the chips filter them, Pass / Undo / Apply hidden, Swipe through them
//  5. the Job Tracker's "Not sent yet" row: the same icon, the same link
//  6. the job is gone and nothing open is like it: "See other open jobs" always leads back to the deck (also with a chip on)
//  7. /api/jobs fails: the line names the job and says the jobs could not load, Try again (a reload) brings the landing back
//  8. boards still loading: the line names the job from the first moment, "Not found yet" with the jobs like it after 3 answers or
//     20 s, and the job moves to the front when a later answer brings it
const fs = require("fs");
const path = require("path");
const PORT = process.env.PORT || "8751";
const SHOTS = process.env.SHOTS || "";
const BASE = "http://127.0.0.1:" + PORT + "/";
const SIZE = (process.env.W || "1100") + "x" + (process.env.H || "900");
const PHONE = Number(process.env.W || 1100) < 700;

const SHARED = 1234567;
const job = (id, role, co, mode, loc, days, o) => Object.assign({ id, live: true, role, co, mode, loc, type: "job", jobType: "full-time", sal: [0, 0], yrs: 1, edu: "Bachelor",
  skills: ["Excel"], blurb: role + " at " + co + ".", url: "https://boards.greenhouse.io/" + co.toLowerCase().replace(/[^a-z]+/g, "") + "/jobs/" + id, source: co + " on Greenhouse",
  via: co + " on Greenhouse", postedDays: days, route: "ready" }, o || {});
const FEED = [
  // the shared job: a poor match for the example profile (a front-end developer), so it is never first on its own
  job(SHARED, "Broker Dealer Operations, Associate", "Coinbase", "onsite", "Chicago, IL", 4, { sal: [121000, 128000], yrs: 7, skills: ["Series 7", "FINRA"] }),
  job(1200001, "Frontend Developer", "Northbeam Labs", "remote", "Remote (US)", 2, { sal: [110000, 130000], yrs: 3, skills: ["JavaScript", "React", "TypeScript"], route: "connected", instant: true }),
  job(1200002, "React Engineer", "Pixelworks", "hybrid", "New York, NY", 6, { sal: [105000, 125000], yrs: 3, skills: ["React", "CSS"] }),
  job(1200003, "Trade Operations Analyst", "Northbeam Markets", "remote", "Remote (US)", 1, { sal: [110000, 124000], route: "connected", instant: true }),
  job(1200004, "Brokerage Operations Specialist", "Ledgerline", "onsite", "New York, NY", 3, { sal: [90000, 105000] }),
  job(1200005, "Compliance Associate", "Coinbase, Inc.", "remote", "Remote (US)", 10),
  job(1200006, "Data Analyst", "Harbor Health", "hybrid", "Philadelphia, PA", 2, { skills: ["SQL", "Python"] }),
  job(1200007, "UX Designer", "Calla Studio", "remote", "Remote (US)", 5, { skills: ["Figma"] }),
  job(1200008, "Operations Intern", "Riverline", "onsite", "Pittsburgh, PA", 0, { type: "internship", jobType: "internship" }),
];
// postings with long ids (jobs_api.py gives one whose 6-hex id collides 7 to 13 hex digits: up to 16 decimal digits, kept below 2**53)
const LONG9 = 268000123, LONG16 = 4503599627370497;
const BIG = [
  job(LONG9, "Payments Operations Lead", "Stripe", "remote", "Remote (US)", 3, { yrs: 8, skills: ["Payments"] }),
  job(LONG16, "Field Service Technician", "Voltaro", "onsite", "Columbus, OH", 2, { yrs: 6, skills: ["HVAC"] }),
];
// open jobs with nothing in common with the shared one (no title word, another company, part-time, not full-time)
const UNLIKE = [
  job(1300001, "Marketing Assistant", "Bloomfield Foods", "remote", "Remote (US)", 1, { jobType: "part-time" }),
  job(1300002, "Graphic Designer", "Calla Studio", "hybrid", "Boston, MA", 2, { jobType: "part-time" }),
  job(1300003, "Nursing Aide", "Harbor Health", "onsite", "Philadelphia, PA", 3, { jobType: "part-time" }),
  job(1300004, "Software Tester", "Pixelworks", "remote", "Remote (US)", 1, { jobType: "part-time" }),
  job(1300005, "Event Planner", "Riverline", "onsite", "Pittsburgh, PA", 5, { jobType: "part-time" }),
];
const T = "Broker Dealer Operations, Associate", C = "Coinbase";
const LINK = BASE + "?job=" + SHARED + "&t=" + encodeURIComponent(T) + "&c=" + encodeURIComponent(C);

module.exports = async ({ ev, sleep, nav, send, on, shot, logs }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let pass = 0, total = 0;
  const check = (name, ok, extra) => { total++; if (ok) pass++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + String(extra).slice(0, 300) : "")); };
  const J = (x) => ev("JSON.stringify(" + x + ")").then((s) => { try { return JSON.parse(s); } catch (e) { return s; } });
  const waitFor = async (expr, ms) => { for (let t = 0; t < (ms || 15000); t += 250) { if (await ev("(()=>{try{return !!(" + expr + ")}catch(e){return false}})()") === true) return true; await sleep(250); } return false; };
  const snap = async (name) => { if (!SHOTS) return; fs.mkdirSync(SHOTS, { recursive: true }); await shot(path.join(SHOTS, name + "-" + SIZE + ".png")); };

  // the job list: the whole feed, or the feed without the shared job ("gone")
  // status: the answer's HTTP status (500: the list failed); pending: boards still loading, so the app asks again
  let feed = "all", status = 200, pending = 0;
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/jobs*" }] });
  on("Fetch.requestPaused", (p) => {
    const list = feed === "gone" ? FEED.filter((j) => j.id !== SHARED) : feed === "big" ? FEED.concat(BIG) : feed === "unlike" ? UNLIKE : FEED;
    send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: status, responseHeaders: [{ name: "Content-Type", value: "application/json" }],
      body: Buffer.from(JSON.stringify(status === 200 ? { jobs: list, pending, sources: { test: list.length } } : { error: "test outage" })).toString("base64") });
  });

  const topId = () => ev("(()=>{const c=" + F + ".querySelector('#deck .card.top');return c?+c.getAttribute('data-id'):0})()");
  const shown = (sel) => ev("(()=>{const e=" + F + ".querySelector(" + JSON.stringify(sel) + ");if(!e)return false;const s=getComputedStyle(e);return !e.closest('[hidden]')&&s.display!=='none'&&s.visibility!=='hidden'&&e.getClientRects().length>0})()");
  const notNow = async () => { if (await waitFor(F + ".getElementById('kcNo')", 2500)) { await ev(F + ".getElementById('kcNo').click()"); await sleep(500); } };
  const fresh = async (url) => {
    await nav(BASE); await ev("localStorage.clear();sessionStorage.clear()");
    await nav(url);
    const ok = await waitFor(FW + ".__uaply&&" + F + ".querySelector('#deck .card.top')&&" + FW + ".__uaplyHideSamples", 20000);
    await notNow();
    return ok;
  };
  // a real tap (phone) or click (laptop) on an element of the app
  const tap = async (sel) => {
    const r = await J("(()=>{const e=" + F + ".querySelector(" + JSON.stringify(sel) + ");if(!e)return null;e.scrollIntoView({block:'center'});const f=document.querySelector('iframe').getBoundingClientRect(),b=e.getBoundingClientRect();return {x:Math.round(f.left+b.left+b.width/2),y:Math.round(f.top+b.top+b.height/2)}})()");
    if (!r) return false;
    if (PHONE) {
      await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: r.x, y: r.y, id: 1 }] }); await sleep(60);
      await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    } else {
      await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: r.x, y: r.y });
      await send("Input.dispatchMouseEvent", { type: "mousePressed", x: r.x, y: r.y, button: "left", clickCount: 1 }); await sleep(60);
      await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: r.x, y: r.y, button: "left", clickCount: 1 });
    }
    await sleep(700);
    return true;
  };
  const stubShare = () => ev("(()=>{window.__shared=[];Object.defineProperty(navigator,'share',{configurable:true,value:function(d){window.__shared.push(d);return Promise.resolve()}});return true})()");
  const unstubShare = () => ev("(()=>{delete navigator.share;return true})()");
  // the swipe page as a list of what is on it (every element outside the cards, with what it says and whether it shows) and the top card's HTML
  const page = () => J("(()=>{const d=" + F + ",col=d.querySelector('#pane-swipe .swipecol'),out=[];" +
    "col.querySelectorAll('*').forEach(e=>{if(e.closest('#deck')||e.closest('[class*=ushr]'))return;" +
    "const s=getComputedStyle(e);out.push(e.tagName+'#'+e.id+'.'+(e.getAttribute('class')||'')+'|'+(e.children.length?'':e.textContent.trim().slice(0,60))+'|'+(e.closest('[hidden]')||s.display==='none'?'hidden':'shown'))});" +
    "const c=d.querySelector('#deck .card.top').cloneNode(true);c.querySelectorAll('.ushr-ic').forEach(x=>x.remove());c.removeAttribute('style');c.querySelectorAll('[style]').forEach(x=>{if(x.classList.contains('stamp'))x.removeAttribute('style')});" +
    "return {page:out,card:c.outerHTML,id:+c.getAttribute('data-id'),bnav:(d.getElementById('bnav')||{}).innerText||'',head:(d.querySelector('header.bar')||{}).innerText||''}})()");

  // ---------- 1. the swipe page: the icon, and nothing else changed ----------
  check("the sandbox opens with real (test) postings", await fresh(BASE));
  check("the experiment is on in the sandbox", !!(await ev("!!(document.querySelector('#feats button[data-k=\"share\"]')||{}).getAttribute&&document.querySelector('#feats button[data-k=\"share\"]').getAttribute('aria-pressed')==='true'")));
  check("the sandbox reports no problem building the app", !/^Problem/.test(await ev("document.getElementById('note').textContent")), await ev("document.getElementById('note').textContent"));
  const ic = await J("(()=>{const c=" + F + ".querySelector('#deck .card.top'),b=c&&c.querySelector('.ushr-ic');if(!b)return null;const r=b.getBoundingClientRect(),k=c.getBoundingClientRect();" +
    "return {label:b.getAttribute('aria-label'),w:Math.round(r.width),h:Math.round(r.height),right:Math.round(k.left+c.clientLeft+c.clientWidth-r.right),top:Math.round(r.top-k.top),svg:!!b.querySelector('svg'),text:b.textContent.trim(),tab:b.tabIndex," +
    "titleRight:Math.round(c.querySelector('.chead h2').getBoundingClientRect().right),btnLeft:Math.round(r.left)}})()");
  check("the top card has a share icon labelled 'Share this job'", ic && ic.label === "Share this job" && ic.svg && ic.text === "", JSON.stringify(ic));
  check("it is about 36 px", ic && ic.w >= 34 && ic.w <= 38 && ic.h >= 34 && ic.h <= 38, ic && ic.w + "x" + ic.h);
  check("it sits in the card's top-right corner (measured inside a scroll bar)", ic && ic.right >= 0 && ic.right <= 16 && ic.top >= 0 && ic.top <= 16, ic && "right " + ic.right + ", top " + ic.top);
  check("the job title never runs under it", ic && ic.titleRight <= ic.btnLeft, ic && ic.titleRight + " <= " + ic.btnLeft);
  check("the cards under the top one keep it out of the keyboard order", (await ev("[...(" + F + ").querySelectorAll('#deck .card:not(.top) .ushr-ic')].every(b=>b.tabIndex===-1)")) === true);
  check("no 'Shared with you' line and no closed screen on an ordinary visit", !(await shown("#ushrLine")) && !(await shown("#ushrClosed")));
  const on1 = await page();
  // the same page with the experiment off (the sandbox's own switch), the same job on top
  await ev("document.querySelector('#feats button[data-k=\"share\"]').click()");
  await sleep(1500);
  await waitFor(FW + ".__uaply&&" + F + ".querySelector('#deck .card.top')&&" + FW + ".__uaplyHideSamples", 20000);
  await notNow();
  const off1 = await page();
  check("with the experiment off the card has no icon", !(await ev("!!" + F + ".querySelector('.ushr-ic')")));
  check("the same job is on top either way", on1.id === off1.id && on1.id > 0, on1.id + " / " + off1.id);
  check("the card's contents are the same with and without the icon", on1.card === off1.card, on1.card.length + " / " + off1.card.length);
  const diff = on1.page.filter((x, i) => x !== off1.page[i]).concat(off1.page.slice(on1.page.length));
  check("nothing else on the swipe page changed (header notice, filters, Pass / Undo / Apply, every element)", on1.page.length === off1.page.length && !diff.length, diff.slice(0, 3).join(" ; "));
  check("the header and the bottom bar are the same", on1.head === off1.head && on1.bnav === off1.bnav);
  await ev("document.querySelector('#feats button[data-k=\"share\"]').click()");
  await sleep(1500);
  await waitFor(FW + ".__uaply&&" + F + ".querySelector('#deck .card.top .ushr-ic')&&" + FW + ".__uaplyHideSamples", 20000);
  await notNow();
  await snap("share-1-card");

  // ---------- 2. the link ----------
  await stubShare();
  const before = await topId();
  check("a tap on the icon (" + (PHONE ? "touch" : "mouse") + ")", await tap("#deck .card.top .ushr-ic"));
  const sh = await J("window.__shared");
  check("it opens the share sheet once", Array.isArray(sh) && sh.length === 1, JSON.stringify(sh));
  const m = (sh && sh[0]) || {};
  const topJob = FEED.find((j) => j.id === before) || {};
  const mm = /^http:\/\/127\.0\.0\.1:\d+\/\?job=(\d+)&t=([^&]+)&c=([^&]+)$/.exec(m.url || "");
  check("the link is this site's address with ?job=<id>&t=<title>&c=<company>", !!mm, m.url);
  check("the id is that job's id", mm && +mm[1] === before, mm && mm[1] + " / " + before);
  check("the title and company are URL-encoded and read back exactly", mm && decodeURIComponent(mm[2]) === topJob.role && decodeURIComponent(mm[3]) === topJob.co && mm[2] === encodeURIComponent(topJob.role), mm && mm[2] + " | " + mm[3]);
  check("nothing personal in the link (no name, email or profile)", !/jordan|example\.com|@/i.test(m.url || ""));
  check("the message reads '<Role> at <Company> on UAply'", (m.text || "").split("\n")[0] === topJob.role + " at " + topJob.co + " on UAply", m.text);
  check("a tap on the icon never swipes the card", (await topId()) === before && (await ev("Object.keys(" + FW + ".__uaply.S.decisions).length")) === 0);
  const hand = await J(FW + ".__uaplyShareMsg(" + FW + ".__uaplyShareById(" + SHARED + "))");
  check("a job that takes applications on its own site: its link is in the message too", /\nCoinbase takes applications on its own site: https:\/\/boards\.greenhouse\.io\/coinbase\/jobs\/1234567$/.test(hand.text || "") && /\?job=1234567&/.test(hand.url), JSON.stringify(hand));
  const inst = await J(FW + ".__uaplyShareMsg(" + FW + ".__uaplyShareById(1200001))");
  check("a job UAply applies to: no employer link needed", inst.text === "Frontend Developer at Northbeam Labs on UAply", inst.text);
  const ex = await J(FW + ".__uaplyShareMsg({id:13,live:false,co:'Calloway Studios',role:'Design Intern',mode:'remote'})");
  check("an example job is never shared with ?job=", !/[?&]job=/.test(ex.url) && /example listing/.test(ex.text), JSON.stringify(ex));
  // no share sheet: the clipboard, with a note that says so
  await ev("(()=>{Object.defineProperty(navigator,'share',{configurable:true,value:undefined});window.__clip=[];const w=" + FW + ";" +
    "[navigator,w.navigator].forEach(n=>{try{Object.defineProperty(n,'clipboard',{configurable:true,value:{writeText:function(t){window.__clip.push(t);return Promise.resolve()}}})}catch(e){}});return true})()");
  await tap("#deck .card.top .ushr-ic");
  const clip = await J("window.__clip");
  check("without a share sheet the message and link are copied", Array.isArray(clip) && clip.length === 1 && clip[0].indexOf(m.url) > -1 && clip[0].indexOf(topJob.role + " at " + topJob.co + " on UAply") === 0, JSON.stringify(clip));
  const toast = await ev("[...(" + F + ").querySelectorAll('.toast')].map(t=>t.innerText).join(' | ')");
  check("and a visible note says it was copied", /Link copied/.test(toast), toast);
  await unstubShare();
  await ev("(()=>{const w=" + FW + ";[navigator,w.navigator].forEach(n=>{try{delete n.clipboard}catch(e){}});return true})()");

  // ---------- 3. the friend opens the link ----------
  feed = "all";
  check("the friend's page opens", await fresh(LINK));
  check("?job= is taken off the address", !/job=/.test(await ev("location.search")), await ev("location.href"));
  check("on an ordinary visit the shared job is not first (a poor match for the example profile)", on1.id !== SHARED && on1.id > 0, on1.id);
  check("the shared job is the top card", (await topId()) === SHARED, await topId());
  const line = await J("(()=>{const d=" + F + ",l=d.getElementById('ushrLine'),c=d.querySelector('#deck .card.top');return l?{text:l.innerText.replace(/\\s+/g,' ').trim(),before:!!(l.compareDocumentPosition(d.getElementById('deck'))&Node.DOCUMENT_POSITION_FOLLOWING),above:Math.round(l.getBoundingClientRect().bottom)<=Math.round(c.getBoundingClientRect().top)}:null})()");
  check("'Shared with you' shows above the card", (await shown("#ushrLine")) && line && line.text === "Shared with you · a free job app · no account needed" && line.before && line.above, JSON.stringify(line));
  check("the card keeps its share icon", !!(await ev("!!" + F + ".querySelector('#deck .card.top .ushr-ic')")));
  check("Pass, Undo and Apply are there", (await shown("#btnNo")) && (await shown("#btnUndo")) && (await shown("#btnYes")) && !(await ev(F + ".getElementById('btnNo').disabled")));
  check("no sign-in or account screen is in the way", !(await shown("#acctSec")) && !(await shown(".sg-card")) && !(await ev("!!" + F + ".querySelector('#kitSheet')")));
  check("no closed screen", !(await shown("#ushrClosed")));
  await snap("share-2-friend");
  await ev(F + ".getElementById('btnNo').click()"); await sleep(1200);
  check("Pass: the next job, and the line goes", (await topId()) !== SHARED && !(await shown("#ushrLine")));
  check("the pass needed no account", (await ev(FW + ".__uaply.S.decisions[" + SHARED + "]&&" + FW + ".__uaply.S.decisions[" + SHARED + "].s")) === "passed");
  await ev(F + ".getElementById('btnUndo').click()"); await sleep(1200);
  check("Undo brings the shared job back with its line", (await topId()) === SHARED && (await shown("#ushrLine")));
  await nav(BASE); await waitFor(FW + ".__uaply&&" + F + ".querySelector('#deck .card.top')&&" + FW + ".__uaplyHideSamples", 20000); await notNow();
  check("a reload without ?job= is an ordinary visit again", (await topId()) !== SHARED && !(await shown("#ushrLine")));

  // ---------- 3b. long ids ----------
  feed = "big";
  const link = (id, t, c) => BASE + "?job=" + id + "&t=" + encodeURIComponent(t) + "&c=" + encodeURIComponent(c);
  const landed = async (id) => (await waitFor("(()=>{const c=" + F + ".querySelector('#deck .card.top');return c&&+c.getAttribute('data-id')===" + id + "})()", 10000)) && (await shown("#ushrLine"));
  check("a friend's page on a 9-digit id opens", await fresh(link(LONG9, "Payments Operations Lead", "Stripe")));
  check("the 9-digit job is the top card, with 'Shared with you'", await landed(LONG9), await topId());
  const m16 = await J(FW + ".__uaplyShareMsg(" + FW + ".__uaplyShareById('" + LONG16 + "'))");
  check("a 16-digit id is shared exactly", (m16.url || "").endsWith("?job=" + LONG16 + "&t=Field%20Service%20Technician&c=Voltaro"), m16.url);
  check("a friend's page on a 16-digit id opens", await fresh(link(LONG16, "Field Service Technician", "Voltaro")));
  check("the 16-digit job is the top card, with 'Shared with you'", await landed(LONG16), await topId());
  check("an id past 2**53 opens an ordinary deck", await fresh(link("9007199254740993", "Field Service Technician", "Voltaro")));
  await sleep(1500);
  check("and no line, no closed screen, ?job= gone", !(await shown("#ushrLine")) && !(await shown("#ushrClosed")) && !/job=/.test(await ev("location.search")) && (await topId()) !== LONG16);

  // ---------- 3c. a saved work-style filter that excludes the shared (on-site) job ----------
  feed = "all";
  check("a friend who already uses UAply opens it", await fresh(BASE));
  await ev(F + ".querySelector('#fWs [data-f=\"remote\"]').click()"); await sleep(600);
  check("their Remote work style is saved", (await ev(FW + ".__uaply.getFilter()")) === "remote" && (await ev("Object.keys(localStorage).some(k=>/\"mode\":\"remote\"/.test(localStorage.getItem(k)))")) === true);
  await nav(LINK); await waitFor(FW + ".__uaply&&" + F + ".querySelector('#deck .card.top')&&" + FW + ".__uaplyHideSamples", 20000); await notNow();
  check("the shared on-site job is still the top card, with 'Shared with you'", await landed(SHARED), await topId());
  check("their Remote filter stays on (not saved over)", (await ev(FW + ".__uaply.getFilter()")) === "remote" && (await ev(F + ".querySelector('#filters [data-f=\"remote\"]').getAttribute('aria-pressed')")) === "true");
  await ev(F + ".getElementById('btnNo').click()"); await sleep(1200);
  const nextId = await topId(), nextJob = FEED.find((j) => j.id === nextId) || {};
  check("after Pass the deck follows their Remote filter again", nextJob.mode === "remote" && !(await shown("#ushrLine")), nextId + " " + nextJob.mode);

  // ---------- 3d. the friend already swiped the shared job (it was passed just above) ----------
  await nav(LINK); await waitFor(FW + ".__uaply&&" + F + ".querySelector('#deck .card.top')&&" + FW + ".__uaplyHideSamples", 20000); await notNow();
  check("an already-passed job is not dealt again", await waitFor("(()=>{const l=" + F + ".getElementById('ushrLine');return l&&!l.hidden})()", 10000) && (await topId()) !== SHARED, await topId());
  const seen = await ev("(" + F + ").getElementById('ushrLine').innerText.replace(/\\s+/g,' ').trim()");
  check("the line says it was shared and that they passed on it", seen === "Shared with you: " + T + " at " + C + ". You passed on it earlier.", seen);
  await ev(F + ".getElementById('btnNo').click()"); await sleep(1200);
  check("the note goes with the next swipe", !(await shown("#ushrLine")));

  // ---------- 4. the job is no longer listed ----------
  feed = "gone";
  check("the friend's page opens on a job that left the list", await fresh(LINK));
  check("'No longer listed' stands in for the card", await waitFor("(()=>{const e=" + F + ".getElementById('ushrClosed');return e&&!e.hidden})()", 8000));
  const gone = await ev("(" + F + ").getElementById('ushrClosed').innerText.replace(/\\s+/g,' ')");
  check("it says No longer listed on UAply, with the title and company from the link", /No longer listed on UAply/.test(gone) && gone.indexOf(T) > -1 && gone.indexOf(C) > -1, gone.slice(0, 200));
  check("'Shared with you' shows above it", await shown("#ushrLine"));
  check("Pass, Undo and Apply are hidden (there is no card)", !(await shown("#btnNo")) && !(await shown("#btnYes")) && !(await shown("#btnUndo")) && !(await shown("#deck")));
  const rows = await J("[...(" + F + ").querySelectorAll('#ushrClosed .ushr-row')].map(r=>({id:+r.getAttribute('data-ushr-go'),label:r.getAttribute('aria-label'),mode:r.getAttribute('data-mode'),text:r.innerText.replace(/\\s+/g,' ')}))");
  check("open jobs like it are listed", rows.length >= 4, rows.length);
  check("the same company with a title word comes first", rows[0] && rows[0].label === "Compliance Associate at Coinbase, Inc.", rows[0] && rows[0].label);
  check("then the ones that share a title word, newest first", rows.slice(1, 4).map((r) => r.label).join(" ; ") === "Operations Intern at Riverline ; Trade Operations Analyst at Northbeam Markets ; Brokerage Operations Specialist at Ledgerline", rows.slice(1, 4).map((r) => r.label).join(" ; "));
  check("then the same kind of job (full-time), newest first", rows.slice(4).map((r) => r.label).join(" ; ") === "Frontend Developer at Northbeam Labs ; Data Analyst at Harbor Health ; UX Designer at Calla Studio ; React Engineer at Pixelworks" && rows.slice(4).every((r) => /Like it: the same kind of job \(full-time\)/.test(r.text)), rows.slice(4).map((r) => r.label).join(" ; "));
  check("each row says its age and where its application goes", rows.every((r) => /Posted (today|\d+ days? ago|1 week ago|\d+ weeks ago)/.test(r.text) && /(Applies through UAply|Finish on their site)/.test(r.text)), rows.map((r) => r.text).join(" ; ").slice(0, 300));
  check("both routes are told apart", rows.some((r) => /Applies through UAply/.test(r.text)) && rows.some((r) => /Finish on their site/.test(r.text)));
  // innerText reads text that is drawn under the next row too, so the rows' boxes are measured
  const lay = await J("(()=>{const rs=[...(" + F + ").querySelectorAll('#ushrClosed .ushr-row')];return rs.map((r,i)=>{const b=r.getBoundingClientRect(),n=rs[i+1]&&rs[i+1].getBoundingClientRect(),l=r.querySelector('.ushr-like').getBoundingClientRect(),a=r.querySelector('.ushr-age').getBoundingClientRect();" +
    "return {h:r.offsetHeight,sh:r.scrollHeight,bottom:Math.round(b.bottom),next:n?Math.round(n.top):null,like:Math.round(l.bottom),age:Math.round(a.bottom)}})})()");
  check("every row is tall enough for all its lines (age, pay, route, Like it)", lay.length === rows.length && lay.every((x) => x.h >= x.sh && x.h > 60 && x.like <= x.bottom && x.age <= x.bottom), lay.map((x) => x.h + "/" + x.sh).join(" "));
  check("no row overlaps the next", lay.every((x) => x.next === null || x.bottom <= x.next), lay.map((x) => x.bottom + "<=" + x.next).join(" "));
  await snap("share-3-closed");
  await ev("(" + F + ").querySelector('#filters [data-f=\"remote\"]').click()"); await sleep(700);
  const remote = await J("[...(" + F + ").querySelectorAll('#ushrClosed .ushr-row')].map(r=>r.getAttribute('data-mode'))");
  check("the Remote chip filters them", remote.length > 0 && remote.length < rows.length && remote.every((x) => x === "remote"), remote.join(","));
  await ev("(" + F + ").querySelector('#filters [data-f=\"all\"]').click()"); await sleep(700);
  check("All brings them back", (await ev("(" + F + ").querySelectorAll('#ushrClosed .ushr-row').length")) === rows.length);
  await ev("(()=>{const d=" + F + ";d.body.focus();d.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));d.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}))})()"); await sleep(900);
  check("the arrow keys swipe nothing while there is no card", (await ev("Object.keys(" + FW + ".__uaply.S.decisions).length")) === 0);
  await tap("#ushrClosed .ushr-sec [data-ushr-go]");
  check("Swipe through them: the deck and Pass / Undo / Apply come back, the first job like it on top", (await shown("#deck")) && (await shown("#btnYes")) && !(await shown("#ushrClosed")) && (await topId()) === rows[0].id, await topId());

  // ---------- 5. the Job Tracker's "Not sent yet" row ----------
  await ev("(()=>{const A=" + FW + ".__uaply,now=Date.now();" +
    "A.S.decisions[1200002]={s:'applied',at:now,pct:80,as:'You',title:'',st:'applied',sent:{at:now,to:'',status:'handoff'}};" +
    "A.S.decisions[1200006]={s:'applied',at:now-1000,pct:70,as:'You',title:'',st:'applied',sent:{at:now,to:'Harbor Health',status:'sent'}};A.save();A.renderAll();return true})()");
  await ev(F + ".getElementById('nb-dash').click()"); await sleep(500);
  await ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Applied'));if(e)e.click()})()"); await sleep(900);
  const ri = await J("(()=>{const d=" + F + ",b=d.querySelector('#pane-track .ushr-rowic');if(!b)return null;const r=b.closest('.row'),k=b.getBoundingClientRect();" +
    "return {label:b.getAttribute('aria-label'),id:b.getAttribute('data-id'),row:r.innerText.replace(/\\s+/g,' ').slice(0,160),w:Math.round(k.width),glyph:b.querySelector('svg').innerHTML===d.querySelector('.ushr-ic svg')?.innerHTML||b.querySelector('svg path').getAttribute('d')==='M12 3v12'," +
    "n:d.querySelectorAll('#pane-track .ushr-rowic').length}})()");
  check("the 'Not sent yet' row has the share icon", ri && ri.id === "1200002" && /Not sent yet/.test(ri.row) && ri.label === "Share this job: React Engineer at Pixelworks", JSON.stringify(ri));
  check("small, the same glyph", ri && ri.w >= 26 && ri.w <= 34 && ri.glyph, ri && ri.w);
  check("a row that was sent gets none", ri && ri.n === 1, ri && ri.n);
  await snap("share-4-applied");
  await stubShare();
  await ev("(" + F + ").querySelector('#pane-track .ushr-rowic').scrollIntoView({block:'center'})"); await sleep(300);
  await tap("#pane-track .ushr-rowic");
  const rs = await J("window.__shared");
  check("tapping it shares the same UAply link for that job", rs && rs.length === 1 && /\?job=1200002&t=React%20Engineer&c=Pixelworks$/.test(rs[0].url) && /^React Engineer at Pixelworks on UAply\nPixelworks takes applications on its own site: https:/.test(rs[0].text), JSON.stringify(rs));
  await ev("document.querySelectorAll('#pane-track')"); await unstubShare();

  const lineText = () => ev("(()=>{const l=" + F + ".getElementById('ushrLine');return l&&!l.hidden?l.innerText.replace(/\\s+/g,' ').trim():''})()");
  const closedUp = "(()=>{const e=" + F + ".getElementById('ushrClosed');return e&&!e.hidden})()";
  const chip = (f) => ev("(" + F + ").querySelector('#filters [data-f=\"" + f + "\"]').click()").then(() => sleep(700));

  // ---------- 6. the job is gone and nothing open is like it: there is always a way back to the deck ----------
  feed = "unlike";
  check("the friend's page opens on a gone job with nothing open like it", await fresh(LINK));
  check("'No longer listed' stands in for the card", await waitFor(closedUp, 8000));
  const z = await ev("(" + F + ").getElementById('ushrClosed').innerText.replace(/\\s+/g,' ')");
  check("it says no open jobs are like it, and offers 'See other open jobs'", /No open jobs like it right now\./.test(z) && (await shown("#ushrClosed .ushr-empty [data-ushr-go='']")) && /See other open jobs/.test(z), z.slice(-160));
  const other = await J("(()=>{const b=" + F + ".querySelector('#ushrClosed .ushr-other');const r=b.getBoundingClientRect();return {h:Math.round(r.height)}})()");
  check("the button is a full-size target", other && other.h >= 44, other && other.h);
  await chip("remote");
  check("with a chip on, it still offers the way back", (await shown("#ushrClosed [data-ushr-go='']")) && !(await shown("#deck")));
  await chip("all");
  await snap("share-3b-closed-nothing-like-it");
  await tap("#ushrClosed [data-ushr-go='']");
  const back = await topId();
  check("See other open jobs: the deck and Pass / Undo / Apply come back, an open job on top", (await shown("#deck")) && (await shown("#btnYes")) && (await shown("#btnNo")) && !(await shown("#ushrClosed")) && UNLIKE.some((j) => j.id === back), back);
  await chip("remote"); await chip("all");
  check("changing the chips does not bring the closed screen back", (await shown("#deck")) && !(await shown("#ushrClosed")));
  await ev(F + ".getElementById('btnNo').click()"); await sleep(1200);
  check("the friend can swipe (Pass) as usual", (await ev(FW + ".__uaply.S.decisions[" + back + "]&&" + FW + ".__uaply.S.decisions[" + back + "].s")) === "passed");

  // ---------- 7. /api/jobs fails: the landing says so and survives Try again ----------
  feed = "all"; status = 500;
  await nav(BASE); await ev("localStorage.clear();sessionStorage.clear()");
  await nav(LINK);
  check("the friend's page opens while the job list fails", await waitFor(FW + ".__uaply&&" + F + ".querySelector('#deck .card.top')", 20000));
  await notNow();
  check("?job= is taken off the address", !/job=/.test(await ev("location.search")), await ev("location.href"));
  const failWant = "Shared with you: " + T + " at " + C + ". UAply couldn’t load jobs just now. Try again";
  check("the line names the shared job and says the jobs could not load", await waitFor("(" + JSON.stringify(failWant) + "===(()=>{const l=" + F + ".getElementById('ushrLine');return l&&!l.hidden?l.innerText.replace(/\\s+/g,' ').trim():''})())", 8000), await lineText());
  check("the landing is kept for Try again", (await ev("!!sessionStorage.getItem('uaply.share.landing')")) === true);
  await snap("share-5-jobs-failed");
  status = 200;
  await tap("#ushrLine [data-ushr-retry]"); await sleep(3000);
  await waitFor(FW + ".__uaply&&" + F + ".querySelector('#deck .card.top')", 20000); await notNow();
  check("Try again: the shared job is the top card", await waitFor("(()=>{const c=" + F + ".querySelector('#deck .card.top');return c&&+c.getAttribute('data-id')===" + SHARED + "})()", 15000), await topId());
  check("with 'Shared with you' above it", (await lineText()) === "Shared with you · a free job app · no account needed", await lineText());
  check("settled: nothing is kept, so a later visit is ordinary", (await ev("sessionStorage.getItem('uaply.share.landing')")) === null);

  // ---------- 8. boards still loading: the friend sees the job named at once, then "Not found yet", then the job if it turns up ----------
  feed = "gone"; pending = 5;
  check("the friend's page opens while boards are still loading", await fresh(LINK));
  const waitWant = "Shared with you: " + T + " at " + C + ". Looking for it in today’s listings…";
  const w1 = await lineText();
  check("from the first moment the line names the job and says UAply is looking", w1 === waitWant, w1);
  check("no closed screen yet, the deck as usual", !(await shown("#ushrClosed")) && (await shown("#deck")));
  const t8 = Date.now();
  check("within 25 s 'Not found yet' with the jobs like it", await waitFor(closedUp, 25000), Math.round((Date.now() - t8) / 1000) + " s");
  const nf = await ev("(" + F + ").getElementById('ushrClosed').innerText.replace(/\\s+/g,' ')");
  check("it says Not found yet and that boards are still loading, never 'No longer listed'", /Not found yet/.test(nf) && /still reading job boards/.test(nf) && !/No longer listed/.test(nf) && nf.indexOf(T) > -1, nf.slice(0, 220));
  check("the jobs like it are listed, Pass / Undo / Apply hidden", (await ev("(" + F + ").querySelectorAll('#ushrClosed .ushr-row').length")) >= 4 && !(await shown("#btnYes")));
  await snap("share-3c-not-found-yet");
  feed = "all";
  check("a later answer that brings the job: it moves to the front", await waitFor("(()=>{const c=" + F + ".querySelector('#deck .card.top');return c&&+c.getAttribute('data-id')===" + SHARED + "})()", 25000), await topId());
  check("with 'Shared with you', the closed screen gone, Pass / Undo / Apply back", (await lineText()) === "Shared with you · a free job app · no account needed" && !(await shown("#ushrClosed")) && (await shown("#btnYes")), await lineText());
  pending = 0;

  const errs = logs.filter((l) => /^(ERR|EXC)\b|patch target not found/.test(l));
  check("no console error, exception or 'patch target not found'", !errs.length, errs.join(" ; "));
  console.log(pass + " / " + total);
  if (pass !== total) process.exitCode = 1;
};
