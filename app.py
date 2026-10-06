import streamlit as st
import json
import re
import os
import zipfile
import shutil
import tempfile
import subprocess
import datetime
import base64
import requests
from io import BytesIO
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "students.json"), encoding="utf-8") as f:
    STUDENT_DATA = json.load(f)

with open(os.path.join(BASE_DIR, "companies.json"), encoding="utf-8") as f:
    COMPANY_DATA = json.load(f)

COMPANY_NAMES = sorted(COMPANY_DATA.keys(), key=str.casefold)

ADD_NEW_COMPANY = "➕ Add New Company"

SCHOOL_MAJORS = {
    "School of Business & Entrepreneurship (SBE)": [
        "Accounting", "Finance", "General Management",
        "Human Resources Management (HRM)", "International Business",
        "Management Information Systems (MIS)", "Marketing",
    ],
    "School of Engineering, Technology & Sciences (SETS)": [
        "Computer Science", "Computer Science & Engineering (CSE)",
        "Computer Engineering", "Electrical & Electronic Engineering (EEE)",
        "Electronic & Telecommunication Engineering",
    ],
    "School of Environment & Life Sciences (SELS)": [
        "Environmental Science & Management", "Biochemistry & Biotechnology",
        "Microbiology",
    ],
    "School of Liberal Arts & Social Sciences (SLASS)": [
        "Economics", "English Literature", "English Language Teaching (ELT)",
        "Media & Communication", "Global Studies & Governance",
        "Anthropology", "Sociology",
    ],
    "School of Pharmacy & Public Health (SPPH)": ["Pharmacy"],
}

def _secret(name, default=""):
    """Read a Streamlit secret safely. Returns default when not configured."""
    try:
        return str(st.secrets.get(name, default)).strip()
    except Exception:
        return default

def persist_company_to_github(company_name, address_lines):
    """Add/update a company in the GitHub-backed companies.json.

    Reads the file from the GitHub Contents API first. If GitHub returns 404,
    it falls back to the public raw file URL for reading (useful when the repo
    is public and the PAT has a scope/configuration problem). Writing still
    requires a valid token with permission to the repository.
    """
    token = _secret("GITHUB_TOKEN")
    repo = _secret("GITHUB_REPO", "jahidofficials/iubcgpar")
    branch = _secret("GITHUB_BRANCH", "main") or "main"
    json_path = _secret("GITHUB_COMPANIES_PATH", "companies.json") or "companies.json"

    # Clean common copy/paste mistakes in Secrets.
    repo = repo.strip().strip("/")
    json_path = json_path.strip().lstrip("/")
    branch = branch.strip()

    if "://" in repo or repo.count("/") != 1:
        return False, (
            "Invalid GITHUB_REPO. It must be exactly: owner/repository "
            "(for example: jahidofficials/iubcgpar)."
        )

    api_url = f"https://api.github.com/repos/{repo}/contents/{json_path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = None
    current_content = None

    try:
        # First try GitHub's Contents API.
        get_response = requests.get(
            api_url, headers=headers, params={"ref": branch}, timeout=20
        )
        if get_response.status_code == 200:
            payload = get_response.json()
            current_content = base64.b64decode(payload["content"]).decode("utf-8")
        elif get_response.status_code == 404:
            # Public-repo fallback: read the exact file directly.
            raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{json_path}"
            raw_response = requests.get(raw_url, timeout=20)
            if raw_response.status_code == 200:
                current_content = raw_response.text
            else:
                return False, (
                    f"GitHub could not find {json_path} on branch '{branch}'. "
                    f"Checked repository '{repo}'. API={get_response.status_code}, "
                    f"raw={raw_response.status_code}."
                )
        else:
            msg = ""
            try:
                msg = get_response.json().get("message", "")
            except Exception:
                pass
            return False, (
                f"GitHub read failed ({get_response.status_code})" +
                (f": {msg}" if msg else ".")
            )

        github_data = json.loads(current_content)
        if not isinstance(github_data, dict):
            return False, "companies.json must contain a JSON object/dictionary."

        existing_name = next(
            (name for name in github_data if name.casefold() == company_name.casefold()),
            None,
        )
        if existing_name:
            company_name = existing_name

        github_data[company_name] = address_lines
        new_content = json.dumps(github_data, ensure_ascii=False, indent=2) + "\n"

        # A valid Contents-API payload (including SHA) is required to write.
        if not token:
            return False, (
                "Company data can be read, but GITHUB_TOKEN is missing. "
                "Add a GitHub token in Streamlit Secrets to save changes."
            )

        # If the API GET was successful, use its SHA. If we had to use raw
        # fallback, fetch the Contents API once more to obtain the SHA.
        if not payload or "sha" not in payload:
            get_for_sha = requests.get(
                api_url, headers=headers, params={"ref": branch}, timeout=20
            )
            if get_for_sha.status_code != 200:
                detail = ""
                try:
                    detail = get_for_sha.json().get("message", "")
                except Exception:
                    pass
                return False, (
                    f"GitHub file read for saving failed ({get_for_sha.status_code})" +
                    (f": {detail}" if detail else ".") +
                    " Check that GITHUB_TOKEN has access to the repository."
                )
            payload = get_for_sha.json()

        put_payload = {
            "message": f"Add/update company: {company_name}",
            "content": base64.b64encode(new_content.encode("utf-8")).decode("ascii"),
            "sha": payload["sha"],
            "branch": branch,
        }
        put_response = requests.put(
            api_url, headers=headers, json=put_payload, timeout=20
        )
        if put_response.status_code not in (200, 201):
            detail = ""
            try:
                detail = put_response.json().get("message", "")
            except Exception:
                pass
            return False, (
                f"GitHub save failed ({put_response.status_code})" +
                (f": {detail}" if detail else ".") +
                " Make sure the token can write to this repository."
            )

        return True, f"{company_name} saved to GitHub."

    except requests.RequestException as exc:
        return False, f"GitHub connection error: {exc}"
    except (ValueError, KeyError, UnicodeDecodeError) as exc:
        return False, f"Could not process companies.json: {exc}"

