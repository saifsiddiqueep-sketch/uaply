// The phone apps' Back button and export buttons, in a real browser with a stand-in Capacitor (the bridge the App Store and Google Play
// builds in mobile/ put on the page). What only a real phone can show (the share sheet itself, the portrait lock, the privacy manifest in
// the bundle, Android backup) is in docs/tester-guide.md, section 7 "If you are testing the phone app".
//   W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-native-back-export.js     (SHOTS=<folder> also saves screenshots)
// 1. Android Back: closes an open menu or box first, then goes back one screen (Job Tracker, Profile), then to the job cards; on the job
//    cards the first press only asks, a second press within 2 seconds leaves the app, a press after that wait asks again. After the app's
//    frame reloads (Delete all my data, or any reload of the frame) there is still exactly one listener, so one press still only asks.
// 2. Export buttons in the app (backup JSON, applications CSV, interview .ics): written to the app's cache folder and handed to the share
//    sheet; an app without @capacitor/filesystem copies the text and says so; a closed share sheet says nothing; a failed copy says
//    nothing was saved. Never a browser download inside the app.
//    A file write that never answers is copied after 8 seconds; the share sheet itself has no time limit. Delete all my data also deletes
//    the export files from the cache folder (uaply-backup.json, uaply-applications.csv, every interview-*.ics), then reloads.
// 3. The website (no Capacitor): no Back listener, and the export buttons still download as before.
// Like Android (Capacitor 7), the app's frame gets a bridge of its own whose plugin calls are never answered (MessageHandler.java:
// "Plugin execution is allowed in Main Frame only"), so every check here also proves the app uses the top page's bridge and never the
// frame's. Device check still needed: Back on a real Android phone (docs/tester-guide.md section 7).
const PORT = process.env.PORT || "18766";
const SHOTS = process.env.SHOTS || "";
const path = require("path");
// the stand-in bridges. The top page's answers (the app runs in an iframe and finds it through window.parent, as in the real app); like
// the real bridge it keeps EVERY listener added for an event and a Back press calls each of them. The frame's bridge never answers and
// records each call in window.top.__capFrame.
const STUB = `(() => {
  let web = false; try { web = /[?&]web=1/.test(window.top.location.search); } catch (e) {}
  if (web) return;
  if (window.top !== window) {
    const flog = (window.top.__capFrame = window.top.__capFrame || []);
    const never = (what) => () => { flog.push(what); return new Promise(() => {}); };
    window.Capacitor = { __frame: true, isNativePlatform: () => true, getPlatform: () => "android", Plugins: {
      App: { addListener: never("App.addListener"), exitApp: never("App.exitApp") },
      Filesystem: { writeFile: never("Filesystem.writeFile"), deleteFile: never("Filesystem.deleteFile"), readdir: never("Filesystem.readdir") },
      Share: { share: never("Share.share") } } };
    if (window.top.__capLog) window.top.__capLog.push({ k: "frameload" });
    return;
  }
  const log = window.__capLog = [], L = window.__capL = {};
  window.__capMode = { fs: true, share: "ok" };
  const files = window.__capFiles = new Set(["interview-acme.ics", "interview-big-co.ics", "notes.txt"]);
  const FS = {
    writeFile: (o) => { log.push({ k: "write", path: o.path, dir: o.directory, enc: o.encoding, data: o.data });
      if (window.__capMode.fs === "hang") return new Promise(() => {});
      files.add(o.path); return Promise.resolve({ uri: "file:///cache/" + o.path }); },
    readdir: (o) => { log.push({ k: "readdir", path: o.path, dir: o.directory });
      return Promise.resolve({ files: [...files].map((name) => ({ name, type: "file", size: 1, mtime: 0, uri: "file:///cache/" + name })) }); },
    deleteFile: (o) => { log.push({ k: "delete", path: o.path, dir: o.directory });
      return new Promise((ok, no) => setTimeout(() => { if (files.delete(o.path)) { log.push({ k: "deleted", path: o.path }); ok(); }
        else { log.push({ k: "missing", path: o.path }); no(new Error("File does not exist")); } }, 300)); },
  };
  const plugins = {
    App: { addListener: (ev, fn) => { (L[ev] = L[ev] || []).push(fn); log.push({ k: "listen", ev }); return Promise.resolve({ remove() { L[ev] = L[ev].filter((f) => f !== fn); } }); },
           exitApp: () => { log.push({ k: "exit" }); return Promise.resolve(); } },
    Share: { share: (o) => { log.push({ k: "share", o }); const m = window.__capMode.share;
      if (m === "slow") return new Promise((ok) => setTimeout(() => { log.push({ k: "shared" }); ok({}); }, 9000));
      return m === "ok" ? Promise.resolve({}) : Promise.reject(new Error(m === "cancel" ? "Share canceled" : "No activity")); } },
  };
  Object.defineProperty(plugins, "Filesystem", { get: () => (window.__capMode.fs ? FS : undefined) });
  window.Capacitor = { isNativePlatform: () => true, getPlatform: () => "android", Plugins: plugins };
})();`;

