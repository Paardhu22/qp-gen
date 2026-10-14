"""Blueprint-driven validation rules.

A slot declares `validation=("sub_question_count", "passage_word_count", …)`
and `constraints={...}`; the rules read the constraints and check the asset
against them. Nothing here knows what CBSE is — the numbers all come from the
blueprint, so a different board's blueprint gets a different check for free.

Rules are advisory by design. A generator retries once when a rule fails and
then ships the best asset it has, recording the failure as a warning. A
structurally imperfect Reading passage is a far better outcome than an empty
Reading section, and the warnings surface on the SSE stream so the teacher can
see what to look at.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("[ASSETS]")

#: Phrases that mean "this question depends on material the student was given
#: elsewhere". An asset generator has no uploaded content, so any of these is a
#: hallucinated dependency and makes the item unanswerable in isolation.
_EXTERNAL_REFERENCE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\byour (?:text ?book|prescribed text|reader|course book)\b",
        r"\bthe (?:text ?book|prescribed text) (?:chapter|lesson|story|poem)\b",
        r"\bas (?:studied|discussed|read) in (?:class|the chapter|the lesson)\b",
        r"\bfrom the chapter\b",
        r"\bin the lesson\b",
        r"\brefer to the (?:chapter|lesson|textbook)\b",
    )
]

RuleResult = Optional[str]
Rule = Callable[[Any, Any, Dict[str, Any]], RuleResult]

_RULES: Dict[str, Rule] = {}


def rule(name: str) -> Callable[[Rule], Rule]:
    def _register(fn: Rule) -> Rule:
        _RULES[name] = fn
        return fn

    return _register


def _range(value: Any) -> Optional[Tuple[int, int]]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
    try:
        single = int(value)
    except (TypeError, ValueError):
        return None
    return single, single


# ── Composite-question shape ────────────────────────────────────────────


@rule("sub_question_marks_sum")
def _sub_question_marks_sum(asset, slot, constraints) -> RuleResult:
    questions = getattr(asset, "questions", None)
    if not questions:
        return None
    total = sum(int(q.marks) for q in questions)
    expected = int(getattr(slot, "marks", 0) or 0)
    if expected and total != expected:
        return f"sub-question marks total {total}, slot is worth {expected}"
    return None


@rule("sub_question_count")
def _sub_question_count(asset, slot, constraints) -> RuleResult:
    questions = getattr(asset, "questions", None)
    if questions is None:
        return None
    bounds = _range(constraints.get("sub_questions"))
    if not bounds:
        return None
    low, high = bounds
    if not (low <= len(questions) <= high):
        return f"expected {low}–{high} sub-questions, got {len(questions)}"
    return None


@rule("paragraph_reference_bounds")
def _paragraph_reference_bounds(asset, slot, constraints) -> RuleResult:
    paragraphs = getattr(asset, "paragraphs", None)
    questions = getattr(asset, "questions", None)
    if not paragraphs or not questions:
        return None
    count = len(paragraphs)
    stray = sorted(
        {
            q.paragraph
            for q in questions
            if q.paragraph is not None and not (1 <= int(q.paragraph) <= count)
        }
    )
    if stray:
        return f"sub-questions reference paragraphs {stray} but the passage has {count}"
    return None


@rule("option_completeness")
def _option_completeness(asset, slot, constraints) -> RuleResult:
    questions = getattr(asset, "questions", None) or []
    thin = [
        i + 1 for i, q in enumerate(questions) if q.options and len(q.options) < 2
    ]
    if thin:
        return f"sub-questions {thin} offer fewer than two options"
    return None


@rule("answer_key_complete")
def _answer_key_complete(asset, slot, constraints) -> RuleResult:
    questions = getattr(asset, "questions", None) or []
    missing = [i + 1 for i, q in enumerate(questions) if not str(q.answer or "").strip()]
    if missing:
        return f"sub-questions {missing} have no answer key"
    return None


# ── Reading ─────────────────────────────────────────────────────────────


@rule("passage_word_count")
def _passage_word_count(asset, slot, constraints) -> RuleResult:
    words = getattr(asset, "word_count", None)
    if words is None:
        return None
    bounds = _range(constraints.get("word_count"))
    if not bounds:
        return None
    low, high = bounds
    # ±20% — a passage 30 words over target is fine; one at half length is not.
    if not (low * 0.8 <= words <= high * 1.2):
        return f"passage is {words} words, blueprint asks for {low}–{high}"
    return None


@rule("paragraph_map_present")
def _paragraph_map_present(asset, slot, constraints) -> RuleResult:
    paragraphs = getattr(asset, "paragraphs", None)
    mapping = getattr(asset, "paragraph_map", None)
    if paragraphs is None or mapping is None:
        return None
    if len(mapping) != len(paragraphs):
        return (
            f"paragraph map has {len(mapping)} entries for {len(paragraphs)} paragraphs"
        )
    return None


# ── Grammar ─────────────────────────────────────────────────────────────


@rule("task_count")
def _task_count(asset, slot, constraints) -> RuleResult:
    tasks = getattr(asset, "tasks", None)
    if tasks is None:
        return None
    bounds = _range(constraints.get("tasks"))
    if not bounds:
        return None
    low, high = bounds
    if not (low <= len(tasks) <= high):
        return f"expected {low}–{high} tasks, got {len(tasks)}"
    return None


@rule("distinct_grammar_topics")
def _distinct_grammar_topics(asset, slot, constraints) -> RuleResult:
    tasks = getattr(asset, "tasks", None)
    if not tasks:
        return None
    seen: Dict[str, int] = {}
    for task in tasks:
        key = str(task.grammar_topic or "").strip().lower()
        seen[key] = seen.get(key, 0) + 1
    allowed = int(constraints.get("max_per_grammar_topic") or 1)
    repeated = sorted(topic for topic, n in seen.items() if n > allowed)
    if repeated:
        return f"grammar topics repeat more than {allowed}×: {repeated}"
    return None


# ── Writing ─────────────────────────────────────────────────────────────


@rule("word_limit_declared")
def _word_limit_declared(asset, slot, constraints) -> RuleResult:
    """A word limit must be printed, and must be the one the blueprint asked for.

    Checking only that *some* limit appears would never fire: the renderer
    appends a default when the scenario omits one. What can genuinely go wrong
    is the model quietly writing a 50-word task where the blueprint wants 120.
    """
    if not hasattr(asset, "word_limit"):
        return None
    stated = re.findall(r"\b(\d{2,4})\s*words\b", asset.render_question(), re.IGNORECASE)
    if not stated:
        return "the prompt does not state a word limit"

    expected = _range(constraints.get("word_limit"))
    if not expected:
        return None
    low, high = expected
    if not any(low * 0.75 <= int(value) <= high * 1.25 for value in stated):
        return f"prompt states {stated} words, blueprint asks for {low}–{high}"
    return None


@rule("stimulus_present")
def _stimulus_present(asset, slot, constraints) -> RuleResult:
    if not constraints.get("stimulus_required"):
        return None
    blocks = getattr(asset, "stimulus", None)
    wanted = int(constraints.get("stimulus_blocks") or 2)
    if not blocks or len(blocks) < wanted:
        return f"expected at least {wanted} stimulus blocks, got {len(blocks or [])}"
    return None


@rule("rubric_present")
def _rubric_present(asset, slot, constraints) -> RuleResult:
    if not hasattr(asset, "rubric"):
        return None
    if not asset.rubric:
        return "the writing task has no marking rubric"
    return None


# ── Architectural guard ─────────────────────────────────────────────────


@rule("self_contained")
def _self_contained(asset, slot, constraints) -> RuleResult:
    """No dependence on material the student was handed elsewhere.

    The generators are never given uploaded content, so this cannot catch a
    genuine leak — it catches the model *pretending* there is one ("as studied
    in the chapter"), which makes an otherwise fine item unanswerable.
    """
    rendered = asset.render_question() if hasattr(asset, "render_question") else ""
    for pattern in _EXTERNAL_REFERENCE_PATTERNS:
        match = pattern.search(rendered)
        if match:
            return f"refers to external material: {match.group(0)!r}"
    return None


# ── Entry point ─────────────────────────────────────────────────────────


def validate_asset(asset: Any, slot: Any) -> List[str]:
    """Run the rules the slot declares. Returns human-readable failures."""
    names: Sequence[str] = tuple(getattr(slot, "validation", ()) or ())
    constraints: Dict[str, Any] = dict(getattr(slot, "constraints", {}) or {})

    failures: List[str] = []
    for name in names:
        check = _RULES.get(str(name))
        if check is None:
            logger.debug("Unknown validation rule %r on slot %s", name, getattr(slot, "index", "?"))
            continue
        try:
            problem = check(asset, slot, constraints)
        except Exception as exc:  # pragma: no cover - a rule must never break a paper
            logger.warning("Validation rule %r crashed: %s", name, exc)
            continue
        if problem:
            failures.append(f"{name}: {problem}")
    return failures


def available_rules() -> List[str]:
    return sorted(_RULES)
