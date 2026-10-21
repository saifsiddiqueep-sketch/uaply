// The Internship stack for a student in Philadelphia: undergraduate roles before graduate-only ones, near on-site roles before remote,
// remote before far away. Also prints, for any job list the server has, how many of the first 20 internships are undergraduate-eligible
// and within 50 miles (MEASURE=1), with the old order (match only) and the new one.
//   PORT=<port> W=390 H=844 node tools/cdp.js tools/ui-intern-order.js     (tools/test-quality.py <port> starts a server and runs this)
const PORT = process.env.PORT || "8766";
module.exports = async ({ ev, sleep, nav }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const W = "document.querySelector('iframe').contentWindow";
  const check = (name, ok, got) => console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  -> " + got));
  await nav("http://127.0.0.1:" + PORT + "/");
  for (let i = 0; i < 40 && (await ev("(()=>{try{return " + W + ".__uaply.JOBS.some(j=>j.live)}catch(e){return false}})()")) !== true; i++) await sleep(500);
  for (let i = 0; i < 10 && (await ev("(()=>{const n=" + F + ".getElementById('kcNo');if(n&&n.offsetParent){n.click();return true}return false})()")) !== true; i++) await sleep(300);
  // a student in Philadelphia; their title matches internships so "Hide roles that do not match my target titles" hides none of them
  await ev("(()=>{const A=" + W + ".__uaply;A.S.profile.loc='Philadelphia, PA';A.S.profile.custom=true;A.S.profile.title='Intern';A.S.profile.modes={remote:true,hybrid:true,onsite:true};A.save();A.setType('internship');A.renderAll();return true})()");
  await sleep(500);
  // a student looking at every internship: "Hide roles that do not match my target titles" off ("Analytics Internship" does not match "Intern")
  await ev("(()=>{const e=" + F + ".getElementById('fTitleOnly');if(!e)return false;e.checked=false;e.dispatchEvent(new Event('change',{bubbles:true}));return true})()");
  await sleep(400);
  const order = (useNew) => ev("(()=>{const w=" + W + ",keep=w.__uaplyDeckSort;if(!" + useNew + ")w.__uaplyDeckSort=null;let q;try{q=w.__uaplyQueue()}finally{w.__uaplyDeckSort=keep}" +
    "return JSON.stringify(q.slice(0,20).map(x=>({role:x.j.role,loc:x.j.loc,mode:x.j.mode,grad:!!x.j.gradOnly,desc:(x.j.desc||'')+' '+(x.j.blurb||'')})))})()");
  if (process.env.MEASURE) {
    for (const [label, useNew] of [["old order (match only)", false], ["new order", true]]) {
      const top = JSON.parse(await order(useNew));
      const near = await ev("(()=>{const w=" + W + ";return JSON.stringify(" + JSON.stringify(top) + ".map(j=>w.__uaplyMilesFromHome?w.__uaplyMilesFromHome(j.loc):null))})()");
      const mi = JSON.parse(near);
      const grad = (j) => j.grad || /\b(ph\.?d|doctoral|mba|master'?s)\b/i.test(j.role) || (/(pursuing|enrolled in|candidate for)\s+(a|an)?\s*(ph\.?d|doctoral|master'?s|mba|graduate)/i.test(j.desc) && !/undergrad|bachelor|\bB\.?S\.?\b|sophomore|junior/i.test(j.desc));
      const ok = top.filter((j, i) => !grad(j) && j.mode !== "remote" && mi[i] != null && mi[i] <= 50).length;
      const okRemote = top.filter((j) => !grad(j) && j.mode === "remote").length;
      const gradN = top.filter(grad).length;
      console.log("MEASURE " + label + ": of the first " + top.length + " internships, " + ok + " are undergraduate-eligible and within 50 miles, " +
                  okRemote + " undergraduate-eligible remote, " + gradN + " graduate-only");
    }
    return;
  }
  const top = JSON.parse(await order(true)).map(j => j.role);
  console.log("order:", top.join(" | "));
  check("undergraduate roles within 50 miles first (Philadelphia, then Wilmington, by match)", top.slice(0, 2).sort().join(",") === "Intern Philadelphia,Intern Wilmington", top.join(" | "));
  check("then the remote undergraduate role", top[2] === "Intern Remote", top.join(" | "));
  check("then the far-away undergraduate role (Seattle)", top[3] === "Intern Seattle", top.join(" | "));
  check("graduate-only roles last, even the near one", top.slice(4).sort().join(",") === "MBA Intern Philadelphia,PhD Research Intern Philadelphia", top.join(" | "));
  const old = JSON.parse(await order(false)).map(j => j.role);
  check("the Full-time stack is not reordered (match only)", await ev("(()=>{const w=" + W + ";return w.__uaplyDeckSort('job')({m:{pct:10},j:{}},{m:{pct:90},j:{}})>0})()") === true, old.join(" | "));
};
