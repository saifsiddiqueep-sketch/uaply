// The "before your first application" agreement must appear on the first swipe right only, and swiping must throw no script error.
//   W=390 H=844 PORT=18766 node tools/cdp.js tools/ui-consent-once.js
module.exports = async ({ ev, sleep, nav, logs }) => {
  const F = "document.querySelector('iframe').contentDocument";
  let bad = 0;
  const check = (n, ok, x) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? "  " + x : "")); };
  await nav("http://127.0.0.1:" + (process.env.PORT || "18766") + "/"); await sleep(3500);
  const seen = [];
  for (let i = 1; i <= 3; i++) {
    await ev(F + ".getElementById('btnYes').click()"); await sleep(1500);
    const shown = await ev("!!" + F + ".getElementById('kcYes')");
    seen.push(shown);
    if (shown) await ev(F + ".querySelectorAll('.kcTick,#kcYes').forEach(c=>{if(c.id==='kcYes'){c.disabled=false;c.click()}else c.checked=true})");
    await sleep(2500);
  }
  check("the agreement shows on the first swipe right only", JSON.stringify(seen) === "[true,false,false]", JSON.stringify(seen));
  check("swiping right three times throws no script error", logs.filter((l) => l.startsWith("EXC")).length === 0, logs.join(" | ").slice(0, 200));
  console.log(bad ? bad + " problem(s)" : "All good");
  if (bad) process.exitCode = 1;
};
