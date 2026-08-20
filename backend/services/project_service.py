from datetime import timedelta
from typing import List, Optional

from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from apps.projects.models import Paper, PaperSet, Project, Question
from apps.projects.question_types import resolve_type_code


def list_projects_for_user(user) -> List[Project]:
    return Project.objects.filter(user=user).prefetch_related("questions").order_by("-created_at")


#: The only PaperSet columns the papers list actually renders. Named here
#: because the reason for the list is easy to lose: `content` and `answers` are
#: whole TipTap documents, tens to hundreds of kilobytes each, and a paper has
#: up to three sets. Prefetching sets without restricting the columns pulled
#: every one of those documents out of the database and threw them away in the
#: serializer — a library of 200 papers was moving tens of megabytes to render
#: a table of titles and dates.
_SET_LIST_FIELDS = ("id", "paper_id", "label", "order", "metadata")

#: Likewise on Paper. `blueprint` is a JSON slot plan and `instructions` is
#: prose; neither appears on a list row.
_PAPER_LIST_DEFER = ("instructions", "blueprint")


def _paper_list_queryset(user, *, deleted: bool):
    """Papers for a list view: no document bodies, one query for the sets."""
    queryset = Paper.objects.filter(user=user)
    queryset = (
        queryset.exclude(deleted_at__isnull=True)
        if deleted
        else queryset.filter(deleted_at__isnull=True)
    )
    return (
        queryset.select_related("project")
        .defer(*_PAPER_LIST_DEFER)
        .prefetch_related(
            # prefetch_related alone fixes the N+1; `.only()` inside it is what
            # keeps each of those rows small. Both matter, for different reasons.
            Prefetch("sets", queryset=PaperSet.objects.only(*_SET_LIST_FIELDS))
        )
        .order_by("-deleted_at" if deleted else "-updated_at")
    )


def list_papers_for_user(user) -> List[Paper]:
    return _paper_list_queryset(user, deleted=False)


def list_deleted_papers_for_user(user) -> List[Paper]:
    """The recycle bin: papers deleted but still inside the retention window."""
    return _paper_list_queryset(user, deleted=True).filter(
        deleted_at__gte=timezone.now() - timedelta(days=trash_retention_days())
    )


def get_paper_for_user(user, paper_id: str) -> Paper:
    """One paper, in full. Never a deleted one.

    A paper in the bin must be unreachable everywhere the product treats a
    paper as live — opening it in the editor would let a teacher keep working
    on something scheduled for permanent deletion. Restoring is the only way
    back, and it goes through `restore_paper`.
    """
    return Paper.objects.select_related("project").get(
        id=paper_id, user=user, deleted_at__isnull=True
    )


def trash_retention_days() -> int:
    return int(getattr(settings, "PAPER_TRASH_RETENTION_DAYS", 30))


def soft_delete_paper(user, paper_id: str) -> Paper:
    """Move a paper to the bin. Raises `Paper.DoesNotExist` if it is not live."""
    paper = Paper.objects.get(id=paper_id, user=user, deleted_at__isnull=True)
    paper.deleted_at = timezone.now()
    paper.save(update_fields=["deleted_at", "updated_at"])
    return paper


def soft_delete_all_papers(user) -> int:
    """Bin every live paper. Returns how many moved."""
    return Paper.objects.filter(user=user, deleted_at__isnull=True).update(
        deleted_at=timezone.now()
    )


def restore_paper(user, paper_id: str) -> Paper:
    """Take a paper back out of the bin.

    Only from inside the retention window: a row past it is already eligible
    for permanent deletion, and restoring one would produce a paper that the
    purge removes again without warning.
    """
    cutoff = timezone.now() - timedelta(days=trash_retention_days())
    paper = Paper.objects.get(
        id=paper_id, user=user, deleted_at__isnull=False, deleted_at__gte=cutoff
    )
    paper.deleted_at = None
    paper.save(update_fields=["deleted_at", "updated_at"])
    return paper


