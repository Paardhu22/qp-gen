"""Per-slot prompt text — grammar, passage, composition and content instructions — and retrieval queries."""

from typing import List, Dict

from services.generation.planner.slots import QuestionGenerationSlot
from services.generation.planner.subjects import normalize_subject


# ---------------------------------------------------------------------------
# Mode-aware prompt builders (GRAMMAR / COMPOSITION / PASSAGE — never use RAG)
# ---------------------------------------------------------------------------

# Telugu prosody: each named వృత్తం maps to its fixed గణ sequence. Injected into
# the Chandas grammar prompt so the model cannot fabricate a mismatched pattern,
# and used by language_validation for a post-hoc consistency check.
TELUGU_METRE_GANA: Dict[str, str] = {
    "ఉత్పలమాల": "భ ర న భ భ ర వ",
    "చంపకమాల": "న జ భ జ జ జ ర",
    "శార్దూలవిక్రీడితం": "మ స జ స త త గ",
    "మత్తేభవిక్రీడితం": "స భ ర న మ య వ",
}

# Per-subject "attempt any N of M" counts for grammar clusters (M tasks generated).
_GRAMMAR_TASK_PLAN = {
    "english": {"tasks": 12, "attempt": 10},  # Q3: any 10 of 12
    "hindi":   {"tasks": 5,  "attempt": 4},   # Q3–Q6: any 4 of 5
}

# Cardinal rule repeated in every composition prompt.
_COMPOSITION_CARDINAL = (
    "CARDINAL RULE: Generate the QUESTION ONLY (scenario / stimulus / topic + hints + word limit). "
    "NEVER write the student's answer. The question MUST be fully answerable WITHOUT any textbook."
)


def _script_directive(subject_norm: str) -> str:
    if subject_norm == "hindi":
        return ("EVERY character — question text, tasks, options, and the answer key — MUST be in "
                "Devanagari Unicode (U+0900–U+097F). No Roman transliteration anywhere.")
    if subject_norm == "telugu":
        return ("EVERY character — question text, tasks, options, and the answer key — MUST be in "
                "Telugu Unicode (U+0C00–U+0C7F). No Roman transliteration anywhere.")
    return ""


def _slot_contract_footer(slot: QuestionGenerationSlot) -> List[str]:
    """Shared JSON-contract tail for non-CONTENT slots (OR/VI/image handling)."""
    subject_norm = normalize_subject(slot.subject)
    lines = [
        f"The JSON field 'marks' MUST be {slot.marks}.",
        f"The JSON field 'type' MUST be {slot.legacy_type}.",
        "Return exactly one top-level `question` object.",
        "Put the full question (and any sub-tasks/options) in `question.content`. "
        "Put the complete answer key in `question.answer`.",
    ]
    if slot.instruction_hint:
        lines.append(slot.instruction_hint)
    if slot.choice_required:
        or_label = {"hindi": "अथवा", "telugu": "లేదా"}.get(subject_norm, "OR")
        lines.append(
            f"Provide exactly TWO options and add one internal choice in `question.or_choice` "
            f"(the backend prints it as '{or_label}'). Do NOT output the alternative as a separate question object."
        )
    else:
        lines.append("Set `question.or_choice` to null.")
    lines.append("Set `question.image_url` to an empty string.")
    return lines


def _build_grammar_instruction(slot: QuestionGenerationSlot) -> str:
    subject_norm = normalize_subject(slot.subject)
    if subject_norm == "english":
        body = _build_english_grammar_prompt(slot)
    elif subject_norm == "hindi":
        body = _build_hindi_grammar_prompt(slot)
    elif subject_norm == "telugu":
        body = _build_telugu_grammar_prompt(slot)
    else:
        body = [f"Generate a {slot.marks}-mark grammar task set. Each task is self-contained and rule-based."]
    return "\n".join(body + _slot_contract_footer(slot))


