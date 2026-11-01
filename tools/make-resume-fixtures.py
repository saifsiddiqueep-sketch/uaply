"""Writes the forty-two made-up resumes in tools/fixtures/resumes/ that tools/test-resume.py reads (and the PDF and Word files among them).
    python tools/make-resume-fixtures.py
Every person, school, employer, phone number and address here is invented. The PDF and Word files are written by hand with the standard
library only, so this needs nothing installed. The expected answers for each resume are in tools/fixtures/resumes/expected.json."""
import os
import re
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

# no headings, a "Sales Associate" job and no school (card 181): "Example Store" was read as the major (an Associate degree in
# Example Store); a major comes only from an education line, so here there is none
STORE = """Dana Example
dana.example@example.com · (267) 555-0188
Philadelphia, PA 19104
Sales Associate, Example Store, Philadelphia, PA        June 2023 – Present
Helped about 80 customers a shift and kept the floor stocked
Cashier, Sample Market, Philadelphia, PA        2021 – 2023
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

# ---------------------------------------------------------------------------------------------------------------------------------
# The wider set (card 181, "keep testing with uploaded resumes"): the layouts, names, phones, places and section names real uploads have.
# Every person, employer, number and street here is made up; phone numbers use 555-01xx (US) or 07700 900xxx (UK drama range).
# ---------------------------------------------------------------------------------------------------------------------------------

# a Google Docs export (.docx): "Company, City — Title" with the dates in capitals on the next line, the street address and a phone
# extension, skills one per line
GDOCS_PARAS = [
    "Olivia Brennan-Hayes", "Operations Coordinator", "1200 Example Street, Columbus, OH 43215", "(614) 555-0142 ext. 12",
    "olivia.brennanhayes@example.com", "", "EXPERIENCE", "Buckeye Example Logistics, Columbus — Operations Coordinator", "MARCH 2022 - PRESENT",
    "Scheduled 40 drivers a day and answered carrier calls.", "Scioto Example Supply, Dublin, OH — Shipping Clerk", "JUNE 2019 - FEBRUARY 2022",
    "Packed and labeled about 300 orders a day.", "", "EDUCATION",
    "Columbus State Community College, Columbus — Associate of Applied Science in Supply Chain Management", "AUGUST 2017 - MAY 2019", "",
    "SKILLS", "Microsoft Excel", "Scheduling", "Inventory", "Customer Service", "", "AWARDS", "Employee of the Month, March 2023",
]

# a Word file with the name and email in the page header and the phone and city in the page footer; "Employment History";
# "Title, Department" on the dates line and the employer below it
WORDHF_HEADER = ["Kwame Mensah", "kwame.mensah@example.com | linkedin.com/in/kwame-mensah-example"]
WORDHF_FOOTER = ["Kwame Mensah · Phone: 704-555-0163 · Charlotte, NC 28202"]
WORDHF_PARAS = [
    "SUMMARY", "Registered nurse with seven years of experience in emergency and cardiac care, calm under pressure and kind to every patient.",
    "", "EMPLOYMENT HISTORY", "Registered Nurse, Emergency Department\tJan 2021 – Present", "Queen City Example Hospital, Charlotte, NC",
    "• Triage about 30 patients a shift", "Staff Nurse\tJul 2017 – Dec 2020", "Piedmont Example Medical Center, Gastonia, NC", "",
    "EDUCATION", "University of North Carolina at Charlotte", "Bachelor of Science in Nursing, May 2017", "",
    "LICENSES & CERTIFICATIONS", "Registered Nurse (NC), BLS, ACLS", "", "SKILLS", "Patient Care; Triage; Epic EHR; IV Therapy",
]

# a Canva-style two-column PDF: the main column on the left written first, the sidebar (contact, education, skills) on the right after it
CANVA_MAIN = [("HANNAH LINDQVIST", 22), ("GRAPHIC DESIGNER", 12), ("", 9), ("ABOUT ME", 11),
              ("Graphic designer who turns brand ideas into packaging, posters and social", 9), ("content that people stop scrolling for.", 9),
              ("", 9), ("WORK EXPERIENCE", 11), ("Junior Graphic Designer", 10), ("Northern Example Studio | 2023 - Present", 9),
              ("• Designed packaging for 12 food brands", 9), ("Design Intern", 10), ("Fjord Example Agency | 2022 - 2023", 9),
              ("• Made social posts and event posters", 9)]
CANVA_SIDE = [("CONTACT", 11), ("+1 (503) 555-0187", 8), ("hannah.lindqvist@example.com", 8), ("Portland, OR 97205", 8),
              ("hannahlindqvist-example.com", 8), ("", 8), ("EDUCATION", 11), ("Pacific Northwest College of Art", 8), ("BFA in Graphic Design", 8),
              ("2018 - 2022", 8), ("", 8), ("SKILLS", 11), ("Adobe Illustrator", 8), ("Photoshop", 8), ("InDesign", 8), ("Typography", 8),
              ("Branding", 8), ("", 8), ("LANGUAGES", 11), ("English", 8), ("Swedish", 8)]

# LinkedIn's "Save to PDF": the sidebar (Contact, Top Skills, Languages, Certifications) first, then the name, the headline and
# "City, State, United States"; each job is company, title, "Month Year - Present (2 years 8 months)", place; the degree
# "Bachelor of Arts - BA, Psychology · (2012 - 2016)"
LINKEDIN_SIDE = [("Contact", 13), ("deshawn.carter@example.com", 9), ("www.linkedin.com/in/deshawn-carter-example (LinkedIn)", 9), ("", 9),
                 ("Top Skills", 13), ("Talent Acquisition", 9), ("Applicant Tracking Systems", 9), ("Sourcing", 9), ("", 9),
                 ("Languages", 13), ("English (Native or Bilingual)", 9), ("Spanish (Professional Working Proficiency)", 9), ("", 9),
                 ("Certifications", 13), ("Certified Diversity Recruiter", 9)]
LINKEDIN_MAIN = [("DeShawn Carter", 24), ("Senior Technical Recruiter at Example Robotics", 11), ("Denver, Colorado, United States", 10),
                 ("", 9), ("Summary", 14), ("I help robotics and hardware teams hire engineers. Ten years of full-cycle recruiting,", 9),
                 ("from sourcing to offer.", 9), ("", 9), ("Experience", 14), ("Example Robotics", 11), ("Senior Technical Recruiter", 10),
                 ("March 2022 - Present (2 years 8 months)", 9), ("Denver, Colorado, United States", 9),
                 ("Hired 45 engineers across mechanical, electrical and software teams.", 9), ("", 9), ("Front Range Example Staffing", 11),
                 ("Recruiter", 10), ("June 2016 - February 2022 (5 years 9 months)", 9), ("Boulder, Colorado", 9), ("", 9),
                 ("Education", 14), ("Colorado State University", 11), ("Bachelor of Arts - BA, Psychology · (2012 - 2016)", 9), ("", 9),
                 ("Page 1 of 1", 8)]

# the contact details on one line with | and • between them, every job on one line "Title | Employer | Place | Dates", * bullets
CONTACTBAR = """PRIYANKA DESAI-ROSS
Austin, TX 78704 | 512.555.0193 | priyanka.dr@example.com | linkedin.com/in/pdesaiross-example • github.com/pdr-example

