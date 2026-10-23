// Every kind of swipe a person really makes, by finger, by mouse and by keyboard, and what each one records.
//   W=390 H=844 PORT=8767 node tools/cdp.js tools/ui-swipe-kinds.js      (a phone; also 440x956 and 375x667)
//   W=1280 H=800 PORT=8767 node tools/cdp.js tools/ui-swipe-kinds.js     (a desktop window: mouse drags, arrow keys, and a touch screen)
//   LIMIT_PORT=<port>  also checks a swipe right at the weekly limit, on a server started with the mock Stripe fixture (see
//                      tools/test-billing.py) so plan limits are switched on. It signs up an account there and uses up its 50.
// For every gesture it checks three things: the choice recorded in the app (window.__uaply.S.decisions), whether the top card
// changed, and that no script error happened. A swipe right must also reach the server exactly once (POST /api/apply).
const PORT = process.env.PORT || "8767";
const WIDTH = Number(process.env.W || 1100), PHONE = WIDTH < 700;
module.exports = async ({ ev, sleep, nav, send, logs, shot }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const FW = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const results = [];
  const check = (name, ok, extra) => { if (!ok) bad++; results.push([name, ok]); console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };

  // ------------------------------------------------------------------ what the page records
  // the frame's own fetch is wrapped (from outside, nothing in the app changes) to see each application request and its answer,
  // and links the app opens are noted instead of opened, so no employer site is visited
  const hook = () => ev(`(()=>{const w=${FW};if(!w||w.__t2)return !!w;w.__t2={pending:0,apply:[],opens:[]};
    const f=w.fetch;w.fetch=function(u,o){const s=String(u);if(!/[/]api[/]apply$/.test(s))return f.apply(this,arguments);
      const rec={id:null,status:'',code:0};try{rec.id=JSON.parse(o.body).job.id}catch(e){}w.__t2.apply.push(rec);w.__t2.pending++;
      return f.apply(this,arguments).then(r=>{rec.code=r.status;r.clone().json().then(j=>{rec.status=j.status||j.code||'';w.__t2.pending--},()=>{w.__t2.pending--});return r},e=>{w.__t2.pending--;rec.status='network';throw e})};
    const op=w.__uaplyOpen;w.__uaplyOpen=function(u){w.__t2.opens.push(String(u))};
    w.open=function(u){w.__t2.opens.push(String(u));return null};
    w.document.addEventListener('click',e=>{const a=e.target.closest&&e.target.closest('a[target=_blank]');if(a){e.preventDefault();w.__t2.opens.push(a.href)}},true);
    return true})()`);
  const state = () => ev(`JSON.stringify((()=>{const d=${F},w=${FW},c=d.querySelector('.card.top');const dec={};
    for(const [k,v] of Object.entries(w.__uaply.S.decisions||{}))dec[k]=v.s;
    return {top:c?c.getAttribute('data-id'):'none',dec,consent:!!d.getElementById('kitConsent'),ask:!!d.getElementById('kitAsk'),
      sheet:!!d.getElementById('kitSheet'),paywall:!!d.getElementById('paywall'),opens:w.__t2.opens.length,applies:w.__t2.apply.length,
      scroll:c?c.scrollTop:0,toast:[...d.querySelectorAll('.toast')].map(t=>t.innerText.replace(/\\s+/g,' ')).join(' / ')}})())`).then(JSON.parse);
  const quiet = async () => { for (let i = 0; i < 60; i++) { if ((await ev(FW + ".__t2.pending")) === 0) break; await sleep(250); } await sleep(350); };
  // answer every question on the "questions from <employer>" sheet the way a person would, and send it
  const answerAsk = () => ev(`(()=>{const d=${F},o=d.getElementById('kitAsk');if(!o)return false;
    o.querySelectorAll('[data-k]').forEach(el=>{const q=((o.querySelector('label[for='+el.id+']')||{}).textContent||'').toLowerCase();
      if(el.tagName==='SELECT'){const op=[...el.options].find(x=>x.value||x.textContent!=='Choose');if(op)el.value=op.value||op.textContent}
      else el.value=/zip|postal/.test(q)?'19104':/phone/.test(q)?'+1 215 555 0100':/salary|compensation|pay/.test(q)?'90000':/city|location|where/.test(q)?'Philadelphia, PA':/linkedin/.test(q)?'https://www.linkedin.com/in/sam-rivera':/website|portfolio|github/.test(q)?'https://samrivera.dev':/date|when|start/.test(q)?'2027-01-15':'Yes, I can.';
      el.dispatchEvent(new Event('input',{bubbles:true}))});
    const f=o.querySelector('form');if(f.requestSubmit)f.requestSubmit();else d.getElementById('kaYes').click();return true})()`);
  const agree = () => ev("(()=>{const b=" + F + ".getElementById('kcYes');if(b){b.click();return true}return false})()");
  // after a swipe right: the consent box (first time) is agreed, employer questions are answered, until the request is answered
  const settle = async (o = {}) => {
    for (let i = 0; i < 4; i++) {
      await quiet();
      const s = await state();
      if (s.consent && !o.keepConsent) { await agree(); continue; }
      if (s.ask && !o.keepAsk) {
        if (i > 0) console.log("   (asked again after answering: " + await ev("[...(" + F + ").querySelectorAll('#kitAsk label')].map(l=>l.textContent.slice(0,70)+' = '+((" + F + ").getElementById(l.htmlFor)||{}).value).join(' ; ')") + ")");
        await answerAsk(); continue;
      }
      break;
    }
  };
  // what one gesture did, from two snapshots
  const outcome = (b, a) => {
    const added = Object.keys(a.dec).filter((k) => !(k in b.dec)), gone = Object.keys(b.dec).filter((k) => !(k in a.dec));
    if (!added.length && !gone.length) return a.top === b.top ? "nothing" : "moved without recording (" + b.top + " -> " + a.top + ")";
    if (added.length === 1 && !gone.length && added[0] === b.top) return a.dec[added[0]];
    if (gone.length && !added.length) return "undone " + gone.join(",");
    return "added " + added.map((k) => k + ":" + a.dec[k]).join(",") + (gone.length ? " removed " + gone.join(",") : "");
  };

  // ------------------------------------------------------------------ fingers, mouse and keys (real input events, not element.click())
  const touch = async (points, ms, holdMs) => {
    await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: points[0][0], y: points[0][1], id: 1, radiusX: 8, radiusY: 8, force: 1 }] });
    for (let i = 1; i < points.length; i++) { await send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: points[i][0], y: points[i][1], id: 1, radiusX: 8, radiusY: 8, force: 1 }] }); await sleep(ms); }
    if (holdMs) await sleep(holdMs);
    await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  };
  // a fast finger: the events go out at a steady pace without waiting for each answer (waiting adds 20 to 40 ms a step, which
  // turns a quick flick into a slow drag). About 15 ms a step, like a phone's touch rate.
  const flick = async (points) => {
    const P = [send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: points[0][0], y: points[0][1], id: 1 }] })];
    for (let i = 1; i < points.length; i++) { await sleep(14); P.push(send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: points[i][0], y: points[i][1], id: 1 }] })); }
    await sleep(8); P.push(send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] }));
    await Promise.all(P);
  };
  const mouse = async (points, ms, button = "left") => {
    const bt = button === "left" ? 1 : 2;
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: points[0][0], y: points[0][1] });
    await send("Input.dispatchMouseEvent", { type: "mousePressed", x: points[0][0], y: points[0][1], button, buttons: bt, clickCount: 1 });
    for (let i = 1; i < points.length; i++) { await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: points[i][0], y: points[i][1], button, buttons: bt }); await sleep(ms); }
    const l = points[points.length - 1];
    await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: l[0], y: l[1], button, buttons: 0, clickCount: 1 });
  };
  const KEYS = { ArrowRight: 39, ArrowLeft: 37, z: 90, Escape: 27 };
  const key = async (k) => {
    await send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: k, code: k.length === 1 ? "Key" + k.toUpperCase() : k, windowsVirtualKeyCode: KEYS[k], nativeVirtualKeyCode: KEYS[k] });
    if (k.length === 1) await send("Input.dispatchKeyEvent", { type: "char", key: k, text: k });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code: k.length === 1 ? "Key" + k.toUpperCase() : k, windowsVirtualKeyCode: KEYS[k], nativeVirtualKeyCode: KEYS[k] });
  };
  const line = (x, y, dx, dy, steps) => { const p = []; for (let i = 0; i <= steps; i++) p.push([x + (dx * i) / steps, y + (dy * i) / steps]); return p; };
  // a thumb pivots at its base, so a sideways swipe is an arc: it starts at an angle and flattens out
  const arc = (x, y, dx, dy, steps) => { const p = []; for (let i = 0; i <= steps; i++) { const t = i / steps; p.push([x + dx * t, y + dy * Math.sin(t * Math.PI / 2)]); } return p; };

  // a point on the top card, in page pixels, that is on the card itself (not a button or link inside it) and on screen
  // (with a box open over the deck, the point is where the card is under the box)
  const cardPoint = async () => JSON.parse(await ev(`JSON.stringify((()=>{const d=${F},w=${FW},c=d.querySelector('.card.top');if(!c)return null;
    const f=document.querySelector('iframe').getBoundingClientRect(),b=c.getBoundingClientRect();
    const box=['kitConsent','kitAsk','kitSheet','paywall'].some(i=>d.getElementById(i));
    if(box)return {x:f.left+b.left+b.width/2,y:f.top+b.top+Math.min(b.height*.3,w.innerHeight/3),w:b.width};
    for(const fy of [.3,.22,.4,.16,.5,.6,.12,.7])for(const fx of [.5,.3,.7]){const x=b.left+b.width*fx,y=b.top+b.height*fy;
      if(y<0||y>w.innerHeight-4)continue;const h=d.elementFromPoint(x,y);
      if(h&&h.closest('.card.top')&&!h.closest('button,a,summary,details,input,select,textarea'))return {x:f.left+x,y:f.top+y,w:b.width}}
    return null})())`));
  const linkPoint = async () => {
    const r = JSON.parse(await ev(`JSON.stringify((()=>{const d=${F},c=d.querySelector('.card.top');const l=c&&c.querySelector('[data-open]');if(!l)return {why:'no posting link on card '+(c&&c.getAttribute('data-id'))};
      l.scrollIntoView({block:'center'});const f=document.querySelector('iframe').getBoundingClientRect(),r=l.getBoundingClientRect();
      const h=d.elementFromPoint(r.left+r.width/2,r.top+r.height/2);if(!h||!l.contains(h))return {why:'the link is covered by '+(h&&(h.id||h.className||h.tagName))+' at y '+Math.round(r.top)};
      return {x:f.left+r.left+r.width/2,y:f.top+r.top+r.height/2}})())`));
    if (r.why) { console.log("   (" + r.why + ")"); return null; }
    return r;
  };
  const center = async (sel) => JSON.parse(await ev(`JSON.stringify((()=>{const d=${F},e=d.querySelector(${JSON.stringify(sel)});if(!e)return null;e.scrollIntoView({block:'nearest'});
    const f=document.querySelector('iframe').getBoundingClientRect(),r=e.getBoundingClientRect();return {x:f.left+r.left+r.width/2,y:f.top+r.top+r.height/2}})())`));
  const tapAt = async (p) => { await touch([[p.x, p.y]], 0, 40); };
  const clickAt = async (p) => { await mouse([[p.x, p.y]], 0); };

  // the deck, ready for the next gesture: Services > Full-time, no box open, a card on top, the last swipe finished
  const flags = { nudgeDone: false };
  const ready = async () => {
    await ev(`(()=>{const d=${F};['kitAsk','paywall','kitSheet'].forEach(i=>{const o=d.getElementById(i);if(o)o.remove()});
      const t=d.getElementById('kitToast');if(t)t.remove();
      const n=d.getElementById('uaNudge');if(${flags.nudgeDone}&&n&&!n.hidden)n.querySelector('.x').click();   /* once its own check ran, close it like a person would */
      if(d.getElementById('pane-swipe').hidden||${FW}.__uaply.getType()!=='job'){const w=d.querySelector('.nwrap[data-k=svc]');if(w.querySelector('.nmenu').hidden)d.getElementById('nb-svc').click();const i=w.querySelector('.nitem[data-v=job]');if(i)i.click()}
      const c=d.querySelector('.card.top');if(c)c.scrollTop=0;d.getElementById('main').scrollTop=0})()`);
    await sleep(450);
    if ((await state()).top === "none") { await ev("(()=>{const b=" + F + ".getElementById('resetPassed')||" + F + ".getElementById('showAll');if(b)b.click()})()"); await sleep(500); }
  };
  // one gesture: snapshot, do it, wait, settle, snapshot, compare
  const kind = async (name, gesture, expect, o = {}) => {
    if (!o.noReady) await ready();
    await hook();
    const b = await state(), n0 = logs.length;
    const c = await cardPoint();
    if (!c) { check(name, false, "no card to swipe"); return null; }
    await gesture(c);
    await sleep(o.wait || 900);
    if (!o.noSettle) await settle(o);
    const a = await state();
    const got = outcome(b, a), errs = logs.slice(n0);
    let ok = got === expect && !errs.length;
    let extra = "did: " + got;
    if (o.opens !== undefined) { const op = a.opens - b.opens; ok = ok && op === o.opens; extra += ", links opened: " + op; }
    if (expect === "applied" && !o.noSettle) {       // a swipe right reaches the server once, and the server took it
      const reqs = JSON.parse(await ev("JSON.stringify(" + FW + ".__t2.apply)")).slice(b.applies).filter((r) => String(r.id) === String(b.top));
      const last = reqs[reqs.length - 1] || {};
      const sentOk = reqs.length >= 1 && /^(delivered_test|handoff|sent|duplicate)$/.test(last.status);
      ok = ok && sentOk; extra += ", sent: " + reqs.map((r) => r.status || r.code).join(">");
    }
    if (o.scrolls && a.scroll === b.scroll && o.scrollable) { ok = false; extra += ", the card did not scroll"; }
    if (errs.length) extra += ", errors: " + errs.join(" / ").slice(0, 160);
    check(name, ok, extra);
    return { b, a, got };
  };

  // ------------------------------------------------------------------ start
  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(4500);
  for (let i = 0; i < 40 && !(await hook()); i++) await sleep(250);
  for (let i = 0; i < 40 && (await ev("(" + F + ").querySelectorAll('.card.top').length")) === 0; i++) await sleep(250);
  const sandboxBox = (await state()).consent;          // the sandbox asks for consent before the first swipe; dev on the first swipe right
  // a person who applies has a name, an email and a resume file (employers' Greenhouse forms ask for one; without it the sandbox
  // says "upload your resume" and puts the job back). Set up in Profile setup, the way tools/ui-swipes.js does.
  {
    const setVal = (id, v) => ev("(()=>{const e=" + F + ".getElementById('" + id + "');if(!e)return false;e.value=" + JSON.stringify(v) + ";e.dispatchEvent(new Event('input',{bubbles:true}));return true})()");
    await ev("(()=>{const d=" + F + ";const w=d.querySelector('.nwrap[data-k=prof]');if(w.querySelector('.nmenu').hidden)d.getElementById('nb-prof').click();w.querySelector('.nitem[data-v=settings]').click()})()"); await sleep(700);
    await setVal("pName", "Sam Rivera"); await setVal("pEmail", "sam.kinds@example.com");
    await ev("(" + F + ").getElementById('wzNext').click()"); await sleep(900);
    await ev("(()=>{const b=" + F + ".querySelector('.wzDots button[data-step=\"3\"]');if(b)b.click()})()"); await sleep(600);
    await ev("(()=>{const w=" + FW + ";const i=" + F + ".getElementById('pResFile');const dt=new w.DataTransfer();const bytes=new w.Uint8Array([37,80,68,70,45,49,46,52,10,37,226,227,207,211,10,115,97,109,10,37,37,69,79,70,10]);dt.items.add(new w.File([bytes],'Sam-Rivera-Resume.pdf',{type:'application/pdf'}));i.files=dt.files;i.dispatchEvent(new w.Event('change',{bubbles:true}))})()");
    await sleep(1500);
    await ev("(" + F + ").getElementById('wzNext').click()"); await sleep(900);
    check("set up: the profile has a name, an email and a resume file", !!(await ev("(()=>{const w=" + FW + ";const p=w.__uaply.S.profile;return p.name==='Sam Rivera'&&p.email==='sam.kinds@example.com'&&!!(w.__uaplyResume&&w.__uaplyResume())})()")));
    await ev("(()=>{const d=" + F + ";const w=d.querySelector('.nwrap[data-k=svc]');if(w.querySelector('.nmenu').hidden)d.getElementById('nb-svc').click();w.querySelector('.nitem[data-v=job]').click()})()"); await sleep(800);
  }

  // ---- the consent box
  if (sandboxBox) {
    // a swipe while the box is open must not slip through to the card behind it
    await kind("finger: a swipe right on the consent box (before agreeing) does nothing behind it", (c) => touch(line(c.x, c.y, 200, 0, 12), 16), "nothing", { noReady: true, noSettle: true, keepConsent: true });
    check("the consent box is still open after that swipe", (await state()).consent);
    await kind("keyboard: ArrowRight while the consent box is open does not swipe the card behind it", async () => { await key("ArrowRight"); }, "nothing", { noReady: true, noSettle: true, keepConsent: true });
    check("the consent box is still open after the key", (await state()).consent);
    const p = await center("#kcYes");
    if (PHONE) await tapAt(p); else await clickAt(p);
    await sleep(500);
    check("Agree (real " + (PHONE ? "tap" : "click") + ") closes the consent box", !(await state()).consent);
  } else {
    // dev: the first swipe right opens the box; the job waits for the answer and is sent after Agree
    const r = await kind("finger: the first swipe right opens the consent box", (c) => touch(line(c.x, c.y, 200, 0, 12), 16), "applied", { noSettle: true, wait: 1200 });
    check("the consent box is open", (await state()).consent);
    await hook();
    const b = await state();
    const c = await cardPoint();
    if (c) await touch(line(c.x, c.y, -200, 0, 12), 16);
    await sleep(900);
    let a = await state();
    check("a swipe left on the consent box does nothing behind it", outcome(b, a) === "nothing" && a.consent, "did: " + outcome(b, a));
    await key("ArrowLeft"); await sleep(900); a = await state();
    check("ArrowLeft while the consent box is open does not swipe the card behind it", outcome(b, a) === "nothing" && a.consent, "did: " + outcome(b, a));
    await key("ArrowRight"); await sleep(900); a = await state();
    check("ArrowRight while the consent box is open does not swipe the card behind it", outcome(b, a) === "nothing" && a.consent, "did: " + outcome(b, a));
    const p = await center("#kcYes");
    if (PHONE) await tapAt(p); else await clickAt(p);
    await sleep(400); await settle();
    a = await state();
    const sent = JSON.parse(await ev("JSON.stringify(" + FW + ".__t2.apply)"));
    check("Agree sends the waiting application (once) and keeps it in Applied", r && a.dec[r.b.top] === "applied" && sent.filter((x) => String(x.id) === String(r.b.top)).length === 1 && !a.consent, JSON.stringify(sent).slice(0, 120));
  }

  // ---- by finger (a touch screen on the desktop size too)
  if (!PHONE) await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  const T = "finger: ";
  await kind(T + "a long straight swipe right applies", (c) => touch(line(c.x, c.y, 200, 0, 12), 16), "applied");
  await kind(T + "a long straight swipe left passes", (c) => touch(line(c.x, c.y, -200, 0, 12), 16), "passed");
  await kind(T + "a quick 60px flick right applies", (c) => flick(line(c.x, c.y, 60, 0, 4)), "applied");
  await kind(T + "a quick 60px flick left passes", (c) => flick(line(c.x, c.y, -60, 0, 4)), "passed");
  await kind(T + "a quick 80px flick right applies", (c) => flick(line(c.x, c.y, 80, 0, 5)), "applied");
  await kind(T + "a quick 80px flick left passes", (c) => flick(line(c.x, c.y, -80, 0, 5)), "passed");
  await kind(T + "a quick 40px flick left passes", (c) => flick(line(c.x, c.y, -40, 0, 3)), "passed");
  await kind(T + "a quick 20px twitch does not swipe", (c) => flick(line(c.x, c.y, 20, 0, 2)), "nothing");
  await kind(T + "a curved thumb swipe right (arcs upward) applies", (c) => touch(arc(c.x, c.y, 170, -60, 14), 16), "applied");
  await kind(T + "a curved thumb swipe left (arcs downward) passes", (c) => touch(arc(c.x, c.y, -170, 60, 14), 16), "passed");
  await kind(T + "a steep thumb swipe right (starts at 50 degrees) applies", (c) => touch([[c.x, c.y], [c.x + 6, c.y - 7], [c.x + 14, c.y - 14], [c.x + 40, c.y - 26], [c.x + 90, c.y - 36], [c.x + 150, c.y - 40], [c.x + 190, c.y - 41]], 16), "applied");
  await kind(T + "a slow half-card drag right applies", (c) => touch(line(c.x, c.y, c.w * 0.5, 8, 30), 25), "applied");
  await kind(T + "a slow half-card drag left passes", (c) => touch(line(c.x, c.y, -c.w * 0.5, 8, 30), 25), "passed");
  // the one-tap rating question comes up after the third application; swiping on means "not now", and it must not stay on the card
  {
    let up = false;
    for (let i = 0; i < 14 && !up; i++) { up = await ev("(()=>{const n=" + F + ".getElementById('uaNudge');return !!n&&!n.hidden})()"); if (!up) await sleep(250); }
    if (up) {
      const over = await ev("(()=>{const d=" + F + ",n=d.getElementById('uaNudge').getBoundingClientRect(),c=d.querySelector('.card.top').getBoundingClientRect();return Math.round(Math.max(0,Math.min(n.bottom,c.bottom)-Math.max(n.top,c.top))*Math.max(0,Math.min(n.right,c.right)-Math.max(n.left,c.left))/(c.width*Math.min(c.height,innerHeight))*100)})()");
      console.log("   (the rating question covers " + over + "% of the visible card)");
      await kind(T + "a swipe left while the rating question is up passes, and the question goes away", (c) => touch(line(c.x, c.y, -200, 0, 12), 16), "passed", { noReady: true });
      check(T + "the rating question is gone after that swipe", await ev("(()=>{const n=" + F + ".getElementById('uaNudge');return !n||n.hidden})()"));
    } else console.log("NOTE the rating question did not come up (it shows once in 14 days, after the third application)");
    flags.nudgeDone = true;
  }
  await kind(T + "a slow drag left that comes back to the middle does nothing", (c) => touch(line(c.x, c.y, -120, 0, 10).concat(line(c.x - 120, c.y, 115, 0, 10).slice(1)), 25, 120), "nothing");
  const scrollable = await ev("(()=>{const c=" + F + ".querySelector('.card.top');return !!c&&c.scrollHeight>c.clientHeight+20})()");
  await kind(T + "a vertical scroll on the card does not swipe" + (scrollable ? " (and scrolls the card)" : ""), (c) => touch(line(c.x, c.y + 60, 8, -160, 12), 16), "nothing", { scrolls: true, scrollable });
  await kind(T + "a slightly slanted vertical scroll (30 degrees off) does not swipe", (c) => touch(line(c.x, c.y + 60, -50, -150, 12), 16), "nothing");
  await kind(T + "a tiny 25px nudge does not swipe", (c) => touch(line(c.x, c.y, 25, 4, 4), 30), "nothing");
  await kind(T + "a slow 45px drag does not swipe", (c) => touch(line(c.x, c.y, 45, 0, 9), 40, 150), "nothing");
  await kind(T + "a tap on the card does not swipe", (c) => tapAt(c), "nothing");
  await kind(T + "a long press on the card does not swipe", (c) => touch([[c.x, c.y], [c.x + 1, c.y + 1]], 0, 650), "nothing");
  await kind(T + "two fingers on the card (a pinch) do not swipe", async (c) => {
    await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: c.x - 30, y: c.y, id: 1 }, { x: c.x + 30, y: c.y, id: 2 }] });
    for (let i = 1; i <= 8; i++) { await send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: c.x - 30 - i * 12, y: c.y, id: 1 }, { x: c.x + 30 + i * 12, y: c.y, id: 2 }] }); await sleep(16); }
    await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  }, "nothing");
  // a swipe that starts on the "View original posting" link inside the card is a swipe, and does not open the posting
  await ready();
  if (await linkPoint()) {
    await kind(T + "a swipe left that starts on the card's posting link passes (and opens nothing)", async () => { const l = await linkPoint(); await touch(line(l.x, l.y, -200, 0, 12), 16); }, "passed", { opens: 0 });
    await ready();
    await kind(T + "a tap on the card's posting link opens the posting (and does not swipe)", async () => { const l = await linkPoint(); await tapAt(l); }, "nothing", { opens: 1 });
    await ready();
    await kind(T + "a vertical scroll that starts on the card's posting link opens nothing", async () => { const l = await linkPoint(); await touch(line(l.x, l.y, 4, -120, 10), 16); }, "nothing", { opens: 0 });
  } else check(T + "the top card has a posting link to test", false);
  // two swipes in quick succession: both count, on two different jobs
  // (each swipe is a fast 200px finger, about 150 ms, started at the same spot, the way a thumb goes through a stack)
  for (const gap of [400, 150, 40]) {
    await ready(); await hook();
    const b = await state();
    const c = await cardPoint(); await flick(line(c.x, c.y, -200, 0, 10));
    await sleep(gap);
    await flick(line(c.x, c.y, -200, 0, 10));
    await sleep(1000);
    const a = await state(), added = Object.keys(a.dec).filter((k) => !(k in b.dec));
    check(T + "two quick swipes left, " + gap + " ms apart, pass two different jobs", added.length === 2 && added.every((k) => a.dec[k] === "passed"), added.length + " recorded");
  }
  {
    await ready(); await hook();
    const b = await state();
    const c = await cardPoint(); await flick(line(c.x, c.y, 200, 0, 10));
    await sleep(150);
    await flick(line(c.x, c.y, -200, 0, 10));
    await sleep(1000); await settle();
    const a = await state(), added = Object.keys(a.dec).filter((k) => !(k in b.dec));
    check(T + "a quick swipe right then left records one apply and one pass", added.length === 2 && added.map((k) => a.dec[k]).sort().join() === "applied,passed", added.map((k) => a.dec[k]).join());
  }
  // the Pass, Undo and Apply buttons by finger
  for (const [id, expect] of [["#btnNo", "passed"], ["#btnYes", "applied"]]) {
    await kind(T + "tapping " + (id === "#btnNo" ? "Pass" : "Apply") + " " + expect.replace("ed", "") + "es", async () => tapAt(await center(id)), expect);
  }
  {
    await ready(); const b = await state();
    await tapAt(await center("#btnNo")); await sleep(900);
    const m = await state();
    await tapAt(await center("#btnUndo")); await sleep(800);
    const a = await state();
    check(T + "tapping Undo brings the passed job back", outcome(b, m) === "passed" && a.top === b.top && !(b.top in a.dec), outcome(b, m) + " then top " + a.top);
  }
  // a swipe while the "questions from <employer>" sheet is open must not slip through to the card behind it
  {
    let opened = false;
    for (let i = 0; i < 8 && !opened; i++) {
      await ready(); await hook();
      const c = await cardPoint(); if (!c) break;
      await touch(line(c.x, c.y, 200, 0, 12), 16); await sleep(800); await quiet();
      opened = (await state()).ask;
      if (!opened) await settle();
    }
    if (opened) {
      const b = await state();
      const c = await cardPoint();
      if (c) await touch(line(c.x, c.y, -200, 0, 12), 16);
      await sleep(900); let a = await state();
      check(T + "a swipe on the employer-questions sheet does nothing behind it", outcome(b, a) === "nothing" && a.ask, "did: " + outcome(b, a));
      await ev("(()=>{const b=" + F + ".getElementById('kaNo');if(b)b.focus()})()");
      await key("ArrowRight"); await sleep(900); a = await state();
      check("keyboard: ArrowRight on the employer-questions sheet does not apply to the job behind it", outcome(b, a) === "nothing" && a.ask, "did: " + outcome(b, a));
      await key("ArrowLeft"); await sleep(900); a = await state();
      check("keyboard: ArrowLeft on the employer-questions sheet does not pass the job behind it", outcome(b, a) === "nothing" && a.ask, "did: " + outcome(b, a));
      await answerAsk(); await sleep(600); await settle(); a = await state();
      const reqs = JSON.parse(await ev("JSON.stringify(" + FW + ".__t2.apply)"));
      const last = reqs[reqs.length - 1] || {};
      check(T + "answering the questions sends the application", !a.ask && /^(delivered_test|handoff|sent)$/.test(last.status) && a.dec[String(last.id)] === "applied", "last: " + JSON.stringify(last));
    } else console.log("NOTE no employer-questions sheet came up in 8 swipes right (no Greenhouse form with unanswered questions here); that case was not tested");
  }
  if (!PHONE) await send("Emulation.setTouchEmulationEnabled", { enabled: false });

  // ---- by mouse (every size: a phone with a mouse is rare, a desktop is not)
  const M = "mouse: ";
  if (!PHONE) {
    await kind(M + "a drag right applies", (c) => mouse(line(c.x, c.y, 220, 0, 12), 16), "applied");
    await kind(M + "a drag left passes", (c) => mouse(line(c.x, c.y, -220, 0, 12), 16), "passed");
    await kind(M + "a quick 70px flick left passes", (c) => mouse(line(c.x, c.y, -70, 0, 4), 12), "passed");
    await kind(M + "a short 40px drag does nothing", (c) => mouse(line(c.x, c.y, 40, 0, 6), 30), "nothing");
    await kind(M + "a click on the card does nothing", (c) => clickAt(c), "nothing");
    await kind(M + "a right-button drag does nothing", (c) => mouse(line(c.x, c.y, 220, 0, 12), 16, "right"), "nothing");
    await kind(M + "a mostly vertical drag does nothing", (c) => mouse(line(c.x, c.y, 30, -150, 12), 16), "nothing");
    await kind(M + "the wheel over the card does not swipe", async (c) => { await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: c.x, y: c.y, deltaX: 0, deltaY: 240 }); }, "nothing");
    await ready();
    if (await linkPoint()) {
      await kind(M + "a drag left that starts on the card's posting link passes (and opens nothing)", async () => { const l = await linkPoint(); await mouse(line(l.x, l.y, -220, 0, 12), 16); }, "passed", { opens: 0 });
      await ready();
      await kind(M + "a click on the card's posting link opens the posting", async () => { const l = await linkPoint(); await clickAt(l); }, "nothing", { opens: 1 });
    }
    for (const [id, expect] of [["#btnNo", "passed"], ["#btnYes", "applied"]]) await kind(M + "clicking " + (id === "#btnNo" ? "Pass" : "Apply"), async () => clickAt(await center(id)), expect);
    // keyboard on the desktop: focus the page with a click on the card, then the arrow keys
    const K = "keyboard: ";
    await kind(K + "ArrowRight applies", async (c) => { await clickAt(c); await key("ArrowRight"); }, "applied");
    await kind(K + "ArrowLeft passes", async (c) => { await clickAt(c); await key("ArrowLeft"); }, "passed");
    {
      await ready(); const b = await state(); const c = await cardPoint();
      await clickAt(c); await key("ArrowLeft"); await sleep(800); await key("z"); await sleep(800);
      const a = await state();
      check(K + "Z undoes the last swipe", a.top === b.top && !(b.top in a.dec), "top " + b.top + " -> " + a.top);
    }
    {
      await ready(); const b = await state();
      await clickAt(await center("#btnNo")); await sleep(900); await clickAt(await center("#btnUndo")); await sleep(800);
      const a = await state();
      check(M + "clicking Undo brings the passed job back", a.top === b.top && !(b.top in a.dec));
    }
  }

  // ---- the Remote / Hybrid / On-site chips above the deck, by finger and by mouse
  for (const how of PHONE ? ["tap"] : ["tap", "click"]) {
    if (how === "tap" && !PHONE) await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
    for (const f of ["remote", "hybrid", "onsite", "all"]) {
      await ready();
      const p = await center("#filters button[data-f=" + f + "]");
      if (!p) { check(how + ": the " + f + " chip is there", false); continue; }
      if (how === "tap") await tapAt(p); else await clickAt(p);
      await sleep(500);
      const r = JSON.parse(await ev(`JSON.stringify((()=>{const d=${F},A=${FW}.__uaply;const b=d.querySelector('#filters button[data-f=${f}]');const c=d.querySelector('.card.top');
        const j=c&&A.JOBS.find(x=>String(x.id)===c.getAttribute('data-id'));return {pressed:b.getAttribute('aria-pressed'),filter:A.getFilter(),mode:j?j.mode:'(empty)'}})())`));
      check(how + ": the " + f + " chip filters the deck", r.pressed === "true" && r.filter === f && (f === "all" || r.mode === f || r.mode === "(empty)"), JSON.stringify(r));
    }
    if (how === "tap" && !PHONE) await send("Emulation.setTouchEmulationEnabled", { enabled: false });
  }

  // ---- a swipe right at the weekly limit (a server with plan limits switched on)
  if (process.env.LIMIT_PORT) {
    const LP = process.env.LIMIT_PORT, EM = "limit." + Date.now() + "@example.com";
    await nav("http://127.0.0.1:" + LP + "/"); await sleep(4000);
    const su = await ev("fetch('/api/auth/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'" + EM + "',password:'limit test 12345',agree:true})}).then(r=>r.status)");
    const code = await ev("fetch('/outbox').then(r=>r.text()).then(t=>{const m=t.match(/([0-9]{6}) is your UAply (?:verification|sign-in) code/);return m?m[1]:''})");
    const vf = await ev("fetch('/api/auth/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:'" + code + "'})}).then(r=>r.status)");
    check("limit server: a test account is signed up and verified", su === 200 && vf === 200, su + "/" + vf);
    // use up the 50 applications of the Free plan with example jobs (40 a minute is the server's swipe limit, so in two batches)
    let used = 0;
    for (let i = 0; i < 50; i++) {
      if (i === 39) await sleep(61000);
      const st = await ev("fetch('/api/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({consent:true,match:50,note:'',job:{id:" + (900000 + i) + ",co:'Limit Co " + i + "',role:'Tester',url:'https://example.com/x" + i + "',loc:'Remote',mode:'remote',type:'job',sal:[0,0],blurb:'x'},profile:{name:'Limit Test',email:'" + EM + "',title:'',years:0,skills:[],loc:'',edu:'',ext:{}}})}).then(r=>r.json()).then(j=>j.status||j.code)");
      if (st === "delivered_test") used++;
    }
    const bs = JSON.parse(await ev("fetch('/api/billing/status').then(r=>r.text())"));
    check("limit server: the account has used its 50 applications this week", bs.used >= 50 && bs.cap === 50, "used " + bs.used + " of " + bs.cap + " (" + used + " sent now)");
    await nav("http://127.0.0.1:" + LP + "/"); await sleep(4500);
    await agree(); await sleep(300);
    // the profile email must be the account's so the request is counted against it
    await ev("(()=>{const A=" + FW + ".__uaply;A.S.profile.name='Limit Test';A.S.profile.email='" + EM + "';A.save();A.renderAll()})()");
    if (!PHONE) await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
    const r = await kind("finger: a swipe right at the weekly limit does not apply, and the job stays in the deck", (c) => touch(line(c.x, c.y, 200, 0, 12), 16), "nothing", { wait: 1500 });
    const s = await state();
    check("at the limit the person is told why and offered the plans", /used your 50 applications/.test(s.toast) && /See plans/.test(s.toast), s.toast.slice(0, 160));
    const p = await ev("(()=>{const b=[...(" + F + ").querySelectorAll('#kitToast button')].find(x=>/See plans/.test(x.textContent));if(!b)return null;const f=document.querySelector('iframe').getBoundingClientRect(),q=b.getBoundingClientRect();return JSON.stringify({x:f.left+q.left+q.width/2,y:f.top+q.top+q.height/2})})()");
    if (p) { await tapAt(JSON.parse(p)); await sleep(800); }
    check("tapping See plans opens Plan & billing", /Plan/.test(await ev("(" + F + ").getElementById('nb-prof').innerText")) && !(await ev("(" + F + ").getElementById('pane-swipe').hidden===false")), await ev("(" + F + ").getElementById('nb-prof').innerText.replace(/\\s+/g,' ')"));
    if (!PHONE) await send("Emulation.setTouchEmulationEnabled", { enabled: false });
    void r;
  }

  if (process.env.OUT) await shot(process.env.OUT + "/swipe-kinds-" + WIDTH + ".png");
  check("no script errors in the whole run", logs.length === 0, logs.join(" / ").slice(0, 200));
  console.log("\n" + results.filter((r) => r[1]).length + " of " + results.length + " checks passed" + (bad ? "; " + bad + " failed" : ""));
};
