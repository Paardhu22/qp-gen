import hashlib
import io
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import openai
from django.conf import settings

logger = logging.getLogger("[PDF_ANALYSIS_SERVICE]")

# In-memory SHA-256 metadata cache to avoid duplicate GPT calls
_ANALYSIS_CACHE: Dict[str, Dict[str, Any]] = {}

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

BOILERPLATE_PATTERNS = [
    re.compile(r"isbn[:\s]", re.IGNORECASE),
    re.compile(r"all rights reserved", re.IGNORECASE),
    re.compile(r"printed in india", re.IGNORECASE),
    re.compile(r"table of contents", re.IGNORECASE),
    re.compile(r"published by", re.IGNORECASE),
    re.compile(r"copyright\s*©", re.IGNORECASE),
    re.compile(r"price[:\s]*rs", re.IGNORECASE),
]

PROMPT_TEMPLATE = """You are an expert educational document analyzer.

Analyze the extracted text from a school educational PDF.

Determine:
• Subject
• Board
• Class
• Chapter
• Document Type

Supported Subjects:
- Mathematics
- Science
- English
- Social Science
- Hindi
- Telugu
- Sanskrit
- Computer Science

Supported Document Types:
- Textbook
- Question Paper
- Notes
- Worksheet
- Other

Return ONLY valid JSON.

Example JSON output:
{
    "subject": "Mathematics",
    "board": "CBSE",
    "class": "10",
    "chapter": "Quadratic Equations",
    "documentType": "Textbook",
    "confidence": 0.98
}

Return nothing except valid JSON."""


def calculate_sha256(buffer: bytes) -> str:
    """Compute SHA-256 hash of PDF file buffer."""
    h = hashlib.sha256()
    h.update(buffer)
    return h.hexdigest()


def _is_boilerplate_page(text: str) -> bool:
    """Check if page text appears to be cover page, copyright, or table of contents."""
    cleaned = text.strip()
    if not cleaned:
        return True
    
    # Very short pages (< 30 words) with copyright/ISBN keywords are boilerplate
    words = cleaned.split()
    if len(words) < 25:
        for pattern in BOILERPLATE_PATTERNS:
            if pattern.search(cleaned):
                return True

    # Check for table of contents listing
    if "contents" in cleaned.lower()[:200] and re.search(r"chapter\s+\d+", cleaned, re.IGNORECASE):
        return True

    return False


def extract_smart_pages_text(buffer: bytes, max_pages: int = 5) -> Tuple[str, List[int]]:
    """
    Extract text starting from Page 1, skipping boilerplate pages (cover, publisher, TOC, blank).
    Reads at most max_pages meaningful pages.
    
    Returns tuple of (concatenated_text, page_indices_used).
    """
    meaningful_chunks: List[str] = []
    used_pages: List[int] = []

    # 1. Try PyMuPDF (fitz)
    try:
        import fitz

        doc = fitz.open(stream=buffer, filetype="pdf")
        total_pages = len(doc)
        
        for i in range(total_pages):
            if len(used_pages) >= max_pages:
                break
            page_text = doc[i].get_text("text") or ""
            if _is_boilerplate_page(page_text):
                logger.debug("Skipping boilerplate page %d", i + 1)
                continue
            
            meaningful_chunks.append(page_text.strip())
            used_pages.append(i + 1)

        doc.close()
        if meaningful_chunks:
            return "\n\n".join(meaningful_chunks), used_pages
    except Exception as exc:
        logger.debug("PyMuPDF smart extraction failed: %s", exc)

    # 2. Fallback to pypdf
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(buffer))
        for i, page in enumerate(reader.pages):
            if len(used_pages) >= max_pages:
                break
            page_text = page.extract_text() or ""
            if _is_boilerplate_page(page_text):
                continue
            meaningful_chunks.append(page_text.strip())
            used_pages.append(i + 1)

        if meaningful_chunks:
            return "\n\n".join(meaningful_chunks), used_pages
    except Exception as exc:
        logger.debug("pypdf smart extraction failed: %s", exc)

    # 3. OCR Fallback for scanned PDFs (if pytesseract + pdf2image installed)
    try:
        if len(meaningful_chunks) == 0 or sum(len(c) for c in meaningful_chunks) < 100:
            import pytesseract
            from pdf2image import convert_from_bytes

            logger.info("Text extraction yielded minimal text; trying OCR fallback")
            images = convert_from_bytes(buffer, first_page=1, last_page=max_pages)
            for idx, img in enumerate(images):
                ocr_text = pytesseract.image_to_string(img) or ""
                if ocr_text.strip():
                    meaningful_chunks.append(ocr_text.strip())
                    used_pages.append(idx + 1)
    except Exception as ocr_exc:
        logger.debug("OCR fallback unavailable: %s", ocr_exc)

    return "\n\n".join(meaningful_chunks), used_pages


