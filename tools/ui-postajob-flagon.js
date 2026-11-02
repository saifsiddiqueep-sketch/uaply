// Post a job with the POST_A_JOB flag on (card 217): the four flag-on bugs in shared/uaply-employers.js.
// The flag is off by default; ?postajob=1 on the page (or its same-origin parent) turns it on, for local preview only.
//   W=390 H=844 PORT=8768 node tools/cdp.js tools/ui-postajob-flagon.js     (sandbox served WITHOUT --api, so hiring runs in local mode)
// No real job site is contacted: the app's fetch is replaced by a stand-in that counts calls and answers when told to.
// Checks:
//   0. flag off (no ?postajob=1): the old import box shows, no one-box "Post a job" button;
//   1. flag on: no "already use an ATS?" link to /employers/connect (it needs a signed invite that does not exist yet);
//   2. a pasted link without https:// and without a path but with a query (acme.com?gh_jid=N) is read as a link, not as job text;
//      a bare domain (acme.com) is a link too; one word without a dot and text with spaces are job text;
//   3. while a link is being read both import buttons are disabled and a fast double click sends one request; they come back after;
//   4. the flag reads the page's own address first and a parent that throws (cross-origin) leaves it as it was, never an error.
const fs = require("fs"), path = require("path");
const PORT = process.env.PORT || "8768";
const BASE = "http://127.0.0.1:" + PORT;
const KEY = "hireswipe.sandbox.v1.hiring";
module.exports = async ({ ev, sleep, nav, shot }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { ok = ok === true; n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };

  // 4 first: the two flag lines, taken from the file itself so the check follows the code
  const src = fs.readFileSync(path.join(__dirname, "..", "shared", "uaply-employers.js"), "utf8").split(/\r?\n/);
  const at = src.findIndex((l) => /var POST_A_JOB=false/.test(l));
  const flag = new Function("w", src.slice(at, at + 2).join("\n") + "\nreturn POST_A_JOB;");
  const throwing = { get location() { throw new Error("cross-origin"); } };
  const win = (own, parent) => { const w = { location: { search: own } }; w.parent = parent === "self" ? w : parent; return w; };
  const run = (w) => { try { return flag(w); } catch (e) { return "threw " + e.message; } };
  check("4 own ?postajob=1 with a cross-origin parent turns the flag on", run(win("?postajob=1", throwing)) === true);
  check("4 no flag anywhere and a cross-origin parent: off, no error", run(win("", throwing)) === false);
  check("4 same-origin parent with ?postajob=1 still turns it on", run(win("", { location: { search: "?a=1&postajob=1" } })) === true);
  check("4 a top page without the flag: off", run(win("?x=1", "self")) === false);
  check("4 ?postajob=10 does not count", run(win("?postajob=10", "self")) === false);

  // a local company in hiring mode, so "+ Post a job" opens the import step straight away
  await nav(BASE + "/");
  await ev("localStorage.setItem('" + KEY + ".local',JSON.stringify({company:{name:'Acme Test Co',industry:'Software',size:'11-50',country:'US',website:'https://acme.example',consent:true},jobs:[],pipe:{},next:390001}));localStorage.setItem('" + KEY + ".mode','\"hire\"');true");
  const open = async (q) => {
    await nav(BASE + "/" + q);
    for (let i = 0; i < 40 && !(await ev("(()=>{try{return !!(" + F + ").querySelector('[data-act=new]')}catch(e){return false}})()")); i++) await sleep(250);
    await ev("(" + F + ").querySelector('[data-act=new]').click()");
    await sleep(400);
  };

  await open("");
  check("0 flag off: the old import box shows", await ev("!!(" + F + ").querySelector('#impUrl') && !(" + F + ").querySelector('[data-act=impAuto]')"));

  await open("?postajob=1");
  check("flag on: the one-box import shows", await ev("!!(" + F + ").querySelector('[data-act=impAuto]')"));
  check("1 no link to /employers/connect", await ev("!!(" + F + ").getElementById('impBox') && !(" + F + ").querySelector('a[href*=\"/employers/connect\"]')"));
  check("1 no 'already use an ATS' text", await ev("!!(" + F + ").getElementById('impBox') && !/already use an ATS/i.test((" + F + ").getElementById('impBox').parentNode.textContent)"));
  if (process.env.SHOT) await shot(process.env.SHOT);

  // the stand-in fetch: counts calls, holds each one until release() answers 404 (so the app tries its next guess, then gives up)
  await ev("(()=>{const w=" + FW + ";w.__f={n:0,urls:[],hold:true,wait:[]};w.fetch=function(u){w.__f.n++;w.__f.urls.push(String(u));if(!w.__f.hold)return Promise.resolve({ok:false,status:404});return new Promise(function(r){w.__f.wait.push(r)})};return true})()");
  const paste = (t) => ev("(()=>{const d=" + F + ",x=d.getElementById('impText');x.value=" + JSON.stringify(t) + ";x.dispatchEvent(new Event('input',{bubbles:true}));return true})()");
  const msg = () => ev("((" + F + ").getElementById('impMsg')||{}).textContent||''");
  const btn = (a) => "(" + F + ").querySelector('[data-act=" + a + "]')";

  await paste("acme.com?gh_jid=4012345");
  await ev("(()=>{const b=" + btn("impAuto") + ";b.click();b.click();b.dispatchEvent(new MouseEvent('click',{bubbles:true}));return true})()");
  await sleep(200);
  const f1 = await ev("JSON.stringify(" + FW + ".__f)");
  const st = JSON.parse(f1);
  check("2 acme.com?gh_jid=N is read as a link", st.n >= 1 && /greenhouse\.io\/.*4012345/.test(st.urls[0] || ""), st.urls[0]);
  check("2 it is not taken for job text", /Reading your job post/.test(await msg()), (await msg()).slice(0, 60));
  check("3 three fast clicks send one request", st.n === 1, "fetch calls=" + st.n);
  check("3 the Post a job button is disabled while reading", await ev(btn("impAuto") + ".disabled===true"));
  await ev("(()=>{const w=" + FW + ";w.__f.hold=false;w.__f.wait.splice(0).forEach(function(r){r({ok:false,status:404})});return true})()");
  await sleep(600);
  check("3 the button comes back after the answer", await ev(btn("impAuto") + ".disabled===false"));
  check("3 the local-mode message says to paste the text", /can't open that website/.test(await msg()), (await msg()).slice(0, 80));

  // the other inputs: a bare domain is a link; a word without a dot and real text are job text
  const reset = () => ev("(()=>{const w=" + FW + ";w.__f.n=0;w.__f.urls=[];return true})()");
  const clear = () => ev("(()=>{const m=(" + F + ").getElementById('impMsg');if(m)m.textContent='';return true})()");
  await paste("acme.com"); await reset(); await clear();
  await ev(btn("impAuto") + ".click()"); await sleep(400);
  check("2 a bare domain (acme.com) is a link", /can't open that website/.test(await msg()), (await msg()).slice(0, 80));
  await paste("jobs@acme.com"); await clear(); await ev(btn("impAuto") + ".click()"); await sleep(300);
  check("2 an email address is job text, not a link", /Paste the whole job post/.test(await msg()));
  await paste("notalink"); await clear(); await ev(btn("impAuto") + ".click()"); await sleep(300);
  check("2 one word without a dot is job text", /Paste the whole job post/.test(await msg()));
  await paste("Software Engineer at acme.com, remote, $120k"); await clear(); await ev(btn("impAuto") + ".click()"); await sleep(300);
  check("2 text with spaces is job text", /Paste the whole job post/.test(await msg()));

  console.log(n - bad + " / " + n);
  if (bad) process.exitCode = 1;
};
