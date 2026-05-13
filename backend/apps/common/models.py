from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_column="createdAt")
    updated_at = models.DateTimeField(auto_now=True, db_column="updatedAt")

    class Meta:
        abstract = True