def classify_student(record):
    reg = str(record.get("register", "")).strip()
    if reg == "BBA499A":
        return "eligible", "✓ ELIGIBLE FOR INTERNSHIP", "#2e7d32", True
    if reg == "Rejected":
        return "rejected", "✕ NOT ELIGIBLE FOR INTERNSHIP", "#c62828", False
    if "Contact to BBA Program Office" in reg:
        return "contact", "⚠ CONTACT BBA PROGRAM OFFICE", "#ef6c00", False
    return "other", "⚠ CHECK BBA PROGRAM OFFICE", "#ef6c00", False

def make_address(lines):
    return [str(x).strip() for x in lines if str(x).strip()]

def apply_letter_transform(xml, name, student_id, org, address_lines,
                           selected_date, start_month, school, major, official_key, gender):
    """Fill an exact Director/Deputy template while preserving every original
    paragraph, blank line, font, alignment, bold run, and spacing."""
    name = xml_escape(name.strip())
    student_id = xml_escape(student_id.strip())
    org = xml_escape(org.strip())
    school = xml_escape(school.strip())
    major = xml_escape(major.strip())
    start_month = xml_escape(start_month.strip())
    gender = gender.strip().lower()

    if gender == "female":
        pronoun, object_pronoun, subject = "her", "her", "she"
    else:
        pronoun, object_pronoun, subject = "his", "him", "he"

    address_lines = make_address(address_lines)
    if not address_lines:
        raise ValueError("Organization address is required.")

    # The address paragraph in the supplied reference files is a single
    # formatted paragraph. Replace only its text while preserving its paragraph
    # and run formatting.
    address_xml = "</w:t><w:br/><w:t>".join(xml_escape(x) for x in address_lines)

    official = OFFICIALS[official_key]

    replacements = {
        b"{{DATE}}": selected_date.strftime("%B %d, %Y").replace(" 0", " ").encode(),
        b"{{NAME}}": name.encode(),
        b"{{ID}}": student_id.encode(),
        b"{{ORG}}": org.encode(),
        b"{{ADDRESS}}": address_xml.encode(),
        b"{{START_MONTH}}": start_month.encode(),
        b"{{SCHOOL}}": school.encode(),
        b"{{MAJOR}}": major.encode(),
        b"{{PRONOUN}}": pronoun.encode(),
        b"{{OBJECT_PRONOUN}}": object_pronoun.encode(),
        b"{{SUBJECT}}": subject.encode(),
        b"{{EMAIL}}": xml_escape(official["email"]).encode(),
        b"{{OFFICIAL_NAME}}": xml_escape(official["name"]).encode(),
        b"{{OFFICIAL_TITLE}}": xml_escape(official["title"]).encode(),
        b"{{OFFICIAL_PHONE}}": xml_escape(official["phone"]).encode(),
    }

    for placeholder, value in replacements.items():
        xml = xml.replace(placeholder, value)

    return xml
