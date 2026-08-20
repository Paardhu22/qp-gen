from django.db.models import Sum
from rest_framework import serializers

from apps.generation.models import ApiUsage
from services.organization_logo import normalize_gstin, organization_logo_url
from services.usage_pricing import inr_cost_of_usage

from .domains import domain_list, normalize_domains
from .models import Membership, Organization, OrganizationInvite
from .selectors import (
    ADMIN_EMAIL_ATTR,
    COST_INR_ATTR,
    MEMBER_COUNT_ATTR,
    TOTAL_TOKENS_ATTR,
    member_usage_map,
)

#: The institute-profile columns an org admin may write. Kept in one place
#: because three call sites need the same list — onboarding, the PATCH endpoint
#: and the serializer — and a field present in one but not the others is the
#: kind of drift that silently drops what an admin typed.
PROFILE_FIELDS = [
    "email_domains",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "postal_code",
    "country",
    "phone",
    "website",
    "gstin",
]


class PublicOrganizationSerializer(serializers.ModelSerializer):
    """The signup dropdown. Deliberately says as little as possible.

    `matches_email_domain` is set from the serializer context when the signup
    form has already collected an address: it lets the form pre-select the
    right school instead of asking a teacher to find it in an alphabetical list
    of every school on the platform. It is a hint and grants nothing — the
    membership still starts pending.
    """

    matches_email_domain = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ["id", "name", "city", "matches_email_domain"]

    def get_matches_email_domain(self, obj):
        domain = (self.context or {}).get("email_domain") or ""
        if not domain:
            return False
        return domain in domain_list(obj.email_domains)


