"""Fill from your resume (resume_parse.py and POST /api/profile/resume): the parser on six made-up resumes, the layouts and date styles
resumes use, every file it must refuse with a plain sentence, and the endpoint on a real server.
  python tools/test-resume.py [PORT]
The six resumes are in tools/fixtures/resumes/ (written by tools/make-resume-fixtures.py) with the right answers in expected.json.
PDF cases need pypdf (pip install pypdf); without it they are skipped with a message and the rest still runs."""
import base64
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8798                # another port can be given, so two test runs never collide
FIX = os.path.join(HERE, "fixtures", "resumes")
sys.path.insert(0, ROOT)
import resume_parse as rp  # noqa: E402

HAS_PDF = rp.pdf_available()
ok = bad = 0


def t(name, got, want):
    global ok, bad
    if got == want:
        ok += 1
        print("PASS", name)
    else:
        bad += 1
        print("FAIL", name, "\n   got: ", repr(got)[:400], "\n   want:", repr(want)[:400])


def skip(name):
    print("SKIP", name, "(pypdf is not installed: pip install pypdf)")


def err_code(data, name="", ctype=""):
    try:
        rp.parse(data, name, ctype)
        return "read"
    except rp.ResumeError as e:
        return e.code


def fields_of(text):
    return rp.extract(rp.clean_text(text))


def val(f, k):
    return (f.get(k) or {}).get("value")


# ---------------------------------------------------------------------------------------------------------------------------------
print("== The six made-up resumes")
EXPECTED = json.load(open(os.path.join(FIX, "expected.json"), encoding="utf-8"))
ACCURACY = []


def same(a, b):
    return re.sub(r"\s+", " ", str(a)).strip().lower() == re.sub(r"\s+", " ", str(b)).strip().lower()


for fname, want in EXPECTED.items():
    if fname == "about":
        continue
    if fname.endswith(".pdf") and not HAS_PDF:
        skip(fname)
        continue
    res = rp.parse(open(os.path.join(FIX, fname), "rb").read(), fname)
    got = res["fields"]
    hits = 0
    for k, w in want.items():
        g = got.get(k)
        if k == "skills":
            have = [s.lower() for s in (g or {}).get("value", [])]
            missing = [s for s in w if s.lower() not in have]
            good = not missing
            t("%s: skills include %s" % (fname, ", ".join(w)), missing, [])
        elif k == "location":
            parts = {x: (g or {}).get(x, "") for x in ("city", "state", "zip")}
            good = parts == w
            t("%s: location" % fname, parts, w)
        elif k == "summary":
            good = bool(g) and g["value"].lower().startswith(w.lower()[:40])
            t("%s: summary starts %r" % (fname, w[:40]), (g or {}).get("value", "")[:40].lower(), w[:40].lower())
        else:
            options = w if isinstance(w, list) else [w]
            good = bool(g) and any(same(g["value"], o) for o in options)
            t("%s: %s = %s" % (fname, k, g and g["value"]), g["value"] if good else (g and g["value"]), g["value"] if good else options)
        if g:
            t("%s: %s says how sure it is and which line it came from" % (fname, k), (g.get("confidence") in ("high", "medium", "low"), bool(g.get("line"))), (True, True))
        hits += 1 if good else 0
    extra = sorted(k for k in got if k not in want)
    t("%s: nothing found that is not in the resume" % fname, extra, [])
    ACCURACY.append((fname, hits, len(want), extra))

# ---------------------------------------------------------------------------------------------------------------------------------
print("\n== Layouts, headings and dates")
f = fields_of("Pat Lee\npat@example.com\n\nE X P E R I E N C E\nBarista   January 2023 to Current\nRiver Cafe\n\nE D U C A T I O N\nCity College\nB.A. in History, 2022")
t("letter-spaced headings and 'January 2023 to Current'", (val(f, "job_title"), val(f, "employer"), val(f, "job_start"), val(f, "job_end"), val(f, "school")),
  ("Barista", "River Cafe", "2023-01", "present", "City College"))