def build_docx(entries, name, student_id, selected_date, start_month, school, major, official_key, gender):
    # Director and Deputy Director outputs are based directly on the two
    # supplied reference letters. Senior Analyst uses the Director layout
    # because it includes the signature/phone block.
    if official_key == "Deputy Director":
        template_name = "template_deputy.docx"
    else:
        template_name = "template_director.docx"

    template_path = os.path.join(BASE_DIR, template_name)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Missing formatting template: {template_name}")

    work_dir = tempfile.mkdtemp(prefix="hello_cgpar_")
    try:
        extracted = os.path.join(work_dir, "extracted")
        with zipfile.ZipFile(template_path, "r") as z:
            z.extractall(extracted)

        doc_path = os.path.join(extracted, "word", "document.xml")
        original = open(doc_path, "rb").read()

        body_open = b"<w:body>"
        body_start = original.index(body_open) + len(body_open)
        sect_start = original.rindex(b"<w:sectPr")
        head = original[:body_start]
        body = original[body_start:sect_start]
        tail = original[sect_start:]

        page_break = b'<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
        pages = []
        for org, address in entries:
            pages.append(apply_letter_transform(
                body, name, student_id, org, address, selected_date,
                start_month, school, major, official_key, gender
            ))

        final_xml = head + page_break.join(pages) + tail
        with open(doc_path, "wb") as f:
            f.write(final_xml)

        output = BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(extracted):
                for file in files:
                    full = os.path.join(root, file)
                    arc = os.path.relpath(full, extracted)
                    z.write(full, arc)
        return output.getvalue()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
def _register_pdf_fonts():
    """Register Carlito, a metrically compatible open-source Calibri substitute."""
    font_dir = os.path.join(BASE_DIR, "fonts")
    regular = os.path.join(font_dir, "Carlito-Regular.ttf")
    bold = os.path.join(font_dir, "Carlito-Bold.ttf")
    if os.path.exists(regular) and os.path.exists(bold):
        if "Carlito" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("Carlito", regular))
        if "Carlito-Bold" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("Carlito-Bold", bold))
        pdfmetrics.registerFontFamily("Carlito", normal="Carlito", bold="Carlito-Bold")
        return "Carlito"
    return "Helvetica"


def _pdf_paragraph(text, style):
    # Escape user/company text first; formatting tags are intentionally supplied
    # by this function only for the fields that are bold in the original DOCX.
    return Paragraph(text, style)


def _register_pdf_fonts():
    """Register Carlito, a metrically compatible open-source Calibri substitute."""
    font_dir = os.path.join(BASE_DIR, "fonts")
    regular = os.path.join(font_dir, "Carlito-Regular.ttf")
    bold = os.path.join(font_dir, "Carlito-Bold.ttf")
    if os.path.exists(regular) and os.path.exists(bold):
        if "Carlito" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("Carlito", regular))
        if "Carlito-Bold" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("Carlito-Bold", bold))
        pdfmetrics.registerFontFamily("Carlito", normal="Carlito", bold="Carlito-Bold")
        return "Carlito"
    return "Helvetica"


