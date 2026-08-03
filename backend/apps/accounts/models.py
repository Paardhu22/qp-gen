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


class BrandKit(TimeStampedModel):
    """A school's identity, stored once instead of retyped onto every paper.

    Every paper a school prints carries the same masthead — the institute's
    name, its address, its crest — and before this each one was typed again
    into the header block, or a logo re-uploaded from the teacher's desktop.
    The kit is what turns that into a default.

    One per user, which is the right grain today: an account belongs to a
    teacher at a school, and the school is the brand. Multiple kits (a teacher
    working across two institutions) would be an additional row plus a default
    flag; nothing here forecloses that.

    Everything is optional. A blank kit is the correct state for a teacher who
    has not set one up, and every consumer has to treat empty as "no opinion"
    and fall back to what it did before — a brand kit must never be the reason
    a paper cannot be printed.
    """

    id = models.CharField(
        primary_key=True, max_length=32, default=generate_id, editable=False
    )
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        db_column="userId",
        related_name="brand_kit",
    )
    institute_name = models.CharField(
        max_length=200, blank=True, default="", db_column="instituteName"
    )
    institute_address = models.TextField(
        blank=True, default="", db_column="instituteAddress"
    )
    #: Hex, e.g. "#2f5fdd". Validated at the API edge rather than here so a
    #: legacy or hand-edited row can never make an existing paper unloadable.
    accent_color = models.CharField(
        max_length=9, blank=True, default="", db_column="accentColor"
    )
    #: A CSS font stack the editor already offers. Free text because the list
    #: lives in the frontend toolbar and duplicating it here would create two
    #: vocabularies that drift.
    font_family = models.CharField(
        max_length=120, blank=True, default="", db_column="fontFamily"
    )
    #: The teacher's house style for the header block: which columns the table
    #: shows and whether the date row starts on. Shape is
    #: `{"columns": ["SUBJECT", ...], "showDate": bool}`. JSON rather than
    #: columns because it describes a layout, and layouts gain fields.
    header_layout = models.JSONField(
        default=dict, blank=True, db_column="headerLayout"
    )

    class Meta:
        db_table = "BrandKit"

    def __str__(self) -> str:
        return f"{self.institute_name or 'Untitled brand'} ({self.id})"


class BrandAsset(TimeStampedModel):
    """One uploaded image belonging to a brand kit — in practice, a logo.

    Separate from `BrandKit` because there is genuinely more than one: a school
    crest and a board emblem sit side by side on a great many Indian question
    papers, and a single `logo` column would have forced a choice between them.

    Only the storage path is persisted. URLs are minted on read through
    `services/media_urls.py`, which is a hard rule in this codebase: a stored
    URL is either a hardcoded `/media/...` that breaks when storage moves, or a
    presigned S3 link that expires and leaves a broken image on a saved paper.
    """

    KIND_LOGO = "logo"

    id = models.CharField(
        primary_key=True, max_length=32, default=generate_id, editable=False
    )
    kit = models.ForeignKey(
        BrandKit,
        on_delete=models.CASCADE,
        db_column="kitId",
        related_name="assets",
    )
    #: What the teacher called it, so a picker showing two crests is usable.
    name = models.CharField(max_length=120, blank=True, default="")
    kind = models.CharField(max_length=20, default=KIND_LOGO)
    #: `default_storage` path — S3 key in production, MEDIA_ROOT-relative
    #: locally. Never a URL. See the class docstring.
    storage_path = models.CharField(max_length=500, db_column="storagePath")
    #: Intrinsic pixel size, recorded at upload so the editor can preserve the
    #: aspect ratio without waiting for the image to load.
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "BrandAsset"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.name or self.kind} ({self.id})"
