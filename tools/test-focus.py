"""The one rule for taps and focus (shared/uaply-focus.css) is in every page UAply serves, word for word. No server, no browser, a second.
  python tools/test-focus.py            check every copy
  python tools/test-focus.py --sync     after changing shared/uaply-focus.css: write the new rule into every static copy, then check
Static copies: the app (shared/uaply-nav.js), dev's and the sandbox's outer pages, the legal pages (legal/style.css), the offline and
starting-up screen, and the phone app's "can't connect" screen. Pages the server builds (404, "UAply has moved", /setup, /feedback, the test
inbox) take it from ui_rules.py and are checked as rendered. tools/ui-focus.js checks what Chrome makes of it on each page."""
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("UAPLY_CONFIG_FILE", "none")
os.environ.setdefault("UAPLY_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("UAPLY_CONFIG_JSON", json.dumps({"feeds": [], "smtp": {}}))
import ui_rules  # noqa: E402

RULE = ui_rules.FOCUS_RULE
COPIES = ["shared/uaply-nav.js", "dev/index.html", "sandbox/index.html", "legal/style.css", "shared/uaply-offline.html", "mobile/www/index.html"]
OLD = re.compile(r"html\{-webkit-tap-highlight-color:[^\n<`]*?:focus-visible\{[^}]*\}")
R = []


def t(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok or not detail else "  -> " + str(detail)))


if "--sync" in sys.argv:
    for rel in COPIES:
        p = os.path.join(ROOT, rel)
        s = open(p, encoding="utf-8", newline="").read()
        n = OLD.sub(lambda m: RULE, s)
        if n != s:
            open(p, "w", encoding="utf-8", newline="").write(n)
            print("updated", rel)

t("the rule makes taps transparent, hides the ring after a tap or click, and keeps a keyboard ring in the accent colour",
  "html{-webkit-tap-highlight-color:transparent}" in RULE and ":focus:not(:focus-visible){outline:none}" in RULE
  and re.search(r":focus-visible\{outline:3px solid var\(--accent", RULE) and "%" not in RULE, RULE)
for rel in COPIES:
    s = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    t("%s has the rule word for word" % rel, s.count(RULE) == 1 and len(OLD.findall(s)) == 1, "copies: %d exact, %d in all" % (s.count(RULE), len(OLD.findall(s))))

# pages the server builds
import uaply_api  # noqa: E402
import chat_api  # noqa: E402
import setup_api  # noqa: E402
uaply_api.init("dev")
chat_api.init("dev")
built = {"/setup": setup_api.page("127.0.0.1:8767", "http"), "/feedback": chat_api.feedback_html(), "the test inbox": uaply_api.outbox_html()}
for name, page in built.items():
    page = page.decode("utf-8") if isinstance(page, bytes) else page
    t("%s (built by the server) has the rule inside its <style>" % name, re.search(r"<style>[^<]*" + re.escape(RULE) + r"[^<]*</style>", page) is not None)
src = open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read()
t("serve.py builds the 404 page and the \"UAply has moved\" page with the rule (and a pressed state)",
  re.search(r'NOT_FOUND_PAGE = ui_rules\.with_focus\("""', src) and 'pressed=True).encode("utf-8")' in src
  and re.search(r"return ui_rules\.with_focus\(MOVED_PAGE %", src))
t("...and the pressed state reaches the page", "button:not(:disabled):active" in ui_rules.with_focus("<style></style>", pressed=True))

print("\n%d / %d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
