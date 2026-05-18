from rest_framework import serializers

from apps.accounts.models import User


class UserSerializer(serializers.ModelSerializer):
    tokens_consumed = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "name", "email", "email_verified", "image", "tokens_consumed"]

    def get_tokens_consumed(self, obj):
        from apps.generation.models import ApiUsage
        from django.db.models import Sum
        result = ApiUsage.objects.filter(user=obj).aggregate(total=Sum("total_tokens"))
        return result["total"] or 0


class ChangePasswordSerializer(serializers.Serializer):
    oldPassword = serializers.CharField(required=True)
    newPassword = serializers.CharField(min_length=8, required=True)


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class RefreshSerializer(serializers.Serializer):
    refreshToken = serializers.CharField()
