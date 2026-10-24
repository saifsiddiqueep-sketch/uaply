// The employer connect page in a browser (swipe phase B, October 23, 2026): from the outreach email's link to "Connected" in under two
// minutes. Run it through tools/ui-connect.py, which starts the stand-in hiring system and a UAply server and makes the link.
module.exports = async ({ ev, sleep, nav }) => {
  let bad = 0;
  const check = (name, ok, extra) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  | " + extra : "")); };
  const URL = process.env.CONNECT_URL;
  const msg = () => ev("(document.getElementById('msg')||{}).textContent||''");
  const until = async (re, ms) => { const end = Date.now() + (ms || 15000); let m = ""; while (Date.now() < end) { m = await msg(); if (re.test(m)) return m; await sleep(150); } return m; };
  const t0 = Date.now();
  await nav(URL); await sleep(600);
  const head = await ev("(document.querySelector('h1')||{}).textContent||''");
  check("the link opens the employer's page for their system", /^Connect Greenhouse to UAply$/.test(head), head);
  check("...it says where the key is made and with which rights only", await ev("/Dev Center, API Credential Management/.test(document.body.innerText)&&/Job Board API/.test(document.body.innerText)"));
  // a wrong key: Test says it does not work, nothing is kept
  await ev("(()=>{const k=document.getElementById('key');k.value='not a key!';k.dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('agree').checked=true;document.getElementById('go').click();return 1})()");
  const wrong = await until(/^(?!Connecting\.\.\.$)./, 15000);
  check("a key that is not a key (typed wrong) is refused at Connect, with the reason", !/^Connected/.test(wrong) && wrong.length > 0, wrong);
  // the right key: Test reads their postings, Connect keeps it
  await ev("(()=>{const k=document.getElementById('key');k.value='gh-secret-key-123';document.getElementById('test').click();return 1})()");
  const tested = await until(/open posting/, 15000);
  check("Test reads their open postings with the key", /3 open postings/.test(tested), tested);
  await ev("(()=>{document.getElementById('go').disabled=false;document.getElementById('go').click();return 1})()");
  const done = await until(/^(Connected|Saved, pending)/, 15000);
  const ms = Date.now() - t0;
  // a Greenhouse key only proves itself on a real send: it is kept as pending, never shown as Connected before then
  check("Connect: 'Saved, pending ... until the first one from UAply arrives in Greenhouse'", /^Saved, pending\. Greenhouse keys can only be checked by a real application, so the connection shows as pending until the first one from UAply arrives in Greenhouse\./.test(done), done);
  check("from the link to saved in " + ms + " ms (under two minutes)", ms < 120000, ms + " ms");
  check("the key never shows on the page", await ev("!/gh-secret-key-123/.test(document.body.innerText)"));
  console.log("CONNECT-MS " + ms);
  await nav(URL.replace(/s=[0-9a-f]{4}/, "s=0000")); await sleep(500);
  check("a link with a wrong signature shows no form", await ev("/This link is not valid/.test(document.body.innerText)&&!document.getElementById('key')"));
  console.log(bad ? bad + " problem(s)" : "All good");
  if (bad) process.exitCode = 1;
};
module.exports.limitMs = 180000;
