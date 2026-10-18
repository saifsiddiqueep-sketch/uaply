// Fills Stripe's hosted Checkout page (checkout.stripe.com) with one of Stripe's published TEST card numbers, through the Chrome DevTools
// protocol (tools/cdp.js). Used by tools/ui-live.js --stripe-test; tried against a stand-in page by tools/ui-stripe-form.js.
//
// Stripe draws some or all of the card fields inside its own iframes (card number, expiry and CVC frames), and Chrome runs a
// cross-origin iframe in a separate process that the page's own JavaScript cannot reach. So every field is looked for in the page
// first and then in every frame Chrome attaches us to (Target.setAutoAttach with flatten, which gives each frame a session id).
// A field is focused inside its own frame and the text is typed with Input.insertText, the way a person's keyboard reaches it; a
// value is read back from the frame to make sure it landed.
//
// Only Stripe's test cards are ever typed: any other number is refused here, before anything is sent.
const TEST_CARDS = new Set(["4242424242424242", "4000000000000002", "4000000000009995", "4000000000000127", "4000000000000101", "4100000000000019",
  "4000000000000341", "4000002500003155", "5555555555554444"]);

const FIELDS = {
  email: ["#email", "input[autocomplete=email]", "input[name=email]"],
  number: ["#cardNumber", "input[name=cardnumber]", "input[name=number]", "input[autocomplete=cc-number]"],
  expiry: ["#cardExpiry", "input[name=exp-date]", "input[name=expiry]", "input[autocomplete=cc-exp]"],
  cvc: ["#cardCvc", "input[name=cvc]", "input[autocomplete=cc-csc]"],
  name: ["#billingName", "input[name=billingName]", "input[autocomplete=cc-name]", "input[autocomplete=name]"],
  postal: ["#billingPostalCode", "input[name=billingPostalCode]", "input[name=postalCode]", "input[name=postal]", "input[autocomplete=postal-code]"],
};

// the first visible, writable input matching one of the selectors, as a JS expression for the frame it runs in
const pick = (sels) => "(()=>{for(const s of " + JSON.stringify(sels) + "){for(const e of document.querySelectorAll(s)){const r=e.getBoundingClientRect();" +
  "if(r.width>2&&r.height>2&&!e.disabled&&getComputedStyle(e).visibility!=='hidden')return e}}return null})()";

const _managers = new WeakMap();                            // one per browser connection: Chrome reports each frame only once

function frames(api) {
  if (!_managers.has(api.send)) _managers.set(api.send, makeFrames(api));
  return _managers.get(api.send);
}

function makeFrames({ send, on }) {
  const sessions = new Map();                               // sessionId -> frame URL
  let started = false;
  const auto = { autoAttach: true, waitForDebuggerOnStart: false, flatten: true };
  async function start() {
    if (started) return;
    started = true;
    on("Target.attachedToTarget", (p) => {
      if (!p || !p.sessionId || !p.targetInfo) return;
      sessions.set(p.sessionId, p.targetInfo.url || "");
      send("Target.setAutoAttach", auto, p.sessionId);      // frames inside that frame too
    });
    on("Target.detachedFromTarget", (p) => { if (p && p.sessionId) sessions.delete(p.sessionId); });
    await send("Target.setAutoAttach", auto);
    await send("Emulation.setFocusEmulationEnabled", { enabled: true });     // a headless page behaves as the focused window
  }
  async function evalIn(sessionId, expr) {
    const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true }, sessionId);
    if (!r || r.error || !r.result || r.result.exceptionDetails) return undefined;
    return r.result.result.value;
  }
  const contexts = () => [undefined, ...sessions.keys()];   // undefined: the page itself
  async function find(field) {
    for (const ctx of contexts()) if (await evalIn(ctx, "!!" + pick(FIELDS[field]))) return { ctx };
    return null;
  }
  async function read(field) {
    const f = await find(field);
    return f ? await evalIn(f.ctx, "(" + pick(FIELDS[field]) + "||{}).value||''") : null;
  }
  async function type(field, text) {
    const f = await find(field);
    if (!f) return "missing";
    await evalIn(f.ctx, "(()=>{const e=" + pick(FIELDS[field]) + ";e.focus();if(e.select)e.select();return true})()");
    await send("Input.insertText", { text });              // reaches the focused field, whichever frame it is in
    await new Promise((r) => setTimeout(r, 250));
    const got = String(await evalIn(f.ctx, "(" + pick(FIELDS[field]) + "||{}).value||''")).replace(/[\s/]/g, "");
    return got && got.includes(text.replace(/[\s/]/g, "").slice(-2)) ? "typed" : "not taken";
  }
  async function text() {
    const parts = [];
    for (const ctx of contexts()) parts.push(String((await evalIn(ctx, "document.body?document.body.innerText:''")) || ""));
    return parts.join(" ").split(/\s+/).join(" ");
  }
  return { start, find, read, type, text, evalIn, sessions };
}

