"""The exact CBSE Class 10 blueprints (Mathematics, English, Hindi, Telugu), section by section."""

from typing import List, Dict, Any

from services.generation.pool.schema import DEFAULT_GENERATOR as POOL_GENERATOR
from services.generation.planner.factory import _make_slot
from services.generation.planner.slots import QuestionGenerationSlot


def _exact_class10_blueprint_entries_mathematics() -> List[Dict[str, Any]]:
    """38 questions, 80 marks — CBSE Class 10 Mathematics Standard (Code 041) SQP 2025-26."""
    entries: List[Dict[str, Any]] = []

    # Section A — Q1–Q18 MCQ (1m) + Q19–Q20 ASSERTION_REASON (1m) = 20m
    mcq_hints = [
        "Q1: LCM/HCF by prime factorisation — fundamental theorem of arithmetic",
        "Q2: Find point on y-axis equidistant from two given points (distance from y-axis)",
        "Q3: Condition for pair of linear equations to have no solution (non-parallel lines)",
        "Q4: Tangent lengths from external point to circumscribed circle",
        "Q5: Use sec²θ - tan²θ = 1 identity to evaluate a trigonometric expression",
        "Q6: Identify which of the given expressions is NOT a quadratic equation",
        "Q7: Area of sector or segment of a circle (VI alternative: find arc length from given angle)",
        "Q8: Probability of an event using complement rule (dice or standard cards)",
        "Q9: Solve 2sin2θ = √3 (or similar) to find the angle θ",
        "Q10: Find all possible HCF values given the product of two numbers",
        "Q11: Find height of a cone given its base circumference and volume",
        "Q12: Condition for a quadratic to have equal roots — sign condition on discriminant",
        "Q13: Find area of a sector given arc length and radius",
        "Q14: Find perimeter of a triangle similar to a given triangle using similarity ratio",
        "Q15: Word problem on probability — solve for a variable in a probability equation",
        "Q16: Classify a quadrilateral as parallelogram/rhombus/square from its vertices",
        "Q17: Effect on median when all observations are shifted by a constant (uniform shift rule)",
        "Q18: Find tangent length from an external point given its distance and circle radius",
    ]
    for hint in mcq_hints:
        entries.append({
            "section": "Section A - Objective Questions",
            "stream": "MATHEMATICS",
            "qtype": "MCQ",
            "marks": 1,
            "count": 1,
            "hint": hint,
        })

    # Q19 — ASSERTION_REASON (prime numbers and powers)
    entries.append({
        "section": "Section A - Objective Questions",
        "stream": "MATHEMATICS",
        "qtype": "ASSERTION_REASON",
        "marks": 1,
        "count": 1,
        "hint": (
            "Q19 (Assertion-Reason, Real Numbers): "
            "Assertion (A): 5^n cannot end in the digit 0 for any natural number n. "
            "Reason (R): Any number ending in 0 must have both 2 and 5 as prime factors, but 5^n has only the prime factor 5. "
            "Include the standard CBSE direction block verbatim."
        ),
    })
    # Q20 — ASSERTION_REASON (trigonometry identity)
    entries.append({
        "section": "Section A - Objective Questions",
        "stream": "MATHEMATICS",
        "qtype": "ASSERTION_REASON",
        "marks": 1,
        "count": 1,
        "hint": (
            "Q20 (Assertion-Reason, Trigonometry): "
            "Assertion (A): If cosA + cos²A = 1, then sin²A + sin⁴A = 1. "
            "Reason (R): From cosA = 1 - cos²A = sin²A, we get sin²A + sin⁴A = cosA + cos²A = 1. "
            "Include the standard CBSE direction block verbatim."
        ),
    })

    # Section B — Q21–Q25 VSA SHORT_ANSWER 2m = 10m
    # Tuples: (choice_required, hint, requires_figure)
    vsa_data = [
        (True,  "Q21 (VSA, internal choice): Find the sum of the last n terms of an AP OR find the middle term of an AP.", False),
        (False, "Q22 (VSA): Given sin(A+B) = 1 and cos(A-B) = √3/2, find angle A and angle B where 0 < A,B < 90°.", False),
        (False, "Q23 (VSA): Prove that the ratio of corresponding sides of similar triangles equals the ratio of their corresponding medians.", True),
        (True,  "Q24 (VSA, internal choice): A horse is tied to a peg by a rope; find the area it can graze (sector area) OR find the area of a major segment of a circle.", False),
        (False, "Q25 (VSA): A triangle is circumscribed about a circle; find its sides using tangent properties. VI alternative: find the inradius of a right triangle with legs 6 cm and 8 cm.", False),
    ]
    for choice, hint, req_fig in vsa_data:
        entries.append({
            "section": "Section B - Very Short Answer",
            "stream": "MATHEMATICS",
            "qtype": "SHORT_ANSWER",
            "marks": 2,
            "count": 1,
            "choice_required": choice,
            "requires_figure": req_fig,
            "hint": hint,
        })

    # Section C — Q26–Q31 SA SHORT_ANSWER 3m = 18m
    sa_data = [
        (False, "Q26 (SA): Prove that tangents drawn from an external point to a circle make equal angles with the line joining the point to the centre (∠AOB = 90°). VI alternative: prove ∠APB = 2∠OAB."),
        (False, "Q27 (SA): HCF application — find the maximum length of a measuring tape that can exactly measure two rooms of given dimensions."),
        (False, "Q28 (SA): Find the zeroes of a given quadratic polynomial and verify the relationship between zeroes and coefficients."),
        (True,  "Q29 (SA, internal choice): Prove a given trigonometric identity OR prove an alternate trigonometric identity of equal difficulty."),
        (False, "Q30 (SA): A real-life scenario with two bags containing different coloured balls; compare the probabilities of drawing a specific colour from each bag."),
        (True,  "Q31 (SA, internal choice): Solve a linear equations word problem (income/expenditure ratio) algebraically OR solve graphically and find the area of the triangle formed with the axes. VI alternative: frame and solve an ages-based linear system."),
    ]
    for choice, hint in sa_data:
        entries.append({
            "section": "Section C - Short Answer",
            "stream": "MATHEMATICS",
            "qtype": "SHORT_ANSWER",
            "marks": 3,
            "count": 1,
            "choice_required": choice,
            "hint": hint,
        })

    # Section D — Q32–Q35 LA LONG_ANSWER 5m = 20m
    # Tuples: (choice_required, hint, requires_figure)
    la_data = [
        (False, "Q32 (LA): Speed-distance-time quadratic word problem (e.g., a train covers a distance; if it travels 10 km/h slower it takes 3 h more — find original speed).", False),
        (False, "Q33 (LA): State and prove the Basic Proportionality Theorem (Thales' theorem). Then apply it to find a side length in a given figure.", True),
        (True,  "Q34 (LA, internal choice): Find the total surface area of a solid formed by combining a cone and a cylinder (or cylinder with hemispherical cavity) OR find the volume of an ice-cream cone (cone + hemisphere).", False),
        (True,  "Q35 (LA, internal choice): Find mode and mean from a grouped frequency distribution table, then use the empirical formula to find the median OR construct a 'less than' ogive from the given data and find the median graphically.", False),
    ]
    for choice, hint, req_fig in la_data:
        entries.append({
            "section": "Section D - Long Answer",
            "stream": "MATHEMATICS",
            "qtype": "LONG_ANSWER",
            "marks": 5,
            "count": 1,
            "choice_required": choice,
            "requires_figure": req_fig,
            "hint": hint,
        })

    # Section E — Q36–Q38 CASE_STUDY 4m = 12m (sub-part iii always has OR)
    cs_hints = [
        (
            "Q36 (Case Study, AP): Real-world Arithmetic Progression scenario "
            "(e.g. stadium seating rows, weekly savings, parade formations). "
            "Sub-parts: (i) 1m — identify if it is an AP or find first term/common difference; "
            "(ii) 1m — find a specific term; "
            "(iii) 2m — find sum or nth term (MUST include an internal OR choice for sub-part iii)."
        ),
        (
            "Q37 (Case Study, Coordinate Geometry): Real-world coordinate geometry scenario "
            "(e.g. park layout, town planning on a grid). "
            "VI alternative MUST state explicit numerical coordinates in the question text. "
            "Sub-parts: (i) 1m — find distance between two points; "
            "(ii) 1m — find midpoint or apply section formula; "
            "(iii) 2m — find area of triangle formed by three points OR find ratio in which a point divides a segment "
            "(MUST include internal OR for sub-part iii)."
        ),
        (
            "Q38 (Case Study, Heights & Distances): A ~42 m tall monument/tower with a ~1.6 m observer. "
            "Sub-parts: (i) 1m — find an angle of elevation or depression; "
            "(ii) 1m — find a horizontal distance using tan/sin/cos; "
            "(iii) 2m — find height or distance using two different angles of elevation "
            "(MUST include internal OR for sub-part iii). Use √3 ≈ 1.732."
        ),
    ]
    for hint in cs_hints:
        entries.append({
            "section": "Section E - Case Based Questions",
            "stream": "MATHEMATICS",
            "qtype": "CASE_STUDY",
            "marks": 4,
            "count": 1,
            "choice_required": True,
            "hint": hint,
        })

    return entries


