/* "signup" experiment (sign-up v2) for the sandbox: "Sign-up, nothing hidden". Never loaded by prod; dev loads it only once it is promoted.
   The design Mohammed chose on Oct 21: one centered card with the brand mark directly above it (the two centered together as one group),
   Continue with Google, "or", Email, First name, Last name, the 18+ tick, Create my account. No password: Create my account emails a
   6-digit code (the server's sign-up v2 routes, sandbox only), and Google skips the code for addresses Google vouches for. After the
   account exists, two questions (kind of work, where), then "You're ready to swipe" (or "Almost ready" while the app's readiness rule,
   READY_MIN in shared/uaply-nav.js, still needs a phone number or a resume). Returning people: Google, or Email me a code.
   What is kept where (the screen says the same): the account (email, when the 18+ box was ticked) on the server; first and last name, the
   work picks and the place on this device only, in the app's own profile (Profile setup shows them). Nothing here is sent anywhere else.
   A shared device: a sign-in to another account than the ones whose details this device holds asks Keep / Start fresh first (while it
   asks, the swipe deck takes no keys and an application waiting to be sent is held), the name typed before Google goes only to that same
   address, and Sign out offers "Remove my details from this device" (default keeps them).
   patch() adds the card's styles to the production page with once(); apply() fills the Account screen through four small hooks in
   shared/uaply-nav.js (look for "sign-up v2" there). A missing hook or anchor stops this experiment loudly, never silently. */
