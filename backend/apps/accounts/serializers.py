import re

from rest_framework import serializers

from apps.accounts.models import User

GMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+\-]+@gmail\.com$')


def validate_gmail(value: str) -> str:
    if not GMAIL_REGEX.match(value):
        raise serializers.ValidationError("Enter a valid Gmail address (e.g. example@gmail.com).")
    return value


class UserSerializer(serializers.ModelSerializer):
    tokens_consumed = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "name", "email", "image", "tokens_consumed"]

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
    email = serializers.EmailField(validators=[validate_gmail])
    password = serializers.CharField(min_length=8, write_only=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(validators=[validate_gmail])
    password = serializers.CharField(write_only=True)


class RefreshSerializer(serializers.Serializer):
    refreshToken = serializers.CharField()
