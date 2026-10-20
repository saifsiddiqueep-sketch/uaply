/* "onboard" experiment (sandbox only, Trello card 9): first-run experience and the swipe lock.
   1. Swipe lock. Until the profile has every field a real application needs (the same rules as readiness.py on the server: name, email,
      phone, city, and a resume file or link), no swipe goes through, left or right: touch and mouse drags, the Pass and Apply buttons,
      the arrow keys and any other caller of decide() are stopped in decide() itself (patch below), the card springs back, nothing is
      applied, passed or saved, and a bottom sheet says what to do. The server refuses the same profile anyway (uaply_api.submit,
      code profile_incomplete), so this lock is the friendly half, not the only half.
   2. "Profile N% complete" above the cards, from the same rules; a tap opens Profile setup at the earliest step with something missing.
   3. Onboarding for a first visit: welcome, sign in (the existing Account screen: email, Continue with Google; Apple is shown as not yet
      available), the existing 5-step Profile setup as a guided flow with "Skip for now" on each step, then a ready check. A returning
      visitor whose profile is complete never sees it.
   Signed-out visitors: they may browse the cards; a swipe with an incomplete profile opens the same sheet, whose button offers sign-in
   first and setup without an account second. A complete profile on the device unlocks swiping signed out too (the profile lives on the
   device, and the server checks the profile each application carries). Signed in, progress is also saved to the account
   (POST /api/profile/state) so readiness is known on the server.
   Needs Bottom navigation (Profile setup lives there). Registered in uaply-envs.js as "onboard". */
