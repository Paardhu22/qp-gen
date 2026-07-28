import io
import json
import logging
from typing import Any, Dict, List, Optional

import openai
from django.conf import settings

logger = logging.getLogger("[SUBJECT_DETECTION_SERVICE]")

SUPPORTED_SUBJECTS: List[str] = [
    "Mathematics",
    "Science",
    "English",
    "Social Science",
    "Hindi",
    "Telugu",
    "Sanskrit",
    "Computer Science",
]

PROMPT_TEMPLATE = """You are an expert classifier for school educational documents.

Given the extracted text from the first few pages of a PDF, determine the subject.

Return ONLY valid JSON.

Supported subjects:
- Mathematics
- Science
- English
- Social Science
- Hindi
- Telugu
- Sanskrit
- Computer Science

JSON format:
{
  "subject": "Mathematics",
  "confidence": 0.98
}

Do not return explanations, markdown, or any additional text."""


def extract_first_pages_text(buffer: bytes, max_pages: int = 5) -> str:
    """
    Extract text strictly from the first max_pages (default 5 pages) of a PDF.
    Returns concatenated text string.
    """
    text_chunks: List[str] = []

    # 1. Try PyMuPDF (fitz) first
    try:
        import fitz

        doc = fitz.open(stream=buffer, filetype="pdf")
        pages_to_read = min(len(doc), max_pages)
        for page_num in range(pages_to_read):
            page_text = doc[page_num].get_text("text") or ""
            if page_text.strip():
                text_chunks.append(page_text.strip())
        doc.close()
        if text_chunks:
            return "\n\n".join(text_chunks)
    except Exception as exc:
        logger.debug("fitz text extraction failed or not available: %s", exc)

    # 2. Fallback to pypdf
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(buffer))
        pages_to_read = min(len(reader.pages), max_pages)
        for page_num in range(pages_to_read):
            page_text = reader.pages[page_num].extract_text() or ""
            if page_text.strip():
                text_chunks.append(page_text.strip())
        if text_chunks:
            return "\n\n".join(text_chunks)
    except Exception as exc:
        logger.debug("pypdf text extraction failed: %s", exc)

    return "\n\n".join(text_chunks)


def detect_subject_from_pdf_buffer(buffer: bytes) -> Dict[str, Any]:
    """
    Extract text from first 2-5 pages of a PDF buffer and classify subject
    using OpenAI GPT-4.1 Mini.

    Returns:
      {
        "detected": bool,
        "subject": str | None,
        "confidence": float,
        "error": str | None
      }
    """
    extracted_text = extract_first_pages_text(buffer, max_pages=5)
    if not extracted_text.strip():
        logger.warning("No text could be extracted from first 5 pages of PDF")
        return {
            "detected": False,
            "subject": None,
            "confidence": 0.0,
            "error": "No text extracted from PDF first pages",
        }

    # Limit prompt input text length (max 10,000 chars) to keep speed fast & tokens low
    trimmed_text = extracted_text[:10000]

    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        logger.error("OPENAI_API_KEY not configured")
        return {
            "detected": False,
            "subject": None,
            "confidence": 0.0,
            "error": "OpenAI API key not configured",
        }

    model_name = getattr(settings, "POOL_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini"

    client = openai.OpenAI(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": PROMPT_TEMPLATE},
                {
                    "role": "user",
                    "content": f"Extracted PDF First Pages Text:\n\n{trimmed_text}",
                },
            ],
            temperature=0.0,
            max_tokens=150,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or ""
        data = json.loads(content)

        subject = str(data.get("subject") or "").strip()
        confidence = float(data.get("confidence") or 0.0)

        # Re-validate subject matches supported list
        matched_subject = None
        for s in SUPPORTED_SUBJECTS:
            if s.lower() == subject.lower():
                matched_subject = s
                break

        if matched_subject and confidence >= 0.5:
            logger.info("Detected subject '%s' with confidence %.2f", matched_subject, confidence)
            return {
                "detected": True,
                "subject": matched_subject,
                "confidence": confidence,
                "error": None,
            }
        else:
            logger.warning("Subject detection low confidence or unsupported: subject='%s', confidence=%.2f", subject, confidence)
            return {
                "detected": False,
                "subject": None,
                "confidence": confidence,
                "error": "Low confidence or unsupported subject",
            }

    except Exception as exc:
        logger.exception("Error calling OpenAI for subject detection")
        return {
            "detected": False,
            "subject": None,
            "confidence": 0.0,
            "error": str(exc),
        }
