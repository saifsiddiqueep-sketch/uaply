// Makes the Google Play listing pictures in mobile/store/play/ from the app itself (headless Chrome, no image library):
//   icon-512.png             the app icon, 512 x 512, from mobile/assets/icon-only.png
//   feature-graphic.png      1024 x 500, the logo and the name on the app's own colours (24-bit, no transparency, as Play asks)
//   screenshots/phone/*.png  1080 x 1920 (a 432 x 768 phone screen at 2.5x): Jobs, Job Tracker, Profile setup, Filters, Help
//   screenshots/tablet/*.png 1080 x 1920 (a 675 x 1200 seven-inch tablet at 1.6x): the same screens
// It starts its own sandbox server on a free port with a temporary data folder and the built-in example jobs (no network), switches
// the sandbox to the same features as the release build (dev/index.html's PROMOTED list, so nothing sandbox-only is pictured), fills in
// an example person's profile and a few applications, and stops the server at the end. Run it again whenever the screens change:
//   node tools/cdp.js tools/make-play-assets.js
// tools/test-play-listing.py checks every picture's exact size and format afterwards.
const { spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const os = require("os");
const path = require("path");
const ROOT = path.join(__dirname, "..");
const OUT = path.join(ROOT, "mobile", "store", "play");
const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const freePort = () => new Promise((r) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => r(p)); }); });

const DEVICES = [
  { dir: "phone", width: 432, height: 768, scale: 2.5 },        // 1080 x 1920
  { dir: "tablet", width: 675, height: 1200, scale: 1.6 },      // 1080 x 1920, a seven-inch tablet's width
];
const PERSON = { name: "Jordan Lee", email: "jordan.lee@example.com", title: "Frontend Developer", years: 3, edu: "Bachelor",
  skills: ["JavaScript", "React", "TypeScript", "CSS", "HTML", "SQL", "Figma"], salary: 90000, loc: "Philadelphia, PA",
  modes: { remote: true, hybrid: true, onsite: true }, reloc: false, custom: true };

