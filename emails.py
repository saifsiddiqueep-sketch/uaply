"""The emails UAply sends when someone swipes right: the receipt to the applicant and the copy to the owner.

Each builder returns (subject, plain_text, html). Every email says plainly what the swipe did, shows the job, lists what was
shared, and says what happens next. In test mode (the sandbox, dev, and any server not switched to live delivery) the subject starts
with [TEST] and a banner explains that nothing was sent to the employer.

How it compares with the big job sites (what they document about their own confirmation emails):
  * Handshake: "You successfully applied to ...", the date and time, a summary card (company, title, pay, location, job type) and a
    View application link; statuses Pending, Reviewed, Declined, Hired.
  * Indeed: an on-screen confirmation plus an email; you track it under Applied; an application cannot be edited after sending;
    its advice is to wait one to two weeks, follow up politely after two to three, and move on after three to four.
  * LinkedIn and ZipRecruiter do not publish the wording of their confirmation emails; both confirm the application and keep it
    listed in the app (My Jobs > Applied on LinkedIn).
UAply combines the common parts: a clear headline, a summary card, the date and time, what was shared, what happens next, and where
to track it. A UAply swipe can also end at the employer's own site, so a swipe that sends nothing is explained instead of hidden.
All text that comes from a person or a job feed is HTML-escaped. Only https links are used.
"""
import html
import time

BRAND = "#C92A55"
TYPE_LABEL = {"job": "Full-time", "parttime": "Part-time", "internship": "Internship", "coop": "Co-op"}
MODE_LABEL = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "On-site"}

SWIPE_MEANING = ("Swiping right means: I want this job. UAply saves it to your Applied list and, if the employer accepts applications "
                 "through UAply, sends them your profile. If the employer takes applications only on its own site, UAply gives you the "
                 "link and your details so you can finish there. Swiping left only hides the job; nothing is sent.")
NOT_SHARED = "Your voluntary answers (such as race, gender, veteran or disability status) are never sent."
NEXT_STEPS = [
    "The employer reviews applications in its own time, and many employers get a lot of them, so you may not hear from every one.",
    "A sensible pace: wait one to two weeks; if you have heard nothing after two to three weeks, send a short, polite follow-up; "
    "after three to four weeks it is reasonable to move on to other jobs.",
    "Keep track in UAply: open Job Tracker, then Applied, and mark the application Interview, Accepted or Rejected as things happen.",
    "An application cannot be edited after it is sent. To correct something, contact the employer directly.",
]


def _money(sal):
    try:
        lo, hi = int(sal[0]), int(sal[1])
    except (TypeError, ValueError, IndexError):
        return ""
    if hi <= 0:
        return ""
    k = lambda n: "$%dk" % round(n / 1000) if n >= 1000 else "$%d" % n   # noqa: E731
    return "%s to %s a year" % (k(lo), k(hi)) if lo else "up to %s a year" % k(hi)


def _when(ts):
    """'Oct 5, 2026 at 9:05 AM UTC': no leading zero on the day or the hour (the old one-time replace dropped only the first of the two)."""
    t = time.gmtime(ts)
    return "%s %d, %d at %d:%02d %s UTC" % (time.strftime("%b", t), t.tm_mday, t.tm_year, (t.tm_hour % 12) or 12, t.tm_min, "AM" if t.tm_hour < 12 else "PM")


def _https(u):
    return u if isinstance(u, str) and u.lower().startswith("https://") and " " not in u else ""


def _summary_rows(job, match):
    rows = [("Company", job.get("co")), ("Job title", job.get("role")), ("Location", job.get("loc")),
            ("Job type", TYPE_LABEL.get(job.get("type") or "job", "")), ("Work style", MODE_LABEL.get(job.get("mode"), "")),
            ("Pay", _money(job.get("sal"))), ("Your match", ("%d%%" % match) if match else ""),
            ("Source", job.get("via")), ("Official announcement", _https(job.get("announcement")))]      # the feed is credited, as its terms ask
    return [(k, v) for k, v in rows if v]


