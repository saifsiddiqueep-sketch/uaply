/* "learn" experiment for the sandbox (never loaded by prod or dev): UAply learns what this person likes from their own swipes and
   reorders the deck, on this device only, and every card says what it learned.
   - The match score stays the starting point (the prior): p0 = match% / 100. With no swipes the deck is exactly today's deck.
   - Each swipe adds evidence for the attributes of that job: work style, opportunity type, role family (first two words of the
     title), company, pay band ($20k steps), years asked, city or state, the skills asked, and where the job came from.
   - It only ever reads those job fields. It never reads the profile, so voluntary answers (race, gender, veteran, disability),
     work authorization and GPA can never count, and an employer's own GPA or work-authorization requirement is not an attribute.
   - Filters stay hard rules: it only reorders the cards the filters already let through, and adds or removes none.
   - What is sent to an employer and saved in Applied is still the profile match, never the learned number.
   Design: "UAply Swipe Learning" (October 16, 2026), section "The recommended design, concretely". */
(function(){
function once(src,a,b){if(src.indexOf(a)<0)throw new Error("patch target not found: "+a.slice(0,40));return src.replace(a,function(){return b})}

/* every number from the design, in one place */
var K={
  right:1.0,read:1.2,finish:1.5,      /* swipe right; swipe right after opening the details; swipe right, then finished on the employer's site */
  slow:-0.6,fast:-0.25,undoRight:-0.3,/* swipe left after reading (2 s or more); swipe left in under 0.7 s; Undo of a swipe right */
  fastMs:700,slowMs:2000,             /* a swipe left between the two is weighed in between, in a straight line */
  keep:300,fade:0.98,                 /* only the last 300 swipes count; each day of age multiplies a swipe's weight by 0.98 */
  cap:1.5,                            /* one attribute moves the log-odds at most 1.5 either way (+1.5 or -1.5), so a few passes never bury a whole kind of job */
  early:30,capEarly:25,capLate:40,    /* the learned part of a score: at most 25 points either way before 30 swipes, 40 after */
  every:5,                            /* one card in every five comes from outside the top of the learned ranking */
  priorN:8,                           /* the card draw (Thompson sampling) counts the match score as 8 swipes of evidence, so a weak job is not over-explored */
  minN:8,                             /* no score moves before 8 swipes, nor until there is at least one yes and one no (nothing to compare
                                         with): a new person's first right swipes used to push a 95% match out of the top 10, and to take
                                         points off a card "because you passed" when they had passed on nothing (October 22) */
  gate:true,                          /* scores stay the match until ready() (see minN); only the design's formula word for word in
                                         tools/test-learn.py turns it off */
  minA:2,                             /* an attribute counts once at least 2 swipes carried it: one swipe is a coincidence, not a taste */
  strong:90,strongDrop:10,            /* before 30 swipes (early), a match of 90% or more never loses more than 10 points to learning and is
                                         ranked by at least that number, so the best matches stay near the top whatever the draw; from 30
                                         swipes on, a clear taste may move them like any other card */
  center:true                         /* each attribute is measured against how often this person says yes overall (naive Bayes). Without it,
                                         someone who passes more than they apply pushes every attribute down, even "full-time" that every job has,
                                         every card hits the -40 limit and the deck never changes (seen in tools/ui-learn.js). With an even
                                         yes/no balance it is exactly the design's formula. It applies only once there are both yeses and
                                         noes, and never turns a kind of job that was only liked into a minus, nor one only passed into a plus. */
};
var DAY=864e5,MODES={remote:1,hybrid:1,onsite:1},TYPES={job:1,internship:1,coop:1,parttime:1};
/* role family: seniority and filler words are dropped, a few word forms are joined ("Product Designer" -> "product design") */
var DROP=/^(senior|sr|junior|jr|lead|staff|principal|associate|entry|level|mid|i|ii|iii|iv|v|the|of|and|a|an|remote|hybrid)$/;
var STEM={designer:"design",designers:"design",engineering:"engineer",engineers:"engineer",developers:"developer",analysts:"analyst",managers:"manager",interns:"intern",internship:"intern",scientists:"scientist"};

function family(title){
  var t=String(title||"").toLowerCase().split(/\s[-–—|]\s|[,(;]/)[0];
  return t.split(/[^a-z0-9+#]+/).filter(function(x){return x&&!DROP.test(x)}).map(function(x){return STEM[x]||x}).slice(0,2).join(" ");
}
function place(loc){
  var c=String(loc||"").split(/[,(;]/)[0].trim().toLowerCase();
  return /^(remote|anywhere|not listed|united states|usa|us|multiple locations|various)\b/.test(c)?"":c;
}
function origin(j){
  if(j.emp)return "uaply";if(j.partner)return "partner";if(!j.live)return "example";
  var s=String(j.source||"");return /careers page$/i.test(s)||!s?"board":s.toLowerCase();
}
/* the attributes a job carries, as "kind:value" keys. Only these job fields are read; nothing else can become an attribute. */
function attrs(j){
  var a=[];if(!j||typeof j!=="object")return a;
  function add(k,v){v=String(v==null?"":v).trim().toLowerCase().replace(/\s+/g," ").slice(0,60);if(v&&a.indexOf(k+":"+v)<0)a.push(k+":"+v)}
  if(MODES[j.mode])add("m",j.mode);
  add("t",TYPES[j.type]?j.type:"job");
  add("r",family(j.role));
  add("c",j.co);
  var s=Array.isArray(j.sal)?j.sal:[0,0],lo=+s[0]||0,hi=+s[1]||0;
  if(hi>0&&j.salUnit!=="hour")add("p",Math.floor((lo>0?(lo+hi)/2:hi)/20000)*20);          /* pay band in $20k steps, from the middle of a yearly range (hourly pay has none: it is never turned into a year) */
  var y=+j.yrs||0;add("y",y<=0?"0":y<=2?"1-2":y<=5?"3-5":"5+");
  if(j.mode!=="remote")add("l",place(j.loc));                          /* a remote job has no city that matters */
  (Array.isArray(j.skills)?j.skills:[]).slice(0,8).forEach(function(x){add("s",x)});
  add("o",origin(j));
  return a;
}
/* the same, plus the match band (always jobs, October 24): what they swipe right on includes the band they favour */
function attrsFit(j,fit){var a=attrs(j);if(j&&typeof j==="object"&&fit!=null&&isFinite(fit))a.push("b:"+band(fit));return a}
function band(f){f=+f||0;return f>=90?"90":f<50?"0":String(Math.floor(f/10)*10)}
function title1(s){return String(s).replace(/\b[a-z]/g,function(c){return c.toUpperCase()})}
/* the words a card uses for an attribute ("remote jobs", "jobs at Figma") */
function label(a,j){
  var k=a.charAt(0),v=a.slice(2),hit;
  if(k==="m")return {remote:"remote jobs",hybrid:"hybrid jobs",onsite:"on-site jobs"}[v];
  if(k==="t")return {job:"full-time jobs",internship:"internships",coop:"co-ops",parttime:"part-time jobs"}[v];
  if(k==="r")return v+" roles";
  if(k==="c")return "jobs at "+(j&&j.co&&String(j.co).trim().toLowerCase()===v?String(j.co).trim():title1(v));
  if(k==="p")return "jobs paying $"+v+"k to $"+(+v+20)+"k";
  if(k==="y")return v==="0"?"jobs that ask for no experience":v==="5+"?"jobs that ask for more than 5 years":"jobs that ask for "+v.replace("-"," to ")+" years";
  if(k==="l")return "jobs in "+title1(v);
  if(k==="s"){hit=j&&Array.isArray(j.skills)?j.skills.filter(function(x){return String(x).trim().toLowerCase()===v})[0]:"";return "jobs asking for "+(hit||v)}
  if(k==="b")return v==="90"?"jobs at a 90% match or more":v==="0"?"jobs under a 50% match":"jobs at a "+v+"% to "+(+v+9)+"% match";
  if(k==="o")return {board:"jobs from employers' own job boards",uaply:"jobs posted on UAply",partner:"jobs from partner employers",example:"example listings"}[v]||"jobs from "+title1(v);
  return v;
}

/* ---------- evidence ---------- */
/* a stored swipe: {id, at (ms), k, d (ms on screen, swipes left only), a (attributes)}.
   k: R right, D right after opening the details, F right and then finished on the employer's site, L left, U a swipe right taken back with Undo */
function weight(e){
  if(e.k==="F")return K.finish;if(e.k==="D")return K.read;if(e.k==="R")return K.right;if(e.k==="U")return K.undoRight;
  if(e.k!=="L")return 0;
  var d=+e.d||0;if(d<=K.fastMs)return K.fast;if(d>=K.slowMs)return K.slow;
  return K.fast+(K.slow-K.fast)*(d-K.fastMs)/(K.slowMs-K.fastMs);
}
function fadeOf(at,now){return Math.pow(K.fade,Math.max(0,Math.floor((now-at)/DAY)))}
/* likes and dislikes per attribute value (weighted and faded), plus plain counts for the explanation.
   Counts: yes = a swipe right (R, D, F), no = a real swipe left (L) and nothing else, undo = a swipe right taken back with Undo (U).
   An Undo is never a pass: it is not in "no", it does not count as one of the swipes (dec), and it never makes the learner ready (P). */
function evidence(list,now){
  var ev=(list||[]).slice(-K.keep),like={},dis={},cnt={},L=0,D=0,P=0,dec=0;
  ev.forEach(function(e){
    var w=weight(e),f=fadeOf(e.at,now),yes=e.k==="R"||e.k==="D"||e.k==="F",no=e.k==="L";
    if(w>0)L+=w*f;else D-=w*f;                                          /* this person's overall yes and no, each swipe once */
    if(no)P++;if(e.k!=="U")dec++;
    (e.a||[]).forEach(function(a){
      if(w>0)like[a]=(like[a]||0)+w*f;else if(w<0)dis[a]=(dis[a]||0)-w*f;
      var c=cnt[a]||(cnt[a]={yes:0,no:0,undo:0});if(yes)c.yes++;else if(no)c.no++;else if(e.k==="U")c.undo++;
    });
  });
  return {like:like,dis:dis,cnt:cnt,n:ev.length,dec:dec,P:P,L:L,D:D};
}
/* enough to learn from: at least minN swipes (an Undo is not one), with at least one yes and one real pass among them */
function ready(E){return !!E&&E.dec>=K.minN&&E.L>0&&E.P>0}
/* this person's overall yes/no balance, the centre each attribute is measured against (only once both a yes and a real pass exist) */
function center(E){return K.center&&E.L>0&&E.P>0?Math.log((E.L+1)/(E.D+1)):0}
/* how far one attribute leans, before the cap: null when it has no evidence or too little (minA). A kind of job never passed on (a real
   swipe left; an Undo is not one) cannot lean down, and one never liked cannot lean up, so the card's reason ("You've passed on N of M")
   is always about a swipe that happened. An Undo can only take some of the lean up away. */
function lean(a,E,base){
  var l=E.like[a]||0,d=E.dis[a]||0,c0=E.cnt[a];if(!l&&!d)return null;
  if(c0&&c0.yes+c0.no<K.minA)return null;
  var raw=Math.log((l+1)/(d+1))-base,passed=c0?c0.no>0:d>0,liked=c0?c0.yes>0:l>0;
  if(!passed&&raw<0)raw=0;if(!liked&&raw>0)raw=0;
  return raw;
}
function logit(p){return Math.log(p/(1-p))}
function sig(z){return 1/(1+Math.exp(-z))}
/* logit(p) = logit(p0) + sum over the job's attributes of a value held between -1.5 and +1.5 of log((likes+1)/(dislikes+1)) - log((all yes+1)/(all no+1));
   the learned part is then limited to 25 points (40 from 30 swipes on). fit = the profile match (0-100).
   An attribute never swiped adds nothing (never shown = unknown, not a no). Before ready() nothing moves: the score is the match. */
function score(j,fit,E){
  fit=Math.max(0,Math.min(100,+fit||0));
  var p0=Math.min(0.99,Math.max(0.01,fit/100)),z=logit(p0),parts=[],mass=0,base=center(E),lim=E.dec<K.early?K.capEarly:K.capLate;   /* an Undo is not a swipe: the 30-swipe limits count decisions (dec), not stored entries (n) */
  attrsFit(j,fit).forEach(function(a){
    var raw=lean(a,E,base);if(raw==null)return;                           /* no evidence, or too little yet (see minA) */
    var c=Math.max(-K.cap,Math.min(K.cap,raw));
    z+=c;mass+=(E.like[a]||0)+(E.dis[a]||0);parts.push({a:a,raw:raw,c:c});
  });
  if(K.gate&&!ready(E))return {fit:fit,p0:p0,z:logit(p0),p:p0,pts:0,lim:lim,shown:Math.round(fit),delta:0,parts:[],mass:mass};   /* the match, unmoved */
  var p=sig(z),pts=Math.max(-lim,Math.min(lim,100*(p-p0)));
  if(fit>=K.strong&&E.dec<K.early)pts=Math.max(pts,-K.strongDrop);                     /* the floor for strong matches (see strong) */
  var shown=Math.max(0,Math.min(100,Math.round(fit+pts)));
  return {fit:fit,p0:p0,z:z,p:p,pts:pts,lim:lim,shown:shown,delta:shown-fit,parts:parts,mass:mass};
}
/* the reason a card gives: the attribute that moved it most in the same direction, with counts from the swipe history */
function explain(j,s,E){
  if(!s.delta)return {why:"",key:""};
  var up=s.delta>0,best=null;
  s.parts.forEach(function(x){
    if(up?x.c<=0:x.c>=0)return;
    var n=E.cnt[x.a];if(!n||(up?!n.yes:!n.no))return;                    /* never "passed on 0" (or "liked 0"): the reason is a swipe that happened */
    if(!best||Math.abs(x.c)>Math.abs(best.c)||(Math.abs(x.c)===Math.abs(best.c)&&Math.abs(x.raw)>Math.abs(best.raw)))best=x;
  });
  if(!best)return {why:"",key:""};
  var c=E.cnt[best.a]||{yes:0,no:0};
  return {why:(up?"You've liked "+c.yes:"You've passed on "+c.no)+" of "+(c.yes+c.no)+" "+label(best.a,j)+".",key:best.a,yes:c.yes,no:c.no};
}

/* ---------- which card next: Thompson sampling ---------- */
function rng(seed){return function(){seed=seed+0x6D2B79F5|0;var t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296}}
function hash(s){var h=2166136261;s=String(s);for(var i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return h>>>0}
function normal(r){var u=r()||1e-12,v=r();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v)}
function gamma(a,r){   /* Marsaglia and Tsang */
  if(a<1){var u=r()||1e-12;return gamma(a+1,r)*Math.pow(u,1/a)}
  var dd=a-1/3,c=1/Math.sqrt(9*dd);
  for(;;){
    var x,v;do{x=normal(r);v=1+c*x}while(v<=0);
    v=v*v*v;var u2=r()||1e-12;
    if(u2<1-0.0331*x*x*x*x||Math.log(u2)<0.5*x*x+dd*(1-v+Math.log(v)))return dd*v;
  }
}
function beta(a,b,r){var x=gamma(a,r),y=gamma(b,r);return x+y>0?x/(x+y):0.5}
/* one draw per card: a Beta with the evidence the job's attributes have (likes_total + 1, dislikes_total + 1) plus the match score
   counted as priorN swipes, centred on the learned score. Few swipes: wide draws (it tries things); many: narrow (it uses what it knows).
   The same state always gives the same draw, so the deck does not reshuffle between two looks at it. */
function draw(s,key){
  var p=Math.min(0.995,Math.max(0.005,s.shown/100)),k=K.priorN+2+s.mass;
  return beta(p*k,(1-p)*k,rng(hash(key)));
}
/* items: the deck as the page built it ({j:job, m:{pct,...}}), already filtered and sorted by match.
   Returns the same cards (never more, never fewer) in the learned order, each with m.pct = the learned number, m.fit = the profile
   match and m.learn = what to say on the card. One card in every five shown comes from the bottom half of the learned ranking. */
function order(items,st,now,pin){
  var E=evidence(st&&st.ev,now);
  if(!E.n||!items||!items.length)return items;
  if(E.dec<K.minN||!(E.P>0))return items;                        /* not enough to learn from yet: the match order, untouched (an Undo is
                                                                    neither a swipe nor a pass here). With passes and no yes yet, scores stay
                                                                    the match (ready) but the 1-in-5 card still runs */
  var list=items.map(function(x){
    var s=score(x.j,x.m.pct,E);
    if(x.m.capped&&s.shown>45){s.shown=Math.max(45,s.fit);s.delta=s.shown-s.fit}   /* "Capped at 45%" stays true */
    var dr=draw(s,st.seed+":"+st.ver+":"+x.j.id);
    if(s.fit>=K.strong&&E.dec<K.early)dr=Math.max(dr,s.shown/100);                     /* a strong match is ranked by at least its own number */
    return {x:x,s:s,d:dr};
  });
  var ranked=list.slice().sort(function(a,b){return b.d-a.d||b.s.shown-a.s.shown});
  /* the explore card: from the bottom half of the learned ranking, the one UAply knows least about (least evidence), then the best match */
  var half=Math.ceil(ranked.length/2),pool=ranked.slice(half).sort(function(a,b){return a.s.mass-b.s.mass||b.s.fit-a.s.fit});
  var used={},out=[],ri=0,pi=0,n=+st.n||0;
  for(var i=0;i<ranked.length;i++){
    var pick=null,ex=false;
    if(i===0&&pin!=null)list.some(function(o){if(o.x.j.id===pin){pick=o;return true}return false});   /* the card Undo brought back stays on top */
    if(!pick&&(n+i+1)%K.every===0){while(pi<pool.length&&used[pool[pi].x.j.id])pi++;if(pi<pool.length){pick=pool[pi];ex=true}}
    if(!pick){while(used[ranked[ri].x.j.id])ri++;pick=ranked[ri]}
    used[pick.x.j.id]=1;
    var why=explain(pick.x.j,pick.s,E);
    out.push({j:pick.x.j,m:Object.assign({},pick.x.m,{pct:pick.s.shown,fit:pick.s.fit,learn:{delta:pick.s.delta,why:why.why,key:why.key,explore:ex,n:E.dec}})});
  }
  return out;
}

/* ---------- the saved state (next to the swipe history, in the same saved record) ---------- */
function fresh(){return {v:1,seed:(Math.random()*1e9)|0,n:0,ver:0,ev:[]}}
function clean(x){
  if(!x||typeof x!=="object"||!Array.isArray(x.ev))return fresh();
  var ev=x.ev.filter(function(e){return e&&typeof e==="object"&&/^[RDFLU]$/.test(e.k)&&isFinite(+e.at)&&Array.isArray(e.a)}).slice(-K.keep).map(function(e){
    return {id:typeof e.id==="number"?e.id:String(e.id).slice(0,40),at:+e.at,k:e.k,d:Math.max(0,Math.min(36e5,+e.d||0)),
      a:e.a.filter(function(a){return typeof a==="string"&&/^[mtrclpysob]:./.test(a)}).slice(0,24).map(function(a){return a.slice(0,64)})};   /* only job attributes can be stored */
  });
  return {v:1,seed:(+x.seed|0)||fresh().seed,n:Math.max(0,Math.min(1e6,+x.n|0)),ver:Math.max(0,+x.ver|0),ev:ev};
}
function last(st,id){for(var i=st.ev.length-1;i>=0;i--)if(st.ev[i].id===id)return i;return -1}
/* a swipe: one entry per job (swiping the same job again replaces the old entry) */
function swipe(st,j,dir,dwell,read,now,fit){
  var i=last(st,j.id);if(i>-1)st.ev.splice(i,1);
  st.ev.push({id:j.id,at:now,k:dir==="applied"?(read?"D":"R"):"L",d:dir==="applied"?0:Math.max(0,Math.round(+dwell||0)),a:attrsFit(j,fit)});
  if(st.ev.length>K.keep)st.ev=st.ev.slice(-K.keep);
  st.n++;st.ver++;
}
/* Undo: a swipe left is removed entirely; a swipe right becomes a small no (U). A U is never called a pass, never counts as a swipe for
   ready(), and can never pull a card down by itself: see evidence() and lean() */
function undo(st,id){
  var i=last(st,id);
  if(i>-1){if(st.ev[i].k==="L")st.ev.splice(i,1);else st.ev[i].k="U"}
  st.n=Math.max(0,st.n-1);st.ver++;
}
/* the person went on to the employer's site for a job they swiped right on */
function finish(st,id){var i=last(st,id);if(i>-1&&(st.ev[i].k==="R"||st.ev[i].k==="D")){st.ev[i].k="F";st.ver++;return true}return false}
function reset(st){st.ev=[];st.n=0;st.ver++}

function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
/* the line under the match ring */
function lineHTML(m){
  var L=m&&m.learn;if(!L)return "";
  var t="";
  if(L.delta)t='<b>Learned from your swipes: '+(L.delta>0?"+":"−")+Math.abs(L.delta)+'.</b> '+esc(L.why)+' Profile fit alone: '+esc(m.fit)+'%.';
  if(L.explore)t+=(t?" ":"")+'<span class="lx">Something different: 1 in 5 cards is outside what you usually like.</span>';
  return t?'<p class="learned"'+(L.explore?' data-explore="1"':'')+'>'+t+'</p>':"";
}

var CSS=".learned{margin:-4px 0 0;font-size:14px;line-height:1.4;color:var(--muted)}.learned b{color:var(--ink);font-weight:700}.learned .lx{color:var(--accent)}"+
  "#lrnBox{display:flex;flex-direction:column;gap:6px}#lrnSum{color:var(--muted)}";

function patch(s){
  /* the deck order: the page's own queue (filters, then match) goes through the learner */
  s=once(s,"function queue(){","function queue(){var q=queue0();return window.__uaplyLearnOrder?window.__uaplyLearnOrder(q):q}\nwindow.__uaplyQueue=queue;\nfunction queue0(){");
  /* what was learned is saved with the swipes and read back with them */
  s=once(s,"if(d.tips===false)S.tips=false;","if(d.tips===false)S.tips=false;if(d.learn&&typeof d.learn===\"object\")S.learn=d.learn;");
  /* every swipe and every Undo is reported before the page saves and redraws */
  s=once(s,"S.history.push(id);S.tips=false;save();","S.history.push(id);if(window.__uaplyLearnSwipe)window.__uaplyLearnSwipe(job,dir);S.tips=false;save();");
  s=once(s,"var id=S.history.pop();if(!id)return;","var id=S.history.pop();if(!id)return;if(window.__uaplyLearnUndo)window.__uaplyLearnUndo(id);");
  /* the card says what it learned, under the match ring */
  s=once(s,"'<ul class=\"crit incard\" aria-label=\"Why this score\">'","(m.learn&&window.__uaplyLearnLine?window.__uaplyLearnLine(m):\"\")+'<ul class=\"crit incard\" aria-label=\"Why this score\">'");
  return once(s,"</style>",CSS+"</style>");
}

function apply(w){
  var d=w.document,A=w.__uaply;if(!A||!A.S)throw new Error("app hooks missing");
  var st=A.S.learn=clean(A.S.learn),pin=null,top=null,shownAt={},read={};
  var reduce=!!(w.matchMedia&&w.matchMedia("(prefers-reduced-motion: reduce)").matches);
  /* the cards outside the person's filters (always jobs) keep their place after the rest, nearest first */
  w.__uaplyLearnOrder=function(q){try{var a=q.filter(function(x){return !x.out}),b=q.filter(function(x){return x.out});return order(a,st,Date.now(),pin).concat(b)}catch(e){return q}};   /* a learner problem never empties the deck */
  w.__uaplyLearnLine=lineHTML;
  w.__uaplyLearnSwipe=function(job,dir){
    if(!job)return;
    var now=Date.now(),t=shownAt[job.id];
    var fit=null;try{fit=A.evaluate(job,A.S.profile).pct}catch(e){}
    swipe(st,job,dir,t?now-t-(reduce?0:280):K.slowMs,!!read[job.id],now,fit);   /* 280 ms: the card's fly-away before the page records the swipe */
    pin=null;delete read[job.id];summary();
  };
  w.__uaplyLearnUndo=function(id){undo(st,+id);pin=+id;summary()};
  /* when each card reached the top (how long it was read before a swipe left) */
  var deck=d.getElementById("deck");
  function seen(){var c=deck&&deck.querySelector(".card.top"),id=c?+c.getAttribute("data-id"):null;if(id!==top){top=id;if(id!=null)shownAt[id]=Date.now()}}
  if(deck){new w.MutationObserver(seen).observe(deck,{childList:true});seen()}
  /* opened the details before deciding: Show all criteria, About the job, the original posting, or scrolled down the card */
  function mark(e){var t=e.target;if(!t||!t.closest)return;var c=t.closest(".card.top");if(c&&t.closest("[data-more],summary,[data-open]"))read[+c.getAttribute("data-id")]=true}
  d.addEventListener("pointerdown",mark,true);d.addEventListener("click",mark,true);
  d.addEventListener("scroll",function(e){var c=e.target;if(c&&c.classList&&c.classList.contains("card")&&c.classList.contains("top")&&c.scrollTop>40)read[+c.getAttribute("data-id")]=true},true);
  /* went to the employer's site after a swipe right (Finish on their site, Open, Finish now): the strongest yes */
  var open0=w.__uaplyOpen;
  if(typeof open0==="function")w.__uaplyOpen=function(u){
    try{var hit=false,bare=String(u||"").replace(/([?&])(gh_src|lever-source)=uaply(&|$)/,function(m,p1,k,p3){return p3?p1:""});A.JOBS.forEach(function(j){if(u&&(j.url===u||j.url===bare||(w.__uaplyHandoffURL&&j.url&&w.__uaplyHandoffURL(j.url)===u))&&finish(st,j.id))hit=true});if(hit){A.save();summary()}}catch(e){}
    return open0.apply(this,arguments);
  };

  /* Profile, Filters: what it learned, and the Reset button */
  var box=d.createElement("div");box.className="field";box.id="lrnBox";
  box.innerHTML='<span class="l">What UAply learned from your swipes</span><small id="lrnSum" aria-live="polite"></small><button type="button" class="btn ghost" id="lrnReset" style="align-self:flex-start">Reset what UAply learned</button>';
  var fs=d.getElementById("filtersSec"),fa=d.querySelector("#form .formacts");
  if(fs)fs.appendChild(box);else if(fa)fa.parentNode.insertBefore(box,fa);
  function summary(msg){
    var el=d.getElementById("lrnSum");if(!el)return;
    if(msg){el.textContent=msg;return}
    var E=evidence(st.ev,Date.now());
    if(!E.dec){el.textContent="Nothing learned yet. Cards are in order of how well your profile fits.";return}
    if(!ready(E)){el.textContent=E.dec+" swipe"+(E.dec===1?"":"s")+" so far, on this device only. No score changes until "+K.minN+" swipes with at least one yes and one no; until then each score is how well your profile fits.";return}
    var up=null,down=null,base=center(E);
    Object.keys(E.cnt).forEach(function(a){var x=lean(a,E,base);if(x==null)return;if(x>0.01&&(!up||x>up.x))up={a:a,x:x};if(x<-0.01&&(!down||x<down.x))down={a:a,x:x}});
    function say(o,yes){var c=E.cnt[o.a];return (yes?"liked "+c.yes:"passed on "+c.no)+" of "+(c.yes+c.no)+" "+label(o.a,null)}
    var said=[up&&"You "+say(up,true),down&&(up?"you ":"You ")+say(down,false)].filter(Boolean).join("; ");
    el.textContent="Learned from your last "+E.dec+" swipe"+(E.dec===1?"":"s")+", on this device only. "+(said?said+".":"Nothing stands out yet: no kind of job gets more yes or no from you than the rest.")+
      " It never uses your voluntary answers, work authorization or GPA, and your filters still decide what you see.";
  }
  d.getElementById("lrnReset").onclick=function(){
    reset(st);pin=null;try{A.save()}catch(e){}try{A.renderAll()}catch(e){}
    summary("Done. UAply forgot what it learned from your swipes; cards are back in order of how well your profile fits.");
  };
  summary();
  /* for tests and the Filters screen */
  w.__uaplyLearn={state:function(){return st},reset:function(){d.getElementById("lrnReset").click()},
    peek:function(n){var q=w.__uaplyQueue?w.__uaplyQueue():[];return q.slice(0,n||5).map(function(x){var L=x.m.learn||{};return {id:x.j.id,mode:x.j.mode,co:x.j.co,fit:x.m.fit==null?x.m.pct:x.m.fit,pct:x.m.pct,delta:L.delta||0,why:L.why||"",key:L.key||"",explore:!!L.explore}})}};
}

window.UAplyLearn={patch:patch,apply:apply,
  core:{K:K,family:family,attrs:attrs,attrsFit:attrsFit,band:band,label:label,weight:weight,evidence:evidence,score:score,explain:explain,ready:ready,lean:lean,order:order,draw:draw,fresh:fresh,clean:clean,swipe:swipe,undo:undo,finish:finish,reset:reset,lineHTML:lineHTML}};
})();
