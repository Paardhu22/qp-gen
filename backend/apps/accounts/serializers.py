from rest_framework import serializers

from apps.accounts.models import User


class UserSerializer(serializers.ModelSerializer):
    tokens_consumed = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "name", "email", "image", "status", "tokens_consumed"]

    def get_tokens_consumed(self, obj):
        from apps.generation.models import ApiUsage
        from django.db.models import Sum
        result = ApiUsage.objects.filter(user=obj).aggregate(total=Sum("total_tokens"))
        return result["total"] or 0
