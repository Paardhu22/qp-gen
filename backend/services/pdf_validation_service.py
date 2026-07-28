import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("[PDF_VALIDATION_SERVICE]")


def validate_pdf_metadata_list(pdf_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validates a list of PDF analysis metadata objects:
    1. Rejects non-educational documents (Resume, Invoice, etc.).
    2. Rejects low confidence (< 0.90) analyses.
    3. Enforces Subject consistency.
    4. Enforces Chapter consistency.
    5. Enforces Board consistency.
    6. Enforces Class consistency.
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

    # 2. Low confidence check
    low_conf = [doc for doc in pdf_results if (doc.get("confidence") or 0.0) < 0.90 or not doc.get("subject")]
    if low_conf:
        bad_files = ", ".join(d.get("fileName", "Unknown") for d in low_conf)
        return {
            "valid": False,
            "errorType": "LOW_CONFIDENCE",
            "message": f"Unable to confidently determine the subject for: {bad_files}",
            "mismatches": [
                {
                    "file": d.get("fileName"),
                    "subject": d.get("subject") or "Unknown",
                    "confidence": d.get("confidence") or 0.0,
                }
                for d in low_conf
            ],
        }

    # 3. Subject Validation
    subjects_map = {d.get("fileName"): d.get("subject") for d in pdf_results}
    unique_subjects = set(subjects_map.values())
    if len(unique_subjects) > 1:
        breakdown = [{"file": fname, "subject": subj} for fname, subj in subjects_map.items()]
        return {
            "valid": False,
            "errorType": "SUBJECT_MISMATCH",
            "message": "Multiple subjects detected. Please upload PDFs belonging to the same subject only.",
            "mismatches": breakdown,
        }

    # 4. Chapter Validation (if multiple chapters detected)
    chapters_map = {d.get("fileName"): d.get("chapter") for d in pdf_results if d.get("chapter")}
    unique_chapters = set(chapters_map.values())
    if len(unique_chapters) > 1:
        breakdown = [{"file": fname, "chapter": chap} for fname, chap in chapters_map.items()]
        return {
            "valid": False,
            "errorType": "CHAPTER_MISMATCH",
            "message": "Multiple chapters detected. Please upload PDFs from the same chapter.",
            "mismatches": breakdown,
        }

    # 5. Board Validation
    boards_map = {d.get("fileName"): d.get("board") for d in pdf_results if d.get("board")}
    unique_boards = set(boards_map.values())
    if len(unique_boards) > 1:
        breakdown = [{"file": fname, "board": b} for fname, b in boards_map.items()]
        return {
            "valid": False,
            "errorType": "BOARD_MISMATCH",
            "message": "Multiple boards detected. Please upload PDFs from the same board.",
            "mismatches": breakdown,
        }

    # 6. Class Validation
    classes_map = {d.get("fileName"): d.get("class") for d in pdf_results if d.get("class")}
    unique_classes = set(classes_map.values())
    if len(unique_classes) > 1:
        breakdown = [{"file": fname, "class": c} for fname, c in classes_map.items()]
        return {
            "valid": False,
            "errorType": "CLASS_MISMATCH",
            "message": "Multiple classes detected. Please upload PDFs from the same class.",
            "mismatches": breakdown,
        }

    first = pdf_results[0]
    return {
        "valid": True,
        "subject": first.get("subject"),
        "board": first.get("board") or "CBSE",
        "class": first.get("class") or "10",
        "chapter": first.get("chapter"),
        "mismatches": [],
    }
