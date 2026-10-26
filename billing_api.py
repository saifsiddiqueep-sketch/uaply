"""Paid plans (Free, Plus, Pro) through Stripe Checkout and the Stripe billing portal. Card details are typed only on Stripe's own pages: UAply never
sees or stores a card number. The plan of each account is stored on the server and changes only when Stripe tells us so through its signed webhook.

  GET  /api/billing/status     the signed-in account's plan, its weekly limit and use, and whether payments are switched on
  POST /api/billing/checkout   {plan: "plus"|"pro"} -> {url} of a Stripe Checkout page for a subscription
  POST /api/billing/portal     -> {url} of the Stripe billing portal (change card, switch plan, cancel, invoices)
  POST /api/billing/webhook    Stripe's events, checked against the Stripe-Signature header

Settings (uaply-config.json "stripe" block, or STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET / STRIPE_PRICE_PLUS / STRIPE_PRICE_PRO in the environment):
secret_key (sk_test_... or sk_live_...), webhook_secret (whsec_...), price_plus and price_pro (price_... ids of monthly prices made in Stripe),
and price_plus_year and price_pro_year (STRIPE_PRICE_PLUS_YEAR / STRIPE_PRICE_PRO_YEAR: the yearly prices, $99.90 and $199.90, two months free;
Yearly shows on the plan screen only when both are set).

Why nobody can get a plan without a real, successful payment:
  * Coming back to /?billing=success changes nothing. Only a webhook signed with our endpoint's secret (HMAC-SHA256, at most 5 minutes old,
    the same rule as Stripe's own libraries) is read, and each event id is handled once (remembered in the database, so also after a restart).
  * The event is only a hint. The plan is read from Stripe itself (GET /v1/subscriptions/<id>, with our secret key), so an old event arriving
    late, or out of order, cannot switch a plan back on. A plan is granted only while that subscription is active (or trialing), on our exact
    Plus or Pro price. A card that is declined, fails 3D Secure, or is not a real card never makes the subscription active: Stripe Checkout checks
    the number itself and asks the card's bank to approve the charge, and Radar blocks the riskiest payments before that.
  * A live server ignores test-mode events (livemode must match the key), so a test card such as 4242 4242 4242 4242 can never unlock a plan on
    the real site, even if a test webhook secret were pasted there by mistake.
  * When a renewal fails, Stripe retries the card (the subscription is past_due). The plan stays during the first two failed tries and is paused
    after the third (MAX_FAILED); it comes back by itself when a retry or a new card in Manage billing succeeds (invoice.paid). When Stripe gives
    up, or the person cancels in the portal and the paid month ends, customer.subscription.deleted puts the account back on Free.
"""
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import auth_api
import uaply_api

PLANS = {"free": {"name": "Free", "price": 0, "year": 0, "cap": 50}, "plus": {"name": "Plus", "price": 9.99, "year": 99.90, "cap": 250},
         "pro": {"name": "Pro", "price": 19.99, "year": 199.90, "cap": 0}}
ACTIVE = ("active", "trialing", "past_due")          # past_due keeps the plan while Stripe retries the card (but see MAX_FAILED)
MAX_FAILED = 3                                       # after this many failed tries of one renewal the plan is paused until a payment succeeds
API_VERSION = "2026-09-30.endive"                    # every call names the Stripe API version this code was written against, so a change
                                                     # of the account's default version in Stripe's dashboard cannot change what comes back
# the events the webhook endpoint in Stripe must send (DEPLOY.md lists the same ones for the owner)
EVENTS = ("checkout.session.completed", "customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted",
          "invoice.paid", "invoice.payment_failed")


def _base():
    v = os.environ.get("UAPLY_STRIPE_BASE", "")
    return v if re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$", v) else "https://api.stripe.com"


