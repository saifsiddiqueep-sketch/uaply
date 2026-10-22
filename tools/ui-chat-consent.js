// The Help chat asks before anything goes to the outside AI company, and a "No" on an answer reports the answer's own words (Trello
// KWU4HK73, Apple guideline 5.1.2(i)). AI answers are switched on in the browser by answering /api/chat/config; /api/chat and /api/feedback
// are answered here too and every body is kept, so the test sees exactly what the page sends. Nothing reaches a real AI.
//   1. the notice names the AI company exactly as legal/privacy.html does (that page is the one source of the name), and links it
//   2. nothing is sent before Yes: not the typed question, not a starter question, and not after No
//   3. a question answered No is never sent later (it is not kept in the chat's history)
//   4. Yes sends one message (aiOk: true), is remembered on this device, and the next question (and the next visit) goes without asking
//   5. the Privacy Policy cannot be reached, or the request stalls: within 3 seconds the notice still asks first and points to the Privacy
//      Policy instead of a name (a stalled lookup used to lock the chat); a Yes there sends that one question, the named line comes next time
//   6. "No" on an answer sends the answer's text with the person's note (typed note, Skip, Talk to a person), so an offensive answer can be reported
//   7. the remembered Yes counts only for the company it named: an older yes (a bare time) or a different company asks again
//   8. "Stop sending to the AI" takes the Yes back; Yes and No look the same (the choice is not nudged)
//   9. the chat's settings (/api/chat/config) are slow or fail: a stored yes that does not count (another company, the unnamed line) never
//      goes out as aiOk: true, a yes to the named company still counts, and a question asked before the settings came never reaches the
//      AI company later (the first message after Yes holds that one question only)
//   W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-chat-consent.js       (SHOTS=<folder> also saves the notice and the report)
const fs = require("fs");
const path = require("path");
const PORT = process.env.PORT, SHOTS = process.env.SHOTS || "";
module.exports = async ({ ev, sleep, nav, send, on, shot, logs }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  const base = "http://127.0.0.1:" + PORT + "/";
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + name + (ok || extra === undefined ? "" : "  | " + extra)); };
  const inApp = (js) => ev("(()=>{try{const d=" + F + ",w=" + FW + ";" + js + "}catch(e){return 'ERR '+e.message}})()");
  const waitFor = async (js, ms) => { const end = Date.now() + (ms || 8000); let v; while (Date.now() < end) { v = await inApp(js); if (v && !String(v).startsWith("ERR")) return v; await sleep(200); } return v; };
  const size = (process.env.W || 1100) + "x" + (process.env.H || 900);

  // the company's name as the Privacy Policy writes it ("our AI provider, X, to write the reply"), read from the file itself
  const privacy = fs.readFileSync(path.join(__dirname, "..", "legal", "privacy.html"), "utf8");
  const NAME = (/our AI provider, ([^,<]+),/.exec(privacy) || [])[1] || "";
  check("the Privacy Policy names the AI company (the one source of the name)", !!NAME);

  const ANSWER = "STAND-IN ANSWER " + Date.now() + ": the exact words the AI wrote, rude ones included.";
  const chats = [], reports = [];
  let policy = "ok";   // the Privacy Policy request: "ok", "down" (the request fails) or "stall" (no answer at all)
  let config = "ok";   // the chat's settings: "ok" (AI on), "hold" (no answer until released) or "fail" (503)
  const held = [], heldCfg = [];
  const ARTICLES = "HELP-ARTICLE ANSWER: nothing left UAply.";
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/chat*", requestStage: "Request" }, { urlPattern: "*/api/feedback*", requestStage: "Request" },
    { urlPattern: "*/legal/privacy.html*", requestStage: "Request" }] });
  on("Fetch.requestPaused", (p) => {
    const u = p.request.url, id = p.requestId;
    const json = (o) => send("Fetch.fulfillRequest", { requestId: id, responseCode: 200, responseHeaders: [{ name: "Content-Type", value: "application/json" }], body: Buffer.from(JSON.stringify(o)).toString("base64") });
    const body = () => { try { return JSON.parse(p.request.postData || "{}"); } catch (e) { return { unreadable: p.request.postData }; } };
    if (/\/legal\/privacy\.html/.test(u)) {
      if (policy === "stall") { held.push(id); return; }
      return policy === "down" ? send("Fetch.failRequest", { requestId: id, errorReason: "ConnectionRefused" }) : send("Fetch.continueRequest", { requestId: id });
    }
    if (/\/api\/chat\/config/.test(u)) {
      if (config === "hold") { heldCfg.push(() => json({ ai: true, support: "", articles: 3 })); return; }
      if (config === "fail") return send("Fetch.fulfillRequest", { requestId: id, responseCode: 503, responseHeaders: [], body: "" });
      return json({ ai: true, support: "", articles: 3 });
    }
    // like chat_api.py with AI on: without aiOk: true the help articles answer (aiConsent: true) and nothing goes to the AI company
    if (/\/api\/chat/.test(u)) { const b = body(); chats.push(b);
      return json(b.aiOk === true ? { answer: ANSWER, ai: true, sources: [{ id: "apply", title: "Applying" }] } : { answer: ARTICLES, ai: false, aiConsent: true, sources: [], related: [] }); }
    if (/\/api\/feedback/.test(u)) { reports.push(body()); return json({ ok: true, id: "t" + reports.length, delivery: "saved" }); }
    return send("Fetch.continueRequest", { requestId: id });
  });

  const openApp = async () => {
    await nav(base); await sleep(3500);
    await waitFor("return !!d.getElementById('uaChatBtn')", 10000);
    if (await inApp("return !!d.getElementById('kcYes')")) { await inApp("d.getElementById('kcYes').click();return 1"); await sleep(400); }
    await inApp("const b=d.getElementById('uaChatBtn');if(b.getAttribute('aria-expanded')!=='true')b.click();return 1");
    return waitFor("return !d.getElementById('uaChat').hidden&&d.getElementById('uaChatTag').textContent==='AI'");
  };
  const chip = (label) => inApp("const b=[...d.querySelectorAll('#uaChat .chips button')].reverse().find(b=>b.offsetParent&&b.textContent.trim()===" + JSON.stringify(label) + ");if(!b)return 'none';b.click();return 'ok'");
  const hasChip = (label) => "return !![...d.querySelectorAll('#uaChat .chips button')].find(b=>b.offsetParent&&b.textContent.trim()===" + JSON.stringify(label) + ")";
  const lastBot = () => inApp("const m=[...d.querySelectorAll('#uaChat .bot')];return m.length?m[m.length-1].innerText:''");
  const type = (text) => inApp("const i=d.getElementById('uaChatIn');i.value=" + JSON.stringify(text) + ";d.getElementById('uaChatF').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));return 1");
  const KEY = "(w.__uaplyKey||'uaply')+'.chat'";
  const stored = () => inApp("try{return JSON.stringify((JSON.parse(w.localStorage.getItem(" + KEY + "))||{}).aiOk||null)}catch(e){return 'null'}").then((v) => { try { return JSON.parse(v); } catch (e) { return null; } });
  const said = async () => { const a = await stored(); return !!(a && a.to === NAME); };   // a standing yes, to the named company
  const setStored = (v) => inApp("const s=JSON.parse(w.localStorage.getItem(" + KEY + ")||'{}');s.aiOk=" + JSON.stringify(v) + ";w.localStorage.setItem(" + KEY + ",JSON.stringify(s));return 1");
  const answered = (n) => waitFor("return [...d.querySelectorAll('#uaChat .bot')].filter(m=>m.innerText.includes(" + JSON.stringify(ANSWER) + ")).length>=" + n);
  const waitChats = async (n) => { for (let i = 0; i < 30 && chats.length < n; i++) await sleep(200); };
  const waitReports = async (n) => { for (let i = 0; i < 30 && reports.length < n; i++) await sleep(200); };
  const userMsgs = (c) => ((c || {}).messages || []).filter((m) => m.role === "user").map((m) => m.content);
  const consentShown = () => waitFor(hasChip("Yes, send it"));

  // ---- the Privacy Policy request stalls (a weak network): the chat is not locked, the notice comes within 3 seconds ----
  policy = "stall";
  check("AI answers on: the panel says AI", await openApp());
  const t0 = Date.now();
  await type("What does UAply do with my data?");
  const c00 = await waitFor(hasChip("Yes, send it"), 6000), ms = Date.now() - t0, n00 = String(await lastBot());
  check("5. the Privacy Policy request stalls: within about 3 s the notice asks first, points to the Privacy Policy, and has its buttons",
    c00 === true && ms < 4500 && /named in our Privacy Policy/.test(n00) && !(await inApp("return !!d.querySelector('#uaChat .typing')")) && (await inApp(hasChip("No, don't send"))) === true && chats.length === 0,
    ms + " ms | " + n00 + " | sent " + chats.length);
  check("8. Yes and No look the same (neither is the filled button)",
    (await inApp("return [...d.querySelectorAll('#uaChat .chips button')].filter(b=>b.offsetParent&&/^(Yes, send it|No, don.t send)$/.test(b.textContent.trim())&&!b.classList.contains('pri')).length")) === 2);
  await chip("No, don't send"); await sleep(500);
  check("2. No sends nothing, and nothing is remembered as a yes", chats.length === 0 && !(await stored()) && /Nothing was sent/.test(String(await lastBot())), "sent " + chats.length);

  // ---- the Privacy Policy cannot be reached: still asks first; a Yes sends that one question but is not a standing yes ----
  policy = "down";
  await type("Where is my profile stored?");
  const c0 = await consentShown(), n0 = String(await lastBot());
  check("5. the Privacy Policy unreachable: the notice still asks first and points to the Privacy Policy", c0 === true && /named in our Privacy Policy/.test(n0) && chats.length === 0, n0 + " | sent " + chats.length);
  await chip("Yes, send it");
  await waitChats(1); await answered(1);
  check("5. ...Yes there sends that one question (aiOk: true)", chats.length === 1 && chats[0].aiOk === true && JSON.stringify(userMsgs(chats[0])) === '["Where is my profile stored?"]', JSON.stringify(chats));
  check("7. ...but it is not a yes to a named company, so it is not remembered as one (no Stop link either)", !(await said()) && !(await inApp("return !!d.getElementById('uaChatStopAi')")), JSON.stringify(await stored()));

  // ---- the notice names the company, from the Privacy Policy ----
  policy = "ok";
  await type("How do I apply?");   // typed: after an answer the chips are the answer's own, not the starters
  const c1 = await consentShown(), n1 = String(await lastBot());
  check("1. the next question shows the named notice: the AI company exactly as the Privacy Policy names it", c1 === true && n1.includes("our AI provider, " + NAME + ".") && /Send it\?/.test(n1), n1);
  const link = await inApp("const a=[...d.querySelectorAll('#uaChat .bot a[data-privacy]')].pop();return a?a.href:''");
  check("...and links the Privacy Policy, which opens", /\/legal\/privacy\.html$/.test(link) && (await ev("fetch(" + JSON.stringify(link) + ").then(r=>r.status)")) === 200, link);
  check("2. nothing is sent while the notice waits", chats.length === 1, "sent " + chats.length);
  await type("Can I type past the notice?");
  check("...and typing past the notice sends nothing either (the notice asks again)", (await consentShown()) === true && chats.length === 1, "sent " + chats.length);
  if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await shot(path.join(SHOTS, "consent-" + size + ".png")); }
  await chip("Yes, send it");
  await waitChats(2); await answered(2);
  const sent = chats[1] || {}, msgs = userMsgs(sent);
  check("4. Yes sends one message, marked aiOk: true", chats.length === 2 && sent.aiOk === true, JSON.stringify(chats));
  check("3. ...holding only questions said Yes to: the questions answered No never go out", JSON.stringify(msgs) === '["Where is my profile stored?","Can I type past the notice?"]' && !msgs.some((m) => /do with my data|How do I apply/.test(m)), JSON.stringify(msgs));
  check("4. ...and the Yes is remembered on this device, for the company it named", await said(), JSON.stringify(await stored()));
  check("8. ...and the footer now offers 'Stop sending to the AI' (a 44 px target)", (await inApp("const b=d.getElementById('uaChatStopAi');return !!(b&&b.offsetParent&&b.getBoundingClientRect().height>=44)")) === true);

  // ---- No on the answer: the report carries the answer's words and the note (typed path) ----
  await chip("No");
  await waitFor(hasChip("Skip"));
  if (SHOTS) await shot(path.join(SHOTS, "report-" + size + ".png"));   // the prompt saying the note and the answer go to the team
  await type("That answer was rude.");
  await waitReports(1);
  const r1 = reports[0] || {};
  check("6. No, then a note: the report has the answer's own words and the note", r1.topic === "answer" && r1.helpful === false && String(r1.text).includes(ANSWER) && String(r1.text).includes("That answer was rude."), JSON.stringify(r1));
  check("...and still names the help article", JSON.stringify(r1.articles) === '["apply"]', JSON.stringify(r1.articles));

  // ---- the next question goes without asking; No, then Skip still reports the answer ----
  await type("How do I set up my profile?");
  await waitChats(3); await answered(3);
  check("4. after Yes, the next question goes without the notice", chats.length === 3 && chats[2].aiOk === true, "sent " + chats.length);
  await chip("No"); await waitFor(hasChip("Skip")); await chip("Skip");
  await waitReports(2);
  check("6. No, then Skip: the report still has the answer's own words", String((reports[1] || {}).text).includes(ANSWER), JSON.stringify(reports[1]));

  // ---- No, then Talk to a person: the report still has the answer's words ----
  await type("Why don't I see any jobs?");
  await waitChats(4); await answered(4);
  await chip("No"); await waitFor(hasChip("Talk to a person")); await chip("Talk to a person");
  await waitReports(3);
  const r3 = reports[2] || {};
  check("6. No, then Talk to a person: the report has the answer's own words", chats.length === 4 && r3.topic === "answer" && r3.helpful === false && String(r3.text).includes(ANSWER), JSON.stringify(r3));

  // ---- the next visit: remembered ----
  await openApp();
  await chip("How do I apply?");
  await waitChats(5);
  check("4. a new visit on this device: the question goes without asking again", chats.length === 5 && !(await inApp(hasChip("Yes, send it"))), "sent " + chats.length);

  // ---- an older yes (a bare time, from the unnamed "Continue" line) asks again, naming the company ----
  await setStored(Date.now() - 86400000);
  await openApp();
  await chip("How do I apply?");
  const c7 = await consentShown(), n7 = String(await lastBot());
  check("7. an older yes that named no company: the named notice is shown again and nothing is sent", c7 === true && n7.includes("our AI provider, " + NAME + ".") && chats.length === 5, n7 + " | sent " + chats.length);
  await chip("Yes, send it"); await waitChats(6); await answered(1);
  check("7. ...Yes sends it and now remembers the company", chats.length === 6 && (await said()), "sent " + chats.length);

  // ---- Stop sending to the AI ----
  await inApp("d.getElementById('uaChatStopAi').click();return 1"); await sleep(400);
  check("8. Stop sending to the AI: the yes is gone, the link too, and the chat says so", !(await stored()) && !(await inApp("return !!d.getElementById('uaChatStopAi')")) && /Nothing more goes to our AI provider/.test(String(await lastBot())), String(await lastBot()));
  await type("Can I change my plan?");
  check("8. ...the next question asks first again and sends nothing", (await consentShown()) === true && chats.length === 6, "sent " + chats.length);
  await chip("No, don't send"); await sleep(400);

  // ---- a yes given to a different company asks again (the Privacy Policy changed provider) ----
  await setStored({ at: Date.now(), to: "Some Other AI Co" });
  await openApp();
  await chip("How do I apply?");
  const c8 = await consentShown(), n8 = String(await lastBot());
  check("7. a yes given to a different company: the notice names the current one and nothing is sent", c8 === true && n8.includes("our AI provider, " + NAME + ".") && chats.length === 6, n8 + " | sent " + chats.length);
  await chip("No, don't send"); await sleep(400);
  check("7. ...No there removes the old yes", !(await stored()) && chats.length === 6, JSON.stringify(await stored()));

  // ---- 9. the chat's settings are slow or fail (CTO round 2: a stored yes that did not count went out as aiOk: true, no notice) ----
  const openEarly = async () => {   // open the panel without waiting for the settings
    await nav(base); await sleep(3500);
    await waitFor("return !!d.getElementById('uaChatBtn')", 10000);
    if (await inApp("return !!d.getElementById('kcYes')")) { await inApp("d.getElementById('kcYes').click();return 1"); await sleep(400); }
    await inApp("const b=d.getElementById('uaChatBtn');if(b.getAttribute('aria-expanded')!=='true')b.click();return 1");
    return waitFor(hasChip("How do I apply?"));
  };
  const releaseCfg = async () => { while (heldCfg.length) await Promise.resolve().then(heldCfg.shift()).catch(() => {}); };
  const aiPosts = (from) => chats.slice(from).filter((c) => c.aiOk === true).length;
  for (const [mode, val, label] of [["hold", { at: Date.now(), to: "Some Other AI Co" }, "a yes to another company"],
    ["hold", { at: Date.now(), to: "" }, "a yes to the unnamed line"], ["fail", { at: Date.now(), to: "Some Other AI Co" }, "a yes to another company"],
    ["fail", { at: Date.now(), to: "" }, "a yes to the unnamed line"]]) {
    config = "ok"; await openApp(); await setStored(val);
    config = mode; const from = chats.length;
    check("9. settings " + (mode === "hold" ? "not arrived" : "failed") + ", " + label + " stored: the panel opens with the starters", (await openEarly()) === true);
    await chip("How do I apply?");
    await waitChats(from + 1); await sleep(600);
    const c = chats[from] || {};
    check("9. ...a starter tapped: nothing goes out as aiOk: true (the question is answered from the help articles)",
      aiPosts(from) === 0 && chats.length === from + 1 && c.aiOk === false && JSON.stringify(userMsgs(c)) === '["How do I apply?"]',
      JSON.stringify(chats.slice(from)));
    check("9. ...and the yes that does not count is not kept", !(await stored()), JSON.stringify(await stored()));
    await releaseCfg();
  }
  // a question asked before the settings came, then Yes: the first message to the AI company holds the new question only
  config = "ok"; await openApp(); await setStored(null);
  config = "hold"; await openEarly();
  const fromH = chats.length;
  await chip("How do I apply?"); await waitChats(fromH + 1); await waitFor("return [...d.querySelectorAll('#uaChat .bot')].some(m=>m.innerText.includes(" + JSON.stringify(ARTICLES) + "))");
  check("9. AI found on after an early question (the server said aiConsent): the panel now says AI", (await waitFor("return d.getElementById('uaChatTag').textContent==='AI'")) === true);
  await releaseCfg(); config = "ok";
  await type("Can I change my plan?");
  check("9. ...the next question asks first", (await consentShown()) === true && chats.length === fromH + 1, "sent " + (chats.length - fromH));
  await chip("Yes, send it"); await waitChats(fromH + 2);
  const first = chats[fromH + 1] || {};
  check("9. ...Yes: the first message to the AI holds that one question only (the earlier one stays on UAply)",
    first.aiOk === true && JSON.stringify((first.messages || []).map((m) => m.content)) === '["Can I change my plan?"]', JSON.stringify(first));
  // a yes to the named company still counts while the settings are slow
  config = "hold"; await openEarly();
  const fromN = chats.length;
  await chip("How do I apply?"); await waitChats(fromN + 1);
  check("9. settings not arrived, a yes to the named company: it still counts (one message, aiOk: true, no notice)",
    chats.length === fromN + 1 && chats[fromN].aiOk === true && !(await inApp(hasChip("Yes, send it"))) && (await said()), JSON.stringify(chats.slice(fromN)));
  await releaseCfg(); config = "ok";

  const problems = await ev("(()=>{const t=(document.body.innerText||'')+' '+((" + F + ")&&(" + F + ").body?(" + F + ").body.innerText:'');return (t.match(/patch target not found|Problem: [^\\n]*/i)||[''])[0]})()");
  check("no 'patch target not found' or Problem: on the page", !problems, problems);
  check("no console errors or page exceptions", !logs.length, logs.join(" | "));
  for (const id of held) await send("Fetch.failRequest", { requestId: id, errorReason: "Aborted" }).catch(() => {});
  await releaseCfg().catch(() => {});
  await send("Fetch.disable");
  console.log("\n" + pass + " / " + (pass + fail));
  if (fail) process.exitCode = 1;
};
