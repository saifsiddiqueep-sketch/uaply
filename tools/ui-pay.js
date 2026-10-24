// Pay as the posting gives it (the recommendations list, October 23): never guessed or estimated. A job with no pay says "Pay not listed"
// in the pay line's place; a yearly range is shown as given with "per year", an hourly one with "per hour" (its cents too), and nothing
// makes a yearly figure from an hourly one or the reverse. One job of each kind, checked on the deck card (its pay line and its Salary
// line), in Job Tracker's rows, in Share this job's rows (the friend's landing when the shared job has closed) and in the application
// summary the server sends (the "Pay" line of the receipt in the test inbox).
//   W=390 H=844 PORT=<sandbox port, sign-up test mode, delivery test> node tools/cdp.js tools/ui-pay.js      (and W=1280 H=800)
const gateSignup = require("./gate-signup.js");
module.exports = async ({ ev, sleep, nav, send, logs }) => {
  const PORT = process.env.PORT, W = Number(process.env.W || 1280), H = Number(process.env.H || 800), phone = W < 700, base = "http://127.0.0.1:" + PORT;
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + "[pay " + W + "] " + name + (extra !== undefined && !ok ? "  | " + String(extra).slice(0, 400) : "")); };
  if (!phone) await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  // any figure made from another: the hourly range as a year ($18 x 2080 = $37k, $22.50 x 2080 = $47k) or the yearly one as an hour
  const DERIVED = /\$37k|\$47k|\$37,440|\$46,800|\$28\.85|\$38\.46|\$29 |\$38 /;

  const who = await gateSignup({ ev, sleep, nav: (u) => send("Page.navigate", { url: u }).then(() => sleep(300)) }, base, "pay");
  check("the test person signs up through the sign-in gate first", !!who.ok, JSON.stringify(who));
  await send("Page.navigate", { url: base + "/" });
  for (let i = 0; i < 80 && !(await ev("(()=>{try{const w=" + FW + ";return !!(w.__uaply&&w.__uaplyJobs&&w.document.getElementById('bnav'))}catch(e){return false}})()")); i++) await sleep(250);
  await sleep(1500);
  await ev("(()=>{const b=" + F + ".getElementById('kcYes');if(b){b.ownerDocument.querySelectorAll('.kcTick').forEach(c=>{c.checked=true});b.disabled=false;b.click()}})()"); await sleep(800);
  await ev("(()=>{const b=[...(" + F + ").querySelectorAll('#locAsk button')].find(x=>/Not now/.test(x.innerText));if(b)b.click()})()");

  // the three postings, and nothing else in the deck; the profile asks for $100k a year
  const mk = (id, co, role, sal, unit) => Object.assign({ id, co, role, sal, live: true, loc: "Remote (US)", mode: "remote", type: "job", yrs: 0, edu: "High school",
    skills: ["Excel"], blurb: "A test posting.", url: "https://example.com/jobs/" + id, source: co + "'s careers page", apply: "link", contact: "" }, unit ? { salUnit: unit } : {});
  const JOBS = [mk(4243001, "Yearly Co", "Yearly Analyst", [60000, 80000]), mk(4243002, "Hourly Co", "Hourly Barista", [18, 22.5], "hour"), mk(4243003, "Unlisted Co", "Unlisted Clerk", [0, 0])];
  const EXPECT = { 4243001: { pay: "$60k–$80kper year", ask: "$60k to $80k" }, 4243002: { pay: "$18–$22.50per hour", ask: "$18–$22.50 an hour" }, 4243003: { pay: "Pay not listed", ask: "Not listed" } };
  await ev("(()=>{const w=" + FW + ",A=w.__uaply;A.JOBS.splice(0);A.S.profile.salary=100000;Object.keys(A.S.decisions||{}).forEach(k=>delete A.S.decisions[k]);" +
    "if(A.setFilter)A.setFilter('all');if(A.setMin)A.setMin(0);if(A.setType)A.setType('job');w.__uaplyJobs.add(" + JSON.stringify(JOBS) + ");A.renderAll();return A.JOBS.length})()");
  await sleep(600);

  // ---- the deck card: its pay line and its Salary line, for each kind, then pass it (the next one comes up) ----
  const seen = {};
  for (let k = 0; k < 3; k++) {
    const c = JSON.parse(await ev("(()=>{const d=" + F + ",c=d.querySelector('#deck .card.top');if(!c)return 'null';const p=c.querySelector('.pay'),li=[...c.querySelectorAll('.crit li')].find(l=>/Salary/.test(l.innerText));" +
      "const r=p.getBoundingClientRect();return JSON.stringify({id:+c.dataset.id,pay:p.textContent.trim(),sal:li?li.innerText.replace(/\\s+/g,' ').trim():'',dot:li?li.querySelector('.dot').getAttribute('aria-label'):'',w:Math.round(r.width),cw:Math.round(c.clientWidth),card:c.innerText.replace(/\\s+/g,' ')})})()"));
    if (!c) { check("a job card is on top (" + (k + 1) + " of 3)", false); break; }
    seen[c.id] = c;
    await ev("(()=>{const b=" + F + ".getElementById('btnNo');if(b)b.click()})()"); await sleep(900);
  }
  const Y = seen[4243001], Hr = seen[4243002], U = seen[4243003];
  check("all three postings came up on the deck", !!(Y && Hr && U), JSON.stringify(Object.keys(seen)));
  if (Y && Hr && U) {
    check("a yearly range: the card shows it as given, $60k–$80k per year", Y.pay === EXPECT[4243001].pay, Y.pay);
    check("an hourly range: the card shows it as given with its unit and cents, $18–$22.50 per hour", Hr.pay === EXPECT[4243002].pay, Hr.pay);
    check("no pay: the card says Pay not listed in the pay line's place", U.pay === EXPECT[4243003].pay, U.pay);
    check("the Salary line: the yearly range against the yearly minimum, as before", /\$60k to \$80k/.test(Y.sal) && /You want \$100k\+/.test(Y.sal), Y.sal);
    // since October 24 hourly and yearly pay are matched on one scale (an hour is 1/2080 of a year): $18 to $22.50 an hour is about $47k a
    // year, under this person's $100k a year, so the Salary line is not met; the line itself still names the pay as the posting gives it
    check("the Salary line of the hourly job names the hourly pay, measured against the yearly minimum on one scale (Not met: about $47k a year)", Hr.sal.includes(EXPECT[4243002].ask) && Hr.dot === "Not met", Hr.sal + " / " + Hr.dot);
    check("the Salary line of the job with no pay says Not listed", /Salary\s*Not listed/.test(U.sal), U.sal);
    check("no card shows a figure made from another (an hourly range as a year, or a yearly one as an hour)", ![Y, Hr, U].some((x) => DERIVED.test(x.card)), [Y, Hr, U].map((x) => x.card).join(" || "));
    check("the pay line fits the card", [Y, Hr, U].every((x) => x.w <= x.cw), JSON.stringify([Y, Hr, U].map((x) => [x.w, x.cw])));
  }

  // ---- Job Tracker: the three rows (passed) name no pay that the posting did not give ----
  await ev("(()=>{const b=" + F + ".getElementById('nb-dash');if(b)b.click()})()"); await sleep(500);
  await ev("(()=>{const e=[...(" + F + ").querySelectorAll('.nitem')].find(b=>b.innerText.trim().startsWith('Applied'));if(e)e.click()})()"); await sleep(800);
  const rows = JSON.parse(await ev("JSON.stringify([...(" + F + ").querySelectorAll('.row')].filter(r=>r.getClientRects().length).map(r=>r.innerText.replace(/\\s+/g,' ').trim()).filter(t=>/Yearly Co|Hourly Co|Unlisted Co/.test(t)))"));
  check("Job Tracker lists the three postings", rows.length === 3, JSON.stringify(rows));
  check("...and no row shows a pay figure the posting did not give (rows name no pay, or the pay as given)",
    rows.length === 3 && rows.every((r) => !DERIVED.test(r) && (!/\$\d/.test(r) || /\$60k–\$80k|\$18–\$22\.50/.test(r))), JSON.stringify(rows));

  // ---- Share this job's rows (the friend's landing, "jobs like it"): the same words through the same helper ----
  const share = JSON.parse(await ev("(()=>{const w=" + FW + ";if(typeof w.uaPayText!=='function')return 'null';return JSON.stringify(" + JSON.stringify(JOBS) + ".map(j=>w.uaPayText(j,1)||'Pay not listed'))})()"));
  check("the pay words every other screen uses (Share this job's rows): $60k–$80k a year, $18–$22.50 an hour, Pay not listed",
    JSON.stringify(share) === JSON.stringify(["$60k–$80k a year", "$18–$22.50 an hour", "Pay not listed"]), JSON.stringify(share));
  const shareSrc = await ev("(()=>{const s=[...document.scripts].map(x=>x.src).filter(Boolean);return s.some(u=>/uaply-share\\.js/.test(u))})()");
  if (shareSrc) {
    const sr = JSON.parse(await ev("(()=>{const d=" + F + ";return JSON.stringify([...d.querySelectorAll('.ushr-row .ushr-pay')].map(e=>e.textContent))})()"));
    check("...and any Share row on screen shows pay only as given", sr.every((t) => !DERIVED.test(t)), JSON.stringify(sr));
  }

  // ---- the application summary (the receipt's Pay line, in the test inbox) ----
  const prof = { name: "Pay Tester", email: who.email || "pay.tester@example.com", ext: { phone: "2155550123" } };
  const st = JSON.parse(await ev("Promise.all(" + JSON.stringify(JOBS) + ".map(j=>fetch('/api/apply',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'}," +
    "body:JSON.stringify({consent:true,confirm_real:true,job:j,profile:" + JSON.stringify(prof) + ",match:70})}).then(r=>r.status))).then(x=>JSON.stringify(x))"));
  check("the three applications are accepted by the test server", st.every((s) => s === 200), JSON.stringify(st));
  await sleep(800);
  const box = await ev("fetch('/outbox').then(r=>r.text()).then(t=>t.replace(/<[^>]+>/g,' ').replace(/&nbsp;/g,' ').replace(/\\s+/g,' '))");
  // the person's own receipt ("finish your application to <the employer>"), its THE JOB block
  const near = (co) => { const i = box.indexOf("your application to " + co); return i < 0 ? "" : box.slice(i, i + 700); };
  check("the summary of the yearly job: Pay: $60k to $80k a year", /Pay:? \$60k to \$80k a year/.test(near("Yearly Co")), near("Yearly Co").slice(0, 500));
  check("the summary of the hourly job: Pay: $18 to $22.50 an hour", /Pay:? \$18 to \$22\.50 an hour/.test(near("Hourly Co")), near("Hourly Co").slice(0, 500));
  check("the summary of the job with no pay: Pay: Not listed", /Pay:? Not listed/.test(near("Unlisted Co")), near("Unlisted Co").slice(0, 500));
  check("no summary shows a figure made from another", !DERIVED.test(box), (box.match(DERIVED) || [""])[0]);

  const errs = logs.filter((l) => !/favicon|ERR_FILE_NOT_FOUND|401|403/.test(l));
  check("no script errors", errs.length === 0, errs.join(" | "));
  console.log("\n" + (n - bad) + " / " + n);
  if (bad) throw new Error(bad + " pay check(s) failed");
};