def _headline(status, job, test):
    co, role = job.get("co", "the employer"), job.get("role", "this job")
    if status == "handoff":
        return ("One more step: finish your application to %s" % co,
                "You swiped right on %s at %s. Your application is not complete yet: %s takes applications on its own site, so UAply "
                "could not send it for you. Use the button below; your details are listed further down, ready to copy." % (role, co, co))
    if status == "sent":
        return ("Your application was sent to %s" % co,
                "You swiped right on %s at %s, and UAply sent your application to the employer." % (role, co))
    return ("You applied to %s at %s" % (role, co),
            "You swiped right on %s at %s. This is a test: UAply recorded the application in its test inbox and sent nothing to %s." % (role, co, co))


def subject_for(status, job, test):
    co, role = job.get("co", ""), job.get("role", "")
    s = ("Finish your application: %s at %s" if status == "handoff" else "Applied: %s at %s") % (role, co)
    return ("[TEST] " if test else "") + s[:190]


def _test_note(status, job, contact, channels=(), preview=False):
    """What the live app would have done with this swipe, said in the test banner. It follows the channels the server recorded, so a
    hiring system is never described as an email and a sandbox preview never as a delivery."""
    if status == "handoff":
        return "This is a test email. It is sent because this copy of UAply is in test mode; the swipe itself behaves the same in the live app."
    co = job.get("co") or "the employer"
    channels = [str(c) for c in channels or []]
    if preview:
        what = ("This test filled in %s's real application form to show what UAply would send once %s connects its hiring system to UAply. "
                "Until then, in the live app this swipe sends you to %s's own site to finish." % (co, co, co))
    elif any(c.startswith("email") for c in channels) or not channels:
        what = "In the live app this swipe would have emailed your application%s." % ((" to %s" % contact) if contact else " to the employer")
    elif any(c.startswith("hiring system") for c in channels):
        what = "In the live app this swipe would have sent your application straight into %s's hiring system." % co
    else:
        what = "In the live app this swipe would have sent your application to %s's own system." % co
    return "This is a test email. In test mode UAply does not send applications to employers. %s Your test application is saved in the test inbox." % what


def _resume_rows(rows, status, co, owner=False):
    """The resume line says where the file really went: no email from UAply to the applicant or the owner carries the file itself."""
    where = {"sent": "sent to %s with the application" % co, "delivered_test": "included in the test application",
             "handoff": "upload it on %s's form" % co}.get(status, "")
    if owner and status in ("sent", "delivered_test"):
        where += "; not attached to this copy"
    elif owner and status == "handoff":
        where = "the applicant uploads it on %s's form" % co
    out = []
    for k, v in rows:
        if k == "Resume file" and str(v).endswith(" (attached)"):
            v = str(v)[:-len(" (attached)")] + ((" (%s)" % where) if where else "")
        out.append((k, v))
    return out