def settings():
    s = dict(uaply_api.config().get("stripe") or {}) if isinstance(uaply_api.config().get("stripe"), dict) else {}
    for k, env in (("secret_key", "STRIPE_SECRET_KEY"), ("webhook_secret", "STRIPE_WEBHOOK_SECRET"), ("price_plus", "STRIPE_PRICE_PLUS"), ("price_pro", "STRIPE_PRICE_PRO"),
                   ("price_plus_year", "STRIPE_PRICE_PLUS_YEAR"), ("price_pro_year", "STRIPE_PRICE_PRO_YEAR")):
        if os.environ.get(env):
            s[k] = os.environ[env].strip()
    key = s.get("secret_key") if isinstance(s.get("secret_key"), str) else ""
    s["on"] = bool(re.match(r"^sk_(test|live)_[A-Za-z0-9]{8,}$", key) and str(s.get("price_plus", "")).startswith("price_") and str(s.get("price_pro", "")).startswith("price_"))
    s["test"] = key.startswith("sk_test_")
    made = _made_prices()
    for k in ("price_plus_year", "price_pro_year"):          # the yearly prices this server made itself (ensure_yearly), when none is set
        if not str(s.get(k, "")).startswith("price_") and str(made.get(k, "")).startswith("price_"):
            s[k] = made[k]
    s["yearly"] = s["on"] and all(str(s.get(k, "")).startswith("price_") for k in ("price_plus_year", "price_pro_year"))
    return s


PUBLIC = False           # serve.py sets this on a hosted (public) server
YEAR_CENTS = {"plus": 9990, "pro": 19990}     # $99.90 and $199.90 a year: two months free


def _prices_file():
    return os.path.join(uaply_api.DATA, "billing-prices.json")


