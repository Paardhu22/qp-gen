"""Model 1 — chapter Markdown in, Question Pool out.

This replaces the per-slot fan-out the generator used to run. The old path
issued one retrieval + one LLM call for every question in the blueprint (38
calls for a Class 10 board paper) and each call saw only the four chunks its
own retrieval surfaced. Model 1 instead reads the entire chapter once per
batch and writes questions with knowledge of the whole thing, which is both
~10× cheaper and produces a pool that covers the chapter evenly instead of
clustering wherever retrieval happened to point.

Batching exists for one reason: output length. ~84 questions is 15-20k
completion tokens, past the point where a single response stays reliable, so
the recipe splits the pool by question shape into four calls that run in
parallel.

Cost note: every batch carries the full chapter, so the chapter is sent 4×.
The prompt is ordered chapter-first precisely so OpenAI's automatic prefix
caching recognises the shared prefix and discounts batches 2-4.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from django.conf import settings

from apps.question_generation.infrastructure.providers.base import (
    LLMMessage,
    LLMRequest,
)
from apps.question_generation.infrastructure.providers.openai_provider import (
    OpenAIProvider,
)
from services.chapter_markdown import ChapterMarkdown
from services.content_filters import clean_question_text
from services.pool.recipes import Batch, batches_for_subject
from services.pool.schema import (
    PoolQuestion,
    PoolValidationError,
    compute_content_hash,
    normalize_pool_question,
)
from services.pool.streaming import JsonObjectStreamExtractor, parse_question_payload
from utils.ids import generate_id

logger = logging.getLogger("[MODEL1]")

#: Attempts per batch. A batch that fails entirely costs its whole quota, so
#: it is worth retrying — but the other batches still deliver, so this never
#: blocks the pool from being produced.
_MAX_BATCH_ATTEMPTS = 3

#: Batches run concurrently. 4 matches the recipe width; raising it would not
#: help since there are only four batches.
_BATCH_CONCURRENCY = 4


@dataclass
class PoolGenerationResult:
    pool_id: str
    questions: List[PoolQuestion] = field(default_factory=list)
    subject: str = ""
    chapter: str = ""
    batch_failures: List[str] = field(default_factory=list)
    duplicates_dropped: int = 0
    invalid_dropped: int = 0

    @property
    def total(self) -> int:
        return len(self.questions)


def _system_prompt(subject: str, class_num: int, difficulty: str) -> str:
    return (
        "You are a senior CBSE examiner writing questions for a Class "
        f"{class_num} {subject} question paper.\n\n"
        "You are given a COMPLETE chapter. Read all of it, then write questions "
        "that cover the chapter EVENLY — do not draw everything from the first "
        "few sections.\n\n"
        "Hard rules:\n"
        "1. Every question must be answerable from the chapter provided. Do not "
        "introduce facts, values, or examples that are not in the text.\n"
        "2. Questions must be self-contained. A student answers from the "
        "question alone, so never write 'according to the passage above', "
        "'as shown in the figure', or 'from the given text'.\n"
        "3. No two questions may test the same fact. Vary the concept, the "
        "section of the chapter, and the phrasing.\n"
        "4. MCQs have exactly 4 options. Distractors must be plausible and "
        "wrong for a reason — never 'none of the above' or an obvious filler.\n"
        "5. Assertion-Reason questions state only the Assertion (A) and the "
        "Reason (R). Do NOT restate the four standard directions; they are "
        "added automatically.\n"
        "6. Case-study questions carry a short stimulus followed by sub-parts "
        "numbered (i), (ii), (iii) inside the question text.\n"
        f"7. Calibrate overall difficulty to '{difficulty}', but still include a "
        "spread — a paper of uniformly identical difficulty is not usable.\n"
        "8. `answer` is what a marking scheme accepts. `explanation` is why it "
        "is correct. Both are required for every question.\n"
        "9. Write in the language of the chapter.\n\n"
        "Return ONLY a JSON array. No prose, no markdown fence, no wrapper "
        "object. Each element:\n"
        "{\n"
        '  "topic": "<specific concept within the chapter>",\n'
        '  "type": "<one of the requested types, verbatim>",\n'
        '  "blooms": "REMEMBER|UNDERSTAND|APPLY|ANALYZE|EVALUATE|CREATE",\n'
        '  "difficulty": "easy|medium|hard",\n'
        '  "marks": <integer>,\n'
        '  "question": "<the question text>",\n'
        '  "options": ["<A>", "<B>", "<C>", "<D>"],\n'
        '  "answer": "<the expected answer>",\n'
        '  "explanation": "<why this is the answer>"\n'
        "}\n"
        "Omit `options` (or send []) for any type that is not multiple-choice."
    )


def _batch_instruction(batch: Batch) -> str:
    lines = [
        f"Write exactly {batch.total} questions with this breakdown:",
        "",
    ]
    for quota in batch.quotas:
        lines.append(
            f"  • {quota.count} × {quota.type} worth {quota.marks} mark"
            f"{'s' if quota.marks != 1 else ''} each"
        )
    lines.extend(
        [
            "",
            "Set each question's `type` and `marks` to exactly the values above. "
            "Return them as one flat JSON array in the order listed.",
        ]
    )
    return "\n".join(lines)


def _build_request(
    *,
    chapter: ChapterMarkdown,
    batch: Batch,
    subject: str,
    class_num: int,
    difficulty: str,
    model: str,
    user=None,
) -> LLMRequest:
    """Chapter first, batch instruction last.

    Ordering is load-bearing. All four batches share the system prompt + the
    chapter, which is the overwhelming majority of the input tokens; putting
    the only varying part at the very end lets OpenAI's automatic prefix cache
    hit on batches 2-4.
    """
    messages = [
        LLMMessage(role="system", content=_system_prompt(subject, class_num, difficulty)),
        LLMMessage(
            role="user",
            content=f"# CHAPTER SOURCE MATERIAL\n\n{chapter.markdown}",
        ),
        LLMMessage(role="user", content=_batch_instruction(batch)),
    ]
    return LLMRequest(
        model=model,
        messages=messages,
        stream=True,
        max_output_tokens=batch.max_output_tokens,
        user=user,
        operation=f"pool_model1_{batch.name}",
    )


def _normalise_batch(
    raw_questions: Sequence[Dict[str, Any]],
    *,
    batch: Batch,
    subject: str,
    chapter_name: str,
    pool_id: str,
    difficulty: str,
) -> tuple[List[PoolQuestion], int]:
    """Coerce a batch's raw objects, dropping the unsalvageable ones."""
    accepted: List[PoolQuestion] = []
    invalid = 0

    # Marks the model may legitimately have used, so a question whose `marks`
    # drifted can be snapped back rather than dropped.
    allowed_marks = {q.marks for q in batch.quotas}

    for raw in raw_questions:
        try:
            question = normalize_pool_question(
                raw,
                subject=subject,
                chapter=chapter_name,
                pool_id=pool_id,
                default_difficulty=difficulty,
            )
        except PoolValidationError as exc:
            invalid += 1
            logger.debug("Dropped a question from batch %s: %s", batch.name, exc)
            continue

        if question.marks not in allowed_marks and len(allowed_marks) == 1:
            # Single-shape batch — an off-by-one marks value is a formatting
            # slip, not a different question. Snap it.
            question.marks = next(iter(allowed_marks))

        # Route the stem through the same scrubber the legacy path used, so
        # figure-label residue and blueprint leakage never reach the bank.
        cleaned = clean_question_text(question.question)
        if not cleaned.strip():
            invalid += 1
            continue
        if cleaned != question.question:
            question.question = cleaned
            question.content_hash = compute_content_hash(
                subject, chapter_name, cleaned
            )

        accepted.append(question)

    return accepted, invalid


