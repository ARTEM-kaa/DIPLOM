from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from duties.models import DutyInstance
from duties.serializers import DutyInstanceSerializer
from users.permissions import (
    IsAdmin,
    IsCommander,
    IsCommanderOrAdmin,
    IsOwnerOrCommander,
)
from .models import ReplacementRequest, ScheduleRule, ScheduleTemplate
from .serializers import (
    GenerateFromTemplateSerializer,
    ReplacementRequestSerializer,
    ReplacementRequestCreateSerializer,
    ScheduleRuleSerializer,
    ScheduleTemplateSerializer,
)
from .services import (
    generate_from_template as generate_from_template_service,
    is_soldier_available,
    users_same_platoon,
)

User = get_user_model()


class ReplacementRequestViewSet(viewsets.ModelViewSet):
    """
    Handle replacement requests.

    Replacement target must be a soldier from the same platoon as the requester
    (platoon rule: admins exempt).

    Custom routes:
    - POST /replacements/request/
    - GET /replacements/pending/ — incoming requests for soldier (replacement)
    - GET /replacements/pending-commander/ — awaits commander approval
    - PUT /replacements/{id}/respond/ — soldier approves/rejects (no swap yet)
    - PUT /replacements/{id}/commander-review/ — commander approves (swap) or rejects
    - PUT /replacements/{id}/cancel/
    """

    queryset = ReplacementRequest.objects.select_related(
        "duty_instance",
        "requester",
        "requested_replacement",
    ).all()
    serializer_class = ReplacementRequestSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrCommander]

    def get_serializer_class(self):
        if self.action == "request_replacement":
            return ReplacementRequestCreateSerializer
        return super().get_serializer_class()

    @extend_schema(exclude=True)
    def create(self, request, *args, **kwargs):
        return Response(
            {
                "detail": "Use POST /api/v1/replacements/request/ to create a replacement request."
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @extend_schema(exclude=True)
    def partial_update(self, request, *args, **kwargs):
        return Response(
            {"detail": "PATCH is not supported for replacement requests."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=False, methods=["post"], url_path="request")
    def request_replacement(self, request):
        """Create replacement request."""
        serializer = ReplacementRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        duty_instance = serializer.validated_data["duty_instance"]
        requested_replacement = serializer.validated_data["requested_replacement"]

        # Only soldiers assigned to duty can request replacement
        if request.user not in duty_instance.assigned_soldiers.all():
            return Response(
                {"detail": "Only assigned soldier can request replacement."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if getattr(request.user, "role", None) != User.Role.ADMIN:
            if not users_same_platoon(request.user, requested_replacement):
                return Response(
                    {
                        "detail": (
                            "Replacement soldier must be from the same platoon as you."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if getattr(requested_replacement, "role", None) != User.Role.SOLDIER:
            return Response(
                {
                    "detail": (
                        "Replacement must be a soldier; commanders and admins "
                        "cannot be assigned as replacement."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check availability of requested replacement
        if not is_soldier_available(requested_replacement, duty_instance.date):
            return Response(
                {"detail": "Requested replacement soldier is not available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        replacement_request = ReplacementRequest.objects.create(
            duty_instance=duty_instance,
            requester=request.user,
            requested_replacement=requested_replacement,
            reason=serializer.validated_data["reason"],
        )
        out = ReplacementRequestSerializer(replacement_request)
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="pending")
    def pending(self, request):
        """Pending incoming replacement requests for current user."""
        qs = self.get_queryset().filter(
            requested_replacement=request.user,
            status=ReplacementRequest.Status.PENDING,
        )
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        url_path="pending-commander",
        permission_classes=[IsAuthenticated, IsCommanderOrAdmin],
    )
    def pending_commander(self, request):
        """Replacement requests waiting for commander after both soldiers agreed."""
        qs = self.get_queryset().filter(
            status=ReplacementRequest.Status.PENDING_COMMANDER,
        )
        role = getattr(request.user, "role", None)
        if role != User.Role.ADMIN:
            # Requests are same-platoon only; commander sees their platoon's queue.
            platoon = (getattr(request.user, "platoon", "") or "").strip()
            if not platoon:
                return Response(
                    {
                        "detail": (
                            "Set platoon on your profile to list pending replacement "
                            "requests."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(requester__platoon__iexact=platoon)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["put"], url_path="respond")
    def respond(self, request, pk=None):
        """
        Requested soldier approves or rejects. Approve moves to commander
        pending (no roster change yet). Body: { "action": "approve" | "reject" }
        """
        replacement_request = self.get_object()
        action_value = request.data.get("action")
        if (
            replacement_request.status
            != ReplacementRequest.Status.PENDING
        ):
            return Response(
                {"detail": "Request already processed or cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if replacement_request.requested_replacement != request.user:
            return Response(
                {"detail": "Only requested replacement can respond."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if action_value == "approve":
            replacement_request.status = (
                ReplacementRequest.Status.PENDING_COMMANDER
            )
            replacement_request.soldier_accepted_at = timezone.now()
        elif action_value == "reject":
            replacement_request.status = ReplacementRequest.Status.REJECTED
            replacement_request.processed_at = timezone.now()
            replacement_request.processed_by = request.user
        else:
            return Response(
                {"detail": "Invalid action. Use 'approve' or 'reject'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        replacement_request.save()
        serializer = self.get_serializer(replacement_request)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["put"],
        url_path="commander-review",
        permission_classes=[IsAuthenticated, IsCommanderOrAdmin],
    )
    def commander_review(self, request, pk=None):
        """
        Commander/admin final approval: swap roster on approve or reject request.
        Body: { "action": "approve" | "reject" }
        """
        replacement_request = self.get_object()
        if (
            replacement_request.status
            != ReplacementRequest.Status.PENDING_COMMANDER
        ):
            return Response(
                {
                    "detail": "Replacement is not waiting for commander approval."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if getattr(request.user, "role", None) != User.Role.ADMIN:
            platoon_relevant = (getattr(request.user, "platoon", "") or "").strip()
            if not platoon_relevant:
                return Response(
                    {
                        "detail": (
                            "Set platoon on your profile before approving replacements."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            req_p = (replacement_request.requester.platoon or "").strip().lower()
            pr = platoon_relevant.lower()
            if req_p != pr:
                return Response(
                    {"detail": "Not your platoon's replacement request."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        action_value = request.data.get("action")
        now = timezone.now()
        if action_value == "approve":
            with transaction.atomic():
                locked = ReplacementRequest.objects.select_for_update().get(
                    pk=replacement_request.pk
                )
                if locked.status != ReplacementRequest.Status.PENDING_COMMANDER:
                    return Response(
                        {
                            "detail": (
                                "Replacement is not waiting for commander approval."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                locked.status = ReplacementRequest.Status.APPROVED
                duty = locked.duty_instance
                duty.assigned_soldiers.remove(locked.requester)
                duty.assigned_soldiers.add(locked.requested_replacement)
                duty.save()
                locked.processed_at = now
                locked.processed_by = request.user
                locked.save(
                    update_fields=["status", "processed_at", "processed_by"]
                )
            replacement_request.refresh_from_db()
        elif action_value == "reject":
            replacement_request.status = ReplacementRequest.Status.REJECTED
            replacement_request.processed_at = now
            replacement_request.processed_by = request.user
            replacement_request.save(
                update_fields=["status", "processed_at", "processed_by"]
            )
        else:
            return Response(
                {"detail": "Invalid action. Use 'approve' or 'reject'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(replacement_request)
        return Response(serializer.data)

    @action(detail=True, methods=["put"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancel own replacement request."""
        replacement_request = self.get_object()
        if replacement_request.requester != request.user:
            return Response(
                {"detail": "Only requester can cancel the request."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if replacement_request.status not in (
            ReplacementRequest.Status.PENDING,
            ReplacementRequest.Status.PENDING_COMMANDER,
        ):
            return Response(
                {
                    "detail": "Only open requests can be cancelled (before commander decision)."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        replacement_request.status = ReplacementRequest.Status.CANCELLED
        replacement_request.save()
        serializer = self.get_serializer(replacement_request)
        return Response(serializer.data)


class ScheduleRuleViewSet(viewsets.ModelViewSet):
    """CRUD for schedule rules (admin/commander)."""

    queryset = ScheduleRule.objects.all()
    serializer_class = ScheduleRuleSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [IsAuthenticated()]
        if self.action in ["create", "destroy"]:
            return [IsAdmin()]
        return [IsAuthenticated(), (IsCommander | IsAdmin)()]

    def _validate_commander_rule_update(self, request):
        if getattr(request.user, "role", None) == "admin":
            return None

        rule = self.get_object()
        attempted_fields = set(request.data.keys())
        allowed_fields = {"name", "value", "is_active", "rule_type"}
        forbidden_fields = attempted_fields - allowed_fields
        if forbidden_fields:
            return Response(
                {"detail": "Commander can update only name, value and is_active."},
                status=status.HTTP_403_FORBIDDEN,
            )

        requested_rule_type = request.data.get("rule_type")
        if requested_rule_type is not None and requested_rule_type != rule.rule_type:
            return Response(
                {"detail": "Commander can update only name, value and is_active."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def update(self, request, *args, **kwargs):
        denied = self._validate_commander_rule_update(request)
        if denied:
            return denied
        if getattr(request.user, "role", None) != "admin":
            instance = self.get_object()
            mutable_data = request.data.copy()
            mutable_data["rule_type"] = instance.rule_type
            serializer = self.get_serializer(instance, data=mutable_data)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        denied = self._validate_commander_rule_update(request)
        if denied:
            return denied
        return super().partial_update(request, *args, **kwargs)


class ScheduleTemplateViewSet(viewsets.ModelViewSet):
    """CRUD for schedule templates."""

    queryset = ScheduleTemplate.objects.all().order_by("-id")
    serializer_class = ScheduleTemplateSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        return [IsAuthenticated(), (IsCommander | IsAdmin)()]


class ScheduleViewSet(viewsets.ViewSet):
    """
    Read-only schedule views:

    - /schedule/calendar/?month=YYYY-MM&platoon=
    - /schedule/week/?date=YYYY-MM-DD
    - /schedule/stats/
    """

    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action == "generate_from_template":
            return [IsAuthenticated(), (IsCommander | IsAdmin)()]
        return [IsAuthenticated()]

    @action(detail=False, methods=["get"], url_path="calendar")
    def calendar(self, request):
        """Calendar view for a month and optional platoon."""
        month_str = request.query_params.get("month")
        platoon = request.query_params.get("platoon")
        if not month_str:
            return Response(
                {"detail": "Parameter 'month' is required (YYYY-MM)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            month_date = datetime.strptime(month_str, "%Y-%m")
        except ValueError:
            return Response(
                {"detail": "Invalid month format. Use YYYY-MM."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        month_start = month_date.date().replace(day=1)
        if month_start.month == 12:
            next_month_start = month_start.replace(
                year=month_start.year + 1,
                month=1,
                day=1,
            )
        else:
            next_month_start = month_start.replace(
                month=month_start.month + 1,
                day=1,
            )
        qs = DutyInstance.objects.filter(
            date__gte=month_start,
            date__lt=next_month_start,
        )
        if platoon:
            qs = qs.filter(assigned_soldiers__platoon=platoon)

        data = {}
        for duty in qs.select_related("duty_type").prefetch_related("assigned_soldiers"):
            day_key = duty.date.isoformat()
            data.setdefault(day_key, [])
            data[day_key].append(
                {
                    "id": duty.id,
                    "duty_type": duty.duty_type.name,
                    "status": duty.status,
                    "assigned_soldiers": [
                        s.id for s in duty.assigned_soldiers.all()
                    ],
                }
            )
        return Response(data)

    @action(detail=False, methods=["get"], url_path="week")
    def week(self, request):
        """Schedule for week starting from given date."""
        date_str = request.query_params.get("date")
        if not date_str:
            return Response(
                {"detail": "Parameter 'date' is required (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        start_date = parse_date(date_str)
        if not start_date:
            return Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        end_date = start_date + timedelta(days=6)
        qs = DutyInstance.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
        ).select_related("duty_type")
        data = {}
        for duty in qs.prefetch_related("assigned_soldiers"):
            day_key = duty.date.isoformat()
            data.setdefault(day_key, [])
            data[day_key].append(
                {
                    "id": duty.id,
                    "duty_type": duty.duty_type.name,
                    "status": duty.status,
                    "assigned_soldiers": [
                        s.id for s in duty.assigned_soldiers.all()
                    ],
                }
            )
        return Response(data)

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """Statistics: number of duties per soldier."""
        stats_qs = (
            DutyInstance.objects.values("assigned_soldiers")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        result = [
            {"user_id": item["assigned_soldiers"], "duties_count": item["count"]}
            for item in stats_qs
            if item["assigned_soldiers"] is not None
        ]
        return Response(result)

    @extend_schema(
        methods=["POST"],
        request=GenerateFromTemplateSerializer,
        responses={201: DutyInstanceSerializer},
    )
    @action(detail=False, methods=["post"], url_path="generate-from-template")
    def generate_from_template(self, request):
        """
        Generate duties from schedule template.

        Body: {
          "start_date": "YYYY-MM-DD",
          "end_date": "YYYY-MM-DD",
          "template_id": 1  # optional
        }
        """
        serializer = GenerateFromTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        template_id = validated.get("template_id")
        if template_id is not None:
            template = ScheduleTemplate.objects.filter(id=template_id).first()
            if template is None:
                return Response(
                    {"detail": "Template not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            template = ScheduleTemplate.objects.filter(is_default=True).first()
            if template is None:
                return Response(
                    {"detail": "Default template not found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            created_instances = generate_from_template_service(
                start_date=validated["start_date"],
                end_date=validated["end_date"],
                template=template,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        result_serializer = DutyInstanceSerializer(created_instances, many=True)
        return Response(
            {
                "template_id": template.id,
                "created_count": len(created_instances),
                "duties": result_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