// Play wants the feature graphic and screenshots as 24-bit PNG (no alpha channel). Chrome and canvas write 32-bit RGBA PNGs, so this
// rewrites one as 8-bit RGB: inflate, undo the row filters, drop every fourth byte, filter none, deflate. Node's own zlib only.
function pngToRGB(buf) {
  const zlib = require("zlib");
  const SIG = buf.subarray(0, 8);
  let p = 8, w = 0, h = 0, depth = 0, type = 0;
  const idat = [];
  while (p < buf.length) {
    const len = buf.readUInt32BE(p), kind = buf.toString("latin1", p + 4, p + 8), body = buf.subarray(p + 8, p + 8 + len);
    if (kind === "IHDR") { w = body.readUInt32BE(0); h = body.readUInt32BE(4); depth = body[8]; type = body[9]; }
    if (kind === "IDAT") idat.push(body);
    p += 12 + len;
  }
  if (type === 2) return buf;                                     // already RGB
  if (type !== 6 || depth !== 8) throw new Error("unexpected PNG (colour type " + type + ", depth " + depth + ")");
  const raw = zlib.inflateSync(Buffer.concat(idat)), stride = w * 4, out = Buffer.alloc(h * (w * 3 + 1));
  let prev = Buffer.alloc(stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)], line = Buffer.from(raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1)));
    for (let i = 0; i < stride; i++) {
      const a = i >= 4 ? line[i - 4] : 0, b = prev[i], c = i >= 4 ? prev[i - 4] : 0;
      let v = line[i];
      if (f === 1) v += a; else if (f === 2) v += b; else if (f === 3) v += (a + b) >> 1;
      else if (f === 4) { const pp = a + b - c, pa = Math.abs(pp - a), pb = Math.abs(pp - b), pc = Math.abs(pp - c); v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c; }
      line[i] = v & 255;
    }
    const o = y * (w * 3 + 1);
    for (let x = 0; x < w; x++) { out[o + 1 + x * 3] = line[x * 4]; out[o + 2 + x * 3] = line[x * 4 + 1]; out[o + 3 + x * 3] = line[x * 4 + 2]; }
    prev = line;
  }
  const crcT = []; for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crcT[n] = c >>> 0; }
  const crc = (b) => { let c = 0xffffffff; for (const x of b) c = crcT[(c ^ x) & 255] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const chunk = (kind, body) => { const len = Buffer.alloc(4); len.writeUInt32BE(body.length); const kb = Buffer.from(kind, "latin1"); const cr = Buffer.alloc(4); cr.writeUInt32BE(crc(Buffer.concat([kb, body]))); return Buffer.concat([len, kb, body, cr]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([SIG, chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(out, { level: 9 })), chunk("IEND", Buffer.alloc(0))]);
}

module.exports = async ({ ev, sleep, nav, send }) => {
  fs.mkdirSync(path.join(OUT, "screenshots", "phone"), { recursive: true });
  fs.mkdirSync(path.join(OUT, "screenshots", "tablet"), { recursive: true });
  const save = async (file) => {                                  // the screen as Chrome draws it, written as a 24-bit PNG
    const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    fs.writeFileSync(file, pngToRGB(Buffer.from(r.result.data, "base64")));
  };

  // ---------- the icon and the feature graphic, drawn on a blank page ----------
  await nav("about:blank");
  const logo = "data:image/png;base64," + fs.readFileSync(path.join(ROOT, "mobile", "assets", "icon-only.png")).toString("base64");
  const art = JSON.parse(await ev(`(async () => {
    const img = new Image(); img.src = ${JSON.stringify(logo)}; await img.decode();
    const icon = document.createElement("canvas"); icon.width = icon.height = 512;
    const ix = icon.getContext("2d"); ix.imageSmoothingQuality = "high"; ix.drawImage(img, 0, 0, 512, 512);
    const g = document.createElement("canvas"); g.width = 1024; g.height = 500;
    const x = g.getContext("2d"); x.imageSmoothingQuality = "high";
    /* the app's light background with a soft rose glow, the logo, the name and one line, all on the left two thirds (Play may crop the edges) */
    x.fillStyle = "#FDF0F2"; x.fillRect(0, 0, 1024, 500);
    const glow = x.createRadialGradient(820, 120, 20, 820, 120, 520); glow.addColorStop(0, "rgba(240,102,59,0.30)"); glow.addColorStop(1, "rgba(240,102,59,0)");
    x.fillStyle = glow; x.fillRect(0, 0, 1024, 500);
    const glow2 = x.createRadialGradient(180, 460, 10, 180, 460, 420); glow2.addColorStop(0, "rgba(201,42,85,0.20)"); glow2.addColorStop(1, "rgba(201,42,85,0)");
    x.fillStyle = glow2; x.fillRect(0, 0, 1024, 500);
    x.save(); x.shadowColor = "rgba(42,18,24,0.28)"; x.shadowBlur = 36; x.shadowOffsetY = 14;
    const r = 48, s = 260, lx = 96, ly = 120;
    x.beginPath(); x.moveTo(lx + r, ly); x.arcTo(lx + s, ly, lx + s, ly + s, r); x.arcTo(lx + s, ly + s, lx, ly + s, r); x.arcTo(lx, ly + s, lx, ly, r); x.arcTo(lx, ly, lx + s, ly, r); x.closePath();
    x.fillStyle = "#240B28"; x.fill(); x.restore();
    x.save(); x.clip(); x.drawImage(img, lx, ly, s, s); x.restore();
    x.fillStyle = "#2A1218"; x.font = "800 104px 'Segoe UI', 'DM Sans', system-ui, sans-serif"; x.textBaseline = "alphabetic";
    x.fillText("UAply", 412, 250);
    const grad = x.createLinearGradient(412, 0, 900, 0); grad.addColorStop(0, "#C92A55"); grad.addColorStop(1, "#F0663B");
    x.fillStyle = grad; x.font = "700 40px 'Segoe UI', 'DM Sans', system-ui, sans-serif";
    x.fillText("Swipe right to apply.", 416, 316);
    x.fillStyle = "#7B5560"; x.font = "500 28px 'Segoe UI', 'DM Sans', system-ui, sans-serif";
    x.fillText("Real jobs, matched to your profile.", 418, 364);
    return JSON.stringify({ icon: icon.toDataURL("image/png").split(",")[1], graphic: g.toDataURL("image/png").split(",")[1] });
  })()`));
  fs.writeFileSync(path.join(OUT, "icon-512.png"), Buffer.from(art.icon, "base64"));
  fs.writeFileSync(path.join(OUT, "feature-graphic.png"), pngToRGB(Buffer.from(art.graphic, "base64")));
  console.log("wrote icon-512.png and feature-graphic.png");

  // ---------- the screenshots, from a sandbox server of its own ----------
  const port = await freePort(), base = "http://127.0.0.1:" + port;
  const data = fs.mkdtempSync(path.join(os.tmpdir(), "uaply-play-"));
  const proc = spawn(PY, [path.join(ROOT, "serve.py"), String(port), path.join(ROOT, "sandbox"), "--api"], { cwd: ROOT, stdio: "ignore",
    env: Object.assign({}, process.env, { UAPLY_DATA_DIR: data, UAPLY_CONFIG_FILE: "none", UAPLY_CONFIG_JSON: '{"feeds":[],"smtp":{}}', HOST: "127.0.0.1" }) });
  try {
    let upOk = false;
    for (let i = 0; i < 120 && !upOk; i++) { try { upOk = (await fetch(base + "/healthz")).ok; } catch (e) {} if (!upOk) await sleep(250); }
    if (!upOk) { console.log("FAIL the sandbox server did not start"); process.exitCode = 1; return; }
    const promoted = JSON.parse(/var PROMOTED=(\[[^\]]*\])/.exec(fs.readFileSync(path.join(ROOT, "dev", "index.html"), "utf8"))[1]);
    const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
    const q = (js) => ev("(()=>{try{const d=" + F + ",w=" + FW + ";" + js + "}catch(e){return 'ERR '+e.message}})()");
    const ready = async () => { for (let i = 0; i < 60; i++) { if ((await q("return !!(d.getElementById('nb-prof')&&w.__uaply)")) === true) return true; await sleep(250); } return false; };
    const go = async (nb, view) => {
      await q("d.getElementById('" + nb + "').click()"); await sleep(400);
      if (view) { const ok = await q("const e=[...d.querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='" + view + "');if(!e)return false;e.click();return true");
        if (ok !== true) { await q("d.getElementById('" + nb + "').click()"); await sleep(300); await q("const e=[...d.querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='" + view + "');if(e)e.click()"); } }
      await sleep(900);
      await q("d.scrollingElement.scrollTop=0;[...d.querySelectorAll('section,main,.screen')].forEach(s=>{s.scrollTop=0})");
      await sleep(250);
    };
    for (const dev of DEVICES) {
      await send("Emulation.setDeviceMetricsOverride", { width: dev.width, height: dev.height, deviceScaleFactor: dev.scale, mobile: true });
      await send("Emulation.setTouchEmulationEnabled", { enabled: true });
      await send("Browser.grantPermissions", { origin: base, permissions: ["geolocation"] });
      await send("Emulation.setGeolocationOverride", { latitude: 39.9526, longitude: -75.1652, accuracy: 100 });   // Philadelphia
      await send("Storage.clearDataForOrigin", { origin: base, storageTypes: "all" });
      await nav(base + "/?app=1");
      await ready();
      // an example person, three applications in different stages and one passed job
      const seeded = await q("const A=w.__uaply;Object.assign(A.S.profile," + JSON.stringify(PERSON) + ");const ids=A.JOBS.slice(0,6).map(j=>j.id),now=Date.now();" +
        "const st=[['applied','interview'],['applied',''],['applied','accepted'],['passed','']];" +
        "st.forEach((s,i)=>{if(ids[i+1]!==undefined){A.S.decisions[ids[i+1]]={s:s[0],st:s[1]||undefined,at:now-(i+1)*86400000*2,pct:88-i*6,as:'You',title:''};A.S.history.push(ids[i+1])}});" +
        "A.S.tips=false;A.save();return ids.length");
      await nav(base + "/?app=1");
      await ready();
      // the release build's features only: switch each sandbox experiment on or off to match dev's PROMOTED list (each switch reloads the
      // app; the switches live in the page, so this comes after the last page load)
      const chips = JSON.parse(await ev("JSON.stringify([...document.querySelectorAll('#feats button')].map(b=>[b.dataset.k,b.getAttribute('aria-pressed')==='true']))"));
      for (const [k, on] of chips) {
        if (on !== promoted.includes(k)) { await ev("document.querySelector('#feats button[data-k=\"" + k + "\"]').click()"); await sleep(150); }
      }
      await sleep(1500); await ready();
      await sleep(1200);
      await q("const b=d.getElementById('kcYes');if(b)b.click()"); await sleep(300);
      await q("const b=d.getElementById('tipsClose');if(b)b.click()"); await sleep(300);
      const dir = path.join(OUT, "screenshots", dev.dir);
      // nothing the release build does not have may be pictured: Hiring mode's switch, the "N jobs left" counter, the example-profile banner
      const extra = await q("const t=d.body.innerText;return [d.getElementById('modeSw')&&d.getElementById('modeSw').offsetParent?'Hiring mode switch':'',/job[s]? left/.test(t)?'jobs-left counter':'',/example profile/i.test(t)?'example-profile banner':''].filter(Boolean).join(', ')");
      if (extra) { console.log("FAIL the " + dev.dir + " screen shows what the release build does not have: " + extra); process.exitCode = 1; }
      await save(path.join(dir, "1-jobs.png"));                   // the deck is the first screen
      await go("nb-dash", "applied"); await save(path.join(dir, "2-job-tracker.png"));
      await go("nb-prof", "settings");
      await q("const b=[...d.querySelectorAll('button')].find(x=>{const t=x.innerText.trim();return x.offsetParent&&t.charAt(0)==='1'&&t.length<4});if(b)b.click()"); await sleep(600);   // step 1, About you
      await q("d.scrollingElement.scrollTop=0"); await sleep(200);
      await save(path.join(dir, "3-profile.png"));
      await go("nb-prof", "filters"); await save(path.join(dir, "4-filters.png"));
      await go("nb-svc", "job");
      await q("const b=d.getElementById('uaChatBtn');if(b)b.click()"); await sleep(1200);
      await save(path.join(dir, "5-help.png"));
      console.log("wrote the " + dev.dir + " screenshots (" + seeded + " example jobs used)");
    }
  } finally {
    proc.kill();
    try { fs.rmSync(data, { recursive: true, force: true }); } catch (e) {}
  }
};
