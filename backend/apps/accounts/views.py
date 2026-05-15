from rest_framework.authentication import get_authorization_header
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import jwt

from apps.accounts.serializers import LoginSerializer, RefreshSerializer, RegisterSerializer, UserSerializer
from services.auth_service import authenticate_user, register_user
from services.jwt_service import (
    create_token_pair,
    decode_access_token,
    decode_refresh_token,
    record_access_session,
    revoke_access_token,
)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = register_user(**serializer.validated_data)
        token_pair = create_token_pair(user)
        record_access_session(user, token_pair.access_jti, token_pair.access_expires_at, request)
        return Response(
            {
                "user": UserSerializer(user).data,
                "accessToken": token_pair.access_token,
                "refreshToken": token_pair.refresh_token,
                "accessTokenExpiresAt": token_pair.access_expires_at.isoformat(),
                "refreshTokenExpiresAt": token_pair.refresh_expires_at.isoformat(),
            },
            status=201,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate_user(**serializer.validated_data)
        token_pair = create_token_pair(user)
        record_access_session(user, token_pair.access_jti, token_pair.access_expires_at, request)
        return Response(
            {
                "user": UserSerializer(user).data,
                "accessToken": token_pair.access_token,
                "refreshToken": token_pair.refresh_token,
                "accessTokenExpiresAt": token_pair.access_expires_at.isoformat(),
                "refreshTokenExpiresAt": token_pair.refresh_expires_at.isoformat(),
            }
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        auth = get_authorization_header(request).split()
        if len(auth) != 2 or auth[0].decode().lower() != "bearer":
            return Response({"error": "Missing access token."}, status=401)

        token = auth[1].decode()
        try:
            payload = decode_access_token(token, verify_exp=False)
        except jwt.InvalidTokenError:
            return Response({"error": "Invalid access token."}, status=401)

        jti = payload.get("jti")
        user_id = payload.get("sub")
        if not jti or not user_id:
            return Response({"error": "Invalid access token."}, status=401)

        revoke_access_token(jti, user_id)
        return Response({"success": True})


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class RefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data["refreshToken"]
        try:
            payload = decode_refresh_token(refresh_token)
        except jwt.ExpiredSignatureError:
            return Response({"error": "Refresh token expired."}, status=401)
        except jwt.InvalidTokenError:
            return Response({"error": "Invalid refresh token."}, status=401)

        user = request.user if request.user.is_authenticated else None
        if not user or user.id != payload.get("sub"):
            from apps.accounts.models import User
            user = User.objects.filter(id=payload.get("sub")).first()

        if not user:
            return Response({"error": "User not found."}, status=401)

        token_pair = create_token_pair(user)
        record_access_session(user, token_pair.access_jti, token_pair.access_expires_at, request)

        return Response(
            {
                "accessToken": token_pair.access_token,
                "accessTokenExpiresAt": token_pair.access_expires_at.isoformat(),
                "refreshToken": token_pair.refresh_token,
                "refreshTokenExpiresAt": token_pair.refresh_expires_at.isoformat(),
            }
        )
