/* "signup" experiment (sign-up v2) for the sandbox: "Sign-up, nothing hidden". Never loaded by prod; dev loads it only once it is promoted.
   The design Mohammed chose on Oct 21: one centered card with the brand mark directly above it (the two centered together as one group),
   Continue with Google, "or", Email, First name, Last name, the 18+ tick, Create my account. No password: Create my account emails a
   6-digit code (the server's sign-up v2 routes, sandbox only), and Google skips the code for addresses Google vouches for. After the
   account exists, two questions (kind of work, where), then "You're ready to swipe" (or "Almost ready" while the app's readiness rule,
   READY_MIN in shared/uaply-nav.js, still needs a phone number or a resume). Returning people: Google, or Email me a code.
   What is kept where (the screen says the same): the account (email, when the 18+ box was ticked) on the server; first and last name, the
   work picks and the place on this device only, in the app's own profile (Profile setup shows them). Nothing here is sent anywhere else.
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
/* the gate (October 22, 2026, Saif): with no account signed in, the card is the whole screen. Everything else (the header, the deck,
   Job Tracker, Profile, Hiring mode, Help, any message or dialog) is not drawn at all, so nothing behind it can be seen, scrolled to,
   tabbed to or read by a screen reader. Signed in, the app is exactly as before */
body.sgGated>*:not(main){display:none!important}
body.sgGated #main{position:fixed;inset:0;z-index:50;overflow-y:auto;overscroll-behavior:contain;background:var(--bg);margin:0;max-width:none;width:auto;height:auto;
  padding:16px 16px calc(16px + env(safe-area-inset-bottom,0px))}
