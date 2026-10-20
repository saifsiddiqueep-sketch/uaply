// A free-only launch in a real browser: with UAPLY_PLANS_HIDDEN=1 on the server, Profile, Plan & billing shows the Free plan and
// "Plus and Pro are coming soon", and no Choose Plus / Choose Pro button. With it off (SHOWN_PORT), the same screen offers Choose Plus,
// so the check above is not passing for some other reason.
//   PORT=<server with UAPLY_PLANS_HIDDEN=1> SHOWN_PORT=<the same server without it> node tools/cdp.js tools/ui-plans-hidden.js
const PORT = process.env.PORT || "8767";
const SHOWN = process.env.SHOWN_PORT || "";
module.exports = async ({ ev, sleep, nav, send }) => {
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + name + (ok || !extra ? "" : "  -> " + extra)); return ok; };
  const F = "document.querySelector('iframe').contentDocument";
  const q = (js) => ev("(()=>{try{const d=" + F + ",w=d.defaultView;" + js + "}catch(e){return 'ERR '+e.message}})()");
  const waitFor = async (js, ms) => { const end = Date.now() + (ms || 8000); let v; while (Date.now() < end) { v = await q(js); if (v && !String(v).startsWith("ERR")) return v; await sleep(250); } return v; };
  const click = (finder) => q("const e=(" + finder + ");if(!e)return false;e.click();return true");
  const plan = async (port) => {
    const base = "http://127.0.0.1:" + port;
    await nav(base + "/healthz");
    await send("Storage.clearDataForOrigin", { origin: base, storageTypes: "all" });
    await nav(base + "/");
    await waitFor("return d.getElementById('nb-prof')", 20000);
    await click("d.getElementById('kcYes')");
    await click("d.getElementById('tipsClose')");
    await click("d.getElementById('nb-prof')"); await sleep(300);
    await click("[...d.querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='plan')");
    await waitFor("return /Current plan/.test(d.getElementById('acctSec').innerText)", 8000);
    await sleep(500);
    return JSON.parse(await q("const s=d.getElementById('acctSec');return JSON.stringify({text:s.innerText,choose:[...s.querySelectorAll('button')].filter(b=>/^Choose /.test(b.innerText.trim())).map(b=>b.innerText.trim()),buy:s.querySelectorAll('[data-bill=plus],[data-bill=pro]').length,cards:[...s.querySelectorAll('.plans .plan b')].map(b=>b.innerText.trim()),soon:!!d.getElementById('plansSoon')})"));
  };
  const h = await plan(PORT);
  check("hidden: no Choose Plus or Choose Pro button, and nothing that starts a checkout", h.choose.length === 0 && h.buy === 0, JSON.stringify(h.choose) + " " + h.buy);
  check("hidden: only the Free plan is shown", JSON.stringify(h.cards) === '["Free"]', JSON.stringify(h.cards));
  check("hidden: it says Plus and Pro are coming soon", h.soon && /Plus and Pro are coming soon/.test(h.text), h.text.slice(0, 300));
  if (SHOWN) {
    const s = await plan(SHOWN);
    check("shown (the default): the same screen offers Choose Plus and Choose Pro", s.choose.includes("Choose Plus") && s.choose.includes("Choose Pro") && !s.soon, JSON.stringify(s.choose));
  }
  console.log("\n" + pass + " / " + (pass + fail));
};
