from rest_framework.authentication import SessionAuthentication

from apps.accounts.models import User


class AppSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        user_id = request.session.get("app_user_id")
        if not user_id:
            return None

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

        self.enforce_csrf(request)
        return (user, None)
