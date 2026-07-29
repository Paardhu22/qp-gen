import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("[PDF_VALIDATION_SERVICE]")


def validate_pdf_metadata_list(pdf_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validates a list of PDF analysis metadata objects:
    1. Rejects non-educational documents (Resume, Invoice, etc.).
    2. Enforces Subject consistency.

    Note: Low-confidence/missing-subject, Chapter, Board, and Class
    consistency checks are disabled for now (SQP testing needs
    multi-chapter uploads that span detection noise in these fields).
    """
    if not pdf_results:
        return {
            "valid": True,
            "subject": None,
            "board": None,
            "class": None,
            "chapter": None,
            "mismatches": [],
        }

    # 1. Non-educational document check
    non_edu = [doc for doc in pdf_results if not doc.get("isEducational")]
    if non_edu:
        bad_files = ", ".join(d.get("fileName", "Unknown") for d in non_edu)
        return {
            "valid": False,
            "errorType": "UNSUPPORTED_DOCUMENT",
            "message": f"This document is not recognized as an educational textbook, worksheet, notes, or question paper: {bad_files}",
            "mismatches": [
                {
                    "file": d.get("fileName"),
                    "documentType": d.get("documentType"),
                    "reason": "Not an educational document",
                }
                for d in non_edu
            ],
        }

    # 3. Subject Validation (only compare files where a subject was actually detected;
    # files with no/low-confidence subject are allowed through rather than blocking upload)
    subjects_map = {d.get("fileName"): d.get("subject") for d in pdf_results if d.get("subject")}
    unique_subjects = set(subjects_map.values())
    if len(unique_subjects) > 1:
        breakdown = [{"file": fname, "subject": subj} for fname, subj in subjects_map.items()]
        return {
            "valid": False,
            "errorType": "SUBJECT_MISMATCH",
            "message": "Multiple subjects detected. Please upload PDFs belonging to the same subject only.",
            "mismatches": breakdown,
        }

    first = pdf_results[0]
    all_chapters = [d.get("chapter") for d in pdf_results if d.get("chapter")]
    unique_chapters_list = list(dict.fromkeys(all_chapters))
    chapter_summary = ", ".join(unique_chapters_list) if unique_chapters_list else None

    return {
        "valid": True,
        "subject": first.get("subject"),
        "board": first.get("board") or "CBSE",
        "class": first.get("class") or "10",
        "chapter": chapter_summary,
        "chapters": unique_chapters_list,
        "mismatches": [],
    }