def _made_prices():
    try:
        with open(_prices_file(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


_YEARLY_TRIED = [0.0]


def ensure_yearly(force=False):
    """When STRIPE_PRICE_PLUS_YEAR / STRIPE_PRICE_PRO_YEAR are not set, make the two yearly prices in Stripe on the products behind the monthly
    prices (9990 and 19990 cents, USD, nickname "yearly"), reusing one that already exists there (same interval and amount), and keep their ids
    in billing-prices.json in the records folder. Only this server holds the secret key, so nobody has to make them by hand. Tried at most
    once every 10 minutes; returns the ids it has."""
    s = settings()
    if not s["on"] or s["yearly"] or (not force and time.time() - _YEARLY_TRIED[0] < 600):
        return {k: s.get(k, "") for k in ("price_plus_year", "price_pro_year")}
    _YEARLY_TRIED[0] = time.time()
    made = _made_prices()
    for plan in ("plus", "pro"):
        k = "price_%s_year" % plan
        if str(s.get(k, "")).startswith("price_"):
            continue
        code, mon = _stripe("GET", "/v1/prices/" + urllib.parse.quote(s["price_" + plan], safe=""))
        prod = mon.get("product") if code == 200 else ""
        prod = prod.get("id") if isinstance(prod, dict) else prod
        if not prod:
            continue
        code, lst = _stripe("GET", "/v1/prices?" + urllib.parse.urlencode({"product": prod, "active": "true", "limit": "100", "recurring[interval]": "year"}))
        hit = [p for p in (lst.get("data") or []) if code == 200 and p.get("unit_amount") == YEAR_CENTS[plan] and p.get("currency") == "usd"
               and (p.get("recurring") or {}).get("interval") == "year"]
        if hit:
            pid = hit[0]["id"]
        else:
            code, new = _stripe("POST", "/v1/prices", {"product": prod, "unit_amount": str(YEAR_CENTS[plan]), "currency": "usd",
                                                       "recurring[interval]": "year", "nickname": "yearly"})
            pid = new.get("id") if code == 200 else ""
        if str(pid).startswith("price_"):
            made[k] = pid
    if made.get("price_plus_year") and made.get("price_pro_year") and not made.get("at"):
        made["at"] = int(time.time())
        sys.stderr.write("[uaply] yearly prices ready in Stripe: Plus %s, Pro %s (billing-prices.json)\n" % (made["price_plus_year"], made["price_pro_year"]))
    try:
        os.makedirs(uaply_api.DATA, exist_ok=True)
        tmp = _prices_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(made, f, indent=1)
        os.replace(tmp, _prices_file())
    except OSError:
        pass
    return {k: made.get(k, "") for k in ("price_plus_year", "price_pro_year")}


def prices_line():
    """The four price ids for the owner's /setup page, and where the yearly ones came from."""
    s, made = settings(), _made_prices()
    yr = ("yearly: created by the server on %s" % time.strftime("%Y-%m-%d", time.gmtime(made["at"]))) if made.get("at") and s.get("price_plus_year") == made.get("price_plus_year") \
        else ("yearly: set in the settings" if s["yearly"] else "yearly: not made yet (the server makes them on the first plan screen)")
    return "Prices: Plus %s, Pro %s, Plus yearly %s, Pro yearly %s; %s." % (s.get("price_plus") or "-", s.get("price_pro") or "-", s.get("price_plus_year") or "-",
                                                                           s.get("price_pro_year") or "-", yr)


def summary():
    """One phrase for the server's start line in the log: is the owner's paste complete, and in which mode."""
    s = settings()
    key = s.get("secret_key") if isinstance(s.get("secret_key"), str) else ""
    if key.startswith("rk_"):
        return "OFF: STRIPE_SECRET_KEY is a restricted key (rk_...); paste the secret key (sk_live_...)"
    if key.startswith("pk_"):
        return "OFF: STRIPE_SECRET_KEY is the publishable key (pk_...); paste the secret key (sk_live_...)"
    if not s["on"]:
        return "off" if not key or key.lower() == "none" else "OFF: check STRIPE_SECRET_KEY, STRIPE_PRICE_PLUS and STRIPE_PRICE_PRO"
    out = "on, %s mode" % ("test" if s["test"] else "LIVE")
    if not str(s.get("webhook_secret") or "").startswith("whsec_"):
        out += ", but NO WEBHOOK SECRET (STRIPE_WEBHOOK_SECRET): people could pay and never get their plan"
    if s["test"] and PUBLIC:
        out += " (test cards work here: use live keys on the real site)"
    return out


def hidden():
    """A free-only launch: UAPLY_PLANS_HIDDEN=1 (or "plans_hidden": true in the config) hides Plus and Pro. Plan and billing then shows the
    Free plan and "Plus and Pro are coming soon", with no Choose buttons, and checkout is refused. Off by default."""
    return os.environ.get("UAPLY_PLANS_HIDDEN", "").strip() == "1" or uaply_api.config().get("plans_hidden") is True


def buttons(s=None):
    """Whether the page offers Choose Plus / Choose Pro (or the sandbox's Payment Links): when Stripe keys are set on this server
    (test or live), or when the server is not public (the owner's own computer, where the test checkout is tried). A public
    server with no keys shows "Paid plans are coming. UAply is free during early access." instead."""
    s = s or settings()
    return bool(s["on"] or not PUBLIC)


def _stripe(method, path, params=None):
    s = settings()
    data = urllib.parse.urlencode(params or {}).encode() if method == "POST" else None
    req = urllib.request.Request(_base() + path + ("" if method == "POST" or not params else "?" + urllib.parse.urlencode(params)), data=data, method=method,
                                 headers={"Authorization": "Bearer " + s["secret_key"], "Content-Type": "application/x-www-form-urlencoded",
                                          "Stripe-Version": API_VERSION})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read(500000))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read(20000))
        except Exception:
            body = {}
        msg = ((body.get("error") or {}).get("message") or "") if isinstance(body, dict) else ""
        sys.stderr.write("[uaply] Stripe answered %d to %s %s: %s\n" % (e.code, method, path.split("?")[0][:60], msg[:200]))     # the owner reads why in the log
        return e.code, body
    except Exception as e:
        sys.stderr.write("[uaply] could not reach Stripe (%s %s): %s\n" % (method, path.split("?")[0][:60], type(e).__name__))
        return 0, {}


def _week_used(user_id):
    since = time.time() - 7 * 86400
    with uaply_api._lock:
        # every application the person sends or saves to send counts, hand-offs included (Saif, October 25); a failed send and a repeat do not
        return sum(1 for a in uaply_api.APPS if a.get("user") == user_id and a["at"] >= since and a["status"] not in ("failed", "duplicate"))


