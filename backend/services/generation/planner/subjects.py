"""Which CBSE subjects and classes the planner can build, and subject-name normalisation."""

import logging
from typing import Dict, Optional

logger = logging.getLogger("[GEN_ROUTER]")


SUPPORTED_SUBJECTS = {
    "science", "social science",
    "mathematics", "english", "hindi", "telugu",
}

# Subject code → eligible class numbers (new engine only)
BLUEPRINT_SUPPORT: Dict[str, list] = {
    "science":        list(range(1, 11)),
    "social science": list(range(1, 11)),
    "mathematics":    [10],
    "english":        [10],
    "hindi":          [10],
    "telugu":         [10],
}

# Subject aliases → canonical name
_SUBJECT_ALIASES: Dict[str, str] = {
    "maths":          "mathematics",
    "math":           "mathematics",
    "mathematics standard": "mathematics",
    "mathematics basic": "mathematics",
    "maths basic":    "mathematics",
    "math basic":     "mathematics",
    "mathematics (code 041)": "mathematics",
    "mathematics (code 241)": "mathematics",
    "041":            "mathematics",
    "241":            "mathematics",
    "sst":            "social science",
    "social studies": "social science",
    "hindi b":        "hindi",
    "hindi course b": "hindi",
    "english language": "english",
    "english literature": "english",
    "english language and literature": "english",
    "telugu telangana": "telugu",
}


def normalize_subject(subject: str) -> str:
    subject_norm = str(subject or "").strip().lower()
    # Check alias map first
    if subject_norm in _SUBJECT_ALIASES:
        return _SUBJECT_ALIASES[subject_norm]
    if subject_norm in SUPPORTED_SUBJECTS:
        return subject_norm
    if subject_norm.replace("_", " ") in SUPPORTED_SUBJECTS:
        return subject_norm.replace("_", " ")
    # Partial alias matching (e.g. "hindi course b" vs "hindi b")
    for alias, canonical in _SUBJECT_ALIASES.items():
        if alias in subject_norm:
            return canonical
    return subject_norm


def resolve_maths_basic(subject_raw: str, payload: Optional[dict] = None) -> bool:
    """True when the request targets Mathematics **Basic** (Code 241).

    Standard (041) vs Basic (241) share the identical 38-question A–E
    skeleton — only the cognitive-band target prose differs. The tier is a
    selection-time flag, NOT a structural change, so it never touches the
    section plan. Detected from an explicit payload field (``mathLevel`` /
    ``math_level`` / ``mathsLevel``) or a "basic"/"241" marker in the subject
    string. Anything that is not Mathematics, or not explicitly Basic,
    resolves to Standard (False) — no breaking change to existing calls.
    """
    if normalize_subject(subject_raw) != "mathematics":
        return False
    payload = payload or {}
    level = str(
        payload.get("mathLevel")
        or payload.get("math_level")
        or payload.get("mathsLevel")
        or payload.get("maths_level")
        or ""
    ).strip().lower()
    if level in {"basic", "241"}:
        return True
    if level in {"standard", "041"}:
        return False
    raw = str(subject_raw or "").lower()
    return "basic" in raw or "241" in raw


def blueprint_supported(subject_norm: str, class_num: int) -> bool:
    """Returns True if this subject+class combination has a new-engine blueprint."""
    if subject_norm not in BLUEPRINT_SUPPORT:
        return False
    return class_num in BLUEPRINT_SUPPORT[subject_norm]


def extract_class_number(class_value: object, default: int = 10) -> int:
    class_str = str(class_value or "").strip().lower()
    digits = "".join(filter(str.isdigit, class_str))
    return int(digits) if digits else default

def payload_has_blueprint(payload: dict) -> bool:
    """
    Determines if the payload is eligible for the new services.generation.blueprint engine.
    Eligibility rule: board == "CBSE" AND the (subject, class) pair has a
    new-engine blueprint per BLUEPRINT_SUPPORT (Science/Social 1-10;
    Mathematics/English/Hindi/Telugu class 10).
    """
    logger.info(f"[GEN_ROUTER] RAW PAYLOAD:\n{payload}")
    
    if not payload:
        logger.info("[ROUTE_DECISION] Missing payload entirely")
        return False
        
    board = payload.get("board", "")
    subject = payload.get("subject", "")
    # Support class, class_level, gradeClass, grade_class
    class_val = payload.get("class", payload.get("class_level", payload.get("gradeClass", payload.get("grade_class", ""))))
    
    if not board:
        logger.info("[ROUTE_DECISION] Missing 'board' in payload")
        return False
    if not subject:
        logger.info("[ROUTE_DECISION] Missing 'subject' in payload")
        return False
    if not class_val:
        logger.info("[ROUTE_DECISION] Missing 'class'/'gradeClass' in payload")
        return False
        
    board_norm = str(board).strip().upper()
    subject_norm = normalize_subject(subject)
    
    # Class cleanup - extract digits and match 10 (tolerant to Class 10, 10th, 10, etc.)
    class_str = str(class_val).strip().lower()
    digits = "".join(filter(str.isdigit, class_str))
    class_num = int(digits) if digits else None
    
    logger.info(f"[GEN_ROUTER] NORMALIZED VALUES:\nboard={board_norm}\nsubject={subject_norm}\nclass={class_num}")
    
    is_eligible = (
        board_norm == "CBSE"
        and class_num is not None
        and blueprint_supported(subject_norm, class_num)
    )
    
    logger.info(f"[GEN_ROUTER] ELIGIBILITY RESULT: {is_eligible}")
    
    if is_eligible:
        logger.info(f"[ROUTE_DECISION] Using NEW engine for {board_norm} Class {class_num} {subject.strip()}")
    else:
        reason = "Mismatch: "
        if board_norm != "CBSE":
            reason += f"board({board_norm}!=CBSE) "
        elif subject_norm not in BLUEPRINT_SUPPORT:
            reason += f"subject({subject_norm} has no new-engine blueprint) "
        elif class_num is None or not blueprint_supported(subject_norm, class_num):
            eligible = BLUEPRINT_SUPPORT.get(subject_norm, [])
            reason += f"class({class_num} not in {eligible} for {subject_norm})"
        logger.info(f"[ROUTE_DECISION] Falling back to LEGACY engine. Reason: {reason}")
        
    return is_eligible


def default_cbse_question_count(subject: str, class_num: int) -> int:
    subject_norm = normalize_subject(subject)
    if class_num == 10 and subject_norm == "science":
        return 39
    if class_num == 10 and subject_norm == "social science":
        return 38
    if class_num == 10 and subject_norm == "mathematics":
        return 38
    if class_num == 10 and subject_norm == "english":
        return 11
    if class_num == 10 and subject_norm == "hindi":
        return 16
    if class_num == 10 and subject_norm == "telugu":
        return 18
    if class_num >= 8:
        return 20
    if class_num >= 6:
        return 15
    return 10
