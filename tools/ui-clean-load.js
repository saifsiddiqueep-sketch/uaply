// A signed-out visitor's first visit leaves a clean console: no failed request (no 4xx or 5xx from UAply's own server) and no console
// error, on the swipe deck and once the job list has arrived. Testers read any red line in the console as a fault (October 22: a 401 from
// GET /api/employer/me on every load of the sandbox).
//   W=390 H=844 PORT=<sandbox or dev port> node tools/cdp.js tools/ui-clean-load.js        (also W=1280 H=800)
module.exports = async ({ ev, sleep, nav, send, on, logs }) => {
  const PORT = process.env.PORT, W = Number(process.env.W || 390), H = Number(process.env.H || 844);
  const base = "http://127.0.0.1:" + PORT;
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra && !ok ? "  " + extra : "")); };
  const failed = [], errors = [], asked = [];
  on("Network.responseReceived", (p) => {
    const u = p.response.url;
    if (u.startsWith(base)) asked.push(u.slice(base.length).split("?")[0]);
    if (p.response.status >= 400 && u.startsWith(base)) failed.push(p.response.status + " " + u.slice(base.length));
  });
  on("Log.entryAdded", (p) => { if (p.entry.level === "error" && (!p.entry.url || p.entry.url.startsWith(base))) errors.push(p.entry.text.slice(0, 160) + (p.entry.url ? " (" + p.entry.url.slice(base.length) + ")" : "")); });
  await send("Network.enable");
  await send("Log.enable");
  if (W >= 700) await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await nav(base + "/?app=1");
  for (let i = 0; i < 60 && !(await ev("(()=>{const w=document.querySelector('iframe')&&document.querySelector('iframe').contentWindow;return !!(w&&w.__uaply&&w.__uaply.JOBS.filter(j=>j.live).length>5)})()")); i++) await sleep(500);
  await sleep(4000);
  console.log("   asked the server for: " + [...new Set(asked)].filter((u) => u.startsWith("/api/")).join(", "));
  check("a first visit, signed out: no request to UAply's server fails (no 4xx, no 5xx)", failed.length === 0, JSON.stringify(failed));
  check("...and the console shows no error (no 'Failed to load resource', no script error)", errors.length === 0 && logs.filter((l) => !/favicon/.test(l)).length === 0, JSON.stringify(errors.concat(logs)));
  check("...and nobody asks for a company while signed out (/api/employer/me)", !asked.includes("/api/employer/me"), JSON.stringify([...new Set(asked)]));
  console.log("\n" + (n - bad) + " / " + n);
};