def applicant_receipt(ctx):
    """ctx keys: test, status, cand, job, at, match, to, rows (application details as (label, value) pairs), note, user_email,
    base_url, support_email. Returns (subject, text, html)."""
    status, job, cand, test = ctx["status"], ctx["job"], ctx["cand"], ctx["test"]
    head, lead = _headline(status, job, test)
    subject = subject_for(status, job, test)
    posting = _https(job.get("url"))
    track = (ctx.get("base_url") or "").rstrip("/")
    desc = (job.get("desc") or job.get("blurb") or "").strip()
    summary = _summary_rows(job, ctx.get("match") or 0)
    rows = _resume_rows(ctx.get("rows") or [], status, job.get("co") or "the employer")
    note = (ctx.get("note") or "").strip()
    name = cand.get("name") or "there"
    when = _when(ctx.get("at") or time.time())
    when_label = "Swiped right on" if status == "handoff" else "Applied on"      # a hand-off is not an application yet
    test_note = _test_note(status, job, ctx.get("to"), ctx.get("channels"), ctx.get("preview"))

    # ---- plain text ----
    t = []
    if test:
        t += ["*** TEST EMAIL ***", test_note, ""]
    t += ["Hi %s," % name, "", head, "", lead, "", "%s: %s" % (when_label, when), ""]
    t += ["THE JOB"] + ["  %s: %s" % kv for kv in summary]
    if posting:
        t += ["  Posting: %s" % posting]
    if desc:
        t += ["", "ABOUT THE JOB", "  " + desc]
    if status == "handoff" and posting:
        t += ["", "FINISH YOUR APPLICATION", "  Open: %s" % posting]
    t += ["", "WHAT A SWIPE RIGHT MEANS", "  " + SWIPE_MEANING]
    t += ["", "WHAT WAS SHARED" if status != "handoff" else "YOUR DETAILS, READY FOR THE EMPLOYER'S FORM"]
    if note:
        t += ["  Message: " + note]
    t += ["  %s: %s" % kv for kv in rows] or ["  Your name and email."]
    t += ["  " + NOT_SHARED]
    t += ["", "WHAT HAPPENS NEXT"] + ["  - " + x for x in NEXT_STEPS]
    t += ["", "TRACK IT", "  Open UAply, then Job Tracker, then Applied." + ((" %s" % track) if track else "")]
    t += ["", "--", "UAply", "You get this email because you are signed in to UAply as %s." % ctx.get("user_email", "")]
    if ctx.get("support_email"):
        t += ["Questions: %s" % ctx["support_email"]]
    text = "\n".join(t) + "\n"

    # ---- HTML ----
    e = html.escape
    def card_rows(pairs):
        return "".join('<tr><td style="padding:5px 12px 5px 0;color:#7B5560;vertical-align:top;white-space:nowrap">%s</td>'
                       '<td style="padding:5px 0;color:#2A1218;font-weight:600">%s</td></tr>' % (e(k), e(str(v))) for k, v in pairs)
    def h(title):
        return '<p style="margin:22px 0 6px;font:700 12px/1 Arial,sans-serif;letter-spacing:.08em;color:%s">%s</p>' % (BRAND, e(title))
    parts = []
    if test:
        parts.append('<div style="background:#FFF4D6;border:1px solid #F0D58A;border-radius:10px;padding:12px 14px;margin-bottom:16px;color:#5A4300">'
                     '<b>TEST EMAIL.</b> %s</div>' % e(test_note))
    parts.append('<h1 style="margin:0 0 8px;font:700 22px/1.25 Arial,sans-serif;color:#2A1218">%s</h1>' % e(head))
    parts.append('<p style="margin:0 0 4px;color:#2A1218">Hi %s,</p><p style="margin:0 0 6px;color:#2A1218">%s</p>' % (e(name), e(lead)))
    parts.append('<p style="margin:0;color:#7B5560;font-size:13px">%s %s</p>' % (e(when_label), e(when)))
    parts.append(h("THE JOB"))
    parts.append('<table role="presentation" style="border-collapse:collapse;font-size:14px">%s</table>' % card_rows(summary))
    if desc:
        parts.append(h("ABOUT THE JOB") + '<p style="margin:0;color:#2A1218">%s</p>' % e(desc))
    if posting:
        label = "Finish your application" if status == "handoff" else "View the job posting"
        parts.append('<p style="margin:18px 0 0"><a href="%s" style="display:inline-block;background:%s;color:#fff;text-decoration:none;'
                     'font-weight:700;padding:12px 20px;border-radius:999px">%s</a></p>' % (e(posting, quote=True), BRAND, e(label)))
    parts.append(h("WHAT A SWIPE RIGHT MEANS") + '<p style="margin:0;color:#2A1218">%s</p>' % e(SWIPE_MEANING))
    parts.append(h("WHAT WAS SHARED" if status != "handoff" else "YOUR DETAILS, READY FOR THE EMPLOYER'S FORM"))
    if note:
        parts.append('<p style="margin:0 0 8px;color:#2A1218"><b>Message:</b> %s</p>' % e(note))
    parts.append('<table role="presentation" style="border-collapse:collapse;font-size:14px">%s</table>' % (card_rows(rows) or card_rows([("Shared", "Your name and email")])))
    parts.append('<p style="margin:8px 0 0;color:#7B5560;font-size:13px">%s</p>' % e(NOT_SHARED))
    parts.append(h("WHAT HAPPENS NEXT") + '<ul style="margin:0;padding-left:20px;color:#2A1218">%s</ul>' % "".join('<li style="margin:4px 0">%s</li>' % e(x) for x in NEXT_STEPS))
    track_html = ('<a href="%s" style="color:%s">%s</a>' % (e(track, quote=True), BRAND, e(track))) if _https(track) else ""
    parts.append(h("TRACK IT") + '<p style="margin:0;color:#2A1218">Open UAply, then <b>Job Tracker</b>, then <b>Applied</b>. %s</p>' % track_html)
    foot = "You get this email because you are signed in to UAply as %s." % ctx.get("user_email", "")
    if ctx.get("support_email"):
        foot += " Questions: %s." % ctx["support_email"]
    parts.append('<p style="margin:26px 0 0;padding-top:12px;border-top:1px solid #F3DADF;color:#7B5560;font-size:12px">%s</p>' % e(foot))
    body = "".join(parts)
    page = ('<!doctype html><html><body style="margin:0;padding:20px;background:#FDF0F2;font:15px/1.5 Arial,Helvetica,sans-serif">'
            '<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:16px;padding:24px 26px">'
            '<p style="margin:0 0 14px;font:800 20px Arial,sans-serif;color:%s">UAply</p>%s</div></body></html>' % (BRAND, body))
    return subject, text, page


