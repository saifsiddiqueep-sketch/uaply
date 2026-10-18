// Every button, link, tab, chip, checkbox, select, box and form on every screen, pressed by a real mouse click and by a real
// finger tap (Chrome input events, not element.click()), on dev or the sandbox, at any size.
//   W=390 H=844 PORT=8767 CDP_LIMIT_MS=3600000 node tools/cdp.js tools/ui-controls.js
//   HOW=mouse or HOW=touch   one way only (default: both)        ONLY=<regex>   only the screens whose name matches
//   OUT=<folder>             also saves a screenshot of every screen there
// For each control it checks:
//   - a finger or the mouse can reach it: nothing covers it at the spot pressed (the bottom bar, the help button, a toast...)
//   - pressing it does something you can see: the page changed, a value toggled, a field took the focus and the typing, a link
//     or download or file picker or email opened, or the clipboard got text; or it is inert on purpose (disabled, already chosen)
//   - no script error
// Screens: the three bottom menus and every item in them, the header (Sign in, Switch to hiring, the logo), the help button
// and its panel, the footer links, the consent box, the message after a swipe, every Dashboard list (with applications in
// each status), the five Profile setup steps, Filters, Account (signed out and signed in), Plan & billing, Data & privacy,
// and in the sandbox the employer-questions box and every Hiring mode screen (with a test account it creates on this server).
// Links that would leave the app (employer sites, legal pages, mail) are noted instead of opened; the legal and help pages on
// this server are then fetched to check they answer 200.
const fs = require("fs");
const pathm = require("path");
const PORT = process.env.PORT || "8767";
const BASE = "http://127.0.0.1:" + PORT + "/";
const WIDTH = Number(process.env.W || 1100), PHONE = WIDTH < 700;
const HOW = (process.env.HOW || "mouse,touch").split(",");
const ONLY = process.env.ONLY ? new RegExp(process.env.ONLY, "i") : null;
module.exports = async ({ ev, sleep, nav, send, logs, shot, on }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const FW = "document.querySelector('iframe').contentWindow";
  let bad = 0, good = 0;
  const table = [];
  const report = (screen, ctl, how, ok, res) => {
    if (ok) good++; else bad++;
    table.push({ screen, ctl, how, ok, res });
    console.log((ok ? "PASS " : "FAIL ") + screen + " › " + ctl + " (" + how + "): " + res);
  };
  const check = (name, ok, extra) => { if (ok) good++; else bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };

  // ------------------------------------------------------------------ what leaves the page is noted, not followed
  let choosers = 0, dialogs = 0;
  await send("Page.setInterceptFileChooserDialog", { enabled: true });
  on("Page.fileChooserOpened", () => { choosers++; });
  on("Page.javascriptDialogOpening", () => { dialogs++; send("Page.handleJavaScriptDialog", { accept: false }); });
  await send("Page.setDownloadBehavior", { behavior: "deny" });
  const hook = () => ev(`(()=>{const w=${FW};if(!w||!w.document||!w.document.body)return false;if(w.__t3)return true;const d=w.document;
    w.__t3={opens:[],downloads:[],mail:0,clip:0};
    w.__uaplyOpen=function(u){w.__t3.opens.push(String(u))};w.open=function(u){w.__t3.opens.push(String(u));return null};
    const leave=a=>{const h=a.getAttribute('href')||'';if(a.hasAttribute('download')){w.__t3.downloads.push(a.download||'file');return true}
      if(/^mailto:/i.test(h)){w.__t3.mail++;return true}if(/^#/.test(h))return false;w.__t3.opens.push(a.href);return true};
    d.addEventListener('click',e=>{const a=e.target.closest&&e.target.closest('a[href]');if(a&&leave(a))e.preventDefault()},true);
    const ac=w.HTMLAnchorElement.prototype.click;w.HTMLAnchorElement.prototype.click=function(){if(!this.isConnected&&!this.hasAttribute('download')&&!/^mailto:/i.test(this.href)&&this.target!=='_blank')return ac.call(this);if(leave(this))return;return ac.call(this)};
    try{const c=w.navigator.clipboard;if(c)c.writeText=function(){w.__t3.clip++;return Promise.resolve()}}catch(e){}
    try{const ex=d.execCommand.bind(d);d.execCommand=function(c){if(c==='copy'){w.__t3.clip++;return true}return ex.apply(d,arguments)}}catch(e){}
    return true})()`);
  const counters = async () => JSON.parse(await ev(`JSON.stringify((()=>{const t=(${FW}||{}).__t3||{opens:[],downloads:[]};return {o:t.opens.length,dl:t.downloads.length,m:t.mail,c:t.clip}})())`));

  // ------------------------------------------------------------------ the page's state, as one fingerprint
  // (the page's HTML, every field's value, and what left the page; not the focus, which every press moves)
  const sig = () => ev(`(()=>{const d=${F},w=${FW};const h=x=>{let a=7;for(let i=0;i<x.length;i++)a=(a*31+x.charCodeAt(i))|0;return a};
    let s=h(d.body.innerHTML.replace(/ style="[^"]*animation[^"]*"/g,''))+'|';
    d.querySelectorAll('input,select,textarea').forEach(e=>{s+=(e.type==='checkbox'||e.type==='radio')?(e.checked?1:0):h(String(e.value))});
    const t=w.__t3||{opens:[],downloads:[]};s+='|'+t.opens.length+','+t.downloads.length+','+t.mail+','+t.clip;
    const tb=document.querySelector('.top');s+='|'+(tb?h(tb.innerHTML):0)+'|'+(document.getElementById('stage')||{}).className;
    return s})()`);
  const stable = async () => { let a = await sig(); for (let i = 0; i < 8; i++) { await sleep(200); const b = await sig(); if (a === b) return a; a = b; } return a; };
  // which screen is showing: the menu labels, the visible pane, Hiring mode and its view, open boxes, the help panel, the setup step
  const screenId = () => ev(`(()=>{const d=${F};if(!d||!d.body)return 'none';const t=x=>{const e=d.getElementById(x);return e?e.innerText.replace(/\\s+/g,' ').trim():''};
    const panes=[...d.querySelectorAll('main > section, #hub')].filter(e=>!e.hidden).map(e=>e.id).join(',');
    const hv=d.querySelector('.hnav [aria-current]');const st=d.querySelector('.wzDots [aria-current]');
    const boxes=['kitConsent','kitAsk','kitSheet','paywall','stConfirm'].filter(i=>d.getElementById(i)).join(',');
    const chat=d.getElementById('uaChat');const menus=[...d.querySelectorAll('.nmenu')].filter(m=>!m.hidden).length;
    return [t('nb-svc'),t('nb-dash'),t('nb-prof'),panes,d.body.classList.contains('hire'),hv?hv.getAttribute('data-view'):'',st?st.getAttribute('aria-label'):'',boxes,chat&&!chat.hidden,menus].join('|')})()`);

  // ------------------------------------------------------------------ real input
  const clickAt = async (p) => {
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: p.x, y: p.y });
    await send("Input.dispatchMouseEvent", { type: "mousePressed", x: p.x, y: p.y, button: "left", buttons: 1, clickCount: 1 });
    await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: p.x, y: p.y, button: "left", buttons: 0, clickCount: 1 });
  };
  const tapAt = async (p) => {
    await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: p.x, y: p.y, id: 1, radiusX: 6, radiusY: 6, force: 1 }] });
    await sleep(50);
    await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  };
  const KC = { ArrowDown: 40, ArrowRight: 39, Escape: 27, Tab: 9 };
  const key = async (k) => {
    await send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: k, code: k, windowsVirtualKeyCode: KC[k], nativeVirtualKeyCode: KC[k] });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code: k, windowsVirtualKeyCode: KC[k], nativeVirtualKeyCode: KC[k] });
  };

  // ------------------------------------------------------------------ controls on a screen
  // root: a CSS selector for the part of the page that belongs to this screen (the bottom bar, header and footer are their own screen)
  const SEL = "button,a[href],[role=tab],[role=button],[role=link],input,select,textarea,summary";
  const enumerate = (root) => ev(`JSON.stringify((()=>{const d=${F};const roots=[...d.querySelectorAll(${JSON.stringify(root)})];const seen={},out=[];
    for(const r of roots)for(const el of [r,...r.querySelectorAll(${JSON.stringify(SEL)})]){
      if(!el.matches(${JSON.stringify(SEL)}))continue;
      if(el.closest('[hidden]'))continue;if(el.closest('.card')&&!el.closest('.card.top'))continue;
      const det=el.closest('details:not([open])');if(det&&!el.closest('summary'))continue;
      if(el.type==='hidden')continue;
      const cs=getComputedStyle(el);if(cs.visibility!=='visible'||cs.display==='none')continue;
      let tgt=el;if(el.tagName==='INPUT'&&(el.type==='checkbox'||el.type==='radio'||el.type==='file')){const r0=el.getBoundingClientRect();if(r0.width<4||r0.height<4||cs.opacity==='0'){const lab=el.closest('label')||(el.id&&d.querySelector('label[for="'+el.id+'"]'));if(lab)tgt=lab}}
      const rr=tgt.getBoundingClientRect();if(rr.width<4||rr.height<4)continue;
      const data=[...el.attributes].filter(a=>/^data-|^id$|^name$|^type$/.test(a.name)&&!/^data-t3/.test(a.name)&&!/^data-sure/.test(a.name)).map(a=>a.name+'='+a.value).sort().join(';');
      const label=(el.getAttribute('aria-label')||el.innerText||el.value||el.placeholder||el.title||el.id||el.tagName).trim().replace(/\\s+/g,' ').slice(0,48);
      const base=el.tagName+'|'+data+'|'+(el.tagName==='INPUT'||el.tagName==='SELECT'||el.tagName==='TEXTAREA'?'':label);
      seen[base]=(seen[base]||0)+1;out.push({key:base+'#'+seen[base],label:label||el.tagName.toLowerCase(),kind:el.tagName==='INPUT'?'input:'+el.type:el.tagName.toLowerCase()});
    }return out})())`).then(JSON.parse);
  // finds the control again (the screen may have been redrawn), scrolls it into view, and says where to press and what covers it
  const locate = (root, k) => ev(`JSON.stringify((()=>{const d=${F},w=${FW};const roots=[...d.querySelectorAll(${JSON.stringify(root)})];const seen={};
    for(const r of roots)for(const el of [r,...r.querySelectorAll(${JSON.stringify(SEL)})]){
      if(!el.matches(${JSON.stringify(SEL)}))continue;
      if(el.closest('[hidden]'))continue;if(el.closest('.card')&&!el.closest('.card.top'))continue;
      const det=el.closest('details:not([open])');if(det&&!el.closest('summary'))continue;if(el.type==='hidden')continue;
      const cs=getComputedStyle(el);if(cs.visibility!=='visible'||cs.display==='none')continue;
      let tgt=el;if(el.tagName==='INPUT'&&(el.type==='checkbox'||el.type==='radio'||el.type==='file')){const r0=el.getBoundingClientRect();if(r0.width<4||r0.height<4||cs.opacity==='0'){const lab=el.closest('label')||(el.id&&d.querySelector('label[for="'+el.id+'"]'));if(lab)tgt=lab}}
      const rr=tgt.getBoundingClientRect();if(rr.width<4||rr.height<4)continue;
      const data=[...el.attributes].filter(a=>/^data-|^id$|^name$|^type$/.test(a.name)&&!/^data-t3/.test(a.name)&&!/^data-sure/.test(a.name)).map(a=>a.name+'='+a.value).sort().join(';');
      const label=(el.getAttribute('aria-label')||el.innerText||el.value||el.placeholder||el.title||el.id||el.tagName).trim().replace(/\\s+/g,' ').slice(0,48);
      const base=el.tagName+'|'+data+'|'+(el.tagName==='INPUT'||el.tagName==='SELECT'||el.tagName==='TEXTAREA'?'':label);
      seen[base]=(seen[base]||0)+1;if(base+'#'+seen[base]!==${JSON.stringify(k)})continue;
      d.querySelectorAll('[data-t3x]').forEach(x=>x.removeAttribute('data-t3x'));el.setAttribute('data-t3x','1');
      tgt.scrollIntoView({block:'center',inline:'nearest'});
      const inline=getComputedStyle(tgt).display==='inline';const r=inline?tgt.getClientRects()[0]:tgt.getBoundingClientRect();
      const f=document.querySelector('iframe').getBoundingClientRect();
      const x=Math.max(r.left+2,Math.min(r.right-2,r.left+r.width/2)),y=r.top+r.height/2;
      if(x<0||y<0||x>w.innerWidth||y>w.innerHeight)return {off:true,label};
      const h=d.elementFromPoint(x,y);
      const lab=el.labels&&el.labels[0];
      const okHit=h&&(h===el||el.contains(h)||h===tgt||tgt.contains(h)||(lab&&(h===lab||lab.contains(h))));
      const cover=okHit?'':(h?((h.id?'#'+h.id:'')+(typeof h.className==='string'&&h.className?'.'+h.className.split(' ')[0]:'')||h.tagName)+' "'+(h.innerText||'').trim().slice(0,30)+'"':'nothing');
      const sel=el.getAttribute('aria-pressed')==='true'||el.getAttribute('aria-current')==='true'||el.getAttribute('aria-current')==='page'||el.getAttribute('aria-current')==='step'||el.getAttribute('aria-selected')==='true'||el.getAttribute('aria-checked')==='true';
      return {x:f.left+x,y:f.top+y,cover,disabled:!!el.disabled||el.getAttribute('aria-disabled')==='true',readonly:!!el.readOnly,selected:sel,tag:el.tagName,type:el.type||'',value:el.value,label};
    }return null})())`).then(JSON.parse);
  const ctlState = () => ev(`JSON.stringify((()=>{const d=${F};const e=d.querySelector('[data-t3x]');if(!e)return {gone:true};return {focused:d.activeElement===e,value:e.value,checked:!!e.checked}})())`).then(JSON.parse);

  // ------------------------------------------------------------------ screens
  const menu = (k, v) => ev(`(()=>{const d=${F};if(d.body.classList.contains('hire')){const s=d.getElementById('modeSw');if(s)s.click()}
    const w=d.querySelector('.nwrap[data-k=${k}]');if(w.querySelector('.nmenu').hidden)d.getElementById('nb-${k}').click();const i=w.querySelector('.nitem[data-v=${v}]');if(i){i.click();return true}return false})()`);
  const closeAll = async () => {
    await ev(`(()=>{const d=${F};if(!d)return;const c=d.getElementById('uaChat');if(c&&!c.hidden){const x=c.querySelector('[data-x],.x,#uaChatClose,[aria-label=Close]');if(x)x.click()}
      ['kitAsk','paywall','kitSheet'].forEach(i=>{const o=d.getElementById(i);if(o)o.remove()});
      const n=d.getElementById('uaNudge');if(n&&!n.hidden)n.querySelector('.x').click();
      d.querySelectorAll('.nmenu').forEach(m=>{if(!m.hidden){m.hidden=true;const b=m.parentNode.querySelector('.nb');if(b)b.setAttribute('aria-expanded','false')}});
      const t=d.getElementById('kitToast');if(t)t.remove();const th=d.getElementById('toastHost');if(th)th.innerHTML=''})()`);
  };
  const openDetails = (root) => ev(`(()=>{const d=${F};d.querySelectorAll(${JSON.stringify(root)}).forEach(r=>r.querySelectorAll('details').forEach(x=>{if(!x.open&&!x.classList.contains('mgr'))x.open=true}))})()`);
  const waitFrame = async () => { for (let i = 0; i < 60; i++) { if (await hook()) { if (await ev("!!(" + FW + ".__uaply)")) return true; } await sleep(250); } return false; };
  const reload = async () => { await nav(BASE); await waitFrame(); await sleep(1500); await hook(); };
  const NOTES = [];

  // makes sure the Dashboard lists have something in every status (applied, interview, accepted, rejected, passed)
  const seed = () => ev(`(()=>{const A=${FW}.__uaply;const want={applied:3,interview:2,accepted:2,rejected:2,passed:2};const have={};
    for(const [k,x] of Object.entries(A.S.decisions)){const st=x.s==='passed'?'passed':(x.st||'applied');have[st]=(have[st]||0)+1}
    const free=A.JOBS.filter(j=>j.live&&!A.S.decisions[j.id]);let n=0;
    for(const [st,c] of Object.entries(want))for(let i=have[st]||0;i<c;i++){const j=free[n++];if(!j)break;A.S.decisions[j.id]={s:st==='passed'?'passed':'applied',st:st==='passed'?'applied':st,at:Date.now()-n*3600e3,pct:70,as:'Sam Rivera',title:''};A.S.history.push(j.id)}
    A.save();A.renderAll();return n})()`);

  const SCREENS = [];
  const add = (name, root, open, o = {}) => SCREENS.push(Object.assign({ name, root, open }, o));
  const svc = [["job", "Full-time"], ["parttime", "Part-time"], ["internship", "Internships"], ["coop", "Coop"]];
  for (const [v, l] of svc) add("Services › " + l, "#pane-swipe", async () => { await menu("svc", v); }, { reset: () => ev("(()=>{const A=" + FW + ".__uaply;if(A.getFilter()!=='all')A.setFilter('all')})()") });
  add("Message after a swipe", "#toastHost,#kitToast", async () => { await menu("svc", "job"); await sleep(300); await ev("(" + F + ").getElementById('btnNo').click()"); await sleep(700); }, { fresh: true });
  for (const [v, l] of [["overview", "Overview"], ["applied", "Applied"], ["interview", "Interviews"], ["accepted", "Accepted"], ["rejected", "Rejected"]])
    add("Dashboard › " + l, "#pane-track", async () => { await seed(); await menu("dash", v); });
  for (let i = 0; i < 5; i++) add("Profile setup › step " + (i + 1), "#pane-profile", async () => { await menu("prof", "settings"); await sleep(300); await ev("(()=>{const b=" + F + ".querySelector('.wzDots button[data-step=\"" + i + "\"]');if(b)b.click()})()"); });
  add("Profile › Filters", "main > section:not([hidden])", async () => { await menu("prof", "filters"); }, { details: true });
  add("Profile › Account", "main > section:not([hidden])", async () => { await menu("prof", "account"); }, { details: true });
  add("Profile › Plan & billing", "main > section:not([hidden])", async () => { await menu("prof", "plan"); });
  add("Profile › Data & privacy", "main > section:not([hidden])", async () => { await menu("prof", "data"); }, { fresh: true });
  add("Help panel", "#uaChat", async () => { await menu("svc", "job"); await sleep(200); await ev("(" + F + ").getElementById('uaChatBtn').click()"); }, { fresh: true });

  // ------------------------------------------------------------------ press one control one way, and judge
  const pressOne = async (S, c, how) => {
    if (!(await hook())) await waitFrame();
    if (S.fresh || (await screenId()) !== S.id) { await closeAll(); await S.open(); await sleep(500); if (S.details) await openDetails(S.root); S.id = await screenId(); }
    // a box that arrived late from an earlier press (the employer-questions box comes a few seconds after Apply) is not this screen's
    if (!/kitAsk|kitConsent/.test(S.root) && (await ev("!!(" + F + ".getElementById('kitAsk')||" + F + ".getElementById('kitConsent'))"))) {
      await ev("(()=>{const d=" + F + ";['kitAsk','kitConsent'].forEach(i=>{const o=d.getElementById(i);if(o)o.remove()})})()"); S.id = "";
      await closeAll(); await S.open(); await sleep(500); if (S.details) await openDetails(S.root); S.id = await screenId();
    }
    if (S.reset) { await S.reset(); await sleep(150); }      // e.g. the work-style chip back to All, so each press starts the same
    const p = await locate(S.root, c.key);
    if (!p) { report(S.name, c.label, how, true, "not shown in this state (left alone)"); return; }
    if (p.off) { report(S.name, c.label, how, false, "cannot be scrolled into view"); return; }
    if (p.disabled) { report(S.name, c.label, how, true, "inert: disabled"); return; }
    if (p.cover) { report(S.name, c.label, how, false, "covered by " + p.cover + " (a " + (how === "touch" ? "tap" : "click") + " there lands on it)"); return; }
    const s0 = await stable(), id0 = await screenId(), k0 = await counters(), ch0 = choosers, dg0 = dialogs, n0 = logs.length;
    const st0 = await ctlState();
    if (how === "touch") await tapAt(p); else await clickAt(p);
    let res = "", ok = false;
    const field = p.tag === "TEXTAREA" || (p.tag === "INPUT" && !/^(checkbox|radio|file|range|button|submit|color)$/.test(p.type));
    if (p.tag === "INPUT" && p.type === "file") {
      for (let i = 0; i < 8 && choosers === ch0; i++) await sleep(100);
      ok = choosers > ch0; res = ok ? "opens the file picker" : "no file picker";
    } else if (field) {
      await sleep(150);
      const st = await ctlState();
      if (!st.focused) { res = "does not take the focus"; }
      else if (p.readonly) { ok = true; res = "takes the focus (read-only)"; }
      else {
        await send("Input.insertText", { text: "7" }); await sleep(150);
        const st2 = await ctlState();
        ok = st2.value !== st.value; res = ok ? "takes the focus and the typing" : "takes the focus but not the typing";
        await ev(`(()=>{const e=${F}.querySelector('[data-t3x]');if(e){e.value=${JSON.stringify(st0.value || "")};e.dispatchEvent(new Event('input',{bubbles:true}))}})()`);
      }
    } else if (p.tag === "SELECT" || (p.tag === "INPUT" && p.type === "range")) {
      await sleep(200);
      if (p.tag === "SELECT") await key("Escape");                 // a click opens the list; close it, then choose with the keyboard
      const st = await ctlState();
      await key(p.tag === "SELECT" ? "ArrowDown" : "ArrowRight"); await sleep(250);
      const st2 = await ctlState();
      ok = st.focused && (st2.value !== st0.value);
      res = !st.focused ? "does not take the focus" : ok ? "takes the focus and changes value (" + String(st0.value).slice(0, 12) + " -> " + String(st2.value).slice(0, 12) + ")" : "takes the focus; the value did not change";
      if (!ok && st.focused && p.tag === "SELECT") { const n = await ev(`${F}.querySelector('[data-t3x]').options.length`); if (n < 2) { ok = true; res = "takes the focus (one option only)"; } }
      if (st2.value !== st0.value) await ev(`(()=>{const e=${F}.querySelector('[data-t3x]');if(e){e.value=${JSON.stringify(String(st0.value))};e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))}})()`);
    } else {
      let s1 = s0;
      for (let i = 0; i < 10; i++) { await sleep(120); s1 = await sig(); if (s1 !== s0 || choosers > ch0 || dialogs > dg0) break; }
      const k1 = await counters(), id1 = await screenId();
      const what = [];
      if (k1.o > k0.o) what.push("opens " + (await ev(FW + ".__t3.opens.slice(-1)[0]")).replace(BASE, "/").slice(0, 70));
      if (k1.dl > k0.dl) what.push("downloads " + (await ev(FW + ".__t3.downloads.slice(-1)[0]")));
      if (k1.m > k0.m) what.push("opens an email");
      if (k1.c > k0.c) what.push("copies to the clipboard");
      if (dialogs > dg0) what.push("asks to confirm (dismissed)");
      if (choosers > ch0) what.push("opens the file picker");
      if (id1 !== id0) what.push("goes to " + id1.split("|").filter(Boolean).slice(0, 4).join(" / ").slice(0, 80));
      else if (s1 !== s0 && !what.length) {
        const st = await ctlState();
        what.push(st.gone ? "the screen redraws" : (p.type === "checkbox" || p.type === "radio") ? (st.checked !== st0.checked ? "toggles (" + st0.checked + " -> " + st.checked + ")" : "the screen changes") : "the screen changes");
      }
      ok = what.length > 0;
      if (!ok && p.selected) { ok = true; what.push("inert: already chosen"); }
      res = ok ? what.join(", ") : "nothing visible happened";
    }
    const errs = logs.slice(n0);
    if (errs.length) { ok = false; res += "; script error: " + errs.join(" / ").slice(0, 120); }
    report(S.name, c.label, how, ok, res);
    if (/^Apply|Send application/.test(c.label)) await sleep(3500);   // let the application's answer (and any box it brings) arrive now
    // put the screen back: close what opened, and redraw it before the next press if it moved or the press can repeat-destroy
    if ((await screenId()) !== S.id || /delete|remove|wipe|sign out|reset|clear/i.test(c.label)) S.id = "";
  };
  const walk = async (S) => {
    if (ONLY && !ONLY.test(S.name)) return;
    await closeAll(); await S.open(); await sleep(600); if (S.details) await openDetails(S.root);
    S.id = await screenId();
    if (process.env.OUT && !S.noShot) { await ev("(()=>{const d=" + F + ";const m=d.getElementById('main');if(m)m.scrollTop=0;d.scrollingElement.scrollTop=0})()"); await sleep(200); await shot(pathm.join(process.env.OUT, (WIDTH + "-" + S.name).replace(/[^a-z0-9]+/gi, "-").toLowerCase() + ".png")); }
    const list = await enumerate(S.root);
    console.log("--- " + S.name + ": " + list.length + " controls");
    if (!list.length) report(S.name, "(the screen)", "-", !!S.mayBeEmpty, "no controls found");
    for (const c of list) {
      if (S.skip && S.skip.test(c.label)) { report(S.name, c.label, "-", true, "left alone: " + S.skipWhy); continue; }
      for (const how of HOW) await pressOne(S, c, how);
    }
  };

  // ================================================================== run
  if (PHONE === false && HOW.indexOf("touch") > -1) await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });   // a touch-screen laptop
  await reload();
  const sandbox = await ev("!!" + F + ".getElementById('modeSw')");
  if (process.env.OUT) fs.mkdirSync(process.env.OUT, { recursive: true });

  // ---- the consent box (sandbox: when the app opens; dev: on the first swipe right)
  const consentOpen = async () => {
    await ev("(()=>{const w=" + FW + ";w.localStorage.removeItem((w.__uaplyKey||'uaply')+'.consent')})()");
    if (sandbox) { await ev("(()=>{const w=" + FW + ";if(!w.document.getElementById('kitConsent')&&w.__uaplyAskConsent)w.__uaplyAskConsent()})()"); await sleep(400); }
    else { await menu("svc", "job"); await sleep(300); await ev("(" + F + ").getElementById('btnYes').click()"); await sleep(1200); }
  };
  await walk({ name: "Consent box", root: "#kitConsent", open: consentOpen, fresh: true });
  await ev("(()=>{const w=" + FW + ";w.localStorage.setItem((w.__uaplyKey||'uaply')+'.consent',JSON.stringify({v:2,at:Date.now()}));const o=w.document.getElementById('kitConsent');if(o)o.remove()})()");

  // ---- a profile that can apply (name, email, resume file), as a person would have it after Profile setup
  await menu("prof", "settings"); await sleep(600);
  await ev("(()=>{const d=" + F + ";for(const [i,v] of [['pName','Sam Rivera'],['pEmail','sam.controls@example.com']]){const e=d.getElementById(i);if(e){e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}))}}d.getElementById('wzNext').click()})()"); await sleep(900);
  await ev("(()=>{const b=" + F + ".querySelector('.wzDots button[data-step=\"3\"]');if(b)b.click()})()"); await sleep(500);
  await ev("(()=>{const w=" + FW + ";const i=" + F + ".getElementById('pResFile');if(!i)return;const dt=new w.DataTransfer();dt.items.add(new w.File([new w.Uint8Array([37,80,68,70,45,49,46,52,10,37,226,227,207,211,10,115,97,109,10,37,37,69,79,70,10])],'Sam-Rivera-Resume.pdf',{type:'application/pdf'}));i.files=dt.files;i.dispatchEvent(new w.Event('change',{bubbles:true}))})()");
  await sleep(1200); await ev("(" + F + ").getElementById('wzNext').click()"); await sleep(800);

  // ---- the bottom menus: each button opens its menu, each item opens its screen
  if (!ONLY || ONLY.test("Bottom menus")) {
    for (const how of HOW) {
      for (const [k, items] of [["svc", ["job", "parttime", "internship", "coop"]], ["dash", ["overview", "applied", "accepted", "rejected", "interview"]], ["prof", ["settings", "filters", "account", "plan", "data"]]]) {
        for (const v of items) {
          await closeAll();
          const b = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ",f=document.querySelector('iframe').getBoundingClientRect(),r=d.getElementById('nb-" + k + "').getBoundingClientRect();return {x:f.left+r.left+r.width/2,y:f.top+r.top+r.height/2}})())"));
          if (how === "touch") await tapAt(b); else await clickAt(b);
          await sleep(400);
          const open = await ev("(" + F + ").getElementById('nb-" + k + "').getAttribute('aria-expanded')==='true'");
          const ip = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ",e=d.querySelector('.nwrap[data-k=" + k + "] .nitem[data-v=" + v + "]');if(!e)return null;const f=document.querySelector('iframe').getBoundingClientRect(),r=e.getBoundingClientRect();const h=d.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return {x:f.left+r.left+r.width/2,y:f.top+r.top+r.height/2,cover:h&&!e.contains(h)?(h.id||h.className||h.tagName):''}})())"));
          if (!open || !ip) { report("Bottom menus", k + " › " + v, how, false, open ? "the item is not in the menu" : "the menu did not open"); continue; }
          if (ip.cover) { report("Bottom menus", k + " › " + v, how, false, "covered by " + ip.cover); continue; }
          if (how === "touch") await tapAt(ip); else await clickAt(ip);
          await sleep(600);
          const r = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ";const w=d.querySelector('.nwrap[data-k=" + k + "]');const i=w.querySelector('.nitem[data-v=" + v + "]');return {closed:w.querySelector('.nmenu').hidden,label:d.getElementById('nb-" + k + "').innerText.replace(/\\s+/g,' ').trim(),cur:d.getElementById('nb-" + k + "').getAttribute('aria-current')}})())"));
          report("Bottom menus", k + " › " + v, how, r.closed && r.cur === "true", "opens " + r.label);
        }
      }
    }
  }

  // ---- header, footer, help button (the same on every screen)
  // (opened from Dashboard, so the UAply logo, which goes home to the job cards, has somewhere to go)
  await walk({ name: "Header and footer", root: ".bar,#legalbar,#uaChatBtn,#bnav", open: async () => { await menu("dash", "overview"); }, fresh: true, noShot: true,
    skip: /^Services|^Dashboard|^Profile/, skipWhy: "the bottom menu buttons are pressed above with each of their items" });
  // keyboard in Hiring mode must never swipe the job deck hidden under it
  if (sandbox) {
    await menu("svc", "job"); await sleep(300);
    const d0 = await ev("Object.keys(" + FW + ".__uaply.S.decisions).length");
    await ev("(" + F + ").getElementById('modeSw').click()"); await sleep(900);
    await send("Input.dispatchMouseEvent", { type: "mousePressed", x: 5, y: 300, button: "left", buttons: 1, clickCount: 1 });
    await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: 5, y: 300, button: "left", buttons: 0, clickCount: 1 });
    await key("ArrowRight"); await sleep(300); await send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: "ArrowLeft", code: "ArrowLeft", windowsVirtualKeyCode: 37 }); await send("Input.dispatchKeyEvent", { type: "keyUp", key: "ArrowLeft", code: "ArrowLeft", windowsVirtualKeyCode: 37 }); await sleep(900);
    const d1 = await ev("Object.keys(" + FW + ".__uaply.S.decisions).length");
    check("Hiring mode: the arrow keys do not swipe the job deck hidden under it", d1 === d0, d0 + " -> " + d1 + " choices");
    await ev("(" + F + ").getElementById('modeSw').click()"); await sleep(600);
  }

  for (const S of SCREENS) await walk(S);

  // ---- sandbox: the employer-questions box after a swipe right
  if (sandbox) {
    const askOpen = async () => {
      for (let i = 0; i < 8; i++) {
        if (await ev("!!" + F + ".getElementById('kitAsk')")) return;
        await menu("svc", "job"); await sleep(300);
        await ev("(" + F + ").getElementById('btnYes').click()"); await sleep(3500);
      }
    };
    await walk({ name: "Employer questions box", root: "#kitAsk", open: askOpen, fresh: true, mayBeEmpty: true });
  }

  // ---- signed in: an account on this server (the test inbox gives the code), then Account again, and Hiring mode in the sandbox
  const email = "controls." + Date.now() + "@example.com";
  const su = await ev("fetch('/api/auth/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'" + email + "',password:'controls test 12345',agree:true})}).then(r=>r.status)");
  const code = await ev("fetch('/outbox').then(r=>r.text()).then(t=>{const m=t.match(/([0-9]{6}) is your UAply verification code/);return m?m[1]:''})");
  const vf = await ev("fetch('/api/auth/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:'" + code + "'})}).then(r=>r.status)");
  check("a test account is created and verified on this server", su === 200 && vf === 200, su + "/" + vf);
  await reload();
  await ev("(()=>{const w=" + FW + ";w.localStorage.setItem((w.__uaplyKey||'uaply')+'.consent',JSON.stringify({v:2,at:Date.now()}));const o=w.document.getElementById('kitConsent');if(o)o.remove()})()");
  await walk({ name: "Profile › Account (signed in)", root: "main > section:not([hidden])", open: async () => { await menu("prof", "account"); }, details: true,
    skip: /^Sign out$/, skipWhy: "pressed last, below" });
  if (sandbox) {
    // a company and one posting, so every Hiring screen has its full content
    const co = await ev("fetch('/api/employer/company',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Controls Test Co',country:'US',region:'PA',city:'Philadelphia',industry:'Accounting',size:'11-50',about:'A test company made by tools/ui-controls.js.',consent:true})}).then(r=>r.status)");
    const jb = await ev("fetch('/api/employer/job',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:'Junior Analyst',mode:'remote',sal_min:50000,sal_max:60000,skills:['Excel'],blurb:'Analyze data and build reports for a small team.'})}).then(r=>r.status)");
    check("Hiring mode set-up: a company and a posting are saved", co === 200 && jb === 200, co + "/" + jb);
    const hire = (view) => async () => { await ev("(()=>{const d=" + F + ";if(!d.body.classList.contains('hire'))d.getElementById('modeSw').click()})()"); await sleep(1200); await ev("(()=>{const b=" + F + ".querySelector('#hub [data-view=" + view + "]');if(b)b.click()})()"); await sleep(500); };
    for (const v of ["overview", "jobs", "applicants", "company", "billing"]) await walk({ name: "Hiring › " + v, root: "#hub", open: hire(v), skip: /^Delete$|^Delete for good/, skipWhy: "deletes the test posting (its first press asks to confirm)" });
    await walk({ name: "Hiring › post a job", root: "#hub", open: async () => { await hire("overview")(); await ev("(()=>{const b=" + F + ".querySelector('#hub [data-act=new]');if(b)b.click()})()"); await sleep(600); } });
    await walk({ name: "Hiring › post a job (form)", root: "#hub", open: async () => { await hire("overview")(); await ev("(()=>{const b=" + F + ".querySelector('#hub [data-act=new]');if(b)b.click()})()"); await sleep(600); await ev("(()=>{const b=" + F + ".querySelector('#hub [data-act=manual]');if(b)b.click()})()"); await sleep(500); } });
    await ev("(()=>{const d=" + F + ";if(d.body.classList.contains('hire'))d.getElementById('modeSw').click()})()"); await sleep(600);
  }
  // Sign out, last
  {
    await menu("prof", "account"); await sleep(600);
    const p = JSON.parse(await ev("JSON.stringify((()=>{const d=" + F + ",b=d.querySelector('[data-auth=sout]');if(!b)return null;b.scrollIntoView({block:'center'});const f=document.querySelector('iframe').getBoundingClientRect(),r=b.getBoundingClientRect();return {x:f.left+r.left+r.width/2,y:f.top+r.top+r.height/2}})())"));
    if (p) { if (PHONE) await tapAt(p); else await clickAt(p); await sleep(1200); }
    check("Account › Sign out (" + (PHONE ? "tap" : "click") + ") signs out", !!p && /Signed out|Create your UAply account|Sign in to UAply|Log in to UAply/.test(await ev("(" + F + ").body.innerText")));
  }

  // ---- the links that were noted instead of opened: the ones on this server must answer
  const opened = JSON.parse(await ev("JSON.stringify((" + FW + ".__t3||{opens:[]}).opens)"));
  const local = [...new Set(table.map((r) => (/opens (\/\S+)/.exec(r.res) || [])[1]).filter(Boolean))];
  for (const u of local) { const st = await ev("fetch(" + JSON.stringify(u) + ").then(r=>r.status,()=>0)"); check("the link " + u + " answers 200", st === 200, String(st)); }
  void opened;

  // ---- summary
  const screens = [...new Set(table.map((r) => r.screen))];
  console.log("\n" + screens.length + " screens, " + table.length + " presses: " + table.filter((r) => r.ok).length + " worked, " + table.filter((r) => !r.ok).length + " did not");
  for (const s of screens) { const r = table.filter((x) => x.screen === s); console.log("  " + s + ": " + r.filter((x) => x.ok).length + "/" + r.length); }
  if (process.env.JSON_OUT) fs.writeFileSync(process.env.JSON_OUT, JSON.stringify({ port: PORT, width: WIDTH, sandbox, table }, null, 1));
  check("no script errors in the whole run", logs.length === 0, logs.join(" / ").slice(0, 300));
  void NOTES;
};
