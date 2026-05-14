from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid

from django.conf import settings
from django.utils import timezone as dj_timezone
import jwt

from apps.accounts.models import Session, User


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    access_jti: str
    refresh_jti: str


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _encode(payload: dict) -> str:
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _build_payload(user: User, token_type: str, expires_at: datetime, jti: str) -> dict:
    payload = {
        "sub": user.id,
        "type": token_type,
        "jti": jti,
        "iat": int(_utc_now().timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.JWT_ISSUER,
    }
    return payload


def create_token_pair(user: User) -> TokenPair:
    access_expires_at = _utc_now() + timedelta(days=settings.JWT_ACCESS_TTL_DAYS)
    refresh_expires_at = _utc_now() + timedelta(days=settings.JWT_REFRESH_TTL_DAYS)

    access_jti = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())

    access_payload = _build_payload(user, "access", access_expires_at, access_jti)
    refresh_payload = _build_payload(user, "refresh", refresh_expires_at, refresh_jti)

    access_token = _encode(access_payload)
    refresh_token = _encode(refresh_payload)

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
        access_jti=access_jti,
        refresh_jti=refresh_jti,
    )


def record_access_session(user: User, access_jti: str, expires_at: datetime, request) -> None:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip_address = forwarded_for.split(",")[0].strip() if forwarded_for else request.META.get("REMOTE_ADDR")
    user_agent = request.META.get("HTTP_USER_AGENT", "")

    Session.objects.create(
        user=user,
        token=access_jti,
        expires_at=expires_at,
        ip_address=ip_address or None,
        user_agent=user_agent or None,
    )


def decode_refresh_token(token: str) -> dict:
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        options={"require": ["exp", "iat", "jti", "sub", "type"]},
    )
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Invalid token type")
    return payload


def decode_access_token(token: str, verify_exp: bool = True) -> dict:
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        options={
            "require": ["exp", "iat", "jti", "sub", "type"],
            "verify_exp": verify_exp,
        },
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    return payload


def revoke_access_token(jti: str, user_id: str) -> None:
    Session.objects.filter(token=jti, user_id=user_id).delete()


def access_token_is_active(jti: str, user_id: str) -> bool:
    session = Session.objects.filter(token=jti, user_id=user_id).first()
    return bool(session and session.expires_at > dj_timezone.now())
