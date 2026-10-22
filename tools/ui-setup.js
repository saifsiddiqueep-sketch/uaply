// The owner's /setup page in a real browser: its script runs without errors and the Connect email box switches between Brevo and Gmail.
//   PORT=8766 node tools/cdp.js tools/ui-setup.js
const PORT = process.env.PORT || "8766";
module.exports = async ({ ev, sleep, nav, logs }) => {
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); };
  await nav("http://127.0.0.1:" + PORT + "/setup"); await sleep(1200);
  check("the setup page opens", await ev("!!document.getElementById('gmail')"));
  check("Brevo is the first choice and asks for Brevo's SMTP login", await ev("document.getElementById('gv').value==='brevo'&&!document.getElementById('glw').hidden"));
  await ev("(()=>{const v=document.getElementById('gv');v.value='gmail';v.onchange()})()");
  check("choosing Gmail hides the Brevo login box", await ev("document.getElementById('glw').hidden"));
  await ev("document.getElementById('sv').click()"); await sleep(800);
  check("saving with empty boxes gives a plain message, not an error", /Enter the Gmail address/.test(await ev("document.getElementById('sr').textContent")), await ev("document.getElementById('sr').textContent"));
  // Test this connection (the hiring-system box): with nothing typed it asks for the key, and it saves nothing
  check("the hiring-system box has a Test this connection button", await ev("(document.getElementById('at')||{}).textContent==='Test this connection'"));
  await ev("(()=>{document.getElementById('ak').value='smartrecruiters';document.getElementById('ab').value='nobody-saved';document.getElementById('aa').value='';document.getElementById('at').click()})()");
  await sleep(900);
  check("testing with no key and no saved connection asks for the key", /Paste the employer's key/.test(await ev("document.getElementById('ar').textContent")), await ev("document.getElementById('ar').textContent"));
  check("no script errors on the page", logs.length === 0, logs.join(" / ").slice(0, 200));
  console.log(bad ? bad + " check(s) failed" : "Setup page works");
};