for txt, start, end in (("01/2024 - 05/2025", "2024-01", "2025-05"), ("2024-01 – 2025-03", "2024-01", "2025-03"), ("Summer 2024 - Fall 2024", "2024-08", "2024-12"),
                        ("2023–2025", "2023", "2025"), ("Jan '24 – Present", "2024-01", "present"), ("Sept. 2021 — Now", "2021-09", "present"),
                        ("Mar 2020 until Jun 2021", "2020-03", "2021-06")):
    f = fields_of("Kim Diaz\nkim@example.com\n\nWork Experience\nSales Associate, Target Corporation   %s\n- helped customers" % txt)
    t("date range %r" % txt, (val(f, "job_start"), val(f, "job_end")), (start, end))
f = fields_of("Lee Wong\nlee@example.com\n\nExperience\nData Analyst\nOld Bank   2018 - 2020\n\nData Engineer\nNew Labs Inc   2021 - Present\n- pipelines")
t("the most recent job wins even when it is listed second", (val(f, "employer"), val(f, "job_title"), val(f, "job_start")), ("New Labs Inc", "Data Engineer", "2021"))
f = fields_of("Ana Silva\nana@example.com\nWORK HISTORY:\n2019 - 2022  Cashier, Corner Store\nSkills: Excel, customer service, Spanish")
t("'WORK HISTORY:' heading, dates first, skills on the heading line", (val(f, "job_title"), val(f, "employer"), val(f, "skills")),
  ("Cashier", "Corner Store", ["Excel", "Customer Service", "Spanish"]))
f = fields_of("Ana Silva\nana@example.com\nEducation 2015 - 2019 Springfield High School")
t("a date range is never read as a phone number", val(f, "phone"), None)
f = fields_of("Ravi Kumar\nravi@example.com\nMobile: +91 98765 43210\nBengaluru, India")
t("an Indian mobile number and a city outside the US", (val(f, "phone"), (f.get("location") or {}).get("city")), ("+91 98765 43210", "Bengaluru"))
f = fields_of("Ravi Kumar\nravi@example.com\nGPA: 8.9/10")
t("a GPA on a 10-point scale is not offered as a 4-point GPA", val(f, "gpa"), None)
f = fields_of("SUMMARY\nI build things.\n\nJane Q Public\njane@example.com")
t("a name below the summary is still found from the email address", val(f, "name"), "Jane Q Public")
messy = open(os.path.join(FIX, "messy.txt"), "rb").read().replace(b"\n", b"\r\n")
messy = b"\x0c\x00" + messy.replace(b"jordan.oneil", "jor​dan.oneil".encode("utf-8"), 1)
f = rp.parse(messy, "messy.txt")["fields"]
t("Windows line endings, a form feed, a NUL and a zero-width space are stripped", (val(f, "email"), val(f, "name")), ("jordan.oneil.reyes@example.com", "Jordan O'Neil-Reyes"))
t("the text keeps no control characters", re.search(r"[\x00-\x08\x0b-\x1f\x7f​]", rp.parse(messy, "messy.txt")["text"]), None)
t("a UTF-16 text file is read", val(rp.parse(open(os.path.join(FIX, "student.txt"), encoding="utf-8").read().encode("utf-16"), "cv.txt")["fields"], "email"), "maya.patel@example.edu")
t("a Windows-1252 text file is read", val(rp.parse("José Núñez\njose@example.com\nSkills: Excel, SQL".encode("cp1252"), "cv.txt")["fields"], "name"), "José Núñez")


def docx_bytes(document_xml, extra=None):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", document_xml)
        for k, v in (extra or {}).items():
            z.writestr(k, v)
    return b.getvalue()


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
P = lambda s: "<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % s  # noqa: E731
table = ('<w:document %s><w:body><w:tbl><w:tr><w:tc>%s%s%s</w:tc><w:tc>%s%s%s%s</w:tc></w:tr></w:tbl></w:body></w:document>'
         % (W, P("SKILLS"), P("Python"), P("SQL"), P("EXPERIENCE"), P("Analyst"), P("Acme Corp"), P("Jan 2022 - Present")))
