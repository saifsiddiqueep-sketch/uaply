"""Writes the six made-up resumes in tools/fixtures/resumes/ that tools/test-resume.py reads (and the PDF and Word files among them).
    python tools/make-resume-fixtures.py
Every person, school, employer, phone number and address here is invented. The PDF and Word files are written by hand with the standard
library only, so this needs nothing installed. The expected answers for each resume are in tools/fixtures/resumes/expected.json."""
import os
import zipfile
from xml.sax.saxutils import escape

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "resumes")

STUDENT = """MAYA PATEL
Philadelphia, PA 19104 | (215) 555-0134 | maya.patel@example.edu
linkedin.com/in/maya-patel-example | github.com/mayapatel-example

EDUCATION
Temple University, Philadelphia, PA
B.S. in Computer Science, Minor in Mathematics          Expected May 2027
GPA: 3.72/4.00
Relevant coursework: Data Structures, Algorithms, Databases

EXPERIENCE
Software Engineering Intern                              Jun 2025 – Aug 2025
Brightline Labs, Philadelphia, PA
• Built a React dashboard used by 40 internal analysts
• Wrote Python scripts that cut a weekly report from 3 hours to 10 minutes

Teaching Assistant                                       Jan 2025 – May 2025
Temple University Department of Computer Science
• Held office hours for 60 students in Intro to Programming

PROJECTS
Campus Eats – a Flask app that lists late-night food near campus

SKILLS
Languages: Python, Java, JavaScript, SQL
Tools: React, Flask, Git, Docker, Figma
"""

INTERNATIONAL = """Aarav Sharma
Data Analyst | Python · SQL · Tableau
London, United Kingdom  •  +44 20 7946 0958  •  aarav.sharma@example.co.uk
www.aaravsharma-example.dev

PROFILE
Data analyst with three years of experience turning messy operational data into dashboards that finance and operations teams use every
day. Looking for an analytics role in the United States; authorised to work there from 2027.

WORK EXPERIENCE
Data Analyst — Northwind Logistics Ltd, London                      Sept 2023 – Present
- Built Tableau dashboards for 12 regional managers
- Automated monthly reconciliation in Python (pandas), saving 2 days a month

Junior Analyst — Harbour Analytics Group, Manchester                 07/2021 – 08/2023
- Cleaned and joined shipment data in SQL

EDUCATION
University of Manchester
MSc Business Analytics, 2021
BSc Economics, 2020

SKILLS
Python; SQL; Tableau; Excel; Power BI; Statistics
"""

MESSY = """resume

   jordan   o'neil-reyes
jordan.oneil.reyes@example.com   ||   cell: 267.555.0199
Austin, Texas 78701

about me:
i am a hard working person who likes customers and computers and is looking for a full time job helping people with technology.

work history
  * 2022 - now    help desk technician at Lone Star Credit Union, austin tx
      -   reset passwords, set up laptops for 80 staff
  * 2019 - 2022   cashier, H-E-B grocery
      - handled the register and the self checkout

Skills: windows, active directory, customer service, Excel, office 365 ,  networking
Education: Austin Community College — A.A.S. Network Administration (2021)
"""

DATES_FIRST = [
    ("CHRIS NAKAMURA", 16, 0),
    ("Product Designer", 12, 0),
    ("Seattle, WA 98101  |  chris.nakamura@example.com  |  (206) 555-0172  |  chrisnakamura-example.design", 9, 0),
    ("", 9, 0),
    ("SUMMARY", 11, 0),
    ("Product designer who has shipped mobile banking and health apps used by millions. I run research, prototype in Figma", 9, 0),
    ("and work closely with engineers until the details are right.", 9, 0),
    ("", 9, 0),
    ("PROFESSIONAL EXPERIENCE", 11, 0),
    ("2023 - Present    Senior Product Designer, Evergreen Health Inc.", 9, 0),
    ("• Led the redesign of appointment booking; completion rose 18%", 9, 0),
    ("2020 - 2023    Product Designer, Cascade Bank", 9, 0),
    ("• Designed the mobile check deposit flow", 9, 0),
    ("", 9, 0),
    ("EDUCATION", 11, 0),
    ("2016 - 2020    University of Washington, Bachelor of Design in Interaction Design", 9, 0),
    ("", 9, 0),
    ("SKILLS", 11, 0),
    ("Figma  |  Prototyping  |  User Research  |  Accessibility  |  Design Systems  |  HTML  |  CSS", 9, 0),
]

