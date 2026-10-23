/* "share" experiment for the sandbox: "Share this job". Never loaded by prod; dev loads it only once it is promoted.
   Mohammed's version A (October 22): the one visible change on the swipe page is a small share icon (36 px, "Share this job") in the
   top-right corner of the job card. Nothing else on that page changes.
   - Tapping it shares a UAply link to that job: <this site>/?job=<id>&t=<title>&c=<company> (public job facts only, nothing about the
     person), through the same path as the Job Tracker's Share: the phone app's share sheet, then the browser's, then a copy to the
     clipboard with a visible "copied" note. The message reads "<Role> at <Company> on UAply"; a job whose application goes on the
     employer's own site also carries the employer's link, so the friend is never told UAply sends it. Example jobs (ids under 100000)
     are never shared with ?job=.
   - The friend who opens that link: ?job= is read from the address and taken off it (a reload or a forwarded address does not repeat
     it), and once /api/jobs has answered, that job goes to the front of the deck with a small "Shared with you" line above the card.
     No account is needed to look, pass or save; the agreement and sign-in appear only where they always do.
     From the first moment the line names the job ("Shared with you: <title> at <company>. Looking for it…"); if /api/jobs fails it says
     so with Try again, and the landing waits in the top page's sessionStorage until it is settled, so a reload brings it back.
     While boards are still loading and the job is not in the answers so far, after 3 answers or 20 s the closed screen shows as
     "Not found yet" (the job still comes to the front if a later answer brings it).
   - If the job is no longer in /api/jobs: "No longer listed on UAply" with the title and company from the link, in place of the card,
     then open jobs like it (same title words or the same company first, then the same kind of job), each with its age and where its
     application goes. The work-style chips filter them; Pass, Undo and Apply are hidden while there is no card. "Swipe through them",
     or "See other open jobs" when nothing is like it, always leads back to the deck.
   - The Job Tracker's "Not sent yet" rows get the same icon.
   patch() adds the icon to the card and the deck-order hook to the production page with once(); apply() does the rest. A missing anchor
   stops this experiment loudly, never silently. One hook in shared/uaply-nav.js (shareJob: w.__uaplyShareJob) makes the Job Tracker's
   Share buttons send the same link. */