#: Section headings, matching the official paper's own wording.
_ENGLISH_SECTION_READING = "Section A - Reading Skills"
_ENGLISH_SECTION_WRITING = "Section B - Grammar and Writing Skills"
_ENGLISH_SECTION_LITERATURE = "Section C - Literature Textbook"


def _exact_class10_blueprint_entries_english() -> List[Dict[str, Any]]:
    """11 questions, 80 marks — CBSE Class 10 English Language & Literature (184).

    This is the blueprint that routes. Reading, Grammar and Writing declare
    independent generators and get their material written fresh; only Section C
    names `question_pool`, so only Section C reads the uploaded textbook. That
    single change is what stops Reading and Writing inheriting Literature
    questions — 40 of the 80 marks no longer touch the upload at all.

    The structural detail each generator needs lives in `constraints`
    (word counts, the sub-question marks pattern, which skill each part
    assesses, how many grammar tasks and how many to attempt), and the checks
    run on what comes back live in `validation`. Nothing about CBSE is encoded
    in the generators themselves — change these numbers and the same generators
    produce a different board's paper.
    """
    return [
        # ── Section A — Reading Skills (20m) — original unseen passages ──
        {
            "section": _ENGLISH_SECTION_READING,
            "stream": "ENGLISH_READING",
            "qtype": "READING_COMP",
            "mode": "PASSAGE",
            "marks": 10,
            "count": 1,
            "generator": "reading_asset_pool",
            "asset_type": "discursive_passage",
            "constraints": {
                "word_count": (350, 450),
                "paragraphs": "5 to 7",
                "reading_level": "class_10",
                "sub_questions": 8,
                "sub_question_marks": (1, 1, 1, 1, 1, 2, 1, 2),
                "sub_question_skills": (
                    "inference_short_answer",
                    "except_mcq",
                    "bracket_gap_fill",
                    "true_statement_mcq",
                    "analogy_completion",
                    "explanation",
                    "paragraph_main_idea_mcq",
                    "synthesis",
                ),
                "topic_domains": (
                    "culture and heritage",
                    "environment and sustainability",
                    "science and everyday technology",
                    "health and well-being",
                    "work, craft and local economies",
                ),
            },
            "validation": (
                "sub_question_marks_sum",
                "sub_question_count",
                "passage_word_count",
                "paragraph_map_present",
                "paragraph_reference_bounds",
                "option_completeness",
                "answer_key_complete",
                "self_contained",
            ),
            "hint": "Discursive passage: an argued position, not a report of data.",
        },
        {
            "section": _ENGLISH_SECTION_READING,
            "stream": "ENGLISH_READING",
            "qtype": "READING_COMP",
            "mode": "PASSAGE",
            "marks": 10,
            "count": 1,
            "generator": "reading_asset_pool",
            "asset_type": "case_based_passage",
            "constraints": {
                "word_count": (220, 300),
                "paragraphs": "4 to 5",
                "reading_level": "class_10",
                "sub_questions": 9,
                "sub_question_marks": (1, 1, 1, 1, 1, 1, 1, 2, 1),
                "sub_question_skills": (
                    "data_interpretation_mcq",
                    "phrase_identification",
                    "bracket_gap_fill",
                    "vocabulary",
                    "data_interpretation_mcq",
                    "inference_short_answer",
                    "relationship",
                    "elaboration",
                    "one_word_gap_fill",
                ),
                "topic_domains": (
                    "survey findings",
                    "consumer or student habits",
                    "transport and mobility",
                    "media and reading habits",
                    "nutrition and lifestyle",
                ),
            },
            "validation": (
                "sub_question_marks_sum",
                "sub_question_count",
                "passage_word_count",
                "paragraph_map_present",
                "paragraph_reference_bounds",
                "option_completeness",
                "answer_key_complete",
                "self_contained",
            ),
            "hint": (
                "Case-based passage: reports a study or survey and carries "
                "concrete figures the sub-questions can be built on."
            ),
        },
        # ── Section B — Grammar (10m) — rule-based, no textbook ──────────
        {
            "section": _ENGLISH_SECTION_WRITING,
            "stream": "ENGLISH_GRAMMAR",
            "qtype": "GRAMMAR",
            "mode": "GRAMMAR",
            "marks": 10,
            "count": 1,
            "generator": "grammar_asset_pool",
            "asset_type": "grammar_task_set",
            "constraints": {
                "tasks": 12,
                "attempt": 10,
                "max_per_grammar_topic": 1,
                "grammar_topics": (
                    "verb_form_gap_fill",
                    "error_correction_table",
                    "tense_gap_fill",
                    "reported_speech_statement",
                    "preposition_mcq",
                    "reported_speech_command",
                    "non_finite_mcq",
                    "error_correction_mcq",
                    "reported_speech_question",
                    "modal_gap_fill",
                    "determiner_mcq",
                    "quantifier_mcq",
                ),
            },
            "validation": ("task_count", "distinct_grammar_topics", "self_contained"),
            "hint": "Twelve one-mark tasks; the student attempts any ten.",
        },
        # ── Section B — Writing (10m) — original scenarios ───────────────
        {
            "section": _ENGLISH_SECTION_WRITING,
            "stream": "ENGLISH_WRITING",
            "qtype": "LETTER",
            "mode": "COMPOSITION",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "generator": "writing_asset_pool",
            "asset_type": "formal_letter_to_authority",
            "constraints": {
                "word_limit": 120,
                "formats": ("formal_letter_to_authority", "letter_to_editor"),
                "themes": (
                    "civic amenities",
                    "school and community initiatives",
                    "environment",
                    "digital safety",
                    "public health",
                ),
            },
            "validation": ("word_limit_declared", "rubric_present", "self_contained"),
            "hint": "Formal letter with a named sender, named recipient and a clear purpose.",
        },
        {
            "section": _ENGLISH_SECTION_WRITING,
            "stream": "ENGLISH_WRITING",
            "qtype": "ANALYTICAL_PARAGRAPH",
            "mode": "COMPOSITION",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "generator": "writing_asset_pool",
            "asset_type": "analytical_paragraph",
            "constraints": {
                "word_limit": 120,
                "formats": ("analytical_paragraph",),
                "stimulus_required": True,
                "stimulus_blocks": 2,
                "single_paragraph": True,
                "themes": (
                    "choosing between two candidates",
                    "comparing two proposals",
                    "interpreting two sets of figures",
                ),
            },
            "validation": (
                "stimulus_present",
                "word_limit_declared",
                "rubric_present",
                "self_contained",
            ),
            "hint": (
                "Stimulus-based analytical paragraph: the question supplies the "
                "material to compare."
            ),
        },
        # ── Section C — Literature (40m) — the ONLY textbook section ─────
        {
            "section": _ENGLISH_SECTION_LITERATURE,
            "stream": "ENGLISH_LITERATURE",
            "qtype": "EXTRACT_PROSE",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "generator": POOL_GENERATOR,
            "asset_type": "extract_prose",
            "hint": (
                "Q6 (5m): a prose/drama extract from the uploaded chapter, quoted "
                "verbatim, followed by 4 sub-questions worth 2+1+1+1 marks. Mix a "
                "short inferential answer, an MCQ and a one-line contextual item. "
                "The extract must come from the source material, not from memory."
            ),
        },
        {
            "section": _ENGLISH_SECTION_LITERATURE,
            "stream": "ENGLISH_LITERATURE",
            "qtype": "EXTRACT_POETRY",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "generator": POOL_GENERATOR,
            "asset_type": "extract_poetry",
            "hint": (
                "Q7 (5m): a poetry extract from the uploaded chapter, quoted "
                "verbatim with its line breaks, followed by 4 sub-questions worth "
                "1+2+1+1 marks: poetic device or imagery, theme/tone, contextual "
                "meaning, inference. Quote only lines present in the source."
            ),
        },
        {
            "section": _ENGLISH_SECTION_LITERATURE,
            "stream": "ENGLISH_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 12,
            "count": 1,
            "generator": POOL_GENERATOR,
            "asset_type": "short_answer_bundle",
            "constraints": {"questions": 5, "attempt": 4, "marks_each": 3},
            "hint": (
                "Q8 (12m): ONE question object containing FIVE numbered "
                "sub-questions of 3 marks each, headed 'Answer any four of the "
                "following five questions, in about 50 words each'. Draw each "
                "sub-question from a DIFFERENT chapter or poem in the source "
                "material. Every one must require analysis or evaluation, never "
                "plain recall. Give the answer key for all five."
            ),
        },
        {
            "section": _ENGLISH_SECTION_LITERATURE,
            "stream": "ENGLISH_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 6,
            "count": 1,
            "generator": POOL_GENERATOR,
            "asset_type": "short_answer_bundle",
            "constraints": {"questions": 3, "attempt": 2, "marks_each": 3},
            "hint": (
                "Q9 (6m): ONE question object containing THREE numbered "
                "sub-questions of 3 marks each, headed 'Answer any two of the "
                "following three questions, in about 40-50 words'. All three from "
                "DIFFERENT chapters of the source material. Give all three answers."
            ),
        },
        {
            "section": _ENGLISH_SECTION_LITERATURE,
            "stream": "ENGLISH_LITERATURE",
            "qtype": "LONG_ANSWER",
            "marks": 6,
            "count": 1,
            "choice_required": True,
            "generator": POOL_GENERATOR,
            "asset_type": "long_answer",
            "constraints": {"word_limit": (100, 120)},
            "hint": (
                "Q10 (6m): a 100-120 word evaluative answer on theme, character "
                "development or moral message, drawing on the source material. "
                "Not a plot summary."
            ),
        },
        {
            "section": _ENGLISH_SECTION_LITERATURE,
            "stream": "ENGLISH_LITERATURE",
            "qtype": "LONG_ANSWER",
            "marks": 6,
            "count": 1,
            "choice_required": True,
            "generator": POOL_GENERATOR,
            "asset_type": "long_answer",
            "constraints": {"word_limit": (100, 120)},
            "hint": (
                "Q11 (6m): a 100-120 word critical commentary on narrative "
                "technique, character significance or thematic message, drawn from "
                "a DIFFERENT chapter than Q10. Not a plot summary."
            ),
        },
    ]


