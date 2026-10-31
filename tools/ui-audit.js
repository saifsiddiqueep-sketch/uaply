// Launch audit: at iPhone width, visit every section, click every visible button once, and report script errors,
// horizontal overflow, tiny tap targets and buttons that do nothing.
//   W=390 H=844 PORT=8769 node tools/cdp.js tools/ui-audit.js
const PORT = process.env.PORT || "8766";
module.exports = async ({ ev, sleep, nav, logs, shot }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const findings = [];
  const note = (kind, where, detail) => { findings.push([kind, where, detail]); console.log("  ! " + kind + " | " + where + (detail ? " | " + detail : "")); };
  const text = (expr) => ev(expr);

  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(2500);
  console.log("viewport:", await ev("innerWidth + 'x' + innerHeight"));

  const closeOverlays = () => ev("(()=>{const d=" + F + ";for(const id of ['kcNo','uaChatX','tipsClose']){const e=d.getElementById(id);if(e&&e.offsetParent)e.click()}"
    + "for(const b of d.querySelectorAll('button')){if(b.offsetParent&&/^(cancel|close|got it|no thanks|keep my account|not now)/i.test(b.innerText.trim()))b.click()}return true})()");

  const overflow = async (where) => {
    const o = JSON.parse(await ev("JSON.stringify({top:document.documentElement.scrollWidth-innerWidth,inner:(" + F + ").documentElement.scrollWidth-(" + F + ").documentElement.clientWidth})"));
    if (o.top > 2 || o.inner > 2) note("OVERFLOW", where, "page is " + Math.max(o.top, o.inner) + "px wider than the screen");
  };
  const tiny = async (where) => {
    const t = JSON.parse(await ev("JSON.stringify([...(" + F + ").querySelectorAll('button,a[href],input,select')].filter(e=>e.offsetParent).map(e=>{const r=e.getBoundingClientRect();return [e.innerText?e.innerText.trim().split(String.fromCharCode(10))[0].slice(0,20):(e.id||e.tagName),Math.round(r.width),Math.round(r.height)]}).filter(x=>x[1]<30||x[2]<30).slice(0,6))"));
    for (const x of t) note("SMALL TAP TARGET", where, '"' + x[0] + '" is ' + x[1] + "x" + x[2] + "px (Apple recommends 44)");
  };

  const sections = [
    ["Services", "nb-svc", ["Full-time", "Part-time", "Internships", "Coop"]],
    ["Job Tracker", "nb-dash", ["Needs you", "Sent", "Heard back", "Jobs you passed on"]],
    ["Profile", "nb-prof", ["Profile setup", "Filters", "Account", "Plan", "Data"]],
  ];
  const DESTRUCTIVE = /delete|wipe|reset my|clear|sign out|log out|remove|cancel plan|go back to free|restore/i;
  let clicked = 0, dead = 0;
  for (const [sname, navId, subs] of sections) {
    for (const sub of subs) {
      const where = sname + " > " + sub;
      await closeOverlays();
      await ev(F + ".getElementById('" + navId + "').click()"); await sleep(350);
      const ok = await ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a,[role=tab]')].find(b=>b.offsetParent&&b.innerText.split(/\\s+/).join(' ').trim().startsWith(" + JSON.stringify(sub) + "));if(!e)return false;e.click();return true})()");
      if (!ok && process.env.REL === "1" && sub === "Plan") { console.log("  Profile > Plan: not in the release build (as intended)"); await ev(F + ".getElementById('" + navId + "').click()"); await sleep(200); continue; }
      if (!ok) { note("MISSING", where, "sub-menu item not found"); continue; }
      await sleep(500);
      await overflow(where); await tiny(where);
      const count = await ev("[...(" + F + ").querySelectorAll('main button,section button,.pane button,#app button,body button')].filter(b=>b.offsetParent).length");
      const labels = JSON.parse(await ev("JSON.stringify([...(" + F + ").querySelectorAll('button')].filter(b=>b.offsetParent&&!b.closest('#nav,.bottomnav,nav')).map((b,i)=>[i,(b.innerText||b.getAttribute('aria-label')||b.id||'?').split(String.fromCharCode(10))[0].trim().slice(0,28)]))"));
      for (const [i, label] of labels) {
        if (DESTRUCTIVE.test(label) || /^(apply|pass|undo)/i.test(label)) continue;
        const before = logs.length;
        const sig0 = await ev("(" + F + ").body.innerText.length + '|' + (" + F + ").body.innerHTML.length");
        const r = await ev("(()=>{const b=[...(" + F + ").querySelectorAll('button')].filter(b=>b.offsetParent&&!b.closest('#nav,.bottomnav,nav'))[" + i + "];if(!b||b.disabled)return 'gone';b.click();return 'ok'})()");
        await sleep(180);
        clicked++;
        if (logs.length > before) note("SCRIPT ERROR", where + " > button \"" + label + "\"", logs.slice(before).join(" / ").slice(0, 160));
        await closeOverlays();
        if (r !== "ok") continue;
        // a click that changes nothing at all (no text, no markup, no dialog) is a dead button, unless it is a toggle chip
        const sig1 = await ev("(" + F + ").body.innerText.length + '|' + (" + F + ").body.innerHTML.length");
        if (sig0 === sig1 && !/^(all|remote|hybrid|on-site)$/i.test(label)) { dead++; note("NO VISIBLE EFFECT", where + " > button \"" + label + "\"", ""); }
        // return to the same screen if the click navigated away
        await ev(F + ".getElementById('" + navId + "').click()"); await sleep(120);
        await ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a,[role=tab]')].find(b=>b.offsetParent&&b.innerText.split(/\\s+/).join(' ').trim().startsWith(" + JSON.stringify(sub) + "));if(e)e.click()})()"); await sleep(150);
      }
      console.log("  " + where + ": " + labels.length + " buttons tried");
    }
  }
  await shot(require("path").join(require("os").tmpdir(), "audit-end.png"));
  console.log("\nbuttons clicked: " + clicked + ", with no visible effect: " + dead + ", findings: " + findings.length);
  console.log("script errors seen anywhere:", logs.length);
};
