"""Fill from your resume (resume_parse.py and POST /api/profile/resume): the parser on forty-two made-up resumes, the layouts and date styles
resumes use, every file it must refuse with a plain sentence, and the endpoint on a real server.
  python tools/test-resume.py [PORT]
The forty-two resumes are in tools/fixtures/resumes/ (written by tools/make-resume-fixtures.py) with the right answers in expected.json.
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

try:                                                                   # resume names can be any language; a Windows pipe is cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

HERE =os.path.dirname(os.path.abspath(__file__))
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
print("== The forty-two made-up resumes")
EXPECTED = json.load(open(os.path.join(FIX, "expected.json"), encoding="utf-8"))
ACCURACY = []


def same(a, b):
    return re.sub(r"\s+", " ", str(a)).strip().lower() == re.sub(r"\s+", " ", str(b)).strip().lower()


WRONG, GOOD, TABLE, FIELDS = [], {}, [], {}        # answers that are not right, which expected answers were right, each resume for the table


def squash(s):
    """Lower case letters and digits only (accents kept): 'PRIYA RAMAN' and 'Priya Raman' read the same."""
    return re.sub(r"[\W_]+", "", str(s).lower())


def traceable(k, field, text):
    """True when the answer is written in the resume: the same words, or the same digits for a phone, or a date written there."""
    v, flat, digits = field.get("value"), squash(text), re.sub(r"\D", "", text)
    if k == "phone":
        return re.sub(r"\D", "", v) in digits
    if k in ("job_start", "job_end", "grad"):
        if v == "present":
            return bool(re.search(rp._NOW, text, re.I))
        written = {rp._fmt(d) for d in (rp._ym(m.group(0)) for m in re.finditer(rp._ONE, text, re.I)) if d and d != "present"}
        return v in written
    if k == "location":
        return (squash(field.get("city", "")) in flat and (not field.get("zip") or field["zip"] in digits) and
                (not field.get("state") or re.search(r"\b%s\b" % re.escape(field["state"]), text) is not None or
                 squash(next((n for n, c in rp._STATE_BY_NAME.items() if c == field["state"]), "")) in flat))
    if k == "skills":
        return all(squash(s) in flat for s in v)
    if k in ("linkedin", "portfolio"):
        return squash(re.sub(r"^https?://(www\.)?", "", v)) in flat
    return squash(v) in flat


for fname, want in EXPECTED.items():
    if fname == "about":
        continue
    if fname.endswith(".pdf") and not HAS_PDF:
        skip(fname)
        continue
    res = rp.parse(open(os.path.join(FIX, fname), "rb").read(), fname)
    got = res["fields"]
    hits = 0
    may_blank = set(want.get("blank_ok", []))       # on the page, but fine to leave empty; if found it must be right
    for k, w in want.items():
        if k == "blank_ok":
            continue
        g = got.get(k)
        if g is None and k in may_blank:
            FIELDS.setdefault(k, {"right": 0, "blank": 0, "wrong": 0})["blank"] += 1
            GOOD[(fname, k)] = False
            continue
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
        if g and not good:
            WRONG.append((fname, k, g.get("confidence")))
        hits += 1 if good else 0
        GOOD[(fname, k)] = good
        FIELDS.setdefault(k, {"right": 0, "blank": 0, "wrong": 0})["right" if good else "blank" if g is None else "wrong"] += 1
    extra = sorted(k for k in got if k not in want)
    for k in extra:
        FIELDS.setdefault(k, {"right": 0, "blank": 0, "wrong": 0})["wrong"] += 1
    t("%s: nothing found that is not in the resume" % fname, extra, [])
    WRONG.extend((fname, k, got[k].get("confidence")) for k in extra)
    ACCURACY.append((fname, hits, len([k for k in want if k != "blank_ok"]), extra))
    # only what is on the resume (card 181): every answer can be found in the resume's own text, as written or trivially reformatted
    untraced = [(k, got[k]["value"]) for k in got if not traceable(k, got[k], res["text"])]
    t("%s: every answer is in the resume's own words (nothing guessed, inferred or padded)" % fname, untraced, [])
    t("%s: no answer is confidently wrong (a wrong one must be marked low)" % fname, [(k, c) for f_, k, c in WRONG if f_ == fname and c != "low"], [])
    TABLE.append((fname, want, got))

NZ = open(os.path.join(FIX, "nunez.txt"), encoding="utf-8").read()
t("the own-words check itself catches a made-up month, a guessed city, a skill from a title and a padded phone",
  [traceable(k, f_, NZ) for k, f_ in (("grad", {"value": "2019-05"}), ("location", {"city": "Hialeah", "state": "FL", "zip": "33130"}),
                                        ("skills", {"value": ["Food Safety", "Grilling"]}), ("phone", {"value": "+1 (305) 555-0199"}),
                                        ("grad", {"value": "2019"}), ("phone", {"value": "305-555-0119"}))],
  [False, False, False, False, True, True])
t("sparse.txt (a name and an email only): everything else comes back empty",
  sorted(rp.parse(open(os.path.join(FIX, "sparse.txt"), "rb").read(), "sparse.txt")["fields"]), ["email", "name"])

# ---------------------------------------------------------------------------------------------------------------------------------
print("\n== Layouts, headings and dates")
f = fields_of("Pat Lee\npat@example.com\n\nE X P E R I E N C E\nBarista   January 2023 to Current\nRiver Cafe\n\nE D U C A T I O N\nCity College\nB.A. in History, 2022")
t("letter-spaced headings and 'January 2023 to Current'", (val(f, "job_title"), val(f, "employer"), val(f, "job_start"), val(f, "job_end"), val(f, "school")),
  ("Barista", "River Cafe", "2023-01", "present", "City College"))
for txt, start, end in (("01/2024 - 05/2025", "2024-01", "2025-05"), ("2024-01 – 2025-03", "2024-01", "2025-03"), ("Summer 2024 - Fall 2024", "2024", "2024"),
                        ("2023–2025", "2023", "2025"), ("Jan '24 – Present", "2024-01", "present"), ("Sept. 2021 — Now", "2021-09", "present"),
                        ("Mar 2020 until Jun 2021", "2020-03", "2021-06")):
    f = fields_of("Kim Diaz\nkim@example.com\n\nWork Experience\nSales Associate, Target Corporation   %s\n- helped customers" % txt)
    t("date range %r" % txt, (val(f, "job_start"), val(f, "job_end")), (start, end))
f = fields_of("Lee Wong\nlee@example.com\n\nExperience\nData Analyst\nOld Bank   2018 - 2020\n\nData Engineer\nNew Labs Inc   2021 - Present\n- pipelines")
t("the most recent job wins even when it is listed second", (val(f, "employer"), val(f, "job_title"), val(f, "job_start")), ("New Labs Inc", "Data Engineer", "2021"))
f = fields_of("Jo Park\njo@example.edu\n\nExperience\nCashier, Corner Store   2023 - Present\n\nLeadership & Activities\nPresident, Finance Club   2024 - Present\n- ran meetings")
t("a club office under 'Leadership & Activities' is not the most recent job", (val(f, "job_title"), val(f, "employer"), val(f, "job_start")), ("Cashier", "Corner Store", "2023"))
f = fields_of("Jo Park\njo@example.edu\n\nSkills\nMicrosoft Excel (pivot tables, VLOOKUP), SQL (basic), Canva")
t("a note in brackets after a skill is not split into skills of its own", [s for s in val(f, "skills") if s in ("Excel", "SQL", "Canva") or "(" in s or ")" in s], ["Excel", "SQL", "Canva"])
f = fields_of("Jo Park\njo@example.edu\n\nExperience\nBarista (part-time)   Sep 2023 - Present\nRiver Cafe")
t("a job title keeps its own bracket: 'Barista (part-time)'", val(f, "job_title"), "Barista (part-time)")
f = fields_of("Ana Silva\nana@example.com\nWORK HISTORY:\n2019 - 2022  Cashier, Corner Store\nSkills: Excel, customer service, Spanish")
t("'WORK HISTORY:' heading, dates first, skills on the heading line", (val(f, "job_title"), val(f, "employer"), val(f, "skills")),
  ("Cashier", "Corner Store", ["Excel", "Customer Service", "Spanish"]))
f = fields_of("Ana Silva\nana@example.com\nEducation 2015 - 2019 Springfield High School")
t("a date range is never read as a phone number", val(f, "phone"), None)
f = fields_of("Ravi Kumar\nravi@example.com\nMobile: +91 98765 43210\nBengaluru, India")
t("an Indian mobile number and a city outside the US", (val(f, "phone"), (f.get("location") or {}).get("city")), ("+91 98765 43210", "Bengaluru"))
f = fields_of("Ana Silva\nana@example.com\n\nEducation\nTemple University\nCoursework in MS Office and Excel")
t("'MS Office' under Education is not an M.S. degree: no major", val(f, "major"), None)
f = fields_of("Ana Silva\nana@example.com\n\nEducation\nTemple University\nMS Excel and Word, 2019")
t("'MS Excel' under Education is not an M.S. degree: no major", val(f, "major"), None)
f = fields_of("Ana Silva\nana@example.com\n\nEducation\nTemple University\nBS Computer Science, 2020")
t("'BS Computer Science' (no 'in') gives the major 'Computer Science'", val(f, "major"), "Computer Science")
f = fields_of("Ana Silva\nana@example.com\n\nEducation\nTemple University\nAssociate Professor of Biology assistant 2020")
t("a job title under Education ('Associate Professor of ...') is not an Associate degree: no major", val(f, "major"), None)
f = fields_of("Ana Silva\nana@example.com\n\nExperience\nCashier, Corner Store   2023 - Present\n\nContact\nReferences: Bob Lee, Dallas, TX 75201")
t("a reference's city under Contact is not where the person lives", f.get("location"), None)
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
t("an empty file (0 bytes) named .pdf", err_code(b"", "cv.pdf"), "empty")
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

    def image_pdf():
        """A scanned resume as most scanners write it: one page that is only a picture (an image XObject), no text at all."""
        px = b"\xff\x00\x00" * 4
        objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im1 5 0 R >> >> /Contents 4 0 R >>"]
        draw = b"q 612 0 0 792 0 0 cm /Im1 Do Q"
        objs.append(b"<< /Length %d >>\nstream\n" % len(draw) + draw + b"\nendstream")
        objs.append(b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Length %d >>\nstream\n" % len(px)
                    + px + b"\nendstream")
        out = bytearray(b"%PDF-1.4\n")
        offs = []
        for n, o in enumerate(objs, 1):
            offs.append(len(out))
            out += b"%d 0 obj\n" % n + o + b"\nendobj\n"
        x = len(out)
        out += (b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offs) +
                b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % x)
        return bytes(out)
    t("a scanned PDF that is only a picture (an image, no text)", err_code(image_pdf(), "scan.pdf"), "scanned")
    t("a broken PDF", err_code(b"%PDF-1.4\n" + b"garbage " * 50, "cv.pdf"), "unreadable")
    import pypdf
    w = pypdf.PdfWriter()
    w.append(pypdf.PdfReader(os.path.join(FIX, "datesfirst.pdf")))
    w.encrypt("secret")
    b = io.BytesIO()
    w.write(b)
    LOCKED = b.getvalue()
    t("a password-protected PDF", err_code(LOCKED, "locked.pdf"), "encrypted")
    biz = rp.read_text(open(os.path.join(FIX, "business.pdf"), "rb").read(), "business.pdf")[1]
    t("a PDF's bullets and accents arrive whole, whatever the computer's code page (no replacement characters)",
      ("�" in biz, "Jordan Álvarez" in biz, "• Ran weekly" in biz), (False, True, True))
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

print("\n== Card 181 fixes: each wrong answer once found, now right or blank")
footer = '<w:ftr %s>%s</w:ftr>' % (W, P("Charlotte, NC 28202 | 704-555-0163"))
f = rp.parse(docx_bytes('<w:document %s><w:body>%s%s</w:body></w:document>' % (W, P("Kwame Mensah"), P("kwame@example.com")),
                        {"word/footer1.xml": footer}), "cv.docx")["fields"]
t("Word: the phone and city in the page footer are read", (val(f, "phone"), (f.get("location") or {}).get("city")), ("704-555-0163", "Charlotte"))
f = fields_of("Kwame Mensah\nkwame@example.com\n\nExperience\nRegistered Nurse, Emergency Department\nQueen City Example Hospital\n"
              "Jan 2021 - Present\n")
t("the employer is the line of its own, not the rest of the title's line", (val(f, "job_title"), val(f, "employer")),
  ("Registered Nurse", "Queen City Example Hospital"))
f = fields_of("Grace Oduya\ngrace@example.com\n\nExperience\nCareer Break (family caregiving)\nMar 2023 - Present\n"
              "Office Manager, Example Dental Group\nJun 2017 - Feb 2023\n")
t("a career break is not the latest job", (val(f, "job_title"), val(f, "employer"), val(f, "job_end")), ("Office Manager", "Example Dental Group", "2023-02"))
f = fields_of("Carlos Mendoza\ncarlos@example.com\n\nExperience\nWarehouse Lead, Example Valley Foods\nJun ’22 - Present\n")
t("a year written with a curly apostrophe (’22)", (val(f, "job_title"), val(f, "job_start")), ("Warehouse Lead", "2022-06"))
f = fields_of("Noah Ruiz\nnoah@example.com\n\nExperience\nSite Reliability Engineer — Example Transit Data Inc.\nFeb 2023 – Present\n")
t("a header ending in 'Inc.' is not a sentence", (val(f, "job_title"), val(f, "employer")), ("Site Reliability Engineer", "Example Transit Data Inc"))
f = fields_of("DeShawn Carter\nRecruiter\n\nExperience\nExample Robotics\nRecruiter\nMarch 2022 - Present (2 years 8 months)\n")
t("a LinkedIn duration '(2 years 8 months)' is not part of the job", (val(f, "job_title"), val(f, "employer")), ("Recruiter", "Example Robotics"))
f = fields_of("Michael Torres\nmike@example.com\n\nMILITARY EXPERIENCE\nSupply Sergeant, U.S. Army        JAN 2016 – DEC 2023\n\n"
              "CIVILIAN EXPERIENCE\nWarehouse Associate, Example Distribution LLC        FEB 2024 – PRESENT\n\nSECURITY CLEARANCE\nSecret\n")
t("Military and Civilian Experience are jobs; Security Clearance is not a skill", (val(f, "job_title"), val(f, "skills")), ("Warehouse Associate", None))
f = fields_of("Thomas Clarke\nManchester, United Kingdom | thomas@example.co.uk\n\nSkills\nSolidWorks, MATLAB\nReferences available on request\n")
t("a city and country is not a headline; 'References available on request' is not a skill", (val(f, "headline"), val(f, "skills")), (None, ["SolidWorks", "MATLAB"]))
f = fields_of("Ananya Krishnan\nananya@example.in\n\nEducational Qualifications\nB.Tech in Computer Science and Engineering, Example Institute, 2020\n\n"
              "Declaration\nI hereby declare that the above is true.\n")
t("'B.Tech' is not a website; Educational Qualifications is education; Declaration is not a skill",
  (val(f, "portfolio"), val(f, "major"), val(f, "grad"), val(f, "skills")), (None, "Computer Science and Engineering", "2020", None))
f = fields_of("Grace Oduya\ngrace@example.com\n\nEducation\nExample College — Associate of Arts, 2014\n")
t("'Associate of Arts' gives no major (Arts is the degree's name)", val(f, "major"), None)
f = fields_of("Danielle Okonkwo\ndanielle@example.com\n\nEducation\nNorth Carolina State University — M.Ed. Science Education, 2015\n")
t("M.Ed. is a degree, and its field the major", val(f, "major"), "Science Education")
f = fields_of("MARY O'BRIEN\nmary@example.com\n\nEDUCATION\nBOSTON COLLEGE — BACHELOR OF SCIENCE IN NURSING, 2014\n")
t("an all-capitals degree gives the major without 'IN'", val(f, "major"), "NURSING")
f = fields_of("Robert Castellano\nrob@example.com\n\nSKILLS\nSAP  Budgeting  Forecasting\nTeam Leadership Board Reporting Treasury\n"
              "Audit Planning Capital Markets Hedging\n")
t("a skills grid with no commas is not joined into one skill", [s for s in (val(f, "skills") or []) if len(s.split()) > 3], [])
f = fields_of("Brianna Lopez\nbrianna@example.com\n\nSkills\nOpera PMS    Customer Service    Conflict Resolution\n")
t("skills set apart by wide spaces are separate", val(f, "skills"), ["Opera PMS", "Customer Service", "Conflict Resolution"])
f = fields_of("Sofía Ramírez\nsofia@example.com\n\n🎓 Education\nUniversity of Texas at San Antonio — B.B.A. Marketing, 2018\n\n"
              "💼 Experience\nCustomer Success Manager, Alamo Example Software\nFeb 2021 - Present\n\n🛠 Skills\nZendesk ⭐ Salesforce ⭐ Spanish\n")
t("headings and skills with emoji icons", (val(f, "grad"), val(f, "job_title"), val(f, "skills")), ("2018", "Customer Success Manager", ["Zendesk", "Salesforce", "Spanish"]))
f = fields_of("Ana Lucía de la Cruz\nana@example.com\n")
t("a name with 'de la' is a name", val(f, "name"), "Ana Lucía de la Cruz")
f = fields_of("CONTACT JORDAN PIKE\n(919) 555-0102\njordan.pike@example.com\nStatistics Example Biotech LLC\n")
t("a company line is not a name; the name spelled by the email is", val(f, "name"), "Jordan Pike")
f = fields_of("SARAH\nCONNOLLY\nsarah.connolly@example.com\n")
t("a name set one word per line", val(f, "name"), "Sarah Connolly")
f = fields_of("Arjun\narjun.dev@example.com\nSan Francisco, CA 94103\n")
t("a one-word name on the first line that starts the email", val(f, "name"), "Arjun")
f = fields_of("Taylor Brooks\ntaylor@example.com\n\nOctober 12, 2026\n\nHiring Manager\nExample Gateway Bank\nSt. Louis, MO 63101\n\n"
              "Dear Hiring Manager,\nI am writing to apply for the Branch Operations Supervisor role.\n")
t("a cover letter in front: the company's address and 'Hiring Manager' are not the person's", (val(f, "headline"), val(f, "location"), val(f, "summary")),
  (None, None, None))
f = fields_of("Contact\ndeshawn@example.com\nCertifications\nCertified Recruiter\nDeShawn Carter\nSenior Technical Recruiter at Example Robotics\n"
              "Denver, Colorado, United States\nSummary\nI help teams hire engineers and close offers fast.\n")
t("LinkedIn PDF: the city under the name is where the person lives", ((f.get("location") or {}).get("city"), (f.get("location") or {}).get("state")), ("Denver", "CO"))
md = rp.parse(b"# Noah Ruiz\n**Site Reliability Engineer** \xc2\xb7 noah@example.com\n\n## Skills\n`Kubernetes` `Terraform`\n\n## Education\n"
              b"**Illinois Institute of Technology** \xe2\x80\x94 B.S. Information Technology, 2019\n", "resume.md")["fields"]
t("a Markdown resume: no # or ** or ` in the answers", (val(md, "name"), val(md, "school"), val(md, "skills")),
  ("Noah Ruiz", "Illinois Institute of Technology", ["Kubernetes", "Terraform"]))

print("\n== Odd files: empty, over 1 MB, no text layer, random bytes, cut-off files (no crash, an answer within 3 s)")
for ext in ("pdf", "docx", "txt"):
    t("a 0-byte .%s is refused as empty" % ext, err_code(b"", "cv." + ext), "empty")
big_txt = (open(os.path.join(FIX, "student.txt"), "rb").read() + b"\n" + b"Volunteer at the food bank every Saturday.\n" * 30000)[:1500000]
t0 = time.time()
f = rp.parse(big_txt, "cv.txt")["fields"]
t("a 1.5 MB text resume is read, the top fields right, in under 3 s", (val(f, "email"), time.time() - t0 < 3), ("maya.patel@example.edu", True))


def fuzz_ok(data, name):
    """Only fields or a ResumeError with a known code, within about 3 seconds."""
    t0 = time.time()
    try:
        res = rp.parse(data, name)
        good = isinstance(res.get("fields"), dict)
    except rp.ResumeError as e:
        good = e.code in rp.MESSAGES or e.code in ("empty", "bad_request")
    except Exception as e:  # noqa: BLE001
        return "%s crashed: %r" % (name, e)
    if time.time() - t0 > 3.5:
        return "%s took %.1f s" % (name, time.time() - t0)
    return None if good else "%s: odd answer" % name


import random  # noqa: E402
rnd = random.Random(181)
bad_runs = []
for n in range(12):
    blob = bytes(rnd.getrandbits(8) for _ in range(rnd.choice([1, 50, 2000, 40000])))
    for name in ("cv.pdf", "cv.docx", "cv.txt"):
        bad_runs.append(fuzz_ok(blob, name))
        bad_runs.append(fuzz_ok(b"%PDF-1.4\n" + blob, name) if name == "cv.pdf" else fuzz_ok(b"PK\x03\x04" + blob, name))
for fx in ("newgrad.docx", "gdocs.docx", "tablecv.docx") + (("datesfirst.pdf", "canva.pdf", "senior3page.pdf") if HAS_PDF else ()):
    whole = open(os.path.join(FIX, fx), "rb").read()
    for cut in (10, 100, len(whole) // 4, len(whole) // 2, len(whole) - 30):
        bad_runs.append(fuzz_ok(whole[:cut], fx))
bad_runs.append(fuzz_ok(b"Jane Doe jane@example.com " + b"Python, " * 120000, "cv.txt"))
bad_runs.append(fuzz_ok(b"x" * 900000, "cv.txt"))
bad_runs.append(fuzz_ok(("\n".join("Line %d " % i + "word " * 8 for i in range(40000))).encode(), "cv.txt"))
t("fuzz: random bytes, cut-off Word and PDF files, a huge single line and 40,000 lines never crash or hang", [b for b in bad_runs if b], [])
f = fields_of("Jane Doe\njane@example.com\n" + "Python, SQL, " * 20000)
t("a huge single line of skills still gives the name and email", (val(f, "name"), val(f, "email")), ("Jane Doe", "jane@example.com"))
if HAS_PDF:
    import pypdf
    many = pypdf.PdfWriter()
    for _ in range(40):
        many.append(pypdf.PdfReader(os.path.join(FIX, "senior3page.pdf")))
    mb = io.BytesIO()
    many.write(mb)
    t0 = time.time()
    try:
        res = rp.parse(mb.getvalue(), "long.pdf")
        r = (val(res["fields"], "email") or "", "ok")
    except rp.ResumeError as e:
        r = ("", e.code)
    t("a 120-page PDF gives an answer (the fields, or a plain 'too long') in under 3 s", (r[1] in ("ok", "too_big", "unreadable"), time.time() - t0 < 3), (True, True))
    pad = blank_pdf(b"0 0 m 100 100 l S\n" + b"% padding\n" * 120000)
    t("a PDF over 1 MB with no text layer says it looks scanned", (len(pad) > 1024 * 1024, err_code(pad, "scan.pdf")), (True, "scanned"))
else:
    skip("many-page and no-text PDFs")

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
           UAPLY_CONFIG_JSON=json.dumps({"feeds": [], "delivery": "test", "smtp": {}, "owner_copy": ""}),
           UAPLY_SIGNUP_TEST="1")          # sign-up test mode (never public): the sign-in gate's test person is confirmed at once
env.pop("HOST", None)
proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(PORT), os.path.join(ROOT, "sandbox"), "--api"], env=env, stdout=logf, stderr=logf)
BASE = "http://127.0.0.1:%d" % PORT
COOKIE = ""                                # the signed-in test person's session (the resume reader is behind the sign-in gate)


def call(body, ctype="application/json", origin=True, path="/api/profile/resume"):
    h = {"Content-Type": ctype}
    if origin:
        h["Origin"] = BASE
    if COOKIE:
        h["Cookie"] = COOKIE
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
    sys.path.insert(0, HERE)
    import gate_session
    COOKIE = gate_session.cookie(BASE)
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
    # the bad files of card 181: each is refused kindly (a sentence for the person), never a server error
    bad_files = [("an empty file", "cv.pdf", "application/pdf", b""),
                 ("a .jpg renamed .pdf", "cv.pdf", "application/pdf", b"\xff\xd8\xff\xe0" + b"\x00" * 200),
                 ("a file over 5 MB", "cv.pdf", "application/pdf", b"%PDF-1.4\n" + b"a" * (5 * 1024 * 1024 + 10))]
    if HAS_PDF:
        bad_files += [("a scanned PDF that is only a picture", "scan.pdf", "application/pdf", image_pdf()),
                      ("a password-protected PDF", "locked.pdf", "application/pdf", LOCKED)]
    for label, name, ct, data in bad_files:
        code, out = call(json.dumps({"resume": {"name": name, "data": "data:%s;base64,%s" % (ct, base64.b64encode(data).decode())}}).encode())
        t("%s: refused kindly (%s), with a sentence, no server error" % (label, code),
          (code in (400, 413, 422), bool(out.get("error")) and len(out["error"]) < 200 and "Traceback" not in out["error"], bool(out.get("ok"))), (True, True, False))
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
# the six answers Profile setup asks about first, per resume: right, blank (in the resume but not found), wrong (found, not right),
# n/a (not in that resume and correctly left empty)
print("\n== Per field: right / blank / wrong (n/a = not in that resume, left empty)")
COLS = [("name", "name"), ("phone", "phone"), ("email", "email"), ("city/ZIP", "location"), ("latest title", "job_title"), ("skills", "skills")]
print("  %-18s" % "resume" + "".join("%-14s" % c for c, _k in COLS))
totals = {"right": 0, "blank": 0, "wrong": 0, "n/a": 0}
for fname, want, got in TABLE:
    row = []
    for _c, k in COLS:
        if k not in want:
            r = "wrong" if k in got else "n/a"
        elif k not in got:
            r = "blank"
        else:
            r = "right" if GOOD.get((fname, k)) else "wrong"
        totals[r] += 1
        row.append(r)
    print("  %-18s" % fname + "".join("%-14s" % r for r in row))
print("  right %d, blank %d, wrong %d, n/a %d" % (totals["right"], totals["blank"], totals["wrong"], totals["n/a"]))
t("the six answers: none wrong on any resume", totals["wrong"], 0)
print("\n== Every field over all resumes: right / blank / wrong")
for k in sorted(FIELDS):
    print("  %-10s right %3d   blank %2d   wrong %2d" % (k, FIELDS[k]["right"], FIELDS[k]["blank"], FIELDS[k]["wrong"]))
allt = {r: sum(v[r] for v in FIELDS.values()) for r in ("right", "blank", "wrong")}
print("  all        right %3d   blank %2d   wrong %2d" % (allt["right"], allt["blank"], allt["wrong"]))
t("every field: none wrong on any resume", [(k, v["wrong"]) for k, v in sorted(FIELDS.items()) if v["wrong"]], [])
print("\n%d / %d" % (ok, ok + bad))
sys.exit(1 if bad else 0)
