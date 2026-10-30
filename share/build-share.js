/* Builds self-contained, hostable copies of the sandbox and dev pages into share/.
   Run from the project folder:  node share/build-share.js
   The hosted copies have no server, so Real jobs, Apply assistant and Send applications are left out, and UAplyOpts.preview tells the
   pages so: Account, Plan, a swipe right and the help assistant then say "This is a preview ... The real site is uaply.net."
   Every <script src="uaply-NAME.js"></script> the page lists is replaced, where it stands, by shared/uaply-NAME.js inlined, so a new
   experiment file added to sandbox/index.html or dev/index.html is in the hosted copy without a change here (the static host answers 404
   for any uaply-*.js left as a link). Files whose features need the server are inlined too; NEEDS_SERVER below keeps those features off.
   prod/index.html is only read, never written. */
const fs = require("fs");
const read = (p) => fs.readFileSync(p, "utf8");
const prod = read("prod/index.html");
let envs = read("shared/uaply-envs.js");

const NEEDS_SERVER = ["live", "kit", "submit", "resume"];   // Fill from your resume reads the file on the server
envs = envs.replace(/fetch\("prod-index\.html",\{cache:"no-store"\}\)\.then\(function\(r\)\{return r\.text\(\)\}\)/, "Promise.resolve(window.__PROD_SRC)");
envs = envs.replace(/var ORDER=\[([^\]]*)\];/, (m, list) => {
  const kept = list.split(",").map((s) => s.trim()).filter((s) => !NEEDS_SERVER.includes(s.replace(/"/g, "")));
  return "var ORDER=[" + kept.join(",") + "];";
});
if (envs.includes('fetch("prod-index.html"')) throw new Error("envs patch failed");

const safe = (s) => s.replace(/<\/script/gi, "<\\/script");
const SKIP = new Set(["live"]);   // uaply-live.js talks to the server (applying, receipts); the hosted copy has none, so it stays out as it always did
const SCRIPT_TAG = /<script src="uaply-([a-z0-9-]+)\.js"><\/script>/g;
// shared/uaply-NAME.js as one inline script (envs with the patches above)
function inlineScript(name) {
  const file = "shared/uaply-" + name + ".js";
  if (!fs.existsSync(file)) throw new Error("the page loads uaply-" + name + ".js but " + file + " does not exist");
  return "<script>" + safe(name === "envs" ? envs : read(file)) + "</script>";
}

function darkBlocks(html) {
  // add the guarded dark block and the explicit data-theme block so the host theme toggle works
  return html.replace(/@media \(prefers-color-scheme: dark\)\{:root\{([^}]*)\}\}/, (m, vars) =>
    "@media (prefers-color-scheme: dark){:root:not([data-theme=\"light\"]){" + vars + ";color-scheme:dark}}\n:root[data-theme=\"dark\"]{" + vars + ";color-scheme:dark}");
}

// extras: names of shared/uaply-NAME.js files added after the page's own scripts, each only when the page does not already list it
function build(src, out, title, edits, extras) {
  let h = read(src);
  const viewport = (h.match(/<meta name="viewport" content="([^"]*)"/i) || [])[1] || "width=device-width,initial-scale=1";
  const names = [...h.matchAll(SCRIPT_TAG)].map((m) => m[1]);
  if (!names.includes("envs")) throw new Error("uaply-envs.js is not among the script tags in " + src);
  const done = new Set();
  let i = -1;
  h = h.replace(SCRIPT_TAG, (tag, name) => {   // each tag becomes its file, in place, so the page's order is kept
    i++;
    let s = i === 0 ? "<script>window.__PROD_SRC=" + JSON.stringify(prod).replace(/</g, "\\u003c") + ";</script>\n" : "";
    if (SKIP.has(name)) { done.add(name); }                               // needs the server: left out of the hosted copy, as before (its feature is off in the on list too)
    else if (!done.has(name)) { done.add(name); s += inlineScript(name); }   // a file listed twice is embedded once
    if (i === names.length - 1) (extras || []).filter((x) => !done.has(x)).forEach((x) => { done.add(x); s += "\n" + inlineScript(x); });
    return s;
  });
  if (!h.includes("__PROD_SRC")) throw new Error("script tags not found in " + src);
  if (/<script[^>]*\bsrc="[^"]*uaply-[^"]*\.js"/.test(h)) throw new Error("a uaply-*.js script link is left in " + src + " (the static host answers 404 for it)");
  console.log("embedded in", out + ":", [...done].join(", "));
  h = h.replace(/<title>[^<]*<\/title>/, "<title>" + title + "</title>");
  // the installable-website parts (web manifest, service worker) need UAply's own server, which a hosted copy does not have
  h = h.replace(/<link rel="manifest"[^>]*>\s*/, "").replace(/<script>\/\* the installable website:[\s\S]*?<\/script>\s*/, "");
  if (/rel="manifest"|uaply-sw\.js/.test(h)) throw new Error("the manifest link or the service worker is still in " + src);
  edits.forEach(([a, b]) => { if (!h.includes(a)) throw new Error("edit target missing: " + a.slice(0, 40)); h = h.replace(a, () => b); });
  h = darkBlocks(h);
  // the host adds the document skeleton
  h = h.replace(/<!doctype html>\s*/i, "").replace(/<html[^>]*>\s*/i, "").replace(/<head>\s*/i, "").replace(/<\/head>\s*/i, "")
       .replace(/<meta charset="utf-8">\s*/i, "").replace(/<meta name="viewport"[^>]*>\s*/i, "").replace(/<body>\s*/i, "").replace(/<\/body>\s*/i, "").replace(/<\/html>\s*/i, "");
  fs.writeFileSync(out, h);
  console.log("wrote", out, Math.round(h.length / 1024) + "KB");
  if (process.argv.includes("--full")) {   // a complete page for ordinary web hosting (GitHub Pages)
    const full = out.replace(/\.html$/, ".full.html");
    // the icon links belong in <head>; the head was stripped above, so put them back there (in <body> some browsers show a plain globe)
    // so are the "add to Home Screen as an app" tags: phones read them only from <head>
    const iconTags = h.match(/<link rel="(?:icon|apple-touch-icon)"[^>]*>\s*|<meta name="(?:apple-mobile-web-app-[a-z-]+|mobile-web-app-capable|theme-color)"[^>]*>\s*/g) || [];
    const bodyHtml = iconTags.reduce((s, t) => s.replace(t, ""), h);
    const page = '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="' + viewport + '">' + iconTags.map((t) => t.trim()).join("") + '</head><body>\n' + bodyHtml + "\n</body></html>\n";
    fs.writeFileSync(full, page);
    console.log("wrote", full);
    // a static host (the Render preview) serves share/ as it is: there share/sandbox.html must be the complete page too, or iPhone Safari,
    // with no viewport tag and no doctype, lays the page out 980 px wide and shrinks it. The body-only copy stays as NAME.body.html
    fs.renameSync(out, out.replace(/\.html$/, ".body.html"));
    fs.writeFileSync(out, page);
    console.log("wrote", out, "(complete page; body only in", out.replace(/\.html$/, ".body.html") + ")");
  }
}

build("sandbox/index.html", "share/sandbox.html", "UAply Sandbox", [
  ["on={glide:true,learn:true,easy:true,axis:true,nav:true,profile:true,live:true,kit:true,submit:true,", "on={glide:true,learn:true,easy:true,axis:true,nav:true,profile:true,"],
  ["Experiment freely. Reads a copy of index.html (prod); prod is never changed.", "Experiment freely. Hosted copy: example jobs only, and your swipes stay in your own browser."],
  ["window.UAplyOpts={", "window.UAplyOpts={preview:true,"],     // no server behind the hosted copy
], ["employers", "learn"]);   // Hiring mode and Learns from your swipes (sandbox/index.html lists both itself today: each is embedded once)
build("dev/index.html", "share/dev.html", "UAply", [
  ['var PROMOTED=["glide","nav","profile","live","kit","submit",', 'var PROMOTED=["glide","nav","profile",'],
  ["window.UAplyOpts={", "window.UAplyOpts={preview:true,"],     // no server behind the hosted copy
  // the hosted copy has no server, so it must say so instead of posing as the real app
  ['<div class="bar" id="devbar" hidden><span class="badge">DEV</span><span id="what">Release candidate</span></div>',
   '<div class="bar" id="devbar"><span class="badge">PREVIEW</span><span id="what">Static preview: example jobs only. Accounts and real jobs run on the UAply server.</span></div>'],
  ['document.getElementById("what").textContent="Release candidate: "+PROMOTED.map(function(k){return UAplyEnv.FEATURES[k].name}).join(", ");', ''],
], ["learn"]);   // Learns from your swipes is in the release build too (dev/index.html lists it itself today)