def finish_digest(ctx):
    """The day's reminder of the jobs a person swiped right on that take applications on the employer's own site (at most one a day, instead
    of an email per swipe). ctx keys: items [{co, role, url, at}], test, base_url, user_email, support_email. Returns (subject, text, html)."""
    items, test = ctx.get("items") or [], bool(ctx.get("test"))
    n = len(items)
    if n == 1:
        subject = "Finish your application: %s at %s" % (items[0].get("role", ""), items[0].get("co", ""))
    else:
        subject = "Finish your applications: %d jobs waiting on the employers' sites" % n
    subject = ("[TEST] " if test else "") + subject[:190]
    head = "One more step for %s" % ("this job" if n == 1 else "%d jobs" % n)
    lead = ("You swiped right on %s. %s takes applications on %s own site, so UAply could not send %s for you. Finish %s there; your "
            "details are in UAply, ready to copy." % ("this job" if n == 1 else "these jobs", "The employer" if n == 1 else "Each employer",
                                                      "its", "it" if n == 1 else "them", "it" if n == 1 else "each one"))
    track = (ctx.get("base_url") or "").rstrip("/")
    t = []
    if test:
        t += ["*** TEST EMAIL ***", "This is a test email. It is sent because this copy of UAply is in test mode.", ""]
    t += [head, "", lead, ""]
    for i in items:
        t += ["- %s at %s (swiped %s)" % (i.get("role", ""), i.get("co", ""), _when(i.get("at") or time.time()))]
        if _https(i.get("url")):
            t += ["  Finish: %s" % _https(i.get("url"))]
    t += ["", "TRACK IT", "  Open UAply, then Job Tracker, then Applied. Mark each one as applied once you finish it." + ((" %s" % track) if track else "")]
    t += ["", "--", "UAply", "You get this at most once a day, only when a job you swiped right on is waiting on the employer's site. "
          "You are signed in to UAply as %s." % ctx.get("user_email", "")]
    if ctx.get("support_email"):
        t += ["Questions: %s" % ctx["support_email"]]
    text = "\n".join(t) + "\n"
    e = html.escape
    parts = []
    if test:
        parts.append('<div style="background:#FFF4D6;border:1px solid #F0D58A;border-radius:10px;padding:12px 14px;margin-bottom:16px;color:#5A4300">'
                     '<b>TEST EMAIL.</b> This is a test email. It is sent because this copy of UAply is in test mode.</div>')
    parts.append('<h1 style="margin:0 0 8px;font:700 22px/1.25 Arial,sans-serif;color:#2A1218">%s</h1>' % e(head))
    parts.append('<p style="margin:0 0 12px;color:#2A1218">%s</p>' % e(lead))
    rows = []
    for i in items:
        link = _https(i.get("url"))
        rows.append('<li style="margin:8px 0;color:#2A1218"><b>%s</b> at %s<br><span style="color:#7B5560;font-size:13px">Swiped %s</span>%s</li>' % (
            e(i.get("role", "")), e(i.get("co", "")), e(_when(i.get("at") or time.time())),
            ('<br><a href="%s" style="color:%s;font-weight:700">Finish on their site</a>' % (e(link, quote=True), BRAND)) if link else ""))
    parts.append('<ul style="margin:0;padding-left:20px">%s</ul>' % "".join(rows))
    track_html = ('<a href="%s" style="color:%s">%s</a>' % (e(track, quote=True), BRAND, e(track))) if _https(track) else ""
    parts.append('<p style="margin:18px 0 0;color:#2A1218">Open UAply, then <b>Job Tracker</b>, then <b>Applied</b>. Mark each one as applied once you finish it. %s</p>' % track_html)
    foot = ("You get this at most once a day, only when a job you swiped right on is waiting on the employer's site. You are signed in to UAply as %s."
            % ctx.get("user_email", ""))
    if ctx.get("support_email"):
        foot += " Questions: %s." % ctx["support_email"]
    parts.append('<p style="margin:26px 0 0;padding-top:12px;border-top:1px solid #F3DADF;color:#7B5560;font-size:12px">%s</p>' % e(foot))
    page = ('<!doctype html><html><body style="margin:0;padding:20px;background:#FDF0F2;font:15px/1.5 Arial,Helvetica,sans-serif">'
            '<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:16px;padding:24px 26px">'
            '<p style="margin:0 0 14px;font:800 20px Arial,sans-serif;color:%s">UAply</p>%s</div></body></html>' % (BRAND, "".join(parts)))
    return subject, text, page


