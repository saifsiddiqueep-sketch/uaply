// "Continue with Google" on an iPhone, in a real browser, on the sign-in gate's card (October 22, Saif: signed out, the card is the whole
// screen). Google says its button needs the full-page sign-in on iPhone and iPad, so the card shows UAply's own Google-styled button, which
// goes to Google and back (here: the stand-in Google, tools/mock-google.py). Also checks that the phone apps (Capacitor) hide Google,
// because Google refuses sign-in inside an app's built-in web view.
// Needs a server with the stand-in Google and a client secret configured (see tools/run-all-tests.sh):
//   W=390 H=844 PORT=18768 MOCK_GOOGLE_PORT=8790 node tools/cdp.js tools/ui-google-ios.js
const PORT = process.env.PORT || "18768";
const MOCK = "http://127.0.0.1:" + (process.env.MOCK_GOOGLE_PORT || "8790");
const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Mobile/15E148 Safari/604.1";
module.exports = async ({ ev, sleep, nav, logs, send }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const BASE = "http://127.0.0.1:" + PORT;
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const q = (sel) => F + ".querySelector(" + JSON.stringify(sel) + ")";
  const card = () => ev("(()=>{try{return ((" + F + ").getElementById('acctSec')||{innerText:''}).innerText.split(/\\s+/).join(' ')}catch(e){return ''}})()");
  const me = () => ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>JSON.stringify(j.user||null))").then(JSON.parse);
  const post = (path, body) => ev("fetch('" + path + "',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(" + JSON.stringify(body) + ")}).then(r=>r.status)");
  const ready = async () => { for (let i = 0; i < 40 && !(await ev("!!" + q(".sg-card")).catch(() => false)); i++) await sleep(250); await sleep(600); };
  const open = async () => { await nav(BASE + "/"); await ready(); };
  const googleFlow = async (who, agree) => {
    await fetch(MOCK + "/mock/next?" + new URLSearchParams(who));          // who the stand-in Google signs in next
    if (agree) await ev("(()=>{const a=" + q(".sg-su .sg-ag") + ";if(a&&!a.checked)a.click()})()");
    const clicked = await ev("(()=>{const b=" + q(".sg-card [data-sg=google]") + ";if(!b)return false;b.click();return true})()");
    await sleep(4500);                                                     // to Google and back: start, the stand-in's page, our callback
    await ready();
    return clicked;
  };

  await send("Emulation.setUserAgentOverride", { userAgent: IPHONE, platform: "iPhone" });
  await send("Storage.clearDataForOrigin", { origin: BASE, storageTypes: "all" });
  const stamp = Date.now();
  const pwEmail = "ios.owner." + stamp + "@gmail.com";
  await open();
  check("the page sees an iPhone", await ev("/iPhone/.test(navigator.userAgent)"));
  check("the server offers the full-page Google sign-in (client secret set)", await ev("fetch('/api/auth/providers').then(r=>r.json()).then(j=>j.googleRedirect===true)"));
  check("on an iPhone the card shows UAply's own Continue with Google button", !!(await ev("!!" + q(".sg-card [data-sg=google]"))));
  check("...with Google's G logo and the words Continue with Google", await ev("(()=>{const b=" + q(".sg-card [data-sg=google]") + ";return !!b&&!!b.querySelector('svg')&&/Continue with Google/.test(b.innerText)})()"));
  check("...and not Google's pop-up button (which Google says needs the full page on iPhone)", !(await ev("!!" + q("#gBtn iframe, .sg-gis"))));

  // someone made a password account with this person's Gmail and never confirmed it; the real owner then arrives with Google
  check("a password account with that Gmail exists (made through the API)", (await post("/api/auth/signup", { email: pwEmail, password: "someone elses 1", first: "Some", last: "One", agree: true })) === 200);
  await post("/api/auth/logout", {});
  await open();
  // the account's address was never proven, so joining it needs this person's own 18+ / Terms tick
  await googleFlow({ email: pwEmail, sub: "ios-" + stamp, verified: "1" }, false);
  check("without the 18+ / Terms tick, Google into that unproven account is refused: the person is told to tick the box", /Tick the box/.test(await card()), (await card()).slice(0, 200));
  check("...nobody is signed in, and the account still has its password (nothing was linked)",
    (await me()) === null && (await post("/api/auth/login", { email: pwEmail, password: "someone elses 1" })) === 200);
  await post("/api/auth/logout", {});
  await open();
  check("pressing the button with the box ticked goes to Google and back", await googleFlow({ email: pwEmail, sub: "ios-" + stamp, verified: "1" }, true));
  check("back in the app, the address bar is clean again", await ev("/^\\/(app\\.html)?$/.test(location.pathname)&&location.search===''"), await ev("location.href"));
  const t1 = await card(), u1 = await me();
  check("it says the person is signed in with Google, and that the unconfirmed password was removed", /was removed to keep the account yours/.test(t1), t1.slice(0, 300));
  check("the account shows them signed in, email verified, no password", !!u1 && u1.email === pwEmail && u1.emailVerified === true && u1.hasPassword === false, JSON.stringify(u1));
  check("the card names them", t1.includes(pwEmail) || t1.includes("Some"), t1.slice(0, 300));
  check("the old password no longer works", (await post("/api/auth/login", { email: pwEmail, password: "someone elses 1" })) === 401);

  // a brand-new person: must tick the 18+ and Terms box first
  await post("/api/auth/logout", {});
  await open();
  const newEmail = "ios.new." + stamp + "@gmail.com";
  await googleFlow({ email: newEmail, sub: "ios-new-" + stamp, verified: "1" }, false);
  check("a new person who did not tick the box is told to", /Tick the box/.test(await card()), (await card()).slice(0, 200));
  check("...and is not signed in", (await me()) === null);
  await googleFlow({ email: newEmail, sub: "ios-new-" + stamp, verified: "1" }, true);
  const u2 = await me();
  check("with the box ticked, the new person is signed in", !!u2 && u2.email === newEmail && u2.hasPassword === false, JSON.stringify(u2));
  check("...and told so", /Account created with Google|Signed in with Google/.test(await card()), (await card()).slice(0, 200));

  // inside the phone app (Capacitor), Google is hidden: Google blocks sign-in in an app's built-in web view
  await post("/api/auth/logout", {});
  for (const platform of ["android", "ios"]) {
    const s = await send("Page.addScriptToEvaluateOnNewDocument", { source: "window.Capacitor={isNativePlatform:()=>true,getPlatform:()=>'" + platform + "'}" });
    await open();
    check("in the " + platform + " app the Google button is hidden", !(await ev("!!" + q(".sg-card [data-sg=google], #gBtn"))));
    check("...and password sign-up is still there", !!(await ev("!!" + q(".sg-su .sg-pw input"))));
    await send("Page.removeScriptToEvaluateOnNewDocument", { identifier: s.result.identifier });
  }
  // a computer (Chrome on Windows): with the client secret set, the same full-page sign-in is used, so neither third-party cookies,
  // Chrome's FedCM prompt nor the srcdoc frame (location.origin "null") can get in the way; Google's pop-up script is not even loaded
  await send("Emulation.setUserAgentOverride", { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36", platform: "Win32" });
  await open();
  check("on a computer the card has the same full-page Continue with Google button", !!(await ev("!!" + q(".sg-card [data-sg=google]"))));
  check("...and Google's pop-up script (accounts.google.com/gsi/client) is not loaded", !(await ev("!!" + q("script[src*=\"gsi/client\"]"))));
  check("the app frame really is a srcdoc frame whose location.origin is 'null' (why Google's pop-up button is not used)", await ev("(document.querySelector('iframe').contentWindow.location.origin)==='null'"));
  const desk = "desk." + stamp + "@gmail.com";
  await googleFlow({ email: desk, sub: "desk-" + stamp, verified: "1" }, true);
  const u3 = await me();
  check("on a computer, pressing it goes to Google and back signed in", !!u3 && u3.email === desk, JSON.stringify(u3));
  const errs = logs.filter((l) => !/401|403|favicon/.test(l));
  check("no script errors", errs.length === 0, errs.join(" / ").slice(0, 160));
  console.log(bad ? "\n" + bad + " check(s) failed" : "\nAll iPhone and computer Google sign-in checks passed");
};
