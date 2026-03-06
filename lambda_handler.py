"""
AWS Lambda handler for Resume-to-JD ATS Aligner.
Single function, path-based: POST /get-upload-urls and POST /process.
"""

import json
import os
import uuid
from typing import Any
import traceback

import boto3

# Presigned URL expiry (seconds)
UPLOAD_URL_EXPIRY = 300
DOWNLOAD_URL_EXPIRY = 300

# CORS: set to your front-end origin in production, or "*" for testing
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
APP_KEY = os.environ.get("APP_KEY")

def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": CORS_ORIGIN,
        "Content-Type": "application/json",
    }


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": _cors_headers(),
        "body": json.dumps(body, ensure_ascii=False),
    }


def _get_path(event: dict) -> str:
    """Get request path from API Gateway (HTTP API 2.0, 1.0, or REST)."""
    ctx = event.get("requestContext") or {}
    http = ctx.get("http") or {}
    path = http.get("path") or event.get("rawPath") or event.get("path") or ""
    return path.strip() or "/"


def _get_body(event: dict) -> dict:
    """Parse JSON body from API Gateway event."""
    body = event.get("body")
    if body is None:
        return {}
    if isinstance(body, dict):
        return body
    if isinstance(body, str):
        try:
            return json.loads(body) if body.strip() else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _get_upload_urls(bucket: str) -> dict[str, Any]:
    s3 = boto3.client("s3")
    request_id = str(uuid.uuid4())
    prefix = f"uploads/{request_id}"
    resume_key = f"{prefix}/resume.pdf"
    jd_key = f"{prefix}/jd.pdf"

    resume_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": resume_key, "ContentType": "application/pdf"},
        ExpiresIn=UPLOAD_URL_EXPIRY,
    )
    jd_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": jd_key, "ContentType": "application/pdf"},
        ExpiresIn=UPLOAD_URL_EXPIRY,
    )

    return {"requestId": request_id, "resumeUrl": resume_url, "jdUrl": jd_url}


def _process_request(bucket: str, request_id: str) -> dict[str, Any]:
    s3 = boto3.client("s3")
    prefix = f"uploads/{request_id}"
    resume_key = f"{prefix}/resume.pdf"
    jd_key = f"{prefix}/jd.pdf"
    resume_path = "/tmp/resume.pdf"
    jd_path = "/tmp/jd.pdf"
    out_path = "/tmp/out.pdf"
    out_key = f"outputs/{request_id}/tailored_resume.pdf"

    s3.download_file(bucket, resume_key, resume_path)
    s3.download_file(bucket, jd_key, jd_path)

    from resume_ats.pdf_io import extract_text_from_pdf, build_resume_pdf

    resume_text = extract_text_from_pdf(resume_path)
    jd_text = extract_text_from_pdf(jd_path)

    if not (resume_text and resume_text.strip()):
        return {
            "error": "No se pudo extraer texto del currículum. Comprueba que el PDF no esté vacío, no sea solo imagen y contenga texto seleccionable."
        }

    if not (jd_text and jd_text.strip()):
        return {
            "error": "No se pudo extraer texto de la descripción del puesto. Comprueba que el PDF no esté vacío y contenga texto seleccionable."
        }

    from resume_ats.anthropic_tailor import tailor_resume

    structured = tailor_resume(resume_text, jd_text)
    build_resume_pdf(structured, out_path)

    s3.upload_file(out_path, bucket, out_key, ExtraArgs={"ContentType": "application/pdf"})

    download_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": out_key},
        ExpiresIn=DOWNLOAD_URL_EXPIRY,
    )

    return {"downloadUrl": download_url}


def lambda_handler(event: dict, context: Any) -> dict[str, Any]:
    """
    Handle API Gateway requests.
    Paths: POST /get-upload-urls -> return presigned PUT URLs
           POST /process -> body { "requestId": "..." } -> run aligner, return presigned download URL
    """
    path = _get_path(event)
    method = (event.get("requestContext") or {}).get("http") or {}
    if isinstance(method, dict):
        method = method.get("method", "GET")
    else:
        method = event.get("httpMethod", "GET")

    if method == "OPTIONS":
        return _response(200, {})

    # --- X-App-Key validation ---
    headers = event.get("headers") or {}
    incoming_key = headers.get("x-app-key")

    if APP_KEY and incoming_key != APP_KEY:
        return _response(403, {"error": "Unauthorized"})

    bucket = os.environ.get("RESUME_ATS_BUCKET")
    if not bucket:
        return _response(500, {"error": "RESUME_ATS_BUCKET no configurado"})

    try:
        if path.endswith("/get-upload-urls") or path == "get-upload-urls":
            if method != "POST":
                return _response(405, {"error": "Método no permitido"})
            data = _get_upload_urls(bucket)
            return _response(200, data)

        if path.endswith("/process") or path == "process":
            if method != "POST":
                return _response(405, {"error": "Método no permitido"})
            body = _get_body(event)
            request_id = (body.get("requestId") or "").strip()
            if not request_id:
                return _response(400, {"error": "Falta requestId en el cuerpo"})
            data = _process_request(bucket, request_id)
            if "error" in data:
                return _response(400, data)
            return _response(200, data)

        return _response(404, {"error": "Ruta no encontrada"})
    except Exception as e:
        print("Unhandled exception in lambda_handler:")
        traceback.print_exc()
        return _response(500, {"error": str(e)})
        #return _response(500, {"error": str(e)})
