module.exports = async ({ ev, sleep, nav }) => {
  const F = "document.querySelector('iframe').contentDocument";
  const sub = (s) => ev("(()=>{const e=[...(" + F + ").querySelectorAll('button')].find(b=>b.offsetParent&&b.innerText.split(/\s+/).join(' ').trim().startsWith(" + JSON.stringify(s) + "));if(e)e.click();return !!e})()");
  const cut = async (where) => {
    const bad = JSON.parse(await ev("JSON.stringify((()=>{const W=innerWidth;const out=[];for(const e of (" + F + ").querySelectorAll('button,a,input,select,textarea,.chip,.card,.banner')){if(!e.offsetParent)continue;const r=e.getBoundingClientRect();if(r.width&&(r.right>W+1||r.left<-1))out.push((e.id||e.innerText||e.tagName).toString().trim().split(String.fromCharCode(10))[0].slice(0,24)+' ['+Math.round(r.left)+'..'+Math.round(r.right)+' of '+W+']')}return out.slice(0,6)})())"));
    const sw = await ev("document.documentElement.scrollWidth - innerWidth");
    if (bad.length || sw > 1) console.log("  CUT OFF on " + where + ": " + (bad.join(", ") || "page scrolls sideways by " + sw + "px"));
    else console.log("  ok " + where);
  };
  await nav("http://127.0.0.1:" + (process.env.PORT || "8767") + "/");
  await sleep(3500);
  await cut("the job deck (with the notice)");
  for (const [nb, s] of [["nb-dash", "Overview"], ["nb-prof", "Settings"], ["nb-prof", "Account"], ["nb-prof", "Filters"], ["nb-prof", "Data"]]) {
    for (let i = 0; i < 3; i++) { await ev(F + ".getElementById('" + nb + "').click()"); await sleep(350); if (await sub(s)) break; }
    await sleep(600);
    await cut(nb === "nb-dash" ? "Job Tracker" : "Profile > " + s);
  }
};
