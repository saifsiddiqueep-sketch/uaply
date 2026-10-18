// Tries tools/stripe-checkout.js (the part of ui-live.js --stripe-test that fills Stripe Checkout) against a stand-in Checkout page on this
// computer, shaped like Stripe's: the email already filled in, the card number, expiry and CVC inside an iframe from ANOTHER site (so Chrome
// runs it in its own process and the page's JavaScript cannot reach it), name, country, ZIP, sometimes a ticked "Save my info" box, and a
// Pay button. The card frame only accepts typing that really comes from the keyboard (isTrusted), as Stripe's fields do.
//   node tools/cdp.js tools/ui-stripe-form.js            (STRIPE_FORM_PORT picks the page's port, default 18820; the card frame uses the next one)
// Checks: 4242 4242 4242 4242 is typed into the iframe and the page sends the browser to ?billing=success; with "Save my info" ticked, it is
// unticked; 4000 0000 0000 0002 shows "declined" inside the card frame and the browser stays; a number that is not a Stripe test card is
// refused before anything is typed. Nothing here talks to Stripe.
const http = require("http");
const stripe = require("./stripe-checkout.js");

const PORT = Number(process.env.STRIPE_FORM_PORT || 18820);
const TOP = "http://127.0.0.1:" + PORT;
const CARD = "http://127.0.0.2:" + (PORT + 1);                // 127.0.0.2 is another site than 127.0.0.1: a separate frame process

const topPage = (link) => `<!doctype html><html><head><meta charset="utf-8"><title>Stand-in Checkout</title></head><body>
<form id="f" onsubmit="return false">
<input id="email" type="email" value="pay1@example.com" readonly>
<iframe id="cardframe" src="${CARD}/card" style="width:420px;height:170px;border:0" title="Secure card payment input frame"></iframe>
<input id="billingName" autocomplete="cc-name">
<select id="billingCountry"><option value="GB">United Kingdom</option><option value="US">United States</option></select>
<input id="billingPostalCode" autocomplete="postal-code">
${link ? '<label><input type="checkbox" id="enableStripePass" checked> Save my info for 1-click checkout</label><input id="phone" autocomplete="tel">' : ""}
<button class="SubmitButton" type="submit">Pay</button>
</form><div id="err"></div>
<script>
let card = null;
addEventListener("message", (e) => { if (e.origin === ${JSON.stringify(CARD)}) card = e.data; });
document.querySelector(".SubmitButton").onclick = () => {
  const fr = document.getElementById("cardframe").contentWindow, err = document.getElementById("err");
  card = null; fr.postMessage("values", ${JSON.stringify(CARD)});
  setTimeout(() => {
    const name = document.getElementById("billingName").value, country = document.getElementById("billingCountry").value,
      postal = document.getElementById("billingPostalCode").value, link = document.getElementById("enableStripePass");
    if (link && link.checked && !document.getElementById("phone").value) { err.textContent = "Enter your phone number to save your info."; return; }
    if (!card || !card.trusted) { err.textContent = "Your card number is incomplete."; return; }
    if (!(card.expiry === "1234" && card.cvc === "123" && name && country === "US" && postal === "19104")) { err.textContent = "Missing: " + JSON.stringify({ card, name, country, postal }); return; }
    if (card.number === "4242424242424242") location.href = "/done?billing=success";
    else if (card.number === "4000000000000002") fr.postMessage("declined", ${JSON.stringify(CARD)});
    else err.textContent = "Your card number is invalid.";
  }, 400);
};
</script></body></html>`;

const cardFrame = `<!doctype html><html><head><meta charset="utf-8"></head><body>
<input id="cardNumber" name="cardnumber" autocomplete="cc-number" placeholder="1234 1234 1234 1234">
<input id="cardExpiry" name="exp-date" autocomplete="cc-exp" placeholder="MM / YY">
<input id="cardCvc" name="cvc" autocomplete="cc-csc" placeholder="CVC">
<div id="msg"></div>
<script>
const v = { number: "", expiry: "", cvc: "" }; let trusted = true;
for (const [id, k] of [["cardNumber", "number"], ["cardExpiry", "expiry"], ["cardCvc", "cvc"]]) {
  const e = document.getElementById(id);
  e.addEventListener("input", (ev) => {
    if (!ev.isTrusted) trusted = false;                          // Stripe's fields ignore script-made events; so does this one
    v[k] = e.value.replace(/[^0-9]/g, "");
    if (k === "number") e.value = v[k].replace(/([0-9]{4})(?=[0-9])/g, "$1 ");
    if (k === "expiry" && v[k].length > 2) e.value = v[k].slice(0, 2) + " / " + v[k].slice(2);
  });
}
addEventListener("message", (e) => {
  if (e.data === "values") parent.postMessage(Object.assign({ trusted }, v), ${JSON.stringify(TOP)});
  if (e.data === "declined") document.getElementById("msg").textContent = "Your card has been declined.";
});
</script></body></html>`;

