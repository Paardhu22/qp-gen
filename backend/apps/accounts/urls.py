from django.urls import path

from .views import CsrfView, LoginView, LogoutView, MeView, RegisterView

urlpatterns = [
    path("csrf", CsrfView.as_view(), name="csrf"),
    path("register", RegisterView.as_view(), name="register"),
    path("login", LoginView.as_view(), name="login"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("me", MeView.as_view(), name="me"),
]
