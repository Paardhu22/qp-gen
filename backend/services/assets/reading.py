"""Reading Asset Generator — original unseen passages and their assessment.

This generator is the reason the refactor exists. Reading Skills is assessed on
material the student has *not* read: the passage must be written fresh, and
every comprehension, vocabulary, inference, gap-fill, analogy and
paragraph-mapping item must be answerable from that passage alone.

It receives no uploaded content and has no way to reach any. The shape of what
it writes — length, sub-question count, the marks pattern, which skill each
sub-question assesses — comes entirely from the blueprint slot's `constraints`,
so a different board or class changes the blueprint, not this file.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Sequence

from services.assets.base import AssetBatchResult, AssetGenerator, AssetRequest
from services.assets.llm import AssetLLMError, request_objects
from services.assets.registry import register
from services.assets.schema import ReadingAsset, build_pool_question
from services.assets.validation import validate_asset
from services.pool.schema import PoolValidationError

logger = logging.getLogger("[ASSETS]")

#: Generic assessment vocabulary, glossed for the prompt. These are skills, not
#: board structure — a blueprint names them in `constraints["sub_question_skills"]`
#: and this map only explains to the model what each one means.
SKILL_GLOSS: Dict[str, str] = {
    "literal_comprehension": "a direct comprehension question answerable from one stated fact",
    "inference": "an inference the passage supports but never states outright",
    "inference_short_answer": "a short-answer inference the passage supports but never states outright",
    "vocabulary": "the contextual meaning of one word or phrase used in the passage",
    "vocabulary_mcq": "a four-option MCQ on the contextual meaning of a word or phrase from the passage",
    "except_mcq": "a four-option MCQ phrased 'all of the following EXCEPT', where three options are supported by the passage and one is not",
    "true_statement_mcq": "an MCQ (three options) asking which single statement is TRUE about a phrase used in the passage",
    "bracket_gap_fill": "a sentence with one blank, completed by choosing between two words given in brackets",
    "one_word_gap_fill": "a sentence with one blank to be filled with a single suitable word",
    "analogy_completion": "an analogy of the form 'a : b :: ___ : ___' completed by choosing one of two given pairs",
    "phrase_identification": "asks the student to quote the exact phrase from a named paragraph that conveys a given idea",
    "explanation": "a short explanatory answer requiring the student to justify or account for something in the passage",
    "synthesis": "a higher-order answer that combines evidence from more than one paragraph",
    "paragraph_main_idea_mcq": "a table-style MCQ matching main ideas to two named paragraphs, with distractors that misstate them",
    "data_interpretation_mcq": "a four-option MCQ requiring a figure or comparison stated in the passage to be interpreted",
    "relationship": "asks how two ideas, terms or figures in the passage are connected",
    "elaboration": "asks the student to elaborate on an implication of the passage in two or three sentences",
}

_DEFAULT_SKILL = "literal_comprehension"

_SYSTEM_PROMPT = (
    "You are a senior examiner writing the READING SKILLS section of a school "
    "language paper.\n\n"
    "You have NO textbook, NO prescribed text, and NO uploaded material. Every "
    "passage you write is ORIGINAL, written by you now, on a topic of general "
    "interest. The student has never seen it before — that is the entire point "
    "of the section.\n\n"
    "Hard rules:\n"
    "1. Never reference a story, poem, chapter, character or author from any "
    "literature syllabus. If a name is needed, invent one.\n"
    "2. Every sub-question must be answerable from YOUR passage alone. No "
    "outside knowledge, no 'as studied in class'.\n"
    "3. The passage must be factually plausible and age-appropriate, written in "
    "clear expository prose with distinct paragraphs.\n"
    "4. Distractors in multiple-choice items must be plausible and wrong for a "
    "reason drawn from the passage — never filler.\n"
    "5. Give the expected answer for EVERY sub-question. A sub-question without "
    "an answer key is unusable.\n"
    "6. Write in the language of the subject named in the request.\n\n"
    "Return ONLY JSON of the form:\n"
    "{\n"
    '  "assets": [\n'
    "    {\n"
    '      "topic": "<short topic label>",\n'
    '      "passage_style": "<the style requested>",\n'
    '      "difficulty": "easy|medium|hard",\n'
    '      "reading_level": "<the level requested>",\n'
    '      "passage": "<the full passage, paragraphs separated by a blank line>",\n'
    '      "paragraph_map": ["<one-line gist of paragraph 1>", "..."],\n'
    '      "questions": [\n'
    '        {"question": "<text>", "marks": <int>, "paragraph": <int|null>,\n'
    '         "skill": "<the skill requested>", "options": ["<A>", "<B>"],\n'
    '         "answer": "<expected answer>"}\n'
    "      ]\n"
    "    }\n"
    "  ]\n"
    "}\n"
    "Omit `options` (or send []) for any sub-question that is not "
    "multiple-choice."
)


class ReadingAssetGenerator(AssetGenerator):
    name = "reading_asset_pool"
    source_type = "reading_asset"
    label = "Reading assets (original unseen passages)"
    asset_types = (
        "discursive_passage",
        "case_based_passage",
        "factual_passage",
        "unseen_passage",
    )

    #: Bank label these assets are filed under. Keeps them out of the textbook
    #: chapters in the question bank and gives "paper from bank" something
    #: stable to select on.
    chapter_label = "Reading Skills — Unseen Passages"

    def generate(self, request: AssetRequest) -> AssetBatchResult:
        result = AssetBatchResult()
        reused = self.reusable(request)
        if reused:
            result.questions.extend(reused)
            result.reused = len(reused)

        used_topics: List[str] = [str(q.topic or "") for q in reused if q.topic]

        for slot in request.slots:
            try:
                produced = self._for_slot(request, slot, avoid_topics=used_topics)
            except AssetLLMError as exc:
                result.failures.append(f"Q{getattr(slot, 'index', '?')}: {exc}")
                continue
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Reading generator crashed: %s", exc, exc_info=True)
                result.failures.append(f"Q{getattr(slot, 'index', '?')}: {exc}")
                continue

            for question, warnings in produced:
                result.questions.append(question)
                result.generated += 1
                used_topics.append(question.topic)
                result.validation_warnings.extend(warnings)

        return result

    # ── internals ───────────────────────────────────────────────────────

    def _for_slot(
        self,
        request: AssetRequest,
        slot: Any,
        *,
        avoid_topics: Sequence[str],
    ) -> List[tuple]:
        constraints = dict(getattr(slot, "constraints", {}) or {})
        wanted = request.target_for(slot)

        raw_assets = request_objects(
            system=_SYSTEM_PROMPT,
            instruction=self._instruction(
                request, slot, constraints, wanted=wanted, avoid_topics=avoid_topics
            ),
            max_output_tokens=self._token_budget(constraints, wanted),
            operation="asset_reading",
            model=request.model,
            user=request.user,
            wrapper_key="assets",
        )

        out: List[tuple] = []
        for raw in raw_assets[:wanted]:
            try:
                asset = ReadingAsset.from_raw(raw)
            except PoolValidationError as exc:
                logger.debug("Dropped a reading asset: %s", exc)
                continue

            warnings = [
                f"Q{getattr(slot, 'index', '?')} reading asset — {problem}"
                for problem in validate_asset(asset, slot)
            ]
            out.append((self._to_question(request, slot, asset), warnings))

        if not out:
            raise AssetLLMError("no reading asset survived validation")
        return out

    def _instruction(
        self,
        request: AssetRequest,
        slot: Any,
        constraints: Dict[str, Any],
        *,
        wanted: int,
        avoid_topics: Sequence[str],
    ) -> str:
        marks = int(getattr(slot, "marks", 10) or 10)
        style = str(getattr(slot, "asset_type", "") or "unseen_passage")
        words = constraints.get("word_count") or (250, 400)
        low, high = (words if isinstance(words, (list, tuple)) else (words, words))

        lines = [
            f"Subject: {request.subject} | Class: {request.class_num} | "
            f"Overall difficulty: {request.difficulty}",
            f"Write {wanted} DIFFERENT reading assets, each worth {marks} marks in total.",
            f"Passage style: {style}. Length: {low}–{high} words.",
            f"Reading level: {constraints.get('reading_level') or f'class_{request.class_num}'}.",
            f"Split the passage into {constraints.get('paragraphs') or '5 to 7'} paragraphs "
            "separated by a blank line, and give a one-line `paragraph_map` entry for each.",
        ]

        domains = constraints.get("topic_domains")
        if domains:
            lines.append(
                "Choose each topic from a different one of these domains: "
                + ", ".join(str(d) for d in domains)
                + "."
            )
        if avoid_topics:
            lines.append(
                "Do NOT write about any of these topics (already used on this "
                "paper): " + "; ".join(sorted({t for t in avoid_topics if t})[:12]) + "."
            )

        lines.append(self._sub_question_spec(constraints, marks))
        lines.append(
            "Anchor each sub-question to the paragraph it is drawn from via the "
            "`paragraph` field (1-based). Sub-questions must run from lower-order "
            "to higher-order thinking in the order given."
        )
        if wanted > 1:
            lines.append(
                f"The {wanted} assets must be on clearly different topics — they are "
                "alternatives for the same slot, so a teacher must be able to pick "
                "either one."
            )
        return "\n".join(lines)

    def _sub_question_spec(self, constraints: Dict[str, Any], marks: int) -> str:
        pattern = list(constraints.get("sub_question_marks") or [])
        skills = list(constraints.get("sub_question_skills") or [])

        if not pattern:
            count = int(constraints.get("sub_questions") or 0) or max(1, marks)
            pattern = [1] * count
            shortfall = marks - sum(pattern)
            for i in range(min(shortfall, len(pattern))):
                pattern[-(i + 1)] += 1

        lines = [
            f"Write EXACTLY {len(pattern)} sub-questions whose marks sum to {marks}:",
        ]
        for position, item_marks in enumerate(pattern, start=1):
            skill = skills[position - 1] if position <= len(skills) else _DEFAULT_SKILL
            gloss = SKILL_GLOSS.get(str(skill), str(skill).replace("_", " "))
            lines.append(f"  {position}. [{item_marks} mark(s)] {gloss}.")
        return "\n".join(lines)

    def _token_budget(self, constraints: Dict[str, Any], wanted: int) -> int:
        words = constraints.get("word_count") or (250, 400)
        high = words[1] if isinstance(words, (list, tuple)) else words
        # ~1.4 tokens per word of passage, plus ~90 tokens per sub-question of
        # stem + options + answer, plus JSON overhead.
        per_asset = int(high * 1.4) + 90 * int(constraints.get("sub_questions") or 9) + 400
        return max(2500, per_asset * max(1, wanted))

    def _to_question(self, request: AssetRequest, slot: Any, asset: ReadingAsset):
        return build_pool_question(
            question=asset.render_question(),
            answer=asset.render_answer(),
            marks=int(getattr(slot, "marks", asset.total_marks) or asset.total_marks),
            subject=request.subject,
            chapter=self.chapter_label,
            topic=asset.topic,
            question_type="READING_COMP",
            generator=self.name,
            asset_type=str(getattr(slot, "asset_type", "") or "unseen_passage"),
            source_type=self.source_type,
            pool_id=request.pool_id,
            explanation=(
                "Original unseen passage generated for this paper; every "
                "sub-question is answerable from the passage alone."
            ),
            blooms="ANALYZE",
            difficulty=asset.difficulty or request.difficulty,
            asset=asset,
            extra_metadata={
                "readingLevel": asset.reading_level,
                "passageWordCount": asset.word_count,
                "paragraphCount": len(asset.paragraphs),
                "subQuestionCount": len(asset.questions),
            },
        )


register(ReadingAssetGenerator())
