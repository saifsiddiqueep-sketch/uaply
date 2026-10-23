// The distance filter for someone in Wilmington DE or Trenton NJ, and remote jobs for everyone.
//   PORT=<port> W=390 H=844 node tools/cdp.js tools/ui-places.js     (tools/test-tristate.py <port> starts a server with made-up jobs and runs this)
// The server's list (full-time, on-site unless said): Wilmington DE, Philadelphia PA, Trenton NJ, Cherry Hill NJ, Pittsburgh PA, Wilmington NC, Newark CA,
// and one remote US job. The person's city is set in the app's own profile (the real distance code then runs); their title is
// Clerk, like the jobs, so "Hide roles that do not match my target titles" (on by default) hides none of them.
const PORT = process.env.PORT || "8766";
module.exports = async ({ ev, sleep, nav }) => {
  // the sign-in gate (October 22, Saif): nobody reaches the jobs without an account, so a fresh test person signs up first (tools/gate-signup.js)
  await require("./gate-signup.js")({ ev, sleep, nav }, "http://127.0.0.1:" + (process.env.PORT || "8767"), "places", { api: true });
  const F = "document.querySelector('iframe').contentDocument";
  const W = "document.querySelector('iframe').contentWindow";
  const check = (name, ok, got) => console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  -> " + got));
  const clickSub = (sub) => ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a,[role=tab]')].find(b=>b.offsetParent&&b.innerText.split(/\\s+/).join(' ').trim().startsWith(" + JSON.stringify(sub) + "));if(!e)return false;e.click();return true})()");
  await nav("http://127.0.0.1:" + PORT + "/");
  for (let i = 0; i < 30 && (await ev("(()=>{try{return !!" + F + ".querySelector('.card .facts .via')}catch(e){return false}})()")) !== true; i++) await sleep(500);
  // the made-up City jobs only: the test server also reads real SmartRecruiters boards (job-boards.json) in the background, and since the
  // sign-in gate (a sign-up first) those can already be in the list when the page asks for it
  await ev("(()=>{const w=" + W + ",A=w.__uaply,J=w.__uaplyJobs,city=(j)=>!j.live||j.co==='City of Philadelphia';if(J&&!J.cityOnly){const add=J.add;J.add=function(list){return add.call(J,(list||[]).filter(city))};J.cityOnly=true}" +
    "const keep=A.JOBS.filter(city);A.JOBS.splice(0,A.JOBS.length,...keep);A.renderAll();return keep.length})()"); await sleep(400);   // and any the page adds later (another stack's answer)
  for (let i = 0; i < 10 && (await ev("(()=>{const n=" + F + ".getElementById('kcNo');if(n&&n.offsetParent){n.click();return true}return false})()")) !== true; i++) await sleep(300);
  await ev(F + ".getElementById('nb-prof').click()"); await sleep(400);
  await clickSub("Filters"); await sleep(600);
  const setHome = (loc) => ev("(()=>{const A=" + W + ".__uaply;A.S.profile.loc=" + JSON.stringify(loc) + ";A.S.profile.custom=true;A.S.profile.title='Clerk';A.S.profile.modes={remote:true,hybrid:true,onsite:true};A.save();A.renderAll();return true})()");
  const setMiles = async (v) => { await ev("(()=>{const e=" + F + ".getElementById('fMiles');e.value=" + JSON.stringify(String(v)) + ";e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true})()"); await sleep(400); };
  const shown = () => ev("(()=>{const A=" + W + ".__uaply,h=" + W + ".__uaplyHide;return A.JOBS.filter(j=>j.live&&!(h&&h(j))).map(j=>j.loc+(j.mode==='remote'?' (remote)':'')).sort().join(' | ')})()");
  for (const [home, near30, label] of [
    ["Wilmington, DE", ["Philadelphia, PA", "Remote", "Wilmington, DE"], "Wilmington DE"],
    ["Trenton, NJ", ["Cherry Hill, NJ", "Philadelphia, PA", "Remote", "Trenton, NJ"], "Trenton NJ"]]) {
    await setHome(home);
    await setMiles(30);
    const got = await shown();
    const want = near30.map(x => x === "Remote" ? "United States (remote)" : x).sort().join(" | ");
    check("someone in " + label + ", within 30 miles: " + near30.join(", "), got === want, got + "  (wanted " + want + ")");
    await setMiles(0);
    const remoteOnly = await shown();
    check("someone in " + label + ", remote only: just the remote US job", remoteOnly === "United States (remote)", remoteOnly);
    await setMiles(105);
    const all = await shown();
    check("someone in " + label + ", any distance: all 8 jobs", all.split(" | ").length === 8, all);
  }
  // Wilmington NC and Newark CA must not count as the Delaware and New Jersey cities
  await setHome("Wilmington, DE");
  await setMiles(100);
  const far = await shown();
  check("Wilmington, NC and Newark, CA are not within 100 miles of Wilmington, DE", !/Wilmington, NC|Newark, CA/.test(far), far);
};
