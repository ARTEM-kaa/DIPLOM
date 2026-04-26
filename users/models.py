from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model with military-specific fields."""

    class Role(models.TextChoices):
        SOLDIER = "soldier", "Soldier"
        COMMANDER = "commander", "Commander"
        ADMIN = "admin", "Admin"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SICK = "sick", "Sick"
        VACATION = "vacation", "Vacation"
        BUSINESS_TRIP = "business_trip", "Business trip"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.SOLDIER,
    )
    military_rank = models.CharField(max_length=255)
    platoon = models.CharField(max_length=255)
    scientific_supervisor = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    research_topic = models.TextField(null=True, blank=True)
    phone_number = models.CharField(max_length=32, null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    status_until = models.DateField(null=True, blank=True)

    duty_count_this_month = models.IntegerField(default=0)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.username} ({self.get_full_name()})"

