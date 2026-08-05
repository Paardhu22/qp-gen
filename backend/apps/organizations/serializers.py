from django.db.models import Sum
from rest_framework import serializers

from apps.generation.models import ApiUsage

from .models import Membership, Organization, OrganizationInvite


class PublicOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name"]


class OrganizationListSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    total_tokens = serializers.SerializerMethodField()
    admin_email = serializers.SerializerMethodField()

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
        ]

    def get_member_count(self, obj):
        return obj.members.count()

    def get_total_tokens(self, obj):
        result = ApiUsage.objects.filter(organization=obj).aggregate(total=Sum("total_tokens"))
        return result["total"] or 0

    def get_admin_email(self, obj):
        admin_membership = obj.members.filter(role="org_admin").select_related("user").first()
        return admin_membership.user.email if admin_membership else None


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

    class Meta(OrganizationListSerializer.Meta):
        fields = OrganizationListSerializer.Meta.fields + ["members"]

    def get_members(self, obj):
        return MembershipSerializer(obj.members.select_related("user").all(), many=True).data


class OrganizationInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationInvite
        fields = ["id", "email", "status", "created_at", "expires_at"]
