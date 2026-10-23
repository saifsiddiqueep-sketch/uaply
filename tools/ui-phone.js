// The app on a big phone (iPhone 17 Pro Max: 440 x 956, touch), the way a thumb uses it.
//   W=440 H=956 PORT=8767 node tools/cdp.js tools/ui-phone.js
// 1. Every visible button, link, tab and box on every screen (Services, Job Tracker, Profile and each of their pages) can be tapped:
//    nothing covers it (the toast after a swipe, the chat button, a menu) and a real touch on it reaches it.
// 2. Swipes the way people really swipe: straight, a quick short flick, a curved thumb swipe that starts slightly downward,
//    and a vertical scroll that must NOT swipe. Each must do what the person meant.
// 3. The phone walk's fit checks (tools/phone-walk.js FIT) on every screen: no tap target under 44 px (an invisible ::after that widens
//    the finger's target counts, as it does for a finger), nothing running off the right edge, no sideways scrolling, the Help button
//    covering nothing, no dialog taller than the screen with its buttons out of sight.
//    LANDSCAPE=1 W=844 H=390 (or 667x375) checks a phone turned on its side: the same screens, the same checks.
const PORT = process.env.PORT || "8767";
const gateSignup = require("./gate-signup.js");   // the test person signs up first (Saif, October 22: no account, no data)
module.exports = async ({ ev, sleep, nav, send, logs, shot, on }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const FW = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const decisions = () => ev("JSON.stringify(Object.values(" + FW + ".__uaply.S.decisions||{}).reduce((a,d)=>{a[d.s]=(a[d.s]||0)+1;return a},{}))").then(JSON.parse);
  const topKey = () => ev("(()=>{const c=" + F + ".querySelector('.card.top');return c?c.getAttribute('data-id'):'none'})()");

  // a finger: touch events at page coordinates, moved in small steps like a real swipe
  // (each step goes out msPerStep after the last without waiting for Chrome's answer: waiting adds 20 to 40 ms a step, which made
  // the "quick flick" below a slow 200 ms drag)
  const touch = async (points, msPerStep) => {
    const P = [send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: points[0][0], y: points[0][1], id: 1 }] })];
    for (let i = 1; i < points.length; i++) { await sleep(msPerStep); P.push(send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: points[i][0], y: points[i][1], id: 1 }] })); }
    await sleep(Math.min(msPerStep, 10)); P.push(send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] }));
    await Promise.all(P);
  };
  const tap = async (x, y) => { await touch([[x, y]], 0); await sleep(60); };
  // where a thumb would start: a spot on the card that is on screen and not under the bottom bar or a button inside the card
  // (on a short screen the middle of the card can sit under the bottom bar, and a touch there never reaches the card)
  const cardCenter = async () => JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ",c=d.querySelector('.card.top');const f=document.querySelector('iframe').getBoundingClientRect();if(!c)return null;const b=c.getBoundingClientRect();" +
    "for(const fy of [.45,.35,.25,.55,.18,.65])for(const fx of [.5,.3,.7]){const x=b.left+b.width*fx,y=b.top+b.height*fy;if(y<0||y>" + FW + ".innerHeight-4)continue;const h=d.elementFromPoint(x,y);if(h&&h.closest('.card.top')&&!h.closest('button,a,summary,input,select'))return {x:f.left+x,y:f.top+y,w:b.width}}" +
    "return {x:f.left+b.left+b.width/2,y:f.top+b.top+b.height*0.45,w:b.width}})())"));
  // the application requests the page sends (the frame's fetch, wrapped from outside), and links it opens (noted, not opened)
  const watch = () => ev("(()=>{const w=" + FW + ";if(w.__t2)return;w.__t2={apply:[],opens:[]};const f=w.fetch;w.fetch=function(u,o){if(/[/]api[/]apply$/.test(String(u))){try{w.__t2.apply.push(JSON.parse(o.body).job.id)}catch(e){}}return f.apply(this,arguments)};w.__uaplyOpen=function(u){w.__t2.opens.push(String(u))}})()");
  const sentFor = (id) => ev("(" + FW + ".__t2.apply||[]).filter(x=>String(x)===" + JSON.stringify(String(id)) + ").length");
  const opens = () => ev(FW + ".__t2.opens.length");
  const path = (x, y, dx, dy, steps, bend) => {   // bend: how much of the vertical part happens first (a curved thumb path)
    const p = [];
    for (let i = 0; i <= steps; i++) { const t = i / steps; const ty = bend ? Math.min(1, t * 2.5) : t; p.push([x + dx * t, y + dy * ty]); }
    return p;
  };

  if (process.env.LANDSCAPE) {          // a phone turned on its side: wider than the laptop break (700 px), so cdp.js does not make it a phone itself
    await send("Emulation.setDeviceMetricsOverride", { width: +process.env.W, height: +process.env.H, deviceScaleFactor: 3, mobile: true, screenOrientation: { type: "landscapePrimary", angle: 90 } });
    await send("Emulation.setTouchEmulationEnabled", { enabled: true });
  }
  const FIT = require("./phone-walk.js").FIT;
  const fit = async (label) => JSON.parse(await ev("(()=>{const fit=" + FIT + ";return JSON.stringify(fit(" + F + ",''))})()")).map((x) => x.replace(/^: /, ""));
  const fits = [];
  // Google Fonts held back for 8 s (a slow phone connection; 6 to 10 s were seen on October 21): the app must still come up at once, with its
  // bottom bar and the agreement, in the system font. Before, a font stylesheet in the head stopped every script until it arrived.
  await send("Fetch.enable", { patterns: [{ urlPattern: "*fonts.googleapis.com*" }, { urlPattern: "*fonts.gstatic.com*" }] });
  on("Fetch.requestPaused", (p) => { setTimeout(() => send("Fetch.continueRequest", { requestId: p.requestId }), 8000); });
  // the test person signs up first (October 22, Saif: on the sandbox nobody reaches anything without an account; the same everywhere)
  const who = await gateSignup({ ev, sleep, nav: (u) => send("Page.navigate", { url: u }).then(() => sleep(300)) }, "http://127.0.0.1:" + PORT, "phone");
  const su = who.ok ? 200 : 0 || await ev("fetch('/api/auth/signup',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'phonefit.'+Date.now()+'@example.com',password:'Signup-first-99',first:'Test',last:'Person',agree:true,passwordless:false})}).then(r=>r.status)");
  check("0. the test person signs up first (POST /api/auth/signup)", su === 200, su);
  const t0 = Date.now();
  await send("Page.navigate", { url: "http://127.0.0.1:" + PORT + "/" });
  let upAt = 0;
  for (let i = 0; i < 120 && !upAt; i++) { if (await ev("(()=>{const f=document.querySelector('iframe'),d=f&&f.contentDocument;return !!d&&!!d.getElementById('bnav')&&!!d.getElementById('kcYes')})()")) upAt = Date.now() - t0; else await sleep(100); }
  check("with the fonts held back 8 s, the bottom bar and the agreement are up within 4 s (" + (upAt ? (upAt / 1000).toFixed(1) + " s" : "not at all") + ")", upAt > 0 && upAt < 4000);
  await sleep(8500); await send("Fetch.disable");
  // a busy computer can take longer than a few seconds to build the app: wait for its bottom bar and the agreement (at most 30 s)
  for (let i = 0; i < 60 && !(await ev("(()=>{const d=" + F + ";return !!d&&!!d.getElementById('bnav')&&!!d.getElementById('kcYes')})()")); i++) await sleep(500);
  // the agreement's Agree button is on screen without scrolling (on a 692 px tall Galaxy it was 21 px below the bottom edge)
  const agree = JSON.parse(await ev("(()=>{const d=" + F + ",b=d.getElementById('kcYes');if(!b)return 'null';const r=b.getBoundingClientRect();return JSON.stringify({t:Math.round(r.top),b:Math.round(r.bottom),h:d.defaultView.innerHeight})})()"));
  check("the agreement's Agree button is on screen at first open with room below it, nothing to scroll", !!agree && agree.t >= 0 && agree.b <= agree.h - 8, JSON.stringify(agree));
  await ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m)m.click()})()");
  await sleep(1200);
  fits.push(["Jobs at first open, after Agree", await fit("jobs")]);
  if (process.env.LANDSCAPE) {      // turned: the card and Pass / Undo / Apply side by side, the buttons never on top of the card
    const L = JSON.parse(await ev("(()=>{const d=" + F + ",r=s=>{const e=d.querySelector(s);if(!e)return null;const b=e.getBoundingClientRect();return {l:b.left,r:b.right,t:b.top,b:b.bottom}};return JSON.stringify({card:r('.card.top'),acts:r('#pane-swipe .actions'),main:r('#main')})})()"));
    const apart = L.card && L.acts && (L.acts.l >= L.card.r - 1 || L.acts.t >= L.card.b - 1);
    check("turned phone: Pass / Undo / Apply sit beside the card, not on it, and are on screen", apart && L.acts.t >= L.main.t - 1 && L.acts.b <= L.main.b + 1, JSON.stringify(L));
  }

  // ---------------------------------------------------------------- 1. every control can be tapped
  // A control "can be tapped" when the top-most element at its center is the control itself (or inside it).
  const coverage = (label) => ev(`(()=>{const d=${F},w=${FW};const out=[];
    const sel='button,a[href],[role=tab],[role=button],input[type=checkbox],input[type=radio],select,.nitem,.chip,.linkbtn';
    for(const el of d.querySelectorAll(sel)){
      if(!el.offsetParent&&getComputedStyle(el).position!=='fixed')continue;
      if(el.closest('.nmenu')&&el.closest('.nmenu').hidden)continue;      /* inside a closed menu */
      if(el.closest('.card')&&!el.closest('.card.top'))continue;             /* the cards stacked behind the top one are not meant to be tapped */
      if(getComputedStyle(el).visibility!=='visible')continue;
      {const det=el.closest('details:not([open])');if(det&&!el.closest('summary'))continue;}   /* inside a collapsed section, opened by its summary */
      let tgt=el;
      if(el.tagName==='INPUT'){const lab=el.closest('label')||(el.id&&d.querySelector('label[for="'+el.id+'"]'));if(lab)tgt=lab}
      let r=tgt.getBoundingClientRect();if(r.width<4||r.height<4)continue;
      const inline=getComputedStyle(tgt).display==='inline';                  /* a text link can wrap onto two lines: test its first line only */
      tgt.scrollIntoView({block:'center',inline:'nearest'});r=inline?tgt.getClientRects()[0]:tgt.getBoundingClientRect();
      const x=r.left+r.width/2,y=r.top+r.height/2;if(x<0||y<0||x>w.innerWidth||y>w.innerHeight)continue;
      /* the center and four points toward the corners: a button half covered (by the help button, say) is as bad as one fully covered */
      let hit=null;
      for(const [fx,fy] of [[.5,.5],[.2,.3],[.8,.3],[.2,.7],[.8,.7]]){
        const px=r.left+r.width*fx,py=r.top+r.height*fy;if(px<0||py<0||px>=w.innerWidth||py>=w.innerHeight)continue;
        const h=d.elementFromPoint(px,py);if(h&&!(h===tgt||tgt.contains(h)||h.contains(tgt))){hit=h;break}
      }
      if(!hit)continue;
      const name=(tgt.innerText||el.getAttribute('aria-label')||el.id||el.tagName).trim().replace(/\\s+/g,' ').slice(0,30);
      const by=(hit.id?'#'+hit.id:'')+(hit.className&&typeof hit.className==='string'?'.'+hit.className.split(' ')[0]:'')||hit.tagName;
      out.push(name+' (covered by '+by+')');
    }
    return JSON.stringify(out)})()`).then(JSON.parse);

  const screens = [];
  const menu = async (nb, item) => {
    await ev("(()=>{const w=" + F + ".querySelector('.nwrap[data-k=" + nb.replace("nb-", "") + "]');if(!w||w.querySelector('.nb').getAttribute('aria-expanded')!=='true')" + F + ".getElementById('" + nb + "').click()})()"); await sleep(450);
    const ok = await ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.offsetParent&&b.innerText.trim().startsWith(" + JSON.stringify(item) + "));if(!e)return false;const r=e.getBoundingClientRect(),f=document.querySelector('iframe').getBoundingClientRect();window.__tapAt=[f.left+r.left+r.width/2,f.top+r.top+r.height/2];return true})()");
    if (!ok) return false;
    const at = await ev("window.__tapAt");
    await tap(at[0], at[1]); await sleep(700);                                // a real touch on the menu item
    return true;
  };
  const before = await ev("(" + F + ").body.innerText.length");
  const items = { "nb-svc": ["Full-time", "Part-time", "Internships", "Coop"], "nb-dash": ["Overview", "Applied", "Accepted", "Rejected", "Interviews"],
                  "nb-prof": ["Profile setup", "Filters", "Account", "Plan", "Data"] };   // Settings, Resume and Preferences are now steps of Profile setup
  for (const [nb, list] of Object.entries(items)) {
    for (const it of list) {
      const opened = await menu(nb, it);
      // textContent, not innerText: with one-word bottom tabs (simpleTabs, the release build) the open item's name is in the tab's hidden sub-label
      const label = await ev("(()=>{const b=" + F + ".getElementById('" + nb + "');return b?b.textContent.replace(/\\s+/g,' ').trim():''})()");
      const want = it.toLowerCase().slice(0, 4);
      check("tapping " + nb.replace("nb-", "") + " › " + it + " on the phone opens it", opened && label.toLowerCase().includes(want), label);
      screens.push([nb.replace("nb-", "") + " › " + it, await coverage(it)]);
      fits.push([nb.replace("nb-", "") + " › " + it, await fit(it)]);
    }
  }
  // the moment right after a swipe, with its message showing, is when taps most often land on the wrong thing
  await ev(F + ".getElementById('nb-svc').click()"); await sleep(300);
  await menu("nb-svc", "Full-time");
  await ev("(()=>{const m=" + F + ".getElementById('main');if(m)m.scrollTop=0})()");
  await ev(F + ".getElementById('btnNo').click()"); await sleep(900);
  // as the screen is (nothing scrolled first): the message must not lie on Pass, Undo or Apply (it did at 390x844: its Undo link
  // sat on Apply, so tapping Apply right after a pass undid the pass)
  const onBtns = await ev("(()=>{const d=" + F + ";const out=[];for(const id of ['btnNo','btnUndo','btnYes']){const e=d.getElementById(id),r=e.getBoundingClientRect();if(r.bottom>innerHeight||r.top<0)continue;for(const [fx,fy] of [[.5,.5],[.2,.3],[.8,.3],[.2,.7],[.8,.7]]){const h=d.elementFromPoint(r.left+r.width*fx,r.top+r.height*fy);if(h&&!(h===e||e.contains(h))&&h.closest('.toast')){out.push(id);break}}}return out.join(',')})()");
  check("the message after a swipe does not cover Pass, Undo or Apply", onBtns === "", onBtns);
  screens.push(["right after a swipe (message showing)", await coverage("after swipe")]);
  for (const [name, covered] of screens) check("nothing covers a button: " + name, covered.length === 0, covered.slice(0, 4).join("; "));
  for (const [name, list] of fits) check("fits the phone: " + name + " (44 px targets, nothing off the edge, Help covers nothing)", list.length === 0, list.slice(0, 4).join("; "));
  await shot((process.env.OUT || require("os").tmpdir()) + "/phone-after-swipe.png");
  check("the screen changed when menus were tapped (sanity)", (await ev("(" + F + ").body.innerText.length")) !== before);

  // ---------------------------------------------------------------- 2. swipes the way people swipe
  // the least a swipe right needs to apply (October 21): a name, an email and a phone number; without them it opens "Finish your profile first"
  await ev("(()=>{const A=document.querySelector('iframe').contentWindow.__uaply;Object.assign(A.S.profile,{name:'Phone Tester',email:'phone.tester@example.com',custom:true});A.S.profile.ext=Object.assign({},A.S.profile.ext,{phone:'+1 215 555 0100'});A.save();A.renderAll()})()");
  await menu("nb-svc", "Full-time"); await sleep(600);
  const swipe = async (name, dx, dy, steps, ms, bend, expect) => {
    const c = await cardCenter(); if (!c) { check(name, false, "no card"); return; }
    await watch();
    const k0 = await topKey(), d0 = await decisions(), s0 = await sentFor(k0);
    const at = await ev("(()=>{const f=document.querySelector('iframe').getBoundingClientRect();const e=" + F + ".elementFromPoint(" + c.x + "-f.left," + c.y + "-f.top);return e?(e.closest('.card.top')?'card':(e.id||e.className||e.tagName)):'none'})()");
    if (at !== "card") console.log("   (the finger lands on " + at + ", not the card)");
    await touch(path(c.x, c.y, dx, dy, steps, bend), ms); await sleep(1100);
    await ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m)m.click()})()"); await sleep(300);
    await ev("(()=>{const o=" + F + ".getElementById('kitAsk');if(o){const n=" + F + ".getElementById('kaNo');if(n)n.click()}})()"); await sleep(300);
    const d1 = await decisions(), k1 = await topKey();
    // a swipe right counts as understood when it was recorded, or when the application went out for that job even if the employer's
    // form then put it back (the sandbox's example profile has no resume file, and "Not now" above returns the job to the deck)
    const did = (d1.applied || 0) > (d0.applied || 0) || (await sentFor(k0)) > s0 ? "applied" : (d1.passed || 0) > (d0.passed || 0) ? "passed" : (k1 !== k0 ? "moved" : "nothing");
    check(name, did === expect, "did: " + did);
  };
  await ev("(()=>{const d=" + F + ";d.scrollingElement.scrollTop=0;document.scrollingElement.scrollTop=0})()"); await sleep(300);
  // on a short phone the notices above the deck (the location box) leave only the card's top edge between them and Pass / Undo /
  // Apply, which now always stay in sight above the bottom bar: a thumb first scrolls the page to the card, so do the same
  await ev("(()=>{const d=" + F + ",m=d.getElementById('main'),c=d.querySelector('.card.top');if(m&&c)m.scrollTop+=c.getBoundingClientRect().top-m.getBoundingClientRect().top})()"); await sleep(300);
  await swipe("a long straight swipe right applies", 200, 0, 12, 16, false, "applied");
  await swipe("a long straight swipe left passes", -200, 0, 12, 16, false, "passed");
  await swipe("a quick short flick left (80px) passes", -80, 0, 4, 12, false, "passed");
  await swipe("a curved thumb swipe left that starts slightly downward passes", -170, 45, 14, 16, true, "passed");
  await swipe("a curved thumb swipe right that starts slightly upward applies", 170, -45, 14, 16, true, "applied");
  await swipe("a slow, deliberate drag left of half the card passes", -0.5 * (await cardCenter()).w, 10, 30, 25, false, "passed");
  await swipe("a vertical scroll on the card does not swipe", 8, -160, 12, 16, false, "nothing");
  await swipe("a short accidental nudge (25px) does not swipe", 25, 4, 4, 30, false, "nothing");
  const c = await cardCenter(); const k0 = await topKey();
  await tap(c.x, c.y); await sleep(500);
  check("a plain tap on the card does not swipe", (await topKey()) === k0);
  // two fast swipes, the second starting 150 ms after the first lifts (while the first card is still flying off): both count
  {
    const d0 = await decisions(), p = await cardCenter();
    const fast = async () => {                          // events paced like a real finger, without waiting for each answer
      const P = [send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: p.x, y: p.y, id: 1 }] })];
      for (let i = 1; i <= 10; i++) { await sleep(14); P.push(send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: p.x - 20 * i, y: p.y, id: 1 }] })); }
      await sleep(8); P.push(send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] })); await Promise.all(P);
    };
    await fast(); await sleep(150); await fast(); await sleep(1100);
    const d1 = await decisions();
    check("two quick swipes left, 150 ms apart, both pass", (d1.passed || 0) - (d0.passed || 0) === 2, "passed " + ((d1.passed || 0) - (d0.passed || 0)));
  }
  // a swipe that starts on the card's "View original posting" link is a swipe, and does not open the employer's site
  {
    await watch();
    const l = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ",c=d.querySelector('.card.top'),l=c&&c.querySelector('[data-open]');if(!l)return null;l.scrollIntoView({block:'center'});const n=d.getElementById('uaNudge');if(n&&!n.hidden)n.querySelector('.x').click();const f=document.querySelector('iframe').getBoundingClientRect(),r=l.getBoundingClientRect();const h=d.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return h&&l.contains(h)?{x:f.left+r.left+r.width/2,y:f.top+r.top+r.height/2}:null})())"));
    if (l) {
      const d0 = await decisions(), o0 = await opens();
      await touch(path(l.x, l.y, -200, 0, 12, false), 16); await sleep(1100);
      const d1 = await decisions();
      check("a swipe left that starts on the posting link passes and opens nothing", (d1.passed || 0) - (d0.passed || 0) === 1 && (await opens()) === o0, "passed " + ((d1.passed || 0) - (d0.passed || 0)) + ", opened " + ((await opens()) - o0));
      await ev("(()=>{const c=" + F + ".querySelector('.card.top');if(c)c.scrollTop=0})()");
    } else check("the top card has a posting link to swipe from", false);
  }
  // the location card when location is blocked (Galaxy walk, October 22: in the installed app it gave laptop instructions, "the icon at
  // the left of the address bar", and pushed the first job down). On a phone: the phone's settings, two lines and its two buttons, and
  // the first job card starts below it, never under it
  if (!process.env.LANDSCAPE) {
    const origin = "http://127.0.0.1:" + PORT;
    await send("Browser.setPermission", { permission: { name: "geolocation" }, setting: "denied", origin });
    await ev("(()=>{const w=" + FW + ";try{w.localStorage.removeItem(w.__uaplyKey+'.loc')}catch(e){}})()");
    await send("Page.navigate", { url: origin + "/" });
    let la = null;
    for (let i = 0; i < 40 && !la; i++) { await sleep(300); la = await ev("(()=>{try{const d=" + F + ",c=d.getElementById('locAsk');return c&&c.getClientRects().length?1:null}catch(e){return null}})()"); }
    for (let i = 0; i < 40 && la && !(await ev("(()=>{const t=" + F + ".querySelector('.card.top');return !!t&&t.getClientRects().length>0})()")); i++) await sleep(300);   // and the first job card
    const L = la && JSON.parse(await ev("(()=>{const d=" + F + ",w=d.defaultView,c=d.getElementById('locAsk'),p=c.querySelector('p'),cr=c.getBoundingClientRect(),t=d.querySelector('.card.top'),tr=t&&t.getBoundingClientRect(),bs=[...c.querySelectorAll('.acts .btn')].map(b=>b.getBoundingClientRect());" +
      "const lh=parseFloat(w.getComputedStyle(p).lineHeight);return JSON.stringify({title:c.querySelector('b').textContent,text:p.textContent,lines:Math.round(p.getBoundingClientRect().height/lh),clipped:p.scrollHeight>p.clientHeight+1,h:Math.round(cr.height),bottom:Math.round(cr.bottom),cardTop:tr?Math.round(tr.top):null,oneRow:bs.length===2&&Math.abs(bs[0].top-bs[1].top)<2,btnH:bs.map(b=>Math.round(b.height))})})()"));
    check("location blocked, on a phone: the card says to allow it in the phone's settings, then Try again (no address bar)", !!L && /phone's settings/.test(L.text) && /Try again/.test(L.text) && !/address bar/.test(L.text), JSON.stringify(L));
    check("...in two lines of text (nothing cut off) and its two buttons side by side", !!L && L.lines <= 2 && !L.clipped && L.oneRow && L.btnH.every((h) => h >= 44), JSON.stringify(L));
    check("...and the first job card starts below it, never under it", !!L && L.cardTop !== null && L.cardTop >= L.bottom, JSON.stringify(L));
    await send("Browser.resetPermissions", {});
  }
  check("no script errors", logs.length === 0, logs.join(" / ").slice(0, 200));
  console.log(bad ? "\n" + bad + " check(s) failed" : "\nEverything works on the phone");
};
