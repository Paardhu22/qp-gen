from django.urls import path

from .views import LoginView, LogoutView, MeView, RefreshView, RegisterView

urlpatterns = [
    path("register", RegisterView.as_view(), name="register"),
    path("login", LoginView.as_view(), name="login"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("me", MeView.as_view(), name="me"),
    path("dashboard", MeView.as_view(), name="dashboard"),
    path("refresh", RefreshView.as_view(), name="refresh"),
]
