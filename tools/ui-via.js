// The card credits where a real job came from: "via City of Philadelphia on SmartRecruiters" next to its apply wording ("Ready"), small and muted.
//   PORT=<port> W=390 H=844 node tools/cdp.js tools/ui-via.js      (tools/test-feeds.py <port> starts a server with recorded City jobs and runs this)
// SHOT=<file.png> saves a picture of the card.
const PORT = process.env.PORT || "8766";
module.exports = async ({ ev, sleep, nav, shot }) => {
  // the sign-in gate (October 22, Saif): nobody reaches the jobs without an account, so a fresh test person signs up first (tools/gate-signup.js)
  await require("./gate-signup.js")({ ev, sleep, nav }, "http://127.0.0.1:" + (process.env.PORT || "8767"), "via", { api: true });
  const F = "document.querySelector('iframe').contentDocument";
  const check = (name, ok, got) => console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  -> " + got));
  await nav("http://127.0.0.1:" + PORT + "/");
  // wait (up to 15 s) for the page, its frame and the real jobs to load
  for (let i = 0; i < 30 && (await ev("(()=>{try{return !!" + F + ".querySelector('.card .facts .via')}catch(e){return false}})()")) !== true; i++) await sleep(500);
  const info = JSON.parse(await ev("(()=>{const c=" + F + ".querySelector('.card');if(!c)return JSON.stringify({});const v=c.querySelector('.facts .via'),x=c.querySelector('.facts .ext');" +
    "const s=v&&getComputedStyle(v),xs=x&&getComputedStyle(x);return JSON.stringify({via:v?v.textContent:'',ext:x?x.textContent:'',next:!!(x&&x.nextElementSibling===v)," +
    "size:s?parseFloat(s.fontSize):0,extSize:xs?parseFloat(xs.fontSize):0,color:s?s.color:'',extColor:xs?xs.color:'',co:(c.querySelector('h2,h3')||c).textContent.trim().slice(0,80)})})()"));
  console.log("top card:", info.co);
  check("the top card is a real City job and says 'Ready' (its route; never the old 'Opens employer site')", /^Ready/.test(info.ext), info.ext);
  check("it says 'via City of Philadelphia on SmartRecruiters'", info.via === "via City of Philadelphia on SmartRecruiters", info.via);
  check("the credit sits right after it", info.next, info.next);
  // no larger than the line it follows, and at least 14 px (the owner's floor since October 23 raised it to the same size)
  check("it is no larger than the line it follows, at least 14 px, in the same muted color", info.size >= 14 && info.size <= info.extSize && info.color === info.extColor, JSON.stringify(info));
  if (process.env.SHOT) await shot(process.env.SHOT);
};
