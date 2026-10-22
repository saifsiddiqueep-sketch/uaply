/* UAply assisted apply: the person's own autofill for an employer's hosted application form (Greenhouse, Lever, Ashby, SmartRecruiters,
   Workable, and any plain HTML form). The phone app injects it into the employer's page it opened in its in-app browser
   (mobile/android: AssistActivity); tools/assist-measure.js injects it into real postings in Chrome to measure it, and
   tools/test-assist.js into the mock form of each system (tools/fixtures/assist/).

   What it does, with the profile the person keeps in UAply:
     - fills each field whose label (its <label>, aria-label, aria-labelledby, the question block around it, placeholder or name) says
       what it asks: name, email, phone, LinkedIn, website, address, city, state, country, ZIP, current employer and title, school, degree,
       major, graduation, GPA, work authorization, sponsorship, earliest start, relocation, on-site work, "have you worked here before",
       how you heard, "why us" (the person's own words from Profile setup), and any question the person already answered in UAply's
       question box (matched by the question's own words);
     - attaches the resume file to the form's resume input (the file the person keeps in UAply, never a stranger's);
     - never fills a voluntary self-identification question (gender, race, ethnicity, veteran, disability, orientation, pronouns), found
       by the question's words or by its answers ("Male", "Decline to self-identify", "I am a protected veteran"...): the person answers
       those or not, themselves;
     - never ticks a consent, acknowledgement or certification box, and never answers a follow-up ("If yes, ...") or a question about
       someone else (relatives, referrers): the person does;
     - never touches a human check (reCAPTCHA, hCaptcha, Cloudflare Turnstile) and never presses Submit. It scrolls to the Submit button
       and says "Review and tap Submit". submitIfAllowed() is the one place that could press it, and only when the host passes
       mode "automatic" (the owner's per-system switch in shared/assist-systems.json, which the lawyer sets, default "assisted"), the
       page shows no human check of any kind, and every required field is filled. See docs/assisted-apply.md.
   It reports what it did: fields seen, filled, left for the person (and how many of those are required), voluntary questions skipped,
   the resume, any human check (kind, shown or invisible), the Submit button, the time. A field the page empties again after it was
   filled (a place box that wants a suggestion chosen) is reported as left, not filled.

   UAplyAssist.fill(profile, opts) -> Promise<report>. profile: {first,last,name,email,phone,linkedin,website,street,city,state,zip,country,
   company,title,jobStart,jobEnd (YYYY-MM),school,degree,major,grad (YYYY-MM),gpa,auth ('yes'|'no'),sponsor ('yes'|'no'),start,relocate,
   office,former,govt,phd ('yes'|'no'),salary,summary,headline,why,heard (text),answers:{question words: answer},resume:{name,type,b64}}.
   opts: {banner:true|false, job:{co,role}, debug:true (adds rep.fields: what each field was read as)}. */
