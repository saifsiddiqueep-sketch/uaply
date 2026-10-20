// Brave-Shields-like request blocking for the browser tests: reads ad-block filter TEXT lists (EasyList, EasyPrivacy, uBlock filters,
// brave/adblock-lists ...; plain .txt files in one folder) and answers "would a rule block this URL?" the way uBlock/ABP rules match:
// ||host^, |, ^, *, /regex/, $third-party, $domain=, resource types, @@ exceptions. Options it cannot judge (ipaddress=, csp, redirect...)
// make the rule be skipped. Used by tools/ui-live.js --shields and tools/live-check.py --shields (through `node tools/shields.js`).
//   node tools/shields.js LISTDIR URL TYPE [PAGEURL] [aggressive]   ->  prints BLOCK <list>: <rule>  or  ALLOW
//   node tools/shields.js LISTDIR - x PAGEURL < list.json            ->  one JSON line per [url, type], both modes
const fs = require("fs"), path = require("path");
const TYPES = { script: "script", stylesheet: "stylesheet", image: "image", font: "font", xmlhttprequest: "xmlhttprequest", xhr: "xmlhttprequest", document: "document", doc: "document", subdocument: "subdocument", frame: "subdocument", other: "other", ping: "ping", media: "media", websocket: "websocket", css: "stylesheet", object: "object", fetch: "xmlhttprequest" };
function esc(s) { return s.replace(/[.+?${}()|[\]\\]/g, "\\$&"); }
function compile(pat) {
  if (pat.length > 2 && pat[0] === "/" && pat[pat.length - 1] === "/") { try { return new RegExp(pat.slice(1, -1), "i"); } catch (e) { return null; } }
  let re = "", s = pat;
  if (s.startsWith("||")) { re = "^[a-z-]+://([^/]*\\.)?"; s = s.slice(2); }
  else if (s.startsWith("|")) { re = "^"; s = s.slice(1); }
  let end = "";
  if (s.endsWith("|")) { end = "$"; s = s.slice(0, -1); }
  for (const c of s) re += c === "*" ? ".*" : c === "^" ? "(?:[^\\w.%-]|$)" : esc(c);
  try { return new RegExp(re + end, "i"); } catch (e) { return null; }
}
function load(dir) {
 const rules = [];
 for (const f of fs.readdirSync(dir).filter((n) => /\.txt$/.test(n))) {
  for (let line of fs.readFileSync(path.join(dir, f), "utf8").split(/\r?\n/)) {
    line = line.trim();
    if (!line || line[0] === "!" || line[0] === "[" || line.includes("##") || line.includes("#@#") || line.includes("#?#") || line.includes("#$#") || line.includes("#%#")) continue;
    let exc = false; if (line.startsWith("@@")) { exc = true; line = line.slice(2); }
    let opts = "", i = line.lastIndexOf("$");
    if (line[0] === "/") { const k = line.lastIndexOf("/$"); i = k > 0 ? k + 1 : (line.endsWith("/") ? -1 : i); }
    if (i > 0) { opts = line.slice(i + 1); line = line.slice(0, i); }
    if (!line) line = "*";
    const r = { f, raw: (exc ? "@@" : "") + line + (opts ? "$" + opts : ""), exc, re: compile(line), tp: null, types: null, ntypes: null, dom: null, ndom: null, skip: false };
    if (!r.re) continue;
    for (const o of opts.split(",").filter(Boolean)) {
      const [k, v] = o.split("=");
      if (["ipaddress", "to", "method", "denyallow", "strict1p", "all"].includes(k)) r.skip = true;
      else if (k === "third-party" || k === "3p" || k === "strict3p") r.tp = true;
      else if (k === "~third-party" || k === "first-party" || k === "1p") r.tp = false;
      else if (k === "domain" || k === "from") { for (const d of v.split("|")) { if (d[0] === "~") (r.ndom = r.ndom || []).push(d.slice(1)); else (r.dom = r.dom || []).push(d); } }
      else if (TYPES[k]) (r.types = r.types || []).push(TYPES[k]);
      else if (k[0] === "~" && TYPES[k.slice(1)]) (r.ntypes = r.ntypes || []).push(TYPES[k.slice(1)]);
      else if (["popup", "csp", "removeparam", "redirect-rule", "header", "permissions", "urltransform", "replace", "elemhide", "generichide", "ehide", "ghide", "specifichide", "shide", "genericblock", "cname", "badfilter"].includes(k)) r.skip = true;
    }
    if (r.skip || (line === "*" && !r.dom)) continue;
    rules.push(r);
  }
 }
 return rules;
}
const onDom = (list, h) => list.some(d => h === d || h.endsWith("." + d));
function applies(r, url, type, thirdParty, host) {
  if (r.tp !== null && r.tp !== thirdParty) return false;
  if (r.types && !r.types.includes(type)) return false;
  if (r.ntypes && r.ntypes.includes(type)) return false;
  if (r.dom && !onDom(r.dom, host)) return false;
  if (r.ndom && onDom(r.ndom, host)) return false;
  return r.re.test(url);
}
function create(dir) {
  const rules = load(dir);
  return {
    size: rules.length,
    // the first blocking rule for url (type: script, xmlhttprequest, image, font, stylesheet, document, subdocument), or null.
    // standard (Brave's default): only third-party requests are blocked; aggressive: first-party too
    match(url, type, pageUrl, aggressive) {
      const host = new URL(pageUrl || url).hostname, uh = new URL(url).hostname;
      const site = (h) => h.split(".").slice(-2).join(".");
      const tp = site(uh) !== site(host);
      if (!tp && !aggressive) return null;
      const hit = rules.find((r) => !r.exc && applies(r, url, type, tp, host));
      if (!hit || rules.some((r) => r.exc && applies(r, url, type, tp, host))) return null;
      return hit.f + ": " + hit.raw;
    },
  };
}
const CDP_TYPES = { Script: "script", XHR: "xmlhttprequest", Fetch: "xmlhttprequest", Image: "image", Font: "font", Stylesheet: "stylesheet", Document: "document", Media: "media", WebSocket: "websocket", Ping: "ping", Other: "other" };
module.exports = { create, CDP_TYPES };
if (require.main === module) {
  const [dir, url, type, page, mode] = process.argv.slice(2);
  if (url === "-") {        // batch: stdin is a JSON list of [url, type]; prints one JSON line {url, type, standard, aggressive} each
    const eng = create(dir), list = JSON.parse(fs.readFileSync(0, "utf8"));
    for (const [u, ty] of list) console.log(JSON.stringify({ url: u, type: ty, standard: eng.match(u, ty, page || u, false), aggressive: eng.match(u, ty, page || u, true) }));
    process.exit(0);
  }
  const r = create(dir).match(url, type || "xmlhttprequest", page || url, mode === "aggressive");
  console.log(r ? "BLOCK " + r : "ALLOW");
}
