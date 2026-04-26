from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import UserViewSet, MeView, LoginView, RefreshView, LogoutView


router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")


urlpatterns = [
    # Auth endpoints
    path("auth/login/", LoginView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", RefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", LogoutView.as_view(), name="token_blacklist"),
    path("auth/me/", MeView.as_view(), name="auth_me"),
    # Users
    path("", include(router.urls)),
]

