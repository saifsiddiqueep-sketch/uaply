// The installable website in a real Chrome: Chrome finds nothing missing to install it (manifest, icons, service worker, a secure
// origin), the service worker saves only its offline screen and icon (never /api/), and that screen really shows when the server is down,
// when the host answers 502 during a deploy, and when the phone is offline, then opens the app by itself once the server is back.
// It starts and stops its own servers on a free port (temporary data folder), so nothing needs to be running:
//   node tools/cdp.js tools/ui-installable.js
const { spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const os = require("os");
const path = require("path");
const ROOT = path.join(__dirname, "..");

const freePort = () => new Promise((r) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => r(p)); }); });
const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");

module.exports = async ({ ev, sleep, nav, send }) => {
  let pass = 0, fail = 0, proc = null;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + name + (ok || extra === undefined ? "" : "  -> " + extra)); return ok; };
  const port = await freePort(), base = "http://127.0.0.1:" + port;
  const data = fs.mkdtempSync(path.join(os.tmpdir(), "uaply-installable-"));
  const up = async () => { for (let i = 0; i < 120; i++) { try { if ((await fetch(base + "/healthz")).ok) return true; } catch (e) {} await sleep(250); } return false; };
  const down = async () => { for (let i = 0; i < 80; i++) { try { await fetch(base + "/healthz"); } catch (e) { return true; } await sleep(250); } return false; };
  const startReal = () => spawn(PY, [path.join(ROOT, "serve.py"), String(port), path.join(ROOT, "dev"), "--api"], { cwd: ROOT, stdio: "ignore",
    env: Object.assign({}, process.env, { UAPLY_DATA_DIR: data, UAPLY_CONFIG_FILE: "none", UAPLY_CONFIG_JSON: '{"feeds":[],"smtp":{}}', HOST: "127.0.0.1" }) });
  // a stand-in for the host during a deploy: every address answers 502 Bad Gateway, /healthz too
  const start502 = () => spawn(PY, ["-c", "import http.server,sys\nclass H(http.server.BaseHTTPRequestHandler):\n def do_GET(s):\n  s.send_response(502);s.send_header('Content-Length','11');s.end_headers();s.wfile.write(b'Bad Gateway')\n def log_message(s,*a):pass\nhttp.server.HTTPServer(('127.0.0.1',int(sys.argv[1])),H).serve_forever()", String(port)], { stdio: "ignore" });
  const stop = async () => { if (proc) { proc.kill(); proc = null; } await down(); };
  const text = () => ev("document.body?document.body.innerText:''");
  const waitText = async (re, ms) => { const end = Date.now() + ms; let t = ""; while (Date.now() < end) { t = String(await text()); if (re.test(t)) return t; await sleep(300); } return t; };
  try {
    proc = startReal();
    if (!check("the test server starts", await up())) return;
    await nav(base + "/");
    await sleep(1500);

    // 1. installable: the manifest Chrome found, and Chrome's own list of reasons it could not be installed (none)
    const man = await send("Page.getAppManifest");
    const mr = man.result || {};
    check("Chrome reads the web manifest the page links (" + (mr.url || "none") + ") without errors", /\/uaply\.webmanifest$/.test(mr.url || "") && !(mr.errors || []).length,
      JSON.stringify(mr.errors));
    let inst = null;
    for (let i = 0; i < 20; i++) {                                  // the worker may still be installing on the first ask
      inst = await send("Page.getInstallabilityErrors");
      if (inst.result && (inst.result.installabilityErrors || []).length === 0) break;
      await sleep(500);
    }
    const errs = inst && inst.result ? inst.result.installabilityErrors : null;
    check("Chrome finds nothing missing to install the site as an app (Page.getInstallabilityErrors is empty)", Array.isArray(errs) && errs.length === 0, JSON.stringify(errs || inst));
    const sw = await ev("navigator.serviceWorker.ready.then(r=>JSON.stringify({scope:r.scope,script:r.active&&r.active.scriptURL}))");
    check("the service worker is active for the whole site", sw === JSON.stringify({ scope: base + "/", script: base + "/uaply-sw.js" }), sw);

    // 2. what it saved, after the app has called the API and a legal page has been opened: only the offline screen and its icon
    await nav(base + "/");                                         // now the page is controlled by the worker
    await ev("Promise.all(['/api/auth/me','/api/jobs','/api/billing/status','/uaply-nav.js'].map(u=>fetch(u).then(r=>r.text()).catch(()=>0)))");
    await nav(base + "/legal/terms.html");
    const saved = await ev("caches.keys().then(ks=>Promise.all(ks.map(k=>caches.open(k).then(c=>c.keys()).then(rs=>k+': '+rs.map(r=>new URL(r.url).pathname).sort().join(','))))).then(a=>a.join(' | '))");
    check("its cache holds only the offline screen and its icon: nothing from /api/, no app code, no pages", saved === "uaply-shell-v1: /uaply-icon-192.png,/uaply-offline.html", saved);
    const ctl = await ev("!!navigator.serviceWorker.controller");
    check("pages are controlled by it (so the next checks test the worker, not the browser)", ctl === true, String(ctl));
    await nav(base + "/legal");
    const lg = await waitText(/UAply legal/, 5000);
    check("a server redirect still works through it (/legal goes on to /legal/)", /UAply legal/.test(lg) && (await ev("location.pathname")) === "/legal/", lg.slice(0, 80));

    // 3. the server is down (no connection at all): the saved screen, with its icon, at the address asked for
    await stop();
    await nav(base + "/");
    const t1 = await waitText(/starting up/, 8000);
    check("server down: opening UAply shows the saved \"UAply is starting up\" screen instead of Chrome's error page", /UAply is starting up/.test(t1) && /Try again/.test(t1), t1.slice(0, 160));
    check("...at the address that was asked for (so its retry opens that page)", (await ev("location.pathname")) === "/");
    check("...with its icon, from the saved copy", (await ev("(()=>{const i=document.querySelector('img');return !!(i&&i.complete&&i.naturalWidth>0)})()")) === true);
    await send("Network.enable");
    await send("Network.emulateNetworkConditions", { offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    const t2 = await waitText(/You're offline/, 5000);
    check("the phone goes offline: the screen says so (\"You're offline\")", /You're offline/.test(t2), t2.slice(0, 160));
    await send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    await nav(base + "/api/auth/me");
    const t3 = String(await text());
    check("server down: an /api/ address is NOT answered by the worker (Chrome's own error, never the saved screen)", !/starting up|You're offline/.test(t3), t3.slice(0, 120));

    // 4. a deploy: the host answers 502; then the real server comes back and the screen opens the app by itself
    proc = start502();
    await sleep(800);
    await nav(base + "/legal/privacy.html");
    const t4 = await waitText(/starting up/, 8000);
    check("the host answers 502 Bad Gateway (a deploy): the saved screen shows instead of the bare 502", /UAply is starting up/.test(t4) && !/Bad Gateway/.test(t4), t4.slice(0, 160));
    await stop();
    proc = startReal();
    check("the real server comes back", await up());
    const t5 = await waitText(/Privacy Policy/, 20000);
    check("...and within seconds the screen reopens the page that was asked for, by itself", /Privacy Policy/.test(t5) && (await ev("location.pathname")) === "/legal/privacy.html", t5.slice(0, 160));
  } finally {
    if (proc) proc.kill();
    try { fs.rmSync(data, { recursive: true, force: true }); } catch (e) {}
    console.log("\n" + pass + " / " + (pass + fail));
    if (fail) process.exitCode = 1;
  }
};
