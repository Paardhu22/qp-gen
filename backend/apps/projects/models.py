from django.db import models
from django.contrib.postgres.fields import ArrayField

from apps.accounts.models import User
from apps.common.models import TimeStampedModel
from utils.ids import generate_id


class Project(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="userId", related_name="projects")

    class Meta:
        db_table = "Project"


class Paper(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    title = models.CharField(max_length=255)
    content = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE, db_column="projectId", related_name="papers")
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="userId", related_name="papers")

    class Meta:
        db_table = "Paper"


class Question(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    type = models.CharField(max_length=50)
    content = models.TextField()
    answer = models.TextField(null=True, blank=True)
    options = ArrayField(models.TextField(), default=list, blank=True)
    marks = models.IntegerField(default=1)
    bloom_taxonomy = models.CharField(max_length=50, null=True, blank=True, db_column="bloomTaxonomy")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, db_column="projectId", related_name="questions")
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, null=True, blank=True, db_column="paperId", related_name="questions")

    class Meta:
        db_table = "Question"
