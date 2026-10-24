/* UAply assisted apply: the person's own autofill for an employer's hosted application form (Greenhouse, Lever, Ashby, SmartRecruiters,
   Workable, and any plain HTML form). The phone app injects it into the employer's page it opened in its in-app browser
   (mobile/android: AssistActivity); tools/assist-measure.js injects it into real postings in Chrome to measure it, and
   tools/test-assist.js into the mock form of each system (tools/fixtures/assist/).

   Two passes, both on the employer's own page:
     scan (UAplyAssist.scan): reads the form and changes nothing. It returns the questions the profile cannot answer, with their kind and
       choices, so UAply asks them in its own question box BEFORE the person sees the form (the "required left" bridge); the answers are
       kept in UAply like every question-box answer.
     fill (UAplyAssist.fill): fills each field whose label (its <label>, aria-label, aria-labelledby, the question block around it,
       placeholder or name) says what it asks, from the profile and from the answers the person gave: name (split or whole), email, phone
       (and its country code), LinkedIn, GitHub, website, address, city, state, country, ZIP, current employer and title and their dates,
       school, degree, major, graduation (as a date, a month, or month and year apart), GPA, work authorization, sponsorship (also asked
       the other way round: "without sponsorship"), 18 or older (the person confirmed it when they agreed to UAply's terms), earliest
       start, relocation, on-site work, "have you worked here before", how you heard ("UAply", or Other and then "UAply"), "why us" (the
       person's own words from Profile setup). Lists and choices are matched by their option's words; yes/no lists also by meaning ("I will
       not require sponsorship" is a no). It attaches the resume file last.
   Never: a voluntary self-identification question (gender, race, ethnicity, veteran, disability, orientation, pronouns), found by the
   question's words or by its answers; a consent, acknowledgement or certification box; a human check (reCAPTCHA, hCaptcha, Cloudflare
   Turnstile); the Submit button. It scrolls to Submit and says "Review and tap Submit". submitIfAllowed() is the one place that could
   press it, and only when the host passes mode "automatic" (shared/assist-systems.json, which the lawyer sets, default "assisted"), the
   page shows no human check of any kind, and every required field is filled. See docs/assisted-apply.md.
   fill reports fields seen, filled, left (and required left), voluntary questions skipped, the resume, any human check, the time; a field
   the page empties again after it was filled (a place box that wants a suggestion chosen) is reported as left, not filled.

   profile: {first,last,name,email,phone,linkedin,website,street,city,state,zip,country,company,title,jobStart,jobEnd (YYYY-MM),school,
   degree,major,grad (YYYY-MM),gpa,auth ('yes'|'no'),sponsor ('yes'|'no'),adult ('yes'),start,relocate,office,former,govt,phd,salary,
   summary,headline,why,heard,answers:{question words: answer},resume:{name,type,b64}}. An answer is plain text, a date as 2027-06-30, a
   month as 2027-06, several choices one per line.
   opts: {banner:true|false, job:{co,role}, debug:true (rep.fields: what each field was read as)}. */