(function(){
"use strict";
var Env=window.UAplyEnv;
if(!Env){if(window.console)console.error("[uaply] share: shared/uaply-share.js must load after uaply-envs.js");return}
function once(src,a,b){if(src.indexOf(a)<0)throw new Error("patch target not found: "+a.slice(0,40));return src.replace(a,function(){return b})}
function fail(m){if(window.console)console.error("[uaply] share: "+m);throw new Error(m)}

var GLYPH='<svg class="ushr-g" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12"/><path d="M7 8l5-5 5 5"/><path d="M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/></svg>';
var CLOCK='<svg class="ushr-g" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>';

var CSS=`
/* "Share this job" (shared/uaply-share.js). Every class starts with ushr so nothing in the app's own styles reaches it */
.ushr-g{width:1em;height:1em;fill:none;stroke:currentColor;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round;flex:none}
.card .chead{padding-right:52px}
.ushr-ic{position:absolute;top:12px;right:12px;z-index:1;width:36px;height:36px;border-radius:50%;display:grid;place-items:center;padding:0;border:1px solid var(--line);background:color-mix(in srgb,var(--surface) 80%,transparent);color:var(--ink);font-size:16px;cursor:pointer}
.ushr-ic::after{content:"";position:absolute;left:50%;top:50%;width:44px;height:44px;transform:translate(-50%,-50%)}
.ushr-ic:hover{border-color:var(--accent);color:var(--accent)}
.ushr-line{width:100%;max-width:620px;margin:0;display:flex;align-items:center;gap:6px;font-size:12.5px;color:var(--muted)}
.ushr-line b{color:var(--ink)}
.ushr-line .ushr-g{color:var(--accent);font-size:14px}
.ushr-line .ushr-retry{position:relative;font-size:inherit;line-height:inherit;min-height:0;min-width:0;padding:0;vertical-align:baseline;text-decoration:underline;text-underline-offset:2px}
.ushr-line .ushr-retry::after{content:"";position:absolute;inset:-14px -8px}
.ushr-empty .ushr-other{display:inline-flex;align-items:center;min-height:44px;font-size:14px;text-decoration:underline;text-underline-offset:3px}
.ushr-closed{width:100%;max-width:620px;flex:1;min-height:0;overflow-y:auto;display:flex;flex-direction:column;gap:12px;padding-bottom:12px}
/* a column flex scroller shrinks its children to fit unless told not to: every block keeps its full height and the list scrolls */
.ushr-closed>*{flex:none}
.ushr-tomb{background:var(--surface);border:1px dashed var(--line);border-radius:22px;padding:16px 18px}
.ushr-tomb h2{margin:10px 0 4px;font:800 20px/1.25 var(--display);color:var(--muted);overflow-wrap:anywhere}
.ushr-tomb h2:focus{outline:none}
.ushr-tomb p{margin:0}
.ushr-tomb .ushr-co{color:var(--muted)}
.ushr-tomb .ushr-why{margin-top:10px}
.ushr-st{display:inline-flex;gap:6px;align-items:center;font-weight:700;font-size:13px;color:var(--mid);background:var(--mid-bg);padding:4px 10px;border-radius:999px}
.ushr-sec h3{margin:6px 0 2px;font:800 18px/1.25 var(--display)}
.ushr-sec p{margin:0;font-size:13px;color:var(--muted)}
.ushr-sec .linkbtn{display:inline-flex;align-items:center;min-height:44px;font-size:14px;text-decoration:underline;text-underline-offset:3px}
.ushr-row{display:flex;gap:12px;width:100%;text-align:left;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px 14px;color:var(--ink);cursor:pointer;font:inherit;align-items:flex-start;min-height:46px}
.ushr-row:hover{border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}
.ushr-row .logo{width:40px;height:40px;font-size:18px;flex:none}
.ushr-row .ushr-bd{flex:1;min-width:0}
.ushr-row b{display:block;font:700 15.5px/1.3 var(--display);overflow-wrap:anywhere}
.ushr-row .ushr-m{display:block;font-size:13px;color:var(--muted)}
.ushr-row .ushr-m2{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center;margin-top:5px;font-size:13px}
.ushr-row .ushr-age{font-weight:600;padding:1px 8px;border-radius:999px;background:var(--yes-bg);color:var(--yes)}
.ushr-row .ushr-age.old{background:var(--bg);color:var(--muted)}
.ushr-row .ushr-pay{font-weight:700}
.ushr-row .ushr-rt{font-weight:600;color:var(--muted)}
.ushr-row .ushr-rt.u{color:var(--yes)}
.ushr-row .ushr-like{display:block;font-size:13px;margin-top:4px}
.ushr-row .ushr-like b{display:inline;font:700 13px var(--body);color:var(--accent)}
.ushr-empty{padding:14px;border:1px dashed var(--line);border-radius:14px;color:var(--muted);text-align:center;margin:0}
.ushr-rowic{display:inline-grid;place-items:center;vertical-align:middle;position:relative;width:30px;height:30px;margin-left:6px;border-radius:50%;border:1px solid var(--line);background:var(--surface);color:var(--ink);font-size:14px;padding:0;cursor:pointer}
.ushr-rowic::after{content:"";position:absolute;inset:-7px}
.ushr-rowic:hover{border-color:var(--accent);color:var(--accent)}
`;

/* the parent page's fetch carries the app's /api/jobs request (shared/uaply-live.js loadJobs); this notes each answer's "pending"
   (boards still loading) without reading the body twice, so the friend's page knows when the list is complete. A request that fails
   (no connection, a 5xx, a plain web host's 404 or HTML page) is noted too: live.js does not ask again after one, so the landing says so */
var answers={n:0,last:null,failed:false},onJobs=null,onFail=null;
function watchJobs(){
  if(typeof window.fetch!=="function"||window.__uaplyShareFetch)return;
  window.__uaplyShareFetch=true;
  var f=window.fetch;
  function failed(){answers.failed=true;setTimeout(function(){if(onFail)onFail()},0)}
  window.fetch=function(u){
    var p=f.apply(this,arguments);
    if(!/^(?:https?:\/\/[^/]+)?\/api\/jobs(?:\?|$)/.test(String(u&&u.url||u)))return p;
    return p.then(function(r){
      try{
        var ct=r&&r.headers&&r.headers.get?r.headers.get("content-type")||"":"";
        if(!r||!r.ok||/text\/html/i.test(ct))failed();
        else if(typeof r.json==="function"){var j=r.json;r.json=function(){return j.call(r).then(function(d){
          answers.n++;answers.last=d;answers.failed=false;setTimeout(function(){if(onJobs)onJobs(d)},0);return d},function(e){failed();throw e})}}
      }catch(e){}
      return r;
    },function(e){failed();throw e});
  };
}

function patch(s){
  watchJobs();
  answers.n=0;answers.last=null;answers.failed=false;onJobs=null;onFail=null;   /* a new frame build (the sandbox's controls): the old frame's watcher and count go */
  s=once(s,"</style>",CSS+"</style>");
  /* the icon: top-right of every card, reachable by keyboard on the top card only (the cards under it are hidden from screen readers) */
  s=once(s,"'<div class=\"chead\">'+logoHTML(j)+'<div><h2>'+esc(j.role)+'</h2><p>'+esc(j.co)+'</p></div></div>'",
    "'<div class=\"chead\">'+logoHTML(j)+'<div><h2>'+esc(j.role)+'</h2><p>'+esc(j.co)+'</p></div></div>'+"+
    "'<button type=\"button\" class=\"ushr-ic\" data-ushare=\"'+j.id+'\"'+(cls===\"top\"?'':' tabindex=\"-1\"')+' aria-label=\"Share this job\" title=\"Share this job\">"+GLYPH.replace(/"/g,'\\"')+"</button>'");
  /* the deck order: whatever the page and the other experiments decided, then the shared job (and, after "Swipe through them", the jobs
     like it) in front, until the person swipes it */
  return once(s,"function queue(){","function queue(){var q=queueShared();return window.__uaplySharePin?window.__uaplySharePin(q,JOB_BY_ID,S,F,evaluate):q}\n"+
    "window.__uaplyShareById=function(id){return JOB_BY_ID[+id]||null};\nfunction queueShared(){");   /* the page keeps its jobs inside its own function: this is how the icon finds one */
}

function apply(w){
  var d=w.document,A=w.__uaply;
  if(!A||!A.S)fail("needs the app's API (Bottom navigation)");
  var deck=d.getElementById("deck"),col=deck&&deck.parentNode,acts=col&&col.querySelector(".actions"),hint=col&&col.querySelector(".hint");
  if(!deck||!acts)fail("patch target not found: #deck or .actions");
  if(typeof w.__uaplyShareById!=="function")fail("patch target not found: the deck order (function queue)");
  var byId=w.__uaplyShareById;
  var esc=A.esc;

  /* ---------- the message ---------- */
  function cap(){var c=w.Capacitor||(w.parent&&w.parent!==w&&w.parent.Capacitor);return c&&c.isNativePlatform&&c.isNativePlatform()?c:null}
  function plug(n){var c=cap();return c&&c.Plugins&&c.Plugins[n]||null}
  function site(){
    try{var L=window.top.location;if(/^https?:$/.test(L.protocol)&&!(w.__uaplyPreview&&w.__uaplyPreview()))return L.origin+L.pathname}catch(e){}
    return "https://uaply.net/";
  }
  function real(j){return !!(j&&j.live&&+j.id>=100000)}
  function viaUAply(j){return !!(w.__uaplyRouteWord&&w.__uaplyRouteWord(j)==="Applies instantly")}
  function msg(j){
    var base=site(),role=String(j.role||""),co=String(j.co||"");
    if(!real(j))return {title:role+" at "+co,text:role+" at "+co+" on UAply (an example listing, not a real opening)",url:base};
    var url=base+"?job="+(+j.id)+"&t="+encodeURIComponent(role.slice(0,160))+"&c="+encodeURIComponent(co.slice(0,120));
    var text=role+" at "+co+" on UAply";
    /* the employer's own link where the application goes on their site: the friend is never told UAply sends it */
    if(!viaUAply(j)&&/^https:\/\//.test(j.url||""))text+="\n"+co+" takes applications on its own site: "+j.url;
    return {title:role+" at "+co,text:text,url:url};
  }
  function note(m){var t=d.createElement("div");t.className="toast";t.setAttribute("role","status");t.textContent=m;d.body.appendChild(t);setTimeout(function(){t.remove()},3500)}
  function copy(m){
    var all=m.text.split("\n")[0]+" "+m.url+(m.text.indexOf("\n")>-1?"\n"+m.text.slice(m.text.indexOf("\n")+1):"");
    var cb=(w.navigator.clipboard&&w.navigator.clipboard.writeText)?w.navigator.clipboard:(window.navigator.clipboard&&window.navigator.clipboard.writeText?window.navigator.clipboard:null);
    if(!cb){note("Copy this link to share: "+m.url);return Promise.resolve(false)}
    return cb.writeText(all).then(function(){note("Link copied. Paste it to share this job.");return true},function(){note("Copy this link to share: "+m.url);return false});
  }
  /* the phone app's share sheet, then the browser's (the top page's: the app's frame is not allowed to open one), then the clipboard */
  function share(j){
    var m=msg(j),SH=plug("Share"),nav=window.navigator;
    if(SH)return Promise.resolve(SH.share({title:m.title,text:m.text,url:m.url})).catch(function(){});
    if(nav.share)return nav.share({title:m.title,text:m.text,url:m.url}).catch(function(e){if(!e||e.name!=="AbortError")return copy(m)});
    return copy(m);
  }
  w.__uaplyShareMsg=msg;w.__uaplyShareJob=share;

  /* ---------- the icon on the card: a tap or Enter shares; it never starts a drag ---------- */
  d.addEventListener("pointerdown",function(e){if(e.target.closest&&e.target.closest("[data-ushare]"))e.stopPropagation()},true);
  d.addEventListener("click",function(e){
    var b=e.target.closest&&e.target.closest("[data-ushare]");if(!b)return;
    e.preventDefault();e.stopPropagation();
    var j=byId(b.getAttribute("data-ushare"));if(j)share(j);
  },true);

  /* ---------- the friend's landing ---------- */
  /* SH.state: "wait" (link read, the job in no answer yet: the line says it is looking), "maybe" (not in the answers so far while boards
     are still loading: the jobs like it show, and the job still moves to the front if a later answer brings it), "fail" (/api/jobs failed:
     the line says so, with Try again), then settled: "open" (in front), "seen" (already swiped), "closed" (the list is complete without it).
     Until it is settled the landing is kept in the top page's sessionStorage: ?job= is already off the address, so this is what lets Try
     again (a reload) or a rebuild of the frame pick it up again. SH.left: the friend chose to swipe on, so the closed screen stays away. */
  var KEEP="uaply.share.landing",KEEP_MS=30*60000;
  var SH={id:0,t:"",c:"",state:"",pins:[],closed:false,left:false,since:0,seen:""};
  function keep(){try{var st=w.top.sessionStorage;if(st)st.setItem(KEEP,JSON.stringify({id:SH.id,t:SH.t,c:SH.c,at:Date.now()}))}catch(e){}}
  function forget(){try{var st=w.top.sessionStorage;if(st)st.removeItem(KEEP)}catch(e){}}
  function clean(x,n){return String(x||"").replace(/[\u0000-\u001f\u007f]+/g," ").replace(/\s+/g," ").trim().slice(0,n)}
  /* real ids are 6 to 16 digits (a posting whose first id collides gets a longer one, always below 2**53); example jobs are under 100000 */
  function realId(id){id=String(id);return /^\d{6,16}$/.test(id)&&Number.isSafeInteger(+id)&&+id>=100000}
  w.__uaplySharePin=function(q,BY,S,F,evaluate){
    if(!SH.pins.length)return q;
    var front=[];
    SH.pins.forEach(function(id){
      /* the shared job itself is an explicit request to see it, so a saved work-style filter does not hide it (the service type and the
         minimum match never did); the jobs like it (after "Swipe through them") still follow the chips */
      var j=BY[id];if(!j||j.stub||!j.live||S.decisions[id]||(id!==SH.id&&F!=="all"&&j.mode!==F))return;
      for(var i=0;i<q.length;i++)if(q[i].j.id===id){front.push(q.splice(i,1)[0]);return}
      front.push({j:j,m:evaluate(j,S.profile)});
    });
    return front.length?front.concat(q):q;
  };
  (function read(){
    var q=null;try{q=new w.URLSearchParams(w.top.location.search)}catch(e){return}
    if(!q.has("job")){
      /* no link in the address: a landing this tab has not settled yet (Try again, a reload, a rebuild of the frame) comes back */
      var k=null;try{k=JSON.parse(w.top.sessionStorage.getItem(KEEP)||"null")}catch(e){k=null}
      if(!k)return;
      if(typeof k!=="object"||!realId(k.id)||!(Date.now()-(+k.at||0)<KEEP_MS)){forget();return}
      SH.id=+k.id;SH.t=clean(k.t,160);SH.c=clean(k.c,120);SH.state="wait";SH.since=Date.now();
      return}
    var id=String(q.get("job")||""),t=String(q.get("t")||""),c=String(q.get("c")||"");
    ["job","t","c"].forEach(function(k){q.delete(k)});
    try{var s=q.toString();w.top.history.replaceState(w.top.history.state,"",w.top.location.pathname+(s?"?"+s:"")+w.top.location.hash)}catch(e){}
    forget();   /* a new link replaces any landing still pending in this tab */
    if(!realId(id))return;
    SH.id=+id;SH.t=clean(t,160);SH.c=clean(c,120);SH.state="wait";SH.since=Date.now();
    keep();
  })();

  var line=d.createElement("p");line.className="ushr-line";line.id="ushrLine";line.hidden=true;line.setAttribute("aria-live","polite");
  col.insertBefore(line,deck);
  line.addEventListener("click",function(e){
    if(!(e.target.closest&&e.target.closest("[data-ushr-retry]")))return;
    e.preventDefault();keep();   /* the landing is still kept; the reload asks for the jobs again and reads it back */
    try{w.top.location.reload()}catch(x){w.location.reload()}
  });
  var gone=d.createElement("section");gone.className="ushr-closed";gone.id="ushrClosed";gone.hidden=true;gone.setAttribute("aria-labelledby","ushrGoneH");
  col.insertBefore(gone,acts);
  var lineKey="";
  function paintLine(){
    var what=esc(SH.t||"A job")+(SH.c?' at '+esc(SH.c):''),k=SH.state+"|"+SH.seen,h;
    if(SH.state==="wait")h='<span><b>Shared with you:</b> '+what+'. Looking for it in today’s listings…</span>';
    else if(SH.state==="fail")h='<span><b>Shared with you:</b> '+what+'. UAply couldn’t load jobs just now. <button type="button" class="linkbtn ushr-retry" data-ushr-retry>Try again</button></span>';
    else if(SH.state==="seen")h=SH.seen;
    else{h='<span><b>Shared with you</b> · a free job app · no account needed</span>';k="plain"}
    if(k!==lineKey){lineKey=k;line.innerHTML=GLYPH+h}
  }

  function arrived(data){
    if(!SH.state||SH.state==="open"||SH.state==="seen")return;
    var list=data&&Array.isArray(data.jobs)?data.jobs:[],has=false;
    for(var i=0;i<list.length;i++)if(+list[i].id===SH.id){has=true;break}
    var j=byId(SH.id);
    if(has&&j&&A.S.decisions[SH.id]){
      /* the friend already swiped this job: no second card (that could send a second application), a short note above the deck instead,
         until the next swipe */
      var s=A.S.decisions[SH.id].s;SH.state="seen";SH.closed=false;SH.pins=[];SH.dn=Object.keys(A.S.decisions).length;forget();
      SH.seen='<span><b>Shared with you:</b> '+esc(j.role)+' at '+esc(j.co)+'. '+(s==="applied"?"You already applied to it (Job Tracker, Applied).":s==="passed"?"You passed on it earlier.":"It is already in your Job Tracker.")+'</span>';
      A.renderAll();update();return}
    /* in the list (also when it turns up after "Not found yet" or after the friend swiped on): in front, with the line */
    if(has&&j){SH.state="open";SH.closed=false;SH.left=false;SH.pins=[SH.id];forget();A.renderAll();update();return}
    if(SH.state==="fail")SH.state="wait";   /* a later answer after a failed one: back to looking */
    /* not in the list. The list is complete once no board is pending (or the app has asked 16 times, its limit): no longer listed */
    if(!(data&&data.pending>0)||answers.n>=16){
      if(SH.state!=="closed"){SH.state="closed";SH.closed=!SH.left;forget();A.renderAll()}
      update();return}
    /* boards still loading: after 3 answers or 20 s the jobs like it show ("Not found yet"), the job still comes forward if it turns up */
    if(SH.state==="wait"&&(answers.n>=3||Date.now()-SH.since>=20000)){SH.state="maybe";SH.closed=!SH.left;A.renderAll()}
    update();
  }
  function failedNow(){
    /* /api/jobs failed: the app will not ask again by itself. Say so above whatever the deck shows, with Try again (the landing is kept) */
    if(SH.state!=="wait"&&SH.state!=="maybe")return;
    SH.state="fail";SH.closed=false;A.renderAll();update();
  }
  onJobs=SH.state?arrived:null;   /* always set: a build without ?job= never keeps an older build's watcher */
  onFail=SH.state?failedNow:null;
  if(SH.state==="wait")setTimeout(function(){if(SH.state==="wait"&&answers.last&&!answers.failed)arrived(answers.last)},20100);

  /* ---------- jobs like the one that is gone ---------- */
  var STOP={a:1,an:1,and:1,the:1,of:1,"for":1,to:1,"in":1,at:1,on:1,"with":1,or:1,ii:1,iii:1,iv:1,sr:1,jr:1,senior:1,junior:1,lead:1,staff:1,principal:1,remote:1,hybrid:1,usa:1,us:1};
  function words(s){return String(s||"").toLowerCase().split(/[^a-z0-9+#]+/).filter(function(x){return x.length>=3&&!STOP[x]})}
  function normCo(s){return String(s||"").toLowerCase().replace(/\b(inc|llc|ltd|corp|corporation|co|company|the)\b/g," ").replace(/[^a-z0-9]+/g," ").trim()}
  var KINDS=[["co-op",/\bco-?op\b/i],["internship",/\binterns?(hip)?s?\b/i],["part-time",/\bpart[- ]time\b/i],["temporary",/\bseasonal\b|\btemporary\b/i]];
  function kindOfTitle(t){for(var i=0;i<KINDS.length;i++)if(KINDS[i][1].test(t))return KINDS[i][0];return "full-time"}
  function kindOf(j){if(j.jobType)return j.jobType;return {internship:"internship",coop:"co-op",parttime:"part-time"}[j.type]||kindOfTitle(j.role)}
  var KIND_WORD={"full-time":"full-time","part-time":"part-time",internship:"internship","co-op":"co-op",contract:"contract",temporary:"temporary"};
  function cap1(s){return s.charAt(0).toUpperCase()+s.slice(1)}
  function similar(){
    var want=words(SH.t),co=normCo(SH.c),kind=kindOfTitle(SH.t),F=A.getFilter?A.getFilter():"all",S=A.S,t1=[],t2=[];
    A.JOBS.forEach(function(j){
      if(!j||!j.live||j.stub||+j.id===SH.id||S.decisions[j.id]||(F!=="all"&&j.mode!==F))return;
      var have=words(j.role),hit=[];want.forEach(function(x){if(have.indexOf(x)>-1&&hit.indexOf(x)<0)hit.push(x)});
      var same=!!co&&normCo(j.co)===co;
      if(hit.length||same){t1.push({j:j,score:hit.length+(same?1:0),why:(same?"the same company":"")+(same&&hit.length?" and ":"")+(hit.length?hit.length+" title word"+(hit.length>1?"s":"")+" ("+hit.map(cap1).join(", ")+")":"")})}
      else if(kindOf(j)===kind)t2.push({j:j,score:0,why:"the same kind of job ("+(KIND_WORD[kind]||kind)+")"});
    });
    function age(x){return typeof x.j.postedDays==="number"?x.j.postedDays:1e6}
    t1.sort(function(a,b){return b.score-a.score||age(a)-age(b)});t2.sort(function(a,b){return age(a)-age(b)});
    return t1.concat(t2).slice(0,10);
  }
  function ageTxt(n){if(typeof n!=="number")return "Posting date not listed";return n<=0?"Posted today":n===1?"Posted 1 day ago":n<7?"Posted "+n+" days ago":n<14?"Posted 1 week ago":"Posted "+Math.floor(n/7)+" weeks ago"}
  function payTxt(j){if(typeof w.uaPayText==="function")return w.uaPayText(j,1)||"Pay not listed";return j.sal&&j.sal[1]>0&&j.salUnit!=="hour"?A.money(j.sal[0])+"–"+A.money(j.sal[1])+" a year":"Pay not listed"}   /* as the posting gives it, with its unit */
  function rowHTML(x){
    var j=x.j,u=viaUAply(j),pay=payTxt(j),did="ushrD"+j.id;
    return '<button type="button" class="ushr-row" data-ushr-go="'+j.id+'" data-mode="'+esc(j.mode||"")+'" aria-label="'+esc(j.role)+' at '+esc(j.co)+'" aria-describedby="'+did+'">'+
      '<span class="logo" aria-hidden="true" style="background:hsl('+A.hue(j.id)+' 60% 46%)">'+esc(String(j.co||"?").charAt(0))+'</span>'+
      '<span class="ushr-bd"><b>'+esc(j.role)+'</b><span id="'+did+'"><span class="ushr-m">'+esc(j.co)+' · '+esc(j.loc||"Not listed")+'</span>'+
      '<span class="ushr-m2"><span class="ushr-age'+(typeof j.postedDays==="number"&&j.postedDays<=7?'':' old')+'">'+ageTxt(j.postedDays)+'</span>'+(pay?'<span class="ushr-pay">'+pay+'</span>':'')+
      '<span class="ushr-rt'+(u?' u':'')+'">'+(u?'Applies through UAply':'Finish on their site')+'</span></span>'+
      '<span class="ushr-like"><b>Like it:</b> '+esc(x.why)+'</span></span></span></button>';
  }
  var drawn="";
  function drawClosed(){
    var fin=SH.state==="closed",list=similar(),key=SH.state+"|"+list.map(function(x){return x.j.id}).join(",")+"|"+(A.getFilter?A.getFilter():"");
    if(gone.firstChild&&key===drawn)return;
    drawn=key;
    /* "maybe": boards are still loading, so UAply only knows it has not found the job yet, and says that */
    gone.innerHTML='<div class="ushr-tomb"><span class="ushr-st">'+CLOCK+(fin?'No longer listed on UAply':'Not found yet')+'</span>'+
      '<h2 id="ushrGoneH" tabindex="-1">'+esc(SH.t||"The job you were sent")+'</h2>'+(SH.c?'<p class="ushr-co">'+esc(SH.c)+'</p>':'')+
      '<p class="ushr-why">'+(fin?'UAply can’t find this job in today’s listings. UAply re-reads job boards every few hours.':
        'UAply is still reading job boards and hasn’t found this job yet. If it turns up, it moves to the front of your cards.')+'</p></div>'+
      '<div class="ushr-sec"><h3>Open now, like the one you were sent</h3><p>Same title words or company first, then the same kind of job. Each age comes from the posting.'+
      (list.length?' <button type="button" class="linkbtn" data-ushr-go="">Swipe through them</button>':'')+'</p></div>'+
      (list.length?list.map(rowHTML).join(""):
        /* nothing like it (or nothing with this filter): the way back to the deck is always here */
        '<p class="ushr-empty">No open jobs like it'+((A.getFilter&&A.getFilter()!=="all")?' with this filter':'')+' right now. '+
        '<button type="button" class="linkbtn ushr-other" data-ushr-go="">See other open jobs</button></p>');
  }
  gone.addEventListener("click",function(e){
    var b=e.target.closest&&e.target.closest("[data-ushr-go]");if(!b)return;
    var ids=similar().map(function(x){return +x.j.id}),at=+b.getAttribute("data-ushr-go");
    if(at&&ids.indexOf(at)>0)ids=ids.slice(ids.indexOf(at)).concat(ids.slice(0,ids.indexOf(at)));
    SH.closed=false;SH.left=true;SH.pins=ids;A.renderAll();update();
    var top=deck.querySelector(".card.top");if(top&&top.focus){top.setAttribute("tabindex","-1");try{top.focus({preventScroll:true})}catch(x){}}
  });
  /* while "No longer listed" stands in for the card, the keys that swipe it do nothing (the deck behind it is hidden) */
  d.addEventListener("keydown",function(e){
    if(!SH.closed||gone.hidden)return;
    var t=e.target&&e.target.tagName;if(t==="INPUT"||t==="SELECT"||t==="TEXTAREA")return;
    if(e.key==="ArrowLeft"||e.key==="ArrowRight"||e.key==="z"||e.key==="Z"){e.stopPropagation();e.preventDefault()}
  },true);

  function update(){
    var closed=SH.closed&&(SH.state==="closed"||SH.state==="maybe");
    if(closed)drawClosed();
    gone.hidden=!closed;deck.hidden=closed;acts.hidden=closed;if(hint)hint.hidden=closed;
    deck.style.display=closed?"none":"";acts.style.display=closed?"none":"";if(hint)hint.style.display=closed?"none":"";
    var top=deck.querySelector(".card.top");
    paintLine();
    line.hidden=!(closed||SH.state==="wait"||SH.state==="fail"||(SH.state==="open"&&top&&+top.getAttribute("data-id")===SH.id)||(SH.state==="seen"&&Object.keys(A.S.decisions).length===SH.dn));
  }
  new w.MutationObserver(update).observe(deck,{childList:true});
  update();
  /* an answer (or a failure) that came before this build was ready */
  if(SH.state&&answers.failed)failedNow();
  else if(SH.state&&answers.last)arrived(answers.last);

  /* ---------- the Job Tracker's "Not sent yet" rows get the same icon (a Share like the row's own: shared/uaply-nav.js handles data-act="share") ---------- */
  var tp=d.getElementById("pane-track");
  if(!tp)fail("patch target not found: #pane-track (Job Tracker)");
  function rowIcons(){
    tp.querySelectorAll(".row").forEach(function(r){
      var s=r.querySelector("small.sent.todo");if(!s||!/^Not sent yet\b/.test(s.textContent)||s.querySelector(".ushr-rowic"))return;
      var b=r.querySelector('[data-act="share"][data-id]');if(!b)return;
      var id=b.getAttribute("data-id"),j=byId(id);
      var x=d.createElement("button");x.type="button";x.className="ushr-rowic";x.setAttribute("data-act","share");x.setAttribute("data-id",id);
      x.setAttribute("aria-label","Share this job"+(j?": "+j.role+" at "+j.co:""));x.title="Share this job";x.innerHTML=GLYPH;
      s.appendChild(x);
    });
  }
  new w.MutationObserver(rowIcons).observe(tp,{childList:true,subtree:true});
  rowIcons();
}

Env.FEATURES.share={name:"Share this job",note:"A small share icon in the top-right corner of the job card (and on Not sent yet rows in Job Tracker) shares a UAply link to that job: the phone's share sheet, else a copied link. A friend who opens the link sees that job first under a \"Shared with you\" line, no account needed; a job no longer listed shows open jobs like it. Needs Bottom navigation and Real jobs, which turn on with it.",patch:patch,apply:apply};
Env.ORDER.push("share");
})();
