// The "UAply has moved" page of an old address, in a real browser, and the Restore it leads to on the new one:
//   PORT=<server with UAPLY_PUBLIC_URL=https://uaply.test> NEW_PORT=<a server without it> node tools/cdp.js tools/ui-moved.js
// 1. a browser with no UAply data goes straight on to the public address (uaply.test is answered by this tool, never the network)
// 2. a browser with a profile and swipes sees Save a backup and Continue; the backup is the app's own format
// 3. on the new address ?moved=1 opens Data & privacy at Restore once, the backup from 2 restores there, and the hint leaves the address
const fs = require("fs");
const os = require("os");
const path = require("path");
const OLD = "http://127.0.0.1:" + (process.env.PORT || "18833");
const NEW = "http://127.0.0.1:" + (process.env.NEW_PORT || "18834");
const PUB = "https://uaply.test";
const KEY = "hireswipe.dev.v1";
module.exports = async ({ ev, sleep, nav, send, on }) => {
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + name + (ok || !extra ? "" : "  -> " + extra)); return ok; };
  const F = "document.querySelector('iframe').contentDocument";
  const q = (js) => ev("(()=>{try{const d=" + F + ",w=d.defaultView;" + js + "}catch(e){return 'ERR '+e.message}})()");
  const waitFor = async (js, ms, inApp) => { const end = Date.now() + (ms || 8000); let v; while (Date.now() < end) { v = inApp === false ? await ev(js) : await q(js); if (v && !String(v).startsWith("ERR") && !String(v).startsWith("JSERR")) return v; await sleep(250); } return v; };
  // the public address is answered here, so nothing leaves this computer
  on("Fetch.requestPaused", (p) => send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: 200, responseHeaders: [{ name: "Content-Type", value: "text/html" }], body: Buffer.from("<!doctype html><title>arrived</title><p>ARRIVED</p>").toString("base64") }));
  await send("Fetch.enable", { patterns: [{ urlPattern: PUB + "/*" }] });

  // 1. nothing to keep
  await nav(OLD + "/healthz");
  await send("Storage.clearDataForOrigin", { origin: OLD, storageTypes: "all" });
  await nav(OLD + "/?from=old");
  const at1 = await waitFor("location.href.startsWith('" + PUB + "')?location.href:''", 6000, false);
  check("1. no UAply data in this browser: the old address's home page goes straight on to the public one, query kept", at1 === PUB + "/?from=old", at1);

  // 1b. only details kept (a resume, a phone number) and no profile edits or swipes: still something to keep
  await nav(OLD + "/healthz");
  await send("Storage.clearDataForOrigin", { origin: OLD, storageTypes: "all" });
  await ev("localStorage.setItem(" + JSON.stringify(KEY + ".acct") + "," + JSON.stringify(JSON.stringify({ resumeName: "cv.pdf", phone: "" })) + ");1");
  await nav(OLD + "/");
  await sleep(800);
  const s1b = JSON.parse(await ev("JSON.stringify({href:location.href,keep:!!document.getElementById('keep')&&!document.getElementById('keep').hidden})"));
  check("1b. only a saved resume in this browser: the page stays and offers the backup (nothing is left behind)", s1b.href.startsWith(OLD) && s1b.keep, JSON.stringify(s1b));
  await nav(OLD + "/healthz");
  await send("Storage.clearDataForOrigin", { origin: OLD, storageTypes: "all" });

  // 2. a profile and swipes in this browser
  await nav(OLD + "/healthz");
  const seed = { profile: { custom: true, name: "Moved Tester", email: "moved.tester@example.com" }, decisions: { "job-1": "applied", "job-2": "passed" }, history: ["job-1", "job-2"], tips: false, v: 2 };
  await ev("localStorage.setItem(" + JSON.stringify(KEY) + "," + JSON.stringify(JSON.stringify(seed)) + ");localStorage.setItem(" + JSON.stringify(KEY + ".acct") + "," + JSON.stringify(JSON.stringify({ phone: "215-555-0100" })) + ");1");
  await nav(OLD + "/");
  await sleep(800);
  const st = JSON.parse(await ev("JSON.stringify({href:location.href,keep:!document.getElementById('keep').hidden,cont:document.getElementById('cont').href,h1:document.querySelector('h1').innerText})"));
  check("2. with a profile in this browser the page stays, says UAply has moved, and offers Save a backup", st.href.startsWith(OLD) && st.keep && /has moved to uaply\.test/.test(st.h1), JSON.stringify(st));
  check("2. Continue leads to the public address with the ?moved=1 hint", st.cont === PUB + "/?moved=1", st.cont);
  await ev("window.__blob=null;const c=URL.createObjectURL;URL.createObjectURL=function(b){b.text().then(t=>window.__blob=t);return c.call(URL,b)};document.getElementById('save').click();1");
  const txt = await waitFor("window.__blob||''", 4000, false);
  let bk = {}; try { bk = JSON.parse(txt); } catch (e) {}
  check("2. Save a backup makes the app's own backup file: profile, swipes and details", bk.app === "uaply" && bk.v === 1 && bk.profile && bk.profile.name === "Moved Tester" && bk.decisions && bk.decisions["job-1"] === "applied" && bk.acct && bk.acct.phone === "215-555-0100", txt.slice(0, 200));
  check("2. ...and says where it went", await ev("!document.getElementById('saved').hidden"), "the 'Saved as' line is hidden");
  const file = path.join(os.tmpdir(), "uaply-moved-" + process.pid + ".json");
  fs.writeFileSync(file, txt || "{}");

  // 3. the new address
  await nav(NEW + "/healthz");
  await send("Storage.clearDataForOrigin", { origin: NEW, storageTypes: "all" });
  await nav(NEW + "/?moved=1");
  const opened = await waitFor("return d.getElementById('aImp')&&!d.getElementById('acctSec').hidden?d.getElementById('acctSec').innerText:''", 15000);
  check("3. ?moved=1 opens Profile, Data & privacy at Restore", !!opened && /Restore/.test(opened), String(opened).slice(0, 200));
  check("3. ...with a line saying to choose the backup there", /choose that file under Restore/.test(await q("return d.getElementById('aMsg')?d.getElementById('aMsg').innerText:''")), await q("return d.getElementById('aMsg')?d.getElementById('aMsg').innerText:''"));
  check("3. the hint leaves the address (a reload does not do it again)", !/moved=/.test(await ev("location.href")), await ev("location.href"));
  const r = await send("Runtime.evaluate", { expression: F + ".getElementById('aImp')", returnByValue: false });
  await send("DOM.enable");
  await send("DOM.setFileInputFiles", { files: [file], objectId: r.result.result.objectId });
  const restored = await waitFor("return /Restored/.test((d.getElementById('aMsg')||{}).innerText||'')?d.getElementById('aMsg').innerText:''", 6000);
  check("3. the backup from the old address restores on the new one", !!restored && /Restored/.test(restored), restored);
  check("3. ...and the profile is back", /Moved Tester/.test(await ev("localStorage.getItem(" + JSON.stringify(KEY) + ")||''")), "the name is not in this browser's storage");
  fs.unlinkSync(file);
  await nav(NEW + "/?moved=1");
  await sleep(2500);
  const again = await q("return !d.getElementById('acctSec').hidden&&!!d.getElementById('aImp')");
  check("3. ?moved=1 a second time in the same browser does not open Restore again (once)", again === false, again);
  await send("Fetch.disable");
  console.log("\n" + pass + " / " + (pass + fail));
};
