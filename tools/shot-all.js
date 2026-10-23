// Saves a screenshot of every screen (Services tabs, Job Tracker tabs, Profile tabs, chat, legal footer) into OUT=<folder>.
//   OUT=<folder> W=390 H=844 PORT=18795 node tools/cdp.js tools/shot-all.js
const path = require("path");
const fs = require("fs");
const PORT = process.env.PORT || "8767";
module.exports = async ({ ev, sleep, nav, shot }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const OUT = process.env.OUT;
  fs.mkdirSync(OUT, { recursive: true });
  const click = (txt) => ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a,[role=tab]')].find(b=>b.offsetParent&&b.innerText.split(/\\s+/).join(' ').trim().startsWith(" + JSON.stringify(txt) + "));if(!e)return false;e.click();return true})()");
  const top = () => ev("(()=>{const d=" + F + ";d.scrollingElement.scrollTop=0;window.scrollTo(0,0)})()");
  let n = 0;
  const snap = async (name) => { await top(); await sleep(250); n++; await shot(path.join(OUT, String(n).padStart(2, "0") + "-" + name + ".png")); console.log("saved", n, name); };

  await nav("http://127.0.0.1:" + PORT + "/");
  await sleep(3500);
  const go = async (id, tab) => {                        // the section menu toggles: open it, and toggle once more if the tab is not there
    await ev(F + ".getElementById('" + id + "').click()"); await sleep(350);
    if (await click(tab)) return true;
    await ev(F + ".getElementById('" + id + "').click()"); await sleep(350);
    return click(tab);
  };
  for (const tab of ["Full-time", "Part-time", "Internships", "Coop"]) { if (await go("nb-svc", tab)) { await sleep(900); await snap("services-" + tab.toLowerCase()); } }
  for (const tab of ["Overview", "Applied", "Accepted", "Rejected", "Interviews"]) { if (await go("nb-dash", tab)) { await sleep(600); await snap("dashboard-" + tab.toLowerCase()); } }
  for (const tab of ["Account", "Settings", "Resume", "Preferences", "Filters", "Plan", "Data"]) { if (await go("nb-prof", tab)) { await sleep(700); await snap("profile-" + tab.toLowerCase()); } else console.log("(no " + tab + " tab in this build)"); }
  // the assistant
  await ev("(()=>{const d=" + F + ";const b=d.getElementById('uaChatBtn');if(b)b.click()})()"); await sleep(900);
  await snap("assistant");
};
