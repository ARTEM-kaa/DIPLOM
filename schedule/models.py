from django.conf import settings
from django.db import models
from django.utils import timezone

from duties.models import DutyInstance


class ReplacementRequest(models.Model):
    """Request to replace a duty."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    duty_instance = models.ForeignKey(
        DutyInstance,
        on_delete=models.CASCADE,
        related_name="replacement_requests",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="requested_replacements",
    )
    requested_replacement = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="replacement_requests_received",
    )
    reason = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_replacements",
    )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Replacement for {self.duty_instance} by {self.requester}"


class ScheduleRule(models.Model):
    """Rules used by schedule generation algorithm."""

    class RuleType(models.TextChoices):
        MAX_DUTIES_PER_MONTH = "max_duties_per_month", "Max duties per month"
        AVOID_CONSECUTIVE_DAYS = "avoid_consecutive_days", "Avoid consecutive days"
        WEEKEND_ROTATION = "weekend_rotation", "Weekend rotation"

    name = models.CharField(max_length=255)
    rule_type = models.CharField(
        max_length=64,
        choices=RuleType.choices,
    )
    value = models.IntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name

