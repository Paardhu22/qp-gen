from typing import List, Optional

from django.db import transaction

from apps.projects.models import Project, Question, Paper


def list_projects_for_user(user) -> List[Project]:
    return Project.objects.filter(user=user).prefetch_related("questions").order_by("-created_at")


def list_papers_for_user(user) -> List[Paper]:
    return Paper.objects.filter(user=user).select_related("project").order_by("-updated_at")


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
                    type=question.get("type", "mcq"),
                    marks=int(question.get("marks") or 1),
                    options=question.get("options") or [],
                    project=projects_cache[q_project_name],
                    grade_class=question.get("grade_class"),
                    subject=question.get("subject"),
                    inferred_topic=question.get("inferred_topic"),
                    inferred_chapter=question.get("inferred_chapter"),
                    source_pdf=question.get("source_pdf"),
                    difficulty=question.get("difficulty"),
                )
            )
        Question.objects.bulk_create(question_objects)

    # Return the first created/fetched project as a fallback for the response
    return list(projects_cache.values())[0] if projects_cache else None


def save_paper_to_project(
    user,
    project_name: str,
    title: str,
    content: str,
    questions: Optional[List[dict]] = None,
    paper_id: Optional[str] = None,
    hsat_source_ids: Optional[List[str]] = None,
) -> Paper:
    """Create or update a Paper and persist its questions."""
    if questions is None:
        questions = []

    with transaction.atomic():
        project, _ = Project.objects.get_or_create(name=project_name, user=user)

        if paper_id:
            # Update existing paper (raises Paper.DoesNotExist if not found/owned)
            paper = Paper.objects.get(id=paper_id, user=user)
            paper.title = title
            paper.content = content
            paper.project = project
            paper.save()
            # Replace questions: delete old paper-linked questions then re-create
            paper.questions.all().delete()
        else:
            paper = Paper.objects.create(
                title=title,
                content=content,
                project=project,
                user=user,
            )

        if questions:
            question_objects = [
                Question(
                    content=q.get("content", ""),
                    answer=q.get("answer") or None,
                    type=q.get("type") or "short",
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

    return paper
