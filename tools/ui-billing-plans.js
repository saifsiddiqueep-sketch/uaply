// Plan & billing with yearly plans (October 25, 2026), on dev (PORT) with a stand-in Stripe (MOCK_STRIPE port) and test keys:
// the Monthly / Yearly toggle, "2 months free", the yearly prices, the 7-day refund line under the buttons, and Choose on Yearly opening
// Checkout with the yearly price.
//   W=390 H=844 PORT=<dev> MOCK_STRIPE=<port> node tools/cdp.js tools/ui-billing-plans.js
const PORT = process.env.PORT || "18767", MOCK = process.env.MOCK_STRIPE;
const gateSignup = require("./gate-signup.js");
module.exports = async ({ ev, sleep, nav, logs }) => {
  const F = "document.querySelector('iframe').contentDocument";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (ok || !extra ? "" : "  | " + String(extra).slice(0, 300))); };
  const base = "http://127.0.0.1:" + PORT;
  await gateSignup({ ev, sleep, nav }, base, "billing");
  await nav(base + "/?app=1"); await sleep(3500);
  const open = async () => {
    await ev("(()=>{const d=" + F + ";d.getElementById('nb-prof').click();return 1})()"); await sleep(400);
    await ev("(()=>{const d=" + F + ";const it=d.querySelector('.nwrap[data-k=prof] .nitem[data-v=plan]');if(it)it.click();return 1})()"); await sleep(1500);
  };
  await open();
  const txt = () => ev("(()=>{const s=" + F + ".getElementById('acctSec');return s?s.innerText.replace(/\\s+/g,' '):''})()");
  let t = await txt();
  check("the plan screen has a Monthly / Yearly toggle, Monthly first", await ev("(()=>{const g=" + F + ".getElementById('bInt');return !!g&&g.querySelector('[data-bint=month]').getAttribute('aria-pressed')==='true'})()"), t.slice(0, 200));
  check("...monthly prices: Plus $9.99/month, Pro $19.99/month", /\$9\.99\s*\/month/.test(t) && /\$19\.99\s*\/month/.test(t), t.slice(0, 300));
  check("the 7-day refund of the first payment is said under the buttons", /first payment can be refunded in full within 7 days: email uaplytechnologies@gmail\.com/.test(t), "");
  await ev("(()=>{" + F + ".querySelector('#bInt [data-bint=year]').click();return 1})()"); await sleep(500);
  t = await txt();
  check("Yearly: Plus $99.90/year and Pro $199.90/year, each with 2 months free", /\$99\.90\s*\/year/.test(t) && /\$199\.90\s*\/year/.test(t) && (t.match(/2 months free/g) || []).length >= 3, t.slice(0, 400));
  const n0 = MOCK ? (await (await fetch("http://127.0.0.1:" + MOCK + "/__sessions")).json()).length : 0;
  await ev("(()=>{const b=" + F + ".querySelector('#acctSec [data-bill=plus]');if(b)b.click();return !!b})()"); await sleep(2500);
  if (MOCK) {
    const ss = await (await fetch("http://127.0.0.1:" + MOCK + "/__sessions")).json();
    const s = ss[ss.length - 1] || {};
    check("Choose Plus on Yearly opens Stripe Checkout with the yearly price", ss.length === n0 + 1 && s["metadata[interval]"] === "year" && /^price_/.test(s["line_items[0][price]"] || "") && s["line_items[0][price]"] !== "price_plus1", JSON.stringify(s).slice(0, 300));
  }
  check("no script errors", logs.filter((l) => l.startsWith("EXC")).length === 0, logs.join(" | "));
  console.log(bad ? bad + " problem(s)" : "All good");
  if (bad) process.exitCode = 1;
};
module.exports.limitMs = 120000;
