// Job Tracker counts (Trello K0QEMeQm, October 22, 2026): a hand-off that was never sent is not counted as applied.
//   PORT=<sandbox port, any job feed> W=390 H=844 node tools/cdp.js tools/ui-dashboard-split.js      (SHOTS=<folder> also saves screenshots)
// Seeds this browser with one application of every kind (sent by UAply, sent on the employer's own page, marked as applied by the person,
// hand-offs, a question only the person can answer, one waiting for the connection, a send that failed, one that went to the test inbox,
// and an interview, an offer and a rejection), then opens Job Tracker, which goes straight to the Overview (card 182). Its counts (Needs you, Sent, Heard back,
// Passed) never add the hand-offs into Sent; a test-inbox send ("Sent (test)", nothing reached the employer) is never counted as Sent; and
// each chip shows exactly the rows its count says, so the numbers and the rows can never disagree. "Mark as applied" is clicked on a
// real row. On the code before the fix the overview read "Applications 13" and "Waiting 10", and the Applied list "Applied 10".
const fs = require("fs"), path = require("path");
const gateSignup = require("./gate-signup.js");   // the test person signs up first (the app opens behind the sign-in gate)
const PORT = process.env.PORT, SHOTS = process.env.SHOTS || "";
module.exports = async ({ ev, sleep, nav, shot }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + "[dashboard] " + name + (ok || extra === undefined ? "" : "  | " + String(extra).slice(0, 400))); };
  const base = "http://127.0.0.1:" + PORT + "/";
  const ready = async () => { for (let i = 0; i < 60; i++) { if (await ev("!!(" + FW + "&&" + FW + ".__uaply&&" + F + ".getElementById('bnav'))").catch(() => false)) return true; await sleep(250); } return false; };
  const agree = () => ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m){m.ownerDocument.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});m.disabled=false;m.click();return true}return false})()");
  const inApp = (js) => ev("(()=>{try{const d=" + F + ",w=" + FW + ";" + js + "}catch(e){return 'ERR '+e.message}})()");

  await gateSignup({ ev, sleep, nav }, base, "dashboard");
  await nav(base); await ready(); await sleep(800); await agree(); await sleep(500);
  const KEY = await ev("window.__uaplyBuildKey");
  const now = Date.now();
  // [id, company, stage, what happened to it]   (stage "" = still at Applied; no record = saved before UAply kept one, nothing was sent)
  const SEED = [
    [9300001, "Sent Freight", "", { status: "sent", to: "Sent Freight" }],
    [9300002, "Assist Labs", "", { status: "sent", via: "assist", to: "Assist Labs" }],
    [9300003, "Self Works", "", { status: "self", to: "", prev: "handoff", once: false }],
    [9300004, "Handoff Co", "", { status: "handoff", to: "" }],
    [9300005, "Careers Only", "", { status: "handoff", to: "" }],
    [9300006, "No Record Inc", "", null],
    [9300007, "Question Co", "", { status: "needs_answers", to: "" }],
    [9300008, "Offline Co", "", { status: "pending", to: "" }],
    [9300009, "Interview Co", "interview", { status: "handoff", to: "" }],
    [9300010, "Offer Co", "accepted", { status: "sent", to: "Offer Co" }],
    [9300011, "Nope Co", "rejected", { status: "sent", to: "Nope Co" }],
    [9300012, "Failed Co", "", { status: "failed", to: "" }],
    [9300013, "Test Inbox Co", "", { status: "delivered_test", to: "the test inbox (simulated)", simulated: true }],
  ];
  await ev("(()=>{const K=" + JSON.stringify(KEY) + ",now=" + now + ",SEED=" + JSON.stringify(SEED) + ";const s=JSON.parse(localStorage.getItem(K)||'{}');" +
    "s.profile=s.profile||{};Object.assign(s.profile,{name:'Sam Rivera',email:'sam@example.com',custom:true});s.decisions={};s.history=[];" +
    "SEED.forEach((x,i)=>{const row={t:'Data Analyst',c:x[1],l:'Austin, TX',u:'https://example.com/jobs/'+x[0],ty:'job',m:'onsite'};" +
    "const dd={s:'applied',at:now-i*36e5,pct:80,as:'Sam',title:'',st:x[2]||'applied',row:row};if(x[3])dd.sent=Object.assign({at:now-i*36e5},x[3]);s.decisions[x[0]]=dd;s.history.push(x[0])});" +
    "[9300101,9300102].forEach((id,i)=>{s.decisions[id]={s:'passed',at:now-i*1000,pct:30,as:'Sam',title:'',row:{t:'Cook',c:'Pass Co '+i,l:'Austin, TX',u:'https://example.com/p/'+id,ty:'job',m:'onsite'}};s.history.push(id)});" +
    "localStorage.setItem(K,JSON.stringify(s));return 1})()");
  await nav(base); await ready(); await sleep(2500); await agree(); await sleep(300);

  // card 182: Job Tracker has one screen, the Overview, opened straight from its button (no menu); its chips filter one list
  const open = async () => { await inApp("d.getElementById('nb-dash').click();return 1"); await sleep(900); };
  const chip = async (f) => { await inApp("const b=d.querySelector('#pane-track [data-filt=" + JSON.stringify(f) + "]');if(b)b.click();return 1"); await sleep(400); };
  // every stat tile in the open Job Tracker view, as {label: number}; and the note under them
  const tiles = async () => JSON.parse(await inApp("const o={};d.querySelectorAll('#pane-track .stat').forEach(t=>{o[t.querySelector('small').textContent.trim()]=t.querySelector('b').textContent.trim()});return JSON.stringify(o)") || "{}");
  const noteText = () => inApp("const n=d.querySelector('#pane-track .stnote');return n?n.textContent:''");
  // what each row the open chip shows says happened (the tracker's own chips)
  const rowChips = async () => JSON.parse(await inApp("return JSON.stringify([...d.querySelectorAll('#pane-track .ovapps .row')].map(r=>{const c=r.querySelector('.stchip');return c?c.textContent:''}))") || "[]");

  await open();
  check("the Job Tracker button opens the Overview, no menu", (await inApp("return d.querySelector('#pane-track .overview')&&d.querySelector('.nwrap[data-k=\"dash\"] .nmenu').hidden?'y':'n'")) === "y");
  const all = await rowChips();
  check("All lists the 13 applications (10 at Applied, an interview, an offer, a rejection), not the 2 passed", all.length === 13, JSON.stringify(all));
  const to = await tiles();
  check("counts: Needs you 6 (3 to finish on their site, 3 not sent yet), Sent 3, Heard back 3, Passed 2", to["Needs you"] === "6" && to["Sent"] === "3" && to["Heard back"] === "3" && to["Passed"] === "2", JSON.stringify(to));
  check("...no \"Applications\", \"Applied\" or \"Waiting\" count that adds the hand-offs in", !("Applications" in to) && !("Applied" in to) && !("Waiting" in to), JSON.stringify(to));
  await chip("sent");
  const sent = await rowChips();
  check("the Sent chip shows exactly the 3 rows labelled Sent / Sent (by you): the test-inbox send is not among them", sent.length === 3 && sent.every((c) => c === "Sent" || c === "Sent (by you)"), JSON.stringify(sent));
  await chip("needs");
  const needs = await rowChips();
  check("Needs you shows the 3 to finish on their site and the 3 not sent yet", needs.length === 6 && needs.filter((c) => c === "Finish on their site").length === 3, JSON.stringify(needs));
  check("...and none of them has a status to set (nothing reached the employer yet)", (await inApp("return d.querySelectorAll('#pane-track .ovapps .stsel').length")) === 0);
  await chip("all");
  const n1 = String(await noteText());
  check("the 3 not sent yet and the 1 test-inbox send are said, not hidden or counted as sent",
    /^3 not sent yet\b/.test(n1) && /\b1 went to the test inbox: nothing reached the employer\.$/.test(n1), n1);
  if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await shot(path.join(SHOTS, "overview-" + (process.env.W || 1100) + ".png")); }

  // ---- a hand-off finished on the employer's site: the person clicks the row's real "Mark as applied"; it moves from Needs you to Sent ----
  const clicked = await inApp("const b=d.querySelector('#pane-track [data-act=\"markapplied\"][data-id=\"9300004\"]');if(!b)return 'no button';b.click();return 'ok'");
  await sleep(500);
  const st4 = await inApp("return (w.__uaply.S.decisions[9300004].sent||{}).status||''");
  const t3 = await tiles();
  check("clicking the Handoff Co row's Mark as applied marks it \"self\", and the counts follow: Sent 4, Needs you 5",
    clicked === "ok" && st4 === "self" && t3["Sent"] === "4" && t3["Needs you"] === "5", clicked + " " + st4 + " " + JSON.stringify(t3));

  // ---- the status field: Interview moves a sent row to Heard back, and its record is kept ----
  const set = await inApp("const s=d.querySelector('#pane-track select[data-stsel][data-id=\"9300001\"]');if(!s)return 'no select';s.value='interview';s.dispatchEvent(new Event('change',{bubbles:true}));return 'ok'");
  await sleep(500);
  const t4 = await tiles();
  const kept = await inApp("const x=w.__uaply.S.decisions[9300001];return x&&x.st==='interview'&&x.sent.status==='sent'?'y':'n'");
  check("setting a sent row's status to Interview: Sent 3, Heard back 4, and its record is kept",
    set === "ok" && t4["Sent"] === "3" && t4["Heard back"] === "4" && kept === "y", set + " " + kept + " " + JSON.stringify(t4));

  // ---- nothing outstanding: no "not sent yet" line at all ----
  await inApp("const A=w.__uaply;[9300007,9300008,9300012,9300013].forEach(id=>{A.S.decisions[id].sent={at:Date.now(),to:'X',status:'sent'}});A.save();return 1");
  await open();
  check("with nothing waiting, unanswered, failed or in the test inbox there is no line under the counts", (await noteText()) === "", await noteText());

  console.log("\n" + pass + " / " + (pass + fail));
  if (fail) process.exitCode = 1;
};