PROFESSIONAL EXPERIENCE
Frontend Developer | Example Health Tech Inc. | Austin, TX | 08/2022 – Present
* Rebuilt the patient portal in React and TypeScript
* Cut page load time by 40%
Web Developer | Lonestar Example Media | Remote | 01/2020 – 07/2022
* Built WordPress sites for 30 clients

EDUCATION
B.S. Computer Science | University of Texas at Austin | 2019

SKILLS
JavaScript, TypeScript, React, Node.js, CSS, Accessibility, Jest
"""

# icons before every contact item (as many templates and phone apps write them) and check marks between the skills
EMOJI_PARAS = [
    "Sofía Ramírez", "Customer Success Manager",
    "📍 San Antonio, TX 78205   📞 (210) 555-0156   ✉️ sofia.ramirez@example.com   🔗 linkedin.com/in/sofia-ramirez-example", "",
    "💼 EXPERIENCE", "Customer Success Manager — Alamo Example Software, San Antonio, TX\tFeb 2021 – Present",
    "➤ Kept 96% of 140 accounts year over year", "Support Specialist — Riverwalk Example Telecom, San Antonio, TX\tJun 2018 – Jan 2021", "",
    "🎓 EDUCATION", "University of Texas at San Antonio — B.B.A. in Marketing, 2018", "",
    "🛠 SKILLS", "☑ Zendesk ☑ Salesforce ☑ Spanish ☑ Onboarding ☑ Account Management",
]

# an accented, hyphenated French name, "City, Country", a French mobile number, dates written first with "Sept." and "present"
LEFEVRE = """Élodie Lefèvre-Marchand
Paris, France · +33 6 55 55 01 23 · elodie.lefevre@example.fr

