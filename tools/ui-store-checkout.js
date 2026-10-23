// The store rules, in a real browser: inside the iPhone and Android apps Profile, Plan & billing shows what each plan includes with no
// button that opens Stripe (no Choose, Switch, Manage billing or Update card) and says "Plans are available on uaply.net"; the website
// keeps the buttons. "The apps" are the Capacitor builds (Capacitor reports "ios" or "android") and the Google Play app, a Trusted Web
// Activity with no Capacitor that Chrome opens with the referrer android-app://com.uaply.app (or a start address with ?src=twa).
// The billing status is answered here (no Stripe needed), as the server would for a free account with payments on and for a Plus
// subscriber whose last payment failed. Checkout and portal requests are caught, so a button that slipped through would be counted, not
// followed. The weekly-limit reply to a swipe right is answered here too, and the no-server (simulated) sandbox Plan screen is checked
// with every /api/ request failed.
//   PORT=18766 [SHOTS=<folder>] node tools/cdp.js tools/ui-store-checkout.js
const PORT = process.env.PORT || "18766";
const SHOTS = process.env.SHOTS || "";
const NOTE = "Plus and Pro cannot be bought or changed in this app. Plans are available on uaply.net.";
module.exports = async ({ ev, sleep, nav, send, on, shot, logs }) => {
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + name + (ok || !extra ? "" : "  -> " + extra)); return ok; };
  const F = "document.querySelector('iframe').contentDocument";
  const q = (js) => ev("(()=>{try{const d=" + F + ",w=d.defaultView;" + js + "}catch(e){return 'ERR '+e.message}})()");
  const waitFor = async (js, ms) => { const end = Date.now() + (ms || 8000); let v; while (Date.now() < end) { v = await q(js); if (v && !String(v).startsWith("ERR")) return v; await sleep(250); } return v; };
  const click = (finder) => q("const e=(" + finder + ");if(!e)return false;e.click();return true");
  const plans = { free: { name: "Free", price: 0, cap: 50 }, plus: { name: "Plus", price: 9.99, cap: 250 }, pro: { name: "Pro", price: 19.99, cap: 0 } };
  const FREE = { enabled: true, test: true, buttons: true, early: false, hidden: false, signedIn: true, plan: "free", used: 3, cap: 50, renews: 0, canceling: false, status: "", hasCustomer: false, problem: "", plans };
  const PLUS = Object.assign({}, FREE, { plan: "plus", cap: 250, renews: Math.floor(Date.now() / 1000) + 20 * 86400, status: "past_due", hasCustomer: true, problem: "retrying" });
  let status = FREE, stripeHits = 0, noServer = false, applyHits = 0, statusHits = 0;
  const LIMIT = "You've used your 50 applications this week on Free. Choose a bigger plan in Profile, Plan and billing to keep applying.";
  const reply = (p, code, body) => send("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: code, responseHeaders: [{ name: "Content-Type", value: "application/json" }], body: Buffer.from(JSON.stringify(body)).toString("base64") });
  on("Fetch.requestPaused", (p) => {
    const u = p.request.url.split("?")[0];
    if (noServer) return send("Fetch.failRequest", { requestId: p.requestId, errorReason: "ConnectionRefused" });   // the no-server sandbox
    if (/\/api\/billing\/status$/.test(u)) { statusHits++; return reply(p, 200, status); }
    if (/\/api\/billing\/(checkout|portal)$/.test(u)) { stripeHits++; return reply(p, 400, { error: "caught by the test" }); }   // the page tried to open Stripe
    if (/\/api\/apply$/.test(u) && p.request.method === "POST") { applyHits++; return reply(p, 402, { error: LIMIT, code: "limit" }); }   // payments on, weekly limit used up
    return send("Fetch.continueRequest", { requestId: p.requestId });
  });
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/*" }] });
  const base = "http://127.0.0.1:" + PORT;
  await nav(base + "/healthz");
  await send("Storage.clearDataForOrigin", { origin: base, storageTypes: "all" });
  const open = async (platform, st, path) => {
    status = st;
    const asked = statusHits;
    await nav(base + (path || "/"));
    if (platform === "ios" || platform === "android") await ev("window.Capacitor={isNativePlatform:()=>true,getPlatform:()=>'" + platform + "'}");
    await waitFor("return d.getElementById('nb-prof')", 20000);
    await click("d.getElementById('kcYes')");
    await click("d.getElementById('tipsClose')");
    await click("d.getElementById('nb-prof')"); await sleep(300);
    await click("[...d.querySelectorAll('.nitem')].find(b=>b.getAttribute('data-v')==='plan')");
    // Before the server answers, the screen shows a placeholder ("Current plan: Free", "Sign in to ...") with no buttons on any platform,
    // so reading it would prove nothing. With a server, wait until this page's billing status was answered and the screen shows it (both
    // mocked statuses are signed in with a weekly cap, so only the answered screen says "applications used this week").
    if (noServer) await waitFor("return /Current plan/.test(d.getElementById('acctSec').innerText)", 8000);
    else {
      const answered = () => q("return /applications used this week/.test(d.getElementById('acctSec').innerText)");
      const end = Date.now() + 12000;
      while (Date.now() < end && !(statusHits > asked && (await answered()) === true)) await sleep(250);
      if (!(statusHits > asked && (await answered()) === true)) check("the Plan screen shows the server's answer (" + platform + ", " + st.plan + ")", false, "status replies " + (statusHits - asked));
    }
    await sleep(600);
    return JSON.parse(await q("const s=d.getElementById('acctSec');return JSON.stringify({sandbox:/SANDBOX/.test(s.innerText),prices:[...s.querySelectorAll('.pr')].map(e=>e.textContent),text:s.innerText,lead:(s.querySelector('.lead')||{}).innerText||'',stripe:[...s.querySelectorAll('[data-bill]')].map(b=>b.getAttribute('data-bill')).filter(k=>k!=='retry'),plan:s.querySelectorAll('[data-plan]').length,choose:[...s.querySelectorAll('button')].filter(b=>/^(Choose|Sign in to choose|Switch)/.test(b.innerText.trim())).map(b=>b.innerText.trim()),perks:s.querySelectorAll('.plans .plan li').length,cards:[...s.querySelectorAll('.plans .plan b')].map(b=>b.innerText.trim()),note:!!d.getElementById('storeNote')})"));
  };
  const tag = (process.env.W || "1280") + "x" + (process.env.H || "720");
  // the "Message the hiring manager" field: on a free account it offers See plans on the website, never in the apps
  const autoPlans = () => q("if(w.__uaplySyncPrefs)w.__uaplySyncPrefs();const b=d.getElementById('aAutoPlans');return b?b.hidden:'none'");

  // the website: every button stays
  const wf = await open("web", FREE);
  check("web, free account: Choose Plus and Choose Pro are offered", wf.choose.includes("Choose Plus") && wf.choose.includes("Choose Pro"), JSON.stringify(wf.choose));
  check("web, free account: prices are shown and the app-only line is not", /\$9\.99/.test(wf.text) && /\$19\.99/.test(wf.text) && !wf.note, wf.text.slice(0, 200));
  if (SHOTS) await shot(SHOTS + "/web-plan-" + tag + ".png");
  const wa = await autoPlans(), rel = (await q("const o=w.UAplyOpts||w.top.UAplyOpts;return !!(o&&o.release)")) === true;
  if (rel) console.log("(release build: the auto-message field's See plans is hidden on every platform, so the website side is not compared)");
  else check("web, free account: the auto-message field offers See plans", wa === false, String(wa));
  const wp = await open("web", PLUS);
  check("web, Plus subscriber with a failed payment: Update card and Manage billing are offered", wp.stripe.filter((k) => k === "portal").length >= 2 && /Manage billing/.test(wp.text), JSON.stringify(wp.stripe));

  for (const platform of ["android", "ios"]) {
    const af = await open(platform, FREE);
    check(platform + " app, free account: no button that opens Stripe (no Choose, no data-bill, no data-plan)", af.stripe.length === 0 && af.plan === 0 && af.choose.length === 0, JSON.stringify(af));
    check(platform + " app, free account: the screen still says what each plan includes (Free, Plus, Pro and their perks)", JSON.stringify(af.cards) === '["Free","Plus","Pro"]' && af.perks >= 6, JSON.stringify(af.cards) + " " + af.perks);
    check(platform + " app, free account: no paid price, and the honest line instead", !/\$9\.99|\$19\.99/.test(af.text) && af.note && af.text.includes(NOTE) && af.lead === "What each plan includes.", af.text.slice(0, 300));
    if (SHOTS && platform === "android") await shot(SHOTS + "/app-plan-" + tag + ".png");
    const aa = await autoPlans();
    check(platform + " app, free account: the auto-message field offers no See plans", aa === true, String(aa));
    const ap = await open(platform, PLUS);
    check(platform + " app, Plus subscriber with a failed payment: no Update card or Manage billing button, told to update the card on uaply.net", ap.stripe.length === 0 && ap.choose.length === 0 && /update your card in Manage billing on uaply\.net/.test(ap.text) && ap.text.includes(NOTE), JSON.stringify(ap.stripe) + " " + ap.text.slice(0, 300));
    // a buy button that slipped onto the screen some other way still does nothing in the apps
    const before = stripeHits;
    await q("const b=d.createElement('button');b.setAttribute('data-bill','plus');b.id='slipped';d.getElementById('acctSec').appendChild(b);b.click();return true");
    await sleep(800);
    const m = await q("return (d.getElementById('aMsg')||{}).innerText||''");
    check(platform + " app: a stray Choose button sends no checkout request and shows the line instead", stripeHits === before && m === NOTE, "hits " + (stripeHits - before) + " msg " + m);
  }

  // the Google Play app: a Trusted Web Activity is plain Chrome (no Capacitor). Chrome opens it with the referrer android-app://com.uaply.app;
  // the referrer is faked on the top page only, the way Chrome sets it on launch
  const noStripe = (r) => r.stripe.length === 0 && r.plan === 0 && r.choose.length === 0 && r.note && !/\$9\.99|\$19\.99/.test(r.text);
  const fake = async (ref) => (await send("Page.addScriptToEvaluateOnNewDocument", { source: "if(window===window.top)Object.defineProperty(document,'referrer',{get:()=>'" + ref + "'})" })).result.identifier;
  // leave the app page first: a page still open at ?src=twa (or with the app's referrer) writes the flag again on its next render
  const forget = async () => { await nav(base + "/healthz"); return ev("(()=>{sessionStorage.removeItem('uaply.storeApp');return true})()"); };
  let sid = await fake("android-app://com.uaply.app/");
  const tf = await open("twa", FREE);
  check("Google Play app (Trusted Web Activity, no Capacitor): no button that opens Stripe, no paid price, the honest line", noStripe(tf), JSON.stringify({ stripe: tf.stripe, plan: tf.plan, choose: tf.choose, note: tf.note }));
  if (SHOTS) await shot(SHOTS + "/twa-plan-" + tag + ".png");
  const tp = await open("twa", PLUS);
  check("Google Play app, Plus subscriber with a failed payment: no Update card or Manage billing button", tp.stripe.length === 0 && /on uaply\.net/.test(tp.text), JSON.stringify(tp.stripe));
  await send("Page.removeScriptToEvaluateOnNewDocument", { identifier: sid });
  const tl = await open("twa", FREE);       // a later page in the same app has no referrer: remembered for the session
  check("Google Play app, a later page with no referrer: still no Stripe button (remembered for the session)", noStripe(tl), JSON.stringify({ stripe: tl.stripe, choose: tl.choose }));
  await forget();
  sid = await fake("android-app://com.google.android.gm/");
  const gm = await open("web", FREE);       // a link opened from another Android app (Gmail) is the website in Chrome
  check("website opened from another Android app (Gmail's referrer): Choose Plus and Choose Pro stay", gm.choose.includes("Choose Plus") && gm.choose.includes("Choose Pro") && !gm.note, JSON.stringify(gm.choose));
  await send("Page.removeScriptToEvaluateOnNewDocument", { identifier: sid });
  await forget();
  const ts = await open("twa", FREE, "/?src=twa");
  check("Google Play app started at /?src=twa: no button that opens Stripe", noStripe(ts), JSON.stringify({ stripe: ts.stripe, choose: ts.choose }));
  await forget();
  const wb = await open("web", FREE);
  check("website again after the app's session is forgotten: the buttons are back", wb.choose.includes("Choose Plus") && !wb.note, JSON.stringify(wb.choose));

  // the weekly limit (payments on): the server says "Choose a bigger plan"; the apps cannot offer one, so they say when applying works again
  const limitToast = async (platform) => {
    await open(platform, FREE);
    const r = await q("const A=w.__uaply,job=(A.JOBS||[])[0];if(!job)return 'no job';w.__uaplyResume=function(){return {name:'Sam Rivera Resume.pdf',size:40,data:'data:application/pdf;base64,'+btoa('%PDF-1.4 test %%EOF')}};" +
      "Object.assign(A.S.profile,{name:'Sam Rivera',email:'sam@example.com',custom:true,title:'Data Analyst',years:1,skills:['Python','SQL']});" +
      "A.S.decisions[job.id]={s:'applied',at:Date.now(),pct:60};A.S.history.push(job.id);A.save();w.__uaplyResend(job.id);return 'ok'");
    const t = await waitFor("const t=d.getElementById('kitToast');return t&&/back in your deck/.test(t.innerText)?JSON.stringify({text:t.innerText.replace(/\\s+/g,' ').trim(),buttons:[...t.querySelectorAll('button')].map(b=>b.innerText)}):''", 8000);
    if (SHOTS && platform === "android") await shot(SHOTS + "/app-limit-" + tag + ".png");
    return { r, t: t && !String(t).startsWith("ERR") ? JSON.parse(t) : { text: String(t), buttons: [] } };
  };
  for (const platform of ["android", "web"]) {
    const before = applyHits, lt = await limitToast(platform);
    const sent = applyHits > before;
    if (platform === "web") check("web, weekly limit: the server's words and See plans stay", sent && lt.t.text.includes("Choose a bigger plan") && lt.t.buttons.includes("See plans"), lt.r + " " + JSON.stringify(lt.t));
    else check(platform + " app, weekly limit: no 'Choose a bigger plan' and no See plans, says when applying works again", sent && !/Choose a bigger plan|See plans/.test(lt.t.text) && lt.t.buttons.length === 0 && /^You've used your 50 applications this week on Free\. The limit counts the last 7 days/.test(lt.t.text), lt.r + " " + JSON.stringify(lt.t));
  }

  // the no-server sandbox (every /api/ request fails): the simulated Plan screen follows the same rule
  noServer = true;
  const ns = await open("android", FREE);
  if (ns.sandbox) {
    check("no-server sandbox, android app: no Choose or Switch button, no paid price, the honest line", ns.plan === 0 && ns.choose.length === 0 && ns.note && JSON.stringify(ns.prices) === '["$0"]', JSON.stringify({ plan: ns.plan, choose: ns.choose, prices: ns.prices, note: ns.note }));
    // the sandbox paywall ("Enforce plan limits" on, 50 applications this week): in the apps it offers no plans to pick
    const paywall = () => q("const e=d.getElementById('aEnf');if(!e.checked)e.click();const A=w.__uaply;for(let i=0;i<50;i++)A.S.decisions[900000+i]={s:'applied',at:Date.now(),pct:50};" +
      "w.__uaplyGate();const p=d.getElementById('paywall');const r=p?JSON.stringify({title:p.querySelector('h2').innerText,buttons:[...p.querySelectorAll('button')].map(b=>b.innerText)}):'none';" +
      "if(p)p.remove();for(let i=0;i<50;i++)delete A.S.decisions[900000+i];if(e.checked)e.click();return r");
    const pa = await paywall();
    check("no-server sandbox, android app: the weekly-limit box says 'Weekly limit reached' with no See plans", pa !== "none" && JSON.parse(pa).title === "Weekly limit reached" && !JSON.parse(pa).buttons.includes("See plans"), pa);
    const nw = await open("web", FREE);
    check("no-server sandbox, website: Choose buttons and prices stay", nw.plan >= 2 && nw.prices.length === 3 && !nw.note, JSON.stringify({ plan: nw.plan, prices: nw.prices }));
    const pw = await paywall();
    check("no-server sandbox, website: the weekly-limit box keeps 'Choose a plan to keep applying' and See plans", pw !== "none" && JSON.parse(pw).title === "Choose a plan to keep applying" && JSON.parse(pw).buttons.includes("See plans"), pw);
  } else console.log("(the no-server checks apply to the sandbox build only; this server's Plan screen is not the simulated one)");
  noServer = false;
  await send("Fetch.disable");
  check("no console errors and no patch target not found", logs.length === 0, logs.join(" / ").slice(0, 300));
  console.log("\n" + pass + " / " + (pass + fail));
};
