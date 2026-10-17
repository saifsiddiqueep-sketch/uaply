"""A stand-in for the parts of the Stripe API UAply uses (Checkout sessions, subscriptions, billing portal), for tests. Nothing here talks to Stripe.
  python tools/mock-stripe.py 8798      Secret key accepted: sk_test_mockkey123456. Created sessions are listed at /__sessions.

What the person does on Stripe's own pages is played by the test through these addresses (they answer with the events Stripe would then send,
unsigned: the test signs them with the webhook secret, as Stripe does):
  POST /__pay            session=cs_test_N&card=4242424242424242   pay a Checkout session with one of Stripe's test card numbers:
                           4242 4242 4242 4242   succeeds: the subscription is active
                           4000 0000 0000 0002   declined by the bank: the session stays open, no subscription, no event (Stripe shows the error)
                           4000 0000 0000 9995   declined, insufficient funds: the same
                           4000 0000 0000 0127   declined, wrong CVC: the same
                           4000 0000 0000 0101   CVC check fails, Radar's CVC rule blocks it: the same
                           4100 0000 0000 0019   blocked by Radar as highest risk: the same
                           4000 0000 0000 0341   the card is saved but the first charge fails: the subscription is incomplete
                           any number that fails the card check digit (Luhn) or has the wrong length: refused on the page, nothing happens
  POST /__renew_fail     sub=sub_x&attempt=N        a monthly renewal failed: past_due, invoice.payment_failed with attempt_count N
  POST /__renew_paid     sub=sub_x                  a retry (or a new card) succeeded: active, invoice.paid
  POST /__portal_cancel  sub=sub_x                  the person pressed Cancel plan in the portal: cancel_at_period_end, customer.subscription.updated
  POST /__period_end     sub=sub_x                  the paid month ended (or Stripe gave up retrying): canceled, customer.subscription.deleted
  POST /__subscription   id=sub_x&json={...}        set a subscription directly
  POST /__fail_cancel                               the next cancellation (DELETE /v1/subscriptions/<id>) fails, as when Stripe is down
  DELETE /v1/subscriptions/<id>                     cancels at once (what UAply does when an account is deleted)
  GET  /__versions                                   the Stripe-Version header of every API call (UAply must pin one)
"""
import json
import sys
import time
import urllib.parse
import http.server

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8798
KEY = "sk_test_mockkey123456"
SESSIONS, SUBS, VERSIONS = [], {}, []
DECLINES = {"4000000000000002": "card_declined", "4000000000009995": "insufficient_funds", "4000000000000127": "incorrect_cvc",
            "4000000000000101": "incorrect_cvc", "4100000000000019": "highest_risk_level"}
N = [0]
FAIL_CANCEL = [False]


def luhn_ok(number):
    """The check every real card number passes (Stripe's page refuses others before anything is sent to a bank)."""
    if not number.isdigit() or not 13 <= len(number) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def event(kind, obj):
    N[0] += 1
    return {"id": "evt_mock_%d_%d" % (int(time.time()), N[0]), "object": "event", "type": kind, "livemode": False, "created": int(time.time()),
            "data": {"object": obj}}


def invoice(sub, paid, attempt=1):
    return {"id": "in_mock_%d" % (N[0] + 1), "object": "invoice", "customer": sub["customer"], "status": "paid" if paid else "open",
            "attempt_count": attempt, "billing_reason": "subscription_cycle", "subscription": None,      # since API 2025-03-31 the id is under parent
            "parent": {"type": "subscription_details", "subscription_details": {"subscription": sub["id"]}}}


