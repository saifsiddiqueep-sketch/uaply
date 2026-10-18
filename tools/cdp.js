// Minimal headless-Chrome driver for UI tests. Usage: node tools/cdp.js tools/<test>.js
// A test file exports async ({ev, sleep, nav, shot, logs, send}) => {}. ev(expr) runs JS in the page and returns its value.
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

// Which Chrome to start: UAPLY_CHROME if set, else the usual Windows install, else common Linux/Mac places
// (a Playwright Chromium under /opt/pw-browsers, google-chrome, chromium, the Mac app).
function findChrome() {
  if (process.env.UAPLY_CHROME) return process.env.UAPLY_CHROME;
  const win = path.join(process.env.LOCALAPPDATA || "", "Google", "Chrome", "Application", "chrome.exe");
  if (fs.existsSync(win)) return win;
  const pw = process.env.PLAYWRIGHT_BROWSERS_PATH || "/opt/pw-browsers";
  try {
    for (const d of fs.readdirSync(pw).filter((n) => /^chromium-\d+$/.test(n)).sort().reverse()) {
      for (const sub of ["chrome-linux", "chrome-linux64"]) {
        const p = path.join(pw, d, sub, "chrome");
        if (fs.existsSync(p)) return p;
      }
    }
  } catch (e) {}
  const dirs = (process.env.PATH || "").split(path.delimiter);
  for (const name of ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]) {
    for (const d of dirs) { const p = path.join(d, name); if (d && fs.existsSync(p)) return p; }
  }
  const mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  if (fs.existsSync(mac)) return mac;
  return win;                                             // not found: keep the old path so the error names it
}
const CHROME = findChrome();
// Chrome refuses to start as root on Linux (containers) unless its sandbox is off
const EXTRA = process.platform === "linux" && process.getuid && process.getuid() === 0 ? ["--no-sandbox"] : [];
// Chrome keeps a socket file under TMPDIR, and on Linux/Mac a socket path longer than about 100 characters fails, so Chrome
// never answers. A long TMPDIR (a test runner's own folder) did that: then Chrome and its profile use /tmp instead.
const TMP = process.platform !== "win32" && os.tmpdir().length > 60 && fs.existsSync("/tmp") ? "/tmp" : os.tmpdir();

let failed = false;                                       // set when the test prints a FAIL line, so the runner (run-all-tests.sh) can see it
const _log = console.log;
console.log = (...a) => { const t = a.join(" "); if (/^FAIL\b|^TEST SCRIPT FAILED/.test(t)) failed = true; _log(...a); };
// a test that hangs says so and fails, instead of going silent until the runner's time limit. A test that waits on a person (ui-live.js waits
// for a code typed from an inbox) may ask for longer by exporting limitMs.
const TEST = require(path.resolve(process.argv[2]));
const LIMIT = Number(process.env.CDP_LIMIT_MS || TEST.limitMs || 540000);
setTimeout(() => { console.log("TEST SCRIPT FAILED: no result after " + Math.round(LIMIT / 1000) + " s (the page or Chrome stopped responding)"); process.exit(1); }, LIMIT).unref();

// start headless Chrome and connect; if it does not answer (a busy computer, a port already taken), try a fresh one, up to 3 times
async function launch() {
  for (let attempt = 1; attempt <= 3; attempt++) {
    const port = 9300 + Math.floor(Math.random() * 500);
    const profile = fs.mkdtempSync(path.join(TMP, "uaply-cdp-"));
    const proc = spawn(CHROME, [...EXTRA, "--headless=new", "--disable-gpu", "--remote-debugging-port=" + port, "--user-data-dir=" + profile,
      "--window-size=" + (process.env.W || 1100) + "," + (process.env.H || 900), "about:blank"], { stdio: "ignore", env: Object.assign({}, process.env, { TMPDIR: TMP }) });
    let tab;
    for (let i = 0; i < 75 && !tab; i++) {
      try { tab = (await (await fetch("http://127.0.0.1:" + port + "/json")).json()).find((t) => t.type === "page"); } catch (e) {}
      if (!tab) await new Promise((r) => setTimeout(r, 200));
    }
    if (tab) {
      const ws = new WebSocket(tab.webSocketDebuggerUrl);
      const opened = await new Promise((r) => { ws.onopen = () => r(true); ws.onerror = () => r(false); setTimeout(() => r(false), 15000); });
      if (opened) return { proc, profile, ws };
      try { ws.close(); } catch (e) {}
    }
    proc.kill();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) {}
    console.error("Chrome did not answer (attempt " + attempt + " of 3); starting a fresh one");
  }
  console.log("TEST SCRIPT FAILED: Chrome would not start after 3 tries");
  process.exit(1);
}

(async () => {
  const { proc, profile, ws } = await launch();
  let id = 0;
  const pending = {};
  const logs = [];
  const listeners = {};
  const on = (method, fn) => { listeners[method] = fn; };          // a test can react to browser events, for example to fail a request on purpose
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.method && listeners[d.method]) { try { listeners[d.method](d.params); } catch (e) { logs.push("LISTENER " + e.message); } }
    if (d.id && pending[d.id]) { pending[d.id](d); delete pending[d.id]; }
    else if (d.method === "Runtime.exceptionThrown") {
      const x = d.params.exceptionDetails;
      logs.push("EXC " + ((x.exception && x.exception.description) || x.text).split("\n")[0]);
    } else if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") {
      logs.push("ERR " + d.params.args.map((a) => a.value || a.description).join(" ").slice(0, 200));
    }
  };
  // sessionId: a frame Chrome attached us to (Target.setAutoAttach with flatten), e.g. a cross-origin iframe running in its own process
  const send = (method, params = {}, sessionId) => new Promise((r) => {
    const i = ++id; pending[i] = r; ws.send(JSON.stringify(sessionId ? { id: i, method, params, sessionId } : { id: i, method, params }));
  });
  await send("Runtime.enable");
  await send("Page.enable");
  if (process.env.W && Number(process.env.W) < 700) {          // phone sizes: real device emulation (a headless window cannot go below ~500px)
    await send("Emulation.setDeviceMetricsOverride", { width: Number(process.env.W), height: Number(process.env.H || 844), deviceScaleFactor: 3, mobile: true });
    await send("Emulation.setTouchEmulationEnabled", { enabled: true });
  }
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const ev = async (expr) => {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.result.exceptionDetails) return "JSERR " + r.result.exceptionDetails.exception.description.split("\n")[0];
    return r.result.result.value;
  };
  const nav = async (u) => { await send("Page.navigate", { url: u }); await sleep(2500); };
  const shot = async (f) => { const r = await send("Page.captureScreenshot", { format: "png" }); fs.writeFileSync(f, Buffer.from(r.result.data, "base64")); };
  try { await TEST({ ev, sleep, nav, shot, logs, send, on }); }
  catch (e) { console.log("TEST SCRIPT FAILED:", e.message); }
  console.log("CONSOLE ISSUES:", logs.length ? "\n" + logs.join("\n") : "none");
  ws.close(); proc.kill();
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) {}
  process.exit(failed || process.exitCode ? 1 : 0);      // a FAIL line, a crashed test script or exitCode set by the test makes the whole run fail
})();