def _build_english_grammar_prompt(slot: QuestionGenerationSlot) -> List[str]:
    plan = _GRAMMAR_TASK_PLAN["english"]
    return [
        f"GRAMMAR SLOT (no retrieval — invent every sentence yourself).",
        f"Generate EXACTLY {plan['tasks']} one-mark grammar tasks, numbered I–XII. "
        f"The stem MUST instruct the student to 'Attempt any {plan['attempt']} of the {plan['tasks']} tasks'.",
        "Cover these DISTINCT CBSE Class-10 skills, one per task, with NO point repeated:",
        " I. Tense/verb-form transformation (fill-blank with a bracketed word, e.g. passive participle).",
        " II. Editing / error correction — WRITTEN: give an Error→Correction table for a sentence with ONE error.",
        " III. Tense — present perfect (fill-blank, bracketed verb).",
        " IV. Reported speech — STATEMENT (complete 'They told ... that ___').",
        " V. Prepositions — MCQ with 4 options.",
        " VI. Reported speech — COMMAND/REQUEST (complete 'She warned him ___').",
        " VII. Non-finite / gerund-participle — MCQ with 4 options.",
        " VIII. Editing / error correction — MCQ: identify error+correction from 4 options.",
        " IX. Reported speech — QUESTION (report a yes/no or wh- question).",
        " X. Modals — fill-blank choosing the right modal (must/may/should).",
        " XI. Determiners — MCQ (All/One/Every/A …).",
        " XII. Quantifiers / subject-verb concord — MCQ (little/any/few/least …).",
        "HARD RULES: reported speech appears EXACTLY 3 times (statement, command, question — all distinct); "
        "error correction appears EXACTLY twice (one written-table, one MCQ).",
        "Each sentence sits in its own realistic micro-context (market research, life-skills book, diary, "
        "order letter, opinion column, sports news) that YOU invent — NOT from any uploaded text.",
        "For each MCQ task: exactly 4 options with plausible distractors (common student errors), and mark which is correct. "
        "For each fill/transform task: give the transformed answer.",
        "In `question.answer`, list every task number with its answer (and the correct option letter for MCQ tasks).",
    ]


def _build_hindi_grammar_prompt(slot: QuestionGenerationSlot) -> List[str]:
    plan = _GRAMMAR_TASK_PLAN["hindi"]
    return [
        "व्याकरण स्लॉट (कोई retrieval नहीं — सभी वाक्य स्वयं रचें).",
        _script_directive("hindi"),
        f"EXACTLY {plan['tasks']} एक-अंकीय व्याकरण कार्य बनाइए; प्रश्न में लिखें 'किन्हीं {plan['attempt']} के उत्तर दीजिए' "
        f"(अर्थात् {plan['tasks']} में से कोई {plan['attempt']}).",
        "इस क्लस्टर के सटीक व्याकरण-बिंदु `instruction hint` में दिए गए हैं "
        "(पदबंध / वाक्य-रूपांतरण / समास / मुहावरे). प्रत्येक कार्य में एक भिन्न उप-बिंदु, कोई पुनरावृत्ति नहीं।",
        "प्रत्येक वाक्य एक भिन्न, यथार्थ सन्दर्भ (विद्यालय, प्रकृति, दैनिक जीवन) में हो — किसी पाठ्यपुस्तक से नहीं।",
        "MCQ कार्य हों तो ठीक 4 विकल्प और सही विकल्प चिह्नित करें; भरें/रूपांतरण कार्य का उत्तर दें।",
        "`question.answer` में हर कार्य-संख्या के सामने उसका उत्तर (MCQ के लिए सही विकल्प) दीजिए।",
    ]


