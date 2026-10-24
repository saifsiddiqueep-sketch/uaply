// The profile kept on the account (Saif, October 24, P0: a Google sign-in lost the profile setup). On the sandbox or dev (PORT):
//   1. sign up, fill the profile: within a few seconds it is kept on the account;
//   2. a new browser (this device's storage emptied, as when Google's sign-in comes back in another browser, or a second device): signed in
//      again, every field comes back;
//   3. sign out, then sign in with the password: every field is still there; a change made after that is kept again.
//   W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-profile-sync.js
const PORT = process.env.PORT || "18766";
const gateSignup = require("./gate-signup.js");
module.exports = async ({ ev, sleep, nav, logs }) => {
  const F = "document.querySelector('iframe').contentDocument", FW = "document.querySelector('iframe').contentWindow";
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (ok || !extra ? "" : "  | " + String(extra).slice(0, 300))); };
  const J = async (x) => { const s = await ev("(async()=>JSON.stringify(await (" + x + ")))()"); try { return JSON.parse(s); } catch (e) { return s; } };
  const base = "http://127.0.0.1:" + PORT;
  const who = await gateSignup({ ev, sleep, nav }, base, "profsync");
  await nav(base + "/?app=1"); await sleep(3500);
  const want = { name: "Sync Tester", title: "Data Analyst", loc: "Philadelphia, PA", skills: ["SQL", "Python"], years: 2 };
  await ev("(()=>{const w=" + FW + ",A=w.__uaply;Object.assign(A.S.profile,{name:'Sync Tester',title:'Data Analyst',loc:'Philadelphia, PA',skills:['SQL','Python'],years:2,custom:true,email:" + JSON.stringify(who.email) + "});A.save();return 1})()");
  let kept = null;
  for (let i = 0; i < 20; i++) { await sleep(500); kept = await J("fetch('/api/profile/data').then(r=>r.json())"); if (kept && kept.fields && kept.fields["p.title"] && kept.fields["p.title"].v === "Data Analyst") break; }
  check("1. the profile is kept on the account within a few seconds of a change", !!(kept && kept.fields && kept.fields["p.name"] && kept.fields["p.name"].v === "Sync Tester"), JSON.stringify(kept).slice(0, 200));
  check("...and no voluntary self-identification answer is in it", !!(kept && kept.fields && !kept.fields["a.eeo"]), "");
  const prof = () => J("(()=>{const p=" + FW + ".__uaply.S.profile;return {name:p.name,title:p.title,loc:p.loc,skills:p.skills,years:p.years}})()");
  // 2. a new browser: this device's storage is emptied, the session stays (the account), the page loads again
  await ev("(()=>{const w=" + FW + ";try{w.localStorage.clear();w.sessionStorage.clear()}catch(e){}return 1})()");
  await nav(base + "/?app=1"); await sleep(6000);
  const p2 = await prof();
  check("2. a new browser signed in to the same account gets every field back", JSON.stringify(p2) === JSON.stringify(want), JSON.stringify(p2));
  // 3. sign out, sign in with the password: still there
  await ev("fetch('/api/auth/logout',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.status)");
  await ev("(()=>{const w=" + FW + ";try{w.localStorage.clear()}catch(e){}return 1})()");
  await ev("fetch('/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:" + JSON.stringify(who.email) + ",password:" + JSON.stringify(who.pw) + "})}).then(r=>r.status)");
  await nav(base + "/?app=1"); await sleep(6000);
  const p3 = await prof();
  check("3. signed out, then in with the password: every field is still there", JSON.stringify(p3) === JSON.stringify(want), JSON.stringify(p3));
  await ev("(()=>{const A=" + FW + ".__uaply;A.S.profile.title='Data Engineer';A.save();return 1})()");
  let k3 = null;
  for (let i = 0; i < 20; i++) { await sleep(500); k3 = await J("fetch('/api/profile/data').then(r=>r.json())"); if (k3 && k3.fields && k3.fields["p.title"] && k3.fields["p.title"].v === "Data Engineer") break; }
  check("...and a change made after that is kept on the account too", !!(k3 && k3.fields && k3.fields["p.title"] && k3.fields["p.title"].v === "Data Engineer"), JSON.stringify(k3 && k3.fields && k3.fields["p.title"]));
  check("no script errors", logs.filter((l) => l.startsWith("EXC")).length === 0, logs.join(" | "));
  console.log(bad ? bad + " problem(s)" : "All good");
  if (bad) process.exitCode = 1;
};
module.exports.limitMs = 180000;
