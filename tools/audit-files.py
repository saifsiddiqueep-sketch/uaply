"""Deep audit of every file in the repository.   python tools/audit-files.py
Checks each tracked file by type (JSON, Python, JavaScript, HTML, Markdown, YAML, XML, SVG, images), plus encoding, line endings,
secrets, old brand spellings and git hygiene. Errors fail the run; warnings are listed for a human to look at."""
import ast
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.chdir(ROOT)
errors, warnings, counts = [], [], {}


def err(f, msg):
    errors.append("%s: %s" % (f, msg))


def warn(f, msg):
    warnings.append("%s: %s" % (f, msg))


def git(*a):
    return subprocess.run(["git"] + list(a), capture_output=True, text=True, encoding="utf-8").stdout


files = [f for f in git("ls-files", "--cached", "--others", "--exclude-standard").split("\n") if f and os.path.isfile(f)]
BINARY = (".png", ".jpg", ".jpeg", ".webp", ".ico", ".pdf", ".jar", ".gif", ".ttf", ".woff", ".woff2", ".docx")


def bump(k):
    counts[k] = counts.get(k, 0) + 1


class Tags(HTMLParser):
    VOID = {"meta", "br", "img", "hr", "input", "link", "source", "area", "base", "col", "embed", "param", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack, self.bad, self.refs, self.ids = [], [], [], []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        for k in ("href", "src"):
            if d.get(k):
                self.refs.append(d[k])
        if d.get("id"):
            self.ids.append(d["id"])
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        d = dict(attrs)
        for k in ("href", "src"):
            if d.get(k):
                self.refs.append(d[k])

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:                       # a missing close tag higher up (html tolerates it, but it is a mistake)
            while self.stack and self.stack[-1] != tag:
                self.bad.append("<%s> never closed" % self.stack.pop())
            self.stack.pop()
        else:
            self.bad.append("stray </%s>" % tag)


SERVED = {os.path.basename(f) for f in files if f.startswith("shared/")} | {"prod-index.html", "articles.json"}   # serve.py serves these under short names


def link_exists(base, ref):
    ref = ref.split("#")[0].split("?")[0]
    if not ref or re.match(r"^(https?:|mailto:|tel:|data:|javascript:|//)", ref):
        return True
    if os.path.basename(ref) in SERVED:
        return True
    target = os.path.normpath(os.path.join(os.path.dirname(base), ref)) if not ref.startswith("/") else ref.lstrip("/")
    return os.path.exists(target)


SECRET_RES = [(re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "an AI provider API key"), (re.compile(r"AKIA[0-9A-Z]{16}"), "an AWS access key"),
              (re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"), "a Google client secret"), (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "a private key"),
              (re.compile(r"ghp_[A-Za-z0-9]{30,}"), "a GitHub token"), (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "a Slack token")]
OLD_BRAND = re.compile(r"\bUApply\b|\bAply\b|\buapply\b|\baply\b|(?<![uU])aply[-_.](?:api|config|partners|envs|nav|live|profile)")
BRAND_OK = ("LEGAL-REVIEW.md", "CHANGELOG.md", "tools/audit-files.py", "marketing/")        # these name the old spellings on purpose

for f in files:
    ext = os.path.splitext(f)[1].lower()
    bump(ext or "(none)")
    raw = open(f, "rb").read()
    if ext in BINARY:
        if not raw:
            err(f, "empty file")
        if ext == ".png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            err(f, "not a valid PNG")
        if len(raw) > 5_000_000:
            warn(f, "large file (%.1f MB)" % (len(raw) / 1e6))
        continue
    if b"\x00" in raw:
        err(f, "contains NUL bytes")
        continue
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        err(f, "not valid UTF-8 (%s)" % e)
        continue
    stray = re.search(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", text)
    if stray:                                             # a backspace or similar inside code is nearly always a backslash escape that got mangled on the way in
        err(f, "contains a stray control character (%r), usually a mangled backslash escape" % stray.group(0))
    if text.startswith("﻿"):
        err(f, "starts with a byte-order mark")
    if "\r\n" in text and not f.endswith((".bat", ".cmd")) and "gradlew.bat" not in f:
        warn(f, "has Windows line endings (CRLF)")
    if len(raw) > 3_000_000 and "package-lock" not in f:
        warn(f, "large file (%.1f MB)" % (len(raw) / 1e6))
    for rx, what in SECRET_RES:
        if rx.search(text):
            err(f, "looks like it contains %s" % what)
    if not f.startswith(BRAND_OK) and f not in BRAND_OK:
        for line in text.splitlines():
            m = OLD_BRAND.search(line)
            if m and "before the rename" not in line:          # a line may say it is on purpose (for example, reading old backups)
                warn(f, "uses an old spelling of the name: %s" % m.group(0))
                break
    for i, line in enumerate(text.split("\n"), 1):
        if re.search(r"\b(?:TODO|FIXME|XXX|HACK)\b", line) and f != "tools/audit-files.py":
            warn(f, "line %d: %s" % (i, line.strip()[:90]))
    try:
        if ext == ".json":
            json.loads(text)
        elif ext == ".py":
            ast.parse(text, f)
        elif ext in (".yml", ".yaml"):
            if "\t" in text:
                err(f, "contains a tab (YAML forbids tabs for indentation)")
            try:
                import yaml
                list(yaml.safe_load_all(text))
            except ImportError:
                pass
        elif ext in (".xml", ".svg", ".plist", ".storyboard", ".xcworkspacedata"):
            ET.fromstring(text.encode("utf-8"))
        elif ext == ".html":
            p = Tags()
            p.feed(text)
            if p.bad or p.stack:
                err(f, "HTML structure problems: %s" % ", ".join((p.bad + ["<%s> never closed" % t for t in p.stack])[:4]))
            dup = {i for i in p.ids if p.ids.count(i) > 1}
            if dup:
                err(f, "duplicate id(s): %s" % ", ".join(sorted(dup)[:4]))
            for r in p.refs:
                if not link_exists(f, r):
                    err(f, "broken link or file reference: %s" % r)
        elif ext == ".md":
            if text.count("```") % 2:
                err(f, "an unclosed code block (odd number of ``` fences)")
            for r in re.findall(r"\]\(([^)\s]+)\)", text):
                if not link_exists(f, r):
                    err(f, "broken link: %s" % r)
        elif ext == ".js":
            r = subprocess.run(["node", "--check", f], capture_output=True, text=True)
            if r.returncode:
                err(f, "JavaScript syntax error: %s" % (r.stderr.strip().split("\n")[0][:140]))
    except Exception as e:
        err(f, "%s: %s" % (type(e).__name__, str(e)[:140]))

# ---- git hygiene ----
tracked = set(git("ls-files").split("\n"))
for secret in ("uaply-config.json", "uaply-partners.json"):
    if secret in tracked:
        err(secret, "is committed to git, but it holds private settings")
for t in sorted(tracked):                                 # backups and scratch files named to slip past .gitignore (this happened with a ".bak" copy of the partner list)
    if re.search(r"(\.bak|\.orig|\.rej|\.swp|\.tmp|\.log|~)$", t) or os.path.basename(t).startswith(("uaply-config.json.", "uaply-partners.json.")):
        err(t, "looks like a local backup, temporary or log file and should not be committed")
for d in ("data/", "__pycache__/"):
    if any(t.startswith(d) or "/" + d in t for t in tracked):
        err(d, "files under here are committed to git")
ign = open(".gitignore", encoding="utf-8").read() if os.path.exists(".gitignore") else ""
for must in ("uaply-config.json", "uaply-partners.json", "data/", "__pycache__"):
    if must not in ign:
        err(".gitignore", "does not ignore %s" % must)
untracked = [f for f in git("ls-files", "--others", "--exclude-standard").split("\n") if f]
if untracked:
    warn("git", "%d file(s) are not committed yet: %s" % (len(untracked), ", ".join(untracked[:5])))

print("Audited %d files: %s" % (len(files), ", ".join("%s %d" % kv for kv in sorted(counts.items(), key=lambda kv: -kv[1])[:10])))
for w in warnings:
    print("  warn  " + w)
for e in errors:
    print("  ERROR " + e)
print("%d error(s), %d warning(s)" % (len(errors), len(warnings)))
sys.exit(1 if errors else 0)