def _build_pdf_reportlab_fallback(entries, name, student_id, selected_date, start_month, school, major, official_key, gender):
    """Fallback for environments where LibreOffice is unavailable."""
    official = OFFICIALS[official_key]
    female = gender.lower() == "female"
    pronoun = "her" if female else "his"
    obj = "her" if female else "him"
    subject = "she" if female else "he"
    font = _register_pdf_fonts()

    buf = BytesIO()
    # The supplied template is US Letter, not A4, with 1-inch margins.
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        rightMargin=1.0 * inch, leftMargin=1.0 * inch,
        topMargin=1.0 * inch, bottomMargin=1.0 * inch,
        title="Internship Forwarding Letter",
    )
    base = ParagraphStyle(
        "TemplateNormal", fontName=font, fontSize=12, leading=12.95,
        spaceBefore=0, spaceAfter=0, allowWidows=0, allowOrphans=0,
    )
    right = ParagraphStyle("TemplateRight", parent=base, alignment=2)
    justify = ParagraphStyle("TemplateJustify", parent=base, alignment=4)
    story = []
    date_str = selected_date.strftime("%B %d, %Y").replace(" 0", " ")
    esc = lambda x: xml_escape(str(x))

    for idx, (org, address) in enumerate(entries):
        story.extend([Spacer(1, 12.95)] * 4)
        story.append(Paragraph(esc(date_str), right))
        story.append(Spacer(1, 12.95))
        story.append(Paragraph("Head of HR", base))
        story.append(Paragraph("<b>" + esc(org) + "</b>", base))
        address_lines = make_address(address)
        story.append(Paragraph("<br/>".join(esc(line) for line in address_lines), base))
        # Heading 5 in the original template: bold + centered, 12 pt.
        story.append(Paragraph("<b>Re: Request for Internship</b>", ParagraphStyle(
            "ReLine", parent=base, alignment=1
        )))
        story.append(Spacer(1, 12.95))
        story.append(Paragraph("Dear Sir/Madam,", justify))
        story.append(Spacer(1, 12.95))
        p1 = (
            "We are pleased to inform you that <b>" + esc(name) + "</b> "
            "<b>(ID: " + esc(student_id) + ")</b> "
            "is about to complete " + esc(pronoun) + " bachelor with a major in "
            "<b>" + esc(major) + "</b> from the <b>" + esc(school) + "</b> of IUB. "
            "<b>" + esc(name) + "</b> is now prepared to join the job market. "
            "It will be helpful for " + esc(obj) + " to have hands-on-experience in an esteemed organization like yours."
        )
        story.append(Paragraph(p1, justify))
        story.append(Spacer(1, 12.95))
        p2 = (
            "The office of CGP &amp; AR requests you to kindly allow <b>" + esc(name) + "</b> with an internship opportunity "
            "at your esteemed organization. We are confident " + esc(subject) + " would be able to gather valuable experience "
            "from your company and will be able to contribute to the corporate world in the future. Also, we will greatly appreciate "
            "if you would please allow <b>" + esc(name) + "</b> one day each week to meet " + esc(pronoun) + " supervising faculty "
            "at IUB to report " + esc(pronoun) + " internship activities and progress."
        )
        story.append(Paragraph(p2, justify))
        story.append(Spacer(1, 12.95))
        story.append(Paragraph(
            "Please confirm if " + esc(subject) + " can start " + esc(pronoun) + " internship from " + esc(start_month) + ".",
            justify
        ))
        story.append(Spacer(1, 12.95))
        closing = (
            "Thank you for your kind cooperation. For any inquiries, please "
            + ("contact us at the following email, director.cgpar@iub.edu.bd"
               if official_key == "Director" else "contact cgp@iub.edu.bd.")
        )
        story.append(Paragraph(closing, justify))
        story.append(Spacer(1, 12.95))
        story.append(Paragraph("Yours sincerely,", justify))
        story.extend([Spacer(1, 12.95)] * 3)
        story.append(Paragraph("<b>" + esc(official["name"]) + "</b>", base))
        story.append(Paragraph(esc(official["title"]), base))
        story.append(Paragraph("Office of Career Guidance, Placement &amp; Alumni Relations", base))
        if official.get("show_phone", True):
            story.append(Paragraph("Phone :" + esc(official["phone"]), base))
        if idx < len(entries) - 1:
            story.append(PageBreak())
    doc.build(story)
    return buf.getvalue()


