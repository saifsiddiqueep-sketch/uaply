// Pass / Undo / Apply always in sight above the bottom bar (Jobs / Dashboard / Profile), the way a new visitor first sees the app.
//   W=390 H=844 PORT=8767 node tools/cdp.js tools/ui-buttons-bar.js        (also 375x667, 440x956, 1280x800; dev and sandbox)
// The October 17 audit found the three buttons under the bar on first open at phone sizes (the job card's 430 px minimum height plus
// the tips, the example-profile notice, the location box and the filters pushed them below the bottom of the scrolling area), so a
// new visitor saw a card and no way to apply: "Start does not work". This test measures the boxes, it does not trust a screenshot:
//   1. on first open (agreement box still up) and after Agree, each button's box lies fully inside the visible part of the app,
//      above the bottom bar and inside the scrolling area, without scrolling anything;
//   2. after Agree a tap at the centre and near the corners of each button reaches that button (nothing lies on top of it);
//   3. the buttons never cover the job card's own controls: scrolled to the end, the card ends above the buttons, and every card
//      control that is on screen can be reached;
//   4. after a swipe the message ("Passed on ...", Undo) sits clear of the three buttons and of the bar.
const PORT = process.env.PORT || "8767";
module.exports = async ({ ev, sleep, nav, shot }) => {
  const F = "document.querySelector('iframe').contentDocument";
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const size = (process.env.W || 1100) + "x" + (process.env.H || 900);

  // every box in the app frame's own coordinates, plus where the frame itself sits in the window
  const boxes = async () => JSON.parse(await ev(`JSON.stringify((()=>{const d=${F},w=d.defaultView,f=document.querySelector('iframe').getBoundingClientRect();
    const r=e=>{if(!e)return null;const b=e.getBoundingClientRect();return {t:b.top,b:b.bottom,l:b.left,r:b.right,h:b.height}};
    const t=d.querySelector('.toast');
    return {vh:w.innerHeight,frameBottom:f.bottom,winH:innerHeight,nav:r(d.getElementById('bnav')),main:r(d.getElementById('main')),
      btns:['btnNo','btnUndo','btnYes'].map(id=>Object.assign({id},r(d.getElementById(id)))),acts:r(d.querySelector('#pane-swipe .actions')),
      card:r(d.querySelector('.card.top')),toast:t&&getComputedStyle(t).display!=='none'&&t.getBoundingClientRect().height?r(t):null}})())`));
  const fullyVisible = (b, B) => {
    const bottomLimit = Math.min(B.vh, B.main ? B.main.b : B.vh, B.nav && B.nav.h && B.nav.t > B.vh / 2 ? B.nav.t : B.vh);
    const topLimit = Math.max(0, B.main ? B.main.t : 0);
    return { ok: b.h > 0 && b.t >= topLimit - 0.5 && b.b <= bottomLimit + 0.5, why: b.id + " " + Math.round(b.t) + "-" + Math.round(b.b) + " must fit in " + Math.round(topLimit) + "-" + Math.round(bottomLimit) };
  };
  const allVisible = (label, B) => {
    for (const b of B.btns) { const v = fullyVisible(b, B); check(size + " " + label + ": " + b.id.replace("btn", "") + " button fully visible above the bottom bar", v.ok, v.ok ? "" : v.why); }
    check(size + " " + label + ": the app frame fits the window (nothing of it below the screen)", B.frameBottom <= B.winH + 0.5, Math.round(B.frameBottom) + " vs " + B.winH);
  };
  // a tap at the centre and four points toward the corners of each button reaches it
  const reachable = () => ev(`(()=>{const d=${F},out=[];for(const id of ['btnNo','btnUndo','btnYes']){const e=d.getElementById(id);if(!e){out.push(id+' missing');continue}
    const b=e.getBoundingClientRect();for(const [fx,fy] of [[.5,.5],[.25,.25],[.75,.25],[.25,.75],[.75,.75]]){const h=d.elementFromPoint(b.left+b.width*fx,b.top+b.height*fy);
    if(!h||!(h===e||e.contains(h))){out.push(id+' covered by '+(h?(h.id?'#'+h.id:'')+(typeof h.className==='string'&&h.className?'.'+h.className.split(' ')[0]:'')||h.tagName:'nothing (off screen)'));break}}}return out.join('; ')})()`);
  // card controls on screen that something else (the buttons) lies on
  const cardCovered = () => ev(`(()=>{const d=${F},w=d.defaultView,c=d.querySelector('.card.top');if(!c)return '';const cr=c.getBoundingClientRect(),out=[];
    for(const e of c.querySelectorAll('button,a[href],summary,input,select')){if(!e.offsetParent)continue;const b=e.getBoundingClientRect();if(b.width<4||b.height<4)continue;
      const x=b.left+b.width/2,y=b.top+b.height/2;if(y<Math.max(0,cr.top)||y>Math.min(w.innerHeight,cr.bottom)||x<0||x>w.innerWidth)continue;
      const h=d.elementFromPoint(x,y);if(h&&!(h===e||e.contains(h))&&h.closest('.actions,#bnav'))out.push((e.innerText||e.getAttribute('aria-label')||e.tagName).trim().slice(0,25)+' under '+(h.closest('.actions')?'the buttons':'the bar'))}
    return out.join('; ')})()`);

  await nav("http://127.0.0.1:" + PORT + "/");
  for (let i = 0; i < 30 && !(await ev("!!(" + F + ") && !!(" + F + ").getElementById('btnYes') && !!(" + F + ").querySelector('.card.top')")); i++) await sleep(300);
  await sleep(1200);

  // 1. first open: the agreement box may be up (consentFirst); the buttons must already sit where the visitor will find them
  const consent = await ev("!!(" + F + ").getElementById('kcYes')");
  allVisible("first open" + (consent ? " (agreement box up)" : ""), await boxes());
  // the location card (and the browser's own location prompt) wait for Agree: never two questions at once on first open
  if (consent) { await sleep(2500); check(size + " first open: no location card while the agreement box is up", !(await ev("!!(" + F + ").getElementById('locAsk')"))); }
  if (process.env.SHOTS) await shot(process.env.SHOTS + "-" + size + "-1-first.png");

  // after Agree (the location prompt may appear now): same, and a real tap reaches each button
  if (consent) { await ev("(" + F + ").getElementById('kcYes').click()"); await sleep(900); }
  let B = await boxes();
  allVisible("after Agree", B);
  const cov = await reachable();
  check(size + " after Agree: a tap anywhere on Pass, Undo and Apply reaches the button", !cov, cov);
  if (process.env.SHOTS) await shot(process.env.SHOTS + "-" + size + "-2-agreed.png");

  // 3. the buttons never sit on the card's own controls
  let cc = await cardCovered();
  check(size + " the buttons cover none of the job card's controls on screen", !cc, cc);
  await ev("(()=>{const m=(" + F + ").getElementById('main');m.scrollTop=m.scrollHeight})()"); await sleep(300);
  B = await boxes();
  check(size + " scrolled to the end, the job card ends above the buttons (its last lines can be read and tapped)", !B.card || !B.acts || B.card.b <= B.acts.t + 0.5,
    B.card && B.acts ? "card ends " + Math.round(B.card.b) + ", buttons start " + Math.round(B.acts.t) : "");
  cc = await cardCovered();
  check(size + " scrolled to the end, no card control lies under the buttons", !cc, cc);
  allVisible("scrolled to the end", B);
  await ev("(()=>{const m=(" + F + ").getElementById('main');m.scrollTop=0})()"); await sleep(200);

  // 4. a swipe (Pass, by its button): the message after it stays clear of the buttons and of the bar
  await ev("(" + F + ").getElementById('btnNo').click()"); await sleep(900);
  B = await boxes();
  if (B.toast) {
    const overl = (a, b) => a && b && a.t < b.b - 0.5 && b.t < a.b - 0.5 && a.l < b.r - 0.5 && b.l < a.r - 0.5;
    const hit = B.btns.filter((b) => overl(B.toast, b)).map((b) => b.id);
    check(size + " after a swipe: the message covers none of Pass, Undo, Apply", !hit.length, hit.join(", "));
    check(size + " after a swipe: the message sits above the bottom bar", !B.nav || !B.nav.h || B.toast.b <= B.nav.t + 0.5, Math.round(B.toast.b) + " vs " + Math.round(B.nav && B.nav.t));
  } else check(size + " after a swipe: a message says what happened", false, "no message shown");
  allVisible("after a swipe", B);
  if (process.env.SHOTS) await shot(process.env.SHOTS + "-" + size + "-3-swiped.png");

  console.log(n - bad + " / " + n);
  if (bad) process.exitCode = 1;
};
