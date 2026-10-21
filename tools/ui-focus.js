// Taps and focus on every page UAply serves, in a phone-sized Chrome with touch: no element keeps the browser's default tap highlight
// (the grey or blue flash where a finger lands), a tap or a click leaves no focus ring, and the keyboard still gets a clear ring.
// Starts its own servers on free ports with temporary data folders, so nothing needs to be running:
//   W=390 H=844 node tools/cdp.js tools/ui-focus.js           (OUT=<folder> also saves a picture of the starting-up page after a tap)
// The pages: the app (dev and the sandbox, outer page and the app inside its frame), every legal page (Terms, Privacy, AI and matching,
// Copyright, Support, Employers, Delete your account, the index), the offline / starting-up screen, the 404 page, /setup, /feedback, the
// test inbox, the "UAply has moved" page, and the phone app's "can't connect" screen (mobile/www/index.html).
const { spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const os = require("os");
const path = require("path");
const ROOT = path.join(__dirname, "..");
const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const freePort = () => new Promise((r) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => r(p)); }); });

module.exports = async ({ ev, sleep, nav, send, shot, on }) => {
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + name + (ok || extra === undefined ? "" : "  -> " + extra)); return ok; };
  const procs = [], dirs = [];
  const serve = async (rootDir, env) => {
    const port = await freePort(), data = fs.mkdtempSync(path.join(os.tmpdir(), "uaply-focus-"));
    dirs.push(data);
    procs.push(spawn(PY, [path.join(ROOT, "serve.py"), String(port), path.join(ROOT, rootDir), "--api"], { cwd: ROOT, stdio: "ignore",
      env: Object.assign({}, process.env, { UAPLY_DATA_DIR: data, UAPLY_CONFIG_FILE: "none", UAPLY_CONFIG_JSON: '{"feeds":[],"smtp":{}}', HOST: "127.0.0.1" }, env || {}) }));
    const base = "http://127.0.0.1:" + port;
    for (let i = 0; i < 120; i++) { try { if ((await fetch(base + "/healthz")).ok) return base; } catch (e) {} await sleep(250); }
    throw new Error("a test server did not start");
  };
  // every element of the page (and of the app inside its frame) whose computed tap highlight is not transparent
  const SCAN = "(()=>{const out=[];const docs=[document];const f=document.querySelector('iframe');try{if(f&&f.contentDocument)docs.push(f.contentDocument)}catch(e){}" +
    "for(const d of docs){for(const el of [d.documentElement,...d.querySelectorAll('*')]){const c=d.defaultView.getComputedStyle(el).webkitTapHighlightColor;" +
    "if(c&&c!=='rgba(0, 0, 0, 0)'&&c!=='transparent')out.push(el.tagName.toLowerCase()+(el.id?'#'+el.id:'')+' '+c)}}" +
    "return JSON.stringify({n:docs.reduce((a,d)=>a+d.querySelectorAll('*').length,0),bad:out.slice(0,5),nbad:out.length})})()";
  const scan = async (label, minEls) => {
    const r = JSON.parse(await ev(SCAN));
    check(label + ": no element keeps the default tap highlight (" + r.n + " elements)", r.nbad === 0 && r.n >= (minEls || 5), r.nbad + " " + r.bad.join(" | "));
  };
  const tapOn = async (sel) => {                               // a real touch on the element's centre (touchstart, touchend); a link is not followed
    await ev("document.addEventListener('click',e=>{if(e.target.closest('a'))e.preventDefault()},true)");
    const box = JSON.parse(await ev("(()=>{const e=document.querySelector(" + JSON.stringify(sel) + ");if(!e)return 'null';const r=e.getBoundingClientRect();return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2})})()"));
    if (!box) return false;
    await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: box.x, y: box.y }] });
    await sleep(80);
    await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await sleep(250);
    return true;
  };
  const ring = (sel) => ev("(()=>{const e=" + (sel ? "document.querySelector(" + JSON.stringify(sel) + ")" : "document.activeElement") + ";if(!e)return 'none';const s=getComputedStyle(e);return s.outlineStyle+' '+s.outlineWidth+' '+(e===document.activeElement?'focused':'not focused')})()");
  try {
    const dev = await serve("dev"), sb = await serve("sandbox"), moved = await serve("dev", { UAPLY_PUBLIC_URL: "https://uaply.net" });

    // ---------- 1. no default tap highlight anywhere ----------
    const PAGES = [[dev, "/", "the app (dev, the release build)", 200], [sb, "/?app=1", "the app (sandbox)", 200], [dev, "/legal/", "legal index"],
      ...["terms", "privacy", "ai-and-employment", "copyright", "support", "employers", "delete-account"].map((n) => [dev, "/legal/" + n + ".html", "legal/" + n]),
      [dev, "/uaply-offline.html", "the starting-up / offline screen"], [dev, "/no-such-page", "the 404 page"], [dev, "/setup", "/setup"],
      [dev, "/feedback", "/feedback"], [dev, "/outbox", "the test inbox"]];
    for (const [base, p, label, minEls] of PAGES) {
      await nav(base + p);
      if (p === "/" || p === "/?app=1") { for (let i = 0; i < 40; i++) { if (await ev("(()=>{try{return !!document.querySelector('iframe').contentDocument.getElementById('nb-prof')}catch(e){return false}})()")) break; await sleep(250); } }
      await scan(label, minEls);
    }
    // the "UAply has moved" page (an address other than UAPLY_PUBLIC_URL), with scripts off so it stays instead of moving on
    // (its HTML is fetched here and shown without its scripts and its no-script redirect, so the browser never leaves for uaply.net)
    const movedHtml = (await (await fetch(moved + "/")).text()).replace(/<noscript>[\s\S]*?<\/noscript>/g, "").replace(/<script>[\s\S]*?<\/script>/g, "");
    await nav("about:blank");
    const tree = await send("Page.getFrameTree");
    await send("Page.setDocumentContent", { frameId: tree.result.frameTree.frame.id, html: movedHtml });
    await sleep(300);
    check("the moved page is the one being checked", /UAply has moved/.test(String(await ev("document.title"))), await ev("document.title"));
    await scan("the \"UAply has moved\" page");
    await nav("file:///" + path.join(ROOT, "mobile", "www", "index.html").replace(/\\/g, "/"));
    await scan("the phone app's \"can't connect\" screen", 3);

    // ---------- 2. a tap leaves no ring; the keyboard gets one ----------
    await nav(dev + "/uaply-offline.html");
    await sleep(300);
    const tapped = await tapOn("#b");
    await sleep(300);
    if (process.env.OUT) await shot(path.join(process.env.OUT, "starting-up-after-tap.png"));
    const afterTap = String(await ring("#b"));
    check("starting-up screen: tapping Try again leaves no focus ring on it", tapped && /^none /.test(afterTap), afterTap);
    await ev("document.activeElement&&document.activeElement.blur()");
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    await sleep(200);
    const kb = String(await ring());
    const col = String(await ev("getComputedStyle(document.activeElement).outlineColor"));
    check("...while the keyboard (Tab) still gets a 3 px ring in the app's accent colour", /^solid 3px focused$/.test(kb) && col === "rgb(201, 42, 85)", kb + " " + col);
    if (process.env.OUT) await shot(path.join(process.env.OUT, "starting-up-keyboard-focus.png"));
    const pressed = String(await ev("[...document.styleSheets].some(s=>{try{return [...s.cssRules].some(r=>/:active/.test(r.selectorText||''))}catch(e){return false}})"));
    check("...and a pressed state (:active) for its button", pressed === "true", pressed);
    await nav(dev + "/no-such-page");
    await tapOn("a.btn");
    const afterLink = String(await ring("a.btn"));
    check("404 page: tapping a link leaves no focus ring", /^none /.test(afterLink), afterLink);
    await nav(dev + "/legal/delete-account.html");
    await tapOn("nav.docs a:nth-child(2)");
    const afterLegal = String(await ring("nav.docs a:nth-child(2)"));
    check("legal pages: tapping a link leaves no focus ring", /^none /.test(afterLegal), afterLegal);

    // ---------- 3. the starting-up screen's retries ----------
    // on a server of its own (no service worker there), with /healthz answering 503 as during a restart, then the real answer again
    const rs = await serve("dev");
    let healthAsked = 0, down = true;
    await send("Fetch.enable", { patterns: [{ urlPattern: "*/healthz*", requestStage: "Request" }] });
    on("Fetch.requestPaused", (p) => {
      healthAsked++;
      if (down) send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: 503, responseHeaders: [{ name: "Content-Type", value: "application/json" }], body: Buffer.from('{"ok":false}').toString("base64") });
      else send("Fetch.continueRequest", { requestId: p.requestId });
    });
    await nav(rs + "/uaply-offline.html");
    const t0 = await ev("performance.timeOrigin");
    healthAsked = 0;
    await sleep(7000);
    const plan = JSON.parse(await ev("JSON.stringify({first:__uaplyRetryWait(),a:__uaplyNextWait(3000,10000),b:__uaplyNextWait(3000,61000),c:__uaplyNextWait(12000,90000),d:__uaplyNextWait(15000,300000)})"));
    check("while the server answers 503 it checks /healthz about every 3 seconds and stays on the screen", healthAsked >= 2 && healthAsked <= 3 && (await ev("performance.timeOrigin")) === t0, healthAsked + " checks in 7 s");
    check("...every 3 seconds for the first minute, then 1.5 times longer each try, never more than 15 seconds",
      plan.first === 3000 && plan.a === 3000 && plan.b === 4500 && plan.c === 15000 && plan.d === 15000, JSON.stringify(plan));
    down = false;
    let reopened = false;
    for (let i = 0; i < 20 && !reopened; i++) { await sleep(250); try { reopened = (await ev("performance.timeOrigin")) !== t0; } catch (e) {} }
    check("the first 200 from /healthz reopens the page by itself (within one 3-second check)", reopened);
    await sleep(500);
    const t1 = await ev("performance.timeOrigin");                // the reopened page; its own first check is 3 seconds away
    const tb = await tapOn("#b");
    await sleep(1200);
    check("Try again with the server up reloads the page at once (before the next automatic check)", tb && (await ev("performance.timeOrigin")) !== t1);
    await send("Fetch.disable");
    const cc = (await fetch(dev + "/")).headers.get("cache-control"), cc2 = (await fetch(dev + "/uaply-offline.html")).headers.get("cache-control");
    check("the page it reopens (and the screen itself) is sent with Cache-Control: no-store, so a reload is never a saved copy", cc === "no-store" && cc2 === "no-store", cc + " / " + cc2);
  } finally {
    for (const p of procs) p.kill();
    for (const d of dirs) { try { fs.rmSync(d, { recursive: true, force: true }); } catch (e) {} }
    console.log("\n" + pass + " / " + (pass + fail));
    if (fail) process.exitCode = 1;
  }
};
