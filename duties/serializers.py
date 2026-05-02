from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers

from users.validators import validate_date_not_before_today

from .models import DutyType, DutyInstance
from schedule.models import ScheduleRule


User = get_user_model()


class DutyTypeSerializer(serializers.ModelSerializer):
    """Serializer for duty types."""

    class Meta:
        model = DutyType
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        inst = self.instance
        start = attrs["start_time"] if "start_time" in attrs else (
            inst.start_time if inst else None
        )
        end = attrs["end_time"] if "end_time" in attrs else (
            inst.end_time if inst else None
        )
        if start is not None and end is not None and end <= start:
            raise serializers.ValidationError(
                {"end_time": "end_time must be after start_time."}
            )
        return attrs


class DutyInstanceSerializer(serializers.ModelSerializer):
    """Serializer for duty instances."""

    duty_type = DutyTypeSerializer(read_only=True)
    duty_type_id = serializers.PrimaryKeyRelatedField(
        queryset=DutyType.objects.all(),
        source="duty_type",
        write_only=True,
    )
    assigned_soldiers_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        source="assigned_soldiers",
        queryset=User.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = DutyInstance
        fields = [
            "id",
            "duty_type",
            "duty_type_id",
            "date",
            "start_time",
            "end_time",
            "assigned_soldiers",
            "assigned_soldiers_ids",
            "status",
            "notes",
        ]
        read_only_fields = ["id", "assigned_soldiers"]

    def validate_date(self, value):
        return validate_date_not_before_today(value, label="Duty date")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        inst = self.instance
        start = attrs["start_time"] if "start_time" in attrs else (
            inst.start_time if inst else None
        )
        end = attrs["end_time"] if "end_time" in attrs else (
            inst.end_time if inst else None
        )
        if start is not None and end is not None and end <= start:
            raise serializers.ValidationError(
                {"end_time": "end_time must be after start_time."}
            )

        assigned_soldiers = attrs.get("assigned_soldiers")
        if assigned_soldiers is None:
            return attrs

        duty_date = attrs.get("date") or (self.instance.date if self.instance else None)
        if duty_date is None:
            raise serializers.ValidationError({"date": "Duty date is required."})

        duty_type = attrs.get("duty_type") or (self.instance.duty_type if self.instance else None)
        if duty_type is None:
            raise serializers.ValidationError({"duty_type_id": "Duty type is required."})

        current_instance_id = self.instance.id if self.instance else None
        errors = []
        max_rule = ScheduleRule.objects.filter(
            is_active=True,
            rule_type=ScheduleRule.RuleType.MAX_DUTIES_PER_MONTH,
        ).first()
        avoid_rule = ScheduleRule.objects.filter(
            is_active=True,
            rule_type=ScheduleRule.RuleType.AVOID_CONSECUTIVE_DAYS,
        ).first()

        if duty_date.month == 12:
            next_month_start = duty_date.replace(year=duty_date.year + 1, month=1, day=1)
        else:
            next_month_start = duty_date.replace(month=duty_date.month + 1, day=1)
        month_start = duty_date.replace(day=1)

        for soldier in assigned_soldiers:
            if soldier.role != User.Role.SOLDIER:
                errors.append(
                    f"User '{soldier.username}' must have role 'soldier' to be assigned."
                )
                continue

            has_same_day_duty = DutyInstance.objects.filter(
                date=duty_date,
                assigned_soldiers=soldier,
            ).exclude(id=current_instance_id).exists()
            if has_same_day_duty:
                errors.append(
                    f"Soldier '{soldier.username}' already has a duty on this date."
                )
                continue

            if max_rule:
                month_count = DutyInstance.objects.filter(
                    date__gte=month_start,
                    date__lt=next_month_start,
                    assigned_soldiers=soldier,
                ).exclude(id=current_instance_id).count()
                if month_count >= max_rule.value:
                    errors.append(
                        f"Soldier '{soldier.username}' reached max duties per month."
                    )
                    continue

            if avoid_rule:
                has_adjacent_duty = DutyInstance.objects.filter(
                    assigned_soldiers=soldier,
                ).filter(
                    Q(date=duty_date - timedelta(days=1))
                    | Q(date=duty_date + timedelta(days=1))
                ).exclude(id=current_instance_id).exists()
                if has_adjacent_duty:
                    errors.append(
                        f"Soldier '{soldier.username}' has duty on an adjacent day."
                    )

        if errors:
            raise serializers.ValidationError({"assigned_soldiers_ids": errors})

        return attrs
