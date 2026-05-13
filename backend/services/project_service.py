from typing import List

from django.db import transaction

from apps.projects.models import Project, Question


def list_projects_for_user(user) -> List[Project]:
    return Project.objects.filter(user=user).prefetch_related("questions").order_by("-created_at")


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