def _run_batch(
    *,
    chapter: ChapterMarkdown,
    batch: Batch,
    subject: str,
    chapter_name: str,
    class_num: int,
    difficulty: str,
    pool_id: str,
    model: str,
    provider: OpenAIProvider,
    user=None,
    on_question: Optional[Callable[[PoolQuestion], None]] = None,
) -> tuple[List[PoolQuestion], int, Optional[str]]:
    """Execute one batch. Returns (questions, invalid_count, failure_reason)."""
    request = _build_request(
        chapter=chapter,
        batch=batch,
        subject=subject,
        class_num=class_num,
        difficulty=difficulty,
        model=model,
        user=user,
    )

    last_error: Optional[str] = None

    for attempt in range(1, _MAX_BATCH_ATTEMPTS + 1):
        extractor = JsonObjectStreamExtractor()
        raw_objects: List[Dict[str, Any]] = []
        buffer_parts: List[str] = []

        try:
            for delta in provider.stream_chat(request):
                if not delta:
                    continue
                buffer_parts.append(delta)
                raw_objects.extend(extractor.feed(delta))
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Batch %s attempt %s/%s failed: %s",
                batch.name, attempt, _MAX_BATCH_ATTEMPTS, last_error,
            )
            if attempt < _MAX_BATCH_ATTEMPTS:
                time.sleep(min(2 ** (attempt - 1), 8))
                continue
            return [], 0, last_error

        if not raw_objects:
            # Provider may have buffered rather than streamed.
            raw_objects = parse_question_payload("".join(buffer_parts))

        if not raw_objects:
            last_error = "no questions returned"
            logger.warning(
                "Batch %s attempt %s/%s returned nothing parseable.",
                batch.name, attempt, _MAX_BATCH_ATTEMPTS,
            )
            if attempt < _MAX_BATCH_ATTEMPTS:
                continue
            return [], 0, last_error

        questions, invalid = _normalise_batch(
            raw_objects,
            batch=batch,
            subject=subject,
            chapter_name=chapter_name,
            pool_id=pool_id,
            difficulty=difficulty,
        )

        if not questions:
            last_error = f"all {len(raw_objects)} questions failed validation"
            if attempt < _MAX_BATCH_ATTEMPTS:
                logger.warning("Batch %s: %s. Retrying.", batch.name, last_error)
                continue
            return [], invalid, last_error

        if on_question:
            for question in questions:
                on_question(question)

        logger.info(
            "Batch %s produced %d/%d questions (%d dropped).",
            batch.name, len(questions), batch.total, invalid,
        )
        return questions, invalid, None

    return [], 0, last_error


