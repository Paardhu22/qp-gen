"""Grammar Asset Generator — rule-based tasks with their own reusable pool.

Grammar is assessed on *rules*, not on content. A grammar item built from a
story sentence tests whether the student remembers the story; a grammar item
built from an invented micro-context tests whether they can apply the rule.
This generator only ever does the second, because it is never given a story.

The reusable unit is the single one-mark task, not the printed bundle. A CBSE
grammar question is "complete any ten of twelve", so the bundle is assembled at
paper time from whatever tasks exist — banked from earlier generations, topped
up with fresh ones for whichever grammar points are short. That is what makes
the grammar pool genuinely reusable rather than regenerated wholesale.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Sequence

from services.assets.base import AssetBatchResult, AssetGenerator, AssetRequest
from services.assets.llm import AssetLLMError, request_objects
from services.assets.registry import register
from services.assets.schema import (
    GrammarAsset,
    GrammarTaskSet,
    build_pool_question,
)
from services.assets.validation import validate_asset
from services.pool.schema import PoolValidationError

logger = logging.getLogger("[ASSETS]")

#: Grammar points, glossed for the prompt. Generic grammar vocabulary — a
#: blueprint names the ones it wants in `constraints["grammar_topics"]` and
#: this map only tells the model what each label means.
GRAMMAR_TASK_GLOSS: Dict[str, str] = {
    "verb_form_gap_fill": "fill one blank with the correct form of a word given in brackets",
    "tense_gap_fill": "fill one blank with the correct tense of a verb given in brackets",
    "modal_gap_fill": "fill one blank by choosing the correct modal from two given in brackets",
    "determiner_gap_fill": "fill one blank with the correct determiner",
    "preposition_gap_fill": "fill one blank with the correct preposition",
    "determiner_mcq": "a four-option MCQ choosing the correct determiner for a blank",
    "quantifier_mcq": "a four-option MCQ choosing the correct quantifier for a blank",
    "preposition_mcq": "a four-option MCQ choosing the correct preposition for a blank",
    "non_finite_mcq": "a four-option MCQ choosing the correct non-finite form (gerund / participle / infinitive)",
    "subject_verb_concord": "a four-option MCQ choosing the verb form that agrees with the subject",
    "error_correction_table": (
        "give a sentence containing exactly ONE error and ask for it in an "
        "Error / Correction table; the answer names the error word and its correction"
    ),
    "error_correction_mcq": (
        "give a sentence containing exactly ONE error and four Error/Correction "
        "pairs as options, only one of which is right"
    ),
    "editing_gap_fill": "an omission/editing item where one word is missing from a sentence",
    "reported_speech_statement": "report a direct STATEMENT by completing 'They told … that ___'",
    "reported_speech_command": "report a direct COMMAND, REQUEST or WARNING by completing the reporting sentence",
    "reported_speech_question": "report a direct QUESTION (yes/no or wh-) by completing the reporting sentence",
    "sentence_transformation": "rewrite a sentence as directed (active/passive, simple/complex, affirmative/negative)",
}

_SYSTEM_PROMPT = (
    "You are a senior examiner writing GRAMMAR items for a school language "
    "paper.\n\n"
    "You have NO textbook, NO prescribed text, NO story and NO uploaded "
    "material. Every sentence you use is invented by you.\n\n"
    "Hard rules:\n"
    "1. Never build a task on a character, plot, poem or author from any "
    "literature syllabus. Grammar tests the rule, not the story.\n"
    "2. Each task is worth exactly ONE mark and is self-contained: the student "
    "needs the sentence in front of them and nothing else.\n"
    "3. Put every sentence in its own small realistic micro-context that you "
    "invent — a market-research report, a diary entry, a teacher's notebook, a "
    "sports bulletin, an order letter, an opinion column.\n"
    "4. Multiple-choice tasks have exactly four options, with distractors that "
    "represent errors a real student would make.\n"
    "5. Every task must carry its exact answer, and a one-line explanation of "
    "the rule being tested.\n"
    "6. Write in the language of the subject named in the request.\n\n"
    "Return ONLY JSON of the form:\n"
    "{\n"
    '  "tasks": [\n'
    '    {"grammar_topic": "<the requested label, verbatim>",\n'
    '     "context": "<one-line description of the invented micro-context>",\n'
    '     "question": "<the full task as the student reads it>",\n'
    '     "options": ["<A>", "<B>", "<C>", "<D>"],\n'
    '     "answer": "<the exact expected answer>",\n'
    '     "difficulty": "easy|medium|hard",\n'
    '     "explanation": "<the rule in one line>"}\n'
    "  ]\n"
    "}\n"
    "Omit `options` (or send []) for any task that is not multiple-choice."
)


def _topic_key(value: Any) -> str:
    return str(value or "").strip().lower()


class GrammarAssetGenerator(AssetGenerator):
    name = "grammar_asset_pool"
    source_type = "grammar_asset"
    label = "Grammar assets (rule-based tasks)"
    asset_types = ("grammar_task_set", "grammar_task")

    chapter_label = "Grammar — Rule-Based Tasks"

    #: Asset type stamped on the atomic one-mark tasks that make up a set.
    atomic_asset_type = "grammar_task"

    def generate(self, request: AssetRequest) -> AssetBatchResult:
        result = AssetBatchResult()
        rng = random.Random(f"grammar:{request.pool_id}")

        banked = self.reusable(request)
        available = self._group_by_topic(banked)
        result.reused = len(banked)

        for slot in request.slots:
            try:
                self._for_slot(request, slot, available, rng, result)
            except AssetLLMError as exc:
                result.failures.append(f"Q{getattr(slot, 'index', '?')}: {exc}")
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Grammar generator crashed: %s", exc, exc_info=True)
                result.failures.append(f"Q{getattr(slot, 'index', '?')}: {exc}")

        return result

    # ── internals ───────────────────────────────────────────────────────

    def _group_by_topic(
        self, questions: Sequence[Any]
    ) -> Dict[str, List[GrammarAsset]]:
        """Rebuild atomic grammar assets from banked pool questions."""
        grouped: Dict[str, List[GrammarAsset]] = {}
        for question in questions:
            payload = (question.metadata or {}).get("asset")
            if not isinstance(payload, dict) or "grammarTopic" not in payload:
                continue
            asset = GrammarAsset(
                grammar_topic=str(payload.get("grammarTopic") or ""),
                question=str(payload.get("question") or question.question),
                answer=str(payload.get("answer") or question.answer),
                options=list(payload.get("options") or question.options or []),
                explanation=str(payload.get("explanation") or ""),
                difficulty=str(payload.get("difficulty") or question.difficulty),
                context=str(payload.get("context") or ""),
            )
            grouped.setdefault(_topic_key(asset.grammar_topic), []).append(asset)
        return grouped

    def _for_slot(
        self,
        request: AssetRequest,
        slot: Any,
        available: Dict[str, List[GrammarAsset]],
        rng: random.Random,
        result: AssetBatchResult,
    ) -> None:
        constraints = dict(getattr(slot, "constraints", {}) or {})
        marks = int(getattr(slot, "marks", 10) or 10)
        task_count = int(constraints.get("tasks") or marks)
        attempt = int(constraints.get("attempt") or marks)
        sets_wanted = request.target_for(slot)

        topics = [str(t) for t in (constraints.get("grammar_topics") or [])]
        if not topics:
            # No declared topic list: ask for an even spread over everything the
            # generator knows how to write.
            known = list(GRAMMAR_TASK_GLOSS)
            topics = [known[i % len(known)] for i in range(task_count)]
        topics = topics[:task_count]
        while len(topics) < task_count:
            topics.append(topics[len(topics) % max(1, len(topics))])

        # One task per declared topic per set, so no set repeats a grammar point
        # and the alternatives are genuinely different papers.
        deficit: Dict[str, int] = {}
        for topic in topics:
            have = len(available.get(_topic_key(topic), []))
            need = sets_wanted - have
            if need > 0:
                deficit[topic] = deficit.get(topic, 0) + need

        if deficit:
            fresh = self._write_tasks(request, deficit, constraints)
            for asset in fresh:
                available.setdefault(_topic_key(asset.grammar_topic), []).append(asset)
                result.questions.append(
                    self._atomic_question(request, asset)
                )
                result.generated += 1

        consumed: Dict[str, int] = {}
        composed = 0
        for _ in range(sets_wanted):
            tasks: List[GrammarAsset] = []
            for topic in topics:
                key = _topic_key(topic)
                candidates = [
                    a for a in available.get(key, []) if a not in tasks
                ]
                if not candidates:
                    continue
                offset = consumed.get(key, 0) % len(candidates)
                tasks.append(candidates[offset])
                consumed[key] = consumed.get(key, 0) + 1

            if not tasks:
                continue

            rng.shuffle(tasks)
            task_set = GrammarTaskSet(
                tasks=tasks,
                attempt=min(attempt, len(tasks)),
                difficulty=request.difficulty,
            )
            warnings = [
                f"Q{getattr(slot, 'index', '?')} grammar set — {problem}"
                for problem in validate_asset(task_set, slot)
            ]
            result.validation_warnings.extend(warnings)
            result.questions.append(
                self._set_question(request, slot, task_set)
            )
            result.generated += 1
            composed += 1

        if not composed:
            # The atomic tasks written above stay in `result` — they are still
            # reusable material for the next paper, even though this slot
            # could not be composed.
            raise AssetLLMError("no grammar task set could be composed")

    def _write_tasks(
        self,
        request: AssetRequest,
        deficit: Dict[str, int],
        constraints: Dict[str, Any],
    ) -> List[GrammarAsset]:
        total = sum(deficit.values())
        lines = [
            f"Subject: {request.subject} | Class: {request.class_num} | "
            f"Overall difficulty: {request.difficulty}",
            f"Write EXACTLY {total} one-mark grammar tasks, distributed like this:",
        ]
        for topic, count in deficit.items():
            gloss = GRAMMAR_TASK_GLOSS.get(topic, topic.replace("_", " "))
            lines.append(f"  • {count} × `{topic}` — {gloss}")
        lines.append(
            "Set each task's `grammar_topic` to the label above, verbatim. "
            "Every task must use a DIFFERENT invented micro-context and a "
            "different sentence — no two tasks may share a scenario."
        )
        if constraints.get("register"):
            lines.append(f"Register: {constraints['register']}.")

        raw = request_objects(
            system=_SYSTEM_PROMPT,
            instruction="\n".join(lines),
            max_output_tokens=max(1500, total * 140 + 400),
            operation="asset_grammar",
            model=request.model,
            user=request.user,
            wrapper_key="tasks",
        )

        assets: List[GrammarAsset] = []
        for item in raw:
            try:
                assets.append(GrammarAsset.from_raw(item))
            except PoolValidationError as exc:
                logger.debug("Dropped a grammar task: %s", exc)
        if not assets:
            raise AssetLLMError("no grammar task survived validation")
        return assets

    def _atomic_question(self, request: AssetRequest, asset: GrammarAsset):
        """The reusable one-mark unit, banked so the next paper can draw on it."""
        return build_pool_question(
            question=asset.question,
            answer=asset.answer,
            marks=1,
            subject=request.subject,
            chapter=self.chapter_label,
            topic=asset.grammar_topic,
            question_type="GRAMMAR",
            generator=self.name,
            asset_type=self.atomic_asset_type,
            source_type=self.source_type,
            pool_id=request.pool_id,
            options=asset.options,
            explanation=asset.explanation,
            blooms="APPLY",
            difficulty=asset.difficulty,
            asset=asset,
            extra_metadata={"grammarTopic": asset.grammar_topic},
        )

    def _set_question(self, request: AssetRequest, slot: Any, task_set: GrammarTaskSet):
        return build_pool_question(
            question=task_set.render_question(),
            answer=task_set.render_answer(),
            marks=int(getattr(slot, "marks", task_set.total_marks) or task_set.total_marks),
            subject=request.subject,
            chapter=self.chapter_label,
            topic="Grammar task set",
            question_type="GRAMMAR",
            generator=self.name,
            asset_type=str(getattr(slot, "asset_type", "") or "grammar_task_set"),
            source_type=self.source_type,
            pool_id=request.pool_id,
            explanation=(
                "Rule-based grammar tasks, each self-contained and independent "
                "of any prescribed text."
            ),
            blooms="APPLY",
            difficulty=task_set.difficulty,
            asset=task_set,
            extra_metadata={
                "taskCount": len(task_set.tasks),
                "attemptCount": task_set.attempt,
                "grammarTopics": [t.grammar_topic for t in task_set.tasks],
            },
        )


register(GrammarAssetGenerator())
