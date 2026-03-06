"""
Resume-to-JD ATS Aligner — main CLI.
Reads resume PDF + JD PDF, tailors resume with Anthropic Claude, writes ATS-friendly PDF.
"""

import argparse
import sys
from pathlib import Path

# Allow running from project root or from resume_ats/
try:
    from resume_ats.pdf_io import extract_text_from_pdf, build_resume_pdf
    from resume_ats.anthropic_tailor import tailor_resume
except ImportError:
    from pdf_io import extract_text_from_pdf, build_resume_pdf
    from anthropic_tailor import tailor_resume


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tailor a resume PDF to a job description PDF using Anthropic Claude; output an ATS-friendly PDF."
    )
    parser.add_argument(
        "resume_pdf",
        type=str,
        help="Path to the candidate's resume PDF",
    )
    parser.add_argument(
        "jd_pdf",
        type=str,
        help="Path to the job description PDF",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="tailored_resume.pdf",
        help="Output PDF path (default: tailored_resume.pdf)",
    )
    args = parser.parse_args()

    resume_path = Path(args.resume_pdf)
    jd_path = Path(args.jd_pdf)
    output_path = Path(args.output)

    # Validate input paths
    if not resume_path.is_file():
        print(f"Error: Resume file not found: {resume_path}", file=sys.stderr)
        sys.exit(1)
    if not jd_path.is_file():
        print(f"Error: Job description file not found: {jd_path}", file=sys.stderr)
        sys.exit(1)

    # Extract text from PDFs
    try:
        resume_text = extract_text_from_pdf(str(resume_path))
    except (FileNotFoundError, ValueError) as e:
        print(f"Error reading resume PDF: {e}", file=sys.stderr)
        sys.exit(1)

    if not resume_text or not resume_text.strip():
        print(
            "Warning: No text could be extracted from the resume PDF. It may be scanned/image-based.",
            file=sys.stderr,
        )
        print("Re-export the resume as a text-based PDF or use an OCR tool.", file=sys.stderr)
        sys.exit(1)

    try:
        jd_text = extract_text_from_pdf(str(jd_path))
    except (FileNotFoundError, ValueError) as e:
        print(f"Error reading job description PDF: {e}", file=sys.stderr)
        sys.exit(1)

    if not jd_text or not jd_text.strip():
        print(
            "Warning: No text could be extracted from the job description PDF.",
            file=sys.stderr,
        )
        print("Re-export the JD as a text-based PDF or use an OCR tool.", file=sys.stderr)
        sys.exit(1)

    # Tailor resume via Anthropic
    try:
        structured = tailor_resume(resume_text, jd_text)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Set ANTHROPIC_API_KEY in your environment or in a .env file.", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Build output PDF
    try:
        build_resume_pdf(structured, str(output_path))
    except Exception as e:
        print(f"Error writing output PDF: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Done. Tailored resume saved to: {output_path.absolute()}")


if __name__ == "__main__":
    main()
