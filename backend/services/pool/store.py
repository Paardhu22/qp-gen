"""Persistence for the Question Pool.

Every question Model 1 produces is saved automatically — there is no Save
button any more. That makes dedup essential rather than nice-to-have: without
it, regenerating a chapter three times leaves a bank with three copies of
every question, and "Create Paper from Saved Questions" becomes unusable.

Dedup is by `content_hash` (subject + chapter + normalised question text),
scoped per user, and enforced here rather than by a UNIQUE index. The live
`Question` table predates the pool and may already contain duplicates from the
manual-save flow, so a unique index could not be built over it without a data
cleanup first.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from django.core.cache import cache
from django.db import transaction

from apps.projects.models import Project, Question
from apps.projects.question_types import valid_type_codes
from services.pool.schema import PoolQuestion

logger = logging.getLogger("[POOL_STORE]")


@dataclass
class PersistResult:
    project_id: str = ""
    project_name: str = ""
    saved: int = 0
    duplicates_skipped: int = 0
    failed: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def project_name_for(class_num: int, subject: str, chapter: str) -> str:
    """Bank grouping key.

    Matches the convention the previous manual-save path inferred
    ("<class> — <subject> — <topic>"), so questions saved before and after the
    pool refactor land in the same project rather than splitting a chapter's
    history across two entries.
    """
    parts = [
        f"Class {class_num}" if class_num else "",
        (subject or "").strip(),
        (chapter or "").strip(),
    ]
    return " — ".join(p for p in parts if p) or "Generated Questions"


def _bust_bank_caches(user_id: str) -> None:
    cache.delete(f"user_projects_full:{user_id}")
    cache.delete(f"user_projects_summary:{user_id}")


def persist_pool(
    *,
    user,
    questions: Sequence[PoolQuestion],
    subject: str,
    chapter: str,
    class_num: int,
    paper=None,
) -> PersistResult:
    """Save a pool to the user's bank, skipping anything already there.

    Never raises. Auto-save runs at the tail of a generation the teacher has
    already watched succeed; a persistence failure must surface as a warning,
    not as a failed generation that discards 80 good questions.
    """
    result = PersistResult()
    if not questions:
        return result

    name = project_name_for(class_num, subject, chapter)
    result.project_name = name

    try:
        with transaction.atomic():
            project, _ = Project.objects.get_or_create(name=name, user=user)
            result.project_id = project.id

            incoming = {q.content_hash: q for q in questions if q.content_hash}
            # Questions without a hash (shouldn't happen, but the contract
            # allows an empty string) are saved unconditionally.
            unhashed = [q for q in questions if not q.content_hash]

            existing_hashes = set(
                Question.objects.filter(
                    user=user, content_hash__in=list(incoming.keys())
                ).values_list("content_hash", flat=True)
            )

            to_save = [
                question
                for content_hash, question in incoming.items()
                if content_hash not in existing_hashes
            ] + unhashed

            result.duplicates_skipped = len(questions) - len(to_save)

            if to_save:
                grade_class = str(class_num) if class_num else None
                # Fetch the canonical type-code set once; every row resolves its
                # pool type against it rather than re-querying per question.
                type_codes = valid_type_codes()
                Question.objects.bulk_create(
                    [
                        Question(
                            **question.to_model_kwargs(
                                user=user,
                                project=project,
                                paper=paper,
                                grade_class=grade_class,
                                valid_type_codes=type_codes,
                            )
                        )
                        for question in to_save
                    ]
                )
                result.saved = len(to_save)

        _bust_bank_caches(user.id)

    except Exception as exc:
        logger.error(
            "Auto-save failed for user=%s chapter=%r: %s",
            getattr(user, "id", "?"), chapter, exc, exc_info=True,
        )
        result.error = str(exc)
        result.failed = len(questions)
        return result

    logger.info(
        "Auto-saved %d question(s) to %r (%d duplicates skipped).",
        result.saved, name, result.duplicates_skipped,
    )
    return result


def load_bank(
    *,
    user,
    subject: Optional[str] = None,
    chapters: Optional[Iterable[str]] = None,
    class_num: Optional[int] = None,
    project_ids: Optional[Iterable[str]] = None,
    limit: int = 2000,
) -> List[PoolQuestion]:
    """Read a user's saved questions back as a pool.

    This is the input to "Create Paper from Saved Questions" — the path that
    skips Model 1 entirely, and the whole reason the pool is persisted per-row
    instead of as a blob.
    """
    query = Question.objects.filter(user=user)

    if subject:
        query = query.filter(subject__iexact=subject.strip())
    if class_num:
        # grade_class is free text ("10", "Class 10", "X"), so match loosely.
        query = query.filter(grade_class__icontains=str(class_num))
    chapter_list = [str(c).strip() for c in (chapters or []) if str(c).strip()]
    if chapter_list:
        from django.db.models import Q as DjangoQ

        clause = DjangoQ()
        for chapter in chapter_list:
            clause |= DjangoQ(inferred_chapter__iexact=chapter)
        query = query.filter(clause)
    if project_ids:
        query = query.filter(project_id__in=list(project_ids))

    rows = query.order_by("-created_at")[:limit]
    return [PoolQuestion.from_model(row) for row in rows]


def bank_summary(*, user) -> List[Dict[str, Any]]:
    """Per-chapter counts for the bank picker UI."""
    from django.db.models import Count

    rows = (
        Question.objects.filter(user=user)
        .values("project_id", "project__name", "subject", "grade_class", "inferred_chapter")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    return [
        {
            "projectId": row["project_id"],
            "projectName": row["project__name"],
            "subject": row["subject"],
            "gradeClass": row["grade_class"],
            "chapter": row["inferred_chapter"],
            "count": row["count"],
        }
        for row in rows
    ]
