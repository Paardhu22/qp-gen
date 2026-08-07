from django.db.models import Sum
from rest_framework import serializers

from apps.generation.models import ApiUsage
from services.organization_logo import normalize_gstin, organization_logo_url

from .models import Membership, Organization, OrganizationInvite

#: The institute-profile columns an org admin may write. Kept in one place
#: because three call sites need the same list — onboarding, the PATCH endpoint
#: and the serializer — and a field present in one but not the others is the
#: kind of drift that silently drops what an admin typed.
PROFILE_FIELDS = [
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
    class Meta:
        model = Organization
        fields = ["id", "name"]


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


class OrganizationListSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    total_tokens = serializers.SerializerMethodField()
    admin_email = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()

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
            "admin_email",
            "logo_url",
            "city",
            "state",
        ]

    def get_member_count(self, obj):
        return obj.members.count()

    def get_total_tokens(self, obj):
        result = ApiUsage.objects.filter(organization=obj).aggregate(total=Sum("total_tokens"))
        return result["total"] or 0

    def get_admin_email(self, obj):
        admin_membership = obj.members.filter(role="org_admin").select_related("user").first()
        return admin_membership.user.email if admin_membership else None

    def get_logo_url(self, obj):
        return organization_logo_url(obj)


class MembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.CharField(source="user.id", read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    tokens_consumed = serializers.SerializerMethodField()

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
        ]

    def get_tokens_consumed(self, obj):
        result = ApiUsage.objects.filter(user=obj.user).aggregate(total=Sum("total_tokens"))
        return result["total"] or 0


class OrganizationDetailSerializer(OrganizationListSerializer):
    members = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()

    class Meta(OrganizationListSerializer.Meta):
        fields = (
            OrganizationListSerializer.Meta.fields
            + ["members", "logo_url", "logo_width", "logo_height"]
            + PROFILE_FIELDS
        )

    def get_members(self, obj):
        return MembershipSerializer(obj.members.select_related("user").all(), many=True).data

    def get_logo_url(self, obj):
        # Minted per read, never stored — see services/organization_logo.py.
        return organization_logo_url(obj)


class OrganizationInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationInvite
        fields = ["id", "email", "status", "created_at", "expires_at"]