body.sgGated #main>*:not(#pane-profile){display:none!important}
body.sgGated #pane-profile{display:flex!important;flex-direction:column;min-height:100%}
body.sgGated #pane-profile>*:not(#acctSec){display:none!important}
body.sgGated #acctSec{display:flex!important}
.sg-legal{margin:2px 0 0;text-align:center;font-size:13px;color:var(--muted);display:flex;flex-wrap:wrap;justify-content:center;column-gap:4px}
.sg-legal a{color:var(--muted);text-decoration:underline;display:inline-flex;align-items:center;min-height:44px;padding:0 6px}
/* the password box: its own show/hide button inside the box, a 44 px target */
#acctSec .sg .sg-pw input{padding-right:52px}
.sg-pw .sg-tick{display:none}
.sg-eye{position:absolute;right:2px;top:50%;transform:translateY(-50%);width:44px;height:44px;border:0;background:none;color:var(--muted);cursor:pointer;display:grid;place-items:center;border-radius:10px;padding:0}
.sg-eye:hover{color:var(--ink)}
.sg-eye svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.sg-pwh{margin-top:6px}
.sg-pw.bad .sg-pwh{display:none}
.sg-alt{margin:0;text-align:center;font-size:13px}
.sg-alt .sg-lnk{font-size:13px;font-weight:500;color:var(--muted)}
`;

/* the card's styles go into the production page's own style sheet, so the card never shows unstyled */
function patch(s){
  s=once(s,"</style>",CSS+"</style>");
  /* the gate (October 22, the runner's finding): signed out, the page builds no job card, no Applied list and no dashboard, so no job's
     title is anywhere in the page, drawn or hidden. __uaplyGateUp is up from the first line and comes down only once /api/auth/me
     answers with an account (gateSync); every drawing of the deck, Applied and the dashboard asks it first, and the gate going up again
     (Sign out) empties them */
  s=once(s,'var KEY="','window.__uaplyGateUp=true;\nvar KEY="');
  s=once(s,'function renderAll(){renderDeck();renderApps();renderDash()}',
    'function renderAll(){if(window.__uaplyGateUp){["deck","pane-apps","pane-dash"].forEach(function(i){var e=$(i);if(e)e.innerHTML=""});return}renderDeck();renderApps();renderDash()}');
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

  /* ---------- the phone's keyboard (Galaxy walk, October 22: in the installed app it covered Create my account by 133 px and Sign in by
     40 px; in Chrome it once covered the Email box while typing). The app runs in a frame, and the frame did not get shorter when the
     keyboard came up, so nothing inside could scroll above it. Now: the pages ask the browser to resize for the keyboard
     (interactive-widget=resizes-content); where it only shrinks the visual viewport instead, the page around the frame sets the
     frame's height to what is still visible (and back when the keyboard goes); and on the card the box being typed in, and the
     card's main button below it, are scrolled into the part of the screen that is left. ---------- */
  function editable(el){return !!el&&(/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)||el.isContentEditable)&&!/^(button|submit|checkbox|radio|range|color|file|hidden|reset|image)$/i.test(el.type||"")}
  function scroller(el){for(var p=el.parentElement;p&&p!==d.body;p=p.parentElement){var o=w.getComputedStyle(p).overflowY;if((o==="auto"||o==="scroll")&&p.scrollHeight>p.clientHeight+1)return p}return d.scrollingElement||d.documentElement}
  function mainAfter(el){var f=el.closest("form")||el.closest(".sg-card");if(!f)return null;var bs=f.querySelectorAll(".sg-btn.pri");
    for(var i=0;i<bs.length;i++){if((el.compareDocumentPosition(bs[i])&4)&&bs[i].getClientRects().length)return bs[i]}return null}
  function inView(el){
    if(!el||!el.getClientRects().length)return;
    var fr=w.frameElement,top0=(fr&&fr.__sgKbVisTop)||0,bot0=w.innerHeight,M=12;
    var sc=scroller(el),sr=sc===d.scrollingElement||sc===d.documentElement?{top:0,bottom:w.innerHeight}:sc.getBoundingClientRect();
    var vt=Math.max(top0,sr.top)+M,vb=Math.min(bot0,sr.bottom)-M;if(vb-vt<40)return;
    var r=el.getBoundingClientRect(),b=mainAfter(el),lo=r.bottom;
    if(b){var br=b.getBoundingClientRect();if(br.bottom-r.top<=vb-vt)lo=br.bottom}   /* the box and its button, when both fit */
    var dy=0;if(lo>vb)dy=lo-vb;if(r.top-dy<vt)dy=r.top-vt;
    if(Math.abs(dy)>=1){if(sc===d.scrollingElement||sc===d.documentElement)w.scrollBy(0,dy);else sc.scrollTop+=dy}
  }
  function bring(){var a=d.activeElement;if(editable(a)&&a.closest(".sg"))inView(a)}
  w.__uaplyKbBring=bring;
  d.addEventListener("focusin",function(e){if(!editable(e.target)||!e.target.closest(".sg"))return;[60,320,650].forEach(function(t){setTimeout(bring,t)})});
  w.addEventListener("resize",function(){setTimeout(bring,30)});
  (function kbFrame(){
    var fr=w.frameElement,top;try{top=fr&&fr.ownerDocument.defaultView}catch(e){}
    if(!fr||!top)return;fr.__sgKbW=w;if(fr.__sgKb)return;fr.__sgKb=true;   /* one set of listeners per frame; a reloaded app takes them over */
    var raf=0;
    function fit(){
      raf=0;var vv=top.visualViewport,iw=fr.__sgKbW;if(!vv)return;
      var inner=null;try{inner=iw&&iw.document.activeElement}catch(e){}
      var bottom=vv.offsetTop+vv.height,covered=top.innerHeight-bottom,t=fr.getBoundingClientRect().top;
      /* the keyboard: a box is being typed in, the page is not pinch-zoomed, and more than 100 px at the bottom are hidden */
      if(covered>100&&Math.abs((vv.scale||1)-1)<.01&&(editable(inner)||editable(top.document.activeElement))&&bottom-Math.max(0,t)>=160){
        fr.style.height=Math.round(bottom-Math.max(0,t))+"px";fr.style.flex="0 0 auto";fr.__sgKbVisTop=Math.max(0,vv.offsetTop-t);fr.__sgKbOn=true;
      }else if(fr.__sgKbOn){fr.style.height="";fr.style.flex="";fr.__sgKbVisTop=0;fr.__sgKbOn=false}
      try{if(iw&&iw.__uaplyKbBring)setTimeout(iw.__uaplyKbBring,30)}catch(e){}
    }
    function soon(){if(!raf)raf=top.requestAnimationFrame(fit)}
    if(top.visualViewport){top.visualViewport.addEventListener("resize",soon);top.visualViewport.addEventListener("scroll",soon)}
    top.addEventListener("resize",soon);
  })();
  function h(html){var t=d.createElement("template");t.innerHTML=html.trim();return t.content.firstElementChild}
  function topStore(){try{return w.top.sessionStorage}catch(e){return null}}
  function getPending(){try{var s=topStore(),p=s&&JSON.parse(s.getItem(PENDING));return p&&typeof p==="object"&&Date.now()-(+p.at||0)<15*60e3?p:null}catch(e){return null}}
  function setPending(p){try{var s=topStore();if(!s)return;if(p)s.setItem(PENDING,JSON.stringify(p));else s.removeItem(PENDING)}catch(e){}}
  /* the code step outlives a reload (a refresh, Back then Forward, a phone that dropped the tab while the person read their email): this
     tab remembers which address the code went to, for which step, and when; never the code. The card then offers "Type the code" for
     10 minutes instead of a new code (each new code cancels the last and counts toward the limit of 3 an hour) */
  function getCodeStep(){try{var s=topStore(),c=s&&JSON.parse(s.getItem(CODEK));return c&&typeof c==="object"&&typeof c.email==="string"&&(c.kind==="up"||c.kind==="in"||c.kind==="pw")&&Date.now()-(+c.at||0)<CODE_MS?c:null}catch(e){return null}}
  function setCodeStep(c){try{var s=topStore();if(!s)return;if(c)s.setItem(CODEK,JSON.stringify(c));else s.removeItem(CODEK)}catch(e){}}
  function ownGet(){try{var o=JSON.parse(w.localStorage.getItem(OWN));return o&&typeof o==="object"?o:{}}catch(e){return {}}}
  function ownSet(o){try{w.localStorage.setItem(OWN,JSON.stringify(o))}catch(e){}}

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
  /* the password box (October 22, Saif): a new one needs 8 characters (auth_api._check_new_password), with a show/hide button inside */
  var EYE=SVG('<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
      EYEX=SVG('<path d="M3 3l18 18"/><path d="M10.6 5.1A10.4 10.4 0 0 1 12 5c6.4 0 10 7 10 7a17.6 17.6 0 0 1-3.1 4.1M6.6 6.6C3.8 8.4 2 12 2 12s3.6 7 10 7a9.7 9.7 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>');
  function pwFieldHTML(isNew){var id=uid("pw");return '<div class="sg-fld sg-pw"><label for="'+id+'">Password</label><div class="sg-in"><input id="'+id+'" data-f="password" type="password" maxlength="128" autocomplete="'+(isNew?"new-password":"current-password")+'" enterkeyhint="'+(isNew?"next":"go")+'" aria-describedby="'+id+'h '+id+'m">'+
    '<button type="button" class="sg-eye" aria-label="Show password" aria-pressed="false" aria-controls="'+id+'">'+EYE+'</button></div>'+(isNew?'<p class="sg-fine sg-pwh" id="'+id+'h">At least 8 characters.</p>':'<span id="'+id+'h" hidden></span>')+'<p class="sg-fmsg" id="'+id+'m" aria-live="polite"></p></div>'}
  function wirePw(fld,isNew){
    var inp=fld.querySelector("input"),m=fld.querySelector(".sg-fmsg"),eye=fld.querySelector(".sg-eye");
    /* the eye (Galaxy walk, October 22): a tap must not take the focus from the box (that closed and re-opened the phone's keyboard,
       and the box could end up under it). pointerdown keeps the focus where it is; the click shows or hides the password, puts the caret
       back at the end when the box was being typed in, and keeps the box (and the button below it) in view */
    function keep(e){e.preventDefault()}
    eye.addEventListener("pointerdown",keep);eye.addEventListener("mousedown",keep);
    eye.onclick=function(){var had=d.activeElement===inp,show=inp.type==="password";inp.type=show?"text":"password";eye.setAttribute("aria-pressed",show?"true":"false");eye.setAttribute("aria-label",show?"Hide password":"Show password");eye.innerHTML=show?EYEX:EYE;
      if(had){try{var n=inp.value.length;inp.setSelectionRange(n,n)}catch(e){}}inView(inp)};
    function set(t){fld.classList.toggle("bad",!!t);if(t)inp.setAttribute("aria-invalid","true");else inp.removeAttribute("aria-invalid");m.textContent=t||""}
    inp.addEventListener("input",function(){if(fld.classList.contains("bad")&&(!isNew||inp.value.length>=8))set("")});
    return {input:inp,value:function(){return inp.value},error:set,
      validate:function(){var v=inp.value;if(!v){set(isNew?"Choose a password of at least 8 characters.":"Enter your password.");return false}
        if(isNew&&v.length<8){set("Use at least 8 characters.");return false}set("");return true}};
  }
  /* reachable without an account, from the card itself: the legal pages, deleting an account, help and support (they are their own pages) */
  function legalHTML(){return '<p class="sg-legal"><a href="'+LB+'terms.html" target="_blank" rel="noopener noreferrer">Terms</a><a href="'+LB+'privacy.html" target="_blank" rel="noopener noreferrer">Privacy</a>'+
    '<a href="'+LB+'delete-account.html" target="_blank" rel="noopener noreferrer">Delete an account</a><a href="'+LB+'support.html" target="_blank" rel="noopener noreferrer">Help and support</a></p>'}
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
  var signupTest=false;   /* a test server (providers.signupTest): Create my account signs the person in, already confirmed */
  var host0=null,back=null,wasIn=false;
  /* after a sign-out the next person on this device starts from an empty card: no email, no name, the box unticked (their tick must be
     their own), no saved Google trip, nothing left from the questions */
  function forget(){
    resetV();V.view="in";V.codeMode=false;V.email=V.first=V.last="";V.pwUp=V.pwIn="";V.agreed=false;V.gWait=false;V.err="";V.errTop=false;V.user=null;V.kind="";V.delivery="";V.cd=null;V.pvOpen=false;
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
    if(user)wasIn=true;else if(wasIn||V.user)forget();   /* signed out since the last drawing */
    var pend=getPending();
    /* the card is drawn at once, before the server has said whether it can email codes (Reviewer 3, October 22: 2.5 s of blank screen
       on load): only "Email me a code instead" waits for that answer, and the redraw it brings keeps what was typed (lastF, V) */
    host0=el;   /* back from Google before the server's answer: the card already knew */
    if(user){
      if(V.view==="q"||V.view==="signedin"||(V.view==="code"&&(V.kind==="g"||V.kind==="pw"))){render();restoreFocus();return true}
      if(pend){startAfterGoogle(user,pend);return true}
      /* a reload during a new password account's code step: the account is signed in but not confirmed, and the step comes back */
      var pcs=pwStep(user);if(pcs){V.user=user;resume(pcs);return true}
      return false;   /* signed in, nothing to ask: the app's own signed-in card */
    }
    if(V.view!=="up"&&V.view!=="in"&&!(V.view==="code"&&V.kind!=="g"))V.view="up";   /* signed out in the middle of the questions */
    render();restoreFocus();
    return true;
  };
  /* back from Google (hook in googleReturn): errors show next to the box they are about; a sign-in was already handled above */
  function mine(){return !!(host0&&host0.isConnected&&acctOn()&&(V.view==="q"||V.view==="signedin"||(V.view==="code"&&(V.kind==="g"||V.kind==="pw"))))}
  w.__uaplySignReturn=function(er,signed,pwGone){
    var pend=getPending();
    if(signed&&pwGone)V.pwGone=true;   /* Google proved the inbox and the server removed a password nobody had proven: the card says so */
    if(!pend&&!mine())return false;
    if(er){
      setPending(null);
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
          off:"Google sign-in is not switched on.",email_in_use:"That email already has a UAply account. Sign in with your password, or Email me a code instead.",disposable:"Please use an email address you’ll keep. Temporary addresses can’t be used for job applications."})[er]||"Google sign-in did not work. Try again, or use your email.";
        V.errTop=true;
      }
      render(true);
      return true;
    }
    if(signed&&mine()){if(pwGone)render();return true}
    return false;
  };
  function acctOn(){var a=d.getElementById("acctSec");return !!(a&&a.classList.contains("sgnOn"))}

  /* ---------- the gate (October 22, 2026, Saif): nobody reaches anything on the site without an account ----------
     No session (GET /api/auth/me without a user): the card is the whole screen (CSS body.sgGated) and the app keeps the Account screen
     open behind it whatever is tapped, typed or linked (uaply-nav.js go() asks __uaplyGated). It stays while a new account's code or its
     two questions are on screen, and lifts once they are done; Sign out brings it back. Until the server has answered it is up (nothing
     shows for a moment and then hides); a preview with no server at all (a plain web host) has no accounts, so no gate. */
  var gated=null;
  function preview(){try{return !!w.__uaplyPreviewOn||!!(w.__uaplyPreview&&w.__uaplyPreview())}catch(e){return false}}
  function wantGate(){
    var s=srv();
    if(!s.up)return !preview();
    return !s.user||V.view==="q"||V.view==="code"||!!pwStep(s.user);
  }
  /* this tab's code step for a new password account that is signed in and not yet confirmed (survives a reload, as Mohammed's does) */
  function pwStep(u){var cs=getCodeStep();return u&&u.emailVerified===false&&cs&&cs.kind==="pw"&&cs.email.toLowerCase()===String(u.email||"").toLowerCase()?cs:null}
  function gateSync(){
    var on=wantGate(),was=gated;
    if(on!==was){
      gated=on;w.__uaplyGateUp=on;d.body.classList.toggle("sgGated",on);try{d.documentElement.classList.toggle("sgGated",on)}catch(e){}
      /* up: the deck, Applied, the dashboard and Job Tracker are emptied. Down: they are drawn, and the job list is asked for now (the
         first time: uaply-live.js waits for this; the server answers 401 to a visitor with no account anyway) */
      try{A.renderAll()}catch(e){}try{var tpn=d.getElementById("pane-track");if(on&&tpn)tpn.innerHTML="";else if(w.__uaplyTrack)w.__uaplyTrack()}catch(e){}
      if(!on&&w.__uaplyLoadJobs)try{w.__uaplyLoadJobs()}catch(e){}
    }
    if(on){try{B.account()}catch(e){}}
    else if(was===true){if(V.view==="signedin")resetV();try{B.cards()}catch(e){}}
  }
  /* any data route answering 401 "signin" (the session ended, or was never there): back to the gate */
  /* the app's own window and the page around it (shared/uaply-live.js reads the job list from there): each is watched once, and its
     answers go to the app of the moment (__uaplyGateHook), so a sandbox rebuilding its app never talks to an old one */
  function onAnswer(status,j){
    if(!j)return;
    if(status===401&&j.code==="signin"){if(srv().user)B.signedIn(null);else gateSync()}
    else if(status===403&&j.code==="verify")needCode();   /* signed in, the address not proven yet: the card's code step (kind "pw") */
  }
  function watch(win){
    win.__uaplyGateHook=onAnswer;
    var f0=win.fetch;
    if(typeof f0!=="function"||f0.__uaplyGateWatch)return;
    var wrapped=function(){
      return f0.apply(this,arguments).then(function(r){
        if(r&&(r.status===401||r.status===403)){try{r.clone().json().then(function(j){if(win.__uaplyGateHook)win.__uaplyGateHook(r.status,j)},function(){})}catch(e){}}
        return r;
      });
    };
    wrapped.__uaplyGateWatch=true;win.fetch=wrapped;
  }
  watch(w);try{if(w.top&&w.top!==w)watch(w.top)}catch(e){}
  function needCode(){
    /* not while a code step or the questions are already on the card, and not while a trip back from Google is being finished (its own
       code step, kind "g", comes from startAfterGoogle) */
    var u=srv().user;if(!u||V.view==="code"||V.view==="q"||getPending())return;
    var cs=getCodeStep();
    V.user=u;V.email=u.email||V.email;V.kind="pw";V.view="code";V.verifyOnly=true;V.noSend=false;
    V.sentAt=cs&&cs.kind==="pw"&&cs.email.toLowerCase()===String(u.email||"").toLowerCase()?+cs.at||0:0;
    gateSync();try{B.redraw()}catch(e){}
  }
  w.__uaplyGated=function(){return gated!==false};
  w.__uaplyGateSync=gateSync;

  /* is the no-password sign-in switched on for this server? (sandbox only; the old card stays everywhere else) */
  w.fetch("/api/auth/providers",{credentials:"same-origin"}).then(function(r){return r.ok?r.json():null}).then(function(j){
    var was=codeOn;codeOn=!!(j&&j.codeSignin);signupTest=!!(j&&j.signupTest);
    if(codeOn!==was)B.redraw();
  }).catch(function(){var was=codeOn;codeOn=false;if(was!==false)B.redraw()});
  /* the app's own signed-in card says how a person with no password signs in: here that is an emailed code (or Google), not "Forgot password" */
  w.__uaplyNoPwNote=function(user){
    if(codeOn!==true)return "";
    var s=srv(),g=!s.hideGoogle&&!!(user&&user.googleLinked)&&!gOff(user&&user.email);
    return '<p class="note" style="margin:0">You sign in with an emailed code'+(g?' or with Google':'')+'. No password needed.</p>';
  };

  /* ---------- drawing ---------- */
  function wide(on){var a=d.getElementById("acctSec");if(a)a.classList.toggle("sgWide",!!on)}
  function shell(inner){
    wide(false);
    host0.className="sg";
    host0.innerHTML='<div class="sg-shell"><div class="sg-bb" aria-hidden="true"><span class="sg-lg">'+LOGO+'</span><span class="sg-wm">UAply</span></div><section class="sg-card sg-pop">'+inner+'</section>'+(gated?legalHTML():'')+'</div>';
    return host0.querySelector(".sg-card");
  }
  function render(focus){
    if(!host0||!host0.isConnected)return;
    msg("");
    if(V.view==="in")signin(focus);
    else if(V.view==="code")code(focus);
    else if(V.view==="q")profile(focus);
    else if(V.view==="signedin")signedIn(focus);
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
    if(cs.kind==="up"||cs.kind==="pw"){V.first=cs.first||V.first;V.last=cs.last||V.last;V.agreed=true}   /* the names and the tick from Create my account */
    V.view="code";render(true);
  }

  /* ---------- sign up ---------- */
  function signup(focus){
    back=null;V.view="up";
    var hid=uid("h"),aid=uid("am"),gh=googleHTML();
    var c=shell('<div class="sg-chead"><h1 id="'+hid+'" tabindex="-1">Create your UAply account</h1></div>'+
      (V.errTop?'<p class="sg-fmsg err" role="alert" style="text-align:center">'+esc(V.err)+'</p>':'')+haveHTML()+
      /* Mohammed's order: Google, "or", Email, First name, Last name, the 18+ tick, Create my account. The server needs the tick before
         Google opens; that is the tick's state, not its place, so an unticked Google tap stays here, shakes the box and says why */
      (gh?gh+'<div class="sg-or">or</div>':'')+
      '<form class="sg-stack sg-su" novalidate>'+emailFieldHTML(V.email)+
      '<div class="sg-two">'+textFieldHTML("First name","given-name","",V.first,"sg-fn","next")+textFieldHTML("Last name","family-name","",V.last,"sg-ln","go")+'</div>'+
      '<p class="sg-fine sg-nameh">Goes on your applications.</p>'+pwFieldHTML(true)+
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
    /* the password is kept only in this page's memory (V.pwUp, never stored), so a redraw of the card (a late answer from the server just
       after the page opens) does not empty the box; it is dropped once the account is made or the card is left */
    var pw=wirePw(c.querySelector(".sg-pw"),true);if(V.pwUp)pw.input.value=V.pwUp;pw.input.addEventListener("input",function(){V.pwUp=pw.input.value});
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
      if(!pw.validate())firstBad=firstBad||pw.input;
      if(!ag.checked){agl.classList.add("bad");agMsg("err","Tick the box to confirm you’re 18 or older and agree.");shake(agl);firstBad=firstBad||ag}else{agl.classList.remove("bad");agMsg()}
      if(firstBad){fxs(firstBad);return}
      V.email=em.value();V.first=fn.value();V.last=ln.value();V.agreed=true;
      sb.disabled=true;sb.setAttribute("aria-busy","true");sb.textContent="Creating your account…";
      /* October 22 (Saif): an account has a password. The server makes it and signs the person in; its first code proves the inbox
         (kind "pw": /api/auth/verify, the session's own code), unless the server is a test server (providers.signupTest): then it is
         already confirmed and the two questions come next */
      B.post("/api/auth/signup",{email:V.email,password:pw.value(),first:V.first,last:V.last,agree:true,passwordless:false}).then(function(r){
        if(!sb.isConnected)return;
        sb.disabled=false;sb.removeAttribute("aria-busy");sb.textContent="Create my account";
        if(!r.ok){var t=(r.j&&r.j.error)||"Could not create the account. Try again.";if(r.j&&r.j.code==="mailbox"||/already has an account/i.test(t)){em.error(t);fxs(em.input)}else if(r.j&&r.j.field==="password"||/password/i.test(t)){pw.error(t);fxs(pw.input)}else{agMsg("err",t);fxs(sb)}return}
        V.email=(r.j&&r.j.user&&r.j.user.email)||(r.j&&r.j.email)||V.email;V.delivery=(r.j&&r.j.delivery)||"";
        V.pwUp="";afterPasswordSignup(r.j&&r.j.user);
      });
    };
    c.querySelector(".sg-to-in").onclick=function(){seen();V.view="in";render(true)};
    /* back from Google with "tick the box first": the box (at the bottom of the card) comes into view with its message */
    if(focus){if(V.err&&!V.errTop)fxs(ag);else fx(c.querySelector("h1"))}
  }

  /* after Create my account (a password account): the code that proves the inbox, or (a test server, or an address already confirmed)
     straight to the two questions */
  function afterPasswordSignup(u){
    setPending(null);
    function questions(user){setCodeStep(null);V.user=user;V.isNew=true;V.viaG=false;V.cd=null;claimDevice(user.email);saveName(V.first,V.last,user.email);V.view="q";B.signedIn(user);startQuestions()}
    if(signupTest||(u&&u.emailVerified)){
      if(u&&u.email){questions(Object.assign({},u,{emailVerified:true}));return}
      w.fetch("/api/auth/me",{credentials:"same-origin"}).then(function(r){return r.ok?r.json():null}).then(function(j){
        if(j&&j.user){questions(j.user);return}
        V.err="Your account was made. Sign in with your email and password.";V.view="in";render(true);
      }).catch(function(){V.err="Your account was made. Sign in with your email and password.";V.view="in";render(true)});
      return;
    }
    /* a server that signs the new account in at once answers with its user: the session's own code (kind "pw"). One that waits for
       the code (no user in the answer) gets Mohammed's emailed-code step (kind "up": /api/auth/code/verify with the address) */
    V.user=u||null;V.kind=u?"pw":"up";V.view="code";V.sentAt=Date.now();V.noSend=false;
    setCodeStep({kind:V.kind,email:V.email,first:V.first,last:V.last,at:V.sentAt});
    if(u)B.signedIn(u);   /* the server signed the new account in; the gate stays until the code proves the inbox */
    render(true);
  }

  /* ---------- sign in (returning) ---------- */
  function signin(focus){
    back=function(){V.err="";V.errTop=false;V.view="up";render(true)};V.view="in";
    var hid=uid("h"),gh=googleHTML();
    /* October 22 (Saif): Email and Password, Sign in, Forgot password?; Mohammed's emailed code stays as a small "Email me a code
       instead" (codeMode), which turns this same card into his code sign-in */
    var cm=!!V.codeMode&&codeOn===true;
    var c=shell('<div class="sg-chead"><h1 id="'+hid+'" tabindex="-1">Welcome back</h1><p class="sg-sub">'+(cm?'We’ll email you a code.':'Sign in to UAply.')+'</p></div>'+
      (V.err?'<p class="sg-fmsg err" role="alert" style="text-align:center">'+esc(V.err)+'</p>':'')+haveHTML()+
      (gh?gh+'<div class="sg-or">or</div>':'')+
      '<form class="sg-stack sg-si" novalidate>'+emailFieldHTML(V.email)+(cm?'':pwFieldHTML(false))+
      '<button type="submit" class="sg-btn pri wide">'+(cm?'Email me a code':'Sign in')+'</button></form>'+
      (cm?'<p class="sg-swap">Already have a code? <button type="button" class="sg-lnk sg-typec">Type it</button></p><p class="sg-alt"><button type="button" class="sg-lnk sg-usepw">Use your password instead</button></p>':
        '<p class="sg-swap"><button type="button" class="sg-lnk sg-forgot">Forgot password?</button></p>'+(codeOn===true?'<p class="sg-alt"><button type="button" class="sg-lnk sg-codeinst">Email me a code instead</button></p>':''))+
      '<p class="sg-swap">New here? <button type="button" class="sg-lnk sg-to-up">Create an account</button></p>');
    c.setAttribute("aria-labelledby",hid);
    function seen(){V.err="";V.errTop=false}
    wireHave(c,seen);
    var em=wireEmail(c.querySelector("[data-email]"),function(v){V.email=v});
    var pf=c.querySelector(".sg-pw"),pw=pf?wirePw(pf,false):null;
    if(pw){if(V.pwIn)pw.input.value=V.pwIn;pw.input.addEventListener("input",function(){V.pwIn=pw.input.value})}   /* memory only, as on Create */
    var gb=c.querySelector('[data-sg="google"]');
    if(gb)gb.onclick=function(){seen();V.email=em.value();goGoogle(gb,"in")};
    mountGis("in");
    var form=c.querySelector(".sg-si"),sb=form.querySelector('[type="submit"]'),sbt=sb.textContent;
    function busy(on,t){sb.disabled=on;if(on){sb.setAttribute("aria-busy","true");sb.textContent=t}else{sb.removeAttribute("aria-busy");sb.textContent=sbt}}
    form.onsubmit=function(e){
      e.preventDefault();seen();
      var bad=null;if(!em.validate())bad=em.input;if(pw&&!pw.validate())bad=bad||pw.input;if(bad){fxs(bad);return}
      V.email=em.value();
      if(!cm){
        busy(true,"Signing in…");
        B.post("/api/auth/login",{email:V.email,password:pw.value()}).then(function(r){
          if(!sb.isConnected)return;busy(false);
          if(!r.ok||!(r.j&&r.j.user)){V.pwIn="";pw.error((r.j&&r.j.error)||"That email and password do not match. Try again, or use Forgot password?");pw.input.value="";fxs(pw.input);return}
          var u=r.j.user;V.pwIn="";setCodeStep(null);V.user=u;V.isNew=false;V.view="signedin";B.signedIn(u);
          saveName("","",u.email,true);render(true);
        });
        return;
      }
      busy(true,"Sending…");
      B.post("/api/auth/code/send",{email:V.email}).then(function(r){
        if(!sb.isConnected)return;busy(false);
        if(!r.ok){em.error((r.j&&r.j.error)||"Could not send a code. Try again.");fxs(em.input);return}
        V.kind="in";V.delivery="";V.view="code";V.sentAt=Date.now();V.noSend=false;
        setCodeStep({kind:"in",email:V.email,at:V.sentAt});
        render(true);
      });
    };
    /* Forgot password?: the reset link goes to the address typed above (the server answers the same whether or not it has an account) */
    var fg=c.querySelector(".sg-forgot");
    if(fg)fg.onclick=function(){
      seen();if(!em.validate()){fxs(em.input);return}
      V.email=em.value();fg.disabled=true;
      B.post("/api/auth/forgot",{email:V.email}).then(function(r){
        fg.disabled=false;if(!c.isConnected)return;
        var t=r.ok?"If "+V.email+" has a UAply account, we sent it a link to choose a new password. It works for an hour.":((r.j&&r.j.error)||"Could not send the link. Try again.");
        var p=c.querySelector(".sg-fgmsg");if(!p){p=h('<p class="sg-fmsg sg-fgmsg" role="status" style="text-align:center"></p>');fg.parentNode.insertAdjacentElement("afterend",p)}
        p.className="sg-fmsg sg-fgmsg"+(r.ok?" ok":" err");p.textContent=t;
      });
    };
    /* Email me a code instead: with a good address typed, the code goes on this press; without one, the card asks for the address */
    var ci=c.querySelector(".sg-codeinst");if(ci)ci.onclick=function(){
      seen();V.email=em.value()||V.email;V.codeMode=true;
      if(checkEmail(V.email).s!=="ok"){render(true);return}
      ci.disabled=true;ci.textContent="Sending a code…";
      B.post("/api/auth/code/send",{email:V.email}).then(function(r){
        if(!c.isConnected)return;
        if(!r.ok){V.err=(r.j&&r.j.error)||"Could not send a code. Try again.";render(true);return}
        V.kind="in";V.delivery="";V.view="code";V.sentAt=Date.now();V.noSend=false;
        setCodeStep({kind:"in",email:V.email,at:V.sentAt});
        render(true);
      });
    };
    var up=c.querySelector(".sg-usepw");if(up)up.onclick=function(){seen();V.email=em.value()||V.email;V.codeMode=false;render(true)};
    /* a code from an earlier email (another tab, or before a reload): the six boxes, and nothing is sent */
    var tc=c.querySelector(".sg-typec");
    if(tc)tc.onclick=function(){
      seen();if(!em.validate()){fxs(em.input);return}
      V.email=em.value();var cs=getCodeStep();
      if(cs&&cs.email.toLowerCase()===V.email.toLowerCase()){resume(cs);return}
      V.kind="in";V.delivery="";V.sentAt=0;V.noSend=true;V.view="code";render(true);
    };
    c.querySelector(".sg-to-up").onclick=function(){seen();V.codeMode=false;V.view="up";render(true)};
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
    back=function(){V.view=kind==="in"?"in":"up";if(kind==="g"){V.view="q";startQuestions();return}
      /* a password account is already made and signed in: "Use a different email" signs it out and starts over (the gate stays) */
      if(kind==="pw"){setCodeStep(null);V.user=null;B.post("/api/auth/logout",{}).then(function(){B.signedIn(null);V.view="up";V.noSend=false;render(true)});return}
      V.noSend=false;render(true)};   /* the card still offers "Type the code" while it works */
    var sub=V.noSend&&kind==="in"?'Type the 6-digit code from the newest UAply email to <b>'+esc(V.email)+'</b>. A code works for 10 minutes after it is sent.':
      kind==="up"||kind==="pw"?'We sent a 6-digit code to <b>'+esc(V.email)+'</b>. It works for 10 minutes.':
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
      var p=kind==="g"||kind==="pw"?B.post("/api/auth/verify",{code:cd}):B.post("/api/auth/code/verify",{email:V.email,code:cd,agree:agreeNow});
      p.then(function(r){
        checking=false;if(!c.isConnected)return;
        if(!r.ok&&r.j&&r.j.needsAgree){cm.className="sg-fmsg sg-cmsg nudge";cm.textContent=r.j.error||"Tick the box to finish creating your account.";ins.forEach(function(x){x.disabled=false});askAgree();return}
        if(!r.ok){cm.className="sg-fmsg sg-cmsg err";cm.textContent=(r.j&&r.j.error)||"That code did not work. Try again.";if(r.j&&r.j.expired)unlock();clear();return}
        box.classList.add("ok");cm.className="sg-fmsg sg-cmsg ok";cm.textContent="Code accepted.";
        setTimeout(function(){if(!c.isConnected)return;
          if(kind==="g"){var u=Object.assign({},V.user||srv().user||{},{emailVerified:true});V.user=u;B.signedIn(u);V.view="q";startQuestions();return}
          if(kind==="pw"&&V.verifyOnly){V.verifyOnly=false;setCodeStep(null);V.view="";B.signedIn(Object.assign({},V.user||srv().user||{},{emailVerified:true}));try{w.top.location.reload()}catch(e){w.location.reload()}return}
          if(kind==="pw"){var pu=Object.assign({},V.user||srv().user||{},{emailVerified:true});setCodeStep(null);V.user=pu;V.isNew=true;V.cd=null;claimDevice(pu.email||V.email);saveName(V.first,V.last,pu.email||V.email);B.signedIn(pu);V.view="q";startQuestions();return}
          var user=r.j&&r.j.user;if(!user){cm.textContent="Signed in, but the answer was incomplete. Reload the page.";return}
          setPending(null);setCodeStep(null);V.noSend=false;V.user=user;V.viaG=false;V.cd=null;if(user.googleRemoved)gGone=String(user.email||"").toLowerCase();
          if(user["new"]){V.isNew=true;claimDevice(user.email);saveName(V.first,V.last,user.email);V.view="q";B.signedIn(user);startQuestions()}
          else{if(kind==="up")saveName(V.first,V.last,user.email,true);V.view="signedin";B.signedIn(user);render(true)}
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
      var p=kind==="g"||kind==="pw"?B.post("/api/auth/resend",{}):B.post("/api/auth/code/send",{email:V.email});
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
    if(!V.first&&!V.last){V.first=pend.first||"";V.last=pend.last||""}
    V.isNew=gh&&typeof gh["new"]==="boolean"?gh["new"]:pend.mode==="up";
    if(!V.isNew){
      if(pend.first&&pend.last)saveName(pend.first,pend.last,user.email,true);
      V.view="signedin";render(true);return;
    }
    V.typedName=!!(pend.first&&pend.last);
    claimDevice(user.email);
    if(V.typedName)saveName(V.first,V.last,user.email);
    if(user.emailVerified===false){
      /* Google vouches only for Gmail and Google-run addresses: any other address gets the code before anything is sent for it */
      V.kind="g";V.view="code";render(true);
      B.post("/api/auth/resend",{}).then(function(r){if(r.ok&&r.j&&r.j.delivery){V.delivery=r.j.delivery;if(V.view==="code")render()}});
      return;
    }
    V.view="q";startQuestions();
  }

  /* ---------- what is kept on this device (the app's own profile and settings; nothing here goes to the server) ---------- */
  function freshProfile(){
    var p=A.S.profile;
    if(p.custom)return p;
    /* the example profile (Jordan Lee) is never copied into a real one: start from empty, like Profile setup does */
    A.S.profile={name:"",title:"",years:0,edu:p.edu,skills:[],salary:0,loc:"",modes:{remote:false,hybrid:false,onsite:false},reloc:false,email:"",custom:true};
    return A.S.profile;
  }
  /* a NEW account on a device whose profile belongs to another account (a shared phone or computer, or a second person after Sign out):
     before, only the name changed, so this account's applications would have gone out with the other person's email, phone, resume and
     answers while the screens said otherwise. Now it starts from a clean profile with its own email; the other person's phone, links,
     resume, work authorization and other answers, saved form answers and agreement to apply are cleared from this device (they were kept
     on this device only), and the first question says so. The same person (same email, or a profile with no email yet) keeps everything. */
  function claimDevice(email){
    email=String(email||"").toLowerCase();if(!email)return false;
    var p=A.S.profile||{},pe=p.custom?String(p.email||"").toLowerCase():"",oe=String(ownGet().email||"").toLowerCase();
    if(!(pe&&pe!==email)&&!(!pe&&oe&&oe!==email)){if(p.custom&&!p.email){p.email=email.slice(0,200);commit()}return false}
    A.S.profile={name:"",title:"",years:0,edu:"",skills:[],salary:0,loc:"",modes:{remote:false,hybrid:false,onsite:false},reloc:false,email:email.slice(0,200),custom:true};
    B.acct(function(a){a.phone=a.linkedin=a.portfolio=a.summary=a.auth=a.notice=a.cover=a.resumeName=a.resumeData=a.resumeUrl="";a.resumeSize=0;a.titles=[];
      a.eeo={auth:"",sponsor:"",veteran:"",hisp:"",race:[],disability:"",gender:""};a.addr={street:"",unit:"",state:"",zip:""}});
    var k=w.__uaplyKey||"uaply";[".answers",".answersAsked",".consent"].forEach(function(x){try{w.localStorage.removeItem(k+x)}catch(e){}});
    ownSet({first:"",last:"",email:email});commit();V.cleared=true;
    return true;
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
    V.steps=needName?["name","work","where"]:["work","where"];
    V.k=0;V.view="q";render(true);
  }
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
      var p=A.S.profile||{},own=!!p.custom,name=(V.first+" "+V.last).trim()||(own?String(p.name||"").trim():""),title=V.work[0]||V.other||(own?p.title||"":""),
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
    if(k===0&&V.cleared)made+='<p class="sg-fine">This device had another account’s details (phone, resume, saved answers). They were cleared here, so your applications carry only your own.</p>';
    if(step==="name")html=made+eyebrow+'<h2 tabindex="-1">What should employers call you?</h2><div class="sg-two">'+textFieldHTML("First name","given-name","",V.first,"sg-fn","next")+textFieldHTML("Last name","family-name","",V.last,"sg-ln","next")+'</div><p class="sg-fine">Employers need a name on every application. Goes on your applications. Use the name on your resume.</p>';
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
      advance=function(){var a=fn.validate(),b=ln.validate();if(!a){fxs(fn.input);return}if(!b){fxs(ln.input);return}V.first=fn.value();V.last=ln.value();V.typedName=true;saveName(V.first,V.last,email);V.k=k+1;render(true)};
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
  function resetV(){V.view="";V.steps=[];V.k=0;V.work=[];V.other="";V.where="";V.remote=false;V.near=false;V.isNew=false;V.viaG=false;V.typedName=false;V.pwGone=false;V.cleared=false;back=null;wide(false)}
  function finish(){
    resetV();
    gateSync();
    try{B.cards()}catch(e){}
    B.redraw();   /* Account now shows the app's own signed-in card */
  }

  /* greet by name only when one is saved on this device; never guess it from the email */
  function signedIn(focus){
    back=null;
    var s=srv(),user=V.user||s.user||{},o=ownGet(),first=o.email&&o.email===String(user.email||"").toLowerCase()?o.first||"":"",rr=ready();   /* this account's own name only */
    var c=shell('<div class="sg-done"><span class="sg-okc">'+I.check+'</span><h2 tabindex="-1">'+(first?'You’re signed in, '+esc(first)+'.':'You’re signed in.')+'</h2><p class="sg-sub">Signed in as '+esc(user.email||V.email)+'.</p>'+
      (user.passwordRemoved||V.pwGone?'<p class="sg-fine">'+PWGONE()+'</p>':'')+(gOff(user.email)?'<p class="sg-fine">'+GGONE+'</p>':'')+
      (rr&&!rr.min?'<p class="sg-fine">Before UAply can apply, add '+esc(joinAnd(rr.missing))+'.</p>'+fixesHTML(rr):'')+
      '<button type="button" class="sg-btn pri wide sg-start">'+(rr&&!rr.min?"Show me jobs":"Start swiping")+'</button></div>');
    c.querySelector(".sg-start").onclick=function(){finish()};
    [].forEach.call(c.querySelectorAll("[data-ready]"),function(b){b.addEventListener("click",function(){resetV()})});
    if(focus)fx(c.querySelector("h2"));
  }
  gateSync();   /* up from the first frame, before the server has said who is signed in */
}

Env.FEATURES.signup={name:"Sign-up, nothing hidden",note:"Account becomes one centered card under the UAply mark: Continue with Google, or Email, First name, Last name, the 18+ tick and Create my account. No password: a 6-digit code is emailed (Google skips it for addresses it vouches for). Then two questions (kind of work, where) and you're ready to swipe, or told what the app still needs to apply. Returning: Google, or Email me a code. Needs Bottom navigation and this server's sign-up v2 (sandbox).",patch:patch,apply:apply};
Env.ORDER.push("signup");
})();
