from typing import List, Optional

from django.db import transaction

from apps.projects.models import Project, Question, Paper
from apps.projects.question_types import resolve_type_code


def list_projects_for_user(user) -> List[Project]:
    return Project.objects.filter(user=user).prefetch_related("questions").order_by("-created_at")


def list_papers_for_user(user) -> List[Paper]:
    # prefetch_related("sets") — the list serializer embeds every PaperSet, so
    # without this the papers table issues one extra query per paper (N+1),
    # which the redesigned enterprise list (hundreds of papers) would feel.
    return (
        Paper.objects.filter(user=user)
        .select_related("project")
        .prefetch_related("sets")
        .order_by("-updated_at")
    )


def get_paper_for_user(user, paper_id: str) -> Paper:
    return Paper.objects.select_related("project").get(id=paper_id, user=user)


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
            # Update existing paper
            paper = Paper.objects.get(id=paper_id, user=user)
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
