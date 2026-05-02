from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional, Dict, List

from django.contrib.auth import get_user_model
from django.db.models import Count

from django.utils import timezone

from duties.models import DutyType, DutyInstance
from .models import ScheduleRule, ScheduleTemplate


User = get_user_model()


def users_same_platoon(a: User, b: User) -> bool:
    """True if both users belong to the same platoon (case-insensitive, trimmed)."""
    pa = (getattr(a, "platoon", None) or "").strip().lower()
    pb = (getattr(b, "platoon", None) or "").strip().lower()
    if not pa or not pb:
        return False
    return pa == pb


@dataclass
class GeneratedAssignment:
    """Result of generated assignment for a duty instance."""

    duty_instance: DutyInstance
    soldiers: list[User]


def _is_status_active_for_date(user: User, duty_date: date) -> bool:
    """
    Check if user's status allows duty on given date.
    Considers status_until for temporary statuses.
    """
    if user.status == User.Status.ACTIVE:
        return True
    if user.status_until and user.status_until < duty_date:
        return True
    return False


def _has_duty_on_date(user: User, duty_date: date) -> bool:
    """Check if user already has duty on given date."""
    return DutyInstance.objects.filter(
        date=duty_date,
        assigned_soldiers=user,
    ).exists()


def _has_duty_on_adjacent_day(user: User, duty_date: date) -> bool:
    """Check if user has duty the day before or after given date."""
    prev_day = duty_date - timedelta(days=1)
    next_day = duty_date + timedelta(days=1)
    return DutyInstance.objects.filter(
        date__in=[prev_day, next_day],
        assigned_soldiers=user,
    ).exists()


def is_soldier_available(
    soldier: User,
    duty_date: date,
    duty_type: Optional[DutyType] = None,
) -> bool:
    """
    Check if soldier can be assigned to duty on given date.

    Considers:
    - current status and status_until
    - existing duties on that date
    - active ScheduleRule entries
    """
    if not _is_status_active_for_date(soldier, duty_date):
        return False

    if _has_duty_on_date(soldier, duty_date):
        return False

    rules = ScheduleRule.objects.filter(is_active=True)

    # Max duties per month
    max_rule = rules.filter(
        rule_type=ScheduleRule.RuleType.MAX_DUTIES_PER_MONTH
    ).first()
    if max_rule:
        month_start = duty_date.replace(day=1)
        # Next month start
        if duty_date.month == 12:
            next_month_start = duty_date.replace(year=duty_date.year + 1, month=1, day=1)
        else:
            next_month_start = duty_date.replace(month=duty_date.month + 1, day=1)
        count = DutyInstance.objects.filter(
            date__gte=month_start,
            date__lt=next_month_start,
            assigned_soldiers=soldier,
        ).count()
        if count >= max_rule.value:
            return False

    # Avoid consecutive days
    avoid_rule = rules.filter(
        rule_type=ScheduleRule.RuleType.AVOID_CONSECUTIVE_DAYS
    ).first()
    if avoid_rule and _has_duty_on_adjacent_day(soldier, duty_date):
        return False

    # Weekend rotation is applied in generate_schedule when choosing candidates.

    # Special skills could be checked here if soldiers had explicit skills.
    if duty_type and duty_type.requires_special_skill and duty_type.special_skill_code:
        # For now, there is no explicit soldier skill model, so we cannot match.
        # Reject such duties to avoid invalid assignment.
        return False

    return True