def _exact_class10_blueprint_entries_hindi() -> List[Dict[str, Any]]:
    """16 questions, 80 marks — CBSE Class 10 Hindi Course B (Code 085) SQP 2025-26."""
    return [
        # खण्ड क — अपठित बोध (14m)
        {
            "section": "खण्ड क - अपठित बोध",
            "stream": "HINDI_READING",
            "mode": "PASSAGE",
            "qtype": "CASE_STUDY",
            "marks": 7,
            "count": 1,
            "hint": (
                "Q1 (7m): Original Hindi prose passage ~250-300 words on theme like कर्म/योग्यता/प्रेरणा. "
                "ALL content in Devanagari Unicode — no Roman transliteration. "
                "Sub-parts (7 total, 7m): (i) 1m MCQ on central fact, (ii) 1m MCQ on purpose/title, "
                "(iii) 1m कथन-कारण MCQ (4 options: i only, ii only, i and ii, neither), "
                "(iv) 1m शब्द-अर्थ/विलोम/समानार्थी, (v) 1m उपयुक्त शीर्षक, "
                "(vi) 1m inference MCQ, (vii) 1m fill-blank from passage."
            ),
        },
        {
            "section": "खण्ड क - अपठित बोध",
            "stream": "HINDI_READING",
            "mode": "PASSAGE",
            "qtype": "CASE_STUDY",
            "marks": 7,
            "count": 1,
            "hint": (
                "Q2 (7m): SECOND original Hindi passage ~250-300 words on a CLEARLY DIFFERENT theme from Q1 "
                "(e.g., प्रकाश/ज्ञान/परंपरा/प्रकृति — NOT कर्म or योग्यता). "
                "ALL content in Devanagari Unicode. "
                "Same 7 sub-part structure as Q1 but with different MCQ types. "
                "Both passages must be original compositions — never reproduce textbook content."
            ),
        },
        # खण्ड ख — व्यावहारिक व्याकरण (16m)
        {
            "section": "खण्ड ख - व्यावहारिक व्याकरण",
            "stream": "HINDI_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "GRAMMAR",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q3 (4m) पदबंध: Generate 5 tasks; student does any 4 (×1m each). "
                "ALL in Devanagari Unicode. "
                "Cover: सर्वनाम पदबंध, विशेषण पदबंध, क्रिया पदबंध, संज्ञा पदबंध, क्रिया-विशेषण पदबंध. "
                "Tasks: identify padband type, make padband from given words, substitute in sentence."
            ),
        },
        {
            "section": "खण्ड ख - व्यावहारिक व्याकरण",
            "stream": "HINDI_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "GRAMMAR",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q4 (4m) वाक्य रूपांतरण: Generate 5 tasks; student does any 4 (×1m). "
                "ALL in Devanagari Unicode. "
                "Cover: सरल→संयुक्त, संयुक्त→मिश्र, मिश्र→सरल वाक्य रूपांतरण, identify type. "
                "Use varied realistic contexts (school, nature, daily life)."
            ),
        },
        {
            "section": "खण्ड ख - व्यावहारिक व्याकरण",
            "stream": "HINDI_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "GRAMMAR",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q5 (4m) समास: Generate 5 tasks; student does any 4 (×1m). "
                "ALL in Devanagari Unicode. "
                "Cover समास bheds: द्वंद्व, द्विगु, कर्मधारय, बहुव्रीहि, नञ् समास. "
                "Tasks: form samashik pad + name bhed, give vigrah + name bhed."
            ),
        },
        {
            "section": "खण्ड ख - व्यावहारिक व्याकरण",
            "stream": "HINDI_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "GRAMMAR",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q6 (4m) मुहावरे: Generate 5 tasks; student does any 4 (×1m). "
                "ALL in Devanagari Unicode. "
                "Tasks: fill blank with correct muhavara, use in sentence, distinguish two similar muhavare, "
                "identify muhavara from a line. "
                "Common examples: नाक में दम करना, हाथ-पाँव फूलना, आँखें खुलना, मुँह में पानी आना."
            ),
        },
        # खण्ड ग — पाठ्यपुस्तक (28m)
        {
            "section": "खण्ड ग - पाठ्यपुस्तक",
            "stream": "HINDI_LITERATURE",
            "qtype": "MCQ",
            "marks": 5,
            "count": 1,
            "hint": (
                "Q7 (5m) पठित गद्यांश: Select extract from a स्पर्श गद्य chapter "
                "(बड़े भाई साहब / डायरी का एक पन्ना / तताँरा-वामीरो कथा / "
                "तीसरी कसम के शिल्पकार / गिरगिट / अब कहाँ दूसरे के दुख से...). "
                "ALL in Devanagari Unicode. "
                "Generate 5 MCQs (1m each) including one कथन-कारण MCQ. "
                "Test: comprehension, vocabulary, inference, character, theme."
            ),
        },
        {
            "section": "खण्ड ग - पाठ्यपुस्तक",
            "stream": "HINDI_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 6,
            "count": 1,
            "hint": (
                "Q8 (6m) गद्य लघु-उत्तर: Generate 4 questions from 4 DIFFERENT स्पर्श गद्य chapters; "
                "student answers any 3 (×2m, ~25-30 words). "
                "ALL in Devanagari Unicode. No chapter repeated. "
                "Chapters: बड़े भाई साहब, डायरी का एक पन्ना, तताँरा-वामीरो कथा, "
                "तीसरी कसम के शिल्पकार शैलेंद्र, गिरगिट, अब कहाँ दूसरे के दुख से दुखी होने वाले."
            ),
        },
        {
            "section": "खण्ड ग - पाठ्यपुस्तक",
            "stream": "HINDI_LITERATURE",
            "qtype": "MCQ",
            "marks": 5,
            "count": 1,
            "hint": (
                "Q9 (5m) पठित काव्यांश: Select extract from a स्पर्श काव्य poem "
                "(साखी / मीरा के पद / बिहारी / मनुष्यता / पर्वत प्रदेश में पावस / "
                "मधुर-मधुर मेरे दीपक जल / तोप / कर चले हम फ़िदा / आत्मत्राण). "
                "ALL in Devanagari Unicode. "
                "Generate 5 MCQs (1m each) — meaning, poetic device, bhav, context, theme."
            ),
        },
        {
            "section": "खण्ड ग - पाठ्यपुस्तक",
            "stream": "HINDI_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 6,
            "count": 1,
            "hint": (
                "Q10 (6m) काव्य लघु-उत्तर: Generate 4 questions from 4 DIFFERENT स्पर्श काव्य poems; "
                "student answers any 3 (×2m, ~25-30 words). "
                "ALL in Devanagari Unicode. No poem repeated. "
                "Poems: साखी, मीरा के पद, बिहारी, मनुष्यता, पर्वत प्रदेश में पावस, "
                "मधुर-मधुर मेरे दीपक जल, तोप, कर चले हम फ़िदा, आत्मत्राण."
            ),
        },
        {
            "section": "खण्ड ग - पाठ्यपुस्तक",
            "stream": "HINDI_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 6,
            "count": 1,
            "hint": (
                "Q11 (6m) संचयन: Generate 3 questions covering ALL 3 संचयन texts; "
                "student answers any 2 (×3m, ~40-50 words). "
                "ALL in Devanagari Unicode. "
                "One question each from: हरिहर काका, सपनों के-से दिन, टोपी शुक्ला. "
                "Test character, theme, or social message — not mere plot recall."
            ),
        },
        # खण्ड घ — रचनात्मक लेखन (22m)
        {
            "section": "खण्ड घ - रचनात्मक लेखन",
            "stream": "HINDI_WRITING",
            "mode": "COMPOSITION",
            "qtype": "LONG_ANSWER",
            "marks": 5,
            "count": 1,
            "hint": (
                "Q12 (5m) अनुच्छेद लेखन: Provide EXACTLY 3 topic options, each with EXACTLY 3 संकेत-बिन्दु; "
                "student writes any 1 (~120 शब्द). "
                "ALL in Devanagari Unicode. State the word limit (शब्द-सीमा) in the stem. "
                "Topics: contemporary and relevant (e.g., डिजिटल भारत, पर्यावरण प्रदूषण, "
                "युवा और खेल, स्वास्थ्य और आहार). "
                "The 3 संकेत-बिन्दु per topic must scaffold: (1) परिभाषा/अर्थ, (2) आवश्यकता/महत्त्व, "
                "(3) भूमिका/प्रभाव. A topic with fewer than 3 संकेत-बिन्दु is INVALID."
            ),
        },
        {
            "section": "खण्ड घ - रचनात्मक लेखन",
            "stream": "HINDI_WRITING",
            "mode": "COMPOSITION",
            "qtype": "LETTER",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q13 (5m) औपचारिक पत्र: Two options — write ONE (~100 words, full format). "
                "ALL in Devanagari Unicode. "
                "(A) Application to Principal requesting a school facility or addressing an issue. "
                "(B) Letter to Editor of a newspaper on a social/environmental issue. "
                "Full format: दिनांक, प्रेषक, सेवा में/श्रीमान् सम्पादक, विषय, विनम्र निवेदन, "
                "प्रार्थना, भवदीय, हस्ताक्षर."
            ),
        },
        {
            "section": "खण्ड घ - रचनात्मक लेखन",
            "stream": "HINDI_WRITING",
            "mode": "COMPOSITION",
            "qtype": "SHORT_ANSWER",
            "marks": 4,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q14 (4m) सूचना लेखन: Two options — write ONE (~60 words). "
                "ALL in Devanagari Unicode. "
                "Topics: school event notice / lost & found / cultural programme / meeting notice. "
                "Full format: शीर्षक सूचना, तिथि, सूचना का विषय, विवरण, हस्ताक्षर/पद."
            ),
        },
        {
            "section": "खण्ड घ - रचनात्मक लेखन",
            "stream": "HINDI_WRITING",
            "mode": "COMPOSITION",
            "qtype": "SHORT_ANSWER",
            "marks": 3,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q15 (3m) विज्ञापन: Two options — make ONE advertisement (~40 words with नारा/tagline). "
                "ALL in Devanagari Unicode. "
                "Topics: natural/organic product, health service, or environment awareness. "
                "Must include: उत्पाद/सेवा का नाम, मुख्य विशेषता, नारा, सम्पर्क (if relevant)."
            ),
        },
        {
            "section": "खण्ड घ - रचनात्मक लेखन",
            "stream": "HINDI_WRITING",
            "mode": "COMPOSITION",
            "qtype": "LONG_ANSWER",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q16 (5m) लघुकथा/ई-मेल: Two options — write ONE (~100 words). "
                "ALL in Devanagari Unicode. "
                "(A) लघुकथा: Provide a vivid opening line (e.g., 'अचानक सन्नाटा टूटा...'); "
                "student continues with पात्र, संघर्ष, समाधान/निष्कर्ष. "
                "(B) ई-मेल: To a friend/official; To/Subject/body/closing format."
            ),
        },
    ]


