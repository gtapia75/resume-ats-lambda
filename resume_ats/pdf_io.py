"""
PDF input/output for the Resume-to-JD ATS Aligner.
- Extract text from resume and JD PDFs (pdfplumber).
- Build ATS-friendly PDF from structured resume dict (ReportLab).
"""

import os
from typing import Any

import pdfplumber
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


def extract_text_from_pdf(path: str) -> str:
    """
    Extract text from a PDF file. Best for machine-generated (text-based) PDFs.
    For scanned PDFs, text may be empty; caller should warn and suggest OCR.
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"PDF file not found: {path}")
    if not path.lower().endswith(".pdf"):
        raise ValueError(f"Not a PDF file: {path}")

    with pdfplumber.open(path) as pdf:
        parts = []
        for page in pdf.pages:
            text = page.extract_text()
            if text and text.strip():
                parts.append(text.strip())
        return "\n\n".join(parts) if parts else ""


def _ensure_str(value: Any) -> str:
    """Coerce value to str; empty or None -> empty string."""
    if value is None:
        return ""
    s = str(value).strip()
    return s if s else ""


def _add_para(doc_elements: list, text: str, style: ParagraphStyle) -> None:
    if not text:
        return
    doc_elements.append(Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style))
    doc_elements.append(Spacer(1, 0.15 * inch))


def build_resume_pdf(sections_dict: dict, output_path: str) -> None:
    """
    Build an ATS-friendly single-column PDF from the structured resume.
    sections_dict expected keys: name, email (optional), phone (optional),
    professional_summary (optional), experience (list of {company, role, dates, bullets}),
    education (str or list), skills (str or list).
    """
    output_path = os.path.abspath(output_path)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="ResumeTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        spaceAfter=2,
    )
    heading_style = ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        name="Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        name="Bullet",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leftIndent=20,
        spaceAfter=2,
    )
    job_header_style = ParagraphStyle(
        name="JobHeader",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=11,
    )

    elements = []

    # Contact: name, email, phone
    name = _ensure_str(sections_dict.get("name"))
    email = _ensure_str(sections_dict.get("email"))
    phone = _ensure_str(sections_dict.get("phone"))
    contact_parts = [name]
    if email:
        contact_parts.append(email)
    if phone:
        contact_parts.append(phone)
    if contact_parts:
        _add_para(elements, " | ".join(contact_parts), title_style)

    # Professional summary
    summary = _ensure_str(sections_dict.get("professional_summary"))
    if summary:
        _add_para(elements, "<b>Professional Summary</b>", heading_style)
        _add_para(elements, summary, body_style)

    # Work experience (reverse chronological assumed from Claude)
    experience = sections_dict.get("experience") or []
    if experience:
        _add_para(elements, "Work Experience", heading_style)
        for job in experience:
            company = _ensure_str(job.get("company"))
            role = _ensure_str(job.get("role"))
            dates = _ensure_str(job.get("dates"))
            line = company
            if role:
                line += f" — {role}"
            if dates:
                line += f" ({dates})"
            if line:
                _add_para(elements, line, job_header_style)
            bullets = job.get("bullets") or []
            for b in bullets:
                bullet_text = _ensure_str(b)
                if bullet_text:
                    safe = bullet_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    elements.append(Paragraph(f"• {safe}", bullet_style))
                    elements.append(Spacer(1, 2))
        elements.append(Spacer(1, 0.1 * inch))

    # Education
    education = sections_dict.get("education")
    if education is not None:
        _add_para(elements, "Education", heading_style)
        if isinstance(education, list):
            for line in education:
                _add_para(elements, _ensure_str(line), body_style)
        else:
            _add_para(elements, _ensure_str(education), body_style)

    # Skills
    skills = sections_dict.get("skills")
    if skills is not None:
        _add_para(elements, "Skills", heading_style)
        if isinstance(skills, list):
            _add_para(elements, ", ".join(_ensure_str(s) for s in skills if _ensure_str(s)), body_style)
        else:
            _add_para(elements, _ensure_str(skills), body_style)

    doc.build(elements)