header = '<w:hdr %s>%s%s</w:hdr>' % (W, P("Morgan Blake"), P("morgan.blake@example.com"))
f = rp.parse(docx_bytes(table, {"word/header1.xml": header}), "cv.docx")["fields"]
t("Word: the name in the page header, a two-column table, cells in order", (val(f, "name"), val(f, "email"), val(f, "skills"), val(f, "employer"), val(f, "job_start")),
  ("Morgan Blake", "morgan.blake@example.com", ["Python", "SQL"], "Acme Corp", "2022-01"))
box = ('<w:document %s><w:body><w:p><w:r><w:t>Before </w:t></w:r><w:r><w:pict><w:txbxContent>%s</w:txbxContent></w:pict></w:r></w:p>%s</w:body></w:document>'
       % (W, P("Riley Chen"), P("riley@example.com")))
t("Word: a text box gives its own line", [x.strip() for x in rp.parse(docx_bytes(box), "cv.docx")["text"].split("\n")[:2]], ["Before", "Riley Chen"])

print("\n== Files it refuses, each with a plain sentence")
t("over 5 MB", err_code(b"a" * (5 * 1024 * 1024 + 1), "cv.txt"), "too_big")
t("empty", err_code(b"   \n ", "cv.txt"), "empty")
t("a photo of a resume (PNG)", err_code(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "cv.png"), "image")
t("a photo named .pdf (JPEG inside)", err_code(b"\xff\xd8\xff\xe0" + b"\x00" * 100, "cv.pdf"), "image")
t("an old Word file (.doc)", err_code(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100, "cv.doc"), "old_doc")
xb = io.BytesIO()
with zipfile.ZipFile(xb, "w") as z:
    z.writestr("xl/workbook.xml", "<workbook/>")
t("an Excel file (a zip without word/document.xml)", err_code(xb.getvalue(), "cv.xlsx"), "wrong_type")
t("a program (.exe)", err_code(b"MZ\x90\x00" + b"\x00" * 100, "cv.exe"), "wrong_type")
t("a binary file named .txt", err_code(b"\x00\x01\x02" * 200, "cv.txt"), "unreadable")
t("a Word file with an entity trick (billion laughs) is refused, never expanded",
  err_code(docx_bytes('<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><w:document %s><w:body>%s</w:body></w:document>' % (W, P("&b;"))), "cv.docx"), "unreadable")
t("a Word file whose text unpacks to over 20 MB (a zip bomb) is refused", err_code(docx_bytes("<a>" + " " * (21 * 1024 * 1024) + "</a>"), "cv.docx"), "unreadable")
t("a broken zip named .docx", err_code(b"PK\x03\x04garbage" * 10, "cv.docx"), "unreadable")
for k in ("too_big", "image", "scanned", "unreadable", "old_doc", "wrong_type", "encrypted", "no_pdf"):
    m = rp.MESSAGES[k]
    t("the %s message speaks to the person in plain words" % k, (m.endswith("."), "pypdf" not in m.lower(), "error" not in m.lower(), len(m) < 200), (True, True, True, True))

if HAS_PDF:
    def blank_pdf(content=b"0 0 m 100 100 l S"):
        objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
                b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"]
        out = bytearray(b"%PDF-1.4\n")
        offs = []
        for n, o in enumerate(objs, 1):
            offs.append(len(out))
            out += b"%d 0 obj\n" % n + o + b"\nendobj\n"
        x = len(out)
        out += b"xref\n0 5\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offs) + b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % x
        return bytes(out)
    t("a scanned PDF (pages with no text)", err_code(blank_pdf(), "scan.pdf"), "scanned")
    t("a broken PDF", err_code(b"%PDF-1.4\n" + b"garbage " * 50, "cv.pdf"), "unreadable")
    import pypdf
    w = pypdf.PdfWriter()
    w.append(pypdf.PdfReader(os.path.join(FIX, "datesfirst.pdf")))
    w.encrypt("secret")
    b = io.BytesIO()
    w.write(b)
    t("a password-protected PDF", err_code(b.getvalue(), "locked.pdf"), "encrypted")
    t("a PDF renamed .txt is still read as a PDF", val(rp.parse(open(os.path.join(FIX, "twocolumn.pdf"), "rb").read(), "cv.txt")["fields"], "name"), "Sam Okafor")
else:
    skip("scanned, broken and password-protected PDFs")
