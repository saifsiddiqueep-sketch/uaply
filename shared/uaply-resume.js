/* "resume" experiment (sandbox first): Fill from your resume.
   Adds a box at the top of Profile setup, Background and links (the step with the resume file). The person chooses their resume (PDF, Word
   .docx or text, up to 1 MB); the server reads it for a moment (resume_parse.py, POST /api/profile/resume, nothing is kept) and answers
   with the fields it found. This file then fills every EMPTY profile field with them. A field the person already typed is never changed:
   when the resume says something different, the list offers Replace for that field. The list shows each answer with the line of the
   resume it came from, so the person can check it before applying. Nothing is saved until the person saves the step, as with typing.
   The same file is also kept as the resume that goes with applications, in Bottom navigation's resume store (on this device), so this
   box's button is the only resume picker on the step (Bottom navigation's own picker is hidden) and its limit is the same 1 MB: the
   file travels inside each application, and the server takes an application of up to 1.5 MB.
   Needs Bottom navigation; uses the Application profile's fields when that experiment is on. Registered in uaply-envs.js as "resume". */
(function(){
"use strict";
var MAX=1048576,OK_EXT=/\.(pdf|docx|txt)$/i;
var MON=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

var CSS=".rsBox{border:1px dashed var(--accent);border-radius:16px;padding:14px;display:flex;flex-direction:column;gap:8px;margin-bottom:14px;background:var(--surface)}"+
".rsBox h4{margin:0;font:800 16px var(--display)}.rsBox>p{margin:0;color:var(--muted);font-size:14px}"+
".rsActs{display:flex;flex-wrap:wrap;gap:8px;align-items:center;position:relative}.rsActs .btn{min-height:44px}.rsActs .linkbtn{font-size:14px;min-height:44px;text-align:left}"+
".rsPick{position:absolute;left:0;top:0;width:1px;height:1px;opacity:0;pointer-events:none;overflow:hidden}"+
"#rsMsg{margin:0;font-size:14px;font-weight:600}#rsMsg.bad{color:var(--no)}#rsMsg:empty{display:none}"+
".rsList{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}"+
".rsList li{border:1px solid var(--line);border-radius:12px;padding:9px 11px;display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center;background:var(--bg)}"+
".rsList .k{font-size:14px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.03em;flex:1 1 100%}"+
".rsList .v{flex:1 1 180px;min-width:0;overflow-wrap:anywhere;font-weight:600}"+
".rsList .st{font-size:14px;color:var(--muted)}.rsList .st.ok{color:var(--yes)}"+
".rsList .src{flex:1 1 100%;font-size:14px;color:var(--muted);overflow-wrap:anywhere}.rsList .src q{font-style:italic}"+
".rsList .chk{font-size:14px;font-weight:700;color:var(--no);border:1px solid currentColor;border-radius:99px;padding:1px 7px}"+
".rsList button{min-height:36px;border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:5px 12px;font-weight:600;font-size:14px;color:var(--ink)}"+
".rsFilled{outline:2px solid var(--accent);outline-offset:1px}";

function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
function month(v){var m=/^(\d{4})-(\d{2})$/.exec(v||"");return m?MON[+m[2]-1]+" "+m[1]:v}
/* a month field takes "2023-09" only: a year alone or "present" is left for the person ("Leave it blank if you still work there") */
function ym(v){return /^\d{4}-(0[1-9]|1[0-2])$/.test(v||"")}
/* still studying: the resume's graduation (expected) month is this month or later */
function student(F){var g=(F.grad||{}).value||"",n=new Date(),now=n.getFullYear()+"-"+("0"+(n.getMonth()+1)).slice(-2);return /^\d{4}-\d{2}$/.test(g)&&g>=now}
function when(v){if(v==="present")return "now";var m=/^(\d{4})-(\d{2})$/.exec(v||"");return m?MON[+m[2]-1]+" "+m[1]:(v||"")}
function norm(k,v){
  v=String(v==null?"":v).trim().toLowerCase();
  if(k==="phone")return v.replace(/\D/g,"").replace(/^1(?=\d{10}$)/,"");
  if(k==="linkedin"||k==="portfolio")return v.replace(/^https?:\/\//,"").replace(/^www\./,"").replace(/\/+$/,"");
  return v.replace(/\s+/g," ");
}

function apply(w){
  var d=w.document,box0=d.getElementById("aResF");
  if(!box0)throw new Error("needs the Bottom navigation experiment");
  var PX=!!w.__uaplyExtRead;   /* the Application profile is on: its fields are the visible ones */
  var st=d.createElement("style");st.textContent=CSS;d.head.appendChild(st);

  /* each answer from the server, the field it goes in, and the twin field Bottom navigation keeps when the Application profile hides it */
  var MAP=[
    {k:"name",label:"Full name",id:"pName",sample:true},
    {k:"email",label:"Email",id:"pEmail"},
    {k:"phone",label:"Phone",id:PX?"px-phone":"pPhone",twin:PX?"pPhone":""},
    {k:"headline",label:"Headline",id:"px-headline"},
    /* the target title drives which jobs show (Hide roles that do not match my target titles). A student's latest job is often a
       part-time one ("Barista and Shift Lead"), not what they want next: it becomes the target title only for someone who has
       graduated, or when it is an internship or co-op */
    {k:"job_title",label:"Current or target title",id:"pTitle",sample:true,when:function(v,F){return !student(F)||/\b(intern|internship|co-?op)\b/i.test(v)}},
    {k:"job_title",label:"Your job title there",id:"px-job_title"},
    {k:"job_start",label:"Started",id:"px-job_start",show:month,when:ym},
    {k:"job_end",label:"Ended",id:"px-job_end",show:month,when:ym},
    {k:"summary",label:"Summary",id:PX?"px-summary":"aSummary",twin:PX?"aSummary":""},
    {k:"linkedin",label:"LinkedIn",id:PX?"px-linkedin":"aLinked",twin:PX?"aLinked":""},
    {k:"portfolio",label:"Portfolio or GitHub",id:PX?"px-portfolio":"aSite",twin:PX?"aSite":""},
    {k:"school",label:"School",id:"px-school"},
    {k:"major",label:"Major",id:"px-major"},
    {k:"grad",label:"Graduation",id:"px-grad",show:month,when:ym},   /* a year alone ("2019") fills nothing: no month is made up */
    {k:"gpa",label:"GPA",id:"px-gpa"},
    {k:"employer",label:"Most recent employer",id:"px-employer"},
    {k:"skills",label:"Skills",id:"pSkills",sample:true},
    {k:"city",label:"City",id:"pLoc",from:"location",sample:true},
    {k:"state",label:"State",id:"adState",from:"location"},
    {k:"zip",label:"ZIP code",id:"adZip",from:"location"}
  ];

  var box=d.createElement("div");box.className="rsBox";box.id="rsBox";
  box.innerHTML='<h4>Fill from your resume</h4>'+
    '<p>Choose your resume and UAply fills in the empty parts of your profile from it. You check every answer before you apply.</p>'+
    '<div class="rsActs"><button type="button" class="btn" id="rsChoose">Choose your resume</button>'+
    '<input type="file" class="rsPick" id="rsFile" tabindex="-1" aria-hidden="true" accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain">'+
    '<button type="button" class="linkbtn" id="rsSaved" hidden></button></div>'+
    '<p><small>PDF, Word (.docx) or text, up to 1 MB. Kept on this device and sent with each application UAply delivers. The file is read on UAply\'s server for a moment and not kept there.</small></p>'+
    '<p id="rsMsg" role="status" aria-live="polite"></p><div id="rsOut"></div>';
  box0.insertBefore(box,box0.firstChild);
  var pick0=d.getElementById("resPick");if(pick0)pick0.hidden=true;   /* one resume picker on the step: this box's */
  var input=d.getElementById("rsFile"),choose=d.getElementById("rsChoose"),savedBtn=d.getElementById("rsSaved"),msgEl=d.getElementById("rsMsg"),out=d.getElementById("rsOut");
  var last=null;   /* the last answer, so Replace can use it */

  function say(t,bad){msgEl.textContent=t||"";msgEl.className=bad?"bad":""}
  function busy(on){choose.disabled=on;savedBtn.disabled=on;box.setAttribute("aria-busy",on?"true":"false")}
  function stored(){try{return w.__uaplyResume?w.__uaplyResume():null}catch(e){return null}}
  function paintSaved(){
    var r=stored();
    savedBtn.hidden=!r;
    if(r)savedBtn.textContent="Or read the resume you already added ("+r.name+")";
  }
  /* the example profile (Jordan Lee) is not something the person typed: its fields count as empty */
  function custom(){try{return !!w.__uaply.S.profile.custom}catch(e){return true}}
  function el(id){return id?d.getElementById(id):null}
  function cur(m){var e=el(m.id);if(!e)return null;if(m.sample&&!custom())return "";return String(e.value||"").trim()}
  var filling=false;
  function setVal(id,v,mark){
    var e=el(id);if(!e)return false;
    if(e.tagName==="SELECT"&&![].some.call(e.options,function(o){return o.value===v}))return false;
    filling=true;
    try{e.value=v;e.dispatchEvent(new w.Event("input",{bubbles:true}));e.dispatchEvent(new w.Event("change",{bubbles:true}))}finally{filling=false}
    if(mark)e.classList.add("rsFilled");
    return true;
  }
  /* the outline marks what came from the resume until the person changes it */
  d.addEventListener("input",function(e){if(!filling&&e.target&&e.target.classList)e.target.classList.remove("rsFilled")},true);

  function valueOf(m,F){
    var f=F[m.from||m.k];if(!f)return null;
    var v=m.from?f[m.k]:f.value;
    if(m.k==="skills")v=(v||[]).slice(0,20);
    if(m.k==="state"&&v&&!/^[A-Z]{2}$/.test(v))return null;
    return v===""||v==null||(Array.isArray(v)&&!v.length)?null:{v:v,f:f};
  }
  function skillList(s){return String(s||"").split(",").map(function(x){return x.trim()}).filter(Boolean)}

  /* fill what is empty; say what differs */
  function fill(F){
    var rows=[],filled=0,differ=0;
    MAP.forEach(function(m){
      var got=valueOf(m,F);if(!got)return;
      if(m.when&&!m.when(got.v,F))return;
      var now=cur(m);if(now===null)return;   /* no place for it in this build of the profile */
      var row={m:m,v:got.v,f:got.f,state:""};
      if(m.k==="skills"){
        var have=custom()?skillList(el(m.id).value):[],low=have.map(function(x){return x.toLowerCase()});
        var add=got.v.filter(function(x){return low.indexOf(x.toLowerCase())<0});
        if(!have.length){setVal(m.id,got.v.join(", "),true);row.state="filled";filled++}
        else if(add.length){row.state="add";row.add=add;differ++}
        else row.state="same";
      }else{
        var v=m.k==="gpa"?String(got.v):got.v;
        if(!now){if(setVal(m.id,v,true)){row.state="filled";filled++;if(m.twin&&!cur({id:m.twin}))setVal(m.twin,v,false)}else return}
        else if(norm(m.k,now)===norm(m.k,v))row.state="same";
        else{row.state="differ";row.now=now;differ++}
      }
      rows.push(row);
    });
    return {rows:rows,filled:filled,differ:differ};
  }

  function paint(res,F,file){
    var job=F.job_start||F.job_end?{t:(F.job_title||{}).value,e:(F.employer||{}).value,a:(F.job_start||{}).value,b:(F.job_end||{}).value,line:(F.job_start||F.job_end).line}:null;
    var h="";
    if(res.filled)h+='<p style="margin:0"><b>We filled '+res.filled+' field'+(res.filled===1?"":"s")+' from your resume. Check them before you apply.</b> They are outlined in your profile. Save each step to keep them.</p>';
    else if(res.differ)h+='<p style="margin:0"><b>Your profile already has answers for everything we found.</b> Where your resume says something different, tap Replace to use it.</p>';
    else if(res.rows.length)h+='<p style="margin:0"><b>Your profile already matches your resume.</b> Nothing needed changing.</p>';
    else h+='<p style="margin:0"><b>We read your resume but found nothing we could fill in.</b> Type your details in the steps of Profile setup instead.</p>';
    if(res.rows.length){
      h+='<ul class="rsList" aria-label="What we found in your resume">'+res.rows.map(function(r,i){
        var m=r.m,shown=m.k==="skills"?(r.state==="add"?r.add:r.v).join(", "):(m.show?m.show(r.v):r.v);
        var stt=r.state==="filled"?'<span class="st ok">Filled in</span>':r.state==="same"?'<span class="st">Already in your profile</span>':
          r.state==="add"?'<span class="st">Not in your skills yet</span><button type="button" data-rs="'+i+'">Add them</button>':
          '<span class="st">You typed: '+esc(m.show?m.show(r.now):r.now)+'</span><button type="button" data-rs="'+i+'">Replace</button>';
        var lines=r.f.lines&&r.f.lines.length>1?r.f.lines.slice(0,3):[r.f.line];
        return '<li><span class="k">'+esc(m.label)+'</span><span class="v">'+esc(shown)+'</span>'+(r.f.confidence==="low"?'<span class="chk">Check this</span>':'')+stt+
          '<span class="src">From your resume: '+lines.map(function(l){return '<q>'+esc(l)+'</q>'}).join(" ")+'</span></li>';
      }).join("")+'</ul>';
    }
    if(job)h+='<p style="margin:0;font-size:14px;color:var(--muted)">Most recent job in your resume: '+esc([job.t,job.e].filter(Boolean).join(" at "))+(job.a?" ("+esc(when(job.a))+(job.b?" to "+esc(when(job.b)):"")+")":"")+'.</p>';
    h+='<p id="rsKeep" style="margin:0;font-size:14px;color:var(--muted)"></p>';
    out.innerHTML=h;
    keep(file);
  }

  /* keep the same file as the resume sent with applications, in Bottom navigation's resume store (one picker, one store): the
     resume you choose here is your resume, so it also replaces an older file */
  function keep(file){
    var k=d.getElementById("rsKeep");if(!k||!file||!file.blob)return;
    var have=stored();
    if(have&&have.name===file.name&&have.size===file.size){k.textContent="This is also the resume file sent with your applications.";return}
    if(typeof w.__uaplySetResumeFile!=="function")return;
    w.__uaplySetResumeFile(file.blob,function(ok){
      paintSaved();
      k.textContent=!ok?"Your resume was read, but this browser could not keep the file for applications.":
        have?"Your applications now send "+file.name+" instead of "+have.name+".":"We also added it as the resume file sent with your applications.";
    });
  }

  out.addEventListener("click",function(e){
    var b=e.target.closest("button[data-rs]");if(!b||!last)return;
    var r=last.rows[+b.getAttribute("data-rs")];if(!r)return;
    if(r.m.k==="skills"){var have=skillList(el(r.m.id).value);setVal(r.m.id,have.concat(r.add).join(", "),true);r.state="filled"}
    else{setVal(r.m.id,r.m.k==="gpa"?String(r.v):r.v,true);r.state="filled"}
    var li=b.closest("li"),s=li.querySelector(".st");if(s){s.className="st ok";s.textContent=r.m.k==="skills"?"Added":"Replaced"}b.remove();
  });

  /* the server reads the file for a moment (POST /api/profile/resume) and answers with the fields it found: cb(error sentence, fields) */
  function parse(name,dataUrl,cb){
    w.fetch("/api/profile/resume",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({resume:{name:name,data:dataUrl}})})
      .then(function(r){
        return r.json().then(function(j){return {ok:r.ok,j:j}},function(){return {ok:false,j:{error:r.status===404?"Reading a resume needs UAply's server, and this copy of the app has none. Type your details instead.":"UAply's server had a problem reading your resume. Try again in a moment."}}});
      })
      .then(function(x){
        if(!x.ok||!x.j||!x.j.fields){cb((x.j&&x.j.error)||"We could not read that file. Try again.");return}
        cb(null,x.j.fields);
      },function(){cb("We could not reach UAply to read your resume. Check your connection and try again.")});
  }
  function send(name,dataUrl,file){
    busy(true);say("Reading your resume…");out.innerHTML="";
    parse(name,dataUrl,function(err,F){
      busy(false);
      if(err){say(err,true);return}
      say("");
      var res=fill(F);last=res;paint(res,F,file);
      if(box.scrollIntoView)box.scrollIntoView({block:"nearest",behavior:"smooth"});
    });
  }
  /* the plain sentence for a file UAply cannot take, or "" (the box here, the first-run question and the swipe-right sheet) */
  function fileProblem(f){
    if(!OK_EXT.test(f.name))return /\.doc$/i.test(f.name)?"That is an older Word file (.doc). Open it in Word, save it as .docx or PDF, and try again.":/\.(png|jpe?g|heic|gif|webp)$/i.test(f.name)?"That is a picture, not a document. Use the PDF or Word file of your resume instead.":"Use a PDF, a Word file (.docx) or a text file (.txt).";
    if(f.size>MAX)return "That file is over 1 MB. Save your resume as a smaller PDF or Word file and try again.";
    if(!f.size)return "That file is empty. Choose the file of your resume and try again.";
    return "";
  }

  choose.addEventListener("click",function(){input.click()});
  input.addEventListener("change",function(){
    var f=input.files&&input.files[0];input.value="";if(!f)return;
    var bad=fileProblem(f);if(bad){say(bad,true);return}
    var rd=new w.FileReader();
    rd.onload=function(){send(f.name,String(rd.result||""),{name:f.name.slice(0,120),size:f.size,blob:f})};
    rd.onerror=function(){say("We could not open that file. Choose it again.",true)};
    rd.readAsDataURL(f);
  });
  savedBtn.addEventListener("click",function(){var r=stored();if(r)send(r.name,r.data,null)});
  var base=w.__uaplySyncPrefs;w.__uaplySyncPrefs=function(){if(base)base();paintSaved()};
  paintSaved();

  /* ---------- the kit: the same reading, field map and stores for the first-run question (uaply-signup.js) and the swipe-right
     sheet (uaply-live.js). It writes straight to where Profile setup keeps each field (the profile, the account, the Application
     profile's answers) and sets the Profile setup box too, so a later save of a step keeps the same answer. Only what the resume
     literally says, only into a field that is empty, and only what the person kept in the "Check these" card. ---------- */
  var KCSS=".rkZone{border:2px dashed var(--line);border-radius:16px;padding:16px;display:flex;flex-direction:column;gap:10px;align-items:flex-start;background:var(--surface)}"+
    ".rkZone.over{border-color:var(--accent);background:var(--bg)}.rkZone .btn,.rkActs .btn,.rkActs .linkbtn{min-height:44px}"+
    ".rkMsg{margin:0;font-size:14px;font-weight:600}.rkMsg.bad{color:var(--no)}.rkMsg:empty{display:none}"+
    ".rkActs{display:flex;flex-wrap:wrap;gap:8px;align-items:center}"+
    ".rkCheck{display:flex;flex-direction:column;gap:10px}.rkCheck h3{margin:0;font:800 18px var(--display)}.rkCheck>p{margin:0;color:var(--muted);font-size:14px}"+
    ".rkF{display:flex;flex-direction:column;gap:3px}.rkF label{font-weight:700;font-size:14px}.rkF input{min-height:44px;font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink)}"+
    ".rkF small{font-size:13px;color:var(--muted);overflow-wrap:anywhere}.rkF .chk{color:var(--no);font-weight:700}.rkF .err{color:var(--no);font-weight:600}"+
    ".rkCheck details summary{min-height:44px;display:flex;align-items:center;cursor:pointer;font-weight:700}"+
    ".rkSheetBg{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9000;display:flex;align-items:flex-end;justify-content:center}"+
    ".rkSheet{background:var(--bg);color:var(--ink);width:100%;max-width:560px;max-height:88vh;overflow:auto;border-radius:20px 20px 0 0;padding:18px 16px 22px;display:flex;flex-direction:column;gap:12px}"+
    ".rkSheet h2{margin:0;font:800 20px var(--display)}.rkSheet>p{margin:0;color:var(--muted)}";
  var kst=d.createElement("style");kst.textContent=KCSS;d.head.appendChild(kst);
  var CORE=["name","email","phone","city","state","zip","job_title"];
  var LABEL={name:"Full name",email:"Email",phone:"Phone",city:"City",state:"State",zip:"ZIP code",job_title:"Job title"};
  function A_(){return w.__uaply}
  function prof(){try{return A_().S.profile||{}}catch(e){return {}}}
  function extNow(){try{return w.__uaplyApplyExt?w.__uaplyApplyExt():{}}catch(e){return {}}}
  function acctDo(fn){var B=w.__uaplyAuthApi;if(B&&B.acct)B.acct(fn)}
  function freshDefault(){
    var a=A_(),p=a.S.profile||{};if(p.custom)return p;
    a.S.profile={name:"",title:"",years:0,edu:p.edu,skills:[],salary:0,loc:"",modes:{remote:false,hybrid:false,onsite:false},reloc:false,email:"",custom:true};
    return a.S.profile;
  }
  /* what this field holds now, wherever Profile setup keeps it ("" = empty; the example profile counts as empty) */
  function stored_(m){
    var p=prof(),c=!!p.custom,x=extNow(),id=m.id;
    if(id==="pName")return c?p.name||"":"";
    if(id==="pEmail")return c?p.email||"":"";
    if(id==="pTitle")return c?p.title||"":"";
    if(id==="pSkills")return c&&p.skills&&p.skills.length?p.skills.join(", "):"";
    if(id==="pLoc")return c?p.loc||"":"";
    if(id==="adState")return x.state||"";
    if(id==="adZip")return x.zip||"";
    if(m.k==="phone")return x.phone||"";
    if(id==="aSummary")return x.summary||"";
    if(id==="aLinked")return x.linkedin||"";
    if(id==="aSite")return x.portfolio||"";
    if(id.indexOf("px-")===0)return String((p.ext||{})[id.slice(3)]||"");
    return "";
  }
  function has(m){return !!String(stored_(m)||"").trim()||!!cur(m)}
  /* the writes Profile setup's save would make, for one field */
  function put(m,v){
    var id=m.id,a=A_(),p=prof();
    if(id==="pName"||id==="pEmail"||id==="pTitle"||id==="pLoc"||id==="pSkills"||id.indexOf("px-")===0){
      p=a.S.profile;
      if(id==="pName")p.name=v;else if(id==="pEmail")p.email=v;else if(id==="pTitle")p.title=v;else if(id==="pLoc")p.loc=v;
      else if(id==="pSkills")p.skills=skillList(v).slice(0,20);
      else{p.ext=(p.ext&&typeof p.ext==="object")?p.ext:{};p.ext[id.slice(3)]=v}
      a.save();
    }
    if(id==="adState"||id==="adZip")acctDo(function(ac){var ad=(ac.addr&&typeof ac.addr==="object")?ac.addr:{street:"",unit:"",state:"",zip:""};ad=Object.assign({street:"",unit:"",state:"",zip:""},ad);ad[id==="adZip"?"zip":"state"]=v;ac.addr=ad});
    if(m.k==="phone")acctDo(function(ac){ac.phone=v});
    if(id==="aSummary")acctDo(function(ac){ac.summary=v});
    if(id==="aLinked")acctDo(function(ac){ac.linkedin=v});
    if(id==="aSite")acctDo(function(ac){ac.portfolio=v});
    setVal(id,v,false);if(m.twin)setVal(m.twin,v,false);
  }
  /* a phone number UAply can pass on: US (10 digits, or 11 starting with 1) or international (+ and 8 to 15 digits) */
  function phoneOk(v){
    v=String(v||"").trim();if(!/^[+()\d\s.-]{7,25}$/.test(v))return false;
    var n=v.replace(/\D/g,"");
    return v.charAt(0)==="+"?n.length>=8&&n.length<=15:(n.length===10||(n.length===11&&n.charAt(0)==="1"));
  }
  function phoneMap(){for(var i=0;i<MAP.length;i++)if(MAP[i].k==="phone")return MAP[i]}
  function savePhone(v){put(phoneMap(),String(v).trim())}
  function zipOk(v){return /^\d{5}(-\d{4})?$/.test(v)}
  function stateOk(v){var s=el("adState");return !!s&&[].some.call(s.options,function(o){return o.value&&o.value===v})}
  /* one row per answer found and still empty in the profile (the title twins become one row) */
  function rowsFor(F){
    var by={},rows=[];
    MAP.forEach(function(m){
      if(!el(m.id)&&!/^(pName|pEmail|pTitle|pSkills|pLoc|adState|adZip)$/.test(m.id))return;
      var got=valueOf(m,F);if(!got)return;
      if(m.when===ym&&!ym(String(got.v)))return;   /* a date the month input cannot hold (a year alone) is not offered */
      if(has(m))return;
      var r=by[m.k];
      if(!r){r=by[m.k]={k:m.k,label:LABEL[m.k]||m.label,v:m.k==="skills"?got.v.join(", "):String(got.v),f:got.f,ms:[],core:CORE.indexOf(m.k)>-1};rows.push(r)}
      r.ms.push(m);
    });
    rows.sort(function(a,b){var i=CORE.indexOf(a.k),j=CORE.indexOf(b.k);return (i<0?99:i)-(j<0?99:j)});
    return rows;
  }
  function readFile(f,cb){var rd=new w.FileReader();rd.onload=function(){cb(null,String(rd.result||""))};rd.onerror=function(){cb("We could not open that file. Choose it again.")};rd.readAsDataURL(f)}
  var uid=0;
  /* mount(host,{onDone(info),onSkip,skipLabel,fresh}): pick or drop the file, read it, check the answers, save. info={saved:[keys],title,file} */
  function mount(host,o){
    o=o||{};var n=++uid,file=null,rows=[],lastF=null;
    host.innerHTML='<div class="rkZone" id="rkZone'+n+'"><div class="rkActs"><button type="button" class="btn" data-rk="pick">Choose your resume</button>'+
      '<span class="rkDrop" style="font-size:14px;color:var(--muted)">or drop the file here</span></div>'+
      '<input type="file" class="rsPick" tabindex="-1" aria-hidden="true" accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain">'+
      '<p class="rkMsg" role="status" aria-live="polite"></p><div class="rkActs" data-rk="after"></div></div><div class="rkOut"></div>';
    var zone=host.querySelector(".rkZone"),inp=host.querySelector("input[type=file]"),msg=host.querySelector(".rkMsg"),after=host.querySelector("[data-rk=after]"),outK=host.querySelector(".rkOut"),pickB=host.querySelector("[data-rk=pick]");
    function sayK(t,bad){msg.textContent=t||"";msg.className="rkMsg"+(bad?" bad":"")}
    function acts(list){after.innerHTML=list.map(function(x){return '<button type="button" class="'+(x[2]||"btn ghost")+'" data-rk="'+x[0]+'">'+esc(x[1])+'</button>'}).join("")}
    function failed(t,useAnyway){
      zone.removeAttribute("aria-busy");pickB.disabled=false;sayK(t,true);
      var l=[["again","Try another file"]];if(useAnyway)l.push(["anyway","Send this file without filling anything"]);if(o.onSkip)l.push(["skip",o.skipLabel||"Continue without"]);acts(l);
      var b=after.querySelector("button");if(b)b.focus();
    }
    function keepFile(cb){
      if(!file||typeof w.__uaplySetResumeFile!=="function"){cb(false);return}
      var have=stored();if(have&&have.name===file.name&&have.size===file.size){cb(true);return}
      w.__uaplySetResumeFile(file.blob,function(ok){paintSaved();cb(!!ok)});
    }
    function take(f){
      if(!f)return;outK.innerHTML="";acts([]);
      var bad=fileProblem(f);if(bad){failed(bad,false);return}
      file={name:f.name.slice(0,120),size:f.size,blob:f};
      pickB.disabled=true;zone.setAttribute("aria-busy","true");sayK("Reading your resume…");
      readFile(f,function(err,data){
        if(err){failed(err,false);return}
        parse(f.name,data,function(err2,F){
          if(err2){failed(err2+" You can still send the file itself with your applications.",true);return}
          zone.removeAttribute("aria-busy");pickB.disabled=false;sayK("");
          (o.fresh||freshDefault)();
          rows=rowsFor(F);lastF=F;check();
        });
      });
    }
    function fieldHTML(r,i){
      var src=r.f.line?'<small>From your resume: <q>'+esc(r.f.line)+'</q></small>':'';
      var low=r.f.confidence==="low"?' <span class="chk">Check this</span>':'';
      var t=r.k==="phone"?"tel":r.k==="email"?"email":"text";
      return '<div class="rkF"><label for="rk'+n+'-'+i+'">'+esc(r.label)+low+'</label><input id="rk'+n+'-'+i+'" type="'+t+'" data-i="'+i+'" value="'+esc(r.v)+'">'+src+'<small class="err" role="alert"></small></div>';
    }
    function check(){
      var core=rows.filter(function(r){return r.core}),more=rows.filter(function(r){return !r.core});
      var h='<form class="rkCheck" novalidate><h3 tabindex="-1">Check these</h3>';
      if(rows.length)h+='<p>We found these in your resume. Change anything that is wrong, or clear a box to leave it out.</p>'+
        core.map(function(r){return fieldHTML(r,rows.indexOf(r))}).join("")+
        (more.length?'<details><summary>More from your resume ('+more.length+')</summary>'+more.map(function(r){return fieldHTML(r,rows.indexOf(r))}).join("")+'</details>':'');
      else h+='<p>We read your resume. Everything we found is already in your profile, or there was nothing we could fill in.</p>';
      h+='<div class="rkActs"><button type="submit" class="btn">'+esc(o.saveLabel||"Save and continue")+'</button><button type="button" class="btn ghost" data-rk="again">Try another file</button></div></form>';
      outK.innerHTML=h;zone.hidden=true;
      var hd=outK.querySelector("h3");if(hd)hd.focus();
    }
    function save(form){
      var ok=true,saved=[],title="";
      [].forEach.call(form.querySelectorAll("input[data-i]"),function(inp2){
        var r=rows[+inp2.getAttribute("data-i")],v=inp2.value.trim(),er=inp2.parentNode.querySelector(".err");er.textContent="";
        if(!v)return;
        var bad=r.k==="phone"&&!phoneOk(v)?"Enter a US number (10 digits) or an international one starting with +.":r.k==="zip"&&!zipOk(v)?"Enter a 5-digit ZIP code.":r.k==="state"&&!stateOk(v)?"Use the 2-letter state code, like PA.":r.k==="email"&&!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)?"That email does not look right.":"";
        if(bad){er.textContent=bad;if(ok)inp2.focus();ok=false;return}
        r.out=v;
      });
      if(!ok)return;
      rows.forEach(function(r){
        if(!r.out)return;var did=false;
        r.ms.forEach(function(m){
          if(has(m))return;   /* typed meanwhile: never replaced */
          if(m.when&&!m.when(r.out,lastF||{}))return;
          if((m.k==="job_start"||m.k==="job_end"||m.k==="grad")&&!ym(r.out))return;
          put(m,r.out);did=true;if(m.id==="pTitle")title=r.out;
        });
        if(did)saved.push(r.k);
      });
      keepFile(function(kept){if(o.onDone)o.onDone({saved:saved,title:title,file:kept?file.name:""})});
    }
    host.addEventListener("click",function(e){
      var b=e.target.closest("[data-rk]");if(!b||b.tagName==="DIV")return;
      var k=b.getAttribute("data-rk");
      if(k==="pick")inp.click();
      else if(k==="again"){outK.innerHTML="";zone.hidden=false;acts([]);sayK("");inp.click();pickB.focus()}
      else if(k==="skip"&&o.onSkip)o.onSkip();
      else if(k==="anyway")keepFile(function(kept){if(o.onDone)o.onDone({saved:[],title:"",file:kept?file.name:""})});
    });
    host.addEventListener("submit",function(e){e.preventDefault();save(e.target)});
    inp.addEventListener("change",function(){var f=inp.files&&inp.files[0];inp.value="";take(f)});
    zone.addEventListener("dragover",function(e){e.preventDefault();zone.classList.add("over")});
    zone.addEventListener("dragleave",function(){zone.classList.remove("over")});
    zone.addEventListener("drop",function(e){e.preventDefault();zone.classList.remove("over");var f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];take(f)});
    return {take:take};
  }
  w.__uaplyResumeKit={mount:mount,phoneOk:phoneOk,savePhone:savePhone,fileProblem:fileProblem,parse:parse,
    hasPhone:function(){return has(phoneMap())},hasName:function(){return has(MAP[0])}};

  /* ---------- swipe right without enough to send (October 30: never send nothing). The sheet offers the resume (read and checked
     as above) or a phone number; done(true) sends THAT application through the normal path, done(false) keeps "Needs profile". ---------- */
  w.__uaplyAddToSend=function(job,done){
    if(d.getElementById("rkSheetBg")){done(false);return}   /* one sheet at a time: a second ask while one is open keeps that job as "Needs profile" */
    var prev=d.activeElement,bg=d.createElement("div"),closed=false;bg.className="rkSheetBg";bg.id="rkSheetBg";
    var needName=!has(MAP[0]);
    bg.innerHTML='<div class="rkSheet" role="dialog" aria-modal="true" aria-labelledby="rkSh"><h2 id="rkSh" tabindex="-1">Add your resume to send this</h2>'+
      '<p>'+esc(job.co||"This employer")+' needs a way to reach you. Add your resume, or a phone number, and '+(job.contact||job.instant?'we send this application now':'we save it to Job Tracker, where a link opens the employer\'s own page to finish')+'.</p>'+
      '<div class="rkUp"></div>'+
      '<div class="rkActs"><button type="button" class="btn ghost" data-sh="phone">Add a phone number instead</button><button type="button" class="linkbtn" data-sh="no">Not now</button></div>'+
      '<form class="rkPh rkCheck" hidden novalidate><h3 tabindex="-1">Add a phone number</h3>'+
      (needName?'<div class="rkF"><label for="rkShName">Full name</label><input id="rkShName" autocomplete="name"><small class="err" role="alert"></small></div>':'')+
      '<div class="rkF"><label for="rkShPh">Phone</label><input id="rkShPh" type="tel" autocomplete="tel" placeholder="(215) 555-0100 or +44 20 7946 0000"><small class="err" role="alert"></small></div>'+
      '<div class="rkActs"><button type="submit" class="btn">Save and send</button></div></form></div>';
    d.body.appendChild(bg);
    function close(sent){if(closed)return;closed=true;bg.remove();d.removeEventListener("keydown",esc_,true);try{if(prev&&prev.focus)prev.focus()}catch(e){}done(!!sent)}
    function esc_(e){if(e.key==="Escape"){e.preventDefault();close(false)}}
    d.addEventListener("keydown",esc_,true);
    mount(bg.querySelector(".rkUp"),{saveLabel:"Save and send",onDone:function(){close(true)}});
    bg.addEventListener("click",function(e){
      if(e.target===bg){close(false);return}
      var b=e.target.closest("[data-sh]");if(!b)return;
      if(b.getAttribute("data-sh")==="no")close(false);
      else{var f=bg.querySelector(".rkPh");f.hidden=false;b.hidden=true;(f.querySelector("input")).focus()}
    });
    bg.querySelector(".rkPh").addEventListener("submit",function(e){
      e.preventDefault();
      var ph=d.getElementById("rkShPh"),nm=d.getElementById("rkShName"),ok=true;
      [].forEach.call(e.target.querySelectorAll(".err"),function(x){x.textContent=""});
      if(nm&&!nm.value.trim()){nm.parentNode.querySelector(".err").textContent="Add your name so the employer knows who applied.";nm.focus();ok=false}
      if(!phoneOk(ph.value)){ph.parentNode.querySelector(".err").textContent="Enter a US number (10 digits) or an international one starting with +.";if(ok)ph.focus();ok=false}
      if(!ok)return;
      if(nm){freshDefault();put(MAP[0],nm.value.trim())}
      savePhone(ph.value);close(true);
    });
    bg.querySelector("#rkSh").focus();
  };
}

window.UAplyResume={apply:apply};
})();
