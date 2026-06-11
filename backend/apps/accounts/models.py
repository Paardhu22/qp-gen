from django.db import models

from apps.common.models import TimeStampedModel
from utils.ids import generate_id


class User(TimeStampedModel):
    # Cognito sub stripped of hyphens is exactly 32 hex characters.
    # Default generate_id is kept for backwards compatibility with tests and system scripts.
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    image = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("admin", "Admin"),
            ("rejected", "Rejected"),
        ],
    )

    class Meta:
        db_table = "user"

    @property
    def is_authenticated(self) -> bool:
        return True
