// Each "Add" item in the profile checklist (Job Tracker > Overview, "Profile N% complete") must open Profile setup on the step that
// asks for it, by a real tap on a phone and a real mouse click on a desktop.
//   PORT=18796 W=390 H=844 node tools/cdp.js tools/ui-checklist.js
// (It used to open Profile > Settings and Profile > Preferences, which the guided Profile setup replaced, so it found 0 items
// and passed without checking anything. It now fails if there is nothing to check.)
const PORT = process.env.PORT || "8766";
const PHONE = Number(process.env.W || 1100) < 700;
module.exports = async ({ ev, sleep, nav, send, logs }) => {
  // the sign-in gate (October 22, Saif): nobody reaches the jobs without an account, so a fresh test person signs up first (tools/gate-signup.js)
  await require("./gate-signup.js")({ ev, sleep, nav }, "http://127.0.0.1:" + (process.env.PORT || "8767"), "checklist");
  const F = "document.querySelector('iframe').contentDocument";
  let bad = 0;
  const check = (n, ok, x) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? "  " + x : "")); };
  const STEP = { about: "About you", jobs: "Jobs you want", where: "Location and pay", back: "Background and links", final: "Eligibility and extras" };
  const press = async (p) => {
    if (PHONE) {
      await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: p.x, y: p.y, id: 1 }] }); await sleep(40);
      await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    } else {
      await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: p.x, y: p.y });
      await send("Input.dispatchMouseEvent", { type: "mousePressed", x: p.x, y: p.y, button: "left", buttons: 1, clickCount: 1 });
      await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: p.x, y: p.y, button: "left", buttons: 0, clickCount: 1 });
    }
  };
  const overview = async () => {
    await ev("(()=>{const d=" + F + ";d.getElementById('nb-dash').click()})()");
    await sleep(600);
  };
  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(3500);
  await ev("(()=>{const b=" + F + ".getElementById('kcYes');if(b){b.ownerDocument.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});b.disabled=false;b.click()}})()"); await sleep(300);
  await overview();
  const items = JSON.parse(await ev("JSON.stringify([...(" + F + ").querySelectorAll('#pane-track button[data-go]')].filter(b=>b.offsetParent&&b.innerText.trim()==='Add').map(b=>[b.parentNode.querySelector('span').innerText.trim(),b.getAttribute('data-go')]))"));
  check("the Overview lists what is missing from the profile, each with an Add button", items.length > 0, items.length + " item(s)");
  for (const [label, step] of items) {
    await overview();
    const p = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ";const b=[...d.querySelectorAll('#pane-track button[data-go]')].find(x=>x.innerText.trim()==='Add'&&x.parentNode.querySelector('span').innerText.trim()===" + JSON.stringify(label) + ");if(!b)return null;b.scrollIntoView({block:'center'});const f=document.querySelector('iframe').getBoundingClientRect(),r=b.getBoundingClientRect();return {x:f.left+r.left+r.width/2,y:f.top+r.top+r.height/2}})())"));
    if (!p) { check("Add for \"" + label + "\" is on the Overview", false); continue; }
    await press(p); await sleep(700);
    const at = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ";const s=d.getElementById('pane-profile');const cur=d.querySelector('.wzDots button[aria-current=step]');return {open:!!s&&!s.hidden,label:d.getElementById('nb-prof').innerText.replace(/\\s+/g,' ').trim(),step:cur?cur.getAttribute('aria-label'):''}})())"));
    check((PHONE ? "tapping" : "clicking") + " Add for \"" + label + "\" opens Profile setup on " + STEP[step], at.open && at.step.indexOf(STEP[step]) > -1, JSON.stringify(at));
  }
  check("no script errors", logs.length === 0, logs.join(" / ").slice(0, 200));
  console.log(bad ? bad + " problem(s)" : "All good");
};