def _build_telugu_grammar_prompt(slot: QuestionGenerationSlot) -> List[str]:
    num_tasks = max(1, int(slot.marks))  # 1 mark per MCQ in Telugu clusters
    lines = [
        "వ్యాకరణ స్లాట్ (retrieval లేదు — అన్ని ఉదాహరణలను మీరే సృష్టించండి).",
        _script_directive("telugu"),
        f"సరిగ్గా {num_tasks} బహుళైచ్ఛిక ప్రశ్నలను (ఒక్కొక్కటి 1 మార్కు) తయారు చేయండి. "
        "ప్రతి ప్రశ్నకు సరిగ్గా 4 తెలుగు ఎంపికలు, ఒక సరైన సమాధానం.",
        "ఈ క్లస్టర్ యొక్క ఖచ్చితమైన అంశాలు `instruction hint`లో ఉన్నాయి. ఏ అంశాన్నీ పునరావృతం చేయవద్దు.",
        "`question.answer`లో ప్రతి ప్రశ్నకు సరైన ఎంపిక అక్షరం + వివరణ ఇవ్వండి.",
    ]
    hint = slot.instruction_hint or ""
    if ("ఛందస్సు" in hint) or ("ఛందస" in hint):
        table = "; ".join(f"{metre} = {gana}" for metre, gana in TELUGU_METRE_GANA.items())
        lines.append(
            "ఛందస్సు: పేరు పెట్టిన వృత్తానికి గణ క్రమం ఈ పట్టికతో సరిగ్గా సరిపోలాలి (తప్పక ధృవీకరించండి): "
            + table + "."
        )
    return lines


def _build_passage_instruction(slot: QuestionGenerationSlot) -> str:
    subject_norm = normalize_subject(slot.subject)
    lines = [
        f"UNSEEN PASSAGE SLOT ({slot.marks} marks) — no retrieval.",
        "Generate an ORIGINAL, previously-unseen passage. NEVER reproduce or draw from any uploaded "
        "textbook or prescribed text — the student has not read this passage before.",
    ]
    sd = _script_directive(subject_norm)
    if sd:
        lines.append(sd)
    lines += [
        "Follow the EXACT sub-question count and marks distribution given in the instruction hint. "
        "Sub-questions must progress from lower-order to higher-order thinking.",
    ]
    return "\n".join(lines + _slot_contract_footer(slot))


def _build_composition_instruction(slot: QuestionGenerationSlot) -> str:
    subject_norm = normalize_subject(slot.subject)
    hint = slot.instruction_hint or ""
    lines = [f"WRITING / COMPOSITION SLOT ({slot.marks} marks) — no retrieval.", _COMPOSITION_CARDINAL]
    sd = _script_directive(subject_norm)
    if sd:
        lines.append(sd)

    if subject_norm == "hindi" and "अनुच्छेद" in hint:
        # Free-topic scaffolded paragraph: 3 topics × exactly 3 hint points.
        lines += [
            "Provide EXACTLY 3 topic options. Each topic MUST carry EXACTLY 3 संकेत-बिन्दु (hint points) "
            "that scaffold the paragraph: (1) परिभाषा/अर्थ, (2) आवश्यकता/महत्त्व, (3) भूमिका/प्रभाव.",
            "State the word limit (~120 शब्द) in the stem. A topic with fewer than 3 संकेत-बिन्दु is INVALID.",
            "Topics must be contemporary, socially relevant, age-appropriate (Class X) and NON-duplicative.",
        ]
    elif str(getattr(slot, "asset_type", "") or "") == "analytical_paragraph" or (
        subject_norm == "english" and "analytical" in hint.lower()
    ):
        # Stimulus-based analytical paragraph. Keyed off the slot's declared
        # asset type first — substring-matching the prose hint was fragile, and
        # silently stopped selecting this branch the moment the hint was
        # reworded.
        lines += [
            "This is a STIMULUS-BASED analytical paragraph — NOT a free-topic essay, NOT a letter.",
            "Generate the STIMULUS inside the question: either TWO excerpts/profiles OR THREE profiles, "
            "each option carrying 3–4 DISTINCT comparable attributes so a genuine comparison is possible.",
            "State the comparison criteria and instruct the student to analyse/justify a choice in ONE cohesive "
            "paragraph of 120–150 words. State the word limit explicitly in the stem.",
        ]
    else:
        # Scenario compositions: letters, notice, advert, diary, news report, story, email.
        lines += [
            "Generate a self-contained scenario with: named role/sender, recipient/audience, and clear purpose. "
            "State the word limit explicitly in the stem.",
            "Where the format requires mandatory inputs (news-report ఆధారాలు/hints, a story's opening line), "
            "GENERATE those inputs in the question.",
        ]
    return "\n".join(lines + _slot_contract_footer(slot))


