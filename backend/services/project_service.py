from typing import List

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
        project, _ = Project.objects.get_or_create(name=project_name, user=user)
        question_objects = []
        for question in questions:
            question_objects.append(
                Question(
                    content=question.get("content", ""),
                    answer=question.get("answer"),
                    type=question.get("type", "mcq"),
                    marks=int(question.get("marks") or 1),
                    options=question.get("options") or [],
                    project=project,
                )
            )
        Question.objects.bulk_create(question_objects)

    return project


def save_paper_to_project(
    user,
    project_name: str,
    title: str,
    content: str,
    questions: List[dict] = None,
    paper_id: str = None,
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

    return paper