Professional Experience
Sept. 2021 – present   Product Marketing Manager, Example Cosmétiques SA, Paris
– Launched 4 skincare lines in 6 countries
Sept. 2018 – Aug. 2021   Brand Assistant, Maison Example, Lyon
– Ran the press samples for 3 product launches

Education
2016 – 2018   ESSEC Business School — Master in Management

Languages
French (native), English (fluent), German (intermediate)

Skills
Market Research · Pricing · Adobe InDesign · Excel
"""

# a single name (a mononym) on the first line
MONONYM = """Arjun
arjun.dev@example.com | +1 415 555 0102
San Francisco, CA 94103

Experience
Machine Learning Engineer, Example Vision Labs — 2021–Present
• Trained the defect detection models for 3 factories
Data Scientist, Example Retail Co. — 2018–2021

Education
University of California, Berkeley — M.S. Electrical Engineering, 2018

Skills: Python, PyTorch, Computer Vision, Docker
"""

# everything in capitals: the name with a hyphen and an apostrophe, the city, the email address, the degree
ALLCAPS = """MARY-KATE O'BRIEN
CHARGE NURSE
BOSTON, MA 02118 • 617-555-0131 • MARYKATE.OBRIEN@EXAMPLE.COM

PROFESSIONAL EXPERIENCE
CHARGE NURSE, CARDIAC UNIT          MAY 2019 – PRESENT
MASS EXAMPLE GENERAL HOSPITAL, BOSTON, MA
• LEAD 12 NURSES ON THE NIGHT SHIFT
STAFF NURSE          JUN 2014 – APR 2019
EXAMPLE CHILDREN'S HOSPITAL, BOSTON, MA

EDUCATION
BOSTON COLLEGE — BACHELOR OF SCIENCE IN NURSING, 2014

SKILLS
PATIENT ASSESSMENT, TELEMETRY, EPIC, BLS, ACLS, TEAM LEADERSHIP
"""

# a British CV: "Curriculum Vitae" on top, "Mobile:" label, a UK mobile, "Personal Profile", "Employment History", ▪ bullets and
# ▪ between the skills, MEng with honours in brackets, A-Levels
UK = """Curriculum Vitae
Thomas Ashworth-Clarke
Manchester, United Kingdom | Mobile: +44 7700 900123 | thomas.ashworth@example.co.uk

Personal Profile
Mechanical engineer with five years in automotive testing, now leading durability tests for electric drivetrains.

Employment History
Test Engineer – Example Automotive Ltd, Coventry          Oct 2021 – Present
▪ Ran durability tests on electric drivetrains
Graduate Engineer – Example Rail plc, Derby                 Sep 2019 – Sep 2021
▪ Wrote test plans for bogie frames

Education
University of Leeds – MEng Mechanical Engineering (First Class Honours), 2015 – 2019
A-Levels: Maths (A*), Physics (A), Chemistry (B)

Skills
SolidWorks ▪ MATLAB ▪ CATIA ▪ Data Acquisition

References available on request.
"""

# an Indian resume: "Name:"/"Email:"/"Phone:"/"Location:" labels, +91 with dashes, "Till Date", "Educational Qualifications",
# a CGPA out of 10 (not a 4-point GPA), Class XII, a Declaration
INDIA = """Name: Ananya Krishnan
Email: ananya.krishnan@example.in
Phone: +91-55555-01234
Location: Bengaluru, India

Career Objective
To work as a software tester in a growing company where I can use my skills in manual and automation testing.

Work Experience
QA Engineer | Example Infotech Pvt. Ltd. | Jun 2022 - Till Date
- Wrote 600 test cases for a banking app
Trainee Test Engineer | Example Soft Solutions | Jan 2021 - May 2022

Educational Qualifications
B.Tech in Computer Science and Engineering, Example Institute of Technology, Bengaluru, 2020 - CGPA 8.4/10
Class XII, Example Public School, 2016 - 91%

Technical Skills
Selenium, Java, TestNG, Postman, JIRA, SQL