def generate_question_pool(
    *,
    chapter: ChapterMarkdown,
    subject: str,
    subject_norm: str,
    chapter_name: str,
    class_num: int,
    difficulty: str = "medium",
    target_total: int = 0,
    model: Optional[str] = None,
    user=None,
    on_question: Optional[Callable[[PoolQuestion], None]] = None,
) -> PoolGenerationResult:
    """Read a chapter, return a deduplicated Question Pool.

    `on_question` is invoked as each question is normalised, from the batch's
    worker thread — callers pushing to an SSE stream must make it thread-safe.
    """
    pool_id = generate_id()
    result = PoolGenerationResult(
        pool_id=pool_id, subject=subject, chapter=chapter_name
    )

    if chapter.is_empty:
        result.batch_failures.append("chapter source material is empty")
        return result

    resolved_model = model or getattr(settings, "POOL_MODEL", settings.OPENAI_MODEL)
    batches = batches_for_subject(subject_norm, target_total=target_total)
    provider = OpenAIProvider()

    logger.info(
        "Model 1 starting: pool=%s subject=%s chapter=%r class=%s "
        "chapter_chars=%d (~%d tok) batches=%s target=%d",
        pool_id, subject, chapter_name, class_num,
        chapter.char_count, chapter.estimated_tokens,
        [b.name for b in batches], sum(b.total for b in batches),
    )

    # Dedup as questions arrive rather than at the end: two batches can
    # independently phrase the same fact, and the earlier one wins.
    seen_hashes: set[str] = set()
    lock = threading.Lock()

    def _accept(question: PoolQuestion) -> bool:
        with lock:
            if question.content_hash in seen_hashes:
                return False
            seen_hashes.add(question.content_hash)
            return True

    def _worker(batch: Batch):
        return batch, _run_batch(
            chapter=chapter,
            batch=batch,
            subject=subject,
            chapter_name=chapter_name,
            class_num=class_num,
            difficulty=difficulty,
            pool_id=pool_id,
            model=resolved_model,
            provider=provider,
            user=user,
            on_question=None,  # emitted below, after the dedup gate
        )

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=_BATCH_CONCURRENCY) as executor:
        futures = [executor.submit(_worker, batch) for batch in batches]
        for future in as_completed(futures):
            try:
                batch, (questions, invalid, failure) = future.result()
            except Exception as exc:
                logger.error("Batch worker crashed: %s", exc, exc_info=True)
                result.batch_failures.append(str(exc))
                continue

            result.invalid_dropped += invalid
            if failure:
                result.batch_failures.append(f"{batch.name}: {failure}")
                continue

            for question in questions:
                if not _accept(question):
                    result.duplicates_dropped += 1
                    continue
                result.questions.append(question)
                if on_question:
                    on_question(question)

    elapsed = time.monotonic() - started
    logger.info(
        "Model 1 finished: pool=%s produced=%d duplicates=%d invalid=%d "
        "failures=%s in %.1fs",
        pool_id, result.total, result.duplicates_dropped,
        result.invalid_dropped, result.batch_failures, elapsed,
    )

    return result
