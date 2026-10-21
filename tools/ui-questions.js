// The one-time question box, in a real browser, at the size given by W and H (run it through tools/ui-questions.py, which starts the
// servers). Answers are typed with real key presses and chosen with real taps (phone) or clicks (computer) through Chrome's input events.
const fs = require("fs");
const PORT = process.env.PORT, ID = JSON.parse(fs.readFileSync(process.env.IDS, "utf8")), W = Number(process.env.W), H = Number(process.env.H);
const PHONE = W < 700, TAG = "[" + W + "x" + H + "]";
module.exports = async ({ ev, sleep, nav, send, shot }) => {
  const snap = async (n) => { if (process.env.SHOTS) await shot(require("path").join(process.env.SHOTS, "questions-" + W + "-" + n + ".png")); };
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + TAG + " " + name + (extra ? "  | " + extra : "")); };
  const base = "http://127.0.0.1:" + PORT + "/";
  const S = (sel) => JSON.stringify(sel);
  const q = (sel, expr) => ev("(()=>{const e=" + F + ".querySelector(" + S(sel) + ");return e?(" + expr + "):null})()");
  const focus = (sel) => q(sel, "(e.focus(),e.scrollIntoView&&e.scrollIntoView({block:'center'}),true)");
  const keys = { Enter: [13, "\r"], " ": [32, " "], End: [35, ""], ArrowDown: [40, ""], ArrowUp: [38, ""], Tab: [9, ""], Escape: [27, ""] };
  async function key(k) {
    const [vk, text] = keys[k];
    const code = k === " " ? "Space" : k;
    await send("Input.dispatchKeyEvent", { type: text ? "keyDown" : "rawKeyDown", key: k, code, windowsVirtualKeyCode: vk, text: text || undefined });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code, windowsVirtualKeyCode: vk });
    await sleep(120);
  }
  const type = async (text) => { await send("Input.insertText", { text }); await sleep(150); };
  // a real tap (phone) or click (computer) in the middle of an element inside the app's frame
  async function tap(sel) {
    await q(sel, "(e.scrollIntoView({block:'center'}),true)"); await sleep(250);
    const r = await ev("(()=>{const f=document.querySelector('iframe').getBoundingClientRect(),e=" + F + ".querySelector(" + S(sel) + ");if(!e)return null;const b=e.getBoundingClientRect();return {x:f.left+b.left+b.width/2,y:f.top+b.top+b.height/2}})()");
    if (!r) return false;
    if (PHONE) {
      await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: r.x, y: r.y }] });
      await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    } else {
      await send("Input.dispatchMouseEvent", { type: "mousePressed", x: r.x, y: r.y, button: "left", clickCount: 1 });
      await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: r.x, y: r.y, button: "left", clickCount: 1 });
    }
    await sleep(300);
    return true;
  }
  // a native select or date box: the browser's own picker cannot be driven here, so its value is set the way the picker sets it
  const pick = (sel, v) => q(sel, "(e.value=" + S(v) + ",e.dispatchEvent(new Event('input',{bubbles:true})),e.dispatchEvent(new Event('change',{bubbles:true})),e.value)");
  const toast = () => ev("(()=>{const t=" + F + ".getElementById('kitToast');return t?t.innerText.replace(/\\s+/g,' ').trim():''})()");
  const swipe = (id) => ev("(()=>{const w=" + FW + ",A=w.__uaply,job=A.JOBS.find(j=>j.id===" + id + ");if(!job)return 'no job';const m=A.evaluate(job,A.S.profile);" +
    "A.S.decisions[job.id]={s:'applied',at:Date.now(),pct:m.pct,as:A.S.profile.name,title:A.S.profile.title};A.S.history.push(job.id);A.save();A.renderAll();" +
    "w.__uaplyOnDecision('applied',job,m,A.S.profile,function(){},A.S,A.save);return 'ok'})()");
  const saved = () => ev("JSON.stringify((()=>{const w=" + FW + ";return JSON.parse(w.localStorage.getItem((w.__uaplyKey||'uaply')+'.answers')||'{}')})())").then(JSON.parse);
  const fits = (sel) => ev("(()=>{const w=" + FW + ",e=" + F + ".querySelector(" + S(sel) + ");if(!e)return 'missing';const b=e.getBoundingClientRect();" +
    "const over=w.document.documentElement.scrollWidth-w.innerWidth;return b.left>=0&&b.right<=w.innerWidth+0.5&&over<=0?'ok':'left '+b.left+' right '+b.right+' of '+w.innerWidth+', page wider by '+over})()");

  // ---- the person: a profile with name and email only, the first-application agreement given --------------------------------------------
  await nav(base); await sleep(3000);
  const email = "q" + W + "@example.com";
  await ev("(()=>{const w=" + FW + ";w.localStorage.setItem((w.__uaplyKey||'uaply')+'.consent',JSON.stringify({v:2,at:Date.now()}));const A=w.__uaply;Object.assign(A.S.profile,{name:'Sam Rivera',email:'" + email + "',custom:true,title:'Data Analyst',years:1,skills:['Python','SQL']});A.save()})()");
  await nav(base); await sleep(4500);
  await ev("(()=>{const w=" + FW + ";w.__uaplyResume=function(){return {name:'Sam Rivera Resume.pdf',size:40,data:'data:application/pdf;base64,'+btoa('%PDF-1.4 Sam Rivera resume for tests %%EOF')}}})()");
  check("app loaded", await ev("!!(" + FW + ".__uaply&&" + FW + ".__uaplyOnDecision)"));

  // ---- the swipe: every kind of question, each with its own control ---------------------------------------------------------------------
  check("swipe right on Every Kind Co", (await swipe(ID["Every Kind Co|Data Analyst"])) === "ok");
  await sleep(3000);
  const head = await q("#kitAsk h2", "e.textContent");
  check("the question box opens with the employer's questions", /^8 questions from Every Kind Co$/.test(head || ""), head);
  check("while the box is open the job is marked Not sent yet (never a plain 'Applied' if the person walks away)",
    (await ev("(()=>{const x=" + FW + ".__uaply.S.decisions[" + ID["Every Kind Co|Data Analyst"] + "];return x&&x.sent?x.sent.status:'none'})()")) === "needs_answers");
  check("the box fits the screen (no sideways scrolling)", (await fits("#kitAsk form")) === "ok", await fits("#kitAsk form"));
  const kinds = await ev("JSON.stringify([..." + F + ".querySelectorAll('#kitAsk .kaF')].map(b=>b.getAttribute('data-kind')))");
  check("each kind is asked with its own control", kinds === JSON.stringify(["textarea", "search", "multi", "month", "date", "number", "select", "consent"]), kinds);
  check("the voluntary question (gender) is not asked", !(await ev(F + ".getElementById('kitAsk').innerText.toLowerCase().includes('gender')")));
  check("nothing is chosen for the person", JSON.stringify(await ev("[...(" + F + ").querySelectorAll('#kitAsk input:checked, #kitAsk [aria-selected=true]')].length")) === "0");
  check("long text counts its characters", /0 of 2000 characters/.test(await q("#kaQ0C", "e.textContent")));
  check("the long list is searchable and shows all 20 choices", (await q("#kaQ1", "e.getAttribute('role')")) === "combobox" && (await ev(F + ".querySelectorAll('#kaQ1B [role=option]').length")) === 20);
  check("the multi-select is one box per choice, with a filter (10 choices)", (await ev(F + ".querySelectorAll('#kaQ2 input[type=checkbox]').length")) === 10 && !!(await q("#kaQ2F", "true")));
  check("the month is asked as month and year", (await ev(F + ".querySelectorAll('#kaQ3W select').length")) === 2);
  check("the date is a date box", (await q("#kaQ4", "e.type")) === "date");
  check("the number shows its unit", (await q("#kaQ5U", "e.textContent")) === "hours" && (await q("#kaQ5", "e.inputMode")) === "decimal");
  check("the notice is shown to read, with its box to tick locked until it is read to the end",
    (await q("#kaQ7R", "e.scrollHeight>e.clientHeight")) && (await q("#kaQ7", "e.disabled")) === true, await q("#kaQ7H", "e.textContent"));
  check("the first question has the keyboard focus", (await ev(F + ".activeElement.id")) === "kaQ0");

  await snap("1-box");
  // nothing answered: nothing is sent, and the box says why
  await tap("#kaYes");
  check("sending with blanks is refused with a reason", /Answer every question/.test(await q("#kaMsg", "e.textContent") || ""), await q("#kaMsg", "e.textContent"));

  // long text: typed
  await focus("#kaQ0"); await type("I built a bus-times app that 300 students use.");
  check("the count follows the typing", /^46 of 2000/.test(await q("#kaQ0C", "e.textContent")), await q("#kaQ0C", "e.textContent"));
  // the long list: type to search, then Enter (keyboard) or a tap on the match (touch)
  await focus("#kaQ1"); await type("phil");
  check("typing filters the long list to the match", (await ev("[...(" + F + ").querySelectorAll('#kaQ1B [role=option]')].filter(o=>!o.hidden).map(o=>o.textContent).join()")) === "Philadelphia");
  if (PHONE) await tap("#kaQ1B [role=option]:not([hidden])"); else await key("Enter");
  check("...and choosing it fills the box", (await q("#kaQ1W", "e.getAttribute('data-v')")) === "Philadelphia" && /Chosen: Philadelphia/.test(await q("#kaQ1S", "e.textContent")));
  if (!PHONE) {      // arrow keys move through the list
    await focus("#kaQ1"); await q("#kaQ1", "(e.value='',e.dispatchEvent(new Event('input',{bubbles:true})),1)"); await type("s");
    await key("ArrowDown"); await key("ArrowDown"); await key("Enter");
    const v = await q("#kaQ1W", "e.getAttribute('data-v')");
    check("arrow keys and Enter choose from the filtered list", v === "Boston", v);
    await q("#kaQ1", "(e.value='',e.dispatchEvent(new Event('input',{bubbles:true})),1)"); await type("philadelphia"); await key("Enter");
  }
  // the multi-select: filter, then tick with a tap or the space bar
  await focus("#kaQ2F"); await type("py");
  check("the filter narrows the choices", (await ev("[...(" + F + ").querySelectorAll('#kaQ2 label')].filter(l=>!l.hidden).length")) === 1);
  await tap("#kaQ2 input[value=Python]");
  await q("#kaQ2F", "(e.value='',e.dispatchEvent(new Event('input',{bubbles:true})),1)");
  await focus("#kaQ2 input[value=SQL]"); await key(" ");
  check("Python and SQL are ticked", (await ev("[...(" + F + ").querySelectorAll('#kaQ2 input:checked')].map(c=>c.value).join()")) === "Python,SQL");
  // month and date: the browser's own pickers
  await pick("#kaQ3", "06"); await pick("#kaQ3Y", "2027"); await pick("#kaQ4", "2027-07-01");
  // the number: words are refused, then a number goes
  await focus("#kaQ5"); await type("about 20");
  await pick("#kaQ6", "Yes");
  await tap("#kaYes");
  check("words in a number box are refused, naming the unit", /Enter a number \(in hours\)/.test(await q("#kaMsg", "e.textContent") || ""), await q("#kaMsg", "e.textContent"));
  await q("#kaQ5", "(e.value='',1)"); await focus("#kaQ5"); await type("20");
  // the notice: read to the end with the keyboard (End) or a scroll, then tick
  if (PHONE) await q("#kaQ7R", "(e.scrollTop=e.scrollHeight,e.dispatchEvent(new Event('scroll')),1)");
  else { await focus("#kaQ7R"); await key("End"); }
  await sleep(300);
  check("once read to the end, the box can be ticked", (await q("#kaQ7", "e.disabled")) === false);
  if (PHONE) await tap("#kaQ7"); else { await focus("#kaQ7"); await key(" "); }
  check("...and it is ticked", (await q("#kaQ7", "e.checked")) === true);
  await q("#kaQ1", "e.scrollIntoView({block:'start'})"); await snap("2-answered");
  if (PHONE) await tap("#kaYes"); else { await focus("#kaYes"); await key("Enter"); }
  await sleep(3000);
  const t1 = await toast();
  check("with every answer, the application goes", /Applied to Every Kind Co \(test\)/.test(t1) && !(await ev("!!" + F + ".getElementById('kitAsk')")), t1);
  check("...and the Not sent yet mark is replaced by what really happened",
    (await ev("(()=>{const x=" + FW + ".__uaply.S.decisions[" + ID["Every Kind Co|Data Analyst"] + "];return x&&x.sent?x.sent.status:'none'})()")) === "delivered_test");
  const a = await saved(), vals = Object.values(a);
  check("the answers are saved on this device, in the shape the form takes", ["Philadelphia", "Python\nSQL", "2027-06", "2027-07-01", "20", "Yes", "I acknowledge"].every((v) => vals.includes(v)),
    JSON.stringify(vals).slice(0, 300));
  const rec = JSON.parse(await ev("fetch('/api/outbox').then(r=>r.text())")).applications.find((x) => x.job.co === "Every Kind Co");
  const filled = JSON.stringify((rec && rec.autofill && rec.autofill.items) || []);
  check("the employer's form was filled with them (month and date as its labels ask)", /06\/2027/.test(filled) && /07\/01\/2027/.test(filled) && /Python, SQL/.test(filled), filled.slice(0, 300));

  // ---- the same questions at another company: answered from what was saved, nothing asked ----------------------------------------------
  await swipe(ID["Second Co|Data Analyst"]); await sleep(3000);
  const t2 = await toast();
  check("another employer asking the same questions gets the saved answers, without asking", /Applied to Second Co \(test\)/.test(t2) && !(await ev("!!" + F + ".getElementById('kitAsk')")), t2);

  // ---- Profile setup, Eligibility and extras: the answers, to change or remove ---------------------------------------------------------
  await ev(FW + ".__uaplyOpenProf('final')"); await sleep(1200);
  check("Profile setup, Eligibility and extras lists 'Answers you gave employers'", /Answers you gave employers/i.test(await q("#aKept", "e.innerText") || "") && (await q("#aKept", "e.offsetParent!==null")));
  const listed = await q("#aKept", "e.innerText.replace(/\\s+/g,' ')");
  check("...each answer in words, with the employer that asked first", /June 2027/.test(listed) && /Python, SQL/.test(listed) && /20 hours/.test(listed) && /First asked by Every Kind Co/.test(listed), listed.slice(0, 400));
  check("...and it fits the screen", (await fits("#aKept")) === "ok", await fits("#aKept"));
  await q("#aKept", "e.scrollIntoView({block:'start'})"); await snap("3-profile");
  const hoursKey = Object.keys(a).find((k) => a[k] === "20");
  await tap("#aKept [data-ak=" + S(hoursKey) + "] [data-act=akedit]");
  check("Change opens the same control, filled with the answer", (await q("#aKept .kaF[data-kind=number] input", "e.value")) === "20");
  await q("#aKept .kaF[data-kind=number] input", "(e.value='',1)"); await focus("#aKept .kaF[data-kind=number] input"); await type("25");
  await tap("#aKept [data-act=aksave]");
  check("...Save keeps the new answer", (await saved())[hoursKey] === "25" && /25 hours/.test(await q("#aKept", "e.innerText")));
  const n0 = Object.keys(await saved()).length;
  await tap("#aKept [data-ak=" + S(hoursKey) + "] [data-act=akdel]");
  check("Remove forgets one answer (the next employer that asks it asks again)", Object.keys(await saved()).length === n0 - 1 && !((await saved())[hoursKey]));
  console.log(bad ? bad + " problem(s)" : "All good");
};
