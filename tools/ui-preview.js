// The public hosted copies (GitHub Pages: /uaply/sandbox.html, /uaply/dev.html, and /uaply/dev/ and /uaply/sandbox/) have no server. Builds them with share/build-share.js, serves
// them from a plain static server laid out like GitHub Pages (anything else, /api/* included, is a 404 HTML page), and checks at phone size
// that Account, Plan & billing, a swipe right and the help assistant say plainly that this is a preview, never "Cannot reach UAply" or
// "check your internet", and that no script error happens.
//   W=390 H=844 PREVIEW_PORT=18786 node tools/cdp.js tools/ui-preview.js
const fs = require("fs"), os = require("os"), path = require("path"), http = require("http"), { spawnSync } = require("child_process");
const PORT = +(process.env.PREVIEW_PORT || 18786);
const ROOT = path.join(__dirname, "..");
const PREVIEW = "This is a preview with example jobs and no server, so sign-in, applying and email are off here. The real site is uaply.net.";
const WRONG = /Cannot reach UAply|check your (internet|connection)|couldn't reach|Could not reach|unexpected reply|Something went wrong|undefined|\[object Object\]|\bNaN\b/i;

function site() {   // the same steps as .github/workflows/pages.yml
  const b = spawnSync(process.execPath, ["share/build-share.js", "--full"], { cwd: ROOT, encoding: "utf8" });
  if (b.status !== 0) throw new Error("share/build-share.js failed: " + b.stderr);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "uaply-preview-")), top = path.join(dir, "uaply");
  for (const [k, src] of [["dev", "dev.full.html"], ["sandbox", "sandbox.full.html"]]) {
    fs.mkdirSync(path.join(top, k), { recursive: true });
    fs.copyFileSync(path.join(ROOT, "share", src), path.join(top, k, "index.html"));
    for (const icon of ["favicon-32.png", "favicon-192.png", "apple-touch-icon.png"]) fs.copyFileSync(path.join(ROOT, k, icon), path.join(top, k, icon));
    // and the names published since October 22: /uaply/sandbox.html, /uaply/dev.html (and .full.html), with the icons beside them
    fs.copyFileSync(path.join(ROOT, "share", src), path.join(top, k + ".html"));
    fs.copyFileSync(path.join(ROOT, "share", src), path.join(top, k + ".full.html"));
    for (const icon of ["favicon-32.png", "favicon-192.png", "apple-touch-icon.png"]) fs.copyFileSync(path.join(ROOT, k, icon), path.join(top, icon));
  }
  fs.cpSync(path.join(ROOT, "legal"), path.join(top, "legal"), { recursive: true });
  return dir;
}
function serve(dir) {   // a plain static host: files only, every other address (and every POST) gets an HTML error page, like GitHub Pages
  const types = { ".html": "text/html; charset=utf-8", ".png": "image/png", ".css": "text/css", ".js": "text/javascript" };
  return new Promise((ok) => {
    const s = http.createServer((q, r) => {
      let p = decodeURIComponent(q.url.split("?")[0]);
      if (p.endsWith("/")) p += "index.html";
      const f = path.join(dir, path.normalize(p).replace(/^([/\\])+/, ""));
      if (q.method === "GET" && f.startsWith(dir) && fs.existsSync(f) && fs.statSync(f).isFile()) {
        r.writeHead(200, { "Content-Type": types[path.extname(f)] || "application/octet-stream" }); return r.end(fs.readFileSync(f));
      }
      r.writeHead(q.method === "GET" ? 404 : 405, { "Content-Type": "text/html; charset=utf-8" });
      r.end("<!DOCTYPE html><html><body><h1>404</h1><p>File not found</p></body></html>");
    });
    s.listen(PORT, "127.0.0.1", () => ok(s));
  });
}