module.exports = async ({ ev, sleep, nav, shot, logs, send }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const W = "document.querySelector('iframe').contentWindow";
  const BASE = "http://127.0.0.1:" + PORT;
  let bad = 0, total = 0;
  const check = (name, ok, extra) => { total++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const snap = async (name) => { if (SHOTS) await shot(path.join(SHOTS, name + "-" + (process.env.W || 1100) + "x" + (process.env.H || 900) + ".png")); };
  const J = async (expr) => JSON.parse(await ev("JSON.stringify(" + expr + ")"));
  const current = () => ev("(()=>{const b=" + F + ".querySelector('#bnav .nb[aria-current=true]');return b?b.id:''})()");
  const back = async () => { await ev("((window.__capL||{}).backButton||[]).forEach(f=>f({canGoBack:false}))"); await sleep(350); };
  const listeners = () => ev("((window.__capL||{}).backButton||[]).length");
  const log = (k) => J("(window.__capLog||[]).filter(x=>x.k==='" + k + "')");
  const frameCalls = () => J("window.__capFrame||[]");   // calls made to the frame's own bridge, which never answers
  // the app's frame has reloaded (W.__beforeReload set before the reload is gone)
  const reloaded = async () => { for (let i = 0; i < 60; i++) { if (!(await ev("(()=>{try{return !!" + W + ".__beforeReload}catch(e){return true}})()"))) return true; await sleep(250); } return false; };
  const toast = () => ev("[...(" + F + ").querySelectorAll('.toast')].map(t=>t.textContent).join(' | ')");
  const clearToasts = () => ev("[...(" + F + ").querySelectorAll('.toast')].forEach(t=>t.remove())");
  const menuItem = async (k, v) => {
    await ev(F + ".getElementById('nb-" + k + "').click()"); await sleep(350);
    // card 182: Job Tracker has no menu; its button opens the Overview, whose chips filter the one list
    if (k === "dash") { await ev("(()=>{const c=" + F + ".querySelector('#pane-track [data-filt=" + ({overview:'all',applied:'all',interview:'heard',accepted:'heard',rejected:'heard',passed:'passed'}[v] || "all") + "]');if(c)c.click()})()"); await sleep(700); return; }
    await ev("(()=>{const b=" + F + ".querySelector('#bnav .nwrap[data-k=" + k + "] .nitem[data-v=" + v + "]');if(b)b.click()})()"); await sleep(700);
  };
  const click = (txt) => ev("(()=>{const e=[...(" + F + ").querySelectorAll('button')].find(b=>b.offsetParent&&b.innerText.replace(/\\s+/g,' ').trim().startsWith(" + JSON.stringify(txt) + "));if(!e)return false;e.click();return true})()");
  // a browser download inside the iframe is recorded instead of saved
  const watchDownloads = () => ev("(()=>{const w=" + W + ";w.__dl=[];w.HTMLAnchorElement.prototype.click=function(){if(this.download)w.__dl.push(this.download)}})()");

  // the app is ready when a job card is on top (dev waits for its job list first; the agreement box opens after that)
  const ready = async () => {
    for (let i = 0; i < 60; i++) { if (await ev("(()=>{try{return !!(" + F + ").querySelector('.card.top')}catch(e){return false}})()")) break; await sleep(250); }
    await sleep(1200);
  };
  await send("Page.addScriptToEvaluateOnNewDocument", { source: STUB });
  await nav(BASE + "/"); await ready();

  // ---------- 1. Back ----------
  check("(the app's frame has a bridge of its own whose calls are never answered, as on Android)", await ev("!!(" + W + ".Capacitor&&" + W + ".Capacitor.__frame&&" + W + ".Capacitor!==window.Capacitor)"));
  check("the app registers one backButton listener with @capacitor/app, on the top page's bridge", (await listeners()) === 1 && (await ev("typeof window.__capL.backButton[0]")) === "function", "listeners: " + (await listeners()));
  check("...and makes no call to the frame's bridge", (await frameCalls()).length === 0, JSON.stringify(await frameCalls()));
  check("it opens on the job cards", (await current()) === "nb-svc", await current());
  // a first visit opens with the agreement box (consentFirst): Back is its "Not now", like Escape, and agrees to nothing
  if (await ev("!!" + F + ".getElementById('kitConsent')")) {
    await snap("back-agreement-box");
    await back();
    check("Back on the first-visit agreement box closes it as Not now", !(await ev("!!" + F + ".getElementById('kitConsent')")));
    check("...records no agreement and does not leave the app", !(await ev("Object.keys(" + W + ".localStorage).some(k=>/consent/i.test(k)&&/\"agent\":true/.test(" + W + ".localStorage.getItem(k)))")) && (await log("exit")).length === 0);
  }
  await clearToasts();
  await back();
  check("first Back on the job cards does not leave the app", (await log("exit")).length === 0);
  check("...it says to press Back again", /Press Back again to leave UAply/.test(await toast()), await toast());
  await snap("back-ask");
  await sleep(2300);
  await back();
  check("a second press after more than 2 seconds only asks again", (await log("exit")).length === 0);
  await back();
  check("a second press within 2 seconds leaves the app (App.exitApp)", (await log("exit")).length === 1);

  await ev(F + ".getElementById('nb-prof').click()"); await sleep(350);
  check("(a bottom-bar menu is open)", await ev("[...(" + F + ").querySelectorAll('#bnav .nmenu')].some(m=>!m.hidden)"));
  await back();
  check("Back with a bottom-bar menu open closes the menu", await ev("[...(" + F + ").querySelectorAll('#bnav .nmenu')].every(m=>m.hidden)"));
  check("...and stays on the job cards", (await current()) === "nb-svc", await current());

  await menuItem("dash", "overview");
  check("(Job Tracker is open)", (await current()) === "nb-dash", await current());
  await menuItem("prof", "data");
  check("(Data & privacy is open)", (await current()) === "nb-prof" && /Back up/.test(await ev(F + ".body.innerText")), await current());
  await back();
  check("Back from Data & privacy returns to the Job Tracker", (await current()) === "nb-dash", await current());
  await back();
  check("Back from the Job Tracker returns to the job cards", (await current()) === "nb-svc", await current());
  check("...and leaving the app was never asked for on the way", (await log("exit")).length === 1);
  await clearToasts();
  await back();
  check("on the job cards again, Back asks before leaving", /Press Back again/.test(await toast()) && (await log("exit")).length === 1);
  await sleep(2300);

  // a box: the help chat panel
  const chat = await ev("(()=>{const b=" + F + ".getElementById('uaChatBtn');if(!b)return false;b.click();return true})()"); await sleep(500);
  check("(the help panel opens)", chat && (await ev("!" + F + ".getElementById('uaChat').hidden")));
  await back();
  check("Back with the help panel open closes it", await ev(F + ".getElementById('uaChat').hidden"));
  check("...stays on the job cards and does not leave", (await current()) === "nb-svc" && (await log("exit")).length === 1);
  // the rating question has no Escape handler: Back uses its Close button
  await ev("(()=>{const n=" + F + ".getElementById('uaNudge');if(n)n.hidden=false})()");
  await back();
  check("Back with the rating question showing closes it", await ev("(" + F + ".getElementById('uaNudge')||{hidden:true}).hidden"));

  // the app's frame reloads on its own (the top page and its bridge stay): still one listener, one press still only asks
  await sleep(2300);
  await ev(W + ".__beforeReload=1;" + W + ".location.reload()"); await sleep(500); await ready();
  check("(the app's frame reloaded and the top page did not)", !(await ev(W + ".__beforeReload")) && (await ev("Array.isArray(window.__capLog)")));
  check("after the app's frame reloads there is still exactly one Back listener", (await listeners()) === 1, "listeners: " + (await listeners()));
  const exitsBefore = (await log("exit")).length;
  // the agreement box was closed with Back (Not now) earlier, so it opens again: one press closes it and leaves nothing
  if (await ev("!!" + F + ".getElementById('kitConsent')")) {
    await back();
    check("...one press on the agreement box after the reload closes it and does not leave", !(await ev("!!" + F + ".getElementById('kitConsent')")) && (await log("exit")).length === exitsBefore);
    await sleep(2300);
  }
  await clearToasts();
  await back();
  check("...and ONE press on the job cards only asks, it does not leave", (await log("exit")).length === exitsBefore && /Press Back again/.test(await toast()), await toast());
  await sleep(2300);
  await menuItem("dash", "overview");
  await menuItem("prof", "data");
  await back();
  check("...and one press from Data & privacy goes back one screen (Job Tracker), not two", (await current()) === "nb-dash", await current());
  await back();
  await sleep(2300);

  // ---------- 2. exports in the app ----------
  await menuItem("prof", "data");
  await watchDownloads();
  await ev("window.__capLog.length=0");
  check("(Download backup is there)", await click("Download backup (JSON)")); await sleep(600);
  let w = await log("write"), s = await log("share");
  check("backup: written to the app's cache folder as uaply-backup.json, UTF-8", w.length === 1 && w[0].path === "uaply-backup.json" && w[0].dir === "CACHE" && w[0].enc === "utf8", JSON.stringify(w.map((x) => [x.path, x.dir, x.enc])));
  let backupOk = false; try { backupOk = JSON.parse(w[0].data).app === "uaply"; } catch (e) {}
  check("...the file is the real backup (UAply's backup format)", backupOk);
  check("...and handed to the share sheet as that file", s.length === 1 && JSON.stringify(s[0].o.files) === JSON.stringify(["file:///cache/uaply-backup.json"]), JSON.stringify(s.map((x) => x.o)));
  check("...no browser download inside the app", (await J(W + ".__dl")).length === 0);
  await ev("window.__capLog.length=0");
  await click("Applications (CSV)"); await sleep(600);
  w = await log("write"); s = await log("share");
  check("CSV: uaply-applications.csv written to the cache folder and shared", w.length === 1 && w[0].path === "uaply-applications.csv" && w[0].dir === "CACHE" && /^"Company","Role"/.test(w[0].data) && s.length === 1, JSON.stringify(w.map((x) => x.path)));

  // the share sheet closed by the person: nothing copied, no message
  await clearToasts();
  await ev("window.__capMode.share='cancel';window.__capLog.length=0;" + W + ".__clip=[];Object.defineProperty(" + W + ".navigator,'clipboard',{configurable:true,value:{writeText:t=>{" + W + ".__clip.push(t);return Promise.resolve()}}})");
  await click("Applications (CSV)"); await sleep(600);
  check("a closed share sheet: nothing is copied and nothing is said", (await J(W + ".__clip")).length === 0 && !(await toast()), await toast());
  // the share sheet fails: the text is copied instead
  await ev("window.__capMode.share='fail';window.__capLog.length=0");
  await click("Applications (CSV)"); await sleep(600);
  check("a share sheet that fails: the CSV is copied and the message says so", (await J(W + ".__clip")).length === 1 && /Copied uaply-applications\.csv\. Paste it into a note or email/.test(await toast()), await toast());
  // a file write that never answers: the export does not hang, after about 8 seconds the text is copied and the message says so
  await clearToasts();
  await ev("window.__capMode.fs='hang';window.__capMode.share='ok';window.__capLog.length=0;" + W + ".__clip=[]");
  const t0 = Date.now();
  await click("Download backup (JSON)");
  let hangToast = "";
  while (Date.now() - t0 < 12000) { hangToast = await toast(); if (hangToast) break; await sleep(200); }
  const waited = (Date.now() - t0) / 1000;
  check("a file write that never answers: after about 8 seconds the backup is copied and the message says so", (await log("write")).length === 1 && (await log("share")).length === 0 &&
    (await J(W + ".__clip")).length === 1 && /^Copied uaply-backup\.json\. Paste it into a note or email/.test(hangToast) && waited >= 7.5 && waited < 10.5, waited.toFixed(1) + " s  " + hangToast);
  // the share sheet has no time limit: open for 9 seconds, then the person shares; nothing is copied and nothing is said
  await sleep(2600); await clearToasts();
  await ev("window.__capMode.fs=true;window.__capMode.share='slow';window.__capLog.length=0;" + W + ".__clip=[]");
  await click("Applications (CSV)"); await sleep(9600);
  check("a share sheet left open for 9 seconds is not cut short: shared, nothing copied, nothing said", (await log("share")).length === 1 && (await log("shared")).length === 1 &&
    (await J(W + ".__clip")).length === 0 && !(await toast()), await toast());

  // an app build without @capacitor/filesystem
  await clearToasts();
  await ev("window.__capMode.fs=false;window.__capMode.share='ok';window.__capLog.length=0;" + W + ".__clip=[]");
  await click("Download backup (JSON)"); await sleep(600);
  const clip = await J(W + ".__clip");
  check("without the Filesystem plugin: nothing is written or shared", (await log("write")).length === 0 && (await log("share")).length === 0);
  check("...the backup text is copied", clip.length === 1 && /"app":"uaply"/.test(clip[0]));
  check("...and the message says Copied, never Saved", /^Copied uaply-backup\.json\. Paste it into a note or email to keep it\.$/.test(await toast()) && !/Saved/i.test(await toast()), await toast());
  await snap("export-copied");
  await clearToasts();
  await ev("Object.defineProperty(" + W + ".navigator,'clipboard',{configurable:true,value:{writeText:()=>Promise.reject(new Error('denied'))}});" + W + ".document.execCommand=()=>false");
  await click("Download backup (JSON)"); await sleep(600);
  check("...and when copying fails too, it says nothing was saved", /cannot save uaply-backup\.json\. Nothing was saved\./.test(await toast()), await toast());
  check("...no browser download inside the app at any point", (await J(W + ".__dl")).length === 0);

  // Delete all my data (the app's own frame-only reload): the export files in the cache folder go too, each failed delete is ignored,
  // and the frame reloads only once every delete has answered. Then still one listener, and one press on the job cards does not leave.
  // (uaply-applications.csv is taken out first, so its delete fails as for a file never made; notes.txt is not UAply's export.)
  await clearToasts();
  await ev("window.__capMode.fs=true;window.__capMode.share='ok';window.__capFiles.delete('uaply-applications.csv');window.__capLog.length=0");
  const wiped = await ev("(()=>{" + W + ".__beforeReload=1;const d=" + F + ";const b=d.querySelector('[data-a=wipe]');if(!b)return false;b.click();const c=d.querySelector('[data-a=wipe]');if(c)c.click();return true})()");
  await reloaded(); await ready();
  check("(Delete all my data was pressed and the app's frame reloaded, the top page did not)", wiped && !(await ev(W + ".__beforeReload")) && (await ev("Array.isArray(window.__capLog)")));
  const dels = await log("delete");
  check("Delete all my data deletes uaply-backup.json, uaply-applications.csv and every interview-*.ics from the app's cache folder",
    JSON.stringify(dels.map((x) => x.path).sort()) === JSON.stringify(["interview-acme.ics", "interview-big-co.ics", "uaply-applications.csv", "uaply-backup.json"]) &&
    dels.every((x) => x.dir === "CACHE") && (await log("readdir")).some((x) => x.dir === "CACHE"), JSON.stringify(dels.map((x) => x.path + " " + x.dir)));
  check("...and nothing else in that folder", (await J("[...window.__capFiles]")).join(",") === "notes.txt", JSON.stringify(await J("[...window.__capFiles]")));
  const order = await J("window.__capLog.map(x=>x.k)");
  const lastAnswer = Math.max(order.lastIndexOf("deleted"), order.lastIndexOf("missing")), firstLoad = order.indexOf("frameload");
  check("...a delete that fails (a file never made) is ignored, and the frame reloads only after every delete has answered",
    order.filter((k) => k === "deleted" || k === "missing").length === 4 && order.includes("missing") && firstLoad > lastAnswer, JSON.stringify(order));
  check("the frame's bridge got no call at any point (Back, the exports, Delete all my data)", (await frameCalls()).length === 0, JSON.stringify(await frameCalls()));
  check("after Delete all my data there is still exactly one Back listener", (await listeners()) === 1, "listeners: " + (await listeners()));
  if (await ev("!!" + F + ".getElementById('kitConsent')")) { await back(); await sleep(2300); }
  await clearToasts();
  const exitsWipe = (await log("exit")).length;
  await back();
  check("...and ONE press on the job cards only asks, it does not leave", (await log("exit")).length === exitsWipe && /Press Back again/.test(await toast()), await toast());

  // the calendar file: an interview with a time on job 1 (a sample job), then Job Tracker > Heard back > Add to calendar
  await ev("(()=>{const w=" + W + ",K=w.__uaplyKey,a=JSON.parse(w.localStorage.getItem(K+'.acct')||'{}');a.apps=a.apps||{};a.apps['1']={when:'2030-03-04T10:30'};w.localStorage.setItem(K+'.acct',JSON.stringify(a));" +
    "w.localStorage.setItem(K,JSON.stringify({profile:{name:'Test Person'},decisions:{'1':{s:'applied',at:Date.now(),pct:80,st:'interview'}}}))})()");
  await nav(BASE + "/"); await ready();
  await menuItem("dash", "interview");
  await ev("window.__capLog.length=0");
  const ics = await click("Add to calendar"); await sleep(600);
  w = await log("write"); s = await log("share");
  check("(the interview's Add to calendar button is there)", ics);
  check("calendar: interview-<company>.ics written to the cache folder and shared", w.length === 1 && /^interview-[a-z0-9-]+\.ics$/.test(w[0].path) && w[0].dir === "CACHE" && /^BEGIN:VCALENDAR/.test(w[0].data) && /DTSTART:20300304T/.test(w[0].data) && s.length === 1, JSON.stringify(w.map((x) => x.path)));
  check("...through the top page's bridge, with no call to the frame's", (await frameCalls()).length === 0, JSON.stringify(await frameCalls()));

  // ---------- 3. the website ----------
  await nav(BASE + "/?web=1"); await ready();
  check("on the website there is no Capacitor and no Back listener", (await ev("typeof window.Capacitor")) === "undefined" && (await ev("typeof " + W + ".Capacitor")) === "undefined" && (await ev("typeof window.__capL")) === "undefined");
  await menuItem("prof", "data");
  await watchDownloads();
  await click("Download backup (JSON)"); await sleep(600);
  await click("Applications (CSV)"); await sleep(600);
  check("on the website the backup and CSV buttons still download the files", JSON.stringify(await J(W + ".__dl")) === JSON.stringify(["uaply-backup.json", "uaply-applications.csv"]), JSON.stringify(await J(W + ".__dl")));
  await snap("website-data");

  const exc = logs.filter((l) => /^EXC/.test(l));
  check("no script error on the page", exc.length === 0, exc.join(" | "));
  console.log(bad ? bad + " problem(s)" : "All good");
  console.log("");
  console.log((total - bad) + " / " + total);
};
