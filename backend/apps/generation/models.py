from django.db import models

from apps.accounts.models import User
from apps.common.models import TimeStampedModel
from utils.ids import generate_id


class GenerationHistory(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    prompt = models.TextField()
    settings = models.JSONField()
    result = models.JSONField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="userId", related_name="history")

    class Meta:
        db_table = "GenerationHistory"