(function(){
"use strict";
function once(src,a,b){if(src.indexOf(a)<0)throw new Error("patch target not found: "+a.slice(0,40));return src.replace(a,function(){return b})}

/* every swipe, whatever started it, goes through decide(): stop it there, before anything is marked busy or saved */
function patch(s){
  return once(s,"function decide(dir){\n  if(busy)return;",
    "function decide(dir){\n  if(busy)return;\n  if(window.__uaplyLocked&&window.__uaplyLocked(dir)){var lc=$(\"deck\").querySelector(\".card.top\");if(lc){lc.style.transition=\"\";clearCardStyle(lc)}return}");
}

var REQ=[["name","Full name","about"],["email","Email","about"],["phone","Phone number","about"],["loc","City","where"],["resume","Resume file or link","back"]];
var STEP_ORDER=["about","jobs","where","back","final"];
var DONE_KEY="uaply.onboard.v1";

var CSS="@keyframes onbIn{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}"+
"@keyframes onbUp{from{transform:translateY(100%)}to{transform:none}}@keyframes onbFade{from{opacity:0}to{opacity:1}}"+
"@keyframes onbPop{0%{transform:scale(.6);opacity:0}60%{transform:scale(1.06);opacity:1}100%{transform:none}}"+
"@keyframes onbNudge{0%,100%{transform:none}30%{transform:translateX(-8px)}60%{transform:translateX(6px)}}"+
"#onb{position:fixed;inset:0;z-index:80;background:var(--bg);color:var(--ink);overflow:auto;-webkit-overflow-scrolling:touch;"+
"padding:max(20px,env(safe-area-inset-top)) max(16px,env(safe-area-inset-right)) max(20px,env(safe-area-inset-bottom)) max(16px,env(safe-area-inset-left))}"+
"#onb .scr{max-width:440px;margin:0 auto;min-height:100%;display:flex;flex-direction:column;gap:14px;justify-content:center;animation:onbIn .32s cubic-bezier(.2,.8,.2,1) both}"+
"#onb h1{margin:0;font:800 30px/1.12 var(--display);letter-spacing:-.01em}#onb h2{margin:0;font:800 24px/1.15 var(--display)}"+
"#onb p{margin:0;color:var(--muted);font-size:15.5px;line-height:1.45}"+
"#onb .logo{width:76px;height:76px;border-radius:22px;display:grid;place-items:center;background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--accent-ink);font:800 38px var(--display);box-shadow:var(--shadow);animation:onbPop .4s cubic-bezier(.2,.8,.2,1) both}"+
"#onb .logo svg{width:44px;height:44px;fill:none;stroke:currentColor;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}"+   /* the same check mark as the UAply logo in the header */
"#onb .acts{display:flex;flex-direction:column;gap:10px;margin-top:8px}#onb .acts .btn{width:100%;min-height:50px;font-size:16px}"+
"#onb .soon{display:flex;align-items:center;justify-content:center;gap:8px;min-height:50px;border:1px dashed var(--line);border-radius:999px;color:var(--muted);font-weight:600}"+
"#onb .soon small{font-size:12px;border:1px solid var(--line);border-radius:99px;padding:1px 8px}"+
"#onb .lnk{background:none;border:0;color:var(--accent);font:inherit;font-weight:700;min-height:44px;cursor:pointer}"+
"#onb .dots{display:flex;gap:6px;justify-content:center}#onb .dots i{width:7px;height:7px;border-radius:9px;background:var(--line);transition:transform .18s,background .18s}#onb .dots i.on{background:var(--accent);transform:scale(1.3)}"+
"#onb ul.chk{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}"+
"#onb ul.chk li{display:flex;gap:10px;align-items:center;border:1px solid var(--line);background:var(--surface);border-radius:14px;padding:12px 14px;font-weight:600}"+
"#onb ul.chk li span{width:26px;height:26px;border-radius:99px;display:grid;place-items:center;font-size:14px;flex:none}"+
"#onb ul.chk li.ok span{background:var(--yes);color:#fff}#onb ul.chk li.no span{border:2px solid var(--no);color:var(--no)}#onb ul.chk li.no{color:var(--muted)}"+
"#onb .big{font-size:56px;line-height:1;animation:onbPop .4s .05s cubic-bezier(.2,.8,.2,1) both}"+
"#onbBar{display:flex;align-items:center;gap:8px;margin:0 auto 8px;max-width:420px;width:100%;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:999px;padding:6px 12px 6px 6px;font:600 13.5px inherit;cursor:pointer;min-height:44px}"+
"#onbBar .ring{--p:0;width:30px;height:30px;border-radius:99px;flex:none;background:conic-gradient(var(--accent) calc(var(--p)*1%),var(--line) 0);display:grid;place-items:center}"+
"#onbBar .ring::after{content:'';width:22px;height:22px;border-radius:99px;background:var(--surface)}#onbBar b{color:var(--accent)}#onbBar .go{margin-left:auto;color:var(--accent);font-weight:700}"+
"#onbSheetBg{position:fixed;inset:0;z-index:75;background:rgba(0,0,0,.42);animation:onbFade .2s ease both}"+
"#onbSheet{position:fixed;left:0;right:0;bottom:0;z-index:76;margin:0 auto;max-width:520px;background:var(--surface);color:var(--ink);border-radius:24px 24px 0 0;box-shadow:0 -10px 40px rgba(0,0,0,.25);"+
"padding:12px 20px max(20px,env(safe-area-inset-bottom));display:flex;flex-direction:column;gap:10px;animation:onbUp .3s cubic-bezier(.2,.8,.2,1) both}"+
"#onbSheet .grab{width:42px;height:5px;border-radius:9px;background:var(--line);margin:0 auto 6px}"+
"#onbSheet h2{margin:0;font:800 22px var(--display)}#onbSheet p{margin:0;color:var(--muted);font-size:15px}"+
"#onbSheet .miss{font-size:13.5px;color:var(--muted)}#onbSheet .miss b{color:var(--ink)}#onbSheet .btn{width:100%;min-height:50px;font-size:16px}"+
"#onbSheet.out,#onbSheetBg.out{animation:none;opacity:0;transform:translateY(40px);transition:opacity .18s,transform .18s}"+
".card.top.onbNudge{animation:onbNudge .22s ease}"+
"body.onbFlow #wzFoot{position:sticky;bottom:0;background:var(--bg);padding-top:8px;padding-bottom:max(8px,env(safe-area-inset-bottom));z-index:2}"+
"body.onbFlow #wzTop .wzBar{height:8px;border-radius:9px}body.onbFlow #wzTop .wzBar i{transition:width .3s cubic-bezier(.2,.8,.2,1)}"+
"body.onbFlow .grid>:not(.wz-off){animation:onbIn .28s cubic-bezier(.2,.8,.2,1) both}"+
"#onbSkip{min-height:44px}"+
"@media (prefers-reduced-motion:reduce){#onb .scr,#onb .logo,#onb .big,#onbSheet,#onbSheetBg,.card.top.onbNudge,body.onbFlow .grid>*{animation:none!important}#onbSheet.out,#onbSheetBg.out,#onbBar .ring,#onb .dots i{transition:none!important}}";

function apply(w){
  var d=w.document,A=w.__uaply;if(!A)throw new Error("needs the app API (Bottom navigation)");
  var st=d.createElement("style");st.textContent=CSS;d.head.appendChild(st);
  var reduce=function(){return !!(w.matchMedia&&w.matchMedia("(prefers-reduced-motion: reduce)").matches)};
  function E(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
  function local(){try{var v=JSON.parse(w.localStorage.getItem(DONE_KEY+":"+(w.__uaplyKey||"")));return v&&typeof v==="object"?v:{}}catch(e){return {}}}
  function saveLocal(v){try{w.localStorage.setItem(DONE_KEY+":"+(w.__uaplyKey||""),JSON.stringify(v))}catch(e){}}
  var mem=local();mem.skipped=Array.isArray(mem.skipped)?mem.skipped:[];
  var srv={enforced:true,signedIn:false};

  /* the profile as an application carries it (the same fields uaply-live.js posts to /api/apply) */
  function appProfile(){
    var p=A.S.profile||{},c=!!p.custom,x={};
    try{x=w.__uaplyApplyExt?w.__uaplyApplyExt():(p.ext||{})}catch(e){x={}}
    return {name:c?p.name||"":"",email:c?p.email||"":"",loc:c?p.loc||"":"",ext:{phone:x.phone||"",resume:x.resume||""}};
  }
  function hasFile(){try{return !!(w.__uaplyResume&&w.__uaplyResume())}catch(e){return false}}
  /* readiness.py, line for line: keep the two in step */
  function ready(){
    var p=appProfile(),f={name:!!String(p.name).trim(),email:/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(p.email).trim()),
      phone:/^[+()\d\s.-]{7,25}$/.test(String(p.ext.phone).trim()),loc:!!String(p.loc).trim(),resume:hasFile()||/^https:\/\//.test(String(p.ext.resume).trim())};
    var missing=REQ.filter(function(r){return !f[r[0]]}).map(function(r){return {key:r[0],label:r[1],step:r[2]}});
    var n=REQ.length-missing.length,first=missing.map(function(m){return STEP_ORDER.indexOf(m.step)}).sort()[0];
    return {state:!missing.length?"ready":n?"in_progress":"not_started",percent:Math.round(100*n/REQ.length),missing:missing,
      step:first==null?null:STEP_ORDER[first],filled:f};
  }
  function signedIn(){try{var a=w.__uaplyAuth&&w.__uaplyAuth();return !!(a&&a.user)}catch(e){return false}}
  function api(){try{var a=w.__uaplyAuth&&w.__uaplyAuth();return !!(a&&a.up)}catch(e){return false}}
  var lastSent="";
  function sync(){
    if(!api()||!signedIn())return;
    var body=JSON.stringify({profile:appProfile(),hasResume:hasFile(),skipped:mem.skipped});
    if(body===lastSent)return;lastSent=body;
    w.fetch("/api/profile/state",{method:"POST",headers:{"Content-Type":"application/json"},body:body,credentials:"same-origin"})
      .then(function(r){return r.json()}).then(function(j){if(j&&typeof j.enforced==="boolean")srv.enforced=j.enforced}).catch(function(){lastSent=""});
  }
  w.fetch("/api/profile/readiness",{credentials:"same-origin"}).then(function(r){return r.ok?r.json():null}).then(function(j){
    if(!j)return;srv.signedIn=!!j.signedIn;
    (j.skipped||[]).forEach(function(k){if(mem.skipped.indexOf(k)<0)mem.skipped.push(k)});
  }).catch(function(){});

  /* ---------- the indicator above the cards ---------- */
  var bar=d.createElement("button");bar.type="button";bar.id="onbBar";
  var deck=d.getElementById("deck");if(deck&&deck.parentNode)deck.parentNode.insertBefore(bar,deck);
  function paintBar(){
    var r=ready();bar.hidden=r.state==="ready";
    bar.innerHTML='<span class="ring" style="--p:'+r.percent+'" aria-hidden="true"></span><span>Profile <b>'+r.percent+'%</b> complete</span><span class="go">Finish</span>';
    bar.setAttribute("aria-label","Profile "+r.percent+" percent complete. Finish your profile to start swiping.");
  }
  bar.onclick=function(){openSetup()};
  function openSetup(){
    closeSheet(true);var r=ready();
    d.body.classList.add("onbFlow");
    var k=r.step||"about";
    if(w.__uaplyOpenProf)w.__uaplyOpenProf(k);
    /* setup opened before keeps its last step; move to the one with something missing */
    setTimeout(function(){if(curStep()!==STEP_ORDER.indexOf(k)){var b=d.querySelector('#wzTop .wzDots button[data-step="'+STEP_ORDER.indexOf(k)+'"]');if(b)b.click()}addSkip()},60);
  }

  /* ---------- the bottom sheet ---------- */
  var closedAt=0;
  function closeSheet(now){
    var s=d.getElementById("onbSheet"),bg=d.getElementById("onbSheetBg");if(!s)return;
    d.removeEventListener("keydown",esc,true);closedAt=Date.now();
    if(now||reduce()){s.remove();if(bg)bg.remove();return}
    s.classList.add("out");if(bg)bg.classList.add("out");setTimeout(function(){s.remove();if(bg)bg.remove()},190);
  }
  function esc(e){if(e.key==="Escape"){e.preventDefault();closeSheet()}}
  function showSheet(){
    if(d.getElementById("onbSheet"))return;            /* already open: one sheet per gesture, however many times decide() is called */
    if(Date.now()-closedAt<300)return;                  /* the tap that closed it (Maybe Later, the backdrop) must not open it again */
    var r=ready(),out=!signedIn()&&api();
    var bg=d.createElement("div");bg.id="onbSheetBg";bg.onclick=function(){closeSheet()};
    var s=d.createElement("div");s.id="onbSheet";s.setAttribute("role","dialog");s.setAttribute("aria-modal","true");s.setAttribute("aria-labelledby","onbSH");
    s.innerHTML='<div class="grab" aria-hidden="true"></div><h2 id="onbSH">You\'re almost there.</h2><p>Complete your profile to unlock job swiping and start applying.</p>'+
      (r.missing.length?'<p class="miss">Still needed: <b>'+r.missing.map(function(m){return E(m.label)}).join(", ")+'</b></p>':'')+
      '<button type="button" class="btn" id="onbGo">Complete My Profile</button>'+
      (out?'<button type="button" class="btn ghost" id="onbAcct">Sign in or create an account</button>':'')+
      '<button type="button" class="btn ghost" id="onbLater">Maybe Later</button>';
    d.body.appendChild(bg);d.body.appendChild(s);
    d.getElementById("onbGo").onclick=openSetup;
    d.getElementById("onbLater").onclick=function(){closeSheet()};
    if(out)d.getElementById("onbAcct").onclick=function(){closeSheet(true);if(w.__uaplyOpenProf)w.__uaplyOpenProf("account")};
    d.addEventListener("keydown",esc,true);
    setTimeout(function(){var b=d.getElementById("onbGo");if(b)b.focus({preventScroll:true})},reduce()?0:120);
  }
  function nudge(){
    if(reduce())return;var c=d.querySelector("#deck .card.top");if(!c)return;
    c.classList.remove("onbNudge");void c.offsetWidth;c.classList.add("onbNudge");setTimeout(function(){c.classList.remove("onbNudge")},260);
  }
  /* called by decide() (see patch): true = this swipe is not allowed */
  w.__uaplyLocked=function(){
    if(!srv.enforced)return false;
    if(ready().state==="ready")return false;
    if(!d.getElementById("onbSheet"))nudge();
    showSheet();paintBar();return true;
  };

  /* ---------- guided Profile setup: Skip for now, and the ready check after the last step ---------- */
  function curStep(){var b=d.querySelector('#wzTop .wzDots button[aria-current="step"]');return b?+b.getAttribute("data-step"):0}
  function addSkip(){
    var foot=d.getElementById("wzFoot");if(!foot||d.getElementById("onbSkip"))return;
    var b=d.createElement("button");b.type="button";b.className="btn ghost";b.id="onbSkip";b.textContent="Skip for now";
    var next=d.getElementById("wzNext");foot.insertBefore(b,next);
    b.onclick=function(){
      var i=curStep(),k=STEP_ORDER[i];
      if(k&&mem.skipped.indexOf(k)<0)mem.skipped.push(k);saveLocal(mem);
      /* keep what was typed: the quiet save Profile setup already uses when someone leaves with unsaved answers */
      var form=d.getElementById("form");
      if(form){w.__uaplyAutoSave=true;try{if(form.requestSubmit)form.requestSubmit();else form.dispatchEvent(new w.Event("submit",{cancelable:true,bubbles:true}))}finally{w.__uaplyAutoSave=false}}
      if(i>=STEP_ORDER.length-1){finishFlow();return}
      var nb=d.querySelector('#wzTop .wzDots button[data-step="'+(i+1)+'"]');if(nb)nb.click();
      afterChange();
    };
  }
  /* a step saved for real is no longer "skipped" */
  d.addEventListener("click",function(e){
    var t=e.target.closest&&e.target.closest("#wzNext");if(!t)return;
    var i=curStep(),k=STEP_ORDER[i],last=/Finish/.test(t.textContent);
    setTimeout(function(){
      if(curStep()!==i||last){mem.skipped=mem.skipped.filter(function(x){return x!==k});saveLocal(mem)}
      afterChange();
      if(last&&(d.body.classList.contains("onbFlow")||!mem.done))finishFlow();
    },60);
  },true);

  /* ---------- the onboarding screens ---------- */
  var ov=null;
  function screen(html){
    if(!ov){ov=d.createElement("div");ov.id="onb";d.body.appendChild(ov)}
    ov.innerHTML='<div class="scr">'+html+'</div>';ov.scrollTop=0;
    var f=ov.querySelector("h1,h2");if(f){f.tabIndex=-1;f.focus({preventScroll:true})}
  }
  function close(){if(ov){ov.remove();ov=null}}
  function dots(n){return '<div class="dots" aria-hidden="true">'+[0,1,2,3].map(function(i){return '<i class="'+(i===n?"on":"")+'"></i>'}).join("")+'</div>'}
  function welcome(){
    screen('<div class="logo" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></div><h1>Your next opportunity starts here.</h1><p>Discover jobs that fit you. Swipe. Apply. Move forward.</p>'+dots(0)+
      '<div class="acts"><button type="button" class="btn" id="onbStart">Get started</button><button type="button" class="lnk" id="onbBrowse">Just look around first</button></div>');
    d.getElementById("onbStart").onclick=function(){signedIn()?toSetup():signin()};
    d.getElementById("onbBrowse").onclick=function(){mem.seen=true;saveLocal(mem);close();paintBar()};
  }
  function signin(){
    screen(dots(1)+'<h2>Create your account</h2><p>Sign in so your profile and applications follow you to any device.</p>'+
      '<div class="acts"><button type="button" class="btn" id="onbEmail">Continue with email</button>'+
      '<button type="button" class="btn ghost" id="onbGoogle">Continue with Google</button>'+
      '<div class="soon" aria-disabled="true">Continue with Apple <small>Not available yet</small></div>'+
      '<button type="button" class="lnk" id="onbNoAcct">Set up my profile first</button></div>');
    function acct(){mem.seen=true;mem.wantSetup=true;saveLocal(mem);close();if(w.__uaplyOpenProf)w.__uaplyOpenProf("account");waitSignIn()}
    d.getElementById("onbEmail").onclick=acct;d.getElementById("onbGoogle").onclick=acct;
    d.getElementById("onbNoAcct").onclick=toSetup;
  }
  /* after the Account screen signs someone in, carry on to the guided setup */
  function waitSignIn(){
    var n=0;(function tick(){
      if(signedIn()&&mem.wantSetup){mem.wantSetup=false;saveLocal(mem);sync();if(ready().state!=="ready")toSetup();return}
      if(++n<600&&mem.wantSetup)setTimeout(tick,1000);
    })();
  }
  function toSetup(){mem.seen=true;saveLocal(mem);close();openSetup();setTimeout(addSkip,0)}
  function finishFlow(){
    var r=ready();d.body.classList.remove("onbFlow");
    if(r.state==="ready"){mem.done=true;saveLocal(mem)}
    screen((r.state==="ready"?'<div class="big" aria-hidden="true">🎉</div>':'')+dots(3)+
      '<h2>'+(r.state==="ready"?"You're ready to make moves.":"Almost there")+'</h2>'+
      '<p>'+(r.state==="ready"?"Everything an application needs is in place. Swipe right to apply, left to pass.":"These are needed before you can swipe. Everything else is optional.")+'</p>'+
      '<ul class="chk">'+REQ.map(function(q){var ok=r.filled[q[0]];return '<li class="'+(ok?"ok":"no")+'"><span aria-hidden="true">'+(ok?"✓":"!")+'</span>'+E(q[1])+'<span class="sr" style="position:absolute;left:-9999px">'+(ok?"done":"missing")+'</span></li>'}).join("")+'</ul>'+
      '<div class="acts">'+(r.state==="ready"?'<button type="button" class="btn" id="onbExplore">Start Exploring Jobs</button>':
        '<button type="button" class="btn" id="onbFix">Finish my profile</button><button type="button" class="lnk" id="onbExplore">Look at jobs for now</button>')+'</div>');
    d.getElementById("onbExplore").onclick=function(){close();if(w.__uaplyHome)w.__uaplyHome();else A.show("swipe");paintBar()};
    var fx=d.getElementById("onbFix");if(fx)fx.onclick=function(){close();openSetup();setTimeout(addSkip,0)};
  }
  function afterChange(){paintBar();sync()}
  var base=w.__uaplySyncPrefs;w.__uaplySyncPrefs=function(){if(base)base();afterChange()};
  var baseShow=w.__uaplyOnShow;w.__uaplyOnShow=function(t){if(baseShow)baseShow(t);if(t==="profile")setTimeout(addSkip,0);else if(t==="swipe"){d.body.classList.remove("onbFlow");paintBar()}};
  /* the one-time agreement (consentFirst) waits until the person is out of onboarding and Profile setup, so it never covers them */
  var askBase=w.__uaplyAskConsent;
  if(askBase)w.__uaplyAskConsent=function(){if(d.getElementById("onb")||d.body.classList.contains("onbFlow")){setTimeout(w.__uaplyAskConsent,1500);return}askBase()};
  /* the first ask is already on a timer from uaply-live.js: if it opens while onboarding is up, put it away and ask again afterwards */
  if(askBase)setTimeout(function(){var k=d.getElementById("kitConsent");if(k&&(d.getElementById("onb")||d.body.classList.contains("onbFlow"))){k.remove();w.__uaplyAskConsent()}},900);
  w.__uaplyOnboard={ready:ready,welcome:welcome,finish:finishFlow,sheet:showSheet};   /* for the tests */
  paintBar();addSkip();
  /* first visit: welcome. A returning visitor whose profile is complete (or who already chose to look around) goes straight to the cards */
  if(!mem.seen&&!mem.done&&ready().state!=="ready")welcome();
  else if(mem.wantSetup)waitSignIn();
}

window.UAplyOnboard={patch:patch,apply:apply};
})();