def _exact_class10_blueprint_entries_telugu() -> List[Dict[str, Any]]:
    """18 questions, 80 marks — CBSE Class 10 Telugu Telangana (Code 089) SQP 2025-26."""
    return [
        # విభాగం ఎ (10m)
        {
            "section": "విభాగం ఎ",
            "stream": "TELUGU_READING",
            "mode": "PASSAGE",
            "qtype": "READING_COMP",
            "marks": 10,
            "count": 1,
            "hint": (
                "Q1 (10m): ORIGINAL ~300-word Telugu passage about a prominent Telugu/Telangana "
                "scholar, writer, poet, or social reformer. "
                "EVERY word — passage, questions, options, section headers — "
                "MUST be in Telugu Unicode script (U+0C00–U+0C7F). No Roman transliteration. "
                "Generate 5 MCQs ×2m (total 10m): "
                "(i) institution/place associated with the person, "
                "(ii) named literary/academic work, "
                "(iii) award/research/recognition, "
                "(iv) source of a quoted line in the passage, "
                "(v) activities/contributions described. "
                "Each MCQ: 4 Telugu-script options."
            ),
        },
        # విభాగం బి (11m)
        {
            "section": "విభాగం బి",
            "stream": "TELUGU_WRITING",
            "mode": "COMPOSITION",
            "qtype": "LETTER",
            "marks": 6,
            "count": 1,
            "hint": (
                "Q2 (6m) లేఖా-రచన: ENTIRE task in Telugu Unicode script only — no Roman letters. "
                "Provide a scenario: named student writer (e.g., రాముడు/లక్ష్మి) writing to a "
                "named recipient (ప్రధానాచార్యులు/తల్లిదండ్రులు/స్నేహితుడు) for a specific purpose "
                "(సౌకర్యం కోసం/సమాచారం/సమస్య పరిష్కారం). ~100 words. "
                "Full format: తేదీ, పంపే వారి పేరు+చిరునామా, స్వీకర్త, విషయం, ముఖ్య విషయం, ముగింపు."
            ),
        },
        {
            "section": "విభాగం బి",
            "stream": "TELUGU_WRITING",
            "mode": "COMPOSITION",
            "qtype": "LONG_ANSWER",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q3 (5m) ప్రక్రియ: Two options — write ONE (~100 words). "
                "ENTIRE task in Telugu Unicode script only. "
                "(a) దినచర్య (Diary): entry for a meaningful day (school event/trip/achievement). "
                "Include: తేదీ, వారం, సమయం, అనుభవం, భావాలు, ముగింపు. "
                "(b) వార్తా-రచన (News report): Write using EXACTLY 4-6 given ఆధారాలు listed in Telugu. "
                "Include: శీర్షిక, తేదీ+స్థలం, ముఖ్య విషయం, వివరాలు, ముగింపు."
            ),
        },
        # విభాగం సి (29m)
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q4 (4m) సంధి: 4 MCQs in Telugu Unicode only (1m each). "
                "(i) identify సంధి సూత్రం for a given example, "
                "(ii) identify correct విభక్తి ప్రత్యయం, "
                "(iii) split (విడదీయడం) a sandhi word, "
                "(iv) combine (సంధి చేయడం) two words. "
                "Cover: అకార/ఇకార/ఉకార/గసడదవాదేశ సంధి. 4 Telugu options each."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q5 (4m) ఛందస్సు: 4 MCQs in Telugu Unicode only (1m each). "
                "Use a verse line from prescribed texts. "
                "(i) identify యతి మైత్రి, "
                "(ii) name the వృత్తం (ఉత్పలమాల/చంపకమాల/శార్దూలవిక్రీడితం/మత్తేభవిక్రీడితం), "
                "(iii) identify గణాలు (pattern), "
                "(iv) count పాదాక్షరం. "
                "Gana patterns MUST match the named metre exactly."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q6 (4m) సమాసం: 4 MCQs in Telugu Unicode only (1m each). "
                "Cover 4 different types: రూపక సమాసం, ద్విగు సమాసం, ద్వంద్వ సమాసం, బహువ్రీహి సమాసం. "
                "Test: lakshana of samasa, give example, identify type of given samashta-pada."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q7 (4m) అలంకారాలు: 4 MCQs in Telugu Unicode only (1m each). "
                "(i) identify అలంకారం in a given Telugu sentence, "
                "(ii) give lakshana of a named alankara, "
                "(iii) identify ఉపమానం in a given simile, "
                "(iv) choose correct example for a named alankara. "
                "Cover: ఉపమా, రూపక, ఉత్ప్రేక్ష, అతిశయోక్తి అలంకారాలు."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 2,
            "count": 1,
            "hint": (
                "Q8 (2m) పర్యాయ పదాలు: 2 MCQs in Telugu Unicode only (1m each). "
                "Test synonyms: (i) identify correct పర్యాయ పదం for a given word, "
                "(ii) find the word that does NOT belong to the synonym group."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 2,
            "count": 1,
            "hint": (
                "Q9 (2m) జాతీయాలు: 2 MCQs in Telugu Unicode only (1m each). "
                "(i) meaning of a given Telugu idiom (జాతీయం), "
                "(ii) identify the sentence that correctly uses a given idiom."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 2,
            "count": 1,
            "hint": (
                "Q10 (2m) సామెతలు: 2 MCQs in Telugu Unicode only (1m each). "
                "(i) meaning of a given Telugu proverb (సామెత), "
                "(ii) match a described situation to the appropriate సామెత."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 2,
            "count": 1,
            "hint": (
                "Q11 (2m) పాఠ్యాంశ ప్రక్రియ: 2 MCQs in Telugu Unicode only (1m each). "
                "(i) given a chapter name, identify its ప్రక్రియ (గద్యం/పద్యం/ఏకాంకిక/కథ/వ్యాసం), "
                "(ii) given a ప్రక్రియ, identify which prescribed chapter belongs to it."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "MCQ",
            "marks": 5,
            "count": 1,
            "hint": (
                "Q12 (5m) పరిచిత గద్యాంశం: Extract from a prescribed Telugu prose/verse chapter. "
                "ENTIRE question in Telugu Unicode only. "
                "5 MCQs (1m each): speaker/character identification, event sequence, "
                "vocabulary meaning in context, inference, author's purpose/tone."
            ),
        },
        # విభాగం డి (30m)
        {
            "section": "విభాగం డి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q13 (4m) సంగ్రహ జవాబులు: 4 questions in Telugu Unicode; student answers any 2 (×2m, ~50-60 words). "
                "Theme: నీతి/పాత్ర/తాత్విక (ethics/character/philosophical). "
                "Chapters: గోలకొండ, కొత్తబాట, లక్ష్యసిద్ధి, భిక్ష. "
                "Questions must require interpretation — not mere factual recall."
            ),
        },
        {
            "section": "విభాగం డి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q14 (4m) సంగ్రహ జవాబులు-2: 4 questions in Telugu Unicode; "
                "student answers any 2 (×2m, ~50-60 words). "
                "Theme: సమాజం/ప్రకృతి/జీవితం (society/nature/life). "
                "Use chapters DIFFERENT from Q13. Questions probe social/natural/life values."
            ),
        },
        {
            "section": "విభాగం డి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "LONG_ANSWER",
            "marks": 4,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q15 (4m) విపులంగా: Two options in Telugu Unicode — write ONE (~120 words). "
                "(a) గోలకొండ పాఠం: analyse theme/characters/social message. "
                "(b) కొత్తబాట పాఠం: analyse theme/moral/significance. "
                "Analytical essay — NOT plot summary."
            ),
        },
        {
            "section": "విభాగం డి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "LONG_ANSWER",
            "marks": 4,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q16 (4m) విపులంగా-2: Two options in Telugu Unicode — write ONE (~120 words). "
                "(a) శతక నీతులు: explain philosophical/ethical message of a given శతక verse. "
                "(b) జీవనభాషం సందేశం: explain life-message of a prescribed poem/prose piece. "
                "Critical reflection required — not mere paraphrase."
            ),
        },
        {
            "section": "విభాగం డి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "LONG_ANSWER",
            "marks": 6,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q17 (6m) పద్య అన్వయ క్రమం + ప్రతిపదార్థాలు: Two padya options in Telugu Unicode — do ONE. "
                "question_text = full padya verse in Telugu Unicode. "
                "answer_key = అన్వయ క్రమం (prose order) + ప్రతిపదార్థాలు (word-by-word meanings). "
                "Source: కాళహస్తీశ్వర శతకం or జీవనభాషం (or other prescribed padya)."
            ),
        },
        {
            "section": "విభాగం డి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "LONG_ANSWER",
            "marks": 8,
            "count": 1,
            "hint": (
                "Q18 (8m) ఉపవాచకం (రామాయణం): Generate ALL 4 questions in Telugu Unicode; "
                "student answers any 2 (×4m, ~100-120 words each). "
                "(i) వాలి-సుగ్రీవ విరోధం — causes and resolution, "
                "(ii) రామాయణం ఎందుకు చదవాలి — relevance and values, "
                "(iii) భరత పాదుక పట్టాభిషేకం — significance and devotion, "
                "(iv) రామ-రావణ యుద్ధం — key events and moral lessons. "
                "Answers require analytical/reflective response — not plot retelling."
            ),
        },
    ]