def build_pdf(entries, name, student_id, selected_date, start_month, school, major, official_key, gender):
    """Generate PDF from the SAME DOCX template used by Word.

    When LibreOffice is available (installed on Streamlit Cloud through
    packages.txt), the DOCX is converted directly to PDF. This preserves the
    template's exact page size, margins, styles, bold runs, paragraph spacing,
    alignment, and page breaks instead of redrawing the letter with a different
    layout engine. ReportLab remains as a safe fallback.
    """
    docx_bytes = build_docx(
        entries, name, student_id, selected_date,
        start_month, school, major, official_key, gender
    )

    work_dir = tempfile.mkdtemp(prefix="hello_cgpar_pdf_")
    try:
        docx_path = os.path.join(work_dir, "letter.docx")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice:
            result = subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", work_dir, docx_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=90,
                check=False,
            )
            pdf_path = os.path.join(work_dir, "letter.pdf")
            if result.returncode == 0 and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    return f.read()

        return _build_pdf_reportlab_fallback(
            entries, name, student_id, selected_date,
            start_month, school, major, official_key, gender
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

st.set_page_config(page_title="Hello CGPAR", page_icon="📄", layout="centered")

st.title("Hello CGPAR")
st.caption("Online Internship Forwarding Letter Generator • CGP & AR, IUB")

# Keep a session copy so a newly saved company is usable immediately, even
# before Streamlit Cloud rebuilds from the GitHub commit.
if "company_data" not in st.session_state:
    st.session_state.company_data = dict(COMPANY_DATA)

if "companies" not in st.session_state:
    st.session_state.companies = [{"name": "", "address": ["", "", ""]}]

# --- Student ID ---
st.subheader("1. Student Eligibility")
student_id = st.text_input(
    "Student ID",
    placeholder="Example: 2110245",
    help="Enter the complete student ID."
).strip()

record = STUDENT_DATA.get(student_id)
can_generate = False
if record:
    state, status, color, can_generate = classify_student(record)
    if state == "eligible":
        st.success(status)
        if "student_name" not in st.session_state or st.session_state.get("student_id_for_name") != student_id:
            st.session_state.student_name = record["name"]
            st.session_state.student_id_for_name = student_id
        st.session_state.student_gender = record.get("gender", "Male")
        student_name = st.text_input(
            "Student Name",
            key="student_name",
            help="Automatically filled from the eligibility list. You can edit it before generating the letter."
        ).strip()
        st.caption("✓ Name auto-filled from the eligibility list — editable.")
    elif state == "rejected":
        st.error(status)
        st.warning("Register: " + str(record.get("register", "")))
        student_name = ""
    else:
        st.warning(status)
        st.info("Register: " + str(record.get("register", "")))
        student_name = ""
else:
    if student_id:
        st.warning("Student ID is not in the existing list.")
        st.info("You can continue by entering the student's name manually.")
        student_name = st.text_input(
            "Student Name (Manual Entry)",
            placeholder="Enter the student's full name",
            key="manual_student_name",
        ).strip()
        can_generate = bool(student_name and student_id)
        st.session_state.student_gender = st.selectbox(
            "Student Gender", ["Male", "Female"], key="manual_gender"
        )
    else:
        st.info("Enter Student ID. If the ID is not in the list, you can still enter it manually.")
        student_name = ""

# --- Common details ---
st.subheader("2. Letter Details")
col1, col2 = st.columns(2)
with col1:
    school = st.selectbox("School", list(SCHOOL_MAJORS.keys()))
major = st.selectbox("Major", SCHOOL_MAJORS[school])
with col2:
    official_key = st.selectbox("Authorized Official", list(OFFICIALS.keys()))

today = datetime.date.today()
d1, d2, d3 = st.columns(3)
with d1:
    letter_date = st.date_input("Letter Date", value=today)
with d2:
    months = []
    for off in range(-12, 25):
        first = (today.replace(day=1) + datetime.timedelta(days=32*off)).replace(day=1)
        months.append(first.strftime("%B, %Y"))
    start_month = st.selectbox("Internship Start Month", months, index=12)
with d3:
    auto_gender = record.get("gender", "Male") if record else "Male"
    gender = st.selectbox(
        "Student Gender",
        ["Male", "Female"],
        index=0 if auto_gender == "Male" else 1,
        key="student_gender"
    )

# --- Companies ---
st.subheader("3. Internship Organization(s)")
st.caption("Search by typing a few letters/words. Select a company and its address will appear directly in editable fields.")

if "companies" not in st.session_state:
    st.session_state.companies = [{"name": "", "address": ["", "", ""]}]

def on_company_change(i):
    """Auto-fill address when an existing company is selected."""
    selected = st.session_state.get(f"company_{i}", "")
    company_db = st.session_state.company_data
    if selected in company_db:
        address = list(company_db[selected])[:3]
        address += [""] * (3 - len(address))
    else:
        address = ["", "", ""]

    # ADD_NEW_COMPANY is an action, not the organization name itself.
    row_name = "" if selected == ADD_NEW_COMPANY else selected
    st.session_state.companies[i]["name"] = row_name
    st.session_state.companies[i]["address"] = address
    for j in range(3):
        st.session_state[f"addr_{i}_{j}"] = address[j]

for i, row in enumerate(st.session_state.companies):
    st.markdown(f"**Company {i+1}**")

    company_db = st.session_state.company_data
    company_names = sorted(company_db.keys(), key=str.casefold)
    options = [""] + company_names + [ADD_NEW_COMPANY]
    current = row["name"] if row["name"] in company_db else ""
    company_key = f"company_{i}"

    # A newly created company becomes selected after the rerun.
    pending_key = f"pending_company_{i}"
    if pending_key in st.session_state:
        pending_company = st.session_state.pop(pending_key)
        st.session_state.pop(company_key, None)
        st.session_state[company_key] = pending_company

    if company_key not in st.session_state:
        st.session_state[company_key] = current

    st.selectbox(
        "Company",
        options,
        key=company_key,
        on_change=on_company_change,
        args=(i,),
        help="Search an existing company, or choose ➕ Add New Company.",
    )

    selected = st.session_state[company_key]

    if selected == ADD_NEW_COMPANY:
        st.info("Add the company once; it will be saved to the shared company list for future users.")
        new_name = st.text_input(
            "New company name",
            key=f"new_company_name_{i}",
            placeholder="Example: ABC Limited",
        ).strip()
        n1, n2, n3 = st.columns(3)
        new_address = []
        for j, col in enumerate((n1, n2, n3)):
            with col:
                value = st.text_input(
                    f"New address line {j+1}",
                    key=f"new_company_addr_{i}_{j}",
                    placeholder="Address line",
                ).strip()
                new_address.append(value)

        if st.button("Save New Company", key=f"save_new_company_{i}", type="primary"):
            clean_address = [line for line in new_address if line]
            if not new_name:
                st.error("Please enter the new company name.")
            elif not clean_address:
                st.error("Please enter at least one address line.")
            else:
                # Preserve existing capitalization when the same name already exists.
                existing_name = next(
                    (name for name in company_db if name.casefold() == new_name.casefold()),
                    None,
                )
                save_name = existing_name or new_name

                with st.spinner("Saving company to the shared list..."):
                    ok, result = persist_company_to_github(save_name, clean_address)

                if ok:
                    save_name = result
                    st.session_state.company_data[save_name] = clean_address
                    padded = clean_address[:3] + [""] * (3 - len(clean_address[:3]))
                    st.session_state.companies[i] = {"name": save_name, "address": padded}
                    for j in range(3):
                        st.session_state[f"addr_{i}_{j}"] = padded[j]
                    st.session_state[pending_key] = save_name
                    st.success(f"✓ {save_name} saved to companies.json and added to the dropdown.")
                    st.rerun()
                else:
                    st.error(result)

        # Do not show the normal editable-address fields until the new company is saved.
        continue

    if selected in company_db:
        st.success("✓ Address auto-filled below — you can edit it directly for this letter.")
    elif selected:
        st.warning("Address not available in the database. Enter it manually below.")

    a1, a2, a3 = st.columns(3)
    for j, col in enumerate((a1, a2, a3)):
        key = f"addr_{i}_{j}"
        if key not in st.session_state:
            existing = row["address"][j] if j < len(row["address"]) else ""
            st.session_state[key] = existing
        with col:
            st.text_input(
                f"Address line {j+1}",
                key=key,
                placeholder="Address line",
            )
        row["address"][j] = st.session_state[key]

    row["name"] = selected

    if len(st.session_state.companies) > 1:
        if st.button("Remove this company", key=f"remove_{i}"):
            st.session_state.companies.pop(i)
            for key in [f"company_{i}", f"addr_{i}_0", f"addr_{i}_1", f"addr_{i}_2"]:
                st.session_state.pop(key, None)
            st.rerun()

if st.button("＋ Add Another Company", use_container_width=True):
    st.session_state.companies.append({"name": "", "address": ["", "", ""]})
    st.rerun()

st.divider()

# --- Live Preview ---
st.subheader("4. Letter Preview")
st.caption("This preview uses the current editable fields. It is only a preview; the downloaded Word/PDF contains the complete letter.")

preview_entries = []
for row in st.session_state.companies:
    org = row["name"].strip()
    address = [x.strip() for x in row["address"] if x.strip()]
    if org:
        preview_entries.append((org, address))

preview_name = student_name or "Student Name"
preview_id = student_id or "Student ID"
preview_official = OFFICIALS[official_key]
preview_date = letter_date.strftime("%B %d, %Y").replace(" 0", " ")
pronoun = "her" if gender == "Female" else "his"
subject = "she" if gender == "Female" else "he"

if preview_entries:
    for pidx, (porg, paddr) in enumerate(preview_entries, 1):
        address_html = "<br>".join(paddr) if paddr else "<span style='color:#b00020'>Address not entered yet</span>"
        closing = (
            "contact us at the following email, director.cgpar@iub.edu.bd"
            if official_key == "Director"
            else "contact cgp@iub.edu.bd"
        )
        phone_html = (
            f"<br>Phone :{preview_official['phone']}"
            if preview_official.get("show_phone", True) else ""
        )
        st.markdown(
            f"""
            <div style="border:1px solid #d9d9d9;border-radius:10px;padding:24px;background:#fff;line-height:1.65;margin-bottom:16px">
            <div style="text-align:right">{preview_date}</div><br>
            Head of HR<br>
            <b>{porg}</b><br>
            {address_html}<br><br>
            <b>Re: Request for Internship</b><br><br>
            Dear Sir/Madam,<br><br>
            We are pleased to inform you that <b>{preview_name}</b> (ID: <b>{preview_id}</b>)
            is about to complete {pronoun} bachelor with a major in {major} from the {school} of IUB.
            The student is now prepared to join the job market. It will be helpful for
            {subject} to have hands-on-experience in an esteemed organization like yours.<br><br>
            Please confirm if {subject} can start {pronoun} internship from {start_month}.<br><br>
            Thank you for your kind cooperation. For any inquiries, please {closing}.<br><br>
            Yours sincerely,<br><br>
            <b>{preview_official['name']}</b><br>
            {preview_official['title']}<br>
            Office of Career Guidance, Placement & Alumni Relations
            {phone_html}
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.info("Select a company above to see the letter preview here.")

if len(preview_entries) > 3:
    st.info(f"{len(preview_entries) - 3} more company letter(s) will be included in the downloaded Word/PDF.")

# --- Generate ---
st.subheader("5. Generate & Download")
if st.button("Generate Letters", type="primary", use_container_width=True):
    # Existing listed students must be eligible.
    # IDs not found in the list are intentionally allowed with manual Name + ID.
    if record is not None and not can_generate:
        st.error("This Student ID is not eligible for internship based on the existing list.")
        st.stop()

    if not student_id.strip():
        st.error("Please enter Student ID.")
        st.stop()

    if not student_name.strip():
        st.error("Please enter Student Name.")
        st.stop()

    entries = []
    seen = set()
    for i, row in enumerate(st.session_state.companies, 1):
        org = row["name"].strip()
        address = [x.strip() for x in row["address"] if x.strip()]
        if not org and not address:
            continue
        if not org:
            st.error(f"Company {i}: select a company.")
            st.stop()
        if org in seen:
            st.error(f"Duplicate company detected: {org}")
            st.stop()
        if not address:
            st.error(f"Company {i} ({org}): address is missing.")
            st.stop()
        seen.add(org)
        entries.append((org, address))

    if not entries:
        st.error("Please add at least one company.")
        st.stop()

    name = student_name.strip()
    if not name:
        st.error("Please enter the student's name.")
        st.stop()

    with st.spinner("Generating Word and PDF files..."):
        word_bytes = build_docx(
            entries, name, student_id, letter_date, start_month,
            school, major, official_key, gender
        )
        pdf_bytes = build_pdf(
            entries, name, student_id, letter_date, start_month,
            school, major, official_key, gender
        )

    safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "", name).strip() or "Student"
    st.success(f"Done — {len(entries)} company letter(s) generated.")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇ Download Word (.docx)",
            data=word_bytes,
            file_name=f"{safe_name} ({student_id}).docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True
        )
    with c2:
        st.download_button(
            "⬇ Download PDF (.pdf)",
            data=pdf_bytes,
            file_name=f"{safe_name} ({student_id}).pdf",
            mime="application/pdf",
            use_container_width=True
        )

st.caption("Hello CGPAR • Autumn 2026 eligibility data • Corrected gender data • Editable company/address data • Word + PDF export")
