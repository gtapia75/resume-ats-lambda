"""
Resume tailoring via Anthropic Claude API.
Takes raw resume and JD text, returns a structured resume dict for PDF build.
"""

import json
import os
import re
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import anthropic


SYSTEM_PROMPT = """You are an expert resume writer who tailors resumes to specific job descriptions for ATS (Applicant Tracking Systems).

Your task:
1. Align the candidate's resume to the job description: use the same keywords, phrasing, and focus areas where truthful.
2. Keep a professional, clear, and concise tone throughout.
3. For each role, rewrite bullet points to emphasize quantitative results and outcomes (metrics, percentages, time saved, scale, impact). Use numbers wherever possible. If the original bullet has no numbers, infer or add plausible, conservative metrics that fit the described work.
4. Preserve truth: do not invent jobs, dates, or qualifications. Only rephrase and emphasize what is supported by the original resume.
5. Output ATS-friendly content: use standard section headers, no graphics or complex layout descriptions.

You must respond with exactly one JSON object and no other text before or after (or wrap it in a markdown code block with language "json"). The JSON must have this structure:

{
  "name": "Full Name",
  "email": "email@example.com",
  "phone": "optional phone or empty string",
  "professional_summary": "2-4 sentences tailored to this role, with keywords from the JD.",
  "experience": [
    {
      "company": "Company Name",
      "role": "Job Title",
      "dates": "e.g. Jan 2020 – Present",
      "bullets": [
        "Outcome-focused bullet with numbers where possible.",
        "Another bullet."
      ]
    }
  ],
  "education": "Degree, Institution, Year" or ["line1", "line2"] for multiple lines,
  "skills": "Comma-separated skills aligned to JD" or ["skill1", "skill2"]
}

List experience in reverse chronological order (most recent first). Include all roles from the original resume unless clearly irrelevant; you may condense or merge only if appropriate. Every bullet should aim for impact with quantitative results where possible."""


def _extract_json_from_response(text: str) -> str:
    """Handle response that may be wrapped in ```json ... ```."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def _validate_and_normalize(data: dict) -> dict:
    """Ensure required keys exist; normalize for build_resume_pdf."""
    required = ["name", "experience"]
    for key in required:
        if key not in data:
            data[key] = "" if key == "name" else []
    if "email" not in data:
        data["email"] = ""
    if "phone" not in data:
        data["phone"] = ""
    if "professional_summary" not in data:
        data["professional_summary"] = ""
    if "education" not in data:
        data["education"] = ""
    if "skills" not in data:
        data["skills"] = ""
    return data


def tailor_resume(resume_text: str, jd_text: str) -> dict[str, Any]:
    """
    Call Anthropic Claude to tailor the resume to the JD. Returns a structured
    dict suitable for build_resume_pdf. Raises on API or JSON parse errors.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not api_key.strip():
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. Set it in your environment or in a .env file."
        )

    model = os.environ.get("ANTHROPIC_RESUME_MODEL", "claude-sonnet-4-20250514")
    user_content = f"""Below is the candidate's current resume and the target job description. Return the tailored resume as a single JSON object with the structure specified in your instructions.

--- RESUME ---
{resume_text}

--- JOB DESCRIPTION ---
{jd_text}

--- END ---

Respond with only the JSON object (or a markdown code block containing the JSON)."""

    client = anthropic.Anthropic()
    try:
        message = client.messages.create(
            model=model,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.APIError as e:
        raise RuntimeError(
            f"Anthropic API error: {e}. Check your ANTHROPIC_API_KEY and network."
        ) from e

    # Get assistant text from first content block
    content = message.content
    if not content or not isinstance(content, list):
        raise RuntimeError("Empty or unexpected response from Claude.")
    block = content[0]
    if getattr(block, "type", None) != "text":
        raise RuntimeError("Claude response did not contain text.")
    response_text = getattr(block, "text", "") or ""

    raw_json = _extract_json_from_response(response_text)
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Claude returned invalid JSON. Please try again. Parse error: {e}"
        ) from e

    if not isinstance(data, dict):
        raise RuntimeError("Claude response JSON is not an object.")

    return _validate_and_normalize(data)
