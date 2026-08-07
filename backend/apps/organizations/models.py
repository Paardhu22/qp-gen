from django.db import models
from django.utils.text import slugify

from apps.accounts.models import User
from apps.common.models import TimeStampedModel
from utils.ids import generate_id


class Organization(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, editable=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organizations_created",
    )
    is_active = models.BooleanField(default=True)

    # ─── Institute profile ──────────────────────────────────────────────────
    # Everything below is optional, and deliberately so: onboarding collects it
    # in a step the admin may skip, because a school administrator setting up an
    # account rarely has the GSTIN certificate to hand, and blocking signup on
    # it would cost more than the missing field is worth. Every consumer must
    # treat blank as "not supplied" and fall back, exactly as BrandKit does.
    address_line1 = models.CharField(max_length=255, blank=True, default="")
    address_line2 = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    state = models.CharField(max_length=120, blank=True, default="")
    #: Indian PIN codes are 6 digits, but this stays free text — an
    #: international school would otherwise be unable to finish onboarding.
    postal_code = models.CharField(max_length=20, blank=True, default="")
    country = models.CharField(max_length=120, blank=True, default="India")
    phone = models.CharField(max_length=32, blank=True, default="")
    website = models.URLField(max_length=255, blank=True, default="")
    #: 15-character Indian GSTIN. Format-checked at the API edge rather than
    #: here, so a legacy or hand-corrected row can never make an existing
    #: organization unloadable — the same rule BrandKit.accent_color follows.
    gstin = models.CharField(max_length=15, blank=True, default="")

    #: `default_storage` path for the crest — never a URL. URLs are minted on
    #: read through services/media_urls, because a stored `/media/...` breaks
    #: when storage moves to S3 and a stored presigned link expires. See
    #: services/organization_logo.py.
    logo_storage_path = models.CharField(max_length=500, blank=True, default="")
    #: Recorded at upload so a consumer can reserve the right box without
    #: waiting for the image to load.
    logo_width = models.IntegerField(null=True, blank=True)
    logo_height = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "Organization"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or generate_id()[:12]
            slug = base_slug
            counter = 2
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class OrganizationInvite(TimeStampedModel):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("expired", "Expired"),
        ("revoked", "Revoked"),
    ]

    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, editable=False)
    invited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="organization_invites_sent"
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invites",
    )
    status = models.CharField(max_length=20, default="pending", choices=STATUS_CHOICES)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "OrganizationInvite"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.email} ({self.status})"


class Membership(TimeStampedModel):
    ROLE_CHOICES = [
        ("org_admin", "Organization Admin"),
        ("teacher", "Teacher"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="membership")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="members")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    status = models.CharField(max_length=20, default="pending", choices=STATUS_CHOICES)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "Membership"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user.email} @ {self.organization.name} ({self.role}, {self.status})"
