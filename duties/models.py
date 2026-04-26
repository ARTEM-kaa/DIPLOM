from django.conf import settings
from django.db import models


class DutyType(models.Model):
    """Type of duty, e.g. 'Дневальный по роте'."""

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=64, unique=True)
    description = models.TextField(null=True, blank=True)
    required_soldiers = models.PositiveIntegerField()
    requires_special_skill = models.BooleanField(default=False)
    special_skill_code = models.CharField(max_length=64, null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


class DutyInstance(models.Model):
    """Concrete duty instance on a specific date."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        ONGOING = "ongoing", "Ongoing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    duty_type = models.ForeignKey(DutyType, on_delete=models.CASCADE)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    assigned_soldiers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="duties",
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    notes = models.TextField(null=True, blank=True)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.duty_type} on {self.date}"

