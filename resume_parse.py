"""Reads a resume (PDF, Word .docx or plain text) and finds what Profile setup asks for, so a person can fill their profile from it.

    parse(data, name="", ctype="")  ->  {"kind": "pdf", "text": "...", "fields": {"email": {"value": ..., "confidence": "high",
                                         "line": "the line it came from"}, ...}}
    handle(body, content_type)      ->  (status, answer) for POST /api/profile/resume (serve.py)

Every field is optional and comes with how sure the reading is (high, medium, low) and the line it came from, so the page can show the
person where each answer came from before anything is used. Nothing here keeps the file or the text: both live only for the length of
the call. Nothing in the file is ever run: PDF text is read by pypdf in a separate, time-limited process, a Word file is read as plain
XML from inside its zip (no macros, no outside references), and a text file is only decoded.

What it cannot do: read a scanned PDF (a picture of text has no text to read; there is no OCR here), or put text back in order when a
PDF's columns were drawn line by line across the page. Those resumes get the fields that are still recognisable (email, phone, links)
and a plain message for the rest.

Layouts it handles: one column; two columns (sidebar first or main column first, as Word and most PDF makers write them); section
headings in any case, letter-spaced (E X P E R I E N C E), with a colon, or with the content on the same line ("Skills: Python, SQL");
dates as "Jan 2024 - Present", "January 2024 to Current", "01/2024 - 05/2025", "2024-01", "Summer 2024", "2023-2025", "2023 - Now",
written before the job ("2023-2025  Analyst, Acme") or after it.
"""
import base64
import io
import json
import os
import re
import subprocess
import sys
import unicodedata
import zipfile
from email.parser import BytesParser
from email.policy import default as _email_policy
from xml.etree import ElementTree

MAX_BYTES = 5 * 1024 * 1024          # the biggest resume file read
MAX_PAGES = 10                        # a resume longer than this is read only this far
MAX_TEXT = 60000                      # characters of text kept for reading the fields
PDF_SECONDS = 15                      # how long one PDF may take to read before it is given up on


class ResumeError(ValueError):
    """A resume that cannot be read. `code` is for the page and the tests; the message is said to the person as it is."""

    def __init__(self, code, message):
        ValueError.__init__(self, message)
        self.code = code
        self.message = message


MESSAGES = {
    "too_big": "That file is over 5 MB. Save your resume as a smaller PDF or Word file and try again.",
    "empty": "That file is empty. Choose the file of your resume and try again.",
    "wrong_type": "Use a PDF, a Word file (.docx) or a text file (.txt).",
    "old_doc": "That is an older Word file (.doc). Open it in Word, save it as .docx or PDF, and try again.",
    "image": "That is a picture, not a document. Use the PDF or Word file of your resume instead.",
    "scanned": "This PDF is a scanned picture of your resume, so there is no text in it to read. Use the PDF or Word file you saved "
               "from your word processor instead.",
    "encrypted": "This PDF is protected with a password. Save a copy without the password and try again.",
    "unreadable": "We could not read any text in that file. Save it again as a PDF or Word file and try again.",
    "slow": "That file took too long to read. Try saving it again as a simpler PDF, or use a Word file.",
    "no_pdf": "Reading PDF files is not switched on here yet. Use a Word (.docx) or text file for now.",
    "bad_request": "We could not receive that file. Choose it again and try once more.",
}


def _fail(code):
    raise ResumeError(code, MESSAGES[code])


# ---------------------------------------------------------------------------------------------------------------------------------
# Getting the text out of the file
# ---------------------------------------------------------------------------------------------------------------------------------

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​-‏  ‪-‮⁠-⁤﻿￾￿]")