def _exact_class10_blueprint_entries(subject_norm: str) -> List[Dict[str, Any]]:
    if subject_norm == "mathematics":
        return _exact_class10_blueprint_entries_mathematics()
    if subject_norm == "english":
        return _exact_class10_blueprint_entries_english()
    if subject_norm == "hindi":
        return _exact_class10_blueprint_entries_hindi()
    if subject_norm == "telugu":
        return _exact_class10_blueprint_entries_telugu()
    if subject_norm == "social science":
        return [
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "History Q1 must be a match-the-following MCQ with Column I and Column II."},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "History Q2 must be a picture/image identification MCQ."},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "History Q3 must be a standard four-option MCQ."},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "History Q4 must be quotation/source-based."},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "SHORT_ANSWER", "marks": 2, "count": 1, "choice_required": True},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "SHORT_ANSWER", "marks": 3, "count": 1, "choice_required": True},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "LONG_ANSWER", "marks": 5, "count": 1, "choice_required": True},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "CASE_STUDY", "marks": 4, "count": 1, "hint": "CBQ must have exactly three sub-questions totalling 4 marks: 1+1+2."},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "DIAGRAM", "marks": 2, "count": 1, "hint": "History map work: identify or locate two historical places on an India outline map."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Geography Q10 must be a standard MCQ."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Geography Q11 must be a diagram/table empty-box fill MCQ."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Geography Q12 must be news article or data-based."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Geography Q13 must be statement classification."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Geography Q14 must be standard factual."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Geography Q15 must be policy/scheme evaluation."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "SHORT_ANSWER", "marks": 2, "count": 1, "hint": "Geography has no 3-mark SA in exact mode."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "LONG_ANSWER", "marks": 5, "count": 1, "choice_required": True},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "CASE_STUDY", "marks": 4, "count": 1, "hint": "CBQ must have exactly three sub-questions totalling 4 marks: 1+2+1."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "DIAGRAM", "marks": 3, "count": 1, "choice_required": True, "hint": "Geography map work: Part I 1 mark with internal OR; Part II 2 marks locating two features."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Civics Q20 must be multi-statement type."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Civics Q21 must be cartoon-based."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Civics Q22 must be case scenario or constitutional reasoning."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "ASSERTION_REASON", "marks": 1, "count": 1, "hint": "Assertion-Reason appears only in Civics for Social Science."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "SHORT_ANSWER", "marks": 2, "count": 2, "hint": "Civics has exactly two VSA questions and no OR at 2 marks."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "SHORT_ANSWER", "marks": 3, "count": 1, "hint": "Civics SA has no OR."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "LONG_ANSWER", "marks": 5, "count": 1, "choice_required": True},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "CASE_STUDY", "marks": 4, "count": 1, "hint": "CBQ must have exactly three sub-questions totalling 4 marks: 1+1+2."},
            {"section": "Section D - Economics", "stream": "ECONOMICS", "qtype": "MCQ", "marks": 1, "count": 6, "hint": "Economics MCQs must vary across factual, inference, example, justification, and match-column forms."},
            {"section": "Section D - Economics", "stream": "ECONOMICS", "qtype": "SHORT_ANSWER", "marks": 3, "count": 3, "hint": "Economics has exactly three 3-mark SA questions, no VSA, no CBQ, no map."},
            {
                "section": "Section D - Economics",
                "stream": "ECONOMICS",
                "qtype": "LONG_ANSWER",
                "marks": 5,
                "count": 1,
                "choice_required": True,
            },
        ]

    return [
        {"section": "Section A - Biology", "stream": "BIOLOGY", "qtype": "MCQ", "marks": 1, "count": 7, "hint": "Standard Biology MCQs come before Assertion-Reason."},
        {"section": "Section A - Biology", "stream": "BIOLOGY", "qtype": "ASSERTION_REASON", "marks": 1, "count": 2},
        {
            "section": "Section A - Biology",
            "stream": "BIOLOGY",
            "qtype": "SHORT_ANSWER",
            "marks": 2,
            "count": 3,
            "choice_first": 1,
        },
        {
            "section": "Section A - Biology",
            "stream": "BIOLOGY",
            "qtype": "SHORT_ANSWER",
            "marks": 3,
            "count": 2,
        },
        {
            "section": "Section A - Biology",
            "stream": "BIOLOGY",
            "qtype": "CASE_STUDY",
            "marks": 4,
            "count": 1,
            "choice_required": True,
            "hint": "Biology competency/case-based question with exactly three sub-questions totalling 4 marks and a partial OR.",
        },
        {
            "section": "Section A - Biology",
            "stream": "BIOLOGY",
            "qtype": "LONG_ANSWER",
            "marks": 5,
            "count": 1,
            "choice_required": True,
        },
        {"section": "Section B - Chemistry", "stream": "CHEMISTRY", "qtype": "MCQ", "marks": 1, "count": 7, "hint": "Standard Chemistry MCQs come before Assertion-Reason."},
        {"section": "Section B - Chemistry", "stream": "CHEMISTRY", "qtype": "ASSERTION_REASON", "marks": 1, "count": 1},
        {"section": "Section B - Chemistry", "stream": "CHEMISTRY", "qtype": "SHORT_ANSWER", "marks": 2, "count": 1},
        {"section": "Section B - Chemistry", "stream": "CHEMISTRY", "qtype": "SHORT_ANSWER", "marks": 3, "count": 2, "choice_first": 1},
        {
            "section": "Section B - Chemistry",
            "stream": "CHEMISTRY",
            "qtype": "CASE_STUDY",
            "marks": 4,
            "count": 1,
            "hint": "Chemistry case-based question.",
        },
        {"section": "Section B - Chemistry", "stream": "CHEMISTRY", "qtype": "LONG_ANSWER", "marks": 5, "count": 1, "choice_required": True},
        {"section": "Section C - Physics", "stream": "PHYSICS", "qtype": "MCQ", "marks": 1, "count": 2, "hint": "Standard Physics MCQs come before Assertion-Reason."},
        {"section": "Section C - Physics", "stream": "PHYSICS", "qtype": "ASSERTION_REASON", "marks": 1, "count": 1},
        {"section": "Section C - Physics", "stream": "PHYSICS", "qtype": "SHORT_ANSWER", "marks": 2, "count": 1, "choice_required": True},
        {"section": "Section C - Physics", "stream": "PHYSICS", "qtype": "SHORT_ANSWER", "marks": 2, "count": 1},
        {"section": "Section C - Physics", "stream": "PHYSICS", "qtype": "SHORT_ANSWER", "marks": 3, "count": 1, "hint": "This Physics question must be a numerical calculation using values not used elsewhere."},
        {"section": "Section C - Physics", "stream": "PHYSICS", "qtype": "SHORT_ANSWER", "marks": 3, "count": 2, "hint": "Physics optics/circuit/data interpretation questions."},
        {
            "section": "Section C - Physics",
            "stream": "PHYSICS",
            "qtype": "CASE_STUDY",
            "marks": 4,
            "count": 1,
            "choice_required": True,
            "hint": "Physics competency/case-based question must have exactly three sub-questions totalling 4 marks and partial OR.",
        },
        {
            "section": "Section C - Physics",
            "stream": "PHYSICS",
            "qtype": "LONG_ANSWER",
            "marks": 5,
            "count": 1,
            "choice_required": True,
        },
    ]


