"""The ten families of the catalogue (A–J).

Family codes double as `QuestionFamily` primary keys. Six of the seven codes
seeded by migration 0012 are kept as they were; `OBJECTIVE` is split into the
choice and supply families, and mathematics and primary activities get their
own, because a picker grouped under "Objective" and "Visual" is exactly the
flat list the redesign exists to fix.
"""

from __future__ import annotations

from typing import Dict, Tuple

from services.question_types.spec import Family

FAMILIES: Tuple[Family, ...] = (
    Family("OBJECTIVE_CHOICE", "A", "Objective — Choice Based", "Pick from given options", True, 10),
    Family("OBJECTIVE_SUPPLY", "B", "Objective — Supply Based", "Write a short exact answer", True, 20),
    Family("DESCRIPTIVE", "C", "Descriptive", "Write in own words", False, 30),
    Family("SOURCE_BASED", "D", "Source & Stimulus Based", "Read something, then answer", False, 40),
    Family("VISUAL", "E", "Visual & Diagram", "Draw, label, read a figure", False, 50),
    Family("LANGUAGE", "F", "Language", "Grammar, vocabulary, writing", False, 60),
    Family("MATHEMATICS", "G", "Mathematics", "Solve, prove, construct", False, 70),
    Family("PRACTICAL", "H", "Practical & Computer", "Lab, code, skill-based", False, 80),
    Family("PRIMARY_ACTIVITY", "I", "Primary & Worksheet Activity", "Trace, colour, circle, join", False, 90),
    Family("STRUCTURAL", "J", "Structural Containers", "OR groups, choice pools, sub-parts", False, 100),
)

FAMILIES_BY_CODE: Dict[str, Family] = {family.code: family for family in FAMILIES}
