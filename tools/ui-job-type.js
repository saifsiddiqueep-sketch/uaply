// The Job type filter on the Filters screen (All, Full-time, Part-time, Internship, Co-op, Contract) and the job type on the card.
//   PORT=<port> W=390 H=844 node tools/cdp.js tools/ui-job-type.js     (tools/test-job-types.py <port> starts a server with made-up jobs and runs this)
// The server's job list has, in the City's place: 3 full-time, 2 contract, 2 part-time, 2 internship, 1 co-op job.
const PORT = process.env.PORT || "8766";
module.exports = async ({ ev, sleep, nav, shot }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const W = "document.querySelector('iframe').contentWindow";
  const check = (name, ok, got) => console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  -> " + got));
  const clickSub = (sub) => ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a,[role=tab]')].find(b=>b.offsetParent&&b.innerText.split(/\\s+/).join(' ').trim().startsWith(" + JSON.stringify(sub) + "));if(!e)return false;e.click();return true})()");
  await nav("http://127.0.0.1:" + PORT + "/");
  for (let i = 0; i < 30 && (await ev("(()=>{try{return !!" + F + ".querySelector('.card .facts .via')}catch(e){return false}})()")) !== true; i++) await sleep(500);
  const top = await ev("(()=>{const c=" + F + ".querySelector('.card.top')||" + F + ".querySelector('.card');return c?[...c.querySelectorAll('.facts span')].map(s=>s.textContent).join(' | '):''})()");
  console.log("top card facts:", top);
  // the one-time swipe agreement opens on a first visit: "Not now" closes it (this test swipes nothing)
  // (it opens 0.7 s after the page loads)
  for (let i = 0; i < 10 && (await ev("(()=>{const n=" + F + ".getElementById('kcNo');if(n&&n.offsetParent){n.click();return true}return false})()")) !== true; i++) await sleep(300);
  await sleep(300);
  check("the card shows the job type next to the work style", /On-?site \| (Full-time|Contract) \|/i.test(top), top);
  // open Filters
  await ev(F + ".getElementById('nb-prof').click()"); await sleep(400);
  await clickSub("Filters"); await sleep(600);
  if (process.env.SHOT0) await shot(process.env.SHOT0);
  const chips = JSON.parse(await ev("JSON.stringify([...(" + F + ").querySelectorAll('#fJt button')].map(b=>[b.textContent,b.getAttribute('aria-pressed'),b.offsetParent!==null]))"));
  check("six chips: All, Full-time, Part-time, Internship, Co-op, Contract", chips.map(c => c[0]).join(",") === "All,Full-time,Part-time,Internship,Co-op,Contract", JSON.stringify(chips));
  check("All is picked by default", chips[0] && chips[0][1] === "true" && chips.slice(1).every(c => c[1] === "false"), JSON.stringify(chips));
  check("every chip is visible", chips.every(c => c[2]), JSON.stringify(chips));
  const same = await ev("(()=>{const a=" + F + ".querySelector('#fJt button'),b=" + F + ".querySelector('#fWs button');if(!a||!b)return 'missing';const x=getComputedStyle(a),y=getComputedStyle(b);return [x.borderRadius===y.borderRadius,x.fontSize===y.fontSize,x.fontWeight===y.fontWeight,x.backgroundColor===y.backgroundColor].join(',')})()");
  check("the chips look like the Work style chips (radius, size, weight, color)", same === "true,true,true,true", same);
  const wide = await ev("(()=>{const g=" + F + ".getElementById('fJt');return g.scrollWidth<=g.clientWidth+1&&" + F + ".documentElement.scrollWidth<=" + W + ".innerWidth+1})()");
  check("the chips fit the phone width (no sideways scroll)", wide === true, wide);
  const count = () => ev(F + ".getElementById('fCount').textContent");
  const pick = async (jt) => { await ev(F + ".querySelector('#fJt [data-jt=\"" + jt + "\"]').click()"); await sleep(400); };
  const before = await count();
  await pick("contract");
  const c1 = await count();
  check("Contract: the full-time tab narrows to its 2 contract jobs", /^2 of 5 listings in /.test(c1), c1 + " (before: " + before + ")");
  await pick("internship");
  const c2 = await count();
  check("Internship: the deck moves to the Internships tab, both internships match", /^2 of 2 listings in Intern/.test(c2), c2);
  if (process.env.SHOT1) await shot(process.env.SHOT1);
  const consent = await ev("!!(" + F + ".getElementById('kcYes')&&" + F + ".getElementById('kcYes').offsetParent)");
  check("picking a type does not open the swipe agreement", consent === false, consent);
  const pressed = await ev("[...(" + F + ").querySelectorAll('#fJt button')].filter(b=>b.getAttribute('aria-pressed')==='true').map(b=>b.textContent).join(',')");
  check("only the picked chip is pressed", pressed === "Internship", pressed);
  await pick("co-op");
  check("Co-op: the Co-op tab, 1 of 1", /^1 of 1 listings in /.test(await count()), await count());
  await pick("part-time");
  check("Part-time: the Part-time tab, 2 of 2", /^2 of 2 listings in /.test(await count()), await count());
  const kept = await ev("(()=>{try{const k=Object.keys(" + W + ".localStorage).find(k=>/acct|account/i.test(k)&&/fJt/.test(" + W + ".localStorage.getItem(k)));return k?JSON.parse(" + W + ".localStorage.getItem(k)).fJt:'(not saved)'}catch(e){return 'error '+e}})()");
  check("the pick is saved with the other filters", kept === "part-time", kept);
  await ev(F + ".getElementById('fClear').click()"); await sleep(400);
  const after = await ev("[...(" + F + ").querySelectorAll('#fJt button')].filter(b=>b.getAttribute('aria-pressed')==='true').map(b=>b.textContent).join(',')");
  check("Clear all filters puts it back to All", after === "All", after);
  if (process.env.SHOT) await shot(process.env.SHOT);
};
