// The apply wording on the card and on the Job Tracker row comes from the job's route (October 22): connected or email -> "Applies
// instantly", one-tap -> "Ready, one tap on their site", assisted or ready -> "Ready"; the server's labels ("Ready", "Ready, one tap")
// read the same; the old "Apply instantly" and "Opens employer site" never show. Starts its own dev server (no job feeds, temporary data).
//   W=390 H=844 node tools/cdp.js tools/ui-route.js        W=1280 H=800 node tools/cdp.js tools/ui-route.js
const { spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const os = require("os");
const path = require("path");
const ROOT = path.join(__dirname, "..");
const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const freePort = () => new Promise((r) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => r(p)); }); });
const TAG = "[" + (process.env.W || 1100) + "] ";

// [route field, instant, the wording]
const CASES = [
  ["connected", true, "Applies instantly"], ["email", true, "Applies instantly"], ["one-tap", false, "Ready, one tap on their site"],
  ["assisted", false, "Ready"], ["ready", false, "Ready"], ["Ready", false, "Ready"], ["Ready, one tap", false, "Ready, one tap on their site"],
  [undefined, true, "Applies instantly"], [undefined, false, "Ready"]];

module.exports = async ({ ev, sleep, nav }) => {
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + TAG + name + (ok || extra === undefined ? "" : "  -> " + extra)); };
  const port = await freePort(), base = "http://127.0.0.1:" + port, data = fs.mkdtempSync(path.join(os.tmpdir(), "uaply-route-"));
  const proc = spawn(PY, [path.join(ROOT, "serve.py"), String(port), path.join(ROOT, "dev"), "--api"], { cwd: ROOT, stdio: "ignore",
    env: Object.assign({}, process.env, { UAPLY_DATA_DIR: data, UAPLY_CONFIG_FILE: "none", UAPLY_CONFIG_JSON: '{"feeds":[],"smtp":{}}', HOST: "127.0.0.1" }) });
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  const q = (js) => ev("(()=>{try{const d=" + F + ",w=" + FW + ";" + js + "}catch(e){return 'ERR '+e.message}})()");
  try {
    let up = false;
    for (let i = 0; i < 120 && !up; i++) { try { up = (await fetch(base + "/healthz")).ok; } catch (e) {} if (!up) await sleep(250); }
    if (!up) { check("the server starts", false, "no answer"); return; }
    await nav(base + "/"); await sleep(4000);
    await q("w.localStorage.setItem((w.__uaplyKey||'uaply')+'.consent',JSON.stringify({v:9,at:Date.now()}));const A=w.__uaply;Object.assign(A.S.profile,{name:'Route Tester',email:'route@example.com',custom:true,title:'Data Analyst',skills:['SQL'],modes:{remote:true,hybrid:true,onsite:true}});A.save();return 1");
    await nav(base + "/"); await sleep(4000);
    const jobs = CASES.map((c, i) => ({ id: 960000 + i, co: "Route Co " + i, role: "Data Analyst", loc: "Remote (US)", mode: "remote", sal: [50000, 70000], yrs: 0, edu: "High school",
      skills: ["SQL"], blurb: "A made-up job for the route wording.", type: "job", jobType: "full-time", url: "https://example.com/jobs/" + i, source: "Route Co careers page",
      contact: "", apply: c[1] ? "direct" : "link", live: true, instant: c[1], route: c[0], seen: Date.now() }));
    await q("w.__uaplyJobs.add(" + JSON.stringify(jobs) + ");return 1");
    const cards = [];
    for (let i = 0; i < CASES.length; i++) {
      const id = 960000 + i;
      await q("w.__uaplyHideMore=function(j){return j.id!==" + id + "};w.__uaply.renderAll();return 1");
      await sleep(250);
      cards.push(String(await q("const c=d.querySelector('.card.top');if(!c||+c.getAttribute('data-id')!==" + id + ")return 'no card: '+(c?c.getAttribute('data-id'):'')+' '+(d.getElementById('deck')||{}).innerText.slice(0,120)+' '+JSON.stringify((()=>{const j=w.__uaply.JOBS.find(x=>x.id===" + id + ");const h0=w.__uaplyHideMore;w.__uaplyHideMore=null;const r={has:!!j,hide:j&&w.__uaplyHide(j),dec:!!w.__uaply.S.decisions[" + id + "],samples:w.__uaplyHideSamples,pct:j&&w.__uaply.evaluate(j,w.__uaply.S.profile).pct,min:w.UAplyNavApi&&0};w.__uaplyHideMore=h0;return r})());const t=c.querySelector('.facts .inst,.facts .ext');return t?t.textContent:'none'")));
    }
    CASES.forEach((c, i) => check("card, route " + JSON.stringify(c[0] === undefined ? "(none)" : c[0]) + (c[1] ? " (instant)" : "") + ": says '" + c[2] + "'", cards[i] === c[2], cards[i]));
    const html = String(await q("return d.getElementById('deck').innerHTML"));
    // the Job Tracker rows: each job saved to Applied, then the Applied list
    await q("w.__uaplyHideMore=null;const A=w.__uaply;" + JSON.stringify(jobs.map((j) => j.id)) + ".forEach((id,i)=>{A.S.decisions[id]={s:'applied',at:Date.now()-i*1000,pct:50,as:'You',title:''};A.S.history.push(id)});A.save();A.renderAll();return 1");
    await q("d.getElementById('nb-dash').click();return 1"); await sleep(400);
    await q("const b=[...d.querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='applied');if(b)b.click();return 1"); await sleep(900);
    const rows = JSON.parse(String(await q("return JSON.stringify(" + JSON.stringify(jobs.map((j) => j.id)) + ".map(id=>{const b=d.querySelector('#pane-track [data-id=\"'+id+'\"]');const r=b&&b.closest('.row');const t=r&&r.querySelector('.rtword');return t?t.textContent.replace(/^ · /,''):'none'}))")));
    CASES.forEach((c, i) => check("Job Tracker row, route " + JSON.stringify(c[0] === undefined ? "(none)" : c[0]) + ": says '" + c[2] + "'", rows[i] === c[2], rows[i]));
    const page = String(await q("return d.body.innerText"));
    check("neither the old 'Apply instantly' nor 'Opens employer site' shows anywhere", !/Apply instantly|Opens employer site/.test(page + html), (page + html).match(/Apply instantly|Opens employer site/));
  } finally {
    proc.kill();
    try { fs.rmSync(data, { recursive: true, force: true }); } catch (e) {}
    console.log("\n" + pass + " / " + (pass + fail));
    if (fail) process.exitCode = 1;
  }
};
