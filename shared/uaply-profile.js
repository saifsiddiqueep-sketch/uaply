/* "profile" experiment: an application-ready profile, modeled on what LinkedIn Easy Apply, Indeed Apply,
   ZipRecruiter 1-Click Apply and Handshake collect so a person can apply quickly and completely.
   Adds to Profile setup: phone, headline, resume link, about you, LinkedIn, portfolio, school, major,
   graduation month, GPA (optional), most recent employer with your title and dates there, country, work authorization,
   sponsorship, earliest start, opportunity types and the questions employers' own forms ask (relocation, expected pay...). uaply-nav.js puts each field on its step (STEPS there);
   the group headings below ("sec", "title") only sort the fields and are not shown in the guided setup.
   Shows an "application readiness" score with one-tap links to whatever is missing, validates links and phone,
   and warns when the authorization and sponsorship answers contradict each other.
   This file does not ask for demographic or EEO data (the optional voluntary questions live in uaply-nav.js and are
   never sent). Everything is optional except what an employer needs.
   Fields are listed in SPEC, so adding one is a one-line change. */
(function(){
function once(src,a,b){if(src.indexOf(a)<0)throw new Error("patch target not found: "+a.slice(0,40));return src.replace(a,function(){return b})}

/* the profile object gets an `ext` bag; the app saves and restores it with the rest of the profile */
function patch(s){
  s=once(s,'loc:typeof p.loc==="string"?p.loc:"",','loc:typeof p.loc==="string"?p.loc:"",ext:(p.ext&&typeof p.ext==="object")?p.ext:{},');
  s=once(s,'salary:num($("pSalary").value,0,10000000),loc:$("pLoc").value.trim(),','salary:num($("pSalary").value,0,10000000),loc:$("pLoc").value.trim(),ext:(window.__uaplyExtRead?window.__uaplyExtRead():{}),');
  s=once(s,'$("pSalary").value=p.salary;$("pLoc").value=p.loc;','$("pSalary").value=p.salary;$("pLoc").value=p.loc;if(window.__uaplyExtFill)window.__uaplyExtFill(p.ext||{});');
  return s;
}

var EMAIL=/^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$/;
function urlOk(v){return !v||/^https:\/\/[^\s.]+\.[^\s]+$/i.test(v)?"":"Use a full link that starts with https://"}
function phoneOk(v){return !v||(/^[+()\d\s.-]{7,25}$/.test(v)&&v.replace(/\D/g,"").length>=7)?"":"Enter a phone number with at least 7 digits"}
function gpaOk(v){return v===""||(+v>=0&&+v<=4.5)?"":"GPA is between 0 and 4.5"}
function payOk(v){return v===""||(/^\d{1,8}$/.test(v)&&+v>0&&+v<=10000000)?"":"Enter a yearly amount in whole dollars, like 85000"}

var START=[["","Choose"],["now","Right away"],["2w","Within 2 weeks"],["1m","Within a month"],["grad","After I graduate"],["flex","Flexible"]];
var SPEC=[
 {sec:"settings",title:"Contact",items:[
  {k:"phone",label:"Phone",type:"tel",ph:"(555) 123-4567",hint:"Recruiters call or text this number.",val:phoneOk},
  {k:"headline",label:"Headline",type:"text",ph:"Frontend developer who builds fast, accessible interfaces",max:120}]},
 {sec:"settings",title:"Resume and links",items:[
  {k:"resume",label:"Resume link",type:"url",full:1,ph:"https://drive.google.com/...",hint:"A file that anyone with the link can open. Employers click this.",val:urlOk},
  {k:"summary",label:"About you",type:"textarea",full:1,ph:"Two or three sentences on what you do best and what you want next.",max:600},
  {k:"linkedin",label:"LinkedIn",type:"url",ph:"https://www.linkedin.com/in/...",val:urlOk},
  {k:"portfolio",label:"Portfolio or GitHub",type:"url",ph:"https://github.com/...",val:urlOk}]},
 {sec:"settings",title:"Education and experience",items:[
  {k:"school",label:"School",type:"text",max:100},
  {k:"major",label:"Major",type:"text",max:100},
  {k:"grad",label:"Graduation (month and year)",type:"month"},
  {k:"gpa",label:"GPA (optional)",type:"number",min:0,max:4.5,step:0.01,hint:"Add it only if it helps you.",val:gpaOk},
  {k:"employer",label:"Most recent employer",type:"text",max:100},
  {k:"job_title",label:"Your job title there",type:"text",max:100,ph:"Sales associate"},
  {k:"job_start",label:"Started (month and year)",type:"month"},
  {k:"job_end",label:"Ended (month and year)",type:"month",hint:"Leave it blank if you still work there."}]},
 {sec:"preferences",title:"Eligibility and availability",items:[
  {k:"auth",label:"Work authorization (United States)",type:"select",full:1,opts:[["","Choose"],["citizen","US citizen or permanent resident"],["authorized","Authorized to work (visa, OPT or similar)"],["none","Not currently authorized"]]},
  {k:"sponsor",label:"Will you now or in the future need visa sponsorship?",type:"select",full:1,hint:"Answer this the same way on every application.",opts:[["","Choose"],["no","No"],["yes","Yes"]]},
  {k:"country",label:"Country you live in",type:"select",opts:[["US","United States"],["CA","Canada"],["GB","United Kingdom"],["other","Other"]],hint:"Employers' forms ask for it with your city, state and ZIP code."},
  {k:"start",label:"Earliest start",type:"select",opts:START}]},
 {sec:"preferences",title:"What you are looking for",items:[
  {k:"types",label:"Opportunity types",type:"checks",full:1,opts:[["fulltime","Full-time"],["parttime","Part-time"],["internship","Internship"],["coop","Co-op"]]}]},
 /* the questions most employers' own application forms ask; answered once here, UAply fills them in on every application
    ("Willing to relocate" here and the box under Work style are the same answer: changing one changes the other) */
 {sec:"preferences",title:"Questions employers ask",items:[
  {k:"office",label:"Willing to work from the job's office (hybrid or on-site)?",type:"select",opts:[["","Choose"],["yes","Yes"],["no","No"]]},
  {k:"relocate",label:"Willing to relocate for the right job?",type:"select",opts:[["","Choose"],["yes","Yes"],["no","No"]]},
  {k:"salary",label:"Expected yearly pay in US dollars (optional)",type:"number",min:0,max:10000000,step:1,ph:"85000",hint:"Only used when a form requires it. Leave it blank to be asked each time.",val:payOk},
  {k:"former",label:"Have you worked at the companies you apply to?",type:"select",full:1,hint:"Choose No only if you have never worked at any company you swipe right on.",opts:[["","Ask me each time"],["no","No, never"]]},
  {k:"govt",label:"Are you, or a close relative, a government official?",type:"select",opts:[["","Choose"],["no","No"],["yes","Yes"]]},
  {k:"phd",label:"Currently in a PhD program?",type:"select",opts:[["","Choose"],["no","No"],["yes","Yes"]]},
  {k:"pronouns",label:"Pronouns (optional)",type:"text",max:30,ph:"she/her, he/him, they/them"},
  {k:"ack",label:"Employers' privacy and AI-use notices",type:"select",full:1,hint:"Many forms ask you to confirm you read their privacy notice. Choose Yes only if you want UAply to confirm it for you.",opts:[["","Ask me each time"],["yes","Yes, confirm them for me"]]},
  {k:"why",label:"Why you want to work there (your own words)",type:"textarea",full:1,max:600,ph:"I'm excited about {company} because...",hint:"Used when a form asks why you want to join. {company} and {role} are filled in for each job."}]}
];

var CSS=".px-h{margin-top:6px}.px-h h3{margin:0}"+
".field .hint{color:var(--muted);font-size:12px}.field .err{color:var(--no);font-size:12px;font-weight:600}.field textarea{width:100%;padding:9px 11px;border-radius:10px;border:1px solid var(--line);background:var(--surface);resize:vertical}"+
".field input[type=tel],.field input[type=url],.field input[type=month]{width:100%;padding:9px 11px;border-radius:10px;border:1px solid var(--line);background:var(--surface)}"+
".field [aria-invalid=true]{border-color:var(--no)}"+
".ready{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:14px 16px;display:flex;flex-direction:column;gap:10px}"+
".ready .top{display:flex;justify-content:space-between;align-items:baseline;gap:10px}.ready b{font:800 16px var(--display)}.ready .pct{font:800 22px var(--display)}"+
".ready .bar{height:8px;border-radius:99px;background:var(--line);overflow:hidden}.ready .bar i{display:block;height:100%;border-radius:99px;background:linear-gradient(135deg,var(--accent),var(--accent2));transition:width .25s}"+
".ready .miss{display:flex;flex-wrap:wrap;gap:6px}.ready .miss button{border:1px solid var(--line);background:var(--bg);border-radius:999px;padding:5px 11px;font-size:12.5px;font-weight:600;min-height:32px}"+
".ready .done{color:var(--yes);font-weight:600;font-size:13.5px}"+
"@media (prefers-reduced-motion:reduce){.ready .bar i{transition:none}}";

function apply(w){
  var d=w.document,form=d.getElementById("form");
  if(!form||!d.getElementById("pEmail"))throw new Error("needs the Bottom navigation experiment");
  var st=d.createElement("style");st.textContent=CSS;d.head.appendChild(st);
  var grid=form.querySelector(".grid"),ALL=[];
  function id(k,extra){return "px-"+k+(extra?"-"+extra:"")}

  /* build the fields from SPEC */
  SPEC.forEach(function(g){
    var h=d.createElement("div");h.className="field full px-h";h.setAttribute("data-sec",g.sec);h.innerHTML="<h3>"+g.title+"</h3>";grid.appendChild(h);
    g.items.forEach(function(it){
      it.sec=g.sec;ALL.push(it);
      var f=d.createElement("div");f.className="field"+(it.full?" full":"");f.setAttribute("data-sec",g.sec);
      var html='<label for="'+id(it.k)+'">'+it.label+'</label>';
      if(it.type==="select")html+='<select id="'+id(it.k)+'">'+it.opts.map(function(o){return '<option value="'+o[0]+'">'+o[1]+'</option>'}).join("")+'</select>';
      else if(it.type==="textarea")html+='<textarea id="'+id(it.k)+'" rows="'+(it.k==="noteTpl"?5:3)+'" maxlength="'+(it.max||600)+'" placeholder="'+(it.ph||"")+'"></textarea>';
      else if(it.type==="checks"){html=html.replace("<label","<span class=\"l\"").replace("</label>","</span>");html+='<div class="checks" role="group" aria-label="'+it.label+'">'+it.opts.map(function(o){return '<label><input type="checkbox" id="'+id(it.k,o[0])+'" value="'+o[0]+'"> '+o[1]+'</label>'}).join("")+'</div>'}
      else html+='<input type="'+(it.type==="url"||it.type==="tel"?"text":it.type)+'" id="'+id(it.k)+'"'+(it.type==="url"?' inputmode="url" autocomplete="url"':'')+(it.type==="tel"?' inputmode="tel" autocomplete="tel"':'')+(it.max?' maxlength="'+it.max+'"':'')+(it.type==="number"?' min="'+it.min+'" max="'+it.max+'" step="'+it.step+'" inputmode="decimal"':'')+(it.ph?' placeholder="'+it.ph+'"':'')+'>';
      if(it.hint)html+='<small class="hint">'+it.hint+'</small>';
      html+='<small class="err" id="'+id(it.k,"err")+'" role="alert"></small>';
      f.innerHTML=html;grid.appendChild(f);
    });
  });

  function el(k){return d.getElementById(id(k))}

  /* the country belongs with the home address (city, state and ZIP code), so it is asked right after the ZIP code */
  var zipF=d.getElementById("adZip");if(zipF&&zipF.closest(".field"))zipF.closest(".field").after(el("country").closest(".field"));
  /* "Willing to relocate" is also a box under Work style (it changes which jobs show); the two always give the same answer */
  var relBox=d.getElementById("pReloc"),relSel=el("relocate");
  if(relBox){
    relSel.addEventListener("change",function(){if(relSel.value)relBox.checked=relSel.value==="yes"});
    relBox.addEventListener("change",function(){relSel.value=relBox.checked?"yes":"no"});
  }
  function relSync(){if(relBox&&!relSel.value&&relBox.checked)relSel.value="yes"}
  function readItem(it){
    if(it.type==="checks")return it.opts.filter(function(o){return d.getElementById(id(it.k,o[0])).checked}).map(function(o){return o[0]});
    return (el(it.k).value||"").trim();
  }
  function read(){var o={};ALL.forEach(function(it){var v=readItem(it);if(it.type==="checks"?v.length:v!=="")o[it.k]=v});return o}
  function fill(o){
    ALL.forEach(function(it){
      if(it.type==="checks"){var a=Array.isArray(o[it.k])?o[it.k]:[];it.opts.forEach(function(x){d.getElementById(id(it.k,x[0])).checked=a.indexOf(x[0])>-1})}
      else{el(it.k).value=typeof o[it.k]==="string"||typeof o[it.k]==="number"?o[it.k]:"";if(it.type==="select"&&el(it.k).selectedIndex<0)el(it.k).selectedIndex=0}   /* a list with no "Choose" (country) starts on its first answer */
    });
    ALL.forEach(validate);update();
    setTimeout(function(){relSync();update()},0);   /* the app fills its own fields (like email and Work style) right after this, so recount once it is done */
  }
  w.__uaplyExtRead=read;w.__uaplyExtFill=fill;

  /* validation, shown under each field */
  function validate(it){
    var msg="",v=readItem(it);
    if(it.val)msg=it.val(v);
    if(it.k==="job_end"&&v){var s0=readItem(ALL.filter(function(x){return x.k==="job_start"})[0]);msg=!s0?"Add the month you started too.":v<s0?"This is before the month you started.":""}
    if(it.k==="sponsor"||it.k==="auth"){
      var a=readItem(ALL.filter(function(x){return x.k==="auth"})[0]),s=readItem(ALL.filter(function(x){return x.k==="sponsor"})[0]);
      if(it.k==="sponsor"&&a&&s&&((a==="citizen"&&s==="yes")||(a==="none"&&s==="no")))msg="This does not match your work authorization answer. Employers often flag that.";
    }
    var e=d.getElementById(id(it.k,"err")),c=el(it.k);if(e)e.textContent=msg;if(c)c.setAttribute("aria-invalid",msg?"true":"false");
    return msg;
  }

  /* readiness: weights add up to 100 */
  var ready=d.createElement("div");ready.className="field full";ready.setAttribute("data-sec","settings preferences");
  ready.innerHTML='<div class="ready" role="status"><div class="top"><b>Application readiness</b><span class="pct" id="px-pct">0%</span></div><div class="bar"><i id="px-bar" style="width:0"></i></div><div class="miss" id="px-miss"></div></div>';
  grid.insertBefore(ready,grid.firstChild);
  function v(i){return (d.getElementById(i).value||"").trim()}
  var READY=[
   {w:10,label:"Full name",sec:"settings",id:"pName",ok:function(){return !!v("pName")}},
   {w:15,label:"Email",sec:"settings",id:"pEmail",ok:function(){return EMAIL.test(v("pEmail"))}},
   {w:15,label:"Phone number",sec:"settings",id:id("phone"),ok:function(){return !!v(id("phone"))&&!phoneOk(v(id("phone")))}},
   {w:20,label:"Resume link or summary",sec:"settings",id:id("resume"),ok:function(){return (!!v(id("resume"))&&!urlOk(v(id("resume"))))||v(id("summary")).length>=40}},
   {w:15,label:"Work authorization and sponsorship",sec:"preferences",id:id("auth"),ok:function(){return !!v(id("auth"))&&!!v(id("sponsor"))}},
   {w:10,label:"At least 3 skills",sec:"settings",id:"pSkills",ok:function(){return v("pSkills").split(",").filter(function(x){return x.trim()}).length>=3}},
   {w:5,label:"Education",sec:"settings",id:id("school"),ok:function(){return !!v(id("school"))}},
   {w:5,label:"Earliest start",sec:"preferences",id:id("start"),ok:function(){return !!v(id("start"))}},
   {w:5,label:"Opportunity types",sec:"preferences",id:id("types","fulltime"),ok:function(){return readItem(ALL.filter(function(x){return x.k==="types"})[0]).length>0}}
  ];
  function curSection(){var b=d.querySelector("#secTitle");return b?b.textContent.toLowerCase():""}
  function goTo(sec,fieldId){
    if(w.__uaplyGoField){w.__uaplyGoField(sec,fieldId);return}   /* the guided setup knows which step the field is on */
    function focus(){var c=d.getElementById(fieldId);if(c){c.scrollIntoView({block:"center"});c.focus()}}
    if(curSection()===sec){focus();return}
    var nb=d.getElementById("nb-prof");if(!nb)return;
    nb.click();var it=d.querySelector('.nwrap[data-k=prof] .nitem[data-v='+sec+']');if(it){it.click();setTimeout(focus,80)}
  }
  function update(){
    var got=0,miss=[];READY.forEach(function(r){r.ok()?got+=r.w:miss.push(r)});
    d.getElementById("px-pct").textContent=got+"%";d.getElementById("px-bar").style.width=got+"%";
    var box=d.getElementById("px-miss");
    box.innerHTML=miss.length?miss.map(function(r,i){return '<button type="button" data-i="'+READY.indexOf(r)+'">Add '+r.label.toLowerCase()+' (+'+r.w+')</button>'}).join(""):'<span class="done">Ready: you can apply in one swipe with everything an employer asks for.</span>';
  }
  d.getElementById("px-miss").addEventListener("click",function(e){var b=e.target.closest("button[data-i]");if(b){var r=READY[+b.getAttribute("data-i")];goTo(r.sec,r.id)}});
  form.addEventListener("input",function(e){var it=ALL.filter(function(x){return e.target.id===id(x.k)||e.target.id.indexOf(id(x.k)+"-")===0})[0];if(it){validate(it);if(it.k==="auth")validate(ALL.filter(function(x){return x.k==="sponsor"})[0]);if(it.k==="job_start")validate(ALL.filter(function(x){return x.k==="job_end"})[0])}update()});
  form.addEventListener("change",function(){update()});

  /* a link or phone that fails its check blocks Save and takes you to the first problem */
  form.addEventListener("submit",function(e){
    var bad=ALL.map(validate).map(function(m,i){return m?ALL[i]:null}).filter(Boolean)[0];
    if(bad){e.preventDefault();e.stopImmediatePropagation();goTo(bad.sec,id(bad.k))}
  },true);

  fill(w.__uaply&&w.__uaply.S&&w.__uaply.S.profile&&w.__uaply.S.profile.ext||{});
}

window.UAplyProfile={patch:patch,apply:apply};
})();