real = rp.pdf_available
rp.pdf_available = lambda: False
t("without pypdf a PDF gets a plain 'use Word or text for now' (503), and Word still works",
  (rp.handle(json.dumps({"resume": {"name": "a.pdf", "data": "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4 hello").decode()}}).encode(), "application/json")[0],
   rp.handle(json.dumps({"resume": {"name": "a.docx", "data": "data:x;base64," + base64.b64encode(open(os.path.join(FIX, "newgrad.docx"), "rb").read()).decode()}}).encode(), "application/json")[0]),
  (503, 200))
rp.pdf_available = real

print("\n== The request shapes (resume_parse.handle)")
student = open(os.path.join(FIX, "student.txt"), "rb").read()
js = json.dumps({"resume": {"name": "student.txt", "data": "data:text/plain;base64," + base64.b64encode(student).decode()}}).encode()
code, out = rp.handle(js, "application/json")
t("JSON with a data: URL (the shape the app already sends with an application)", (code, out["ok"], val(out["fields"], "email")), (200, True, "maya.patel@example.edu"))
t("the answer never carries the resume's text or the file", ("text" in out, "data" in json.dumps(out).lower() and student[:40].decode() in json.dumps(out)), (False, False))
bnd = "----uaplytest"
mp = ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"student.txt\"\r\nContent-Type: text/plain\r\n\r\n" % bnd).encode() + student + ("\r\n--%s--\r\n" % bnd).encode()
code, out = rp.handle(mp, "multipart/form-data; boundary=" + bnd)
t("a multipart form with the field 'file'", (code, val(out.get("fields", {}), "name")), (200, "Maya Patel"))
t("not JSON", rp.handle(b"{nope", "application/json")[1].get("code"), "bad_request")
t("no resume in the JSON", rp.handle(b'{"x":1}', "application/json")[1].get("code"), "bad_request")
t("data that is not base64", rp.handle(b'{"resume":{"name":"a.txt","data":"data:text/plain;base64,@@@"}}', "application/json")[1].get("code"), "bad_request")
t("a multipart form without a file", rp.handle(("--%s\r\nContent-Disposition: form-data; name=\"x\"\r\n\r\n1\r\n--%s--\r\n" % (bnd, bnd)).encode(), "multipart/form-data; boundary=" + bnd)[1].get("code"), "bad_request")

# ---------------------------------------------------------------------------------------------------------------------------------
print("\n== The endpoint on a real server (POST /api/profile/resume)")
tmp = tempfile.mkdtemp(prefix="uaply-resume-")
logf = open(os.path.join(tmp, "server.log"), "w+")
env = dict(os.environ, UAPLY_DATA_DIR=os.path.join(tmp, "data"), UAPLY_CONFIG_FILE="none",
           UAPLY_CONFIG_JSON=json.dumps({"feeds": [], "delivery": "test", "smtp": {}, "owner_copy": ""}))
env.pop("HOST", None)
proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(PORT), os.path.join(ROOT, "sandbox"), "--api"], env=env, stdout=logf, stderr=logf)
BASE = "http://127.0.0.1:%d" % PORT


