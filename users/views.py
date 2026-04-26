from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_date
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenBlacklistView,
)

from .serializers import UserSerializer, UserStatusSerializer
from .permissions import IsAdmin, IsCommander, IsOwnerOrCommander
from schedule.services import is_soldier_available
from duties.models import DutyType


User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user management.

    - list: only for commander/admin
    - retrieve: own profile for soldier, any for commander/admin
    - update: restricted fields for soldier
    - update_status: PATCH /users/{id}/update_status/
    - available: GET /users/available/?date=YYYY-MM-DD&duty_type_id=
    """

    serializer_class = UserSerializer
    queryset = User.objects.all()

    def get_permissions(self):
        if self.action in ["list", "create", "destroy"]:
            permission_classes = [IsAuthenticated & (IsAdmin | IsCommander)]
        elif self.action in ["retrieve", "update", "partial_update"]:
            permission_classes = [IsAuthenticated, IsOwnerOrCommander]
        else:
            permission_classes = [IsAuthenticated]
        return [perm() for perm in permission_classes]

    @action(detail=True, methods=["patch"], url_path="update_status")
    def update_status(self, request, pk=None):
        """
        Update status of a user.
        Soldier may change only own status.
        """
        user = self.get_object()
        if (
            request.user.role == User.Role.SOLDIER
            and request.user.pk != user.pk
        ):
            return Response(
                {"detail": "Soldier can change only own status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = UserStatusSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="available")
    def available(self, request):
        """Return soldiers available for specific date and duty type."""
        date_str = request.query_params.get("date")
        duty_type_id = request.query_params.get("duty_type_id")

        if not date_str:
            return Response(
                {"detail": "Parameter 'date' is required (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        date = parse_date(date_str)
        if not date:
            return Response(
                {"detail": "Invalid date format. Expected YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        duty_type = None
        if duty_type_id:
            try:
                duty_type = DutyType.objects.get(pk=duty_type_id)
            except DutyType.DoesNotExist:
                return Response(
                    {"detail": "Duty type not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        soldiers = User.objects.filter(role=User.Role.SOLDIER)
        available = [
            s for s in soldiers if is_soldier_available(s, date, duty_type=duty_type)
        ]
        serializer = self.get_serializer(available, many=True)
        return Response(serializer.data)


class MeView(APIView):
    """Return data of the current authenticated user."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class LoginView(TokenObtainPairView):
    """Obtain JWT access and refresh tokens."""


class RefreshView(TokenRefreshView):
    """Refresh JWT access token."""


class LogoutView(TokenBlacklistView):
    """Blacklist refresh token on logout."""

