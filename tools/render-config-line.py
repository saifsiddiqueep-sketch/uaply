"""Puts the UAPLY_CONFIG_JSON line for Render on the clipboard, built from this computer's uaply-config.json.

Nothing is printed except which blanks are left: the owner pastes the line into Render -> Environment -> UAPLY_CONFIG_JSON
himself. Keys this computer does not have are left as PASTE-... blanks to fill in there. Run from the project folder:

    python tools/render-config-line.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOGLE_CLIENT_ID = "75329399310-ufa3e3aanuovf058c9ua3lbv9d1vo1vv.apps.googleusercontent.com"   # public: it is sent to every browser

path = os.path.join(HERE, "uaply-config.json")
cfg = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
smtp = cfg.get("smtp") or {}
google = cfg.get("google") or {}
feed_keys = {k: v for k, v in (cfg.get("feed_keys") or {}).items() if v}

line = {
    "delivery": "live",
    "public_url": "https://uaply.net",
    "owner_copy": "uaplytechnologies@gmail.com",
    "support_email": "uaplytechnologies@gmail.com",
    "smtp": {
        "host": smtp.get("host") or "smtp-relay.brevo.com",
        "port": int(smtp.get("port") or 587),
        "starttls": True,
        "user": smtp.get("user") or "PASTE-BREVO-LOGIN",
        "password": smtp.get("password") or "PASTE-BREVO-SMTP-KEY",
        "from_addr": smtp.get("from_addr") or "uaplytechnologies@uaply.net",
    },
    "google": {
        "client_id": google.get("client_id") or GOOGLE_CLIENT_ID,
        "client_secret": google.get("client_secret") or "PASTE-GOOGLE-CLIENT-SECRET",
    },
}
if feed_keys:
    line["feed_keys"] = feed_keys

text = json.dumps(line, separators=(",", ":"))        # one line, ASCII only
if sys.platform == "win32":
    subprocess.run("clip", input=text.encode("ascii"), check=True)
elif sys.platform == "darwin":
    subprocess.run("pbcopy", input=text.encode("ascii"), check=True)
else:
    sys.exit("No clipboard command known for this system; paste the line by hand from uaply-config.json.")

blanks = [w for w in ("PASTE-BREVO-LOGIN", "PASTE-BREVO-SMTP-KEY", "PASTE-GOOGLE-CLIENT-SECRET") if w in text]
print("UAPLY_CONFIG_JSON is on the clipboard (%d characters)." % len(text))
print("Blanks still to fill in Render: " + (", ".join(blanks) if blanks else "none"))