class OrganizationProfileSerializer(serializers.ModelSerializer):
    """Write path for the institute profile: onboarding step 2 and Settings.

    Every field is optional — see the model. `name` is accepted so an admin can
    correct a typo later, but it is never required here either; a PATCH that
    omits it leaves it alone.
    """

    class Meta:
        model = Organization
        fields = ["name"] + PROFILE_FIELDS
        extra_kwargs = {field: {"required": False} for field in ["name"] + PROFILE_FIELDS}

    def validate_name(self, value):
        cleaned = (value or "").strip()
        if not cleaned:
            raise serializers.ValidationError("The organization needs a name.")
        return cleaned

    def validate_gstin(self, value):
        # Shape-checked here rather than on the model so an existing row with a
        # legacy value can still be loaded and corrected.
        try:
            return normalize_gstin(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_email_domains(self, value):
        # Same reasoning as `gstin`: validated at the edge, stored loosely, so a
        # legacy row can never make an organization unloadable.
        try:
            return normalize_domains(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class OrganizationListSerializer(serializers.ModelSerializer):
    """One row of the superadmin table.

    Every count here is read from an attribute `selectors.with_usage()` stamped
    on the instance, falling back to computing it per-object. The fallback is
    correctness insurance for a serializer handed a bare model; the batched
    path is what keeps a page of schools a fixed number of queries instead of
    four per row.
    """

    member_count = serializers.SerializerMethodField()
    total_tokens = serializers.SerializerMethodField()
    total_cost_inr = serializers.SerializerMethodField()
    admin_email = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()
    email_domains = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "is_active",
            "created_at",
            "member_count",
            "total_tokens",
            "total_cost_inr",
            "monthly_token_limit",
            "admin_email",
            "logo_url",
            "city",
            "state",
            "email_domains",
        ]

    def get_member_count(self, obj):
        cached = getattr(obj, MEMBER_COUNT_ATTR, None)
        return cached if cached is not None else obj.members.count()

    def get_total_tokens(self, obj):
        cached = getattr(obj, TOTAL_TOKENS_ATTR, None)
        if cached is not None:
            return cached
        result = ApiUsage.objects.filter(organization=obj).aggregate(total=Sum("total_tokens"))
        return result["total"] or 0

    def get_total_cost_inr(self, obj):
        """Estimated rupee spend, all time. See services/usage_pricing.py.

        An estimate, and the UI must say so: our token counts cannot see
        cached-input discounts or the separate image-token tiers.
        """
        cached = getattr(obj, COST_INR_ATTR, None)
        if cached is not None:
            return cached
        return inr_cost_of_usage(ApiUsage.objects.filter(organization=obj))

    def get_admin_email(self, obj):
        if hasattr(obj, ADMIN_EMAIL_ATTR):
            return getattr(obj, ADMIN_EMAIL_ATTR)
        admin_membership = obj.members.filter(role="org_admin").select_related("user").first()
        return admin_membership.user.email if admin_membership else None

    def get_logo_url(self, obj):
        return organization_logo_url(obj)

    def get_email_domains(self, obj):
        return domain_list(obj.email_domains)


class MembershipSerializer(serializers.ModelSerializer):
    """One member row.

    `usage_by_user` in the serializer context is the batched answer for the
    whole roster — see `selectors.member_usage_map`. Without it each row falls
    back to its own aggregate, which is correct but is the N+1 this context is
    there to avoid.
    """

    user_id = serializers.CharField(source="user.id", read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    tokens_consumed = serializers.SerializerMethodField()
    cost_inr = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = [
            "id",
            "user_id",
            "name",
            "email",
            "role",
            "status",
            "created_at",
            "tokens_consumed",
            "cost_inr",
        ]

    def _usage(self, obj):
        batched = (self.context or {}).get("usage_by_user")
        if batched is not None:
            return batched.get(obj.user_id) or {"tokens": 0, "cost_inr": 0.0}
        usage = ApiUsage.objects.filter(user=obj.user, organization=obj.organization)
        return {
            "tokens": usage.aggregate(total=Sum("total_tokens"))["total"] or 0,
            "cost_inr": inr_cost_of_usage(usage),
        }

    def get_tokens_consumed(self, obj):
        return self._usage(obj)["tokens"]

    def get_cost_inr(self, obj):
        return self._usage(obj)["cost_inr"]


class OrganizationDetailSerializer(OrganizationListSerializer):
    members = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()

    class Meta(OrganizationListSerializer.Meta):
        # De-duplicated: `email_domains` is on both lists — it is part of the
        # institute profile an admin edits AND part of what the list row shows —
        # and naming a field twice is the kind of thing that works until a DRF
        # upgrade decides it shouldn't.
        fields = list(
            dict.fromkeys(
                OrganizationListSerializer.Meta.fields
                + ["members", "logo_url", "logo_width", "logo_height"]
                + PROFILE_FIELDS
            )
        )

    def get_members(self, obj):
        members = list(obj.members.select_related("user").all())
        return MembershipSerializer(
            members,
            many=True,
            # Two queries for the whole roster instead of two per member.
            context={"usage_by_user": member_usage_map(obj)},
        ).data

    def get_logo_url(self, obj):
        # Minted per read, never stored — see services/organization_logo.py.
        return organization_logo_url(obj)


class OrganizationInviteSerializer(serializers.ModelSerializer):
    """An outstanding invite, as the admin screens list it.

    `effective_status` rather than the raw column: an invite whose date has
    passed is still stored as "pending" until something touches it, and a list
    that shows it as pending is lying to the person deciding whether to chase
    it. The stored value is reconciled lazily by the list view; this makes the
    display correct even before that happens.

    The token is never serialized. It is the secret that accepts the invite, and
    it belongs in the emailed link and nowhere else.
    """

    organization_name = serializers.CharField(
        source="organization.name", read_only=True, default=None
    )
    effective_status = serializers.SerializerMethodField()
    invited_by_email = serializers.CharField(
        source="invited_by.email", read_only=True, default=None
    )

    class Meta:
        model = OrganizationInvite
        fields = [
            "id",
            "email",
            "role",
            "status",
            "effective_status",
            "organization",
            "organization_name",
            "invited_by_email",
            "created_at",
            "expires_at",
        ]

    def get_effective_status(self, obj):
        if obj.status == "pending" and obj.is_expired:
            return "expired"
        return obj.status
