"""Save your Google sign-in keys and your Gmail sending login into uaply-config.json (git-ignored), without showing them.

  python tools/setup-config.py

It asks for each value; press Enter to keep what is already saved. Secrets are typed hidden. Nothing is printed back,
and nothing is sent anywhere. Then restart the server and open http://localhost:8766/setup to see everything go green.
"""
import getpass
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "uaply-config.json")
CLIENT_RE = re.compile(r"^\d+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

try:
    with open(PATH, encoding="utf-8") as f:
        cfg = json.load(f)
except (OSError, ValueError):
    cfg = {}
g = cfg.setdefault("google", {})
s = cfg.setdefault("smtp", {"host": "smtp.gmail.com", "port": 587, "starttls": True})


def ask(label, current, secret=False, check=None, hint=""):
    shown = "set" if (current and secret) else (current or "not set")
    while True:
        raw = (getpass.getpass if secret else input)("%s [%s]%s: " % (label, shown, (" " + hint) if hint else "")).strip()
        if not raw:
            return current
        if check and not check(raw):
            print("  That does not look right. Try again, or press Enter to skip.")
            continue
        return raw


print("UAply setup. Press Enter to keep a value. Secrets are hidden as you type.\n")
print("-- Sign in with Google (Google Auth Platform > Clients > UAply web, a Web application client; DEPLOY.md section 3)")
g["client_id"] = ask("Google client ID", g.get("client_id", ""), check=lambda v: bool(CLIENT_RE.match(v)), hint="(ends in .apps.googleusercontent.com)")
g["client_secret"] = ask("Google client secret (GOCSPX-...: the full-page sign-in used on every device)", g.get("client_secret", ""), secret=True)
url = ask("Public site address (leave empty on this computer)", g.get("public_url", ""), check=lambda v: v.startswith(("http://", "https://")))
if url:
    g["public_url"] = url.rstrip("/")
elif "public_url" in g and not g["public_url"]:
    del g["public_url"]

print("\n-- Email sending (a Gmail App Password: myaccount.google.com/apppasswords, needs 2-Step Verification)")
mail = ask("Gmail address that sends UAply email", s.get("user", ""), check=lambda v: bool(EMAIL_RE.match(v)))
if mail:
    s["user"] = s["from_addr"] = mail
s["password"] = ask("Gmail App Password", s.get("password", ""), secret=True)
s.setdefault("host", "smtp.gmail.com")
s.setdefault("port", 587)
s.setdefault("starttls", True)
cfg["owner_copy"] = ask("Your email (gets a copy of every application)", cfg.get("owner_copy", ""), check=lambda v: bool(EMAIL_RE.match(v)))

for key in ("client_id", "client_secret"):
    if not g.get(key):
        g.pop(key, None)
if not g:
    cfg.pop("google")
with open(PATH, "w", encoding="utf-8", newline="\n") as f:
    json.dump(cfg, f, indent=2)
print("\nSaved to uaply-config.json (git-ignored). Restart the server, then open http://localhost:8766/setup")
