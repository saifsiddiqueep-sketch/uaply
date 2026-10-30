// Report this job (card 036): the button on the job card, its box, what it sends and what happens after.
// The button is behind REPORT_JOB (off until the server's /api/jobs/report is live); ?flag=report_job turns it on here.
//   W=390 H=844 PORT=8766 node tools/cdp.js tools/ui-report-job.js        (dev and sandbox)
// Checks, in a real browser against a local server:
//   0. with the flag off (the default) no card has the button;
//   1. with ?flag=report_job the top card has a flag button labelled "Report this job" beside Share, and only the top card has one;
//   2. the link opens a box (a dialog) with five reasons (scam, fake, offensive, closed, other), the first one chosen and focused, a note box and the job-safety link,
//      and that page is served;
//   3. while the box is open the deck's own keys do nothing (ArrowRight on a button in the box does not apply to the job behind it),
//      and Escape closes it, gives focus back to the link and leaves the same job on top;
//   4. Send posts one report {job_id, reason, note} to /api/jobs/report (answered ok by a stand-in until the endpoint exists); the box thanks
//      the person and says the job is skipped; closing it passes on that job (a different job, or none, is on top).
const PORT = process.env.PORT || "8767";
module.exports = async ({ ev, sleep, nav, send }) => {
  await send("Emulation.setFocusEmulationEnabled", { enabled: true });
  await require("./gate-signup.js")({ ev, sleep, nav }, "http://127.0.0.1:" + PORT, "rep");
  const F = "document.querySelector('iframe').contentDocument";
  let bad = 0, n = 0;
  const check = (name, ok, extra) => { n++; if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  const size = (process.env.W || 1100) + "x" + (process.env.H || 900);
  const done = () => { console.log(n - bad + " / " + n); if (bad) process.exitCode = 1; };

  for (let tries = 0; tries < 2 && !(await ev("(()=>{try{return !!(" + F + ").querySelector('.card.top')}catch(e){return false}})()")); tries++) {
    await nav("http://127.0.0.1:" + PORT + "/");
    for (let i = 0; i < 60 && !(await ev("(()=>{try{return !!(" + F + ").querySelector('.card.top')}catch(e){return false}})()")); i++) {
      // dev can open on Account right after sign-up: go to the jobs (the Jobs tab, then its first menu item when it has a menu)
      if (i === 10) await ev("(()=>{const d=" + F + ";if(!d)return;const b=d.getElementById('nb-svc');if(b)b.click();const m=d.querySelector('.nmenu:not([hidden]) .nitem');if(m)m.click()})()");
      await sleep(300);
    }
  }
  await sleep(1200);
  if (await ev("!!(" + F + ").getElementById('kcYes')")) { await ev("(" + F + ").getElementById('kcYes').click()"); await sleep(900); }
  const topId = () => ev("((" + F + ").querySelector('.card.top')||{}).getAttribute?.('data-id')||''");
  let first = await topId();
  check(size + " a job card is up", !!first);
  if (!first) return done();
  check(size + " with the flag off no card has a Report button", !(await ev("!!(" + F + ").querySelector('.card [data-report]')") === true));
  await nav("http://127.0.0.1:" + PORT + "/?flag=report_job");
  for (let i = 0; i < 60 && !(await ev("(()=>{try{return !!(" + F + ").querySelector('.card.top [data-report]')}catch(e){return false}})()")); i++) await sleep(300);
  await sleep(800);
  if (await ev("!!(" + F + ").getElementById('kcYes')")) { await ev("(" + F + ").getElementById('kcYes').click()"); await sleep(900); }
  first = await topId();

  // 0. an example job (made up, id under 100000) says there is nothing to report and sends nothing; then Pass until a real job is on top
  if (+first < 100000) {
    const lab = await ev("((" + F + ").querySelector('.card.top [data-report]')||{getAttribute:()=>''}).getAttribute('aria-label')");
    check(size + " the top card has a flag button labelled \"Report this job\"", lab === "Report this job", lab);
    await ev("(" + F + ").querySelector('.card.top [data-report]').click()");
    await sleep(300);
    const X = await ev("((" + F + ").getElementById('urepBox')||{}).innerText||''");
    check(size + " an example job's box says it is made up and has nothing to send", /example job/.test(X) && !(await ev("!!(" + F + ").querySelector('#urepBox [data-send]')")), X.replace(/\s+/g, ' '));
    await ev("(" + F + ").querySelector('#urepBox [data-x]').click()");
    await sleep(300);
  }
  for (let i = 0; i < 25 && +first < 100000; i++) { await ev("(" + F + ").getElementById('btnNo').click()"); await sleep(700); first = await topId(); }
  // no real jobs on this server (third-party feeds off, no partner jobs): the send checks need one, so skip them, loudly
  if (+first < 100000) { console.log("SKIP " + size + " the send checks: no real job on this server (feeds off, no partner jobs)"); return done(); }

  // 1. the link
  const L = JSON.parse(await ev(`JSON.stringify((()=>{const d=${F};return {top:d.querySelectorAll('.card.top [data-report]').length,all:d.querySelectorAll('.card [data-report]').length,
    text:(d.querySelector('.card.top [data-report]')||{}).getAttribute?.('aria-label')||''}})())`));
  check(size + " the top card has one \"Report this job\" flag button, and no other card has one", L.top === 1 && L.all === 1 && L.text === "Report this job", JSON.stringify(L));

  // 2. the box (the page's own fetch is wrapped so the test sees what is sent and what comes back)
  await ev(`(()=>{const w=${F}.defaultView;w.__rep=[];const f=w.fetch;w.fetch=function(u,o){if(String(u).indexOf('/api/jobs/report')>-1){const j={ok:true};w.__rep.push({body:JSON.parse(o.body),reply:j});return Promise.resolve(new Response(JSON.stringify(j),{headers:{'Content-Type':'application/json'}}))}return f.apply(this,arguments)}})()`);
  await ev("(" + F + ").querySelector('.card.top [data-report]').click()");
  await sleep(300);
  const B = JSON.parse(await ev(`JSON.stringify((()=>{const d=${F},o=d.getElementById('urepBox');if(!o)return null;const dl=o.querySelector('[role=dialog]'),a=d.activeElement,lk=o.querySelector('a[href$="job-safety.html"]');
    return {modal:dl&&dl.getAttribute('aria-modal'),title:(d.getElementById('urepH')||{}).textContent,reasons:o.querySelectorAll('input[name=urepWhy]').length,
      focusFirst:!!a&&a.name==='urepWhy'&&a.value==='scam'&&a.checked,note:!!d.getElementById('urepNote'),safety:lk?lk.href:''}})())`));
  check(size + " the link opens a box titled \"Report this job\" with five reasons, the first chosen and focused, a note box", !!B && B.modal === "true" && B.title === "Report this job" && B.reasons === 5 && B.focusFirst && B.note, JSON.stringify(B));
  const safety = B && B.safety ? await ev("fetch(" + JSON.stringify(B.safety) + ").then(r=>r.status+' '+r.headers.get('content-type'))") : "";
  check(size + " the box links to the job-safety page, and it is served", /^200 text\/html/.test(safety), B && B.safety + " " + safety);

  // 3. keys stay in the box; Escape closes it
  await ev(`(()=>{const d=${F},b=d.querySelector('#urepBox [data-x]');b.focus();b.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}))})()`);
  await sleep(500);
  check(size + " ArrowRight inside the box does not apply to the job behind it", (await topId()) === first && (await ev("!!(" + F + ").getElementById('urepBox')")));
  await ev(`(()=>{const d=${F},b=d.querySelector('#urepBox input:checked');b.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}))})()`);
  await sleep(300);
  const E = JSON.parse(await ev(`JSON.stringify((()=>{const d=${F};return {open:!!d.getElementById('urepBox'),back:!!d.activeElement&&d.activeElement.hasAttribute('data-report')}})())`));
  check(size + " Escape closes the box, focus goes back to the link, and the same job is still on top", !E.open && E.back && (await topId()) === first, JSON.stringify(E));

  // 4. send
  await ev("(" + F + ").querySelector('.card.top [data-report]').click()");
  await sleep(300);
  await ev(`(()=>{const d=${F};d.querySelector('#urepBox input[value=closed]').click();d.getElementById('urepNote').value='The apply link gives a 404.';d.querySelector('#urepBox [data-send]').click()})()`);
  for (let i = 0; i < 30 && !(await ev("(" + F + ").defaultView.__rep.length")); i++) await sleep(200);
  await sleep(300);
  const S = JSON.parse(await ev(`JSON.stringify((()=>{const d=${F},r=d.defaultView.__rep;return {sent:r,thanks:(d.getElementById('urepH')||{}).textContent,text:(d.getElementById('urepBox')||{}).innerText||''}})())`));
  const s = S.sent[0] || {};
  check(size + " one report is posted to /api/jobs/report", S.sent.length === 1, JSON.stringify(S.sent));
  check(size + " ...naming the job, the reason and the note", !!s.body && String(s.body.job_id) === first && s.body.reason === "closed" && /404/.test(s.body.note), JSON.stringify(s.body));
  check(size + " ...and the server keeps it (ok)", !!s.reply && s.reply.ok === true, JSON.stringify(s.reply));
  check(size + " the box thanks the person and says the job is skipped for them", S.thanks === "Thanks for the report" && /skipped for you/.test(S.text), S.text.replace(/\s+/g, " "));
  await ev("(" + F + ").querySelector('#urepBox [data-x]').click()");
  await sleep(1200);
  const after = await topId();
  check(size + " closing it passes on that job: it is no longer on top", after !== first, first + " -> " + after);
  done();
};
