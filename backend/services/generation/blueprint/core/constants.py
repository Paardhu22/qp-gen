"""
AOS Core — Board-Level Numeric Constants
==========================================
Immutable numeric constraints derived from official CBSE policy.
Zero dependencies.
"""

# ---------------------------------------------------------------------------
# CBSE 2026 Board Constraints
# ---------------------------------------------------------------------------

CBSE_TOTAL_MARKS = 80
CBSE_PRACTICAL_INTERNAL_MARKS = 20
CBSE_EXAM_DURATION_MINUTES = 180
CBSE_COMPETENCY_MINIMUM_RATIO = 0.50
CBSE_MCQ_MINIMUM_RATIO = 0.20
CBSE_LONG_ANSWER_MAX_RATIO = 0.20
CBSE_INTERNAL_CHOICE_MIN_PAIRS = 3

# ---------------------------------------------------------------------------
# IB Board Constraints
# ---------------------------------------------------------------------------

IB_TOTAL_MARKS = 90
IB_EXAM_DURATION_MINUTES = 150
IB_CRITERION_SCALE_MAX = 7

# ---------------------------------------------------------------------------
# Cambridge CIE Constraints
# ---------------------------------------------------------------------------

CAMBRIDGE_TOTAL_MARKS = 100
CAMBRIDGE_EXAM_DURATION_MINUTES = 120

# ---------------------------------------------------------------------------
# Psychometric Model Constants
# ---------------------------------------------------------------------------

FATIGUE_DECAY_RATE = 0.03
ANXIETY_GROWTH_RATE = 0.02
RECOVERY_THRESHOLD = 0.15
MAX_COGNITIVE_LOAD_PER_QUESTION = 6.0

# ---------------------------------------------------------------------------
# Safety Engine Constants
# ---------------------------------------------------------------------------

FORBIDDEN_HALLUCINATION_TERMS = frozenset({
    "flux-gate-membrane",
    "phlogiston",
    "ether-drag",
    "mitochondrial-combustion-valves",
    "cellular-oxygenation-cables",
    "nephron-electricity",
    "chromosomal-voltage",
})

# ---------------------------------------------------------------------------
# Retrieval Constants
# ---------------------------------------------------------------------------

DEFAULT_EMBEDDING_DIMENSION = 8
MAX_RETRIEVAL_CHUNKS = 3
MINIMUM_SIMILARITY_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# File Size Governance
# ---------------------------------------------------------------------------

MAX_LINES_PER_MODULE = 500
