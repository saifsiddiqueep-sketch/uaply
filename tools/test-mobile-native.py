"""The phone apps' native settings for testers (mobile/): portrait iPhone, the privacy manifest, Android backup, the Back and export plugins.
No network, under a second.
  python tools/test-mobile-native.py
1. iPhone (Info.plist): portrait only. The layout was never checked in landscape inside the app (notch and home-bar insets),
   so the app does not turn. The iPad list does not matter while the app is iPhone-only (TARGETED_DEVICE_FAMILY = 1).
2. iPhone privacy manifest (PrivacyInfo.xcprivacy): no tracking, the two required-reason APIs with their reasons (file timestamps
   C617.1, user defaults CA92.1), collected data types that match the Google Play Data safety answers, and the file is part of
   the App target's resources in project.pbxproj (a file only on disk is not put into the app).
3. Android (AndroidManifest.xml): allowBackup is off, so Android's automatic backup does not copy the profile and applications
   kept in the web view to the person's Google account.
4. The plugins the web code needs for Back (@capacitor/app) and the export buttons (@capacitor/filesystem, @capacitor/share)
   are in mobile/package.json, the lock file, both Android build files and the Podfile, and shared/uaply-nav.js calls them."""
import json
import os
import plistlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOB = os.path.join(ROOT, "mobile")
A = "{http://schemas.android.com/apk/res/android}"
R = []


def t(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok or not detail else "  -> " + str(detail)))