def verification_email(digits):
    """The email that carries the 6-digit code proving an email address is the person's own. Returns (subject, text, html).
    The code is shown large, with how long it works and what to do if the person did not ask for it (the same wording as the big job sites)."""
    code = "".join(ch for ch in str(digits) if ch.isdigit())[:6]
    subject = "%s is your UAply verification code" % code
    text = ("Your UAply verification code is:\n\n    %s\n\n"
            "Enter it in UAply to confirm this email address. It works for 10 minutes.\n\n"
            "If you did not create a UAply account, ignore this email. Nobody can use your address without this code.\n\n--\nUAply\n") % code
    e = html.escape
    page = ('<!doctype html><html><body style="margin:0;padding:20px;background:#FDF0F2;font:15px/1.5 Arial,sans-serif;color:#2A1218">'
            '<div style="max-width:480px;margin:0 auto;background:#fff;border:1px solid #F3DADF;border-radius:14px;padding:22px">'
            '<p style="margin:0 0 14px;color:%s;font-weight:800;font-size:18px">UAply</p>'
            '<h1 style="margin:0 0 8px;font-size:20px">Confirm your email</h1>'
            '<p style="margin:0 0 14px">Enter this code in UAply to confirm that this email address is yours:</p>'
            '<p style="margin:0 0 14px;padding:14px;background:#FDF0F2;border-radius:10px;text-align:center;font:800 32px/1 ui-monospace,Menlo,Consolas,monospace;letter-spacing:.3em">%s</p>'
            '<p style="margin:0 0 8px;color:#7B5560;font-size:13px">The code works for 10 minutes. After 5 wrong tries you will need a new one.</p>'
            '<p style="margin:0;color:#7B5560;font-size:13px">If you did not create a UAply account, ignore this email. Nobody can use your address without this code.</p>'
            '</div></body></html>') % (BRAND, e(code))
    return subject, text, page


