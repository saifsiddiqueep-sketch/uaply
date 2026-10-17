/* Shared engine for the sandbox and dev instances.
   It reads index.html (production), patches a copy in memory, and runs it in a frame with its own storage key.
   Nothing here ever writes to index.html. */
(function(){
function once(src,a,b){if(src.indexOf(a)<0)throw new Error("patch target not found: "+a.slice(0,40));return src.replace(a,function(){return b})}

var CSS_RISE="@keyframes rise{from{transform:translateY(14px) scale(.96);opacity:.6}to{transform:none;opacity:1}}@media (prefers-reduced-motion:no-preference){.card.top{animation:rise .35s ease-out}}";
var CSS_FIT=".card.under>*,.card.under2>*{visibility:hidden}.deck{min-height:430px}.ring b.r3{transform:scale(.8)}@media (max-height:700px){.card{padding:16px;gap:12px}.chead{margin:-16px -16px 0;padding:16px 16px 10px}.chead h2{font-size:22px}.logo{width:46px;height:46px;font-size:21px}.pay{font-size:26px}}";
var CSS_GUIDE="#banner:not([hidden]){display:flex!important}#progress{display:flex!important}@media (max-height:700px){#banner,#progress{display:none!important}}";
var CSS_NOTICE="#banner:not([hidden]){display:flex!important}@media (max-height:700px){#banner{display:none!important}}";   /* the example-profile notice alone, without the "N jobs left" counters */
var CSS_TAP=".tab,.filters button,.tips button,.banner button,.linkbtn,.row .btn,.checks label,.btn{min-height:44px}.chip.pick{min-height:36px}.rb.small{width:48px;height:48px}";
var CSS_TOP2=".crit:not(.open) li.extra{display:none}.crit li.more{display:block}.crit li.more .linkbtn{font-size:13.5px}";

var CRIT_TOP2=`function critHTML(m){
  var rows=m.rows.slice().sort(function(a,b){return (b.w*(1-b.s))-(a.w*(1-a.s))||b.w-a.w});
  return rows.map(function(r,i){
    var word=r.st===2?"Met":(r.st===1?"Partly met":"Not met");
    return '<li class="'+(i>1?'extra':'')+'"><span class="dot s'+r.st+'" role="img" aria-label="'+word+'">'+(r.st===2?"✓":(r.st===1?"~":"✕"))+'</span><span class="lbl">'+r.k+'</span><span class="val"><span class="ask">'+esc(r.ask)+'</span><span class="sep"> · </span><em>'+esc(r.have)+'</em></span><span class="pts">'+Math.round(r.w*r.s)+'/'+r.w+'</span></li>';
  }).join("")+'<li class="more"><button type="button" class="linkbtn" data-more>Show all criteria</button></li>';
}
`;

/* the swipe, rebuilt for phones. Touch is handled with touch events and a direction lock: the first few pixels decide whether the
   person means sideways (swipe) or up and down (scroll the card), and once it is sideways the browser is told not to scroll, so
   Safari can no longer take a curved thumb swipe over and cancel it. A swipe counts at 18% of the card's width (at most 80px) or as a
   quick flick. Mouse and pen keep pointer events. Replaces bindDrag in index.html.
   A second swipe that starts while the last card is still flying off (the quarter second before the next card is on top) counts
   too: the deck follows that finger, moves the next card once it is on top, and swipes it when the finger lifts (glideLate). */
var GLIDE=`window.__uaplyGlide=true;
/* one drag: where it started, how far it went, which way it is locked ("x" swipe, "y" scroll) and its recent path, for the speed */
function glideTrack(x,y){return {sx:x,sy:y,dx:0,dy:0,lock:"",trail:[[performance.now(),x]]}}
function glideMove(g,x,y){
  g.dx=x-g.sx;g.dy=y-g.sy;
  g.trail.push([performance.now(),x]);if(g.trail.length>12)g.trail.shift();
  if(!g.lock){var ax=Math.abs(g.dx),ay=Math.abs(g.dy);if(ax<6&&ay<6)return "";g.lock=ax>=ay*0.6?"x":"y"}
  return g.lock;
}
/* the finger's speed over its last tenth of a second (px per ms); 0 if it paused before lifting */
function glideSpeed(g){
  var t=g.trail,n=t.length,now=performance.now();if(n<2||now-t[n-1][0]>120)return 0;
  var i=n-1;while(i>0&&t[n-1][0]-t[i-1][0]<=100)i--;
  var dt=t[n-1][0]-t[i][0];return dt>0?(t[n-1][1]-t[i][1])/dt:0;
}
/* "applied", "passed" or "" (not a swipe): sideways past 18% of the card's width (56 to 80px), or a quick flick past 28px */
function glideDir(g,card){
  var v=glideSpeed(g),flick=Math.abs(v)>0.4&&Math.abs(g.dx)>28&&(v>0)===(g.dx>0);
  var need=Math.min(80,Math.max(56,(card?card.offsetWidth:360)*0.18));
  return g.lock==="x"&&(Math.abs(g.dx)>need||flick)?(g.dx>0?"applied":"passed"):"";
}
/* a box that asks something (consent, an employer's questions, the paywall) is open over the deck: no swipe goes through it */
function glideBoxOpen(){return !!(document.getElementById("kitConsent")||document.getElementById("kitAsk")||document.getElementById("kitSheet")||document.getElementById("paywall")||document.getElementById("stConfirm"))}
function glideLate(deck){
  deck.addEventListener("touchstart",function(e){
    /* only while the last card is still on its way out; otherwise the top card handles its own swipes. The cards under the top one
       do not take touches (pointer-events:none), so this finger is on the flying card or on the deck itself */
    if(!busy||e.touches.length!==1)return;
    var hit=e.target.closest&&e.target.closest(".card");
    var t=e.touches[0],g=glideTrack(t.clientX,t.clientY),node=e.target,moved=null;
    /* the touch keeps going to the element it started on, even after the deck redraws it away, so listen there */
    function top(){return busy?null:deck.querySelector(".card.top")}
    function off(){node.removeEventListener("touchmove",mv);node.removeEventListener("touchend",up);node.removeEventListener("touchcancel",cancel)}
    function mv(ev){
      if(ev.touches.length!==1){cancel();return}
      var p=ev.touches[0];if(glideMove(g,p.clientX,p.clientY)!=="x")return;
      if(ev.cancelable)ev.preventDefault();
      var c=top();if(c){if(c!==moved){moved=c;c.style.transition="none"}setDrag(c,g.dx)}
    }
    function cancel(){off();if(moved&&moved.isConnected){moved.style.transition="";clearCardStyle(moved)}}
    function up(){
      off();var dir=glideDir(g,top()||hit),tries=0;
      if(moved)moved.style.transition="";
      (function commit(){
        if(busy&&tries++<60){setTimeout(commit,25);return}         /* the last card is still on its way out */
        var c=deck.querySelector(".card.top");if(!c)return;
        if(dir&&!busy&&!glideBoxOpen())decide(dir);else if(moved&&moved.isConnected)clearCardStyle(moved);
      })();
    }
    node.addEventListener("touchmove",mv,{passive:false});node.addEventListener("touchend",up);node.addEventListener("touchcancel",cancel);
  },{passive:true});
}
function bindDrag(card){
  var drag=false,g=null;
  if(card.parentNode&&!card.parentNode.__glideLate){card.parentNode.__glideLate=true;glideLate(card.parentNode)}
  function start(x,y){if(busy)return false;drag=true;g=glideTrack(x,y);card.style.transition="none";return true}
  function move(x,y,e){
    if(!drag)return;
    if(glideMove(g,x,y)!=="x")return;
    if(e&&e.cancelable)e.preventDefault();
    setDrag(card,g.dx);
  }
  function end(){
    if(!drag)return;
    drag=false;card.style.transition="";
    var dir=glideDir(g,card);
    if(dir)decide(dir);else clearCardStyle(card);
  }
  function cancel(){if(!drag)return;drag=false;card.style.transition="";clearCardStyle(card)}
  card.addEventListener("touchstart",function(e){if(e.touches.length!==1){cancel();return}var t=e.touches[0];start(t.clientX,t.clientY)},{passive:true});
  card.addEventListener("touchmove",function(e){if(e.touches.length!==1)return;var t=e.touches[0];move(t.clientX,t.clientY,e)},{passive:false});
  card.addEventListener("touchend",end);
  card.addEventListener("touchcancel",cancel);
  card.addEventListener("pointerdown",function(e){
    if(e.pointerType==="touch")return;
    if(e.pointerType==="mouse"&&e.button!==0)return;
    if(start(e.clientX,e.clientY)){try{card.setPointerCapture(e.pointerId)}catch(x){}}
  });
  card.addEventListener("pointermove",function(e){if(e.pointerType!=="touch")move(e.clientX,e.clientY,null)});
  card.addEventListener("pointerup",function(e){if(e.pointerType!=="touch")end()});
  card.addEventListener("pointercancel",function(e){if(e.pointerType!=="touch")cancel()});
}
`;

var ALIAS_NORM=`var ALIAS={js:"javascript",ts:"typescript",py:"python",postgres:"postgresql",psql:"postgresql",reactjs:"react","react.js":"react",nodejs:"node","node.js":"node",k8s:"kubernetes",tf:"terraform",ml:"machine learning","ux research":"user research"};
function norm(s){var k=String(s).trim().toLowerCase();return ALIAS.hasOwnProperty(k)?ALIAS[k]:k}
function locHit(a,b){a=norm(a);b=norm(b);if(!b)return false;var i=a.indexOf(b);while(i>-1){var pre=i===0||!/[a-z0-9]/.test(a.charAt(i-1));var post=i+b.length>=a.length||!/[a-z0-9]/.test(a.charAt(i+b.length));if(pre&&post)return true;i=a.indexOf(b,i+1)}return false}`;

var FEATURES={
 glide:{name:"Phone swipe",note:"Swipes work the way thumbs move: a curved or quick swipe counts, a vertical drag scrolls the card instead, and the browser can no longer cancel a swipe halfway. Replaces Easy swipe and Axis lock.",patch:function(s){
   var a=s.indexOf("function bindDrag(card){"),b=s.indexOf("function decide(dir){");
   if(a<0||b<0)throw new Error("bindDrag not found");
   return s.slice(0,a)+GLIDE+s.slice(b);
 }},
 easy:{name:"Easy swipe",note:"Swipe commits at 60px, or a quick 30px flick, instead of 110px.",apply:function(w){
   if(w.__uaplyGlide)return;                                   /* Phone swipe already does this, better */
   var d=w.document,deck=d.getElementById("deck"),sx=0,dx=0,t0=0;
   deck.addEventListener("pointerdown",function(e){sx=e.clientX;dx=0;t0=performance.now()},true);
   deck.addEventListener("pointermove",function(e){dx=e.clientX-sx},true);
   function release(e){
     if(w.__axisY)return;
     var a=Math.abs(dx),v=a/Math.max(1,performance.now()-t0);
     if(a>110||!(a>60||(a>30&&v>0.5)))return;
     e.stopPropagation();d.getElementById(dx>0?"btnYes":"btnNo").click();
   }
   deck.addEventListener("pointerup",release,true);
   /* a phone can cut a sideways swipe short (pointercancel) when the finger drifts: it still counts once it went far enough */
   deck.addEventListener("pointercancel",release,true);
 }},
 confirm:{name:"Confirm apply",note:"Saving to Applied by swipe, button or → key asks for confirmation first. Passing stays instant.",apply:function(w){
   var d=w.document,ok=false,sx=0,dx=0;
   function ask(){
     if(d.getElementById("stConfirm"))return;
     var card=d.querySelector(".card.top");if(!card)return;
     var role=card.querySelector("h2").textContent,co=card.querySelector(".chead p").textContent,pct=card.querySelector(".ring b").textContent,who="you";
     try{var p=JSON.parse(w.localStorage.getItem(w.__uaplyKey)).profile;if(p.custom&&p.name)who=p.name}catch(x){}
     var o=d.createElement("div");o.id="stConfirm";
     o.style.cssText="position:fixed;inset:0;z-index:50;display:grid;place-items:center;padding:16px;background:rgba(0,0,0,.45)";
     o.innerHTML='<div role="dialog" aria-modal="true" aria-label="Confirm application" style="background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:18px;padding:22px;max-width:380px;width:100%;box-shadow:var(--shadow)"><h2 style="margin:0 0 6px;font:800 20px var(--display)">Save '+co+' to Applied?</h2><p style="margin:0 0 16px;color:var(--muted)">'+role+' · '+pct+' match. This saves it to your list as '+who+'. Nothing is sent to the company.</p><div style="display:flex;gap:10px;justify-content:flex-end"><button class="btn ghost" id="stNo" type="button">Cancel</button><button class="btn" id="stYes" type="button">Save</button></div></div>';
     d.body.appendChild(o);
     var yes=d.getElementById("stYes");yes.focus();
     function close(){o.remove()}
     d.getElementById("stNo").onclick=close;
     o.addEventListener("keydown",function(e){if(e.key==="Escape")close()});
     yes.onclick=function(){close();ok=true;d.getElementById("btnYes").click();ok=false};
   }
   d.addEventListener("click",function(e){
     if(!ok&&e.target.closest&&e.target.closest("#btnYes")){e.stopPropagation();e.preventDefault();ask()}
   },true);
   d.addEventListener("keydown",function(e){
     if(d.getElementById("stConfirm")){if(e.key==="ArrowRight"||e.key==="ArrowLeft")e.stopPropagation();return}
     if(e.key==="ArrowRight"&&!ok){var t=e.target&&e.target.tagName;if(t==="INPUT"||t==="SELECT"||t==="TEXTAREA")return;e.stopPropagation();e.preventDefault();ask()}
   },true);
   var deck=d.getElementById("deck");
   deck.addEventListener("pointerdown",function(e){sx=e.clientX;dx=0},true);
   deck.addEventListener("pointermove",function(e){dx=e.clientX-sx},true);
   deck.addEventListener("pointerup",function(e){
     if(w.__axisY||dx<=110||(w.__uaplyGlide&&e.pointerType==="touch"))return;   /* with Phone swipe, a touch swipe is decided there */
     e.stopPropagation();
     var c=d.querySelector(".card.top");
     if(c){c.style.transition="";c.style.transform="";c.style.background="";c.style.borderColor="";c.style.boxShadow="";c.querySelectorAll(".stamp").forEach(function(s){s.style.opacity=0})}
     d.getElementById("edgeY").style.opacity=0;d.getElementById("edgeN").style.opacity=0;
     dx=0;ask();
   },true);
 }},
 axis:{name:"Axis lock",note:"A mostly vertical drag scrolls the card and never swipes it; a sideways drag swipes.",apply:function(w){
   if(w.__uaplyGlide)return;                                   /* Phone swipe has its own direction lock */
   var d=w.document,deck=d.getElementById("deck"),sx=0,sy=0,lock="";
   w.__axisY=false;
   deck.addEventListener("pointerdown",function(e){sx=e.clientX;sy=e.clientY;lock="";w.__axisY=false},true);
   deck.addEventListener("pointermove",function(e){
     if(!lock){var ax=Math.abs(e.clientX-sx),ay=Math.abs(e.clientY-sy);if(ax>8||ay>8){lock=ay>ax*1.2?"y":"x";w.__axisY=lock==="y"}}
     if(lock==="y")e.stopPropagation();
   },true);
   /* iPhone: once a drag is clearly sideways, keep Safari from turning it into a scroll. Otherwise Safari cancels the
      swipe part-way (pointercancel) and the card snaps back. Up-and-down drags still scroll the card. */
   var tx=0,ty=0,tlock="";
   deck.addEventListener("touchstart",function(e){var t=e.touches[0];if(t){tx=t.clientX;ty=t.clientY;tlock=""}},{capture:true,passive:true});
   deck.addEventListener("touchmove",function(e){
     var t=e.touches[0];if(!t)return;
     if(!tlock){var ax=Math.abs(t.clientX-tx),ay=Math.abs(t.clientY-ty);if(ax>6||ay>6)tlock=ay>ax*1.2?"y":"x"}
     if(tlock==="x"&&e.cancelable&&!(e.target.closest&&e.target.closest("details,input,textarea,select")))e.preventDefault();
   },{capture:true,passive:false});
 }},
 caps:{name:"Must-have caps",note:"If pay, work style or experience is a clear miss, the match is capped at 45% and the card says why.",patch:function(s){
   s=once(s,"return {pct:Math.round(total),rows:rows,matched:matched};","var pct=Math.round(total);var hard=rows[2].s===0||rows[3].s===0||ex<0.5;if(hard&&pct>45)pct=45;return {pct:pct,rows:rows,matched:matched,capped:hard};");
   return once(s,"<small>How well your profile fits what they ask for</small>","<small>'+(m.capped?\"Capped at 45%: a must-have (pay, work style or experience) is missing\":\"How well your profile fits what they ask for\")+'</small>");
 }},
 smart:{name:"Smarter matching",note:"Skill aliases (JS = JavaScript, Postgres = PostgreSQL, k8s, ...) and whole-word city matching (\"Bos\" no longer matches Boston).",patch:function(s){
   s=once(s,'function norm(s){return String(s).trim().toLowerCase()}',ALIAS_NORM);
   return once(s,"norm(job.loc).indexOf(norm(p.loc))>-1","locHit(job.loc,p.loc)");
 }},
 top2:{name:"Top 2 reasons",note:"The card shows the two criteria costing (or earning) the most points, with a Show all criteria toggle.",patch:function(s){
   var a=s.indexOf("function critHTML(m){"),b=s.indexOf("function cardHTML(q,cls)");
   if(a<0||b<0)throw new Error("critHTML not found");
   s=s.slice(0,a)+CRIT_TOP2+s.slice(b);
   return once(s,"</style>",CSS_TOP2+"</style>");
 },apply:function(w){
   var d=w.document;
   function toggle(b){var ul=b.closest(".crit");ul.classList.toggle("open");b.textContent=ul.classList.contains("open")?"Show fewer":"Show all criteria"}
   d.addEventListener("pointerdown",function(e){var b=e.target.closest&&e.target.closest("[data-more]");if(b){e.stopPropagation();e.preventDefault();toggle(b)}},true);
   d.addEventListener("click",function(e){var b=e.target.closest&&e.target.closest("[data-more]");if(b&&e.detail===0)toggle(b)},true);
 }},
 fit:{name:"Compact fit",note:"Short windows: the card keeps a usable minimum height (the page scrolls instead of crushing it), the cards behind it no longer show through, and padding tightens.",patch:function(s){return once(s,"</style>",CSS_FIT+"</style>")},apply:function(w){      /* mark three-digit scores so the style above can fit "100%" inside its ring */
   var d=w.document,deck=d.getElementById("deck");if(!deck)return;
   function mark(){var bs=d.querySelectorAll(".ring b");for(var i=0;i<bs.length;i++)bs[i].classList.toggle("r3",bs[i].textContent.length>3)}
   new w.MutationObserver(mark).observe(deck,{childList:true,subtree:true,characterData:true});mark();
 }},
 notice:{name:"Example-profile notice",note:"While you are still on the example profile, a notice says so and offers Enter your details. No job counters.",patch:function(s){return once(s,"</style>",CSS_NOTICE+"</style>")}},
 guide:{name:"Progress & profile notice",note:"Shows 'N jobs left · M applied' above the deck, and a notice with an Enter your details button while you are still on the example profile.",patch:function(s){return once(s,"</style>",CSS_GUIDE+"</style>")}},
 tap:{name:"Bigger tap targets",note:"Tabs, filters, buttons and checkboxes are at least 44px tall so they are easy to hit on a phone.",patch:function(s){return once(s,"</style>",CSS_TAP+"</style>")}},
 dates:{name:"Applied dates",note:"Each application in the Applied tab shows the date you applied.",patch:function(s){return once(s,"'<small>Sent as '","'<small>Applied '+new Date(x.d.at).toLocaleDateString(undefined,{month:\"short\",day:\"numeric\"})+' · sent as '")}},
 hint:{name:"Swipe hint",note:"First-time visitors see the top card wiggle left and right once to show that it can be swiped (skipped with reduced motion).",apply:function(w){
   var d=w.document,tips=d.getElementById("tips");
   if(!tips||tips.hidden||w.matchMedia("(prefers-reduced-motion: reduce)").matches)return;
   setTimeout(function(){var c=d.querySelector(".card.top");if(c&&c.animate)c.animate([{transform:"translateX(0)"},{transform:"translateX(30px) rotate(1.6deg)"},{transform:"translateX(-30px) rotate(-1.6deg)"},{transform:"translateX(0)"}],{duration:1100,easing:"ease-in-out"})},700);
 }},
 nav:{name:"Bottom navigation",note:"Bottom bar with three dropdowns: Services (Full-time, Part-time, Internships, Coop), Dashboard (Overview, Applied, Accepted, Rejected, Interviews), Profile (Profile setup, Filters, Account, Plan & billing, Data & privacy). Adds part-time, internship and co-op listings.",patch:function(s){return window.UAplyNav.patch(s)},apply:function(w,host){window.UAplyNav.apply(w,host)}},
 live:{name:"Real jobs",note:"Loads real, current postings from employers' public job boards (Greenhouse, Lever, Ashby, and any other feed switched on in the server's settings) through this server's back end, hides the made-up examples, and links each card to the original posting. Indeed and ZipRecruiter have no open API, so they are not included.",patch:function(s){return window.UAplyLive.patch(s)},apply:function(w,host){return window.UAplyLive.apply(w,host)}},
 kit:{name:"Apply assistant",note:"After a swipe right on a real posting: a ready-to-send note, Copy, an email draft (opens your mail app; you press send) and a button to the employer's application page. UAply cannot submit applications itself.",patch:function(s){return window.UAplyLive.kit.patch(s)},apply:function(w,host){window.UAplyLive.kit.apply(w,host)}},
 submit:{name:"Send applications",note:"Swipe right sends the application through this server: in test mode to a simulated recruiter inbox (nothing leaves this computer, see /outbox), in live mode by email to the recruiter after you review and press Send. Swipe left only records a pass; nothing is sent. Needs Bottom navigation, Real jobs and Apply assistant, which turn on with it.",apply:function(w,host){return window.UAplyLive.submit.apply(w,host)}},
 profile:{name:"Application profile",note:"Profile gets what LinkedIn, Indeed, ZipRecruiter and Handshake collect for a fast, complete application: phone, resume link, LinkedIn and portfolio, school and major, work authorization and sponsorship, start date, opportunity types and a default note. Shows a readiness score and checks your links. Needs Bottom navigation.",patch:function(s){return window.UAplyProfile.patch(s)},apply:function(w,host){window.UAplyProfile.apply(w,host)}},
 anim:{name:"Card rise motion",note:"The next card eases up into place after each swipe (skipped when reduced motion is on).",patch:function(s){return once(s,"</style>",CSS_RISE+"</style>")}},
 a11y:{name:"Screen reader announce",note:"A hidden live region announces the new top job after each swipe.",apply:function(w){
   var d=w.document,lr=d.createElement("div");
   lr.setAttribute("aria-live","polite");lr.style.cssText="position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden";d.body.appendChild(lr);
   function say(){var c=d.querySelector(".card.top");lr.textContent=c?c.querySelector("h2").textContent+" at "+c.querySelector(".chead p").textContent+", "+c.querySelector(".ring b").textContent+" match":"No more jobs in this view"}
   new w.MutationObserver(say).observe(d.getElementById("deck"),{childList:true});say();
 }},
 backend:{name:"Mock back end",note:"Pretends to be a server: each apply/pass/withdraw and profile save is sent as an API call with latency, shown in the log below. Nothing leaves your browser.",apply:function(w,host){
   var K=w.__uaplyKey,logEl=host&&host.getElementById("log");if(!logEl)return;
   var proto=w.Storage.prototype,orig=proto.setItem,prev={},prevProfile="";
   function snap(){try{var d=JSON.parse(w.localStorage.getItem(K));prev={};Object.keys(d.decisions||{}).forEach(function(k){prev[k]=d.decisions[k].s});prevProfile=JSON.stringify(d.profile||{})}catch(e){prev={};prevProfile=""}}
   function line(m){logEl.classList.add("on");var p=host.createElement("div");p.innerHTML=m;logEl.appendChild(p);logEl.scrollTop=logEl.scrollHeight}
   function call(method,path,body){
     var t=Math.round(150+Math.random()*350);
     line("<b>"+method+"</b> "+path+" "+body+" …");
     setTimeout(function(){line("&nbsp;&nbsp;← "+(method==="POST"?"201 Created":"200 OK")+" in "+t+"ms")},t);
   }
   snap();
   proto.setItem=function(k,v){
     orig.call(this,k,v);
     if(this!==w.localStorage||k!==K)return;
     try{
       var d=JSON.parse(v),cur={};
       Object.keys(d.decisions||{}).forEach(function(id){cur[id]=d.decisions[id].s;if(prev[id]!==cur[id])call(cur[id]==="applied"?"POST":"PUT",cur[id]==="applied"?"/api/applications":"/api/decisions/"+id,JSON.stringify({jobId:+id,status:cur[id],matchPct:d.decisions[id].pct}))});
       Object.keys(prev).forEach(function(id){if(!(id in cur))call("DELETE","/api/decisions/"+id,"")});
       var pj=JSON.stringify(d.profile||{});if(pj!==prevProfile)call("PUT","/api/profile","{"+(d.profile&&d.profile.name?"name, title, skills, salary…":"…")+"}");
       prev=cur;prevProfile=pj;
     }catch(e){}
   };
 }}
};
FEATURES.chat={name:"Assistant and feedback",note:"A Help button (bottom right) opens UAply Assistant: answers from UAply's help articles (written by AI when an API key is set on the server, and labeled AI or Automated either way), one-question-at-a-time feedback, problem reports, a way to reach a person, and a one-tap rating after the third application in a visit. Needs this server's back end.",apply:function(w,host){window.UAplyChat.apply(w,host)}};
FEATURES.learn={name:"Learns from your swipes",note:"UAply learns what you like from your own swipes (work style, type, role, company, pay, years asked, city, skills, where the job came from) and reorders the deck, starting from the match score. Each card says what it learned (\"Learned from your swipes: +9. You've liked 7 of 8 remote jobs.\"), 1 in 5 cards is something different, your filters still decide what you see, and Profile, Filters has Reset what UAply learned. Stays on this device; never uses voluntary answers, work authorization or GPA. Sandbox only.",patch:function(s){return window.UAplyLearn.patch(s)},apply:function(w,host){window.UAplyLearn.apply(w,host)}};
FEATURES.resume={name:"Fill from your resume",note:"Profile setup, Background and links gets a Fill from your resume box: choose a PDF, Word or text resume and UAply fills every empty profile field it finds (name, email, phone, links, headline, summary, school, major, graduation, GPA, most recent job, skills, city, state, ZIP). Fields you already typed are never changed; a Replace button appears where the resume differs. Each answer shows the line it came from. The file is read on this server for a moment and not kept, and also becomes the resume sent with applications if you have none. Needs Bottom navigation and this server's back end. Sandbox only.",apply:function(w,host){if(!window.UAplyResume)throw new Error("needs uaply-resume.js");window.UAplyResume.apply(w,host)}};
var ORDER=["glide","easy","confirm","axis","caps","smart","top2","nav","profile","resume","live","kit","submit","fit","guide","notice","tap","dates","hint","anim","a11y","backend","chat","learn"];   /* chat after kit: it wraps the apply hook set by kit. learn last: it reorders the deck the other features built */

function build(on,key){
  return fetch("prod-index.html",{cache:"no-store"}).then(function(r){return r.text()}).then(function(src){
    var err="";
    window.__uaplyBuildKey=key;
    try{src=once(src,'var KEY="hireswipe.v1";','var KEY="'+key+'";')}catch(e){err+="Storage key: "+e.message+". "}
    ORDER.forEach(function(k){if(on[k]&&FEATURES[k].patch){try{src=FEATURES[k].patch(src)}catch(e){err+=FEATURES[k].name+": "+e.message+". "}}});
    return {src:src,err:err};
  });
}
/* Load the patched copy into frame. `on` = {featureKey:true}. `key` = this instance's own localStorage key. */
function run(frame,on,key,done){
  if(on.submit)on=Object.assign({},on,{nav:true,live:true,kit:true});   /* sending applications needs these three */
  if(on.profile)on=Object.assign({},on,{nav:true});                     /* the profile fields live in the navigation's Profile sections */
  if(on.resume)on=Object.assign({},on,{nav:true});                      /* Fill from your resume sits on Profile setup's Background and links step */
  return build(on,key).then(function(b){
    frame.onload=function(){
      var w=frame.contentWindow;w.__uaplyKey=key;
      ORDER.forEach(function(k){if(on[k]&&FEATURES[k].apply){try{FEATURES[k].apply(w,document)}catch(e){b.err+=FEATURES[k].name+": "+e.message+". "}}});
      if(done)done(b.err);
    };
    frame.srcdoc=b.src;
  });
}
window.UAplyEnv={FEATURES:FEATURES,ORDER:ORDER,run:run};
})();