Declaration
I hereby declare that the above information is true to the best of my knowledge.
"""

# "Remote" instead of a city: no home city is written, and the city of an old job is not where the person lives
REMOTE = """Jamal Whitaker
Senior Data Engineer · Remote (US) · jamal.whitaker@example.com · (470) 555-0129

Experience
Senior Data Engineer, Example Cloud Inc. (Remote)          Apr 2020 – Present
- Built the streaming pipeline for 2 billion events a day
Data Engineer, Example Mart, Atlanta, GA          2017 – 2020

Education
Georgia Institute of Technology — B.S. Industrial Engineering, 2017

Skills
Python | Spark | Airflow | Snowflake | dbt | Kafka
"""

# "City, Country" in Canada, a hyphenated given name, the degree "Bachelor of Commerce"
TORONTO_PARAS = [
    "Mei-Ling Chen", "Toronto, Canada  |  +1 416 555 0175  |  meiling.chen@example.ca", "", "Experience",
    "Financial Analyst — Example Maple Bank, Toronto\tJan 2022 – Present", "Built the monthly forecast for the retail branches",
    "Junior Accountant — Example & Partners LLP, Mississauga\t2019 – 2021", "", "Education", "University of Toronto — Bachelor of Commerce, 2019", "",
    "Skills", "Financial Modeling, Excel, Power BI, SQL, IFRS",
]

# a college student with no jobs yet: projects only, no phone, no home city (the school's city is not where they live)
PROJECTS = """Kenji Watanabe
kenji.watanabe@example.com · github.com/kenjiw-example

Education
Rutgers University, New Brunswick, NJ
Bachelor of Science in Computer Science, Expected May 2027
GPA: 3.41

Projects
Study Buddy — a React Native app that matches classmates for study sessions (2025)
Trail Weather Bot — a Python Discord bot with 400 users

Skills
Python, React Native, Firebase, C++, Git
"""

# a career changer (teacher to UX): the newest job has no employer at all, an M.Ed., a certificate line under Education
CAREER_PARAS = [
    "Danielle Okonkwo", "Junior UX Designer (former teacher)", "Raleigh, NC 27601 · 919-555-0144 · danielle.okonkwo@example.com", "",
    "Summary", "Former middle-school science teacher moving into UX design, with a bootcamp fellowship and two freelance redesigns.", "",
    "Relevant Experience", "Freelance UX Designer\tJul 2025 – Present", "• Redesigned the volunteer sign-up for a community garden",
    "UX Design Fellow, Example Design Bootcamp\tJan 2025 – Jun 2025", "8th Grade Science Teacher, Example Middle School\tAug 2015 – Dec 2024", "",
    "Education", "North Carolina State University — M.Ed. Science Education, 2015", "Google UX Design Certificate, 2024", "",
    "Skills", "Figma, User Research, Wireframing, Prototyping, Public Speaking",
]

# a gap written as the newest entry ("Career Break"): the newest job is the one before it
GAP = """Grace Oduya
Tampa, FL 33602 • (813) 555-0117 • grace.oduya@example.com

Experience
Career Break — Full-time caregiver for a family member      Mar 2023 – Present
Office Manager, Example Dental Group, Tampa, FL      Jun 2017 – Feb 2023
- Ran scheduling and billing for 4 dentists
Front Desk Coordinator, Example Family Clinic, Tampa, FL      2014 – 2017

Education
Hillsborough Community College — Associate in Arts, 2014

