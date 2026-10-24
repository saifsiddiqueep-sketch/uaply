// Pass / Undo / Apply always in sight above the bottom bar (Jobs / Job Tracker / Profile), the way a new visitor first sees the app.
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
// Since October 20 (layout pass), also: 2a. on phones the Help button is out of the thumb's path to Apply and lies on nothing in the
// header; 3a. on a short phone, before the deck is scrolled, the card scrolled inside to its own end shows its last line above the
// buttons; 5. with an emulated 34 px bottom safe area the bar keeps clear of it, counted once.
const PORT = process.env.PORT || "8767";
module.exports = async ({ ev, sleep, nav, shot, send }) => {
  // the sign-in gate (October 22, Saif): nobody reaches the jobs without an account, so a fresh test person signs up first (tools/gate-signup.js)
  await require("./gate-signup.js")({ ev, sleep, nav }, "http://127.0.0.1:" + (process.env.PORT || "8767"), "bar");
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

  // 0. the Job Tracker tab (the one-word "Dashboard" became two words on October 21; at 375 px the three tabs share about 340 px):
  //    its label reads exactly "Job Tracker", on one line, and lies inside its tab, which lies inside the bar
  const tab = JSON.parse(await ev(`JSON.stringify((()=>{const d=${F},b=d.getElementById('nb-dash'),s=b&&b.querySelector('span'),nv=d.getElementById('bnav');if(!s||!nv)return null;
    const sr=s.getBoundingClientRect(),br=b.getBoundingClientRect(),nr=nv.getBoundingClientRect(),cs=getComputedStyle(s),lh=parseFloat(cs.lineHeight)||parseFloat(cs.fontSize)*1.15;
    return {text:s.textContent,lines:s.getClientRects().length,h:Math.round(sr.height),lh:Math.round(lh),span:[Math.round(sr.left),Math.round(sr.right)],tab:[Math.round(br.left),Math.round(br.right)],bar:[Math.round(nr.left),Math.round(nr.right)],
      inTab:sr.width>0&&sr.left>=br.left-0.5&&sr.right<=br.right+0.5,inBar:br.left>=nr.left-0.5&&br.right<=nr.right+0.5}})())`));
  check(size + " the bottom bar's tab reads exactly \"Job Tracker\"", !!tab && tab.text === "Job Tracker", JSON.stringify(tab));
  check(size + " ...on one line, not spilling out of its tab, and the tab inside the bar", !!tab && tab.lines === 1 && tab.h <= tab.lh * 1.5 && tab.inTab && tab.inBar, JSON.stringify(tab));

  // 1. first open: the agreement box may be up (consentFirst); the buttons must already sit where the visitor will find them
  const consent = await ev("!!(" + F + ").getElementById('kcYes')");
  allVisible("first open" + (consent ? " (agreement box up)" : ""), await boxes());
  // the location card (and the browser's own location prompt) wait for Agree: never two questions at once on first open
  if (consent) { await sleep(2500); check(size + " first open: no location card while the agreement box is up", !(await ev("!!(" + F + ").getElementById('locAsk')"))); }
  if (process.env.SHOTS) await shot(process.env.SHOTS + "-" + size + "-1-first.png");

  // after Agree (the location prompt may appear now): same, and a real tap reaches each button
  if (consent) { await ev("(" + F + ").querySelectorAll('.kcTick,#kcYes').forEach(c=>{if(c.id==='kcYes'){c.disabled=false;c.click()}else c.checked=true})"); await sleep(900); }
  let B = await boxes();
  allVisible("after Agree", B);
  const cov = await reachable();
  check(size + " after Agree: a tap anywhere on Pass, Undo and Apply reaches the button", !cov, cov);
  if (process.env.SHOTS) await shot(process.env.SHOTS + "-" + size + "-2-agreed.png");

  // 2a. phones: the Help button is out of the thumb's path to Apply (it sat 17 px to the right of Apply at 390x844), and where it sits
  //     now (the right end of the header) it lies on nothing in the header: the brand and the Sign in / account button keep their room
  if (+(process.env.W || 1100) <= 700) {
    const Hp = JSON.parse(await ev(`JSON.stringify((()=>{const d=${F},h=d.getElementById('uaChatBtn');if(!h)return null;const r=e=>{const b=e.getBoundingClientRect();return {l:b.left,r:b.right,t:b.top,b:b.bottom}};
      const hb=r(h),gap=(a,b)=>Math.hypot(Math.max(0,a.l-b.r,b.l-a.r),Math.max(0,a.t-b.b,b.t-a.b));
      const near=Math.round(Math.min(...['btnNo','btnUndo','btnYes'].map(id=>gap(hb,r(d.getElementById(id))))));
      const hdr=d.querySelector('header.bar'),hit=hdr?[...hdr.querySelectorAll('*')].filter(e=>e.offsetParent&&e.getBoundingClientRect().width&&!e.closest('.tabs')).filter(e=>{const b=r(e);return b.l<hb.r-0.5&&hb.l<b.r-0.5&&b.t<hb.b-0.5&&hb.t<b.b-0.5}).map(e=>e.className||e.tagName):[];
      const top=d.elementFromPoint((hb.l+hb.r)/2,(hb.t+hb.b)/2);
      return {near,hit:hit.join(','),own:!!top&&(top===h||h.contains(top)),onScreen:hb.t>=0&&hb.r<=d.defaultView.innerWidth+0.5,hdrRows:hdr?Math.round(hdr.getBoundingClientRect().height):0}})())`));
    if (Hp) {
      check(size + " phone: the Help button is at least 96 px from Pass, Undo and Apply", Hp.near >= 96, "closest " + Hp.near + " px");
      check(size + " phone: the Help button covers nothing in the header, is on screen and a tap on it reaches it", !Hp.hit && Hp.own && Hp.onScreen, (Hp.hit ? "lies on " + Hp.hit + " " : "") + (Hp.own ? "" : "something lies on it ") + (Hp.onScreen ? "" : "off screen"));
      check(size + " phone: the header stays one row with the Help button in it", Hp.hdrRows <= 56, "header " + Hp.hdrRows + " px tall");
    }
  }

  // 2b. on a short phone with the notices and the location card up, the useful top of the card (title, company, pay) shows
  //     above the buttons without scrolling (before: only the card's top edge did, at 375x667)
  if (+(process.env.W || 1100) <= 430 && +(process.env.H || 900) <= 700) {   // short phones only (375x667, 360x640)
    for (let i = 0; i < 12 && !(await ev("!!(" + F + ").getElementById('locAsk')")); i++) await sleep(250);
    const T = JSON.parse(await ev(`JSON.stringify((()=>{const d=${F},m=d.getElementById('main').getBoundingClientRect(),a=d.querySelector('#pane-swipe .actions').getBoundingClientRect(),c=d.querySelector('.card.top');
      const r=s=>{const e=c&&c.querySelector(s);if(!e)return null;const b=e.getBoundingClientRect();return [Math.round(b.top),Math.round(b.bottom)]};
      return {loc:!!d.getElementById('locAsk'),top:Math.round(m.top),lim:Math.round(a.top),h2:r('.chead h2'),co:r('.chead p'),pay:r('.pay')}})())`));
    const inView = (x) => !!x && x[0] >= T.top - 0.5 && x[1] <= T.lim + 0.5;
    check(size + " after Agree" + (T.loc ? " with the location card open" : "") + ": the card's title, company" + (+(process.env.H || 900) < 667 ? "" : " and pay") + " sit above the buttons without scrolling",
      inView(T.h2) && inView(T.co) && (!T.pay || +(process.env.H || 900) < 667 || inView(T.pay)), "title " + T.h2 + ", company " + T.co + ", pay " + T.pay + ", visible " + T.top + "-" + T.lim);
  }

  // 3a. before the deck is scrolled, the row lies over the lower part of the card on a short phone (375x667: about 280 px of it). The
  //     card scrolls inside itself; scrolled to its own end, its last line of text must sit above Pass / Undo / Apply, not under them.
  //     Measured on the text itself (the lowest line box of any shown text in the card), against the top of the row.
  const lastLine = () => ev(`(()=>{const d=${F},c=d.querySelector('.card.top'),a=d.querySelector('#pane-swipe .actions');if(!c||!a)return null;
    c.scrollTop=c.scrollHeight;const ar=a.getBoundingClientRect(),cr=c.getBoundingClientRect(),tw=d.createTreeWalker(c,NodeFilter.SHOW_TEXT);let n,low=-1e9,what='';
    while((n=tw.nextNode())){if(!n.textContent.trim())continue;const p=n.parentElement,s=d.defaultView.getComputedStyle(p);if(!p.offsetParent||s.visibility==='hidden'||+s.opacity===0)continue;
      const rg=d.createRange();rg.selectNodeContents(n);for(const b of rg.getClientRects())if(b.height&&b.bottom>low){low=b.bottom;what=n.textContent.trim().slice(-30)}}
    return JSON.stringify({over:Math.round(cr.bottom-ar.top),low:Math.round(low),row:Math.round(ar.top),what:what,inner:c.scrollHeight>c.clientHeight})})()`);
  await ev("(()=>{const m=(" + F + ").getElementById('main');m.scrollTop=0})()"); await sleep(400);
  const L = JSON.parse((await lastLine()) || "null");
  if (L && +(process.env.H || 900) <= 700) check(size + " not scrolled: the button row lies over the lower part of the card (the next check is not empty here)", L.over > 0, "overlap " + L.over + " px");
  if (L && L.over > 0) check(size + " not scrolled, the card scrolled inside to its end: its last line sits above the buttons", L.low <= L.row + 0.5,
    "last line \"" + L.what + "\" ends " + L.low + ", buttons start " + L.row + " (row over the card by " + L.over + " px)");
  await ev("(()=>{const c=(" + F + ").querySelector('.card.top');if(c)c.scrollTop=0})()"); await sleep(200);

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
  // on a cold start (empty job cache) the release build shows "Finding jobs for you" with Pass disabled for up to a minute: wait for a card
  for (let i = 0; i < 240 && !(await ev("(()=>{const d=" + F + ",b=d.getElementById('btnNo');return !!d.querySelector('.card.top')&&!!b&&!b.disabled})()")); i++) await sleep(250);
  await ev("(" + F + ").getElementById('btnNo').click()");
  for (let w = 0; w < 12; w++) { await sleep(300); B = await boxes(); if (B.toast) break; }   // the message animates in; wait up to 3.6 s for it
  if (B.toast) {
    const overl = (a, b) => a && b && a.t < b.b - 0.5 && b.t < a.b - 0.5 && a.l < b.r - 0.5 && b.l < a.r - 0.5;
    const hit = B.btns.filter((b) => overl(B.toast, b)).map((b) => b.id);
    check(size + " after a swipe: the message covers none of Pass, Undo, Apply", !hit.length, hit.join(", "));
    check(size + " after a swipe: the message sits above the bottom bar", !B.nav || !B.nav.h || B.toast.b <= B.nav.t + 0.5, Math.round(B.toast.b) + " vs " + Math.round(B.nav && B.nav.t));
  } else check(size + " after a swipe: a message says what happened", false, "no message shown");
  allVisible("after a swipe", B);
  if (process.env.SHOTS) await shot(process.env.SHOTS + "-" + size + "-3-swiped.png");

  // 5. phones: a 34 px bottom safe area (an iPhone's home indicator, emulated by Chrome) keeps the bottom bar clear of it, counted once:
  //    the app's frame gets only the part the page around it does not already leave free (the sandbox's app mode pads its stage; before,
  //    that and the frame's own env() added up, 56 px at 390x844). The bar's distance from the screen's bottom must be
  //    max(34, the space below the frame) plus the bar's own lift.
  if (+(process.env.W || 1100) <= 700) {
    const ok = await send("Emulation.setSafeAreaInsetsOverride", { insets: { top: 0, bottom: 34, left: 0, right: 0 } });
    if (ok && ok.error) console.log("NOTE " + size + " this Chrome cannot emulate a safe area (" + ok.error.message + "): check 5 skipped");
    else {
      await nav("http://127.0.0.1:" + PORT + "/");
      for (let i = 0; i < 40 && !(await ev("!!(" + F + ") && !!(" + F + ").getElementById('bnav')")); i++) await sleep(250);
      await sleep(800);
      const S = JSON.parse(await ev(`JSON.stringify((()=>{const d=${F},f=document.querySelector('iframe').getBoundingClientRect(),n=d.getElementById('bnav').getBoundingClientRect();
        const lv=getComputedStyle(d.documentElement).getPropertyValue('--nav-lift').trim(),simple=d.getElementById('bnav').classList.contains('simple');
        return {gap:innerHeight-(f.top+n.bottom),below:innerHeight-f.bottom,lift:lv?parseFloat(lv)||0:1,simple}})())`));
      const want = Math.max(34, S.below) + S.lift;
      if (!S.simple) console.log("NOTE " + size + " the bar has two-line tabs here (the legal links sit below it): check 5 skipped");
      else check(size + " with a 34 px bottom safe area the bar sits clear of it, counted once (" + Math.round(S.gap) + " px from the bottom, want " + Math.round(want) + ")",
        Math.abs(S.gap - want) <= 1.5, "space below the frame " + Math.round(S.below) + ", lift " + S.lift);
      await send("Emulation.setSafeAreaInsetsOverride", { insets: { top: 0, bottom: 0, left: 0, right: 0 } });
    }
  }

  console.log(n - bad + " / " + n);
  if (bad) process.exitCode = 1;
};
