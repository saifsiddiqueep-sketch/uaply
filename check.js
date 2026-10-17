/* One command to check the whole project for mistakes:  node check.js
   Runs the same checks on your computer and on every pull request (see .github/workflows/check.yml).
   Exits with an error if anything is wrong. Needs Node and Python 3. */
const fs = require("fs");
const { spawnSync } = require("child_process");
let failed = 0;
const ok = (m) => console.log("  ok    " + m);
const bad = (m) => { failed++; console.log("  FAIL  " + m); };

function listJs() { return fs.readdirSync("shared").filter((f) => f.endsWith(".js")).map((f) => "shared/" + f).concat(["share/build-share.js", "check.js"]); }

console.log("JavaScript files");
listJs().forEach((f) => {
  const r = spawnSync(process.execPath, ["--check", f], { encoding: "utf8" });
  r.status === 0 ? ok(f) : bad(f + "\n" + r.stderr);
});

console.log("Scripts inside the pages");
["prod/index.html", "sandbox/index.html", "dev/index.html"].forEach((f) => {
  const s = fs.readFileSync(f, "utf8");
  const re = /<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g;
  let m, n = 0, err = null;
  while ((m = re.exec(s))) { n++; try { new Function(m[1]); } catch (e) { err = e.message; } }
  err ? bad(f + ": " + err) : ok(f + " (" + n + " inline script" + (n === 1 ? "" : "s") + ")");
});

console.log("Python files");
/* On Windows "python" is often only a Microsoft Store shortcut; fall back to the "py" launcher when it does not run. */
const py = process.platform !== "win32" ? "python3"
  : (spawnSync("python", ["--version"], { encoding: "utf8" }).status === 0 ? "python" : "py");
fs.readdirSync(".").filter((f) => f.endsWith(".py")).forEach((f) => {     /* every server module, not a hand-kept list (it had missed 8 of 13) */
  const r = spawnSync(py, ["-m", "py_compile", f], { encoding: "utf8" });
  r.status === 0 ? ok(f) : bad(f + "\n" + (r.stderr || r.error));
});

console.log("JSON files");
fs.readdirSync(".").filter((f) => f.endsWith(".json") && !["uaply-config.json", "uaply-partners.json"].includes(f)).concat(   /* never the owner's secret files: an error message could quote them */[".claude/launch.json", "help/articles.json", "mobile/capacitor.config.json"]).filter((f) => fs.existsSync(f)).forEach((f) => {
  try { JSON.parse(fs.readFileSync(f, "utf8")); ok(f); } catch (e) { bad(f + ": " + e.message); }
});

console.log("Legal pages");
try {
  ["index", "terms", "privacy", "ai-and-employment", "copyright"].forEach((n) => {
    const s = fs.readFileSync("legal/" + n + ".html", "utf8");
    const open = (s.match(/<mark>/g) || []).length, close = (s.match(/<\/mark>/g) || []).length;
    open === close ? ok("legal/" + n + ".html (" + open + " blank" + (open === 1 ? "" : "s") + " to fill in before publishing)") : bad("legal/" + n + ".html has an unclosed <mark>");
  });
  if (!fs.existsSync("legal/style.css")) bad("legal/style.css is missing");
} catch (e) { bad("legal pages: " + e.message); }

console.log("Every experiment still applies to the production page");
try {
  global.window = {}; global.localStorage = { getItem() { return null; } };
  ["shared/uaply-nav.js", "shared/uaply-live.js", "shared/uaply-profile.js", "shared/uaply-learn.js"].forEach((f) => new Function("window", "localStorage", fs.readFileSync(f, "utf8"))(window, localStorage));
  let src = fs.readFileSync("prod/index.html", "utf8");
  src = window.UAplyNav.patch(src); src = window.UAplyProfile.patch(src); src = window.UAplyLive.patch(src); src = window.UAplyLive.kit.patch(src); src = window.UAplyLearn.patch(src);
  new Function(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/.exec(src)[1]);
  ok("patched app assembles and parses");
} catch (e) { bad("patching the production page failed: " + e.message); }

