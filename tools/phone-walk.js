// The phone walk: every screen a student uses, on a real Android phone's Chrome, with real touches, a screenshot of each screen and
// a fit check of each (cut off, sideways scrolling, small targets, things under the keyboard or the bottom bar, collisions, modals taller
// than the screen). Run before every release on the sandbox, dev and the live site (RELEASE checklist):
//   node tools/phone-walk.js sandbox            a local sandbox server (temp data, real job feeds, a stand-in mail server): the full walk,
//                                               sign-up with a code from the stand-in inbox, swipes, the offline screen
//   node tools/phone-walk.js dev                the same against a local dev (release build) server
//   node tools/phone-walk.js live               https://uaply.net, read only: screens and fit checks, no swipes, no sign-up, no form sent
// Options (environment): ADB=<path to adb> (else adb on PATH), SERIAL=<device> (else the only one plugged in), OUT=<folder> (else
// phone-walk/<target>-<time>/), PORT=<local server port> (else 18990 / 18991). Needs USB debugging on the phone and Chrome on it. It touches
// only Chrome: it opens one tab with UAply in it and leaves the phone's other tabs alone. It installs nothing and changes no phone setting.
// Landscape is checked by emulating the turned screen in that same tab (turning the phone would mean changing its rotation setting).
// Prints a FAIL line per fit problem and a summary; exits 1 if any.
const { execFileSync, spawn, spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const ROOT = path.dirname(__dirname);

// ------------------------------------------------------------------ the launcher (node tools/phone-walk.js <target>) -------------------
if (require.main === module) {
  const target = process.argv[2] || "sandbox";
  if (!["sandbox", "dev", "live"].includes(target)) { console.log("usage: node tools/phone-walk.js sandbox|dev|live"); process.exit(2); }
  const ADB = process.env.ADB || "adb";
  const adbRaw = (args, opts) => execFileSync(ADB, args, Object.assign({ encoding: "utf8", timeout: 30000 }, opts || {}));
  let serial = process.env.SERIAL;
  if (!serial) {
    const devs = adbRaw(["devices"]).split(/\r?\n/).slice(1).map((l) => l.trim().split(/\s+/)).filter((x) => x[1] === "device").map((x) => x[0]);
    if (devs.length !== 1) { console.log("FAIL plug in exactly one phone with USB debugging on (found " + devs.length + "), or set SERIAL"); process.exit(1); }
    serial = devs[0];
  }
  const adb = (...a) => adbRaw(["-s", serial, ...a]);
  const stamp = new Date().toISOString().replace(/[:T]/g, "-").slice(0, 16);
  const OUT = process.env.OUT || path.join(ROOT, "phone-walk", target + "-" + stamp);
  fs.mkdirSync(OUT, { recursive: true });
  const kids = [];
  let url = "https://uaply.net/", port = 0, mailFile = "", dataDir = "";
  const stopKids = () => { for (const k of kids) { try { k.kill(); } catch (e) {} } };
  process.on("exit", stopKids);
  const waitFor = (u, ms) => { const end = Date.now() + ms; while (Date.now() < end) { const r = spawnSync(process.execPath, ["-e", "fetch(" + JSON.stringify(u) + ").then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]); if (r.status === 0) return true; spawnSync(process.execPath, ["-e", "setTimeout(()=>{},300)"]); } return false; };
  if (target !== "live") {
    port = Number(process.env.PORT || (target === "sandbox" ? 18990 : 18991));
    const mailPort = port + 100;
    dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "uaply-phone-"));
    mailFile = path.join(dataDir, "mail.jsonl");
    kids.push(spawn("python", [path.join(ROOT, "tools", "fake-smtp.py"), String(mailPort), mailFile], { stdio: "ignore" }));
    const cfg = { feeds: ["greenhouse", "lever", "ashby"], delivery: "test", owner_copy: "", google: {},
      smtp: { host: "127.0.0.1", port: mailPort, starttls: false, from_addr: "uaply@example.com" } };
    const env = Object.assign({}, process.env, { UAPLY_DATA_DIR: path.join(dataDir, "data"), UAPLY_CONFIG_FILE: "none", UAPLY_CONFIG_JSON: JSON.stringify(cfg) });
    delete env.UAPLY_PUBLIC_URL; delete env.HOST;
    const srv = spawn("python", [path.join(ROOT, "serve.py"), String(port), path.join(ROOT, target), "--api"], { env, stdio: ["ignore", "ignore", fs.openSync(path.join(OUT, "server.log"), "w")] });
    kids.push(srv); process.env.WALK_SERVER_PID = String(srv.pid);
    if (!waitFor("http://127.0.0.1:" + port + "/healthz", 30000)) { console.log("FAIL the local " + target + " server did not start (see " + OUT + "/server.log)"); process.exit(1); }
    adb("reverse", "tcp:" + port, "tcp:" + port);
    url = "http://localhost:" + port + "/";
  }
  // the DevTools forward may already be there (another tool on this computer uses the phone too): set it only if missing, and remove only
  // what this run set up (its own server's port, and the forward if it made it)
  const hadForward = /tcp:9222 localabstract:chrome_devtools_remote/.test(adbRaw(["forward", "--list"]));
  if (!hadForward) adb("forward", "tcp:9222", "localabstract:chrome_devtools_remote");
  adb("shell", "input", "keyevent", "KEYCODE_WAKEUP");
  try { adb("shell", "wm", "dismiss-keyguard"); } catch (e) {}
  adb("shell", "am", "start", "-n", "com.android.chrome/com.google.android.apps.chrome.Main", "-a", "android.intent.action.VIEW", "-d", url);
  spawnSync(process.execPath, ["-e", "setTimeout(()=>{},4000)"]);
  const env = Object.assign({}, process.env, { CDP_ATTACH: "127.0.0.1:9222", CDP_TAB: url.replace(/^https?:\/\//, "").replace(/\/$/, ""), CDP_OPEN: url,
    CDP_LIMIT_MS: "1500000", WALK_TARGET: target, WALK_URL: url, WALK_OUT: OUT, WALK_SERIAL: serial, ADB, WALK_MAIL: mailFile, WALK_PORT: String(port) });
  const r = spawnSync(process.execPath, [path.join(ROOT, "tools", "cdp.js"), __filename], { env, stdio: "inherit" });
  if (port) { try { adb("reverse", "--remove", "tcp:" + port); } catch (e) {} }
  if (!hadForward) { try { adb("forward", "--remove", "tcp:9222"); } catch (e) {} }
  stopKids();
  console.log("screenshots: " + OUT);
  process.exit(r.status || 0);
}

// ------------------------------------------------------------------ the walk (run by tools/cdp.js, attached to the phone's tab) --------
const T = process.env.WALK_TARGET, URL = process.env.WALK_URL, OUT = process.env.WALK_OUT, SERIAL = process.env.WALK_SERIAL, ADB = process.env.ADB;
const LIVE = T === "live";
const adb = (...a) => execFileSync(ADB, ["-s", SERIAL, ...a], { encoding: "utf8", timeout: 30000 });
const F = "document.querySelector('iframe')";

// the fit checks, run in a document (the page and the app's frame): returns a list of problems in plain words
const FIT = String.raw`(doc,label)=>{const w=doc.defaultView,out=[],vw=w.innerWidth,ih=w.innerHeight,vv=w.visualViewport,vh=vv?vv.height:ih,vt=vv?vv.offsetTop:0,kb=vh<ih*0.85;
  const shown=e=>{if(!e.getClientRects().length)return false;for(let x=e;x&&x.nodeType===1;x=x.parentElement){const s=w.getComputedStyle(x);if(s.visibility==='hidden'||+s.opacity===0||s.display==='none'||x.inert||x.getAttribute('aria-hidden')==='true')return false}return true};
  /* the part of an element that can be seen: its box cut by every scrolling or clipping box around it and by the screen */
  const seen=e=>{let r=e.getBoundingClientRect(),L=r.left,R=r.right,Tp=r.top,B=r.bottom;for(let x=e.parentElement;x&&x!==doc.documentElement;x=x.parentElement){const s=w.getComputedStyle(x);if(/(hidden|auto|scroll|clip)/.test(s.overflowX+s.overflowY)){const c=x.getBoundingClientRect();L=Math.max(L,c.left);R=Math.min(R,c.right);Tp=Math.max(Tp,c.top);B=Math.min(B,c.bottom)}}
    L=Math.max(L,0);R=Math.min(R,vw);Tp=Math.max(Tp,vt);B=Math.min(B,vt+vh);return R-L>1&&B-Tp>1?{l:L,r:R,t:Tp,b:B}:null};
  const hits=(e,x,y)=>{const t=doc.elementFromPoint(x,y);return !!t&&(t===e||e.contains(t))};
  /* how far a finger can land from the middle and still reach it, up and down and sideways (an invisible ::after counts, as it does for a finger) */
  const reach=(e,s)=>{const cx=(s.l+s.r)/2,cy=(s.t+s.b)/2;if(!hits(e,cx,cy))return null;let up=0,dn=0,lf=0,rt=0;for(let k=1;k<=22&&hits(e,cx,cy-k);k++)up=k;for(let k=1;k<=22&&hits(e,cx,cy+k);k++)dn=k;for(let k=1;k<=22&&hits(e,cx-k,cy);k++)lf=k;for(let k=1;k<=22&&hits(e,cx+k,cy);k++)rt=k;return {h:up+dn+1,w:lf+rt+1}};
  const name=e=>{const t=/^(INPUT|TEXTAREA|SELECT)$/.test(e.tagName)?(e.getAttribute('aria-label')||e.getAttribute('placeholder')||e.id||e.type):(e.innerText||e.getAttribute('aria-label')||e.id||e.tagName);return (t+'').replace(/\s+/g,' ').trim().slice(0,28)};   /* never what a person typed */
  const meta=doc.querySelector('meta[name=viewport]');if(!meta||!/width=device-width/.test(meta.content))out.push(label+': no viewport meta with width=device-width (Chrome would zoom out and enlarge text by itself)');
  if(doc.documentElement.scrollWidth>vw+1)out.push(label+': the page scrolls sideways ('+doc.documentElement.scrollWidth+' > '+vw+' px)');
  const inter=[...doc.querySelectorAll('a[href],button,input,select,textarea,summary,[role=button],label.toggle,.nb,.nitem')].filter(shown);
  for(const e of inter){if(/^(hidden|checkbox|radio|file)$/.test(e.type||''))continue;const s=seen(e);if(!s)continue;const bx=e.getBoundingClientRect();if(s.l>bx.left+1||s.r<bx.right-1||s.t>bx.top+1||s.b<bx.bottom-1)continue;const g=reach(e,s);if(!g)continue;
    const inline=e.tagName==='A'&&e.parentElement&&/^(P|LI|SMALL|SPAN|TD|LABEL)$/.test(e.parentElement.tagName)&&e.parentElement.textContent.trim().length>e.textContent.trim().length+12;
    if(!inline&&(g.h<44||g.w<44))out.push(label+': small tap target "'+name(e)+'" '+g.w+'x'+g.h+' reachable');
    const r=e.getBoundingClientRect();if(r.right>vw+1&&!e.closest('.chips,.filters,[style*=overflow-x]'))out.push(label+': "'+name(e)+'" runs off the right edge ('+Math.round(r.right)+' > '+vw+')')}
  for(const d of doc.querySelectorAll('[role=dialog]')){if(!shown(d))continue;const r=d.getBoundingClientRect();const scroller=[d,d.parentElement].find(x=>x&&x.scrollHeight>x.clientHeight+1&&/(auto|scroll)/.test(w.getComputedStyle(x).overflowY));
    if(r.height>vh+1&&!scroller)out.push(label+': dialog "'+name(d).slice(0,20)+'" is taller than the screen and cannot scroll');
    const acts=[...d.querySelectorAll('button')].filter(shown);const last=acts[acts.length-1];if(last&&!kb){const b=last.getBoundingClientRect();if(b.bottom>vt+vh+1)out.push(label+': dialog button "'+name(last)+'" starts off the screen ('+Math.round(b.bottom)+' > '+Math.round(vt+vh)+'): the person must scroll to find it')}}
  const help=doc.getElementById('uaChatBtn');if(help&&shown(help)){const h=help.getBoundingClientRect();for(const e of inter){if(e===help||help.contains(e)||e.closest('#uaChat'))continue;const s=seen(e);if(!s)continue;
    const L=Math.max(s.l,h.left),R=Math.min(s.r,h.right),Tp=Math.max(s.t,h.top),B=Math.min(s.b,h.bottom);if(R-L>1&&B-Tp>1){const top=doc.elementFromPoint((L+R)/2,(Tp+B)/2);if(top&&(top===help||help.contains(top)))out.push(label+': the Help button covers "'+name(e)+'"')}}}
  const a=doc.activeElement;if(kb&&a&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)){const s=seen(a);if(!s)out.push(label+': the field being typed in ("'+name(a)+'") is hidden behind the keyboard or off the screen');
    else if(!hits(a,(s.l+s.r)/2,(s.t+s.b)/2)){const t=doc.elementFromPoint((s.l+s.r)/2,(s.t+s.b)/2);out.push(label+': "'+(t?name(t):'?')+'" lies over the field being typed in ("'+name(a)+'")')}}
  const bar=doc.getElementById('bnav');if(bar&&shown(bar)&&!kb){const b=bar.getBoundingClientRect();if(b.bottom>vt+vh+1)out.push(label+': the bottom bar is partly below the screen ('+Math.round(b.bottom)+' > '+Math.round(vt+vh)+')')}
  return out}`;
// small text is listed as a note, not a fit problem: Chrome does not enlarge it on a page with width=device-width
const SMALL = String.raw`(doc,label)=>{const w=doc.defaultView;return [...doc.querySelectorAll('p,li,small,span,label,button,a,b,em,strong,td,th,div')].filter(e=>e.getClientRects().length&&w.getComputedStyle(e).visibility!=='hidden'&&!e.closest('[aria-hidden=true]')&&[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim().length>1)&&parseFloat(w.getComputedStyle(e).fontSize)<12).slice(0,4).map(e=>label+': '+w.getComputedStyle(e).fontSize+' "'+e.textContent.trim().slice(0,20)+'"')}`;

module.exports = async ({ ev, sleep, nav, send }) => {
  fs.mkdirSync(OUT, { recursive: true });
  const problems = [], steps = [], notes = new Set();
  let n = 0;
  const log = (s) => { steps.push(s); console.log(s); };
  const fail = (s) => { problems.push(s); console.log("FAIL " + s); };
  const wake = () => { try { adb("shell", "input", "keyevent", "KEYCODE_WAKEUP"); } catch (e) {} };
  // a screenshot of the phone's real screen (status bar, Chrome's address bar and Android's buttons included)
  const shot = async (name) => { wake(); await sleep(250); n++; const f = path.join(OUT, String(n).padStart(2, "0") + "-" + name + ".png");
    fs.writeFileSync(f, execFileSync(ADB, ["-s", SERIAL, "exec-out", "screencap", "-p"], { maxBuffer: 64 * 1024 * 1024, timeout: 30000 })); return f; };
  const fit = async (label) => {
    const r = await ev("(()=>{const fit=" + FIT + ";const o=fit(document,'page');const fr=" + F + ";if(fr&&fr.contentDocument)o.push(...fit(fr.contentDocument," + JSON.stringify("app") + "));return JSON.stringify(o)})()");
    let list = []; try { list = JSON.parse(r); } catch (e) { list = ["the fit check could not run: " + r]; }
    for (const p of [...new Set(list)]) fail(label + " · " + p);
    const small = JSON.parse(await ev("(()=>{const sm=" + SMALL + ";const fr=" + F + ";return JSON.stringify([...sm(document,'page'),...(fr&&fr.contentDocument?sm(fr.contentDocument,'app'):[])])})()") || "[]");
    for (const s of small) if (!notes.has(s)) { notes.add(s); log("note: small text " + label + " · " + s); }
    return list;
  };
  let turned = "";
  const orient = async () => { const o = await ev("(screen.orientation&&screen.orientation.type||'')+' '+innerWidth+'x'+innerHeight"); if (turned && o.split(" ")[0] !== turned.split(" ")[0]) { log("the phone was turned: " + turned + " -> " + o + " (measuring the taps again)"); turned = o; await calibrate(); } turned = o; return /landscape/.test(o) ? "landscape" : "portrait"; };
  const step = async (name, label) => { await sleep(500); const o = await orient(); await shot(name + (o === "landscape" ? "-landscape" : "")); await fit((label || name) + (o === "landscape" ? " [landscape]" : "")); };
  // where a CSS point of the page is on the phone's screen: measured with one tap on a part of the page that does nothing (the header's
  // logo), because the address bar's height above the page differs between phones and changes when the bar hides
  let dpr = 1, top = 0, left = 0;
  const calibrate = async (finder) => {
    dpr = await ev("devicePixelRatio");
    await ev("window.__pd=null;const f=" + F + ";const hit=e=>{if(!window.__pd)window.__pd=[e.clientX,e.clientY,e.view===window?0:1]};addEventListener('pointerdown',hit,true);if(f&&f.contentWindow)f.contentWindow.addEventListener('pointerdown',hit,true);1");
    const p = JSON.parse(await ev("(()=>{const f=" + F + ";const d=f?f.contentDocument:document;const e=" + (finder || "d.getElementById('kcH')||d.querySelector('.brand')||d.querySelector('h1')") + ";const r=e.getBoundingClientRect(),o=f?f.getBoundingClientRect():{left:0,top:0};return JSON.stringify({x:o.left+r.left+Math.min(r.width/2,30),y:o.top+r.top+r.height/2})})()"));
    const guessTop = Math.round((await ev("screen.height")) * dpr - (await ev("innerHeight")) * dpr - 134);
    const X = Math.round(p.x * dpr), Y = Math.round(guessTop + p.y * dpr);
    wake(); adb("shell", "input", "tap", String(X), String(Y)); await sleep(700);
    const got = JSON.parse(await ev("JSON.stringify(window.__pd)") || "null");
    if (!got) { fail("calibration: a tap on the phone did not reach the page (is the screen on and Chrome in front?)"); return false; }
    const fr = got[2] ? JSON.parse(await ev("JSON.stringify(" + F + ".getBoundingClientRect())")) : { left: 0, top: 0 };
    top = Y - (fr.top + got[1]) * dpr; left = X - (fr.left + got[0]) * dpr;
    return true;
  };
  const toScreen = (x, y) => [Math.round(left + x * dpr), Math.round(top + y * dpr)];
  // the middle of an element in the app's frame (or the page), scrolled into view first
  const where = async (finder, inPage) => JSON.parse(await ev("(()=>{const f=" + F + ";const d=" + (inPage ? "document" : "f.contentDocument") + ";const e=(" + finder + ");if(!e)return 'null';e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect(),o=" + (inPage ? "{left:0,top:0}" : "f.getBoundingClientRect()") + ";return JSON.stringify({x:o.left+r.left+r.width/2,y:o.top+r.top+r.height/2,w:r.width,h:r.height})})()"));
  const tap = async (finder, inPage) => { await orient(); let p = await where(finder, inPage); if (!p) return false; await sleep(250); p = await where(finder, inPage); const [x, y] = toScreen(p.x, p.y); wake(); adb("shell", "input", "tap", String(x), String(y)); await sleep(700); return true; };
  const swipe = async (finder, dx, dy, ms) => { await orient(); const p = await where(finder); if (!p) return false; await sleep(250); const [x, y] = toScreen(p.x, p.y);
    wake(); adb("shell", "input", "swipe", String(x), String(y), String(Math.round(x + dx * dpr)), String(Math.round(y + dy * dpr)), String(ms || 250)); await sleep(900); return true; };
  const q = (js) => ev("(()=>{try{const d=" + F + ".contentDocument,w=d.defaultView;" + js + "}catch(e){return 'ERR '+e.message}})()");
  const waitFor = async (js, ms) => { const end = Date.now() + (ms || 10000); let v; while (Date.now() < end) { v = await q(js); if (v && !String(v).startsWith("ERR")) return v; await sleep(300); } return v; };
  const byText = (re, sel) => "[...d.querySelectorAll('" + (sel || "button,a,[role=button],.nitem") + "')].find(b=>b.offsetParent&&" + re + ".test(b.innerText.trim()))";
  const menu = async (tab, item) => { await tap("d.getElementById('" + tab + "')"); await sleep(400); return tap("[...d.querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')==='" + item + "')"); };
  const keyboardShot = async (name, finder, label) => {           // tap a field so Android's keyboard opens, check it, then close the keyboard
    if (!(await tap(finder))) { fail(label + " · the field to type in was not found"); return; }
    await sleep(900);
    const kb = await ev("JSON.stringify({vv:Math.round(visualViewport.height),ih:innerHeight})");
    await step(name, label + " (keyboard open " + kb + ")");
    await q("if(d.activeElement)d.activeElement.blur();return 1"); await sleep(700);   // closes the keyboard (Back could leave Chrome)
  };
  const frames = async (fn) => {                                  // frames during a real swipe: how many took longer than two at 60 fps
    await q("w.__fr=[];let l=performance.now();w.__frOn=true;(function f(t){if(!w.__frOn)return;w.__fr.push(t-l);l=t;w.requestAnimationFrame(f)})(l);return 1");
    await fn(); await sleep(300);
    return JSON.parse(await q("w.__frOn=false;const a=w.__fr.slice(2).sort((x,y)=>x-y);return JSON.stringify({n:a.length,p95:Math.round(a[Math.floor(a.length*.95)]||0),slow:a.filter(x=>x>34).length,max:Math.round(a[a.length-1]||0)})"));
  };

  // ---- 1. first visit and the agreement --------------------------------------------------------------------------------------------
  const origin = URL.replace(/\/$/, "");
  if (!LIVE) await send("Storage.clearDataForOrigin", { origin, storageTypes: "all" });
  await send("Emulation.clearDeviceMetricsOverride");
  await nav(URL); await sleep(4000);
  if (!(await calibrate())) return;
  await orient();
  log("phone: " + (await ev("JSON.stringify({css:[innerWidth,innerHeight],dpr:devicePixelRatio,ua:navigator.userAgent.match(/Chrome\\/[\\d.]+/)[0]})")) + " · " + T + " " + URL);
  await waitFor("return d.getElementById('kcYes')||d.querySelector('.card.top')", 20000);
  await step("first-visit", "first visit");
  if (await q("return !!d.getElementById('kcYes')")) {
    await swipe("d.querySelector('#kitConsent [role=dialog] p')", 0, -400, 300);
    await step("agreement-scrolled", "agreement, scrolled to its end");
    if (LIVE) { log("live: the agreement is left unanswered (read only)"); }
    else await tap("d.getElementById('kcYes')");
  }
  if (!LIVE) {
    // ---- 2. the deck: real swipes, Undo, the buttons ---------------------------------------------------------------------------------
    await waitFor("return d.querySelector('.card.top')&&!d.getElementById('btnNo').disabled", 60000);
    await step("jobs", "Jobs");
    const left = await frames(() => swipe("d.querySelector('.card.top')", -240, 6, 220));
    await step("after-swipe-left", "Jobs after a swipe left");
    const right = await frames(() => swipe("d.querySelector('.card.top')", 240, 6, 220));
    log("frames during a swipe left " + JSON.stringify(left) + ", right " + JSON.stringify(right));
    for (const [k, f] of [["left", left], ["right", right]]) if (f.slow > 3) fail("Jobs · the swipe " + k + " dropped frames: " + f.slow + " of " + f.n + " took over 34 ms (slowest " + f.max + " ms)");
    await step("after-swipe-right", "Jobs after a swipe right");
    await tap("d.getElementById('btnUndo')"); await step("after-undo", "Jobs after Undo");
    await tap("d.getElementById('btnNo')"); await tap("d.getElementById('btnYes')"); await step("after-buttons", "Jobs after Pass and Apply buttons");
    // a vertical move on the card scrolls instead of swiping
    const before = await q("return d.querySelector('.card.top')&&d.querySelector('.card.top').getAttribute('data-id')");
    await swipe("d.querySelector('.card.top')", 4, -200, 400);
    if (before !== (await q("return d.querySelector('.card.top')&&d.querySelector('.card.top').getAttribute('data-id')"))) fail("Jobs · a vertical finger move on the card swiped it");
  }
  // ---- 3. Filters (job type chips) and Profile setup with the keyboard -----------------------------------------------------------------
  if (!LIVE || !(await q("return !!d.getElementById('kcYes')"))) {
    await menu("nb-prof", "filters"); await step("filters", "Filters");
    await menu("nb-prof", "settings"); await step("profile-setup", "Profile setup, first step");
    await keyboardShot("profile-keyboard", "d.getElementById('pName')", "Profile setup, typing a name");
    for (let k = 2; k <= (LIVE ? 1 : 8); k++) {     // live: no "Save and continue" (it would change this phone's saved profile on the real site)
      const more = await q("const b=[...d.querySelectorAll('#form button')].find(b=>b.offsetParent&&/^Save and continue|^Next/.test(b.innerText.trim()));return b?'yes':''");
      if (more !== "yes") break;
      await tap("[...d.querySelectorAll('#form button')].find(b=>b.offsetParent&&/^Save and continue|^Next/.test(b.innerText.trim()))"); await sleep(600);
      const title = await q("return (d.getElementById('secTitle')||{}).textContent||''");
      await step("profile-step-" + k, "Profile setup step " + k + " (" + title + ")");
      if (/resume|background/i.test(title)) log("resume upload: the file box is checked for fit; choosing a file opens Android's picker (outside Chrome), not done here");
    }
    await keyboardShot("profile-keyboard-last", "[...d.querySelectorAll('#form input[type=text],#form input[type=url],#form textarea')].filter(e=>e.offsetParent).pop()", "Profile setup, typing in the last field");
    // ---- 4. Account: sign-in options; sign-up with the stand-in inbox (local only) ----------------------------------------------------
    await menu("nb-prof", "account"); await step("account", "Account");
    await keyboardShot("signin-keyboard", "d.getElementById('aEmail')||d.getElementById('sEmail')||d.querySelector('#acctSec input[type=email],#acctSec input[inputmode=email]')", "Sign in, typing an email");
    if (!LIVE && process.env.WALK_MAIL) {
      const EMAIL = "uaplytechnologies+phone1@gmail.com", PW = "phone walk " + Math.random().toString(36).slice(2, 10);
      const set = (id, v) => q("const e=d.getElementById('" + id + "');if(!e)return '';e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return 'ok'");
      const toSignup = await q("const b=" + byText("/^(Create an account|Sign up|Create account)/i") + ";if(b)b.click();return b?'ok':''");
      await sleep(800);
      if ((await set("sEmail", EMAIL)) && (await set("sPw", PW))) {
        await set("sPw2", PW); await q("const c=d.getElementById('sAgree');if(c)c.checked=true;return 1");
        await step("signup-filled", "Sign up, filled in");
        await tap("d.querySelector('[data-auth=ssubmit]')"); await sleep(2500);
        await step("signup-code", "Sign up, the code screen");
        let code = "";
        for (let k = 0; k < 20 && !code; k++) { await sleep(500); try { const rows = fs.readFileSync(process.env.WALK_MAIL, "utf8").trim().split(/\n/).map((l) => JSON.parse(l)); const m = rows.reverse().map((r) => JSON.stringify(r).match(/\b(\d{6})\b/)).find(Boolean); if (m) code = m[1]; } catch (e) {} }
        if (code) { await tap("d.getElementById('sCode')"); await sleep(600); wake(); adb("shell", "input", "text", code); await sleep(400);
          await step("signup-code-typed", "Sign up, typing the code (keyboard open)"); await q("if(d.activeElement)d.activeElement.blur();return 1"); await sleep(500);
          await tap(byText("/^(Verify|Confirm)/i")); await sleep(2000); await step("signed-in", "Account, signed in");
        } else fail("Sign up · no code arrived in the stand-in inbox");
      } else log("sign-up form not found (" + toSignup + ")");
    }
    await menu("nb-prof", "plan"); await sleep(800); await step("plan", "Plan & billing");
    await menu("nb-prof", "data"); await step("data", "Data & privacy");
    // ---- 5. Applied and its rows -------------------------------------------------------------------------------------------------------
    await menu("nb-dash", "applied"); await step("applied", "Applied");
    await menu("nb-dash", "overview"); await step("dashboard", "Dashboard overview");
    // ---- 6. Help ---------------------------------------------------------------------------------------------------------------------
    await menu("nb-svc", "job"); await sleep(500);
    await tap("d.getElementById('uaChatBtn')"); await step("help", "Help");
    await keyboardShot("help-keyboard", "d.getElementById('uaChatIn')", "Help, typing a question");
    await tap("d.getElementById('uaChatX')");
  }
  // ---- 7. landscape: turning the phone would mean changing its rotation setting, so the turned screen is checked headless by
  //      tools/ui-phone.js (LANDSCAPE=1, 844x390 and 667x375) with the same fit checks
  // ---- 8. legal pages, with the address bar shown and hidden ------------------------------------------------------------------------
  await nav(origin + "/legal/terms.html"); await sleep(2500);
  await calibrate("document.querySelector('h1')"); turned = "";
  await step("terms", "Terms");
  wake(); adb("shell", "input", "swipe", "540", "1700", "540", "700", "300"); await sleep(1200);
  await step("terms-bar-hidden", "Terms, scrolled (address bar hidden)");
  await nav(origin + "/legal/support.html"); await sleep(2000); await step("support", "Support");
  // ---- 9. the offline screen: the local server is stopped for real (the launcher started it), then the app is opened again
  if (!LIVE && process.env.WALK_SERVER_PID) {
    await nav(URL); await sleep(3000);
    try { process.kill(Number(process.env.WALK_SERVER_PID)); } catch (e) { log("could not stop the server: " + e.message); }
    await sleep(1500);
    await nav(URL); await sleep(3500);
    await step("offline", "Offline screen (server stopped)");
    const what = await ev("document.title+' | '+document.body.innerText.slice(0,80).replace(/\\s+/g,' ')");
    log("offline screen: " + what);
    if (!/offline|can.t reach|cannot reach|starting|no connection/i.test(what)) fail("Offline screen · with the server stopped the page shows no offline screen: " + what);
  }
  console.log("\n" + steps.length + " notes, " + n + " screenshots, " + problems.length + " fit problems");
  console.log((problems.length ? "FIT PROBLEMS" : "NO FIT PROBLEMS") + " on " + T);
  fs.writeFileSync(path.join(OUT, "walk.txt"), steps.concat(problems.map((p) => "FAIL " + p)).join("\n") + "\n");
  if (problems.length) process.exitCode = 1;
};
module.exports.limitMs = 1500000;
module.exports.FIT = FIT;           // the same checks, for tools/ui-phone.js
module.exports.SMALL = SMALL;
