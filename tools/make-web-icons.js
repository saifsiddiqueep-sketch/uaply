// Makes the installable website's icons (shared/uaply-icon-*.png, listed in shared/uaply.webmanifest) from the app logo
// mobile/assets/icon-only.png, in headless Chrome (no image library needed). Run it again only when the logo changes:
//   node tools/cdp.js tools/make-web-icons.js
// "any" icons: the logo as it is (its own rounded square). "maskable" icons: Android crops them to a circle, a squircle or a rounded
// square, so the logo is drawn at 90% on a full square of its own dark edge colour: the whole U stays inside the 80% safe circle (its tips reach 40%).
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..");
module.exports = async ({ ev }) => {
  const src = "data:image/png;base64," + fs.readFileSync(path.join(ROOT, "mobile", "assets", "icon-only.png")).toString("base64");
  const out = await ev(`(async () => {
    const img = new Image(); img.src = ${JSON.stringify(src)}; await img.decode();
    const probe = document.createElement("canvas"); probe.width = img.width; probe.height = img.height;
    const pc = probe.getContext("2d"); pc.drawImage(img, 0, 0);
    const px = (x, y) => Array.from(pc.getImageData(Math.round(x * img.width), Math.round(y * img.height), 1, 1).data);
    const bg = px(0.02, 0.5);                                   /* the dark edge of the logo, so the extra border blends in */
    const make = (size, maskable) => {
      const c = document.createElement("canvas"); c.width = c.height = size;
      const x = c.getContext("2d"); x.imageSmoothingEnabled = true; x.imageSmoothingQuality = "high";
      if (maskable) { x.fillStyle = "rgb(" + bg[0] + "," + bg[1] + "," + bg[2] + ")"; x.fillRect(0, 0, size, size); const s = size * 0.9, o = (size - s) / 2; x.drawImage(img, o, o, s, s); }
      else x.drawImage(img, 0, 0, size, size);
      return c.toDataURL("image/png").split(",")[1];
    };
    return JSON.stringify({ corner: px(0.01, 0.01), bg, icons: { "192": make(192, false), "512": make(512, false), "maskable-192": make(192, true), "maskable-512": make(512, true) } });
  })()`);
  const r = JSON.parse(out);
  console.log("logo corner pixel (RGBA):", r.corner.join(","), " background used for the maskable icons:", r.bg.slice(0, 3).join(","));
  for (const [name, b64] of Object.entries(r.icons)) {
    const f = path.join(ROOT, "shared", "uaply-icon-" + name + ".png");
    fs.writeFileSync(f, Buffer.from(b64, "base64"));
    console.log("wrote", path.relative(ROOT, f), Math.round(fs.statSync(f).size / 1024) + " KB");
  }
};
