// The app on a big phone (iPhone 17 Pro Max: 440 x 956, touch), the way a thumb uses it.
//   W=440 H=956 PORT=8767 node tools/cdp.js tools/ui-phone.js
// 1. Every visible button, link, tab and box on every screen (Services, Dashboard, Profile and each of their pages) can be tapped:
//    nothing covers it (the toast after a swipe, the chat button, a menu) and a real touch on it reaches it.
// 2. Swipes the way people really swipe: straight, a quick short flick, a curved thumb swipe that starts slightly downward,
//    and a vertical scroll that must NOT swipe. Each must do what the person meant.
const PORT = process.env.PORT || "8767";
module.exports = async ({ ev, sleep, nav, send, logs, shot }) => {
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

  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(4500);
  await ev("(()=>{const m=" + F + ".getElementById('kcYes');if(m)m.click()})()");

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
  await shot((process.env.OUT || require("os").tmpdir()) + "/phone-after-swipe.png");
  check("the screen changed when menus were tapped (sanity)", (await ev("(" + F + ").body.innerText.length")) !== before);

  // ---------------------------------------------------------------- 2. swipes the way people swipe
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
  check("no script errors", logs.length === 0, logs.join(" / ").slice(0, 200));
  console.log(bad ? "\n" + bad + " check(s) failed" : "\nEverything works on the phone");
};
