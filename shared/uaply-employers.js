/* "Hiring mode" (sandbox only): the employer side of UAply, reached from a "Switch to hiring" pill in the header.
   An employer sets up the company once (name, logo, industry, size, United States or Canada, About), posts jobs on one page with a live
   preview, and works applicants through a simple pipeline. A posting asks for exactly what a job seeker's Profile setup, application
   details and Filters hold, so cards are scored and filtered on equal terms. Prices are TBD.
   With the UAply server (employers_api.py) postings go into the shared job feed; on a static copy they are kept in this browser and
   added to this browser's own deck, so the whole flow can be tried. Registers itself as an experiment: only pages that load this file
   (the sandbox) have it. */
(function(){
"use strict";
var Env=window.UAplyEnv;if(!Env)return;
function once(src,a,b){if(src.indexOf(a)<0)throw new Error("patch target not found: "+a.slice(0,40));return src.replace(a,function(){return b})}

var TYPES=[["job","Full-time"],["parttime","Part-time"],["internship","Internship"],["coop","Co-op"]];
var MODES=[["remote","Remote"],["hybrid","Hybrid"],["onsite","On-site"]];
var COUNTRIES=[["US","United States"],["CA","Canada"]];
var REGIONS={
  US:[["AL","Alabama"],["AK","Alaska"],["AZ","Arizona"],["AR","Arkansas"],["CA","California"],["CO","Colorado"],["CT","Connecticut"],["DE","Delaware"],["DC","District of Columbia"],["FL","Florida"],["GA","Georgia"],["HI","Hawaii"],["ID","Idaho"],["IL","Illinois"],["IN","Indiana"],["IA","Iowa"],["KS","Kansas"],["KY","Kentucky"],["LA","Louisiana"],["ME","Maine"],["MD","Maryland"],["MA","Massachusetts"],["MI","Michigan"],["MN","Minnesota"],["MS","Mississippi"],["MO","Missouri"],["MT","Montana"],["NE","Nebraska"],["NV","Nevada"],["NH","New Hampshire"],["NJ","New Jersey"],["NM","New Mexico"],["NY","New York"],["NC","North Carolina"],["ND","North Dakota"],["OH","Ohio"],["OK","Oklahoma"],["OR","Oregon"],["PA","Pennsylvania"],["RI","Rhode Island"],["SC","South Carolina"],["SD","South Dakota"],["TN","Tennessee"],["TX","Texas"],["UT","Utah"],["VT","Vermont"],["VA","Virginia"],["WA","Washington"],["WV","West Virginia"],["WI","Wisconsin"],["WY","Wyoming"],["PR","Puerto Rico"]],
  CA:[["AB","Alberta"],["BC","British Columbia"],["MB","Manitoba"],["NB","New Brunswick"],["NL","Newfoundland and Labrador"],["NS","Nova Scotia"],["NT","Northwest Territories"],["NU","Nunavut"],["ON","Ontario"],["PE","Prince Edward Island"],["QC","Quebec"],["SK","Saskatchewan"],["YT","Yukon"]]
};
var LEVELS=["High school","Associate","Bachelor","Master","Doctorate"];
var PERKS=[["health","Health insurance"],["dental","Dental insurance"],["vision","Vision insurance"],["k401","401(k) or RRSP"],["match","Retirement plan with employer match"],["loan","Student loan repayment"],["stock","Stock options"],["pto","Paid time off (PTO)"],["maternity","Paid maternity leave"],["paternity","Paid paternity leave"],["tuition","Tuition assistance"]];
var START=[["","Not decided"],["now","Right away"],["2w","Within 2 weeks"],["1m","Within a month"],["grad","After graduation"],["flex","Flexible"]];
var INDUSTRIES=["Accounting","Advertising and marketing","Aerospace and defense","Agriculture","Architecture and planning","Arts and design","Biotech and pharmaceuticals","Consulting","Education","Energy and utilities","Engineering","Finance and banking","Government and public sector","Healthcare","Hospitality and food service","Insurance","Law and legal services","Manufacturing","Media and entertainment","Nonprofit and social services","Real estate and construction","Retail and consumer goods","Science and research","Software and technology","Sports and recreation","Telecommunications","Transportation and logistics","Other"];
var SIZES=["1-10","11-50","51-200","201-500","501-1,000","1,001-5,000","5,001-10,000","10,001+"];
var STAGES=[["new","New"],["review","Reviewing"],["interview","Interview"],["offer","Offer"],["hired","Hired"],["no","Not a fit"]];
var AUTH_LBL={citizen:"Citizen or permanent resident",authorized:"Authorized (visa, OPT or similar)",none:"Not currently authorized"};
function lbl(list,k){for(var i=0;i<list.length;i++)if(list[i][0]===k)return list[i][1];return ""}

/* ---------- the job seeker app learns about employer postings ---------- */
function patch(s){
  s=once(s,"function logoHTML(j){return ","function logoHTML(j){if(window.__uaplyLogo){var L=window.__uaplyLogo(j);if(L)return L}return ");
  s=once(s,"<p class=\"blurb\">'+esc(j.blurb)+'</p>","<p class=\"blurb\">'+esc(j.blurb)+'</p>'+(window.__uaplyEmpCard?window.__uaplyEmpCard(j):'')+'");
  /* add, update or drop employer postings in this page's job list (a closed one that someone already swiped stays, marked closed) */
  s=once(s,"var JOB_BY_ID={};JOBS.forEach(function(j){JOB_BY_ID[j.id]=j});",
    "var JOB_BY_ID={};JOBS.forEach(function(j){JOB_BY_ID[j.id]=j});\n"+
    "window.__uaplyEmpJobs={sync:function(list,mine){var ids={};list.forEach(function(j){ids[j.id]=1;var o=JOB_BY_ID[j.id];if(o){Object.keys(o).forEach(function(k){if(!(k in j)&&k!==\"seen\")delete o[k]});Object.assign(o,j)}else{JOBS.push(j);JOB_BY_ID[j.id]=j}});"+
    "for(var i=JOBS.length-1;i>=0;i--){var x=JOBS[i];if(mine(x)&&!ids[x.id]){if(S.decisions[x.id])x.closed=true;else{JOBS.splice(i,1);delete JOB_BY_ID[x.id]}}}renderAll()}};");
  return s;
}

/* ---------- reading an existing job post (a link or pasted text) into the Post a job form ----------
   Sources, best first: the schema.org JobPosting block most career sites carry for Google Jobs, the public job feeds of
   Greenhouse, Lever, Ashby and SmartRecruiters, then the posting's own words. Every rule is a plain pattern on the text;
   nothing is guessed that the posting does not say, and the employer checks every field before publishing. */
var IMP=(function(){
  var STATES={},US=REGIONS.US,CAP=REGIONS.CA;
  US.concat(CAP).forEach(function(r){STATES[r[1].toLowerCase()]=r[0]});
  var CODES=US.map(function(r){return r[0]}).concat(CAP.map(function(r){return r[0]}));
  var MONTHS={jan:1,feb:2,mar:3,apr:4,may:5,jun:6,jul:7,aug:8,sep:9,oct:10,nov:11,dec:12,spring:5,summer:8,fall:12,autumn:12,winter:12};
  var PERK_RES=[["health",/health(?:care)? (?:insurance|coverage|benefits|plans?)|medical (?:insurance|coverage|benefits|plans?)|medical,? dental/i],["dental",/\bdental\b/i],["vision",/\bvision (?:insurance|coverage|benefits|care|plans?)\b|dental,? (?:and |& )?vision/i],["k401",/401\s?\(?k\)?|\bRRSP\b/i],["match",/401\s?\(?k\)?[^.]{0,80}match|(?:employer|company) match|matching contributions?/i],["loan",/student loan/i],["stock",/stock options?|equity (?:grants?|compensation|package)|\bRSUs?\b|\bESPP\b|stock purchase/i],["pto",/\bPTO\b|paid time off|paid vacation|unlimited (?:vacation|time off)|vacation days/i],["maternity",/paid (?:maternity|parental)|maternity leave|parental leave/i],["paternity",/paid (?:paternity|parental)|paternity leave|parental leave/i],["tuition",/tuition (?:assistance|reimbursement|support)|education(?:al)? (?:assistance|reimbursement)/i]];
  var COMM=/commission[- ]only|100% commission|straight commission|commission[- ]based (?:pay|compensation|position|role|only)|no base (?:salary|pay)|1099 commission/i;
  /* sites whose terms forbid other sites reading their pages, or that need a login: the employer pastes the text instead */
  var NO_READ=[["linkedin.com","LinkedIn"],["indeed.com","Indeed"],["ziprecruiter.com","ZipRecruiter"],["glassdoor.com","Glassdoor"],["joinhandshake.com","Handshake"],["handshake.com","Handshake"],["monster.com","Monster"],["hiring.cafe","Hiring Cafe"]];
  function blocked(host){host=String(host||"").toLowerCase();for(var i=0;i<NO_READ.length;i++){var h=NO_READ[i][0];if(host===h||host.slice(-h.length-1)==="."+h)return NO_READ[i][1]}return ""}
  function clean(s){return String(s==null?"":s).replace(/ /g," ").replace(/[ \t]+/g," ").replace(/ *\n */g,"\n").replace(/\n{3,}/g,"\n\n").trim()}
  function htmlText(h){
    h=String(h||"");
    if(typeof DOMParser!=="undefined"){var dd=new DOMParser().parseFromString("<div>"+h.replace(/<(br|\/p|\/li|\/h\d|\/div|\/tr)\b[^>]*>/gi,"$&\n")+"</div>","text/html");dd.querySelectorAll("script,style,noscript").forEach(function(e){e.remove()});return clean(dd.body.textContent)}
    return clean(h.replace(/<(script|style|noscript)[\s\S]*?<\/\1>/gi," ").replace(/<(br|\/p|\/li|\/h\d|\/div)\b[^>]*>/gi,"\n").replace(/<[^>]+>/g," ").replace(/&nbsp;/g," ").replace(/&amp;/g,"&").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&#39;|&apos;/g,"'").replace(/&quot;/g,'"'));
  }
  function decodeEntities(s){return String(s||"").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&amp;/g,"&")}
  function money(v){v=String(v).replace(/[$,\s]/g,"");var k=/k$/i.test(v);v=parseFloat(v);return isFinite(v)?(k?v*1000:v):0}
  function yearly(n,unit){unit=String(unit||"").toLowerCase();if(/hour|hr/.test(unit))return Math.round(n*2080);if(/week/.test(unit))return Math.round(n*52);if(/month/.test(unit))return Math.round(n*12);if(!unit&&n>0&&n<250)return Math.round(n*2080);return Math.round(n)}
  function wordAt(t,i,len){var b=i>0?t.charAt(i-1):" ",a=t.charAt(i+len)||" ";return !/[A-Za-z0-9]/.test(b)&&!/[A-Za-z0-9+#]/.test(a)}
  /* skills, in three tiers. TOOLS are names written with capitals in every post (matched exactly, so "rest" is not REST
     and "excel at" is not Excel); PHRASES are skills written in plain words; GENERAL are broad skills that only fill spare slots */
  var TOOLS=("Excel|Microsoft Office|PowerPoint|Google Sheets|Outlook|SQL|Python|Java|JavaScript|TypeScript|C\\+\\+|C#|\\.NET|Golang|Rust|Swift|Kotlin|Scala|PHP|Ruby|Rails|HTML|CSS|React Native|React|Angular|Vue|Node\\.js|Django|Flask|Spring Boot|AWS|Azure|Google Cloud|GCP|Docker|Kubernetes|Terraform|Linux|Git|REST|GraphQL|PostgreSQL|MySQL|MongoDB|Redis|Kafka|Elasticsearch|Snowflake|Databricks|BigQuery|Redshift|Airflow|dbt|Tableau|Power BI|Looker|Spark|Hadoop|PyTorch|TensorFlow|Android|iOS|Flutter|Unity|Unreal|Objective-C|Selenium|Cypress|Jenkins|CI/CD|Jira|Figma|Sketch|Adobe Creative Suite|Photoshop|Illustrator|InDesign|Premiere Pro|After Effects|Canva|Google Analytics|Google Ads|HubSpot|Salesforce|SAP|NetSuite|Zendesk|Shopify|WordPress|Webflow|QuickBooks|GAAP|Bloomberg|Epic|EMR|CPR|BLS|PCR|AutoCAD|SolidWorks|CAD|MATLAB|LabVIEW|PLC|Civil 3D|Revit|GIS|SEO|SEM|ETL|CRM|Microsoft Word|Spanish|French|Mandarin").split("|");
  var PHRASES=("machine learning|deep learning|data analysis|data visualization|statistics|user research|UX research|prototyping|wireframing|design systems|financial modeling|financial analysis|email marketing|content writing|copywriting|social media|lead generation|account management|customer service|project management|product management|supply chain|risk management|legal research|contract drafting|litigation|patient care|clinical research|lab techniques|phlebotomy|lesson planning|curriculum development|classroom management|event planning|video editing|photography|journalism|public relations|cash handling|food safety|merchandising|bookkeeping|payroll|auditing|accounting|underwriting|valuation|agile|scrum|automated testing|unit testing|bilingual").split("|");
  var GENERAL=("communication|leadership|teamwork|problem solving|time management|attention to detail|research|writing|sales|marketing|operations|negotiation|public speaking|scheduling|budgeting|forecasting|logistics|inventory|procurement|teaching|tutoring|compliance").split("|");
  function nice(s){return s.replace(/\\/g,"").replace(/^[a-z]/,function(c){return c.toUpperCase()})}
  /* the hiring boilerplate most posts end with (equal opportunity, privacy, benefits, pay ranges): never a skill source */
  var BOILER=/equal (?:employment )?opportunity|\bEEO\b|affirmative action|reasonable accommodation|disabilit|protected veteran|privacy (?:policy|notice)|background check|e-?verify|recruiting scam|fraudulent|arrest (?:or|and) conviction|pay transparency|salary range|compensation (?:range|package)|benefits (?:include|package)|we offer|our benefits|medical, dental|401\s?\(?k|parental leave|paid time off/i;
  function reqPart(t){var m=t.search(/\b(?:requirements|qualifications|what you(?:'ll| will)? (?:need|bring)|what we(?:'re| are) looking for|about you|you (?:have|bring|might be a fit)|who you are|skills (?:and|&) experience|minimum qualifications|basic qualifications)\b/i);return m<0?"":t.slice(m,m+3000)}
  function findSkills(t){
    var body=t.split("\n").filter(function(l){return !BOILER.test(l)}).join("\n"),req=reqPart(body),hits=[];
    function scan(list,tier,flags){
      list.forEach(function(s){
        var re=new RegExp(s.replace(/ /g,"\\s+"),flags),m,n=0,inReq=false,first=-1;
        while((m=re.exec(body))){if(wordAt(body,m.index,m[0].length)){n++;if(first<0)first=m.index}if(re.lastIndex===m.index)re.lastIndex++}
        if(!n)return;
        if(req){var r2=new RegExp(s.replace(/ /g,"\\s+"),flags.replace("g",""));inReq=r2.test(req)}
        hits.push({s:nice(s),tier:tier,score:n+(inReq?3:0),i:first});
      });
    }
    scan(TOOLS,0,"g");scan(PHRASES,1,"gi");scan(GENERAL,2,"gi");
    hits=hits.filter(function(h){return !(h.s==="React"&&hits.some(function(x){return x.s==="React Native"}))});
    hits.sort(function(a,b){return a.tier-b.tier||b.score-a.score||a.i-b.i});
    var picked=hits.filter(function(h){return h.tier<2}).slice(0,6);
    hits.filter(function(h){return h.tier===2&&h.score>=3}).forEach(function(h){if(picked.length<6)picked.push(h)});
    if(!picked.length)picked=hits.slice(0,3);
    return picked.slice(0,6).map(function(h){return h.s});
  }
  function findLoc(t){
    var m=t.match(/\b(?:location|based in|office in|located in)\s*:?\s*([A-Z][A-Za-z.'-]+(?:[ -][A-Z][A-Za-z.'-]+){0,3}),\s*([A-Z]{2}|[A-Z][a-z]+(?: [A-Z][a-z]+){0,2})\b/);
    var all=m?[m]:[],re=/\b([A-Z][A-Za-z.'-]+(?:[ -][A-Z][A-Za-z.'-]+){0,3}),\s*([A-Z]{2}|[A-Z][a-z]+(?: [A-Z][a-z]+){0,2})\b/g,x;
    if(!all.length)while((x=re.exec(t))&&all.length<20)all.push(x);
    for(var i=0;i<all.length;i++){
      var city=all[i][1].replace(/^(?:in|at|near)\s+/i,""),r=all[i][2],code=CODES.indexOf(r)>-1?r:STATES[r.toLowerCase()];
      /* "San Francisco, New York" is a list of two cities, not San Francisco in New York state */
      if(code&&/^(?:New York|Washington)$/.test(r)){var mm=METROS.filter(function(x){return x[0].test(city)})[0];if(mm&&mm[2]!==code)return {city:mm[1],region:mm[2],country:mm[3]||"US"}}
      if(code&&!/^(Inc|LLC|Ltd|Corp|Remote|Hybrid)$/i.test(city))return {city:city,region:code,country:CAP.some(function(p){return p[0]===code})?"CA":"US"};
    }
    /* a big city or metro area named on its own ("San Francisco Bay Area", "NYC") */
    for(var k=0;k<METROS.length;k++){if(METROS[k][0].test(t))return {city:METROS[k][1],region:METROS[k][2],country:METROS[k][3]||"US"}}
    return null;
  }
  var METROS=[[/\bbay area\b|\bsan francisco\b/i,"San Francisco","CA"],[/\bnew york city\b|\bnyc\b|\bnew york,? ny\b|\bmanhattan\b|\bbrooklyn\b/i,"New York","NY"],[/\bphiladelphia\b/i,"Philadelphia","PA"],[/\blos angeles\b/i,"Los Angeles","CA"],[/\bchicago\b/i,"Chicago","IL"],[/\bboston\b/i,"Boston","MA"],[/\bseattle\b/i,"Seattle","WA"],[/\baustin\b/i,"Austin","TX"],[/\bdallas\b/i,"Dallas","TX"],[/\bhouston\b/i,"Houston","TX"],[/\batlanta\b/i,"Atlanta","GA"],[/\bdenver\b/i,"Denver","CO"],[/\bwashington,? d\.?c\.?|\bwashington dc\b/i,"Washington","DC"],[/\bmiami\b/i,"Miami","FL"],[/\bpittsburgh\b/i,"Pittsburgh","PA"],[/\bsan diego\b/i,"San Diego","CA"],[/\bsan jose\b/i,"San Jose","CA"],[/\bpalo alto\b/i,"Palo Alto","CA"],[/\bmountain view\b/i,"Mountain View","CA"],[/\bmenlo park\b/i,"Menlo Park","CA"],[/\bminneapolis\b/i,"Minneapolis","MN"],[/\bdetroit\b/i,"Detroit","MI"],[/\bcharlotte\b/i,"Charlotte","NC"],[/\braleigh\b/i,"Raleigh","NC"],[/\bnashville\b/i,"Nashville","TN"],[/\bphoenix\b/i,"Phoenix","AZ"],[/\bportland,? or\b/i,"Portland","OR"],[/\bsalt lake city\b/i,"Salt Lake City","UT"],[/\bbaltimore\b/i,"Baltimore","MD"],[/\bnewark\b/i,"Newark","NJ"],[/\bjersey city\b/i,"Jersey City","NJ"],[/\bcolumbus,? oh/i,"Columbus","OH"],[/\bcleveland\b/i,"Cleveland","OH"],[/\bindianapolis\b/i,"Indianapolis","IN"],[/\bst\.? louis\b/i,"St. Louis","MO"],[/\bkansas city\b/i,"Kansas City","MO"],[/\borlando\b/i,"Orlando","FL"],[/\btampa\b/i,"Tampa","FL"],[/\blas vegas\b/i,"Las Vegas","NV"],[/\btoronto\b/i,"Toronto","ON","CA"],[/\bvancouver,? bc|\bvancouver\b(?!,? wa)/i,"Vancouver","BC","CA"],[/\bmontr[eé]al\b/i,"Montreal","QC","CA"],[/\bcalgary\b/i,"Calgary","AB","CA"],[/\bottawa\b/i,"Ottawa","ON","CA"],[/\bwaterloo,? on/i,"Waterloo","ON","CA"]];
  function findMode(t,hint){
    hint=String(hint||"").toLowerCase();
    if(/hybrid/.test(hint)||/\bhybrid\b/i.test(t))return "hybrid";
    if(/remote|telecommute/.test(hint)||/\b(?:fully remote|100% remote|remote[- ]first|remote (?:position|role|job|opportunity)|work from home|this (?:role|position|job) is remote|location:\s*remote)\b/i.test(t))return "remote";
    if(/on-?site|office/.test(hint)||/\b(?:on[- ]?site|in[- ]office|in person|in-person)\b/i.test(t))return "onsite";
    return "";
  }
  function findType(t,emp,title){
    var e=String(emp||"").toLowerCase().replace(/[^a-z]/g,"");
    if(/co-?op\b/i.test(title||"")||/\bco-?op (?:position|program|role|term)\b/i.test(t))return "coop";
    if(/intern/.test(e)||/\bintern(?:ship)?\b/i.test(title||""))return "internship";
    if(/parttime/.test(e)||/\bpart[- ]time\b/i.test(title||""))return "parttime";
    if(/fulltime/.test(e))return "job";
    if(/\binternship\b/i.test(t))return "internship";
    if(/\bpart[- ]time\b/i.test(t)&&!/\bfull[- ]time\b/i.test(t))return "parttime";
    return "job";
  }
  function findPay(t){
    var re=/\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?([kK])?\s*(?:-|–|—|to)\s*\$?\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?([kK])?(?:\s*(?:USD|CAD))?\s*(?:\/|per|an|a)?\s*(hour|hr|year|yr|annually|annum|month|week)?/i,m=t.match(re);
    if(!m)return null;
    var lo=money(m[1]+(m[2]||"")),hi=money(m[3]+(m[4]||""));if(!(lo>0&&hi>=lo))return null;
    var unit=m[5]||(/per hour|hourly|\/hr|an hour/i.test(t.slice(Math.max(0,m.index-40),m.index+m[0].length+40))?"hour":"");
    return [yearly(lo,unit),yearly(hi,unit)];
  }
  function findYears(t,type){
    var m=t.match(/(?:minimum of |at least |)(\d{1,2})\s*\+?\s*(?:(?:-|–|to)\s*\d{1,2}\s*)?(?:years?|yrs?)(?:'s)?(?:\s+of)?(?:\s+[\w-]+){0,4}?\s+(?:experience|exp\b)/i);
    if(m)return Math.min(15,+m[1]);
    return type==="internship"||type==="coop"?0:null;
  }
  function findEdu(t){
    var L=[["Doctorate",/\b(?:ph\.?d|doctorate|doctoral)\b/i],["Master",/\b(?:master'?s|m\.?s\.?|mba|m\.?a\.?)\s*(?:degree|in|of)\b|\bmaster'?s\b|\bmba\b/i],["Bachelor",/\bbachelor'?s|\bb\.?[as]\.?\s+(?:degree|in)\b|\b4-year degree|\bfour-year degree|\bundergraduate degree/i],["Associate",/\bassociate'?s? degree\b/i],["High school",/\bhigh school\b|\bGED\b/i]];
    var req=t.match(/([^.\n]{0,80})\b(?:required|minimum|must have)\b([^.\n]{0,40})/i),found=[];
    L.forEach(function(l,i){if(l[1].test(t))found.push(i)});
    if(!found.length)return "";
    if(req){var seg=req[0];for(var i=L.length-1;i>=0;i--)if(L[i][1].test(seg))return L[i][0]}
    return L[Math.max.apply(null,found)][0];   /* the lowest level the post mentions */
  }
  function findMajors(t){
    var m=t.match(/(?:degree|major(?:ing)?|studying|coursework|pursuing (?:a |an )?(?:bachelor'?s|master'?s|degree)?)\s+(?:in|of)\s+([^.;:\n()]{3,160})/i);if(!m)return [];
    return m[1].split(/,|\/|\bor\b|\band\b/i).map(function(x){return x.replace(/\b(?:a |an |the |related (?:fields?|disciplines?|areas?)|similar|equivalent|field|or|degree|preferred|required|etc)\b/gi,"").replace(/\s+/g," ").trim()})
      .filter(function(x){return x.length>=3&&x.length<=50&&x.split(" ").length<=5&&/^[A-Z]/.test(x)}).slice(0,6);
  }
  function findGpa(t){var m=t.match(/(\d\.\d{1,2})\s*(?:\/\s*4\.0+\s*)?(?:or (?:higher|above|better)|\+)?\s*(?:cumulative |overall )?GPA/i)||t.match(/GPA\s*(?:of|:)?\s*(?:at least |minimum(?: of)? |of at least )?(\d\.\d{1,2})/i);var g=m?+m[1]:0;return g>0&&g<=4?g:0}
  function ym(s,end){var m=String(s).match(/([A-Za-z]+)?\s*(20\d\d)/);if(!m)return "";var mo=m[1]?MONTHS[m[1].slice(0,3).toLowerCase()]||MONTHS[m[1].toLowerCase()]:0;mo=mo||(end?12:1);return m[2]+"-"+(mo<10?"0":"")+mo}
  function findGrad(t){
    var W="(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|spring|summer|fall|autumn|winter)?\\s*20\\d\\d";
    var m=t.match(new RegExp("graduat\\w*\\s+(?:date\\s+)?(?:between|from|in|by|of)?\\s*("+W+")(?:\\s*(?:-|–|and|to|through)\\s*("+W+"))?","i"))||t.match(/class of (20\d\d)(?:\s*(?:or|and|-|–)\s*(20\d\d))?/i);
    if(!m)return ["",""];
    return [ym(m[1],false),ym(m[2]||m[1],true)];
  }
  function findSponsor(t){
    if(/(?:unable to|cannot|can ?not|will not|won'?t|does not|do not|not able to|is not able to)\s+(?:currently\s+)?(?:provide|offer|support)?\s*(?:visa\s+|immigration\s+)?sponsor|without (?:the need for )?(?:current or future |now or in the future )?(?:visa |employment )?sponsorship|\bno (?:visa )?sponsorship|sponsorship (?:is )?not (?:available|provided|offered)/i.test(t))return "no";
    if(/(?:visa\s+)?sponsorship (?:is )?(?:available|provided|offered)|(?:will|can|able to) (?:provide |offer )?(?:visa )?sponsor|we sponsor/i.test(t))return "yes";
    return "";
  }
  function findAuth(t){return /must be (?:a )?(?:U\.?S\.?|united states) citizen|(?:U\.?S\.?|united states) citizenship (?:is )?required|security clearance|citizens? (?:or|and) (?:lawful )?permanent residents? only|canadian citizens?(?: or permanent residents?)? only/i.test(t)?"citizen":""}
  function findStart(t){if(/start(?:ing)?(?: date)?\s*:?\s*(?:immediately|asap|as soon as possible|right away)|immediate start/i.test(t))return "now";if(/start(?:ing)?\s+(?:date\s*:?\s*)?(?:is\s+)?flexible/i.test(t))return "flex";return ""}
  function findTitle(t){var m=t.match(/(?:job title|position title|title|position|role)\s*:\s*([^\n]{3,90})/i);if(m)return m[1].trim();var lines=t.split("\n").map(function(x){return x.trim()}).filter(Boolean);for(var i=0;i<Math.min(6,lines.length);i++){if(lines[i].length>=4&&lines[i].length<=80&&!/^(about|job description|description|overview|apply|share|save|back)\b/i.test(lines[i])&&!/[.!?]$/.test(lines[i]))return lines[i]}return ""}
  /* the one-line card summary: a sentence about the role itself, not the company's "About us" intro */
  function blurbOf(t){
    var s=t.replace(/([.!?])\s+/g,"$1\n").split("\n").map(function(x){return x.replace(/^(?:[A-Z][A-Z&'.-]+\s+){1,4}(?=[A-Z][a-z])/,"").trim()}).filter(function(x){return x.length>=30&&x.length<=220&&/[a-z]/.test(x)});
    var best="",score=-99;
    s.forEach(function(x,i){
      var v=0;
      if(/\b(?:you will|you'll|we(?:'re| are) looking|responsible for|join (?:our|the)|in this role|as (?:a|an|our) [A-Za-z ]{3,40},? you|this role|the role)\b/i.test(x))v+=3;
      if(/^about\b|\b(?:is building|was founded|our mission|we are a|is a leading|founded in|we believe|equal opportunity|accommodation|referr(?:ed|al)|on your behalf|please (?:contact|apply|note|submit)|privacy|e-?verify|background check)\b/i.test(x))v-=4;
      if(/^[-•*]/.test(x))v-=1;
      v-=i*0.02;
      if(v>score){score=v;best=x}
    });
    return best.replace(/^[-•*]\s*/,"").slice(0,220);
  }
  /* turn any source into the Post a job fields; base holds what a structured source already knows */
  function fill(text,base,url){
    base=base||{};text=clean(text||"");var f={},got={};
    function put(k,v){if(v!==""&&v!=null&&!(Array.isArray(v)&&!v.length)){f[k]=v;got[k]=1}}
    var title=String(base.title||findTitle(text)).replace(/\s+/g," ").trim();put("role",title.slice(0,120));
    var type=findType(text,base.employmentType,title);f.type=type;if(base.employmentType||/intern|co-?op|part[- ]time/i.test(title+" "+text.slice(0,600)))got.type=1;
    var loc=base.city&&base.region?{city:base.city,region:base.region,country:base.country||"US"}:findLoc((base.locationText?base.locationText+"\n":"")+text);
    if(loc){put("city",loc.city);put("region",loc.region);put("country",loc.country)}
    else if(base.country){put("country",base.country)}
    put("mode",findMode(text,base.workplace));
    var pay=base.pay||findPay(text);if(pay){f.sal_min=pay[0];f.sal_max=pay[1];got.sal=1}
    var y=base.years!=null?base.years:findYears(text,type);if(y!=null){f.yrs=y;got.yrs=1}
    put("edu",base.edu||findEdu(text));
    put("skills",findSkills(text));put("majors",findMajors(text));
    var g=findGpa(text);if(g){f.gpa=String(g);got.gpa=1}
    var gr=findGrad(text);if(gr[0]||gr[1]){f.grad_from=gr[0];f.grad_to=gr[1];got.grad=1}
    put("sponsor",findSponsor(text));put("auth",findAuth(text));put("start",findStart(text));
    if(/relocation (?:assistance|package|support|stipend|bonus|is provided|available)/i.test(text)){f.reloc=true;got.reloc=1}
    if(COMM.test(text)){f.comm=true;got.comm=1}
    var perks=PERK_RES.filter(function(p){return p[1].test(text)}).map(function(p){return p[0]});put("perks",perks);
    put("blurb",blurbOf(text));put("desc",text.slice(0,5000));
    if(/^https:\/\//.test(url||""))put("url",url.slice(0,300));
    return {fields:f,got:got,org:base.org||""};
  }
  /* schema.org JobPosting (the block career sites add for Google Jobs) */
  function fromJsonLd(j,url){
    var a=(Array.isArray(j.jobLocation)?j.jobLocation[0]:j.jobLocation)||{},ad=a.address||{},b={},bs=j.baseSalary||{},v=bs.value||{};
    b.title=j.title||j.name||"";b.employmentType=Array.isArray(j.employmentType)?j.employmentType.join(" "):j.employmentType;
    b.org=(j.hiringOrganization&&j.hiringOrganization.name)||"";
    var c=String(ad.addressCountry&&ad.addressCountry.name||ad.addressCountry||"").toUpperCase();b.country=/^(CA|CAN|CANADA)$/.test(c)?"CA":(/^(US|USA|UNITED STATES)/.test(c)?"US":"");
    var r=String(ad.addressRegion||""),code=CODES.indexOf(r.toUpperCase())>-1?r.toUpperCase():STATES[r.toLowerCase()];
    if(ad.addressLocality&&code){b.city=ad.addressLocality;b.region=code;b.country=b.country||(CAP.some(function(p){return p[0]===code})?"CA":"US")}
    b.workplace=(j.jobLocationType||"")+" "+(j.applicantLocationRequirements?"remote":"");
    if(b.city&&!/telecommute/i.test(b.workplace))b.workplace+=" onsite";     /* Google's rule: a job with an address and no TELECOMMUTE is on-site (the text can still say hybrid) */
    var lo=+(v.minValue!=null?v.minValue:v.value),hi=+(v.maxValue!=null?v.maxValue:v.value);if(lo>0&&hi>=lo)b.pay=[yearly(lo,v.unitText||bs.unitText||"YEAR"),yearly(hi,v.unitText||bs.unitText||"YEAR")];
    var er=j.experienceRequirements;if(er&&er.monthsOfExperience)b.years=Math.min(15,Math.round(+er.monthsOfExperience/12));
    var ed=j.educationRequirements,cc=String(ed&&(ed.credentialCategory||ed)||"").toLowerCase();
    b.edu=/doctor|phd/.test(cc)?"Doctorate":/master|postgraduate/.test(cc)?"Master":/bachelor/.test(cc)?"Bachelor":/associate/.test(cc)?"Associate":/high school/.test(cc)?"High school":"";
    var text=htmlText(decodeEntities(j.description||""))+"\n"+[j.qualifications,j.responsibilities,j.skills,j.jobBenefits,j.incentiveCompensation].filter(function(x){return typeof x==="string"}).map(htmlText).join("\n");
    return fill(text,b,j.url||url);
  }
  function fromGreenhouse(j,url){var where=[j.location&&j.location.name].concat((j.offices||[]).map(function(o){return o.name})).filter(Boolean).join(" | ");
    return fill(htmlText(decodeEntities(j.content||"")),{title:j.title,locationText:where,workplace:where,
    pay:(j.pay_input_ranges&&j.pay_input_ranges[0])?[Math.round(j.pay_input_ranges[0].min_cents/100),Math.round(j.pay_input_ranges[0].max_cents/100)]:null},j.absolute_url||url)}
  function fromLever(j,url){var sr=j.salaryRange||{},t=[j.descriptionPlain||htmlText(j.description)].concat((j.lists||[]).map(function(l){return l.text+"\n"+htmlText(l.content)})).concat([j.additionalPlain||htmlText(j.additional)]).join("\n");
    return fill(t,{title:j.text,employmentType:j.categories&&j.categories.commitment,locationText:j.categories&&j.categories.location,workplace:j.workplaceType,
      pay:sr.min&&sr.max?[yearly(sr.min,/hour/.test(sr.interval||"")?"hour":"year"),yearly(sr.max,/hour/.test(sr.interval||"")?"hour":"year")]:null},j.hostedUrl||url)}
  function fromAshby(j,url){var ad=(j.address&&j.address.postalAddress)||{},comp=((j.compensation&&j.compensation.summaryComponents)||[]).filter(function(c){return /salary/i.test(c.compensationType||"")})[0],b={title:j.title,employmentType:j.employmentType,locationText:j.location,workplace:(j.workplaceType||"")+(j.isRemote?" remote":"")};
    var code=CODES.indexOf(String(ad.addressRegion||"").toUpperCase())>-1?String(ad.addressRegion).toUpperCase():STATES[String(ad.addressRegion||"").toLowerCase()];if(ad.addressLocality&&code){b.city=ad.addressLocality;b.region=code;b.country=CAP.some(function(p){return p[0]===code})?"CA":"US"}
    if(comp&&comp.minValue&&comp.maxValue)b.pay=[yearly(comp.minValue,/hour/i.test(comp.interval||"")?"hour":"year"),yearly(comp.maxValue,/hour/i.test(comp.interval||"")?"hour":"year")];
    return fill(j.descriptionPlain||htmlText(j.descriptionHtml),b,j.jobUrl||url)}
  function fromSmartRecruiters(j,url){var l=j.location||{},sec=((j.jobAd||{}).sections)||{},t=["companyDescription","jobDescription","qualifications","additionalInformation"].map(function(k){return sec[k]?(sec[k].title||"")+"\n"+htmlText(sec[k].text):""}).join("\n");
    var code=CODES.indexOf(String(l.region||"").toUpperCase())>-1?String(l.region).toUpperCase():STATES[String(l.region||"").toLowerCase()];
    return fill(t,{title:j.name,employmentType:j.typeOfEmployment&&j.typeOfEmployment.label,city:code?l.city:"",region:code||"",country:/^ca$/i.test(l.country||"")?"CA":"US",workplace:l.remote?"remote":(l.hybrid?"hybrid":"")},url)}
  /* public job feeds that answer browsers directly, so a link works even on the copy with no server */
  function feedFor(u){
    var p;try{p=new URL(u)}catch(e){return null}
    var h=p.hostname.toLowerCase(),s=p.pathname.split("/").filter(Boolean),q=p.searchParams;
    if(/(^|\.)greenhouse\.io$/.test(h)){var board=q.get("for")||s[0],id=q.get("token")||s[s.indexOf("jobs")+1];if(board&&/^\d+$/.test(id||""))return {kind:"Greenhouse",api:"https://boards-api.greenhouse.io/v1/boards/"+encodeURIComponent(board)+"/jobs/"+id+"?pay_transparency=true",read:fromGreenhouse}}
    /* a company careers page that shows a Greenhouse job (?gh_jid=123): the board is usually the company's own name */
    if(/^\d+$/.test(q.get("gh_jid")||"")){
      var parts=h.replace(/^www\./,"").split("."),name=parts.length>2&&/^(careers|jobs|job|work|join|about|apply)$/.test(parts[0])?parts[1]:parts[0];
      var guesses=[name,name.replace(/(careers?|jobs|hq|inc|corp)$/,""),name.replace(/^(careers?|jobs|join|work(?:at)?)/,"")].filter(function(g,i,a){return g&&a.indexOf(g)===i});
      return {kind:"Greenhouse",apis:guesses.map(function(g){return "https://boards-api.greenhouse.io/v1/boards/"+encodeURIComponent(g)+"/jobs/"+q.get("gh_jid")+"?pay_transparency=true"}),read:fromGreenhouse}}
    if(h==="jobs.lever.co"&&s.length>=2)return {kind:"Lever",api:"https://api.lever.co/v0/postings/"+encodeURIComponent(s[0])+"/"+encodeURIComponent(s[1]),read:fromLever};
    if(h==="jobs.ashbyhq.com"&&s.length>=2)return {kind:"Ashby",api:"https://api.ashbyhq.com/posting-api/job-board/"+encodeURIComponent(s[0])+"?includeCompensation=true",read:function(j,url){var job=(j.jobs||[]).filter(function(x){return x.id===s[1]})[0];if(!job)throw new Error("That job was not found on this Ashby board.");return fromAshby(job,url)}};
    if(h==="jobs.smartrecruiters.com"&&s.length>=2){var sid=(s[1].match(/^\d+/)||[])[0];if(sid)return {kind:"SmartRecruiters",api:"https://api.smartrecruiters.com/v1/companies/"+encodeURIComponent(s[0])+"/postings/"+sid,read:fromSmartRecruiters}}
    return null;
  }
  return {fromText:function(t,url){return fill(t,{},url)},fromJsonLd:fromJsonLd,feedFor:feedFor,blocked:blocked,htmlText:htmlText};
})();
window.UAplyJobImport=IMP;

var CSS=[
/* header pill, Fiverr-style */
".modesw{margin-left:auto;display:inline-flex;align-items:center;gap:7px;min-height:44px;padding:6px 15px;border-radius:999px;border:1.5px solid color-mix(in srgb,var(--accent) 45%,var(--line));background:var(--surface);color:var(--ink);font:700 13.5px var(--body);cursor:pointer;white-space:nowrap}",
".modesw:hover{border-color:var(--accent)}.modesw:focus-visible{outline:3px solid var(--accent);outline-offset:2px}.modesw svg{width:16px;height:16px;flex:none;stroke:var(--accent);fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}",
".modesw+.hdrbtn{margin-left:8px}.modetag{font:700 11px var(--mono);letter-spacing:.08em;text-transform:uppercase;padding:4px 9px;border-radius:7px;background:var(--ink);color:var(--surface)}",
"@media (max-width:520px){.modesw .lg{display:none}.modesw{padding:6px 11px}}",
"body.hire>*:not(.bar):not(#hub){display:none!important}#hub{flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;max-width:1180px;width:100%;margin-inline:auto}",
/* job card additions */
".logo.emplogo{background:#fff;border:1px solid var(--line);overflow:hidden;padding:4px}.logo.emplogo img{width:100%;height:100%;object-fit:contain;display:block}",
".empx{display:flex;flex-direction:column;gap:10px;border-top:1px solid var(--line);padding-top:12px}.empx-h{margin:0;font:700 12px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}",
".empx .crit{gap:8px}.empx .crit li{grid-template-columns:22px 110px 1fr;font-size:14px}",
".team{display:flex;gap:10px;align-items:center;padding:10px 12px;border-radius:12px;background:color-mix(in srgb,var(--accent) 8%,var(--surface));border:1px solid var(--line)}.team .tav{width:38px;height:38px;flex:none;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--accent-ink);font:800 14px var(--display)}.team b{display:block;font-size:14px}.team small{color:var(--muted);font-size:12.5px}",
".empmore summary{cursor:pointer;min-height:40px;display:flex;align-items:center;font-weight:700;font-size:14px}.empmore h4{margin:10px 0 4px;font:700 13px var(--body)}.empmore p{margin:0 0 6px;font-size:14px;white-space:pre-line;color:var(--ink)}.empmore .m{color:var(--muted);font-size:13px}",
/* the hub */
"#hub .hub{display:grid;grid-template-columns:230px minmax(0,1fr);gap:20px;align-items:start;padding-bottom:40px}",
"#hub .hnav{position:sticky;top:0;display:flex;flex-direction:column;gap:4px;padding:14px;border:1px solid var(--line);border-radius:18px;background:var(--surface)}",
"#hub .hnav button.hco{display:flex;gap:10px;align-items:center;justify-content:flex-start;padding:6px 6px 12px;margin-bottom:6px;border-bottom:1px solid var(--line);border-radius:12px 12px 0 0;min-width:0;text-align:left}#hub .hco b{display:block;font:800 15px/1.2 var(--display);overflow-wrap:anywhere}#hub .hco small{display:block;color:var(--muted);font-size:12px;font-weight:500}",
".brand[role=link]:focus-visible{outline:3px solid var(--accent);outline-offset:4px;border-radius:10px}",
"#hub .hlogo{width:42px;height:42px;flex:none;border-radius:11px;display:grid;place-items:center;background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--accent-ink);font:800 18px var(--display);overflow:hidden}#hub .hlogo img{width:100%;height:100%;object-fit:contain;background:#fff}",
"#hub .hnav button{display:flex;align-items:center;justify-content:space-between;gap:8px;text-align:left;min-height:42px;padding:8px 12px;border:0;border-radius:11px;background:none;color:var(--ink);font:600 14.5px var(--body);cursor:pointer}",
"#hub .hnav button:hover{background:color-mix(in srgb,var(--accent) 8%,transparent)}#hub .hnav button[aria-current=page]{background:color-mix(in srgb,var(--accent) 14%,var(--surface));color:var(--accent)}",
"#hub .hnav button.post{margin-top:6px;justify-content:center;background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--accent-ink)}#hub .hnav .n{font:600 11.5px var(--mono);padding:2px 8px;border-radius:99px;background:var(--bg);color:var(--muted)}",
"#hub .hmain{display:flex;flex-direction:column;gap:18px;min-width:0}",
"#hub h1{margin:0;font:800 28px/1.15 var(--display);letter-spacing:-.02em;text-wrap:balance}#hub h2{margin:0;font:800 18px/1.2 var(--display)}#hub .lead{margin:4px 0 0;color:var(--muted);max-width:68ch}",
"#hub .box{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:18px 20px;display:flex;flex-direction:column;gap:14px;min-width:0}",
"#hub .h-row{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between}",
"#hub .tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}#hub .tile{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:14px 16px}#hub .tile b{display:block;font:800 28px/1.1 var(--display);font-variant-numeric:tabular-nums}#hub .tile small{color:var(--muted);font-size:12.5px}",
"#hub .steps{display:flex;flex-direction:column;gap:8px;margin:0;padding:0;list-style:none}#hub .steps li{display:flex;gap:10px;align-items:center}#hub .steps .ck{width:24px;height:24px;flex:none;border-radius:50%;display:grid;place-items:center;font:700 12px var(--mono);border:1.5px solid var(--line);color:var(--muted)}#hub .steps .ck.on{background:var(--yes-bg);color:var(--yes);border-color:transparent}#hub .steps button{margin-left:auto}",
"#hub table{width:100%;border-collapse:collapse;font-size:14px}#hub th{text-align:left;font:600 11.5px var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--muted);padding:8px 10px;border-bottom:1px solid var(--line)}#hub td{padding:10px;border-bottom:1px solid var(--line);vertical-align:middle}#hub tr:last-child td{border-bottom:0}#hub .tw{overflow-x:auto}",
"#hub .st{display:inline-block;font:600 11.5px var(--mono);padding:3px 9px;border-radius:99px}#hub .st.open{background:var(--yes-bg);color:var(--yes)}#hub .st.paused{background:var(--mid-bg);color:var(--mid)}#hub .st.closed{background:var(--bg);color:var(--muted);border:1px solid var(--line)}",
"#hub .acts{display:flex;flex-wrap:wrap;gap:6px}#hub .sm{padding:6px 11px;font-size:13px;border-radius:9px}#hub .linkish{border:0;background:none;color:var(--accent);font-weight:600;cursor:pointer;padding:4px}",
"#hub .promise{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}#hub .promise div{border:1px solid var(--line);border-radius:14px;padding:12px 14px;background:var(--bg)}#hub .promise b{display:block;font-size:14px;margin-bottom:3px}#hub .promise small{color:var(--muted);font-size:12.5px}",
"#hub .pform{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:18px;align-items:start}#hub .pside{position:sticky;top:0;display:flex;flex-direction:column;gap:12px}",
"#hub fieldset{border:1px solid var(--line);border-radius:18px;background:var(--surface);padding:16px 18px 18px;margin:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 14px;min-width:0}#hub legend{padding:0 6px;font:800 16px var(--display)}",
"#hub .match{grid-column:1/-1;margin:-4px 0 2px;font-size:12.5px;color:var(--muted)}#hub .match b{color:var(--accent);font-weight:600}",
"#hub .f{display:flex;flex-direction:column;gap:5px;min-width:0}#hub .f.full{grid-column:1/-1}#hub .f>label,#hub .f>.l{font-weight:600;font-size:13.5px}#hub .f small{color:var(--muted);font-size:12px}#hub .req{color:var(--accent)}",
"#hub .f input[type=text],#hub .f input[type=number],#hub .f input[type=month],#hub .f input[type=email],#hub .f input[type=url],#hub .f select,#hub .f textarea{width:100%;padding:9px 11px;border-radius:10px;border:1px solid var(--line);background:var(--surface);color:var(--ink);font:inherit}",
"#hub .f textarea{resize:vertical;min-height:84px}#hub .f [aria-invalid=true]{border-color:var(--no);box-shadow:0 0 0 3px color-mix(in srgb,var(--no) 18%,transparent)}#hub .err{color:var(--no);font-weight:600;font-size:12.5px;min-height:0}",
"#hub .seg{display:flex;flex-wrap:wrap;gap:6px}#hub .seg label{display:flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:7px 13px;font-weight:600;font-size:13.5px;cursor:pointer}#hub .seg input{accent-color:var(--accent)}#hub .seg label:has(input:checked){border-color:var(--accent);background:color-mix(in srgb,var(--accent) 10%,var(--surface));color:var(--accent)}",
"#hub .perks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 12px}#hub .perks label{display:flex;gap:8px;align-items:center;font-size:14px}",
"#hub .ckline{display:flex;gap:9px;align-items:flex-start;font-size:14px}#hub .ckline input{margin-top:3px;accent-color:var(--accent)}",
"#hub .cnt{font:400 11.5px var(--mono);color:var(--muted);align-self:flex-end}",
"#hub .pbar{position:sticky;bottom:0;display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;padding:12px 16px;border:1px solid var(--line);border-radius:16px;background:color-mix(in srgb,var(--surface) 92%,transparent);backdrop-filter:blur(8px)}",
"#hub .price{font:600 13.5px var(--body)}#hub .price b{font:800 15px var(--display)}",
"#hub .pv{border:1px solid var(--line);border-radius:20px;background:var(--surface);padding:16px;display:flex;flex-direction:column;gap:10px;box-shadow:0 10px 30px -18px color-mix(in srgb,var(--accent) 60%,transparent)}",
"#hub .pv-h{display:flex;gap:10px;align-items:center}#hub .pv-h b{display:block;font:800 18px/1.15 var(--display)}#hub .pv-h small{color:var(--muted)}#hub .pv-pay{font:800 24px var(--display)}#hub .pv-pay small{font:500 12px var(--body);color:var(--muted);margin-left:4px}",
"#hub .facts{display:flex;flex-wrap:wrap;gap:6px}#hub .facts span{font-size:12.5px;padding:3px 9px;border-radius:99px;background:var(--bg);border:1px solid var(--line)}#hub .pv p{margin:0;font-size:14px}#hub .pv .chips{display:flex;flex-wrap:wrap;gap:6px}#hub .pv .chip{font-size:12px;padding:3px 9px}",
"#hub .pvlist{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:5px;font-size:13px}#hub .pvlist span{color:var(--muted)}",
"#hub .logoup{display:flex;gap:14px;align-items:center}#hub .logoup .hlogo{width:72px;height:72px;border-radius:16px;font-size:28px}",
"#hub .apps{display:flex;flex-direction:column;gap:12px}#hub .app{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px 14px;align-items:start}",
"#hub .app .av{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;background:var(--bg);border:1px solid var(--line);font:800 15px var(--display)}#hub .app h3{margin:0;font:800 17px var(--display)}#hub .app .sub{color:var(--muted);font-size:13.5px}",
"#hub .mp{font:800 15px var(--display);padding:4px 10px;border-radius:99px}#hub .mp.yes{background:var(--yes-bg);color:var(--yes)}#hub .mp.mid{background:var(--mid-bg);color:var(--mid)}#hub .mp.no{background:var(--no-bg);color:var(--no)}",
"#hub .app .body{grid-column:2/-1;display:flex;flex-direction:column;gap:8px}#hub .kv{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13.5px}#hub .kv span{color:var(--muted)}#hub .flag{font:600 12px var(--body);padding:3px 9px;border-radius:99px}#hub .flag.ok{background:var(--yes-bg);color:var(--yes)}#hub .flag.bad{background:var(--no-bg);color:var(--no)}#hub .flag.unk{background:var(--mid-bg);color:var(--mid)}",
"#hub .app a{color:var(--accent);font-weight:600}#hub .note{color:var(--muted);font-size:13px;margin:0}",
"#hub .h-empty{text-align:center;padding:30px 16px;color:var(--muted)}#hub .h-empty b{display:block;color:var(--ink);font:800 18px var(--display);margin-bottom:4px}",
"#hub .msg{min-height:1.4em;margin:0;font-weight:600;font-size:14px}#hub .msg.bad{color:var(--no)}#hub .msg.good{color:var(--yes)}",
"#hub .imp{border:2px solid color-mix(in srgb,var(--accent) 35%,var(--line))}#hub .imp .f{gap:8px}#hub .imp input[type=url],#hub .imp textarea{width:100%;padding:11px 12px;border-radius:12px;border:1px solid var(--line);background:var(--surface);color:var(--ink);font:inherit}#hub .imp textarea{resize:vertical}",
"#hub .impok{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;padding:12px 16px;border-radius:14px;background:var(--yes-bg);color:var(--ink);font-size:14px}#hub .impok b{color:var(--yes)}",
"#hub .chipok,#hub .f.filled>label:first-child::after,#hub .f.filled>.l::after{display:inline-block;margin-left:8px;font:600 10.5px var(--mono);padding:2px 7px;border-radius:99px;background:var(--yes-bg);color:var(--yes);vertical-align:middle}#hub .f.filled>label:first-child::after,#hub .f.filled>.l::after{content:'From your post'}",
"#hub .f.filled{border-left:3px solid var(--yes);padding-left:9px}",
"#hub .optn{display:inline-block;margin-bottom:6px;font:600 11px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}",
"#hub .psteps{display:flex;gap:6px;list-style:none;margin:0;padding:0}#hub .psteps li{flex:1;min-width:0}#hub .psteps button{width:100%;min-height:44px;border:1px solid var(--line);border-radius:12px;background:var(--surface);color:var(--muted);font-weight:600;font-size:13.5px;cursor:pointer;padding:6px 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}#hub .psteps button.done{background:var(--yes-bg);color:var(--ink);border-color:transparent}#hub .psteps button[aria-current=step]{background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--accent-ink);border-color:transparent}#hub .psteps button:focus-visible{outline:3px solid var(--accent);outline-offset:2px}",
"#hub .pbar.pnav{position:static;backdrop-filter:none;background:var(--surface)}#hub .pbar.pnav .acts{display:flex;gap:8px;flex-wrap:wrap}",
"#hub .prev{display:flex;flex-direction:column;gap:12px}#hub .prev ul{list-style:none;margin:6px 0 0;padding:0;display:flex;flex-direction:column;gap:8px}#hub .prev li{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;padding:10px 12px;border-radius:12px;border:1px solid var(--line)}#hub .prev .ready{padding:12px 14px;border-radius:12px;background:var(--yes-bg);font-weight:600}#hub .prev dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 14px;margin:0}#hub .prev dt{color:var(--muted)}#hub .prev dd{margin:0;overflow-wrap:anywhere}",
"@media (max-width:560px){#hub .psteps button{font-size:12px;padding:6px 4px}}",
"#hub .orline{display:flex;align-items:center;gap:12px;color:var(--muted);font:600 12px var(--mono);letter-spacing:.06em;text-transform:uppercase}#hub .orline::before,#hub .orline::after{content:'';flex:1;height:1px;background:var(--line)}",
"#hub .h-banner{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;padding:12px 16px;border-radius:14px;background:var(--mid-bg);color:var(--mid);font-weight:600;font-size:14px}",
"@media (max-width:1100px){#hub .pform{grid-template-columns:minmax(0,1fr)}#hub .pside{position:static;order:-1}}",
"@media (max-width:860px){#hub .hub{grid-template-columns:minmax(0,1fr)}#hub .hnav{position:static;flex-direction:row;flex-wrap:nowrap;overflow-x:auto;padding:8px;border-radius:14px}#hub .hnav button.hco{display:none}#hub .hnav button{flex:none}#hub .hnav button.post{margin-top:0}#hub .tiles{grid-template-columns:repeat(2,minmax(0,1fr))}#hub .promise{grid-template-columns:minmax(0,1fr)}}",
"@media (max-width:560px){#hub fieldset{grid-template-columns:minmax(0,1fr)}#hub .perks{grid-template-columns:minmax(0,1fr)}#hub .app{grid-template-columns:auto minmax(0,1fr)}#hub .app .mp{grid-column:2;justify-self:start}}"
].join("\n");

function apply(w,host){
  var d=w.document,A=w.__uaply,hdr=d.getElementById("hdrAcct"),bar=d.querySelector(".bar");
  if(!A||!hdr||!bar)throw new Error("needs the Bottom navigation experiment");
  var esc=A.esc,money=A.money;
  var lp=(host&&host.defaultView&&host.defaultView.location.pathname)||"/",SUPPORT=(/\/(sandbox|dev)\/(index\.html)?$/.test(lp)?"../legal/":"legal/")+"support.html";   /* legal/support.html, one folder up on the hosted copies */
  var KEY=(w.__uaplyKey||"uaply")+".hiring";
  function lsGet(k,def){try{var v=JSON.parse(w.localStorage.getItem(k));return v==null?def:v}catch(e){return def}}
  function lsSet(k,v){try{w.localStorage.setItem(k,JSON.stringify(v))}catch(e){}}
  var st=d.createElement("style");st.textContent=CSS;d.head.appendChild(st);

  /* ================= job seeker side ================= */
  var LOGO_OK=/^(\/api\/employer\/logo\/\d+\?v=[a-f0-9]{6,12}|data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+\/=]+)$/;
  w.__uaplyLogo=function(j){return j&&j.emp&&j.logo&&LOGO_OK.test(j.logo)?'<div class="logo emplogo" aria-hidden="true"><img src="'+j.logo+'" alt=""></div>':""};
  function X(){try{return (w.__uaplyApplyExt?w.__uaplyApplyExt():(A.S.profile.ext||{}))||{}}catch(e){return {}}}
  function fmtMonth(m){if(!/^\d{4}-\d{2}$/.test(m||""))return "";var p=m.split("-");return ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+p[1]-1]+" "+p[0]}
  function gradAsk(g){return g[0]&&g[1]?fmtMonth(g[0])+" to "+fmtMonth(g[1]):g[0]?fmtMonth(g[0])+" or later":"By "+fmtMonth(g[1])}
  /* what an employer posting asks for, checked against this person's own answers. st: 2 met, 1 unknown or soft, 0 not met. must: a requirement, not a preference */
  function elig(j){
    var x=X(),rows=[],us=j.country!=="CA";
    if(us){
      var a=x.auth||"",s;
      if(j.auth==="citizen")s=a==="citizen"?2:(a?0:1);
      else s=(a==="citizen"||a==="authorized")?2:(a==="none"?(j.sponsor==="yes"?1:0):1);
      rows.push({k:"Work in the US",ask:j.auth==="citizen"?"Citizens and permanent residents":"Anyone authorized",have:AUTH_LBL[a]||"Not in your profile",st:s,must:true});
    }else rows.push({k:"Work in Canada",ask:"Authorized to work in Canada",have:"Your profile covers US work only",st:1,must:false});
    if(j.sponsor)rows.push({k:"Visa sponsorship",ask:j.sponsor==="yes"?"Offered":"Not offered",have:x.sponsor==="yes"?"You need it":x.sponsor==="no"?"You don't need it":"Not in your profile",st:j.sponsor==="no"&&x.sponsor==="yes"?0:(x.sponsor?2:1),must:true});
    if(j.gpa)rows.push({k:"GPA",ask:(+j.gpa).toFixed(2)+" or higher",have:x.gpa?"Yours: "+x.gpa:"Not in your profile",st:x.gpa?(+x.gpa>=+j.gpa?2:0):1,must:true});
    if(j.grad&&(j.grad[0]||j.grad[1])){var g=x.grad||"";rows.push({k:"Graduation",ask:gradAsk(j.grad),have:g?fmtMonth(g):"Not in your profile",st:g?((!j.grad[0]||g>=j.grad[0])&&(!j.grad[1]||g<=j.grad[1])?2:0):1,must:true})}
    if(j.majors&&j.majors.length){var mj=String(x.major||"").toLowerCase();rows.push({k:"Major",ask:j.majors.join(", ")+" preferred",have:x.major||"Not in your profile",st:mj&&j.majors.some(function(m){m=m.toLowerCase();return mj.indexOf(m)>-1||m.indexOf(mj)>-1})?2:1,must:false})}
    if(j.start)rows.push({k:"Start date",ask:lbl(START,j.start),have:lbl(START,x.start)||"Not in your profile",st:(x.start===j.start||x.start==="flex"||j.start==="flex")?2:1,must:false});
    var tp=Array.isArray(x.types)?x.types:[],tmap={job:"fulltime",parttime:"parttime",internship:"internship",coop:"coop"};
    if(tp.length)rows.push({k:"Job type",ask:lbl(TYPES,j.type),have:tp.indexOf(tmap[j.type])>-1?"On your list":"Not on your list",st:tp.indexOf(tmap[j.type])>-1?2:1,must:false});
    if(j.reloc&&j.mode!=="remote")rows.push({k:"Relocation",ask:"Help offered",have:A.S.profile.reloc?"You would relocate":"",st:2,must:false});
    return rows;
  }
  function eligible(j){return !elig(j).some(function(r){return r.must&&r.st===0})}
  function initials(n){var p=String(n||"?").trim().split(/\s+/);return ((p[0]||"?").charAt(0)+(p[1]?p[1].charAt(0):"")).toUpperCase()}
  w.__uaplyEmpCard=function(j){
    if(!j||!j.emp)return "";
    var rows=elig(j),h='<div class="empx">';
    if(rows.length)h+='<p class="empx-h">What '+esc(j.co)+' asks for</p><ul class="crit">'+rows.map(function(r){var word=r.st===2?"Met":(r.st===1?"Check":"Not met");return '<li><span class="dot s'+r.st+'" role="img" aria-label="'+word+'">'+(r.st===2?"✓":(r.st===1?"?":"✕"))+'</span><span class="lbl">'+esc(r.k)+'</span><span class="val"><span class="ask">'+esc(r.ask)+'</span>'+(r.have?'<span class="sep"> · </span><em>'+esc(r.have)+'</em>':'')+'</span></li>'}).join("")+'</ul>';
    if(j.manager&&j.manager.name)h+='<div class="team"><span class="tav" aria-hidden="true">'+esc(initials(j.manager.name))+'</span><div><b>Meet the hiring team</b><small>'+esc(j.manager.name)+(j.manager.title?" · "+esc(j.manager.title):"")+'</small></div></div>';
    var perks=(j.perks||[]).map(function(k){return lbl(PERKS,k)}).filter(Boolean);
    h+='<details class="empmore"><summary>About the job and '+esc(j.co)+'</summary>'+
      (j.desc?'<h4>About the job</h4><p>'+esc(j.desc)+'</p>':'')+
      (perks.length?'<h4>Benefits</h4><p>'+esc(perks.join(" · "))+'</p>':'')+
      '<h4>About '+esc(j.co)+'</h4><p class="m">'+esc([j.industry,j.size?j.size+" employees":"",j.country==="CA"?"Canada":"United States"].filter(Boolean).join(" · "))+'</p>'+(j.about?'<p>'+esc(j.about)+'</p>':'')+
      '</details></div>';
    return h;
  };
  /* tapping inside the card's extra section must not start a swipe */
  d.addEventListener("pointerdown",function(e){if(e.target.closest&&e.target.closest(".empmore summary,.empmore"))e.stopPropagation()},true);

  var ELIG_K=KEY+".eligOnly";
  w.__uaplyHideMore=function(j){
    if(j.closed)return true;                                  /* a paused or closed posting never shows as a new card */
    return !!(j.emp&&lsGet(ELIG_K,false)&&!eligible(j));
  };
  (function filterBox(){
    var cnt=d.getElementById("fCount");if(!cnt)return;
    var f=d.createElement("div");
    f.innerHTML='<div class="checks" style="margin-top:8px"><label><input type="checkbox" id="fElig"> Hide jobs I\'m not eligible for</label></div><small>For jobs posted on UAply by employers: uses your work authorization, sponsorship, GPA and graduation date from Profile setup.</small>';
    cnt.parentNode.insertBefore(f,cnt);
    var cb=d.getElementById("fElig");cb.checked=!!lsGet(ELIG_K,false);
    cb.addEventListener("change",function(){lsSet(ELIG_K,cb.checked);A.renderAll()});
  })();

  /* ================= mode switch ================= */
  var ICON_HIRE='<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/></svg>';
  var ICON_SEEK='<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>';
  var sw=d.createElement("button");sw.type="button";sw.id="modeSw";sw.className="modesw";bar.insertBefore(sw,hdr);
  var tag=d.createElement("span");tag.className="modetag";tag.textContent="Hiring";tag.hidden=true;
  var brand=bar.querySelector(".brand");if(brand)brand.appendChild(tag);
  /* the UAply logo goes home: the job search swipe page (leaving Hiring if it is open) */
  function goHome(){
    if(d.body.classList.contains("hire"))setMode(false,true);
    var nb=d.getElementById("nb-svc");
    if(nb){nb.click();var it=d.querySelector('.nwrap[data-k=svc] .nitem[aria-checked="true"]')||d.querySelector(".nwrap[data-k=svc] .nitem");if(it)it.click()}
    var mn=d.querySelector("main");if(mn)mn.scrollTop=0;
  }
  if(brand){
    brand.setAttribute("role","link");brand.tabIndex=0;brand.title="UAply home: jobs";brand.style.cursor="pointer";
    brand.addEventListener("click",goHome);
    brand.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();goHome()}});
  }
  var hub=d.createElement("section");hub.id="hub";hub.hidden=true;hub.setAttribute("aria-label","Hiring");bar.parentNode.insertBefore(hub,bar.nextSibling);
  var MODE_K=KEY+".mode";
  function paintSwitch(hire){
    sw.innerHTML=hire?ICON_SEEK+'<span><span class="lg">Switch to </span>job search</span>':ICON_HIRE+'<span><span class="lg">Switch to </span>hiring</span>';
    sw.setAttribute("aria-label",hire?"Switch to job search":"Switch to hiring: post jobs and review applicants");
  }
  function setMode(hire,quiet){
    d.body.classList.toggle("hire",hire);hub.hidden=!hire;tag.hidden=!hire;paintSwitch(hire);lsSet(MODE_K,hire?"hire":"seek");
    if(hire){load().then(function(){render()})}
    else{if(!quiet)syncDeck();if(w.__uaplyAskConsent)w.__uaplyAskConsent()}
  }
  sw.addEventListener("click",function(){setMode(!d.body.classList.contains("hire"))});
  /* in Hiring mode the job deck is hidden but still the page's current screen: ArrowRight, ArrowLeft and Z used to apply to,
     pass and undo jobs the employer could not see. They now stay with Hiring mode (moving the cursor in a field still works). */
  d.addEventListener("keydown",function(e){
    var k=e.key;if(d.body.classList.contains("hire")&&(k==="ArrowRight"||k==="ArrowLeft"||k==="z"||k==="Z"))e.stopPropagation();
  },true);

  /* ================= data ================= */
  var H={mode:"loading",company:null,jobs:[],apps:[],verified:false,email:"",view:"overview",edit:null,appJob:"all",mustOnly:false,sort:"match",pendingLogo:null,L:null};
  function api(path,body){
    var o=body?{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{credentials:"same-origin"};
    return w.fetch(path,o).then(function(r){return r.json().then(function(j){return {ok:r.ok,status:r.status,j:j||{}}},function(){return {ok:false,status:r.status,j:{}}})},function(){return {ok:false,status:0,j:{}}});
  }
  function load(){
    /* a signed-out visitor is never asked about a company: /api/employer/me would answer 401, which the browser prints in the console
       as a failed request on every page load (testers read it as an error). /api/auth/me answers 200 either way; without a server
       (a static copy) it fails and the company question below finds that out as before. */
    return api("/api/auth/me").then(function(a){
      if(a.ok&&a.j&&a.j.user===null){H.mode="signedout";return}
      return loadMe();
    });
  }
  function loadMe(){
    return api("/api/employer/me").then(function(r){
      if(r.ok){H.mode="server";H.company=r.j.company;H.jobs=r.j.jobs||[];H.apps=r.j.applicants||[];H.verified=!!r.j.verified;H.email=r.j.email||""}
      else if(r.status===401)H.mode="signedout";
      else{H.mode="local";loadLocal()}
    });
  }
  /* ---- this browser only (a static copy has no server) ---- */
  function loadLocal(){
    H.L=lsGet(KEY+".local",null)||{company:null,jobs:[],pipe:{},next:390001};
    H.company=H.L.company;H.jobs=H.L.jobs;H.verified=true;H.email="";H.apps=localApps();
  }
  function saveLocal(){H.L.company=H.company;H.L.jobs=H.jobs;lsSet(KEY+".local",H.L)}
  function localApps(){
    var ids={},out=[];H.jobs.forEach(function(j){ids[j.id]=1});
    var p=A.S.profile,x=X();
    Object.keys(A.S.decisions).forEach(function(id){
      var dd=A.S.decisions[id];if(dd.s!=="applied"||!ids[id])return;
      var pi=(H.L.pipe||{})[id]||{};
      out.push({id:String(id),job:+id,at:Math.round((dd.at||Date.now())/1000),match:dd.pct||0,note:"",name:p.name||"You (test application)",email:x.email||"",phone:x.phone||"",title:p.title||"",loc:p.loc||"",years:p.years||0,edu:p.edu||"",skills:p.skills||[],
        school:x.school||"",major:x.major||"",grad:x.grad||"",gpa:x.gpa||"",auth:x.auth||"",sponsor:x.sponsor||"",start:x.start||"",headline:x.headline||"",summary:x.summary||"",resume:x.resume||"",linkedin:x.linkedin||"",portfolio:x.portfolio||"",stage:pi.stage||"new",private:pi.note||""});
    });
    return out;
  }
  function locOf(j){return j.mode==="remote"?"Remote ("+(j.country==="CA"?"Canada":"US")+")":j.city+", "+j.region+(j.country==="CA"?", Canada":"")}
  function feedOf(j,c){
    return {id:j.id,co:c.name,role:j.role,loc:locOf(j),mode:j.mode,sal:j.sal.slice(),yrs:j.yrs,edu:j.edu,skills:j.skills.slice(),blurb:j.blurb,type:j.type,url:j.url||c.website||"",
      source:"Posted on UAply by "+c.name,apply:"direct",partner:true,live:true,instant:true,local:true,posted:j.posted*1000,perks:j.perks.slice(),comm:j.comm,closed:j.status!=="open",emp:true,
      country:j.country,region:j.region,city:j.city,desc:j.desc,majors:j.majors.slice(),gpa:j.gpa,grad:j.grad.slice(),auth:j.auth,sponsor:j.sponsor,start:j.start,reloc:j.reloc,
      about:c.about||"",industry:c.industry||"",size:c.size||"",website:c.website||"",logo:c.logo||"",manager:j.show_manager&&j.manager.name?{name:j.manager.name,title:j.manager.title}:null};
  }
  /* bring the job seeker deck up to date with what employers posted */
  function syncDeck(){
    if(!w.__uaplyEmpJobs)return;
    if(H.mode==="local"){w.__uaplyEmpJobs.sync(H.company&&H.company.consent?H.jobs.map(function(j){return feedOf(j,H.company)}):[],function(x){return x.emp&&x.local});return}
    if(H.mode!=="server")return;
    w.fetch("/api/jobs").then(function(r){return r.json()}).then(function(data){
      var emp=(data.jobs||[]).filter(function(j){return j.emp});
      w.__uaplyEmpJobs.sync(emp,function(x){return x.emp&&!x.local});
      remember(emp);
    }).catch(function(){});
  }
  /* add employer jobs to the saved copy of the feed that the app reads before it starts, so a swipe on a job posted after the page
     opened is still there after a reload (the app keeps a decision only for a job it knows when it loads) */
  function remember(emp){
    var k=(w.__uaplyKey||"hireswipe")+".live",c=lsGet(k,null);if(!c||!Array.isArray(c.jobs))c={jobs:[]};
    var ids={},now=Date.now();emp.forEach(function(j){ids[j.id]=1});
    c.jobs=c.jobs.filter(function(j){return !(j&&j.emp)||ids[j.id]||A.S.decisions[j.id]}).filter(function(j){return !(j&&ids[j.id])}).concat(emp.map(function(j){return Object.assign({},j,{seen:now})})).slice(-400);
    lsSet(k,c);
  }
  if(lsGet(MODE_K,"seek")!=="hire"){load().then(function(){if(H.mode==="local")syncDeck()})}

  /* ---- the same checks the server makes, so mistakes show at once ---- */
  var EMAIL=/^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/,HTTPS=/^https:\/\/[^\s\/]+\.[^\s]+$/;
  function listOf(v,n,c){var seen={},out=[];String(v||"").split(",").forEach(function(x){x=x.replace(/\s+/g," ").trim().slice(0,c);if(x&&!seen[x.toLowerCase()]){seen[x.toLowerCase()]=1;out.push(x)}});return out.slice(0,n)}
  function checkCompany(p){
    if(p.name.length<2)return ["Enter your company name.","name"];
    if(INDUSTRIES.indexOf(p.industry)<0)return ["Choose your industry.","industry"];
    if(SIZES.indexOf(p.size)<0)return ["Choose how many people work at your company.","size"];
    if(!p.country)return ["Choose the United States or Canada.","country"];
    if(p.website&&!HTTPS.test(p.website))return ["Use a full website address that starts with https://","website"];
    if(!p.consent)return ["Confirm that you may post jobs for this company and receive applications through UAply.","consent"];
    return null;
  }
  function checkJob(p){
    if(p.role.length<2)return ["Enter the job title.","role"];
    if(!p.mode)return ["Choose remote, hybrid or on-site.","mode"];
    if(p.mode!=="remote"&&!(p.city&&p.region))return ["Enter the city and "+(p.country==="CA"?"province":"state")+" where the job is.","city"];
    if(!(p.sal_min>0)||!(p.sal_max>0)||p.sal_max<p.sal_min)return ["Enter the yearly pay range (the most must be at least the least).","sal_min"];
    if(!p.skills.length)return ["Add at least one skill the job needs.","skills"];
    if(p.blurb.length<20)return ["Write a one-line summary for the job card (20 characters or more).","blurb"];
    if(p.gpa&&!(+p.gpa>0&&+p.gpa<=4))return ["GPA is between 0 and 4.0.","gpa"];
    if(p.grad_from&&p.grad_to&&p.grad_to<p.grad_from)return ["The graduation window ends before it starts.","grad_to"];
    if(p.url&&!HTTPS.test(p.url))return ["Use a full link that starts with https://","url"];
    if(p.manager.email&&!EMAIL.test(p.manager.email))return ["Enter the hiring team email as name@company.com","mgr_email"];
    if(p.manager.linkedin&&!/^https:\/\/([a-z]{2,3}\.)?linkedin\.com\/in\/\S+$/.test(p.manager.linkedin))return ["Use the LinkedIn profile link (https://www.linkedin.com/in/...)","mgr_linkedin"];
    return null;
  }

  /* ================= rendering ================= */
  function opt(list,cur,ph){return (ph?'<option value="">'+ph+'</option>':'')+list.map(function(o){var k=Array.isArray(o)?o[0]:o,t=Array.isArray(o)?o[1]:o;return '<option value="'+esc(k)+'"'+(String(cur)===String(k)?" selected":"")+'>'+esc(t)+'</option>'}).join("")}
  function radios(name,list,cur){return '<div class="seg" role="radiogroup">'+list.map(function(o){return '<label><input type="radio" name="'+name+'" value="'+o[0]+'"'+(cur===o[0]?" checked":"")+'> '+esc(o[1])+'</label>'}).join("")+'</div>'}
  function logoBox(c,big){var lg=H.pendingLogo||(c&&c.logo);return '<span class="hlogo"'+(big?' style="width:72px;height:72px;border-radius:16px;font-size:28px"':'')+' aria-hidden="true">'+(lg&&LOGO_OK.test(lg)?'<img src="'+lg+'" alt="">':esc((c&&c.name||"?").charAt(0).toUpperCase()))+'</span>'}
  function tone(p){return p>=80?"yes":(p>=60?"mid":"no")}
  function ago(t){var s=Math.max(0,Date.now()/1000-t);return s<3600?Math.max(1,Math.round(s/60))+" min ago":s<86400?Math.round(s/3600)+" h ago":Math.round(s/86400)+" d ago"}
  function jobById(id){for(var i=0;i<H.jobs.length;i++)if(H.jobs[i].id===+id)return H.jobs[i];return null}
  function counts(){var o={open:0,apps:H.apps.length,week:0,avg:0};H.jobs.forEach(function(j){if(j.status==="open")o.open++});var now=Date.now()/1000,sum=0;H.apps.forEach(function(a){if(now-a.at<7*86400)o.week++;sum+=a.match||0});o.avg=H.apps.length?Math.round(sum/H.apps.length):0;return o}

  function shell(inner){
    var c=H.company,n=counts();
    var nav=[["overview","Overview",""],["jobs","Jobs",H.jobs.length||""],["applicants","Applicants",n.apps||""],["company","Company",""],["billing","Billing",""]];
    return '<div class="hub"><nav class="hnav" aria-label="Hiring sections"><button type="button" class="hco" data-view="company" title="Company profile">'+logoBox(c)+'<span><b>'+esc(c?c.name:"Your company")+'</b><small>'+(c?esc(c.industry||"Employer"):"Set up your company")+'</small></span></button>'+
      nav.map(function(x){return '<button type="button" data-view="'+x[0]+'"'+(H.view===x[0]?' aria-current="page"':'')+'>'+x[1]+(x[2]!==""?'<span class="n">'+x[2]+'</span>':'')+'</button>'}).join("")+
      '<button type="button" class="post" data-act="new">+ Post a job</button><a class="hsupport" data-support="1" href="'+SUPPORT+'" target="_blank" rel="noopener noreferrer" style="display:block;padding:10px 12px;color:var(--muted);font-size:14px">Help and support</a></nav><div class="hmain">'+banner()+inner+'<p class="msg" id="hMsg" role="status" aria-live="polite"></p></div></div>';
  }
  function banner(){
    if(H.mode==="local")return '<div class="h-banner"><span>Preview copy: your company and jobs are saved in this browser only, and your jobs appear in this browser\'s own swipe deck. On the UAply server they are published to everyone.</span></div>';
    if(H.mode==="server"&&!H.verified)return '<div class="h-banner"><span>Verify your email to publish jobs. Applications are sent to '+esc(H.email)+'.</span><button type="button" class="btn sm" data-act="verify">Verify email</button></div>';
    return "";
  }
  function say(m,kind){var e=d.getElementById("hMsg");if(e){e.textContent=m||"";e.className="msg"+(kind?" "+kind:"")}}

  function render(){
    if(H.mode==="loading"){hub.innerHTML='<div class="box h-empty"><b>Loading…</b></div>';return}
    if(H.mode==="signedout"){hub.innerHTML='<div class="box" style="max-width:640px;margin:24px auto"><h1>Hire on UAply</h1><p class="lead">Post a job in a few minutes and get applicants who already match what you ask for. Every applicant arrives with a match score against your requirements.</p>'+
      '<div class="promise"><div><b>One page to post</b><small>Live preview of the card job seekers see.</small></div><div><b>No surprise bills</b><small>Pricing is TBD. When it starts, you see the price before you publish.</small></div><div><b>Close in one click</b><small>A closed job leaves the feed right away.</small></div></div>'+
      '<div class="h-row" style="justify-content:flex-start"><button type="button" class="btn" data-act="signin">Sign in or create an account</button><small class="note">Use the same UAply account you use for job search.</small></div><p class="note"><a data-support="1" href="'+SUPPORT+'" target="_blank" rel="noopener noreferrer">Help and support</a></p></div>';return}
    var v=H.view;
    if(!H.company&&v!=="company"&&v!=="billing")v="welcome";
    var inner=v==="welcome"?welcome():v==="overview"?overview():v==="jobs"?jobsView():v==="post"?postView():v==="applicants"?appsView():v==="company"?companyView():billingView();
    hub.innerHTML=shell(inner);
    if(v==="post"){if(hub.querySelector("#impBox"))wireImport();wirePost()}
    if(v==="company")wireCompany();
    hub.scrollTop=0;
  }
  function welcome(){
    return '<div class="box"><h1>Welcome to Hiring</h1><p class="lead">Three steps, about five minutes. Your company profile is saved once and shown on every job you post.</p>'+
      '<ol class="steps"><li><span class="ck">1</span>Add your company: name, logo, industry, size and where you are.<button type="button" class="btn sm" data-view="company">Add company</button></li><li><span class="ck">2</span>Post a job on one page, with a live preview of the card job seekers swipe.</li><li><span class="ck">3</span>Review applicants, each with a match score and your must-haves checked.</li></ol></div>';
  }
  function overview(){
    var n=counts(),c=H.company;
    var steps=[[!!c,"Company profile","company"],[H.jobs.length>0,"First job posted","new"],[H.mode!=="server"||H.verified,"Email verified (applications go there)","verify"]];
    var h='<div class="h-row"><div><h1>'+esc(c.name)+'</h1><p class="lead">Your hiring at a glance.</p></div><button type="button" class="btn" data-act="new">+ Post a job</button></div>';
    if(steps.some(function(s){return !s[0]}))h+='<div class="box"><h2>Finish setting up</h2><ul class="steps">'+steps.map(function(s){return '<li><span class="ck'+(s[0]?" on":"")+'">'+(s[0]?"✓":"")+'</span>'+s[1]+(s[0]?'':'<button type="button" class="btn ghost sm" '+(s[2]==="new"?'data-act="new"':s[2]==="verify"?'data-act="verify"':'data-view="company"')+'>Do it</button>')+'</li>'}).join("")+'</ul></div>';
    h+='<div class="tiles"><div class="tile"><b>'+n.open+'</b><small>Open jobs</small></div><div class="tile"><b>'+n.apps+'</b><small>Applicants</small></div><div class="tile"><b>'+n.week+'</b><small>New this week</small></div><div class="tile"><b>'+(n.apps?n.avg+"%":"–")+'</b><small>Average match</small></div></div>';
    h+='<div class="box"><div class="h-row"><h2>Your jobs</h2><button type="button" class="linkish" data-view="jobs">See all</button></div>'+jobsTable(H.jobs.slice(0,5))+'</div>';
    var recent=H.apps.slice(0,3);
    h+='<div class="box"><div class="h-row"><h2>Recent applicants</h2><button type="button" class="linkish" data-view="applicants">See all</button></div>'+(recent.length?'<div class="apps">'+recent.map(appCard).join("")+'</div>':'<p class="note">No applicants yet. When someone swipes right on your job, they show up here with their match score.</p>')+'</div>';
    h+='<div class="promise"><div><b>Pay only what you agree to</b><small>Pricing: TBD. One upfront price per job, shown before you publish. No pay-per-click, no auto-renew.</small></div><div><b>Applicants who fit</b><small>Every applicant has a match score, and job seekers can hide jobs they are not eligible for.</small></div><div><b>No ghost jobs</b><small>Pause or close in one click. Closed jobs leave the feed at once.</small></div></div>';
    return h;
  }
  function jobsTable(list){
    if(!list.length)return '<div class="h-empty"><b>No jobs yet</b>Post your first job and it appears in the swipe deck right away.<div style="margin-top:12px"><button type="button" class="btn" data-act="new">+ Post a job</button></div></div>';
    return '<div class="tw"><table><thead><tr><th>Job</th><th>Status</th><th>Applicants</th><th>Posted</th><th></th></tr></thead><tbody>'+list.map(function(j){
      var na=H.apps.filter(function(a){return a.job===j.id}).length;
      return '<tr><td><b>'+esc(j.role)+'</b><br><small class="note">'+esc(lbl(TYPES,j.type))+' · '+esc(locOf(j))+'</small></td><td><span class="st '+j.status+'">'+cap(j.status)+'</span></td><td>'+(na?'<button type="button" class="linkish" data-act="apps" data-id="'+j.id+'">'+na+'</button>':'0')+'</td><td><small>'+new Date(j.posted*1000).toLocaleDateString()+'</small></td>'+
        '<td><div class="acts"><button type="button" class="btn ghost sm" data-act="edit" data-id="'+j.id+'">Edit</button>'+
        (j.status==="open"?'<button type="button" class="btn ghost sm" data-act="status" data-st="paused" data-id="'+j.id+'">Pause</button><button type="button" class="btn ghost sm" data-act="status" data-st="closed" data-id="'+j.id+'">Close</button>':'<button type="button" class="btn ghost sm" data-act="status" data-st="open" data-id="'+j.id+'">Reopen</button>')+
        '<button type="button" class="btn ghost sm" data-act="del" data-id="'+j.id+'">Delete</button></div></td></tr>';
    }).join("")+'</tbody></table></div>';
  }
  function cap(s){return s.charAt(0).toUpperCase()+s.slice(1)}
  function jobsView(){return '<div class="h-row"><div><h1>Jobs</h1><p class="lead">Open jobs show in the swipe deck. Paused and closed jobs are hidden from new job seekers right away.</p></div><button type="button" class="btn" data-act="new">+ Post a job</button></div><div class="box">'+jobsTable(H.jobs)+'</div>'}

  /* ---- post or edit a job ---- */
  function blankJob(){var c=H.company||{};return {role:"",type:"job",mode:"",country:c.country||"US",city:c.city||"",region:c.region||"",sal:[0,0],comm:false,yrs:0,edu:"Bachelor",skills:[],majors:[],gpa:0,grad:["",""],auth:"any",sponsor:"",start:"",reloc:false,perks:[],blurb:"",desc:"",url:"",manager:{name:"",title:"",email:"",linkedin:""},show_manager:true}}
  function F(id,label,inner,o){o=o||{};return '<div class="f'+(o.full?" full":"")+'"><'+(o.group?'span class="l"':'label for="'+id+'"')+'>'+label+(o.req?' <span class="req" aria-hidden="true">*</span>':'')+'</'+(o.group?'span':'label')+'>'+inner+(o.hint?'<small>'+o.hint+'</small>':'')+'<small class="err" id="'+id+'-err" role="alert"></small></div>'}
  /* option 1, above the form: start from the job post they already have */
  function importBox(){
    var t=H.impTab||"link";
    return '<div class="box imp" id="impBox"><div><span class="optn">Option 1 · fastest</span><h2>Start from your existing job post</h2><p class="note" style="margin-top:4px">Paste the link to the job (or its text) and UAply fills in the form below. You check it and publish.</p></div>'+
      '<div class="seg" role="radiogroup" aria-label="How to bring in your job"><label><input type="radio" name="impTab" value="link"'+(t==="link"?" checked":"")+'> Paste a link</label><label><input type="radio" name="impTab" value="text"'+(t==="text"?" checked":"")+'> Paste the job text</label></div>'+
      '<div id="impLinkWrap"'+(t==="link"?"":" hidden")+' class="f"><label for="impUrl">Link to the job</label><div class="h-row" style="flex-wrap:nowrap"><input type="url" id="impUrl" inputmode="url" maxlength="600" placeholder="https://yourcompany.com/careers/marketing-coordinator" value="'+esc(H.impUrl||"")+'" style="flex:1;min-width:0"><button type="button" class="btn" data-act="impLink">Fill it in for me</button></div>'+
        '<small>Works with your careers page, Greenhouse, Lever, Ashby, SmartRecruiters, Workday and most job sites. LinkedIn, Indeed, ZipRecruiter, Glassdoor and Handshake don\'t let other sites read their pages: use Paste the job text for those.</small></div>'+
      '<div id="impTextWrap"'+(t==="text"?"":" hidden")+' class="f"><label for="impText">Job text</label><textarea id="impText" rows="9" maxlength="30000" placeholder="Open your job post, select all of it (title, location, pay, description, requirements, benefits), copy, and paste it here.">'+esc(H.impText||"")+'</textarea><div><button type="button" class="btn" data-act="impText">Fill it in for me</button></div></div>'+
      '<p class="msg" id="impMsg" role="status" aria-live="polite"></p></div>'+
      '<div class="orline" id="manualStart"><span>or</span></div><div><button type="button" class="btn ghost" data-act="manual">Skip this and fill it in myself</button></div>';
  }
  /* Post a job in four named steps. Every field stays in one form, so moving between steps never loses what was typed. */
  var STEP_NAME={1:"Import",2:"The role",3:"Pay and rules",4:"Review"};
  function postSteps(editing){return editing?[2,3,4]:[1,2,3,4]}
  function fieldEl(field){
    var map={role:"jRole",mode:"jMode",city:"jCity",sal_min:"jSalMin",skills:"jSkills",blurb:"jBlurb",gpa:"jGpa",grad_to:"jGradTo",url:"jUrl"};
    var id=map[field]||field;return hub.querySelector("#"+id)||hub.querySelector('input[name="'+id+'"]');
  }
  function needList(p){
    var n=[];
    if(p.role.length<2)n.push(["Job title",2,"jRole"]);
    if(!p.mode)n.push(["Work style",2,"jMode"]);
    if(p.mode&&p.mode!=="remote"&&!(p.city&&p.region))n.push(["City and "+(p.country==="CA"?"province":"state"),2,p.city?"jRegion":"jCity"]);
    if(p.blurb.length<20)n.push(["One-line summary for the card (20 characters or more)",2,"jBlurb"]);
    if(!(p.sal_min>0)||!(p.sal_max>0)||p.sal_max<p.sal_min)n.push(["Yearly pay range",3,"jSalMin"]);
    if(!p.skills.length)n.push(["At least one skill",3,"jSkills"]);
    if(!n.length){var c=checkJob(p);if(c){var el=fieldEl(c[1]),st=el&&el.closest("[data-st]");n.push([c[0],st?+st.getAttribute("data-st"):2,el?(el.id||el.name):""])}}
    return n;
  }
  function reviewHTML(){
    var p=readPost(),n=needList(p),c=H.company||{};
    var where=p.mode==="remote"?"Remote ("+(p.country==="CA"?"Canada":"US")+")":[p.city,p.region].filter(Boolean).join(", ")||"Not set";
    var md=MODES.filter(function(m){return m[0]===p.mode})[0];
    var rows=[["Job",p.role||"Not set"],["Company",c.name||""],["Work style",md?md[1]:"Not set"],["Where",where],
      ["Pay",p.sal_max>0?money(p.sal_min)+" to "+money(p.sal_max)+" a year":"Not set"],["Skills",p.skills.join(", ")||"Not set"],["Benefits",p.perks.length?p.perks.length+" ticked":"None ticked"],["Hiring team",p.manager.name||"Not added"]];
    return '<div><h2>Review</h2><p class="note">Check the job, then publish. You can edit, pause or close it any time.</p></div>'+
      (n.length?'<div><b>Still needed before you publish</b><ul>'+n.map(function(x){return '<li><span>'+esc(x[0])+'</span><button type="button" class="btn ghost sm" data-act="fix" data-s="'+x[1]+'" data-f="'+esc(x[2])+'">Fix in '+STEP_NAME[x[1]]+'</button></li>'}).join("")+'</ul></div>':'<div class="ready" role="status">✓ Everything needed is filled in. Ready to publish.</div>')+
      '<dl>'+rows.map(function(r){return '<dt>'+r[0]+'</dt><dd>'+esc(r[1])+'</dd>'}).join("")+'</dl>';
  }
  function goStep(s,focusId){
    var f=hub.querySelector("#pForm");if(!f)return;
    var editing=!!(H.edit&&H.edit.id),ST=postSteps(editing);if(ST.indexOf(s)<0)s=ST[0];
    if(s===1){H.edit=null;H.filled=null;H.manual=false;H.step=1;render();return}       /* back to Import: start over from a link or text */
    H.step=s;f.hidden=false;
    [].slice.call(f.querySelectorAll("[data-st]")).forEach(function(x){x.hidden=+x.getAttribute("data-st")!==s});
    if(s===4)f.querySelector("#pReview").innerHTML=reviewHTML();
    [].slice.call(hub.querySelectorAll(".psteps button")).forEach(function(b){var k=+b.getAttribute("data-s");if(k===s)b.setAttribute("aria-current","step");else b.removeAttribute("aria-current");b.classList.toggle("done",k<s);b.textContent=(k<s?"✓ ":(ST.indexOf(k)+1)+" ")+STEP_NAME[k]});
    var i=ST.indexOf(s);
    f.querySelector("#pStepN").innerHTML="Step "+(i+1)+" of "+ST.length+' <small class="note">· price to post: TBD, no card needed</small>';
    f.querySelector("#pBack").hidden=i===0;
    var nx=f.querySelector("#pNext");nx.hidden=s===4;if(s<4)nx.textContent="Next: "+STEP_NAME[ST[i+1]];
    f.querySelector("#jSubmit").hidden=s!==4;
    var top=hub.querySelector(".psteps");if(top&&top.scrollIntoView)top.scrollIntoView({block:"start"});
    if(focusId){var el=hub.querySelector("#"+focusId)||hub.querySelector('input[name="'+focusId+'"]');if(el){try{el.focus()}catch(x){}}}
  }
  function postView(){
    var j=H.edit||blankJob(),editing=!!(H.edit&&H.edit.id);
    var yrs=[[0,"No minimum"]];for(var i=1;i<=15;i++)yrs.push([i,i+"+ years"]);
    var gpa=j.gpa?(+j.gpa).toFixed(2):"";
    var got=H.filled||{},n=Object.keys(got).length,need=[["mode","work style"],["city","city and state (the post names no US or Canada location)"],["sal","pay range"],["skills","skills"],["blurb","one-line summary"]].filter(function(x){return !got[x[0]]&&!(x[0]==="city"&&j.mode==="remote")}).map(function(x){return x[1]});
    var ST=postSteps(editing),cur=H.step&&ST.indexOf(H.step)>-1?H.step:ST[0];H.step=cur;
    return '<div><h1>'+(editing?"Edit job":"Post a job")+'</h1><p class="lead">'+(editing?'One page. Each section is matched to what job seekers fill in, so the right people see your job and their match score is fair.':'Bring in a job you already posted, or fill it in yourself. Each section is matched to what job seekers fill in.')+'</p></div>'+
    '<ol class="psteps" aria-label="Steps">'+ST.map(function(s){return '<li><button type="button" data-act="step" data-s="'+s+'"'+(s===cur?' aria-current="step"':'')+(s<cur?' class="done"':'')+'>'+(s<cur?'✓ ':(ST.indexOf(s)+1)+' ')+STEP_NAME[s]+'</button></li>'}).join("")+'</ol>'+
    (editing?'':H.filled?'<div class="impok" role="status"><div><b>✓ Filled '+n+' field'+(n===1?"":"s")+' from '+esc(H.impFrom||"your post")+'.</b> Fields marked <span class="chipok">From your post</span> came from it. Check them, then fill in the rest.'+(need.length?' <b>Still needed:</b> '+esc(need.join(", "))+'.':'')+'</div><button type="button" class="btn ghost sm" data-act="reimport">Use a different link</button></div>':cur===1?importBox():'')+
    '<form id="pForm" class="pform" novalidate'+(cur===1?' hidden':'')+'><div style="display:flex;flex-direction:column;gap:16px;min-width:0">'+
    '<fieldset data-st="2"><legend>The role</legend><p class="match">Matched to the job seeker\'s <b>target titles</b>, <b>opportunity types</b>, <b>work style</b>, <b>city and commute distance</b> and <b>willingness to relocate</b>.</p>'+
      F("jRole","Job title",'<input type="text" id="jRole" maxlength="120" value="'+esc(j.role)+'" placeholder="Marketing Coordinator">',{req:1,full:1})+
      F("jType","Job type",radios("jType",TYPES,j.type),{req:1,full:1,group:1})+
      F("jMode","Work style",radios("jMode",MODES,j.mode),{req:1,full:1,group:1})+
      F("jCountry","Country",radios("jCountry",COUNTRIES,j.country),{req:1,full:1,group:1})+
      '<div class="f" id="jCityWrap"><label for="jCity">City <span class="req" aria-hidden="true">*</span></label><input type="text" id="jCity" maxlength="60" value="'+esc(j.city)+'" placeholder="Philadelphia"><small class="err" id="jCity-err" role="alert"></small></div>'+
      '<div class="f" id="jRegionWrap"><label for="jRegion" id="jRegionL">State</label><select id="jRegion"></select></div>'+
      '<div class="f full" id="jRelocWrap"><label class="ckline"><input type="checkbox" id="jReloc"'+(j.reloc?" checked":"")+'> We help with relocation</label></div></fieldset>'+
    '<fieldset data-st="3"><legend>Pay</legend><p class="match">Matched to the job seeker\'s <b>minimum salary</b>, the <b>salary dealbreaker</b> and the <b>commission-only</b> filter.</p>'+
      F("jSalMin","Lowest yearly pay (USD)",'<input type="number" id="jSalMin" min="0" step="1000" inputmode="numeric" value="'+(j.sal[0]||"")+'" placeholder="55000">',{req:1})+
      F("jSalMax","Highest yearly pay (USD)",'<input type="number" id="jSalMax" min="0" step="1000" inputmode="numeric" value="'+(j.sal[1]||"")+'" placeholder="70000">',{req:1,hint:"Paid hourly? Multiply by 2,080 (40 hours × 52 weeks)."})+
      '<div class="f full"><label class="ckline"><input type="checkbox" id="jComm"'+(j.comm?" checked":"")+'> This role is paid by commission only</label></div></fieldset>'+
    '<fieldset data-st="3"><legend>Who it\'s for</legend><p class="match">Matched to the job seeker\'s <b>years of experience</b>, <b>experience level</b>, <b>education</b>, <b>skills</b>, <b>major</b>, <b>GPA</b> and <b>graduation date</b>.</p>'+
      F("jYrs","Minimum experience",'<select id="jYrs">'+opt(yrs,j.yrs)+'</select>',{req:1})+
      F("jEdu","Minimum education",'<select id="jEdu">'+opt(LEVELS,j.edu)+'</select>',{req:1})+
      F("jSkills","Skills the job needs",'<input type="text" id="jSkills" maxlength="300" value="'+esc(j.skills.join(", "))+'" placeholder="Excel, Customer service, SQL">',{req:1,full:1,hint:'Up to 6, separated by commas. These drive 40% of the match score. <span id="jSkillsN"></span>'})+
      F("jMajors","Preferred majors",'<input type="text" id="jMajors" maxlength="300" value="'+esc(j.majors.join(", "))+'" placeholder="Marketing, Communications">',{full:1,hint:"Optional. A preference, never a hard rule."})+
      F("jGpa","Minimum GPA",'<input type="number" id="jGpa" min="0" max="4" step="0.1" inputmode="decimal" value="'+gpa+'" placeholder="3.0">',{hint:"Optional, out of 4.0."})+
      '<div class="f"><span class="l">Graduation window</span><div style="display:flex;gap:6px;align-items:center"><input type="month" id="jGradFrom" aria-label="Graduating from" value="'+esc(j.grad[0])+'"><span>to</span><input type="month" id="jGradTo" aria-label="Graduating by" value="'+esc(j.grad[1])+'"></div><small>Optional. Useful for internships and new graduate roles.</small><small class="err" id="jGradTo-err" role="alert"></small></div></fieldset>'+
    '<fieldset data-st="3"><legend>Eligibility</legend><p class="match">Matched to the job seeker\'s <b>work authorization</b>, <b>visa sponsorship</b> and <b>earliest start</b>. Job seekers can hide jobs they are not eligible for.</p>'+
      F("jAuth","Who can apply",radios("jAuth",[["any","Anyone authorized to work here, including visa and OPT holders"],["citizen","Citizens and permanent residents only"]],j.auth),{full:1,group:1})+
      F("jSponsor","Visa sponsorship",radios("jSponsor",[["yes","We sponsor"],["no","We don't sponsor"],["","Not decided"]],j.sponsor),{full:1,group:1})+
      F("jStart","When should the hire start?",'<select id="jStart">'+opt(START,j.start)+'</select>')+'</fieldset>'+
    '<fieldset data-st="3"><legend>Benefits</legend><p class="match">Matched to the job seeker\'s <b>Benefits</b> filter. Tick only what you really offer.</p><div class="perks f full">'+PERKS.map(function(p){return '<label><input type="checkbox" data-perk="'+p[0]+'"'+(j.perks.indexOf(p[0])>-1?" checked":"")+'> '+esc(p[1])+'</label>'}).join("")+'</div></fieldset>'+
    '<fieldset data-st="2"><legend>Describe the job</legend>'+
      F("jBlurb","One-line summary for the card",'<input type="text" id="jBlurb" maxlength="220" value="'+esc(j.blurb)+'" placeholder="Plan and run campaigns for our three Philadelphia stores."><span class="cnt" id="jBlurbN"></span>',{req:1,full:1})+
      F("jDesc","Full description",'<textarea id="jDesc" maxlength="5000" rows="7" placeholder="What the hire will do, who they work with, what success looks like in 90 days.">'+esc(j.desc)+'</textarea><span class="cnt" id="jDescN"></span>',{full:1,hint:"Shown under About the job when a job seeker opens the card."})+
      F("jUrl","Link to this job on your site",'<input type="text" id="jUrl" inputmode="url" maxlength="300" value="'+esc(j.url)+'" placeholder="https://yourcompany.com/careers/...">',{full:1,hint:"Optional. Applications through UAply come to your email either way."})+'</fieldset>'+
    '<fieldset data-st="2"><legend>Meet the hiring team</legend><p class="match">Plus and Pro job seekers can choose to send the hiring team a short message with their application. The email and LinkedIn are never shown publicly.</p>'+
      F("jMgrName","Name",'<input type="text" id="jMgrName" maxlength="80" value="'+esc(j.manager.name)+'" placeholder="Dana Ortiz">')+
      F("jMgrTitle","Title",'<input type="text" id="jMgrTitle" maxlength="80" value="'+esc(j.manager.title)+'" placeholder="Marketing Manager">')+
      F("mgr_email","Email",'<input type="email" id="mgr_email" maxlength="120" value="'+esc(j.manager.email)+'" placeholder="dana@yourcompany.com">')+
      F("mgr_linkedin","LinkedIn",'<input type="text" id="mgr_linkedin" inputmode="url" maxlength="200" value="'+esc(j.manager.linkedin)+'" placeholder="https://www.linkedin.com/in/...">')+
      '<div class="f full"><label class="ckline"><input type="checkbox" id="jShowMgr"'+(j.show_manager?" checked":"")+'> Show the name and title on the job card under "Meet the hiring team"</label></div></fieldset>'+
    '<div class="box prev" data-st="4" id="pReview"></div>'+
    '<div class="pbar pnav"><span class="price" id="pStepN"></span><div class="acts"><button type="button" class="btn ghost" data-act="back" id="pBack">Back</button><button type="button" class="btn ghost" data-view="jobs">Cancel</button><button type="button" class="btn" data-act="next" id="pNext">Next</button><button type="submit" class="btn" id="jSubmit">'+(editing?"Save changes":"Publish job")+'</button></div></div>'+
    '</div><aside class="pside" aria-label="Preview"><div><h2>Preview</h2><p class="note">What job seekers see on the swipe card.</p></div><div id="pPrev"></div></aside></form>';
  }
  function readPost(){
    var f=hub.querySelector("#pForm");function v(id){var e=f.querySelector("#"+id);return e?e.value.trim():""}function r(n){var e=f.querySelector('input[name="'+n+'"]:checked');return e?e.value:""}function c(id){var e=f.querySelector("#"+id);return !!(e&&e.checked)}
    var mode=r("jMode");
    return {id:H.edit&&H.edit.id||undefined,role:v("jRole").replace(/\s+/g," "),type:r("jType")||"job",mode:mode,country:r("jCountry")||"US",city:v("jCity"),region:v("jRegion"),
      sal_min:+v("jSalMin")||0,sal_max:+v("jSalMax")||0,comm:c("jComm"),yrs:+v("jYrs")||0,edu:v("jEdu"),skills:listOf(v("jSkills"),6,40),majors:listOf(v("jMajors"),6,60),
      gpa:v("jGpa"),grad_from:v("jGradFrom"),grad_to:v("jGradTo"),auth:r("jAuth")||"any",sponsor:r("jSponsor"),start:v("jStart"),reloc:mode!=="remote"&&c("jReloc"),
      perks:[].slice.call(f.querySelectorAll("[data-perk]")).filter(function(x){return x.checked}).map(function(x){return x.getAttribute("data-perk")}),
      blurb:v("jBlurb").replace(/\s+/g," "),desc:v("jDesc"),url:v("jUrl"),manager:{name:v("jMgrName"),title:v("jMgrTitle"),email:v("mgr_email").toLowerCase(),linkedin:v("mgr_linkedin")},show_manager:c("jShowMgr")};
  }
  function asJob(p){return {role:p.role,type:p.type,mode:p.mode||"remote",country:p.country,city:p.city,region:p.region,sal:[p.sal_min,p.sal_max],comm:p.comm,yrs:p.yrs,edu:p.edu,skills:p.skills,majors:p.majors,gpa:+p.gpa||0,grad:[p.grad_from,p.grad_to],auth:p.auth,sponsor:p.sponsor,start:p.start,reloc:p.reloc,perks:p.perks,blurb:p.blurb,desc:p.desc,url:p.url,manager:p.manager,show_manager:p.show_manager&&!!p.manager.name}}
  function preview(){
    var p=readPost(),j=asJob(p),c=H.company||{name:"Your company"},box=hub.querySelector("#pPrev");if(!box)return;
    var fj=feedOf(Object.assign({id:0,status:"open",posted:Date.now()/1000},j),c);
    var pay=j.sal[1]>0?money(j.sal[0])+"–"+money(j.sal[1])+"<small>per year</small>":"<small>Add the pay range</small>";
    var req=elig(fj).filter(function(r){return r.must}).map(function(r){return '<li><span>'+esc(r.k)+':</span> '+esc(r.ask)+'</li>'});
    if(j.yrs)req.unshift('<li><span>Experience:</span> '+j.yrs+'+ years</li>');req.unshift('<li><span>Education:</span> '+esc(j.edu)+' or higher</li>');
    box.innerHTML='<div class="pv"><div class="pv-h">'+logoBox(c)+'<div><b>'+esc(j.role||"Job title")+'</b><small>'+esc(c.name)+'</small></div></div><div class="pv-pay">'+pay+'</div>'+
      '<div class="facts"><span>'+esc(j.mode==="remote"||!j.city?locOf(Object.assign({},j,{mode:j.city?j.mode:"remote"})):locOf(j))+'</span><span>'+esc(lbl(MODES,j.mode)||"Work style")+'</span><span>'+esc(lbl(TYPES,j.type))+'</span>'+(j.comm?'<span>Commission only</span>':'')+'</div>'+
      (j.skills.length?'<div class="chips">'+j.skills.map(function(s){return '<span class="chip">'+esc(s)+'</span>'}).join("")+'</div>':'')+
      '<p>'+esc(j.blurb||"Your one-line summary shows here.")+'</p><ul class="pvlist">'+req.join("")+'</ul>'+
      (j.show_manager?'<div class="team"><span class="tav" aria-hidden="true">'+esc(initials(j.manager.name))+'</span><div><b>Meet the hiring team</b><small>'+esc(j.manager.name)+(j.manager.title?" · "+esc(j.manager.title):"")+'</small></div></div>':'')+
      '</div><p class="note">Job seekers also see a match score from 0 to 100% for their own profile, and can open About the job and '+esc(c.name)+'.</p>';
  }
  function wirePost(){
    var f=hub.querySelector("#pForm");
    function regions(){
      var country=(f.querySelector('input[name="jCountry"]:checked')||{}).value||"US",sel=f.querySelector("#jRegion"),cur=sel.value||(H.edit||blankJob()).region;
      sel.innerHTML=opt(REGIONS[country],cur,country==="CA"?"Choose a province":"Choose a state");
      f.querySelector("#jRegionL").innerHTML=(country==="CA"?"Province":"State")+' <span class="req" aria-hidden="true">*</span>';
    }
    function where(){
      var m=(f.querySelector('input[name="jMode"]:checked')||{}).value;
      var remote=m==="remote";f.querySelector("#jRelocWrap").hidden=remote;
      f.querySelector("#jCityWrap").querySelector("label").innerHTML="City"+(remote?' <small>(optional for remote)</small>':' <span class="req" aria-hidden="true">*</span>');
    }
    function counters(){
      f.querySelector("#jBlurbN").textContent=f.querySelector("#jBlurb").value.length+" / 220";
      f.querySelector("#jDescN").textContent=f.querySelector("#jDesc").value.length+" / 5000";
      var n=listOf(f.querySelector("#jSkills").value,99,40).length;f.querySelector("#jSkillsN").textContent=n?"("+Math.min(n,6)+" of 6"+(n>6?", only the first 6 are kept":"")+")":"";
    }
    regions();where();counters();preview();
    if(H.filled){       /* mark what came from their post, so they know what to check */
      var MAP={role:"#jRole",type:'input[name="jType"]',mode:'input[name="jMode"]',country:'input[name="jCountry"]',city:"#jCity",region:"#jRegion",sal:"#jSalMin",comm:"#jComm",yrs:"#jYrs",edu:"#jEdu",skills:"#jSkills",majors:"#jMajors",gpa:"#jGpa",grad:"#jGradFrom",auth:'input[name="jAuth"]',sponsor:'input[name="jSponsor"]',start:"#jStart",reloc:"#jReloc",perks:".perks",blurb:"#jBlurb",desc:"#jDesc",url:"#jUrl"};
      Object.keys(H.filled).forEach(function(k){var e=MAP[k]&&f.querySelector(MAP[k]);var box=e&&(e.classList.contains("f")?e:e.closest(".f"));if(box)box.classList.add("filled");if(k==="sal"){var mx=f.querySelector("#jSalMax");if(mx)mx.closest(".f").classList.add("filled")}});
    }
    var t=null;
    f.addEventListener("input",function(){counters();clearTimeout(t);t=setTimeout(preview,120)});
    f.addEventListener("change",function(e){if(e.target.name==="jCountry")regions();if(e.target.name==="jMode")where();preview()});
    f.addEventListener("submit",function(e){e.preventDefault();if(H.step<4){var STs=postSteps(!!(H.edit&&H.edit.id));goStep(STs[STs.indexOf(H.step)+1]);return}submitJob()});
    if(H.step!==1)goStep(H.step);
  }
  /* ---- step 1: bring in an existing post ---- */
  function wireImport(){
    var box=hub.querySelector("#impBox");
    box.addEventListener("change",function(e){if(e.target.name==="impTab"){H.impTab=e.target.value;box.querySelector("#impLinkWrap").hidden=H.impTab!=="link";box.querySelector("#impTextWrap").hidden=H.impTab!=="text";(box.querySelector(H.impTab==="link"?"#impUrl":"#impText")).focus()}});
    box.addEventListener("keydown",function(e){if(e.key==="Enter"&&e.target.id==="impUrl"){e.preventDefault();runImport("link")}});
    box.addEventListener("input",function(e){if(e.target.id==="impUrl")H.impUrl=e.target.value;if(e.target.id==="impText")H.impText=e.target.value});
  }
  function impSay(m,kind){var e=hub.querySelector("#impMsg");if(e){e.textContent=m||"";e.className="msg"+(kind?" "+kind:"")}}
  function toText(m){       /* switch to "Paste the job text" in place, so nothing typed in the form below is lost */
    H.impTab="text";var box=hub.querySelector("#impBox");if(!box)return;
    var r=box.querySelector('input[name="impTab"][value="text"]');if(r)r.checked=true;
    box.querySelector("#impLinkWrap").hidden=true;box.querySelector("#impTextWrap").hidden=false;
    impSay(m,"bad");var t=box.querySelector("#impText");if(t)t.focus();
  }
  function jobFromFields(fd){
    var j=blankJob();
    ["role","type","mode","country","city","region","edu","auth","sponsor","start","blurb","desc","url"].forEach(function(k){if(fd[k]!=null&&fd[k]!=="")j[k]=fd[k]});
    if(fd.sal_min)j.sal=[fd.sal_min,fd.sal_max];if(fd.yrs!=null)j.yrs=fd.yrs;if(fd.skills)j.skills=fd.skills.slice(0,6);if(fd.majors)j.majors=fd.majors.slice(0,6);
    if(fd.gpa)j.gpa=+fd.gpa;if(fd.grad_from||fd.grad_to)j.grad=[fd.grad_from||"",fd.grad_to||""];if(fd.perks)j.perks=fd.perks.slice();if(fd.comm)j.comm=true;if(fd.reloc)j.reloc=true;
    if(!fd.city){j.city="";j.region=""}       /* the post names no US or Canada place: leave it empty rather than show the company's own city as if it came from the post */
    if(j.region&&!REGIONS[j.country||"US"].some(function(r){return r[0]===j.region}))j.region="";
    return j;
  }
  function useResult(res,from){
    var n=Object.keys(res.got).length;
    if(n<3){impSay("We could only find "+n+" detail"+(n===1?"":"s")+" in that. Try pasting the full job text, or fill it in yourself.","bad");return}
    H.edit=jobFromFields(res.fields);H.filled=res.got;H.impFrom=from;H.manual=true;H.step=2;render();
    say("Filled "+n+" fields from "+from+". Check them, then publish.","good");
  }
  function runImport(kind){
    if(kind==="text"){
      var txt=(hub.querySelector("#impText")||{}).value||"";
      if(txt.trim().length<80){impSay("Paste the whole job post: title, location, pay, description and requirements.","bad");return}
      useResult(IMP.fromText(txt,""),"your pasted text");return;
    }
    var url=((hub.querySelector("#impUrl")||{}).value||"").trim();if(url&&!/^https?:\/\//i.test(url))url="https://"+url;
    var host="";try{host=new URL(url).hostname}catch(e){impSay("Paste the full link to the job, starting with https://","bad");return}
    var no=IMP.blocked(host);
    if(no){toText(no+" doesn't let other sites read its pages. Open your post on "+no+", select all of it, copy, and paste it here.");return}
    impSay("Reading your job post…");
    var btn=hub.querySelector('[data-act="impLink"]');if(btn)btn.disabled=true;
    function done(){if(btn)btn.disabled=false}
    var feed=IMP.feedFor(url);
    function viaServer(){
      if(H.mode!=="server"){done();toText("This preview copy can't open that website. Copy the job text from it and paste it here (on the UAply server, links like this are read for you).");return}
      api("/api/employer/import",{url:url}).then(function(r){done();
        if(!r.ok){if(r.j.code==="no_read"||r.j.code==="fetch"||r.j.code==="empty"){toText(r.j.error);return}impSay(r.j.error||"That link could not be read.","bad");return}
        var res=r.j.jsonld?IMP.fromJsonLd(r.j.jsonld,r.j.url||url):IMP.fromText((r.j.title?r.j.title+"\n":"")+r.j.text,r.j.url||url);
        useResult(res,host.replace(/^www\./,""));
      });
    }
    if(!feed){viaServer();return}
    var apis=feed.apis||[feed.api];
    (function tryNext(i){       /* the job's public feed answers the browser directly; a career page may need a second guess at the board name */
      if(i>=apis.length){viaServer();return}
      var ctl=w.AbortController?new w.AbortController():null,timer=ctl&&setTimeout(function(){ctl.abort()},12000);   /* a slow job site gives up after 12 seconds instead of hanging */
      w.fetch(apis[i],ctl?{signal:ctl.signal}:{}).then(function(r){if(!r.ok)throw new Error("HTTP "+r.status);return r.json()}).then(function(j){clearTimeout(timer);done();useResult(feed.read(j,url),feed.kind)}).catch(function(e){
        clearTimeout(timer);
        if(/not found on this/i.test(e.message||"")){done();impSay(e.message,"bad");return}
        if(e.name==="AbortError"){done();impSay(feed.kind+" took too long to answer. Try again, or paste the job text instead.","bad");return}
        tryNext(i+1);
      });
    })(0);
  }
  function showErr(field,msg){
    hub.querySelectorAll("[aria-invalid=true]").forEach(function(x){x.removeAttribute("aria-invalid")});hub.querySelectorAll(".err").forEach(function(x){x.textContent=""});
    var map={role:"jRole",mode:"jMode",city:"jCity",sal_min:"jSalMin",skills:"jSkills",blurb:"jBlurb",gpa:"jGpa",grad_to:"jGradTo",url:"jUrl",name:"cName",industry:"cIndustry",size:"cSize",country:"cCountry",website:"cWebsite",consent:"cConsent",logo:"cLogoF"};
    var id=map[field]||field,el=hub.querySelector("#"+id)||hub.querySelector('input[name="'+id+'"]'),er=hub.querySelector("#"+id+"-err");
    var st=el&&el.closest&&el.closest("[data-st]");if(st&&st.hidden)goStep(+st.getAttribute("data-st"));
    if(er)er.textContent=msg;if(el){el.setAttribute("aria-invalid","true");el.scrollIntoView({block:"center",behavior:"smooth"});try{el.focus({preventScroll:true})}catch(x){}}
    say(msg,"bad");
  }
  function submitJob(){
    var p=readPost(),bad=checkJob(p);if(bad){showErr(bad[1],bad[0]);return}
    var btn=hub.querySelector("#jSubmit");btn.disabled=true;say(p.id?"Saving…":"Publishing…");
    if(H.mode==="server"){
      api("/api/employer/job",p).then(function(r){btn.disabled=false;
        if(!r.ok){if(r.j.code==="company"){H.view="company";render();return}showErr(r.j.field||"",r.j.error||"Could not save. Try again.");return}
        afterSave(p.id?"Saved.":"Published. It is in the swipe deck now.");
      });return;
    }
    var j=asJob(p),now=Math.round(Date.now()/1000);
    if(p.id){var cur=jobById(p.id);Object.assign(cur,j,{updated:now})}
    else{H.jobs.unshift(Object.assign(j,{id:H.L.next++,status:"open",posted:now,updated:now}))}
    saveLocal();afterSave(p.id?"Saved.":"Published. Switch to job search to see it in your deck.");
  }
  function afterSave(m){H.edit=null;H.view="jobs";(H.mode==="server"?load():Promise.resolve()).then(function(){render();say(m,"good");syncDeck()})}

  /* ---- applicants ---- */
  function appFlags(a,j){
    var f=[];if(!j)return f;
    var x={gpa:a.gpa,grad:a.grad};
    if(j.auth==="citizen")f.push(a.auth==="citizen"?["ok","Citizen or permanent resident"]:a.auth?["bad","Not a citizen or permanent resident"]:["unk","Work authorization not given"]);
    else f.push(a.auth==="citizen"||a.auth==="authorized"?["ok","Authorized to work"]:a.auth==="none"?["bad","Not authorized to work"]:["unk","Work authorization not given"]);
    if(a.sponsor==="yes")f.push(j.sponsor==="no"?["bad","Needs sponsorship (you don't sponsor)"]:["unk","Needs sponsorship"]);
    if(j.gpa)f.push(x.gpa?(+x.gpa>=j.gpa?["ok","GPA "+x.gpa]:["bad","GPA "+x.gpa+" (below "+j.gpa+")"]):["unk","GPA not given"]);
    if(j.grad&&(j.grad[0]||j.grad[1]))f.push(x.grad?((!j.grad[0]||x.grad>=j.grad[0])&&(!j.grad[1]||x.grad<=j.grad[1])?["ok","Graduates "+fmtMonth(x.grad)]:["bad","Graduates "+fmtMonth(x.grad)+" (outside your window)"]):["unk","Graduation date not given"]);
    return f;
  }
  function meetsAll(a){return !appFlags(a,jobById(a.job)).some(function(f){return f[0]==="bad"})}
  function appCard(a){
    var j=jobById(a.job),have=(a.skills||[]).map(function(s){return String(s).toLowerCase()});
    var links=[["Resume",a.resume],["LinkedIn",a.linkedin],["Portfolio",a.portfolio]].filter(function(l){return /^https:\/\//.test(l[1]||"")});
    return '<div class="box app" data-app="'+esc(a.id)+'"><span class="av" aria-hidden="true">'+esc(initials(a.name))+'</span><div><h3>'+esc(a.name||"Applicant")+'</h3><div class="sub">'+esc([a.title,a.years?a.years+(+a.years===1?" year":" years"):"",a.edu].filter(Boolean).join(" · "))+(j?' · applied to <b>'+esc(j.role)+'</b>':'')+' · '+ago(a.at)+'</div></div>'+
      '<span class="mp '+tone(a.match)+'" title="Match score against this job">'+(a.match||0)+'%</span><div class="body">'+
      '<div class="kv">'+appFlags(a,j).map(function(f){return '<span class="flag '+f[0]+'">'+esc(f[1])+'</span>'}).join("")+'</div>'+
      ((a.school||a.major||a.grad)?'<div class="kv"><span>Education</span>'+esc([a.school,a.major,a.grad?"class of "+fmtMonth(a.grad):""].filter(Boolean).join(" · "))+'</div>':'')+
      (j&&j.skills.length?'<div class="kv"><span>Skills you asked for</span>'+j.skills.map(function(s){var ok=have.indexOf(s.toLowerCase())>-1;return '<span class="flag '+(ok?"ok":"unk")+'">'+(ok?"✓ ":"")+esc(s)+'</span>'}).join("")+'</div>':'')+
      (a.headline||a.summary?'<p class="note">'+esc(a.headline||a.summary)+'</p>':'')+
      (a.note?'<p class="note"><b>Their message:</b> '+esc(a.note)+'</p>':'')+
      '<div class="kv">'+(a.email?'<span>Email</span><b>'+esc(a.email)+'</b>':'')+(a.phone?'<span>Phone</span><b>'+esc(a.phone)+'</b>':'')+links.map(function(l){return '<a href="'+esc(l[1])+'" target="_blank" rel="noopener noreferrer">'+l[0]+' ↗</a>'}).join("")+'</div>'+
      '<div class="h-row" style="justify-content:flex-start"><label class="note" for="stg-'+esc(a.id)+'">Stage</label><select id="stg-'+esc(a.id)+'" data-stage="'+esc(a.id)+'" style="padding:7px 10px;border-radius:9px;border:1px solid var(--line);background:var(--surface);color:var(--ink)">'+opt(STAGES,a.stage||"new")+'</select>'+
      '<input type="text" data-pnote="'+esc(a.id)+'" maxlength="1000" value="'+esc(a.private||"")+'" placeholder="Private note (only your team sees it)" aria-label="Private note" style="flex:1;min-width:180px;padding:7px 10px;border-radius:9px;border:1px solid var(--line);background:var(--surface);color:var(--ink)"></div>'+
      '</div></div>';
  }
  function appsView(){
    var list=H.apps.filter(function(a){return (H.appJob==="all"||a.job===+H.appJob)&&(!H.mustOnly||meetsAll(a))});
    list.sort(H.sort==="match"?function(a,b){return (b.match||0)-(a.match||0)}:function(a,b){return b.at-a.at});
    return '<div><h1>Applicants</h1><p class="lead">Everyone who swiped right on your jobs, with what they agreed to share. Highest match first.</p></div>'+
      '<div class="box"><div class="h-row" style="justify-content:flex-start"><select id="aJob" aria-label="Job" style="padding:8px 10px;border-radius:10px;border:1px solid var(--line);background:var(--surface);color:var(--ink)">'+opt([["all","All jobs"]].concat(H.jobs.map(function(j){return [String(j.id),j.role]})),String(H.appJob))+'</select>'+
      '<select id="aSort" aria-label="Sort" style="padding:8px 10px;border-radius:10px;border:1px solid var(--line);background:var(--surface);color:var(--ink)">'+opt([["match","Best match first"],["new","Newest first"]],H.sort)+'</select>'+
      '<label class="ckline"><input type="checkbox" id="aMust"'+(H.mustOnly?" checked":"")+'> Only people who meet every must-have</label></div></div>'+
      (list.length?'<div class="apps">'+list.map(appCard).join("")+'</div>':'<div class="box h-empty"><b>No applicants '+(H.apps.length?"match these filters":"yet")+'</b>'+(H.mode==="local"?"To try it, switch to job search and swipe right on your own job.":"When someone swipes right on your job, they show up here.")+'</div>');
  }
  function saveStage(id,stage,note){
    var a=H.apps.filter(function(x){return x.id===id})[0];if(!a)return;
    if(stage)a.stage=stage;if(note!=null)a.private=note;
    if(H.mode==="server"){api("/api/employer/applicant",{id:id,stage:stage||undefined,note:note==null?undefined:note}).then(function(r){say(r.ok?"Saved.":(r.j.error||"Could not save."),r.ok?"good":"bad")});return}
    H.L.pipe=H.L.pipe||{};var cur=H.L.pipe[id]||{};if(stage)cur.stage=stage;if(note!=null)cur.note=note;H.L.pipe[id]=cur;saveLocal();say("Saved.","good");
  }

  /* ---- company ---- */
  function companyView(){
    var c=H.company||{country:"US"};
    return '<div><h1>'+(H.company?"Company profile":"Add your company")+'</h1><p class="lead">Shown on every job you post. Job seekers see it under About the company.</p></div>'+
      '<form id="cForm" novalidate style="display:flex;flex-direction:column;gap:16px"><fieldset><legend>Company</legend>'+
      '<div class="f full"><span class="l">Logo</span><div class="logoup">'+logoBox(c,true)+'<div style="display:flex;flex-direction:column;gap:6px"><input type="file" id="cLogoF" accept="image/png,image/jpeg,image/webp"><small>PNG, JPEG or WebP. Square works best; it is resized for you.</small>'+(c.logo?'<button type="button" class="linkish" data-act="rmlogo" style="align-self:flex-start">Remove logo</button>':'')+'<small class="err" id="cLogoF-err" role="alert"></small></div></div></div>'+
      F("cName","Company name",'<input type="text" id="cName" maxlength="100" value="'+esc(c.name||"")+'" autocomplete="organization">',{req:1,full:1})+
      F("cIndustry","Industry",'<select id="cIndustry">'+opt(INDUSTRIES,c.industry||"","Choose your industry")+'</select>',{req:1})+
      F("cSize","Number of employees",'<select id="cSize">'+opt(SIZES.map(function(s){return [s,s+" employees"]}),c.size||"","Choose a size")+'</select>',{req:1})+
      F("cCountry","Country",radios("cCountry",COUNTRIES,c.country||"US"),{req:1,full:1,group:1,hint:"UAply lists jobs in the United States and Canada."})+
      F("cRegion",'<span id="cRegionL">State</span>','<select id="cRegion"></select>',{hint:"Where your headquarters is."})+
      F("cCity","City",'<input type="text" id="cCity" maxlength="60" value="'+esc(c.city||"")+'" autocomplete="address-level2">')+
      F("cWebsite","Website",'<input type="text" id="cWebsite" inputmode="url" maxlength="300" value="'+esc(c.website||"")+'" placeholder="https://yourcompany.com">',{full:1})+
      F("cAbout","About the company",'<textarea id="cAbout" maxlength="1500" rows="6" placeholder="What you do, who you serve, and what it is like to work with you.">'+esc(c.about||"")+'</textarea><span class="cnt" id="cAboutN"></span>',{full:1})+
      '</fieldset><fieldset><legend>Applications</legend>'+
      '<div class="f full"><span class="l">Applications are sent to</span><b>'+(H.mode==="server"?esc(H.email)+(H.verified?' <span class="flag ok">Verified</span>':' <span class="flag unk">Not verified yet</span>'):'your account email (on the UAply server)')+'</b><small>Your UAply account email. It cannot be changed here, so applications always reach someone who proved they own the address.</small></div>'+
      '<div class="f full"><label class="ckline"><input type="checkbox" id="cConsent"'+(c.consent||H.company?" checked":"")+'> I may post jobs for this company, and I agree to receive applications through UAply. <span class="req" aria-hidden="true">*</span></label><small class="err" id="cConsent-err" role="alert"></small></div>'+
      '</fieldset><div class="pbar"><span class="note">You can change all of this later.</span><button type="submit" class="btn">Save company</button></div></form>';
  }
  function wireCompany(){
    var f=hub.querySelector("#cForm");
    function regions(){var country=(f.querySelector('input[name="cCountry"]:checked')||{}).value||"US",sel=f.querySelector("#cRegion"),cur=sel.value||(H.company||{}).region||"";sel.innerHTML=opt(REGIONS[country],cur,country==="CA"?"Choose a province":"Choose a state");f.querySelector("#cRegionL").textContent=country==="CA"?"Province":"State"}
    function n(){f.querySelector("#cAboutN").textContent=f.querySelector("#cAbout").value.length+" / 1500"}
    regions();n();
    f.addEventListener("change",function(e){if(e.target.name==="cCountry")regions();if(e.target.id==="cLogoF")readLogo(e.target.files&&e.target.files[0])});
    f.addEventListener("input",n);
    f.addEventListener("submit",function(e){e.preventDefault();saveCompany()});
  }
  function readLogo(file){
    if(!file)return;
    if(!/^image\/(png|jpeg|webp)$/.test(file.type)){showErr("logo","Use a PNG, JPEG or WebP image.");return}
    if(file.size>8*1024*1024){showErr("logo","That image is over 8 MB. Use a smaller one.");return}
    var rd=new w.FileReader();
    rd.onload=function(){
      var img=new w.Image();
      img.onload=function(){
        function shrink(max,type,q){var s=Math.min(1,max/Math.max(img.width,img.height)),cv=d.createElement("canvas");cv.width=Math.max(1,Math.round(img.width*s));cv.height=Math.max(1,Math.round(img.height*s));var cx=cv.getContext("2d");if(type==="image/jpeg"){cx.fillStyle="#fff";cx.fillRect(0,0,cv.width,cv.height)}cx.drawImage(img,0,0,cv.width,cv.height);return cv.toDataURL(type,q)}
        var type=file.type==="image/jpeg"?"image/jpeg":"image/png",url=shrink(256,type,0.88);
        if(url.length>155000)url=shrink(160,"image/jpeg",0.85);
        if(url.length>155000){showErr("logo","That logo is too detailed. Try a simpler image.");return}
        H.pendingLogo=url;var box=hub.querySelector(".logoup .hlogo");if(box)box.innerHTML='<img src="'+url+'" alt="">';say("Logo ready. Save company to keep it.");
      };
      img.onerror=function(){showErr("logo","That file could not be read as an image.")};
      img.src=rd.result;
    };
    rd.readAsDataURL(file);
  }
  function saveCompany(){
    var f=hub.querySelector("#cForm");function v(id){return f.querySelector("#"+id).value.trim()}
    var p={name:v("cName").replace(/\s+/g," "),industry:v("cIndustry"),size:v("cSize"),country:(f.querySelector('input[name="cCountry"]:checked')||{}).value||"",region:v("cRegion"),city:v("cCity"),website:v("cWebsite"),about:v("cAbout"),consent:f.querySelector("#cConsent").checked};
    var bad=checkCompany(p);if(bad){showErr(bad[1],bad[0]);return}
    if(H.pendingLogo)p.logo=H.pendingLogo;else if(H.removeLogo)p.logo="remove";
    say("Saving…");
    if(H.mode==="server"){
      api("/api/employer/company",p).then(function(r){
        if(!r.ok){if(r.j.code==="verify"){say(r.j.error,"bad");return}showErr(r.j.field||"",r.j.error||"Could not save. Try again.");return}
        H.pendingLogo=null;H.removeLogo=false;load().then(function(){H.view=H.jobs.length?"overview":"post";H.edit=null;render();say("Company saved.","good");syncDeck()});
      });return;
    }
    var logo=H.pendingLogo||(H.removeLogo?"":(H.company&&H.company.logo)||"");
    H.company=Object.assign({},p,{logo:logo,consent:"Agreed in this browser on "+new Date().toISOString().slice(0,10)});
    H.pendingLogo=null;H.removeLogo=false;saveLocal();H.view=H.jobs.length?"overview":"post";H.edit=null;render();say("Company saved.","good");syncDeck();
  }

  /* ---- billing ---- */
  function billingView(){
    return '<div><h1>Billing</h1><p class="lead">Pricing for employers is TBD. Posting is free while UAply is in testing.</p></div>'+
      '<div class="box"><div class="h-row"><div><h2>Price to post a job</h2><p class="note">One price per job, shown before you publish.</p></div><span style="font:800 30px var(--display)">TBD</span></div>'+
      '<ul class="steps"><li><span class="ck on">✓</span>You see the exact price on the Publish button before anything is charged.</li><li><span class="ck on">✓</span>You pay once per job on Stripe\'s secure page. UAply never sees or stores your card number.</li><li><span class="ck on">✓</span>No pay-per-click and no automatic renewals: a job never costs more than the price you approved.</li><li><span class="ck on">✓</span>Every receipt is emailed and listed below.</li></ul></div>'+
      '<div class="box"><h2>Receipts</h2><p class="note">No payments yet.</p></div>';
  }

  /* ================= events ================= */
  hub.addEventListener("click",function(e){
    var b=e.target.closest("button,[data-view]");if(!b||!hub.contains(b))return;
    var view=b.getAttribute("data-view"),act=b.getAttribute("data-act"),id=b.getAttribute("data-id");
    if(view){if(view==="post"){H.edit=null;H.filled=null;H.manual=false;H.step=1}H.view=view;render();return}
    if(act==="signin"||act==="verify"){setMode(false,true);hdr.click();return}
    if(act==="new"){if(!H.company){H.view="company";render();say("Add your company first. It is shown on every job.");return}H.edit=null;H.manual=false;H.filled=null;H.step=1;H.view="post";render();return}
    if(act==="edit"){var j=jobById(id);H.edit=JSON.parse(JSON.stringify(j));H.manual=true;H.filled=null;H.step=2;H.view="post";render();return}
    if(act==="manual"){H.manual=true;H.filled=null;H.edit=null;H.step=2;render();return}
    if(act==="step"){goStep(+b.getAttribute("data-s"));return}
    if(act==="next"||act==="back"){var STs=postSteps(!!(H.edit&&H.edit.id)),ix=STs.indexOf(H.step)+(act==="next"?1:-1);if(ix>=0&&ix<STs.length)goStep(STs[ix]);return}
    if(act==="fix"){goStep(+b.getAttribute("data-s"),b.getAttribute("data-f"));return}
    if(act==="reimport"){H.manual=false;H.filled=null;H.edit=null;H.step=1;render();return}
    if(act==="impLink"){runImport("link");return}
    if(act==="impText"){runImport("text");return}
    if(act==="apps"){H.appJob=String(id);H.view="applicants";render();return}
    if(act==="rmlogo"){H.pendingLogo=null;H.removeLogo=true;var box=hub.querySelector(".logoup .hlogo");if(box)box.textContent=((H.company||{}).name||"?").charAt(0).toUpperCase();b.remove();say("Logo will be removed when you save.");return}
    if(act==="status"||act==="del"){
      var stt=act==="del"?"deleted":b.getAttribute("data-st"),jj=jobById(id);if(!jj)return;
      if(act==="del"&&b.getAttribute("data-sure")!=="1"){b.setAttribute("data-sure","1");b.textContent="Delete for good?";b.classList.remove("ghost");return}
      if(H.mode==="server"){api("/api/employer/job/status",{id:+id,status:stt}).then(function(r){if(!r.ok){say(r.j.error||"Could not change it.","bad");return}load().then(function(){render();say(stt==="deleted"?"Deleted.":stt==="open"?"Reopened. It is back in the swipe deck.":"Done. It no longer shows to new job seekers.","good");syncDeck()})});return}
      if(stt==="deleted")H.jobs=H.jobs.filter(function(x){return x!==jj});else{if(stt==="open"&&jj.status!=="open")jj.posted=Math.round(Date.now()/1000);jj.status=stt}
      saveLocal();H.apps=localApps();render();say(stt==="deleted"?"Deleted.":stt==="open"?"Reopened.":"Done. It no longer shows to new job seekers.","good");syncDeck();
    }
  });
  hub.addEventListener("change",function(e){
    var t=e.target;
    if(t.id==="aJob"){H.appJob=t.value;render();return}
    if(t.id==="aSort"){H.sort=t.value;render();return}
    if(t.id==="aMust"){H.mustOnly=t.checked;render();return}
    if(t.hasAttribute("data-stage")){saveStage(t.getAttribute("data-stage"),t.value,null);return}
    if(t.hasAttribute("data-pnote")){saveStage(t.getAttribute("data-pnote"),null,t.value.trim().slice(0,1000))}
  });

  paintSwitch(false);
  if(lsGet(MODE_K,"seek")==="hire")setMode(true,true);
}

Env.FEATURES.employers={name:"Hiring mode",note:"A \"Switch to hiring\" pill in the header opens the employer hub: company profile with logo, industry, size and country (United States or Canada), one-page job posting matched field by field to the job seeker's profile and filters, a hiring team contact, and an applicant pipeline. Employer jobs show their requirements and \"Meet the hiring team\" on the card. Prices are TBD. Needs Bottom navigation.",patch:patch,apply:apply};
Env.ORDER.push("employers");
})();
