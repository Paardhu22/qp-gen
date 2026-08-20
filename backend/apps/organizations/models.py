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

    #: Zero means no cap. A positive number blocks new billable model calls
    #: once this organization's recorded usage for the calendar month reaches
    #: the limit.
    monthly_token_limit = models.PositiveIntegerField(default=0)

    #: Comma-separated email domains this school's staff addresses end in, e.g.
    #: "dpsbangalore.edu.in,dps-blr.org". Used to pre-select the right school on
    #: the signup dropdown — a hint, never an authorisation. Membership still
    #: starts pending and still needs an admin's approval; a domain is trivially
    #: spoofable at signup. Stored as text rather than rows because it is a
    #: short list edited as one field, and public providers are refused at the
    #: API edge. See apps/organizations/domains.py.
    email_domains = models.CharField(max_length=500, blank=True, default="")

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
    """A link that lets one named email address join the platform.

    Two kinds, distinguished by `role`, and the difference matters:

    *   `org_admin` — issued by the platform superadmin to an address with no
        organization yet. Accepting it CREATES a school and makes the accepter
        its administrator. `organization` is null until then.
    *   `teacher` — issued by a school's own admin, for their own school.
        `organization` is set at creation. Accepting it joins that school
        **already approved**, because the admin who would have approved the
        request is the person who sent the link. That is the entire point: it
        collapses "sign up, pick your school from a list, wait" into one click,
        and it is the only place a teacher skips the approval queue.

    Either way the token is the secret and the email is the binding: accepting
    checks that the authenticated caller's address matches the one invited, so
    a leaked link is not a way into someone else's school.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("expired", "Expired"),
        ("revoked", "Revoked"),
    ]
    ROLE_CHOICES = [
        ("org_admin", "Organization Admin"),
        ("teacher", "Teacher"),
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
    #: Defaults to org_admin so every row written before teacher invites
    #: existed keeps its original meaning.
    role = models.CharField(max_length=20, default="org_admin", choices=ROLE_CHOICES)
    status = models.CharField(max_length=20, default="pending", choices=STATUS_CHOICES)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "OrganizationInvite"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.email} ({self.role}, {self.status})"

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone

        return self.expires_at < timezone.now()

    @property
    def is_open(self) -> bool:
        """Still usable: never accepted, never revoked, not past its date."""
        return self.status == "pending" and not self.is_expired


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
    #: A ForeignKey, not a OneToOne. Teachers genuinely work at more than one
    #: school — a subject specialist covering two branches of the same trust, a
    #: visiting examiner, someone mid-move between jobs — and a one-to-one made
    #: the second school unreachable without deleting the first, which took the
    #: first school's papers with it.
    #:
    #: Which of several memberships is *in effect* is not stored here. It is
    #: `User.active_organization`, because that is a property of the person's
    #: current session, not of any one membership; keeping it on the membership
    #: would mean two rows can disagree about which is active.
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
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
        constraints = [
            # One membership per person per school. Two rows for the same pair
            # would make "are they approved here?" a question with two answers.
            models.UniqueConstraint(
                fields=["user", "organization"], name="unique_membership_per_organization"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user.email} @ {self.organization.name} ({self.role}, {self.status})"