Skills
Scheduling, Billing, Dentrix, Customer Service, Excel
"""

# a senior three-page PDF: "Executive Summary", "Employment", MM/YYYY dates, – bullets, an initial in the name, an MBA,
# skills drawn as a grid of columns
SENIOR3_PAGES = [
    [("Robert J. Castellano", 18), ("Phoenix, AZ 85004 • (602) 555-0111 • rob.castellano@example.com", 9), ("", 9),
     ("EXECUTIVE SUMMARY", 11), ("Finance executive with twenty years in treasury, planning and audit for manufacturing and real estate.", 9),
     ("", 9), ("EMPLOYMENT", 11), ("Vice President of Finance                                              04/2019 – Present", 10),
     ("Example Desert Holdings, Phoenix, AZ", 10)] +
    [("– Led %s for a $900M portfolio" % w, 9) for w in ("the annual plan", "treasury", "two audits", "the ERP move", "debt refinancing")] +
    [("Controller                                                                     06/2012 – 03/2019", 10),
     ("Example Copper Manufacturing Co., Tempe, AZ", 10)] +
    [("– Ran %s" % w, 9) for w in ("the month-end close", "cost accounting", "payroll", "tax filings", "the audit")],
    [("Senior Accountant                                                            01/2006 – 05/2012", 10), ("Example & Sons CPAs, Phoenix, AZ", 10)] +
    [("– Prepared %s" % w, 9) for w in ("financial statements", "tax returns", "audit work papers", "budgets", "forecasts", "board decks")] +
    [("Staff Accountant                                                             07/2001 – 12/2005", 10), ("Example Valley Bank, Mesa, AZ", 10),
     ("– Reconciled 40 accounts each month", 9)],
    [("EDUCATION", 11), ("Arizona State University — MBA, 2006", 10), ("University of Arizona — B.S. Accounting, 2001", 10), ("", 9),
     ("BOARD SERVICE", 11), ("Treasurer, Example Food Bank of Arizona, 2018 – Present", 9), ("", 9), ("SKILLS", 11)],
]
SENIOR3_GRID = [("FP&A", "Treasury", "SAP"), ("Budgeting", "Forecasting", "Audit")]

# many ways to write a date and a bullet: Jun '22 with a curly apostrophe, 2019.03, Summer 2018, Dec. 2021; ▪ * – • bullets
DATES = """Carlos Mendoza
Fresno, CA 93721 | (559) 555-0108 | carlos.mendoza@example.com

Work Experience
Warehouse Lead
Example Valley Foods, Fresno, CA
Jun ’22 – Present
▪ Lead a crew of 8 on the night shift
* Trained 15 new hires on forklift safety
Forklift Operator
Example Ag Supply
2019.03 – 2022.05
– Moved 200 pallets a shift
Seasonal Picker
Example Orchards
Summer 2018
• Picked and packed fruit

Education
Fresno City College — Certificate in Logistics, Dec. 2021

Certifications
OSHA 10, Forklift Certified

Skills
Forklift, Inventory, RF Scanners, Spanish, Microsoft Office
"""

# a resume that is one big table: the name row, a CONTACT row, an EXPERIENCE row, an EDUCATION row, a SKILLS row whose cell holds
# a table of its own
TABLE_ROWS = [
    [["Ifeoma Adeyemi"], ["Accounts Payable Specialist"]],
    [["CONTACT"], ["Newark, NJ 07102", "973-555-0166", "ifeoma.adeyemi@example.com"]],
    [["EXPERIENCE"], ["Accounts Payable Specialist\tMay 2021 – Present", "Example Port Authority Credit Union, Newark, NJ",
                      "• Processed 1,200 invoices a month", "Accounting Clerk\tJan 2018 – Apr 2021", "Example Ironbound Supply Co., Newark, NJ"]],
    [["EDUCATION"], ["Rutgers University–Newark", "Bachelor of Science in Accounting, 2017"]],
    [["SKILLS"], [("table", [[["QuickBooks"], ["Excel"], ["SAP"]], [["Accounts Payable"], ["Vendor Reconciliation"], ["Data Entry"]]])]],
]

# a cover letter on page one (with the bank's address, not the person's), the resume on page two; the person's own city is not written
COVER_PAGES = [
    [("Taylor Brooks", 16), ("taylor.brooks@example.com | (816) 555-0150", 9), ("", 9), ("October 12, 2026", 10), ("", 9),
     ("Hiring Manager", 10), ("Example Gateway Bank", 10), ("200 Market Street", 10), ("St. Louis, MO 63101", 10), ("", 9),
     ("Dear Hiring Manager,", 10), ("", 9),
     ("I am writing to apply for the Branch Operations Supervisor role at Example Gateway Bank. In my four years at Example", 10),
     ("Heartland Credit Union I have run a team of tellers, opened new accounts and kept our audits clean.", 10), ("", 9),
     ("Sincerely,", 10), ("Taylor Brooks", 10)],
    [("Taylor Brooks", 16), ("taylor.brooks@example.com | (816) 555-0150", 9), ("", 9), ("EXPERIENCE", 11),
     ("Member Services Supervisor                                          Aug 2022 – Present", 10),
     ("Example Heartland Credit Union, Kansas City, MO", 10), ("• Lead 7 tellers and member service reps", 9),
     ("Teller                                                                          2020 – 2022", 10), ("Example Plaza Bank, Kansas City, MO", 10),
     ("", 9), ("EDUCATION", 11), ("University of Missouri–Kansas City", 10), ("Bachelor of Business Administration, 2020", 10), ("", 9),
     ("SKILLS", 11), ("Cash Handling, Customer Service, Loan Processing, Excel, Spanish", 10)],
]

# a Markdown resume: # headings, **bold**, *italic* dates, a [link](url), skills in `code`
MARKDOWN = """# Noah Feldman-Ruiz

