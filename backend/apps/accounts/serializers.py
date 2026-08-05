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

    class Meta:
        model = User
        fields = ["id", "name", "email", "image", "status", "is_superadmin", "membership", "tokens_consumed"]

    def get_tokens_consumed(self, obj):
        from apps.generation.models import ApiUsage
        from django.db.models import Sum
        result = ApiUsage.objects.filter(user=obj).aggregate(total=Sum("total_tokens"))
        return result["total"] or 0

    def get_membership(self, obj):
        membership = getattr(obj, "membership", None)
        if not membership:
            return None
        return MembershipSummarySerializer(membership).data
