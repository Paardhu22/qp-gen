from django.middleware.csrf import get_token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAppUserAuthenticated
from apps.accounts.serializers import LoginSerializer, RegisterSerializer, UserSerializer
from services.auth_service import authenticate_user, register_user


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = register_user(**serializer.validated_data)
        request.session["app_user_id"] = user.id
        return Response(UserSerializer(user).data, status=201)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate_user(**serializer.validated_data)
        request.session["app_user_id"] = user.id
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAppUserAuthenticated]

    def post(self, request):
        request.session.flush()
        return Response({"success": True})


class MeView(APIView):
    permission_classes = [IsAppUserAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class CsrfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        token = get_token(request)
        return Response({"csrfToken": token})
