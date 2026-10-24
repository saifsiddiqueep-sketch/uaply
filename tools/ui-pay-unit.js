// One pay question, per year or per hour (Saif, October 24): Profile setup step 3 "Location and pay" asks the lowest pay with a per year /
// per hour choice beside it, remembered across a reload; step 5 no longer asks a second, yearly-only pay question (employers' forms get
// step 3's amount, per year and per hour); matching puts hourly and yearly pay on one scale (an hour is 1/2080 of a year) while the card
// still shows each posting's own figure and unit.
//   W=390 H=844 PORT=<sandbox or dev, sign-up test mode> node tools/cdp.js tools/ui-pay-unit.js      (and W=1280 H=800)
module.exports = async ({ ev, sleep, nav, send, logs }) => {
  const PORT = process.env.PORT, W = Number(process.env.W || 390), H = Number(process.env.H || 844), base = "http://127.0.0.1:" + PORT;
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + "[pay-unit " + W + "] " + name + (extra !== undefined && !ok ? "  | " + String(extra).slice(0, 300) : "")); };
  if (W >= 700) await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  const who = await require("./gate-signup.js")({ ev, sleep, nav }, base, "payunit", { api: true });
  check("the test person signs up first", !!who.ok);
  const load = async () => {
    await send("Page.navigate", { url: base + "/" });
    for (let i = 0; i < 80 && !(await ev("!!(" + F + "&&" + FW + ".__uaply&&" + FW + ".__uaplyOpenProf&&" + F + ".getElementById('bnav'))").catch(() => false)); i++) await sleep(250);
    await sleep(800);
    await ev("(()=>{const b=" + F + ".getElementById('kcYes');if(b)b.click()})()"); await sleep(300);
  };
  const step3 = async () => { await ev(FW + ".__uaplyOpenProf('where')"); await sleep(900); };
  const field = () => ev("(()=>{const d=" + F + ",w=d.defaultView,i=d.getElementById('pSalary'),ls=[...d.querySelectorAll('.payunit label')];if(!i)return 'null';" +
    "return JSON.stringify({vis:i.getClientRects().length>0,val:i.value,ph:i.placeholder,unit:(d.querySelector('.payunit input:checked')||{}).value,labels:ls.map(l=>l.textContent.trim())," +
    "h:ls.map(l=>Math.round(l.getBoundingClientRect().height)),fs:ls.map(l=>parseFloat(w.getComputedStyle(l).fontSize)),row:(()=>{const a=i.getBoundingClientRect(),b=d.querySelector('.payunit').getBoundingClientRect();return {sw:d.documentElement.scrollWidth>w.innerWidth+1,right:Math.round(Math.max(a.right,b.right)),vw:w.innerWidth}})()," +
    "label:(d.querySelector('label[for=pSalary]')||{}).textContent,help:(d.getElementById('payHelp')||{}).textContent})})()").then(JSON.parse);
  const save = async () => { await ev("(()=>{const b=" + F + ".getElementById('wzNext');if(b)b.click()})()"); await sleep(900); };
  const prof = () => ev("JSON.stringify((()=>{const p=" + FW + ".__uaply.S.profile;return {payUnit:p.payUnit,salary:p.salary,ext:{salary:p.ext&&p.ext.salary,salaryHour:p.ext&&p.ext.salaryHour,payUnit:p.ext&&p.ext.payUnit}}})())").then(JSON.parse);

  // ---- the question: one amount and per year / per hour, 14 px, 44 px targets, fits the screen ----
  await load(); await step3();
  let f = await field();
  check("step 3 asks the lowest pay with a per year / per hour choice beside it, per year by default", !!f && f.vis && f.unit === "year" && JSON.stringify(f.labels) === '["per year","per hour"]' && /Lowest pay/.test(f.label), JSON.stringify(f));
  check("the choices are 44 px tall targets in 14 px text, and the row fits the screen (no sideways scroll)", f.h.every((x) => x >= 44) && f.fs.every((x) => x >= 14) && !f.row.sw && f.row.right <= f.row.vw, JSON.stringify(f));
  check("plain example and help: e.g. 55000 per year, or 18 per hour", f.ph === "e.g. 55000" && /55000 per year/.test(f.help) && /18 per hour/.test(f.help), JSON.stringify(f));
  const s5 = await ev("(()=>{const d=" + F + ";return JSON.stringify({box:!!d.getElementById('px-salary'),text:/Expected yearly pay/.test(d.body.innerText)})})()").then(JSON.parse);
  check("step 5 no longer asks a second pay question (Expected yearly pay)", !s5.box && !s5.text, JSON.stringify(s5));

  // ---- per hour, saved, then a reload ----
  await ev("(()=>{const d=" + F + ";d.getElementById('pu-hour').click();const i=d.getElementById('pSalary');i.value='18';i.dispatchEvent(new Event('input',{bubbles:true}))})()"); await sleep(200);
  f = await field();
  check("per hour: the example changes to e.g. 18", f.unit === "hour" && f.ph === "e.g. 18", JSON.stringify(f));
  await save();
  let p = await prof();
  check("saved per hour: the profile keeps 18 per hour, and forms get 37440 per year or 18 per hour", p.payUnit === "hour" && p.salary === 18 && p.ext.salary === "37440" && p.ext.salaryHour === "18" && p.ext.payUnit === "hour", JSON.stringify(p));
  await load(); await step3();
  f = await field(); p = await prof();
  check("after a reload step 3 still says 18 per hour", f.unit === "hour" && f.val === "18" && p.payUnit === "hour", JSON.stringify({ f, p }));
  // ---- and back to per year ----
  await ev("(()=>{const d=" + F + ";d.getElementById('pu-year').click();const i=d.getElementById('pSalary');i.value='55000';i.dispatchEvent(new Event('input',{bubbles:true}))})()"); await sleep(200);
  await save(); await load(); await step3();
  f = await field(); p = await prof();
  check("back to 55000 per year, after a reload too; forms get 55000 per year or 26.44 per hour", f.unit === "year" && f.val === "55000" && p.payUnit === "year" && p.ext.salary === "55000" && p.ext.salaryHour === "26.44", JSON.stringify({ f, p }));

  // ---- matching on one scale: an hourly seeker against hourly and yearly postings ----
  const mk = (id, co, sal, unit) => Object.assign({ id, co, role: "Store Associate", sal, live: true, loc: "Philadelphia, PA", mode: "onsite", type: "job", yrs: 0, edu: "High school",
    skills: ["Customer service"], blurb: "A test posting.", url: "https://example.com/jobs/" + id, source: co + "'s careers page", apply: "link", contact: "", posted: Date.now() }, unit ? { salUnit: unit } : {});
  const JOBS = [mk(4251001, "Yearly Low Co", [40000, 50000]), mk(4251002, "Hourly Co", [25, 30], "hour"), mk(4251003, "Yearly High Co", [70000, 80000])];
  const R = JSON.parse(await ev("(()=>{const w=" + FW + ",A=w.__uaply;Object.assign(A.S.profile,{payUnit:'hour',salary:30,custom:true,title:'',skills:['Customer service'],years:0,edu:'High school',loc:'Philadelphia',modes:{remote:true,hybrid:true,onsite:true}});A.save();" +
    "A.JOBS.splice(0);A.S.decisions={};w.__uaplyJobs.add(" + JSON.stringify(JOBS) + ");A.renderAll();" +
    "const sal=(j)=>{const r=A.evaluate(j,A.S.profile).rows.find(x=>x.k==='Salary');return {s:r.s,ask:r.ask,have:r.have,pct:A.evaluate(j,A.S.profile).pct}};return JSON.stringify(A.JOBS.map(j=>[j.co,sal(j)]))})()"));
  const by = Object.fromEntries(R);
  check("an hourly seeker ($30 an hour, about $62k a year): $25-$30 an hour and $70k-$80k a year both meet it, $40k-$50k a year does not",
    by["Hourly Co"].s === 1 && by["Yearly High Co"].s === 1 && by["Yearly Low Co"].s === 0, JSON.stringify(by));
  check("...so the yearly job under it ranks below both", by["Yearly Low Co"].pct < by["Hourly Co"].pct && by["Yearly Low Co"].pct < by["Yearly High Co"].pct, JSON.stringify(by));
  check("the Salary line says what the person wants in their own unit: You want $30+ an hour", /You want \$30\+ an hour/.test(by["Hourly Co"].have), by["Hourly Co"].have);
  const order = [];
  for (let i = 0; i < 3; i++) {
    const t = JSON.parse(await ev("(()=>{const c=" + F + ".querySelector('#deck .card.top');return c?JSON.stringify({co:(c.querySelector('.chead p')||{}).textContent,pay:(c.querySelector('.pay')||{}).textContent}):'null'})()"));
    if (!t) break; order.push(t);
    await ev("(()=>{const b=" + F + ".getElementById('btnNo');if(b)b.click()})()"); await sleep(700);
  }
  check("on the deck the yearly job under the minimum comes last", order.length === 3 && order[2].co === "Yearly Low Co", JSON.stringify(order));
  const hc = order.find((x) => x.co === "Hourly Co");
  check("the hourly card still shows the posting's own figure and unit ($25-$30 per hour), never a converted one", !!hc && hc.pay === "$25–$30per hour", JSON.stringify(hc));

  const errs = logs.filter((l) => !/favicon|ERR_FILE_NOT_FOUND|401|403/.test(l));
  check("no script errors", errs.length === 0, errs.join(" | "));
  console.log("\n" + (n - bad) + " / " + n);
  if (bad) throw new Error(bad + " pay-unit check(s) failed");
};
