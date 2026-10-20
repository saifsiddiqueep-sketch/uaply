// A bare "?signed_in=google" link (typed, shared or replayed) must not claim anything: no "Signed in with Google", and no "privacy shields
// are blocking sign-in" notice, because nobody pressed Continue with Google in this tab. The notice still comes after a real round trip
// (this tab left for Google within 15 minutes) that brought back no session. Needs a server whose page has OPTS.shieldsHelp (the sandbox):
//   PORT=8766 node tools/cdp.js tools/ui-signed-in-link.js
const BASE = "http://127.0.0.1:" + (process.env.PORT || "8766");
module.exports = async ({ ev, sleep, nav, send }) => {
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { ok ? pass++ : fail++; console.log((ok ? "PASS " : "FAIL ") + name + (ok || !extra ? "" : "  -> " + extra)); return ok; };
  const F = "document.querySelector('iframe').contentDocument";
  const q = (js) => ev("(()=>{try{const d=" + F + ",w=d.defaultView;" + js + "}catch(e){return 'ERR '+e.message}})()");
  const state = () => q("return JSON.stringify({shield:!!d.getElementById('shieldsNote'),msg:(d.getElementById('aMsg')||{}).innerText||'',acct:!d.getElementById('acctSec').hidden})").then((s) => { try { return JSON.parse(s); } catch (e) { return { err: s }; } });
  const open = async (pre) => {
    await nav(BASE + "/healthz");
    await send("Storage.clearDataForOrigin", { origin: BASE, storageTypes: "all" });
    await send("Network.clearBrowserCookies");
    if (pre) await ev(pre);
    await nav(BASE + "/?signed_in=google");
    for (let i = 0; i < 40; i++) { const s = await state(); if (s.acct) break; await sleep(250); }
    await sleep(1500);
    return state();
  };
  const a = await open("");
  check("a bare ?signed_in=google link: no privacy-shields notice", a.shield === false, JSON.stringify(a));
  check("...and no 'Signed in with Google' (nobody is signed in)", !/Signed in with Google/.test(a.msg), a.msg);
  check("...and the address no longer carries it", !/signed_in=/.test(await ev("location.href")), await ev("location.href"));
  const b = await open("sessionStorage.setItem('uaply.gstart',String(Date.now()));1");
  check("after a real round trip (this tab left for Google) with no session back: the shields notice shows", b.shield === true, JSON.stringify(b));
  const c = await open("sessionStorage.setItem('uaply.gstart',String(Date.now()-16*60e3));1");
  check("a round trip older than 15 minutes counts as a bare link: no notice", c.shield === false, JSON.stringify(c));
  console.log("\n" + pass + " / " + (pass + fail));
};