def clean_text(s):
    """Plain text with ordinary spaces and line breaks only: no control characters, no invisible direction marks, Windows and old Mac line
    endings made into \\n, ligatures (the fi in "Profile" that some PDFs write as one letter) spelled out."""
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n").replace("\v", "\n").replace("\t", "  ")
    s = unicodedata.normalize("NFKC", s)
    s = _CONTROL.sub("", s)
    s = s.replace(" ", " ")
    s = re.sub(r"[ ]{3,}", "   ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()[:MAX_TEXT]


def _kind(data, name, ctype):
    """What the file really is, by its first bytes first and its name second (a renamed file is read as what it is)."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    ctype = (ctype or "").split(";")[0].strip().lower()
    if data.startswith(b"%PDF") or (b"%PDF-" in data[:1024] and ext == "pdf"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        return "docx"
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        _fail("old_doc")
    if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:6] in (b"GIF87a", b"GIF89a") or data[:4] in (b"II*\x00", b"MM\x00*") \
            or (data[:4] == b"RIFF" and data[8:12] == b"WEBP") or data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1"):
        _fail("image")
    if ext in ("txt", "md", "text") or ctype.startswith("text/") or not ext:
        return "txt"
    if ext in ("pdf", "docx"):                                       # named like one but is not one
        _fail("unreadable")
    if ext == "doc":
        _fail("old_doc")
    _fail("wrong_type")


def _txt(data):
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        enc = "utf-16"
    elif data.startswith(b"\xef\xbb\xbf"):
        enc = "utf-8-sig"
    else:
        enc = "utf-8"
    try:
        s = data.decode(enc)
    except UnicodeDecodeError:
        try:
            s = data.decode("cp1252")                               # a text file saved by an older Windows program
        except UnicodeDecodeError:
            _fail("unreadable")
    if s.count("\x00") > len(s) // 20:                               # a binary file with a .txt name
        _fail("unreadable")
    return s


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_part(xml):
    """The paragraphs of one part of a Word file, in order, one per line. Tables give their cells left to right, row by row, which is how
    a two-column Word resume built on a table reads; text boxes give their own paragraphs where they sit."""
    if b"<!DOCTYPE" in xml[:4096] or b"<!ENTITY" in xml:            # a Word file never has these; refusing them stops entity tricks
        _fail("unreadable")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        _fail("unreadable")
    lines = []

    def para(p):
        out = []

        def walk(el):
            for c in el:
                if c.tag == _W + "p":                               # a paragraph inside a text box: its own line, read below
                    continue
                if c.tag == _W + "t" and c.text:
                    out.append(c.text)
                elif c.tag == _W + "tab":
                    out.append("  ")
                elif c.tag in (_W + "br", _W + "cr"):
                    out.append("\n")
                walk(c)
        walk(p)
        return "".join(out)

    seen = set()
    for p in root.iter(_W + "p"):
        if id(p) in seen:
            continue
        seen.add(id(p))
        lines.append(para(p))
    return "\n".join(lines)


def _docx(data):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = z.namelist()
    except (zipfile.BadZipFile, ValueError, OSError):
        _fail("unreadable")
    if "word/document.xml" not in names:
        _fail("wrong_type")                                         # a zip, or an Excel or PowerPoint file
    parts = sorted(n for n in names if re.match(r"^word/header\d*\.xml$", n)) + ["word/document.xml"]
    text = []
    for n in parts:
        info = z.getinfo(n)
        if info.file_size > 20 * 1024 * 1024:                       # a resume's text is a few kilobytes; this is a zip bomb
            _fail("unreadable")
        try:
            text.append(_docx_part(z.read(n)))
        except ResumeError:
            raise
        except Exception:
            _fail("unreadable")
    return "\n".join(text)


# The PDF is read in a separate Python process: a file built to make the reader loop or eat memory then costs at most PDF_SECONDS and a
# capped amount of memory, and can never take the server down with it.
_PDF_CHILD = r"""
import sys, io
try:
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
except Exception:
    pass
try:
    import pypdf
except ImportError:
    sys.stdout.write("E:no_pdf"); sys.exit(0)
data = sys.stdin.buffer.read()
try:
    r = pypdf.PdfReader(io.BytesIO(data))
    if r.is_encrypted:
        try:
            if not r.decrypt(""):
                sys.stdout.write("E:encrypted"); sys.exit(0)
        except Exception:
            sys.stdout.write("E:encrypted"); sys.exit(0)
    out = []
    for i, page in enumerate(r.pages):
        if i >= int(sys.argv[1]):
            break
        try:
            out.append(page.extract_text() or "")
        except Exception:
            out.append("")
    sys.stdout.write("T:" + "\n".join(out))
except Exception:
    sys.stdout.write("E:unreadable")
"""


def pdf_available():
    """True when pypdf can be imported (it is imported here only to check; the reading itself happens in the separate process)."""
    try:
        import importlib
        importlib.import_module("pypdf")
        return True
    except Exception:
        return False


def _pdf(data):
    if not pdf_available():
        _fail("no_pdf")
    try:
        r = subprocess.run([sys.executable, "-c", _PDF_CHILD, str(MAX_PAGES)], input=data, capture_output=True, timeout=PDF_SECONDS,
                           cwd=os.path.dirname(os.path.abspath(__file__)), env={k: v for k, v in os.environ.items() if k in ("PATH", "PYTHONPATH", "HOME", "SYSTEMROOT", "LANG")})
    except subprocess.TimeoutExpired:
        _fail("slow")
    except OSError:
        _fail("unreadable")
    out = r.stdout.decode("utf-8", "replace")
    if out.startswith("E:"):
        _fail(out[2:].strip() if out[2:].strip() in MESSAGES else "unreadable")
    if not out.startswith("T:"):
        _fail("slow" if r.returncode and r.returncode < 0 else "unreadable")
    text = out[2:]
    if len(re.sub(r"\s", "", text)) < 20:
        _fail("scanned")                                            # pages with no text at all: a scan or a photo saved as PDF
    return text


def read_text(data, name="", ctype=""):
    """(kind, plain text) of a resume file. Raises ResumeError with a sentence for the person when it cannot be read."""
    if not isinstance(data, (bytes, bytearray)):
        _fail("bad_request")
    if len(data) > MAX_BYTES:
        _fail("too_big")
    if not data.strip():
        _fail("empty")
    kind = _kind(bytes(data), name or "", ctype or "")
    raw = _pdf(data) if kind == "pdf" else _docx(data) if kind == "docx" else _txt(data)
    text = clean_text(raw)
    if len(re.sub(r"\W", "", text)) < 20:
        _fail("scanned" if kind == "pdf" else "unreadable")
    return kind, text


# ---------------------------------------------------------------------------------------------------------------------------------
# Finding the fields in the text
# ---------------------------------------------------------------------------------------------------------------------------------

SECTIONS = {
    "summary": ["summary", "professional summary", "career summary", "profile", "professional profile", "personal profile", "objective",
                "career objective", "professional objective", "about me", "about", "personal statement", "summary of qualifications",
                "career profile", "introduction", "overview"],
    "experience": ["experience", "work experience", "professional experience", "relevant experience", "employment", "employment history",
                   "work history", "career history", "professional background", "internships", "internship experience", "work",
                   "experience and internships", "industry experience", "professional employment", "positions held", "job history"],
    "education": ["education", "academic background", "academics", "education and training", "education & training", "academic history",
                  "education and certifications", "education & certifications", "academic qualifications", "qualifications", "studies"],
    "skills": ["skills", "technical skills", "core skills", "key skills", "skills & tools", "skills and tools", "core competencies",
               "competencies", "technologies", "tools", "technical proficiencies", "skills and interests", "skills & interests",
               "skills & abilities", "skills and abilities", "areas of expertise", "expertise", "tech stack", "toolbox", "software",
               "technical expertise", "programming languages", "languages and tools", "skill set", "skillset", "strengths",
               "skills & languages", "skills and languages"],
    "projects": ["projects", "selected projects", "academic projects", "personal projects", "key projects", "project experience",
                 "side projects", "portfolio"],
    "other": ["certifications", "certificates", "licenses", "licenses and certifications", "licenses & certifications", "awards", "honors",
              "honors and awards", "honors & awards", "achievements", "activities", "leadership", "leadership experience",
              "volunteer", "volunteering", "volunteer experience", "community involvement", "publications", "languages", "interests",
              "hobbies", "references", "coursework", "relevant coursework", "contact", "contact information", "contact info", "links",
              "extracurricular activities", "extracurriculars", "affiliations", "memberships", "research", "research experience",
              "conferences", "presentations", "additional information", "additional", "personal details", "details"],
}
_HEAD = {}
for _sec, _names in SECTIONS.items():
    for _n in _names:
        _HEAD[_n] = _sec

MONTHS = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
          "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11,
          "november": 11, "dec": 12, "december": 12, "spring": 5, "summer": 8, "fall": 12, "autumn": 12, "winter": 12}
_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|spring|summer|fall|autumn|winter)"
_YEAR = r"(?:19[5-9]\d|20[0-4]\d)"
_ONE = r"(?:%s\.?,?\s*'?%s|%s\.?\s*'\d\d|(?:0?[1-9]|1[0-2])\s*[/.]\s*%s|%s\s*[-/.]\s*(?:0[1-9]|1[0-2])(?!\d)|%s)" % (_MON, _YEAR, _MON, _YEAR, _YEAR, _YEAR)
_NOW = r"(?:present|current(?:ly)?|now|today|ongoing|till date|to date)"
_SEP = r"\s*(?:-|–|—|―|−|~|to|until|thru|through)\s*"
DATE_RANGE = re.compile(r"(?<![\w/])(%s)%s(%s|%s)(?![\w/])" % (_ONE, _SEP, _ONE, _NOW), re.I)
DATE_ONE = re.compile(r"(?<![\w/])(%s)(?![\w/])" % _ONE, re.I)

EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}(?![\w-])")
LINKEDIN = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/(in|pub)/([A-Za-z0-9\-_%.]{2,100})", re.I)
GITHUB = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?![\w-])", re.I)
URL = re.compile(r"(?<![@\w.])(?:https?://)?(?:www\.)?((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:com|net|org|io|dev|me|app|co|ai|xyz|site|tech|design|info|page|blog|us|uk|ca|de|in|portfolio|studio)(?:/[^\s,;|)]*)?)(?![\w@])", re.I)
PHONE = re.compile(r"(?<![\w+])(\+\d{1,3}[\s.-]?)?(\(\d{1,4}\)[\s.-]?)?\d{1,4}(?:[\s.-]?\d{2,5}){1,4}(?![\w])")
GPA = re.compile(r"(?:\b(?:cumulative |overall |major |cum\.? )?gpa\b\s*(?:of\s*)?[:\-–]?\s*(\d\.\d{1,2})(?:\s*/\s*(\d(?:\.\d{1,2})?))?)|(?:\b(\d\.\d{1,2})(?:\s*/\s*(\d(?:\.\d{1,2})?))?\s*(?:cumulative |overall )?gpa\b)", re.I)

US_STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
             "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
             "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
             "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
             "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
             "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
             "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
             "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}
_STATE_BY_NAME = {v.lower(): k for k, v in US_STATES.items()}
_CITY = r"([A-Z][A-Za-z.'\-]+(?:[ ][A-Z][A-Za-z.'\-]+){0,3})"
LOC_US = re.compile(_CITY + r",\s*(%s)\b\.?(?:\s+(\d{5})(?:-\d{4})?)?(?![a-z])" % "|".join(US_STATES))
LOC_US_NAME = re.compile(_CITY + r",\s*(%s)\b(?:\s+(\d{5})(?:-\d{4})?)?" % "|".join(re.escape(v) for v in US_STATES.values()))
COUNTRIES = ["United Kingdom", "UK", "England", "Scotland", "Ireland", "Canada", "India", "Germany", "France", "Spain", "Italy", "Netherlands",
             "Australia", "New Zealand", "Singapore", "Japan", "China", "Hong Kong", "Brazil", "Mexico", "Nigeria", "Kenya", "South Africa",
             "Pakistan", "Bangladesh", "Philippines", "Vietnam", "South Korea", "Korea", "UAE", "United Arab Emirates", "Israel", "Poland",
             "Sweden", "Norway", "Denmark", "Switzerland", "Portugal", "Egypt", "Turkey", "Colombia", "Argentina", "Chile", "Peru"]
LOC_INTL = re.compile(_CITY + r",\s*(%s)\b" % "|".join(re.escape(c) for c in COUNTRIES))

# words that make a line (or part of one) a job title
TITLE_WORDS = ("engineer", "developer", "programmer", "intern", "internship", "analyst", "assistant", "associate", "manager", "designer",
               "specialist", "coordinator", "consultant", "scientist", "researcher", "research", "lead", "director", "tutor", "teacher",
               "instructor", "cashier", "server", "barista", "representative", "technician", "administrator", "officer", "nurse",
               "accountant", "architect", "advisor", "adviser", "fellow", "head", "president", "vice president", "founder", "co-founder",
               "owner", "writer", "editor", "marketer", "strategist", "planner", "supervisor", "clerk", "agent", "recruiter", "student",
               "graduate", "major", "candidate", "volunteer", "counselor", "trainer", "mentor", "producer", "artist", "photographer",
               "librarian", "attendant", "operator", "mechanic", "electrician", "pharmacist", "therapist", "paralegal", "lawyer",
               "attorney", "chef", "cook", "host", "sales", "lifeguard", "ambassador", "scholar", "chair", "captain", "member", "staff",
               "worker", "partner", "principal", "sde", "swe", "devops", "sre", "qa", "ux", "ui", "product owner", "cto", "ceo", "cfo")
ORG_WORDS = ("inc", "inc.", "llc", "l.l.c.", "ltd", "ltd.", "corp", "corp.", "corporation", "company", "co.", "group", "labs", "lab",
             "technologies", "technology", "solutions", "systems", "partners", "bank", "university", "college", "hospital", "health",
             "foundation", "institute", "agency", "studio", "studios", "consulting", "capital", "ventures", "services", "software",
             "media", "networks", "logistics", "gmbh", "plc", "s.a.", "ag", "associates", "industries", "enterprises", "holdings",
             "department", "council", "city of", "county", "school district", "restaurant", "cafe", "store", "market", "clinic", "union",
             "grocery", "payments", "bakery", "hotel", "airlines", "motors", "pharmacy", "library", "museum", "church", "nonprofit")
SCHOOL_WORDS = re.compile(r"\b(university|universit[éeàa]|universidad|college|institute|institut|school|academy|polytechnic|politecnico|"
                          r"conservatory|seminary|community college|high school|iit|mit|ucla|nyu|usc|cuny|suny)\b", re.I)
_DW = r"(?: of (?!in\b)[a-z]+(?: (?!in\b|and\b)[a-z]+)?)?"
DEGREE = re.compile(r"\b(bachelor(?:'?s)?" + _DW + r"|master(?:'?s)?" + _DW + r"|associate(?:'?s)?" + _DW + r"|"
                    r"doctor(?:ate)?(?: of [a-z]+)?|ph\.?\s?d\.?|m\.?b\.?a\.?|b\.?\s?s\.?c?\.?|b\.?\s?a\.?|m\.?\s?s\.?c?\.?|m\.?\s?a\.?|b\.?\s?eng\.?|m\.?\s?eng\.?|"
                    r"b\.?\s?tech\.?|m\.?\s?tech\.?|b\.?\s?b\.?\s?a\.?|b\.?\s?f\.?\s?a\.?|a\.?\s?a\.?s?\.?|a\.?\s?s\.?|bsc|msc|beng|meng|btech|mtech|bba|bfa|"
                    r"high school diploma|diploma|certificate|ged)(?![a-z])", re.I)

# a reasonable vocabulary of skills that appear on resumes, with the spelling shown back to the person
SKILLS = ["Python", "Java", "JavaScript", "TypeScript", "C", "C++", "C#", "Go", "Golang", "Rust", "Ruby", "PHP", "Swift", "Kotlin", "Scala", "R",
          "MATLAB", "SQL", "NoSQL", "PostgreSQL", "MySQL", "SQLite", "MongoDB", "Redis", "Elasticsearch", "GraphQL", "REST", "HTML", "CSS",
          "Sass", "Tailwind", "Bootstrap", "React", "React Native", "Next.js", "Vue", "Angular", "Svelte", "jQuery", "Node.js", "Express",
          "Django", "Flask", "FastAPI", "Spring", "Spring Boot", ".NET", "Rails", "Laravel", "Flutter", "Android", "iOS", "SwiftUI",
          "AWS", "Azure", "GCP", "Google Cloud", "Docker", "Kubernetes", "Terraform", "Ansible", "Jenkins", "GitHub Actions", "CI/CD",
          "Git", "Linux", "Bash", "PowerShell", "Unix", "Kafka", "Spark", "Hadoop", "Airflow", "Snowflake", "BigQuery", "dbt",
          "Pandas", "NumPy", "SciPy", "scikit-learn", "TensorFlow", "PyTorch", "Keras", "OpenCV", "NLP", "Machine Learning",
          "Deep Learning", "Computer Vision", "Data Analysis", "Data Visualization", "Statistics", "Tableau", "Power BI", "Looker",
          "Excel", "Google Sheets", "VBA", "SAS", "SPSS", "Stata", "Jupyter", "LaTeX", "Figma", "Sketch", "Adobe XD", "Photoshop",
          "Illustrator", "InDesign", "Premiere Pro", "After Effects", "Canva", "UX Research", "User Research", "Wireframing",
          "Prototyping", "Accessibility", "SEO", "Google Analytics", "HubSpot", "Salesforce", "Marketo", "Mailchimp", "Jira",
          "Confluence", "Asana", "Trello", "Notion", "Agile", "Scrum", "Kanban", "Project Management", "Product Management",
          "QuickBooks", "Xero", "SAP", "Oracle", "Microsoft Office", "Word", "PowerPoint", "Outlook", "AutoCAD", "SolidWorks",
          "Revit", "CAD", "Arduino", "Raspberry Pi", "Embedded Systems", "Verilog", "VHDL", "Unity", "Unreal Engine", "Blender",
          "Selenium", "Cypress", "Jest", "Pytest", "JUnit", "Postman", "Webpack", "Vite", "Firebase", "Supabase", "Heroku", "Vercel",
          "Nginx", "Microservices", "System Design", "Data Structures", "Algorithms", "Object-Oriented Programming", "Cybersecurity",
          "Networking", "TCP/IP", "Customer Service", "Sales", "Public Speaking", "Leadership", "Teamwork", "Communication",
          "Copywriting", "Content Writing", "Social Media", "Event Planning", "Financial Modeling", "Accounting", "Bookkeeping",
          "Budgeting", "Forecasting", "Research", "Spanish", "French", "Mandarin", "German", "Hindi", "Arabic", "Portuguese"]
# short or common words that only count inside a skills section, never from a sentence elsewhere ("Go to market", "R&D", "Word")
_SECTION_ONLY = {"C", "R", "Go", "Word", "Sales", "Research", "Leadership", "Teamwork", "Communication", "Spring", "Express", "Unity",
                 "Excel", "Swift", "Rails", "Statistics", "Accounting", "Networking", "Outlook", "Oracle", "Sketch", "Spanish", "French",
                 "German", "Mandarin", "Hindi", "Arabic", "Portuguese", "REST", "Agile", "Scrum", "Budgeting", "Forecasting", "Kanban",
                 "Notion", "Android", "iOS", "Accessibility", "Social Media", "Customer Service", "Public Speaking"}
_SKILL_BY_LOWER = {s.lower(): s for s in SKILLS}
_SKILL_ALIAS = {"js": "JavaScript", "ts": "TypeScript", "golang": "Go", "postgres": "PostgreSQL", "reactjs": "React", "react.js": "React",
                "nodejs": "Node.js", "node": "Node.js", "vue.js": "Vue", "vuejs": "Vue", "k8s": "Kubernetes", "ms excel": "Excel",
                "microsoft excel": "Excel", "ms office": "Microsoft Office", "sklearn": "scikit-learn", "gcp": "GCP", "ml": "Machine Learning",
                "powerbi": "Power BI", "c/c++": "C++", "html5": "HTML", "css3": "CSS", "amazon web services": "AWS", "next": "Next.js",
                "nextjs": "Next.js", "tf": "TensorFlow"}

_BULLET = re.compile(r"^[\s•‣▪▫●○◦⁃∙·➢➤►▸❖✔✓→\-\*–—>»o§]+\s*")


def _plain(line):
    """A line without its bullet and extra spaces, for matching."""
    return re.sub(r"\s+", " ", _BULLET.sub("", line)).strip()


def _is_bullet(line):
    s = line.lstrip()
    return bool(s) and (s[0] in "•‣▪▫●○◦⁃∙·➢➤►▸❖✔✓→*>»"
                        or re.match(r"^[-–—o]\s", s) is not None)


def _unspace(s):
    """E X P E R I E N C E  ->  EXPERIENCE (letter-spaced headings some templates use)."""
    if re.fullmatch(r"(?:[A-Za-z&] ){3,}[A-Za-z&]", s):
        return s.replace(" ", "")
    if re.fullmatch(r"(?:(?:[A-Za-z&] ){1,}[A-Za-z&])(?:\s{2,}(?:[A-Za-z&] ){1,}[A-Za-z&])+", s):
        return " ".join(w.replace(" ", "") for w in re.split(r"\s{2,}", s))
    return s


def heading(line):
    """(section, rest of the line) when the line is a section heading, else None. 'Skills: Python, SQL' gives ('skills', 'Python, SQL')."""
    s = _unspace(_plain(line).strip(" :|#=_*"))
    if not s:
        return None
    key = re.sub(r"\s+", " ", s.lower().replace("&", " & ")).strip()
    key2 = key.replace(" & ", " and ")
    for k in (key, key2):
        if len(k) <= 60 and k in _HEAD:
            return _HEAD[k], ""
    m = re.match(r"^([A-Za-z][A-Za-z &/]{1,40}?)\s*[:|\-–]\s+(.+)$", s)
    if m:
        k = re.sub(r"\s+", " ", m.group(1).lower().replace("&", " & ")).strip()
        for kk in (k, k.replace(" & ", " and ")):
            if kk in _HEAD:
                return _HEAD[kk], m.group(2).strip()
    return None


def split_sections(lines):
    """{section: [line indexes]} plus "top" for what comes before the first heading. A heading that appears twice (a two-column PDF that
    repeats "Experience" on page two) adds to the same section."""
    out = {"top": []}
    cur = "top"
    inline = {}
    for i, ln in enumerate(lines):
        h = heading(ln)
        if h and h[1] and cur != "top" and (h[0] == "other" or h[0] == cur):
            h = None                                                # "Languages: Python, Java" inside Skills, "Coursework: ..." inside Education
        if h:
            cur = h[0]
            out.setdefault(cur, [])
            if h[1]:
                inline[i] = h[1]
                out[cur].append(i)
            continue
        out.setdefault(cur, []).append(i)
    return out, inline


def _ym(text):
    """'Jan 2024' -> (2024, 1); '2024' -> (2024, None); 'Present' -> 'present'."""
    t = text.strip().lower().rstrip(".")
    if re.fullmatch(_NOW, t, re.I):
        return "present"
    m = re.match(r"^(%s)\.?,?\s*'?(\d{2,4})$" % _MON, t, re.I)
    if m:
        y = int(m.group(2))
        y = y + 2000 if y < 50 else y + 1900 if y < 100 else y
        key = m.group(1).lower()
        return (y, MONTHS.get(key) or MONTHS[key[:3]])
    m = re.match(r"^(\d{1,2})\s*[/.]\s*(\d{4})$", t)
    if m:
        return (int(m.group(2)), int(m.group(1)))
    m = re.match(r"^(\d{4})\s*[-/.]\s*(\d{2})$", t)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.match(r"^(\d{4})$", t)
    if m:
        return (int(m.group(1)), None)
    return None


def _fmt(d):
    if d == "present":
        return "present"
    if not d:
        return ""
    return "%04d-%02d" % d if d[1] else "%04d" % d[0]


def _sortkey(d):
    if d == "present":
        return (9999, 12)
    if not d:
        return (0, 0)
    return (d[0], d[1] or 6)


def _field(value, confidence, line):
    return {"value": value, "confidence": confidence, "line": re.sub(r"\s+", " ", line).strip()[:200]}


def _smart_case(s):
    """JANE DOE -> Jane Doe; jane doe -> Jane Doe; McKenzie O'Neil stays as written."""
    if s.isupper() or s.islower():
        s = " ".join("-".join(p[:1].upper() + p[1:].lower() for p in w.split("-")) for w in s.split(" "))
        s = re.sub(r"\b([OD])'([a-z])", lambda m: m.group(1) + "'" + m.group(2).upper(), s)          # O'Neil, D'Angelo
    return s


_NAME_WORD = re.compile(r"^[A-ZÀ-ɏ][A-Za-zÀ-ɏ'’.\-]*$|^[a-zß-ɏ][a-zß-ɏ'’\-]+$")
_NOT_NAME = {"resume", "curriculum", "vitae", "cv", "contact", "page", "profile", "summary", "objective", "email", "phone", "address",
             "education", "experience", "skills", "the", "and", "of", "for", "at", "in", "university", "college", "street", "avenue"}


def _name_like(s):
    s = re.sub(r"\s+", " ", s).strip(" ,|·•")
    if not 3 <= len(s) <= 60 or any(ch.isdigit() for ch in s) or "@" in s or "/" in s or ":" in s:
        return ""
    words = s.split(" ")
    if not 2 <= len(words) <= 4:
        return ""
    if any(w.lower().strip(".,") in _NOT_NAME for w in words):
        return ""
    if any(w.lower().strip(".,") in TITLE_WORDS for w in words):
        return ""
    cased = _smart_case(s)
    if all(_NAME_WORD.match(w) for w in cased.split(" ")) and not heading(s):
        return cased
    return ""


def _contact_line(s):
    return bool(EMAIL.search(s) or LINKEDIN.search(s) or GITHUB.search(s) or re.search(r"\d{3}[\s.)-]+\d{3}[\s.-]+\d{4}", s)
                or URL.search(s))


def _strip_dates(s):
    s = DATE_RANGE.sub(" ", s)
    s = re.sub(r"\(?\s*(?:expected|anticipated|exp\.?|graduat(?:ed|ing|ion)|class of)\s*:?\s*%s\s*\)?" % _ONE, " ", s, flags=re.I)
    s = DATE_ONE.sub(" ", s)
    return re.sub(r"\s{2,}", " ", s).strip(" ,|·•-–—()")


def _strip_location(s):
    s = LOC_US.sub(" ", s)
    s = LOC_US_NAME.sub(" ", s)
    s = LOC_INTL.sub(" ", s)
    s = re.sub(r"\b(remote|hybrid|on-?site)\b", " ", s, flags=re.I)
    return re.sub(r"\s{2,}", " ", s).strip(" ,|·•-–—()")


def _has_word(s, words):
    low = " " + re.sub(r"[^a-z0-9.&/ -]", " ", s.lower()) + " "
    return any((" " + w + " ") in low or (" " + w + "s ") in low or (" " + w + ",") in low for w in words)


def _phone(lines, order):
    for i in order:
        ln = lines[i]
        labeled = re.search(r"\b(phone|tel|telephone|mobile|cell|mob|ph)\b\.?\s*[:#]?", ln, re.I)
        for m in PHONE.finditer(ln):
            raw = m.group(0).strip()
            digits = re.sub(r"\D", "", raw)
            if not 7 <= len(digits) <= 15:
                continue
            if DATE_RANGE.search(raw) or re.fullmatch(r"(19|20)\d\d\s*[-–]\s*(19|20)\d\d", raw):
                continue
            us = re.fullmatch(r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", raw)
            intl = raw.startswith("+") and len(digits) >= 8
            if us or intl or (labeled and len(digits) >= 7):
                return _field(raw, "high" if (us or intl) else "medium", ln)
    return None


def _skills(lines, secs, inline):
    found, seen = [], set()

    def add(name, conf, line):
        k = name.lower()
        if k in seen or not name:
            return
        seen.add(k)
        found.append((name, conf, line))

    idx = secs.get("skills", [])
    for i in idx:
        ln = inline.get(i, lines[i])
        body = _plain(ln)
        if re.match(r"^[A-Za-z][A-Za-z &/]{1,30}:\s", body):              # "Languages: Python, Java" -> the list after the label
            body = body.split(":", 1)[1]
        for part in re.split(r"\s*(?:,|;|\||•|·|/(?!\w*\b(?:IP|CD)\b)|\s{2,}|\t| and )\s*", body):
            part = part.strip(" .()[]-–")
            if not part or len(part) > 40 or len(part.split()) > 4 or re.search(r"\d{4}", part):
                continue
            canon = _SKILL_ALIAS.get(part.lower()) or _SKILL_BY_LOWER.get(part.lower())
            add(canon or (part.title() if part.islower() else part), "high", lines[i])
    text_lines = [(i, lines[i]) for i in range(len(lines)) if i not in set(idx)]
    for s in SKILLS:
        if s in _SECTION_ONLY or s.lower() in seen:
            continue
        pat = re.compile(r"(?<![\w+#.])" + re.escape(s) + r"(?![\w+#])" + (r"" if s[-1].isalnum() else ""), re.I if len(s) > 3 else 0)
        for i, ln in text_lines:
            if pat.search(ln) and not EMAIL.search(ln):
                add(s, "medium", ln)
                break
    return found[:40]


def _education(lines, secs, inline):
    out = {}
    idx = secs.get("education", [])
    pool = idx if idx else list(range(len(lines)))
    school_i = None

    def at(i):
        """The line as plain text, joined with the next one when it stops mid-phrase ("Bachelor of Science in" / "Computer Engineering")."""
        p = _plain(inline.get(i, lines[i]))
        if re.search(r"\b(in|of|and|&)$|,$", p) and i + 1 < len(lines) and lines[i + 1].strip() and not heading(lines[i + 1]):
            p = p.rstrip(",") + (", " if p.endswith(",") else " ") + _plain(lines[i + 1])
        return p

    for i in pool:
        p = at(i)
        m = SCHOOL_WORDS.search(p)
        if m and len(p) < 140 and not (not idx and _is_bullet(lines[i])):
            name = p
            # "B.S. Computer Science, Temple University" or "Temple University | B.S. ..." -> keep the part with the school word
            parts = re.split(r"\s+[|•·]\s+|\s{2,}|\s[-–—]\s|,\s(?=[A-Z])", name)
            for part in parts:
                if SCHOOL_WORDS.search(part):
                    name = part
                    break
            name = _strip_location(_strip_dates(name))
            name = re.sub(r"^(at|from)\s+", "", name, flags=re.I).strip(" ,.")
            if DEGREE.match(name) and " in " not in name.lower():
                continue
            if 3 <= len(name) <= 100:
                out["school"] = _field(name, "high" if idx else "medium", lines[i])
                school_i = i
                break
    near = [i for i in pool if school_i is None or abs(i - school_i) <= 4] if pool else []
    for i in near or pool:
        p = at(i)
        major = ""
        m = re.search(r"\b(?:major|concentration|field of study)\s*(?:in)?\s*[:\-]?\s*([A-Z][A-Za-z&,' -]{2,60})", p)
        if m:
            major = m.group(1)
        else:
            d = DEGREE.search(p)
            if d:
                tail = p[d.end():]
                m = re.match(r"^\.?\s*(?:,|in|of|:|-|–)?\s*(?:in\s+)?([A-Z][A-Za-z&' -]{2,60}?)(?=\s*(?:,|\||;|\(|·|•|\s[-–—]\s|\s{2,}|minor|gpa|$|%s|%s))" % (_MON, _YEAR), tail)
                if m and not SCHOOL_WORDS.search(m.group(1)):
                    major = m.group(1)
                elif d.group(0).lower().startswith(("bachelor of", "master of", "associate of", "doctor of")):
                    sub = re.sub(r"^(bachelor|master|associate|doctor)(?:'?s)? of ", "", d.group(0), flags=re.I)
                    if sub.lower() not in ("science", "arts", "engineering", "business administration", "fine arts", "applied science", "philosophy"):
                        major = sub
        major = re.sub(r"\s+(minor|with|gpa|expected|graduat).*$", "", major, flags=re.I).strip(" ,.-–")
        if major and 2 < len(major) <= 80 and not SCHOOL_WORDS.search(major):
            out["major"] = _field(major[:1].upper() + major[1:], "high" if idx else "medium", lines[i])
            break
    # graduation: "Expected May 2027", the end of the date range next to the school, or the year alone
    grad = None
    for i in ((near or pool) if (idx or school_i is not None) else []):   # a date with no school near it is not a graduation
        p = at(i)
        m = re.search(r"(?:expected|anticipated|exp\.?|graduat(?:ed|ing|ion)(?: date)?|class of|degree expected)\s*:?\s*(%s)" % _ONE, p, re.I)
        if m:
            grad = (_ym(m.group(1)), "high", lines[i])
            break
        m = DATE_RANGE.search(p)
        if m:
            end = _ym(m.group(2))
            if end and end != "present":
                grad = (end, "medium", lines[i])
                break
            if end == "present":
                continue
        m = DATE_ONE.search(p)
        if m and grad is None and (school_i is None or abs(i - school_i) <= 2):
            grad = (_ym(m.group(1)), "medium", lines[i])
    if grad and grad[0] and grad[0] != "present":
        y, mo = grad[0]
        out["grad"] = _field("%04d-%02d" % (y, mo or 5), grad[1] if mo else "low", grad[2])    # a year alone: May of that year, to be checked
    for i in (pool if idx else range(len(lines))):
        m = GPA.search(lines[i])
        if m:
            val, scale = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            try:
                v = float(val)
                sc = float(scale) if scale else 4.0
            except ValueError:
                continue
            if sc in (4.0, 4.3, 4.33, 4.5) and 0 < v <= sc:
                out["gpa"] = _field(val, "high", lines[i])
                break
    return out


def _split_header(s):
    return [p.strip(" ,.;:") for p in re.split(r"\s+[|•·@]\s+|\s{2,}|\s[-–—]\s|,\s+|\s+at\s+|\t", s) if p.strip(" ,.;:")]


def _experience(lines, secs, inline):
    idx = secs.get("experience", [])
    if not idx:
        return {}
    entries = []
    for pos, i in enumerate(idx):
        ln = inline.get(i, lines[i])
        m = DATE_RANGE.search(ln)
        if not m:
            continue
        start, end = _ym(m.group(1)), _ym(m.group(2))
        if not start:
            continue
        header = []
        rest = _strip_location(_strip_dates(_plain(ln)))
        if rest:
            header.append((rest, lines[i]))
        # the job's other header lines: just above the dates (title and employer first), or just below (dates first)
        above = [j for j in idx[max(0, pos - 2):pos]]
        below = [j for j in idx[pos + 1:pos + 3]]
        for j in reversed(above):
            t = lines[j]
            if not t.strip() or _is_bullet(t) or DATE_RANGE.search(t) or len(_plain(t)) > 90 or re.search(r"[.!?]$", _plain(t)):
                break
            header.insert(0, (_strip_location(_plain(t)), t))
        if len(header) < 2:
            for j in below:
                t = lines[j]
                if not t.strip() or _is_bullet(t) or DATE_RANGE.search(t) or len(_plain(t)) > 90 or re.search(r"[.!?]$", _plain(t)):
                    break
                header.append((_strip_location(_plain(t)), t))
                if len(header) >= 2:
                    break
        entries.append({"start": start, "end": end, "header": [h for h in header if h[0]], "date_line": lines[i]})
    if not entries:
        return {}
    best = max(enumerate(entries), key=lambda e: (_sortkey(e[1]["end"]), _sortkey(e[1]["start"]), -e[0]))[1]
    out = {"job_start": _field(_fmt(best["start"]), "high", best["date_line"]),
           "job_end": _field(_fmt(best["end"]), "high", best["date_line"])}
    pieces = []
    for text, src in best["header"]:
        for p in _split_header(text):
            if p and not DATE_ONE.fullmatch(p) and len(p) <= 80:
                pieces.append((p, src))
    # a job title ends with the role ("... Intern", "... Engineer"); an employer often ends with "Inc", "Labs", "Bank" ...
    def last(p):
        return re.sub(r"[^a-z&.-]", "", p.lower().split()[-1]) if p.split() else ""

    def is_title(p):
        return (2 if last(p).rstrip("s") in TITLE_WORDS or last(p) in TITLE_WORDS else 0) + (1 if _has_word(p, TITLE_WORDS) else 0) - (2 if last(p) in ORG_WORDS else 0)

    def is_org(p):
        return (2 if last(p) in ORG_WORDS else 0) + (1 if _has_word(p, ORG_WORDS) else 0) - (2 if last(p).rstrip("s") in TITLE_WORDS else 0)

    title = max(pieces, key=lambda x: is_title(x[0]), default=None)
    if title and is_title(title[0]) <= 0:
        title = None
    others = [x for x in pieces if title is None or x[0] != title[0]]
    employer = max(others, key=lambda x: is_org(x[0]), default=None)
    sure = bool(title and employer and is_org(employer[0]) > 0)
    if employer and is_org(employer[0]) <= 0:
        employer = others[0]                                        # no company word: the first other part of the header
    if title is None and employer:
        rest = [x for x in others if x[0] != employer[0]]
        title = rest[0] if rest else None
    if title:
        out["job_title"] = _field(_smart_case(title[0]) if title[0].islower() else title[0], "high" if sure else "medium", title[1])
    if employer:
        out["employer"] = _field(_smart_case(employer[0]) if employer[0].islower() else employer[0], "high" if sure else "medium", employer[1])
    return out


def _location(lines, order):
    for i in order:
        ln = lines[i]
        if EMAIL.search(ln) and not re.search(r"[|•·]", ln):
            pass
        for chunk in re.split(r"\s+[|•·]\s+|\s{3,}", ln):
            m = LOC_US.search(chunk) or LOC_US_NAME.search(chunk)
            if m:
                city = re.sub(r"^(?:Address|Location|Based in|Lives in)\s*:?\s*", "", m.group(1)).strip()
                state = m.group(2) if len(m.group(2)) == 2 else _STATE_BY_NAME.get(m.group(2).lower(), "")
                if city.lower() in ("remote", "hybrid") or not state:
                    continue
                z = m.group(3) or ""
                f = _field(", ".join([city, (state + (" " + z if z else ""))]), "high" if z else "medium", ln)
                f.update({"city": city, "state": state, "zip": z})
                return f
            m = LOC_INTL.search(chunk)
            if m:
                city = re.sub(r"^(?:Address|Location|Based in)\s*:?\s*", "", m.group(1)).strip()
                f = _field("%s, %s" % (city, m.group(2)), "low", ln)
                f.update({"city": city, "state": "", "zip": "", "country": m.group(2)})
                return f
    return None


def extract(text):
    """The fields found in a resume's plain text. Every field is optional."""
    lines = [ln.rstrip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln.strip() or True]
    secs, inline = split_sections(lines)
    nonblank = [i for i, ln in enumerate(lines) if ln.strip()]
    top = [i for i in nonblank if i in set(secs.get("top", []))] or nonblank[:12]
    contact_order = top + [i for i in nonblank if i not in set(top)]
    f = {}

    m = None
    for i in contact_order:
        m = EMAIL.search(lines[i])
        if m:
            f["email"] = _field(m.group(0).rstrip("."), "high", lines[i])
            break
    ph = _phone(lines, contact_order)
    if ph:
        f["phone"] = ph
    for i in contact_order:
        m = LINKEDIN.search(lines[i])
        if m:
            f["linkedin"] = _field("https://www.linkedin.com/%s/%s" % (m.group(1).lower(), m.group(2).rstrip("/.")), "high", lines[i])
            break
    for i in contact_order:
        m = GITHUB.search(lines[i])
        if m and m.group(1).lower() not in ("features", "about", "pricing", "orgs", "topics"):
            f["portfolio"] = _field("https://github.com/" + m.group(1), "high", lines[i])
            break
    if "portfolio" not in f:
        email_host = f["email"]["value"].split("@")[1].lower() if "email" in f else ""
        for i in contact_order[:40]:
            ln = lines[i]
            for m in URL.finditer(ln):
                host = m.group(1).lower()
                if "linkedin." in host or "github.com" in host or host == email_host or host.split("/")[0] in (
                        "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "google.com"):
                    continue
                if EMAIL.search(ln) and ("@" + host.split("/")[0]) in ln:
                    continue
                f["portfolio"] = _field("https://" + m.group(1).rstrip("/.)"), "medium", ln)
                break
            if "portfolio" in f:
                break

    # the name: a short line of two to four capitalised words near the top (or "Name: ...")
    for i in contact_order[:30]:
        ln = _plain(lines[i])
        lm = re.match(r"^(?:full\s+)?name\s*:\s*(.+)$", ln, re.I)
        if lm and _name_like(lm.group(1)):
            f["name"] = _field(_name_like(lm.group(1)), "high", lines[i])
            break
    if "name" not in f:
        # the first likely line wins, unless a later one matches the email address (a two-column PDF often puts the sidebar first)
        local = re.sub(r"[^a-z]", "", f["email"]["value"].split("@")[0].lower()) if "email" in f else ""
        cands = []
        for rank, i in enumerate(contact_order[:40]):
            cand = _name_like(re.split(r"\s+[|•·]\s+|\s{3,}", _plain(lines[i]))[0])
            if cand:
                parts = [re.sub(r"[^a-z]", "", p.lower()) for p in re.split(r"[ \-]", cand)]
                agree = bool(local) and sum(1 for p in parts if len(p) > 2 and p in local) >= 1
                cands.append((rank, i, cand, agree))
        pick = next((c for c in cands if c[3]), cands[0] if cands else None)
        if pick:
            rank, i, cand, agree = pick
            f["name"] = _field(cand, "high" if rank == 0 or agree else "medium" if rank < 8 else "low", lines[i])

    # the headline: a title-like line just under the name, before the first section
    if "name" in f:
        start = next((k for k, i in enumerate(contact_order) if lines[i] == f["name"]["line"] or _plain(lines[i]) == f["name"]["line"]), None)
        cands = contact_order[start + 1:start + 5] if start is not None else []
        top_set = set(secs.get("top", []))
        for i in cands:
            ln = _plain(lines[i])
            if top_set and i not in top_set:                         # a job line under Experience is not a headline
                break
            if not ln or heading(ln) or len(ln) > 120 or DATE_RANGE.search(ln):
                continue
            first = re.split(r"\s+[|•·]\s+", ln)[0] if _contact_line(ln) else ln
            if _contact_line(first) or LOC_US.fullmatch(first.strip()) or re.search(r"[.!?]$", first):
                continue
            if _has_word(first, TITLE_WORDS) or "|" in ln:
                f["headline"] = _field(first.strip(" |"), "medium", lines[i])
                break

    # the summary: the Summary, Profile, Objective or About section, as one paragraph
    sm = [inline.get(i, lines[i]) for i in secs.get("summary", []) if lines[i].strip() or i in inline]
    if sm:
        para = []
        for ln in sm:
            if not ln.strip():
                if para:
                    break
                continue
            para.append(_plain(ln))
        txt = re.sub(r"\s+", " ", " ".join(para)).strip()
        if len(txt) >= 25:
            if len(txt) > 600:
                txt = txt[:600].rsplit(" ", 1)[0].rstrip(",;") + "…"
            f["summary"] = _field(txt, "high", sm[0])
    else:
        for i in secs.get("top", []):
            ln = _plain(lines[i])
            if len(ln) >= 100 and len(ln.split()) >= 15 and not _contact_line(ln):
                f["summary"] = _field(ln[:600], "low", lines[i])
                break

    f.update(_education(lines, secs, inline))
    f.update(_experience(lines, secs, inline))
    sk = _skills(lines, secs, inline)
    if sk:
        conf = "high" if any(c == "high" for _, c, _l in sk) else "medium"
        f["skills"] = _field([s for s, _c, _l in sk], conf, sk[0][2])
        f["skills"]["lines"] = list(dict.fromkeys(re.sub(r"\s+", " ", l).strip()[:200] for _s, _c, l in sk))[:6]
    top_set = set(secs.get("top", []))
    loc = _location(lines, [i for i in contact_order if i in top_set] if top_set else contact_order[:25])   # where the person lives, not a job's city
    if loc:
        f["location"] = loc
    return f


def parse(data, name="", ctype=""):
    """Read a resume file and find its fields. Raises ResumeError (with a sentence for the person) when it cannot be read."""
    kind, text = read_text(data, name, ctype)
    fields = extract(text)
    return {"kind": kind, "text": text, "fields": fields}


# ---------------------------------------------------------------------------------------------------------------------------------
# POST /api/profile/resume
# ---------------------------------------------------------------------------------------------------------------------------------

MAX_BODY = MAX_BYTES * 4 // 3 + 64 * 1024      # the file as base64 text (a third bigger) plus the rest of the request


def _from_json(body):
    try:
        p = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        _fail("bad_request")
    r = p.get("resume") if isinstance(p, dict) else None
    if not isinstance(r, dict):
        _fail("bad_request")
    name = r.get("name") if isinstance(r.get("name"), str) else ""
    m = re.match(r"^data:([\w/+.-]*);base64,([A-Za-z0-9+/=\s]+)$", r.get("data") if isinstance(r.get("data"), str) else "")
    if not m:
        _fail("bad_request")
    if len(m.group(2)) > MAX_BYTES * 4 // 3 + 8:
        _fail("too_big")
    try:
        data = base64.b64decode(re.sub(r"\s", "", m.group(2)), validate=True)
    except ValueError:
        _fail("bad_request")
    return data, name[:200], m.group(1)


def _from_multipart(body, content_type):
    try:
        msg = BytesParser(policy=_email_policy).parsebytes(b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + body)
    except Exception:
        _fail("bad_request")
    if not msg.is_multipart():
        _fail("bad_request")
    for part in msg.iter_parts():
        if part.get_param("name", header="content-disposition") in ("file", "resume"):
            data = part.get_payload(decode=True) or b""
            return data, (part.get_filename() or "")[:200], part.get_content_type()
    _fail("bad_request")


def handle(body, content_type):
    """(status, answer) for one upload. The answer holds the fields only: never the file and never the full text."""
    try:
        if len(body) > MAX_BODY:
            _fail("too_big")
        ct = (content_type or "").lower()
        data, name, ctype = _from_multipart(body, content_type) if ct.startswith("multipart/form-data") else _from_json(body)
        res = parse(data, name, ctype)
    except ResumeError as e:
        return (413 if e.code == "too_big" else 422 if e.code in ("scanned", "unreadable", "encrypted", "image", "old_doc", "wrong_type", "empty", "slow")
                else 503 if e.code == "no_pdf" else 400), {"error": e.message, "code": e.code}
    fields = res["fields"]
    return 200, {"ok": True, "kind": res["kind"], "fields": fields, "found": len(fields), "chars": len(res["text"])}


if __name__ == "__main__":                                          # python resume_parse.py my-resume.pdf  -> the fields, to check by eye
    if len(sys.argv) != 2:
        sys.exit("usage: python resume_parse.py FILE")
    with open(sys.argv[1], "rb") as fh:
        try:
            out = parse(fh.read(), os.path.basename(sys.argv[1]))
        except ResumeError as e:
            sys.exit("%s: %s" % (e.code, e.message))
    print(json.dumps(out["fields"], indent=2, ensure_ascii=False))