def signin_code_email(digits):
    """The email with the 6-digit code that signs in to an existing account (Email me a code), not the "Confirm your email" one (item
    21): it says what the code does, that UAply never asks for it, and what to do if the person did not ask. Returns (subject, text, html)."""
    code = "".join(ch for ch in str(digits) if ch.isdigit())[:6]
    subject = "%s is your UAply sign-in code" % code
    text = ("Your UAply sign-in code is:\n\n    %s\n\n"
            "This code signs in to your UAply account. It works for 10 minutes. UAply will never ask you for it.\n\n"
            "If it was not you, ignore this email. Nobody can sign in without this code.\n\n--\nUAply\n") % code
    e = html.escape
    page = ('<!doctype html><html><body style="margin:0;padding:20px;background:#FDF0F2;font:15px/1.5 Arial,sans-serif;color:#2A1218">'
            '<div style="max-width:480px;margin:0 auto;background:#fff;border:1px solid #F3DADF;border-radius:14px;padding:22px">'
            '<p style="margin:0 0 14px;color:%s;font-weight:800;font-size:18px">UAply</p>'
            '<h1 style="margin:0 0 8px;font-size:20px">Your sign-in code</h1>'
            '<p style="margin:0 0 14px">This code signs in to your UAply account. UAply will never ask you for it.</p>'
            '<p style="margin:0 0 14px;padding:14px;background:#FDF0F2;border-radius:10px;text-align:center;font:800 32px/1 ui-monospace,Menlo,Consolas,monospace;letter-spacing:.3em">%s</p>'
            '<p style="margin:0 0 8px;color:#7B5560;font-size:13px">The code works for 10 minutes. After 5 wrong tries you will need a new one.</p>'
            '<p style="margin:0;color:#7B5560;font-size:13px">If it was not you, ignore this email. Nobody can sign in without this code.</p>'
            '</div></body></html>') % (BRAND, e(code))
    return subject, text, page


KIND_LABEL = {"contact": "help", "bug": "problem", "general": "feedback", "answer": "feedback", "nudge": "feedback"}


def support_ticket(rec, account_email=""):
    """The email the UAply team receives when someone asks for help in the assistant. Returns (subject, text).
    The reply address of the email is the person's own (set by the sender), so pressing Reply answers them."""
    kind = KIND_LABEL.get(rec.get("topic"), "feedback")
    first = " ".join((rec.get("text") or "").split())[:70] or "(no message)"
    subject = "[UAply %s] %s" % (kind, first)
    when = time.strftime("%b %d, %Y %H:%M UTC", time.gmtime(rec.get("at") or time.time()))
    lines = ["Someone asked for help in the UAply assistant.", "", "THEIR MESSAGE", (rec.get("text") or "(they left no message)").strip(), "", "HOW TO REPLY"]
    if rec.get("email"):
        lines += ["  Press Reply. The reply address of this email is theirs: %s" % rec["email"]]
    else:
        lines += ["  They did not leave an email, so this cannot be answered by email."]
    lines += ["", "DETAILS", "  Ticket: %s" % rec.get("id", ""), "  Type: %s" % kind, "  Sent: %s" % when]
    if rec.get("page"):
        lines.append("  Screen they were on: %s" % rec["page"])
    if account_email:
        lines.append("  Signed in to UAply as: %s" % account_email)
    if rec.get("articles"):
        lines.append("  Help articles the assistant showed: %s" % ", ".join(rec["articles"]))
    return subject, "\n".join(lines) + "\n\n--\nSent by the UAply assistant. The same message is in the Feedback page of the server.\n"


def support_ack(rec):
    """The acknowledgement to a person whose email UAply has already proven is theirs. Returns (subject, text)."""
    text = ("Hi,\n\nThanks for writing to UAply. We got your message and a person on our team will reply to this address.\n\n"
            "YOUR MESSAGE\n%s\n\nTicket: %s\n\nIf you did not send this, ignore this email.\n\n--\nUAply\n") % ((rec.get("text") or "").strip(), rec.get("id", ""))
    return "We got your message to UAply", text


