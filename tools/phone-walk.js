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
  let url = "https://uaply.net/", port = 0, mailFile = "", dataDir = "", mgPort = 0;
  const stopKids = () => { for (const k of kids) { try { k.kill(); } catch (e) {} } };
  process.on("exit", stopKids);
  const waitFor = (u, ms) => { const end = Date.now() + ms; while (Date.now() < end) { const r = spawnSync(process.execPath, ["-e", "fetch(" + JSON.stringify(u) + ").then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]); if (r.status === 0) return true; spawnSync(process.execPath, ["-e", "setTimeout(()=>{},300)"]); } return false; };
  if (target !== "live") {
    port = Number(process.env.PORT || (target === "sandbox" ? 18990 : 18991));
    const mailPort = port + 100;
    dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "uaply-phone-"));
    mailFile = path.join(dataDir, "mail.jsonl");
    kids.push(spawn("python", [path.join(ROOT, "tools", "fake-smtp.py"), String(mailPort), mailFile], { stdio: "ignore" }));
    // the stand-in Google (tools/mock-google.py): the sign-up card's "Continue with Google" is walked too, and nothing talks to Google
    mgPort = port + 200;
    kids.push(spawn("python", [path.join(ROOT, "tools", "mock-google.py"), String(mgPort)], { stdio: "ignore" }));
    const mg = "http://127.0.0.1:" + mgPort;
    const cfg = { feeds: ["greenhouse", "lever", "ashby"], delivery: "test", owner_copy: "",
      google: { client_id: "test.apps.googleusercontent.com", client_secret: "test-secret", auth_url: mg + "/auth", token_url: mg + "/token", certs_url: mg + "/certs" },
      smtp: { host: "127.0.0.1", port: mailPort, starttls: false, from_addr: "uaply@example.com" } };
    const env = Object.assign({}, process.env, { UAPLY_DATA_DIR: path.join(dataDir, "data"), UAPLY_CONFIG_FILE: "none", UAPLY_CONFIG_JSON: JSON.stringify(cfg) });
    delete env.UAPLY_PUBLIC_URL; delete env.HOST;
    const srv = spawn("python", [path.join(ROOT, "serve.py"), String(port), path.join(ROOT, target), "--api"], { env, stdio: ["ignore", "ignore", fs.openSync(path.join(OUT, "server.log"), "w")] });
    kids.push(srv); process.env.WALK_SERVER_PID = String(srv.pid);
    if (!waitFor("http://127.0.0.1:" + port + "/healthz", 30000)) { console.log("FAIL the local " + target + " server did not start (see " + OUT + "/server.log)"); process.exit(1); }
    adb("reverse", "tcp:" + port, "tcp:" + port);
    adb("reverse", "tcp:" + mgPort, "tcp:" + mgPort);          // the phone's Chrome opens the stand-in Google's page
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
    CDP_LIMIT_MS: "1500000", WALK_TARGET: target, WALK_URL: url, WALK_OUT: OUT, WALK_SERIAL: serial, ADB, WALK_MAIL: mailFile, WALK_PORT: String(port), WALK_MG: String(mgPort) });
  const r = spawnSync(process.execPath, [path.join(ROOT, "tools", "cdp.js"), __filename], { env, stdio: "inherit" });
  if (port) { try { adb("reverse", "--remove", "tcp:" + port); } catch (e) {} }
  if (mgPort) { try { adb("reverse", "--remove", "tcp:" + mgPort); } catch (e) {} }
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
// small text (under 14 px, the owner's rule since October 23) is listed as a note, not a fit problem: Chrome does not enlarge it on a page
// with width=device-width
const SMALL = String.raw`(doc,label)=>{const w=doc.defaultView;return [...doc.querySelectorAll('p,li,small,span,label,button,a,b,em,strong,td,th,div')].filter(e=>e.getClientRects().length&&w.getComputedStyle(e).visibility!=='hidden'&&!e.closest('[aria-hidden=true]')&&[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim().length>1)&&parseFloat(w.getComputedStyle(e).fontSize)<14).slice(0,4).map(e=>label+': '+w.getComputedStyle(e).fontSize+' "'+e.textContent.trim().slice(0,20)+'"')}`;

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
  const orient = async () => { const o = await ev("(screen.orientation&&screen.orientation.type||'')+' '+innerWidth+'x'+innerHeight"); if (turned && o !== turned) { log((o.split(" ")[0] !== turned.split(" ")[0] ? "the phone was turned: " : "the page's size changed (Chrome's address bar): ") + turned + " -> " + o + " (measuring the taps again)"); turned = o; await calibrate(); } turned = o; return /landscape/.test(o) ? "landscape" : "portrait"; };
  const step = async (name, label) => { await sleep(500); const o = await orient(); await shot(name + (o === "landscape" ? "-landscape" : "")); await fit((label || name) + (o === "landscape" ? " [landscape]" : "")); };
  // where a CSS point of the page is on the phone's screen: measured with one tap on a part of the page that does nothing (the header's
  // logo), because the address bar's height above the page differs between phones and changes when the bar hides
  let dpr = 1, top = 0, left = 0;
  // the first one on show: under the sign-in gate .brand is hidden, so the card's logo (.sg-bb .sg-lg) or its heading is used
  const calibrate = async (finder) => {
    dpr = await ev("devicePixelRatio");
    await ev("window.__pd=null;const f=" + F + ";const hit=e=>{if(!window.__pd)window.__pd=[e.clientX,e.clientY,e.view===window?0:1]};addEventListener('pointerdown',hit,true);if(f&&f.contentWindow)f.contentWindow.addEventListener('pointerdown',hit,true);1");
    // (not the header's logo when the header shows: on the sandbox the logo is a link home, so every measuring tap jumped to the Jobs tab, and
    //  a walk that measured again after the keyboard closed lost its place: Account never opened, Sign out never pressed, October 23. The
    //  widest empty stretch of the header between its buttons is used, which does nothing when tapped)
    const gap = finder ? "" : "if(!(k&&k.getClientRects().length)){const h=d.querySelector('header.bar');if(h&&h.getClientRects().length&&h.getBoundingClientRect().height>20){const hr=h.getBoundingClientRect();" +
      "const cs=[...h.querySelectorAll('button,a,input,[role=link],[role=button],[tabindex]')].filter(x=>x.getClientRects().length).map(x=>x.getBoundingClientRect()).sort((a,b)=>a.left-b.left);" +
      "let best=null,prev=hr.left;for(const c of cs){if(c.left-prev>(best?best.w:0))best={x:(prev+c.left)/2,w:c.left-prev};prev=Math.max(prev,c.right)}if(hr.right-prev>(best?best.w:0))best={x:(prev+hr.right)/2,w:hr.right-prev};" +
      "if(best&&best.w>=16)return JSON.stringify({x:o.left+best.x,y:o.top+hr.top+hr.height/2})}}";
    const p = JSON.parse(await ev("(()=>{const f=" + F + ";const d=f?f.contentDocument:document;const o=f?f.getBoundingClientRect():{left:0,top:0};const k=d.getElementById('kcH');" + gap + "const e=" + (finder || "[k,d.querySelector('.sg-bb .sg-lg'),d.querySelector('.sg-card h1,.sg-card h2'),d.querySelector('h1')].find(e=>e&&e.getClientRects().length&&e.getBoundingClientRect().width>0)") + ";const r=e.getBoundingClientRect();return JSON.stringify({x:o.left+r.left+Math.min(r.width/2,30),y:o.top+r.top+r.height/2})})()"));
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
  const where = async (finder, inPage) => JSON.parse(await ev("(()=>{const f=" + F + ";const d=" + (inPage ? "document" : "f.contentDocument") + ";const e=(" + finder + ");if(!e)return 'null';e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect(),o=" + (inPage ? "{left:0,top:0}" : "f.getBoundingClientRect()") + ";const v=window.visualViewport||{offsetLeft:0,offsetTop:0};return JSON.stringify({x:o.left+r.left+r.width/2-v.offsetLeft,y:o.top+r.top+r.height/2-v.offsetTop,w:r.width,h:r.height})})()"));
  // (the visual viewport's offset: with Android's keyboard open Chrome scrolls the visible part, and a tap measured without it landed
  //  on the box above the one meant: the sign-up card's First name tap went to Email, October 22, 2026)
  // a tap is checked: the element the finger reached must be the one meant (or inside it). When it was not (the address bar or the keyboard
  // moved the page between measuring and tapping: a Save and continue tap landed on the Jobs tab, then Account was never opened and Sign
  // out never pressed, October 23), the screen is measured again and the tap tried once more
  const tapOnce = async (finder, inPage) => {
    await orient(); let p = await where(finder, inPage); if (!p) return null; await sleep(250); p = await where(finder, inPage); if (!p) return null;
    await ev("(()=>{window.__th=null;const f=" + F + ";const rec=e=>{if(!window.__th)window.__th=e.target};const on=(t)=>{t.addEventListener('pointerdown',rec,{capture:true,once:true})};on(window);if(f&&f.contentWindow)on(f.contentWindow);return 1})()");
    const [x, y] = toScreen(p.x, p.y); wake(); adb("shell", "input", "tap", String(x), String(y)); await sleep(700);
    return ev("(()=>{const f=" + F + ";const d=" + (inPage ? "document" : "f.contentDocument") + ";const e=(" + finder + "),h=window.__th;return !!h&&(!e||e===h||e.contains(h)||(h.closest&&h.closest('label')&&h.closest('label').contains(e)))})()");   // no pointerdown in the page (the keyboard, the address bar): a miss
  };
  const tap = async (finder, inPage) => {
    const ok = await tapOnce(finder, inPage); if (ok === null) return false; if (ok) return true;
    await calibrate(); const again = await tapOnce(finder, inPage); if (again === null) return false;
    if (!again) { fail("a tap missed twice (" + finder.slice(0, 60) + "): it reached something else, or nothing in the page"); return false; }
    return true;
  };
  const swipe = async (finder, dx, dy, ms) => { await orient(); const p = await where(finder); if (!p) return false; await sleep(250); const [x, y] = toScreen(p.x, p.y);
    wake(); adb("shell", "input", "swipe", String(x), String(y), String(Math.round(x + dx * dpr)), String(Math.round(y + dy * dpr)), String(ms || 250)); await sleep(900); return true; };
  const q = (js) => ev("(()=>{try{const d=" + F + ".contentDocument,w=d.defaultView;" + js + "}catch(e){return 'ERR '+e.message}})()");
  const waitFor = async (js, ms) => { const end = Date.now() + (ms || 10000); let v; while (Date.now() < end) { v = await q(js); if (v && !String(v).startsWith("ERR")) return v; await sleep(300); } return v; };
  const byText = (re, sel) => "[...d.querySelectorAll('" + (sel || "button,a,[role=button],.nitem") + "')].find(b=>b.offsetParent&&" + re + ".test(b.innerText.trim()))";
  // a tab opens its menu, and a second tap closes it: the tab is tapped only while its menu is shut, and again if the item is not on show
  // (a walk that tapped Profile with its menu already open closed it, so Account never opened, October 23)
  const menu = async (tab, item) => {
    const shown = "[...d.querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.getAttribute('data-v')==='" + item + "')";
    for (let k = 0; k < 2; k++) {
      if (!(await q("return " + shown + "?'yes':''"))) { await tap("d.getElementById('" + tab + "')"); await sleep(500); }
      if (await q("return " + shown + "?'yes':''")) return tap(shown);
    }
    fail("menu · " + tab.replace("nb-", "") + " › " + item + " did not open"); return false;
  };
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
  // the sign-in gate (October 22, Saif; the sandbox): signed out, the card is the whole screen. The walk's person signs up through it
  // first (the card's own boxes, the code from the stand-in inbox, the two questions); section 4 signs out and walks the card by touch
  await waitFor("return d.getElementById('kcYes')||d.querySelector('.card.top')||(d.body.classList.contains('sgGated')&&d.querySelector('.sg-su'))", 20000);
  if (await q("return d.body.classList.contains('sgGated')?'yes':''")) {
    await step("gate", "the sign-in gate (signed out)");
    if (LIVE || !process.env.WALK_MAIL) { log("the sign-in gate is up and this walk does not sign up here (" + (LIVE ? "live: read only" : "no stand-in inbox") + "): the rest needs an account"); return; }
    const E0 = "uaplytechnologies+phone0@gmail.com", seen0 = (() => { try { return fs.readFileSync(process.env.WALK_MAIL, "utf8").trim().split(/\n/).filter(Boolean).length; } catch (e) { return 0; } })();
    const setv = (sel, v) => q("const e=d.querySelector(" + JSON.stringify(sel) + ");if(!e)return '';e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return 'ok'");
    await setv(".sg-su [data-email] input", E0); await setv(".sg-su .sg-fn input", "Pat"); await setv(".sg-su .sg-ln input", "Walker"); await setv(".sg-su .sg-pw input", "Phone-walk-" + Date.now());
    await q("const a=d.querySelector('.sg-su .sg-ag');if(a&&!a.checked)a.click();d.querySelector('.sg-su [type=submit]').click();return 1"); await sleep(2500);
    let c0 = "";
    for (let k = 0; k < 30 && !c0; k++) { await sleep(500); try { const rows = fs.readFileSync(process.env.WALK_MAIL, "utf8").trim().split(/\n/).map((l) => JSON.parse(l)); if (rows.length > seen0) { const m = rows.slice(seen0).reverse().map((r) => JSON.stringify(r).match(/\b(\d{6})\b/)).find(Boolean); if (m) c0 = m[1]; } } catch (e) {} }
    if (c0) { await setv(".sg-code input", c0); await sleep(2500); }
    for (let k = 0; k < 3; k++) { await q("const b=d.querySelector('.sg-next');if(b)b.click();return 1"); await sleep(900); }
    const in0 = await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user?j.user.email:'')");
    if (in0 === E0 && !(await q("return d.body.classList.contains('sgGated')?'yes':''"))) log("signed up through the gate first (" + E0 + "): the app is open");
    else { fail("Sign-in gate · could not sign up through it (" + (c0 ? "signed in: " + in0 : "no code in the stand-in inbox") + ")"); return; }
    await waitFor("return d.getElementById('kcYes')||d.querySelector('.card.top')", 20000);
  }
  await step("first-visit", "first visit");
  if (await q("return !!d.getElementById('kcYes')")) {
    await swipe("d.querySelector('#kitConsent [role=dialog] p')", 0, -400, 300);
    await step("agreement-scrolled", "agreement, scrolled to its end");
    if (LIVE) { log("live: the agreement is left unanswered (read only)"); }
    else await tap("(()=>{d.querySelectorAll('.kcTick').forEach(c=>{c.checked=true;c.dispatchEvent(new Event('change'))});return d.getElementById('kcYes')})()");
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
    if (!LIVE && (await q("return d.querySelector('[data-auth=sout]')?'in':''"))) {     // signed up through the gate: sign out, and the gate is back
      await tap("d.querySelector('[data-auth=sout]')"); await sleep(1800);
      if (await waitFor("return d.body.classList.contains('sgGated')?'yes':''", 6000) === "yes") log("Sign out: the sign-in gate is back"); else fail("Sign out · the sign-in gate did not come back");
      await step("gate-after-signout", "the sign-in gate after Sign out");
    }
    await keyboardShot("signin-keyboard", "d.getElementById('aEmail')||d.getElementById('sEmail')||d.querySelector('#acctSec input[type=email],#acctSec input[inputmode=email]')", "Sign in, typing an email");
    if (!LIVE && process.env.WALK_MAIL) {
      const EMAIL = "uaplytechnologies+phone1@gmail.com", PW = "phone walk " + Math.random().toString(36).slice(2, 10), PW1 = "Walk" + Math.random().toString(36).slice(2, 10);
      const set = (id, v) => q("const e=d.getElementById('" + id + "');if(!e)return '';e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return 'ok'");
      // the newest 6-digit code in the stand-in inbox that was not there before `seen`
      const codeAfter = async (seen) => { for (let k = 0; k < 30; k++) { await sleep(500); try { const rows = fs.readFileSync(process.env.WALK_MAIL, "utf8").trim().split(/\n/).map((l) => JSON.parse(l));
        if (rows.length > seen) { const m = rows.slice(seen).reverse().map((r) => JSON.stringify(r).match(/\b(\d{6})\b/)).find(Boolean); if (m) return m[1]; } } catch (e) {} } return ""; };
      const inbox = () => { try { return fs.readFileSync(process.env.WALK_MAIL, "utf8").trim().split(/\n/).filter(Boolean).length; } catch (e) { return 0; } };
      const card = () => q("return (d.getElementById('acctSec')||{innerText:''}).innerText");
      // type with Android's keyboard: a real tap on the box, then adb's text (spaces as %s), the box must hold exactly that
      const typeInto = async (finder, text, label) => { for (let a = 1; a <= 3; a++) {
        await tap(finder); await sleep(600);
        if ((await q("return d.activeElement===(" + finder + ")?'ok':''")) !== "ok") { log("sign-up: the tap on " + label + " did not focus it (try " + a + ")"); continue; }
        await q("const e=(" + finder + ");e.select&&e.select();return 1"); wake(); adb("shell", "input", "text", text.replace(/ /g, "%s")); await sleep(600);
        if ((await q("return (" + finder + ").value")) === text) return true; log("sign-up: " + label + " did not take the text (try " + a + ")"); }
        fail("Sign up · could not type into " + label + " by touch in 3 tries"); return false; };
      const blur = () => q("if(d.activeElement)d.activeElement.blur();return 1");
      const typeCode = async (code, label) => { await tap("d.querySelector('.sg-code input')"); await sleep(600); wake(); adb("shell", "input", "text", code); await sleep(500);
        await step(label + "-typed", label + ", typing the code (keyboard open)"); await blur(); await sleep(2200); };
      if (await q("return d.querySelector('.sg-su')?'v2':''")) {
        // ---- the sandbox's sign-up card (shared/uaply-signup.js): Continue with Google, Email, First name, Last name, the 18+ tick ----
        const g = await q("const b=d.querySelector('[data-sg=google]');return b&&b.offsetParent?'shown':''");
        if (g) log("sign-up card: Continue with Google is shown"); else fail("Sign up · the card shows no Continue with Google");
        await step("signup-card", "Sign up, the card");
        const ok = (await typeInto("d.querySelector('.sg-su [data-email] input')", EMAIL, "Email")) &&
          (await typeInto("d.querySelector('.sg-su .sg-fn input')", "Sam", "First name")) && (await typeInto("d.querySelector('.sg-su .sg-ln input')", "Rivera", "Last name")) &&
          (await typeInto("d.querySelector('.sg-su .sg-pw input')", PW1, "Password"));
        await blur(); await sleep(700);
        if (ok) {
          await tap("d.querySelector('.sg-su .sg-ag')"); await sleep(400);
          if ((await q("return d.querySelector('.sg-su .sg-ag').checked?'ok':''")) !== "ok") fail("Sign up · a tap on the 18+ box did not tick it");
          await step("signup-filled", "Sign up, filled in");
          const before = inbox();
          await tap("d.querySelector('.sg-su [type=submit]')"); await sleep(2500);
          if (!/Check your email/.test(await card())) fail("Sign up · Create my account did not go to the code step: " + (await card()).slice(0, 120).replace(/\s+/g, " "));
          await step("signup-code", "Sign up, the code screen");
          const code = await codeAfter(before);
          if (!code) fail("Sign up · no code arrived in the stand-in inbox");
          else {
            await typeCode(code, "signup-code");
            if (!/Account created/.test(await card())) fail("Sign up · the code did not make the account: " + (await card()).slice(0, 120).replace(/\s+/g, " "));
            await step("signup-question-1", "Sign up, question 1 of 2");
            await tap("d.querySelector('.sg-chip')"); await sleep(300); await tap("d.querySelector('.sg-next')"); await sleep(800);
            await step("signup-question-2", "Sign up, question 2 of 2");
            await tap("d.querySelector('.sg-next')"); await sleep(1000);
            await step("signup-ready", "Sign up, ready (or almost ready)");
            await tap("d.querySelector('.sg-next')"); await sleep(1200);          // Show me jobs: the questions are done
            const me = await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user?j.user.email:'')");
            if (me === EMAIL) log("sign-up checked: the account exists and is signed in (" + EMAIL + "), by touch and a code from the stand-in inbox");
            else fail("Sign up · after the code nobody is signed in (" + me + ")");
            // ---- sign out, then back in with an emailed code ----
            await menu("nb-prof", "account"); await sleep(800);
            await tap("d.querySelector('[data-auth=sout]')"); await sleep(1800);
            if (await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user?'in':'')")) fail("Sign out · a tap on Sign out did not sign out");
            await tap("d.querySelector('.sg-to-in')"); await sleep(700);
            await step("signin-card", "Sign in, the card");
            if ((await typeInto("d.querySelector('#acctSec [data-email] input')", EMAIL, "Sign-in email")) && (await typeInto("d.querySelector('.sg-si .sg-pw input')", PW1, "Sign-in password"))) {
              await blur(); await sleep(600);
              await step("signin-filled", "Sign in, filled in");
              await tap("d.querySelector('.sg-si [type=submit]')"); await sleep(2500);
              if ((await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user?j.user.email:'')")) === EMAIL) log("sign-in by password checked"); else fail("Sign in · the password did not sign in");
              await menu("nb-prof", "account"); await sleep(800);
              await tap("d.querySelector('[data-auth=sout]')"); await sleep(1800);
            }
            await tap("d.querySelector('.sg-to-in')"); await sleep(700);
            await tap("d.querySelector('.sg-codeinst')"); await sleep(600);
            await step("signin-code-card", "Sign in, Email me a code instead");
            if (await typeInto("d.querySelector('#acctSec [data-email] input')", EMAIL, "Sign-in email (code)")) {
              await blur(); await sleep(600); const b2 = inbox();
              await tap("d.querySelector('.sg-si [type=submit]')"); await sleep(2000);
              const code2 = await codeAfter(b2);
              if (!code2) fail("Sign in · no code arrived in the stand-in inbox");
              else { await typeCode(code2, "signin-code"); if ((await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user?j.user.email:'')")) === EMAIL) log("sign-in by code checked"); else fail("Sign in · the code did not sign in: " + (await card()).slice(0, 120).replace(/\s+/g, " ")); }
              await step("signed-in", "Account, signed in again");
            }
            // ---- Continue with Google (the stand-in Google approves at once and sends the phone back) ----
            if (process.env.WALK_MG && g) {
              await menu("nb-prof", "account"); await sleep(800);
              if (await q("return d.querySelector('[data-auth=sout]')?'in':''")) { await tap("d.querySelector('[data-auth=sout]')"); await sleep(1800); }
              try { await fetch("http://127.0.0.1:" + process.env.WALK_MG + "/mock/next?email=" + encodeURIComponent(EMAIL) + "&sub=walk" + Date.now() + "&verified=1"); } catch (e) {}
              await tap("d.querySelector('.sg-to-in')"); await sleep(600);
              await tap("d.querySelector('[data-sg=google]')"); await sleep(7000);
              await waitFor("return d.getElementById('bnav')?1:0", 20000); await calibrate(); await sleep(1500);
              const g2 = await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user?j.user.email:'')");
              if (g2 === EMAIL) log("Continue with Google checked (stand-in Google): the same account, signed in");
              else fail("Sign in · Continue with Google did not sign in (" + g2 + ")");
              await step("google-back", "Back from Google");
            }
          }
        }
      } else if ((await q("const b=" + byText("/^(Create an account|Sign up|Create account)/i") + ";if(b)b.click();return b?'ok':''")) && (await sleep(800), (await set("sEmail", EMAIL)) && (await set("sPw", PW)))) {
        // ---- the password card (dev and the live site) ----
        await set("sPw2", PW); await q("const c=d.getElementById('sAgree');if(c)c.checked=true;return 1");
        await step("signup-filled", "Sign up, filled in");
        const before = inbox();
        await tap("d.querySelector('[data-auth=ssubmit]')"); await sleep(2500);
        await step("signup-code", "Sign up, the code screen");
        const code = await codeAfter(before);
        if (code) { await tap("d.getElementById('sCode')"); await sleep(600); wake(); adb("shell", "input", "text", code); await sleep(400);
          await step("signup-code-typed", "Sign up, typing the code (keyboard open)"); await blur(); await sleep(500);
          await tap(byText("/^(Verify|Confirm)/i")); await sleep(2000); await step("signed-in", "Account, signed in");
          log("sign-up checked (password card)");
        } else fail("Sign up · no code arrived in the stand-in inbox");
      } else fail("Sign up · neither the sign-up card nor the password form was found on Account: sign-up was not checked");
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
