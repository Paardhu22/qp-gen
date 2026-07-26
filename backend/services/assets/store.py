"""Reading assets back out of the bank.

Assets are persisted by the same auto-save that banks the textbook pool, so
nothing new writes here. What this module adds is the *read* side: pulling
previously generated assets back as candidates, which is what "reusable
wherever appropriate" means in practice.

Reuse is scoped to the user, the subject and the class — never to a chapter.
Chapter is a textbook concept; an unseen passage or a grammar task has no
chapter, and filtering assets by one is exactly the bug that would make them
invisible to "Create Paper from Saved Questions".
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from django.conf import settings

from services.assets.registry import registered_generators
from services.pool.schema import PoolQuestion

logger = logging.getLogger("[ASSETS]")

#: Default ceiling on reused candidates per generation. Big enough that a
#: grammar pool built over a few papers has real variety, small enough that the
#: query and the in-memory selection stay trivial.
DEFAULT_LIMIT = 400


def asset_source_types() -> List[str]:
    return sorted({g.source_type for g in registered_generators()})


def reuse_enabled() -> bool:
    return bool(getattr(settings, "ASSET_REUSE_ENABLED", True))


def load_reusable_assets(
    *,
    user,
    subject: str = "",
    class_num: Optional[int] = None,
    generators: Optional[Iterable[str]] = None,
    limit: int = DEFAULT_LIMIT,
) -> List[PoolQuestion]:
    """Assets this user's earlier generations produced, as pool questions.

    Returns [] rather than raising on any database problem: reuse is an
    optimisation, and losing it must never cost a generation.
    """
    if not user or not reuse_enabled():
        return []

    wanted = {str(g) for g in (generators or []) if str(g)}
    source_types = asset_source_types()
    if not source_types:
        return []

    try:
        from apps.projects.models import Question

        query = Question.objects.filter(user=user, source_type__in=source_types)
        if subject:
            query = query.filter(subject__iexact=str(subject).strip())
        if class_num:
            query = query.filter(grade_class__icontains=str(class_num))
        rows = query.order_by("-created_at")[:limit]
        questions = [PoolQuestion.from_model(row) for row in rows]
    except Exception as exc:
        logger.warning("Could not load reusable assets: %s", exc)
        return []

    if wanted:
        questions = [q for q in questions if q.generator in wanted]

    logger.info(
        "Loaded %d reusable asset(s) for subject=%r class=%s.",
        len(questions), subject, class_num,
    )
    return questions
