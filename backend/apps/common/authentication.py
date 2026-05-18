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

            cached = cache.get(f"session:{jti}")
            if cached:
                cached_exp = cached.get("expires_at")
                if cached_exp and cached_exp <= int(timezone.now().timestamp()):
                    cache.delete(f"session:{jti}")
                else:
                    user_data = cached.get("user_data")
                    if user_data:
                        return (User(**user_data), None)
                    # Fallback for old cache format: delete and fall through to DB fetch
                    cache.delete(f"session:{jti}")

            session = (
                Session.objects
                .select_related("user")
                .filter(token=jti, user_id=user_id)
                .first()
            )
            if not session:
                raise AuthenticationFailed("Access token revoked.")

            expires_at = session.expires_at
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at, dt_timezone.utc)

            if expires_at <= timezone.now():
                raise AuthenticationFailed("Access token revoked.")

            # Cache session info to avoid a DB round-trip on every request
            ttl = int((expires_at - timezone.now()).total_seconds())
            if ttl > 0:
                user = session.user
                user_data = {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "image": user.image,
                }
                cache.set(
                    f"session:{jti}",
                    {
                        "user_id": user.id,
                        "expires_at": int(expires_at.timestamp()),
                        "user_data": user_data
                    },
                    ttl,
                )

            return (session.user, None)
        except DataError as exc:
            raise AuthenticationFailed("Invalid access token.") from exc

    def authenticate_header(self, request) -> str:
        return self.keyword
