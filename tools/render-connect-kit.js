// The one-page employer kit as a PDF: docs/employers/connect-kit.md, the part between <!-- PAGE ... --> and <!-- /PAGE -->, drawn as a page in
// headless Chrome and printed to docs/employers/connect-kit.pdf (US Letter). It fails when the page no longer fits on one sheet.
//   node tools/cdp.js tools/render-connect-kit.js            (OUT=other.pdf to write somewhere else)
const fs = require("fs");
const os = require("os");
const path = require("path");
const ROOT = path.join(__dirname, "..");
const SRC = path.join(ROOT, "docs", "employers", "connect-kit.md");
const OUT = process.env.OUT || path.join(ROOT, "docs", "employers", "connect-kit.pdf");

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const inline = (s) => esc(s).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");

// the small part of Markdown the page uses: one heading, paragraphs, and one table
function html(md) {
  const out = [];
  let para = [], rows = [];
  const flushPara = () => { if (para.length) out.push("<p>" + inline(para.join(" ")) + "</p>"); para = []; };
  const flushTable = () => {
    if (!rows.length) return;
    const cells = (r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
    const head = cells(rows[0]), body = rows.slice(2).map(cells);
    out.push("<table><thead><tr>" + head.map((c) => "<th>" + inline(c) + "</th>").join("") + "</tr></thead><tbody>" +
      body.map((r) => "<tr>" + r.map((c) => "<td>" + inline(c) + "</td>").join("") + "</tr>").join("") + "</tbody></table>");
    rows = [];
  };
  for (const line of md.split(/\r?\n/)) {
    if (/^\|/.test(line)) { flushPara(); rows.push(line); continue; }
    flushTable();
    if (/^# /.test(line)) { flushPara(); out.push("<h1>" + inline(line.slice(2)) + "</h1>"); continue; }
    if (!line.trim()) { flushPara(); continue; }
    para.push(line.trim());
  }
  flushPara(); flushTable();
  return out.join("\n");
}

module.exports = async ({ send, sleep }) => {
  const md = fs.readFileSync(SRC, "utf8");
  const m = /<!-- PAGE[^>]*-->([\s\S]*?)<!-- \/PAGE -->/.exec(md);
  if (!m) { console.log("FAIL docs/employers/connect-kit.md has no PAGE section"); process.exitCode = 1; return; }
  const page = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>UAply: connect your hiring system</title><style>' +
    "@page{size:Letter;margin:0.5in}body{font:10.5px/1.42 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1d1d1f;margin:0}" +
    "h1{font-size:19px;margin:0 0 8px;color:#2A1218}h1::before{content:'UAply';display:block;font-size:11px;letter-spacing:.08em;color:#E11D48;margin-bottom:2px}" +
    "p{margin:0 0 7px}b{color:#2A1218}code{font:9.5px ui-monospace,Consolas,monospace;background:#f3f1ef;padding:0 2px;border-radius:3px}" +
    "table{border-collapse:collapse;width:100%;margin:2px 0 9px;font-size:9.4px}th,td{border:1px solid #ddd6d2;padding:4px 5px;text-align:left;vertical-align:top}" +
    "th{background:#2A1218;color:#fff;font-weight:600}tr:nth-child(even) td{background:#faf8f7}</style></head><body>" + html(m[1]) + "</body></html>";
  const tmp = path.join(os.tmpdir(), "uaply-connect-kit.html");
  fs.writeFileSync(tmp, page);
  await send("Page.navigate", { url: "file:///" + tmp.replace(/\\/g, "/") });
  await sleep(1200);
  const opts = { printBackground: true, preferCSSPageSize: true };
  const two = await send("Page.printToPDF", Object.assign({ pageRanges: "2" }, opts));   // a second page must not exist
  if (!two.error) { console.log("FAIL the kit no longer fits on one page: shorten docs/employers/connect-kit.md's PAGE section"); process.exitCode = 1; return; }
  const r = await send("Page.printToPDF", opts);
  if (!r.result || !r.result.data) { console.log("FAIL Chrome did not print the page: " + JSON.stringify(r.error || {})); process.exitCode = 1; return; }
  fs.writeFileSync(OUT, Buffer.from(r.result.data, "base64"));
  console.log("PASS one page, written to " + path.relative(ROOT, OUT) + " (" + Math.round(fs.statSync(OUT).size / 1024) + " KB)");
};
module.exports.limitMs = 60000;
