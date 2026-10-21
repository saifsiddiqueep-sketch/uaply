"""The one rule for taps and focus (shared/uaply-focus.css), for the pages the server builds: the 404 page, the "UAply has moved" page,
/setup, /feedback and the test inbox. Static pages carry a word-for-word copy; tools/test-focus.py checks every copy."""
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared", "uaply-focus.css")
with open(_PATH, encoding="utf-8") as _f:
    FOCUS_RULE = [ln for ln in _f.read().splitlines() if ln.startswith("html{")][0]
# a pressed button on the small standalone pages (the app has its own pressed states)
PRESSED_RULE = "button:not(:disabled):active,.btn:active{transform:translateY(1px);filter:brightness(.95)}"


def with_focus(page, pressed=False):
    """page (str or bytes) with the rule added at the end of its first <style> block (or in a new one before </head>)."""
    raw = isinstance(page, bytes)
    s = page.decode("utf-8") if raw else page
    rule = FOCUS_RULE + (PRESSED_RULE if pressed else "")
    if "</style>" in s:
        s = s.replace("</style>", rule + "</style>", 1)
    else:
        s = s.replace("</head>", "<style>" + rule + "</style></head>", 1)
    return s.encode("utf-8") if raw else s