def _plan_from_row(r):
    st = r.get("plan_status") or ""
    if r.get("plan") not in ("plus", "pro") or st not in ACTIVE:
        return "free"
    if st == "past_due" and (r.get("plan_failed") or 0) >= MAX_FAILED:
        return "free"                                    # Stripe is still retrying, but three tries have failed: paused until a payment succeeds
    return r["plan"]


def plan_of(user):
    """The plan that is in force for an account right now ("free" when payments are off, the subscription lapsed, or there is no account)."""
    if not user or not settings()["on"]:
        return "free"
    return _plan_from_row(auth_api.billing_row(user["id"]) or {})


def limit_reached(user):
    """None, or a plain sentence when this account has used its weekly applications (only enforced when payments are switched on)."""
    if not user or not settings()["on"]:
        return None
    p = PLANS[plan_of(user)]
    if p["cap"] and _week_used(user["id"]) >= p["cap"]:
        day = time.strftime("%A", time.gmtime(_next_free(user["id"])))
        if hidden():                                   # no bigger plan can be chosen yet: say when applying works again instead
            return "You've used your %d applications this week on %s. More open up on %s, as the oldest ones pass 7 days. Plus and Pro are coming soon." % (p["cap"], p["name"], day)
        return "You've used your %d applications this week on %s. More open up on %s, or choose a bigger plan in Profile, Plan and billing to keep applying." % (p["cap"], p["name"], day)
    return None


def _next_free(user_id):
    """When the oldest application of the last 7 days passes 7 days (the moment one more opens up)."""
    since = time.time() - 7 * 86400
    with uaply_api._lock:
        ats = [a["at"] for a in uaply_api.APPS if a.get("user") == user_id and a["at"] >= since and a["status"] not in ("failed", "duplicate")]
    return (min(ats) if ats else time.time()) + 7 * 86400


def _problem(r):
    """What the person must be told about their payment: "" (nothing), "retrying" (a renewal failed, the plan is still on) or "paused"."""
    st = r.get("plan_status") or ""
    if r.get("plan") in ("plus", "pro") and st == "past_due":
        return "paused" if (r.get("plan_failed") or 0) >= MAX_FAILED else "retrying"
    if r.get("plan") in ("plus", "pro") and st == "unpaid":
        return "paused"
    return ""


def status(user):
    ensure_yearly()
    s = settings()
    out = {"enabled": s["on"], "test": s["test"], "buttons": buttons(s) and not hidden(), "early": not buttons(s), "hidden": hidden(), "yearly": s["yearly"],
           "plans": {k: {"name": v["name"], "price": v["price"], "year": v["year"], "cap": v["cap"]} for k, v in PLANS.items()}}
    if user:
        r = auth_api.billing_row(user["id"]) or {}
        plan = plan_of(user)
        out.update(signedIn=True, plan=plan, used=_week_used(user["id"]), cap=PLANS[plan]["cap"], renews=r.get("plan_renews") or 0,
                   canceling=bool(r.get("plan_cancel")), status=r.get("plan_status") or "", hasCustomer=bool(r.get("stripe_customer")),
                   problem=_problem(r) if s["on"] else "", interval=r.get("plan_interval") or "month")
    else:
        out.update(signedIn=False, plan="free")
    return out