console.log("Release build (dev)");
{
  const dev = fs.readFileSync("dev/index.html", "utf8");
  /release:\s*true/.test(dev) ? ok("dev/index.html is flagged as the release build") : bad("dev/index.html lost release:true (the developer bar, simulated sign-in and paid plans would show to users)");
  /<div class="bar" id="devbar" hidden>/.test(dev) ? ok("the developer bar is hidden") : bad("the DEV bar is no longer hidden in dev/index.html");
  /<title>UAply<\/title>/.test(dev) ? ok("the tab title is UAply") : bad("dev/index.html title should be exactly UAply");
  const art = JSON.parse(fs.readFileSync("help/articles.json", "utf8")).articles;
  const plans = art.find((a) => a.id === "plans");
  /* dev shows Plan & billing (backed by Stripe), so the article may stay, but the release wording must never talk about test payments */
  const relPlans = plans && plans.release ? (plans.release.hide ? "" : plans.release.body || "") : null;
  relPlans === "" || (relPlans && !/\btest\b/i.test(relPlans)) ? ok("the assistant's plans article is hidden or has its own release wording (no test payments)")
    : bad("help/articles.json: the plans article needs release.hide or a release.body without test-payment wording");
  /* nothing the release assistant says may call the app a test version or send people to a test inbox */
  const relText = art.filter((a) => !(a.release && a.release.hide)).map((a) => a.id + ": " + ((a.release && a.release.body) || a.body));
  const testy = relText.filter((t) => /test version|test inbox|sandbox|simulated|isn't available yet|claude|anthropic/i.test(t));
  testy.length ? bad("help/articles.json: release answers with test or developer wording: " + testy.map((t) => t.split(":")[0]).join(", ")) : ok("no release answer mentions a test version, a test inbox or the coding tools");
}

console.log("Wiring between files");
try {
  /* a fresh copy of every shared script, so this does not depend on the section above */
  const W = {}, fakeDoc = { getElementById() { return null; } };
  ["nav", "live", "profile", "chat", "envs", "employers", "learn", "resume"].forEach((f) => new Function("window", "localStorage", "document", fs.readFileSync("shared/uaply-" + f + ".js", "utf8"))(W, localStorage, fakeDoc));
  const E = W.UAplyEnv, prod = fs.readFileSync("prod/index.html", "utf8");
  const NEEDS = { submit: ["nav", "live", "kit"], profile: ["nav"], employers: ["nav"], resume: ["nav"] };   /* the same rule as run() in uaply-envs.js */
  const build = (keys) => {
    let s = prod, err = "";
    E.ORDER.forEach((k) => { if (keys.includes(k) && E.FEATURES[k].patch) { try { s = E.FEATURES[k].patch(s); } catch (e) { err += k + ": " + e.message + ". "; } } });
    for (const m of s.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g)) { try { new Function(m[1]); } catch (e) { err += "the patched script no longer parses: " + e.message + ". "; } }
    return err;
  };
  /* a patch whose text is no longer in prod/index.html throws, and the app would show "Problem: ..." instead of the feature */
  const alone = E.ORDER.map((k) => [k, build([k].concat(NEEDS[k] || []))]).filter((x) => x[1]);
  alone.length ? bad("these experiments no longer apply on their own: " + alone.map((x) => x[1]).join(" ")) : ok("each of the " + E.ORDER.length + " experiments applies on its own");
  const all = build(E.ORDER);
  all ? bad("with every experiment on: " + all) : ok("every experiment applies together");
  const dev = fs.readFileSync("dev/index.html", "utf8"), P = JSON.parse(/var PROMOTED=(\[[^\]]*\])/.exec(dev)[1]);
  const unknown = P.filter((k) => !E.FEATURES[k]);
  unknown.length ? bad("dev/index.html PROMOTED names features that do not exist: " + unknown.join(", ")) : ok("every feature dev's PROMOTED list names exists (" + P.length + ")");
  /* sandbox-only: Hiring mode, the pretend back end, and the "Save to Applied?" question the sandbox removed */
  const leak = P.filter((k) => ["employers", "backend", "confirm"].includes(k));
  leak.length ? bad("sandbox-only features in the release build: " + leak.join(", ")) : ok("no sandbox-only feature (Hiring mode, Mock back end, Confirm apply) is in the release build");
  /* allowed in dev since October 17: Learns from your swipes (its file must load) and consent before the first swipe. Still sandbox-only:
     Hiring mode's file and the sandbox's controls bar (All on / All off / Clear saved swipes) */
  !P.includes("learn") || dev.includes('<script src="uaply-learn.js"></script>') ? ok("Learns from your swipes is promoted and its file loads in dev") : bad("dev promotes learn but does not load uaply-learn.js");
  !dev.includes("uaply-employers.js") && !/id="(all|none|reset|feats)"/.test(dev) ? ok("dev loads neither Hiring mode nor the sandbox's controls") : bad("dev loads uaply-employers.js or the sandbox controls");
  /consentFirst:\s*true/.test(dev) ? ok("dev asks for the agreement before the first swipe (consentFirst)") : bad("dev/index.html lost consentFirst:true");
  const devErr = build(P.concat(NEEDS.submit));
  devErr ? bad("the release build does not assemble: " + devErr) : ok("the release build (dev's PROMOTED list) assembles and parses");
  /* "Take me there" under an assistant answer: each article's destination must be a real menu item or Profile setup step, reached
     directly (the old names "preferences" and "resume" are only shortcuts and land on the wrong step) */
  const navSrc = fs.readFileSync("shared/uaply-nav.js", "utf8"), items = {};
  for (const m of navSrc.matchAll(/(svc|dash|prof):\{label:"[^"]*",items:\[(.*?)\]\}/g)) items[m[1]] = [...m[2].matchAll(/\["(\w+)"/g)].map((x) => x[1]);
  const steps = [...(/var STEPS=\[([\s\S]*?)\n  \];/.exec(navSrc) || ["", ""])[1].matchAll(/\{k:"(\w+)"/g)].map((x) => x[1]);
  const wrong = [];
  JSON.parse(fs.readFileSync("help/articles.json", "utf8")).articles.forEach((a) => {
    [["", a.go], [" (release)", a.release && a.release.go]].forEach(([which, g]) => {
      if (!g) return;
      const [sec, v] = String(g).split(":");
      if (!items[sec] || !(items[sec].includes(v) || (sec === "prof" && steps.includes(v)))) wrong.push(a.id + which + " -> " + g);
    });
  });
  !items.prof || steps.length !== 5 ? bad("could not read the menus or the Profile setup steps from shared/uaply-nav.js") :
    wrong.length ? bad("help articles whose \"Take me there\" goes nowhere or to the wrong place: " + wrong.join(", ")) : ok("every help article's \"Take me there\" is a real screen or Profile setup step");
  /* getElementById("x") in the shared scripts: x must be made by prod/index.html or by one of the scripts */
  const every = ["prod/index.html", "sandbox/index.html", "dev/index.html"].concat(fs.readdirSync("shared").map((f) => "shared/" + f)).map((f) => fs.readFileSync(f, "utf8")).join("\n");
  const made = new Set([...every.matchAll(/\bid=\\?["']([A-Za-z][\w-]*)|\.id\s*=\s*["']([A-Za-z][\w-]*)["']/g)].map((m) => m[1] || m[2]));
  const prefixes = [...every.matchAll(/\bid=\\?["']([A-Za-z][\w-]*)['"]\s*\+/g)].map((m) => m[1]);
  const missing = new Set();
  fs.readdirSync("shared").forEach((f) => { for (const m of fs.readFileSync("shared/" + f, "utf8").matchAll(/getElementById\(\s*"([^"]+)"\s*\)/g)) if (!made.has(m[1]) && !prefixes.some((p) => m[1].startsWith(p))) missing.add(f + ": " + m[1]); });
  missing.size ? bad("getElementById of ids nothing creates: " + [...missing].join(", ")) : ok("every id the shared scripts look up is created somewhere (" + made.size + " ids)");
} catch (e) { bad("wiring checks could not run: " + e.message); }

console.log("Python lint (pyflakes, when installed)");
{
  /* the same interpreter as above (the Windows "py" launcher when "python" is only a Store shortcut), on the project's own scripts */
  const mine = fs.readdirSync(".").filter((f) => f.endsWith(".py")).concat(fs.existsSync("tools") ? fs.readdirSync("tools").filter((f) => f.endsWith(".py")).map((f) => "tools/" + f) : []);
  const r = spawnSync(py, ["-m", "pyflakes"].concat(mine), { encoding: "utf8" });
  if (/No module named pyflakes/.test((r.stderr || "") + (r.stdout || ""))) console.log("  skip  pyflakes is not installed (pip install pyflakes)");
  else if (r.status === 0) ok("no unused imports, undefined names or other pyflakes findings");
  else bad("pyflakes found problems:\n" + (r.stdout || r.stderr).slice(0, 1500));
}

console.log("Hosted icons");
{
  /* the hosted pages ask for their icons next to themselves; a file that is not copied by the publish workflow is a 404, and the
     browser then shows a plain globe in the tab and in bookmarks */
  const pages = fs.readFileSync(".github/workflows/pages.yml", "utf8");
  ["sandbox", "dev"].forEach((dir) => {
    const html = fs.readFileSync(dir + "/index.html", "utf8");
    const files = [...html.matchAll(/<link rel="(?:icon|apple-touch-icon)"[^>]*href="([^"?]+)/g)].map((m) => m[1]);
    if (!files.length) bad(dir + "/index.html declares no icons");
    files.forEach((f) => {
      if (!fs.existsSync(dir + "/" + f)) bad(dir + "/" + f + " is declared but missing");
      else if (!pages.includes(dir + "/" + f)) bad(dir + "/" + f + " is not copied by .github/workflows/pages.yml, so the hosted page would show a plain globe");
      else ok(dir + "/" + f + " exists and is published");
    });
  });
}

console.log("Hosted copies build");
const b = spawnSync(process.execPath, ["share/build-share.js", "--full"], { encoding: "utf8" });
b.status === 0 ? ok("share/build-share.js --full") : bad("build failed\n" + b.stderr);
for (const f of ["dev", "sandbox", "dev.full", "sandbox.full"]) {
  const html = fs.readFileSync("share/" + f + ".html", "utf8");
  const re = /<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g;
  let m, n = 0, broken = "";
  while ((m = re.exec(html))) { n++; try { new Function(m[1]); } catch (e) { broken += " script " + n + ": " + e.message; } }
  broken ? bad("hosted copy share/" + f + ".html has a script syntax error:" + broken) : ok("share/" + f + ".html: " + n + " inline scripts parse");
}

console.log(failed ? "\n" + failed + " problem(s) found." : "\nAll checks passed.");
process.exit(failed ? 1 : 0);
