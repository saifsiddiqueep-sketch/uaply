// Screenshots of the sandbox's sign-up card (sign-up v2) and the measurements behind Mohammed's layout call: the brand mark directly above
// the card, the two centered together, Continue with Google above the fold, 16 px gutters on a phone.
//   OUT=<folder> W=1280 H=720 PORT=<sandbox port> [DARK=1] [BEFORE=1] node tools/cdp.js tools/shot-signup.js
// BEFORE=1 switches the "Sign-up, nothing hidden" experiment off first (the sandbox as it was). NAME sets the file name.
const path = require("path");
module.exports = async ({ ev, sleep, nav, shot, send }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const W = process.env.W || 1280, H = process.env.H || 720, dark = process.env.DARK === "1", before = process.env.BEFORE === "1";
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: dark ? "dark" : "light" }] });
  if (Number(W) >= 700) await send("Emulation.setDeviceMetricsOverride", { width: Number(W), height: Number(H), deviceScaleFactor: 1, mobile: false });   // the exact laptop viewport
  await nav("http://127.0.0.1:" + process.env.PORT + "/?app=1");
  await sleep(3500);
  if (before) {
    await ev("document.querySelector('#feats button[data-k=signup]').click()");
    await sleep(4000);
  }
  // the one-time "Before you start swiping" agreement covers the screen on a first visit: Not now (it asks again at the first swipe)
  await ev("(()=>{const b=[...(" + F + ").querySelectorAll('button')].find(x=>x.offsetParent&&x.innerText.trim()==='Not now');if(b)b.click()})()"); await sleep(500);
  await ev(F + ".getElementById('nb-prof').click()"); await sleep(450);
  await ev("[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Account')).click()"); await sleep(3000);
  const name = process.env.NAME || ((before ? "before" : "after") + "-" + W + "x" + H + "-" + (dark ? "dark" : "light") + ".png");
  await shot(path.join(process.env.OUT, name));
  const m = await ev("(()=>{const d=" + F + ",fw=d.defaultView,r=(e)=>e&&e.getBoundingClientRect();" +
    "const card=d.querySelector('.sg-card')||d.getElementById('signBox'),g=d.querySelector('[data-sg=google]')||d.querySelector('[data-auth=gsign]')||d.getElementById('gBtn'),bb=d.querySelector('.sg-bb');" +
    "const c=r(card),gr=r(g),br=r(bb),vw=fw.innerWidth,vh=fw.innerHeight;" +
    "return JSON.stringify({frame:[vw,vh],card:c&&{left:Math.round(c.left),right:Math.round(vw-c.right),top:Math.round(c.top),bottom:Math.round(c.bottom),width:Math.round(c.width)}," +
    "googleBottom:gr&&Math.round(gr.bottom),googleAboveFold:!!gr&&gr.bottom<vh,logoToCard:br&&c?Math.round(c.top-br.bottom):null,hscroll:d.documentElement.scrollWidth>vw})})()");
  console.log(name + " " + m);
};