def purge_paper(user, paper_id: str) -> None:
    """Delete a binned paper for real, at the teacher's explicit request."""
    paper = Paper.objects.get(id=paper_id, user=user, deleted_at__isnull=False)
    paper.delete()


def purge_expired_papers(*, now=None) -> int:
    """Permanently remove papers past the retention window. Returns the count.

    Called both from the management command and lazily whenever a bin is
    listed, so the promise the UI makes ("deleted after 30 days") holds on a
    deployment with no scheduler as well as on one with cron.
    """
    cutoff = (now or timezone.now()) - timedelta(days=trash_retention_days())
    expired = Paper.objects.filter(deleted_at__isnull=False, deleted_at__lt=cutoff)
    count = expired.count()
    if count:
        expired.delete()
    return count


def save_questions_to_project(user, project_name: str, questions: List[dict]) -> Project:
    with transaction.atomic():
        # If project_name is provided, use it for all questions (Legacy single-topic flow)
        if project_name:
            project, _ = Project.objects.get_or_create(name=project_name, user=user)
            projects_cache = {project_name: project}
        else:
            projects_cache = {}

        question_objects = []
        for question in questions:
            # If no project_name provided, infer it from the question metadata
            q_project_name = project_name
            if not q_project_name:
                q_class = question.get("grade_class", "Unknown Class")
                q_subject = question.get("subject", "Unknown Subject")
                q_topic = question.get("inferred_topic", "Unknown Topic")
                q_project_name = f"{q_class} — {q_subject} — {q_topic}"

            if q_project_name not in projects_cache:
                p, _ = Project.objects.get_or_create(name=q_project_name, user=user)
                projects_cache[q_project_name] = p

            question_objects.append(
                Question(
                    content=question.get("content", ""),
                    answer=question.get("answer"),
                    # `type` is a FK to QuestionType; the serializer has already
                    # resolved it to a canonical code string, so assign via the
                    # `_id` attribute rather than the relation.
                    type_id=question.get("type"),
                    marks=int(question.get("marks") or 1),
                    options=question.get("options") or [],
                    project=projects_cache[q_project_name],
                    grade_class=question.get("grade_class"),
                    subject=question.get("subject"),
                    inferred_topic=question.get("inferred_topic"),
                    inferred_chapter=question.get("inferred_chapter"),
                    source_pdf=question.get("source_pdf"),
                    difficulty=question.get("difficulty"),
                    # Both columns exist and the pool's own auto-save writes
                    # them; this path did not, so a diagram question saved by
                    # hand lost its figure permanently — the row went in with
                    # image_url NULL and the picture was never recoverable from
                    # it. `bloom_taxonomy` was dropped the same way.
                    image_url=question.get("image_url"),
                    explanation=question.get("explanation"),
                    bloom_taxonomy=question.get("bloom_taxonomy"),
                )
            )
        Question.objects.bulk_create(question_objects)

    # Return the first created/fetched project as a fallback for the response
    return list(projects_cache.values())[0] if projects_cache else None


