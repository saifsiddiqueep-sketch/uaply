// The Help chat bubble must not crowd Pass/Undo/Apply on phones, and Plan & billing / Account must be centered like the deck.
//   W=375 H=812 PORT=8767 TAG=after node tools/cdp.js tools/ui-help-centering.js
module.exports = async ({ ev, sleep, nav, shot }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const W = Number(process.env.W || 1100), H = process.env.H || 900, TAG = process.env.TAG || "run";
  let bad = 0;
  const check = (n, ok, x) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? "  " + x : "")); };
  await nav("http://127.0.0.1:" + (process.env.PORT || "8767") + "/");
  await sleep(4000);
  await ev("(()=>{const b=" + F + ".getElementById('kcNo');if(b)b.click()})()"); await sleep(400);   // the one-time notice
  // nearest Pass/Undo/Apply button to the Help bubble (edge-to-edge distance, 0 = touching or overlapping)
  const m = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ";const h=d.getElementById('uaChatBtn');if(!h||!h.getClientRects().length)return {none:1};const a=h.getBoundingClientRect();let gap=1e9,who='';" +
    "for(const b of d.querySelectorAll('button')){if(b===h||!b.getClientRects().length)continue;const t=(b.innerText||b.title||b.getAttribute('aria-label')||'').trim();if(!/^(pass|undo|apply)/i.test(t))continue;const r=b.getBoundingClientRect();if(!r.width)continue;" +
    "const dx=Math.max(0,r.left-a.right,a.left-r.right),dy=Math.max(0,r.top-a.bottom,a.top-r.bottom);const g=Math.hypot(dx,dy);if(g<gap){gap=g;who=t.split(String.fromCharCode(10))[0]}}return {gap:Math.round(gap),nearest:who,help:[a.left,a.top,a.right,a.bottom].map(Math.round)}})())"));
  if (W < 700) check("Help bubble clear of Pass/Undo/Apply (" + W + "x" + H + ")", m.none || m.gap >= 16, JSON.stringify(m));
  await shot("shot-" + TAG + "-swipe-" + W + "x" + H + ".png");
  const sub = (k) => ev("(()=>{const d=" + F + ";d.getElementById('nb-prof').click();const it=d.querySelector('.nwrap[data-k=prof] .nitem[data-v=" + k + "]');if(it)it.click();return !!it})()");
  // the screen's content block (#acctSec) inside the app column (#main): its left and right margins
  const margins = () => ev("JSON.stringify((()=>{const d=" + F + ";const e=d.getElementById('acctSec');if(!e||e.hidden)return null;const m=e.closest('main')||d.body;const c=m.getBoundingClientRect(),cs=getComputedStyle(m),r=e.getBoundingClientRect();return {w:Math.round(r.width),left:Math.round(r.left-c.left-parseFloat(cs.paddingLeft)),right:Math.round(c.left+m.clientLeft+m.clientWidth-parseFloat(cs.paddingRight)-r.right)}})())").then(JSON.parse);
  for (const k of ["plan", "account"]) {
    await sub(k); await sleep(900);
    const b = await margins();
    if (W >= 700) check(k + " centered at " + W + "px", !!b && Math.abs(b.left - b.right) <= 4, JSON.stringify(b));
    await shot("shot-" + TAG + "-" + k + "-" + W + "x" + H + ".png");
  }
  console.log(bad ? bad + " FAILED" : "ALL PASS");
  process.exitCode = bad ? 1 : 0;
};
