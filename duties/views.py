from datetime import datetime

from django.utils.dateparse import parse_date
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.permissions import IsAdmin, CanManageDuties
from .models import DutyType, DutyInstance
from .serializers import DutyTypeSerializer, DutyInstanceSerializer
from schedule.services import generate_schedule


class DutyTypeViewSet(viewsets.ModelViewSet):
    """CRUD for duty types."""

    queryset = DutyType.objects.all()
    serializer_class = DutyTypeSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [IsAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        if self.action == "list":
            return DutyType.objects.filter(is_active=True)
        return DutyType.objects.all()


class DutyInstanceViewSet(viewsets.ModelViewSet):
    """
    CRUD and extra actions for duty instances.

    - /duties/ - list with filters
    - /duties/my/ - current user's duties
    - /duties/platoon/ - duties of user's platoon
    - /duties/generate/ - run schedule generation
    """

    queryset = DutyInstance.objects.select_related("duty_type").all()
    serializer_class = DutyInstanceSerializer
    permission_classes = [IsAuthenticated, CanManageDuties]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["date", "duty_type", "status"]

    def get_permissions(self):
        if self.action in ["list", "retrieve", "my", "platoon"]:
            return [IsAuthenticated()]
        return [CanManageDuties()]

    @action(detail=False, methods=["get"], url_path="my")
    def my(self, request):
        """Return duties assigned to current user."""
        qs = self.get_queryset().filter(assigned_soldiers=request.user)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="platoon")
    def platoon(self, request):
        """Return duties for user's platoon."""
        qs = self.get_queryset().filter(
            assigned_soldiers__platoon=request.user.platoon
        ).distinct()
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request):
        """
        Generate schedule for given period and duty types.

        Body: {
          "start_date": "YYYY-MM-DD",
          "end_date": "YYYY-MM-DD",
          "duty_type_ids": [1,2,3]
        }
        """
        start_date_str = request.data.get("start_date")
        end_date_str = request.data.get("end_date")
        duty_type_ids = request.data.get("duty_type_ids", [])

        if not (start_date_str and end_date_str and duty_type_ids):
            return Response(
                {
                    "detail": "start_date, end_date and duty_type_ids are required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
        if not (start_date and end_date):
            return Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        duty_types = list(DutyType.objects.filter(id__in=duty_type_ids, is_active=True))
        if not duty_types:
            return Response(
                {"detail": "No active duty types found for given ids."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = generate_schedule(start_date, end_date, duty_types)
        return Response(result, status=status.HTTP_201_CREATED)

