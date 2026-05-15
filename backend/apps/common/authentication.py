from django.conf import settings
from django.db import DataError
from django.utils import timezone
from datetime import timezone as dt_timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
import jwt

from apps.accounts.models import Session, User
from django.core.cache import cache


class JWTAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        try:
            auth = get_authorization_header(request).split()
            if not auth:
                return None

            if auth[0].decode().lower() != self.keyword.lower():
                return None

            if len(auth) != 2:
                raise AuthenticationFailed("Invalid Authorization header.")

            token = auth[1].decode()

            try:
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM],
                    issuer=settings.JWT_ISSUER,
                    options={"require": ["exp", "iat", "jti", "sub", "type"]},
                )
            except jwt.ExpiredSignatureError as exc:
                raise AuthenticationFailed("Access token expired.") from exc
            except jwt.InvalidTokenError as exc:
                raise AuthenticationFailed("Invalid access token.") from exc

            if payload.get("type") != "access":
                raise AuthenticationFailed("Invalid access token.")

            user_id = payload.get("sub")
            jti = payload.get("jti")
            if not user_id or not jti:
                raise AuthenticationFailed("Invalid access token.")

            # Guard against malformed tokens causing DB-level type/length errors.
            if len(str(user_id)) > 32 or len(str(jti)) > 255:
                raise AuthenticationFailed("Invalid access token.")

            session = Session.objects.filter(token=jti, user_id=user_id).first()
            # Cache session existence briefly to avoid a DB round-trip on every request
            # Cache key TTL is set to remaining lifetime of the session when available.
            if not session:
                cached = cache.get(f"session:{jti}")
                if cached:
                    # cached stores user id as a simple truthy value
                    session = True
            if not session:
                raise AuthenticationFailed("Access token revoked.")

            # If we had a full Session object, get its expiry; if cache returned True,
            # we will skip expiry comparison (cache TTL provides protection).
            expires_at = None
            if hasattr(session, "expires_at"):
                expires_at = session.expires_at
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at, dt_timezone.utc)

            if expires_at is not None:
                if timezone.is_naive(expires_at):
                    expires_at = timezone.make_aware(expires_at, dt_timezone.utc)

                if expires_at <= timezone.now():
                    raise AuthenticationFailed("Access token revoked.")

            user = User.objects.filter(id=user_id).first()
            if not user:
                raise AuthenticationFailed("User not found.")
            # If we resolved a real Session object, cache a lightweight marker
            # so subsequent requests can skip the DB check until TTL expires.
            if hasattr(session, "expires_at"):
                ttl = int((expires_at - timezone.now()).total_seconds())
                if ttl > 0:
                    cache.set(f"session:{jti}", True, ttl)

            return (user, None)
        except DataError as exc:
            raise AuthenticationFailed("Invalid access token.") from exc

    def authenticate_header(self, request) -> str:
        return self.keyword