def owner_copy(ctx):
    """The owner's copy of an application. ctx keys: status, cand, job, at, match, to, rows, note, base_url. Returns (subject, text, html)."""
    status, job, cand = ctx["status"], ctx["job"], ctx["cand"]
    where = {"delivered_test": "the simulated test inbox (nothing was sent to %s)" % job.get("co", "the employer"),
             "sent": ("%s's own hiring system" % job.get("co", "the employer")) if any(str(c).startswith("hiring system") for c in ctx.get("channels") or []) and not ctx.get("to") else "%s, by email" % (ctx.get("to") or "the employer"),
             "handoff": "no one: %s takes applications on its own site, so the applicant was pointed there" % job.get("co", "the employer")}.get(status, status)
    subject = "%s[UAply copy] %s at %s: %s" % ("[TEST] " if ctx.get("test") else "", job.get("role", ""), job.get("co", ""),
                                               {"delivered_test": "test application", "sent": "sent", "handoff": "applicant sent to the employer's site"}.get(status, status))
    posting = _https(job.get("url"))
    summary = [("Match", v) if k == "Your match" else (k, v) for k, v in _summary_rows(job, ctx.get("match") or 0)]     # this copy is read by the owner, not the applicant
    rows = [("Name", cand.get("name")), ("Email", cand.get("email"))] + [r for r in _resume_rows(ctx.get("rows") or [], status, job.get("co") or "the employer", owner=True)
                                                                         if r[0] not in ("Applicant", "Email")]
    t = ["This is a copy for you, the UAply owner.", "", "A swipe right on %s at %s" % (job.get("role"), job.get("co")),
         "Applied on: %s" % _when(ctx.get("at") or time.time()), "It went to: %s." % where, "", "THE JOB"]
    t += ["  %s: %s" % kv for kv in summary] + (["  Posting: %s" % posting] if posting else [])
    if job.get("desc") or job.get("blurb"):
        t += ["", "ABOUT THE JOB", "  " + (job.get("desc") or job.get("blurb"))]
    t += ["", "THE APPLICANT"] + ["  %s: %s" % kv for kv in rows if kv[1]]
    if ctx.get("note"):
        t += ["", "MESSAGE", "  " + ctx["note"].strip()]
    t += ["", "WHAT A SWIPE RIGHT MEANS", "  " + SWIPE_MEANING]
    text = "\n".join(t) + "\n"
    e = html.escape
    def tbl(pairs):
        return '<table role="presentation" style="border-collapse:collapse;font-size:14px">%s</table>' % "".join(
            '<tr><td style="padding:4px 12px 4px 0;color:#7B5560;vertical-align:top;white-space:nowrap">%s</td><td style="padding:4px 0;font-weight:600">%s</td></tr>' % (e(k), e(str(v))) for k, v in pairs if v)
    page = ('<!doctype html><html><body style="margin:0;padding:20px;background:#FDF0F2;font:15px/1.5 Arial,sans-serif"><div style="max-width:600px;margin:0 auto;background:#fff;border-radius:16px;padding:24px 26px;color:#2A1218">'
            '<p style="margin:0 0 6px;color:%s;font-weight:800">UAply: copy for the owner</p>'
            '<h1 style="margin:0 0 6px;font-size:20px">%s at %s</h1><p style="margin:0 0 4px">Applied on %s. It went to: %s.</p>%s'
            '<p style="margin:16px 0 4px;color:%s;font-size:12px;font-weight:700;letter-spacing:.08em">THE JOB</p>%s%s'
            '<p style="margin:16px 0 4px;color:%s;font-size:12px;font-weight:700;letter-spacing:.08em">THE APPLICANT</p>%s%s'
            '<p style="margin:16px 0 4px;color:%s;font-size:12px;font-weight:700;letter-spacing:.08em">WHAT A SWIPE RIGHT MEANS</p><p style="margin:0">%s</p></div></body></html>') % (
        BRAND, e(job.get("role", "")), e(job.get("co", "")), e(_when(ctx.get("at") or time.time())), e(where),
        ('<p style="margin:0"><a href="%s" style="color:%s">View the posting</a></p>' % (e(posting, quote=True), BRAND)) if posting else "",
        BRAND, tbl(summary), ('<p style="margin:8px 0 0">%s</p>' % e(job.get("desc") or job.get("blurb"))) if (job.get("desc") or job.get("blurb")) else "",
        BRAND, tbl(rows), ('<p style="margin:8px 0 0"><b>Message:</b> %s</p>' % e(ctx["note"].strip())) if ctx.get("note") else "",
        BRAND, e(SWIPE_MEANING))
    return subject, text, page
