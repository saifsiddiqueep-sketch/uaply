"""The Google Play listing pack (mobile/store/play/) against Google Play's rules. No network, a second or two.
  python tools/test-play-listing.py
1. Pictures: the icon is a 512 x 512 PNG under 1 MB; the feature graphic is 1024 x 500 without transparency; phone and tablet screenshots
   are 9:16, the right size, without transparency, under 8 MB, at least 4 of each, and each of Jobs, Job Tracker, Profile and Filters is there.
2. Texts: app name 30 characters at most, short description 80, full description 4000, test release notes 500; no emoji, no ranking
   claims Google refuses ("best", "#1", "top"), and the wording promises nothing the app does not do (free during early access, no ads).
3. Forms: the Data safety answers give the deletion page, the App content answers give the privacy policy, and both pages exist in legal/.
Pictures are made by `node tools/cdp.js tools/make-play-assets.js`."""
import glob
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLAY = os.path.join(ROOT, "mobile", "store", "play")
R = []


def t(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok or not detail else "  -> " + str(detail)))


def png(path):
    """(width, height, colour type, bytes) of a PNG, or None when it is not one."""
    try:
        with open(path, "rb") as f:
            head = f.read(33)
        if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
            return None
        w, h = struct.unpack(">II", head[16:24])
        return w, h, head[25], os.path.getsize(path)
    except OSError:
        return None


def read(rel):
    try:
        with open(os.path.join(PLAY, rel), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


# ---------- 1. pictures ----------
icon = png(os.path.join(PLAY, "icon-512.png"))
t("icon-512.png is a 512 x 512 PNG (32-bit with alpha is allowed) under 1 MB", icon and icon[:2] == (512, 512) and icon[2] in (2, 6) and icon[3] <= 1024 * 1024, icon)
fg = png(os.path.join(PLAY, "feature-graphic.png"))
t("feature-graphic.png is 1024 x 500, a 24-bit PNG (no transparency), under 15 MB", fg and fg[:3] == (1024, 500, 2) and fg[3] <= 15 * 1024 * 1024, fg)

NEEDED = ("jobs", "job-tracker", "profile", "filters")
for kind, lo, hi in (("phone", 320, 3840), ("tablet", 1080, 7680)):
    files = sorted(glob.glob(os.path.join(PLAY, "screenshots", kind, "*.png")))
    bad = []
    for f in files:
        p = png(f)
        if not p:
            bad.append(os.path.basename(f) + ": not a PNG")
            continue
        w, h, ct, size = p
        if (w, h) != (1080, 1920) or ct != 2 or size > 8 * 1024 * 1024 or not (lo <= min(w, h) and max(w, h) <= hi) or w * 16 != h * 9:
            bad.append("%s: %dx%d colour type %d, %d KB" % (os.path.basename(f), w, h, ct, size // 1024))
    names = {re.sub(r"^\d+-", "", os.path.splitext(os.path.basename(f))[0]) for f in files}
    t("%s screenshots: 4 to 8 of them, each 1080 x 1920 (9:16), 24-bit PNG without transparency, under 8 MB" % kind, 4 <= len(files) <= 8 and not bad,
      "%d files; %s" % (len(files), "; ".join(bad)))
    t("%s screenshots include Jobs, Job Tracker, Profile and Filters" % kind, set(NEEDED) <= names, sorted(names))

# ---------- 2. texts ----------
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")
RANK = re.compile(r"\b(best|top|#1|number one|no\. ?1)\b", re.I)
name, short, full = read("text/app-name.txt"), read("text/short-description.txt"), read("text/full-description.txt")
t("app name: UAply, 30 characters at most, one line", name is not None and name.strip() == "UAply" and len(name) <= 30 and "\n" not in name.strip(), repr(name))
t("short description: 1 to 80 characters, one line", short is not None and 0 < len(short.strip()) <= 80 and "\n" not in short.strip(), short and len(short))
t("full description: 1 to 4000 characters", full is not None and 0 < len(full) <= 4000, full and len(full))
alltext = "\n".join(x or "" for x in (name, short, full))
t("no emoji and no ranking claims Google refuses (best, top, #1)", not EMOJI.search(alltext) and not RANK.search(alltext),
  (EMOJI.findall(alltext), RANK.findall(alltext)))
t("the full description says how it really applies: connected employers get the application, everywhere else it opens the employer's page",
  full and "connected employer" in full and "Opens employer site" in full and "Nothing is sent for you" in full)
t("...and that it is free during early access, has no ads, is 18+, and links the privacy policy",
  full and "free during early access" in full.lower() and "no ads" in full.lower() and "18 and older" in full and "https://uaply.net/legal/privacy.html" in full)
testers = read("testers.md") or ""
notes = re.search(r"## Release notes[^\n]*\n```\n(.*?)\n```", testers, re.S)
t("test release notes: 1 to 500 characters", notes and 0 < len(notes.group(1)) <= 500, notes and len(notes.group(1)))
t("the tester invite has the opt-in link placeholder and asks for 14 days", "[OPT-IN LINK]" in testers and "14 days" in testers)

# ---------- 3. forms ----------
ds, ac, cr = read("data-safety.md") or "", read("app-content.md") or "", read("content-rating.md") or ""
t("Data safety gives the deletion page https://uaply.net/legal/delete-account.html, and that page exists",
  "https://uaply.net/legal/delete-account.html" in ds and os.path.isfile(os.path.join(ROOT, "legal", "delete-account.html")))
t("Data safety says encrypted in transit and deletion available", re.search(r"encrypted in transit\? \| \*\*Yes\*\*", ds) and re.search(r"data is deleted\? \| \*\*Yes\*\*", ds))
t("Data safety: voluntary self-identification and device location are marked not collected (they never leave the device)",
  re.search(r"Race and ethnicity \| \*\*No\*\*", ds) and re.search(r"Precise location \| \*\*No\*\*", ds))
t("App content gives the privacy policy https://uaply.net/legal/privacy.html, and that page exists",
  "https://uaply.net/legal/privacy.html" in ac and os.path.isfile(os.path.join(ROOT, "legal", "privacy.html")))
t("App content: no ads, 18 and over", "No, my app does not contain ads" in ac and "18 and over" in ac)
t("content rating answers: no user interaction, no location sharing, no digital purchases",
  all(re.search(q + r"[^|]*\| \*\*No\*\*", cr) for q in ("interact or exchange content", "physical location", "purchase digital goods")))
readme = read("README.md") or ""
missing = [f for f in ("text/app-name.txt", "text/short-description.txt", "text/full-description.txt", "icon-512.png", "feature-graphic.png",
                       "data-safety.md", "content-rating.md", "app-content.md", "testers.md") if f not in readme or not os.path.isfile(os.path.join(PLAY, f))]
t("the README's checklist names every file of the pack, and each file exists", not missing, missing)
t("docs/play-store.md has the ten steps", os.path.isfile(os.path.join(ROOT, "docs", "play-store.md")) and
  len(re.findall(r"^\| (?:[1-9]|10) \|", open(os.path.join(ROOT, "docs", "play-store.md"), encoding="utf-8").read(), re.M)) == 10)

print("\n%d / %d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
