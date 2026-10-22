"""The phone apps' permissions (mobile/) match what the web app asks for, and the words match what the code does. No network, under a second.
  python tools/test-mobile-perms.py
1. iPhone (mobile/ios/App/App/Info.plist): the location reason text is there (without it iOS refuses navigator.geolocation in the app's web
   view), says what it is for and that it never reaches the server, and no "Always" (background) location key is asked for.
2. Android (mobile/android/app/src/main/AndroidManifest.xml): coarse and fine location (Capacitor's web view asks for both at once) and
   POST_NOTIFICATIONS (interview reminders on Android 13+); never background location; the location hardware is not required.
3. Plugins: every Capacitor plugin the web code calls (plug("...") in shared/uaply-nav.js) is in mobile/package.json, the Android build
   files and the iPhone Podfile (the app's own UAply... plugins: declared in Java and registered in MainActivity). Jobs near you uses the browser's own navigator.geolocation today, so it needs no Geolocation plugin;
   if the web code ever calls plug("Geolocation"), the loop below requires @capacitor/geolocation to be installed in both apps.
4. The promise is the same everywhere: the web card says the location is never sent to our server, the iPhone text says so too, and the
   Google Play Data safety answer marks location as not collected.
5. Employer pages never get the location: the apps' main web view does not navigate to other sites (no server.allowNavigation
   beyond uaply.net), and AssistActivity (the employer and hiring-system pages) never grants geolocation. Capacitor's web view grants
   location to whatever page it has loaded, so the permission above is safe only while both hold."""
import json
import os
import plistlib
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MOB = os.path.join(ROOT, "mobile")
R = []
A = "{http://schemas.android.com/apk/res/android}"


def t(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok or not detail else "  -> " + str(detail)))


def read(*rel):
    try:
        with open(os.path.join(ROOT, *rel), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


# ---------- 1. iPhone ----------
try:
    with open(os.path.join(MOB, "ios", "App", "App", "Info.plist"), "rb") as f:
        plist = plistlib.load(f)
except Exception as e:  # noqa: BLE001  (a broken plist is a failed check, not a crash)
    plist = {}
    t("Info.plist parses", False, e)
why = plist.get("NSLocationWhenInUseUsageDescription", "")
t("Info.plist has NSLocationWhenInUseUsageDescription (iOS blocks location in the app's web view without it)", isinstance(why, str) and why.strip(), why)
t("the iPhone location text names the purpose (jobs near you) and says it is never sent to our server",
  re.search(r"\bjobs near you\b", why, re.I) and re.search(r"never sent to our server", why, re.I), why)
t("the iPhone location text is plain and short (at most 200 characters, no build-variable placeholder)", 0 < len(why) <= 200 and "$(" not in why, len(why))
always = [k for k in plist if k.startswith("NSLocationAlways")]
t("no background (Always) location key on iPhone", not always, always)
t("the bundle still names itself UAply", plist.get("CFBundleDisplayName") == "UAply", plist.get("CFBundleDisplayName"))

# ---------- 2. Android ----------
try:
    man = ET.parse(os.path.join(MOB, "android", "app", "src", "main", "AndroidManifest.xml")).getroot()
except Exception as e:  # noqa: BLE001
    man = ET.Element("manifest")
    t("AndroidManifest.xml parses", False, e)
perms = {p.get(A + "name") for p in man.findall("uses-permission")}
for p in ("INTERNET", "ACCESS_COARSE_LOCATION", "ACCESS_FINE_LOCATION", "POST_NOTIFICATIONS"):
    t("Android asks for android.permission." + p, "android.permission." + p in perms, sorted(perms))
t("Android never asks for background location", "android.permission.ACCESS_BACKGROUND_LOCATION" not in perms)
feat = {f.get(A + "name"): f.get(A + "required") for f in man.findall("uses-feature")}
t("the location hardware is optional (phones and tablets without GPS can still install)", feat.get("android.hardware.location") == "false", feat)
t("uses-permission lines sit directly under <manifest> (not inside <application>, where Android ignores them)",
  not man.findall("application/uses-permission"))

# ---------- 3. plugins ----------
nav = read("shared", "uaply-nav.js")
called = sorted(set(re.findall(r'plug\("([A-Za-z]+)"\)', nav)))
pkg = json.loads(read("mobile", "package.json") or "{}").get("dependencies", {})
gradle = read("mobile", "android", "capacitor.settings.gradle") + read("mobile", "android", "app", "capacitor.build.gradle")
pod = read("mobile", "ios", "App", "Podfile")


def kebab(name):
    return re.sub(r"(?<!^)([A-Z])", r"-\1", name).lower()


t("the web code calls at least the reminders plugin (LocalNotifications)", "LocalNotifications" in called, called)
JAVA = os.path.join("mobile", "android", "app", "src", "main", "java", "com", "uaply", "app")
main = read(JAVA, "MainActivity.java")
for name in called:
    if name.startswith("UAply"):   # the app's own plugin (Android only): declared by name in its Java file and registered in MainActivity
        own = [f for f in os.listdir(os.path.join(ROOT, JAVA)) if f.endswith("Plugin.java") and 'name = "%s"' % name in read(JAVA, f)]
        t("own plugin %s: declared in Java and registered in MainActivity" % name,
          own and "registerPlugin(%s.class)" % own[0][:-5] in main, own)
        continue
    k = kebab(name)
    t("plugin %s: @capacitor/%s in package.json, the Android build and the Podfile" % (name, k),
      "@capacitor/" + k in pkg and ":capacitor-" + k in gradle and "Capacitor" + name in pod,
      {"package.json": "@capacitor/" + k in pkg, "gradle": ":capacitor-" + k in gradle, "Podfile": "Capacitor" + name in pod})
t("Jobs near you uses navigator.geolocation (works in the apps' web views with the permissions above)",
  "navigator.geolocation.getCurrentPosition" in nav)
cfg = json.loads(read("mobile", "capacitor.config.json") or "{}")
srv = cfg.get("server", {})
t("the apps open the HTTPS site with no cleartext (geolocation only works on a secure page)",
  str(srv.get("url", "")).startswith("https://") and srv.get("cleartext") is False, srv)

# ---------- 4. one promise everywhere ----------
t("the web location card says it is never sent to our server", "never sent to our server" in nav)
t("the web code keeps the position on the device (localStorage) and rounds it to about a mile",
  re.search(r"localStorage\.setItem\(LK", nav) and "Math.round(pos.coords.latitude*100)/100" in nav)
ds = read("mobile", "store", "play", "data-safety.md")
t("Google Play Data safety marks location as not collected", re.search(r"Precise location \| \*\*No\*\*", ds))

# ---------- 5. employer pages never get the location ----------
nav_to = srv.get("allowNavigation") or []
other = [h for h in nav_to if not re.fullmatch(r"(\*\.)?(www\.)?uaply\.net", str(h))]
t("the apps' main web view never navigates to other sites (no allowNavigation beyond uaply.net), so only UAply's page can ask for location",
  not other, other)
assist = read(JAVA, "AssistActivity.java")
t("AssistActivity (employer and hiring-system pages) never grants geolocation",
  assist and "onGeolocationPermissionsShowPrompt" not in assist and "GeolocationPermissions" not in assist,
  "AssistActivity.java missing" if not assist else "geolocation handler found")

print("\n%d / %d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