module.exports = async ({ ev, sleep, nav, logs }) => {
  let bad = 0;
  const check = (name, good, extra) => { if (!good) bad++; console.log((good ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const F = "document.querySelector('iframe').contentDocument";
  const text = (sel) => ev("(()=>{const e=" + F + ".querySelector(" + JSON.stringify(sel) + ");return e?e.innerText.split(/\\s+/).join(' '):''})()");
  const dir = site(), srv = await serve(dir);
  try {
    for (const [copy, at] of [["dev", "dev/"], ["sandbox", "sandbox/"], ["dev", "dev.html"], ["sandbox", "sandbox.html"]]) {
      const before = logs.length;
      console.log("   -- /uaply/" + at);
      await nav("http://127.0.0.1:" + PORT + "/uaply/" + at); await sleep(3500);
      await ev("(()=>{const y=" + F + ".getElementById('kcYes');if(y)y.click()})()");          // a first-visit box, if any
      // Account: the header's Sign in button, then Sign in / Create account
      await ev(F + ".getElementById('hdrAcct').click()"); await sleep(700);
      let acct = await text("#acctSec");
      console.log("   [" + copy + "] Account says:", acct.slice(0, 220));
      check("[" + copy + "] Account says it is a preview with no server", acct.includes(PREVIEW), "");
      check("[" + copy + "] Account never says 'Cannot reach UAply' or 'check your internet'", !WRONG.test(acct), (acct.match(WRONG) || [""])[0]);
      check("[" + copy + "] Account links to the real site", await ev("!!" + F + ".querySelector('#acctSec a[href=\"https://uaply.net\"]')"));
      // every button on the Account screen does something visible (a message, a new screen) or is a plain link
      const clicked = await ev("(async()=>{const d=" + F + ",out=[];for(const b of [...d.querySelectorAll('#acctSec button')].filter(x=>x.offsetParent)){const t=b.innerText.trim(),before=d.getElementById('acctSec').innerText;b.click();await new Promise(r=>setTimeout(r,500));const after=d.getElementById('acctSec').innerText;out.push([t,after!==before]);if(after!==before)break}return out})()");
      check("[" + copy + "] the first Account button that is pressed changes what the screen says (never silently nothing)", clicked.length === 0 || clicked.some((x) => x[1]), JSON.stringify(clicked));
      acct = await text("#acctSec");
      check("[" + copy + "] ...and still no 'Cannot reach' or internet wording", !WRONG.test(acct), (acct.match(WRONG) || [""])[0]);
      // Plan & billing (the release copy would otherwise offer sign-in buttons that cannot work)
      if (copy === "dev") {
        await ev("(()=>{const d=" + F + ";d.getElementById('nb-prof').click();const it=d.querySelector('.nwrap[data-k=prof] .nitem[data-v=plan]');if(it)it.click()})()"); await sleep(600);
        const plan = await text("#acctSec");
        check("[dev] Plan & billing says it is a preview", plan.includes(PREVIEW) && !WRONG.test(plan), plan.slice(0, 160));
      }
      // swipe right on the top card
      await ev("(()=>{const d=" + F + ";d.getElementById('nb-svc').click();const it=d.querySelector('.nwrap[data-k=svc] .nitem[data-v=job]');if(it)it.click()})()"); await sleep(600);
      const card = await ev("(()=>{const c=" + F + ".querySelector('.card.top h2');return c?c.textContent:''})()");
      check("[" + copy + "] the deck shows example jobs", !!card, card);
      await ev(F + ".getElementById('btnYes').click()"); await sleep(900);
      const toast = await ev("(()=>{const t=[..." + F + ".querySelectorAll('.toast')].map(x=>x.innerText).join(' | ');return t.split(/\\s+/).join(' ')})()");
      console.log("   [" + copy + "] after a swipe right:", toast.slice(0, 220));
      check("[" + copy + "] a swipe right says it was saved on this device and that applying is off in the preview", /Saved .* to Applied/.test(toast) && toast.includes(PREVIEW) && !WRONG.test(toast), toast.slice(0, 160));
      // the help assistant: a question, and Talk to a person
      check("[" + copy + "] the Help button is there", await ev("!!" + F + ".getElementById('uaChatBtn')"));
      await ev(F + ".getElementById('uaChatBtn').click()"); await sleep(500);
      const said = async () => (await text("#uaChatLog")).split(PREVIEW).length - 1;    // how many times the assistant has said the preview line
      const n0 = await said();
      await ev("(()=>{const d=" + F + ";const b=[...d.querySelectorAll('#uaChatLog .chips button')].find(x=>x.innerText==='Talk to a person');if(b)b.click()})()"); await sleep(900);
      const help = await text("#uaChatLog");
      console.log("   [" + copy + "] help, Talk to a person:", help.slice(-200));
      check("[" + copy + "] Talk to a person says it is a preview and points to uaply.net", (await said()) > n0 && !WRONG.test(help) && await ev("!!" + F + ".querySelector('#uaChatLog a[href=\"https://uaply.net\"]')"), help.slice(-160));
      const n1 = await said();
      await ev("(()=>{const d=" + F + ",i=d.getElementById('uaChatIn');i.value='How do I apply?';d.getElementById('uaChatF').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))})()"); await sleep(1200);
      const ans = await text("#uaChatLog");
      check("[" + copy + "] a typed question gets the preview answer, not an error", (await said()) > n1 && !WRONG.test(ans), ans.slice(-160));
      const errs = logs.slice(before).filter((l) => !/Failed to load resource|status of 40[45]/i.test(l));
      check("[" + copy + "] no script errors", errs.length === 0, errs.slice(0, 3).join(" | "));
    }
  } finally {
    srv.close();
    try { fs.rmSync(dir, { recursive: true, force: true }); } catch (e) {}
  }
  console.log(bad ? bad + " problem(s)" : "All good");
};