def _build_exact_cbse_class10_plan(
    *,
    topic: str,
    difficulty: str,
    subject_norm: str,
    subject_label: str,
    instructions: str,
) -> List[QuestionGenerationSlot]:
    slots: List[QuestionGenerationSlot] = []

    for entry in _exact_class10_blueprint_entries(subject_norm):
        choice_first = int(entry.get("choice_first") or 0)

        for local_index in range(int(entry["count"])):
            qtype_name = str(entry["qtype"])
            marks = int(entry["marks"])
            slots.append(
                _make_slot(
                    index=len(slots) + 1,
                    section_title=str(entry["section"]),
                    subject=subject_label,
                    stream=str(entry["stream"]),
                    qtype_name=qtype_name,
                    marks=marks,
                    difficulty=difficulty,
                    class_num=10,
                    topic=topic,
                    instructions=instructions,
                    choice_required=bool(entry.get("choice_required")) or local_index < choice_first,
                    requires_figure=bool(entry.get("requires_figure")),
                    instruction_hint=str(entry.get("hint") or ""),
                    mode=str(entry.get("mode") or "CONTENT").upper(),
                    # Routing declaration. Entries that omit these — every
                    # subject except English — fall through to the textbook
                    # pool defaults, so their plans are unchanged.
                    generator=str(entry.get("generator") or POOL_GENERATOR),
                    asset_type=str(entry.get("asset_type") or ""),
                    constraints=entry.get("constraints") or {},
                    validation=entry.get("validation") or (),
                )
            )

    total_marks = sum(slot.marks for slot in slots)
    if total_marks != 80:
        raise ValueError(f"Internal CBSE Class 10 blueprint error: expected 80 marks, got {total_marks}.")
    _expected_counts = {
        "mathematics": 38,
        "english": 11,
        "hindi": 16,
        "telugu": 18,
        "social science": 38,
        "science": 39,
    }
    expected_count = _expected_counts.get(subject_norm, 39)
    if len(slots) != expected_count:
        raise ValueError(f"Internal CBSE Class 10 blueprint error: expected {expected_count} questions, got {len(slots)}.")

    # ── Math-specific structural invariants ──────────────────────────────
    # Every real CBSE Class 10 Maths board paper places the 2 Assertion-Reason
    # questions at slots Q19 and Q20 of Section A (after 18 MCQs). Random
    # placement breaks teacher trust, so we hard-fail rather than emit a
    # paper that violates the official Sample Question Paper layout.
    if subject_norm == "mathematics":
        section_a_slots = [s for s in slots if str(s.section_title).startswith("Section A")]
        if len(section_a_slots) != 20:
            raise ValueError(
                f"Mathematics Section A must have exactly 20 questions, got {len(section_a_slots)}."
            )
        for idx, s in enumerate(section_a_slots[:18], start=1):
            if s.legacy_type != "MCQ":
                raise ValueError(
                    f"Mathematics Section A invariant: Q{idx} must be MCQ, got {s.legacy_type}."
                )
        for q_num, s in zip((19, 20), section_a_slots[18:20]):
            if s.legacy_type != "ASSERTION_REASON":
                raise ValueError(
                    f"Mathematics Section A invariant: Q{q_num} must be ASSERTION_REASON, got {s.legacy_type}."
                )

    # ── Mathematics-only figure cap (max 2) ───────────────────────────────
    # Math papers must contain at most 2 figure-bearing questions across
    # the whole paper.
    if subject_norm == "mathematics":
        picture_slots = [s for s in slots if s.requires_figure]
        if len(picture_slots) > 2:
            raise ValueError(
                f"Mathematics figure cap exceeded: blueprint produced "
                f"{len(picture_slots)} figure slots; max 2."
            )
    return slots
