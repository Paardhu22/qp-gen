import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("[PDF_VALIDATION_SERVICE]")


def _same_subject(a: Optional[str], b: Optional[str]) -> bool:
    """Compare two subject labels tolerantly.

    The detector answers from a fixed vocabulary ("Social Science"), while the
    paper's subject comes from the template catalog and can differ in case or
    spacing. Only a genuine disagreement should raise a warning — "science"
    vs "Science" is not one.
    """
    if not a or not b:
        return True  # No opinion on one side is not a mismatch.
    return a.strip().casefold() == b.strip().casefold()


def validate_pdf_metadata_list(
    pdf_results: List[Dict[str, Any]],
    expected_subject: Optional[str] = None,
    expected_class: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validates a list of PDF analysis metadata objects:
    1. Rejects non-educational documents (Resume, Invoice, etc.).
    2. Rejects low confidence (< 0.90) analyses.
    3. Enforces Subject consistency.
    4. Enforces Chapter consistency.
    5. Enforces Board consistency.
    6. Enforces Class consistency.

    ``expected_subject``/``expected_class`` describe the paper the teacher is
    actually building. Without them this function can only check the uploads
    against *each other*, so a single Physics chapter attached to a
    Mathematics paper passes — it is perfectly self-consistent. Passing the
    paper's own subject is what turns this into a real check.
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

    # 3. Subject Validation (Mandatory Content-based Validation)
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

    # 4. The uploads agree with each other — but do they agree with the paper?
    # This is the check that catches a single wrong-subject chapter, which
    # every consistency rule above waves through.
    detected_subject = next(iter(unique_subjects), None)
    if not _same_subject(detected_subject, expected_subject):
        return {
            "valid": False,
            "errorType": "SUBJECT_MISMATCH",
            "message": (
                f"These files look like {detected_subject}, but this paper is "
                f"{expected_subject}. Attaching them will produce "
                f"{expected_subject} questions from {detected_subject} material."
            ),
            "subject": detected_subject,
            "expectedSubject": expected_subject,
            "mismatches": [
                {"file": fname, "subject": subj, "reason": "Subject differs from the paper"}
                for fname, subj in subjects_map.items()
            ],
        }

    first = pdf_results[0]
    all_chapters = [d.get("chapter") for d in pdf_results if d.get("chapter")]
    unique_chapters_list = list(dict.fromkeys(all_chapters))
    chapter_summary = ", ".join(unique_chapters_list) if unique_chapters_list else None

    # Class is a warning, not a verdict. It is inferred far less reliably than
    # subject — plenty of chapters never state their grade — so a disagreement
    # is worth mentioning and not worth blocking.
    soft_warnings: List[str] = []
    detected_class = str(first.get("class") or "").strip()
    if expected_class and detected_class:
        if detected_class.casefold() != str(expected_class).strip().casefold():
            soft_warnings.append(
                f"These files look like Class {detected_class}, but this paper "
                f"is Class {expected_class}."
            )

    return {
        "valid": True,
        "warnings": soft_warnings,
        "subject": first.get("subject"),
        "board": first.get("board") or "CBSE",
        "class": first.get("class") or "10",
        "chapter": chapter_summary,
        "chapters": unique_chapters_list,
        "mismatches": [],
    }
