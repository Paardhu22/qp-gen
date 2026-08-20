from rest_framework import serializers

from apps.accounts.models import User


class MembershipSummarySerializer(serializers.Serializer):
    organization_id = serializers.CharField(source="organization.id")
    organization_name = serializers.CharField(source="organization.name")
    role = serializers.CharField()
    status = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):
    tokens_consumed = serializers.SerializerMethodField()
    membership = serializers.SerializerMethodField()
    memberships = serializers.SerializerMethodField()
    # No `source=` — the model attribute is already `active_organization_id`.
    active_organization_id = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "image",
            "status",
            "is_superadmin",
            "membership",
            "memberships",
            "active_organization_id",
            "tokens_consumed",
        ]

    def get_tokens_consumed(self, obj):
        from apps.generation.models import ApiUsage
        from django.db.models import Sum
        result = ApiUsage.objects.filter(user=obj).aggregate(total=Sum("total_tokens"))
        return result["total"] or 0

    def get_membership(self, obj):
        """The membership currently in effect.

        Kept singular and kept first because it is what almost every consumer
        wants — "which school is this person working as" — and because every
        client that predates multi-org reads exactly this field. `memberships`
        below is the new, complete answer.
        """
        membership = obj.active_membership
        if not membership:
            return None
        return MembershipSummarySerializer(membership).data

    def get_memberships(self, obj):
        """Every school this account belongs to, whatever the status.

        Pending and rejected rows are included on purpose: they are what tells
        a teacher they are waiting on someone, or that they need to try a
        different school. A list of only the approved ones would leave the most
        stuck accounts looking like they belong nowhere and had never asked.
        """
        return MembershipSummarySerializer(
            obj.memberships.select_related("organization").all(), many=True
        ).data