def generate_schedule(
    start_date: date,
    end_date: date,
    duty_types: Iterable[DutyType],
    soldiers: Optional[Iterable[User]] = None,
    create_instances: bool = True,
) -> Dict[str, List[Dict[str, list[int]]]]:
    """
    Generate schedule for given period and duty types.

    Args:
        start_date: period start date (inclusive).
        end_date: period end date (inclusive).
        duty_types: iterable of DutyType to schedule.
        soldiers: optional iterable of User (soldiers) to consider.
        create_instances: create DutyInstance objects if True.

    Returns:
        Dict with structure:
        {
          "assignments": [
            {"duty_instance_id": int, "soldier_ids": [int, ...]},
            ...
          ]
        }
    """
    if start_date > end_date:
        raise ValueError("start_date must be before or equal to end_date")

    today = timezone.localdate()
    if start_date < today or end_date < today:
        raise ValueError("Schedule period cannot be in the past.")

    if soldiers is None:
        soldiers_qs = User.objects.filter(role=User.Role.SOLDIER)
    else:
        soldiers_qs = User.objects.filter(id__in=[s.id for s in soldiers])

    rules = ScheduleRule.objects.filter(is_active=True)
    weekend_rule = rules.filter(
        rule_type=ScheduleRule.RuleType.WEEKEND_ROTATION
    ).first()

    current = start_date
    assignments: list[dict] = []

    while current <= end_date:
        is_weekend = current.weekday() >= 5

        for duty_type in duty_types:
            required = duty_type.required_soldiers
            if required <= 0:
                continue

            available_candidates = [
                s
                for s in soldiers_qs
                if is_soldier_available(s, current, duty_type=duty_type)
            ]

            if not available_candidates:
                continue

            # Order by duty_count_this_month and optionally by weekend load.
            def sort_key(user: User):
                base = user.duty_count_this_month
                if is_weekend and weekend_rule:
                    weekend_duties = DutyInstance.objects.filter(
                        date__week_day__in=[1, 7],  # Sunday=1, Saturday=7 in Django
                        assigned_soldiers=user,
                    ).count()
                    return (base, weekend_duties)
                return (base,)

            ordered = sorted(available_candidates, key=sort_key)
            chosen = ordered[:required]
            if not chosen:
                continue

            # Create or get duty instance
            start_time = duty_type.start_time or timezone.now().time()
            end_time = duty_type.end_time or timezone.now().time()

            instance = None
            if create_instances:
                instance, _ = DutyInstance.objects.get_or_create(
                    duty_type=duty_type,
                    date=current,
                    defaults={
                        "start_time": start_time,
                        "end_time": end_time,
                        "status": DutyInstance.Status.SCHEDULED,
                    },
                )
                instance.assigned_soldiers.add(*chosen)
                # Update counters
                for soldier in chosen:
                    soldier.duty_count_this_month += 1
                    soldier.save(update_fields=["duty_count_this_month"])

            assignments.append(
                {
                    "duty_type_id": duty_type.id,
                    "date": current.isoformat(),
                    "duty_instance_id": instance.id if instance else None,
                    "soldier_ids": [s.id for s in chosen],
                }
            )

        current += timedelta(days=1)

    return {"assignments": assignments}


def generate_from_template(
    start_date: date,
    end_date: date,
    template: ScheduleTemplate,
    validate_not_past: bool = True,
) -> list[DutyInstance]:
    """
    Generate duty instances from weekly template rules.

    For each date in range:
    - resolve weekday (0=Monday ... 6=Sunday)
    - create DutyInstance per duty_type_id from template.rules[weekday]
    - if weekday key is missing, skip day
    """
    if start_date > end_date:
        raise ValueError("start_date must be before or equal to end_date")

    today = timezone.localdate()
    if validate_not_past and (start_date < today or end_date < today):
        raise ValueError("Schedule period cannot be in the past.")

    current = start_date
    created_instances: list[DutyInstance] = []
    rules = ScheduleRule.objects.filter(is_active=True)
    weekend_rule = rules.filter(
        rule_type=ScheduleRule.RuleType.WEEKEND_ROTATION
    ).first()
    soldiers_qs = User.objects.filter(role=User.Role.SOLDIER)

    while current <= end_date:
        weekday = str(current.weekday())
        duty_type_ids = template.rules.get(weekday, [])
        if not isinstance(duty_type_ids, list):
            raise ValueError(f"Invalid template.rules format for weekday {weekday}.")

        duty_types_by_id = {
            duty_type.id: duty_type
            for duty_type in DutyType.objects.filter(id__in=duty_type_ids, is_active=True)
        }
        missing_ids = set(duty_type_ids) - set(duty_types_by_id.keys())
        if missing_ids:
            raise ValueError(
                f"Template references missing or inactive duty types: {sorted(missing_ids)}."
            )

        for duty_type_id in duty_type_ids:
            duty_type = duty_types_by_id[duty_type_id]
            start_time = duty_type.start_time or timezone.now().time()
            end_time = duty_type.end_time or timezone.now().time()
            instance = DutyInstance.objects.create(
                duty_type=duty_type,
                date=current,
                start_time=start_time,
                end_time=end_time,
                status=DutyInstance.Status.SCHEDULED,
            )

            # Assign soldiers with the same availability/rule checks as regular generation.
            required = duty_type.required_soldiers
            if required > 0:
                available_candidates = [
                    s
                    for s in soldiers_qs
                    if is_soldier_available(s, current, duty_type=duty_type)
                ]

                if available_candidates:
                    is_weekend = current.weekday() >= 5

                    def sort_key(user: User):
                        base = user.duty_count_this_month
                        if is_weekend and weekend_rule:
                            weekend_duties = DutyInstance.objects.filter(
                                date__week_day__in=[1, 7],
                                assigned_soldiers=user,
                            ).count()
                            return (base, weekend_duties)
                        return (base,)

                    chosen = sorted(available_candidates, key=sort_key)[:required]
                    if chosen:
                        instance.assigned_soldiers.add(*chosen)
                        for soldier in chosen:
                            soldier.duty_count_this_month += 1
                            soldier.save(update_fields=["duty_count_this_month"])

            created_instances.append(instance)

        current += timedelta(days=1)

    return created_instances