def checkout(user, plan, site, interval="month"):
    if hidden():
        return 403, {"error": "Plus and Pro are not open yet. They are coming soon; nothing was charged.", "code": "plans_hidden"}
    s = settings()
    if not s["on"]:
        return 503, {"error": "Payments are not switched on yet."}
    if not user:
        return 401, {"error": "Sign in first so the plan is saved to your account."}
    if not user.get("emailVerified"):
        return 403, {"error": "Verify your email first (Profile, Account).", "code": "verify"}
    if plan not in ("plus", "pro"):
        return 400, {"error": "Choose Plus or Pro."}
    if interval not in ("month", "year") or (interval == "year" and not s["yearly"]):
        return 400, {"error": "Choose Monthly or Yearly."}
    r = auth_api.billing_row(user["id"]) or {}
    if r.get("stripe_sub") and (plan_of(user) != "free" or _problem(r)):
        return 409, {"error": "You already have a plan. Use Manage billing to switch, cancel or update your card.", "code": "has_plan"}
    # Card checks are Stripe's: Checkout refuses numbers that are not real (wrong length or check digit), asks the card's bank to approve the
    # first charge (CVC and postal code included), runs Radar, and asks for 3D Secure whenever the bank or Radar wants it (Stripe's
    # recommended automatic setting, so it is not forced on every card). The plan only starts when that charge succeeded (see webhook).
    price = s["price_" + plan + ("_year" if interval == "year" else "")]
    params = {"mode": "subscription", "line_items[0][price]": price, "line_items[0][quantity]": "1",
              "success_url": site + "/?billing=success", "cancel_url": site + "/?billing=cancel",
              "client_reference_id": str(user["id"]), "metadata[uaply_user]": str(user["id"]), "metadata[plan]": plan,
              "subscription_data[metadata][uaply_user]": str(user["id"]), "subscription_data[metadata][plan]": plan,
              # the account number alone is not enough to find the account again: if the accounts file were ever lost (a host with no
              # disk) numbers start again at 1 and would name someone else, so the address goes along and must match (_uid)
              "metadata[uaply_email]": user["email"], "subscription_data[metadata][uaply_email]": user["email"],
              "metadata[interval]": interval, "subscription_data[metadata][interval]": interval,
              # the payment methods switched on in Stripe's dashboard (no payment_method_types: so Link, Apple Pay and Google Pay appear
              # once enabled there), and no address beyond what Stripe itself needs for the card
              "allow_promotion_codes": "true", "billing_address_collection": "auto",
              "payment_method_options[card][request_three_d_secure]": "automatic"}
    if r.get("stripe_customer"):
        params["customer"] = r["stripe_customer"]
    else:
        params["customer_email"] = user["email"]
    code, body = _stripe("POST", "/v1/checkout/sessions", params)
    if code == 200 and str(body.get("url", "")).startswith(("https://", "http://127.0.0.1")):
        return 200, {"url": body["url"]}
    return 502, {"error": "The payment page could not be opened. Try again in a moment."}


def portal(user, site):
    s = settings()
    if not s["on"]:
        return 503, {"error": "Payments are not switched on yet."}
    if not user:
        return 401, {"error": "Sign in first."}
    r = auth_api.billing_row(user["id"]) or {}
    if not r.get("stripe_customer"):
        return 400, {"error": "There is no subscription to manage yet."}
    code, body = _stripe("POST", "/v1/billing_portal/sessions", {"customer": r["stripe_customer"], "return_url": site + "/?billing=portal"})
    if code == 200 and str(body.get("url", "")).startswith(("https://", "http://127.0.0.1")):
        return 200, {"url": body["url"]}
    return 502, {"error": "The billing page could not be opened. Try again in a moment."}


KEEP_ACCOUNT = ("Your plan could not be cancelled with Stripe just now, so your account was NOT deleted (you would have kept being charged "
                "with no account to stop it). Open Profile, Plan and billing, Manage billing, cancel the plan there, then delete the account again.")


