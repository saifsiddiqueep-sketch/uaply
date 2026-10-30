"""Writes the thirteen made-up resumes in tools/fixtures/resumes/ that tools/test-resume.py reads (and the PDF and Word files among them).
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

# a business student's one-page PDF: right-aligned dates, bullets, a club office under "Leadership & Activities" (not a job), skills
# with notes in brackets "Microsoft Excel (pivot tables, VLOOKUP)", and a part-time job title "(part-time)"
BUSINESS = [
    ("Jordan Álvarez", 18), ("Philadelphia, PA 19104 | (267) 555-0182 | jordan.alvarez@example.edu", 9), ("linkedin.com/in/jordan-alvarez-example", 9),
    ("", 9), ("EDUCATION", 11), ("Drexel University, LeBow College of Business                              Philadelphia, PA", 10),
    ("Bachelor of Science in Business Administration, Marketing and Business Analytics      Expected June 2028", 10),
    ("GPA: 3.58/4.00  |  Dean's List (4 terms)", 10), ("", 9), ("EXPERIENCE", 11),
    ("Marketing Co-op                                                                        Apr 2025 - Sep 2025", 10),
    ("Schuylkill Health Partners, Philadelphia, PA", 10), ("• Ran weekly email campaigns to 18,000 patients; open rate up from 21% to 29%", 10),
    ("Barista and Shift Lead (part-time)                                                     Sep 2023 - Present", 10),
    ("Lancaster Avenue Coffee Co., Philadelphia, PA", 10), ("• Train new baristas and close the store three nights a week", 10),
    ("", 9), ("LEADERSHIP & ACTIVITIES", 11),
    ("Vice President of Events, Drexel American Marketing Association                       2024 - Present", 10),
    ("• Planned 6 speaker nights with Philadelphia agencies", 10), ("", 9), ("SKILLS", 11),
    ("Technical: Microsoft Excel (pivot tables, VLOOKUP), Tableau, SQL (basic), Canva, HubSpot", 10),
    ("Languages: English (native), Spanish (fluent)", 10),
]

# a first job: a high-school senior with no work history yet (school, activities, volunteering, skills), one column; the phone written
# "+1 215.555.0134" and the address "Philadelphia, PA 19104" (card 181: the form most phones and templates use)
FIRSTJOB = [
    ("Destiny Williams", 18), ("+1 215.555.0134  |  destiny.williams@example.com  |  Philadelphia, PA 19104", 9), ("", 9),
    ("OBJECTIVE", 11), ("High school senior looking for a part-time job in retail or food service on weekends and after school.", 9), ("", 9),
    ("EDUCATION", 11), ("Central High School, Philadelphia, PA                                   Expected June 2027", 10),
    ("High School Diploma  |  Honor Roll (3 semesters)", 10), ("", 9),
    ("ACTIVITIES", 11), ("Member, Key Club                                                          2024 - Present", 10),
    ("• Help run the fall canned food drive", 10), ("Junior Varsity Track and Field                                            2023 - 2025", 10), ("", 9),
    ("SKILLS", 11), ("Customer Service, Cash Handling, Microsoft Excel, Spanish, Teamwork", 10),
]

# almost nothing: a name and an email, so every other answer must come back empty (card 181: nothing is guessed or padded)
SPARSE = """Riley Morgan
riley.morgan@example.com
"""

# a senior person's five-page PDF: the name in ALL CAPS, "PROFESSIONAL EXPERIENCE", the latest job on page 1,
# education and skills on page 5 (card 181: long resumes)
SENIOR_PAGES = [
    [("PRIYA RAMAN", 18), ("Director of Supply Chain Operations", 12),
     ("Pittsburgh, PA 15222  |  (412) 555-0163  |  priya.raman@example.com  |  linkedin.com/in/priya-raman-example", 9), ("", 9),
     ("SUMMARY", 11), ("Operations leader with eighteen years of experience running regional distribution networks and warehouse teams.", 9), ("", 9),
     ("PROFESSIONAL EXPERIENCE", 11),
     ("Director of Supply Chain Operations                                         Jan 2021 - Present", 10),
     ("Allegheny Freight Systems, Pittsburgh, PA", 10)] +
    [("• Lead %s across four distribution centers and 310 staff" % w, 9) for w in
     ("inbound planning", "outbound routing", "carrier contracts", "safety programs", "budget reviews", "hiring plans",
      "vendor scorecards", "peak season staffing", "returns handling", "cycle counting", "yard management", "transport audits")],
    [("Senior Operations Manager                                                   Mar 2016 - Dec 2020", 10),
     ("Three Rivers Distribution Co., Pittsburgh, PA", 10)] +
    [("• Ran the %s program for a 600,000 square foot building" % w, 9) for w in
     ("slotting", "labor planning", "pick accuracy", "dock scheduling", "training", "overtime", "inventory control", "quality",
      "shrink", "automation pilot", "space planning", "night shift", "safety audit", "process mapping", "cost per unit")],
    [("Operations Manager                                                          Jun 2011 - Feb 2016", 10),
     ("Keystone Parcel Inc., Harrisburg, PA", 10)] +
    [("• Managed %s for the central Pennsylvania region" % w, 9) for w in
     ("daily dispatch", "route planning", "driver schedules", "claims", "fleet upkeep", "customer escalations",
      "weekly reporting", "new hire training", "fuel costs", "holiday surge", "hub transfers", "billing audits")],
    [("Logistics Analyst                                                           Jul 2007 - May 2011", 10),
     ("Monongahela Supply LLC, Pittsburgh, PA", 10)] +
    [("• Built reports on %s for the logistics director" % w, 9) for w in
     ("freight spend", "on-time delivery", "carrier performance", "lane volumes", "damage rates", "detention time",
      "backorders", "forecast error", "stock turns", "supplier lead times")] +
    [("", 9), ("AWARDS", 11), ("Regional Operations Leader of the Year, Allegheny Freight Systems, 2023", 9)],
    [("EDUCATION", 11), ("Carnegie Mellon University, Pittsburgh, PA", 10),
     ("Master of Business Administration                                            May 2011", 10),
     ("Penn State University, University Park, PA", 10),
     ("Bachelor of Science in Industrial Engineering                                May 2007", 10), ("", 9),
     ("SKILLS", 11), ("Lean Six Sigma, SAP, SQL, Excel, Tableau, Forecasting, Budgeting", 10)],
]

# an hourly retail worker's one-page PDF: "WORK HISTORY", no LinkedIn, no summary (card 181)
RETAIL = [
    ("Marcus Bell", 18), ("Camden, NJ 08102  |  856-555-0127  |  marcus.bell@example.com", 9), ("", 9),
    ("WORK HISTORY", 11), ("Sales Associate                                                    Jun 2023 - Present", 10),
    ("Riverside Outfitters, Cherry Hill, NJ", 10), ("• Run the register and open the store three mornings a week", 10),
    ("• Restock the floor and count inventory every Sunday", 10),
    ("Cashier                                                            Aug 2021 - May 2023", 10),
    ("Corner Market Grocery, Camden, NJ", 10), ("• Handled about 200 transactions a shift", 10), ("", 9),
    ("EDUCATION", 11), ("Camden High School, Camden, NJ                                     June 2021", 10), ("High School Diploma", 10), ("", 9),
    ("SKILLS", 11), ("Cash Handling, Customer Service, Inventory, Spanish", 10),
]

# accented letters in a plain text file, "Work History", a line cook (card 181)
NUNEZ = """José Núñez
Line Cook
Miami, FL 33130 · (305) 555-0119 · jose.nunez@example.com

