/* "resume" experiment (sandbox first): Fill from your resume.
   Adds a box at the top of Profile setup, Background and links (the step with the resume file). The person chooses their resume (PDF, Word
   .docx or text, up to 5 MB); the server reads it for a moment (resume_parse.py, POST /api/profile/resume, nothing is kept) and answers
   with the fields it found. This file then fills every EMPTY profile field with them. A field the person already typed is never changed:
   when the resume says something different, the list offers Replace for that field. The list shows each answer with the line of the
   resume it came from, so the person can check it before applying. Nothing is saved until the person saves the step, as with typing.
   The same file is also kept as the resume that goes with applications, through the resume file box Bottom navigation already has (one
   store, on this device), unless a different resume file is already there; then the list offers to use this one instead.
   Needs Bottom navigation; uses the Application profile's fields when that experiment is on. Registered in uaply-envs.js as "resume". */
(function(){
"use strict";
var MAX=5*1024*1024,OK_EXT=/\.(pdf|docx|txt)$/i;
var MON=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

var CSS=".rsBox{border:1px dashed var(--accent);border-radius:16px;padding:14px;display:flex;flex-direction:column;gap:8px;margin-bottom:14px;background:var(--surface)}"+
".rsBox h4{margin:0;font:800 16px var(--display)}.rsBox>p{margin:0;color:var(--muted);font-size:13.5px}"+
".rsActs{display:flex;flex-wrap:wrap;gap:8px;align-items:center;position:relative}.rsActs .btn{min-height:44px}.rsActs .linkbtn{font-size:13.5px;min-height:44px;text-align:left}"+
".rsPick{position:absolute;left:0;top:0;width:1px;height:1px;opacity:0;pointer-events:none;overflow:hidden}"+
"#rsMsg{margin:0;font-size:14px;font-weight:600}#rsMsg.bad{color:var(--no)}#rsMsg:empty{display:none}"+
".rsList{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}"+
".rsList li{border:1px solid var(--line);border-radius:12px;padding:9px 11px;display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center;background:var(--bg)}"+
".rsList .k{font-size:12px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.03em;flex:1 1 100%}"+
".rsList .v{flex:1 1 180px;min-width:0;overflow-wrap:anywhere;font-weight:600}"+
".rsList .st{font-size:12.5px;color:var(--muted)}.rsList .st.ok{color:var(--yes)}"+
".rsList .src{flex:1 1 100%;font-size:12px;color:var(--muted);overflow-wrap:anywhere}.rsList .src q{font-style:italic}"+
".rsList .chk{font-size:11.5px;font-weight:700;color:var(--no);border:1px solid currentColor;border-radius:99px;padding:1px 7px}"+
".rsList button{min-height:36px;border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:5px 12px;font-weight:600;font-size:13px;color:var(--ink)}"+
".rsFilled{outline:2px solid var(--accent);outline-offset:1px}";

function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
function month(v){var m=/^(\d{4})-(\d{2})$/.exec(v||"");return m?MON[+m[2]-1]+" "+m[1]:v}
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
    {k:"job_title",label:"Current or target title",id:"pTitle",sample:true},
    {k:"summary",label:"About you",id:PX?"px-summary":"aSummary",twin:PX?"aSummary":""},
    {k:"linkedin",label:"LinkedIn",id:PX?"px-linkedin":"aLinked",twin:PX?"aLinked":""},
    {k:"portfolio",label:"Portfolio or GitHub",id:PX?"px-portfolio":"aSite",twin:PX?"aSite":""},
    {k:"school",label:"School",id:"px-school"},
    {k:"major",label:"Major",id:"px-major"},
    {k:"grad",label:"Graduation",id:"px-grad",show:month},
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
    '<p><small>PDF, Word (.docx) or text, up to 5 MB. The file is read on UAply\'s server for a moment and not kept there.</small></p>'+
    '<p id="rsMsg" role="status" aria-live="polite"></p><div id="rsOut"></div>';
  box0.insertBefore(box,box0.firstChild);
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
    if(job)h+='<p style="margin:0;font-size:13px;color:var(--muted)">Most recent job in your resume: '+esc([job.t,job.e].filter(Boolean).join(" at "))+(job.a?" ("+esc(when(job.a))+(job.b?" to "+esc(when(job.b)):"")+")":"")+'.</p>';
    h+='<p id="rsKeep" style="margin:0;font-size:13px;color:var(--muted)"></p>';
    out.innerHTML=h;
    keep(file);
  }

  /* keep the same file as the resume sent with applications, through Bottom navigation's resume file box (the one store) */
  function keep(file){
    var k=d.getElementById("rsKeep");if(!k||!file||!file.blob)return;
    var have=stored(),pick=d.getElementById("pResFile");
    if(have&&have.name===file.name&&have.size===file.size){k.textContent="This is also the resume file sent with your applications.";return}
    if(file.size>1048576){k.textContent="Your resume is over 1 MB, so it was read but not kept for applications. Save a smaller PDF and add it under Resume below.";return}
    if(!pick||typeof w.DataTransfer!=="function"){k.textContent="To send this file with your applications, add it under Resume below.";return}
    function put(){
      try{var dt=new w.DataTransfer();dt.items.add(new w.File([file.blob],file.name,{type:file.blob.type||""}));pick.files=dt.files}catch(e){k.textContent="To send this file with your applications, add it under Resume below.";return false}
      pick.dispatchEvent(new w.Event("change",{bubbles:true}));
      setTimeout(paintSaved,300);
      return true;
    }
    if(!have){if(put())k.textContent="We also added it as the resume file sent with your applications.";return}
    k.innerHTML='Your applications send '+esc(have.name)+'. <button type="button" class="linkbtn" id="rsUse">Send this resume instead</button>';
    d.getElementById("rsUse").onclick=function(){if(put())k.textContent="Done: your applications now send "+file.name+"."};
  }

  out.addEventListener("click",function(e){
    var b=e.target.closest("button[data-rs]");if(!b||!last)return;
    var r=last.rows[+b.getAttribute("data-rs")];if(!r)return;
    if(r.m.k==="skills"){var have=skillList(el(r.m.id).value);setVal(r.m.id,have.concat(r.add).join(", "),true);r.state="filled"}
    else{setVal(r.m.id,r.m.k==="gpa"?String(r.v):r.v,true);r.state="filled"}
    var li=b.closest("li"),s=li.querySelector(".st");if(s){s.className="st ok";s.textContent=r.m.k==="skills"?"Added":"Replaced"}b.remove();
  });

  function send(name,dataUrl,file){
    busy(true);say("Reading your resume…");out.innerHTML="";
    w.fetch("/api/profile/resume",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({resume:{name:name,data:dataUrl}})})
      .then(function(r){
        return r.json().then(function(j){return {ok:r.ok,j:j}},function(){return {ok:false,j:{error:r.status===404?"Reading a resume needs UAply's server, and this copy of the app has none. Type your details instead.":"UAply's server had a problem reading your resume. Try again in a moment."}}});
      })
      .then(function(x){
        busy(false);
        if(!x.ok||!x.j||!x.j.fields){say((x.j&&x.j.error)||"We could not read that file. Try again.",true);return}
        say("");
        var res=fill(x.j.fields);last=res;paint(res,x.j.fields,file);
        if(box.scrollIntoView)box.scrollIntoView({block:"nearest",behavior:"smooth"});
      })
      .catch(function(){busy(false);say("We could not reach UAply to read your resume. Check your connection and try again.",true)});
  }

  choose.addEventListener("click",function(){input.click()});
  input.addEventListener("change",function(){
    var f=input.files&&input.files[0];input.value="";if(!f)return;
    if(!OK_EXT.test(f.name)){say(/\.doc$/i.test(f.name)?"That is an older Word file (.doc). Open it in Word, save it as .docx or PDF, and try again.":/\.(png|jpe?g|heic|gif|webp)$/i.test(f.name)?"That is a picture, not a document. Use the PDF or Word file of your resume instead.":"Use a PDF, a Word file (.docx) or a text file (.txt).",true);return}
    if(f.size>MAX){say("That file is over 5 MB. Save your resume as a smaller PDF or Word file and try again.",true);return}
    if(!f.size){say("That file is empty. Choose the file of your resume and try again.",true);return}
    var rd=new w.FileReader();
    rd.onload=function(){send(f.name,String(rd.result||""),{name:f.name.slice(0,120),size:f.size,blob:f})};
    rd.onerror=function(){say("We could not open that file. Choose it again.",true)};
    rd.readAsDataURL(f);
  });
  savedBtn.addEventListener("click",function(){var r=stored();if(r)send(r.name,r.data,null)});
  var base=w.__uaplySyncPrefs;w.__uaplySyncPrefs=function(){if(base)base();paintSaved()};
  paintSaved();
}

window.UAplyResume={apply:apply};
})();
