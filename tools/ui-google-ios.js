// "Continue with Google" on an iPhone, in a real browser: Google says its button needs the full-page sign-in on iPhone and iPad, so there the
// page shows UAply's own Google-styled button, which goes to Google and back (here: the stand-in Google, tools/mock-google.py). Also checks
// that the phone apps (Capacitor) hide Google, because Google refuses sign-in inside an app's built-in web view.
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
  const msg = () => ev("((" + F + ").getElementById('aMsg')||{}).innerText||''");
  const openAccount = async () => {
    await ev(F + ".getElementById('nb-prof').click()"); await sleep(450);
    await ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Account'));if(e)e.click()})()"); await sleep(1200);
  };
  const post = (path, body) => ev("fetch('" + path + "',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(" + JSON.stringify(body) + ")}).then(r=>r.status)");
  const googleFlow = async (who, agree) => {
    await fetch(MOCK + "/mock/next?" + new URLSearchParams(who));          // who the stand-in Google signs in next
    await openAccount();
    if (agree) await ev("(()=>{const c=" + F + ".getElementById('gAgree');if(c)c.checked=true})()");
    const clicked = await ev("(()=>{const b=" + F + ".querySelector('#gBtn [data-auth=gsign]');if(!b)return false;b.click();return true})()");
    await sleep(4000);                                                     // to Google and back: start, the stand-in's page, our callback
    return clicked;
  };

  await send("Emulation.setUserAgentOverride", { userAgent: IPHONE, platform: "iPhone" });
  const stamp = Date.now();
  const pwEmail = "ios.owner." + stamp + "@gmail.com";
  await nav(BASE + "/");
  await sleep(2500);
  check("the page sees an iPhone", await ev("/iPhone/.test(navigator.userAgent)"));
  check("the server offers the full-page Google sign-in (client secret set)", await ev("fetch('/api/auth/providers').then(r=>r.json()).then(j=>j.googleRedirect===true)"));
  await openAccount();
  check("on an iPhone the Google area shows UAply's own Continue with Google button", await ev("!!" + F + ".querySelector('#gBtn [data-auth=gsign]')"));
  check("...with Google's G logo and the words Continue with Google", await ev("(()=>{const b=" + F + ".querySelector('#gBtn [data-auth=gsign]');return !!b&&!!b.querySelector('svg')&&/Continue with Google/.test(b.innerText)})()"));
  check("...and not Google's pop-up button (which Google says needs the full page on iPhone)", !(await ev("!!" + F + ".querySelector('#gBtn iframe')")));

  // someone made a password account with this person's Gmail and never confirmed it; the real owner then arrives with Google
  check("a password account with that Gmail exists (made through the API)", (await post("/api/auth/signup", { email: pwEmail, password: "someone elses 1", agree: true })) === 200);
  await post("/api/auth/logout", {});
  await nav(BASE + "/"); await sleep(2500);
  check("pressing the button goes to Google and back", await googleFlow({ email: pwEmail, sub: "ios-" + stamp, verified: "1" }, false));
  check("back in the app, the address bar is clean again", await ev("location.pathname==='/'&&location.search===''"), await ev("location.href"));
  const m1 = await msg();
  check("it says the person is signed in with Google, and that the unconfirmed password was removed", /Signed in with Google/.test(m1) && /removed/.test(m1), m1.slice(0, 120));
  check("the account screen shows them signed in, email verified", await ev("/You are signed in/.test((" + F + ").body.innerText)&&/email verified/.test((" + F + ").body.innerText)"));
  check("the header's account button names them", (await ev("(" + F + ".getElementById('hdrAcct')||{getAttribute:()=>''}).getAttribute('aria-label')||''")).includes(pwEmail));
  check("the old password no longer works", (await post("/api/auth/login", { email: pwEmail, password: "someone elses 1" })) === 401);

  // a brand-new person: must tick the 18+ and Terms box first
  await post("/api/auth/logout", {});
  await nav(BASE + "/"); await sleep(2500);
  const newEmail = "ios.new." + stamp + "@gmail.com";
  await googleFlow({ email: newEmail, sub: "ios-new-" + stamp, verified: "1" }, false);
  check("a new person who did not tick the box is told to", /Tick the box/.test(await msg()), (await msg()).slice(0, 100));
  check("...and is not signed in", await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>j.user===null)"));
  await googleFlow({ email: newEmail, sub: "ios-new-" + stamp, verified: "1" }, true);
  check("with the box ticked, the new person is signed in", await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>!!j.user&&j.user.email==='" + newEmail + "'&&j.user.hasPassword===false)"));
  check("...and told so", /Signed in with Google/.test(await msg()), (await msg()).slice(0, 80));

  // inside the phone app (Capacitor), Google is hidden: Google blocks sign-in in an app's built-in web view
  await post("/api/auth/logout", {});
  for (const platform of ["android", "ios"]) {
    await nav(BASE + "/"); await sleep(1500);
    await ev("window.Capacitor={isNativePlatform:()=>true,getPlatform:()=>'" + platform + "'}");
    await openAccount();
    check("in the " + platform + " app the Google button is hidden", !(await ev("!!" + F + ".getElementById('gBtn')")) && !(await ev("!!" + F + ".querySelector('[data-auth=gsign]')")));
    check("...and password sign-up is still there", await ev("!!" + F + ".getElementById('sEmail')"));
  }
  // a computer (Chrome on Windows): with the client secret set, the same full-page sign-in is used, so neither third-party cookies,
  // Chrome's FedCM prompt nor the srcdoc frame (location.origin "null") can get in the way; Google's pop-up script is not even loaded
  await send("Emulation.setUserAgentOverride", { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36", platform: "Win32" });
  await nav(BASE + "/"); await sleep(2500);
  await openAccount();
  check("on a computer the Google area is the same full-page Continue with Google button", await ev("!!" + F + ".querySelector('#gBtn [data-auth=gsign]')"));
  check("...and Google's pop-up script (accounts.google.com/gsi/client) is not loaded", !(await ev("!!" + F + ".querySelector('script[src*=\"gsi/client\"]')")));
  check("the app frame really is a srcdoc frame whose location.origin is 'null' (why Google's pop-up button is not used)", await ev("(document.querySelector('iframe').contentWindow.location.origin)==='null'"));
  const desk = "desk." + stamp + "@gmail.com";
  await googleFlow({ email: desk, sub: "desk-" + stamp, verified: "1" }, true);
  check("on a computer, pressing it goes to Google and back signed in", await ev("fetch('/api/auth/me').then(r=>r.json()).then(j=>!!j.user&&j.user.email==='" + desk + "')"));
  check("no script errors", logs.length === 0, logs.join(" / ").slice(0, 160));
  console.log(bad ? "\n" + bad + " check(s) failed" : "\nAll iPhone and computer Google sign-in checks passed");
};