// Fill the form. Returns { ok, notes } where notes says what was done or missing, for the test's output.
async function fill(api, { card, email, name = "UAply Live Check", postal = "19104", expiry = "1234", cvc = "123" }) {
  const digits = String(card).replace(/\D/g, "");
  if (!TEST_CARDS.has(digits)) return { ok: false, notes: ["refused: " + digits.slice(-4) + " is not one of Stripe's published test cards"] };
  const F = frames(api);
  await F.start();
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const notes = [];
  // Stripe sometimes folds the card form behind a "Card" choice: open it
  await F.evalIn(undefined, "(()=>{const b=document.querySelector('[data-testid=card-accordion-item-button]');if(b&&!document.querySelector('#cardNumber'))b.click()})()");
  // the card frames appear a moment after the page: wait up to 20 s for the card number field in any frame
  const end = Date.now() + 20000;
  while (Date.now() < end && !(await F.find("number"))) await sleep(500);
  if (!(await F.find("number"))) return { ok: false, notes: ["no card number field in the page or any of its " + F.sessions.size + " frame(s)"], F };
  if (email) {
    const now = await F.read("email");
    if (now === null) notes.push("no email field (Stripe shows the address as text)");
    else if (!now) notes.push("email " + (await F.type("email", email)));
    else notes.push("email prefilled");
  }
  for (const [field, value] of [["number", digits], ["expiry", expiry], ["cvc", cvc]]) {
    const r = await F.type(field, value);
    notes.push(field + " " + r);
    if (r !== "typed") return { ok: false, notes, F };
  }
  if (await F.find("name")) notes.push("name " + (await F.type("name", name)));
  await F.evalIn(undefined, "(()=>{const s=document.getElementById('billingCountry');if(s&&s.value!=='US'){const set=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set;set.call(s,'US');s.dispatchEvent(new Event('change',{bubbles:true}))}})()");
  await sleep(400);
  if (await F.find("postal")) notes.push("postal " + (await F.type("postal", postal)));
  // "Save my information for faster checkout" (Link) asks for a phone number when ticked: make sure it is not ticked; often it is not there
  const link = await F.evalIn(undefined, "(()=>{const c=document.querySelector('#enableStripePass,input[name=enableStripePass]');if(!c)return 'absent';if(c.checked){c.click();return c.checked?'still ticked':'unticked'}return 'not ticked'})()");
  notes.push("save-my-info " + link);
  return { ok: true, notes, F };
}

// Press Pay (the page's submit button) once it is enabled.
async function submit(api, F) {
  const end = Date.now() + 10000;
  while (Date.now() < end) {
    const pressed = await F.evalIn(undefined, "(()=>{const b=document.querySelector('.SubmitButton,button[type=submit]');if(!b||b.disabled)return false;b.click();return true})()");
    if (pressed) return true;
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

// A bot check Stripe may show: this tool never solves one.
async function captcha(F) {
  return !!(await F.evalIn(undefined, "[...document.querySelectorAll('iframe')].some(f=>/hcaptcha|recaptcha|challenges/.test(f.src)&&f.offsetWidth>100&&f.offsetHeight>100)"));
}

module.exports = { fill, submit, captcha, frames, TEST_CARDS };
