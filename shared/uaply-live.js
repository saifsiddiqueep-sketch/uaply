/* "live", "kit" and "submit" experiments for the sandbox and dev instances (never loaded by prod).
   live   : loads real postings from this server's /api/jobs (see jobs_api.py) and links every card to the original.
   kit    : after a swipe right on a real posting, a sheet with a ready-to-send note, Copy, an email draft and the
            employer's application page.
   submit : the sheet also delivers the application through this server (see uaply_api.py): in test mode to a
            simulated recruiter inbox, in live mode by email to the recruiter after the user reviews and presses Send.
            Swipes in either direction are logged so you can see whether people actually swipe. */
(function(){
function once(src,a,b){if(src.indexOf(a)<0)throw new Error("patch target not found: "+a.slice(0,40));return src.replace(a,function(){return b})}
var MAX_CACHE=400,MAX_AGE=30*24*3600*1000;
/* Job Tracker keeps (October 22, 2026): every application up to MAX_APPLIED and the newest MAX_PASSED passes (the oldest passes go first:
   such a job may come back to the deck, nothing else is lost). Each swipe carries a short copy of its row ("row": title, company, place,
   link, kind), so the row stays in Job Tracker after the job leaves the feed or the saved copy below; a swiped job's saved copy never
   ages out. Before, a saved copy older than MAX_AGE, or past the 400 newest swiped ones (passes counted), took its row with it. */
var MAX_APPLIED=2000,MAX_PASSED=1000;
function rowOf(j){return {t:String(j.role||"").slice(0,160),c:String(j.co||"").slice(0,120),l:String(j.loc||"").slice(0,120),u:/^https:\/\//.test(j.url||"")?String(j.url).slice(0,600):"",ty:String(j.type||"job").slice(0,12),m:String(j.mode||"").slice(0,10)}}
/* the oldest passes beyond MAX_PASSED, and the oldest applications beyond MAX_APPLIED, are let go; true when something was */
function trimDecisions(S){
  if(!S||!S.decisions)return false;
  var ks=Object.keys(S.decisions),gone={},n=0;
  ["passed","applied"].forEach(function(st){
    var cap=st==="passed"?MAX_PASSED:MAX_APPLIED,mine=ks.filter(function(k){var x=S.decisions[k];return x&&(st==="passed"?x.s==="passed":x.s!=="passed")});
    if(mine.length<=cap)return;
    mine.sort(function(a,b){return (+S.decisions[a].at||0)-(+S.decisions[b].at||0)}).slice(0,mine.length-cap).forEach(function(k){delete S.decisions[k];gone[k]=1;n++});
  });
  if(n&&Array.isArray(S.history))S.history=S.history.filter(function(id){return !gone[id]});
  return n>0;
}

function cacheKey(){return (window.__uaplyBuildKey||"hireswipe")+".live"}
function readCache(){
  try{
    var c=JSON.parse(localStorage.getItem(cacheKey()));
    if(!c||!Array.isArray(c.jobs))return [];
    /* a swiped job never ages out: marked kept when saved, or (a copy saved before October 22) found among the saved swipes */
    var dec={};try{dec=(JSON.parse(localStorage.getItem(window.__uaplyBuildKey||"hireswipe"))||{}).decisions||{}}catch(e){}
    return c.jobs.filter(function(j){return j&&j.id>=100000&&(j.kept||dec[j.id]||Date.now()-(j.seen||0)<MAX_AGE)});
  }catch(e){return []}
}
/* the saved copy of the job list: every job the person swiped on first (their Applied and Passed rows need the job itself, even after it
   leaves the feed), then the newest of the rest, MAX_CACHE in all. Keeping only the last MAX_CACHE of the list lost the swiped ones as
   soon as the feed passed 400 postings (it is over 1,000 now). */
function writeCache(jobs,decided){
  jobs=jobs.filter(function(j){return j&&!j.stub});
  var keep=decided?jobs.filter(function(j){return decided[j.id]}):[],rest=decided?jobs.filter(function(j){return !decided[j.id]}):jobs;
  /* applications before passes, newest last; a full copy dropped here still has its row in the swipe itself (rowOf) */
  var rank=function(j){var x=decided[j.id];return (x.s==="passed"?0:1e15)+(+x.at||0)};
  keep.sort(function(a,b){return rank(a)-rank(b)});
  keep=keep.slice(-MAX_CACHE);keep.forEach(function(j){j.kept=1});rest.forEach(function(j){if(j.kept)delete j.kept});
  try{localStorage.setItem(cacheKey(),JSON.stringify({jobs:keep.concat(rest.slice(-Math.max(0,MAX_CACHE-keep.length)))}))}catch(e){}
}

/* ---------------- live ---------------- */
function patch(s){
  var cached=readCache();
  var extra=cached.length?","+JSON.stringify(cached).slice(1,-1).replace(/<\//g,"<\\/"):"";
  s=once(s,'regional cookbooks."}','regional cookbooks."}'+extra);
  s=once(s,"var JOB_BY_ID={};JOBS.forEach(function(j){JOB_BY_ID[j.id]=j});",
    "var JOB_BY_ID={};JOBS.forEach(function(j){JOB_BY_ID[j.id]=j});\nwindow.__uaplyJobs={add:function(list){var n=0;list.forEach(function(j){if(!JOB_BY_ID[j.id]){JOBS.push(j);JOB_BY_ID[j.id]=j;n++}else{var o=JOB_BY_ID[j.id];if(o.stub){for(var f in j)o[f]=j[f];delete o.stub;return}if(j.posted)o.posted=j.posted;if(j.perks)o.perks=j.perks;if(j.type)o.type=j.type;if(j.jobType)o.jobType=j.jobType;o.comm=!!j.comm}});renderAll();return n}};\n"+
    /* Links open as real anchor clicks (a user gesture), which popup blockers accept; window.open can be refused silently. */
    "window.__uaplyOpen=function(u){if(!/^https:\\/\\//.test(u||\"\"))return;var a=document.createElement(\"a\");a.href=u;a.target=\"_blank\";a.rel=\"noopener noreferrer\";document.body.appendChild(a);a.click();a.remove()};");
  /* a swipe on a real posting is kept when the page starts, even before the job list arrives (or after the job left the feed): the start-up
     read used to drop every decision whose job was not in the list yet, and the next save made that loss permanent */
  s=once(s,'if(JOB_BY_ID[k]&&x&&(x.s==="applied"||x.s==="passed"))','if((JOB_BY_ID[k]||+k>=100000)&&x&&(x.s==="applied"||x.s==="passed"))');
  s=once(s,"return !S.decisions[j.id]&&","return !S.decisions[j.id]&&!j.stub&&(j.live||!window.__uaplyHideSamples)&&");
  /* a swipe's own copy of its row (rowOf) is kept at start-up, and a swiped job that is in neither the list nor the saved copy comes back
     from it as a stand-in ("stub": its row in Job Tracker, never a card on the deck; the real posting replaces it when the list has it) */
  s=once(s,"S.history=(Array.isArray(d.history)?d.history:[])",
    'Object.keys(S.decisions).forEach(function(k){var r=d.decisions[k]&&d.decisions[k].row;if(!r||typeof r!=="object")return;'+
    'var u=String(r.u||"");var row={t:String(r.t||"").slice(0,160),c:String(r.c||"").slice(0,120),l:String(r.l||"").slice(0,120),u:u.indexOf("https://")===0?u.slice(0,600):"",ty:String(r.ty||"job").slice(0,12),m:String(r.m||"").slice(0,10)};'+
    'S.decisions[k].row=row;if(!JOB_BY_ID[k]&&+k>=100000&&row.t&&row.c){var sj={id:+k,co:row.c,role:row.t,loc:row.l||"Not listed",url:row.u,'+
    'type:["job","parttime","internship","coop"].indexOf(row.ty)>-1?row.ty:"job",mode:["remote","hybrid","onsite"].indexOf(row.m)>-1?row.m:"onsite",'+
    'sal:[0,0],yrs:0,edu:"High school",skills:[],blurb:"",live:true,stub:true,source:""};JOBS.push(sj);JOB_BY_ID[k]=sj}});\n    '+
    "S.history=(Array.isArray(d.history)?d.history:[])");
  s=once(s,"'+money(j.sal[0])+'–'+money(j.sal[1])+'<small>per year</small>","'+(j.sal[1]>0?money(j.sal[0])+'–'+money(j.sal[1])+'<small>per year</small>':'Pay not listed')+'");
  s=once(s,"var salOk=job.sal[1]>=p.salary;","var unk=job.sal[1]<=0;var salOk=unk||job.sal[1]>=p.salary;");
  s=once(s,'s:salOk?1:(sa>=0.9?0.5:0),ask:money(job.sal[0])+" to "+money(job.sal[1])','s:unk?0.5:salOk?1:(sa>=0.9?0.5:0),ask:unk?"Not listed":money(job.sal[0])+" to "+money(job.sal[1])');
  /* every real listing names its source and links to the original; example listings say they are examples */
  s=once(s,"<p class=\"blurb\">'+esc(j.blurb)+'</p>","<p class=\"blurb\">'+esc(j.blurb)+'</p>'+(j.url?'<button type=\"button\" class=\"linkbtn\" data-open=\"'+esc(j.url)+'\">View original posting ↗</button>':'')+(j.live?'<small class=\"note\">Source: '+esc(j.source||'the employer')+'</small>':'<small class=\"note\">Example listing, not a real opening.</small>')+'");
  s=once(s,'toast(dir==="applied"?"Applied to "+job.co+" · "+m.pct+"% match":"Passed on "+job.co,"Undo",undo);',
    'if(dir==="applied"&&(job.live||window.__uaplyMode==="test")&&window.__uaplyQuiet&&window.__uaplySubmitOn){}else{toast(dir==="applied"?"Saved "+job.co+" to Applied · "+m.pct+"% match"+(window.__uaplyPreview&&window.__uaplyPreview()?". "+window.__uaplyPreviewText:""):"Passed on "+job.co,"Undo",undo)}');
  return s;
}

function apply(w,host){
  var d=w.document;
  function open(url){if(w.__uaplyOpen)w.__uaplyOpen(url)}
  /* "View original posting" (on a card) and "Finish on their site" (in Applied) open on a tap or a click: when the same finger or
     mouse button lifts within 10px of where it went down. They used to open on the first touch, so a swipe or a scroll that
     happened to start on the link opened the employer's site (and a mouse drag from it could not swipe the card). The card's
     mouse drag holds the pointer, so the browser's own click never reaches the link; this does the job instead. */
  var tapLink=null;
  d.addEventListener("pointerdown",function(e){
    var b=e.target.closest&&e.target.closest("[data-open]");
    tapLink=b&&(e.pointerType!=="mouse"||e.button===0)?{b:b,id:e.pointerId,x:e.clientX,y:e.clientY}:null;
  },true);
  d.addEventListener("pointercancel",function(e){if(tapLink&&tapLink.id===e.pointerId)tapLink=null},true);   /* the browser took it for a scroll */
  d.addEventListener("pointerup",function(e){
    var t=tapLink;tapLink=null;
    if(!t||t.id!==e.pointerId||Math.abs(e.clientX-t.x)>10||Math.abs(e.clientY-t.y)>10||!t.b.isConnected)return;
    open(t.b.getAttribute("data-open"));
  },true);
  d.addEventListener("click",function(e){
    var b=e.target.closest&&e.target.closest("[data-open]");
    if(b&&e.detail===0)open(b.getAttribute("data-open"));
  },true);

  var el=host&&(host.getElementById("note")||host.getElementById("what"));
  function say(m){if(el)el.textContent=m}
  var REL=!!((host&&host.defaultView&&host.defaultView.UAplyOpts)||{}).release;
  if(REL){            /* a release build never shows the made-up example listings, not even while the real ones load or if they fail to */
    w.__uaplyHideSamples=true;w.__uaplyLoadingJobs=true;
    try{w.__uaply.renderAll()}catch(e){}
  }
  say("Loading real postings…");
  /* On a fresh start the server answers within seconds with the boards it has read so far and says how many are still loading
     ("pending"): the app asks again a few times and adds what came in, so the first visitor never waits for every board. */
  function loadJobs(round){
  return fetch("/api/jobs").then(function(r){
    /* a plain web host with no UAply server (a 404, or an HTML page): a preview. Show the example jobs and say so; a 5xx stays an outage */
    if(r.status===404||(r.ok&&/text\/html/i.test(r.headers.get("content-type")||""))){var pe=new Error("preview");pe.preview=true;throw pe}
    if(!r.ok)throw new Error("HTTP "+r.status);return r.json()}).then(function(data){
    w.__uaplyLoadingJobs=false;
    var now=Date.now(),fresh=(data.jobs||[]).map(function(j){j.seen=now;return j});
    if(fresh.length>=5)w.__uaplyHideSamples=true;      /* set before adding, so the deck renders once */
    var added=w.__uaplyJobs.add(fresh);
    if(w.__uaplyRetryPending)setTimeout(w.__uaplyRetryPending,1500);   /* applications that were waiting for a connection */
    var all=readCache(),ids={};all.forEach(function(j){ids[j.id]=1});
    var byId={};fresh.forEach(function(j){byId[j.id]=j;if(!ids[j.id])all.push(j)});
    all.forEach(function(c){var f=byId[c.id];if(f){c.posted=f.posted;c.perks=f.perks;c.type=f.type;c.jobType=f.jobType;c.comm=!!f.comm;c.via=f.via}});   /* keep saved copies current */
    /* swipes made before rows were copied (October 22): each gets its row as soon as its job is in the list or the saved copy */
    try{var U=w.__uaply,fill=0;if(U&&U.S&&U.S.decisions){all.forEach(function(j){var x=U.S.decisions[j.id];if(x&&!x.row&&!j.stub){x.row=rowOf(j);fill++}});if(fill&&U.save)U.save()}}catch(e){}
    writeCache(all,(w.__uaply&&w.__uaply.S&&w.__uaply.S.decisions)||null);
    var src=Object.keys(data.sources||{}).map(function(k){return k+": "+data.sources[k]}).join(" · ");
    say("Real postings: "+fresh.length+" loaded ("+added+" new). "+src);
    if(data.pending>0&&round<15){
      setTimeout(function(){loadJobs(round+1)},round<3?5000:15000);
      if(fresh.length<5){w.__uaplyLoadingJobs=true;try{w.__uaply.renderAll()}catch(x){}}   /* "Finding jobs for you…", not an empty deck */
    }
  }).catch(function(e){if(round>0)return;   /* a later round that fails changes nothing: the jobs already shown stay */
    w.__uaplyLoadingJobs=false;
    if(e&&e.preview){w.__uaplyPreviewOn=true;w.__uaplyHideSamples=false;w.__uaplyJobsFailed=false;try{w.__uaply.renderAll()}catch(x){}say(w.__uaplyPreviewText||"Preview: example jobs only.");return}
    if(REL)w.__uaplyJobsFailed=true;if(REL){try{w.__uaply.renderAll()}catch(x){}}say(REL?"Could not load jobs ("+e.message+"). Check your connection and try again.":"Could not load real postings ("+e.message+"). Showing the example jobs.")});
  }
  /* the sign-in gate (shared/uaply-signup.js): no request for the job list while nobody is signed in; it is asked for once the gate lifts */
  /* (asked again each time the gate lifts: after a code that confirmed the address, the list that answered 403 "verify" comes now) */
  if(w.__uaplyGateUp){w.__uaplyLoadJobs=function(){loadJobs(0)};return}
  return loadJobs(0);
}

/* ---------------- kit + submit ---------------- */
function kitPatch(s){
  if(s.indexOf("__uaplyOnDecision")>-1)return s;
  s=once(s,'var card=$("deck").querySelector(".card.top");if(!card)return;\n  busy=true;',
    'var card=$("deck").querySelector(".card.top");if(!card)return;\n  if(dir==="applied"&&window.__uaplyReadyGate&&window.__uaplyReadyGate(JOB_BY_ID[+card.getAttribute("data-id")])){card.style.transition="";clearCardStyle(card);return}\n  busy=true;');
  s=once(s,"S.history.push(id);S.tips=false;save();busy=false;renderAll();",
    "S.history.push(id);S.tips=false;save();busy=false;renderAll();if(window.__uaplyOnDecision)window.__uaplyOnDecision(dir,job,m,S.profile,undo,S,save);");
  /* Undo (the button or Z) on an application that already went out: say so, because undo only takes it off the list */
  return once(s,"delete S.decisions[id];save();renderAll();clearToast();",
    "var was=S.decisions[id];delete S.decisions[id];save();renderAll();clearToast();if(window.__uaplyUndone)window.__uaplyUndone(was,JOB_BY_ID[id]);");
}

function kitApply(w,host){
  var d=w.document;
  function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
  var EMAIL=/^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$/;
  function session(){
    try{var k="uaply.session",v=w.localStorage.getItem(k);if(!v){v=Math.random().toString(36).slice(2)+Date.now().toString(36);w.localStorage.setItem(k,v)}return v}catch(e){return "anon"}
  }
  function post(path,body){
    /* a reply that is not JSON (a host's "Bad gateway" page, say) is a server problem, not "you're offline": only a request that never
       arrived rejects, which is what queues the application for when the connection is back */
    if(w.__uaplyPreview&&w.__uaplyPreview())return Promise.resolve({ok:false,j:{error:w.__uaplyPreviewText,code:"preview"}});   /* no server here: say so */
    return w.fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j}},function(){return {ok:false,j:{error:"UAply's server had a problem and nothing was sent. Try again in a moment.",code:"server"}}})});
  }
  /* contact lines under the note, from the Application profile experiment (empty if it is off) */
  function signature(p){
    var x=p.ext||{},rows=[];
    if(x.phone)rows.push("Phone: "+x.phone);
    if(p.email)rows.push("Email: "+p.email);
    if(x.linkedin)rows.push("LinkedIn: "+x.linkedin);
    if(x.portfolio)rows.push("Portfolio: "+x.portfolio);
    if(x.resume)rows.push("Resume: "+x.resume);
    return rows.length?"\n\n"+rows.join("\n"):"";
  }
  function note(job,m,p){
    var skills=(m.matched||[]).slice(0,5).join(", "),name=p.name||"[Your name]";
    var tpl=p.ext&&typeof p.ext.noteTpl==="string"?p.ext.noteTpl.trim():"";
    if(tpl){
      var vals={company:job.co,role:job.role,name:name,title:p.title||"candidate",years:p.years||0,skills:skills||(p.skills||[]).slice(0,5).join(", "),city:p.loc||""};
      return tpl.replace(/\{(company|role|name|title|years|skills|city)\}/g,function(_,k){return vals[k]})+"\n\n"+name+signature(p);
    }
    var intro="I'm "+(p.title?"a "+p.title:"a candidate")+(p.years?" with "+p.years+" years of experience":"")+(skills?", and my background includes "+skills:"")+".";
    var where=p.loc?" I'm based in "+p.loc+".":"";
    return "Hi "+job.co+" team,\n\nI'm interested in the "+job.role+" role"+(job.loc?" ("+job.loc+")":"")+". "+intro+where+" I'd welcome the chance to talk.\n\nThank you for your time,\n"+name+signature(p);
  }
  function copy(text,btn){
    function done(){btn.textContent="Copied";setTimeout(function(){btn.textContent="Copy note"},1500)}
    function fallback(){var t=d.getElementById("kitText");t.select();try{d.execCommand("copy");done()}catch(e){}}
    if(w.navigator.clipboard&&w.navigator.clipboard.writeText){w.navigator.clipboard.writeText(text).then(done,fallback)}else fallback();
  }

  function sheet(job,m,p,undo,S,save){
    if(!job.url||d.getElementById("kitSheet"))return;
    var submitOn=!!w.__uaplySubmitOn&&!!w.__uaplyMode,mode=w.__uaplyMode,live=mode==="live";
    /* ask = show a review screen with a Send button first. Always in live mode; in test mode only where the page opts in (sandbox). */
    var auto=live&&w.__uaplyAuto!==false;     /* live + auto_send (the default): swipe right sends by itself after a short undo window */
    var ask=(live&&!auto)||!!((host&&host.defaultView&&host.defaultView.UAplyOpts)||{}).reviewBeforeSend;
    var target=(live&&w.__uaplyRedirect)||job.contact||(job.instant?"hiring system":"");
    var contact=job.contact||"",profileOk=!!(p.name&&EMAIL.test(p.email||"")&&(!live||p.custom));
    var o=d.createElement("div");o.id="kitSheet";
    o.style.cssText="position:fixed;inset:0;z-index:50;display:grid;place-items:center;padding:16px;background:rgba(0,0,0,.45);overflow:auto";
    var intro=!submitOn
      ?'Saved to your Applied list. UAply does not send applications for you: '+esc(job.co)+' only accepts them on its own page'+(contact?'':', and the posting does not list a recruiter email')+'. Here is a note and the quickest way to finish.'
      :(live&&auto
        ?(target
          ?'<b>'+(w.__uaplyRedirect?'Test redirect. ':'')+'Applying automatically.</b> Your application will be emailed to <b>'+esc(target)+'</b> in a few seconds. Press Undo to cancel. Replies go to your email.'
          :'This posting lists no recruiter email, so UAply cannot email it. Use the application page below to apply on the employer\'s site.')
      :(live
        ?(w.__uaplyRedirect
          ?'<b>Test redirect.</b> Pressing Send emails this application to <b>'+esc(w.__uaplyRedirect)+'</b> instead of the recruiter. Replies go to your email.'
          :'Review your application. Pressing Send emails it to the recruiter'+(contact?' at <b>'+esc(contact)+'</b>':'')+', and replies go to your email.'+(contact?'':' This posting lists no recruiter email, so UAply cannot email it: use the application page instead.'))
        :(ask
          ?'<b>Test mode.</b> Review the note, then press Send. It goes to a simulated recruiter inbox on this computer; nothing is sent to '+esc(job.co)+'.'
          :'<b>Test mode.</b> Your application was delivered to a simulated recruiter inbox on this computer. Nothing was sent to '+esc(job.co)+'.')));
    o.innerHTML='<div role="dialog" aria-modal="true" aria-labelledby="kitH" style="background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:18px;padding:20px;max-width:460px;width:100%;box-shadow:var(--shadow);display:flex;flex-direction:column;gap:12px">'+
      '<h2 id="kitH" style="margin:0;font:800 20px var(--display)">'+(submitOn&&!ask?'Sending to ':'Finish applying to ')+esc(job.co)+'</h2>'+
      '<p style="margin:0;color:var(--muted);font-size:14px">'+intro+'</p>'+
      (!p.custom?'<p style="margin:0;color:var(--mid);font-size:13px">This uses the example profile. Add your own details in Profile setup first.</p>':'')+
      (submitOn&&!profileOk?'<p style="margin:0;color:var(--no);font-size:13px">Add your name and a valid email in Profile setup, under About you, so the recruiter can reply.</p>':'')+
      '<textarea id="kitText" rows="7" aria-label="Application note" style="width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:var(--surface);font:inherit;resize:vertical"></textarea>'+
      '<p id="kitStatus" role="status" style="margin:0;font-size:13.5px;font-weight:600;min-height:1.3em"></p>'+
      '<div style="display:flex;gap:8px;flex-wrap:wrap">'+
        (submitOn&&ask?'<button type="button" class="btn" id="kitSend"'+((!profileOk||(live&&!(contact||w.__uaplyRedirect)))?' disabled':'')+'>Send application</button>':'')+
        (submitOn&&!profileOk?'<button type="button" class="btn" id="kitProfile">Open Profile</button>':'')+
        '<button type="button" class="btn'+(submitOn&&ask?' ghost':'')+'" id="kitOpen">Open application page ↗</button>'+
        '<button type="button" class="btn ghost" id="kitCopy">Copy note</button>'+
        (w.__uaplyAnswers?'<button type="button" class="btn ghost" id="kitAnswers">Copy my answers</button>':'')+
        '<button type="button" class="btn ghost" id="kitMail">Email draft</button>'+
        (submitOn&&!live?'<a class="linkbtn" href="/outbox" target="_blank" rel="noopener noreferrer" style="align-self:center">View test inbox ↗</a>':'')+
      '</div>'+
      '<div style="display:flex;gap:8px;justify-content:space-between;flex-wrap:wrap"><button type="button" class="linkbtn" id="kitUndo">Undo, do not save</button><button type="button" class="btn ghost" id="kitDone">Done</button></div></div>';
    d.body.appendChild(o);
    var ta=d.getElementById("kitText"),statusEl=d.getElementById("kitStatus"),undoBtn=d.getElementById("kitUndo");
    ta.value=(w.__uaplyAutoMsg&&w.__uaplyAutoMsg()&&w.__uaplyMessage)?w.__uaplyMessage(job,m,p):note(job,m,p);
    var cancelled=false,tm=0;
    function close(){clearInterval(tm);o.remove()}
    function setStatus(t,bad){statusEl.textContent=t;statusEl.style.color=bad?"var(--no)":"var(--yes)"}
    function send(){
      clearInterval(tm);
      var sendBtn=d.getElementById("kitSend");if(sendBtn)sendBtn.disabled=true;
      setStatus("Sending…");
      post("/api/apply",{consent:true,confirm_real:live,match:m.pct,note:ta.value,
        job:{id:job.id,co:job.co,role:job.role,url:job.url,source:job.source,loc:job.loc,contact:contact,mode:job.mode,type:job.type||"job",sal:job.sal,blurb:job.blurb},
        profile:{name:p.name,email:p.email,title:p.title,years:p.years,skills:p.skills,loc:p.loc,edu:p.edu,ext:(w.__uaplyApplyExt?w.__uaplyApplyExt():(p.ext||{}))},
        resume:(w.__uaplyResume?w.__uaplyResume():null)
      }).then(function(r){
        var j=r.j||{};
        if(!r.ok){setStatus(j.error||"Could not send.",true);if(sendBtn&&live)sendBtn.disabled=false;return}
        var dec=S&&S.decisions&&S.decisions[job.id];
        if(dec&&(j.status!=="duplicate"||j.was)){dec.sent={at:Date.now(),to:j.to||"",status:j.status==="duplicate"?j.was:j.status};if(save)save()}
        if(j.status==="delivered_test")setStatus("Delivered to the test inbox as "+(j.to||"recruiter")+".");
        else if(j.status==="sent")setStatus("Sent to "+j.to+". Replies go to "+p.email+".");
        else if(j.status==="duplicate")setStatus("You already sent this application.");
        else if(j.status==="handoff")setStatus("This employer takes applications on its own page. Use the button below.");
        else if(j.status==="failed"){setStatus(j.error||"The email could not be sent.",true);if(sendBtn)sendBtn.disabled=false;return}
        else setStatus("Done.");
        var rc=j.receipt,au=w.__uaplyAuth?w.__uaplyAuth():null;
        if(rc)statusEl.textContent+=" "+({digest:"The steps to finish it come by email, once a day with any others.",sent:"Confirmation emailed to "+rc.to+".",delivered_test:testInboxNote(),not_configured:(isRelease?"":"No confirmation email: email sending is not set up yet."),failed:"The confirmation email to "+rc.to+" could not be sent.",held:"Your confirmation email is queued and will arrive later (UAply's email is busy).",bounced:"No confirmation email: emails to "+rc.to+" bounce back.",unverified:"Verify your email (Profile, Account) to get confirmation emails."}[rc.status]||"");
        else if(au&&au.up&&!au.user)statusEl.textContent+=" Sign in to get a confirmation email.";
        if(j.status!=="handoff")undoBtn.hidden=true;
        if(sendBtn&&(j.status==="sent"||j.status==="delivered_test"||j.status==="duplicate"))sendBtn.hidden=true;
      }).catch(function(){setStatus("Could not reach the server.",true);if(sendBtn)sendBtn.disabled=false});
    }
    var sendBtn=d.getElementById("kitSend");if(sendBtn)sendBtn.onclick=send;
    var pb=d.getElementById("kitProfile");
    if(pb)pb.onclick=function(){close();openProfile("about")};   /* the message above asks for the name and email: open that step */
    d.getElementById("kitOpen").onclick=function(){if(w.__uaplyOpen)w.__uaplyOpen(job.url)};
    d.getElementById("kitCopy").onclick=function(){copy(ta.value,this)};
    var ansBtn=d.getElementById("kitAnswers");
    if(ansBtn)ansBtn.onclick=function(){
      var b=this,t=w.__uaplyAnswers();
      function done(){b.textContent="Copied";setTimeout(function(){b.textContent="Copy my answers"},1500)}
      if(w.navigator.clipboard&&w.navigator.clipboard.writeText)w.navigator.clipboard.writeText(t).then(done,function(){setStatus("Copy was blocked by the browser.",true)});else setStatus("Copy is not available here.",true);
    };
    d.getElementById("kitMail").onclick=function(){
      var a=d.createElement("a");a.href="mailto:"+encodeURIComponent(contact).replace("%40","@")+"?subject="+encodeURIComponent("Application: "+job.role)+"&body="+encodeURIComponent(ta.value);
      d.body.appendChild(a);a.click();a.remove();
    };
    d.getElementById("kitDone").onclick=close;
    undoBtn.onclick=function(){cancelled=true;close();undo()};
    o.addEventListener("keydown",function(e){if(e.key==="Escape")close()});
    (d.getElementById("kitSend")&&!d.getElementById("kitSend").disabled?d.getElementById("kitSend"):d.getElementById("kitOpen")).focus();
    if(submitOn&&!ask&&profileOk){
      if(!live||!target)send();          /* test mode, or nothing to email: record it now */
      else{                              /* live: send by itself after a short window in which Undo cancels it */
        var left=Math.max(0,w.__uaplyGrace||0),timer=null;
        var tick=function(){
          if(cancelled){clearInterval(timer);return}
          if(left<=0){clearInterval(timer);send();return}
          setStatus("Sending to "+target+" in "+left+" second"+(left===1?"":"s")+". Press Undo to cancel.");left--;
        };
        timer=setInterval(tick,1000);tick();
      }
    }
    else if(submitOn&&!ask&&!profileOk)setStatus("Not sent yet: your profile needs a name and email.",true);
  }

  /* ---- quiet apply: a swipe right is the whole action, like pressing Submit application ---- */
  var isRelease=!!((host&&host.defaultView&&host.defaultView.UAplyOpts)||{}).release;
  /* with no real email connected yet, a confirmation is only saved in the test inbox page of the owner's own server: say where. A hosted server has none, so say nothing. */
  function testInboxNote(){
    if(!w.__uaplyTestInbox)return isRelease?"":"Confirmation saved in the test inbox.";
    var origin="";try{origin=host.defaultView.location.origin}catch(e){}
    return "Confirmation is in the test inbox: "+origin+w.__uaplyTestInbox;
  }
  var showSheet=!!((host&&host.defaultView&&host.defaultView.UAplyOpts)||{}).showSheet;   /* opt back in to the full sheet */
  function toast(msg,action,fn,ms){
    var old=d.getElementById("kitToast");if(old)old.remove();
    w.clearTimeout(w.__kitToastT);
    var t=d.createElement("div");t.id="kitToast";t.className="toast";t.setAttribute("role","status");
    var s=d.createElement("span");s.textContent=msg;t.appendChild(s);
    if(action){var b=d.createElement("button");b.type="button";b.textContent=action;b.onclick=fn;t.appendChild(b)}
    d.body.appendChild(t);
    if(ms!==0){t.setAttribute("data-until",String(Date.now()+(ms||6000)));w.__kitToastT=w.setTimeout(function(){t.remove()},ms||6000)}
    return {el:t,set:function(x){s.textContent=x}};
  }
  w.__uaplyKitToast=toast;
  /* a hidden tab runs its timers late (Chrome may hold them for minutes), so a "Saved ... Undo" stayed on screen 10 minutes after coming
     back to the tab (apply journey, October 22): when the page is shown again, a message whose time is up goes at once */
  function dropExpired(){var t=d.getElementById("kitToast"),u=t&&+t.getAttribute("data-until");if(u&&Date.now()>=u)t.remove()}
  d.addEventListener("visibilitychange",function(){if(d.visibilityState==="visible")dropExpired()});
  w.addEventListener("pageshow",dropExpired);w.addEventListener("focus",dropExpired);
  /* first application only: say plainly what a swipe right does with the person's details, and get agreement */
  var CONSENT_V=3;   /* 2: also explains the optional hiring-manager message and that voluntary answers are never sent.
                       3 (October 21, 2026, the owner's position, drafted for the Terms in LEGAL-REVIEW.md): the person authorizes UAply to
                       complete and submit applications on their behalf; recorded with the time ({v:3,at,agent:true}), so everyone agrees again once */
  var AGENT_CLAUSE="You authorize UAply to complete and submit job applications on your behalf using the information you provide.";
  w.__uaplyAgentClause=AGENT_CLAUSE;
  function legalBase(){var p=(host&&host.defaultView&&host.defaultView.location.pathname)||"/";return /\/(sandbox|dev)\/(index\.html)?$/.test(p)?"../legal/":"legal/"}   /* the hosted copies live at /dev/ and /sandbox/, with legal/ beside them */
  function consentKey(){return (w.__uaplyKey||"uaply")+".consent"}
  function hasConsent(){try{var c=JSON.parse(w.localStorage.getItem(consentKey()));return !!(c&&c.v===CONSENT_V)}catch(e){return false}}
  /* consentFirst (sandbox): ask once when the swipe deck first opens, so no swipe is ever interrupted by it */
  var consentFirst=!!((host&&host.defaultView&&host.defaultView.UAplyOpts)||{}).consentFirst;
  /* the sandbox opens the box before the first swipe (atStart). A swipe made while that box is open (the keyboard can reach the
     deck behind it) waits for the answer and then goes on, or back. Only one: more presses, or a double tap on a box a swipe
     opened, add nothing, so a job is never sent twice. */
  var consentWait=[],consentAtStart=false;
  /* while a box is open over the deck (this consent box, an employer's questions, the apply sheet, the plan paywall), the arrow
     keys and Z belong to the box, never to the deck behind it. They used to reach it: ArrowRight on a focused button in the box
     applied to the next job behind it, which then sat in Applied without ever being sent; ArrowLeft passed it unseen. */
  d.addEventListener("keydown",function(e){
    var k=e.key;if(k!=="ArrowRight"&&k!=="ArrowLeft"&&k!=="z"&&k!=="Z")return;
    if(d.getElementById("kitConsent")||d.getElementById("kitAsk")||d.getElementById("kitSheet")||d.getElementById("paywall"))e.stopPropagation();
  },true);
  function ensureConsent(go,cancel,atStart){
    if(hasConsent()){go();return}      /* outside hasConsent's try: a problem while applying must never look like "not agreed yet" and bring this box back */
    if(d.getElementById("kitConsent")){if(consentAtStart&&!consentWait.length&&!atStart)consentWait.push([go,cancel]);return}
    consentAtStart=!!atStart;
    var b=legalBase(),o=d.createElement("div");o.id="kitConsent";
    o.style.cssText="position:fixed;inset:0;z-index:60;display:grid;place-items:center;padding:16px;background:rgba(0,0,0,.45);overflow:auto";
    o.innerHTML='<div role="dialog" aria-modal="true" aria-labelledby="kcH" style="background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:18px;padding:20px;max-width:460px;width:100%;box-shadow:var(--shadow);display:flex;flex-direction:column;gap:10px;font-size:14px">'+
      '<h2 id="kcH" style="margin:0;font:800 20px var(--display)">'+(consentFirst?"Before you start swiping":"Before your first application")+'</h2>'+
      '<p style="margin:0">When you swipe right, UAply applies for you at connected employers: employers that have agreed to receive applications through UAply get the details in your profile (your name, email, and anything else you filled in, such as phone, resume file or link, education or work authorization), plus a short message if you turned on "Message the hiring manager". Everywhere else, UAply sends nothing: it saves the job in Applied and takes you to the employer\'s own application page to finish there. UAply never emails a company that has not agreed.</p>'+
      '<p style="margin:0"><b>'+AGENT_CLAUSE+'</b> Today that means two things: UAply sends your application to connected employers, and in the UAply phone app it fills in other employers\' own application forms from your profile for you to review and submit yourself.</p>'+
      '<p style="margin:0">Your voluntary answers (such as race, gender, veteran or disability status) are never sent. They stay on your device unless you copy them yourself.</p>'+
      '<p style="margin:0">The match percentage is worked out automatically from your profile to help order jobs. It never rejects you, and employers make every hiring decision. <a href="'+b+'ai-and-employment.html" target="_blank" rel="noopener noreferrer">How matching works</a></p>'+
      '<p style="margin:0">By continuing you agree to the <a href="'+b+'terms.html" target="_blank" rel="noopener noreferrer">Terms of Service</a> and <a href="'+b+'privacy.html" target="_blank" rel="noopener noreferrer">Privacy Policy</a>.</p>'+
      (consentFirst?'<p style="margin:0">You only see this once. After you agree, every swipe is just a swipe.</p>':'')+
      '<div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap"><button type="button" class="btn ghost" id="kcNo">'+(consentFirst?"Not now":"Cancel")+'</button><button type="button" class="btn" id="kcYes">'+(consentFirst?"Agree and start swiping":"Agree and continue")+'</button></div></div>';
    d.body.appendChild(o);
    d.getElementById("kcYes").focus();
    function answer(ok){o.remove();var waiting=consentWait.splice(0);(ok?go:cancel)();waiting.forEach(function(p){(ok?p[0]:p[1])()})}
    d.getElementById("kcYes").onclick=function(){try{w.localStorage.setItem(consentKey(),JSON.stringify({v:CONSENT_V,at:Date.now(),agent:true}))}catch(e){}answer(true)};
    d.getElementById("kcNo").onclick=function(){answer(false)};
    o.addEventListener("keydown",function(e){if(e.key==="Escape")answer(false)});
  }
  /* step: a Profile setup step ("about", "back"...) to open on. Called from a button it gets the click event, which is ignored */
  function openProfile(step){if(typeof step==="string"&&w.__uaplyOpenProf){w.__uaplyOpenProf(step);return}var b=d.getElementById("nb-prof");if(b){b.click();var it=d.querySelector('.nwrap[data-k=prof] .nitem[data-v=settings]');if(it)it.click()}}

  /* answers the person gave to questions employers' forms asked, kept on this device and sent with each application so the
     same question is never asked twice (the server matches them to each new form; see autofill.py). Beside each answer UAply keeps how
     the question was asked (its words, kind and options, and which employer asked it first), so Profile setup, under Eligibility and
     extras, can list them and let the person change one with the same control. */
  function answersKey(){return (w.__uaplyKey||"uaply")+".answers"}
  function askedKey(){return (w.__uaplyKey||"uaply")+".answersAsked"}
  function readObj(k){try{var a=JSON.parse(w.localStorage.getItem(k));return a&&typeof a==="object"&&!Array.isArray(a)?a:{}}catch(e){return {}}}
  function savedAnswers(){return readObj(answersKey())}
  /* the saved answers that may go with an application to employer `co` (October 22, 2026): an answer kept for one employer ("{at
     <employer>}", autofill.norm) goes only to that employer; an older answer about an employer ("{co}" in its key, a "why us" question,
     or one asked by another employer whose answer names that employer) goes to none. The server drops the same ones (clean_answers). */
  var EMP_Q=/\bwhy\b.*\b(work|join|joining|interested|apply|applying|us|here|company|role|position|team|this)\b|\bwhat (excites|interests|draws|attracts|motivates) you\b|\bcover letter\b|\btell us (about )?why\b|\binterest(ed)? in (this|our|the) (company|role|position|team|job|opportunity)\b|\babout (this|our) (company|role|position|team|mission)\b/i;
  function answersFor(co){
    var a=savedAnswers(),m=savedAsked(),out={},mine="{at "+String(co||"").toLowerCase().replace(/[^a-z0-9]+/g," ").trim().slice(0,60)+"}";
    Object.keys(a).forEach(function(k){
      if(k.indexOf("{at ")===0){if(co&&k.indexOf(mine+" ")===0)out[k]=a[k];return}
      if(k.indexOf("{co}")>-1||EMP_Q.test(k))return;
      var by=String((m[k]&&m[k].co)||"");
      if(by&&co&&by!==co&&String(a[k]).toLowerCase().indexOf(by.toLowerCase())>-1)return;
      out[k]=a[k];
    });
    return out;
  }
  function savedAsked(){return readObj(askedKey())}
  function keepAnswers(add,meta){
    var a=savedAnswers(),m=savedAsked();
    Object.keys(add).forEach(function(k){if(add[k]){a[k]=String(add[k]).slice(0,2000);if(meta&&meta[k])m[k]=meta[k]}});
    var keys=Object.keys(a);while(keys.length>80)delete a[keys.shift()];
    Object.keys(m).forEach(function(k){if(!(k in a))delete m[k]});
    try{w.localStorage.setItem(answersKey(),JSON.stringify(a));w.localStorage.setItem(askedKey(),JSON.stringify(m))}catch(e){}
    paintKept();
  }
  function forgetAnswer(k){var a=savedAnswers(),m=savedAsked();delete a[k];delete m[k];try{w.localStorage.setItem(answersKey(),JSON.stringify(a));w.localStorage.setItem(askedKey(),JSON.stringify(m))}catch(e){}paintKept()}

  /* ---- one control per kind of question. Every kind an employer's form can ask on screen:
     text, textarea (long text, with a count), number (with its unit), date, month (month and year), select (a short list, or a
     searchable list when it is long), multi (tick every one that applies; searchable when long) and consent (a notice the person
     reads, then ticks). A file other than the resume is never asked here: the person finishes on the employer's page.
     Nothing is ever chosen for the person: every control starts empty. */
  var MANY=8,MONTHS=["January","February","March","April","May","June","July","August","September","October","November","December"];
  function kaStyle(){
    if(d.getElementById("kaStyle"))return;
    var st=d.createElement("style");st.id="kaStyle";
    st.textContent=".kaF{display:flex;flex-direction:column;gap:6px;min-width:0}.kaF>.kaL{font-weight:600}"+
      ".kaF input,.kaF select,.kaF textarea{width:100%;min-height:44px;padding:9px 11px;border-radius:10px;border:1px solid var(--line);background:var(--surface);color:var(--ink);font:inherit;box-sizing:border-box}"+
      ".kaF textarea{resize:vertical;min-height:110px}.kaF .kaRow{display:flex;gap:8px;align-items:center}.kaF .kaRow>*{flex:1;min-width:0}"+
      ".kaF .kaUnit{flex:0 0 auto;color:var(--muted);font-weight:600}.kaF small{color:var(--muted)}"+
      ".kaF .kaList{max-height:220px;overflow:auto;border:1px solid var(--line);border-radius:10px;padding:4px;margin:0;list-style:none}"+
      ".kaF .kaList [role=option]{padding:10px 11px;border-radius:8px;cursor:pointer;min-height:24px}"+
      ".kaF .kaList [role=option][aria-selected=true]{background:var(--accent);color:var(--accent-ink)}"+
      ".kaF .kaList [role=option].on{outline:2px solid var(--accent);outline-offset:-2px}"+
      ".kaF fieldset{border:1px solid var(--line);border-radius:10px;margin:0;padding:6px 10px;max-height:240px;overflow:auto}"+
      ".kaF fieldset label,.kaF .kaTick{display:flex;gap:10px;align-items:center;min-height:44px;cursor:pointer}"+
      ".kaF fieldset input,.kaF .kaTick input{width:22px;height:22px;min-height:0;flex:0 0 auto;margin:0}"+
      ".kaF .kaRead{max-height:150px;overflow:auto;border:1px solid var(--line);border-radius:10px;padding:10px 12px;white-space:pre-wrap;background:var(--bg)}"+
      ".kaF .kaRead:focus-visible,.kaF .kaList:focus-visible{outline:2px solid var(--accent)}"+
      ".kaF .kaTick.off{opacity:.55;cursor:not-allowed}";
    d.head.appendChild(st);
  }
  /* how a question is asked: the server's kind, with a consent and a long list made explicit */
  function askKind(q){var k=q.kind||"text";if(q.consent&&q.agree)return "consent";if((k==="select")&&q.opts&&q.opts.length>MANY)return "search";if(k==="select"&&!(q.opts&&q.opts.length))return "text";return k}
  function fieldHtml(q,id,val){
    var k=askKind(q),v=val==null?"":String(val),dk=' data-kind="'+k+'"';
    var h='<div class="kaF" id="'+id+'W"'+dk+'>';
    var lab='<label class="kaL" for="'+id+'">'+esc(q.q)+'</label>';
    if(k==="file")return h+'<span class="kaL">'+esc(q.q)+'</span><small id="'+id+'" style="color:var(--no)">Upload your resume in Profile setup, under Background and links, then swipe right again.</small></div>';
    if(k==="consent"){
      h+='<span class="kaL" id="'+id+'L">Please read this from the employer</span>'+
        '<div class="kaRead" id="'+id+'R" tabindex="0" role="region" aria-labelledby="'+id+'L">'+esc(q.q)+'</div>'+
        (q.link?'<small><a href="'+esc(q.link)+'" target="_blank" rel="noopener noreferrer">Open the employer\'s full notice</a></small>':'')+
        '<label class="kaTick" for="'+id+'"><input type="checkbox" id="'+id+'"'+(v?' checked':'')+'> <span>I have read it. '+esc(q.agree)+'</span></label>'+
        '<small id="'+id+'H" aria-live="polite"></small>';
    }else if(k==="textarea"){
      h+=lab+'<textarea id="'+id+'" maxlength="2000" rows="5" aria-describedby="'+id+'C">'+esc(v)+'</textarea><small id="'+id+'C">'+v.length+' of 2000 characters</small>';
    }else if(k==="number"){
      h+=lab+'<div class="kaRow"><input id="'+id+'" type="text" inputmode="decimal" autocomplete="off" maxlength="20" value="'+esc(v)+'"'+(q.unit?' aria-describedby="'+id+'U"':'')+'>'+
        (q.unit?'<span class="kaUnit" id="'+id+'U">'+esc(q.unit==="USD"?"US dollars":q.unit)+'</span>':'')+'</div>';
    }else if(k==="date"){
      h+=lab+'<input id="'+id+'" type="date" value="'+esc(/^\d{4}-\d{2}-\d{2}$/.test(v)?v:"")+'">';
    }else if(k==="month"){
      var mm=/^(\d{4})-(\d{2})$/.exec(v)||[],y0=new Date().getFullYear(),ys=[];for(var y=y0+8;y>=y0-60;y--)ys.push(y);
      h+='<span class="kaL" id="'+id+'L">'+esc(q.q)+'</span><div class="kaRow" role="group" aria-labelledby="'+id+'L">'+
        '<select id="'+id+'" aria-label="Month"><option value="">Month</option>'+MONTHS.map(function(n,i){var x=(i<9?"0":"")+(i+1);return '<option value="'+x+'"'+(mm[2]===x?' selected':'')+'>'+n+'</option>'}).join("")+'</select>'+
        '<select id="'+id+'Y" aria-label="Year"><option value="">Year</option>'+ys.map(function(n){return '<option'+(mm[1]===String(n)?' selected':'')+'>'+n+'</option>'}).join("")+'</select></div>';
    }else if(k==="search"){
      h+=lab+'<input id="'+id+'" type="search" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="'+id+'B" autocomplete="off" placeholder="Type to search '+q.opts.length+' choices" value="'+esc(v)+'">'+
        '<ul class="kaList" id="'+id+'B" role="listbox" aria-label="'+esc(q.q)+'">'+q.opts.map(function(o,i){return '<li role="option" id="'+id+'o'+i+'" aria-selected="'+(o===v)+'">'+esc(o)+'</li>'}).join("")+'</ul>'+
        '<small id="'+id+'S" aria-live="polite">'+(v?'Chosen: '+esc(v):'Nothing chosen yet')+'</small>';
    }else if(k==="multi"){
      var on=v?v.split("\n"):[];
      h+='<span class="kaL" id="'+id+'L">'+esc(q.q)+'</span><small>Tick every one that applies.</small>'+
        (q.opts.length>MANY?'<input type="search" id="'+id+'F" aria-label="Filter the choices" placeholder="Type to filter '+q.opts.length+' choices" autocomplete="off">':'')+
        '<fieldset id="'+id+'" aria-labelledby="'+id+'L">'+q.opts.map(function(o,i){return '<label><input type="checkbox" value="'+esc(o)+'"'+(on.indexOf(o)>-1?' checked':'')+'> <span>'+esc(o)+'</span></label>'}).join("")+'</fieldset>';
    }else if(k==="select"){
      h+=lab+'<select id="'+id+'"><option value="">Choose</option>'+q.opts.map(function(x){return '<option'+(x===v?' selected':'')+'>'+esc(x)+'</option>'}).join("")+'</select>';
    }else{
      h+=lab+'<input id="'+id+'" maxlength="300" autocomplete="off" value="'+esc(v)+'">';
    }
    return h+'</div>';
  }
  /* the behaviour each control needs once it is on the page (the count, the search list, the notice read to its end) */
  function wireField(box,q){
    var k=box.getAttribute("data-kind"),id=box.id.slice(0,-1),el=d.getElementById(id);
    if(el&&q&&q.key!=null)el.setAttribute("data-k",q.key);         /* the answer's key, on the control itself */
    if(k==="textarea"){var c=d.getElementById(id+"C");el.addEventListener("input",function(){c.textContent=el.value.length+" of 2000 characters"})}
    if(k==="consent"){
      var r=d.getElementById(id+"R"),tick=el.closest(".kaTick"),hint=d.getElementById(id+"H");
      function read(){return r.scrollHeight-r.scrollTop-r.clientHeight<4}
      function upd(){var ok=el.checked||read();el.disabled=!ok;tick.classList.toggle("off",!ok);hint.textContent=ok?"":"Scroll to the end of the notice to tick the box."}
      r.addEventListener("scroll",upd);upd();w.setTimeout(upd,60);
    }
    if(k==="search"){
      var list=d.getElementById(id+"B"),say=d.getElementById(id+"S"),act=-1;
      var items=[].slice.call(list.querySelectorAll("[role=option]"));
      function shown(){return items.filter(function(o){return !o.hidden})}
      function mark(i){var s=shown();items.forEach(function(o){o.classList.remove("on")});act=Math.max(-1,Math.min(i,s.length-1));
        if(act>-1){s[act].classList.add("on");el.setAttribute("aria-activedescendant",s[act].id);if(s[act].scrollIntoView)s[act].scrollIntoView({block:"nearest"})}else el.removeAttribute("aria-activedescendant")}
      function pick(o){items.forEach(function(x){x.setAttribute("aria-selected","false")});o.setAttribute("aria-selected","true");el.value=o.textContent;box.setAttribute("data-v",o.textContent);say.textContent="Chosen: "+o.textContent;items.forEach(function(x){x.hidden=false});if(o.scrollIntoView)o.scrollIntoView({block:"nearest"})}
      var pre=items.filter(function(o){return o.getAttribute("aria-selected")==="true"})[0];if(pre)box.setAttribute("data-v",pre.textContent);
      el.addEventListener("input",function(){var t=el.value.trim().toLowerCase();box.removeAttribute("data-v");items.forEach(function(o){o.setAttribute("aria-selected","false");o.hidden=!!t&&o.textContent.toLowerCase().indexOf(t)<0});
        var n=shown().length;say.textContent=n?n+" match"+(n===1?"":"es")+". Use the arrow keys and Enter, or tap one.":"No match. Try fewer letters.";mark(n===1?0:-1)});
      el.addEventListener("keydown",function(e){
        if(e.key==="ArrowDown"){e.preventDefault();mark(act+1)}else if(e.key==="ArrowUp"){e.preventDefault();mark(act-1)}
        else if(e.key==="Enter"){var s=shown();if(act>-1&&s[act]){e.preventDefault();pick(s[act])}else if(s.length===1){e.preventDefault();pick(s[0])}}
      });
      list.addEventListener("click",function(e){var o=e.target.closest("[role=option]");if(o){pick(o);el.focus()}});
    }
    if(k==="multi"){
      var f=d.getElementById(id+"F");
      if(f)f.addEventListener("input",function(){var t=f.value.trim().toLowerCase();el.querySelectorAll("label").forEach(function(l){l.hidden=!!t&&l.textContent.toLowerCase().indexOf(t)<0&&!l.querySelector("input").checked})});
    }
  }
  /* the answer as UAply stores it: plain text; a number as digits; a date as 2027-06-30 and a month as 2027-06; several choices one per
     line; a consent as the employer's own "I agree" option. "" when unanswered; {bad:"why"} when what was typed cannot be sent */
  function fieldVal(box,q){
    var k=box.getAttribute("data-kind"),id=box.id.slice(0,-1),el=d.getElementById(id);
    if(!el||k==="file")return "";
    if(k==="consent")return el.checked?q.agree:"";
    if(k==="month"){var m=el.value,y=d.getElementById(id+"Y").value;if(!m&&!y)return "";if(!m||!y)return {bad:"Choose both the month and the year."};return y+"-"+m}
    if(k==="search")return box.getAttribute("data-v")||(el.value.trim()?{bad:"Choose one of the choices in the list."}:"");
    if(k==="multi")return [].slice.call(el.querySelectorAll("input:checked")).map(function(c){return c.value}).join("\n");
    var v=(el.value||"").trim();
    if(k==="number"&&v){var n=v.replace(/(\d),(?=\d{3}\b)/g,"$1").replace(/[\s$]/g,"");if(!/^-?\d+(\.\d+)?$/.test(n))return {bad:"Enter a number"+(q.unit?" (in "+(q.unit==="USD"?"US dollars":q.unit)+")":"")+"."};return n}
    if(k==="date"&&v&&!/^\d{4}-\d{2}-\d{2}$/.test(v))return {bad:"Choose a whole date."};
    return v;
  }
  function metaOf(q,co){var m={q:String(q.q||"").slice(0,600),kind:q.kind||"text",co:co||"",at:Date.now()};["opts","unit","consent","agree","link"].forEach(function(k){if(q[k]!=null)m[k]=q[k]});return m}
  /* shown to the person: a stored answer in words ("June 2027", "Python, SQL") */
  function shownVal(m,v){
    v=String(v||"");m=m||{};
    if(m.consent)return "Agreed ("+v+")";
    var mo=/^(\d{4})-(\d{2})$/.exec(v);if(mo&&+mo[2]>=1&&+mo[2]<=12)return MONTHS[+mo[2]-1]+" "+mo[1];
    var dt=/^(\d{4})-(\d{2})-(\d{2})$/.exec(v);if(dt)return MONTHS[+dt[2]-1]+" "+(+dt[3])+", "+dt[1];
    if(v.indexOf("\n")>-1)return v.split("\n").join(", ");
    if(m.unit&&/^-?\d+(\.\d+)?$/.test(v))return m.unit==="USD"?"$"+v:v+" "+m.unit;
    return v;
  }
  w.__uaplyAskField={html:fieldHtml,wire:wireField,value:fieldVal};

  /* a phone or tablet (no mouse to hover with, a finger to point with) */
  function touchFirst(){try{return !!(w.matchMedia&&w.matchMedia("(hover: none) and (pointer: coarse)").matches)}catch(e){return false}}
  /* the questions on an employer's form that the profile could not answer: asked once, then the application goes */
  /* how (assisted apply's bridge, shared/uaply-nav.js): {lead, yes} replace the words about sending, and a question with optional:true
     may be left blank */
  function askSheet(job,qs,filled,total,go,cancel,how){
    var old=d.getElementById("kitAsk");if(old)old.remove();
    kaStyle();
    var o=d.createElement("div");o.id="kitAsk";
    o.style.cssText="position:fixed;inset:0;z-index:55;display:grid;place-items:center;padding:16px;background:rgba(0,0,0,.45);overflow:auto;overscroll-behavior:contain";
    var hasFile=qs.some(function(q){return q.kind==="file"});
    var h='<form role="dialog" aria-modal="true" aria-labelledby="kaH" novalidate style="background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:18px;padding:20px 20px 0;max-width:520px;width:100%;max-height:100%;overflow:auto;overscroll-behavior:contain;box-sizing:border-box;box-shadow:var(--shadow);display:flex;flex-direction:column;gap:14px;font-size:14px;min-width:0">'+
      '<h2 id="kaH" tabindex="-1" style="margin:0;font:800 20px var(--display);outline:none">'+(qs.length===1?'One question':qs.length+' questions')+' from '+esc(job.co)+'</h2>'+
      '<p style="margin:0;color:var(--muted)">'+(how&&how.lead?esc(how.lead):'UAply filled in '+filled+' of '+total+' answers on '+esc(job.co)+'\'s application. '+(hasFile?'It also needs a resume file. Answer what you can (it is saved), then upload your resume in Profile setup, under Background and links, and swipe right again.':'Answer '+(qs.length===1?'this':'these')+' and UAply sends it. Your answers are saved, so the next employer that asks the same thing gets them automatically. You can change them in Profile setup, under Eligibility and extras.'))+'</p>';
    qs.forEach(function(q,i){h+=fieldHtml(q.optional?Object.assign({},q,{q:q.q+" (optional)"}):q,"kaQ"+i,"")});
    h+='<p id="kaMsg" role="alert" style="margin:0;font-size:13px;color:var(--no);min-height:1.2em"></p>'+
      '<div id="kaBtns" style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;position:sticky;bottom:0;margin:0 -20px;padding:12px 20px 20px;background:var(--surface);border-top:1px solid var(--line)"><button type="button" class="btn ghost" id="kaNo">Not now</button><button type="submit" class="btn" id="kaYes">'+(hasFile?'Open Profile':how&&how.yes?esc(how.yes):'Send application')+'</button></div></form>';
    o.innerHTML=h;d.body.appendChild(o);
    var boxes=[].slice.call(o.querySelectorAll(".kaF"));
    boxes.forEach(function(b,i){wireField(b,qs[i])});
    /* a touch screen: the box opens without a field focused, so the phone's keyboard does not cover it before the person reads it (the
       heading takes the focus, for screen readers); a keyboard and mouse: the first field, ready to type */
    if(touchFirst())d.getElementById("kaH").focus({preventScroll:true});
    else(o.querySelector(".kaF input:not([disabled]),.kaF select,.kaF textarea,.kaF .kaRead")||d.getElementById("kaYes")).focus();
    /* the phone's keyboard: the box is fitted to the part of the screen still visible (the top page's visual viewport, as the app runs in
       a frame), so Send application, pinned to the bottom of the box, stays above the keyboard (apply journey, October 22) */
    var tw=null;try{tw=w.top&&w.top.visualViewport?w.top:null}catch(e){tw=null}
    var vv=tw?tw.visualViewport:w.visualViewport;
    function fit(){
      if(!o.isConnected){if(vv){vv.removeEventListener("resize",fit);vv.removeEventListener("scroll",fit)}return}
      if(!vv)return;
      var fr=null;try{fr=w.frameElement}catch(e){fr=null}
      var top0=fr&&tw?fr.getBoundingClientRect().top:0,vis=Math.max(120,Math.min(w.innerHeight,vv.height));
      var t=Math.max(0,(vv.offsetTop||0)-top0);
      o.style.inset="auto 0 auto 0";o.style.top=t+"px";o.style.height=vis+"px";
    }
    if(vv){vv.addEventListener("resize",fit);vv.addEventListener("scroll",fit);fit()}
    o.querySelector("form").onsubmit=function(e){
      e.preventDefault();
      var add={},meta={},blank=null,why="";
      boxes.forEach(function(b,i){
        var q=qs[i];if(q.kind==="file")return;
        var v=fieldVal(b,q);
        if(v&&typeof v==="object"){if(!blank){blank=b;why=v.bad}v=""}
        else if(!v&&!blank&&!q.optional)blank=b;
        add[q.key]=v;meta[q.key]=metaOf(q,job.co);
      });
      if(hasFile){keepAnswers(add,meta);o.remove();cancel();openProfile("back");return}   /* keep whatever was answered: only the resume is left next time */
      if(blank){
        var lab=blank.querySelector(".kaL");
        d.getElementById("kaMsg").textContent=(why?why+" ":"Answer every question to send the application. ")+(lab?"("+lab.textContent.slice(0,80)+")":"");
        var f=blank.querySelector("input:not([disabled]),select,textarea,.kaRead");if(f)f.focus();return;
      }
      keepAnswers(add,meta);o.remove();go();
    };
    d.getElementById("kaNo").onclick=function(){o.remove();cancel()};
    o.addEventListener("keydown",function(e){if(e.key==="Escape"){o.remove();cancel()}});
  }
  w.__uaplyAskSheet=askSheet;   /* assisted apply asks the questions the employer's form has and the profile cannot answer, before the form opens */

  /* Profile setup, Eligibility and extras: "Answers you gave employers". Each one can be changed with the control it was asked with, or
     removed (then the next employer that asks it asks again). They stay on this device and travel only with the applications sent. */
  var kept=null,keptEdit=null;
  function paintKept(){
    if(!kept)return;
    kaStyle();
    var a=savedAnswers(),m=savedAsked(),keys=Object.keys(a);
    var h='<h3 style="margin:0;font-size:15px">Answers you gave employers</h3>'+
      '<small>When an employer\'s form asks something your profile does not answer, UAply asks you once and keeps the answer here. The next employer that asks the same question gets it automatically. These stay on this device and go only with the applications you send.</small>';
    if(!keys.length)h+='<p class="note" style="margin:0" id="akNone">None yet.</p>';
    else h+='<ul id="akList" style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px">'+keys.map(function(k,i){
      var q=m[k]||{q:k.replace(/\{co\}/g,"(the company)"),kind:"text"},id="akQ"+i;
      if(keptEdit===k)return '<li data-ak="'+esc(k)+'" style="border:1px solid var(--line);border-radius:12px;padding:12px;display:flex;flex-direction:column;gap:10px">'+
        fieldHtml(dataQ(q,k),id,a[k])+'<p class="note" role="alert" id="akMsg" style="margin:0;color:var(--no)"></p><div style="display:flex;gap:8px;flex-wrap:wrap"><button type="button" class="btn" data-act="aksave">Save</button><button type="button" class="btn ghost" data-act="akcancel">Cancel</button></div></li>';
      return '<li data-ak="'+esc(k)+'" style="border:1px solid var(--line);border-radius:12px;padding:12px;display:flex;flex-direction:column;gap:6px;min-width:0">'+
        '<span style="font-weight:600;overflow-wrap:anywhere">'+esc(q.q.length>220?q.q.slice(0,217)+"...":q.q)+'</span>'+
        '<span style="overflow-wrap:anywhere;white-space:pre-wrap" class="akA">'+esc(shownVal(q,a[k]))+'</span>'+
        (q.co?'<small>First asked by '+esc(q.co)+'</small>':'')+
        '<div style="display:flex;gap:8px;flex-wrap:wrap"><button type="button" class="btn ghost" data-act="akedit" aria-label="Change your answer to: '+esc(q.q.slice(0,80))+'">Change</button><button type="button" class="btn ghost" data-act="akdel" aria-label="Remove your answer to: '+esc(q.q.slice(0,80))+'">Remove</button></div></li>';
    }).join("")+'</ul>';
    kept.innerHTML=h;
    var ed=keptEdit&&kept.querySelector('[data-ak] .kaF');
    if(ed){wireField(ed,dataQ(m[keptEdit]||{kind:"text"},keptEdit));var f=ed.querySelector("input:not([disabled]),select,textarea,.kaRead");if(f)f.focus()}
  }
  function dataQ(q,k){var x={};Object.keys(q).forEach(function(n){x[n]=q[n]});x.key=k;x.q=x.q||k;if(x.kind==="file"||x.kind==="other")x.kind="text";return x}
  function liKey(el){var li=el.closest("[data-ak]");return li?li.getAttribute("data-ak"):null}
  var grid=d.querySelector("#form .grid");
  if(grid&&!d.getElementById("aKept")){
    kept=d.createElement("div");kept.className="field full";kept.id="aKept";
    kept.style.cssText="display:flex;flex-direction:column;gap:8px;min-width:0";
    var eeo=d.getElementById("aEeo");if(eeo&&eeo.parentElement===grid)grid.insertBefore(kept,eeo);else grid.appendChild(kept);
    kept.addEventListener("click",function(e){
      var b=e.target.closest("[data-act]");if(!b)return;
      var act=b.getAttribute("data-act"),k=liKey(b);if(k==null)return;
      if(act==="akedit"){keptEdit=k;paintKept();return}
      if(act==="akcancel"){keptEdit=null;paintKept();var c=kept.querySelector('[data-ak="'+k.replace(/["\\]/g,"\\$&")+'"] [data-act=akedit]');if(c)c.focus();return}
      if(act==="akdel"){if(keptEdit===k)keptEdit=null;forgetAnswer(k);var n=kept.querySelector("[data-act=akedit]")||kept.querySelector("h3");if(n&&n.focus)n.focus();return}
      if(act==="aksave"){
        var m=savedAsked(),q=dataQ(m[k]||{kind:"text"},k),box=kept.querySelector('[data-ak] .kaF'),v=fieldVal(box,q),msg=d.getElementById("akMsg");
        if(v&&typeof v==="object"){msg.textContent=v.bad;return}
        if(!v){msg.textContent="Type an answer, or use Remove to forget this one.";return}
        var add={};add[k]=v;var mm={};if(m[k])mm[k]=m[k];keptEdit=null;keepAnswers(add,mm);
        var s=kept.querySelector('[data-ak="'+k.replace(/["\\]/g,"\\$&")+'"] [data-act=akedit]');if(s)s.focus();
      }
    });
    /* editing an answer here is saved by its own Save button, not by Profile setup's "Save and continue" */
    ["input","change"].forEach(function(t){kept.addEventListener(t,function(e){e.stopPropagation()})});
    w.addEventListener("storage",function(e){if(e.key===answersKey()&&!keptEdit)paintKept()});
    paintKept();
  }
  /* applications that could not reach the server: sent again when the connection is back, and on the next visit. The "online" event only
     comes after the device itself was offline, so when the device is online but UAply's server did not answer, it tries again every 30 seconds. */
  var queue=[],queueT=0;
  function flushQueue(){w.clearTimeout(queueT);queueT=0;var q=queue;queue=[];q.forEach(function(f){f()})}
  function waitToSend(f){queue.push(f);if(!queueT)queueT=w.setTimeout(flushQueue,30000)}
  w.addEventListener("online",flushQueue);
  function openAccount(){var b=d.getElementById("nb-prof");if(b){b.click();var it=d.querySelector('.nwrap[data-k=prof] .nitem[data-v=account]');if(it)it.click()}}
  /* Undo or Withdraw on an application that already went out: it stays with the employer, so say so instead of letting it look taken back */
  w.__uaplyUndone=function(was,job){
    var st=was&&was.s==="applied"&&was.sent&&was.sent.status;if(!job||!st)return;
    if(st==="sent")toast("Removed from your list. Your application to "+job.co+" was already sent, so "+job.co+" still has it.","","",9000);
    else if(st==="delivered_test")toast("Removed from your list. The test application to "+job.co+" stays in the test inbox.","","",9000);
  };
  function retryPending(){
    var A=w.__uaply;if(!A||!A.S||!A.S.decisions)return;
    A.JOBS.forEach(function(job){
      var dec=A.S.decisions[job.id];
      if(dec&&dec.s==="applied"&&dec.sent&&dec.sent.status==="pending")quietApply(job,{pct:dec.pct||0},A.S.profile,function(){},A.S,A.save,true);
    });
  }
  w.__uaplyRetryPending=retryPending;
  w.__uaplyAnswersFor=answersFor;   /* what a swipe to that employer would send (tools/ui-tracker-keep.js checks it) */
  /* "Try again" / "Answer now" in the Applied list: the same as swiping right on that job again */
  w.__uaplyResend=function(id){
    var A=w.__uaply;if(!A||!A.S||!A.S.decisions[id])return;
    var job=A.JOBS.filter(function(j){return j.id===id})[0];if(!job)return;
    quietApply(job,{pct:A.S.decisions[id].pct||0},A.S.profile,function(){},A.S,A.save,false);
  };

  function quietApply(job,m,p,undo,S,save,retry){
    var live=w.__uaplyMode==="live",auto=w.__uaplyAuto!==false;
    var target=(live&&w.__uaplyRedirect)||job.contact||(job.instant?"hiring system":"");
    /* take back this one swipe (never just "the last one": the person may have swiped on while this was on its way) */
    function revert(){
      if(retry)return;
      var dec=S&&S.decisions&&S.decisions[job.id];if(!dec)return;
      delete S.decisions[job.id];var i=S.history?S.history.lastIndexOf(job.id):-1;if(i>-1)S.history.splice(i,1);
      if(save)save();try{w.__uaply.renderAll()}catch(e){}
    }
    /* Undo on the saved message takes back this job only (the person may have swiped on since); nothing was sent for a hand-off */
    function undoThis(){revert()}
    function savedToast(){toast("Saved "+job.co+" to Applied · "+m.pct+"% match","Undo",undoThis,9000)}
    function mark(status,to){var dec=S&&S.decisions&&S.decisions[job.id];if(dec){dec.sent={at:Date.now(),to:to||"",status:status};if(save)save();if(w.__uaplyTrack)w.__uaplyTrack()}}   /* the Applied list, if it is open, shows the new state at once */
    var rdy=w.__uaplyReadiness?w.__uaplyReadiness():null;
    if(rdy&&!rdy.min&&!retry){revert();if(w.__uaplyFinishProfile)w.__uaplyFinishProfile(job);return}
    if(!(p.name&&EMAIL.test(p.email||"")&&(!live||p.custom))){
      revert();toast("Add your name and email in Profile setup, under About you, so employers can reply. "+job.co+" is back in your deck.","Open Profile",function(){openProfile("about")},9000);return;
    }
    if(live&&!auto){sheet(job,m,p,undo,S,save);return}           /* auto_send is off in the config: show the review screen */
    /* what happened to the applicant's own email receipt (signed-in accounts only) */
    function receiptNote(j){
      var rc=j.receipt,au=w.__uaplyAuth?w.__uaplyAuth():null;
      if(rc)return " "+({digest:"The steps to finish it come by email, once a day with any others.",sent:"Confirmation emailed to "+rc.to+".",delivered_test:testInboxNote(),not_configured:(isRelease?"":"No confirmation email: email sending is not set up yet."),failed:"The confirmation email could not be sent.",held:"Your confirmation email is queued and will arrive later (UAply's email is busy).",bounced:"No confirmation email: emails to "+rc.to+" bounce back.",unverified:"Verify your email (Profile, Account) to get confirmation emails."}[rc.status]||"");
      return au&&au.up&&!au.user?" Sign in to get a confirmation email.":"";
    }
    function deliver(){
      /* the application is the profile itself: no cover note or message is written for the recruiter, unless the person
         turned on the opt-in "Message the hiring manager" preference (Plus and Pro; off by default) */
      var msgOn=!!(w.__uaplyAutoMsg&&w.__uaplyAutoMsg()&&w.__uaplyMessage);
      if(!(S&&S.decisions&&S.decisions[job.id]))return;   /* undone or withdrawn in the meantime (also while it waited for a connection): send nothing */
      post("/api/apply",{consent:true,confirm_real:live,match:m.pct,note:msgOn?w.__uaplyMessage(job,m,p):"",
        job:{id:job.id,co:job.co,role:job.role,url:job.url||"https://example.com/example-listing",source:job.source,loc:job.loc,contact:job.contact||"",mode:job.mode,type:job.type||"job",sal:job.sal,blurb:job.blurb},
        profile:{name:p.name,email:p.email,title:p.title,years:p.years,skills:p.skills,loc:p.loc,edu:p.edu,ext:(w.__uaplyApplyExt?w.__uaplyApplyExt():(p.ext||{}))},
        resume:(w.__uaplyResume?w.__uaplyResume():null),
        answers:answersFor(job.co)
      }).then(function(r){
        var j=r.j||{};
        if(!r.ok){
          /* nothing was sent (a limit, a missing detail, an unverified email): the job goes back to the deck rather than sitting in Applied.
             A waiting application sent again later stays in Applied, marked not sent, with Try again. */
          if(retry){if(j.code!=="server")mark("failed");return}          /* a server hiccup keeps it waiting for the next try */
          revert();
          var act=j.code==="limit"?["See plans",function(){var b=d.getElementById("nb-prof");if(b){b.click();var it=d.querySelector('.nwrap[data-k=prof] .nitem[data-v=plan]');if(it)it.click()}}]
                  :j.code==="slow_down"||j.code==="server"||j.code==="preview"?["",null]:(j.code==="signin"||j.code==="verify")?["Open Account",openAccount]:["Open Profile",openProfile];
          toast((j.error||"Could not send your application.")+" "+job.co+" is back in your deck.",act[0],act[1],9000);return;
        }
        if(j.status==="needs_answers"){
          var qs=Array.isArray(j.questions)?j.questions:[];
          if(retry||!qs.length){mark("needs_answers");return}      /* asked when the person taps Answer now in Applied */
          /* marked before the box opens: if the person leaves it open, goes to Applied or closes the app, the job says "Not sent yet",
             never a plain "Applied" for an application nothing was sent for. Sending replaces the mark; Not now leaves it waiting with Answer now */
          mark("needs_answers");
          askSheet(job,qs,j.filled||0,j.total||0,deliver,function(){
            if(!(S&&S.decisions&&S.decisions[job.id]))return;
            mark("needs_answers");toast("Not sent yet: "+job.co+" waits in Job Tracker. Tap Answer now there when you're ready.","","",9000);
          });
          return;
        }
        if(j.status==="duplicate"){             /* sent before (then undone, or from another device): show what happened that time */
          if(j.was)mark(j.was,j.to);
          if(j.was==="handoff"){if(!retry)savedToast();return}      /* a hand-off swiped again: quiet, the Applied row has the links */
        }
        else mark(j.status,j.to);
        var cp=receiptNote(j),pl=j.plan;
        var auto=pl&&pl.total?" UAply filled in "+pl.filled+" of "+pl.total+" answers.":"";
        if(j.status==="delivered_test")toast("Applied to "+job.co+" (test)."+auto+cp,"","",9000);
        else if(j.status==="sent")toast("Applied to "+job.co+"."+auto+cp,"","",9000);
        else if(j.status==="duplicate")toast("Already applied to "+job.co+".");
        else if(j.status==="handoff"){if(!retry&&!deliver.waiting)savedToast()}        /* quiet: no "finish on their site" interruption; Applied shows the links */
        else if(j.status==="failed")toast(j.error||"The application could not be sent.","Try again",deliver,9000);
        else toast("Done.");
      }).catch(function(){
        /* offline or the server did not answer: kept as waiting, and sent once the connection is back (said once, not on every new try) */
        var first=!deliver.waiting;deliver.waiting=true;
        mark("pending");waitToSend(deliver);
        if(!retry&&first)toast(w.navigator.onLine===false?"You're offline. UAply will send your application to "+job.co+" when you're back online."
                                                        :"UAply could not reach its server. It will send your application to "+job.co+" as soon as it can.","","",9000);
      });
    }
    var grace=Math.max(0,w.__uaplyGrace||0);
    if(!live||!target||grace===0){deliver();return}              /* test mode, or nothing to email: nothing to wait for */
    var left=grace,cancelled=false,timer=null,t=null;            /* live: send by itself, with a short window for Undo */
    function tick(){
      if(cancelled)return;
      if(!(S&&S.decisions&&S.decisions[job.id])){    /* undone some other way (the Undo button, Z, Withdraw): stop and say nothing went */
        cancelled=true;clearInterval(timer);toast("Cancelled. Nothing was sent to "+job.co+".");return;
      }
      if(left<=0){clearInterval(timer);deliver();return}
      var msg="Applying to "+job.co+" in "+left+"…";
      if(t)t.set(msg);else t=toast(msg,"Undo",function(){cancelled=true;clearInterval(timer);revert();toast("Cancelled. Nothing was sent.")},0);
      left--;
    }
    timer=setInterval(tick,1000);tick();
  }


  /* ---------- ready or not, on each card, before the swipe (the owner's rule, October 21) ----------
     A job whose employer connected its hiring system: the posting's own form is read ahead (POST /api/apply/plan: the same reading a swipe
     right does, nothing recorded or sent), kept per posting until the profile or a saved answer changes, and the card says "Ready to apply"
     or "N answers needed". An employer who takes email, and every hand-off: "Ready" once the profile has READY_MIN. Below it, every card
     says "Finish your profile", and a swipe right opens "Finish your profile first" instead of applying (__uaplyReadyGate). */
  var RDY={},RDYQ={};
  function rdyApplies(job){return !!(job&&w.__uaplySubmitOn&&w.__uaplyMode&&!(w.__uaplyPreview&&w.__uaplyPreview())&&(job.live||w.__uaplyMode==="test"))}
  function rdyConnected(job){return !!(job.live&&job.instant&&!job.contact&&!job.webhook)}
  /* whether a swipe right reads this posting's own form first (and may ask its questions): an employer who connected its hiring system,
     or, where the server previews forms in test mode (the sandbox), any Greenhouse posting. The card then asks the server for the same
     plan the swipe uses, so it never says "Ready" for a form that will ask questions (apply journey, October 22: 15 such cards) */
  function rdyReadsForm(job){return rdyConnected(job)||!!(w.__uaplyFormPreview&&job.live&&!job.instant&&job.ats&&job.ats.kind==="greenhouse")}
  function rdyPayload(job){
    var p=(w.__uaply&&w.__uaply.S.profile)||{},res=w.__uaplyResume?w.__uaplyResume():null;
    return {plan_only:true,match:0,job:{id:job.id,co:job.co,role:job.role,url:job.url||"https://example.com/example-listing",source:job.source,loc:job.loc,contact:job.contact||"",mode:job.mode,type:job.type||"job",sal:job.sal,blurb:job.blurb},
      profile:{name:p.name,email:p.email,title:p.title,years:p.years,skills:p.skills,loc:p.loc,edu:p.edu,ext:(w.__uaplyApplyExt?w.__uaplyApplyExt():(p.ext||{}))},
      resume:res&&res.name?{name:res.name,present:true}:null,answers:answersFor(job.co)};
  }
  function rdySig(pl){var s=JSON.stringify([pl.profile,pl.resume,pl.answers,(w.__uaplyAuth&&w.__uaplyAuth()||{}).user||null]),h=0;for(var i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))|0;return String(h)}
  function rdyFromPlan(r){
    var j=r.j||{};
    if(r.ok&&j.status==="ready")return {k:"ok",t:"Ready to apply"};
    if(r.ok&&j.status==="needs_answers"){var n=(j.questions||[]).length;return {k:"need",t:n===1?"1 answer needed":n+" answers needed",n:n}}
    if(r.ok&&j.status==="handoff")return {k:"ext",t:"Finish on their site"};
    if(j.code==="signin")return {k:"need",t:"Sign in to apply"};
    if(j.code==="verify")return {k:"need",t:"Verify your email to apply"};
    return null;                                             /* already applied, or the form could not be read: no promise either way */
  }
  /* the card's state now (null: nothing to show yet); a connected employer's form is read once per posting and profile */
  function rdyState(job,then){
    var r=w.__uaplyReadiness?w.__uaplyReadiness():{min:true};
    if(!r.min)return {k:"need",t:"Finish your profile"};
    if(!rdyReadsForm(job))return {k:"ok",t:"Ready"};
    var pl=rdyPayload(job),sig=rdySig(pl),c=RDY[job.id];
    if(c&&c.sig===sig)return c.st;
    if(RDYQ[job.id]!==sig){
      RDYQ[job.id]=sig;
      post("/api/apply/plan",pl).then(function(res){RDY[job.id]={sig:sig,st:rdyFromPlan(res)};delete RDYQ[job.id];rdyPaint();if(then)then()},
        function(){delete RDYQ[job.id];if(then)then()});
    }
    return undefined;                                        /* asked; the card is painted again when the answer arrives */
  }
  function rdyPaint(){
    var deck=d.getElementById("deck"),A=w.__uaply;if(!deck||!A)return;
    [].slice.call(deck.querySelectorAll(".card")).forEach(function(card){
      var id=+card.getAttribute("data-id"),job=null;for(var i=0;i<A.JOBS.length;i++)if(A.JOBS[i].id===id){job=A.JOBS[i];break}
      var st=job&&rdyApplies(job)?rdyState(job):null,el=card.querySelector(".facts .rdy");
      if(!st){if(el&&st===null)el.remove();return}
      if(!el){var f=card.querySelector(".facts");if(!f)return;el=d.createElement("span");f.appendChild(el)}
      var cls="rdy "+st.k;if(el.className!==cls)el.className=cls;if(el.textContent!==st.t)el.textContent=st.t;
    });
  }
  w.__uaplyRdyPaint=rdyPaint;
  (function(){var deck=d.getElementById("deck");if(deck&&w.MutationObserver){var busyP=false;new w.MutationObserver(function(){if(busyP)return;busyP=true;w.setTimeout(function(){busyP=false;rdyPaint()},0)}).observe(deck,{childList:true,subtree:true})}})();
  /* for the browser tests: the state a card for this job shows once its plan is in */
  w.__uaplyReadyOf=function(id){
    var A=w.__uaply,job=null;for(var i=0;i<A.JOBS.length;i++)if(A.JOBS[i].id===id){job=A.JOBS[i];break}
    if(!job||!rdyApplies(job))return Promise.resolve(null);
    return new Promise(function(done){var st=rdyState(job,function(){var s2=rdyState(job);done(s2===undefined?null:s2)});if(st!==undefined)done(st)});
  };
  /* a swipe right below READY_MIN, wherever it comes from (a finger, Apply, the arrow key): nothing happens to the card, and the box says
     what is missing (called by prod's decide(), patched in kitPatch, before the card moves) */
  w.__uaplyReadyGate=function(job){
    if(!job||!rdyApplies(job))return false;
    var r=w.__uaplyReadiness?w.__uaplyReadiness():null;
    if(!r||r.min)return false;
    if(w.__uaplyFinishProfile)w.__uaplyFinishProfile(job);
    return true;
  };

  w.__uaplyOnApplied=sheet;   /* tells the live patch the apply assistant is on */
  w.__uaplyOnDecision=function(dir,job,m,p,undo,S,save){
    /* the swipe keeps a short copy of its row (Job Tracker shows it after the job leaves the feed); then the oldest passes beyond the cap go */
    try{if(job&&S&&S.decisions[job.id]){S.decisions[job.id].row=rowOf(job);trimDecisions(S);if(save)save()}}catch(e){}
    if(w.__uaplyPreview&&w.__uaplyPreview())return;          /* a preview with no server: the swipe is only saved here, and the toast says so */
    /* the job itself goes into the saved job list at once: its Job Tracker row needs it after the page is reloaded (a phone reloads a tab it
       put to sleep), and the server's list may no longer have it, or not yet while that list is still loading. It used to be saved only
       when the list loaded, so a job swiped after that was missing from Job Tracker after a reload (apply journey, October 22, job 14769135) */
    if(job&&job.live&&job.id>=100000){try{var all=readCache();if(!all.some(function(c){return c.id===job.id})){var keep=JSON.parse(JSON.stringify(job));keep.seen=Date.now();all.push(keep)}
      writeCache(all,(S&&S.decisions)||null)}catch(e){}}
    var ready=!!(w.__uaplySubmitOn&&w.__uaplyMode);
    if(ready){
      post("/api/decision",{session:session(),dir:dir==="applied"?"apply":"pass",jobId:job.id,co:job.co,role:job.role,pct:m.pct}).catch(function(){});
    }
    /* real listings always go through the apply flow; the made-up example listings only do so in test mode,
       where "sending" means the simulated inbox (and your own copy), never a real company */
    if(dir!=="applied"||(!job.live&&w.__uaplyMode!=="test"))return;
    if(ready&&!showSheet)ensureConsent(function(){quietApply(job,m,p,undo,S,save)},undo);
    else if(job.url)sheet(job,m,p,undo,S,save);
  };
  w.__uaplyQuiet=!showSheet;
  /* Data and privacy: when this browser agreed (null if never, or only to an earlier version), and Show it again, which forgets the
     saved agreement for this build and opens the box; `done(agreed)` is called with the answer */
  w.__uaplyConsentInfo=function(){try{var c=JSON.parse(w.localStorage.getItem(consentKey()));return c&&typeof c==="object"?{at:+c.at||0,current:c.v===CONSENT_V}:null}catch(e){return null}};
  w.__uaplyConsentAgain=function(done){try{w.localStorage.removeItem(consentKey())}catch(e){}var o=d.getElementById("kitConsent");if(o)o.remove();
    ensureConsent(function(){if(done)done(true)},function(){if(done)done(false)},true);
    /* shown again on request, so "You only see this once" is no longer true: that line goes */
    var box=d.getElementById("kitConsent");if(box)[].slice.call(box.querySelectorAll("p")).forEach(function(p){if(/^You only see this once/.test(p.textContent))p.remove()})};
  if(consentFirst&&!showSheet){
    /* not while someone is in Hiring mode: employers do not swipe. Hiring mode calls this again when they switch back */
    w.__uaplyAskConsent=function(){if(!hasConsent()&&!d.body.classList.contains("hire"))ensureConsent(function(){},function(){},true)};
    w.setTimeout(w.__uaplyAskConsent,700);
  }
}

function submitApply(w){
  w.__uaplySubmitOn=true;   /* from here on a swipe right applies by itself (see quietApply) */
  return w.fetch("/api/apply/config").then(function(r){return r.json()}).then(function(c){w.__uaplyMode=c.mode==="live"?"live":"test";w.__uaplyRedirect=c.redirect||"";w.__uaplyAuto=c.autoSend!==false;w.__uaplyTestInbox=c.testInbox||"";w.__uaplyGrace=typeof c.graceSeconds==="number"?c.graceSeconds:5;w.__uaplyFormPreview=c.formPreview===true;if(w.__uaplyRdyPaint)w.__uaplyRdyPaint()}).catch(function(){});
}

window.UAplyLive={patch:patch,apply:apply,kit:{patch:kitPatch,apply:kitApply},submit:{apply:submitApply}};
})();
