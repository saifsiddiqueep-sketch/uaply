/* "chat" experiment: UAply Assistant, for the sandbox and dev instances (never loaded by prod).
   A chat button opens a support assistant that answers from UAply's help articles (chat_api.py). With an API key
   on the server the answers are written by AI and the panel says so; without one it says the answers come
   from the help articles. Every answer names its source and asks whether it helped.
   Feedback is collected one question at a time (rating, then one follow-up chosen by the rating, then an optional
   email for a reply), and a one-tap rating appears after the third application in a visit, at most every 14 days.
   Nothing here sees or sends the person's profile: only what they type into the chat. */
(function(){
var CSS=`
#uaChatBtn{position:fixed;right:16px;bottom:var(--above-nav,calc(96px + var(--safe-b,env(safe-area-inset-bottom,0px))));z-index:40;display:flex;align-items:center;gap:8px;min-height:48px;padding:0 18px 0 14px;border:0;border-radius:999px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--accent-ink);font-weight:700;font-size:14.5px;box-shadow:var(--shadow);cursor:pointer}
#uaChatBtn svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
#uaChatBtn:focus-visible,#uaChat button:focus-visible,#uaChat input:focus-visible,#uaNudge button:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
#uaChat{position:fixed;right:16px;bottom:calc(var(--above-nav,96px) + 60px);z-index:45;width:min(390px,calc(100vw - 24px));height:min(580px,calc(100vh - 190px));display:flex;flex-direction:column;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow);overflow:hidden}
#uaChat[hidden],#uaNudge[hidden]{display:none}
#uaChat .hd{display:flex;align-items:center;gap:10px;padding:12px 12px 12px 16px;border-bottom:1px solid var(--line)}
#uaChat .hd b{font:800 16px var(--display,inherit)}
#uaChat .tag{font:700 14px var(--mono,ui-monospace,monospace);letter-spacing:.06em;padding:3px 8px;border-radius:6px;background:var(--bg);color:var(--accent);border:1px solid var(--line)}
#uaChat .x{margin-left:auto;border:0;background:none;color:var(--muted);min-width:44px;min-height:44px;border-radius:10px;font-size:22px;cursor:pointer}
#uaChat .x:hover{background:var(--bg)}
#uaChat .log{flex:1;overflow:auto;padding:14px;display:flex;flex-direction:column;gap:10px;background:var(--bg)}
#uaChat .msg{max-width:88%;padding:10px 13px;border-radius:16px;font-size:14.5px;line-height:1.45;white-space:normal;overflow-wrap:anywhere}
#uaChat .bot{align-self:flex-start;background:var(--surface);border:1px solid var(--line);border-bottom-left-radius:6px}
#uaChat .me{align-self:flex-end;background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--accent-ink);border-bottom-right-radius:6px}
#uaChat .src{display:block;margin-top:6px;font-size:14px;color:var(--muted)}
#uaChat .chips{display:flex;flex-wrap:wrap;gap:6px;align-self:flex-start;max-width:100%}
#uaChat .chips button{border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:999px;padding:7px 13px;min-height:44px;font:600 14px inherit;cursor:pointer}
#uaChat .chips button:hover{border-color:var(--accent)}
#uaChat .chips button.pri{background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--accent-ink);border-color:transparent}
#uaChat .chips.rate button{min-width:44px;padding:7px 10px}
#uaChat .typing{align-self:flex-start;color:var(--muted);font-size:20px;letter-spacing:3px;padding:2px 12px}
#uaChat form{display:flex;gap:8px;padding:10px 12px;border-top:1px solid var(--line);background:var(--surface)}
#uaChat input{flex:1;min-width:0;min-height:44px;padding:0 14px;border:1px solid var(--line);border-radius:999px;background:var(--bg);color:var(--ink);font:inherit}
#uaChat form button{min-width:44px;min-height:44px;border:0;border-radius:999px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--accent-ink);font-weight:700;padding:0 16px;cursor:pointer}
#uaChat .ft{padding:0 14px 10px;font-size:14px;color:var(--muted);background:var(--surface)}
#uaChat .ft button{display:inline-flex;align-items:center;min-height:44px;margin-left:4px;padding:0 4px;border:0;background:none;color:var(--accent);font:inherit;font-size:14px;font-weight:600;text-decoration:underline;cursor:pointer}
#uaChat .bot .src a{color:var(--accent);text-decoration:underline}
#uaNudge{position:fixed;right:16px;bottom:calc(var(--above-nav,96px) + 60px);z-index:44;width:min(330px,calc(100vw - 24px));background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);padding:14px;display:flex;flex-direction:column;gap:10px}
#uaNudge p{margin:0;font-weight:700;padding-right:44px}
#uaNudge small{color:var(--muted)}
#uaNudge .x{position:absolute;top:4px;right:4px;border:0;background:none;color:var(--muted);min-width:44px;min-height:44px;font-size:20px;cursor:pointer}
#uaNudge .row{display:flex;gap:6px}
#uaNudge .row button{flex:1;min-height:44px;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:12px;font-weight:700;cursor:pointer}
#uaNudge .row button:hover{border-color:var(--accent)}
@media (max-width:520px){#uaChat{left:12px;right:12px;width:auto;bottom:calc(var(--above-nav,96px) + 54px)}#uaChatBtn span{display:none}#uaChatBtn{padding:0 13px}}
/* phones: the Help button sits at the right end of the header row instead of in the thumb's path to Apply (it lay 17 px from the
   Apply button at 390x844). The header keeps room for it, the panel and the rating question open under the header, and the bottom
   corner belongs to Pass / Undo / Apply and the tabs again. Hiring mode hides the button, so the header keeps its full width there. */
@media (max-width:700px),(max-height:500px){
 #uaChatBtn{top:10px;bottom:auto;min-height:44px;height:44px}
 body:not(.hire):has(>#uaChatBtn)>header.bar{padding-right:106px}
 #uaChat{top:62px;bottom:var(--above-nav,96px);height:auto}
 #uaNudge{top:62px;bottom:auto}
}
@media (max-width:520px){#uaChatBtn{padding:0 11px}body:not(.hire):has(>#uaChatBtn)>header.bar{padding-right:56px;column-gap:8px}}
/* a short turned phone (667x375): the page itself scrolls a little, and a fixed button stayed put while the header row went up, so it lay
   over the top of the card (the sign-up card's Last name box). There it scrolls with the header row it belongs to (October 22, 2026). */
@media (max-height:500px) and (orientation:landscape){#uaChatBtn{position:absolute}}
/* the account button shows the email from 481 px (below that only the initial, uaply-nav.js): there it gives up the Help button's room */
@media (min-width:481px) and (max-width:520px){.hdrbtn{max-width:min(60vw,calc(100vw - 190px))}}
@media (min-width:521px) and (max-width:700px){.hdrbtn{max-width:min(60vw,calc(100vw - 240px))}}
@media (prefers-reduced-motion:no-preference){#uaChat:not([hidden]),#uaNudge:not([hidden]){animation:uaUp .18s ease-out}@keyframes uaUp{from{transform:translateY(8px);opacity:0}to{transform:none;opacity:1}}}
`;

var RATING_WORDS=["","Very poor","Poor","Okay","Good","Excellent"];
var STARTERS=[["ask","How do I apply?"],["ask","How do I set up my profile?"],["ask","Why don't I see any jobs?"],["ask","How do plans and billing work?"],["bug","Report a problem"],["fb","Give feedback"],["human","Talk to a person"]];
var EMAIL=/^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$/;

function apply(w,host){
  var d=w.document,A=w.__uaply||null;
  /* inside a store app (the iPhone app, App Store guideline 3.1.1; the Android app and the Play wrapper): an answer never gives a plan's
     price or how to pay. Those sentences are left out and "Plans are managed on uaply.net." is said instead; the website shows it as it is */
  var IOS_PAY=/\$\d|\bStripe\b|card number|Manage billing|Choose (Plus|Pro)\b|\ba month\b|\bpaid plans?\b|\bpayments?\b|\bcancel\b|\bbuy\b|\bbought\b/i;
  function iosApp(){try{if(w.__uaplyStoreApp)return !!w.__uaplyStoreApp();var c=w.top.Capacitor;return !!(c&&c.getPlatform&&/^(ios|android)$/.test(c.getPlatform()))}catch(e){return false}}
  function iosAnswer(t){
    t=String(t||"");if(!iosApp()||!IOS_PAY.test(t))return t;
    var out=[];t.split(/\n/).forEach(function(line){
      var ss=line.match(/[^.!?]+[.!?]+["')]*\s*|[^.!?]+$/g)||[line];   /* sentences, without a lookbehind (iPhones before iOS 16.4 cannot parse one) */
      var keep=ss.filter(function(s){return !IOS_PAY.test(s)}).join("").trim();
      if(keep||!line.trim())out.push(keep);
    });
    return (out.join("\n").replace(/\n{3,}/g,"\n\n").trim()+" Plans are managed on uaply.net.").trim();
  }
  w.__uaplyIosAnswer=iosAnswer;   /* for the tests */
  /* the Support and Privacy pages sit in legal/ next to the app (one folder up on the hosted /dev/ and /sandbox/ copies) */
  var lp=(host&&host.defaultView&&host.defaultView.location.pathname)||"/",LEGAL=/\/(sandbox|dev)\/(index\.html)?$/.test(lp)?"../legal/":"legal/",SUPPORT=LEGAL+"support.html",PRIVACY=LEGAL+"privacy.html";
  if(!d.body)return;
  var st=d.createElement("style");st.textContent=CSS;d.head.appendChild(st);
  var K=(w.__uaplyKey||"uaply")+".chat";
  function load(){try{return JSON.parse(w.localStorage.getItem(K))||{}}catch(e){return {}}}
  function store(o){try{w.localStorage.setItem(K,JSON.stringify(o))}catch(e){}}
  var CFG={ai:false,support:""},hist=[],flow=null,started=false,busy=false,cfgSettled=false,cfgReady=null,histPlain=false;

  /* ---------- launcher and panel ---------- */
  var btn=d.createElement("button");btn.type="button";btn.id="uaChatBtn";btn.setAttribute("aria-haspopup","dialog");btn.setAttribute("aria-expanded","false");btn.setAttribute("aria-controls","uaChat");
  btn.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/><path d="M8.5 11h.01M12 11h.01M15.5 11h.01"/></svg><span>Help</span>';
  btn.setAttribute("aria-label","Help and feedback: open UAply Assistant");
  var p=d.createElement("section");p.id="uaChat";p.hidden=true;p.setAttribute("role","dialog");p.setAttribute("aria-modal","false");p.setAttribute("aria-labelledby","uaChatT");
  p.innerHTML='<div class="hd"><b id="uaChatT">UAply Assistant</b><span class="tag" id="uaChatTag">AI</span><button type="button" class="x" id="uaChatX" aria-label="Close assistant">&times;</button></div>'+
    '<div class="log" id="uaChatLog" role="log" aria-live="polite" aria-relevant="additions"></div>'+
    '<form id="uaChatF" autocomplete="off"><label for="uaChatIn" style="position:absolute;left:-9999px">Message</label><input id="uaChatIn" maxlength="1000" placeholder="Ask a question…"><button type="submit" aria-label="Send">Send</button></form>'+
    '<div class="ft" id="uaChatFt"></div>';
  d.body.appendChild(btn);d.body.appendChild(p);
  var log=p.querySelector("#uaChatLog"),input=p.querySelector("#uaChatIn"),form=p.querySelector("#uaChatF");

  function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
  function scroll(){log.scrollTop=log.scrollHeight}
  function bubble(cls,html){var m=d.createElement("div");m.className="msg "+cls;m.innerHTML=html;log.appendChild(m);scroll();return m}
  function botSay(text,extra){return bubble("bot",esc(text).replace(/\n/g,"<br>")+(extra||""))}
  function meSay(text){return bubble("me",esc(text).replace(/\n/g,"<br>"))}
  function chips(list,cls){
    var c=d.createElement("div");c.className="chips"+(cls?" "+cls:"");c.setAttribute("role","group");
    list.forEach(function(it){var b=d.createElement("button");b.type="button";b.textContent=it.label;if(it.aria)b.setAttribute("aria-label",it.aria);if(it.pri)b.className="pri";b.onclick=function(){c.remove();it.run()};c.appendChild(b)});
    log.appendChild(c);scroll();return c;
  }
  function clearChips(){log.querySelectorAll(".chips").forEach(function(c){c.remove()})}
  function typing(on){var t=log.querySelector(".typing");if(on&&!t){t=d.createElement("div");t.className="typing";t.textContent="•••";t.setAttribute("aria-label","UAply Assistant is typing");log.appendChild(t);scroll()}else if(!on&&t)t.remove()}
  function hint(ph){input.placeholder=ph||"Ask a question…"}

  function open(){
    p.hidden=false;btn.setAttribute("aria-expanded","true");hideNudge(false);
    if(!started){started=true;greet()}
    if(CFG.ai)providerName();   /* look the AI company's name up now, so it is usually ready before the first question */
    setTimeout(function(){input.focus()},30);
  }
  function close(){p.hidden=true;btn.setAttribute("aria-expanded","false");btn.focus()}
  btn.onclick=function(){p.hidden?open():close()};
  p.querySelector("#uaChatX").onclick=close;
  p.addEventListener("keydown",function(e){if(e.key==="Escape"){e.stopPropagation();close()}});

  /* where the person is in the app, so feedback can say which screen it was about */
  function where(){
    var c=d.querySelector('#bnav [aria-current="true"]');if(!c)return "";
    var a=c.querySelector("span"),b=c.querySelector("small");
    return ((a?a.textContent:"")+(b&&b.textContent?", "+b.textContent:"")).replace(/\s+/g," ").trim().slice(0,40);
  }
  function knownEmail(){
    var au=w.__uaplyAuth?w.__uaplyAuth():null;if(au&&au.user&&au.user.email)return au.user.email;
    var pr=A&&A.S&&A.S.profile;return pr&&pr.custom&&EMAIL.test(pr.email||"")&&!/example\.com$/.test(pr.email)?pr.email:"";
  }
  function goTo(dest){
    var parts=String(dest||"").split(":"),nb=d.getElementById("nb-"+parts[0]);if(!nb)return;
    nb.click();var it=d.querySelector('.nwrap[data-k='+parts[0]+'] .nitem[data-v="'+parts[1]+'"]');
    if(it)it.click();else if(parts[0]==="prof"&&w.__uaplyOpenProf)w.__uaplyOpenProf(parts[1]);   /* "preferences" and "resume" now live inside Profile setup */
    if(w.innerWidth<=520)close();
  }
  /* a static preview with no server (uaply-nav.js decides): nothing to ask or send to, so every answer says that, with a link */
  function isPreview(){return !!(w.__uaplyPreview&&w.__uaplyPreview())}
  function previewText(){return w.__uaplyPreviewText||"This is a preview with no server."}
  function previewSay(){botSay(previewText(),'<span class="src"><a href="'+esc(w.__uaplyPreviewUrl||"https://uaply.net")+'" target="_blank" rel="noopener noreferrer">uaply.net</a></span>')}
  function post(path,body){
    if(isPreview())return Promise.resolve({ok:false,j:{error:previewText()}});
    return w.fetch(path,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})
      .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j}},function(){return {ok:false,j:{}}})})
      .catch(function(){return {ok:false,j:{error:"I couldn't reach UAply just now. Check your connection and try again."}}});
  }
  /* the AI company's name, exactly as the Privacy Policy gives it ("our AI provider, X," / "our AI provider (X)"): that page is the one
     place the name is written. Not found or not reachable: "" (the notice then points to the Privacy Policy), and it is asked again next time.
     A slow or stalled request waits at most 3 seconds (the chat is busy meanwhile, so a hang would lock it: no chips, typing ignored),
     then gives "" and the next ask starts a fresh lookup. Nothing is sent either way: the line still asks first. */
  var provider=null;
  function providerName(){
    if(!provider){var pr=provider=w.fetch(PRIVACY,{credentials:"same-origin"}).then(function(r){return r.ok?r.text():""}).then(function(t){
      pr.done=true;var m=/our AI provider(?:,\s*|\s*\()([A-Z][A-Za-z0-9.&' -]{0,40}?)\s*[,)]/.exec(t);if(!m&&provider===pr)provider=null;return m?m[1]:"";
    },function(){pr.done=true;if(provider===pr)provider=null;return ""})}
    var cur=provider;
    return Promise.race([cur,new Promise(function(r){setTimeout(function(){if(!cur.done&&provider===cur)provider=null;r("")},3000)})]);
  }
  /* the remembered Yes counts only for the company it named: an older yes (a bare time, from the unnamed "Continue" line), a yes to the
     "named in our Privacy Policy" line, or a different company in the Privacy Policy later all ask again */
  function agreed(name){var a=load().aiOk;return !!(name&&a&&typeof a==="object"&&a.to===name)}
  /* a stored yes that can never count (a bare time, or the one-question yes to the unnamed line) is dropped; a yes to a different company
     is dropped once the Privacy Policy's name is known. A yes to a named company is kept while the name cannot be read (it does not count
     then, and does not travel with the question either: see send) */
  function dropStale(name){var s=load(),a=s.aiOk;if(!a)return;
    if(typeof a!=="object"||!a.to||(name&&a.to!==name)){delete s.aiOk;store(s);paintMode()}}

  /* ---------- greeting: say clearly that this is automated / AI ---------- */
  function paintMode(){
    p.querySelector("#uaChatTag").textContent=CFG.ai?"AI":"AUTOMATED";
    p.querySelector("#uaChatTag").title=CFG.ai?"Answers are written by AI":"Answers come from UAply's help articles";
    var ft=p.querySelector("#uaChatFt");
    ft.textContent=CFG.ai
      ?"AI-written answers can be wrong. Don't share passwords or sensitive details."
      :"Automated answers from UAply's help articles. Don't share passwords or sensitive details.";
    /* a Yes takes one tap, so taking it back takes one tap too: after it, nothing goes to the AI company until the person says yes again */
    var ok=load().aiOk;
    if(CFG.ai&&ok&&ok.to){var b=d.createElement("button");b.type="button";b.id="uaChatStopAi";b.textContent="Stop sending to the AI";
      b.onclick=function(){var s=load();delete s.aiOk;store(s);paintMode();botSay("Done. Nothing more goes to our AI provider unless you say yes again.");input.focus()};
      ft.appendChild(d.createTextNode(" "));ft.appendChild(b)}
  }
  function greet(){
    botSay(CFG.ai
      ?"Hi! I'm UAply Assistant, an AI. I can answer questions about UAply and pass your feedback to the team. I can't see your profile or applications, and I can make mistakes."
      :"Hi! I'm UAply Assistant, an automated helper (not a person). I answer from UAply's help articles and pass your feedback to the team. I can't see your profile or applications.");
    if(isPreview())previewSay();
    botSay("What can I help with?");
    starters();
  }
  function starters(){
    chips(STARTERS.map(function(s){return {label:s[1],pri:s[0]==="fb",run:function(){
      if(s[0]==="ask"){meSay(s[1]);ask(s[1])}
      else if(s[0]==="fb"){meSay(s[1]);startFeedback(null,"chat")}
      else if(s[0]==="bug"){meSay(s[1]);startBug()}
      else {meSay(s[1]);startHuman()}
    }}}));
  }

  /* ---------- questions ---------- */
  /* ask(q, how): how is unset for a new question; after the checks it is "ai" (a counted yes to the named company), "once" (Yes to the
     unnamed line: this question only) or "plain" (no yes: sent with aiOk false, so the server answers from the help articles and nothing
     leaves UAply). cfgWaited: the wait for the chat's settings is over. */
  function ask(q,ok,cfgWaited){
    if(busy)return;
    if(isPreview()){clearChips();previewSay();starters();return}
    /* the settings (/api/chat/config) say whether AI is on. Until they arrive the chat cannot know, so it waits for them (at most 3 seconds:
       a stalled request must not lock the chat) instead of sending with whatever yes is stored (CTO round 2: a stored yes to another
       company, or to the unnamed line, went out as aiOk: true with no notice when a starter was tapped before the settings came) */
    if(!ok&&!cfgSettled&&!cfgWaited&&cfgReady){
      busy=true;clearChips();typing(true);
      Promise.race([cfgReady,new Promise(function(r){setTimeout(r,3000)})]).then(function(){typing(false);busy=false;ask(q,ok,true)});
      return;
    }
    /* AI off (or not known) and no stored yes: nothing can go to the AI company, the server answers from the help articles */
    if(!ok&&!CFG.ai&&!load().aiOk){ask(q,"plain");return}
    /* AI answers on: the first time, say in one line which outside AI company the message goes to, and send it only on Yes (remembered on
       this device). No sends nothing (October 22: the Help chat went to the AI provider without asking; Apple 5.1.2(i) wants the
       company named and a clear yes). The company's name is read from the Privacy Policy, so that page stays its one source. */
    if(!ok){   /* AI on, or a stored yes to check before it travels with the question */
      busy=true;clearChips();typing(true);
      providerName().then(function(name){
        typing(false);busy=false;
        if(agreed(name)){ask(q,"ai");return}
        dropStale(name);
        /* AI off, or the settings never came: a yes that does not count is not used, and the question goes without one (the server
           keeps it from the AI); if AI turns out to be on, the answer says so and the next question asks */
        if(!CFG.ai){ask(q,"plain");return}
        botSay("AI answers are on: to write the reply, your message goes to our AI provider"+(name?", "+name:" (named in our Privacy Policy)")+". UAply does not keep it. Send it?",
          '<span class="src"><a href="'+PRIVACY+'" target="_blank" rel="noopener noreferrer" data-privacy="1">Privacy Policy</a></span>');
        /* both buttons look the same: the choice is not nudged. A yes to the line without a name sends this question only (to:"" never
           counts as agreed), so the named line is shown next time */
        chips([{label:"Yes, send it",run:function(){meSay("Yes, send it");if(!name){ask(q,"once");return}var s=load();s.aiOk={at:Date.now(),to:name};store(s);paintMode();ask(q,"ai")}},
          {label:"No, don't send",run:function(){var s=load();if(s.aiOk){delete s.aiOk;store(s);paintMode()}meSay("No, don't send");botSay("Nothing was sent. You can still talk to a person, report a problem or give feedback.");starters()}}]);
      });
      return;
    }
    busy=true;clearChips();
    /* the stored yes travels with this question only when it was just checked ("ai") or given for it ("once", stored for the one post
       and removed straight after it); for "plain" it is set aside for the post and put back. Turns sent without a yes stay on UAply, so
       they are dropped before a question goes to the AI company (the server sends the whole history to it) */
    var aiNow=ok==="ai"||ok==="once",st=load(),kept=st.aiOk;
    if(ok==="once")st.aiOk={at:Date.now(),to:""};else if(!aiNow)delete st.aiOk;
    if(ok!=="ai")store(st);
    if(aiNow&&histPlain)hist=[];
    histPlain=!aiNow;
    hist.push({role:"user",content:q});hist=hist.slice(-10);
    typing(true);
    post("/api/chat",{messages:hist,aiOk:!!load().aiOk}).then(function(r){   /* aiOk: the person said Yes to the AI notice; the server checks it too */
      typing(false);busy=false;
      if(r.j&&r.j.aiConsent&&!CFG.ai){CFG.ai=true;paintMode()}   /* AI is on after all (the settings came late or not at all): the next question asks */
      if(!r.ok){botSay((r.j&&r.j.error)||"Something went wrong on my side.");chips([{label:"Try again",run:function(){hist.pop();meSay(q);ask(q)}},{label:"Talk to a person",run:function(){meSay("Talk to a person");startHuman()}}]);return}
      var j=r.j||{};
      if(!j.aiConsent&&j.ai!==undefined&&!!j.ai!==CFG.ai){CFG.ai=!!j.ai;paintMode()}
      var src=(j.sources||[]).map(function(s){return s.title}).join(", ");
      j.answer=iosAnswer(j.answer||"");
      botSay(j.answer||"",src?'<span class="src">From help: '+esc(src)+'</span>':'');
      hist.push({role:"assistant",content:j.answer||""});
      var acts=[],ids=(j.sources||[]).map(function(s){return s.id});
      (j.sources||[]).slice(0,1).forEach(function(s){if(s.go)acts.push({label:"Take me there",pri:true,run:function(){goTo(s.go)}})});
      acts.push({label:"Yes, that helped",run:function(){meSay("Yes, that helped");post("/api/feedback",{topic:"answer",helpful:true,articles:ids,page:where(),source:"chat"});botSay("Great! Anything else?");starters()}});
      acts.push({label:"No",aria:"No, that did not help",run:function(){meSay("No");notHelpful(q,ids,j.answer)}});
      if(j.needs_human)acts.push({label:"Talk to a person",run:function(){meSay("Talk to a person");startHuman()}});
      (j.related||[]).forEach(function(s){acts.push({label:s.title,run:function(){meSay(s.title);ask(s.title)}})});
      chips(acts);
    });
    if(ok!=="ai"){st=load();if(kept&&typeof kept==="object"&&kept.to)st.aiOk=kept;else delete st.aiOk;store(st)}
  }
  /* a "No" carries the answer's own words (not only its article ids), so a wrong or offensive answer can be reported as it was written.
     The server keeps 2,000 characters of text: the person's note first, then as much of the answer as fits */
  function reportText(note,ans){
    var n=note?"What I was looking for: "+note+"\n":"",a="The answer I got: ";
    return n+a+String(ans||"").trim().slice(0,Math.max(0,2000-n.length-a.length));
  }
  function notHelpful(q,ids,ans){
    botSay("Sorry about that. What were you looking for, or what was wrong with the answer? Your note and the answer above go to the team so we can fix it.");
    flow={kind:"answer",step:"text",data:{topic:"answer",helpful:false,articles:ids},answer:ans};
    hint("What were you looking for?");
    /* an answer that did not help is the moment people want a person: offer it here, not two taps later behind Skip */
    chips([{label:"Talk to a person",pri:true,run:function(){meSay("Talk to a person");flow=null;hint();post("/api/feedback",{topic:"answer",helpful:false,articles:ids,text:reportText("",ans),page:where(),source:"chat"});startHuman()}},
      {label:"Skip",run:function(){meSay("Skip");finish({topic:"answer",helpful:false,articles:ids,text:reportText("",ans)})}}]);
  }

  /* ---------- feedback: one question at a time ---------- */
  function startFeedback(rating,source){
    clearChips();
    if(isPreview()){previewSay();starters();return}
    flow={kind:"fb",step:"rating",data:{topic:source==="nudge"?"nudge":"general",source:source}};
    if(rating){setRating(rating);return}
    botSay("Thanks for helping make UAply better! How would you rate UAply so far?");
    chips([1,2,3,4,5].map(function(n){return {label:String(n),aria:n+" out of 5, "+RATING_WORDS[n],run:function(){meSay(n+" out of 5 ("+RATING_WORDS[n]+")");setRating(n)}}})
      .concat([{label:"Skip",run:function(){meSay("Skip");setRating(null)}}]),"rate");
    botSay("1 is very poor, 5 is excellent.");
  }
  function setRating(n){
    flow.data.rating=n;flow.step="text";
    var q=n===null?"What's one thing we should know?":(n<=2?"Sorry it's not working well. What went wrong?":(n===3?"Thanks. What's one thing that would make UAply better for you?":"Glad you like it! What do you like most, and is there anything we could add?"));
    botSay(q);hint("Type your answer…");
    chips([{label:"Skip",run:function(){meSay("Skip");askFollowup()}}]);
  }
  function startBug(){
    clearChips();
    if(isPreview()){previewSay();starters();return}
    flow={kind:"bug",step:"what",data:{topic:"bug",source:"chat"}};
    botSay("Sorry about that. What happened? A sentence is enough.");hint("What happened?");
    chips([{label:"Cancel",run:function(){meSay("Cancel");flow=null;hint();botSay("No problem. Anything else?");starters()}}]);
  }
  function startHuman(){
    clearChips();
    if(isPreview()){previewSay();starters();return}
    var sp=' <span class="src"><a href="'+SUPPORT+'" target="_blank" rel="noopener noreferrer" data-support="1">Support page: what to include, reply times</a></span>';
    if(CFG.support){
      botSay("You can email the UAply team at "+CFG.support+". Or leave a message here and we'll reply by email.",
        '<span class="src"><a href="mailto:'+esc(CFG.support)+'">'+esc(CFG.support)+'</a></span>'+sp);
      chips([{label:"Leave a message here",pri:true,run:function(){meSay("Leave a message here");startContact()}},{label:"Back to topics",run:function(){meSay("Back to topics");starters()}}]);
    }else{botSay("We usually reply within 2 business days.",sp);startContact()}
  }
  function startContact(){
    flow={kind:"contact",step:"text",data:{topic:"contact",source:"chat"}};
    botSay("What do you need help with? A person on the UAply team will read it and reply by email.");hint("Your message…");
    chips([{label:"Cancel",run:function(){meSay("Cancel");flow=null;hint();botSay("No problem. Anything else?");starters()}}]);
  }
  function askFollowup(){
    flow.step="followup";hint();
    var em=knownEmail(),req=flow.kind==="contact";
    botSay(req?"Which email should we reply to?":"Can we email you if we have a question about this?");
    var list=[];
    if(em)list.push({label:"Yes, at "+em,pri:true,run:function(){meSay("Yes, at "+em);flow.data.email=em;flow.data.followup=true;finish(flow.data)}});
    list.push({label:em?"Use a different email":"Yes, I'll type my email",run:function(){meSay(em?"Use a different email":"Yes");flow.step="email";hint("you@example.com");botSay("Type the email we should use.")}});
    if(!req)list.push({label:"No thanks",run:function(){meSay("No thanks");flow.data.followup=false;finish(flow.data)}});
    chips(list);
  }
  function finish(data){
    if(isPreview()){clearChips();hint();flow=null;previewSay();starters();return}
    data.page=where();clearChips();hint();
    typing(true);
    post("/api/feedback",data).then(function(r){
      typing(false);
      if(!r.ok){botSay((r.j&&r.j.error)||"I couldn't send that just now.");chips([{label:"Try again",run:function(){finish(data)}}]);return}
      var s=load();s.given=Date.now();store(s);
      flow=null;
      var dv=r.j&&r.j.delivery,who=data.email||"you",ownerHint=false;
      if(data.topic==="contact"||data.topic==="bug"){
        /* say what really happened: only "emailed" means the team has it by email */
        if(dv==="emailed")botSay("Sent to the UAply team"+(data.email?". They will reply to "+who+" by email.":". They read every message, but you did not leave an email, so they cannot reply."));
        else if(dv==="failed")botSay("We saved your message, but the email to our team did not go through, so it may take a little longer."+(CFG.support?" You can also write to "+CFG.support+".":""));
        else if(CFG.owner){botSay("Saved, but not emailed: no real email is connected on this computer yet. The message is in your Feedback inbox. Connect Gmail in setup and these arrive by email.");ownerHint=true}
        else botSay("Got it. A person on the UAply team will read this"+(data.email?" and reply to "+who+" by email.":"."));
      }else botSay(data.topic==="answer"?"Thanks, that helps us improve these answers.":"Thank you! A person on the UAply team reads every message.");
      botSay("Anything else I can help with?");
      if(ownerHint)chips([{label:"Open the Feedback inbox",run:function(){meSay("Open the Feedback inbox");try{w.open("/feedback","_blank","noopener")}catch(e){}starters()}},{label:"Connect Gmail",run:function(){meSay("Connect Gmail");try{w.open("/setup#gmail","_blank","noopener")}catch(e){}starters()}}]);
      else starters();
    });
  }

  /* typed text goes to the current feedback step, or becomes a question */
  form.addEventListener("submit",function(e){
    e.preventDefault();
    var t=input.value.trim();if(!t||busy)return;
    input.value="";meSay(t);
    if(flow){
      clearChips();
      if(flow.step==="email"){
        if(!EMAIL.test(t)){botSay("That email doesn't look right. Try again, like name@example.com.");return}
        flow.data.email=t;flow.data.followup=true;finish(flow.data);return;
      }
      if(flow.kind==="bug"&&flow.step==="what"){flow.data.text="What happened: "+t;flow.step="doing";botSay("Thanks. What were you trying to do when it happened? (optional)");hint("What were you trying to do?");chips([{label:"Skip",run:function(){meSay("Skip");askFollowup()}}]);return}
      if(flow.kind==="bug"&&flow.step==="doing"){flow.data.text+="\nTrying to: "+t;askFollowup();return}
      if(flow.kind==="answer"){flow.data.text=reportText(t,flow.answer);finish(flow.data);return}
      if(flow.step==="text"){flow.data.text=t;askFollowup();return}
      if(flow.step==="rating"){var n=parseInt(t,10);if(n>=1&&n<=5){setRating(n);return}botSay("Pick a number from 1 to 5, or tap Skip.");return}
      if(flow.step==="followup"){botSay("Tap one of the options above, or type your email.");if(EMAIL.test(t)){flow.data.email=t;flow.data.followup=true;finish(flow.data)}return}
    }
    ask(t);
  });

  /* ---------- one-tap rating after the third application in a visit, at most every 14 days ---------- */
  var nudge=d.createElement("div");nudge.id="uaNudge";nudge.hidden=true;nudge.setAttribute("role","dialog");nudge.setAttribute("aria-modal","false");nudge.setAttribute("aria-labelledby","uaNudgeT");
  nudge.innerHTML='<button type="button" class="x" aria-label="Close">&times;</button><p id="uaNudgeT">Quick question: how is UAply working for you?</p>'+
    '<div class="row" role="group" aria-label="Rate from 1 to 5">'+[1,2,3,4,5].map(function(n){return '<button type="button" data-r="'+n+'" aria-label="'+n+' out of 5, '+RATING_WORDS[n]+'">'+n+'</button>'}).join("")+'</div><small>1 is very poor, 5 is excellent. One tap, then one short question.</small>';
  d.body.appendChild(nudge);
  function hideNudge(remember){if(!nudge.hidden){nudge.hidden=true;if(remember){var s=load();s.nudged=Date.now();store(s)}}}
  nudge.querySelector(".x").onclick=function(){hideNudge(true);btn.focus()};
  /* a tap anywhere else means "not now": the question floats where the bottom-bar menus open, so a tap meant for Applied landed on
     the "3" and sent a rating nobody chose */
  d.addEventListener("pointerdown",function(e){if(!nudge.hidden&&!nudge.contains(e.target))hideNudge(false)},true);
  nudge.addEventListener("click",function(e){
    var b=e.target.closest("[data-r]");if(!b)return;
    var n=+b.getAttribute("data-r");hideNudge(true);
    open();clearChips();meSay(n+" out of 5 ("+RATING_WORDS[n]+")");startFeedback(n,"nudge");
  });
  var applied=0,DAY=864e5;
  function maybeNudge(){
    var s=load(),now=Date.now();
    if(applied<3||!p.hidden)return;
    if(s.nudged&&now-s.nudged<14*DAY)return;
    if(s.given&&now-s.given<30*DAY)return;
    if(d.getElementById("kitConsent")||d.getElementById("kitSheet")||d.getElementById("paywall")||d.getElementById("stConfirm"))return;
    nudge.hidden=false;
    var sv=load();sv.nudged=now;store(sv);
  }
  var prevDecision=w.__uaplyOnDecision;
  w.__uaplyOnDecision=function(dir){
    var r=prevDecision?prevDecision.apply(this,arguments):undefined;
    /* someone who keeps swiping instead of answering has said "not now": the question goes, so it never sits on the card they
       are swiping (on a small phone it covers the middle of the card). It was already noted as asked when it opened. */
    hideNudge(false);
    if(dir==="applied"){applied++;setTimeout(maybeNudge,2500)}
    return r;
  };
  w.__uaplyFeedback=function(){open();clearChips();startFeedback(null,"chat")};

  /* mode: AI or help articles, from the server */
  paintMode();
  cfgReady=w.fetch("/api/chat/config").then(function(r){return r.ok?r.json():null}).then(function(c){
    if(c){CFG.ai=!!c.ai;CFG.support=c.support||"";CFG.owner=!!c.owner;paintMode();if(CFG.ai&&started)providerName()}
  }).catch(function(){}).then(function(){cfgSettled=true});
}

window.UAplyChat={apply:apply};
})();