Work History
Line Cook — Calle Ocho Kitchen, Miami, FL        Mar 2022 – Present
- Run the grill station for 150 covers a night
Prep Cook — Biscayne Bistro, Miami, FL           2019 – 2022
- Prepped vegetables and sauces for lunch service

Education
Miami Dade College — Associate in Culinary Arts, 2019

Skills
Food Safety, Knife Skills, Inventory, Spanish
"""

# a Word resume built on a table: a Vietnamese name, the email and LinkedIn address in the page header, no phone number (card 181)
LAN_HEADER = ["lan.nguyen@example.com  |  https://www.linkedin.com/in/lan-nguyen-example"]
LAN_TOP = ["Nguyễn Thị Lan"]
LAN_LEFT = ["CONTACT", "Houston, TX 77036", "", "SKILLS", "Inventory", "Customer Service", "Vietnamese", "Excel"]
LAN_RIGHT = ["PROFESSIONAL EXPERIENCE", "Pharmacy Technician\tAug 2022 – Present", "Bayou City Pharmacy, Houston, TX",
             "Filled about 300 prescriptions a day and answered patients' questions at the counter",
             "Cashier\t2020 – 2022", "Bellaire Market, Houston, TX", "", "EDUCATION", "Houston Community College",
             "Certificate in Pharmacy Technology, May 2022"]

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


def pdf_pages(path, pages):
    """A PDF of several pages (Helvetica, WinAnsi), each page from its own (x, y, size, text) runs."""
    n = len(pages)
    kids = " ".join("%d 0 R" % (4 + 2 * i) for i in range(n)).encode()   # 1 catalog, 2 pages, 3 font, then a page and its contents each
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % n,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    for i, runs in enumerate(pages):
        ops = []
        for x, y, size, text in runs:
            if not text:
                continue
            b = text.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            ops.append(b"BT /F1 %d Tf %d %d Td (" % (size, x, y) + b + b") Tj ET")
        stream = b"\n".join(ops)
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (5 + 2 * i))
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for k, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % k + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    with open(path, "wb") as f:
        f.write(bytes(out))


def docx_table(path, header, top, left, right):
    """A Word file laid out like many templates: a page header, a paragraph on top, then a two-column table.
    Each zip entry has a fixed date, so the bytes are the same on every run."""
    def p(t):
        runs = "<w:r><w:tab/></w:r>".join('<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % escape(s) for s in t.split("\t"))
        return "<w:p>%s</w:p>" % runs
    ns = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
    cells = "<w:tc>%s</w:tc><w:tc>%s</w:tc>" % ("".join(p(t) for t in left), "".join(p(t) for t in right))
    body = ("".join(p(t) for t in top) + "<w:tbl><w:tr>%s</w:tr></w:tbl>" % cells +
            '<w:sectPr><w:headerReference w:type="default" r:id="rId9"/></w:sectPr>')
    doc = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document %s><w:body>%s</w:body></w:document>' % (ns, body)
    hdr = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr %s>%s</w:hdr>' % (ns, "".join(p(t) for t in header))
    parts = (
        ("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
         '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
         '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/></Types>'),
        ("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'),
        ("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/></Relationships>'),
        ("word/document.xml", doc), ("word/header1.xml", hdr))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts:
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)


def main():
    os.makedirs(HERE, exist_ok=True)
    for name, text in (("student.txt", STUDENT), ("international.txt", INTERNATIONAL), ("messy.txt", MESSY), ("sparse.txt", SPARSE),
                       ("nunez.txt", NUNEZ)):
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
    runs, y = [], 750
    for text, size in BUSINESS:
        runs.append((50, y, size, text))
        y -= size + 6
    pdf(os.path.join(HERE, "business.pdf"), runs)
    runs, y = [], 750
    for text, size in FIRSTJOB:
        runs.append((50, y, size, text))
        y -= size + 6
    pdf(os.path.join(HERE, "firstjob.pdf"), runs)
    pages = []
    for page in SENIOR_PAGES:
        runs, y = [], 750
        for text, size in page:
            runs.append((50, y, size, text))
            y -= size + 6
        pages.append(runs)
    pdf_pages(os.path.join(HERE, "senior5page.pdf"), pages)
    runs, y = [], 750
    for text, size in RETAIL:
        runs.append((50, y, size, text))
        y -= size + 6
    pdf(os.path.join(HERE, "retail.pdf"), runs)
    docx_table(os.path.join(HERE, "lantable.docx"), LAN_HEADER, LAN_TOP, LAN_LEFT, LAN_RIGHT)
    print("wrote 13 resumes to", HERE)


if __name__ == "__main__":
    main()