def cancel_on_delete(user_id):
    """Called by auth_api.delete_account once the password is right and BEFORE the account is removed. Returns "" (go ahead) or the sentence
    that keeps the account. The subscription is cancelled IMMEDIATELY (DELETE /v1/subscriptions/<id>), not at the end of the period: once
    the account is gone nobody can use the rest of the month or manage the subscription, and a subscription left running until the period
    ends could still renew or retry a charge if that cancellation were later undone in the portal. Stripe does not refund the current month
    by itself; the owner can refund it in Stripe if asked. With payments off, or no subscription, nothing needs cancelling."""
    row = auth_api.billing_row(user_id) or {}
    sub = row.get("stripe_sub") or ""
    if not sub:
        return ""
    if row.get("plan_status") in ("canceled", "incomplete_expired"):
        return ""                                        # already over: Stripe will never charge it again
    if not settings()["on"]:
        # no keys on this server, so Stripe cannot be asked and Manage billing cannot open either; keeping the account would trap the
        # person, so it is deleted and the owner is told to cancel the subscription in Stripe by hand
        sys.stderr.write("[uaply] account %s was deleted while payments are off: CANCEL subscription %s in Stripe, Customers\n" % (user_id, sub[:40]))
        return ""
    code, body = _stripe("DELETE", "/v1/subscriptions/" + urllib.parse.quote(sub, safe=""))
    if code == 200 or code == 404:                       # 404: Stripe no longer has it, so nothing can be charged
        auth_api.set_billing(user_id, plan="free", plan_status="canceled", plan_cancel=0)
        return ""
    sys.stderr.write("[uaply] the subscription %s of account %s could not be cancelled (HTTP %s); the account was kept\n" % (sub[:40], user_id, code))
    return KEEP_ACCOUNT


def verify_signature(raw, header, secret, tolerance=300, now=None):
    """Stripe's scheme: header 't=TIMESTAMP,v1=HEX[,v1=...]'; HEX = HMAC-SHA256(secret, 'TIMESTAMP.' + raw body). The timestamp is inside what is
    signed, so it cannot be changed; an event more than 5 minutes old or ahead (a recorded one sent again) is refused, as Stripe's libraries do."""
    if not secret or not header or not isinstance(raw, bytes):
        return False
    parts = [p.split("=", 1) for p in header.split(",") if "=" in p]
    ts = next((v.strip() for k, v in parts if k.strip() == "t"), "")
    sigs = [v.strip() for k, v in parts if k.strip() == "v1"]
    if not ts.isdigit() or not sigs or len(ts) > 12:
        return False
    if abs((now or time.time()) - int(ts)) > tolerance:
        return False
    want = hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(want, s) for s in sigs)


def _plan_for_price(price):
    """Plus or Pro for one of our two exact prices; otherwise "" (an unknown price never unlocks a plan)."""
    s = settings()
    pid = price.get("id") if isinstance(price, dict) else price
    return ("plus" if pid and pid in (s.get("price_plus"), s.get("price_plus_year")) else
            "pro" if pid and pid in (s.get("price_pro"), s.get("price_pro_year")) else "")


def _interval_for_price(price):
    s = settings()
    pid = price.get("id") if isinstance(price, dict) else price
    return "year" if pid and pid in (s.get("price_plus_year"), s.get("price_pro_year")) else "month"


def _ref_uid(ref, meta):
    """The account a Stripe object's account number names, or None. When the object also carries the account's address (every checkout
    since uaply_email was added), the number counts only if that account still has that address: a number reused after the accounts file
    was lost, or after the account was deleted, never hands one person's subscription to another."""
    ref = str(ref or "")
    row = auth_api.billing_row(int(ref)) if ref.isdigit() else None
    if not row:
        return None
    want = (meta or {}).get("uaply_email") if isinstance(meta, dict) else None
    if want and auth_api.canonical_email(str(want)) != row["email"]:
        return None
    return int(ref)


def _uid(meta, customer, sub_id, user_id=None):
    if user_id:
        return user_id
    uid = _ref_uid((meta or {}).get("uaply_user", ""), meta)
    if uid:
        return uid
    return auth_api.find_billing(customer or "", sub_id or "")


def _fresh_subscription(sub_id, fallback=None):
    """The subscription as Stripe has it now (events can arrive late or out of order). If Stripe cannot be asked right now, raise, so the
    webhook answers 500 and Stripe sends the event again later; a subscription Stripe no longer has falls back to the signed event's copy."""
    code, sub = _stripe("GET", "/v1/subscriptions/" + urllib.parse.quote(str(sub_id), safe=""))
    if code == 200 and isinstance(sub, dict) and sub.get("id"):
        return sub
    if code == 404 and isinstance(fallback, dict):
        return fallback
    raise RuntimeError("Stripe did not return subscription %s (HTTP %s)" % (str(sub_id)[:40], code))