(function () {
  "use strict";
  if (window.UAplyAssist) return;

  /* voluntary self-identification: by the question, or by its answers */
  var EEO = /\b(gender|sex\b|race\b|racial|ethnic|hispanic|latin[oax]|veteran|disabilit|sexual orientation|transgender|lgbt|pronoun|self[- ]identif|voluntary)/i;
  var EEO_OPT = /^\s*(male|female|man|woman|non-?binary|genderqueer|agender|cisgender|two or more races|white( \(|$)|black or african american|asian( \(|$)|american indian|native hawaiian|hispanic or latin|not hispanic|i am a (protected )?veteran|i am not a (protected )?veteran|i identify as one or more|yes, i have a disability|no, i (do not|don't) have a disability|i (do not|don't) want to answer|decline to self[- ]identify|heterosexual|gay|lesbian|bisexual|he\/him|she\/her|they\/them)\b/i;
  var CHECK_SEL = "iframe[src*='recaptcha'],iframe[src*='hcaptcha'],iframe[src*='turnstile'],iframe[src*='challenges.cloudflare'],iframe[title*='reCAPTCHA' i],iframe[title*='hCaptcha' i],.g-recaptcha,.h-captcha,.cf-turnstile,.grecaptcha-badge,[data-sitekey]";
  var CHECK_SCRIPT = "script[src*='recaptcha'],script[src*='hcaptcha'],script[src*='turnstile'],script[src*='challenges.cloudflare.com']";
  var FIELD_SEL = "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]):not([type=image]):not([type=search]),textarea,select";

  function norm(s) { return String(s || "").toLowerCase().replace(/\s+/g, " ").replace(/[^a-z0-9 ?]/g, "").trim(); }
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

  /* what a label asks for, as a profile key (null: not something the profile answers). Order matters: the first rule that matches wins. */
  var RULES = [
    ["why", /^why\b|why (do you want|are you interested|you want)|what (makes|draws|attracts) you to (join|work)|interested in (working|joining)/i],
    ["name", /\bfirst (name )?(and|&) last name\b|\bfirst and last\b/i],
    ["first", /\b(first|given|preferred first|legal first)[ -]?name\b|^first$/i],
    ["last", /\b(last|family|sur)[ -]?name\b|\bsurname\b|^last$/i],
    ["company", /\b(current|present|most recent) (company|employer)\b|^(company|employer)( name)?$/i],
    ["title", /\b(current|present|most recent) (job )?(title|role|position)\b|^(job )?title$/i],
    ["name", /^(full |your |legal |candidate )?name\b|\bfull (legal )?name\b|\blegal name\b/i],
    ["email", /e-?mail/i],
    ["phone", /^(your |primary |best )?(phone|mobile|cell|telephone)\b|\b(phone|mobile|cell|telephone)( number| no\.?)\b/i],
    ["linkedin", /linked\s?in/i],
    ["github", /\bgithub\b/i],
    ["twitter", /\btwitter\b|^x( handle| profile| url)?$|\bx\.com\b/i],
    ["website", /\b(website|portfolio|personal (site|url|web)|other (website|url|link)|blog)\b/i],
    ["nosponsor", /\bwithout (\w+ ){0,2}sponsorship\b/i],
    ["auth", /(legally )?(authori[sz]ed|eligible|permitted) to work|work authori[sz]ation|right to work|work permit/i],
    ["sponsor", /sponsor/i],
    ["former", /\b(have|had|were|are|do|did) you\b.{0,40}\b(employed|worked|work) (by|at|for|with)\b|\bpreviously (been )?(employed|worked)\b|\bformer\b.*\bemployee\b/i],
    ["govt", /government official/i],
    ["phd", /\b(ph\.?d|doctoral) program\b/i],
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
    if (/^(auth|nosponsor|sponsor|relocate|office|former|govt|phd|heard)$/.test(k) && /any other|additional (context|information|details)|explain|describe|tell us|share (any|more)/i.test(label)) return null;   /* free text around a yes/no topic */
    if (/^(auth|nosponsor|sponsor)$/.test(k) && /limited|temporary|expir|type of visa|visa type|which visa|\bopt\b|\bead\b|\bcpt\b|h-?1b/i.test(label)) return null;   /* about a kind of status the profile does not hold */
    if (/^(auth|nosponsor|sponsor|relocate|office|former|govt|phd)$/.test(k) && label.indexOf("?") < 0 && !/^(are|do|does|will|would|have|has|is|can|could|did|were|please (select|confirm|indicate)|select)\b/i.test(label)) return null;   /* a statement, not a yes/no question */
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
  function yesNo(v) { return v === "yes" ? /^\s*yes\b/i : v === "no" ? /^\s*no\b/i : null; }
  var COUNTRY = { US: /^\s*(united states|usa|us|u\.s\.)/i, CA: /^\s*canada/i, GB: /^\s*(united kingdom|uk|great britain)/i };
  var STATES = { AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California", CO: "Colorado", CT: "Connecticut", DE: "Delaware", DC: "District of Columbia", FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa", KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland", MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi", MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada", NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York", NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia", WA: "Washington", WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming" };
  function stateName(p) { var s = String(p.state || "").trim(); return STATES[s.toUpperCase()] || s; }
  function countryName(p) { var c = String(p.country || "US").toUpperCase(); return c === "US" ? "United States" : c === "CA" ? "Canada" : c === "GB" ? "United Kingdom" : ""; }
  var START_TEXT = { now: "Immediately", "2w": "2 weeks", "1m": "1 month", grad: "After I graduate", flex: "Flexible" };
  /* the option of a choice that matches what the profile says */
  function pickText(key, p) {
    switch (key) {
      case "auth": return yesNo(p.auth);
      case "sponsor": return yesNo(p.sponsor);
      case "nosponsor": return yesNo(noSponsor(p));
      case "relocate": return yesNo(p.relocate);
      case "office": return yesNo(p.office);
      case "former": return p.former === "no" ? /^\s*no\b/i : null;
      case "govt": return yesNo(p.govt);
      case "phd": return yesNo(p.phd);
      case "heard": return /^\s*(job board|online job board|job site|internet|online|website|other)\b/i;
      case "degree": return p.degree ? new RegExp("^\\s*" + esc(String(p.degree).split(/['’ ]/)[0]), "i") : null;
      case "school": return p.school ? new RegExp(esc(p.school), "i") : null;
      case "country": return COUNTRY[String(p.country || "US").toUpperCase()] || null;
      case "state": var s = stateName(p); return s ? new RegExp("^\\s*(" + esc(s) + "|" + esc(String(p.state || "").toUpperCase()) + ")\\b", "i") : null;
      case "city": return p.city ? new RegExp("^\\s*" + esc(p.city), "i") : null;
    }
    return null;
  }
  /* "Can you work here without sponsorship?": yes only for someone authorized who needs none */
  function noSponsor(p) { return p.sponsor === "no" && p.auth === "yes" ? "yes" : p.sponsor === "yes" || p.auth === "no" ? "no" : ""; }
  function fillIn(t, job) { return String(t || "").replace(/\{company\}/g, job && job.co || "your company").replace(/\{role\}/g, job && job.role || "this role"); }
  function textFor(key, p, el, job, req, label) {
    switch (key) {
      case "first": return p.first || String(p.name || "").split(/\s+/)[0];
      case "last": return p.last || String(p.name || "").split(/\s+/).slice(1).join(" ");
      case "name": return p.name || [p.first, p.last].filter(Boolean).join(" ");
      case "email": return p.email; case "phone": return p.phone; case "linkedin": return p.linkedin;
      case "github": return /github\.com/i.test(p.website || "") ? p.website : "";
      case "twitter": return "";
      case "website": return p.website;
      case "company": return p.company; case "title": return p.title;
      case "school": return p.school; case "degree": return p.degree; case "major": return p.major; case "gpa": return p.gpa ? String(p.gpa) : "";
      case "grad":
        if (!/^\d{4}-\d{2}$/.test(p.grad || "")) return "";
        if (el && el.type === "month") return p.grad;
        return new Date(+p.grad.slice(0, 4), +p.grad.slice(5) - 1, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });
      case "start": return START_TEXT[p.start] || p.start || "";
      case "jobmonth": case "jobyear": case "endmonth": case "endyear":   /* the most recent job, from Profile setup (an empty end: still there) */
        var ym = key.indexOf("job") === 0 ? p.jobStart : p.jobEnd;
        if (!/^\d{4}-\d{2}$/.test(ym || "")) return "";
        return /year$/.test(key) ? ym.slice(0, 4) : new Date(2000, +ym.slice(5) - 1, 1).toLocaleDateString("en-US", { month: "long" });
      case "heard": return p.heard;
      case "salary": return req ? (p.salary ? String(p.salary) : "") : "";   /* only where the form requires it (Profile setup says so) */
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
      case "auth": case "sponsor": case "relocate": case "office": case "govt": case "phd":
        return p[key] === "yes" ? "Yes" : p[key] === "no" ? "No" : "";
      case "former": return p.former === "no" ? "No" : "";
      case "nosponsor": var ns = noSponsor(p); return ns === "yes" ? "Yes" : ns === "no" ? "No" : "";
    }
    return "";
  }
  /* a question the person already answered in UAply's question box, matched by its words */
  function savedAnswer(label, p) {
    var a = p.answers || {}, n = norm(label);
    if (!n) return "";
    if (a[n]) return a[n];
    for (var k in a) if (Object.prototype.hasOwnProperty.call(a, k) && norm(k) === n) return a[k];
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

  /* React Select and other comboboxes: open the list, type the answer, wait for the options, choose the one that matches */
  function listOptions() {
    return [].slice.call(document.querySelectorAll("[role=option],[role=listbox] li,[class*='menu' i] [class*='option' i]")).filter(function (o) { return (o.offsetParent || o.getClientRects().length) && (o.innerText || "").length < 200; });
  }
  async function comboPick(el, text, re) {
    try {
      el.focus();
      var ctl = el.closest("[class*='control' i]") || el;
      ctl.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
      await sleep(60);
      if (el.getAttribute("aria-expanded") !== "true" && typeof TouchEvent === "function") {   /* React Select on a phone opens on touchend, not mousedown */
        try { var tch = new Touch({ identifier: Date.now(), target: ctl, clientX: 1, clientY: 1 }); ctl.dispatchEvent(new TouchEvent("touchend", { bubbles: true, cancelable: true, changedTouches: [tch] })); } catch (e) {}
        await sleep(60);
      }
      if (el.getAttribute("aria-expanded") === "false") el.click();
      if (text) setValue(el, text, true); else el.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
      var hit = null, opts = [];
      for (var i = 0; i < 16 && !hit; i++) {
        await sleep(150);
        opts = listOptions();
        if (opts.some(function (o) { return EEO_OPT.test(o.innerText || ""); })) { el.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); return "eeo"; }
        opts = opts.filter(function (o) { return !/notice|no-?options|loading|empty/i.test(String(o.className || "")) && !/^(no (options|results)|loading)/i.test((o.innerText || "").trim()); });
        hit = opts.filter(function (o) { return (re && re.test(o.innerText)) || (text && norm(o.innerText) === norm(text)); })[0] || null;
      }
      if (hit) { hit.dispatchEvent(new MouseEvent("mousedown", { bubbles: true })); hit.click(); await sleep(100); return "picked"; }
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      return el.value && text && norm(el.value) === norm(text) ? "typed" : "no";
    } catch (e) { return "no"; }
  }
  /* a place box that lists suggestions under the field (not a combobox by its markup): choose the one that starts with the city */
  async function pickSuggestion(el, re) {
    if (!re) return false;
    var box = el.closest(".application-field") || (el.parentElement && el.parentElement.parentElement) || el.parentElement;
    if (!box || !box.querySelector("[class*='dropdown' i],[class*='suggest' i],[class*='results' i],[class*='autocomplete' i],[role=listbox]")) return false;
    for (var i = 0; i < 24; i++) {
      await sleep(150);
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

  var LAST = null;
  async function fill(p, opts) {
    opts = opts || {};
    var t0 = Date.now(), job = opts.job || {};
    var rep = { url: location.href, seen: 0, filled: 0, left: [], leftReq: 0, eeoSkipped: 0, prefilled: 0, humanCheck: false, checkKind: "", checkShown: false,
      resumeInput: false, resumeAttached: false, submit: false, ms: 0, filledKeys: [] };
    if (opts.debug) rep.fields = [];
    function note(label, key, how, req) { if (rep.fields) rep.fields.push({ q: String(label).slice(0, 80), key: key || "", how: how, req: !!req }); }
    function leave(label, key, req, why) { rep.left.push((req ? "(required) " : "") + String(label).slice(0, 70)); if (req) rep.leftReq++; note(label, key, why || "left", req); }
    var typed = [];
    function got(label, key, req, how, el) { rep.filled++; rep.filledKeys.push(key || "answer"); note(label, key, how || "filled", req); if (el) typed.push([el, label, key, req]); }
    var done = new Set();
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
        var otexts = group.map(optionText), label = groupQuestion(group, otexts), raw = label;
        if (group.length === 1 && el.type === "checkbox" && (!label || label === el.name)) label = otexts[0];
        var req = group.some(function (g) { return g.required || g.getAttribute("aria-required") === "true"; }) || /[*✱]/.test(raw);
        label = clean(label);
        if (EEO.test(label) || otexts.some(function (o) { return EEO_OPT.test(o); })) { rep.eeoSkipped++; note(label, "", "voluntary, skipped", req); continue; }
        if (group.some(function (g) { return g.checked; })) { rep.prefilled++; note(label, "", "already chosen", req); continue; }   /* the person or the page chose it */
        rep.seen++;
        if (el.type === "checkbox" && /consent|acknowledg|agree|privacy|terms|certif|confirm|i have read|authori[sz]e/i.test(label + " " + otexts.join(" "))) { leave(label + " (the person ticks it)", "", req, "the person ticks it"); continue; }
        if (el.type === "radio" && /\b(consent|acknowledg|i agree|agree to|certify|i have read)\b/i.test(label + " " + otexts.join(" "))) { leave(label + " (the person answers it)", "", req, "the person answers it"); continue; }   /* an agreement drawn as radios */
        var key = keyOf(label), re = key ? pickText(key, p) : null, ans = savedAnswer(label, p);
        var hit = group.filter(function (g, j) { var t = otexts[j]; return (re && re.test(t)) || (ans && norm(t) === norm(ans)); });
        if (hit.length && (el.type === "radio" || hit.length === 1)) { (hit[0].closest("[role=radio],[role=checkbox]") || hit[0]).click(); if (!hit[0].checked) hit[0].click(); got(label, key, req); } else leave(label, key, req);
        continue;
      }
      done.add(el);
      var raw2 = rawLabelOf(el), label2 = clean(raw2), req2 = required(el, raw2);
      if (EEO.test(label2) || (el.tagName === "SELECT" && [].slice.call(el.options).some(function (o) { return EEO_OPT.test(o.text); })) ||
          (/^(custom|other|please specify|self[- ]describe|prefer to self[- ]describe|not listed)\b/i.test(label2) && eeoNear(el))) { rep.eeoSkipped++; note(label2, "", "voluntary, skipped", req2); continue; }
      if (el.tagName === "SELECT" ? (el.selectedIndex > 0 && el.options[el.selectedIndex].value) : (el.value && el.value.trim())) { rep.prefilled++; note(label2, "", "already filled", req2); continue; }   /* the page filled it */
      rep.seen++;
      var k = keyOf(label2), saved = savedAnswer(label2, p), val = saved || (k ? textFor(k, p, el, job, req2, label2) : "");
      if (el.tagName === "SELECT") {
        if (!val && !(k && pickText(k, p))) { leave(label2, k, req2); continue; }
        var r2 = (!saved && k && pickText(k, p)) || new RegExp("^\\s*" + esc(String(val)), "i");
        var o = [].slice.call(el.options).filter(function (x) { return x.value && r2.test(x.text); })[0];
        if (!o && k === "city") { var rc = pickText("country", p); o = rc && [].slice.call(el.options).filter(function (x) { return x.value && rc.test(x.text); })[0]; }   /* "What is your location?" as a list of countries */
        if (o) { setValue(el, o.value); got(label2, k, req2); } else leave(label2, k, req2);
      } else if (el.getAttribute("role") === "combobox" || el.getAttribute("aria-autocomplete") === "list" || el.getAttribute("aria-haspopup") === "listbox") {
        var yn = /^(auth|nosponsor|sponsor|relocate|office|former|govt|phd|heard)$/.test(k || "");
        if (!val && !(k && pickText(k, p))) { leave(label2, k, req2); continue; }
        var how = await comboPick(el, yn && !saved ? "" : (k === "city" ? p.city : val), saved ? null : (k ? pickText(k, p) : null));
        if (how === "eeo") { rep.seen--; rep.eeoSkipped++; note(label2, "", "voluntary, skipped", req2); }
        else if (how === "picked" || how === "typed") got(label2, k, req2, how);
        else leave(label2, k, req2);
      } else {
        if (!val) { leave(label2, k, req2); continue; }
        setValue(el, val, k === "city");
        if (k === "city") {   /* a place box (Lever's) searches as you type and empties itself unless a suggestion is chosen */
          el.dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true }));
          if (await pickSuggestion(el, pickText("city", p))) { got(label2, k, req2, "picked"); continue; }
          el.dispatchEvent(new Event("blur", { bubbles: true }));
          await sleep(50);
        }
        if (el.value) got(label2, k, req2, "filled", el); else leave(label2, k, req2);
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
      var q = clean(groupQuestion(bs, bs.map(function (b) { return (b.innerText || "").trim(); })));
      if (EEO.test(q)) { rep.eeoSkipped++; note(q, "", "voluntary, skipped", false); return; }
      if (bs.some(function (b) { return b.getAttribute("aria-pressed") === "true" || b.getAttribute("aria-checked") === "true"; })) { rep.prefilled++; return; }
      rep.seen++;
      var key = keyOf(q), want = key ? pickText(key, p) : null, ans = savedAnswer(q, p);
      var b = bs.filter(function (x) { var t = (x.innerText || "").trim(); return (want && want.test(t)) || (ans && norm(ans) === norm(t)); })[0];
      if (b) { b.click(); got(q, key, false, "button"); } else leave(q, key, false);
    });
    /* the resume goes in last: a form that reads it (Workable, Greenhouse) may then show a progress step over the fields, and on the
       phone the measurement showed Workable's fields unreachable while it did */
    attachResume(p, rep);
    await sleep(300);
    /* a field the page emptied again after we moved on (a place box that wants a suggestion chosen) is not filled: say so */
    typed.forEach(function (t) {
      if (t[0].isConnected && !String(t[0].value || "").trim()) {
        rep.filled--; var at = rep.filledKeys.indexOf(t[2] || "answer"); if (at >= 0) rep.filledKeys.splice(at, 1);
        rep.left.push((t[3] ? "(required) " : "") + String(t[1]).slice(0, 70)); if (t[3]) rep.leftReq++;
        if (rep.fields) rep.fields.push({ q: String(t[1]).slice(0, 80), key: t[2] || "", how: "emptied by the page", req: !!t[3] });
      }
    });
    var sb = submitButton();
    rep.submit = !!sb;
    if (sb) { sb.scrollIntoView({ block: "center" }); sb.style.outline = "3px solid #E11D48"; sb.style.outlineOffset = "3px"; }
    var hc = humanCheck();
    rep.humanCheck = hc.present; rep.checkKind = hc.kind; rep.checkShown = hc.shown;
    rep.ms = Date.now() - t0;
    if (opts.banner !== false) banner(rep.leftReq ? "Filled from your UAply profile. Answer the " + rep.leftReq + " question" + (rep.leftReq === 1 ? "" : "s") + " left, review it, then tap Submit." :
      hc.shown ? "Filled from your UAply profile. Review it, complete the check, then tap Submit." : "Filled from your UAply profile. Review it, then tap Submit.");
    LAST = rep;
    return rep;
  }

  /* the one place that could press Submit: only in "automatic" mode (the owner's per-system switch), only with no human check of any
     kind on the page (looked at again right now), only with nothing required left and the resume attached where the form takes one */
  function submitIfAllowed(mode, rep) {
    rep = rep || LAST;
    if (mode !== "automatic" || !rep) return false;
    var hc = humanCheck();
    if (hc.present || rep.humanCheck || rep.leftReq > 0 || (rep.resumeInput && !rep.resumeAttached)) return false;
    var sb = submitButton(); if (!sb) return false;
    sb.click();
    return true;
  }

  /* the employer's confirmation page: only then does UAply say Sent */
  function confirmed() {
    var t = (document.body && document.body.innerText || "").slice(0, 4000);
    if (document.querySelector("input[type=file]") && submitButton()) return false;   /* the form is still there: not sent */
    return /thank(s| you) for (applying|your application|your interest|submitting)|application (has been |was )?(submitted|received|sent)|we('ve| have) received your application|successfully (submitted|applied)|your application (is|has been) (in|on its way|complete)/i.test(t) ||
      /\/(confirmation|thank[-_]?you|thanks|submitted|success)\b/i.test(location.pathname);
  }

  window.UAplyAssist = { fill: fill, confirmed: confirmed, submitIfAllowed: submitIfAllowed, humanCheck: humanCheck, keyOf: keyOf, eeo: EEO, eeoOption: EEO_OPT, labelOf: labelOf };
})();