(function () {
  "use strict";
  /* The phone app puts this file into the employer's page as (function(__uaplyAssistKey){ <this file> })('<32 random hex digits, new
     every time the form opens>'), and then lives under a name made from that key, which the page cannot guess, set so the page cannot
     replace it. It never looks at window.UAplyAssist there: any page can define that first, and a page that did used to be handed the
     profile ("if (window.UAplyAssist) return" kept the page's own copy). Loaded plainly (the mock-form tests, the measurement tool) it is
     window.UAplyAssist, as before. */
  var KEY = typeof __uaplyAssistKey === "string" && __uaplyAssistKey.length >= 32 ? __uaplyAssistKey : "";
  var NAME = KEY ? "__uaplyAssist_" + KEY : "UAplyAssist";
  if (KEY ? Object.prototype.hasOwnProperty.call(window, NAME) : window.UAplyAssist) return;

  /* voluntary self-identification: by the question, or by its answers */
  var EEO = /\b(gender|sex\b|race\b|racial|ethnic|hispanic|latin[oax]|veteran|disabilit|sexual orientation|transgender|lgbt|pronoun|self[- ]identif|voluntary)/i;
  var EEO_OPT = /^\s*(male|female|man|woman|non-?binary|genderqueer|agender|cisgender|two or more races|white( \(|$)|black or african american|asian( \(|$)|american indian|native hawaiian|hispanic or latin|not hispanic|i am a (protected )?veteran|i am not a (protected )?veteran|i identify as one or more|yes, i have a disability|no, i (do not|don't) have a disability|i (do not|don't) want to answer|decline to self[- ]identify|heterosexual|gay|lesbian|bisexual|he\/him|she\/her|they\/them)\b/i;
  var CONSENT = /consent|acknowledg|agree|privacy|terms|certif|confirm|i have read|authori[sz]e/i;
  /* an agreement asked as a question (radios, a list, Yes/No buttons): the person answers it on the page, never UAply */
  var CONSENT_Q = /\b(consent|acknowledg\w*|i agree|agree to|certify|attest|i have read|confirm that (everything|the information|all|my)|everything in this application is true)\b/i;
  /* asked like a voluntary question though not on the usual list: age */
  var PRIVACY_Q = /^(privacy|data protection|gdpr|candidate privacy)( (statement|notice|policy|consent))?\b/i, CONSENT_OPT = /acknowledg|\bi agree\b|\bi accept\b|i have read|\bi consent\b|\bi certify\b/i;
  var OTHER_BOX = /^(custom|other|please specify|self[- ]describe|prefer to self[- ]describe|not listed)\b/i;
  var SENSITIVE = /\bage range\b|\bdate of birth\b|\bbirth ?date\b|\bdob\b|\bhow old\b/i;
  var CHECK_SEL = "iframe[src*='recaptcha'],iframe[src*='hcaptcha'],iframe[src*='turnstile'],iframe[src*='challenges.cloudflare'],iframe[title*='reCAPTCHA' i],iframe[title*='hCaptcha' i],.g-recaptcha,.h-captcha,.cf-turnstile,.grecaptcha-badge,[data-sitekey]";
  var CHECK_SCRIPT = "script[src*='recaptcha'],script[src*='hcaptcha'],script[src*='turnstile'],script[src*='challenges.cloudflare.com']";
  var FIELD_SEL = "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]):not([type=image]):not([type=search]),textarea,select";
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

  function norm(s) { return String(s || "").toLowerCase().replace(/\s+/g, " ").replace(/[^a-z0-9 ?]/g, "").trim(); }
  /* the key a saved answer is kept under: the server's autofill.norm, letter for letter, so a question answered in UAply's question box
     or in the bridge before this form is the same question here (asked once). A question about this employer (it names the employer, or
     asks why this company or role) starts with "{at <employer>}": only this employer's answer fills it, never another's. */
  var EMP_Q = /\bwhy\b.*\b(work|join|joining|interested|apply|applying|us|here|company|role|position|team|this)\b|\bwhat (excites|interests|draws|attracts|motivates) you\b|\bcover letter\b|\btell us (about )?why\b|\binterest(ed)? in (this|our|the) (company|role|position|team|job|opportunity)\b|\babout (this|our) (company|role|position|team|mission)\b/;
  function akey(label, co) {
    var s = String(label || "").toLowerCase();
    co = String(co || "");
    if (co) s = s.split(co.toLowerCase()).join(" {co} ");
    s = s.replace(/[^a-z0-9{} ]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 160).trim();
    if (co && s && s.indexOf("{at ") !== 0 && (s.indexOf("{co}") > -1 || EMP_Q.test(s))) {
      var slug = co.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().slice(0, 60);
      if (slug) s = ("{at " + slug + "} " + s).slice(0, 160).trim();
    }
    return s;
  }
  function clean(s) { return String(s || "").replace(/\s+/g, " ").replace(/[*✱]/g, "").trim(); }
  function esc(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  function visible(el) {
    if (!el || el.disabled) return false;
    if (el.type === "hidden") return false;
    if (el.getAttribute("aria-hidden") === "true" && el.tabIndex < 0 && el.type !== "radio" && el.type !== "checkbox") return false;   /* a form library's hidden copy of a visible field (Workable) */
    var r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none") return false;
    return (r.width > 0 && r.height > 0) || el.type === "file" || el.type === "radio" || el.type === "checkbox";
  }
  /* a node's words without the words of the fields inside it (a select's options, a button's text) */
  function textWithout(node) {
    if (!node) return "";
    var c = node.cloneNode(true);
    [].slice.call(c.querySelectorAll("select,option,textarea,input,button,script,style,svg,[role=listbox],[role=option]")).forEach(function (x) { x.remove(); });
    return clean(c.textContent);
  }
  function fieldsIn(box) {
    var seen = {}, n = 0;
    [].slice.call(box.querySelectorAll(FIELD_SEL)).forEach(function (f) {
      if (f.type === "file") return;
      var k = (f.type === "radio" || f.type === "checkbox") && f.name ? "g:" + f.name : null;
      if (k) { if (!seen[k]) { seen[k] = 1; n++; } } else n++;
    });
    return n;
  }
  function required(el, raw) {
    return !!(el.required || el.getAttribute("aria-required") === "true" || /[*✱]/.test(raw || "") || /\brequired\b/i.test(el.className || ""));
  }

  /* the words a field is asked with; raw keeps the required star */
  function rawLabelOf(el) {
    var t = "";
    if (el.id) { var l = document.querySelector("label[for='" + CSS.escape(el.id) + "']"); if (l) t = textWithout(l); }
    if (!t) { var p = el.closest("label"); if (p) { var inner = p.querySelector(".application-label,[class*='label' i]"); t = textWithout(inner && !inner.contains(el) ? inner : p); } }
    if (!t && el.getAttribute("aria-labelledby")) {
      t = el.getAttribute("aria-labelledby").split(/\s+/).map(function (i) { var e = document.getElementById(i); return e ? textWithout(e) : ""; }).join(" ");
    }
    if (!t) t = el.getAttribute("aria-label") || "";
    if (!t) {   /* a question block: climb while the block holds only this field, and take its words */
      var box = el.parentElement, i = 0;
      while (box && box !== document.body && i < 6 && !t) {
        if (fieldsIn(box) > 1) break;
        var q = [].slice.call(box.querySelectorAll("legend,label,h3,h4,h5,[class*='label' i],[class*='question' i],[class*='title' i]")).filter(function (x) { return !x.contains(el) && textWithout(x); })[0];
        var txt = q ? textWithout(q) : textWithout(box);
        if (txt && txt.length < 400) t = txt;
        box = box.parentElement; i++;
      }
    }
    if (!t) t = el.getAttribute("placeholder") || el.getAttribute("data-qa") || el.name || "";
    return String(t).replace(/\s+/g, " ").trim();
  }
  function labelOf(el) { return clean(rawLabelOf(el)); }
  /* a "Custom" or "Other" box inside a voluntary question's block (Lever's pronouns) */
  function eeoNear(el) {
    var box = el.parentElement, i = 0;
    while (box && box !== document.body && i < 4) {
      var t = textWithout(box);
      if (t.length < 600 && EEO.test(t)) return true;
      if (fieldsIn(box) > 8) return false;   /* past the question's own block */
      box = box.parentElement; i++;
    }
    return false;
  }

  /* a choice: its own option text */
  function optionText(g) {
    var t = "";
    if (g.id) { var l = document.querySelector("label[for='" + CSS.escape(g.id) + "']"); if (l) t = textWithout(l); }
    if (!t) { var p = g.closest("label"); if (p) t = textWithout(p); }
    if (!t) t = g.getAttribute("aria-label") || "";
    if (!t && g.parentElement) t = textWithout(g.parentElement);
    return clean(t || g.value || "");
  }
  /* the question a radio or checkbox group (or a row of Yes/No buttons) asks: the block that holds the whole group, minus the options */
  function groupQuestion(members, opts) {
    var first = members[0], fs = first.closest("fieldset,[role=radiogroup],[role=group]");
    if (fs && members.every(function (m) { return fs.contains(m); })) {
      var lg = fs.querySelector("legend"); if (lg && textWithout(lg)) return clean(textWithout(lg));
      var lb = fs.getAttribute("aria-labelledby");
      if (lb) { var lt = lb.split(/\s+/).map(function (i) { var e = document.getElementById(i); return e ? textWithout(e) : ""; }).join(" "); if (clean(lt)) return clean(lt); }
      if (fs.getAttribute("aria-label")) return clean(fs.getAttribute("aria-label"));
    }
    var box = first.parentElement, i = 0;
    while (box && box !== document.body && !members.every(function (m) { return box.contains(m); })) box = box.parentElement;
    while (box && box !== document.body && i < 5) {
      var t = " " + textWithout(box) + " ";
      opts.forEach(function (o) { if (o) t = t.replace(o, " "); });
      t = clean(t);
      if (t) return t.slice(0, 300);
      if (box.parentElement && fieldsIn(box.parentElement) > fieldsIn(box)) break;
      box = box.parentElement; i++;
    }
    return first.name || "";
  }

  /* what a label asks for, as a profile key (null: not something the profile answers). The first rule that matches wins. */
  var RULES = [
    ["why", /^why\b|why (do you want|are you interested|you want)|what (makes|draws|attracts) you to (join|work)|interested in (working|joining)/i],
    ["name", /\bfirst (name )?(and|&) last name\b|\bfirst and last\b/i],
    ["first", /\b(first|given|preferred first|legal first)[ -]?name\b|^first$|^preferred name\b|^nickname\b/i],
    ["last", /\b(last|family|sur)[ -]?name\b|\bsurname\b|^last$/i],
    ["current", /^(current (role|position|job|employer)|i currently work here|currently (work|working|employed) here|this is my current (role|job))$/i],
    ["company", /\b(current|present|most recent) (company|employer)\b|^(company|employer)( name)?$/i],
    ["title", /\b(current|present|most recent) (job )?(title|role|position)\b|^(job )?title$/i],
    ["name", /^(full |your |legal |candidate )?name\b|\bfull (legal )?name\b|\blegal name\b/i],
    ["email", /e-?mail/i],
    ["phonecc", /country code|phone country|dial(ing)? code/i],
    ["phone", /^(your |primary |best )?(phone|mobile|cell|telephone)\b|\b(phone|mobile|cell|telephone)( number| no\.?)\b/i],
    ["linkedin", /linked\s?in/i],
    ["github", /\bgithub\b/i],
    ["twitter", /\btwitter\b|^x( handle| profile| url)?$|\bx\.com\b/i],
    ["website", /\b(website|portfolio|personal (site|url|web)|other (website|url|link)|blog)\b/i],
    ["adult", /\b(at least|over|older than|above) (the age of )?(18|eighteen)\b|\b(18|eighteen) (years|yrs)( of age| old)?( or (older|over))?\b|\blegal (working )?age\b/i],
    ["nosponsor", /\bwithout (\w+ ){0,2}sponsorship\b/i],
    ["auth", /(legally )?(authori[sz]ed|eligible|permitted) to work|work authori[sz]ation|right to work|work permit/i],
    ["sponsor", /sponsor/i],
    ["former", /\b(have|had|were|are|do|did) you\b.{0,40}\b(employed|worked|work) (by|at|for|with)\b|\bpreviously (been )?(employed|worked)\b|\bformer\b.*\bemployee\b/i],
    ["govt", /government official/i],
    ["phd", /\b(ph\.?d|doctoral) program\b/i],
    ["gradmonth", /graduat\w*.{0,25}\bmonth\b|month of graduation/i],
    ["gradyear", /graduat\w*.{0,25}\byear\b|year of graduation|^class of\b|\bgrad(uation)? year\b/i],
    ["school", /\b(school|university|college|institution)\b/i],
    ["degree", /\bdegree\b|education level|highest (level of )?education/i],
    ["major", /\b(major|discipline|field of study|area of study)\b/i],
    ["grad", /graduat/i],
    ["gpa", /\bgpa\b|grade point/i],
    ["salary", /salary|compensation|pay (rate|expectation|range)|desired pay|base pay|expected pay/i],
    ["jobmonth", /^(start date|start|from) month$|^start month$/i],
    ["jobyear", /^(start date|start|from) year$|^start year$/i],
    ["endmonth", /^(end date|end|to) month$|^end month$/i],
    ["endyear", /^(end date|end|to) year$|^end year$/i],
    ["start", /(earliest|available|desired|possible|preferred|potential|anticipated) start|start date\?|when (can|could|would) you (start|begin)|available to (start|begin)|availability to start|notice period/i],
    ["relocate", /relocat/i],
    ["office", /\b(on-?site|in[- ]office|in the office|hybrid|commute|in person)\b/i],
    ["heard", /(how|where) did you (first )?(hear|find|learn|come across)|hear about (us|this|the)|^(referral )?source\b|^source of/i],
    ["summary", /^(summary|about you|about yourself|tell us about yourself|professional summary)\b/i],
    ["headline", /^headline\b/i],
    ["csz", /\bcity,? state,? (and |& )?(zip|postal)/i],
    ["street", /street address|address line ?1|home address|mailing address|^(current )?address$|^street$/i],
    ["zip", /\bzip\b|postal ?code|post ?code/i],
    ["country", /\bcountry\b/i],
    ["state", /\bstate\b/i],
    ["city", /\b(current )?(location|city|where (do )?you live|where are you (based|located))\b/i]
  ];
  var DATA_KEYS = /^(first|last|name|email|phone|linkedin|github|twitter|website|company|title|school|major|gpa|zip|csz|street|city|state|country|headline|summary)$/;
  var YN_KEYS = /^(auth|nosponsor|sponsor|relocate|office|former|govt|phd|adult)$/;
  /* a follow-up that depends on another answer ("If yes, what is the email of...") is the person's to answer */
  var FOLLOW_UP = /^(if (yes|so|no|not|applicable|other|you (are|were|have|answered|selected))\b|if '?other'?|please (list|state|specify|provide|explain|describe|include)\b|list (any|all|the)\b)/i;
  function keyOf(label) {
    if (!label || FOLLOW_UP.test(label)) return null;
    var k = null, m = null;
    for (var i = 0; i < RULES.length; i++) { m = RULES[i][1].exec(label); if (m) { k = RULES[i][0]; break; } }
    if (!k) return null;
    if (DATA_KEYS.test(k) && m.index > 40) return null;   /* a long question that mentions an email or a city deep inside is not asking for yours */
    if (k === "former" && /relative|family|friend|related|spouse|partner|referr|know anyone|someone/i.test(label)) return null;   /* about someone else */
    if (k === "city" && /applying (for|to)|which (office|location|site)|preferred (work |office )?location|location (preference|you('| a)re applying)|(work|office) location/i.test(label)) return null;   /* the job's location, the person's choice */
    if (/pronunciation|phonetic|password|access code|high school/i.test(label)) return null;   /* asks something else that shares a word */
    if (/^(auth|nosponsor|sponsor|relocate|office|former|govt|phd|heard|adult)$/.test(k) && /any other|additional (context|information|details)|explain|describe|tell us|share (any|more)/i.test(label)) return null;   /* free text around a yes/no topic */
    if (/^(auth|nosponsor|sponsor)$/.test(k) && /limited|temporary|expir|type of visa|visa type|which visa|\bopt\b|\bead\b|\bcpt\b|h-?1b/i.test(label)) return null;   /* about a kind of status the profile does not hold */
    if (YN_KEYS.test(k) && label.indexOf("?") < 0 && !/^(are|do|does|will|would|have|has|is|can|could|did|were|please (select|confirm|indicate)|select|i am)\b/i.test(label)) return null;   /* a statement, not a yes/no question */
    if (k === "adult" && /\b(21|twenty[- ]one)\b/.test(label)) return null;   /* 21 or older: the profile does not know */
    if (k === "heard" && label.length > 70) return null;   /* "How did you hear about us? And what do you know about..." */
    return k;
  }

  /* set a value the way typing does, so React and Angular forms see it; keepFocus leaves the field focused (a place box needs that) */
  function setValue(el, v, keepFocus) {
    var proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    var d = Object.getOwnPropertyDescriptor(proto, "value");
    el.focus();
    if (d && d.set) d.set.call(el, v); else el.value = v;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    if (!keepFocus) el.dispatchEvent(new Event("blur", { bubbles: true }));
  }
  var COUNTRY = { US: /^\s*(united states|usa|us|u\.s\.)/i, CA: /^\s*canada/i, GB: /^\s*(united kingdom|uk|great britain)/i };
  var STATES = { AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California", CO: "Colorado", CT: "Connecticut", DE: "Delaware", DC: "District of Columbia", FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa", KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland", MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi", MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada", NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York", NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia", WA: "Washington", WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming" };
  function stateName(p) { var s = String(p.state || "").trim(); return STATES[s.toUpperCase()] || s; }
  function countryName(p) { var c = String(p.country || "US").toUpperCase(); return c === "US" ? "United States" : c === "CA" ? "Canada" : c === "GB" ? "United Kingdom" : ""; }
  var START_TEXT = { now: "Immediately", "2w": "2 weeks", "1m": "1 month", grad: "After I graduate", flex: "Flexible" };
  var START_OPT = { now: /immediate|asap|right away|^\s*now\b|no notice|0 (days|weeks)|none/i, "2w": /\b(2|two) weeks?\b|14 days/i, "1m": /\b(1|one) month\b|30 days|4 weeks|four weeks/i, grad: /graduat/i, flex: /flexib|negotiab/i };
  var DEGREE_OPT = [[/^bachelor/i, /bachelor|\bb\.?\s?a\.?\b|\bb\.?\s?s\.?\b|\bbsc\b|undergrad/i], [/^master/i, /master|\bm\.?\s?s\.?\b|\bm\.?\s?a\.?\b|\bmba\b|\bmsc\b/i],
    [/^(phd|ph\.d|doctor)/i, /ph\.?\s?d|doctor/i], [/^associate/i, /associate/i], [/^high school/i, /high school|\bged\b|secondary|diploma/i]];
  /* "yes" or "no" read from a choice's words: "Yes, I am", "I do not require sponsorship" (a no), "I am authorized" (a yes) */
  function ynOf(t) {
    t = String(t || "").trim();
    if (!t || /decline|prefer not|not applicable|\bn\/a\b|unsure|not sure|don'?t know/i.test(t)) return "";
    if (/^(yes|y)\b/i.test(t)) return "yes";
    if (/^(no|n)\b/i.test(t)) return "no";
    return /\b(not|never|no|none|without)\b|n't\b/i.test(t) ? "no" : "yes";
  }
  function noSponsor(p) { return p.sponsor === "no" && p.auth === "yes" ? "yes" : p.sponsor === "yes" || p.auth === "no" ? "no" : ""; }
  function ynWant(key, p) {
    switch (key) {
      case "auth": case "sponsor": case "relocate": case "office": case "govt": case "phd": return p[key] === "yes" || p[key] === "no" ? p[key] : "";
      case "nosponsor": return noSponsor(p);
      case "former": return p.former === "no" ? "no" : "";
      case "adult": return p.adult === "yes" ? "yes" : "";
    }
    return "";
  }
  /* which choices fit the profile, best first (a list of patterns tried in order) */
  function pickText(key, p) {
    var yn = ynWant(key, p);
    if (YN_KEYS.test(key)) return yn === "yes" ? [/^\s*yes\b/i] : yn === "no" ? [/^\s*no\b/i] : null;
    switch (key) {
      case "heard": return [/^\s*uaply\b/i, /^\s*other\b/i, /^\s*(job board|online job board|job site|job search|internet|online|website|company website|careers? (site|page))\b/i];
      case "degree": var d = DEGREE_OPT.filter(function (x) { return x[0].test(String(p.degree || "")); })[0]; return d ? [d[1]] : (p.degree ? [new RegExp("^\\s*" + esc(String(p.degree).split(/['’ ]/)[0]), "i")] : null);
      case "school": return p.school ? [new RegExp(esc(p.school), "i")] : null;
      case "country": return COUNTRY[String(p.country || "US").toUpperCase()] ? [COUNTRY[String(p.country || "US").toUpperCase()]] : null;
      case "phonecc": return String(p.country || "US").toUpperCase() === "US" ? [/united states|\+\s?1\b|^\s*us\b|\busa\b/i] : null;
      case "state": var s = stateName(p); return s ? [new RegExp("^\\s*(" + esc(s) + "|" + esc(String(p.state || "").toUpperCase()) + ")\\b", "i")] : null;
      case "city": return p.city ? [new RegExp("^\\s*" + esc(p.city), "i")] : null;
      case "start": return START_OPT[p.start] ? [START_OPT[p.start]] : null;
      case "gradmonth": case "jobmonth": case "endmonth":
        var ym = key === "gradmonth" ? p.grad : key === "jobmonth" ? p.jobStart : p.jobEnd, mo = /^\d{4}-(\d{2})$/.exec(ym || "");
        if (!mo) return null; var nm = MONTHS[+mo[1] - 1];
        return [new RegExp("^\\s*(" + nm + "|" + nm.slice(0, 3) + "|0?" + (+mo[1]) + ")\\b", "i")];
      case "gradyear": case "jobyear": case "endyear":
        var yy = key === "gradyear" ? p.grad : key === "jobyear" ? p.jobStart : p.jobEnd;
        return /^\d{4}-\d{2}$/.test(yy || "") ? [new RegExp("^\\s*" + yy.slice(0, 4) + "\\b")] : null;
    }
    return null;
  }
  /* the choice to make among option texts: the person's own answer first, then the profile's, then yes/no by meaning. -1: none fits */
  function chooseOpt(texts, key, p, saved) {
    var n = texts.map(norm), i;
    if (saved) {
      var sv = norm(String(saved).split("\n")[0]);
      i = n.indexOf(sv); if (i >= 0) return i;
      if (sv) for (i = 0; i < n.length; i++) if (n[i] && (n[i].indexOf(sv) === 0 || sv.indexOf(n[i]) === 0)) return i;
      return -1;
    }
    var pats = key ? pickText(key, p) : null;
    if (pats) for (var j = 0; j < pats.length; j++) for (i = 0; i < texts.length; i++) if (pats[j].test(texts[i])) return i;
    if (key && YN_KEYS.test(key) && texts.length <= 4) {
      var want = ynWant(key, p);
      if (want) {
        var by = texts.map(ynOf);
        if (by.indexOf("yes") >= 0 && by.indexOf("no") >= 0) { i = by.indexOf(want); if (i >= 0) return i; }
      }
    }
    return -1;
  }
  function fillIn(t, job) { return String(t || "").replace(/\{company\}/g, job && job.co || "your company").replace(/\{role\}/g, job && job.role || "this role"); }
  /* a date the way the field wants it: a date input takes 2027-06-30; a typed field follows its placeholder (MM/DD/YYYY, MM/YYYY) */
  function dateFor(el, ymd) {
    var m = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(ymd || ""); if (!m) return ymd || "";
    var y = m[1], mo = m[2], dd = m[3] || "01";
    if (el && el.type === "date") return y + "-" + mo + "-" + dd;
    if (el && el.type === "month") return y + "-" + mo;
    var ph = String(el && (el.getAttribute("placeholder") || "") || "").toLowerCase();
    if (/dd\/mm\/yyyy/.test(ph)) return dd + "/" + mo + "/" + y;
    if (/mm\/dd\/yyyy|mm\/dd\/yy/.test(ph)) return mo + "/" + dd + "/" + y;
    if (/mm\/yyyy|mm\/yy|mm-yyyy/.test(ph)) return mo + "/" + y;
    if (/yyyy-mm-dd/.test(ph)) return y + "-" + mo + "-" + dd;
    return m[3] ? mo + "/" + dd + "/" + y : MONTHS[+mo - 1] + " " + y;
  }
  function textFor(key, p, el, job, req, label) {
    switch (key) {
      case "first": return p.first || String(p.name || "").split(/\s+/)[0];
      case "last": return p.last || String(p.name || "").split(/\s+/).slice(1).join(" ");
      case "name": return p.name || [p.first, p.last].filter(Boolean).join(" ");
      case "email": return p.email;
      case "phone":
        var digits = String(p.phone || "").replace(/\D/g, "");
        if (el && (el.maxLength === 10 || /\\d\{10\}|\[0-9\]\{10\}/.test(el.getAttribute("pattern") || ""))) return digits.slice(-10);
        return p.phone;
      case "phonecc": return String(p.country || "US").toUpperCase() === "US" ? "+1" : "";
      case "linkedin": return p.linkedin;
      case "github": return /github\.com/i.test(p.website || "") ? p.website : "";
      case "twitter": return "";
      case "website": return p.website;
      case "company": return p.company; case "title": return p.title;
      case "school": return p.school; case "degree": return p.degree; case "major": return p.major; case "gpa": return p.gpa ? String(p.gpa) : "";
      case "grad": return /^\d{4}-\d{2}$/.test(p.grad || "") ? dateFor(el, p.grad) : "";
      case "gradmonth": return /^\d{4}-\d{2}$/.test(p.grad || "") ? MONTHS[+p.grad.slice(5) - 1] : "";
      case "gradyear": return /^\d{4}-\d{2}$/.test(p.grad || "") ? p.grad.slice(0, 4) : "";
      case "start": return START_TEXT[p.start] || p.start || "";
      case "jobmonth": case "jobyear": case "endmonth": case "endyear":   /* the most recent job, from Profile setup (an empty end: still there) */
        var ym = key.indexOf("job") === 0 ? p.jobStart : p.jobEnd;
        if (!/^\d{4}-\d{2}$/.test(ym || "")) return "";
        return /year$/.test(key) ? ym.slice(0, 4) : MONTHS[+ym.slice(5) - 1];
      case "heard": return p.heard || "UAply";
      case "salary":   /* only where the form requires it (Profile setup says so); per hour when the field says hour */
        if (!req) return "";
        if (/\bhour|hourly/i.test(labelOf(el) || "") && p.salaryHour) return String(p.salaryHour);
        return p.salary ? String(p.salary) : "";
      case "why": return el && (el.tagName === "TEXTAREA" || el.type === "text") ? fillIn(p.why, job) : "";
      case "summary": return el && (el.tagName === "TEXTAREA" || el.type === "text") ? p.summary : "";
      case "headline": return p.headline;
      case "zip": return p.zip;
      case "csz": return p.city && p.state && p.zip ? p.city + ", " + p.state + " " + p.zip : "";
      case "street":   /* "Street address" gets the street; "Home address" or "Address" the whole address */
        if (!p.street) return "";
        return label && /street|line ?1/i.test(label) ? p.street : [p.street, p.city, [p.state, p.zip].filter(Boolean).join(" ")].filter(Boolean).join(", ");
      case "country": return countryName(p);
      case "state": return stateName(p);
      case "city": return label && /\bcity\b/i.test(label) && !/\bstate\b/i.test(label) ? p.city : [p.city, p.state].filter(Boolean).join(", ");
    }
    if (YN_KEYS.test(key)) { var w = ynWant(key, p); return w === "yes" ? "Yes" : w === "no" ? "No" : ""; }
    return "";
  }
  /* a question the person already answered (UAply's question box, or the bridge before this form), matched by its words */
  function savedAnswer(label, p, co, rep) {
    var a = p.answers || {}, n = akey(label, co);
    if (!n) return "";
    if (Object.prototype.hasOwnProperty.call(a, n) && a[n]) { if (rep) rep.answerKeys.push(n); return a[n]; }
    if (n.indexOf("{at ") === 0) return "";      /* this employer's own question: only its own answer, never one given to another employer */
    /* an answer kept before October 22 under the question's own words (the bridge kept those): the same question when its key matches,
       unless that old key was about an employer ("{co}", or another employer's name in it) */
    for (var k in a) if (Object.prototype.hasOwnProperty.call(a, k) && a[k] && k.indexOf("{") < 0 && akey(k, "") === n && !EMP_Q.test(n)) { if (rep) rep.answerKeys.push(k); return a[k]; }
    return "";
  }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  /* the resume: the person's own file, put into the form's file input as if they had chosen it */
  function resumeInput() {
    var inputs = [].slice.call(document.querySelectorAll("input[type=file]"));
    return inputs.filter(function (i) { return /resume|\bcv\b|curriculum/i.test(labelOf(i) + " " + (i.name || "") + " " + (i.id || "") + " " + (i.getAttribute("data-qa") || "") + " " + (i.getAttribute("aria-label") || "")); })[0] ||
      (inputs.length === 1 ? inputs[0] : null);
  }
  function attachResume(p, rep) {
    var target = resumeInput();
    rep.resumeInput = !!target;
    if (!target || !p.resume || !p.resume.b64) return false;
    try {
      var bin = atob(p.resume.b64), u = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
      var f = new File([u], p.resume.name || "resume.pdf", { type: p.resume.type || "application/pdf" });
      var dt = new DataTransfer(); dt.items.add(f);
      target.files = dt.files;
      target.dispatchEvent(new Event("input", { bubbles: true }));
      target.dispatchEvent(new Event("change", { bubbles: true }));
      rep.resumeAttached = !!(target.files && target.files.length === 1);
      return rep.resumeAttached;
    } catch (e) { rep.resumeError = String(e && e.message || e).slice(0, 80); return false; }
  }

  /* React Select and other comboboxes */
  function listOptions() {
    return [].slice.call(document.querySelectorAll("[role=option],[role=listbox] li,[class*='menu' i] [class*='option' i]")).filter(function (o) { return (o.offsetParent || o.getClientRects().length) && (o.innerText || "").length < 200; })
      .filter(function (o) { return !/notice|no-?options|loading|empty/i.test(String(o.className || "")) && !/^(no (options|results)|loading)/i.test((o.innerText || "").trim()); });
  }
  async function comboOpen(el) {
    el.focus();
    var ctl = el.closest("[class*='control' i]") || el;
    ctl.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
    await sleep(30);
    if (el.getAttribute("aria-expanded") !== "true" && typeof TouchEvent === "function") {   /* React Select on a phone opens on touchend, not mousedown */
      try { var tch = new Touch({ identifier: Date.now(), target: ctl, clientX: 1, clientY: 1 }); ctl.dispatchEvent(new TouchEvent("touchend", { bubbles: true, cancelable: true, changedTouches: [tch] })); } catch (e) {}
      await sleep(30);
    }
    if (el.getAttribute("aria-expanded") === "false") el.click();
  }
  function comboClose(el) { el.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); }
  /* the options a list offers without typing (the scan reads them to ask the person); [] for a list that only searches */
  async function comboRead(el) {
    try {
      await comboOpen(el); el.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
      var opts = [];
      /* looked at often (one tap, October 23: the form is ready seconds after the swipe), for as long as before (0.7 s) */
      for (var i = 0; i < 24 && !opts.length; i++) {
        await sleep(30); opts = listOptions();
        if (!opts.length && i >= 4 && el.getAttribute("aria-expanded") !== "true") break;     /* it did not open: a list that only searches */
      }
      var texts = opts.map(function (o) { return clean(o.innerText); }).filter(Boolean);
      comboClose(el); el.blur();
      return texts.length > 300 ? texts.slice(0, 300) : texts;
    } catch (e) { return []; }
  }
  /* open the list, type (to search), wait for the options, choose the one chooser() picks */
  async function comboPick(el, text, chooser) {
    try {
      await comboOpen(el);
      if (text) setValue(el, text, true); else el.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
      var hit = null, opts = [];
      for (var i = 0; i < 40 && !hit; i++) {      /* every 60 ms, for as long as before (2.4 s): a list that is there at once is picked at once */
        await sleep(i ? 60 : 30);
        opts = listOptions();
        if (opts.some(function (o) { return EEO_OPT.test(o.innerText || ""); })) { comboClose(el); return "eeo"; }
        var at = opts.length ? chooser(opts.map(function (o) { return clean(o.innerText); })) : -1;
        if (at >= 0) hit = opts[at];
      }
      if (hit) { hit.dispatchEvent(new MouseEvent("mousedown", { bubbles: true })); hit.click(); await sleep(60); return "picked"; }
      comboClose(el);
      return el.value && text && norm(el.value) === norm(text) ? "typed" : "no";
    } catch (e) { return "no"; }
  }
  /* a place box that lists suggestions under the field (not a combobox by its markup): choose the one that starts with the city */
  async function pickSuggestion(el, re) {
    if (!re) return false;
    var box = el.closest(".application-field") || (el.parentElement && el.parentElement.parentElement) || el.parentElement;
    if (!box || !box.querySelector("[class*='dropdown' i],[class*='suggest' i],[class*='results' i],[class*='autocomplete' i],[role=listbox]")) return false;
    for (var i = 0; i < 60; i++) {           /* every 60 ms for 3.6 s, as long as before: the suggestions come from the employer's server */
      await sleep(60);
      var c = [].slice.call(box.querySelectorAll("[class*='dropdown' i] *,[class*='suggest' i] *,[class*='results' i] *,[role=option]")).filter(function (x) {
        return x !== el && !x.children.length && (x.offsetParent || x.getClientRects().length) && re.test(x.textContent || "") && (x.textContent || "").length < 120;
      })[0];
      if (c) { var t = c.closest("[role=option],li,[class*='location' i],[class*='item' i]") || c; t.dispatchEvent(new MouseEvent("mousedown", { bubbles: true })); t.click(); await sleep(100); return true; }
    }
    return false;
  }

  function submitButton() {
    var bs = [].slice.call(document.querySelectorAll("button,input[type=submit],[role=button]")).filter(function (b) { return b.offsetParent || b.getClientRects().length; });
    return bs.filter(function (b) { return /^(submit|submit application|submit your application|apply|apply now|send application|send|complete application)\b/i.test((b.innerText || b.value || "").trim()); }).pop() ||
      bs.filter(function (b) { return b.type === "submit"; }).pop() || null;
  }

  /* any human check on the page: kind, and whether it shows a box the person must answer (a visible widget) */
  function humanCheck() {
    var els = [].slice.call(document.querySelectorAll(CHECK_SEL)), scripts = [].slice.call(document.querySelectorAll(CHECK_SCRIPT));
    var all = els.concat(scripts), src = all.map(function (e) { return (e.src || e.className || e.getAttribute("title") || "") + ""; }).join(" ");
    var kind = /h-?captcha/i.test(src) ? "hCaptcha" : /turnstile|challenges\.cloudflare/i.test(src) ? "Turnstile" : /recaptcha/i.test(src) ? "reCAPTCHA" : all.length ? "check" : "";
    if (!kind && (window.grecaptcha || window.hcaptcha || window.turnstile)) kind = window.hcaptcha ? "hCaptcha" : window.turnstile ? "Turnstile" : "reCAPTCHA";
    var shown = els.some(function (e) {
      if (e.tagName !== "IFRAME" || e.closest(".grecaptcha-badge")) return false;
      var r = e.getBoundingClientRect(); return r.width >= 120 && r.height >= 60 && getComputedStyle(e).visibility !== "hidden";
    });
    return { present: !!kind, kind: kind, shown: shown };
  }

  function banner(text) {
    var old = document.getElementById("uaplyAssistBar"); if (old) old.remove();
    var b = document.createElement("div"); b.id = "uaplyAssistBar"; b.setAttribute("role", "status");
    b.style.cssText = "position:fixed;left:8px;right:8px;bottom:8px;z-index:2147483647;background:#2A1218;color:#fff;font:600 15px/1.35 system-ui,sans-serif;padding:12px 14px;border-radius:14px;box-shadow:0 8px 24px rgba(0,0,0,.3);pointer-events:none";
    b.textContent = text;
    var vv = window.visualViewport;   /* a page wider than the phone's screen (Lever's) would push a fixed bar's right half off screen */
    if (vv && vv.width) { b.style.boxSizing = "border-box"; b.style.right = "auto"; b.style.left = Math.round(vv.offsetLeft + 8) + "px"; b.style.width = Math.round(vv.width - 16) + "px"; }
    document.body.appendChild(b);
  }

  /* the kind of question a field is, as UAply's question box asks it */
  function kindOf(el) {
    if (el.tagName === "TEXTAREA") return "textarea";
    if (el.type === "number") return "number";
    if (el.type === "date") return "date";
    if (el.type === "month") return "month";
    return "text";
  }

  /* a "Current role" tick box on the form (Greenhouse's employment block) */
  function currentBox() {
    return [].slice.call(document.querySelectorAll("input[type=checkbox]")).some(function (c) { return keyOf(optionText(c)) === "current" || keyOf(labelOf(c)) === "current"; });
  }

  var LAST = null;
  /* fill (opts.dry: scan only, nothing changed: rep.questions lists what the profile cannot answer) */
  async function fill(p, opts) {
    opts = opts || {};
    p = p || {};
    var dry = !!opts.dry, t0 = Date.now(), job = opts.job || {};
    var rep = { url: location.href, seen: 0, filled: 0, left: [], leftReq: 0, eeoSkipped: 0, prefilled: 0, consentLeft: 0, consentReq: 0, fromAnswers: 0, fromAnswersOpt: 0, humanCheck: false, checkKind: "", checkShown: false,
      resumeInput: false, resumeAttached: false, submit: false, ms: 0, filledKeys: [], keys: [], answerKeys: [] };
    if (dry) rep.questions = [];
    if (opts.debug) rep.fields = [];
    function note(label, key, how, req) { if (rep.fields) rep.fields.push({ q: String(label).slice(0, 80), key: key || "", how: how, req: !!req }); }
    /* left for the person; in a scan, the question to ask before the form (kind and choices as UAply's question box shows them) */
    /* keys: every profile item a field on this form asks for (filled or not); answerKeys: the saved answers it used. The phone app hands
       the fill only those (uaply-nav.js, assistOnly), never the whole profile */
    function addKey(k) { if (k && rep.keys.indexOf(k) < 0) rep.keys.push(k); }
    function leave(label, key, req, why, ask) {
      addKey(key);
      rep.left.push((req ? "(required) " : "") + String(label).slice(0, 70)); if (req) rep.leftReq++;
      note(label, key, why || "left", req);
      if (dry && ask && label) rep.questions.push({ q: String(label).slice(0, 600), key: akey(label, job.co) || String(label).slice(0, 160), kind: ask.kind, opts: ask.opts && ask.opts.length ? ask.opts.slice(0, 300) : undefined, required: !!req });
    }
    function consentLeft(label, req, why) { rep.consentLeft++; if (req) rep.consentReq++; rep.left.push((req ? "(required) " : "") + String(label).slice(0, 70)); if (req) rep.leftReq++; note(label, "", why, req); }
    var typed = [];
    function got(label, key, req, how, el, saved) { addKey(key); rep.filled++; if (saved) { rep.fromAnswers++; if (!req) rep.fromAnswersOpt++; } rep.filledKeys.push(key || "answer"); note(label, key, (saved ? "answer, " : "") + (how || "filled"), req); if (el) typed.push([el, label, key, req]); }
    var done = new Set(), prevKey = "", heardOther = false;
    /* a page drawn on the server and then taken over by React (Greenhouse's Remix form) throws away whatever was typed before that:
       wait until its fields are live (up to 10 s) */
    if (window.__remixContext || window.__NEXT_DATA__ || document.querySelector("[data-reactroot]")) {
      for (var w8 = 0; w8 < 50; w8++) {
        var f0 = document.querySelector(FIELD_SEL);
        if (f0 && Object.keys(f0).some(function (k2) { return /^__react(Props|Fiber)/.test(k2); })) break;
        await sleep(200);
      }
    }
    var fields = [].slice.call(document.querySelectorAll(FIELD_SEL)).filter(function (el) {
      return visible(el) && el.type !== "file" && !el.closest("#uaplyAssistBar");
    });
    for (var i = 0; i < fields.length; i++) {
      var el = fields[i];
      if (done.has(el)) continue;
      var isChoice = el.type === "radio" || el.type === "checkbox";
      if (isChoice) {   /* one question for the whole group */
        var group = el.name ? [].slice.call(document.querySelectorAll("input[name='" + CSS.escape(el.name) + "']")) : [el];
        group.forEach(function (g) { done.add(g); });
        var otexts = group.map(optionText), label = groupQuestion(group, otexts), raw = label, single = group.length === 1 && el.type === "checkbox";
        if (single && otexts[0] && (!label || label === el.name || !/^(yes|no|i do|i am|true|agree)\.?$/i.test(otexts[0]))) label = otexts[0];   /* a lone tick box says its own question ("Current role"), unless it only says "Yes" */
        var req = group.some(function (g) { return g.required || g.getAttribute("aria-required") === "true"; }) || /[*✱]/.test(raw);
        label = clean(label);
        if (EEO.test(label) || SENSITIVE.test(label) || otexts.some(function (o) { return EEO_OPT.test(o); }) || (OTHER_BOX.test(label) && eeoNear(el))) { rep.eeoSkipped++; note(label, "", "voluntary, skipped", req); continue; }
        if (group.some(function (g) { return g.checked; })) { rep.prefilled++; note(label, "", "already chosen", req); continue; }   /* the person or the page chose it */
        rep.seen++;
        if (el.type === "checkbox" && CONSENT.test(label + " " + otexts.join(" "))) { consentLeft(label + " (the person ticks it)", req, "the person ticks it"); continue; }
        if (el.type === "radio" && CONSENT_Q.test(label + " " + otexts.join(" "))) { consentLeft(label + " (the person answers it)", req, "the person answers it"); continue; }   /* an agreement drawn as radios */
        var key = keyOf(label), ans = savedAnswer(label, p, job.co, rep), hits = [];
        if (el.type === "checkbox" && !single && ans) {   /* tick every one that applies: the person's answer, one choice per line */
          var want = String(ans).split("\n").map(norm).filter(Boolean);
          hits = group.filter(function (g, j) { return want.indexOf(norm(otexts[j])) >= 0; });
        } else if (single) {
          var yes = ans ? ynOf(ans) === "yes" : key === "current" ? !!(p.company && !p.jobEnd) : (key && YN_KEYS.test(key) ? ynWant(key, p) === "yes" : false);
          if (yes) hits = [el]; else if (ans || (key && ynWant(key, p)) || (key === "current" && p.company)) { got(label, key, req, "no: left unticked", null, !!ans); prevKey = key || ""; continue; }
        } else {
          var at = chooseOpt(otexts, key, p, ans);
          if (at >= 0) hits = [group[at]];
        }
        if (hits.length) {
          if (!dry) hits.forEach(function (h) { (h.closest("[role=radio],[role=checkbox]") || h).click(); if (!h.checked) h.click(); });
          if (key === "heard" && /other/i.test(otexts[group.indexOf(hits[0])] || "")) heardOther = true;
          got(label, key, req, "", null, !!ans);
        } else leave(label, key, req, "", single ? { kind: "select", opts: ["Yes", "No"] } : { kind: el.type === "checkbox" ? "multi" : "select", opts: otexts });
        prevKey = key || "";
        continue;
      }
      done.add(el);
      var raw2 = rawLabelOf(el), label2 = clean(raw2), req2 = required(el, raw2);
      if (EEO.test(label2) || SENSITIVE.test(label2) || (el.tagName === "SELECT" && [].slice.call(el.options).some(function (o) { return EEO_OPT.test(o.text); })) ||
          (OTHER_BOX.test(label2) && eeoNear(el))) { rep.eeoSkipped++; note(label2, "", "voluntary, skipped", req2); continue; }
      if (el.tagName === "SELECT" ? (el.selectedIndex > 0 && el.options[el.selectedIndex].value) : (el.value && el.value.trim())) { rep.prefilled++; note(label2, "", "already filled", req2); continue; }   /* the page filled it */
      rep.seen++;
      if ((CONSENT_Q.test(label2) || PRIVACY_Q.test(label2) || (el.tagName === "SELECT" && [].slice.call(el.options).some(function (o) { return CONSENT_OPT.test(o.text); }))) && el.tagName !== "TEXTAREA" && (el.type !== "text" || el.getAttribute("role") === "combobox")) { consentLeft(label2 + " (the person answers it)", req2, "the person answers it"); continue; }
      var k = keyOf(label2);
      if ((k === "endmonth" || k === "endyear") && p.company && !p.jobEnd && currentBox()) { addKey(k); rep.seen--; note(label2, k, "current job: no end date", req2); continue; }
      var saved = savedAnswer(label2, p, job.co, rep), val = saved || (k ? textFor(k, p, el, job, req2, label2) : "");
      if (!k && !saved && heardOther && prevKey === "heard" && /\bother\b|specify/i.test(label2) && el.tagName !== "SELECT") val = "UAply";   /* "If other, please specify" after How did you hear: Other */
      if (saved && el.tagName !== "SELECT" && (el.type === "date" || el.type === "month" || /^\d{4}-\d{2}(-\d{2})?$/.test(saved))) val = dateFor(el, saved);
      prevKey = k || "";
      if (el.tagName === "SELECT") {
        var sopts = [].slice.call(el.options).filter(function (x) { return x.value && !/^\s*(select|choose|please select|--)/i.test(x.text); });
        var st = sopts.map(function (x) { return clean(x.text); });
        var si = chooseOpt(st, k, p, saved);
        if (si < 0 && k === "city") si = chooseOpt(st, "country", p, "");   /* "What is your location?" as a list of countries */
        if (si < 0 && !saved && val) si = chooseOpt(st, null, p, val);
        if (si >= 0) { if (!dry) setValue(el, sopts[si].value); if (k === "heard" && /other/i.test(st[si])) heardOther = true; got(label2, k, req2, "", null, !!saved); }
        else leave(label2, k, req2, "", { kind: "select", opts: st });
      } else if (el.getAttribute("role") === "combobox" || el.getAttribute("aria-autocomplete") === "list" || el.getAttribute("aria-haspopup") === "listbox") {
        var canKnow = !!(saved || val || (k && pickText(k, p)));
        if (dry) {   /* read its options: a list the profile has an answer in is fine; otherwise the person is asked, with the same options */
          var ro = await comboRead(el);
          if (ro.some(function (o) { return CONSENT_OPT.test(o); })) { consentLeft(label2 + " (the person answers it)", req2, "the person answers it"); continue; }
          if (ro.some(function (o) { return EEO_OPT.test(o); })) { rep.seen--; rep.eeoSkipped++; note(label2, "", "voluntary, skipped", req2); continue; }
          var ok = canKnow && (!ro.length || chooseOpt(ro, k, p, saved) >= 0 || (!saved && val && chooseOpt(ro, null, p, val) >= 0) || /^(city|school|country|state)$/.test(k || ""));
          if (ok) got(label2, k, req2, "would pick", null, !!saved); else leave(label2, k, req2, "", ro.length ? { kind: "select", opts: ro } : { kind: "text" });
          continue;
        }
        if (!canKnow) { leave(label2, k, req2); continue; }
        var typeText = saved ? String(saved).split("\n")[0] : (k && YN_KEYS.test(k)) || k === "heard" || k === "start" ? "" : (k === "city" ? p.city : val);
        var how = await comboPick(el, typeText, function (texts) {
          var c = chooseOpt(texts, k, p, saved);
          if (c < 0 && !saved && val) c = chooseOpt(texts, null, p, val);
          if (c >= 0 && k === "heard" && /other/i.test(texts[c])) heardOther = true;
          return c;
        });
        if (how === "eeo") { rep.seen--; rep.eeoSkipped++; note(label2, "", "voluntary, skipped", req2); }
        else if (how === "picked" || how === "typed") got(label2, k, req2, how, null, !!saved);
        else leave(label2, k, req2);
      } else {
        if (!val) { leave(label2, k, req2, "", { kind: kindOf(el) }); continue; }
        if (dry) { got(label2, k, req2, "would fill", null, !!saved); continue; }
        setValue(el, val, k === "city");
        if (k === "city") {   /* a place box (Lever's) searches as you type and empties itself unless a suggestion is chosen */
          el.dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true }));
          var pc = pickText("city", p);
          if (pc && await pickSuggestion(el, pc[0])) { got(label2, k, req2, "picked"); continue; }
          el.dispatchEvent(new Event("blur", { bubbles: true }));
          await sleep(50);
        }
        if (el.value) got(label2, k, req2, "filled", el, !!saved); else leave(label2, k, req2);
      }
    }
    /* Ashby, Workable and others draw Yes/No as buttons inside the question block */
    var rows = new Map();
    [].slice.call(document.querySelectorAll("button[type=button],[role=radio]")).forEach(function (b) {
      if (!/^(yes|no)$/i.test((b.innerText || "").trim()) || b.closest("#uaplyAssistBar")) return;
      if (b.querySelector("input") || (b.closest("label") && b.closest("label").querySelector("input")) || (b.parentElement && b.parentElement.querySelector("input[type=radio],input[type=checkbox]"))) return;   /* a styled real radio, handled above */
      var par = b.parentElement; if (!rows.has(par)) rows.set(par, []); rows.get(par).push(b);
    });
    rows.forEach(function (bs) {
      var bt = bs.map(function (b) { return (b.innerText || "").trim(); });
      var q = clean(groupQuestion(bs, bt));
      if (EEO.test(q)) { rep.eeoSkipped++; note(q, "", "voluntary, skipped", false); return; }
      if (bs.some(function (b) { return b.getAttribute("aria-pressed") === "true" || b.getAttribute("aria-checked") === "true"; })) { rep.prefilled++; return; }
      if (CONSENT_Q.test(q)) { rep.seen++; consentLeft(q + " (the person answers it)", false, "the person answers it"); return; }
      rep.seen++;
      var req = /[*✱]/.test(q) || bs.some(function (b) { return b.closest("[aria-required=true],[required]"); });
      var key = keyOf(q), ans = savedAnswer(q, p, job.co, rep), at = chooseOpt(bt, key, p, ans);
      if (at >= 0) { if (!dry) bs[at].click(); got(q, key, req, "button", null, !!ans); } else leave(q, key, req, "", { kind: "select", opts: ["Yes", "No"] });
    });
    if (!dry) {
      /* the resume goes in last: a form that reads it (Workable, Greenhouse) may then show a progress step over the fields, and on the
         phone the measurement showed Workable's fields unreachable while it did */
      attachResume(p, rep);
      await sleep(300);
      /* a field the page emptied again after we moved on (a place box that wants a suggestion chosen) is not filled: say so */
      typed.forEach(function (t) {
        if (t[0].isConnected && !String(t[0].value || "").trim()) {
          rep.filled--; var at2 = rep.filledKeys.indexOf(t[2] || "answer"); if (at2 >= 0) rep.filledKeys.splice(at2, 1);
          rep.left.push((t[3] ? "(required) " : "") + String(t[1]).slice(0, 70)); if (t[3]) rep.leftReq++;
          if (rep.fields) rep.fields.push({ q: String(t[1]).slice(0, 80), key: t[2] || "", how: "emptied by the page", req: !!t[3] });
        }
      });
    } else rep.resumeInput = !!resumeInput();
    var sb = submitButton();
    rep.submit = !!sb;
    var hc = humanCheck();
    rep.humanCheck = hc.present; rep.checkKind = hc.kind; rep.checkShown = hc.shown;
    if (sb && !dry) {
      sb.style.outline = "3px solid #E11D48"; sb.style.outlineOffset = "3px";
      /* one tap (October 23): the page is scrolled to what the person does next. A check the page shows as a box: the box's own place on
         the page (its container, never anything inside it: UAply does not fill, start or touch a check); otherwise the Submit button */
      var box = hc.shown ? checkBox() : null;
      (box || sb).scrollIntoView({ block: "center" });
      rep.scrolledTo = box ? "check" : "submit";
    }
    rep.ms = Date.now() - t0;
    var leftLine = rep.leftReq ? "Answer the " + rep.leftReq + " question" + (rep.leftReq === 1 ? "" : "s") + " left, " : "";
    if (!dry && opts.banner !== false) banner(hc.present ? ONE_TAP + " " + (leftLine ? leftLine + "complete the check, then tap Submit." : "Review it, complete the check, then tap Submit.") :
      leftLine ? "Filled from your UAply profile. " + leftLine + "review it, then tap Submit." : "Filled from your UAply profile. Review it, then tap Submit.");
    if (!dry) LAST = rep;
    return rep;
  }
  /* the line a form with a human check shows when it opens (Saif, October 23): the person, not UAply, answers the check */
  var ONE_TAP = "One tap to finish: this employer asks you to confirm you are a person.";
  /* the element a shown check sits in on the page (the widget's own box, not its frame's inside), to scroll to: null when none is shown */
  function checkBox() {
    var el = [].slice.call(document.querySelectorAll(CHECK_SEL)).filter(function (e) {
      if (e.closest(".grecaptcha-badge")) return false;
      var r = e.getBoundingClientRect(); return r.width >= 120 && r.height >= 60 && getComputedStyle(e).visibility !== "hidden" && getComputedStyle(e).position !== "fixed";
    })[0];
    return el ? (el.tagName === "IFRAME" && el.parentElement ? el.parentElement : el) : null;
  }
  /* the scan: what the profile cannot answer on this form, to ask in UAply's question box before the form opens. Changes nothing
     (lists are opened to read their choices and closed again). */
  function scan(p, opts) { return fill(p, Object.assign({}, opts || {}, { dry: true, banner: false })); }

  /* the one place that could press Submit: only in "automatic" mode (the owner's per-system switch), only with no human check of any
     kind on the page (looked at again right now), only with nothing required left and the resume attached where the form takes one */
  function submitIfAllowed(mode, rep) {
    rep = rep || LAST;
    if (!mayAuto(mode, rep)) return false;
    var sb = submitButton(); if (!sb) return false;
    sb.click();
    return true;
  }
  /* every condition of automatic submit, looked at again right now: "automatic" (the per-system switch, and the person's own tick on
     record: the app passes it only with both), no human check of any kind on the page, nothing required left (a consent or certification
     box counts: the person ticks those), the resume attached where the form takes one, and a Submit button */
  function mayAuto(mode, rep) {
    if (mode !== "automatic" || !rep) return false;
    var hc = humanCheck();
    return !(hc.present || rep.humanCheck || rep.leftReq > 0 || rep.consentReq > 0 || (rep.resumeInput && !rep.resumeAttached) || !submitButton());
  }
  /* automatic submit with the notice (October 23): "Submitting for you in 3" and a Cancel the person can press; at 0 every condition is
     looked at again and only then is Submit pressed. Resolves "submitted", "cancelled" or "refused" (a condition did not hold: the bar
     says to review it and tap Submit, as in assisted mode). Sent is still said only on the employer's confirmation page. */
  function autoSubmit(mode, rep, wait) {
    rep = rep || LAST;
    if (!mayAuto(mode, rep)) return Promise.resolve("refused");
    var left = Math.max(1, Math.min(10, wait == null ? 3 : wait | 0));
    return new Promise(function (done) {
      var old = document.getElementById("uaplyAssistBar"); if (old) old.remove();
      var b = document.createElement("div"); b.id = "uaplyAssistBar"; b.setAttribute("role", "status");
      b.style.cssText = "position:fixed;left:8px;right:8px;bottom:8px;z-index:2147483647;background:#2A1218;color:#fff;font:600 15px/1.35 system-ui,sans-serif;padding:10px 10px 10px 14px;border-radius:14px;box-shadow:0 8px 24px rgba(0,0,0,.3);display:flex;gap:10px;align-items:center";
      var t = document.createElement("span"); t.style.flex = "1";
      var c = document.createElement("button"); c.type = "button"; c.id = "uaplyAssistCancel"; c.textContent = "Cancel";
      c.style.cssText = "font:700 15px system-ui,sans-serif;min-height:44px;min-width:88px;border-radius:12px;border:0;background:#fff;color:#2A1218";
      b.appendChild(t); b.appendChild(c); document.body.appendChild(b);
      var timer = null, over = false;
      function end(how) { if (over) return; over = true; clearInterval(timer); if (how !== "submitted") banner("Not submitted. Review it, then tap Submit when you are ready."); done(how); }
      c.addEventListener("click", function (e) { e.stopPropagation(); end("cancelled"); });
      function step() {
        if (over) return;
        if (left <= 0) { end(submitIfAllowed(mode, rep) ? "submitted" : "refused"); return; }
        t.textContent = "Submitting for you in " + left + "... Filled from your UAply profile; nothing voluntary was answered.";
        left--;
      }
      step(); timer = setInterval(step, 1000);
    });
  }

  /* the employer's confirmation page: only then does UAply say Sent */
  function confirmed() {
    var t = (document.body && document.body.innerText || "").slice(0, 4000);
    if (document.querySelector("input[type=file]") && submitButton()) return false;   /* the form is still there: not sent */
    return /thank(s| you) for (applying|your application|your interest|submitting)|application (has been |was )?(submitted|received|sent)|we('ve| have) received your application|successfully (submitted|applied)|your application (is|has been) (in|on its way|complete)/i.test(t) ||
      /\/(confirmation|thank[-_]?you|thanks|submitted|success)\b/i.test(location.pathname);
  }

  /* the phone app's one way in (AssistActivity.CALL, which first checks the page's own address): what the page shows ("ask"), the scan
     and the fill. Their results stay in here, never in page globals, which the page could write itself (window.__uaplyScan was one: a
     page could have put its own questions into UAply's question box, or said Sent) */
  var STATE = { ran: "", scan: null, rep: null };
  function run(C) {
    C = C || {};
    if (C.act === "ask") {
      return JSON.stringify({ c: confirmed(), n: document.querySelectorAll("input:not([type=hidden]),textarea,select").length, ran: STATE.ran === location.href,
        rep: STATE.rep, scan: STATE.scan, url: location.href });
    }
    if (C.act === "scan") {
      STATE.ran = location.href; STATE.scan = null;
      scan(C.p || {}, { job: C.j || {} }).then(function (r) {
        STATE.scan = JSON.stringify({ questions: r.questions || [], seen: r.seen, filled: r.filled, keys: r.keys, answerKeys: r.answerKeys, resume: !!r.resumeInput });
      }, function () { STATE.scan = JSON.stringify({ questions: [] }); });
      return "scanning";
    }
    if (C.act === "fill") {
      STATE.ran = location.href; STATE.rep = null;
      fill(C.p || {}, { job: C.j || {}, banner: true }).then(function (r) {
        var out = { seen: r.seen, filled: r.filled, leftReq: r.leftReq, eeoSkipped: r.eeoSkipped, resumeAttached: r.resumeAttached,
          humanCheck: r.humanCheck, checkKind: r.checkKind, submit: r.submit, scrolledTo: r.scrolledTo || "", ms: r.ms };
        STATE.rep = JSON.stringify(out);
        if (C.mode === "automatic") autoSubmit("automatic", r).then(function (how) { out.auto = how; STATE.rep = JSON.stringify(out); });
      }, function () { STATE.rep = JSON.stringify({ error: true }); });
      return "filling";
    }
    return "";
  }

  if (KEY) {   /* only run, under the name the page cannot guess, and fixed: the page can neither replace it nor wrap it */
    Object.defineProperty(window, NAME, { value: Object.freeze({ run: run }), enumerable: false, writable: false, configurable: false });
  } else {
    window.UAplyAssist = { fill: fill, scan: scan, confirmed: confirmed, submitIfAllowed: submitIfAllowed, autoSubmit: autoSubmit, humanCheck: humanCheck, keyOf: keyOf, answerKey: akey, savedAnswer: savedAnswer, ynOf: ynOf, eeo: EEO, eeoOption: EEO_OPT, labelOf: labelOf, run: run };
  }
})();