function serve(host, port, routes) {
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, "http://x");
    const body = routes(u);
    res.writeHead(body ? 200 : 404, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" });
    res.end(body || "not here");
  });
  return new Promise((r) => srv.listen(port, host, () => r(srv)));
}

module.exports = async (api) => {
  const { ev, sleep, nav } = api;
  let pass = 0, fail = 0;
  const check = (name, ok, extra) => { if (ok) pass++; else fail++; console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  -> " + extra)); return ok; };
  const s1 = await serve("127.0.0.1", PORT, (u) => (u.pathname === "/pay" ? topPage(u.searchParams.get("link") === "1") : u.pathname === "/done" ? "<p>Back on the site</p>" : ""));
  const s2 = await serve("127.0.0.2", PORT + 1, (u) => (u.pathname === "/card" ? cardFrame : ""));
  try {
    // 1. the card that works
    await nav(TOP + "/pay");
    const r1 = await stripe.fill(api, { card: "4242 4242 4242 4242", email: "pay1@example.com" });
    const where = r1.F ? await r1.F.find("number") : null;
    check("the card number field is found inside the card iframe (a separate frame process), not in the page", !!where && where.ctx !== undefined, JSON.stringify(r1.notes));
    check("4242 4242 4242 4242, 12/34, CVC 123, name and ZIP are typed (the email was already filled in)", r1.ok && r1.notes.includes("email prefilled") &&
      ["number typed", "expiry typed", "cvc typed", "name typed", "postal typed"].every((n) => r1.notes.includes(n)), JSON.stringify(r1.notes));
    check("...no 'Save my info' box on this page, and that is fine", r1.notes.includes("save-my-info absent"), JSON.stringify(r1.notes));
    check("...the country is set to United States", (await ev("document.getElementById('billingCountry').value")) === "US", "");
    check("Pay is pressed", await stripe.submit(api, r1.F), "");
    let back = "";
    for (let i = 0; i < 20 && !back; i++) { await sleep(500); const h = await ev("location.href"); if (/[?&]billing=success/.test(h)) back = h; }
    check("the stand-in accepts the typing as a person's (isTrusted) and sends the browser back with ?billing=success", !!back,
      (await ev("location.href")) + " | " + (await ev("(document.getElementById('err')||{}).textContent||''")));

    // 2. the declined card, with "Save my info" ticked
    await nav(TOP + "/pay?link=1");
    const r2 = await stripe.fill(api, { card: "4000000000000002", email: "pay2@example.com" });
    check("4000 0000 0000 0002 is typed the same way", r2.ok, JSON.stringify(r2.notes));
    check("...a ticked 'Save my info' box (it would ask for a phone number) is unticked", r2.notes.includes("save-my-info unticked"), JSON.stringify(r2.notes));
    await stripe.submit(api, r2.F);
    let said = "";
    for (let i = 0; i < 20 && !said; i++) { await sleep(500); const t = await r2.F.text(); if (/declined/i.test(t)) said = t; }
    check("the decline shown inside the card frame is read (Stripe shows its errors there)", !!said, (await r2.F.text()).slice(0, 160));
    check("...and the browser stays on the payment page", /\/pay\?link=1$/.test(await ev("location.href")), await ev("location.href"));
    check("the stand-in did not see a script-made event anywhere (everything was typed)", !/incomplete/.test(await ev("(document.getElementById('err')||{}).textContent||''")), "");

    // 3. never a real card
    await nav(TOP + "/pay");
    const r3 = await stripe.fill(api, { card: "1234 5678 1234 5678" });
    check("a number that is not one of Stripe's published test cards is refused before anything is typed",
      !r3.ok && /not one of Stripe's published test cards/.test(r3.notes[0]) && !(await stripe.frames(api).read("number")), JSON.stringify(r3.notes));
  } finally {
    s1.close(); s2.close();
  }
  console.log(pass + " / " + (pass + fail));
};
