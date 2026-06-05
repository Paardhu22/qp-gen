from rest_framework.authentication import get_authorization_header
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import jwt

from apps.accounts.models import User
from apps.accounts.serializers import (
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    RefreshSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserSerializer,
)
from services.auth_service import authenticate_user, register_user
from services.email_service import send_password_reset_email, send_welcome_email
from services.jwt_service import (
    create_token_pair,
    decode_access_token,
    decode_refresh_token,
    record_access_session,
    revoke_access_token,
)
from services.password_reset_service import consume_reset_token, issue_reset_token


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = register_user(**serializer.validated_data)
        token_pair = create_token_pair(user)
        record_access_session(user, token_pair.access_jti, token_pair.access_expires_at, request)
        # Welcome email is best-effort — a transient mail failure must NEVER
        # abort the signup HTTP response. send_welcome_email already swallows
        # exceptions and logs them; we ignore the return value here.
        send_welcome_email(to_email=user.email, user_name=user.name)
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


class ForgotPasswordView(APIView):
    """Issue and email a reset-password token.

    Always returns 200 with the same generic message regardless of whether
    the email matches a real account — this prevents account-enumeration
    via the reset endpoint. The actual delivery (or non-delivery) is
    visible only to the legitimate account owner.
    """

    permission_classes = [AllowAny]

    GENERIC_OK = {
        "success": True,
        "message": (
            "If an account with that email exists, a password reset link "
            "has been sent."
        ),
    }

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        user = User.objects.filter(email=email).first()
        if user is None:
            return Response(self.GENERIC_OK)

        token = issue_reset_token(user)
        send_password_reset_email(
            to_email=user.email, token=token, user_name=user.name
        )
        return Response(self.GENERIC_OK)


class ResetPasswordView(APIView):
    """Consume a reset-password token and set the new password.

    Returns 400 with a single generic error on any failure so the API
    surface gives no hint about why a particular token was rejected
    (unknown, expired, already used, no matching local account).
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ok = consume_reset_token(
            token=serializer.validated_data["token"],
            new_password=serializer.validated_data["newPassword"],
        )
        if not ok:
            return Response(
                {
                    "error": (
                        "This password reset link is invalid or has expired. "
                        "Please request a new one."
                    )
                },
                status=400,
            )
        return Response({"success": True})


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


class VerifyPasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.accounts.models import Account
        password = request.data.get("password", "")
        account = Account.objects.filter(user=request.user, provider_id="email").first()
        if not account or not account.check_password(password):
            return Response({"error": "Incorrect password."}, status=400)
        return Response({"valid": True})


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        old_password = serializer.validated_data["oldPassword"]
        new_password = serializer.validated_data["newPassword"]

        from apps.accounts.models import Account
        account = Account.objects.filter(user=request.user, provider_id="email").first()
        if not account:
            return Response({"error": "Local account not found for this user."}, status=400)

        if not account.check_password(old_password):
            return Response({"error": "Incorrect current password."}, status=400)

        account.set_password(new_password)
        account.save(update_fields=["password"])

        return Response({"success": True})


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
