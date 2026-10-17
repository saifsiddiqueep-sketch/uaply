/* Builds self-contained, hostable copies of the sandbox and dev pages into share/.
   Run from the project folder:  node share/build-share.js
   The hosted copies have no server, so Real jobs, Apply assistant and Send applications are left out, and UAplyOpts.preview tells the
   pages so: Account, Plan, a swipe right and the help assistant then say "This is a preview ... The real site is uaply.net."
   prod/index.html is only read, never written. */
const fs = require("fs");
const read = (p) => fs.readFileSync(p, "utf8");
const prod = read("prod/index.html");
const nav = read("shared/uaply-nav.js");
const profile = read("shared/uaply-profile.js");
const chat = read("shared/uaply-chat.js");               // the Help button: in a preview it answers that there is no server here
const employers = read("shared/uaply-employers.js");     // Hiring mode: sandbox only (it registers itself after envs)
const learn = read("shared/uaply-learn.js");             // Learns from your swipes: sandbox and dev (envs asks for it only when it is on)
let envs = read("shared/uaply-envs.js");

const NEEDS_SERVER = ["live", "kit", "submit", "resume"];   // Fill from your resume reads the file on the server
envs = envs.replace(/fetch\("prod-index\.html",\{cache:"no-store"\}\)\.then\(function\(r\)\{return r\.text\(\)\}\)/, "Promise.resolve(window.__PROD_SRC)");
envs = envs.replace(/var ORDER=\[([^\]]*)\];/, (m, list) => {
  const kept = list.split(",").map((s) => s.trim()).filter((s) => !NEEDS_SERVER.includes(s.replace(/"/g, "")));
  return "var ORDER=[" + kept.join(",") + "];";
});
if (envs.includes('fetch("prod-index.html"')) throw new Error("envs patch failed");

const safe = (s) => s.replace(/<\/script/gi, "<\\/script");
const inline = "<script>window.__PROD_SRC=" + JSON.stringify(prod).replace(/</g, "\\u003c") + ";</script>\n" +
  "<script>" + safe(nav) + "</script>\n<script>" + safe(profile) + "</script>\n<script>" + safe(chat) + "</script>\n<script>" + safe(envs) + "</script>";

function darkBlocks(html) {
  // add the guarded dark block and the explicit data-theme block so the host theme toggle works
  return html.replace(/@media \(prefers-color-scheme: dark\)\{:root\{([^}]*)\}\}/, (m, vars) =>
    "@media (prefers-color-scheme: dark){:root:not([data-theme=\"light\"]){" + vars + ";color-scheme:dark}}\n:root[data-theme=\"dark\"]{" + vars + ";color-scheme:dark}");
}

function build(src, out, title, edits, extra) {
  let h = read(src);
  const viewport = (h.match(/<meta name="viewport" content="([^"]*)"/i) || [])[1] || "width=device-width,initial-scale=1";
  h = h.replace(/(<script src="uaply-[a-z]+\.js"><\/script>\s*)+/, () => inline + (extra || "") + "\n");
  if (!h.includes("__PROD_SRC")) throw new Error("script tags not found in " + src);
  h = h.replace(/<title>[^<]*<\/title>/, "<title>" + title + "</title>");
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
    fs.writeFileSync(full, '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="' + viewport + '">' + iconTags.map((t) => t.trim()).join("") + '</head><body>\n' + bodyHtml + "\n</body></html>\n");
    console.log("wrote", full);
  }
}

build("sandbox/index.html", "share/sandbox.html", "UAply Sandbox", [
  ["on={glide:true,learn:true,easy:true,axis:true,nav:true,profile:true,live:true,kit:true,submit:true,", "on={glide:true,learn:true,easy:true,axis:true,nav:true,profile:true,"],
  ["Experiment freely. Reads a copy of index.html (prod); prod is never changed.", "Experiment freely. Hosted copy: example jobs only, and your swipes stay in your own browser."],
  ["window.UAplyOpts={", "window.UAplyOpts={preview:true,"],     // no server behind the hosted copy
], "\n<script>" + safe(employers) + "</script>\n<script>" + safe(learn) + "</script>");
build("dev/index.html", "share/dev.html", "UAply", [
  ['var PROMOTED=["glide","nav","profile","live","kit","submit",', 'var PROMOTED=["glide","nav","profile",'],
  ["window.UAplyOpts={", "window.UAplyOpts={preview:true,"],     // no server behind the hosted copy
  // the hosted copy has no server, so it must say so instead of posing as the real app
  ['<div class="bar" id="devbar" hidden><span class="badge">DEV</span><span id="what">Release candidate</span></div>',
   '<div class="bar" id="devbar"><span class="badge">PREVIEW</span><span id="what">Static preview: example jobs only. Accounts and real jobs run on the UAply server.</span></div>'],
  ['document.getElementById("what").textContent="Release candidate: "+PROMOTED.map(function(k){return UAplyEnv.FEATURES[k].name}).join(", ");', ''],
], "\n<script>" + safe(learn) + "</script>");   // Learns from your swipes is in the release build too
