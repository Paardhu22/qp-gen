"""Writing Asset Generator — original prompts, rubrics and model answers.

A writing task asks the student to produce language, so the question is a
*scenario*, not a recall probe. The scenario is invented here: a named role, a
real audience, a concrete purpose, a stated word limit. It never asks a student
to write as a character from a prescribed text, because this generator has no
prescribed text — the formats it can write and the constraints it works to both
come from the blueprint slot.

Every asset carries a rubric and a model answer so the same object serves the
paper, the marking scheme and the answer-key service.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Sequence

from services.assets.base import AssetBatchResult, AssetGenerator, AssetRequest
from services.assets.llm import AssetLLMError, request_objects
from services.assets.registry import register
from services.assets.schema import WritingAsset, build_pool_question
from services.assets.validation import validate_asset
from services.pool.schema import PoolValidationError

logger = logging.getLogger("[ASSETS]")

#: Writing formats, glossed for the prompt. Generic composition vocabulary — a
#: blueprint picks the ones it wants in `constraints["formats"]`.
WRITING_FORMAT_GLOSS: Dict[str, str] = {
    "formal_letter_to_authority": (
        "a formal letter from a named student office-bearer to a named official "
        "(Education Secretary, Municipal Commissioner, Principal) proposing or "
        "requesting something, in full letter format"
    ),
    "letter_to_editor": (
        "a letter to the editor of a national daily on a current social, civic "
        "or environmental issue, in full letter format"
    ),
    "letter_of_complaint": "a formal letter of complaint about a product or service, in full letter format",
    "letter_of_enquiry": "a formal letter of enquiry seeking specific information, in full letter format",
    "letter_placing_order": "a formal letter placing a bulk order, in full letter format",
    "analytical_paragraph": (
        "an analytical paragraph task: the question itself supplies two or three "
        "comparable stimulus blocks (excerpts, candidate profiles or data), and "
        "the student analyses them and justifies one choice in a single paragraph"
    ),
    "article": "an article for a school magazine or newspaper on a given topic",
    "speech": "a speech to be delivered at a named school occasion",
    "report": "a report of a school or community event for a newspaper or noticeboard",
    "notice": "a notice for a school noticeboard, in the standard notice format",
    "email": "a formal email to a named recipient with a clear purpose",
    "story": "a story to be completed from a given opening line",
    "debate": "a debate speech for or against a stated motion",
}

_SYSTEM_PROMPT = (
    "You are a senior examiner writing the WRITING SKILLS tasks for a school "
    "language paper.\n\n"
    "You have NO textbook, NO prescribed text and NO uploaded material. Every "
    "scenario, name, place and detail is invented by you for this paper.\n\n"
    "CARDINAL RULE: write the QUESTION ONLY — the scenario, any stimulus, and "
    "the word limit. The `model_answer` field is for the teacher's marking "
    "scheme and is never printed on the question paper.\n\n"
    "Hard rules:\n"
    "1. Never ask the student to write as, to, or about a character, author or "
    "event from any literature syllabus.\n"
    "2. Give the student a named role, a named audience and a concrete purpose. "
    "A task that says only 'write a letter about pollution' is unusable.\n"
    "3. State the word limit inside the scenario text.\n"
    "4. Where the format needs supplied material (an analytical paragraph's "
    "excerpts or profiles, a story's opening line, a report's input hints), "
    "GENERATE that material inside the question.\n"
    "5. Give a `rubric` of 3–5 marking points that add up to the marks stated, "
    "and a `model_answer` a teacher could mark against.\n"
    "6. All names, organisations and figures are imaginary and created for "
    "assessment purposes.\n"
    "7. Write in the language of the subject named in the request.\n\n"
    "Return ONLY JSON of the form:\n"
    "{\n"
    '  "assets": [\n'
    '    {"task_type": "<the requested format label, verbatim>",\n'
    '     "role": "<who the student is>",\n'
    '     "audience": "<who they are writing to>",\n'
    '     "scenario": "<the complete task as the student reads it>",\n'
    '     "word_limit": <int>,\n'
    '     "stimulus": [{"title": "<label>", "body": "<the excerpt or profile>"}],\n'
    '     "rubric": ["<marking point>", "..."],\n'
    '     "model_answer": "<a full sample response>",\n'
    '     "difficulty": "easy|medium|hard"}\n'
    "  ]\n"
    "}\n"
    "Send `stimulus` as [] for formats that do not supply material."
)


class WritingAssetGenerator(AssetGenerator):
    name = "writing_asset_pool"
    source_type = "writing_asset"
    label = "Writing assets (original prompts)"
    asset_types = tuple(WRITING_FORMAT_GLOSS)

    chapter_label = "Writing Skills — Composition Tasks"

    #: Pool type per asset type. Letters are `LETTER`; anything else is a
    #: composition. Kept here rather than in the blueprint because it is a
    #: property of the format, not of the paper.
    def _question_type(self, asset_type: str) -> str:
        if "letter" in asset_type:
            return "LETTER"
        if asset_type == "analytical_paragraph":
            return "ANALYTICAL_PARAGRAPH"
        return "COMPOSITION"

    def generate(self, request: AssetRequest) -> AssetBatchResult:
        result = AssetBatchResult()
        reused = self.reusable(request)
        if reused:
            result.questions.extend(reused)
            result.reused = len(reused)

        for slot in request.slots:
            try:
                produced = self._for_slot(request, slot)
            except AssetLLMError as exc:
                result.failures.append(f"Q{getattr(slot, 'index', '?')}: {exc}")
                continue
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Writing generator crashed: %s", exc, exc_info=True)
                result.failures.append(f"Q{getattr(slot, 'index', '?')}: {exc}")
                continue

            for question, warnings in produced:
                result.questions.append(question)
                result.generated += 1
                result.validation_warnings.extend(warnings)

        return result

    # ── internals ───────────────────────────────────────────────────────

    def _for_slot(self, request: AssetRequest, slot: Any) -> List[tuple]:
        constraints = dict(getattr(slot, "constraints", {}) or {})
        wanted = request.target_for(slot)
        formats = self._formats_for(slot, constraints, wanted)

        raw_assets = request_objects(
            system=_SYSTEM_PROMPT,
            instruction=self._instruction(request, slot, constraints, formats),
            max_output_tokens=max(2000, 700 * len(formats) + 400),
            operation="asset_writing",
            model=request.model,
            user=request.user,
            wrapper_key="assets",
        )

        out: List[tuple] = []
        for raw in raw_assets[: len(formats)]:
            try:
                asset = WritingAsset.from_raw(raw)
            except PoolValidationError as exc:
                logger.debug("Dropped a writing asset: %s", exc)
                continue
            warnings = [
                f"Q{getattr(slot, 'index', '?')} writing asset — {problem}"
                for problem in validate_asset(asset, slot)
            ]
            out.append((self._to_question(request, slot, asset), warnings))

        if not out:
            raise AssetLLMError("no writing asset survived validation")
        return out

    def _formats_for(
        self, slot: Any, constraints: Dict[str, Any], wanted: int
    ) -> List[str]:
        """One format per candidate, cycling the blueprint's declared list.

        A slot with an internal choice wants its two alternatives to be
        genuinely different tasks (a letter to an official OR a letter to the
        editor), which is why the formats cycle rather than repeat.
        """
        declared = [str(f) for f in (constraints.get("formats") or []) if str(f)]
        if not declared:
            declared = [str(getattr(slot, "asset_type", "") or "formal_letter_to_authority")]
        return [declared[i % len(declared)] for i in range(max(1, wanted))]

    def _instruction(
        self,
        request: AssetRequest,
        slot: Any,
        constraints: Dict[str, Any],
        formats: Sequence[str],
    ) -> str:
        marks = int(getattr(slot, "marks", 5) or 5)
        word_limit = constraints.get("word_limit") or 120
        if isinstance(word_limit, (list, tuple)):
            word_limit_text = f"{word_limit[0]}–{word_limit[-1]}"
        else:
            word_limit_text = str(word_limit)

        lines = [
            f"Subject: {request.subject} | Class: {request.class_num} | "
            f"Overall difficulty: {request.difficulty}",
            f"Write {len(formats)} DIFFERENT writing tasks, each worth {marks} marks.",
            f"Word limit for every task: about {word_limit_text} words — state it in the scenario.",
            "Formats, in this exact order:",
        ]
        for position, fmt in enumerate(formats, start=1):
            gloss = WRITING_FORMAT_GLOSS.get(fmt, fmt.replace("_", " "))
            lines.append(f"  {position}. `{fmt}` — {gloss}")

        if constraints.get("stimulus_required"):
            blocks = int(constraints.get("stimulus_blocks") or 2)
            lines.append(
                f"Each task MUST supply {blocks} comparable stimulus blocks inside "
                "the question, every block carrying 3–4 distinct, comparable "
                "attributes so a genuine comparison is possible. State the "
                "comparison criteria in the scenario."
            )
        if constraints.get("single_paragraph"):
            lines.append(
                "The response must be ONE cohesive paragraph — say so explicitly. "
                "It is not an essay, not a letter and not a bulleted list."
            )
        if constraints.get("themes"):
            lines.append(
                "Draw the situations from clearly different areas: "
                + ", ".join(str(t) for t in constraints["themes"])
                + "."
            )
        lines.append(
            f"Give a rubric whose marking points add up to {marks} marks."
        )
        if len(formats) > 1:
            lines.append(
                "These tasks are alternatives for the same question, so they must "
                "be on clearly different situations — a teacher must be able to "
                "print either one."
            )
        return "\n".join(lines)

    def _to_question(self, request: AssetRequest, slot: Any, asset: WritingAsset):
        asset_type = asset.task_type or str(getattr(slot, "asset_type", "") or "")
        return build_pool_question(
            question=asset.render_question(),
            answer=asset.render_answer(),
            marks=int(getattr(slot, "marks", 5) or 5),
            subject=request.subject,
            chapter=self.chapter_label,
            topic=asset_type.replace("_", " ").title(),
            question_type=self._question_type(asset_type),
            generator=self.name,
            asset_type=asset_type,
            source_type=self.source_type,
            pool_id=request.pool_id,
            explanation=(
                "Original writing prompt. All names and details are imaginary "
                "and created for assessment purposes."
            ),
            blooms="CREATE",
            difficulty=asset.difficulty or request.difficulty,
            asset=asset,
            extra_metadata={
                "taskType": asset_type,
                "wordLimit": asset.word_limit,
                "hasRubric": bool(asset.rubric),
                "hasModelAnswer": bool(asset.model_answer),
                "stimulusBlocks": len(asset.stimulus),
            },
        )


register(WritingAssetGenerator())