def read(*rel):
    try:
        with open(os.path.join(ROOT, *rel), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def plist(*rel):
    try:
        with open(os.path.join(ROOT, *rel), "rb") as f:
            return plistlib.load(f)
    except Exception as e:  # noqa: BLE001  (a missing or broken file is a failed check, not a crash)
        t("/".join(rel) + " parses", False, e)
        return {}


# ---------- 1. portrait iPhone ----------
info = plist("mobile", "ios", "App", "App", "Info.plist")
t("iPhone: portrait only (UISupportedInterfaceOrientations)", info.get("UISupportedInterfaceOrientations") == ["UIInterfaceOrientationPortrait"],
  info.get("UISupportedInterfaceOrientations"))
pbx = read("mobile", "ios", "App", "App.xcodeproj", "project.pbxproj")
fam = set(re.findall(r"TARGETED_DEVICE_FAMILY = ([^;]+);", pbx))
t("the app is iPhone-only, so the iPad orientation list is not used", fam == {"1"}, fam)

# ---------- 2. privacy manifest ----------
pm = plist("mobile", "ios", "App", "App", "PrivacyInfo.xcprivacy")
t("privacy manifest: no tracking and no tracking domains", pm.get("NSPrivacyTracking") is False and pm.get("NSPrivacyTrackingDomains") == [])
apis = {a.get("NSPrivacyAccessedAPIType"): a.get("NSPrivacyAccessedAPITypeReasons") for a in pm.get("NSPrivacyAccessedAPITypes", [])}
t("privacy manifest: file timestamps with reason C617.1", apis.get("NSPrivacyAccessedAPICategoryFileTimestamp") == ["C617.1"], apis)
t("privacy manifest: user defaults with reason CA92.1", apis.get("NSPrivacyAccessedAPICategoryUserDefaults") == ["CA92.1"], apis)
kinds = {c.get("NSPrivacyCollectedDataType"): c for c in pm.get("NSPrivacyCollectedDataTypes", [])}
need = ["Name", "EmailAddress", "PhoneNumber", "PhysicalAddress", "UserID", "OtherUserContent", "CustomerSupport", "ProductInteraction", "DeviceID"]
t("privacy manifest: the data types the Play Data safety form marks as collected", all("NSPrivacyCollectedDataType" + k in kinds for k in need),
  sorted(set("NSPrivacyCollectedDataType" + k for k in need) - set(kinds)))
never = ["PreciseLocation", "CoarseLocation", "RacialOrEthnicData", "CreditCardNumber", "AdvertisingData"]
t("privacy manifest: never location, self-identification, card numbers or advertising data (they stay on the phone or never reach UAply)",
  not [k for k in never if "NSPrivacyCollectedDataType" + k in kinds])
t("privacy manifest: nothing is used for tracking", all(c.get("NSPrivacyCollectedDataTypeTracking") is False for c in kinds.values()))
ds = read("mobile", "store", "play", "data-safety.md")
t("...and Play still says location and race/ethnicity are not collected", re.search(r"Precise location \| \*\*No\*\*", ds) and re.search(r"Race and ethnicity \| \*\*No\*\*", ds))
ref = re.search(r"(\w{24}) /\* PrivacyInfo\.xcprivacy \*/ = \{isa = PBXFileReference;[^}]*path = PrivacyInfo\.xcprivacy;", pbx)
build = ref and re.search(r"(\w{24}) /\* PrivacyInfo\.xcprivacy in Resources \*/ = \{isa = PBXBuildFile; fileRef = " + ref.group(1), pbx)
res = re.search(r"/\* Resources \*/ = \{\s*isa = PBXResourcesBuildPhase;[^}]*?files = \(([^)]*)\)", pbx)
group = re.search(r"/\* App \*/ = \{\s*isa = PBXGroup;\s*children = \(([^)]*)\)", pbx)
t("the privacy manifest is in the App group and copied into the app (Resources build phase)",
  build and res and build.group(1) in res.group(1) and group and ref.group(1) in group.group(1))
ids = re.findall(r"^\t\t(\w{24}) ", pbx, re.M)
t("project.pbxproj: no object id used twice", len(ids) == len(set(ids)))

# ---------- 3. Android backup ----------
try:
    app = ET.parse(os.path.join(MOB, "android", "app", "src", "main", "AndroidManifest.xml")).getroot().find("application")
except Exception as e:  # noqa: BLE001
    app = None
    t("AndroidManifest.xml parses", False, e)
t("Android: allowBackup is off (the profile and applications in the web view stay out of automatic Google backup)",
  app is not None and app.get(A + "allowBackup") == "false", app is not None and app.get(A + "allowBackup"))

# ---------- 4. plugins ----------
pkg = json.loads(read("mobile", "package.json") or "{}").get("dependencies", {})
lock = json.loads(read("mobile", "package-lock.json") or "{}").get("packages", {})
gradle = read("mobile", "android", "capacitor.settings.gradle")
build_g = read("mobile", "android", "app", "capacitor.build.gradle")
pod = read("mobile", "ios", "App", "Podfile")
for name, k in (("App", "app"), ("Filesystem", "filesystem"), ("Share", "share")):
    t("plugin @capacitor/%s: package.json, lock file, Android settings and build, Podfile" % k,
      ("@capacitor/" + k) in pkg and ("node_modules/@capacitor/" + k) in lock and "':capacitor-%s'" % k in gradle
      and "project(':capacitor-%s')" % k in build_g and "pod 'Capacitor%s'" % name in pod)
    v = pkg.get("@capacitor/" + k, "")
    t("...@capacitor/%s is on Capacitor 7 like the rest (%s)" % (k, v), v.startswith("^7."))
nav = read("shared", "uaply-nav.js")
t("the web code listens for the Back button and can leave the app", 'plug("App")' in nav and 'addListener("backButton"' in nav and "exitApp" in nav)
t("the export buttons write to the app's cache folder and open the share sheet", 'plug("Filesystem")' in nav and 'directory:"CACHE"' in nav and "files:[r.uri]" in nav)
t("plugin calls go to the top page's bridge first (Android answers the main frame only; the app's frame has a bridge that never answers)",
  "if(w.parent&&w.parent!==w)c=w.parent.Capacitor||null" in nav and "c=c||w.Capacitor" in nav)
t("Delete all my data also deletes the export files from the app's cache folder",
  'FS.deleteFile({path:p,directory:"CACHE"})' in nav and 'del("uaply-backup.json"),del("uaply-applications.csv")' in nav and "/^interview-" in nav)
t("without the plugin the words say Copied, never Saved", "Copied \"+name+\". Paste it into a note or email to keep it." in nav and not re.search(r"Saved \"\+name", nav))

print("\n%d / %d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
