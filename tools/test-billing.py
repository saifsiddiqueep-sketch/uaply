"""Tests paid plans end to end against a stand-in Stripe: checkout, the signed webhook, activation, cancel and lapse, weekly limits, and forged or replayed events.
  python tools/test-billing.py"""
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="uaply-billing-")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8798          # a free port can be given: python tools/test-billing.py PORT
os.environ.update(UAPLY_DATA_DIR=TMP, UAPLY_CONFIG_JSON="{}", UAPLY_STRIPE_BASE="http://127.0.0.1:%d" % PORT)
import auth_api  # noqa: E402
import billing_api  # noqa: E402
import uaply_api  # noqa: E402

R = []
WH = "whsec_testsecret"


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


proc = subprocess.Popen([sys.executable, os.path.join(HERE, "mock-stripe.py"), str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
cfg = {"delivery": "test", "smtp": {}, "stripe": {"secret_key": "sk_test_mockkey123456", "webhook_secret": WH, "price_plus": "price_plus1", "price_pro": "price_pro1"}}
uaply_api.config = lambda: cfg
uaply_api.init("billing")
auth_api.init("billing")


def signed(event, ts=None, secret=WH):
    raw = json.dumps(event).encode()
    ts = str(int(ts or time.time()))
    return raw, "t=%s,v1=%s" % (ts, hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest())


def add_sub(sid, cust, price, status="active", cancel=False, end=None):
    sub = {"id": sid, "customer": cust, "status": status, "cancel_at_period_end": cancel, "current_period_end": end or int(time.time()) + 30 * 86400,
           "items": {"data": [{"price": {"id": price}}]}, "metadata": {}}
    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%d/__subscription" % PORT, data=urllib.parse.urlencode({"id": sid, "json": json.dumps(sub)}).encode()))
    return sub


try:
    s, out, tok = auth_api.signup("payer@example.com", "correct horse 99", "10.0.0.1", True)
    uid = auth_api.user_for(tok)["id"]
    user = auth_api.user_for(tok)
    t("payments are on with a test key and both prices", (billing_api.settings()["on"], billing_api.settings()["test"]), (True, True))
    t("a new account is on Free with 50 a week", (billing_api.status(user)["plan"], billing_api.status(user)["cap"]), ("free", 50))
    t("checkout needs a verified email", billing_api.checkout(user, "plus", "http://x")[0], 403)
    auth_api.verify_code(tok, auth_api.issue_code_for_token(tok)[2], "10.0.0.1")
    user = auth_api.user_for(tok)
    t("a made-up plan is refused", billing_api.checkout(user, "gold", "http://x")[0], 400)
    t("checkout without an account is refused", billing_api.checkout(None, "plus", "http://x")[0], 401)
    code, out = billing_api.checkout(user, "plus", "http://localhost:8767")
    sess = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/__sessions" % PORT).read())[-1]
    t("checkout opens a Stripe page for the Plus price as a subscription", (code, out["url"].startswith("http://127.0.0.1"), sess["mode"], sess["line_items[0][price]"]), (200, True, "subscription", "price_plus1"))
    t("...tied to this account, with the account email, and coming back to the site", (sess["client_reference_id"], sess["customer_email"], sess["success_url"]), (str(uid), "payer@example.com", "http://localhost:8767/?billing=success"))
    t("before Stripe confirms, the plan is still Free (a redirect alone never upgrades anyone)", billing_api.plan_of(user), "free")

    add_sub("sub_1", "cus_1", "price_plus1")
    ev = {"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {"mode": "subscription", "client_reference_id": str(uid), "customer": "cus_1", "subscription": "sub_1"}}}
    raw, sig = signed(ev)
    t("a forged event (wrong secret) is refused and changes nothing", (billing_api.webhook(*signed(ev, secret="whsec_wrong"))[0], billing_api.plan_of(user)), (400, "free"))
    t("an old event (replayed) is refused", billing_api.webhook(*signed(ev, ts=time.time() - 3600))[0], 400)
    t("a signed event from Stripe is accepted", billing_api.webhook(raw, sig)[0], 200)
    st = billing_api.status(user)
    t("the account is now on Plus with 250 a week and a renewal date", (st["plan"], st["cap"], st["renews"] > time.time()), ("plus", 250, True))
    t("the same event twice is handled once", billing_api.webhook(raw, sig)[1].get("duplicate"), True)
    t("a second checkout while subscribed is refused (use Manage billing)", billing_api.checkout(user, "pro", "http://x")[0], 409)
    code, out = billing_api.portal(user, "http://localhost:8767")
    t("Manage billing opens the Stripe portal for this customer", (code, out["url"].endswith("/portal/cus_1")), (200, True))

    sub = add_sub("sub_1", "cus_1", "price_pro1")
    billing_api.webhook(*signed({"id": "evt_2", "type": "customer.subscription.updated", "data": {"object": sub}}))
    t("switching to Pro in the portal makes the account Pro (no weekly limit)", (billing_api.plan_of(user), billing_api.status(user)["cap"]), ("pro", 0))
    sub = add_sub("sub_1", "cus_1", "price_pro1", cancel=True)
    billing_api.webhook(*signed({"id": "evt_3", "type": "customer.subscription.updated", "data": {"object": sub}}))
    t("canceling keeps Pro until the end of the paid month and says so", (billing_api.plan_of(user), billing_api.status(user)["canceling"]), ("pro", True))
    sub = add_sub("sub_1", "cus_1", "price_pro1", status="canceled", end=int(time.time()) - 10)
    billing_api.webhook(*signed({"id": "evt_4", "type": "customer.subscription.deleted", "data": {"object": sub}}))
    t("when the subscription ends the account is back on Free", billing_api.plan_of(user), "free")
    # the server fails while handling an event (the database is busy, say): Stripe sends it again, and that retry must count
    sub = add_sub("sub_1", "cus_1", "price_plus1")
    raw6, sig6 = signed({"id": "evt_6", "type": "customer.subscription.updated", "data": {"object": sub}})
    real_set = auth_api.set_billing

    def busy(*a, **k):
        raise RuntimeError("database is locked")
    auth_api.set_billing = busy
    try:
        billing_api.webhook(raw6, sig6)
        first = "handled"
    except RuntimeError:
        first = "error"                                   # serve.py answers 500 here, so Stripe tries again later
    auth_api.set_billing = real_set
    t("an event whose handling failed is not remembered as done, so Stripe's retry switches the plan on",
      (first, billing_api.webhook(raw6, sig6)[1].get("duplicate"), billing_api.plan_of(user)), ("error", None, "plus"))
    sub = add_sub("sub_1", "cus_1", "price_pro1", status="canceled", end=int(time.time()) - 10)
    billing_api.webhook(*signed({"id": "evt_7", "type": "customer.subscription.deleted", "data": {"object": sub}}))
    t("a signed event that is not an object is refused, not a crash", billing_api.webhook(*signed(["not", "an", "object"]))[0], 400)

    # ---- real cards, fake cards and scams: a second person goes through Stripe's page with Stripe's own test card numbers ----
    def mock(path, **params):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), data=urllib.parse.urlencode(params).encode())
        try:
            r = urllib.request.urlopen(req)
            return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def deliver(events):
        """Stripe sends each event to the webhook, signed. Returns the answers."""
        return [billing_api.webhook(*signed(ev)) for ev in events]

    def fresh_checkout(u, plan="plus"):
        code, out = billing_api.checkout(u, plan, "https://uaply.net")
        return code, json.loads(urllib.request.urlopen("http://127.0.0.1:%d/__sessions" % PORT).read())[-1]["id"]

    s2, out2, tok2 = auth_api.signup("card.tester@example.com", "correct horse 99", "10.0.0.2", True)
    auth_api.verify_code(tok2, auth_api.issue_code_for_token(tok2)[2], "10.0.0.2")
    u2 = auth_api.user_for(tok2)
    code, cs = fresh_checkout(u2)
    sess = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/__sessions" % PORT).read())[-1]
    t("checkout leaves 3D Secure to Stripe's automatic rule and lets Stripe collect the billing address it needs",
      (sess.get("payment_method_options[card][request_three_d_secure]"), sess.get("billing_address_collection")), ("automatic", "auto"))
    versions = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/__versions" % PORT).read())
    t("every call to Stripe names the pinned API version", (len(versions) > 0, set(versions)), (True, {billing_api.API_VERSION}))
    for label, card in (("a made-up card number (fails the check digit)", "4242424242424241"), ("a number that is too short", "42424242"),
                        ("a card the bank declines", "4000000000000002"), ("a card with no money on it", "4000000000009995"),
                        ("a wrong CVC", "4000000000000127"), ("a card that fails the CVC check (Radar's CVC rule)", "4000000000000101"),
                        ("a card Radar blocks as highest risk", "4100000000000019")):
        code, out = mock("/__pay", session=cs, card=card)
        t("%s: Stripe refuses it, sends no event, and the account stays on Free" % label, (code, out.get("events"), billing_api.plan_of(u2)), (402, [], "free"))
    code, out = mock("/__pay", session=cs, card="4000000000000341")
    answers = deliver(out["events"])
    st2 = billing_api.status(u2)
    t("a card that is saved but whose first charge fails: every event is accepted, yet no plan (the subscription is incomplete)",
      ([a[0] for a in answers], st2["plan"], st2["status"]), ([200, 200, 200], "free", "incomplete"))
    code, cs = fresh_checkout(u2)
    t("after a failed first payment the person can try again with another card", code, 200)
    code, out = mock("/__pay", session=cs, card="4242 4242 4242 4242")
    sub2 = out["subscription"]
    before = billing_api.plan_of(u2)
    deliver(out["events"])
    t("a real successful payment (4242 4242 4242 4242) makes the account Plus, and only after Stripe's signed events", (before, billing_api.plan_of(u2)), ("free", "plus"))

    # forged, replayed and old events
    fake = {"id": "evt_forged_1", "type": "customer.subscription.updated", "livemode": False,
            "data": {"object": {"id": sub2, "customer": "cus_x", "status": "active", "items": {"data": [{"price": {"id": "price_pro1"}}]}, "metadata": {"uaply_user": str(u2["id"])}}}}
    t("a forged signature (someone without our webhook secret) is refused and changes nothing",
      (billing_api.webhook(*signed(fake, secret="whsec_guessed"))[0], billing_api.plan_of(u2)), (400, "plus"))
    raw_f, sig_f = signed(fake)
    t("a correctly signed event whose body was changed afterwards is refused", billing_api.webhook(raw_f.replace(b"price_pro1", b"price_pro2"), sig_f)[0], 400)
    t("no signature at all is refused", billing_api.webhook(raw_f, "")[0], 400)
    t("a signature header with junk in it is refused", billing_api.webhook(raw_f, "t=abc,v1=zz")[0], 400)
    t("an event signed 6 minutes ago (older than Stripe's 5-minute window) is refused", billing_api.webhook(*signed(fake, ts=time.time() - 360))[0], 400)
    t("an event stamped 10 minutes in the future is refused", billing_api.webhook(*signed(fake, ts=time.time() + 600))[0], 400)
    t("an event signed 4 minutes ago is still accepted (Stripe's own tolerance is 5 minutes)", billing_api.webhook(*signed(dict(fake, id="evt_recent_1"), ts=time.time() - 240))[0], 200)
    t("...and a signed event whose copy says Pro cannot switch Pro on: the plan is read from Stripe, which says Plus", billing_api.plan_of(u2), "plus")
    t("the same event sent again is recognised and handled once", billing_api.webhook(*signed(dict(fake, id="evt_recent_1")))[1].get("duplicate"), True)
    t("handled event ids are kept in the database, so a restart does not forget them", auth_api.stripe_event_seen("evt_recent_1"), True)
    cfg["stripe"]["secret_key"] = "sk_live_mockkey123456"
    t("a server with LIVE keys ignores a test-mode event (a test card can never unlock a plan on the real site)",
      billing_api.webhook(*signed(dict(fake, id="evt_testmode_1")))[1].get("ignored"), "mode")
    cfg["stripe"]["secret_key"] = "sk_test_mockkey123456"
    t("a server with test keys ignores a live-mode event", billing_api.webhook(*signed(dict(fake, id="evt_livemode_1", livemode=True)))[1].get("ignored"), "mode")
    cheap = add_sub("sub_cheap", "cus_cheap", "price_somethingelse")
    cheap["metadata"] = {"uaply_user": str(u2["id"]), "plan": "pro"}
    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%d/__subscription" % PORT, data=urllib.parse.urlencode({"id": "sub_cheap", "json": json.dumps(cheap)}).encode()))
    t("an active subscription on any other price (not our exact Plus or Pro price) never unlocks a plan, whatever its notes say",
      (billing_api.webhook(*signed({"id": "evt_cheap", "type": "customer.subscription.updated", "data": {"object": cheap}}))[0], billing_api.plan_of(u2)), (200, "free"))
    deliver(mock("/__renew_paid", sub=sub2)[1]["events"])          # puts u2 back on its own Plus subscription after the cheap one above
    t("(back on the real Plus subscription)", billing_api.plan_of(u2), "plus")

    # a renewal fails: Stripe retries; the plan stays for two failed tries and is paused after the third, then comes back when a payment works
    deliver(mock("/__renew_fail", sub=sub2, attempt="1")[1]["events"])
    st2 = billing_api.status(u2)
    t("first failed renewal: still Plus, and the person is told the payment is being retried", (st2["plan"], st2["problem"]), ("plus", "retrying"))
    deliver(mock("/__renew_fail", sub=sub2, attempt="2")[1]["events"])
    t("second failed renewal: still Plus", billing_api.plan_of(u2), "plus")
    deliver(mock("/__renew_fail", sub=sub2, attempt="3")[1]["events"])
    st2 = billing_api.status(u2)
    t("third failed renewal: the plan is paused (back to Free limits) and the person is told to update the card", (st2["plan"], st2["problem"], st2["cap"]), ("free", "paused", 50))
    t("...a new checkout is refused; Manage billing is where the card is updated", billing_api.checkout(u2, "plus", "https://uaply.net")[1].get("code"), "has_plan")
    t("...and Manage billing opens", billing_api.portal(u2, "https://uaply.net")[0], 200)
    deliver(mock("/__renew_paid", sub=sub2)[1]["events"])
    st2 = billing_api.status(u2)
    t("the card is updated and the retry succeeds: Plus is back and the warning is gone", (st2["plan"], st2["problem"]), ("plus", ""))

    # cancelled in the portal: kept until the paid month ends, then Free
    deliver(mock("/__portal_cancel", sub=sub2)[1]["events"])
    st2 = billing_api.status(u2)
    t("cancelled in Stripe's portal: still Plus until the paid month ends, and the page says when it ends", (st2["plan"], st2["canceling"]), ("plus", True))
    deliver(mock("/__period_end", sub=sub2)[1]["events"])
    st2 = billing_api.status(u2)
    t("the paid month ends: back on Free, nothing more to cancel", (st2["plan"], st2["canceling"], st2["problem"]), ("free", False, ""))

    # deleting the account cancels the subscription at Stripe, so a deleted account is never charged again
    code, cs = fresh_checkout(u2, "pro")
    code, out = mock("/__pay", session=cs, card="4242424242424242")
    deliver(out["events"])
    t("subscribed again, to Pro", billing_api.plan_of(u2), "pro")
    sub_status = lambda: billing_api._stripe("GET", "/v1/subscriptions/" + out["subscription"])[1]["status"]     # noqa: E731
    t("a wrong password deletes nothing and cancels nothing", (auth_api.delete_account(tok2, "wrong password 1", "10.0.0.2", before_delete=billing_api.cancel_on_delete)[0], sub_status()), (401, "active"))
    mock("/__fail_cancel")
    code, body, gone = auth_api.delete_account(tok2, "correct horse 99", "10.0.0.2", before_delete=billing_api.cancel_on_delete)
    t("if Stripe refuses to cancel the plan, the account is KEPT and the person is told to cancel in Manage billing first",
      (code, body.get("code"), gone, "Manage billing" in body.get("error", ""), bool(auth_api.user_for(tok2)), sub_status()), (409, "billing", None, True, True, "active"))
    code, body, gone = auth_api.delete_account(tok2, "correct horse 99", "10.0.0.2", before_delete=billing_api.cancel_on_delete)
    t("deleting the account with an active plan cancels the subscription at Stripe immediately, then removes the account",
      (code, gone == u2["id"], sub_status(), auth_api.user_for(tok2)), (200, True, "canceled", None))
    t("...and Stripe's later event about it is accepted without error", billing_api.webhook(*signed({"id": "evt_after_delete", "type": "customer.subscription.deleted", "data": {"object": {"id": out["subscription"]}}}))[0], 200)
    s3, _, tok3 = auth_api.signup("never.paid@example.com", "correct horse 99", "10.0.0.3", True)
    t("an account that never paid is deleted without asking Stripe anything", auth_api.delete_account(tok3, "correct horse 99", "10.0.0.3", before_delete=billing_api.cancel_on_delete)[0], 200)
    saved = dict(cfg["stripe"])
    cfg["stripe"] = {"webhook_secret": WH}
    t("with the keys removed, an event is answered 503 so Stripe sends it again later (not lost)",
      (billing_api.webhook(*signed({"id": "evt_while_off", "type": "invoice.paid", "data": {"object": {}}}))[0], auth_api.stripe_event_seen("evt_while_off")), (503, False))
    cfg["stripe"] = saved

    # weekly limits, enforced by the server
    for i in range(50):
        uaply_api.APPS.append({"user": uid, "at": time.time(), "status": "delivered_test", "job": {"id": i}, "candidate": {"email": "payer@example.com"}, "mode": "test"})
    t("on Free the 51st application in a week is stopped with a plain reason", "50 applications this week" in (billing_api.limit_reached(user) or ""), True)
    sub = add_sub("sub_2", "cus_1", "price_plus1")
    billing_api.webhook(*signed({"id": "evt_5", "type": "customer.subscription.updated", "data": {"object": sub}}))
    t("on Plus the same account can keep applying", billing_api.limit_reached(user), None)
    cfg["stripe"] = {}
    t("with payments switched off nobody is limited and everyone is on Free", (billing_api.limit_reached(user), billing_api.plan_of(user), billing_api.status(user)["enabled"]), (None, "free", False))
    t("checkout is refused while payments are off", billing_api.checkout(user, "plus", "http://x")[0], 503)
    # the three states of the buy buttons (owner's rule): keys set (test or live), or the owner's own computer, or neither
    t("no keys, owner's own computer: buttons shown (Payment Links fallback), not early access",
      (billing_api.status(user)["buttons"], billing_api.status(user)["early"], billing_api.status(user)["enabled"]), (True, False, False))
    billing_api.PUBLIC = True
    t("no keys, public server: no buttons, early access, nobody limited", (billing_api.status(user)["buttons"], billing_api.status(user)["early"], billing_api.limit_reached(user)), (False, True, None))
    cfg["stripe"] = {"secret_key": "sk_test_mockkey123456", "webhook_secret": WH, "price_plus": "price_plus1", "price_pro": "price_pro1"}
    st = billing_api.status(user)
    t("test keys, public server: buttons shown and marked as test mode", (st["buttons"], st["early"], st["enabled"], st["test"]), (True, False, True, True))
    t("test keys, public server: checkout opens (the stand-in Stripe answers)", billing_api.checkout(dict(user, emailVerified=True), "pro", "http://x")[0] in (200, 409), True)
    cfg["stripe"]["secret_key"] = "sk_live_mockkey123456"
    st = billing_api.status(user)
    t("live keys, public server: buttons shown, not test mode", (st["buttons"], st["early"], st["test"]), (True, False, False))
    billing_api.PUBLIC = False
finally:
    proc.terminate()

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
