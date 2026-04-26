import os
import sys
from pathlib import Path
import django
from django.utils import timezone
from datetime import timedelta


def setup_django():
    """Configure Django settings for standalone script."""
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()


def run():
    """Seed database with demo data."""
    from django.contrib.auth import get_user_model
    from duties.models import DutyType, DutyInstance
    from schedule.models import ReplacementRequest, ScheduleRule

    User = get_user_model()

    # Officers
    officers = []
    for i in range(1, 4):
        officer, _ = User.objects.get_or_create(
            username=f"commander{i}",
            defaults={
                "role": User.Role.COMMANDER,
                "military_rank": "Captain",
                "platoon": f"Platoon-{i}",
                "first_name": f"Commander{i}",
                "last_name": "Test",
            },
        )
        officers.append(officer)

    # Soldiers
    soldiers = []
    for i in range(1, 31):
        platoon = f"Platoon-{(i % 3) + 1}"
        soldier, _ = User.objects.get_or_create(
            username=f"soldier{i}",
            defaults={
                "role": User.Role.SOLDIER,
                "military_rank": "Private",
                "platoon": platoon,
                "first_name": f"Soldier{i}",
                "last_name": "Test",
                "scientific_supervisor": f"Supervisor {i}",
                "research_topic": f"Research topic {i}",
            },
        )
        soldiers.append(soldier)

    # Duty types
    duty_types_data = [
        ("Дневальный по роте", "day_room"),
        ("Караул", "guard"),
        ("Наряд по кухне", "kitchen"),
        ("Наряд по парку", "park"),
        ("Офицер дежурный", "officer"),
    ]
    duty_types = []
    for name, code in duty_types_data:
        duty_type, _ = DutyType.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "required_soldiers": 2,
                "requires_special_skill": False,
                "is_active": True,
            },
        )
        duty_types.append(duty_type)

    # Schedule rules
    ScheduleRule.objects.get_or_create(
        rule_type=ScheduleRule.RuleType.MAX_DUTIES_PER_MONTH,
        defaults={"name": "Max 5 duties per month", "value": 5, "is_active": True},
    )
    ScheduleRule.objects.get_or_create(
        rule_type=ScheduleRule.RuleType.AVOID_CONSECUTIVE_DAYS,
        defaults={"name": "Avoid consecutive duties", "value": 1, "is_active": True},
    )

    # Duties for current month
    today = timezone.localdate()
    start_of_month = today.replace(day=1)
    for i in range(5):
        duty_date = start_of_month + timedelta(days=i)
        for duty_type in duty_types[:3]:
            duty_instance, _ = DutyInstance.objects.get_or_create(
                duty_type=duty_type,
                date=duty_date,
                defaults={
                    "start_time": timezone.now().time(),
                    "end_time": (timezone.now() + timedelta(hours=4)).time(),
                    "status": DutyInstance.Status.SCHEDULED,
                },
            )
            duty_instance.assigned_soldiers.set(soldiers[i : i + duty_type.required_soldiers])

    # Replacement requests with different statuses
    if DutyInstance.objects.exists():
        duty = DutyInstance.objects.first()
        requester = duty.assigned_soldiers.first()
        replacement = soldiers[-1]

        pending, _ = ReplacementRequest.objects.get_or_create(
            duty_instance=duty,
            requester=requester,
            requested_replacement=replacement,
            reason="Болен",
        )

        approved, _ = ReplacementRequest.objects.get_or_create(
            duty_instance=duty,
            requester=requester,
            requested_replacement=replacement,
            reason="Учёба",
            status=ReplacementRequest.Status.APPROVED,
        )

        rejected, _ = ReplacementRequest.objects.get_or_create(
            duty_instance=duty,
            requester=requester,
            requested_replacement=replacement,
            reason="Личные дела",
            status=ReplacementRequest.Status.REJECTED,
        )

    print("Seeding completed.")


if __name__ == "__main__":
    setup_django()
    run()