def save_paper_to_project(
    user,
    project_name: str,
    title: str,
    subject: str = "",
    grade_class: str = "",
    board: str = "",
    instructions: str = "",
    blueprint: Optional[dict] = None,
    question_pool_id: str = "",
    sets: Optional[List[dict]] = None,
    questions: Optional[List[dict]] = None,
    paper_id: Optional[str] = None,
    hsat_source_ids: Optional[List[str]] = None,
) -> Paper:
    """Create or update a Paper and persist its Sets and questions."""
    from apps.projects.models import PaperSet
    
    if questions is None:
        questions = []
    if sets is None:
        sets = []

    with transaction.atomic():
        project, _ = Project.objects.get_or_create(name=project_name, user=user)

        if paper_id:
            # Update existing paper. `deleted_at__isnull=True` so a paper in the
            # recycle bin cannot be written back to life by a stale editor tab
            # autosaving over it — restoring is an explicit action.
            paper = Paper.objects.get(id=paper_id, user=user, deleted_at__isnull=True)
            paper.title = title
            paper.subject = subject
            paper.grade_class = grade_class
            paper.board = board
            paper.instructions = instructions
            paper.blueprint = blueprint
            paper.question_pool_id = question_pool_id
            paper.project = project
            paper.save()

            # Replace questions
            paper.questions.all().delete()
        else:
            paper = Paper.objects.create(
                title=title,
                subject=subject,
                grade_class=grade_class,
                board=board,
                instructions=instructions,
                blueprint=blueprint,
                question_pool_id=question_pool_id,
                project=project,
                user=user,
            )

        # ── Paper Sets: upsert by label, never delete-and-recreate ──────────
        #
        # This used to be `paper.sets.all().delete()` followed by a bulk
        # create, which had two consequences on a paper that has more than
        # one set:
        #
        #   1. Editor autosave sends ONLY Set A (updatePaperAction wraps the
        #      current document into a lone Set A when no `sets` are given),
        #      so the first keystroke on a multi-set paper silently destroyed
        #      Sets B and C.
        #   2. Every save minted new PaperSet ids, discarding each set's
        #      s3_pdf_key / s3_docx_key / s3_content_key. Previously exported
        #      PDFs became unreachable and their S3 objects orphaned.
        #
        # Upserting on the normalised label keeps ids — and therefore export
        # keys — stable, and leaves sets the payload does not mention alone.
        # Removing a set is not something the UI offers, so absence means
        # "not included in this save", never "delete me".
        def _norm(label: str) -> str:
            return (label or "").strip().upper().removeprefix("SET ").strip()

        existing = {_norm(s.label): s for s in paper.sets.all()}
        for set_data in sets:
            label = set_data.get("label", "Set")
            paper_set = existing.get(_norm(label))
            if paper_set is None:
                PaperSet.objects.create(
                    paper=paper,
                    label=label,
                    order=set_data.get("order", 1),
                    content=set_data.get("content", ""),
                    answers=set_data.get("answers", ""),
                    metadata=set_data.get("metadata", {}),
                )
                continue
            paper_set.label = label
            paper_set.order = set_data.get("order", 1)
            paper_set.content = set_data.get("content", "")
            paper_set.answers = set_data.get("answers", "")
            paper_set.metadata = set_data.get("metadata", {})
            paper_set.save(
                update_fields=[
                    "label",
                    "order",
                    "content",
                    "answers",
                    "metadata",
                    "updated_at",
                ]
            )

        if questions:
            question_objects = [
                Question(
                    content=q.get("content", ""),
                    answer=q.get("answer") or None,
                    # `type` is a FK to QuestionType. Assigning the raw string
                    # raises ValueError ("must be a QuestionType instance") the
                    # moment a caller sends a non-empty `questions` list, so
                    # set the id side of the relation. Unlike the questions
                    # endpoint this payload is a bare DictField — nothing has
                    # canonicalised the code — so resolve it here or an alias
                    # ("short", "MCQ") becomes a foreign-key violation.
                    type_id=resolve_type_code(q.get("type")),
                    marks=int(q.get("marks") or 1),
                    options=q.get("options") or [],
                    project=project,
                    paper=paper,
                )
                for q in questions
            ]
            Question.objects.bulk_create(question_objects)

        if hsat_source_ids is not None:
            from apps.documents.models import PaperHsatSource
            # Remove any linked HSAT sources not in the new set
            PaperHsatSource.objects.filter(paper=paper).exclude(hsat_source_id__in=hsat_source_ids).delete()
            # Link new ones
            for hsat_id in hsat_source_ids:
                PaperHsatSource.objects.get_or_create(paper=paper, hsat_source_id=hsat_id)

    from services.paper_content_service import dual_write_set_content
    for paper_set in paper.sets.all():
        dual_write_set_content(paper_set)

    return paper