**Site Reliability Engineer** · Chicago, IL 60614 · noah.feldman@example.com · [github.com/noahfr-example](https://github.com/noahfr-example)

## Experience

### Site Reliability Engineer — Example Transit Data Inc.
*Feb 2023 – Present*

- Kept the trip planner API at 99.95% uptime
- Moved alerting to Prometheus and Grafana

### Systems Administrator — Example Lakeside College
*2019 – 2023*

## Education

**Illinois Institute of Technology** — B.S. Information Technology, 2019

## Skills

`Kubernetes` `Terraform` `Prometheus` `Grafana` `Linux` `AWS`
"""

# five words in a name with the particles "de la", labels "Phone:" and "Email:", the state written out, no ZIP
DELACRUZ_PARAS = [
    "Ana Lucía de la Cruz", "Phone: (713) 555-0190 | Email: ana.delacruz@example.com | Houston, Texas", "", "Work Experience",
    "Bilingual Customer Service Representative\t08/2020 - Present", "Example Gulf Energy, Houston, Texas",
    "Answered 70 billing calls a day in English and Spanish", "Cashier\t06/2018 - 07/2020", "Example Food Mart, Pasadena, Texas", "",
    "Education", "Lone Star College — Associate of Arts, 2019", "", "Skills", "Customer Service, Spanish, Billing, Data Entry, Excel",
]

# two columns drawn row by row across the page (some design tools do this): each line of text mixes the two columns
ROWS_LEFT = ["CONTACT", "(919) 555-0102", "jordan.pike@example.com", "Durham, NC 27701", "", "SKILLS", "Python", "R", "Tableau",
             "Statistics", "", "EDUCATION", "North Carolina Central University", "B.S. in Biology", "2020"]
ROWS_RIGHT = ["JORDAN PIKE", "Clinical Research Coordinator", "", "EXPERIENCE", "Clinical Research Coordinator", "Example Research Institute",
              "Jun 2022 - Present", "• Enrolled 140 patients in two trials", "Lab Assistant", "Example Biotech LLC", "2020 - 2022"]

# a PDF that draws every word as its own piece of text (as some browsers' "Save as PDF" and online editors do)
WORDRUNS = [("Lucas Moreau", 18), ("Denver, CO 80202 | (303) 555-0161 | lucas.moreau@example.com", 9), ("", 9), ("EXPERIENCE", 11),
            ("Electrician Apprentice                                   Mar 2022 - Present", 10), ("Example Front Range Electric, Denver, CO", 10),
            ("• Wired 25 new homes and 3 retail spaces", 9), ("", 9), ("EDUCATION", 11), ("Emily Griffith Technical College", 10),
            ("Certificate in Electrical Technology, Dec 2021", 10), ("", 9), ("SKILLS", 11),
            ("Residential Wiring, Conduit Bending, Blueprint Reading, OSHA 10", 10)]

# a name in large capitals on two lines (as poster-like templates set it), skills in a grid
STACKED = [("SARAH", 28), ("CONNOLLY", 28), ("Physical Therapist Assistant", 12), ("sarah.connolly@example.com   (724) 555-0156", 9),
           ("Greensburg, PA 15601", 9), ("", 9), ("WORK EXPERIENCE", 11), ("Physical Therapist Assistant                     Sept 2021 - Present", 10),
           ("Example Rehab Partners, Greensburg, PA", 10), ("• Treat about 14 patients a day after joint replacements", 9), ("", 9),
           ("EDUCATION", 11), ("Westmoreland County Community College", 10),
           ("Associate of Applied Science in Physical Therapist Assistant, May 2021", 10), ("", 9), ("SKILLS", 11)]
STACKED_GRID = [("Gait Training", "Therapeutic Exercise", "Patient Education"), ("Manual Therapy", "CPR", "Documentation")]

# a veteran: a nickname in quotes, "Military Experience" and "Civilian Experience", a summary paragraph with no heading,
# "Associate in Applied Science, Logistics Management"
VETERAN = """MICHAEL "MIKE" TORRES
Fayetteville, NC 28301 | 910-555-0138 | mike.torres@example.com
Logistics professional with eight years as an Army supply sergeant, now running inventory for a regional distribution center.

MILITARY EXPERIENCE
Supply Sergeant (92Y), U.S. Army, Fort Example, NC        JAN 2016 – DEC 2023
• Managed $4M of equipment for a 120-soldier company

CIVILIAN EXPERIENCE
Warehouse Associate, Example Distribution LLC, Fayetteville, NC        FEB 2024 – PRESENT
• Count and reconcile 2,000 locations a month

EDUCATION
Fayetteville Technical Community College — Associate in Applied Science, Logistics Management, 2025

SKILLS
Inventory Management, Supply Chain, Forklift, Microsoft Excel, Leadership

SECURITY CLEARANCE
Secret (inactive)
"""

# hotel front desk: "Professional Summary", "Employment History", "2023 – Current", skills in columns spaced apart
HOSPITALITY = """Brianna Lopez-Whitman
Las Vegas, NV 89109
+1 (702) 555-0124
brianna.lw@example.com

Professional Summary
Front desk and guest services lead with six years on the Las Vegas Strip, calm with long lines and upset guests.

Employment History
Front Desk Supervisor
Example Grand Resort & Casino  |  2023 – Current
- Lead a team of 9 agents
Guest Services Agent
Example Desert Inn  |  Mar 2019 – Dec 2022

Education
College of Southern Nevada — Associate of Applied Science in Hospitality Management, May 2019

Skills
Opera PMS     Customer Service     Conflict Resolution     Spanish     Cash Handling
"""

# a teacher's Word file: name, phone and email in the page header, "Page 1" in the footer, the degree with two fields
TEACHER_HEADER = ["Samantha Reyes  |  602-555-0179  |  sam.reyes@example.org"]
TEACHER_FOOTER = ["Page 1"]
TEACHER_PARAS = [
    "Elementary Teacher", "Mesa, AZ 85201", "", "Professional Experience", "3rd Grade Teacher\tAug 2019 – Present",
    "Example Unified School District, Mesa, AZ", "Teach 26 students reading, math and science", "Student Teacher\tJan 2019 – May 2019",
    "Example Elementary School, Tempe, AZ", "", "Education", "Arizona State University, Tempe, AZ",
    "Bachelor of Arts in Education, Elementary Education, May 2019", "", "Certifications", "Arizona Standard Professional Certificate, Elementary K-8",
    "", "Skills", "Classroom Management, Google Classroom, Lesson Planning, Parent Communication, Spanish",
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


def docx_full(path, body, header=(), footer=()):
    """A Word file with a page header and footer and a body of paragraphs and tables. A body item is a paragraph (text, \\t for a tab)
    or ("table", rows): rows of cells, each cell a list of body items (so a cell can hold a table of its own). Fixed zip dates."""
    def p(t):
        runs = "<w:r><w:tab/></w:r>".join('<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % escape(s) for s in t.split("\t"))
        return "<w:p>%s</w:p>" % runs

    def items(xs):
        out = []
        for x in xs:
            if isinstance(x, tuple) and x[0] == "table":
                out.append("<w:tbl>%s</w:tbl>" % "".join("<w:tr>%s</w:tr>" % "".join("<w:tc>%s</w:tc>" % items(c) for c in row) for row in x[1]))
            else:
                out.append(p(x))
        return "".join(out)
    ns = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
    refs = ('<w:headerReference w:type="default" r:id="rId8"/>' if header else "") + ('<w:footerReference w:type="default" r:id="rId9"/>' if footer else "")
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document %s><w:body>%s<w:sectPr>%s</w:sectPr></w:body></w:document>'
           % (ns, items(body), refs))
    rels = ""
    parts = [("word/document.xml", doc)]
    over = '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    if header:
        parts.append(("word/header1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr %s>%s</w:hdr>' % (ns, items(header))))
        rels += '<Relationship Id="rId8" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
        over += '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
    if footer:
        parts.append(("word/footer1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr %s>%s</w:ftr>' % (ns, items(footer))))
        rels += '<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
        over += '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
    parts = [("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>' + over + '</Types>'),
             ("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'),
             ("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              + rels + '</Relationships>')] + parts
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts:
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)


def column(items, x, y=750, gap=6):
    """(x, y, size, text) runs for a column of (text, size) lines, top to bottom."""
    runs = []
    for text, size in items:
        runs.append((x, y, size, text))
        y -= size + gap
    return runs, y


def word_runs(items, x=50, y=750):
    """Every word as its own run at its own x (Helvetica is about half a point wide per point of size per letter)."""
    runs = []
    for text, size in items:
        cx = x
        for w in re.split(r"( +)", text):
            if w.strip():
                runs.append((int(cx), y, size, w))
            cx += len(w) * size * 0.56
        y -= size + 6
    return runs


def main():
    os.makedirs(HERE, exist_ok=True)
    for name, text in (("student.txt", STUDENT), ("international.txt", INTERNATIONAL), ("messy.txt", MESSY), ("sparse.txt", SPARSE),
                       ("nunez.txt", NUNEZ), ("store.txt", STORE)):
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

    # the wider set
    for name, text in (("contactbar.txt", CONTACTBAR), ("lefevre.txt", LEFEVRE), ("mononym.txt", MONONYM), ("allcaps.txt", ALLCAPS),
                       ("uk.txt", UK), ("india.txt", INDIA), ("remote.txt", REMOTE), ("projects.txt", PROJECTS), ("gap.txt", GAP),
                       ("dates.txt", DATES), ("resume.md", MARKDOWN), ("veteran.txt", VETERAN), ("hospitality.txt", HOSPITALITY)):
        with open(os.path.join(HERE, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    docx_full(os.path.join(HERE, "gdocs.docx"), GDOCS_PARAS)
    docx_full(os.path.join(HERE, "wordhf.docx"), WORDHF_PARAS, WORDHF_HEADER, WORDHF_FOOTER)
    docx_full(os.path.join(HERE, "emoji.docx"), EMOJI_PARAS)
    docx_full(os.path.join(HERE, "toronto.docx"), TORONTO_PARAS)
    docx_full(os.path.join(HERE, "careerchange.docx"), CAREER_PARAS)
    docx_full(os.path.join(HERE, "tablecv.docx"), [("table", TABLE_ROWS)])
    docx_full(os.path.join(HERE, "delacruz.docx"), DELACRUZ_PARAS)
    docx_full(os.path.join(HERE, "teacher.docx"), TEACHER_PARAS, TEACHER_HEADER, TEACHER_FOOTER)
    left, _ = column(CANVA_MAIN, 40)
    right, _ = column(CANVA_SIDE, 410)
    pdf(os.path.join(HERE, "canva.pdf"), left + right)
    side, _ = column(LINKEDIN_SIDE, 30)
    main_col, _ = column(LINKEDIN_MAIN, 220)
    pdf(os.path.join(HERE, "linkedin.pdf"), side + main_col)
    pages = []
    for i, page in enumerate(SENIOR3_PAGES):
        runs, y = column(page, 50)
        if i == len(SENIOR3_PAGES) - 1:
            for row in SENIOR3_GRID:
                runs += [(50 + 170 * k, y, 9, w) for k, w in enumerate(row)]
                y -= 15
        pages.append(runs)
    pdf_pages(os.path.join(HERE, "senior3page.pdf"), pages)
    pdf_pages(os.path.join(HERE, "coverletter.pdf"), [column(page, 60)[0] for page in COVER_PAGES])
    runs, y = [], 750
    for k in range(max(len(ROWS_LEFT), len(ROWS_RIGHT))):          # row by row: the left piece, then the right piece of the same row
        if k < len(ROWS_LEFT) and ROWS_LEFT[k]:
            runs.append((40, y, 9, ROWS_LEFT[k]))
        if k < len(ROWS_RIGHT) and ROWS_RIGHT[k]:
            runs.append((230, y, 9 if k else 20, ROWS_RIGHT[k]))
        y -= 16
    pdf(os.path.join(HERE, "canvarows.pdf"), runs)
    pdf(os.path.join(HERE, "wordruns.pdf"), word_runs(WORDRUNS))
    runs, y = column(STACKED, 50)
    for row in STACKED_GRID:
        runs += [(50 + 170 * k, y, 9, w) for k, w in enumerate(row)]
        y -= 15
    pdf(os.path.join(HERE, "stacked.pdf"), runs)
    print("wrote 42 resumes to", HERE)


if __name__ == "__main__":
    main()
