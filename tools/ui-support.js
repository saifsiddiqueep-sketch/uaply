// Sandbox: the legal footer and the Hiring hub link the Support page (legal/support.html), and it opens.
//   W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-support.js
module.exports = async ({ ev, sleep, nav }) => {
  const F = "document.querySelector('iframe').contentDocument";
  let bad = 0;
  const check = (n, ok, x) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? "  " + x : "")); };
  await nav("http://127.0.0.1:" + process.env.PORT + "/?app=1"); await sleep(4000);
  if (await ev("!!" + F + ".getElementById('kcYes')")) { await ev(F + ".querySelectorAll('.kcTick,#kcYes').forEach(c=>{if(c.id==='kcYes'){c.disabled=false;c.click()}else c.checked=true})"); await sleep(400); }
  const foot = await ev("([...(" + F + ").querySelectorAll('#legalbar a')].find(a=>a.innerText==='Support')||{}).href||''");
  check("the legal footer links Support", /\/legal\/support\.html$/.test(foot) && (await ev("fetch(" + JSON.stringify(foot) + ").then(r=>r.status)")) === 200, foot);
  const pill = await ev("(()=>{const e=[...(" + F + ").querySelectorAll('button,a')].find(b=>/^Switch to hiring/.test(b.getAttribute('aria-label')||''));if(!e)return false;e.click();return true})()");
  await sleep(1500);
  check("Switch to hiring opens the hub", pill && (await ev(F + ".body.classList.contains('hire')")));
  const href = await ev("((" + F + ").querySelector('#hub a[data-support]')||{}).href||''");
  check("the Hiring hub has a Help and support link that opens", /\/legal\/support\.html$/.test(href) && (await ev("fetch(" + JSON.stringify(href) + ").then(r=>r.status)")) === 200, href || "(no link: " + (await ev("(" + F + ").getElementById('hub').innerText.slice(0,120)")) + ")");
  console.log(bad ? bad + " problem(s)" : "All good");
};