# two columns: a sidebar on the left (written first, as most templates write it) and the main column on the right
TWO_LEFT = [
    ("CONTACT", 11), ("sam.okafor@example.com", 8), ("(312) 555-0148", 8), ("Chicago, IL 60607", 8),
    ("linkedin.com/in/samokafor-example", 8), ("", 8), ("SKILLS", 11), ("TypeScript", 8), ("Node.js", 8), ("PostgreSQL", 8), ("AWS", 8),
    ("Kubernetes", 8), ("GraphQL", 8), ("", 8), ("EDUCATION", 11), ("University of Illinois", 8), ("Urbana-Champaign", 8),
    ("Bachelor of Science in", 8), ("Computer Engineering", 8), ("2014 - 2018", 8),
]
TWO_RIGHT = [
    ("Sam Okafor", 18), ("Backend Engineer", 12), ("", 9), ("SUMMARY", 11),
    ("Backend engineer with six years of experience building payment", 9), ("and logistics APIs that handle millions of requests a day.", 9),
    ("", 9), ("EXPERIENCE", 11), ("Senior Software Engineer", 10), ("Lakeshore Payments, Chicago, IL", 9), ("March 2022 - Present", 9),
    ("• Moved card authorization to Kubernetes with zero downtime", 9), ("• Cut p99 latency from 900 ms to 180 ms", 9), ("", 9),
    ("Software Engineer", 10), ("Midway Freight Technologies", 9), ("July 2018 - February 2022", 9), ("• Built the shipment tracking API in Node.js", 9),
]

NEWGRAD_PARAS = [
    "Elena Rossi", "Marketing Coordinator", "Boston, MA 02115 · elena.rossi@example.com · 617-555-0110", "", "Objective",
    "Recent marketing graduate who has run social campaigns for a nonprofit and a campus startup, looking for a full-time marketing role "
    "where I can grow into content strategy.", "", "Work Experience", "Marketing Intern\tJune 2024 – Present", "Harborview Community Foundation, Boston, MA",
    "Planned and posted 5 social posts a week; follower count grew 35%", "Sales Associate\tSeptember 2022 – May 2024", "Newbury Books, Boston, MA",
    "", "Education", "Northeastern University, Boston, MA", "Bachelor of Science in Marketing, May 2025", "GPA 3.5", "",
    "Skills", "HubSpot, Canva, Google Analytics, Copywriting, Social Media, Mailchimp, Excel",
]


def pdf(path, runs):
    """A one-page PDF (Helvetica, WinAnsi) from (x, y, size, text) runs, written in the order given."""
    ops = []
    for x, y, size, text in runs:
        if not text:
            continue
        b = text.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        ops.append(b"BT /F1 %d Tf %d %d Td (" % (size, x, y) + b + b") Tj ET")
    stream = b"\n".join(ops)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for n, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % n + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    with open(path, "wb") as f:
        f.write(bytes(out))


def docx(path, paras):
    """A minimal Word file: one paragraph per item, a tab character where the text has \\t."""
    def p(t):
        runs = "<w:r><w:tab/></w:r>".join('<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % escape(s) for s in t.split("\t"))
        return "<w:p>%s</w:p>" % runs
    body = "".join(p(t) for t in paras)
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           "<w:body>%s</w:body></w:document>" % body)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", doc)


def main():
    os.makedirs(HERE, exist_ok=True)
    for name, text in (("student.txt", STUDENT), ("international.txt", INTERNATIONAL), ("messy.txt", MESSY)):
        with open(os.path.join(HERE, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    docx(os.path.join(HERE, "newgrad.docx"), NEWGRAD_PARAS)
    runs, y = [], 750
    for text, size, _ in DATES_FIRST:
        runs.append((50, y, size, text))
        y -= size + 6
    pdf(os.path.join(HERE, "datesfirst.pdf"), runs)
    runs, y = [], 750
    for text, size in TWO_LEFT:
        runs.append((40, y, size, text))
        y -= size + 6
    y = 750
    for text, size in TWO_RIGHT:
        runs.append((220, y, size, text))
        y -= size + 6
    pdf(os.path.join(HERE, "twocolumn.pdf"), runs)
    print("wrote 6 resumes to", HERE)


if __name__ == "__main__":
    main()