(function(){
"use strict";
var Env=window.UAplyEnv;
if(!Env){if(window.console)console.error("[uaply] sign-up v2: shared/uaply-signup.js must load after uaply-envs.js");return}
function once(src,a,b){if(src.indexOf(a)<0)throw new Error("patch target not found: "+a.slice(0,40));return src.replace(a,function(){return b})}

var CSS=`
/* sign-up v2 (shared/uaply-signup.js). Every class starts with sg so nothing in the app's own styles (.card, .chips, .btn, .bar) reaches it */
#acctSec.sgnOn{max-width:none;width:100%;padding:12px 0 16px;flex:1 0 auto;justify-content:center;justify-content:safe center;gap:0}
#acctSec.sgnOn.sgWide{max-width:none}
#acctSec.sgnOn>h3,#acctSec.sgnOn>.lead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
#acctSec.sgnOn>#aMsg{text-align:center;margin-top:10px}
#acctSec.sgnOn>#aMsg:empty{display:none}
#pane-profile:has(>#acctSec.sgnOn:not([hidden])){display:flex;flex-direction:column;min-height:100%}
.sg{--sg-field:color-mix(in srgb,var(--muted) 72%,var(--surface));--sg-no:color-mix(in srgb,var(--no,#E03A45) 88%,var(--ink));--sg-yes:var(--yes,#0B8F62);--sg-yes-ink:color-mix(in srgb,var(--yes,#0B8F62) 80%,var(--ink));--sg-yes-bg:var(--yes-bg,#DCF5EA);
  --sg-g-bg:#FFFFFF;--sg-g-ink:#1F1F1F;--sg-g-line:#747775;color:var(--ink);font:15px/1.45 var(--body);width:100%}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .sg{--sg-g-bg:#131314;--sg-g-ink:#E3E3E3;--sg-g-line:#8E918F}}
:root[data-theme="dark"] .sg{--sg-g-bg:#131314;--sg-g-ink:#E3E3E3;--sg-g-line:#8E918F}
.sg *{box-sizing:border-box}
.sg h1,.sg h2{font-family:var(--display);letter-spacing:-.01em;margin:0;color:var(--ink);text-transform:none}
.sg h1:focus,.sg h2:focus{outline:none}
.sg :focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.sg .sg-vh{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.sg .sg-i{width:1em;height:1em;fill:none;stroke:currentColor;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round;vertical-align:-.15em;flex:none}
.sg-shell{display:grid;grid-template-columns:minmax(0,1fr);justify-items:center;width:100%}
.sg-bb{display:flex;align-items:center;justify-content:center;gap:10px;padding:0 0 14px}
.sg-lg{width:34px;height:34px;border-radius:10px;display:inline-grid;place-items:center;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;flex:none}
.sg-lg svg{width:62%;height:62%;fill:none;stroke:currentColor;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}
.sg-wm{font:800 19px var(--display);letter-spacing:-.01em}
.sg-card{background:var(--surface);border:1px solid var(--line);border-radius:24px;box-shadow:var(--shadow);padding:26px 28px;width:100%;max-width:440px;display:flex;flex-direction:column;gap:12px}
.sg-chead{display:flex;flex-direction:column;align-items:center;text-align:center;gap:4px;margin-bottom:4px}
.sg-chead h1{font-size:25px;line-height:1.15}
.sg-sub{color:var(--muted);margin:0}
.sg-fine{color:var(--muted);font-size:13px;margin:0}
.sg-or{display:flex;align-items:center;gap:12px;color:var(--muted);font-size:13px}
.sg-or::before,.sg-or::after{content:"";flex:1;height:1px;background:var(--line)}
.sg-stack{display:flex;flex-direction:column;gap:12px}
.sg-two{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.sg-btn{font:600 15px/1.1 var(--body);min-height:48px;padding:0 20px;border-radius:999px;border:1px solid transparent;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:10px;transition:transform .12s ease,background-color .15s ease,box-shadow .15s ease;text-decoration:none}
.sg-btn:active{transform:scale(.98)}
.sg-btn.pri{background:var(--accent);color:var(--accent-ink)}
.sg-btn.pri:hover{background:color-mix(in srgb,var(--accent) 86%,var(--ink))}
.sg-btn.ghost{background:transparent;border-color:var(--line);color:var(--ink)}
.sg-btn.ghost:hover{background:var(--bg)}
.sg-btn.wide{width:100%}
.sg-btn.g{background:var(--sg-g-bg);color:var(--sg-g-ink);border-color:var(--sg-g-line)}
.sg-btn.g:hover{box-shadow:0 1px 3px rgba(0,0,0,.18)}
.sg-btn.g svg{width:20px;height:20px;flex:none}
.sg-btn[aria-busy="true"],.sg-btn:disabled{pointer-events:none;opacity:.8}
.sg-lnk{font:600 14px var(--body);color:var(--accent);background:none;border:0;padding:6px 4px;cursor:pointer;border-radius:6px;min-height:44px;display:inline-flex;align-items:center;justify-content:center;vertical-align:middle}
.sg-lnk:hover{text-decoration:underline}
.sg-lnk[disabled]{color:var(--muted);cursor:default;text-decoration:none}
.sg-lnk.inl{min-height:0;padding:0;font-size:inherit;text-decoration:underline}
.sg-swap{margin:0;text-align:center;font-size:14px;color:var(--muted)}
.sg-swap .sg-lnk{padding:6px 2px}
.sg-fld{display:flex;flex-direction:column;min-width:0}
.sg-fld label{font-weight:600;font-size:14px;margin-bottom:6px;color:var(--ink)}
.sg-fld .sg-in{position:relative}
#acctSec .sg .sg-fld input{width:100%;min-height:48px;border-radius:12px;border:1.5px solid var(--sg-field);background:var(--surface);color:var(--ink);font:16px var(--body);padding:0 40px 0 14px;margin:0;transition:border-color .15s,box-shadow .15s}
#acctSec .sg .sg-fld input::placeholder{color:color-mix(in srgb,var(--muted) 75%,transparent)}
#acctSec .sg .sg-fld input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 4px color-mix(in srgb,var(--accent) 22%,transparent)}
#acctSec .sg .sg-fld.bad input{border-color:var(--sg-no)}
.sg-fld .sg-tick{position:absolute;right:13px;top:50%;transform:translateY(-50%) scale(.6);color:var(--sg-yes);opacity:0;transition:opacity .2s,transform .2s;font-size:18px;display:flex;pointer-events:none}
.sg-fld.good .sg-tick{opacity:1;transform:translateY(-50%) scale(1)}
.sg-fmsg{margin:6px 0 0;font-size:13px;color:var(--muted)}
.sg-fmsg:empty{display:none}
.sg-fld.bad .sg-fmsg,.sg-fmsg.err{color:var(--sg-no)}
.sg-fmsg.nudge{color:var(--accent);font-weight:600}
.sg-fmsg.ok{color:var(--sg-yes-ink)}
.sg-fix{font:600 13px var(--body);color:var(--accent);background:none;border:0;padding:0;text-decoration:underline;cursor:pointer}
.sg-agree{display:flex;gap:10px;align-items:flex-start;font-size:14px;cursor:pointer;line-height:1.4;color:var(--ink);min-height:44px;padding:2px 0}   /* the whole row ticks the box: a 44 px target (phone fit rule) */
.sg-agree input{width:20px;height:20px;margin:0;flex:none;accent-color:var(--accent);cursor:pointer}
.sg-agree span{flex:1;min-width:0}
.sg-agree a{color:var(--accent)}
.sg-agree.bad span{color:var(--sg-no)}
.sg-note{margin:0;font-size:13px;color:var(--muted);text-align:center}
.sg-note a{color:var(--accent)}
.sg-gnote{margin:0;font-size:13px;background:var(--sg-yes-bg);color:var(--ink);border-radius:12px;padding:9px 12px;display:flex;gap:8px;align-items:flex-start}
.sg-gnote .sg-i{color:var(--sg-yes);margin-top:2px}
.sg-gis{min-height:44px;display:flex;justify-content:center}
.sg-have{margin:0;font-size:14px;text-align:center;background:color-mix(in srgb,var(--accent) 9%,var(--surface));border:1px solid color-mix(in srgb,var(--accent) 30%,var(--line));border-radius:12px;padding:6px 12px;display:flex;flex-wrap:wrap;align-items:center;justify-content:center;column-gap:6px}
.sg-have b{word-break:break-all}
.sg-wait{min-height:min(560px,70vh)}
.sg-fixes{display:flex;flex-wrap:wrap;gap:8px}
.sg-okc{width:58px;height:58px;border-radius:50%;display:grid;place-items:center;background:var(--sg-yes-bg);color:var(--sg-yes);font-size:28px;margin:0 auto}
.sg-done{display:flex;flex-direction:column;gap:12px;text-align:center}
.sg-done h2,.sg-codestep h2{font-size:25px;line-height:1.15}
.sg-mark{font:12px var(--mono);color:var(--muted);margin:0;text-align:center}
.sg-mark a{color:var(--accent)}
.sg-code{display:flex;gap:8px;justify-content:center}
#acctSec .sg .sg-code input{flex:0 1 46px;min-width:0;width:46px;height:56px;border-radius:12px;border:1.5px solid var(--sg-field);background:var(--surface);color:var(--ink);text-align:center;font:600 22px var(--mono);padding:0;margin:0}
#acctSec .sg .sg-code input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 4px color-mix(in srgb,var(--accent) 22%,transparent)}
.sg-code.ok input{border-color:var(--sg-yes)}
.sg-codestep{display:flex;flex-direction:column;gap:12px;text-align:center}
.sg-codestep .sg-sub b{color:var(--ink);word-break:break-all}
.sg-between{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.sg-nameh{margin-top:-6px}
.sg-pop{animation:sgrise .3s cubic-bezier(.2,.8,.2,1) both}
@keyframes sgrise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
.sg-shake{animation:sgshake .38s}
@keyframes sgshake{20%,60%{transform:translateX(-6px)}40%,80%{transform:translateX(6px)}}
/* the two questions, after the account exists */
.sg-q4{background:var(--surface);border:1px solid var(--line);border-radius:24px;box-shadow:var(--shadow);width:100%;max-width:960px;margin:0 auto;display:flex;flex-direction:column;overflow:hidden}
.sg-q4b{display:flex;align-items:center;gap:12px;padding:16px 28px}
.sg-prog{flex:1;display:flex;gap:6px;max-width:420px;margin-inline:auto}
.sg-prog i{flex:1;height:6px;border-radius:999px;background:var(--line);overflow:hidden;position:relative}
.sg-prog i::after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,var(--accent),var(--accent2));transform:scaleX(0);transform-origin:left;transition:transform .35s ease}
.sg-prog i.cur::after{transform:scaleX(.35)}
.sg-prog i.on::after{transform:scaleX(1)}
.sg-who{display:inline-flex;align-items:center;gap:8px;font:600 14px var(--body)}
.sg-who i{width:30px;height:30px;border-radius:50%;background:var(--accent);color:var(--accent-ink);display:grid;place-items:center;font-style:normal;font-weight:800}
.sg-q4m{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:40px;padding:10px 40px 24px;align-items:center}
.sg-qs{max-width:540px;display:flex;flex-direction:column;gap:16px}
.sg-qs h2{font-size:32px;line-height:1.1}
.sg-made{display:inline-flex;align-self:flex-start;align-items:center;gap:8px;margin:0 0 4px;font-weight:600;font-size:14px;color:var(--sg-yes-ink);background:var(--sg-yes-bg);border-radius:999px;padding:6px 12px 6px 10px}
.sg-eyebrow{font:600 12px var(--mono);color:var(--accent);text-transform:uppercase;letter-spacing:.08em;margin:0}
.sg-chips{display:flex;flex-wrap:wrap;gap:8px}
.sg-chip{font:600 14px var(--body);color:var(--ink);background:var(--surface);border:1.5px solid var(--sg-field);border-radius:999px;padding:9px 15px;min-height:44px;cursor:pointer;display:inline-flex;align-items:center;gap:6px;transition:background-color .15s,border-color .15s}
.sg-chip:hover{border-color:var(--accent)}
.sg-chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.sg-pvh{font:600 11px var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 8px}
.sg-pvcard{background:var(--bg);border:1px solid var(--line);border-radius:20px;padding:20px;display:flex;flex-direction:column;gap:10px}
.sg-pvn{font:800 22px var(--display);overflow-wrap:anywhere}
.sg-pvph{color:var(--muted);font-weight:600}
.sg-pvr{display:grid;grid-template-columns:96px 1fr;gap:8px;font-size:14px;border-top:1px solid var(--line);padding-top:9px;border-radius:4px}
.sg-pvr span{color:var(--muted)}
.sg-pvr b{font-weight:600;min-width:0;overflow-wrap:anywhere}
.sg-pvr.later b{font-weight:400;color:var(--muted);font-style:italic}
.sg-vfl{display:flex;align-items:center;gap:6px;margin:10px 0 0;font-size:13px;font-weight:600;color:var(--sg-yes-ink)}
.sg-vfl .sg-i{color:var(--sg-yes)}
.sg-flash{animation:sgflash .6s}
@keyframes sgflash{0%{background:color-mix(in srgb,var(--accent2) 30%,transparent)}100%{background:transparent}}
.sg-meter{height:8px;border-radius:999px;background:var(--line);overflow:hidden;margin-top:4px}
.sg-meter i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));transition:width .4s ease}
.sg-pvmini{display:none}
.sg-q4f{display:flex;align-items:center;gap:12px;padding:14px 28px 18px;border-top:1px solid var(--line)}
.sg-q4f .sp{flex:1}
.sg-kh{font:12px var(--mono);color:var(--muted)}
.sg-kh kbd{font:11px var(--mono);border:1px solid var(--line);border-bottom-width:2px;border-radius:5px;padding:1px 5px;background:var(--bg)}
@media (max-width:700px){
  .sg-card{max-width:none;padding:22px 20px 20px;border-radius:22px;gap:11px}
  .sg-bb{padding:0 0 12px}
  .sg-chead{margin-bottom:2px}
  .sg-chead h1,.sg-done h2,.sg-codestep h2{font-size:23px}
  .sg-chip{min-height:48px}
  .sg-q4{border-radius:22px}
  .sg-q4b{padding:14px 16px 8px;gap:10px;flex-wrap:wrap}
  .sg-q4b .sg-prog{order:3;flex-basis:100%;max-width:none}
  .sg-q4b .sg-who{margin-left:auto}
  .sg-q4b .sg-whon{display:none}
  .sg-q4m{grid-template-columns:1fr;padding:6px 16px 16px;gap:14px}
  .sg-pv{order:-1}
  .sg-pvh,.sg-pvcard,.sg-vfl{display:none}
  .sg-pv.open .sg-pvcard,.sg-pv.open .sg-vfl{display:flex}
  .sg-pvmini{display:flex;width:100%;align-items:center;gap:10px;font:600 13px var(--body);color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:14px;padding:10px 12px;min-height:44px;cursor:pointer;margin-bottom:8px}
  .sg-pvmini .sg-meter{flex:1;margin:0;height:6px}
  .sg-pvmini .sg-i{transition:transform .2s}
  .sg-pv.open .sg-pvmini .sg-i{transform:rotate(90deg)}
  .sg-qs h2{font-size:26px}
  .sg-kh{display:none}
  .sg-q4f{padding:12px 16px 16px}
  .sg-qs .sg-two{grid-template-columns:1fr}
}
/* a laptop window under 800 px tall: a little less padding, so more of the card shows above the bottom bar */
.sg-qstack{gap:16px}
@media (min-width:701px) and (max-height:800px){.sg-card{padding:20px 26px;gap:10px}.sg-chead{margin-bottom:0}.sg-bb{padding-bottom:10px}
  .sg-q4b{padding:10px 24px}.sg-q4m{padding:0 32px 12px;gap:32px}.sg-qs h2{font-size:27px}.sg-qstack{gap:11px}.sg-made{margin:0}
  .sg-q4f{padding:10px 24px 12px}.sg-pvcard{padding:14px 16px;gap:7px}.sg-pvr{padding-top:7px}.sg-pvh{margin-bottom:6px}}
@media (max-width:360px){.sg-two{grid-template-columns:1fr}#acctSec .sg .sg-code input{height:50px}}
@media (prefers-reduced-motion:reduce){.sg *,.sg *::before,.sg *::after{animation-duration:1ms!important;animation-iteration-count:1!important;transition-duration:1ms!important}}
/* the sheet that asks before anything on this device is kept or removed (sign-in to another account, Sign out): the card's own look */
.sg-sheet{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;padding:16px;background:color-mix(in srgb,#000 45%,transparent)}
.sg-sheet .sg-card{max-width:440px;max-height:100%;overflow:auto;text-align:left}
.sg-sheet h2{font-size:22px;line-height:1.2}
.sg-sheet .sg-sub b{color:var(--ink);overflow-wrap:anywhere}
.sg-acts{display:flex;flex-wrap:wrap;gap:10px;margin-top:4px}
.sg-acts .sg-btn{flex:1 1 150px}
.sg-sheet .sg-agree b{font-weight:600}
.sg-sheet .sg-agree small{display:block;color:var(--muted);font-size:13px;margin-top:2px}
@media (max-width:700px){.sg-sheet{align-items:flex-end}.sg-acts{flex-direction:column-reverse}.sg-acts .sg-btn{flex:none;width:100%}}
`;

/* the card's styles go into the production page's own style sheet, so the card never shows unstyled */
function patch(s){
  s=once(s,"</style>",CSS+"</style>");
  return s;
}

var WORK=["Barista","Retail","Warehouse","Front desk","Cook","Delivery","Office","Healthcare"];
var GSTART="uaply.gstart";            /* the same top-page key shared/uaply-nav.js reads when a tab comes back from Google */
var PENDING="uaply.signup.pending";   /* top-page sessionStorage: what the card held when this tab left for Google */
var CODEK="uaply.signup.code";        /* top-page sessionStorage: the code step (which address, which step, when the code was sent) */
var CODE_MS=10*60e3;                  /* a code works for 10 minutes (auth_api.CODE_SECONDS) */

function apply(w,host){
  var d=w.document,A=w.__uaply,B=w.__uaplyAuthApi;
  /* fail loudly: the sandbox shows "Problem: ..." and the console says which hook is missing; the old card keeps working */
  if(!A||!B||typeof B.post!=="function"||typeof B.srv!=="function"){
    var why="sign-up v2: the Account screen hooks are missing from shared/uaply-nav.js (needs Bottom navigation, and __uaplyAuthApi)";
    try{(host&&host.defaultView||window).console.error("[uaply] "+why)}catch(e){}
    throw new Error(why);
  }
  var OWN=(w.__uaplyKey||"uaply")+".signup";   /* this device: the first and last name, for the greeting */

  /* ---------- small helpers ---------- */
  function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]})}
  var _id=0;function uid(p){return "sg-"+(p||"u")+(++_id)}
  function RM(){try{return w.matchMedia("(prefers-reduced-motion: reduce)").matches}catch(e){return false}}
  function fx(el){if(!el)return;try{el.focus({preventScroll:true})}catch(e){try{el.focus()}catch(_){}}}
  /* error focus: bring the problem into view first (a phone shows less than the card), then focus it. Headings keep plain fx() */
  function fxs(el){if(!el)return;try{el.scrollIntoView({block:"center",behavior:RM()?"auto":"smooth"})}catch(e){}fx(el)}
  function h(html){var t=d.createElement("template");t.innerHTML=html.trim();return t.content.firstElementChild}
  function topStore(){try{return w.top.sessionStorage}catch(e){return null}}
  function getPending(){try{var s=topStore(),p=s&&JSON.parse(s.getItem(PENDING));return p&&typeof p==="object"&&Date.now()-(+p.at||0)<15*60e3?p:null}catch(e){return null}}
  function setPending(p){try{var s=topStore();if(!s)return;if(p)s.setItem(PENDING,JSON.stringify(p));else s.removeItem(PENDING)}catch(e){}}
  /* the code step outlives a reload (a refresh, Back then Forward, a phone that dropped the tab while the person read their email): this
     tab remembers which address the code went to, for which step, and when; never the code. The card then offers "Type the code" for
     10 minutes instead of a new code (each new code cancels the last and counts toward the limit of 3 an hour) */
  function getCodeStep(){try{var s=topStore(),c=s&&JSON.parse(s.getItem(CODEK));return c&&typeof c==="object"&&typeof c.email==="string"&&(c.kind==="up"||c.kind==="in")&&Date.now()-(+c.at||0)<CODE_MS?c:null}catch(e){return null}}
  function setCodeStep(c){try{var s=topStore();if(!s)return;if(c)s.setItem(CODEK,JSON.stringify(c));else s.removeItem(CODEK)}catch(e){}}
  function ownGet(){try{var o=JSON.parse(w.localStorage.getItem(OWN));return o&&typeof o==="object"?o:{}}catch(e){return {}}}
  function ownSet(o){try{w.localStorage.setItem(OWN,JSON.stringify(o))}catch(e){}}

  /* ---------- whose profile this device holds (PR #49 finding 5, PR #50's clean start, Saif's sign-out note of Oct 22) ----------
     UAply keeps the profile, phone, resume, saved answers and the swipe list on the device only. The device remembers which account last
     used them (OWNER: the signed-in account's email, never an email typed in the profile) and, after a Keep, the other accounts that share
     them. A sign-in to any other account, new or existing, by code or by Google, first asks in a sheet: Keep (applications go out with the
     profile saved here as it is, and the Account screen says whose name it carries) or Start fresh (those details are removed from this
     device). Nothing is removed, and no waiting application is sent, before that choice. */
  var DK=w.__uaplyKey||"uaply",OWNER=DK+".signup.owner";
  function lc(s){return String(s||"").trim().toLowerCase()}
  function lsJSON(k){try{var o=JSON.parse(w.localStorage.getItem(k));return o&&typeof o==="object"?o:null}catch(e){return null}}
  function ownerGet(){var o=lsJSON(OWNER);return o&&typeof o.email==="string"&&o.email?o:null}
  function emList(a){var seen={};return (Array.isArray(a)?a:[]).map(lc).filter(function(x){if(!x||seen[x])return false;seen[x]=1;return true}).slice(0,20)}
  /* {email: the account using the details now, with: the other accounts that share them after a Keep, keptBy: the accounts that chose Keep} */
  function ownerSet(email,shared,keptBy){
    email=lc(email).slice(0,200);
    try{if(!email){w.localStorage.removeItem(OWNER);return}
      var kb=emList(keptBy);
      w.localStorage.setItem(OWNER,JSON.stringify({email:email,kept:kb.indexOf(email)>-1,"with":emList(shared).filter(function(x){return x!==email}),keptBy:kb}))}catch(e){}
  }
  function keptByOf(o){return !o?[]:Array.isArray(o.keptBy)?emList(o.keptBy):o.kept?[lc(o.email)]:[]}
  function ownerKept(o){return !!o&&keptByOf(o).indexOf(lc(o.email))>-1}
  /* anything personal on this device: a profile someone filled in, a phone, a resume, links, an address, saved answers, a swipe, a saved location */
  function deviceHasData(){
    var p=A.S.profile||{},a=lsJSON(DK+".acct")||{},ad=a.addr||{},an=lsJSON(DK+".answers"),lo=lsJSON(DK+".loc"),le=A.S.learn;
    return !!((p.custom&&(p.name||p.email||p.title||p.loc||(p.skills||[]).length))||a.phone||a.resumeName||a.resumeData||a.resumeUrl||a.linkedin||a.portfolio||
      a.summary||a.cover||ad.street||ad.zip||Object.keys(A.S.decisions||{}).length||(an&&Object.keys(an).length)||(lo&&typeof lo.lat==="number")||
      (le&&Array.isArray(le.ev)&&le.ev.length));
  }
  /* the accounts the saved details belong to: the one that last used them here, and any that share them after Keep. A device from before
     this record: the account whose name the card saved with its email. An email typed in Profile setup is never used: a device nobody has
     signed in on yet is taken as it is by the first account (the device cannot tell that person from another) */
  function holders(){var o=ownerGet();if(o)return emList([o.email].concat(o["with"]||[]));var oe=lc(ownGet().email);return oe?[oe]:[]}
  function otherProfile(email){email=lc(email);var hs=holders();return !!email&&hs.length>0&&hs.indexOf(email)<0&&deviceHasData()}
  /* the same person, someone the profile is shared with, or a device with nothing of anyone's: this account now uses what is here (a
     profile with no email takes this one). Sharing is remembered only among the accounts that already share. An account that shares the
     profile applies with its own address: the live server sends an application straight to an employer only when the profile's email is
     the signed-in account's (uaply_api.py, "Use your account email in Profile setup"), so another sharer's email is replaced */
  function adopt(email){
    var p=A.S.profile||{},em=lc(email),hs=holders(),o=ownerGet(),shared=!!o&&hs.indexOf(em)>-1,pe=lc(p.email);
    if(p.custom&&(!pe||(shared&&pe!==em&&hs.indexOf(pe)>-1))){p.email=String(email).slice(0,200);commit()}
    if(shared)ownerSet(em,hs,keptByOf(o));else ownerSet(em,[],[]);
  }
  /* Keep: this account shares the profile saved here with the accounts that already had it (each of them signs in again without the
     question). The name, phone and resume are shared; the email becomes this account's own, as the sheet says (see adopt) */
  function keepFor(email){
    var o=ownerGet(),p=A.S.profile||{};ownerSet(email,holders(),keptByOf(o).concat([lc(email)]));
    if(p.custom&&lc(p.email)!==lc(email)){p.email=String(email).slice(0,200);commit()}
  }
  /* Start fresh, or Remove my details at Sign out: the profile, phone, links, resume, work authorization and other answers, the address,
     saved form answers, the agreement to apply, the help chat's record (with its agreement to the AI notice), the swipe list (Applied and passed jobs, with their application notes), what "Learns from
     your swipes" learned (as its own Reset does), the plan and payments shown on this device, the company and keyword filters, and the
     saved device location leave this device. The location the app already read stays in use until UAply next opens (the sheet says so) */
  function wipeDevice(email){
    email=lc(email).slice(0,200);
    A.S.profile={name:"",title:"",years:0,edu:"",skills:[],salary:0,loc:"",modes:{remote:false,hybrid:false,onsite:false},reloc:false,email:email,custom:true};
    A.S.decisions={};A.S.history=[];
    var le=A.S.learn;if(le&&typeof le==="object"&&Array.isArray(le.ev)){le.ev=[];le.n=0;le.ver=(+le.ver|0)+1}
    B.acct(function(a){a.phone=a.linkedin=a.portfolio=a.summary=a.auth=a.notice=a.cover=a.resumeName=a.resumeData=a.resumeUrl="";a.resumeSize=0;a.titles=[];a.apps={};
      a.eeo={auth:"",sponsor:"",veteran:"",hisp:"",race:[],disability:"",gender:""};a.addr={street:"",unit:"",state:"",zip:""};
      a.plan="trial";a.pay=[];a.since=Date.now();a.renews=0;a.canceled=false;a.fCo="";a.fKw=""});
    [".answers",".answersAsked",".consent",".loc",".chat"].forEach(function(x){try{w.localStorage.removeItem(DK+x)}catch(e){}});
    if(email)ownSet({first:"",last:"",email:email});else try{w.localStorage.removeItem(OWN)}catch(e){}
    ownerSet(email);commit();
  }
  /* while the Keep / Start fresh question is open, an application waiting to be sent (shared/uaply-live.js sends those again 1.5 s after
     the jobs load, and every 30 s while the server is out of reach) would go out under the account that just signed in with the profile
     saved here: it is held. Keep sends it as before; Start fresh drops it (its swipe is gone too, so nothing is sent later). The hold also
     covers a page that opens with a session, until the start-up check below has looked. A dropped one is answered "not sent" (409, code
     "preview": shared/uaply-live.js then takes the swipe back with no button and queues nothing), never a failed request, which uaply-live
     reads as "could not reach the server" and promises to send later */
  var holdApply=false,heldApply=[],fetch0=w.fetch;
  if(typeof fetch0==="function")w.fetch=function(u){
    var url=String(u&&typeof u==="object"&&u.url?u.url:u||""),args=arguments,ap=/^(?:https?:\/\/[^\/]+)?\/api\/apply(?:[?#]|$)/.test(url);
    if(ap&&!holdApply)try{watchAs()}catch(e){}   /* a sign-in the page has not looked at yet: look first (below), so the question can hold this */
    if(holdApply&&ap)return new Promise(function(res,rej){heldApply.push({go:function(){fetch0.apply(w,args).then(res,rej)},drop:function(why){res(notSent(why))}})});
    return fetch0.apply(w,args);
  };
  function notSent(why){var b=JSON.stringify({error:why,code:"preview"});try{return new w.Response(b,{status:409,headers:{"Content-Type":"application/json"}})}catch(e){return {ok:false,status:409,json:function(){return Promise.resolve(JSON.parse(b))}}}}
  var FRESHNS="Not sent: you chose Start fresh.",OUTNS="Not sent: you signed out before choosing Keep or Start fresh.";
  function releaseApply(send,why){holdApply=false;var q=heldApply;heldApply=[];q.forEach(function(x){try{if(send)x.go();else x.drop(why||FRESHNS)}catch(e){}})}
  /* a sheet in the card's own style (never the browser's confirm box): a choice must be made, focus stays inside it */
  var sheetOn=null,sheetCtl=null;
  function closeSheet(){var r=sheetOn;sheetOn=null;sheetCtl=null;if(r&&r.parentNode)r.parentNode.removeChild(r)}
  function sheetStops(root){return [].slice.call(root.querySelectorAll("button,input,a[href]")).filter(function(x){return !x.disabled})}
  /* while a sheet is open it owns the keyboard, on the window in the capture phase so it runs before anything on the page: the swipe
     deck's keys (ArrowLeft, ArrowRight, Z) and every other key aimed behind the sheet never arrive there (a reload with the question
     open put it over the deck, and one ArrowRight applied with the other person's profile), Tab stays inside, Esc is the sheet's own */
  w.addEventListener("keydown",function(e){
    var root=sheetOn;if(!root)return;
    var k=e.key,t=e.target,inside=!!(t&&t.nodeType===1&&root.contains(t));
    if(k==="Escape"){e.preventDefault();e.stopPropagation();if(sheetCtl&&sheetCtl.escNo)sheetCtl.done(false);return}
    if(k==="Tab"){
      var f=sheetStops(root),first=f[0],last=f[f.length-1],ae=d.activeElement;
      if(!inside||!ae||!root.contains(ae)){e.preventDefault();e.stopPropagation();fx(e.shiftKey?last:first);return}
      if(e.shiftKey&&(ae===first||ae.tagName==="H2")){e.preventDefault();fx(last)}
      else if(!e.shiftKey&&ae===last){e.preventDefault();fx(first)}
      return;
    }
    if(!inside){e.preventDefault();e.stopPropagation();return}
    if(k==="ArrowLeft"||k==="ArrowRight"||k==="z"||k==="Z"){e.stopPropagation();if(t.tagName!=="INPUT"||t.type==="checkbox")e.preventDefault()}
  },true);
  /* focus that something else moves behind the open sheet comes back to it */
  d.addEventListener("focusin",function(e){var root=sheetOn;if(root&&e.target&&e.target.nodeType===1&&!root.contains(e.target)){var f=sheetStops(root);fx(f[0]||root.querySelector("h2"))}},true);
  function sheet(o){
    closeSheet();
    var hid=uid("sh"),bid=uid("sb");
    var root=h('<div class="sg sg-sheet"><section class="sg-card sg-pop" role="alertdialog" aria-modal="true" aria-labelledby="'+hid+'" aria-describedby="'+bid+'">'+
      '<h2 id="'+hid+'" tabindex="-1">'+o.title+'</h2><div class="sg-stack" id="'+bid+'">'+o.body+'</div>'+
      '<div class="sg-acts"><button type="button" class="sg-btn ghost" data-sh="no">'+o.no+'</button><button type="button" class="sg-btn pri" data-sh="yes">'+o.yes+'</button></div></section></div>');
    var prev=d.activeElement;d.body.appendChild(root);sheetOn=root;
    /* afterwards focus goes back where it was, unless what the choice did put it somewhere else */
    function done(yes){if(sheetOn!==root)return;closeSheet();o.then(yes,root);var ae=d.activeElement;if(prev&&prev.isConnected&&(!ae||ae===d.body))fx(prev)}
    sheetCtl={escNo:!!o.escNo,done:done};
    root.querySelector('[data-sh="yes"]').onclick=function(){done(true)};
    root.querySelector('[data-sh="no"]').onclick=function(){done(false)};
    /* a press on the dark background (or on the sheet's text) never takes focus out of the sheet; buttons and the tick box still work */
    root.addEventListener("mousedown",function(e){var t=e.target;if(!(t&&t.closest&&t.closest("button,input,a[href],label")))e.preventDefault()});
    fx(root.querySelector("h2"));
    return root;
  }
  /* before the choice the sheet shows nothing of the other person's details (not their name): only that the device holds another profile */
  function askFresh(email,then){
    holdApply=true;
    sheet({title:"This device holds another person’s profile.",
      body:'<p class="sg-sub">Start fresh for <b>'+esc(email)+'</b>?</p>'+
        '<p class="sg-fine">UAply keeps profiles on the device only.</p>'+
        '<p class="sg-fine"><b>Start fresh</b> removes that profile, phone, resume, saved answers and swipe list (Applied) from this device, with what UAply learned from those swipes, the plan shown here and the saved location (jobs stop being sorted by it the next time UAply opens). '+
        '<b>Keep</b> uses that profile for your applications: its name, phone and resume, with your account email.</p>',
      no:"Keep",yes:"Start fresh",then:function(fresh){then(fresh);releaseApply(!fresh)}});
  }
  /* every sign-in passes here once the session is real; go() carries on with the card */
  function guard(email,go){
    email=lc(email);
    if(!otherProfile(email)){adopt(email);releaseApply(true);go();return}
    V.view="ask";render();
    askFresh(email,function(fresh){
      if(fresh){wipeDevice(email);V.cleared=true;V.kept=false}else{keepFor(email);V.kept=true;V.cleared=false}
      go();
    });
  }
  /* "Your applications from this device go out with ...": after Keep, the Account screen says whose profile it is */
  function keptHTML(user,cls){
    var o=ownerGet(),em=lc(user&&user.email);if(!ownerKept(o)||!em||o.email!==em)return "";
    var p=A.S.profile||{},nm=p.custom?String(p.name||"").trim():"",own=lc(p.email)===em;
    /* the email is this account's own after Keep; if another one was typed in Profile setup since, the line says so without showing it */
    return '<p class="'+cls+'" style="margin:0">You kept the profile saved on this device, so your applications from here go out as <b>'+(nm?esc(nm):"no name yet")+'</b>, with that profile’s phone and resume and '+
      (own?'your account email':'the email in Profile setup (applications sent straight to an employer need your account email there)')+'. Change it in Profile setup.</p>';
  }
  /* the page opened with a session already (a reload, or a sign-in from before this check): the same question when the device's details
     belong to another account; with no record yet, this account takes the device as it is */
  function startCheck(user){
    if(!user||!user.email||V.user||V.view==="ask"||sheetOn||getPending())return;
    var em=lc(user.email);
    if(!otherProfile(em)){adopt(em);return}
    askFresh(em,function(fresh){if(fresh)wipeDevice(em);else keepFor(em);try{B.redraw()}catch(e){}});
  }
  /* a device holding someone's details holds applications from the start, until the server says who is signed in and the check has run
     (a return from Google waits for the card's own check, guard()) */
  holdApply=holders().length>0&&deviceHasData();
  /* after the start-up check, a sign-in that did not come through the card (the app's own password sign-in in shared/uaply-nav.js, when
     the server has code sign-in off, or a sign-in in another tab) gets the same check as soon as the page sees the new account. The card's
     own sign-ins are skipped by startCheck (V.user, the "ask" view, a return from Google) because guard() looks at those */
  var seenAs=null;
  function watchAs(){if(seenAs===null)return;var u=srv().user,em=lc(u&&u.email);if(em===seenAs)return;seenAs=em;if(em)startCheck(u)}
  (function(){var n=0,iv=setInterval(function(){var s=srv();if(!s.up&&++n<120)return;clearInterval(iv);if(s.user)startCheck(s.user);
    seenAs=lc(s.user&&s.user.email);setInterval(watchAs,500);
    if(!sheetOn&&V.view!=="ask"&&!(s.user&&getPending()))releaseApply(true)},500)})();

  /* ---------- Sign out (the app's button, shared/uaply-nav.js "sout"): the choice to remove this person's details from this device ----------
     Saif's review (Oct 22, 2:39 AM). The default keeps them. They are removed only once the server has ended the session. */
  var soutPass=false,wipeAt=0;
  d.addEventListener("click",function(e){
    if(soutPass)return;
    var b=e.target&&e.target.closest&&e.target.closest('#acctSec [data-auth="sout"]');if(!b)return;
    e.preventDefault();e.stopPropagation();
    var u=srv().user||{};
    sheet({title:"Sign out of UAply?",
      body:'<p class="sg-sub">Signed in as <b>'+esc(u.email||"")+'</b>.</p>'+
        '<label class="sg-agree"><input type="checkbox" class="sg-rm" data-f="rm"><span><b>Remove my details from this device</b><small>Your profile, phone, resume, saved answers and swipe list (Applied) on this device, with what UAply learned from your swipes, the plan shown here and the saved location. Your account stays.</small></span></label>'+
        '<p class="sg-fine">Left unticked, they stay on this device for your next sign-in.</p>',
      no:"Cancel",yes:"Sign out",escNo:true,then:function(yes,root){
        if(!yes)return;
        var rm=!!(root.querySelector(".sg-rm")||{}).checked,nb=b.isConnected?b:d.querySelector('#acctSec [data-auth="sout"]');
        if(!nb)return;
        wipeAt=rm?Date.now():0;
        soutPass=true;try{nb.click()}finally{soutPass=false}
        if(rm){var k=0,iv=setInterval(function(){if(!srv().user){clearInterval(iv);signedOut()}else if(++k>100){clearInterval(iv);wipeAt=0}},150)}
      }});
  },true);
  /* the session ended: when this person asked, their details leave this device now (never while the server still has them signed in) */
  function signedOut(){
    if(!wipeAt||Date.now()-wipeAt>15e3)return;
    wipeAt=0;wipeDevice("");
    setTimeout(function(){msg("Signed out. Your details were removed from this device.")},0);
  }

  /* the app's readiness rule (shared/uaply-nav.js): null when that nav has no such rule */
  function ready(){try{return typeof w.__uaplyReadiness==="function"?w.__uaplyReadiness():null}catch(e){return null}}
  function hasPR(){var r=ready();return !!(r&&r.items.some(function(i){return (i.k==="phone"||i.k==="resume")&&i.done}))}
  function joinAnd(a){return a.length<2?(a[0]||""):a.slice(0,-1).join(", ")+" and "+a[a.length-1]}
  var FIXL={name:"Add your name",email:"Add your email",phone:"Add a phone number",resume:"Add a resume"};
  function fixesHTML(r){return '<div class="sg-fixes">'+r.items.filter(function(i){return i.needed&&!i.done&&FIXL[i.k]}).map(function(i){return '<button type="button" class="sg-btn ghost" data-ready="'+i.k+'">'+FIXL[i.k]+'</button>'}).join("")+'</div>'}
  /* a code sign-in that first proves the inbox takes off a Google login Google did not vouch for (auth_api login_with_code, googleRemoved):
     from then on this card never offers that person Google, which would answer "email_in_use" */
  var gGone="";
  function gOff(em){var u=V.user||srv().user||{};return !!gGone&&gGone===String(em||u.email||"").toLowerCase()}
  function PWGONE(){return "This account had a password that was never confirmed by email, so it was removed to keep the account yours. Sign in with an emailed code"+(gOff()?".":" or with Google.")}
  var GGONE="Google sign-in was taken off this account to keep it yours. Sign in with an emailed code.";
  var SVG=function(p){return '<svg class="sg-i" viewBox="0 0 24 24" aria-hidden="true">'+p+'</svg>'};
  var I={check:SVG('<path d="M5 12.5l4.5 4.5L19 7.5"/>'),chev:SVG('<path d="M9 6l6 6-6 6"/>'),
    pin:SVG('<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>')};
  var LOGO='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
  /* Google's "G" stays still while Google opens (Google's brand rules); only the label changes */
  var GLOGO='<svg viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>';
  var LB="/legal/";   /* the Terms and Privacy Policy pages on this server */
  var AGREE='I am 18 or older and agree to the <a href="'+LB+'terms.html" target="_blank" rel="noopener noreferrer">Terms</a> and <a href="'+LB+'privacy.html" target="_blank" rel="noopener noreferrer">Privacy&nbsp;Policy</a>';

  /* ---------- the email box: validation, the typo fix ("Did you mean gmail.com?"), throwaway addresses ---------- */
  var DOMS=["gmail.com","yahoo.com","outlook.com","hotmail.com","icloud.com","aol.com","live.com","proton.me","msn.com","comcast.net"];
  var DISP=["mailinator.com","10minutemail.com","guerrillamail.com","tempmail.com","temp-mail.org","yopmail.com","trashmail.com","sharklasers.com"];
  function lev(a,b){var m=[],i,j;for(i=0;i<=a.length;i++)m[i]=[i];for(j=0;j<=b.length;j++)m[0][j]=j;for(i=1;i<=a.length;i++)for(j=1;j<=b.length;j++)m[i][j]=Math.min(m[i-1][j]+1,m[i][j-1]+1,m[i-1][j-1]+(a[i-1]===b[j-1]?0:1));return m[a.length][b.length]}
  function checkEmail(v){
    v=v.trim();if(!v)return {s:"empty",msg:"Enter your email address."};
    var at=v.lastIndexOf("@");
    if(at<1)return {s:"bad",msg:"Add the @ and the rest of your address."};
    var dom=v.slice(at+1).toLowerCase();
    if(!/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(v))return {s:"bad",msg:"That email looks unfinished. Check the part after the @."};
    if(DISP.indexOf(dom)>-1)return {s:"bad",msg:"Please use an email address you’ll keep. Temporary addresses can’t be used for job applications."};
    if(DOMS.indexOf(dom)<0){var best=null;DOMS.forEach(function(x){var k=lev(dom,x);if(k>0&&k<=2&&(!best||k<best.k))best={x:x,k:k}});if(best)return {s:"typo",fix:v.slice(0,at+1)+best.x}}
    return {s:"ok"};
  }
  function emailFieldHTML(val){var id=uid("em");return '<div class="sg-fld" data-email><label for="'+id+'">Email</label><div class="sg-in"><input id="'+id+'" data-f="email" type="email" inputmode="email" enterkeyhint="go" autocomplete="email" autocapitalize="off" spellcheck="false" maxlength="200" placeholder="you@example.com" aria-describedby="'+id+'m" value="'+esc(val||"")+'"><span class="sg-tick" aria-hidden="true">'+I.check+'</span></div><p class="sg-fmsg" id="'+id+'m" aria-live="polite"></p></div>'}
  function textFieldHTML(label,ac,ph,val,cls,ekh){var id=uid("tx");return '<div class="sg-fld'+(cls?" "+cls:"")+'"><label for="'+id+'">'+label+'</label><div class="sg-in"><input id="'+id+'" data-f="'+esc(label)+'" type="text" maxlength="80" autocomplete="'+ac+'"'+(ekh?' enterkeyhint="'+ekh+'"':'')+' placeholder="'+esc(ph||"")+'" aria-describedby="'+id+'m" value="'+esc(val||"")+'"><span class="sg-tick" aria-hidden="true">'+I.check+'</span></div><p class="sg-fmsg" id="'+id+'m" aria-live="polite"></p></div>'}
  /* "reward early, punish late": an error waits for blur or submit, but clears the moment the address becomes valid */
  function wireEmail(fld,onChange){
    var inp=fld.querySelector("input"),m=fld.querySelector(".sg-fmsg"),tmr;
    function paint(r,strict){
      var good=r.s==="ok"||r.s==="typo";
      fld.classList.toggle("good",good);
      var showBad=r.s==="bad"||(strict&&r.s==="empty");
      if(showBad&&(strict||fld.classList.contains("bad"))){fld.classList.add("bad");inp.setAttribute("aria-invalid","true");m.textContent=r.msg;return}
      if(good||r.s==="empty"){fld.classList.remove("bad");inp.removeAttribute("aria-invalid")}
      if(r.s==="typo"){m.innerHTML='Did you mean <button type="button" class="sg-fix">'+esc(r.fix)+'</button>?';m.querySelector(".sg-fix").onclick=function(){inp.value=r.fix;run(true);fx(inp)};return}
      m.textContent=fld.classList.contains("bad")?m.textContent:"";
    }
    function run(now){var r=checkEmail(inp.value);clearTimeout(tmr);if(now)paint(r,false);else{if(r.s==="ok"||r.s==="empty"||fld.classList.contains("bad"))paint(r,false);else{fld.classList.remove("good");m.textContent="";tmr=setTimeout(function(){if(inp.isConnected)paint(checkEmail(inp.value),false)},550)}}if(onChange)onChange(inp.value.trim())}
    inp.addEventListener("input",function(){run(false)});
    inp.addEventListener("blur",function(){var r=checkEmail(inp.value);paint(r,!!inp.value.trim()&&r.s==="bad")});
    if(inp.value)paint(checkEmail(inp.value),false);
    return {input:inp,value:function(){return inp.value.trim()},
      error:function(t){fld.classList.add("bad");inp.setAttribute("aria-invalid","true");m.textContent=t},
      validate:function(){var r=checkEmail(inp.value);paint(r,true);if(r.s==="bad"||r.s==="empty"){fld.classList.remove("sg-shake");void fld.offsetWidth;if(!RM())fld.classList.add("sg-shake");return false}return true}};
  }
  /* a required text box: the error shows on submit and clears as soon as something is typed */
  function wireReq(fld,msg){
    var inp=fld.querySelector("input"),m=fld.querySelector(".sg-fmsg");
    function set(bad){fld.classList.toggle("bad",bad);fld.classList.toggle("good",!bad&&!!inp.value.trim());if(bad)inp.setAttribute("aria-invalid","true");else inp.removeAttribute("aria-invalid");m.textContent=bad?msg:""}
    inp.addEventListener("input",function(){if(fld.classList.contains("bad")&&inp.value.trim())set(false);else fld.classList.toggle("good",!!inp.value.trim())});
    if(inp.value.trim())fld.classList.add("good");
    return {input:inp,value:function(){return inp.value.trim().slice(0,60)},validate:function(){var ok=!!inp.value.trim();set(!ok);return ok}};
  }

  /* ---------- state: survives the Account screen being redrawn (the server's start-up answers redraw it) ---------- */
  var V={view:"up",email:"",first:"",last:"",agreed:false,gWait:false,err:"",kind:"",delivery:"",steps:[],k:0,work:[],other:"",where:"",remote:false,near:false,pvOpen:false,viaG:false,isNew:false,typedName:false,pwGone:false,user:null};
  var codeOn=null;   /* the server signs in by emailed code (providers.codeSignin): null until it answers */
  var host0=null,back=null,wasIn=false;
  /* after a sign-out the next person on this device starts from an empty card: no email, no name, the box unticked (their tick must be
     their own), no saved Google trip, nothing left from the questions */
  function forget(){
    resetV();V.view="up";V.email=V.first=V.last="";V.agreed=false;V.gWait=false;V.err="";V.errTop=false;V.user=null;V.kind="";V.delivery="";V.cd=null;V.pvOpen=false;
    gGone="";lastF=null;wasIn=false;setPending(null);setCodeStep(null);V.sentAt=0;V.noSend=false;
  }
  /* the card field that had focus (data-f), so a redraw from the app (a late start-up answer on a slow connection replaces the Account
     screen) puts the person back in the same box with the same caret, instead of dropping focus and closing a phone's keyboard */
  var lastF=null;
  function selOf(t){try{return [t.selectionStart,t.selectionEnd]}catch(e){return [null,null]}}
  d.addEventListener("focusin",function(e){var t=e.target,f=host0&&host0.contains(t)&&t.getAttribute&&t.getAttribute("data-f");
    if(!f){lastF=null;return}var sl=selOf(t);lastF={f:f,view:V.view,a:sl[0],b:sl[1]}});
  /* typing counts too (a window that is not in front gets no focus events, but the person may still type) */
  ["input","keyup","mouseup","select"].forEach(function(ev){d.addEventListener(ev,function(e){var t=e.target,f=host0&&host0.contains(t)&&t.getAttribute&&t.getAttribute("data-f");
    if(f&&t===d.activeElement){var sl=selOf(t);lastF={f:f,view:V.view,a:sl[0],b:sl[1]}}},true)});
  /* the person left the box on purpose (tapped outside it, not a redraw): nothing to put back */
  d.addEventListener("focusout",function(e){var t=e.target;setTimeout(function(){if(t.isConnected&&(!d.activeElement||d.activeElement===d.body))lastF=null},0)});
  function restoreFocus(){
    var f=lastF;if(!f||f.view!==V.view||!host0)return;
    var ae=d.activeElement;if(ae&&ae!==d.body&&ae.isConnected)return;
    var el=host0.querySelector('[data-f="'+f.f.replace(/["\\]/g,"")+'"]');if(!el||el.disabled)return;
    fx(el);
    if(f.a!=null)try{el.setSelectionRange(f.a,f.b)}catch(e){}
    else if(el.type==="email")try{el.type="text";el.setSelectionRange(el.value.length,el.value.length);el.type="email"}catch(e){}
    if(lastF){lastF.a=f.a;lastF.b=f.b}
  }
  function srv(){return B.srv()}
  function msg(t){try{B.msg(t||"")}catch(e){}}

  /* ---------- the Account screen asks for the card (hook in renderAcct) ---------- */
  w.__uaplySignCard=function(el,user){
    if(!user)signedOut();   /* a Sign out that asked to remove this person's details: the session has ended, so now */
    /* signed out since the last drawing; an application held for a question nobody answered is not sent */
    if(user)wasIn=true;else if(wasIn||V.user){forget();closeSheet();if(holdApply||heldApply.length)releaseApply(false,OUTNS)}
    var pend=getPending();
    if(codeOn===false)return false;
    if(codeOn===null&&!pend){
      /* the server has not said yet whether it signs in by code: hold the card's place (nothing to type into, so nothing typed is lost
         when the answer redraws the screen); signed in, the app's own card as before */
      if(user)return false;
      host0=el;back=null;el.className="sg";el.innerHTML='<div class="sg-wait" aria-busy="true"><span class="sg-vh">Loading…</span></div>';
      return true;
    }
    host0=el;   /* back from Google before the server's answer: the card already knew */
    if(user){
      if(V.view==="q"||V.view==="signedin"||V.view==="ask"||(V.view==="code"&&V.kind==="g")){render();restoreFocus();return true}
      if(pend){startAfterGoogle(user,pend);return true}
      return false;   /* signed in, nothing to ask: the app's own signed-in card */
    }
    if(V.view!=="up"&&V.view!=="in"&&!(V.view==="code"&&V.kind!=="g"))V.view="up";   /* signed out in the middle of the questions */
    render();restoreFocus();
    return true;
  };
  /* back from Google (hook in googleReturn): errors show next to the box they are about; a sign-in was already handled above */
  function mine(){return !!(host0&&host0.isConnected&&acctOn()&&(V.view==="q"||V.view==="signedin"||(V.view==="code"&&V.kind==="g")))}
  w.__uaplySignReturn=function(er,signed,pwGone){
    var pend=getPending();
    if(signed&&pwGone)V.pwGone=true;   /* Google proved the inbox and the server removed a password nobody had proven: the card says so */
    if(!pend&&!mine())return false;
    if(er){
      setPending(null);if(!sheetOn)releaseApply(true);
      if(pend){V.first=pend.first||V.first;V.last=pend.last||V.last;V.email=pend.email||V.email;V.agreed=!!pend.agreed}
      if(er==="agree_owner"){
        /* Google proved this person owns the address, which has an account someone opened and never finished: their own tick, then Google */
        V.view="up";V.gWait=true;V.err="This email has a UAply account that was never finished. Tick the box to confirm you’re 18 or older and agree, then Continue with Google.";
      }else if(er==="agree"){
        /* a new person pressed Google on "Welcome back": the server needs the one tick first, so they land on Create your account */
        V.view="up";V.gWait=true;V.err=pend&&pend.mode==="in"?"This Google account has no UAply account yet. Tick the box, then Continue with Google.":"Tick the box first, then Continue with Google.";
      }else{
        V.view=pend&&pend.mode==="in"?"in":"up";
        V.err=({cancelled:"Google sign-in was cancelled.",expired:"That Google sign-in expired or could not be checked. Try again.",unverified:"Google says that email address is not verified, so UAply cannot use it.",
          off:"Google sign-in is not switched on.",email_in_use:"That email already has a UAply account. Use Email me a code to sign in to it.",disposable:"Please use an email address you’ll keep. Temporary addresses can’t be used for job applications."})[er]||"Google sign-in did not work. Try again, or use your email.";
        V.errTop=true;
      }
      render(true);
      return true;
    }
    if(signed&&mine()){if(pwGone)render();return true}
    return false;
  };
  function acctOn(){var a=d.getElementById("acctSec");return !!(a&&a.classList.contains("sgnOn"))}

  /* is the no-password sign-in switched on for this server? (sandbox only; the old card stays everywhere else) */
  w.fetch("/api/auth/providers",{credentials:"same-origin"}).then(function(r){return r.ok?r.json():null}).then(function(j){
    var was=codeOn;codeOn=!!(j&&j.codeSignin);
    if(codeOn!==was)B.redraw();
  }).catch(function(){var was=codeOn;codeOn=false;if(was!==false)B.redraw()});
  /* the app's own signed-in card says how a person with no password signs in: here that is an emailed code (or Google), not "Forgot password" */
  w.__uaplyNoPwNote=function(user){
    if(codeOn!==true)return "";
    var s=srv(),g=!s.hideGoogle&&(s.google||s.testInbox)&&!gOff(user&&user.email);
    return '<p class="note" style="margin:0">You sign in with an emailed code'+(g?' or with Google':'')+'. No password needed.</p>'+keptHTML(user,"note");
  };

  /* ---------- drawing ---------- */
  function wide(on){var a=d.getElementById("acctSec");if(a)a.classList.toggle("sgWide",!!on)}
  function shell(inner){
    wide(false);
    host0.className="sg";
    host0.innerHTML='<div class="sg-shell"><div class="sg-bb" aria-hidden="true"><span class="sg-lg">'+LOGO+'</span><span class="sg-wm">UAply</span></div><section class="sg-card sg-pop">'+inner+'</section></div>';
    return host0.querySelector(".sg-card");
  }
  function render(focus){
    if(!host0||!host0.isConnected)return;
    msg("");
    if(V.view==="in")signin(focus);
    else if(V.view==="code")code(focus);
    else if(V.view==="q")profile(focus);
    else if(V.view==="signedin")signedIn(focus);
    else if(V.view==="ask")askWait();
    else signup(focus);
  }
  /* Esc goes back wherever there is a "back"; one listener on the Account screen, so redraws never stack them */
  d.addEventListener("keydown",function(e){if(e.key==="Escape"&&back&&acctOn()&&host0&&host0.contains(e.target)){e.preventDefault();back()}});

  /* the Google part of a card: our own button (full-page sign-in), Google's button (no client secret: the owner's computer), the
     owner-only setup button, or nothing (no Google on this server, or inside the phone apps where Google refuses to sign in) */
  function googleHTML(){
    var s=srv();
    if(s.hideGoogle)return "";
    if(s.google&&s.redirect)return '<button type="button" class="sg-btn g wide" data-sg="google">'+GLOGO+'<span class="sg-gl">Continue with Google</span></button>';
    if(s.google&&s.clientId)return '<div id="gBtn" class="sg-gis"></div>';
    if(s.testInbox)return '<button type="button" class="sg-btn g wide" data-auth="gsetup">'+GLOGO+'<span>Continue with Google</span></button><p class="sg-mark">Owner only: Google sign-in is not connected on this computer yet; this button opens setup. Visitors never see it.</p>';
    return "";
  }
  function goGoogle(btn,mode){
    setPending({mode:mode,first:V.first,last:V.last,email:V.email,agreed:V.agreed,at:Date.now()});
    btn.setAttribute("aria-busy","true");var l=btn.querySelector(".sg-gl");if(l)l.textContent="Opening Google…";
    try{w.top.sessionStorage.setItem(GSTART,String(Date.now()))}catch(e){}
    var gu="/api/auth/google/start"+(mode==="up"?"?agree=1":"");
    try{w.top.location.assign(gu)}catch(e){w.location.assign(gu)}
  }
  /* Google's own button (no client secret): it reads the tick from #gAgree, and the card's details ride along in case it signs in */
  function mountGis(mode){
    if(!host0.querySelector("#gBtn"))return;
    setPending({mode:mode,first:V.first,last:V.last,email:V.email,agreed:V.agreed,at:Date.now(),gis:true});
    setTimeout(function(){try{B.mountGoogle()}catch(e){}},0);
  }

  /* "A code went to sam@example.com 2 min ago. Type the code": shown on both cards while this tab's last code still works */
  function haveHTML(){
    var cs=getCodeStep();if(!cs)return "";
    var m=Math.floor((Date.now()-(+cs.at||0))/60e3);
    return '<div class="sg-have" role="status"><span>A code went to <b>'+esc(cs.email)+'</b> '+(m<1?"just now":m===1?"1 min ago":m+" min ago")+'.</span><button type="button" class="sg-lnk sg-havec">Type the code</button></div>';
  }
  function wireHave(c,seen){var b=c.querySelector(".sg-havec");if(b)b.onclick=function(){seen();resume(getCodeStep())}}
  /* back to the code step this tab was on, without sending anything */
  function resume(cs){
    if(!cs){render(true);return}
    V.email=cs.email;V.kind=cs.kind;V.sentAt=+cs.at||0;V.noSend=false;
    if(cs.kind==="up"){V.first=cs.first||V.first;V.last=cs.last||V.last;V.agreed=true}   /* the names and the tick from Create my account */
    V.view="code";render(true);
  }

  /* ---------- sign up ---------- */
  function signup(focus){
    back=null;V.view="up";
    var hid=uid("h"),aid=uid("am"),gh=googleHTML();
    var c=shell('<div class="sg-chead"><h1 id="'+hid+'" tabindex="-1">Create your UAply account</h1><p class="sg-sub">Takes a minute. No password to remember.</p></div>'+
      (V.errTop?'<p class="sg-fmsg err" role="alert" style="text-align:center">'+esc(V.err)+'</p>':'')+haveHTML()+
      /* Mohammed's order: Google, "or", Email, First name, Last name, the 18+ tick, Create my account. The server needs the tick before
         Google opens; that is the tick's state, not its place, so an unticked Google tap stays here, shakes the box and says why */
      (gh?gh+'<div class="sg-or">or</div>':'')+
      '<form class="sg-stack sg-su" novalidate>'+emailFieldHTML(V.email)+
      '<div class="sg-two">'+textFieldHTML("First name","given-name","",V.first,"sg-fn","next")+textFieldHTML("Last name","family-name","",V.last,"sg-ln","go")+'</div>'+
      '<p class="sg-fine sg-nameh">Goes on your applications. Kept on this device.</p>'+
      '<label class="sg-agree"><input type="checkbox" class="sg-ag" data-f="tick"'+(gh.indexOf('id="gBtn"')>-1?' id="gAgree"':'')+' aria-describedby="'+aid+'"'+(V.agreed?" checked":"")+'><span>'+AGREE+'</span></label>'+
      '<p class="sg-fmsg sg-amsg" id="'+aid+'" aria-live="polite"></p>'+
      '<button type="submit" class="sg-btn pri wide">Create my account</button></form>'+
      '<p class="sg-swap">Have an account? <button type="button" class="sg-lnk sg-to-in">Sign in</button></p>');
    c.setAttribute("aria-labelledby",hid);
    var amsg=c.querySelector(".sg-amsg"),ag=c.querySelector(".sg-ag"),agl=c.querySelector(".sg-agree");
    function agMsg(cls,txt){amsg.className="sg-fmsg sg-amsg"+(cls?" "+cls:"");amsg.textContent=txt||""}
    function shake(el){el.classList.remove("sg-shake");void el.offsetWidth;if(!RM())el.classList.add("sg-shake")}
    /* a message from the trip to Google stays until the person acts on the card (the screen may be redrawn meanwhile) */
    if(V.err&&!V.errTop){agl.classList.add("bad");agMsg("err",V.err)}
    function seen(){V.err="";V.errTop=false}
    wireHave(c,seen);
    var em=wireEmail(c.querySelector("[data-email]"),function(v){V.email=v;keepGis()});
    var fn=wireReq(c.querySelector(".sg-fn"),"Add your first name."),ln=wireReq(c.querySelector(".sg-ln"),"Add your last name.");
    fn.input.addEventListener("input",function(){V.first=fn.value();keepGis()});ln.input.addEventListener("input",function(){V.last=ln.value();keepGis()});
    function keepGis(){if(c.querySelector("#gBtn"))setPending({mode:"up",first:V.first,last:V.last,email:V.email,agreed:V.agreed,at:Date.now(),gis:true})}
    var gb=c.querySelector('[data-sg="google"]');
    ag.addEventListener("change",function(){seen();V.agreed=ag.checked;agl.classList.remove("bad");keepGis();
      if(ag.checked&&V.gWait){agMsg("nudge","Ticked. Now press Continue with Google.");var g=gb||c.querySelector("#gBtn");if(g)try{g.scrollIntoView({block:"nearest",behavior:RM()?"auto":"smooth"})}catch(e){}}else agMsg()});
    /* the server needs the tick before Google opens, so an unticked tap stays here, shakes the box and brings it into view */
    if(gb)gb.onclick=function(){
      seen();
      if(!ag.checked){V.gWait=true;agl.classList.add("bad");agMsg("err","Tick the box first, then Continue with Google.");shake(agl);fxs(ag);return}
      V.first=fn.value();V.last=ln.value();V.email=em.value();V.agreed=true;goGoogle(gb,"up");
    };
    mountGis("up");
    var form=c.querySelector(".sg-su"),sb=form.querySelector('[type="submit"]');
    /* every problem shows in one pass; focus goes to the first one in page order */
    form.onsubmit=function(e){
      e.preventDefault();var firstBad=null;V.gWait=false;seen();
      if(!em.validate())firstBad=em.input;
      if(!fn.validate())firstBad=firstBad||fn.input;
      if(!ln.validate())firstBad=firstBad||ln.input;
      if(!ag.checked){agl.classList.add("bad");agMsg("err","Tick the box to confirm you’re 18 or older and agree.");shake(agl);firstBad=firstBad||ag}else{agl.classList.remove("bad");agMsg()}
      if(firstBad){fxs(firstBad);return}
      V.email=em.value();V.first=fn.value();V.last=ln.value();V.agreed=true;
      sb.disabled=true;sb.setAttribute("aria-busy","true");sb.textContent="Creating your account…";
      B.post("/api/auth/signup",{email:V.email,agree:true,passwordless:true}).then(function(r){
        if(!sb.isConnected)return;
        sb.disabled=false;sb.removeAttribute("aria-busy");sb.textContent="Create my account";
        if(!r.ok){var t=(r.j&&r.j.error)||"Could not create the account. Try again.";if(r.j&&r.j.code==="mailbox"){em.error(t);fxs(em.input)}else{agMsg("err",t);fxs(sb)}return}
        V.email=(r.j&&r.j.email)||V.email;V.delivery=(r.j&&r.j.delivery)||"";V.kind="up";V.view="code";V.sentAt=Date.now();V.noSend=false;
        setCodeStep({kind:"up",email:V.email,first:V.first,last:V.last,at:V.sentAt});
        render(true);
      });
    };
    c.querySelector(".sg-to-in").onclick=function(){seen();V.view="in";render(true)};
    /* back from Google with "tick the box first": the box (at the bottom of the card) comes into view with its message */
    if(focus){if(V.err&&!V.errTop)fxs(ag);else fx(c.querySelector("h1"))}
  }

  /* ---------- sign in (returning) ---------- */
  function signin(focus){
    back=function(){V.err="";V.errTop=false;V.view="up";render(true)};V.view="in";
    var hid=uid("h"),gh=googleHTML();
    var c=shell('<div class="sg-chead"><h1 id="'+hid+'" tabindex="-1">Welcome back</h1><p class="sg-sub">We’ll email you a code. No password needed.</p></div>'+
      (V.err?'<p class="sg-fmsg err" role="alert" style="text-align:center">'+esc(V.err)+'</p>':'')+haveHTML()+
      (gh?gh+'<div class="sg-or">or</div>':'')+
      '<form class="sg-stack sg-si" novalidate>'+emailFieldHTML(V.email)+
      '<button type="submit" class="sg-btn pri wide">Email me a code</button></form>'+
      '<p class="sg-swap">Already have a code? <button type="button" class="sg-lnk sg-typec">Type it</button></p>'+
      '<p class="sg-swap">New here? <button type="button" class="sg-lnk sg-to-up">Create an account</button></p>');
    c.setAttribute("aria-labelledby",hid);
    function seen(){V.err="";V.errTop=false}
    wireHave(c,seen);
    var em=wireEmail(c.querySelector("[data-email]"),function(v){V.email=v});
    var gb=c.querySelector('[data-sg="google"]');
    if(gb)gb.onclick=function(){seen();V.email=em.value();goGoogle(gb,"in")};
    mountGis("in");
    var form=c.querySelector(".sg-si"),sb=form.querySelector('[type="submit"]');
    form.onsubmit=function(e){
      e.preventDefault();seen();
      if(!em.validate()){fxs(em.input);return}
      V.email=em.value();
      sb.disabled=true;sb.setAttribute("aria-busy","true");sb.textContent="Sending…";
      B.post("/api/auth/code/send",{email:V.email}).then(function(r){
        if(!sb.isConnected)return;
        sb.disabled=false;sb.removeAttribute("aria-busy");sb.textContent="Email me a code";
        if(!r.ok){em.error((r.j&&r.j.error)||"Could not send a code. Try again.");fxs(em.input);return}
        V.kind="in";V.delivery="";V.view="code";V.sentAt=Date.now();V.noSend=false;
        setCodeStep({kind:"in",email:V.email,at:V.sentAt});
        render(true);
      });
    };
    /* a code from an earlier email (another tab, or before a reload): the six boxes, and nothing is sent */
    c.querySelector(".sg-typec").onclick=function(){
      seen();if(!em.validate()){fxs(em.input);return}
      V.email=em.value();var cs=getCodeStep();
      if(cs&&cs.email.toLowerCase()===V.email.toLowerCase()){resume(cs);return}
      V.kind="in";V.delivery="";V.sentAt=0;V.noSend=true;V.view="code";render(true);
    };
    c.querySelector(".sg-to-up").onclick=function(){seen();V.view="up";render(true)};
    if(focus)fx(c.querySelector("h1"));
  }

  /* ---------- the 6-digit code (sign-up, sign-in, and a Google address Google does not vouch for) ---------- */
  function deliveryNote(){
    var s=srv(),dl=V.delivery;
    if(dl==="failed")return "We could not send the code to that address. Check it, then press Resend code.";
    if(dl==="busy")return "We could not send the code just now: the problem is on our side. Press Resend code in a few minutes.";
    if(dl==="bounced")return "Emails to that address bounce back, so we did not send a code. Use a different email.";
    if(s.testInbox&&!s.canEmail)return 'Sandbox: no real email is connected on this computer, so the code is in the <a href="/outbox" target="_blank" rel="noopener noreferrer">test inbox</a>.';
    if(!s.canEmail&&s.mailKnown)return "Email is not switched on for this site yet, so no code can arrive. Use Continue with Google for now.";
    return "";
  }
  function code(focus){
    var kind=V.kind;
    back=function(){V.view=kind==="in"?"in":"up";if(kind==="g"){V.view="q";startQuestions();return}V.noSend=false;render(true)};   /* the card still offers "Type the code" while it works */
    var sub=V.noSend&&kind==="in"?'Type the 6-digit code from the newest UAply email to <b>'+esc(V.email)+'</b>. A code works for 10 minutes after it is sent.':
      kind==="up"?'We sent a 6-digit code to <b>'+esc(V.email)+'</b>. It works for 10 minutes.':
      kind==="g"?'Google signed you in, but it vouches only for Gmail and Google-run addresses. We sent a 6-digit code to <b>'+esc(V.email)+'</b>. It works for 10 minutes.':
      'If <b>'+esc(V.email)+'</b> has a UAply account, we sent it a 6-digit code. It works for 10 minutes.';
    var note=deliveryNote();
    var c=shell('<div class="sg-codestep"><h2 tabindex="-1">Check your email</h2><p class="sg-sub">'+sub+'</p>'+
      '<div class="sg-code" role="group" aria-label="6-digit code"></div><p class="sg-fmsg sg-cmsg" aria-live="polite"></p><div class="sg-cag"></div>'+(note?'<p class="sg-mark">'+note+'</p>':'')+
      '<div class="sg-between"><button type="button" class="sg-lnk sg-chg">'+(kind==="g"?"Later":"Use a different email")+'</button><button type="button" class="sg-lnk sg-resend" disabled>New code in&nbsp;<span>30</span>s</button></div></div>');
    var box=c.querySelector(".sg-code"),cm=c.querySelector(".sg-cmsg");
    for(var i=0;i<6;i++)box.appendChild(h('<input data-f="c'+i+'" inputmode="numeric" pattern="[0-9]*" maxlength="6" aria-label="Digit '+(i+1)+' of 6"'+(i===0?' autocomplete="one-time-code"':' autocomplete="off"')+'>'));
    var ins=[].slice.call(box.querySelectorAll("input")),checking=false;
    /* what is typed in the boxes outlives a redraw of the same code step; a new code step (render(true)) starts empty */
    if(focus||!V.cd||V.cdK!==kind+"|"+V.email)V.cd=["","","","","",""];
    V.cdK=kind+"|"+V.email;
    if(V.cd.join("").length<6)ins.forEach(function(x,i){x.value=V.cd[i]||""});
    function keep(){V.cd=ins.map(function(x){return x.value})}
    /* the 18+ / Terms tick goes with the code: ticked on Create your account; asked here when "Email me a code" finishes a brand-new
       account (made by someone who left before typing the code, or on another device), so the tick on record is this person's own */
    var agreeNow=kind==="up";
    function askAgree(){
      var slot=c.querySelector(".sg-cag");if(slot.firstChild)return;
      var aid=uid("am");
      slot.innerHTML='<label class="sg-agree" style="text-align:left"><input type="checkbox" class="sg-ag" data-f="ctick" aria-describedby="'+aid+'"><span>'+AGREE+'</span></label><p class="sg-fmsg" id="'+aid+'"></p>';
      var cb=slot.querySelector("input");
      cb.addEventListener("change",function(){if(cb.checked){agreeNow=true;check()}});
      fxs(cb);
    }
    function fill(t,start){for(var k=0;k+start<6&&k<t.length;k++)ins[start+k].value=t[k];keep();fx(ins[Math.min(5,start+t.length)]);check()}
    function clear(){ins.forEach(function(x){x.value="";x.disabled=false});keep();box.classList.remove("ok");fx(ins[0])}
    function check(){
      var cd=ins.map(function(x){return x.value}).join("");if(cd.length<6||checking)return;checking=true;
      cm.className="sg-fmsg sg-cmsg";cm.textContent="Checking…";ins.forEach(function(x){x.disabled=true});
      var p=kind==="g"?B.post("/api/auth/verify",{code:cd}):B.post("/api/auth/code/verify",{email:V.email,code:cd,agree:agreeNow});
      p.then(function(r){
        checking=false;if(!c.isConnected)return;
        if(!r.ok&&r.j&&r.j.needsAgree){cm.className="sg-fmsg sg-cmsg nudge";cm.textContent=r.j.error||"Tick the box to finish creating your account.";ins.forEach(function(x){x.disabled=false});askAgree();return}
        if(!r.ok){cm.className="sg-fmsg sg-cmsg err";cm.textContent=(r.j&&r.j.error)||"That code did not work. Try again.";if(r.j&&r.j.expired)unlock();clear();return}
        box.classList.add("ok");cm.className="sg-fmsg sg-cmsg ok";cm.textContent="Code accepted.";
        setTimeout(function(){if(!c.isConnected)return;
          if(kind==="g"){var u=Object.assign({},V.user||srv().user||{},{emailVerified:true});V.user=u;B.signedIn(u);V.view="q";startQuestions();return}
          var user=r.j&&r.j.user;if(!user){cm.textContent="Signed in, but the answer was incomplete. Reload the page.";return}
          setPending(null);setCodeStep(null);V.noSend=false;V.user=user;V.viaG=false;V.cd=null;if(user.googleRemoved)gGone=String(user.email||"").toLowerCase();
          holdApply=true;   /* the session is already this account's: nothing waiting goes out until guard() has looked */
          /* the session is real; when this device holds another account's details the card waits for Keep or Start fresh (guard) */
          V.view="ask";B.signedIn(user);
          if(user["new"]){V.isNew=true;guard(user.email,function(){saveName(V.first,V.last,user.email,V.kept);startQuestions()})}
          else guard(user.email,function(){if(kind==="up")saveName(V.first,V.last,user.email,true);V.view="signedin";render(true)});
        },RM()?50:350);
      });
    }
    ins.forEach(function(inp,i){
      inp.addEventListener("input",function(){var v=inp.value.replace(/\D/g,"");if(v.length>1){inp.value="";fill(v.slice(0,6-i),i);return}inp.value=v;keep();if(v&&i<5)fx(ins[i+1]);check()});
      inp.addEventListener("keydown",function(e){
        if(e.key==="Backspace"&&!inp.value&&i>0){e.preventDefault();ins[i-1].value="";keep();fx(ins[i-1])}
        else if(e.key==="ArrowLeft"&&i>0){e.preventDefault();fx(ins[i-1])}
        else if(e.key==="ArrowRight"&&i<5){e.preventDefault();fx(ins[i+1])}});
      inp.addEventListener("paste",function(e){var t=(((e.clipboardData||w.clipboardData)||{getData:function(){return ""}}).getData("text")||"").replace(/\D/g,"");if(t){e.preventDefault();fill(t.slice(0,6),0)}});
      inp.addEventListener("focus",function(){inp.select()});
    });
    c.querySelector(".sg-chg").onclick=back;
    /* Resend opens 30 seconds after the code was really sent (a reload does not restart the wait; a typed earlier code: at once) */
    var rs=c.querySelector(".sg-resend"),n=Math.max(0,30-Math.floor((Date.now()-(V.sentAt||0))/1000)),iv=null;
    function unlock(){clearInterval(iv);rs.disabled=false;rs.textContent="Resend code"}
    if(n<=0)unlock();
    else{rs.querySelector("span").textContent=n;iv=setInterval(function(){if(!c.isConnected){clearInterval(iv);return}n--;if(n<=0)unlock();else rs.querySelector("span").textContent=n},1000)}
    rs.onclick=function(){
      rs.disabled=true;rs.textContent="Sending…";
      var p=kind==="g"?B.post("/api/auth/resend",{}):B.post("/api/auth/code/send",{email:V.email});
      p.then(function(r){
        if(!c.isConnected)return;
        if(!r.ok){cm.className="sg-fmsg sg-cmsg err";cm.textContent=(r.j&&r.j.error)||"Could not send a new code.";rs.textContent="Resend code";rs.disabled=false;return}
        if(r.j&&r.j.delivery)V.delivery=r.j.delivery;
        V.sentAt=Date.now();V.noSend=false;
        if(kind!=="g"){var cs=getCodeStep()||{kind:kind,email:V.email,first:V.first,last:V.last};cs.at=V.sentAt;setCodeStep(cs)}
        cm.className="sg-fmsg sg-cmsg";cm.textContent="A new code is on its way. The old one no longer works.";rs.textContent="Sent";clear();
        n=30;setTimeout(function(){if(c.isConnected){rs.innerHTML="New code in&nbsp;<span>30</span>s";iv=setInterval(function(){if(!c.isConnected){clearInterval(iv);return}n--;if(n<=0)unlock();else rs.querySelector("span").textContent=n},1000)}},1500);
      });
    };
    /* a redraw while the person is typing in a box: __uaplySignCard puts them back in that box, so nothing here moves focus */
    if(focus||!(lastF&&lastF.view==="code")){fx(c.querySelector("h2"));setTimeout(function(){if(c.isConnected&&!(lastF&&lastF.view==="code"&&!focus))fx(ins[0])},RM()||!focus?0:250)}
  }

  /* ---------- back from Google with a session ---------- */
  function startAfterGoogle(user,pend){
    setPending(null);
    var gh=user.google||null;   /* serve.py (sandbox): whether the account was made just now. Google is asked for "openid email" only */
    V.user=user;V.email=user.email;V.viaG=true;
    /* the name typed on the card belongs to the email typed with it: it is used only when Google signed in that same address (or no
       address was typed). A different Google account (a partner's, on a shared phone) gets empty name boxes and the name question */
    if(pend.email&&lc(pend.email)!==lc(user.email)){pend=Object.assign({},pend,{first:"",last:""});V.first=V.last=""}
    if(!V.first&&!V.last){V.first=pend.first||"";V.last=pend.last||""}
    V.isNew=gh&&typeof gh["new"]==="boolean"?gh["new"]:pend.mode==="up";
    V.view="ask";
    if(!V.isNew){
      guard(user.email,function(){if(pend.first&&pend.last)saveName(pend.first,pend.last,user.email,true);V.view="signedin";render(true)});
      return;
    }
    V.typedName=!!(pend.first&&pend.last);
    guard(user.email,function(){
      if(V.typedName)saveName(V.first,V.last,user.email,V.kept);
      if(user.emailVerified===false){
        /* Google vouches only for Gmail and Google-run addresses: any other address gets the code before anything is sent for it */
        V.kind="g";V.view="code";render(true);
        B.post("/api/auth/resend",{}).then(function(r){if(r.ok&&r.j&&r.j.delivery){V.delivery=r.j.delivery;if(V.view==="code")render()}});
        return;
      }
      V.view="q";startQuestions();
    });
  }
  /* behind the sheet: the card says what it is waiting for */
  function askWait(){
    back=null;
    shell('<div class="sg-done"><h2 tabindex="-1">One question first</h2><p class="sg-sub">This device holds another person’s profile. Choose Keep or Start fresh to go on.</p></div>');
  }

  /* ---------- what is kept on this device (the app's own profile and settings; nothing here goes to the server) ---------- */
  function freshProfile(){
    var p=A.S.profile;
    if(p.custom)return p;
    /* the example profile (Jordan Lee) is never copied into a real one: start from empty, like Profile setup does */
    A.S.profile={name:"",title:"",years:0,edu:p.edu,skills:[],salary:0,loc:"",modes:{remote:false,hybrid:false,onsite:false},reloc:false,email:"",custom:true};
    return A.S.profile;
  }
  function commit(){try{A.save()}catch(e){}try{A.renderAll()}catch(e){}try{if(w.__uaplySyncPrefs)w.__uaplySyncPrefs()}catch(e){}}
  function saveName(first,last,email,onlyIfEmpty){
    first=String(first||"").trim().slice(0,60);last=String(last||"").trim().slice(0,60);
    if(!first&&!last)return;
    var p=A.S.profile;if(onlyIfEmpty&&p.custom&&p.name)return;
    p=freshProfile();p.name=(first+" "+last).trim();
    if(email&&!p.email)p.email=String(email).slice(0,200);
    commit();ownSet({first:first,last:last,email:String(email||"").toLowerCase()});
  }
  function saveWork(){
    var picks=V.work.slice();if(V.other)picks.push(V.other.slice(0,60));
    if(!picks.length)return;
    var p=freshProfile();p.title=picks[0];commit();
    /* the other picks become extra target titles (at most four). They only sort jobs: "Hide roles that do not match my titles" is
       switched off, so a pick never empties the deck (Mohammed can flip this: open question D3) */
    B.acct(function(a){a.titles=picks.slice(1,5);a.fTitleOnly=false});
  }
  function saveWhere(){
    var p,t=V.where.trim().slice(0,100);
    if(t){p=freshProfile();if(/^\d{5}$/.test(t))B.acct(function(a){a.addr=a.addr||{};a.addr.zip=t});else p.loc=t}
    /* "Remote is fine": remote jobs count as a match, and so does everything else (ticking only Remote would hide on-site jobs) */
    if(V.remote){p=freshProfile();p.modes={remote:true,hybrid:true,onsite:true}}
    if(t||V.remote)commit();
  }

  /* ---------- after the account exists: the name (Google only, when missing), two questions, then ready to swipe ---------- */
  function startQuestions(){
    /* the name is asked unless it was typed on the card in this visit (lost with a refresh before the code, or when the account was
       started on another device), and after Google unless typed. It is never taken from an earlier account on this device: on a
       shared computer that would put someone else's name on applications */
    var needName=!(V.first&&V.last)||(V.viaG&&!V.typedName);
    if(keptName())needName=false;   /* Keep: the profile saved here goes out as it is, with its own name */
    V.steps=needName?["name","work","where"]:["work","where"];
    V.k=0;V.view="q";render(true);
  }
  function keptName(){var p=A.S.profile||{};return !!(V.kept&&p.custom&&String(p.name||"").trim())}
  function profile(focus){
    back=null;wide(true);
    var steps=V.steps.length?V.steps:["work","where"],n=steps.length,k=Math.min(V.k,n),step=k<n?steps[k]:"done";
    var s=srv(),user=V.user||s.user||{},email=user.email||V.email||"";
    var who=V.first||"";
    host0.className="sg";
    host0.innerHTML='<div class="sg-q4 sg-pop"><header class="sg-q4b"><span class="sg-lg" aria-hidden="true">'+LOGO+'</span><span class="sg-wm">UAply</span>'+
      '<div class="sg-prog" role="progressbar" aria-label="Profile questions" aria-valuemin="0" aria-valuemax="'+n+'" aria-valuenow="'+k+'">'+steps.map(function(){return "<i></i>"}).join("")+'</div>'+
      '<span class="sg-who"><i aria-hidden="true">'+esc((who||email||"?").charAt(0).toUpperCase())+'</i>'+(who?'<span class="sg-whon">'+esc(who)+'</span>':'<span class="sg-vh">Signed in as '+esc(email)+'</span>')+'</span></header>'+
      '<div class="sg-q4m"><section class="sg-qs" aria-live="polite"></section><aside class="sg-pv'+(V.pvOpen?" open":"")+'" aria-label="Preview of what employers see"></aside></div>'+
      '<footer class="sg-q4f"><button type="button" class="sg-btn ghost sg-back">Back</button><span class="sp"></span><span class="sg-kh">Press <kbd>Enter</kbd> to continue</span><button type="button" class="sg-btn pri sg-next">Continue</button></footer></div>';
    var root=host0.querySelector(".sg-q4"),q=root.querySelector(".sg-qs"),pv=root.querySelector(".sg-pv"),nextBtn=root.querySelector(".sg-next");
    [].forEach.call(root.querySelectorAll(".sg-prog i"),function(x,i){x.classList.toggle("on",i<k);x.classList.toggle("cur",i===k)});
    function paintPV(flashKey){
      /* the meter counts the app's minimum to apply (READY_MIN in shared/uaply-nav.js): a name, an email, and a phone number or a resume */
      var p=A.S.profile||{},own=!!p.custom,name=keptName()?String(p.name).trim():(V.first+" "+V.last).trim()||(own?String(p.name||"").trim():""),title=V.work[0]||V.other||(own?p.title||"":""),
        where=V.where||(own?p.loc||"":""),em=(own&&p.email)||email,pr=hasPR(),
        filled=[name,/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(em),pr].filter(Boolean).length,pct=Math.round(filled/3*100);
      /* confirmed only from the server's emailVerified; it is not sent to employers, so it sits under their view, not on it */
      var vfd=(V.user||srv().user||{}).emailVerified===true;
      pv.innerHTML='<button type="button" class="sg-pvmini" aria-expanded="'+pv.classList.contains("open")+'">What employers see · '+filled+' of 3 needed<span class="sg-meter"><i style="width:'+pct+'%"></i></span>'+I.chev+'</button>'+
        '<p class="sg-pvh">What an employer sees when you apply through UAply</p><div class="sg-pvcard"><div class="sg-pvn" data-k="name">'+(name?esc(name):'<span class="sg-pvph">Your name</span>')+'</div>'+
        '<div class="sg-pvr" data-k="work"><span>Target title</span><b>'+(title?esc(title):"—")+'</b></div>'+
        '<div class="sg-pvr" data-k="where"><span>Where</span><b>'+esc(where||"—")+'</b></div>'+
        '<div class="sg-pvr" data-k="email"><span>Email</span><b>'+esc(em)+'</b></div>'+
        '<div class="sg-pvr'+(pr?'':' later')+'" data-k="pr"><span>Phone or resume</span><b>'+(pr?"Added":"Needed before UAply can apply")+'</b></div>'+
        '<div class="sg-meter"><i style="width:'+pct+'%"></i></div><p class="sg-fine">'+filled+' of 3 needed to apply: your name, your email, and a phone number or a resume. Your other work picks stay on this device and only sort jobs.</p></div>'+
        (vfd?'<p class="sg-vfl">'+I.check+'Your email is confirmed.</p>':'');
      pv.querySelector(".sg-pvmini").onclick=function(){pv.classList.toggle("open");V.pvOpen=pv.classList.contains("open");this.setAttribute("aria-expanded",V.pvOpen)};
      if(flashKey&&!RM()){var el=pv.querySelector('[data-k="'+flashKey+'"]');if(el)el.classList.add("sg-flash")}
    }
    var made="",eyebrow='<p class="sg-eyebrow">'+(k+1)+' of '+n+'</p>',html="";
    if(k===0&&V.isNew)made=V.viaG?
      '<p class="sg-made">'+I.check+' Account created with Google.</p><p class="sg-gnote">'+I.check+'<span>UAply keeps only your email ('+esc(email)+') and your Google account number from Google, so you can sign in again. UAply never sees your Google password.</span></p>':
      '<p class="sg-made">'+I.check+' Account created'+(V.first?', '+esc(V.first):'')+'.</p>';
    if(k===0&&V.pwGone)made+='<p class="sg-fine">'+PWGONE()+'</p>';
    if(k===0&&gOff(email))made+='<p class="sg-fine">'+GGONE+'</p>';
    if(k===0&&V.cleared)made+='<p class="sg-fine">You chose Start fresh: the other person’s profile, phone, resume, saved answers and swipe list were removed from this device, so your applications carry only your own.</p>';
    if(k===0&&V.kept)made+=keptHTML(user,"sg-fine");
    if(step==="name")html=made+eyebrow+'<h2 tabindex="-1">What should employers call you?</h2><div class="sg-two">'+textFieldHTML("First name","given-name","",V.first,"sg-fn","next")+textFieldHTML("Last name","family-name","",V.last,"sg-ln","next")+'</div><p class="sg-fine">Employers need a name on every application. Kept on this device. Use the name on your resume.</p>';
    if(step==="work")html=made+eyebrow+'<h2 tabindex="-1">What kind of work are you after?</h2><p class="sg-sub">We’ll show these first. You can change this later.</p><div class="sg-chips" role="group" aria-label="Kinds of work">'+WORK.map(function(x){return '<button type="button" class="sg-chip" aria-pressed="'+(V.work.indexOf(x)>-1)+'">'+x+'</button>'}).join("")+'</div>'+textFieldHTML("Something else","off","e.g. dental assistant",V.other,"","next");
    if(step==="where")html=eyebrow+'<h2 tabindex="-1">Where do you want to work?</h2>'+textFieldHTML("City or ZIP code","address-level2","Austin, TX",V.where,"","done")+'<div class="sg-chips"><button type="button" class="sg-chip sg-rem" aria-pressed="'+V.remote+'">Remote is fine</button>'+(s.near?'<button type="button" class="sg-chip sg-loc" aria-pressed="'+V.near+'">'+I.pin+' Use my location</button>':'')+'</div><p class="sg-fine sg-locmsg" aria-live="polite">'+(s.near?(V.near?"Using your device location, rounded to about a mile. It stays on this device and is never sent to our server.":"Your browser asks before it shares your location. It stays on this device and is never sent to our server."):"Kept on this device. Used to sort jobs by distance.")+'</p>';
    /* the end: honest about the app's readiness rule. Below READY_MIN a swipe right sends nothing, so this says what is missing, one tap from its field */
    if(step==="done"){var rr=ready(),low=!!(rr&&!rr.min);
      html='<div class="sg-done" style="text-align:left"><span class="sg-okc" style="margin:0">'+I.check+'</span><h2 tabindex="-1">'+(low?"Almost ready":"You’re ready to swipe.")+'</h2>'+
        (low?'<p class="sg-sub">Before UAply can apply, add '+esc(joinAnd(rr.missing))+'. You can look through jobs now.</p>'+fixesHTML(rr):'<p class="sg-sub">A swipe right applies for you.</p>')+
        '<p class="sg-sub">For employers who don’t take UAply applications yet, we open their own site instead.</p></div>'}
    q.innerHTML='<div class="sg-stack sg-qstack">'+html+'</div>';
    var ins=q.querySelectorAll("input"),advance=function(){V.k=k+1;render(true)};
    /* one main button: Skip while the question is empty, Continue once something is picked or typed */
    function paintNext(){var has=step==="work"?(V.work.length||V.other):step==="where"?(V.where||V.remote||V.near):true,r=step==="done"?ready():null;nextBtn.textContent=step==="done"?(r&&!r.min?"Show me jobs":"Start swiping"):has?"Continue":"Skip"}
    if(step==="name"){
      var fn=wireReq(q.querySelector(".sg-fn"),"Add your first name."),ln=wireReq(q.querySelector(".sg-ln"),"Add your last name.");
      fn.input.addEventListener("input",function(){V.first=fn.value();paintPV()});
      ln.input.addEventListener("input",function(){V.last=ln.value();paintPV()});
      advance=function(){var a=fn.validate(),b=ln.validate();if(!a){fxs(fn.input);return}if(!b){fxs(ln.input);return}V.first=fn.value();V.last=ln.value();V.typedName=true;saveName(V.first,V.last,email,V.kept);V.k=k+1;render(true)};
    }
    if(step==="work"){
      [].forEach.call(q.querySelectorAll(".sg-chip"),function(cp){cp.onclick=function(){var on=cp.getAttribute("aria-pressed")!=="true";cp.setAttribute("aria-pressed",on);var x=cp.textContent;if(on)V.work.push(x);else V.work=V.work.filter(function(y){return y!==x});paintPV("work");paintNext()}});
      ins[0].oninput=function(){V.other=this.value.trim();paintPV();paintNext()};
      advance=function(){saveWork();V.k=k+1;render(true)};
    }
    if(step==="where"){
      ins[0].oninput=function(){V.where=this.value.trim();paintPV();paintNext()};
      q.querySelector(".sg-rem").onclick=function(){V.remote=!V.remote;this.setAttribute("aria-pressed",V.remote);paintNext()};
      var lb=q.querySelector(".sg-loc"),lm=q.querySelector(".sg-locmsg");
      if(lb)lb.onclick=function(){
        if(V.near)return;
        lm.textContent="Waiting for your browser…";
        B.askDevice(function(ok,why){
          if(!lb.isConnected)return;
          V.near=!!ok;lb.setAttribute("aria-pressed",V.near);paintNext();
          lm.textContent=ok?"Using your device location, rounded to about a mile. It stays on this device and is never sent to our server.":
            why==="denied"?"Your browser blocked location for this site. Type your city or ZIP code instead.":"No location came back. Type your city or ZIP code instead.";
        });
      };
      advance=function(){saveWhere();V.k=k+1;render(true)};
    }
    /* the last screen keeps the footer: Back on the left, the main button where every earlier one was ("Show me jobs" until a swipe right
       can apply, "Start swiping" once it can) */
    if(step==="done"){advance=function(){finish()};
      /* "Add a phone number" and the like: shared/uaply-nav.js opens Profile setup on that field; the questions are over */
      [].forEach.call(q.querySelectorAll("[data-ready]"),function(b){b.addEventListener("click",function(){resetV()})})}
    var bk=root.querySelector(".sg-back");bk.style.visibility=k===0?"hidden":"visible";
    bk.onclick=function(){if(k>0){V.k=k-1;render(true)}};
    nextBtn.onclick=function(){advance()};
    paintNext();
    /* Enter continues from anywhere on the question except a button (a chip toggles, Back goes back) */
    root.addEventListener("keydown",function(e){
      if(e.key!=="Enter"||e.defaultPrevented)return;
      var t=e.target;if(t.closest("button,a"))return;
      e.preventDefault();advance();
    });
    back=k>0?function(){V.k=k-1;render(true)}:null;
    paintPV();
    if(focus)fx(q.querySelector("h2"));
  }
  function resetV(){V.view="";V.steps=[];V.k=0;V.work=[];V.other="";V.where="";V.remote=false;V.near=false;V.isNew=false;V.viaG=false;V.typedName=false;V.pwGone=false;V.cleared=false;V.kept=false;back=null;wide(false)}
  function finish(){
    resetV();
    try{B.cards()}catch(e){}
    B.redraw();   /* Account now shows the app's own signed-in card */
  }

  /* greet by name only when one is saved on this device; never guess it from the email */
  function signedIn(focus){
    back=null;
    var s=srv(),user=V.user||s.user||{},o=ownGet(),first=o.email&&o.email===String(user.email||"").toLowerCase()?o.first||"":"",rr=ready();   /* this account's own name only */
    var c=shell('<div class="sg-done"><span class="sg-okc">'+I.check+'</span><h2 tabindex="-1">'+(first?'You’re signed in, '+esc(first)+'.':'You’re signed in.')+'</h2><p class="sg-sub">Signed in as '+esc(user.email||V.email)+'.</p>'+
      (user.passwordRemoved||V.pwGone?'<p class="sg-fine">'+PWGONE()+'</p>':'')+(gOff(user.email)?'<p class="sg-fine">'+GGONE+'</p>':'')+
      (V.cleared?'<p class="sg-fine">You chose Start fresh: the other person’s profile, phone, resume, saved answers and swipe list were removed from this device.</p>':keptHTML(user,"sg-fine"))+
      (rr&&!rr.min?'<p class="sg-fine">Before UAply can apply, add '+esc(joinAnd(rr.missing))+'.</p>'+fixesHTML(rr):'')+
      '<button type="button" class="sg-btn pri wide sg-start">'+(rr&&!rr.min?"Show me jobs":"Start swiping")+'</button></div>');
    c.querySelector(".sg-start").onclick=function(){finish()};
    [].forEach.call(c.querySelectorAll("[data-ready]"),function(b){b.addEventListener("click",function(){resetV()})});
    if(focus)fx(c.querySelector("h2"));
  }
}

Env.FEATURES.signup={name:"Sign-up, nothing hidden",note:"Account becomes one centered card under the UAply mark: Continue with Google, or Email, First name, Last name, the 18+ tick and Create my account. No password: a 6-digit code is emailed (Google skips it for addresses it vouches for). Then two questions (kind of work, where) and you're ready to swipe, or told what the app still needs to apply. Returning: Google, or Email me a code. Needs Bottom navigation and this server's sign-up v2 (sandbox).",patch:patch,apply:apply};
Env.ORDER.push("signup");
})();
