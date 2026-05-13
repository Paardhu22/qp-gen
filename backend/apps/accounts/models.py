from django.db import models
from django.contrib.auth.hashers import check_password, make_password

from apps.common.models import TimeStampedModel
from utils.ids import generate_id


class User(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False, db_column="emailVerified")
    image = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "user"

    @property
    def is_authenticated(self) -> bool:
        return True


class Session(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    expires_at = models.DateTimeField(db_column="expiresAt")
    token = models.CharField(unique=True, max_length=255)
    ip_address = models.CharField(max_length=255, null=True, blank=True, db_column="ipAddress")
    user_agent = models.TextField(null=True, blank=True, db_column="userAgent")
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="userId", related_name="sessions")

    class Meta:
        db_table = "session"


class Account(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    account_id = models.CharField(max_length=255, db_column="accountId")
    provider_id = models.CharField(max_length=255, db_column="providerId")
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="userId", related_name="accounts")
    access_token = models.TextField(null=True, blank=True, db_column="accessToken")
    refresh_token = models.TextField(null=True, blank=True, db_column="refreshToken")
    id_token = models.TextField(null=True, blank=True, db_column="idToken")
    access_token_expires_at = models.DateTimeField(null=True, blank=True, db_column="accessTokenExpiresAt")
    refresh_token_expires_at = models.DateTimeField(null=True, blank=True, db_column="refreshTokenExpiresAt")
    scope = models.TextField(null=True, blank=True)
    password = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "account"

    def set_password(self, raw_password: str) -> None:
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        if not self.password:
            return False
        return check_password(raw_password, self.password)


class Verification(TimeStampedModel):
    id = models.CharField(primary_key=True, max_length=32, default=generate_id, editable=False)
    identifier = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
    expires_at = models.DateTimeField(db_column="expiresAt")

    class Meta:
        db_table = "verification"