class H(http.server.BaseHTTPRequestHandler):
    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _auth(self):
        VERSIONS.append(self.headers.get("Stripe-Version") or "")
        return self.headers.get("Authorization") == "Bearer " + KEY

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/__sessions":
            return self._json(200, SESSIONS)
        if u.path == "/__versions":
            return self._json(200, VERSIONS)
        if u.path.startswith(("/pay/", "/portal/")):          # what the person sees on Stripe's own page (a simple stand-in)
            last = SESSIONS[-1] if SESSIONS else {}
            body = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><body style='font:16px Arial;margin:0;background:#f6f9fc'>"
                    "<div style='background:#635bff;color:#fff;padding:14px 18px;font-weight:700'>Stripe Checkout (stand-in, test mode)</div><div style='padding:18px'>"
                    "<p style='color:#555'>Subscribe to UAply</p><h2 style='margin:4px 0'>%s</h2><p>%s</p>"
                    "<div style='border:1px solid #ddd;border-radius:8px;padding:12px;background:#fff;color:#888'>Card number 4242 4242 4242 4242 (Stripe test card)</div>"
                    "<p style='margin-top:14px'><span style='background:#635bff;color:#fff;padding:12px 20px;border-radius:8px;display:inline-block'>Subscribe</span></p></div>") % (
                "Plus, $9.99 per month" if last.get("metadata[plan]") == "plus" else "Pro, $19.99 per month", last.get("customer_email", ""))
            b = body.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            return
        if not self._auth():
            return self._json(401, {"error": {"message": "Invalid API key"}})
        if u.path.startswith("/v1/subscriptions/"):
            sid = u.path.rsplit("/", 1)[1]
            return self._json(200, SUBS[sid]) if sid in SUBS else self._json(404, {"error": {"message": "No such subscription"}})
        return self._json(404, {})

    def do_DELETE(self):
        u = urllib.parse.urlparse(self.path)
        if not self._auth():
            return self._json(401, {"error": {"message": "Invalid API key"}})
        sid = u.path.rsplit("/", 1)[1]
        if FAIL_CANCEL[0]:                                    # Stripe having a bad moment (the test asked for it with /__fail_cancel)
            FAIL_CANCEL[0] = False
            return self._json(500, {"error": {"type": "api_error", "message": "An unknown error occurred"}})
        if u.path.startswith("/v1/subscriptions/") and sid in SUBS:
            SUBS[sid].update(status="canceled", cancel_at_period_end=False)
            return self._json(200, SUBS[sid])
        return self._json(404, {"error": {"message": "No such subscription"}})

    def _sub_change(self, params, **change):
        sub = SUBS.get(params.get("sub", ""))
        if not sub:
            return None
        sub.update(change)
        return sub

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        params = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode()).items()}
        if u.path == "/__fail_cancel":                        # the next cancellation (DELETE /v1/subscriptions/...) fails with a 500
            FAIL_CANCEL[0] = True
            return self._json(200, {"ok": True})
        if u.path == "/__subscription":                       # the test creates the subscription Stripe would make after payment
            SUBS[params["id"]] = json.loads(params["json"])
            return self._json(200, {"ok": True})
        if u.path == "/__pay":
            sess = next((s for s in SESSIONS if s["id"] == params.get("session")), None)
            card = "".join(ch for ch in params.get("card", "") if ch.isdigit())
            if not sess or sess.get("status") == "complete":
                return self._json(400, {"error": {"message": "This Checkout session is no longer open."}})
            if not luhn_ok(card):
                return self._json(402, {"error": {"code": "invalid_number", "message": "Your card number is invalid."}, "events": []})
            if card in DECLINES:
                return self._json(402, {"error": {"code": "card_declined", "decline_code": DECLINES[card], "message": "Your card was declined."}, "events": []})
            sid, cust = "sub_mock_%d" % (len(SUBS) + 1), sess.get("customer") or "cus_mock_%d" % (len(SUBS) + 1)
            price = sess["line_items[0][price]"]
            ok = card != "4000000000000341"
            sub = {"id": sid, "object": "subscription", "customer": cust, "status": "active" if ok else "incomplete", "cancel_at_period_end": False,
                   "cancel_at": None, "metadata": {"uaply_user": sess.get("subscription_data[metadata][uaply_user]", ""), "plan": sess.get("subscription_data[metadata][plan]", "")},
                   "items": {"data": [{"price": {"id": price}, "current_period_end": int(time.time()) + 30 * 86400}]}}
            SUBS[sid] = sub
            sess.update(status="complete", subscription=sid, customer=cust)
            evs = [event("customer.subscription.created", sub)]
            evs.append(event("invoice.paid" if ok else "invoice.payment_failed", invoice(sub, ok)))
            evs.append(event("checkout.session.completed", {"id": sess["id"], "object": "checkout.session", "mode": "subscription", "status": "complete",
                                                            "payment_status": "paid" if ok else "unpaid", "client_reference_id": sess.get("client_reference_id"),
                                                            "customer": cust, "subscription": sid}))
            return self._json(200 if ok else 402, {"subscription": sid, "events": evs})
        if u.path == "/__renew_fail":
            sub = self._sub_change(params, status="past_due")
            return self._json(200, {"events": [event("invoice.payment_failed", invoice(sub, False, int(params.get("attempt", "1")))),
                                               event("customer.subscription.updated", sub)]}) if sub else self._json(404, {})
        if u.path == "/__renew_paid":
            sub = self._sub_change(params, status="active")
            if sub:
                sub["items"]["data"][0]["current_period_end"] = int(time.time()) + 30 * 86400
                return self._json(200, {"events": [event("invoice.paid", invoice(sub, True)), event("customer.subscription.updated", sub)]})
            return self._json(404, {})
        if u.path == "/__portal_cancel":
            sub = self._sub_change(params, cancel_at_period_end=True)
            return self._json(200, {"events": [event("customer.subscription.updated", sub)]}) if sub else self._json(404, {})
        if u.path == "/__period_end":
            sub = self._sub_change(params, status="canceled")
            return self._json(200, {"events": [event("customer.subscription.deleted", sub)]}) if sub else self._json(404, {})
        if not self._auth():
            return self._json(401, {"error": {"message": "Invalid API key"}})
        if u.path == "/v1/checkout/sessions":
            sid = "cs_test_%d" % (len(SESSIONS) + 1)
            SESSIONS.append(dict(params, id=sid, status="open"))
            return self._json(200, {"id": sid, "url": "http://127.0.0.1:%d/pay/%s" % (PORT, sid)})
        if u.path == "/v1/billing_portal/sessions":
            return self._json(200, {"id": "bps_1", "url": "http://127.0.0.1:%d/portal/%s" % (PORT, params.get("customer", ""))})
        return self._json(404, {})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