def call(body, ctype="application/json", origin=True, path="/api/profile/resume"):
    h = {"Content-Type": ctype}
    if origin:
        h["Origin"] = BASE
    req = urllib.request.Request(BASE + path, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


try:
    for _ in range(80):
        try:
            urllib.request.urlopen(BASE + "/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    code, out = call(js)
    t("a text resume: 200 and its fields", (code, out.get("found", 0) >= 12, val(out.get("fields", {}), "school")), (200, True, "Temple University"))
    code, out = call(mp, "multipart/form-data; boundary=" + bnd)
    t("the same as a multipart form", (code, val(out.get("fields", {}), "gpa")), (200, "3.72"))
    newgrad = open(os.path.join(FIX, "newgrad.docx"), "rb").read()
    code, out = call(json.dumps({"resume": {"name": "newgrad.docx", "data": "data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64," + base64.b64encode(newgrad).decode()}}).encode())
    t("a Word resume", (code, val(out.get("fields", {}), "employer")), (200, "Harborview Community Foundation"))
    if HAS_PDF:
        two = open(os.path.join(FIX, "twocolumn.pdf"), "rb").read()
        code, out = call(json.dumps({"resume": {"name": "twocolumn.pdf", "data": "data:application/pdf;base64," + base64.b64encode(two).decode()}}).encode())
        t("a two-column PDF resume", (code, val(out.get("fields", {}), "name"), val(out.get("fields", {}), "job_title")), (200, "Sam Okafor", "Senior Software Engineer"))
        code, out = call(json.dumps({"resume": {"name": "scan.pdf", "data": "data:application/pdf;base64," + base64.b64encode(blank_pdf()).decode()}}).encode())
        t("a scanned PDF: 422 and the scanned-picture sentence", (code, out.get("code"), out.get("error")), (422, "scanned", rp.MESSAGES["scanned"]))
    else:
        skip("PDFs through the endpoint")
    code, out = call(json.dumps({"resume": {"name": "cv.png", "data": "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50).decode()}}).encode())
    t("a picture: 422 with a plain sentence", (code, out.get("code")), (422, "image"))
    big = b"a" * (5 * 1024 * 1024 + 10)
    code, out = call(json.dumps({"resume": {"name": "big.txt", "data": "data:text/plain;base64," + base64.b64encode(big).decode()}}).encode())
    t("a file over 5 MB: 413 'over 5 MB'", (code, out.get("code")), (413, "too_big"))
    code, out = call(js, origin=False)
    t("a request from another site is refused", code, 403)
    code, out = call(b"", "application/json")
    t("an empty request: 400", code, 400)
    try:
        with urllib.request.urlopen(BASE + "/uaply-resume.js", timeout=5) as r:
            js_file = (r.status, b"UAplyResume" in r.read())
    except urllib.error.HTTPError as e:
        js_file = (e.code, False)
    t("the page can load shared/uaply-resume.js", js_file, (200, True))
    # nothing kept: no file under the data folder mentions the resume, and the log has only counts
    kept = []
    for d, _, files in os.walk(os.path.join(tmp, "data")):
        for fn in files:
            try:
                if b"maya.patel" in open(os.path.join(d, fn), "rb").read() or b"Okafor" in open(os.path.join(d, fn), "rb").read():
                    kept.append(fn)
            except OSError:
                pass
    t("nothing from a resume is written to the server's disk", kept, [])
    codes = [call(js)[0] for _ in range(14)]
    t("more than 12 resumes a minute from one address: 429 with a plain sentence", 429 in codes, True)
    logf.flush()
    logf.seek(0)
    log = logf.read()
    t("the server log says only how many resumes were read", ("resume read #" in log, "maya" in log.lower(), "Temple" in log, "okafor" in log.lower()), (True, False, False, False))
finally:
    proc.terminate()
    try:
        proc.wait(5)
    except Exception:
        proc.kill()

print("\n== Wiring")
sb = open(os.path.join(ROOT, "sandbox", "index.html"), encoding="utf-8").read()
dv = open(os.path.join(ROOT, "dev", "index.html"), encoding="utf-8").read()
envs = open(os.path.join(ROOT, "shared", "uaply-envs.js"), encoding="utf-8").read()
t("the sandbox loads uaply-resume.js and switches Fill from your resume on", ('<script src="uaply-resume.js"></script>' in sb, bool(re.search(r"var on=\{[^}]*resume:true", sb))), (True, True))
t("dev does not have it yet (sandbox first)", ("uaply-resume.js" in dv, '"resume"' in (re.search(r"var PROMOTED=\[[^\]]*\]", dv) or [""])[0]), (False, False))
t("uaply-envs.js lists the resume experiment", ("FEATURES.resume=" in envs and '"resume"' in envs), True)
req = open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8").read()
t("requirements.txt asks for pypdf (Render installs it)", bool(re.search(r"^pypdf\b", req, re.M)), True)

print("\n== Accuracy per resume (fields found / fields in the resume)")
for fname, hits, total, extra in ACCURACY:
    print("  %-18s %2d / %2d%s" % (fname, hits, total, ("   extra: " + ", ".join(extra)) if extra else ""))
if not HAS_PDF:
    print("  (the two PDF resumes were skipped: pip install pypdf)")
print("\n%d / %d" % (ok, ok + bad))
sys.exit(1 if bad else 0)