def _apply_subscription(sub, user_id=None, failed=None):
    meta = sub.get("metadata") or {}
    uid = _uid(meta, sub.get("customer"), sub.get("id"), user_id)
    if not uid:
        return False
    items = ((sub.get("items") or {}).get("data") or [])
    plan = _plan_for_price(items[0].get("price") or {}) if items else ""
    st = sub.get("status") or ""
    renews = int(sub.get("current_period_end") or (items[0].get("current_period_end") if items else 0) or 0)     # on the item since API 2025-03-31
    fields = dict(plan=plan if (plan and st in ACTIVE) else "free", plan_status=st, plan_renews=renews,
                  plan_cancel=1 if (sub.get("cancel_at_period_end") or sub.get("cancel_at")) and st != "canceled" else 0,
                  stripe_customer=sub.get("customer") or "", stripe_sub=sub.get("id") or "",
                  plan_interval=_interval_for_price(items[0].get("price") or {}) if items else "month")
    if st in ("active", "trialing"):
        fields["plan_failed"] = 0                        # a payment went through: nothing is owed
    elif failed is not None:
        fields["plan_failed"] = failed
    auth_api.set_billing(uid, **fields)
    return True


def _invoice_sub(inv):
    """The subscription id of an invoice: inv.subscription in older API versions, inv.parent.subscription_details.subscription since 2025-03-31."""
    sid = inv.get("subscription")
    if not sid:
        sid = (((inv.get("parent") or {}).get("subscription_details") or {}).get("subscription"))
    return sid.get("id") if isinstance(sid, dict) else (sid or "")


def webhook(raw, header):
    """Returns (status, body). Only events with a valid signature change anything. Each event id is handled once."""
    s = settings()
    if not verify_signature(raw, header, s.get("webhook_secret") or ""):
        return 400, {"error": "bad signature"}
    try:
        ev = json.loads(raw.decode("utf-8"))
    except ValueError:
        return 400, {"error": "bad body"}
    if not isinstance(ev, dict) or not isinstance(ev.get("id"), str) or not ev["id"]:
        return 400, {"error": "bad body"}
    if s["on"] and isinstance(ev.get("livemode"), bool) and ev["livemode"] == s["test"]:
        sys.stderr.write("[uaply] Stripe sent a %s-mode event to a server with %s keys; ignored (check STRIPE_WEBHOOK_SECRET)\n"
                         % ("live" if ev["livemode"] else "test", "test" if s["test"] else "live"))
        return 200, {"ok": True, "ignored": "mode"}
    if auth_api.stripe_event_seen(ev["id"]):
        return 200, {"ok": True, "duplicate": True}
    if not s["on"]:
        return 503, {"error": "payments are off"}        # Stripe tries again later, once the keys are back
    kind, obj = ev.get("type", ""), ((ev.get("data") or {}).get("object") or {})
    if not isinstance(obj, dict):
        return 400, {"error": "bad body"}
    if kind == "checkout.session.completed" and obj.get("mode") == "subscription":
        ref = obj.get("client_reference_id") or ""
        uid = _ref_uid(ref, obj.get("metadata"))
        if uid and obj.get("customer"):
            auth_api.set_billing(uid, stripe_customer=obj["customer"], stripe_sub=obj.get("subscription") or "")
        if obj.get("subscription"):
            _apply_subscription(_fresh_subscription(obj["subscription"]), uid)     # active only if the first payment really succeeded
    elif kind in ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted") and obj.get("id"):
        _apply_subscription(_fresh_subscription(obj["id"], obj))
    elif kind in ("invoice.paid", "invoice.payment_failed"):
        sid = _invoice_sub(obj)
        if sid:
            tries = obj.get("attempt_count") if isinstance(obj.get("attempt_count"), int) else 1
            _apply_subscription(_fresh_subscription(sid), failed=0 if kind == "invoice.paid" else tries)
    # remembered only once it was handled: if handling failed (an error reaches serve.py, which answers 500), Stripe sends the event
    # again and that retry must not be thrown away as a duplicate, or the person who paid would never get the plan
    auth_api.remember_stripe_event(ev["id"])
    return 200, {"ok": True}
