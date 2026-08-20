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
    # Platform-wide admin, independent of any organization. Synced from the
    # Cognito "superadmin" group claim — see CognitoJWTAuthentication.
    is_superadmin = models.BooleanField(default=False)

    #: Which school this account is currently acting as, when it belongs to
    #: more than one.
    #:
    #: A teacher can hold several memberships — a subject specialist covering
    #: two branches, someone mid-move between jobs — but at any moment they are
    #: working *as* one school: one brand header on the paper, one budget the
    #: tokens come out of, one set of colleagues in the admin screens. This
    #: names that one. It lives on the user rather than as a flag on a
    #: Membership row because it describes the person's current context, and
    #: two rows can disagree about a flag in a way one column cannot.
    #:
    #: Null is normal and self-healing: `active_membership` falls back to the
    #: sole approved membership, so an account with one school never has to set
    #: this at all, and one whose active school is removed lands somewhere
    #: sensible rather than nowhere.
    active_organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_users",
    )

    class Meta:
        db_table = "user"

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def active_membership(self):
        """The membership currently in effect, or None.

        Resolution order, and each step earns its place:

        1.  The membership for `active_organization`, if there still is one.
            This is the teacher's explicit choice and outranks everything.
        2.  Otherwise the single approved membership — an account with one
            school never has to choose, and must not be asked to.
        3.  Otherwise the most recent membership of any status, so a teacher
            whose only join request is still pending still has a membership to
            show them (which is what tells them they are waiting on someone).

        Never raises. A user with no memberships gets None, and every caller
        already treats None as "no school".
        """
        memberships = list(self.memberships.all())
        if not memberships:
            return None

        if self.active_organization_id:
            for membership in memberships:
                if membership.organization_id == self.active_organization_id:
                    return membership

        approved = [m for m in memberships if m.status == "approved"]
        if approved:
            # Deterministic without a second query: oldest approved wins, which
            # is the school they have been at longest.
            return sorted(approved, key=lambda m: m.created_at)[0]

        return sorted(memberships, key=lambda m: m.created_at)[-1]

    @property
    def membership(self):
        """Back-compatible alias for `active_membership`.

        Every existing call site asks `user.membership` and means "the one that
        is in effect". Keeping the name means multi-org did not have to touch
        permissions, serializers and views to say the same thing differently.
        """
        return self.active_membership

    @property
    def organization(self):
        """The organization this user acts on behalf of, or None.

        Approval-gated on purpose: this is the *authorisation* answer, and a
        teacher whose join request is still pending must not read their
        school's data. For the *billing* answer — who pays for what this
        account spends — use `billing_organization`, which is not gated.
        """
        membership = self.active_membership
        if not membership or membership.status != "approved":
            return None
        return membership.organization

    @property
    def billing_organization(self):
        """The organization whose budget this account's usage comes out of.

        Deliberately NOT approval-gated, which is the whole point. A teacher
        can spend tokens while their membership is pending or after it is
        rejected — an admin approves them mid-session, they are downgraded
        mid-session, or a request slips through between the two states — and
        under the approval-gated `organization` every one of those calls was
        written with `organization=None`. That did two bad things at once: the
        spend vanished from the school's dashboard into "unassigned", and it
        escaped the school's monthly token limit entirely, because a limit
        check that resolves to no organization returns early.

        Attribution follows the membership, not its status. If the account
        belongs to a school at all, the school pays.
        """
        membership = self.active_membership
        return membership.organization if membership else None

    def membership_for(self, organization_id):
        """This user's membership at one school, or None."""
        if not organization_id:
            return None
        for membership in self.memberships.all():
            if membership.organization_id == organization_id:
                return membership
        return None

    def approved_memberships(self):
        return [m for m in self.memberships.all() if m.status == "approved"]


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
