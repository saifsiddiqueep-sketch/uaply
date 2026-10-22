// Job Tracker counts (Trello K0QEMeQm, October 22, 2026): a hand-off that was never sent is not counted as applied.
//   PORT=<sandbox port, any job feed> W=390 H=844 node tools/cdp.js tools/ui-dashboard-split.js      (SHOTS=<folder> also saves screenshots)
// Seeds this browser with one application of every kind (sent by UAply, sent on the employer's own page, marked as applied by the person,
// hand-offs, a question only the person can answer, one waiting for the connection, a send that failed, one that went to the test inbox,
// and an interview, an offer and a rejection), then opens Job Tracker. Overview and the Applied list must show "Sent" and "To finish" as
// two counts, never one "Applied", "Applications" or "Waiting" count that adds the hand-offs in; a test-inbox send ("Sent (test)", nothing
// reached the employer) is never counted as Sent; and each count must equal the rows the Applied list labels the same way (its "Sent",
// "Sent (by you)" and "Finish on their site" chips), so the numbers and the rows can never disagree. "Mark as applied" is clicked on a
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

  const open = async (v) => {
    await inApp("d.getElementById('nb-dash').click();return 1"); await sleep(400);
    await inApp("const b=[...d.querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')===" + JSON.stringify(v) + ");if(b)b.click();return 1"); await sleep(900);
  };
  // every stat tile in the open Job Tracker view, as {label: number}; and the note under them
  const tiles = async () => JSON.parse(await inApp("const o={};d.querySelectorAll('#pane-track .stat').forEach(t=>{o[t.querySelector('small').textContent.trim()]=t.querySelector('b').textContent.trim()});return JSON.stringify(o)") || "{}");
  const noteText = () => inApp("const n=d.querySelector('#pane-track .stnote');return n?n.textContent:''");

  // ---- the Applied list: what each row says happened (the tracker's own chips) ----
  await open("applied");
  const chips = JSON.parse(await inApp("const h=[...d.querySelectorAll('#pane-track h3')].find(h=>/^Passed/.test(h.textContent));" +
    "return JSON.stringify([...d.querySelectorAll('#pane-track .row')].filter(r=>!h||(h.compareDocumentPosition(r)&Node.DOCUMENT_POSITION_PRECEDING)).map(r=>{const c=r.querySelector('.stchip');return c?c.textContent:''}))") || "[]");
  const chipSent = chips.filter((c) => c === "Sent" || c === "Sent (by you)").length, chipFinish = chips.filter((c) => c === "Finish on their site").length;
  const chipTest = chips.filter((c) => c === "Sent (test)").length, chipNotYet = chips.filter((c) => c === "Waiting to send" || c === "Needs profile" || c === "Not sent" || c === "Not sent yet").length;
  check("the Applied list has the 10 seeded applications still at Applied: 3 Sent, 3 Finish on their site, 1 Sent (test), 3 not sent (waiting, failed, a question)",
    chips.length === 10 && chipSent === 3 && chipFinish === 3 && chipTest === 1 && chipNotYet === 3, JSON.stringify(chips));
  const tl = await tiles();
  check("the Applied list's counts: Sent and To finish, each equal to its rows' chips", tl["Sent"] === String(chipSent) && tl["To finish"] === String(chipFinish), JSON.stringify(tl));
  check("...and no \"Applied\" count that adds the hand-offs in", !("Applied" in tl), JSON.stringify(tl));
  check("...Interviews, Accepted and Rejected still counted", tl["Interviews"] === "1" && tl["Accepted"] === "1" && tl["Rejected"] === "1", JSON.stringify(tl));
  const n1 = String(await noteText());
  check("...the test-inbox send is not in Sent: Sent + To finish + not sent yet + test inbox = every row at Applied",
    +tl["Sent"] + +tl["To finish"] + chipNotYet + chipTest === chips.length && tl["Sent"] === "3", JSON.stringify(tl));
  check("...and the 3 not sent yet (a question to answer, one waiting for the connection, a failed send) and the 1 test-inbox send are said, not hidden or counted as sent",
    /^3 not sent yet\b/.test(n1) && /\b1 went to the test inbox: nothing reached the employer\.$/.test(n1), n1);
  if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await shot(path.join(SHOTS, "applied-" + (process.env.W || 1100) + ".png")); }

  // ---- Overview ----
  await open("overview");
  const to = await tiles();
  check("Overview: Sent " + chipSent + " and To finish " + chipFinish + ", the same as the Applied list's rows", to["Sent"] === String(chipSent) && to["To finish"] === String(chipFinish), JSON.stringify(to));
  check("...no \"Applications\", \"Applied\" or \"Waiting\" count that adds the hand-offs in", !("Applications" in to) && !("Applied" in to) && !("Waiting" in to), JSON.stringify(to));
  check("...Interviews 1, Offers 1, Rejected 1, Passed 2", to["Interviews"] === "1" && to["Offers"] === "1" && to["Rejected"] === "1" && to["Passed"] === "2", JSON.stringify(to));
  const n2 = String(await noteText());
  check("...and the same \"3 not sent yet\" and test-inbox line", n2 === n1 && n2 !== "", n2);
  if (SHOTS) await shot(path.join(SHOTS, "overview-" + (process.env.W || 1100) + ".png"));

  // ---- a hand-off finished on the employer's site: the person clicks the row's real "Mark as applied"; it moves from To finish to Sent ----
  await open("applied");
  const clicked = await inApp("const b=d.querySelector('#pane-track [data-act=\"markapplied\"][data-id=\"9300004\"]');if(!b)return 'no button';b.click();return 'ok'");
  await sleep(500);
  const st4 = await inApp("return (w.__uaply.S.decisions[9300004].sent||{}).status||''");
  const t3l = await tiles();
  check("clicking the Handoff Co row's Mark as applied marks it \"self\", and the list's counts follow: Sent " + (chipSent + 1) + ", To finish " + (chipFinish - 1),
    clicked === "ok" && st4 === "self" && t3l["Sent"] === String(chipSent + 1) && t3l["To finish"] === String(chipFinish - 1), clicked + " " + st4 + " " + JSON.stringify(t3l));
  await open("overview");
  const t3 = await tiles();
  check("...and so does Overview", t3["Sent"] === String(chipSent + 1) && t3["To finish"] === String(chipFinish - 1), JSON.stringify(t3));

  // ---- nothing outstanding: no "not sent yet" line at all ----
  await inApp("const A=w.__uaply;[9300007,9300008,9300012,9300013].forEach(id=>{A.S.decisions[id].sent={at:Date.now(),to:'X',status:'sent'}});A.save();return 1");
  await open("overview");
  check("with nothing waiting, unanswered, failed or in the test inbox there is no line under the counts", (await noteText()) === "", await noteText());

  console.log("\n" + pass + " / " + (pass + fail));
  if (fail) process.exitCode = 1;
};