def analyze_pdf_buffer(buffer: bytes, file_name: str = "document.pdf") -> Dict[str, Any]:
    """
    Analyzes an uploaded PDF buffer:
    1. Checks SHA-256 cache.
    2. Extracts smart pages text (max 5 pages).
    3. Calls OpenAI GPT-4.1 Mini to extract Subject, Board, Class, Chapter, DocumentType, Confidence.
    4. Caches & returns metadata result.
    """
    file_hash = calculate_sha256(buffer)
    if file_hash in _ANALYSIS_CACHE:
        logger.info("Cache hit for SHA-256 %s (%s)", file_hash[:8], file_name)
        cached = dict(_ANALYSIS_CACHE[file_hash])
        cached["fileName"] = file_name
        cached["fromCache"] = True
        return cached

    text, pages_read = extract_smart_pages_text(buffer, max_pages=5)
    if not text.strip():
        result = {
            "fileName": file_name,
            "hash": file_hash,
            "subject": None,
            "board": None,
            "class": None,
            "chapter": None,
            "documentType": "Other",
            "confidence": 0.0,
            "isEducational": False,
            "error": "Could not extract text from document",
            "pagesAnalyzed": len(pages_read),
        }
        return result

    # Limit text to first 12,000 characters for token efficiency
    trimmed_text = text[:12000]

    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        return {
            "fileName": file_name,
            "hash": file_hash,
            "subject": None,
            "board": None,
            "class": None,
            "chapter": None,
            "documentType": "Other",
            "confidence": 0.0,
            "isEducational": False,
            "error": "OPENAI_API_KEY not configured",
            "pagesAnalyzed": len(pages_read),
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
                    "content": f"Document Filename: {file_name}\n\nExtracted Content:\n\n{trimmed_text}",
                },
            ],
            temperature=0.0,
            max_tokens=250,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        data = json.loads(content)

        detected_subject = str(data.get("subject") or "").strip()
        board = str(data.get("board") or "").strip()
        cls = str(data.get("class") or "").strip()
        chapter = str(data.get("chapter") or "").strip()
        doc_type = str(data.get("documentType") or "Other").strip()
        confidence = float(data.get("confidence") or 0.0)

        # Match subject against supported list
        matched_subject = None
        for s in SUPPORTED_SUBJECTS:
            if s.lower() == detected_subject.lower():
                matched_subject = s
                break

        is_educational = doc_type in ["Textbook", "Question Paper", "Notes", "Worksheet"]

        analysis_result = {
            "fileName": file_name,
            "hash": file_hash,
            "subject": matched_subject,
            "board": board if board else None,
            "class": cls if cls else None,
            "chapter": chapter if chapter else None,
            "documentType": doc_type,
            "confidence": confidence,
            "isEducational": is_educational,
            "pagesAnalyzed": len(pages_read),
            "error": None if (matched_subject and confidence >= 0.90 and is_educational) else (
                "Document is not a recognized educational type" if not is_educational else "Low confidence detection"
            ),
        }

        # Cache result if valid
        _ANALYSIS_CACHE[file_hash] = analysis_result
        return analysis_result

    except Exception as exc:
        logger.exception("Error analyzing PDF with GPT-4.1 Mini")
        return {
            "fileName": file_name,
            "hash": file_hash,
            "subject": None,
            "board": None,
            "class": None,
            "chapter": None,
            "documentType": "Other",
            "confidence": 0.0,
            "isEducational": False,
            "pagesAnalyzed": len(pages_read),
            "error": str(exc),
        }