def _slot_instruction(slot: QuestionGenerationSlot) -> str:
    mode = str(getattr(slot, "generation_mode", "CONTENT") or "CONTENT").upper()
    if mode == "GRAMMAR":
        return _build_grammar_instruction(slot)
    if mode == "COMPOSITION":
        return _build_composition_instruction(slot)
    if mode == "PASSAGE":
        return _build_passage_instruction(slot)
    # ---- CONTENT mode (default): unchanged behaviour for Science/Social/Math/Literature ----
    return _build_content_instruction(slot)


def _build_content_instruction(slot: QuestionGenerationSlot) -> str:
    qtype = slot.question_type
    subject_norm = normalize_subject(slot.subject)
    lines = [
        f"Generate exactly ONE {slot.marks}-mark {qtype} question.",
        f"Subject: {slot.subject} | Class: {slot.class_num} | Track: {slot.stream}.",
        f"Difficulty target: {slot.difficulty}.",
        "Use only the retrieved textbook chunks. Do not introduce unsupported facts.",
        f"The JSON field 'marks' MUST be {slot.marks}.",
        f"The JSON field 'type' MUST be {slot.legacy_type}.",
        "Return exactly one top-level `question` object.",
    ]

    if qtype == "MCQ":
        lines.append("Provide exactly four plausible options and one correct answer.")
    elif qtype == "ASSERTION_REASON":
        lines.append(
            "Format content as 'Assertion (A): ...\\nReason (R): ...' and provide the four standard CBSE "
            "assertion-reason direction options: (A) Both A and R true, R is correct explanation; "
            "(B) Both A and R true, R is NOT correct explanation; (C) A true R false; (D) A false R true."
        )
    elif qtype == "CASE_STUDY":
        if subject_norm in ("hindi", "telugu"):
            lines.append(
                "Create the passage and ALL sub-questions in the correct script "
                "(Devanagari for Hindi, Telugu Unicode for Telugu). "
                "Follow the sub-part structure specified in the instruction hint."
            )
        else:
            lines.append("Create a short source-backed passage followed by exactly three sub-questions (1+1+2 marks).")
    elif qtype == "READING_COMP":
        lines.append(
            "Generate an ORIGINAL passage (never reproduce prescribed textbook content). "
            "Follow the exact sub-question count and marks distribution in the instruction hint. "
            "Sub-questions must progress from lower to higher order thinking."
        )
        if subject_norm == "telugu":
            lines.append("EVERY word — passage text, sub-questions, options — MUST be in Telugu Unicode script. No Roman letters.")
    elif qtype == "GRAMMAR":
        lines.append(
            "Generate the exact number of grammar tasks specified in the instruction hint. "
            "Each task is self-contained and worth 1 mark. "
            "Cover the distinct grammar points listed — do not repeat types."
        )
        if subject_norm == "hindi":
            lines.append("ALL grammar tasks and sentences MUST be in Devanagari Unicode. No transliteration.")
    elif qtype == "LETTER":
        lines.append(
            "Generate a formal letter writing task with full format: "
            "sender/date, recipient/designation, subject line, body, closing, signature. "
            "State the word limit in the question stem."
        )
        if subject_norm == "hindi":
            lines.append("The letter task and all instructions MUST be in Devanagari Unicode.")
        elif subject_norm == "telugu":
            lines.append("The entire letter task MUST be in Telugu Unicode script. No Roman transliteration.")
    elif qtype == "LONG_ANSWER":
        lines.append("Require structured reasoning appropriate for a long-answer response.")
        if subject_norm == "telugu":
            lines.append("Generate ALL content in Telugu Unicode script. No Roman transliteration anywhere.")
        elif subject_norm == "hindi":
            lines.append("Generate ALL content in Devanagari Unicode. No transliteration.")

    # Mathematics-specific notes
    if subject_norm == "mathematics":
        lines.append("State π = 22/7 unless otherwise specified.")
        # Uniqueness directive — the parallel generation pipeline can issue
        # several Section A MCQ prompts with overlapping retrieval contexts
        # (this is what caused Q4 and Q7 to print identical sin-A right
        # triangle stems). Tying the slot's `index` and `instruction_hint`
        # into the per-slot prompt forces the model to produce a distinct
        # scenario for THIS slot rather than echoing the retrieval chunk
        # verbatim.
        if slot.instruction_hint:
            lines.append(
                f"UNIQUENESS (slot Q{slot.index}): write a question that "
                f"matches THIS slot's instruction hint exactly — do NOT "
                f"recycle a scenario, values, or wording that could equally "
                f"apply to another slot in the same section. The hint above "
                f"is the only allowed topic for this question."
            )
        # Delimiter contract: the editor parses ONLY \( ... \) and \[ ... \]
        # for KaTeX rendering. Bare $...$ collides with currency literals and
        # $$...$$ has no inline form, so both are rejected. Unicode glyphs
        # (²/³/√/×/÷/π) are still fine when no nesting is needed.
        lines.append(
            "Math typesetting: wrap inline math in \\( ... \\) and display equations in \\[ ... \\]. "
            "Do NOT use $...$ or $$...$$. Example inline: \"Solve \\( x^2 + 3x + 2 = 0 \\).\" "
            "Example display: \"\\[ \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a} \\]\"."
        )
        lines.append("MCQ distractors must be plausible (represent common errors), not random numbers.")

    if slot.instruction_hint:
        lines.append(slot.instruction_hint)

    if slot.choice_required:
        lines.append(
            "Add exactly one internal choice in `question.or_choice`. "
            "Do NOT output the OR alternative as a separate question object. "
            "Never write the word 'OR' before the first alternative or after "
            "the last one — the renderer inserts the OR separator BETWEEN the "
            "two alternatives itself. Never repeat these instructions or any "
            "field name in the question text."
        )
    else:
        lines.append("Set `question.or_choice` to null.")

    if getattr(slot, "requires_figure", False):
        lines.append(
            "MANDATORY FIGURE: This question MUST include an inline SVG diagram in the `figure` field. "
            "Emit `\"figure\": {\"type\": \"svg\", \"content\": \"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200'>...</svg>\"}`. "
            "The SVG must DRAW the actual geometry with shape elements "
            "(<line>, <path>, <circle>, <polygon>, <rect>) — an SVG containing "
            "ONLY <text> labels is rejected as residue. "
            "Label vertices/sides/angles with <text> IN ADDITION to the shapes. "
            "NO <script>, NO <foreignObject>, NO external xlink:href. "
            "A response without a valid `figure` field will be rejected."
        )

    return "\n".join(lines)


def build_retrieval_query(
    *,
    mode: str,
    topic: str,
    subject: str,
    stream: str,
    qtype_name: str,
    marks: int,
    difficulty: str,
    class_num: int,
    choice_required: bool = False,
    instruction_hint: str = "",
    instructions: str = "",
) -> str:
    """
    Build the vector-search query for one slot.

    RAG is meaningful ONLY in CONTENT mode (questions ABOUT studied chapters).
    PASSAGE / GRAMMAR / COMPOSITION slots are generated from rules or a fresh
    scenario, so they MUST NOT retrieve educator-uploaded chunks — they return
    an empty query, and the assembler then injects no [CONTEXT] block.
    """
    if str(mode).upper() != "CONTENT":
        return ""
    query_parts = [
        topic.strip(),
        subject,
        f"class {class_num}",
        stream.replace("_", " "),
        qtype_name.replace("_", " "),
        f"{marks} mark",
        difficulty,
        "internal choice OR alternative" if choice_required else "",
        instruction_hint[:160].strip(),
        instructions[:240].strip(),
    ]
    return " ".join(part for part in query_parts if part)
