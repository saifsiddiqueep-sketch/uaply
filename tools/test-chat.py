"""The Help chat and the AI provider (October 22 review): with AI answers on, a message goes to the AI only when the person said Continue to
the page's one-line notice (the page sends aiOk: true, and the server checks it); without it the answer comes from the help articles and
nothing leaves UAply. No network: the AI call is stood in for here, and the key is fake.
  python tools/test-chat.py"""
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}", UAPLY_DATA_DIR=tempfile.mkdtemp(prefix="uaply-chat-"))
os.environ.pop("ANTHROPIC_API_KEY", None)
import chat_api  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


SENT = []
chat_api._sdk = lambda: object()                       # the SDK is "installed"
chat_api._ai_budget_ok = lambda limit: True
chat_api._ask_ai = lambda history, settings: (SENT.append([m["content"] for m in history]), {"answer": "From the AI.", "source_ids": []})[1]
MSG = {"messages": [{"role": "user", "content": "How do I apply to a job?"}]}

# AI answers off (no key): the help articles answer, whatever the page says
s, out = chat_api.chat(dict(MSG), "198.51.100.1")
t("AI off: the help articles answer and nothing goes out", (s, out.get("ai", False), "aiConsent" in out, len(SENT)), (200, False, False, 0))

os.environ["ANTHROPIC_API_KEY"] = "sk-ant-api03-FAKEKEYFORTESTSONLY"
s, out = chat_api.chat(dict(MSG), "198.51.100.2")
t("AI on, and the page did not say the person agreed: nothing goes to the AI", (s, len(SENT)), (200, 0))
t("...the help articles answer instead, and the answer says agreement is needed", (bool(out.get("answer")), out.get("ai", False), out.get("aiConsent")), (True, False, True))
for bad in ("yes", 1, "true", None):
    chat_api.chat(dict(MSG, aiOk=bad), "198.51.100.3")
t("...only aiOk: true counts (not 'yes', 1, 'true' or null)", len(SENT), 0)
s, out = chat_api.chat(dict(MSG, aiOk=True), "198.51.100.4")
t("after Continue (aiOk: true) the message goes to the AI and its answer comes back", (s, out.get("answer"), out.get("ai"), SENT), (200, "From the AI.", True, [["How do I apply to a job?"]]))
page = open(os.path.join(ROOT, "shared", "uaply-chat.js"), encoding="utf-8").read()
t("the page sends aiOk with every chat message, from the remembered Continue", bool(re.search(r'post\("/api/chat",\{messages:hist,aiOk:!!load\(\)\.aiOk\}\)', page)), True)

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
